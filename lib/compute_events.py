"""Tab 3 Event-Driven Analytics (bug triggers, auto-transit, cohorts)."""
from collections import Counter, defaultdict
import json
from .date_utils import (status_group, _status_events_from_text,
                         _status_transitions_from_text, _utc_instant)

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

def _parent_status_at(transitions, moment, parent):
    """Return a known status at the event time, or Unknown."""
    moment = _utc_instant(moment.isoformat())
    created = _utc_instant(parent.get("created"))
    if not parent.get("status_history_complete") or not created or moment < created:
        return "Unknown"
    if not transitions:
        return parent.get("status") or "Unknown"
    if (transitions[-1][2] != parent.get("status") or
            any(a[2] != b[1] for a, b in zip(transitions, transitions[1:]))):
        return "Unknown"
    current = transitions[0][1]
    for dt, before, after in transitions:
        if dt > moment:
            break
        if before != current:
            return "Unknown"
        current = after
    return current


def _closure_sync(parent, children, docs):
    snapshot = _utc_instant(parent.get("jira_snapshot_at"))
    if not snapshot or not parent.get("status_history_complete"):
        return None
    try:
        expected = json.loads(parent.get("subtask_keys_json") or "null")
    except (TypeError, ValueError):
        return None
    if (not isinstance(expected, list) or not all(isinstance(key, str) for key in expected)
            or set(expected) != {c.get("issue_key") for c in children}):
        return None
    last_closures = []
    for child in children:
        if (_utc_instant(child.get("jira_snapshot_at")) != snapshot or
                not child.get("status_history_complete") or
                status_group(child.get("status")) != "Closed"):
            return None
        events = _status_transitions_from_text(docs.get(child.get("issue_key")))
        if not events or events[-1][2] != child.get("status") or events[-1][0] > snapshot:
            return None
        if any(a[2] != b[1] for a, b in zip(events, events[1:])):
            return None
        entered = [dt for dt, before, after in events
                   if status_group(before) != "Closed" and status_group(after) == "Closed"]
        if not entered:
            return None
        last_closures.append(entered[-1])
    if not last_closures:
        return None
    events = _status_transitions_from_text(docs.get(parent.get("issue_key")))
    if (events and (events[-1][0] > snapshot or events[-1][2] != parent.get("status") or
                    any(a[2] != b[1] for a, b in zip(events, events[1:])))):
        return None
    last_closed = max(last_closures)
    moved = any(dt > last_closed for dt, _, _ in events)
    return moved, round((snapshot - last_closed).total_seconds() / 3600, 1)


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
        candidates = set()
        for r in recs:
            tgt_type = (r.get("target_type") or "").strip().lower()
            if tgt_type not in ("story", "task"):
                continue
            lname = (r.get("type") or "").strip().lower()
            if any(kw in lname for kw in ("block", "relat", "associat",
                                          "depend", "caus")):
                tgt_key = r.get("target_key")
                if tgt_key and tgt_key in meta_by_key:
                    candidates.add(tgt_key)
        return (next(iter(candidates)), "link") if len(candidates) == 1 else (None, "link")

    m1a_total = 0
    m1a_with_parent = 0
    m1a_dist = Counter()
    m1a_pairs = []   # [{defect, parent, parent_status, created}]
    for m in meta:
        typ = (m.get("type") or "").strip().lower()
        if typ not in ("bug", "sub-bug"):
            continue
        m1a_total += 1
        created = _utc_instant(m.get("created"))
        if not created:
            continue
        pk, how = _resolve_defect_parent(m)
        if not pk or pk not in doc_by_key:
            continue
        parent_events = _status_transitions_from_text(doc_by_key.get(pk))
        st = _parent_status_at(parent_events, created, meta_by_key[pk])
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

    m1b_stuck, m1b_moved, m1b_parents, m1b_unknown = [], 0, 0, 0
    for key, children in children_by_parent.items():
        parent = meta_by_key.get(key)
        observation = _closure_sync(parent, children, doc_by_key) if parent else None
        if observation is None:
            m1b_unknown += 1
            continue
        moved, latency = observation
        m1b_parents += 1
        if moved or status_group(parent.get("status")) == "Closed":
            m1b_moved += 1
        else:
            m1b_stuck.append({"type": parent.get("type", "?"), "key": key,
                              "url": parent.get("url", ""), "status": parent.get("status"),
                              "latency_hrs": latency})
    m1b_stuck.sort(key=lambda row: -row["latency_hrs"])
    module1b = {
        "parents_analyzed": m1b_parents, "moved": m1b_moved,
        "stuck_count": len(m1b_stuck) if m1b_parents else None,
        "stuck": m1b_stuck, "unknown_count": m1b_unknown, "na": m1b_parents == 0,
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
        created = _utc_instant(m.get("created"))
        if not pk or pk not in doc_by_key or not created:
            continue
        parent_events = _status_transitions_from_text(doc_by_key.get(pk))
        st = _parent_status_at(parent_events, created, meta_by_key[pk])
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
    m1c_known = m1c_total - m1c_dist.get("Unknown", 0)
    module1c = {
        "total_pairs": m1c_total,
        "distribution": m1c_distribution_pct,
        "in_testing_pct": round(m1c_in_testing / m1c_known * 100, 1) if m1c_known else None,
        "in_testing_count": m1c_in_testing,
        "known_pairs": m1c_known,
        "pairs": m1c_pairs[:50],
        "na": m1c_total == 0,
    }

    module1 = {
        "module1a": module1a,
        "module1b": module1b,
        "module1c": module1c,
    }

    # ---- Module 2: Auto-transit / Parent-Child sync -----------------------
    # Timestamps alone cannot identify automation versus manual actions.
    module2 = {
        "parents_analyzed": 0, "transitions": None,
        "auto": {"count": None, "pct": None},
        "manual": {"count": None, "pct": None},
        "target_statuses": [], "auto_by_status": [], "manual_by_status": [],
        "mermaid": "", "na": True,
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

    def _pingpong(m, doc):
        """Count consecutive observed returns on the same issue."""
        if not m.get("status_history_complete"):
            return None
        ev = _status_transitions_from_text(doc)
        if ev and (ev[-1][2] != m.get("status") or
                   any(a[2] != b[1] for a, b in zip(ev, ev[1:]))):
            return None
        return sum(a[1] == b[2] and a[2] == b[1] and a[1] != a[2]
                   for a, b in zip(ev, ev[1:]))

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
        p = _pingpong(m, d)
        if p is not None:
            base_pings.append(p)
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
            p = _pingpong(m, d)
            if p is not None:
                pings.append(p)
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
