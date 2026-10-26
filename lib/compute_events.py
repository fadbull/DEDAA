"""Tab 3 Event-Driven Analytics (bug triggers, auto-transit, cohorts)."""
from collections import Counter, defaultdict
from datetime import datetime
import json
from .date_utils import _dt_full, _biweek, status_group, _status_events_from_text

# ============================================================================
# Event-Driven Analytics (Tab 3) — advanced event/trigger analysis
# ----------------------------------------------------------------------------
# Module 1: Bug-creation triggers (parent issue status at the moment a Bug /
#           Sub-Bug was created).
# Module 2: Auto-transit / Parent-Child sync (how quickly a parent follows its
#           last closed child — automation-rule vs manual-leakage detection).
# Module 3: Metadata impact (labels/custom fields vs median cycle time and
#           ping-pong rate vs the project baseline).
# ============================================================================

# A status-transition is classified as an "automation trigger" if the parent
# changes status within this many seconds of its last child closing.
AUTO_TRIGGER_WINDOW_SEC = 300


def _parent_status_at(events, moment):
    """Given a parent's sorted status-change events [(dt, to_status)] and a
    moment, return the status the parent was in at that moment (the last event
    whose time <= moment). If no transition happened before 'moment', default
    to 'Open' (Jira's initial state)."""
    if not events:
        return "Open"
    current = "Open"
    for dt, to in events:
        if dt <= moment:
            current = to
        else:
            break
    return current


