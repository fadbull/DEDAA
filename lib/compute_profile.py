"""Tab 3 Jira Data Profile computation (field density, workflow)."""
from collections import Counter, defaultdict
from datetime import datetime
import json
from .date_utils import _dt, _biweek, status_group

# ---------------------------------------------------------------------------
# Tab 3 — Jira Data Profile (Data & Workflow Architecture)
# ---------------------------------------------------------------------------
# Standard metadata fields we persist per issue (used for the field matrix).
JIRA_PROFILE_FIELDS = [
    "type", "status", "priority", "resolution", "assignee", "reporter",
    "components", "labels", "created", "updated", "resolutiondate", "duedate",
    "in_progress_date", "done_date",
]


def _field_type(field):
    """Best-effort Jira data type mapping for a metadata field."""
    if field in ("assignee", "reporter"):
        return "User"
    if field in ("priority", "resolution", "status", "type"):
        return "Option"
    if field in ("components", "labels"):
        return "Array<Option>"
    if field in ("created", "updated", "resolutiondate", "in_progress_date",
                 "done_date", "duedate"):
        return "Date/Time"
    return "Text"


def compute_jira_profile(meta, docs):
    """Compute Tab 3 'Jira Data Profile' data: field density per issue type,
    data-type mapping, per-type status state machines (from changelog), and
    heuristic associations (assignee<->component, reporter->priority)."""
    from collections import Counter, defaultdict
    import json

    # 1) Field Density: for each issue type, what fraction of issues populate
    #    each field (non-empty).
    types = sorted({m.get("type", "?") for m in meta})
    field_density = {}   # field -> {type: pct}
    type_counts = Counter(m.get("type", "?") for m in meta)
    for field in JIRA_PROFILE_FIELDS:
        density = {}
        for t in types:
            total = type_counts[t]
            if not total:
                density[t] = 0
                continue
            filled = sum(1 for m in meta
                         if m.get("type") == t and (m.get(field) or ""))
            density[t] = round(filled / total * 100, 1)
        field_density[field] = density

    # 2) Data Type Mapping
    data_type_map = {f: _field_type(f) for f in JIRA_PROFILE_FIELDS}

    # 3) State machines per issue type from Status history.
    trans_by_type = defaultdict(Counter)
    states_by_type = defaultdict(Counter)
    for m, d in zip(meta, docs):
        typ = m.get("type", "?")
        states_by_type[typ][m.get("status", "?")] += 1
        if "Status history" not in d:
            continue
        sec = d.split("Status history:", 1)[1]
        for line in sec.splitlines():
            line = line.strip()
            if "->" in line:
                frto = line.split(": ")[-1]
                if "->" in frto:
                    fr, to = [x.strip() for x in frto.split("->")]
                    trans_by_type[typ][(fr, to)] += 1
    state_machines = {}
    for typ in types:
        trans = trans_by_type[typ]
        # Keep top transitions (by frequency) to build a readable graph.
        top = trans.most_common(14)
        state_machines[typ] = {
            "transitions": [{"from": fr, "to": to, "count": c}
                            for (fr, to), c in top],
            "states": dict(states_by_type[typ].most_common()),
        }

    # 4) Heuristic: Assignee <-> Component ownership grid.
    #    (assignee, component) -> count, for issues with both.
    assignee_component = Counter()
    for m in meta:
        assignee = m.get("assignee") or ""
        comp = m.get("components") or ""
        if not assignee or not comp:
            continue
        for c in [x.strip() for x in comp.split(",") if x.strip()]:
            assignee_component[(assignee, c)] += 1

    # 5) Heuristic: Reporter -> Priority escalation.
    reporter_priority = Counter()
    for m in meta:
        reporter = m.get("reporter") or ""
        prio = m.get("priority") or ""
        if reporter and prio:
            reporter_priority[(reporter, prio)] += 1

    # 6) Resolution & Status alignment anomalies.
    #    issues "Closed/Done/Resolved" but missing resolutiondate.
    alignment_anomalies = []
    closed_statuses = {"closed", "done", "resolved", "complete", "completed",
                       "verified", "released"}
    for m in meta:
        st = (m.get("status") or "").lower()
        if st in closed_statuses and not m.get("resolutiondate"):
            alignment_anomalies.append({
                "key": m.get("issue_key"),
                "status": m.get("status"),
                "url": m.get("url", ""),
            })
    # issues with a Resolution value but still open
    open_with_resolution = []
    for m in meta:
        st = (m.get("status") or "").lower()
        if st not in closed_statuses and (m.get("resolution") or ""):
            open_with_resolution.append({
                "key": m.get("issue_key"),
                "status": m.get("status"),
                "resolution": m.get("resolution"),
                "url": m.get("url", ""),
            })

    # 7) Heuristic: field co-occurrence — Priority change vs custom fields is
    #    not directly available; instead report Priority vs labels/component
    #    co-occurrence as a proxy (fields that tend to appear together).
    priority_labels = Counter()
    for m in meta:
        prio = m.get("priority") or ""
        labels = (m.get("labels") or "").lower()
        if prio and "prod" in labels:
            priority_labels[(prio, "Prod")] += 1
        if prio and "sast" in labels:
            priority_labels[(prio, "SAST")] += 1

    # 8) Time-in-Status: exact days each issue spent in each status, from the
    #    status-history timestamps. -> list of (key, type, status, days).
    def _status_events(doc_text):
        """Return sorted [(datetime, to_status)] from Status history."""
        ev = []
        if not doc_text or "Status history:" not in doc_text:
            return ev
        sec = doc_text.split("Status history:", 1)[1]
        for line in sec.splitlines():
            line = line.strip()
            if "->" not in line:
                continue
            ts_str, _, frto = line.partition(": ")
            dt = _dt(ts_str)
            if dt and "->" in frto:
                to = [x.strip() for x in frto.split("->")][1]
                ev.append((dt, to))
        ev.sort(key=lambda x: x[0])
        return ev

    time_in_status = []   # (key, type, status, days)
    transition_freq = Counter()  # (from,to) -> count
    for m, doc in zip(meta, docs):
        typ = m.get("type", "?")
        ev = _status_events(doc)
        end_dt = _dt(m.get("updated")) or _dt(m.get("done_date")) or \
            _dt(m.get("created"))
        for i, (dt, st) in enumerate(ev):
            nxt = ev[i + 1][0] if i + 1 < len(ev) else end_dt
            if nxt and nxt > dt:
                days = round((nxt - dt).total_seconds() / 86400.0, 2)
                time_in_status.append({
                    "key": m.get("issue_key"), "type": typ,
                    "status": st, "days": days,
                })
            if i + 1 < len(ev):
                transition_freq[(st, ev[i + 1][1])] += 1

    # Aggregate median time-in-status per (status, type).
    from statistics import median
    tis_agg = defaultdict(list)
    for t in time_in_status:
        tis_agg[(t["status"], t["type"])].append(t["days"])
    time_in_status_median = {
        f"{st}__{typ}": round(median(v), 1)
        for (st, typ), v in tis_agg.items()}

    # 9) OLAP slice data: (type, assignee) -> (count, avg lifecycle days).
    olap_slices = defaultdict(lambda: {"count": 0, "life": []})
    for m, doc in zip(meta, docs):
        typ = m.get("type", "?")
        assignee = m.get("assignee") or "Unassigned"
        key = (typ, assignee)
        olap_slices[key]["count"] += 1
        cd = _dt(m.get("created", ""))
        dnd = _dt(m.get("done_date", "")) or _dt(m.get("resolutiondate", ""))
        if cd and dnd:
            olap_slices[key]["life"].append((dnd - cd).days)
    olap_slice_rows = []
    for (typ, assignee), v in olap_slices.items():
        life = v["life"]
        olap_slice_rows.append({
            "type": typ, "assignee": assignee, "count": v["count"],
            "avg_life": round(sum(life) / len(life), 1) if life else None,
        })

    # 10) Field Dependencies: pairwise co-fill percentage (which optional
    #     fields tend to be populated together). Rendered as a correlation
    #     matrix table in Tab 3.
    corr_fields = ["components", "labels", "resolution", "duedate",
                   "in_progress_date", "done_date", "priority"]
    field_corr = {}   # "fieldA|fieldB" -> pct of issues where both are filled
    for i, fa in enumerate(corr_fields):
        for fb in corr_fields[i + 1:]:
            both = sum(1 for m in meta
                       if (m.get(fa) or "") and (m.get(fb) or ""))
            pct = round(both / len(meta) * 100, 1) if meta else 0
            field_corr[f"{fa}|{fb}"] = pct

    # 11) Field fill-rate trend over biweekly periods (shows fields like
    #     Component / Labels / Resolution being left empty over time).
    trend_fields = ["components", "labels", "resolution", "duedate",
                    "in_progress_date"]
    field_fill_trend = {}   # field -> {biweek: pct filled}
    for field in trend_fields:
        per = defaultdict(lambda: [0, 0])   # biweek -> [filled, total]
        for m in meta:
            dt = _dt(m.get("created"))
            if not dt:
                continue
            bk = _biweek(dt)
            per[bk][1] += 1
            if m.get(field) or "":
                per[bk][0] += 1
        field_fill_trend[field] = {
            bk: round(filled / total * 100, 1)
            for bk, (filled, total) in sorted(per.items())
        }

    # 12) Transition frequency matrix (from x to) + ping-pong detection
    #     (back-and-forth status jumps that indicate rework / churn).
    trans_statuses = sorted(
        {s for (fr, to) in transition_freq for s in (fr, to)})
    trans_index = {s: i for i, s in enumerate(trans_statuses)}
    trans_matrix = [[0] * len(trans_statuses) for _ in trans_statuses]
    for (fr, to), c in transition_freq.items():
        trans_matrix[trans_index[fr]][trans_index[to]] = c
    pingpong = []
    seen = set()
    for (fr, to), c in transition_freq.items():
        rev = transition_freq.get((to, fr), 0)
        pair = tuple(sorted((fr, to)))
        if rev > 0 and fr != to and pair not in seen:
            seen.add(pair)
            pingpong.append({"a": fr, "b": to, "ab": c, "ba": rev,
                             "total": c + rev})
    pingpong.sort(key=lambda x: -x["total"])

    # 13) Time-in-Status per issue type (median days per status), flagging
    #     statuses where work "dies" (median > 60 days).
    tis_by_type = defaultdict(dict)
    for key, med in time_in_status_median.items():
        st, typ = key.split("__", 1)
        tis_by_type[typ][st] = med
    time_in_status_series = []
    for typ in types:
        items = [{"status": st, "median": v, "stagnant": v > 60}
                 for st, v in sorted(tis_by_type[typ].items(),
                                     key=lambda kv: -kv[1])]
        time_in_status_series.append({"type": typ, "items": items})

    # 14) OLAP cube: per-issue rows sliceable by any dimension combination
    #     (type / assignee / priority / status / component) in the interactive
    #     Slice & Dice constructor. Life = resolution/done - created (days).
    olap_dims = ["type", "assignee", "priority", "status", "component"]
    olap_rows = []
    for m in meta:
        comp = ""
        if m.get("components"):
            comp = m["components"].split(",")[0].strip()
        life = None
        cd = _dt(m.get("created", ""))
        dnd = _dt(m.get("done_date", "")) or _dt(m.get("resolutiondate", ""))
        if cd and dnd and dnd >= cd:
            life = (dnd - cd).days
        olap_rows.append({
            "type": m.get("type", "?"),
            "assignee": m.get("assignee") or "Unassigned",
            "priority": m.get("priority") or "None",
            "status": m.get("status") or "None",
            "component": comp or "None",
            "life": life,
        })

    # 14b) OLAP cube over ISSUE LINKS (issuelinks): one row per link record,
    #      sliceable by any combination of its dimensions — link type, direction,
    #      source & target issue type, and source & target status — in the
    #      interactive Slice & Dice constructor (mirrors the issue data cube).
    olap_link_dims = ["link_type", "direction", "source_type",
                      "target_type", "source_status", "target_status"]
    olap_link_rows = []
    for m in meta:
        src_key = m.get("issue_key")
        src_type = m.get("type", "?")
        src_status = m.get("status") or "None"
        raw = m.get("issuelinks")
        if not raw:
            continue
        try:
            recs = json.loads(raw)
        except Exception:
            continue
        for r in recs:
            olap_link_rows.append({
                "link_type": r.get("type") or "None",
                "direction": r.get("direction") or "None",
                "source_type": src_type,
                "target_type": r.get("target_type") or "None",
                "source_status": src_status,
                "target_status": r.get("target_status") or "None",
            })

    # 15) SDLC Process Matrix: Issue Type x Status distribution (heatmap).
    #     Rows = issue types, cols = key SDLC statuses, cells = % of that
    #     type's issues currently in that status.
    sdlc_statuses = ["Analysis", "Open", "Ready for Development", "In Progress",
                     "Ready for QA", "In Testing", "Resolved", "Closed"]
    # Normalize status labels so "Ready For Grooming" ~ "Ready for Development".
    def _sdlc_status(st):
        s = (st or "").strip().lower()
        if s in ("analysis", "design"):
            return "Analysis"
        if s in ("open", "new"):
            return "Open"
        if s in ("ready for development", "ready for grooming", "ready for demo"):
            return "Ready for Development"
        if s in ("in progress",):
            return "In Progress"
        if s in ("ready for qa", "in qa"):
            return "Ready for QA"
        if s in ("in testing", "in review"):
            return "In Testing"
        if s in ("resolved",):
            return "Resolved"
        if s in ("closed", "done", "complete", "completed", "released", "verified"):
            return "Closed"
        return None

    sdlc_types = ["Story", "Bug", "Sub-Bug", "Task", "Security issue",
                  "Sub-task", "Epic", "Improvement", "Test"]
    type_status_counts = Counter()
    type_total = Counter()
    sdlc_matrix = {}   # type -> {status: pct}
    for m in meta:
        t = m.get("type", "?")
        st = _sdlc_status(m.get("status"))
        if st:
            type_status_counts[(t, st)] += 1
            type_total[t] += 1
    for t in sdlc_types:
        total = type_total.get(t, 0)
        row = {}
        for st in sdlc_statuses:
            c = type_status_counts.get((t, st), 0)
            row[st] = round(c / total * 100, 1) if total else 0
        sdlc_matrix[t] = row

    # 16) Value Stream Mapping Gaps — heuristic risk flags.
    vsm_findings = []

    # (a) Sub-Bug / Story ratio (Stories Leakage into Sub-Bugs).
    n_story = type_counts.get("Story", 0)
    n_subbug = type_counts.get("Sub-Bug", 0)
    ratio = n_subbug / n_story if n_story else None
    if ratio is not None and ratio > 0.2:
        vsm_findings.append({
            "level": "warning", "kind": "Stories Leakage into Sub-Bugs",
            "message": ("Риск низкого качества первичной разработки "
                        "(Stories Leakage into Sub-Bugs), отношение количества "
                        f"Sub-Bug к Story выше 0.2 (ratio = {ratio:.2f}, "
                        f"Sub-Bug={n_subbug}, Story={n_story})."),
            "value": round(ratio, 2),
        })

    # (b) Backlog Stagnation — issues in Open status older than 180 days,
    #     broken down per issue type.
    stagnation = Counter()   # type -> count of stagnant Open issues
    now = datetime.now()
    for m in meta:
        st = (m.get("status") or "").strip().lower()
        if st not in ("open", "new"):
            continue
        cd = _dt(m.get("created"))
        if cd and (now - cd).days > 180:
            stagnation[m.get("type", "?")] += 1
    stagnation_total = sum(stagnation.values())
    stagnation_by_type = [{"type": t, "count": c}
                          for t, c in stagnation.most_common()]
    if stagnation_total:
        vsm_findings.append({
            "level": "warning", "kind": "Backlog Stagnation",
            "message": (f"Мертвый объем бэклога (Backlog Stagnation Rate): "
                        f"{stagnation_total} задач(и) в статусе Open со сроком "
                        f"жизни > 180 дней."),
            "value": stagnation_total,
        })

    # (c) Security issues in active development (In Progress).
    n_sec = type_counts.get("Security issue", 0)
    sec_in_progress = sum(
        1 for m in meta
        if m.get("type") == "Security issue"
        and (m.get("status") or "").strip().lower() == "in progress")
    sec_pct = round(sec_in_progress / n_sec * 100, 1) if n_sec else None
    if sec_pct is not None and sec_pct < 10:
        vsm_findings.append({
            "level": "warning", "kind": "Isolated Security Loop",
            "message": (f"Изолированный контур безопасности (Security issues "
                        f"игнорируются девелоперами), процент задач в активной "
                        f"разработке < 10% (In Progress = {sec_pct}%, "
                        f"{sec_in_progress}/{n_sec})."),
            "value": sec_pct,
        })

    return {
        "types": types,
        "sdlc_matrix": sdlc_matrix,
        "sdlc_statuses": sdlc_statuses,
        "sdlc_types": sdlc_types,
        "vsm_findings": vsm_findings,
        "subbug_story_ratio": ratio,
        "backlog_stagnation": {"total": stagnation_total,
                               "by_type": stagnation_by_type},
        "security_in_progress": {"count": sec_in_progress, "total": n_sec,
                                 "pct": sec_pct},
        "type_counts": dict(type_counts),
        "field_density": field_density,
        "data_type_map": data_type_map,
        "state_machines": state_machines,
        "assignee_component": dict(assignee_component.most_common(40)),
        "reporter_priority": dict(reporter_priority.most_common(40)),
        "alignment_anomalies": alignment_anomalies[:20],
        "open_with_resolution": open_with_resolution[:20],
        "priority_labels": dict(priority_labels),
        "time_in_status_median": time_in_status_median,
        "time_in_status_raw": time_in_status[:2000],
        "transition_freq": dict(transition_freq.most_common(80)),
        "olap_slice_rows": olap_slice_rows,
        "field_corr": field_corr,
        "field_fill_trend": field_fill_trend,
        "trans_statuses": trans_statuses,
        "trans_matrix": trans_matrix,
        "pingpong": pingpong[:20],
        "time_in_status_series": time_in_status_series,
        "olap_dims": olap_dims,
        "olap_rows": olap_rows,
        # Issue-links OLAP cube (Slice & Dice over issuelinks records).
        "olap_link_dims": olap_link_dims,
        "olap_link_rows": olap_link_rows,
    }
