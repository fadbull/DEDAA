"""Tab 3 Jira Data Profile computation (field density, workflow)."""
from collections import Counter, defaultdict
import json
from .date_utils import (_dt, _biweek, status_group, _status_transitions_from_text,
                         _utc_datetime, _utc_instant)

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
    types = sorted({m.get("type") or "?" for m in meta})
    field_density = {}   # field -> {type: pct}
    type_counts = Counter(m.get("type") or "?" for m in meta)
    for field in JIRA_PROFILE_FIELDS:
        density = {}
        for t in types:
            total = type_counts[t]
            if not total:
                density[t] = 0
                continue
            filled = sum(1 for m in meta
                         if (m.get("type") or "?") == t and (m.get(field) or ""))
            density[t] = round(filled / total * 100, 1)
        field_density[field] = density

    # 2) Data Type Mapping
    data_type_map = {f: _field_type(f) for f in JIRA_PROFILE_FIELDS}

    # 3) State machines per issue type from Status history.
    trans_by_type = defaultdict(Counter)
    states_by_type = defaultdict(Counter)
    for m, d in zip(meta, docs):
        typ = m.get("type") or "?"
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
    time_in_status = []   # (key, type, status, days)
    transition_freq = Counter()  # (from,to) -> count
    returns = Counter()
    for m, doc in zip(meta, docs):
        typ = m.get("type", "?")
        ev = _status_transitions_from_text(doc)
        created = _utc_instant(m.get("created"))
        if ev and m.get("status_history_complete") == True and created and created < ev[0][0]:
            time_in_status.append({
                "key": m.get("issue_key"), "type": typ, "status": ev[0][1],
                "days": (ev[0][0] - created).total_seconds() / 86400,
            })
        for i, (dt, before, st) in enumerate(ev):
            transition_freq[(before, st)] += 1
            if i + 1 < len(ev):
                nxt, next_before, next_after = ev[i + 1]
                if st == next_before and before == next_after and before != st:
                    returns[(before, st)] += 1
            else:
                nxt = _utc_instant(m.get("jira_snapshot_at")) if m.get("status_history_complete") == True else None
                next_before = m.get("status")
            if nxt and nxt > dt and st == next_before:
                days = (nxt - dt).total_seconds() / 86400
                time_in_status.append({
                    "key": m.get("issue_key"), "type": typ,
                    "status": st, "days": days,
                })

    # Aggregate median time-in-status per (status, type).
    from statistics import median
    tis_agg = defaultdict(list)
    for t in time_in_status:
        tis_agg[(t["status"], t["type"])].append(t["days"])
    time_in_status_median = {
        f"{st}__{typ}": round(median(v), 2)
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
    for (fr, to), c in returns.items():
        rev = returns.get((to, fr), 0)
        pair = tuple(sorted((fr, to)))
        if pair not in seen:
            seen.add(pair)
            pingpong.append({"a": fr, "b": to, "ab": c + rev, "ba": c + rev,
                             "total": 2 * (c + rev)})
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
        components = list(dict.fromkeys(
            c.strip() for c in (m.get("components") or "").split(",") if c.strip()
        )) or ["None"]
        life = None
        cd = _utc_datetime(m.get("created"))
        dnd = _utc_datetime(m.get("resolutiondate"))
        if cd and dnd and dnd >= cd:
            life = round((dnd - cd).total_seconds() / 86400, 2)
        olap_rows.append({
            "type": m.get("type", "?"),
            "assignee": m.get("assignee") or "Unassigned",
            "priority": m.get("priority") or "None",
            "status": m.get("status") or "None",
            "components": components,
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
    type_status_counts = defaultdict(Counter)
    for m in meta:
        t = (m.get("type") or "").strip() or "Unknown (missing)"
        st = (m.get("status") or "").strip() or "Unknown (missing)"
        type_status_counts[t][st] += 1
    sdlc_types = sorted(type_status_counts, key=str.casefold)
    sdlc_statuses = sorted({s for counts in type_status_counts.values() for s in counts},
                           key=str.casefold)
    type_total = {t: sum(counts.values()) for t, counts in type_status_counts.items()}
    sdlc_counts = {t: {st: type_status_counts[t][st] for st in sdlc_statuses}
                   for t in sdlc_types}
    sdlc_matrix = {t: {st: round(sdlc_counts[t][st] / type_total[t] * 100, 1)
                       for st in sdlc_statuses} for t in sdlc_types}

    # 16) Value Stream Mapping Gaps.
    vsm_findings = []

    # (a) Sub-Bug / Story ratio.
    n_story = type_counts.get("Story", 0)
    n_subbug = type_counts.get("Sub-Bug", 0)
    ratio = n_subbug / n_story if n_story else None
    if ratio is not None:
        relation = "at or below" if ratio <= 0.2 else "above"
        vsm_findings.append({
            "level": "warning" if ratio <= 0.2 else "success",
            "kind": "Sub-Bug / Story ratio",
            "message": (f"Sub-Bug / Story = {n_subbug}/{n_story} = {ratio:.2f}; "
                        f"{relation} the illustrative threshold of 0.2. "
                        "This ratio does not establish a cause or quality outcome."),
            "value": ratio,
        })

    # (b) Backlog Stagnation — issues in Open status older than 180 days,
    #     broken down per issue type.
    stagnation = Counter()   # type -> count of stagnant Open issues
    stagnation_unknown = 0
    stagnation_observed = 0
    for m, doc in zip(meta, docs):
        st = (m.get("status") or "").strip().lower()
        if st not in ("open", "new"):
            continue
        snapshot = _utc_instant(m.get("jira_snapshot_at"))
        ev = _status_transitions_from_text(doc)
        if not snapshot or m.get("status_history_complete") != True:
            stagnation_unknown += 1
            continue
        if ev and (ev[-1][2].strip().lower() != st or
                   any(a[2] != b[1] for a, b in zip(ev, ev[1:]))):
            stagnation_unknown += 1
            continue
        entered = next((dt for dt, before, after in reversed(ev)
                        if before.strip().lower() not in ("open", "new")
                        and after.strip().lower() in ("open", "new")), None)
        if entered is None and (not ev or ev[0][1].strip().lower() in ("open", "new")):
            entered = _utc_instant(m.get("created"))
        if not entered or entered > snapshot:
            stagnation_unknown += 1
            continue
        stagnation_observed += 1
        if (snapshot - entered).total_seconds() > 180 * 86400:
            stagnation[m.get("type", "?")] += 1
    stagnation_total = sum(stagnation.values())
    stagnation_by_type = [{"type": t, "count": c}
                          for t, c in stagnation.most_common()]
    if stagnation_total:
        vsm_findings.append({
            "level": "info", "kind": "Backlog Stagnation",
            "message": (f"{stagnation_total} observed issues remained continuously "
                        "in Open or New for more than 180 days at the snapshot."),
            "value": stagnation_total,
        })

    # (c) Security issues in active development (In Progress).
    n_sec = type_counts.get("Security issue", 0)
    sec_in_progress = sum(
        1 for m in meta
        if m.get("type") == "Security issue"
        and (m.get("status") or "").strip().lower() == "in progress")
    sec_pct = round(sec_in_progress / n_sec * 100, 1) if n_sec else None
    sec_statuses = Counter((m.get("status") or "").strip() or "Unknown (missing)"
                           for m in meta if m.get("type") == "Security issue")

    return {
        "types": types,
        "sdlc_matrix": sdlc_matrix,
        "sdlc_counts": sdlc_counts,
        "sdlc_totals": type_total,
        "sdlc_statuses": sdlc_statuses,
        "sdlc_types": sdlc_types,
        "vsm_findings": vsm_findings,
        "subbug_story_ratio": ratio,
        "backlog_stagnation": {"total": stagnation_total if stagnation_observed or not stagnation_unknown else None,
                               "by_type": stagnation_by_type,
                               "unknown": stagnation_unknown},
        "security_in_progress": {"count": sec_in_progress, "total": n_sec,
                                 "pct": sec_pct, "statuses": dict(sec_statuses)},
        "type_counts": dict(type_counts),
        "field_density": field_density,
        "data_type_map": data_type_map,
        "state_machines": state_machines,
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