def compute_event_analytics(meta, docs):
    """Compute the three Event-Driven Analytics modules for Tab 3.

    Returns a dict:
      module1: {total_bugs, with_parent, distribution:[{status,count,pct}], na:bool}
      module2: {parents_analyzed, transitions, auto:{count,pct}, manual:{count,pct},
                target_statuses:[{status,count}], mermaid:[...]}
      module3: {baseline:{cycle_days,pingpong}, cohorts:[{label,count,cycle_days,
                pingpong,cycle_delta_pct,pingpong_delta_pct,risk}], risk:[labels]}
    """
    import json
    # ---- Build lookup maps -------------------------------------------------
    doc_by_key = {}
    meta_by_key = {}
    for m, d in zip(meta, docs):
        k = m.get("issue_key")
        if k:
            doc_by_key[k] = d
            meta_by_key[k] = m

    # Group CHILD issues (Sub-task or Sub-Bug) by their parent. A parent can be
    # ANY issue type (Story/Task/Bug/Epic/...) that has Sub-task or Sub-Bug
    # children. Used by the parent-child sync trackers (Module 1b / Module 2).
    children_by_parent = defaultdict(list)   # parent_key -> [child meta]
    for m in meta:
        pk = m.get("parent_key")
        k = m.get("issue_key")
        if pk and k and (m.get("type") or "").strip().lower() in ("sub-task", "sub-bug"):
            children_by_parent[pk].append(m)

    # ---- Module 1: Jira Defect Causality & SDLC Triggers ------------------
    # Hard parent-linkage resolution for every Bug / Sub-Bug:
    #   1) Sub-Bug -> use the system `parent` field (its Bug/Story/Task).
    #   2) Bug    -> if `parent` is empty, scan `issuelinks` for a link whose
    #                counterpart is a Story/Task (blocked-by / relates-to /
    #                associated / depends). The first such Story/Task found is
    #                treated as the "Target Scope" (parent feature).
    def _resolve_defect_parent(m):
        typ = (m.get("type") or "").strip().lower()
        pk = m.get("parent_key")
        if pk and pk in meta_by_key:
            return pk, "parent"
        if typ == "sub-bug":
            return None, "parent"  # sub-bug MUST use parent field
        # Bug: fall back to issuelinks -> Story/Task
        raw = m.get("issuelinks")
        if not raw:
            return None, "link"
        try:
            recs = json.loads(raw)
        except Exception:
            return None, "link"
        for r in recs:
            tgt_type = (r.get("target_type") or "").strip().lower()
            if tgt_type not in ("story", "task"):
                continue
            lname = (r.get("type") or "").strip().lower()
            if any(kw in lname for kw in ("block", "relat", "associat",
                                          "depend", "caus")):
                tgt_key = r.get("target_key")
                if tgt_key and tgt_key in meta_by_key:
                    return tgt_key, "link"
        return None, "link"

    m1a_total = 0
    m1a_with_parent = 0
    m1a_dist = Counter()
    m1a_pairs = []   # [{defect, parent, parent_status, created}]
    for m in meta:
        typ = (m.get("type") or "").strip().lower()
        if typ not in ("bug", "sub-bug"):
            continue
        m1a_total += 1
        created = _dt_full(m.get("created"))
        if not created:
            continue
        pk, how = _resolve_defect_parent(m)
        if not pk or pk not in doc_by_key:
            continue
        parent_events = _status_events_from_text(doc_by_key.get(pk))
        st = _parent_status_at(parent_events, created)
        m1a_dist[st] += 1
        m1a_with_parent += 1
        m1a_pairs.append({
            "defect": m.get("issue_key"), "parent": pk,
            "parent_status": st, "created": m.get("created"), "how": how,
        })

    m1a_distribution = [{"status": st, "count": c}
                        for st, c in m1a_dist.most_common()]
    m1a_total_dist = max(m1a_with_parent, 1)
    m1a_distribution_pct = [
        {"status": st, "count": c,
         "pct": round(c / m1a_total_dist * 100, 1)}
        for st, c in m1a_dist.most_common()]
    module1a = {
        "total_bugs": m1a_total,
        "with_parent": m1a_with_parent,
        "distribution": m1a_distribution,
        "distribution_pct": m1a_distribution_pct,
        "pairs": m1a_pairs[:50],
        "na": m1a_with_parent == 0,
    }

    # ---- Module 1b: Parent-Child Closure Sync Tracker ----------------------
    # For every parent (ANY issue type) with Sub-task / Sub-Bug children,
    # T_last_child = max(updated) among children that reached Closed/Resolved.
    # Then check whether the parent's status CHANGED (any status transition)
    # strictly after that moment. If it did NOT, the parent is "stuck" — it
    # should have moved to its next workflow status (in testing / resolved /
    # closed / done / ...) once all its children closed, but did not. This
    # answers: "which parents fail to advance in their workflow after the last
    # child closes?" — regardless of whether the transition is automated or
    # manual.
    m1b_stuck = []            # dicts: {type,key,url,status,latency_hrs}
    m1b_parents = 0
    m1b_moved = 0
    for parent_key, children in children_by_parent.items():
        parent_doc = doc_by_key.get(parent_key)
        parent_events = _status_events_from_text(parent_doc) if parent_doc else []
        if not parent_events:
            continue
        last_child_closed = None
        for ch in children:
            fst = (ch.get("status") or "").strip().lower()
            if fst not in ("closed", "resolved"):
                continue
            upd = _dt_full(ch.get("updated")) or _dt_full(ch.get("done_date"))
            if upd and (last_child_closed is None or upd > last_child_closed):
                last_child_closed = upd
        if last_child_closed is None:
            continue
        m1b_parents += 1
        # Did the parent have ANY status transition strictly AFTER the last
        # child closed?
        moved = any(dt > last_child_closed for dt, _to in parent_events)
        if moved:
            m1b_moved += 1
            continue
        pm = meta_by_key.get(parent_key, {})
        # Latency = time elapsed since the last child closed (stuck so far).
        from datetime import timezone as _tz
        latency_hrs = round((datetime.now(_tz.utc) - last_child_closed).total_seconds() / 3600.0, 1)
        m1b_stuck.append({
            "type": pm.get("type", "?"),
            "key": parent_key,
            "url": pm.get("url", ""),
            "status": pm.get("status") or "None",
            "latency_hrs": latency_hrs,
        })

    # Sort stuck parents by latency (longest first).
    m1b_stuck.sort(key=lambda r: -r["latency_hrs"])
    module1b = {
        "parents_analyzed": m1b_parents,
        "moved": m1b_moved,
        "stuck_count": len(m1b_stuck),
        "stuck": m1b_stuck,
        "na": m1b_parents == 0,
    }

    # ---- Module 1c: Sub-Bug Creation Constraints Validation ---------------
    # For every [Story/Task/Bug -> Sub-Bug] pair, capture the parent's status
    # at the exact second the Sub-Bug was created. Hypothesis: Sub-Bugs are
    # only created while the parent is in 'In Testing' (100%).
    m1c_total = 0
    m1c_dist = Counter()
    m1c_pairs = []
    for m in meta:
        typ = (m.get("type") or "").strip().lower()
        if typ != "sub-bug":
            continue
        pk = m.get("parent_key")
        created = _dt_full(m.get("created"))
        if not pk or pk not in doc_by_key or not created:
            continue
        parent_events = _status_events_from_text(doc_by_key.get(pk))
        st = _parent_status_at(parent_events, created)
        m1c_dist[st] += 1
        m1c_total += 1
        m1c_pairs.append({
            "sub_bug": m.get("issue_key"), "parent": pk,
            "parent_status": st, "created": m.get("created"),
        })
    m1c_total_safe = max(m1c_total, 1)
    m1c_distribution_pct = [
        {"status": st, "count": c,
         "pct": round(c / m1c_total_safe * 100, 1)}
        for st, c in m1c_dist.most_common()]
    m1c_in_testing = m1c_dist.get("In Testing", 0)
    module1c = {
        "total_pairs": m1c_total,
        "distribution": m1c_distribution_pct,
        "in_testing_pct": round(m1c_in_testing / m1c_total_safe * 100, 1),
        "in_testing_count": m1c_in_testing,
        "pairs": m1c_pairs[:50],
        "na": m1c_total == 0,
    }

    module1 = {
        "module1a": module1a,
        "module1b": module1b,
        "module1c": module1c,
    }

    # ---- Module 2: Auto-transit / Parent-Child sync -----------------------
    auto_count = 0
    manual_count = 0
    target_status_counter = Counter()
    mermaid_edges = Counter()   # (target_status, kind) -> count
    parents_analyzed = 0

    for parent_key, children in children_by_parent.items():
        parent_doc = doc_by_key.get(parent_key)
        parent_events = _status_events_from_text(parent_doc) if parent_doc else []
        if not parent_events:
            continue
        # Timestamp of the LAST child that reached a final (Closed/Resolved)
        # status.
        last_child_closed = None
        for ch in children:
            fst = (ch.get("status") or "").strip().lower()
            if fst not in ("closed", "resolved"):
                continue
            upd = _dt_full(ch.get("updated")) or _dt_full(ch.get("done_date"))
            if upd and (last_child_closed is None or upd > last_child_closed):
                last_child_closed = upd
        if last_child_closed is None:
            continue
        parents_analyzed += 1
        # Parent status transitions strictly AFTER the last child closed.
        for dt, to in parent_events:
            if dt <= last_child_closed:
                continue
            delta = (dt - last_child_closed).total_seconds()
            target_status_counter[to] += 1
            if delta <= AUTO_TRIGGER_WINDOW_SEC:
                auto_count += 1
                mermaid_edges[(to, "auto")] += 1
            else:
                manual_count += 1
                mermaid_edges[(to, "manual")] += 1

    m2_total = auto_count + manual_count
    m2_auto_pct = round(auto_count / m2_total * 100, 1) if m2_total else 0.0
    m2_manual_pct = round(manual_count / m2_total * 100, 1) if m2_total else 0.0
    m2_targets = [{"status": st, "count": c}
                  for st, c in target_status_counter.most_common()]
    # Mermaid flow graph: [Last Sub-task Closed] -> target statuses, with the
    # auto/manual split annotated on each edge.
    mermaid_lines = ["graph LR",
                     '    A["Last Sub-task Closed"]']
    top_targets = target_status_counter.most_common(6)
    for idx, (st, c) in enumerate(top_targets):
        auto_edge = mermaid_edges.get((st, "auto"), 0)
        man_edge = mermaid_edges.get((st, "manual"), 0)
        pct = round(c / m2_total * 100, 1) if m2_total else 0.0
        node = f"S{idx}"
        mermaid_lines.append(f'    {node}["{st} ({pct}%)"]')
        mermaid_lines.append(
            f'    A -->|{auto_edge} auto / {man_edge} manual| {node}')
    # Per-target-status auto/manual split for the stacked bar chart.
    m2_auto_by_status = [
        {"status": st, "count": mermaid_edges.get((st, "auto"), 0)}
        for st, _ in target_status_counter.most_common()]
    m2_manual_by_status = [
        {"status": st, "count": mermaid_edges.get((st, "manual"), 0)}
        for st, _ in target_status_counter.most_common()]
    module2 = {
        "parents_analyzed": parents_analyzed,
        "transitions": m2_total,
        "auto": {"count": auto_count, "pct": m2_auto_pct},
        "manual": {"count": manual_count, "pct": m2_manual_pct},
        "target_statuses": m2_targets,
        "auto_by_status": m2_auto_by_status,
        "manual_by_status": m2_manual_by_status,
        "mermaid": "\n".join(mermaid_lines),
        "na": parents_analyzed == 0,
    }

    # ---- Module 3: Metadata impact (labels vs cycle time / ping-pong) -----
    def _issue_cycle(m, doc):
        """Median-style cycle = first Done/Closed minus first In Progress."""
        ev = _status_events_from_text(doc)
        first_ip = None
        first_done = None
        for dt, to in ev:
            low = to.strip().lower()
            if first_ip is None and low in ("in progress", "in review",
                                            "in testing", "in qa"):
                first_ip = dt
            if first_done is None and low in ("closed", "done", "resolved",
                                              "complete", "completed"):
                first_done = dt
        if first_ip and first_done and first_done > first_ip:
            return (first_done - first_ip).days
        return None

    def _pingpong(doc):
        """Count rework ping-pong transitions (In Testing->In Progress,
        Closed->Reopened) in the issue changelog."""
        ev = _status_events_from_text(doc)
        count = 0
        for i in range(1, len(ev)):
            fr = ev[i - 1][1].strip().lower()
            to = ev[i][1].strip().lower()
            if (fr in ("in testing", "in qa") and to in ("in progress", "open")) \
               or (fr in ("closed", "resolved") and to in ("reopened", "open")):
                count += 1
        return count

    # Baseline across all work items (no label filter).
    base_cycles = []
    base_pings = []
    for m, d in zip(meta, docs):
        typ = (m.get("type") or "").lower()
        if typ not in ("story", "task", "bug", "sub-task", "sub-bug",
                       "improvement"):
            continue
        c = _issue_cycle(m, d)
        if c is not None:
            base_cycles.append(c)
        base_pings.append(_pingpong(d))
    from statistics import median
    base_cycle = median(base_cycles) if base_cycles else None
    base_ping = (sum(base_pings) / len(base_pings)) if base_pings else None

    # Label cohorts: keep labels appearing in >= 3 issues (noise filter).
    label_count = Counter()
    for m in meta:
        for lab in ((m.get("labels") or "").split(",")):
            lab = lab.strip().lower()
            if lab:
                label_count[lab] += 1
    keep_labels = {lab for lab, c in label_count.items() if c >= 3}

    cohorts = []
    risk_labels = []
    for lab in sorted(keep_labels):
        cycles = []
        pings = []
        n = 0
        for m, d in zip(meta, docs):
            labs = {(x.strip().lower()) for x in (m.get("labels") or "").split(",")
                    if x.strip()}
            if lab not in labs:
                continue
            n += 1
            c = _issue_cycle(m, d)
            if c is not None:
                cycles.append(c)
            pings.append(_pingpong(d))
        if n == 0:
            continue
        cyc = median(cycles) if cycles else None
        pin = (sum(pings) / len(pings)) if pings else None
        cyc_delta = (round((cyc - base_cycle) / base_cycle * 100, 1)
                     if cyc is not None and base_cycle else None)
        pin_delta = (round((pin - base_ping) / base_ping * 100, 1)
                     if pin is not None and base_ping else None)
        high_cycle = cyc is not None and base_cycle is not None and cyc > base_cycle
        high_ping = pin is not None and base_ping is not None and pin > base_ping
        risk = bool(high_cycle and high_ping)
        if risk:
            risk_labels.append(lab)
        cohorts.append({
            "label": lab, "count": n,
            "cycle_days": cyc, "pingpong": round(pin, 2) if pin is not None else None,
            "cycle_delta_pct": cyc_delta, "pingpong_delta_pct": pin_delta,
            "risk": risk,
        })

    module3 = {
        "baseline": {"cycle_days": base_cycle,
                     "pingpong": round(base_ping, 2) if base_ping is not None
                     else None},
        "cohorts": cohorts,
        "risk_labels": risk_labels,
    }

    return {"module1": module1, "module2": module2, "module3": module3}
