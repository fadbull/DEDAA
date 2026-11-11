"""Compute PM metrics from Jira metadata + documents (Tab 2)."""
from collections import Counter, defaultdict
from datetime import datetime
from .date_utils import _dt, _dt_full, _biweek, status_group, _status_events_from_text
from .metric_settings import DEFAULT_SETTINGS, merge_settings
from .jira_sprints import issue_sprints, sprint_catalog


import copy
import re


def _auto_seed_settings(S, raw_items):
    """[P1v3-2/3] + [P2v3-2] Settings-generation auto-seed.

    Runs at settings-GENERATION time (this function produces the runtime
    settings JSON the widget ships with) — the widget runtime never seeds.

    [P2v3-2] Review status set: fires ONLY when at least one status in the
    project vocabulary contains 'review' (case-insensitive). Multi-match →
    ALL matching statuses join the set. Zero matches → the set stays empty,
    no marker flag is written (the absence of the flag means "no candidates
    at generation time"). No JS-side seeding ever runs; manual edits are
    never overwritten by later regenerations (the seed writes only when the
    set is absent/empty).

    P1-2 Design Review Turnaround: seed designStart/reviewDone when each
    status is UNIQUELY present in the project status vocabulary:
      designStart = 'Design', reviewDone = 'Ready for Development'
    (case-insensitive). Both required.

    P1-3 Defect Escape Rate: scan labels of the metric's configured bug
    types; qaLabel = the UNIQUE label containing 'qa' (not 'review');
    reviewLabel = the UNIQUE label containing 'review' (not 'qa'). Both
    required. A marker flag records the seed so a later regeneration does
    not overwrite user edits (the flag survives export/import)."""
    out = copy.deepcopy(S)
    metrics = out.setdefault("metrics", {})

    # ---- [P2v3-2] Review status set auto-seed ----------------------------
    if not (S.get("statusSets") or {}).get("review"):
        vocab = set()
        for r in raw_items:
            st = str(r.get("status") or "").strip().lower()
            if st:
                vocab.add(st)
            for _t, to in (r.get("events") or []):
                if to:
                    vocab.add(to.strip().lower())
        matches = sorted(s for s in vocab if "review" in s)
        if matches:
            sets2 = copy.deepcopy(S.get("statusSets") or {})
            sets2["review"] = matches
            out["statusSets"] = sets2

    # ---- P1-2: Design Review Turnaround ---------------------------------
    dr = metrics.setdefault("designreview", {})
    if not dr.get("autoSeeded"):
        vocab = set()
        for r in raw_items:
            for _t, to in (r.get("events") or []):
                if to:
                    vocab.add(to.strip().lower())
        ds = [s for s in vocab if s == "design"]
        rd = [s for s in vocab if s == "ready for development"]
        if len(ds) == 1 and len(rd) == 1:
            dr["designStart"] = "Design"
            dr["reviewDone"] = "Ready for Development"
            dr["autoSeeded"] = True

    # ---- P1-3: Defect Escape Rate labels --------------------------------
    er = metrics.get("escapereview") or {}
    if not er.get("qaLabel") or not er.get("reviewLabel"):
        types_ref = er.get("types") or DEFAULT_SETTINGS["metrics"][
            "escapereview"]["types"]
        # Alias resolution ('bug' → the shared type list), as the runtime does.
        if isinstance(types_ref, str):
            types_ref = (S.get("types") or {}).get(types_ref) or []
        bug_types = {str(t).strip().lower() for t in (types_ref or [])}
        qa_labels, rev_labels = set(), set()
        for r in raw_items:
            if str(r.get("type") or "").strip().lower() not in bug_types:
                continue
            for lab in str(r.get("labels") or "").split(","):
                lab = lab.strip().lower()
                if not lab:
                    continue
                if "qa" in lab and "review" not in lab:
                    qa_labels.add(lab)
                if "review" in lab and "qa" not in lab:
                    rev_labels.add(lab)
        if len(qa_labels) == 1 and len(rev_labels) == 1:
            er["qaLabel"] = next(iter(qa_labels))
            er["reviewLabel"] = next(iter(rev_labels))
            er["autoSeeded"] = True
            metrics["escapereview"] = er
    return out


def _label_has(labels, want):
    """[P24-P2] Token label match (mirrors rcLabelHas in derive.py):
    'prod' matches prod / PROD / prod_* / prod-* / production, NOT
    product / non-prod / preprod."""
    want = (want or "").strip().lower()
    if not want:
        return False
    for tok in re.split(r"[,;\s]+", labels or ""):
        v = tok.strip().lower()
        if not v:
            continue
        if v == want or v.startswith(want + "_") or v.startswith(want + "-"):
            return True
        if want == "prod" and v == "production":
            return True
    return False


def compute_jira(meta, docs, settings=None):
    """Compute PM metrics from Jira metadata + documents.

    ``settings`` — optional metric-settings dict (see lib/metric_settings.py).
    When None, DEFAULT_SETTINGS are used, which reproduces the previous
    hardcoded behaviour byte-for-byte. The settings drive the status sets
    (dev start / done / QA entry / backlog / refinement), the production
    label and the priority->severity map used by every metric below."""
    S = merge_settings(settings)
    def _set(name):
        return {v.strip().lower() for v in (S.get("statusSets", {}).get(name) or [])}
    DONE_ST = _set("done") or {"closed", "done", "resolved", "complete",
                               "completed", "verified", "released"}
    DEVSTART_ST = _set("devStart") or {"in progress"}
    QA_ST = _set("qaEntry") or {"ready for qa", "in testing", "in qa",
                                "testing", "qa"}
    # [P0v3-F2] QA-exit statuses — the work PASSED QA (Time in QA end).
    QA_EXIT_ST = _set("qaExit") or {"ready for demo", "resolved", "closed"}
    BACKLOG_ST = _set("backlog") or {"new", "open", "to do", "backlog",
                                     "reopened", "ready for development",
                                     "ready for grooming", "ready for demo",
                                     "analysis", "design"}
    REFINEMENT_ST = _set("refinement") or {
        "new", "open", "to do", "backlog", "reopened", "ready for grooming",
        "refinement", "requirements", "backlog refinement", "grooming"}
    _PROD_LABEL = (S.get("prodLabel") or "prod").strip().lower()
    _SEV_MAP = S.get("severityMap") or {}

    def cfg_metric(mk):
        return (S.get("metrics") or {}).get(mk) or {}

    def _norm_type(t):
        """Normalize a raw Jira type to the UI label used in the settings
        (Bug -> Defect, Sub-Bug -> Sub-bug), lowercased."""
        low = (t or "").strip().lower()
        return "defect" if low == "bug" else low

    def _mtypes(mk, key="types"):
        """Resolve a metric's type-set reference (named set or explicit
        list) to a set of lowercase UI type labels."""
        ref = cfg_metric(mk).get(key)
        if ref is None:
            return set()
        if isinstance(ref, str):
            ref = (S.get("types") or {}).get(ref) or []
        return {t.strip().lower() for t in ref}

    def _first_status(ev, stset):
        """First event timestamp whose target status is in the set."""
        for t, to in ev:
            if (to or "").strip().lower() in stset:
                return t
        return None

    # ---- Team dimension (widget-level setting, not per-metric) ----------
    _TEAM_UNDEF = "Team is not defined"
    _tc = S.get("teamConfig") or {}
    _tc_source = _tc.get("source", "none")
    _tc_field = (_tc.get("fieldName") or "").strip()
    _tc_labels = {str(l).strip().lower(): str(l).strip()
                  for l in (_tc.get("labels") or []) if str(l).strip()}

    def _teams_for(m, d):
        """Resolve the issue's team(s) per the configured source.
        Returns a list (multi-membership for the labels source)."""
        if _tc_source == "field" and _tc_field:
            # The sync renders every custom field into the issue text as
            # "FieldName: value" lines; the native Team field (UUID) is
            # stored by its resolved display name the same way.
            val = _extract_field_value(d, _tc_field)
            if val:
                return [val]
            return []
        if _tc_source == "labels" and _tc_labels:
            labs = [x.strip().lower() for x in (m.get("labels") or "").split(",") if x.strip()]
            return [_tc_labels[l] for l in labs if l in _tc_labels]
        return []

    def _extract_field_value(doc, field_name):
        """Extract a field's value from the issue document text
        ('FieldName: value' line, first occurrence)."""
        if not doc:
            return None
        prefix = field_name + ":"
        for line in doc.splitlines():
            ls = line.strip()
            if ls.startswith(prefix):
                v = ls[len(prefix):].strip()
                if v:
                    return v
        return None

    def _story_points(doc):
        """Parse the issue's story points from the document text
        ('Story Points: N' line produced by the sync). Returns a float or
        None when the field is absent/empty."""
        import re
        if not doc:
            return None
        m = re.search(r"^Story Points:\s*([\d]+(?:[.,]\d+)?)", doc,
                      re.MULTILINE)
        if not m:
            return None
        try:
            return float(str(m.group(1)).replace(",", "."))
        except ValueError:
            return None

    def _time_spent(doc):
        """Parse the issue's logged work time from the document text
        ('Time Spent: N' line, seconds as produced by the Jira sync).
        Returns SECONDS (float) or None when the field is absent/empty.
        Used by the Bug Fixing Time Allocation metric (FIX-A5)."""
        import re
        if not doc:
            return None
        m = re.search(r"^Time Spent:\s*([\d]+(?:[.,]\d+)?)", doc,
                      re.MULTILINE)
        if not m:
            return None
        try:
            return float(str(m.group(1)).replace(",", "."))
        except ValueError:
            return None

    n = len(meta)
    by_type = Counter()
    by_status = Counter()
    by_priority = Counter()
    by_group = Counter()
    by_component = Counter()
    by_month = Counter()
    by_week = Counter()
    resolved_by_week = Counter()
    opened_by_week = Counter()
    opened_by_2wk = Counter()
    resolved_by_2wk = Counter()
    bugs = []
    security = []
    backlog_ready = []
    open_issues = []
    aging = []
    # CFD buckets by week
    cfd = defaultdict(lambda: Counter())
    cycle_times = []
    lead_times = []
    bug_cycle_times = []   # cycle time for Bug / Sub-Bug issues only
    bug_lead_times = []    # lead time for Bug / Sub-Bug issues only
    # Per-issue items for the combined "Process Metrics - Trends" widget.
    pm_cycle_items = []       # Cycle Time (avg days) - story/task
    pm_lead_items = []        # Lead Time (avg days) - story/task
    pm_flow_items = []        # Opened vs Resolved (two series) - all types
    pm_throughput_items = []  # Throughput (completed per period) - all types
    pm_velocity_items = []    # Velocity (completed Story/Task/Bug per period)
    pm_backlog_items = []     # Backlog Health (count) - issues in backlog/ready
    pm_bugflow_items = []     # Bug Growth (new vs resolved) - bug/sub-bug
    pm_leakage_items = []     # Defect Containment / Production Leakage - bugs
    pm_bugfix_items = []      # Bug Fixing Time Allocation (avg days) - bugs
    pm_incident_items = []    # Incident Frequency (prod bugs by severity)
    pm_qa_items = []          # Time in QA (avg days) - story/task w/ QA transition
    pm_defect_density_items = []  # Defect density (rate) - defects / stories+tasks
    pm_wip_items = []         # Work in Progress (count) - story/task in progress
    pm_floweff_items = []     # Flow Efficiency (%) - active / total elapsed
    pm_issue_dir = {}
    # Raw per-issue records (events/labels/priority/created/...) for the
    # dashboard's settings-driven metric derivation (RC_RAW).
    pm_raw_items = []
    pm_sprint_records = []

    # ---- Team-source discovery (before the main loop) ----------------------
    # Scan the issue documents for fields rendered as "Team: value" /
    # "Team Name: value" lines (the native Team field or custom fields).
    # These field names are offered as Team sources in the widget settings
    # and their per-issue values are embedded in RC_RAW (fieldvals) so the
    # browser can resolve source=field at runtime.
    import re
    _team_field_names = set()
    for _d in docs:
        if not _d:
            continue
        for _line in _d.splitlines():
            _ls = _line.strip()
            _mm = re.match(r"^(Team|Team Name):\s+(.+)$", _line)
            if _mm and _mm.group(2).strip():
                _team_field_names.add(_mm.group(1))
                break

    for m, d in zip(meta, docs):
        typ = m.get("type", "Unknown")
        status = m.get("status", "Unknown")
        prio = m.get("priority") or "None"
        created = m.get("created", "")
        updated = m.get("updated", "")
        resolution = m.get("resolution") or "None"
        resolution_date = m.get("resolutiondate", "")
        assignee = m.get("assignee") or "Unassigned"
        comp = m.get("components") or ""
        labels = m.get("labels") or ""
        # Story points (from the issue text 'Story Points: N' line) — used
        # by the Backlog Health coverage metric (Velocity in SP denominator).
        _sp = _story_points(d)
        # Logged work time in SECONDS (from the 'Time Spent: N' line) — used
        # by the Bug Fixing Time Allocation metric (FIX-A5).
        _ts = _time_spent(d)

        by_type[typ] += 1
        by_status[status] += 1
        by_priority[prio] += 1
        by_group[status_group(status)] += 1
        if comp:
            for c in [x.strip() for x in comp.split(",") if x.strip()]:
                by_component[c] += 1

        if _norm_type(typ) in _mtypes("bugflow"):
            bugs.append((m.get("issue_key"), m.get("summary"), status,
                         prio, m.get("url"), created, resolution_date))
        if typ.lower() == "security issue":
            security.append((m.get("issue_key"), m.get("summary"), status,
                             prio, m.get("url")))

        cd = _dt(created)
        ud = _dt(updated)
        rd = _dt(resolution_date)
        # Changelog-based status-transition timestamps
        idp = _dt(m.get("in_progress_date", ""))
        dnd = _dt(m.get("done_date", ""))
        if cd:
            wk = cd.isocalendar()[:2]
            by_week[f"{wk[0]}-W{wk[1]:02d}"] += 1
            by_month[cd.strftime("%Y-%m")] += 1
            opened_by_week[f"{wk[0]}-W{wk[1]:02d}"] += 1
            opened_by_2wk[_biweek(cd)] += 1
            cfd[f"{wk[0]}-W{wk[1]:02d}"][status_group(status)] += 1
            # Lead time = first Done/Closed (from changelog) - created.
            # Total lifetime in the system including queue/backlog wait.
            # This metric covers ONLY Story/Task issue types; bugs have their
            # own dedicated "Lead Time (Bug)" metric below.
            if _norm_type(typ) in _mtypes("cycle"):
                if dnd:
                    lead_times.append((dnd - cd).days)
                elif rd:
                    lead_times.append((rd - cd).days)
        if rd:
            wk = rd.isocalendar()[:2]
            resolved_by_week[f"{wk[0]}-W{wk[1]:02d}"] += 1
            resolved_by_2wk[_biweek(rd)] += 1
        # Cycle time = first Done - first In Progress (from changelog).
        # Active work duration only, excluding backlog/queue wait.
        # This metric covers ONLY Story/Task issue types; bugs have their own
        # dedicated "Cycle Time (Bug)" metric below.
        is_story_task = _norm_type(typ) in _mtypes("cycle")
        if idp and dnd:
            ct = (dnd - idp).days
            if is_story_task:
                cycle_times.append(ct)
            if _norm_type(typ) in _mtypes("bugflow"):
                bug_cycle_times.append(ct)
        elif idp and rd:
            ct = (rd - idp).days
            if is_story_task:
                cycle_times.append(ct)
            if _norm_type(typ) in _mtypes("bugflow"):
                bug_cycle_times.append(ct)
        # Bug-specific lead time (created -> done/resolved) for Bug/Sub-Bug.
        if _norm_type(typ) in _mtypes("bugflow"):
            if dnd and cd:
                bug_lead_times.append((dnd - cd).days)
            elif rd and cd:
                bug_lead_times.append((rd - cd).days)

        # ---- per-issue items for the combined Process Metrics - Trends widget
        # (per-metric type filters come from the metric settings; the dims and
        # dev_start anchors below mirror the JS derivation in dashboard_html)
        team = comp.split(",")[0].strip() if comp else "Unassigned"
        # Team dimension per the widget-level teamConfig source. `teams` is
        # a list (multi-membership for labels); `team` = first team or the
        # "Team is not defined" group (kept for the static by-team tables).
        teams = _teams_for(m, d)
        if not teams:
            teams = [_TEAM_UNDEF]
        dims = {
            "key": m.get("issue_key", ""),
            "project": m.get("project") or "Unknown",
            "team": teams[0],
            "teams": teams,
            "epic": m.get("epic") or m.get("parent_key") or "No Epic",
            "person": assignee,
            "type": typ,
        }
        # Cycle Time (avg days) - story/task with in-progress + done.
        # Clamp to >= 0: a negative duration (done before in-progress) is a
        # data anomaly that would otherwise render negative bars / Y-axis.
        # [P2-2] Zero-day rule (uniform with the JS derivation): an item with
        # a zero-day interval is excluded from the average.
        if is_story_task and idp and (dnd or rd):
            end = dnd or rd
            c_days = max(0, (end - idp).days)
            if c_days > 0:
                pm_cycle_items.append(dict(dims, days=c_days,
                                           dev_start=idp.isoformat()))
        # Lead Time (avg days) - story/task with created + done.
        # [P2-2] Zero-day items are excluded (incl. the resolutiondate
        # fallback — a 0-day fallback interval is not a real duration).
        if is_story_task and cd and (dnd or rd):
            end = dnd or rd
            l_days = max(0, (end - cd).days)
            if l_days > 0:
                # [P24-B] Bucketed by COMPLETION (end anchor) — completed-
                # item time metrics are reported in the period they finish.
                pm_lead_items.append(dict(dims, days=l_days,
                                          dev_start=end.isoformat()))
        # Opened vs Resolved (two series) - all types
        if cd:
            pm_flow_items.append(dict(dims, series="opened",
                                      dev_start=cd.isoformat()))
        if rd:
            pm_flow_items.append(dict(dims, series="resolved",
                                      dev_start=rd.isoformat()))
        # Throughput (completed per period) - all types
        if rd:
            pm_throughput_items.append(dict(dims, dev_start=rd.isoformat(),
                                            sp=_sp))
        # Velocity (completed Story/Task/Bug per period) — carries the
        # issue's story points so the JS can average Velocity in SP.
        if rd and _norm_type(typ) in _mtypes("velocity"):
            pm_velocity_items.append(dict(dims, dev_start=rd.isoformat(),
                                          sp=_sp))
        # Backlog Health - count of issues in backlog/ready states (by created).
        # Only the filterable issue types (Story/Task/Bug/Sub-bug/Sub-task) are
        # counted so the Issue Type filter can actually control the chart.
        _bl = status.lower()
        if (_norm_type(typ) in _mtypes("backlog")
                and cd and _bl in BACKLOG_ST):
            pm_backlog_items.append(dict(dims, dev_start=cd.isoformat()))
        # Bug Growth (new vs resolved) - bug/sub-bug only (two series)
        is_bug = _norm_type(typ) in _mtypes("bugflow")
        if is_bug and cd:
            pm_bugflow_items.append(dict(dims, series="new",
                                         dev_start=cd.isoformat()))
        if is_bug and rd:
            pm_bugflow_items.append(dict(dims, series="resolved",
                                         dev_start=rd.isoformat()))
        # [P0v3-F1] Production Leakage: numerator = prod-labelled defects.
        # [P3-LK] Denominator = defects that REACHED CHECKING: at least one
        # transition into a QA-set status OR the production label. Defects
        # caught before QA enter neither role (they diluted the denominator
        # and understated the leakage). Value = prod-labelled ÷
        # (QA-entered ∪ prod-labelled) × 100, bucketed by CREATED date (cd).
        if is_bug and cd:
            leaked = 1 if _label_has(labels, _PROD_LABEL) else 0
            _lk_in_qa = False
            for _lk_dt, _lk_st in _status_events_from_text(d):
                if (_lk_st or "").strip().lower() in QA_ST:
                    _lk_in_qa = True
                    break
            if _lk_in_qa or leaked:
                pm_leakage_items.append(dict(dims, leaked=0,
                                             dev_start=cd.isoformat()))
                if leaked:
                    pm_leakage_items.append(dict(dims, leaked=1,
                                                 dev_start=cd.isoformat()))
        # Bug Fixing Time Allocation - avg lead time (days) for bug/sub-bug.
        # Clamp to >= 0 (same data-anomaly guard as Cycle/Lead Time above).
        if is_bug and cd and (dnd or rd):
            end = dnd or rd
            pm_bugfix_items.append(dict(dims, days=max(0, (end - cd).days),
                                        dev_start=cd.isoformat()))
        # Incident Frequency - number of production defects (bugs tagged 'Prod')
        # per time period, by severity. Uses created date (when the incident was
        # opened/found). Severity is derived from priority: Critical/High ->
        # Critical, Major -> Major, Minor/Low/Trivial -> Minor.
        if is_bug and cd and _label_has(labels, _PROD_LABEL):
            _pl = prio.lower()
            _sev_map_i = cfg_metric("incident").get("severityMap") or _SEV_MAP
            sev = "Minor"
            for _sev_name in ("Critical", "Major", "Minor"):
                _sev_prios = [p.strip().lower()
                              for p in (_sev_map_i.get(_sev_name) or [])]
                if _pl in _sev_prios:
                    sev = _sev_name
                    break
            pm_incident_items.append(dict(dims, severity=sev,
                                          dev_start=cd.isoformat()))

        # ---- Additional Process Metrics (from status history) ----
        # Parse the issue's status history (status transitions with timestamps)
        # once and reuse it for Time in QA, WIP and Flow Efficiency.
        ev = _status_events_from_text(d)
        _ikey = m.get("issue_key")
        # Raw per-issue record for the dashboard's settings-driven derivation
        # (RC_RAW): everything the JS needs to re-derive every metric from
        # configurable status sets / anchors (see lib/metric_settings.py).
        if _ikey:
            sprint_present, sprints = issue_sprints(m, d)
            pm_sprint_records.extend(sprints)
            pm_raw_items.append({
                "key": _ikey,
                "type": typ,
                "project": m.get("project") or "Unknown",
                "team": team,
                "teams": teams,
                # Values of the discovered Team fields (the browser resolves
                # source=field at runtime so the setting can change live).
                "fieldvals": {f: _extract_field_value(d, f)
                              for f in _team_field_names},
                "epic": m.get("epic") or m.get("parent_key") or "No Epic",
                "person": assignee,
                "status": status,
                "created": (created or "")[:19],
                "resolutiondate": (resolution_date or "")[:10],
                "created_ts": created or "",
                "resolved_ts": resolution_date or "",
                "updated_ts": updated or "",
                "has_sprint": sprint_present,
                "sprint_ids": list(dict.fromkeys(s["id"] for s in sprints)),
                "labels": labels or "",
                "priority": prio,
                "sp": _sp,
                # Logged work time in seconds (None = no worklog). Normalized
                # to hours in the browser for the allocation metric (FIX-A5).
                "timeSpent": _ts,
                "events": [[t.isoformat(), to] for t, to in ev],
            })
        # Issue directory entry for the widget's issues table. days_in_status
        # = days since the last status transition (fallback: created date).
        _ikey = m.get("issue_key")
        if _ikey and _ikey not in pm_issue_dir:
            _last_change = ev[-1][0] if ev else None
            if _last_change is not None:
                _days = (datetime.now().date() - _last_change.date()).days
            elif cd:
                _days = (datetime.now() - cd).days
            else:
                _days = None
            pm_issue_dir[_ikey] = {
                "url": m.get("url") or "",
                "type": typ,
                "summary": (m.get("summary") or "")[:120],
                "status": status,
                "created": (created or "")[:10],
                "updated": (updated or "")[:10],
                "days_in_status": _days,
            }
        # 1) Time in QA (avg days) - Story/Task with a QA transition.
        #    in_qa = first entry into a QA status (Ready for QA / In Testing);
        #    qa_exit = first transition into a QA-PASSED status (Ready for
        #    DEMO / Resolved / Closed by default — [P0v3-F2] the dedicated
        #    qaExit set, NOT the general done set). QA time = exit - in_qa.
        if is_story_task:
            in_qa = done_ts = None
            for t, to in ev:
                low = to.strip().lower()
                if in_qa is None and low in QA_ST:
                    in_qa = t
                if done_ts is None and low in QA_EXIT_ST:
                    done_ts = t
                if in_qa and done_ts:
                    break
            if in_qa and done_ts and done_ts > in_qa:
                qa_days = (done_ts - in_qa).days
                # [P2-2] Zero-day rule: floor(<24h)=0 → excluded.
                if qa_days > 0:
                    pm_qa_items.append(dict(dims, days=qa_days,
                                            dev_start=done_ts.isoformat()))
        # 2) Defect density (rate) - defects found in QA / stories+tasks per
        #    period. [P0-B2] The numerator counts ONLY defects that have a
        #    transition into a QA status (found in QA) — prod-only defects
        #    are excluded (they still count in Production Leakage). The
        #    denominator (completed Story/Task) is unchanged.
        if cd:
            if is_bug:
                _dd_in_qa = any(to.strip().lower() in QA_ST for _, to in ev)
                # [P6-B5] Prod-labelled defects are excluded from the DD
                # numerator — they belong to Production Leakage (the two
                # populations must not overlap).
                _dd_prod = _label_has(labels, _PROD_LABEL)
                if _dd_in_qa and not _dd_prod:
                    pm_defect_density_items.append(dict(dims, density=1,
                                                        dev_start=cd.isoformat()))
            elif is_story_task:
                pm_defect_density_items.append(dict(dims, density=0,
                                                    dev_start=cd.isoformat()))
        # 3) Work in Progress (count) - Story/Task entering dev start.
        #    Bucketed by the date the issue entered the dev-start status.
        if is_story_task:
            for t, to in ev:
                if to.strip().lower() in DEVSTART_ST:
                    pm_wip_items.append(dict(dims, dev_start=t.isoformat()))
                    break
        # 4) Flow Efficiency (%) - active work time / total elapsed x 100.
        #    active = first dev-start -> first Done; total = Created -> first
        #    Done. Only issues with both transitions.
        if is_story_task:
            ip_ts = done_ts2 = None
            for t, to in ev:
                low = to.strip().lower()
                if ip_ts is None and low in DEVSTART_ST:
                    ip_ts = t
                if done_ts2 is None and low in DONE_ST:
                    done_ts2 = t
                if ip_ts and done_ts2:
                    break
            if (ip_ts and done_ts2 and done_ts2 > ip_ts and cd
                    and done_ts2.date() > cd.date()):
                active = (done_ts2 - ip_ts).days
                # done_ts2 is tz-aware (from _dt_full); cd is naive (from _dt).
                # Normalize to naive for a consistent day-level subtraction.
                done_naive = done_ts2.replace(tzinfo=None)
                total = (done_naive - cd).days
                if total > 0:
                    pm_floweff_items.append(dict(dims,
                                                 eff=active / total * 100.0,
                                                 dev_start=done_ts2.isoformat()))

        g = status_group(status)
        if g == "Backlog":
            open_issues.append((m.get("issue_key"), m.get("summary"), status,
                                prio, m.get("url"), created))
        if status.lower() == "ready for development":
            backlog_ready.append((m.get("issue_key"), m.get("summary"), prio,
                                  m.get("url")))
        if g != "Closed" and cd:
            age = (datetime.now() - cd).days
            if age > 30:
                aging.append((age, m.get("issue_key"), m.get("summary"),
                              status, prio, m.get("url")))

    aging.sort(reverse=True)
    # Build sorted week axis
    weeks = sorted(set(list(opened_by_week.keys()) + list(resolved_by_week.keys())))
    # CFD cumulative by week
    cfd_series = []
    running = Counter()
    for wk in weeks:
        running.update(cfd[wk])
        cfd_series.append({"week": wk, **dict(running)})

    # Bug growth: new vs resolved by week
    bug_new_by_week = Counter()
    bug_resolved_by_week = Counter()
    for m, d in zip(meta, docs):
        if m.get("type", "").lower() in ("bug", "sub-bug"):
            cd = _dt(m.get("created", ""))
            rd = _dt(m.get("resolutiondate", ""))
            if cd:
                wk = cd.isocalendar()[:2]
                bug_new_by_week[f"{wk[0]}-W{wk[1]:02d}"] += 1
            if rd:
                wk = rd.isocalendar()[:2]
                bug_resolved_by_week[f"{wk[0]}-W{wk[1]:02d}"] += 1

    # Open bugs by priority over time (current snapshot)
    # bugs tuple: (key, summary, status, prio, url, created, resolution_date)
    # Build open_bugs as (key, summary, PRIORITY, url, created)
    open_bugs = [(k, s, prio, u, c)
                 for k, s, _st, prio, u, c, _r2 in bugs
                 if status_group(_st) != "Closed"]
    open_bug_by_prio = Counter(p for _, _, p, _, _ in open_bugs)

    # Defect age by priority (age of unresolved defects by priority)
    defect_age = defaultdict(list)
    for k, s, _st, prio, _u, c, _r2 in bugs:
        if status_group(_st) != "Closed" and c:
            cd = _dt(c)
            if cd:
                defect_age[prio].append((datetime.now() - cd).days)

    # Velocity = count of completed WORK items (Story/Task/Bug), based on their
    # first Done/Closed transition date from the changelog. Grouped by 2-week
    # periods for biweekly capacity tracking.
    velocity_by_week = Counter()
    velocity_by_2wk = Counter()
    work_types = {"story", "task", "bug", "sub-bug"}
    for m in meta:
        if m.get("type", "").lower() not in work_types:
            continue
        dnd = _dt(m.get("done_date", ""))
        if dnd:
            wk = dnd.isocalendar()[:2]
            velocity_by_week[f"{wk[0]}-W{wk[1]:02d}"] += 1
            velocity_by_2wk[_biweek(dnd)] += 1

    # ------------------------------------------------------------------
    # Requirements Cycle Time — time from a requirement being CREATED to it
    # ENTERING DEVELOPMENT (first 'In Progress' transition from the changelog).
    # Definition: avg(story_dev_start - story_created) for stories/tasks that
    # entered development in the period. Period = sprint, or 2-week bucket if
    # sprints are absent (no sprint metadata stored). Breakdown by team
    # (component), project, type, and a trend over the last 5 periods.
    # ------------------------------------------------------------------
    req_types = _mtypes("cycle")
    req_cycle_by_period = defaultdict(list)   # period -> [days]
    req_cycle_by_team = defaultdict(list)     # team(component) -> [days]
    req_cycle_by_project = defaultdict(list)  # project -> [days]
    req_cycle_by_type = defaultdict(list)     # type -> [days]
    req_cycle_items = []  # per-issue records for the interactive chart
    for m, doc in zip(meta, docs):
        if _norm_type(m.get("type", "")) not in req_types:
            continue
        # Anchor-driven (settings): resolve the cycle metric's start/end
        # anchors from its config. {kind:'field'} -> date field;
        # {kind:'status',set} -> first transition into that status set from
        # the changelog. Defaults reproduce the pre-settings pipeline
        # (created -> first In Progress via the metadata field).
        _cyc = cfg_metric("cycle")

        def _resolve_anchor(spec, doc=doc, m=m):
            """Resolve an anchor spec to a naive datetime (or None)."""
            if spec.get("kind") == "field":
                if spec.get("field") == "resolutiondate":
                    return _dt(m.get("resolutiondate", ""))
                return _dt(m.get("created", ""))
            ts = _first_status(_status_events_from_text(doc), _set(spec["set"]))
            if ts is not None:
                return ts.replace(tzinfo=None)
            return None

        created = _resolve_anchor(_cyc["start"])
        if _cyc["end"].get("kind") == "field":
            dev_start = created if _cyc["end"].get("field") != "resolutiondate" \
                else _dt(m.get("resolutiondate", ""))
        elif _set(_cyc["end"]["set"]) != {"in progress"}:
            # Custom devStart set: re-derive from the status history
            # (metadata in_progress_date only knows "in progress").
            dev_start = _first_status(_status_events_from_text(doc),
                                      _set(_cyc["end"]["set"]))
            if dev_start is not None:
                dev_start = dev_start.replace(tzinfo=None)
            else:
                dev_start = _dt(m.get("in_progress_date", ""))
        else:
            dev_start = _dt(m.get("in_progress_date", ""))
        if not created or not dev_start or dev_start < created:
            continue
        days = (dev_start - created).days
        # [P2-2] Zero-day rule (uniform with the JS derivation): an item
        # with a zero-day interval does not enter the average.
        if days <= 0:
            continue
        period = _biweek(dev_start)
        req_cycle_by_period[period].append(days)
        # Team per the widget-level teamConfig source (multi-membership:
        # an issue with several teams counts in each).
        req_cycle_teams = _teams_for(m, doc) or [_TEAM_UNDEF]
        for _t in req_cycle_teams:
            req_cycle_by_team[_t].append(days)
        req_cycle_by_project[m.get("project") or "Unknown"].append(days)
        req_cycle_by_type[m.get("type") or "Unknown"].append(days)
        req_cycle_items.append({
            "key": m.get("issue_key", ""),
            "days": days,
            "dev_start": dev_start.isoformat(),
            "period": period,
            "project": m.get("project") or "Unknown",
            "team": (req_cycle_teams or [_TEAM_UNDEF])[0],
            "epic": m.get("epic") or m.get("parent_key") or "No Epic",
            "person": m.get("assignee") or "Unassigned",
            "type": m.get("type") or "Unknown",
        })

    def _avg_rc(d):
        return round(sum(d) / len(d), 1) if d else None

    # Per-period averages (sorted) + last 5 periods trend.
    req_cycle_periods = sorted(req_cycle_by_period.keys())
    req_cycle_trend = [
        {"period": p, "avg_days": _avg_rc(req_cycle_by_period[p]),
         "count": len(req_cycle_by_period[p])}
        for p in req_cycle_periods[-5:]
    ]
    req_cycle_overall = _avg_rc(
        [d for lst in req_cycle_by_period.values() for d in lst])
    req_cycle_by_team_rows = sorted(
        ({"team": t, "avg_days": _avg_rc(v), "count": len(v)}
         for t, v in req_cycle_by_team.items()),
        key=lambda r: (r["avg_days"] is None, -(r["avg_days"] or 0)))
    req_cycle_by_project_rows = sorted(
        ({"project": p, "avg_days": _avg_rc(v), "count": len(v)}
         for p, v in req_cycle_by_project.items()),
        key=lambda r: (r["avg_days"] is None, -(r["avg_days"] or 0)))
    req_cycle_by_type_rows = sorted(
        ({"type": t, "avg_days": _avg_rc(v), "count": len(v)}
         for t, v in req_cycle_by_type.items()),
        key=lambda r: (r["avg_days"] is None, -(r["avg_days"] or 0)))

    # ------------------------------------------------------------------
    # Requirements Rework Rate — % of stories that return to
    # requirements/refinement (backlog: New/Open/To Do/Backlog/Reopened) AFTER
    # entering development. Formula:
    #   (Stories reopened or returned to backlog after dev started)
    #   / (Total stories started) × 100%
    # Period = sprint, or 2-week bucket if sprints are absent. Breakdown by
    # team (component) and project, with a trend over the last 5 periods.
    # HEALTHY < 10%; consistently >20% indicates a requirements quality issue.
    # ------------------------------------------------------------------
    # Rework = returned to requirements/refinement after dev started. Includes
    # backlog states (New/Open/To Do/Backlog/Reopened) AND refinement states
    # (Analysis/Design/Ready for Development/Ready for Grooming) — the statuses
    # this project uses to send work back for re-clarification.
    # Rework "return-to" status set comes from the metric settings
    # (statusSets.refinement by default).
    _BACKLOG_ST = REFINEMENT_ST
    req_rework_by_period = defaultdict(lambda: {"reworked": 0, "total": 0})
    req_rework_by_team = defaultdict(lambda: {"reworked": 0, "total": 0})
    req_rework_by_project = defaultdict(lambda: {"reworked": 0, "total": 0})
    req_rework_items = []  # per-issue records for the interactive chart
    for m, doc in zip(meta, docs):
        if m.get("type", "").lower() not in req_types:
            continue
        dev_start = _dt(m.get("in_progress_date", ""))
        if not dev_start:
            continue
        # Sort status events; find the first transition into development.
        ev = _status_events_from_text(doc)
        # The anchor is the FIRST transition into the devStart set (the same
        # semantics as the JS derivation's rework.anchor). Matching by date
        # against the metadata in_progress_date was wrong: when several
        # events share that calendar day (e.g. Open -> Analysis ->
        # Ready for Development -> In Progress within seconds) it anchored at
        # the FIRST event of the day, so pre-development refinement hops were
        # miscounted as rework. Anchor on the first DEVSTART_ST event
        # directly (mirrors rcDeriveAll's firstEvIdx(ev, DEV)).
        dev_idx = None
        for i, (dt, st) in enumerate(ev):
            if (st or "").strip().lower() in DEVSTART_ST:
                dev_idx = i
                break
        if dev_idx is None:
            # Fallback: metadata date without a matching changelog event —
            # anchor at the first event on/after that date.
            for i, (dt, st) in enumerate(ev):
                if dt and dt.date() >= dev_start.date():
                    dev_idx = i
                    break
        if dev_idx is None:
            continue
        # Rework = any event AFTER dev_start whose target status is a backlog
        # /refinement status (New/Open/To Do/Backlog/Reopened).
        reworked = False
        for dt, st in ev[dev_idx + 1:]:
            if (st or "").strip().lower() in _BACKLOG_ST:
                reworked = True
                break
        period = _biweek(dev_start)
        # Team per the widget-level teamConfig source (multi-membership).
        rework_teams = _teams_for(m, doc) or [_TEAM_UNDEF]
        req_rework_by_period[period]["total"] += 1
        req_rework_by_project[m.get("project") or "Unknown"]["total"] += 1
        for _t in rework_teams:
            req_rework_by_team[_t]["total"] += 1
        if reworked:
            req_rework_by_period[period]["reworked"] += 1
            req_rework_by_project[m.get("project") or "Unknown"]["reworked"] += 1
            for _t in rework_teams:
                req_rework_by_team[_t]["reworked"] += 1
        req_rework_items.append({
            "key": m.get("issue_key", ""),
            "reworked": reworked,
            "dev_start": dev_start.isoformat(),
            "period": period,
            "project": m.get("project") or "Unknown",
            "team": (rework_teams or [_TEAM_UNDEF])[0],
            "epic": m.get("epic") or m.get("parent_key") or "No Epic",
            "person": m.get("assignee") or "Unassigned",
            "type": m.get("type") or "Unknown",
        })

    # ------------------------------------------------------------------
    # [P2v3-1] Clarification Cycle Count — returns to refinement BEFORE the
    # first dev-start (per requirement that entered development; count 0
    # participates). Bucket = the first dev-start transition.
    # [P2v3-2] Review Cycle Count: review-set entries − 1 per reviewed item
    # whose CURRENT status is in the done set; anchor = the LAST done
    # transition (the re-review count is only final there).
    # ------------------------------------------------------------------
    # [P2v3-2] The review set the RUNTIME sees = the seeded settings (the
    # widget derives from pm_settings, not from the pre-seed S) — resolve the
    # seed here so the Python ground truth matches the JS derivation.
    _seeded = _auto_seed_settings(S, pm_raw_items)
    _REVIEW_ST = {v.strip().lower() for v in
                  ((_seeded.get("statusSets") or {}).get("review") or [])}
    pm_clarcycle_items = []
    pm_reviewcycle_items = []
    # [P6-B2] The clarcycle return-to set follows the metric settings (the
    # same set-map semantics as the JS derivation) — no hardcoded refinement.
    _clar_set_name = ((S.get("metrics", {}).get("clarcycle", {})
                       .get("returnTo") or {}).get("set")) or "refinement"
    _CLAR_RETURN_ST = _set(_clar_set_name) or REFINEMENT_ST
    # [P5-TP] Resolve via _mtypes: alias-aware ("work" etc.) — the manual
    # inline resolution above would iterate a STRING alias char-by-char.
    _clarcycle_types = _mtypes("clarcycle")
    _reviewcycle_types = _mtypes("reviewcycle")
    for m, doc in zip(meta, docs):
        _typ = _norm_type(m.get("type", ""))
        ev = _status_events_from_text(doc)
        cd = _dt(m.get("created", ""))
        # ---- Clarification Cycle Count ----------------------------------
        if _typ in _clarcycle_types:
            dev_idx = None
            for i, (dt, st) in enumerate(ev):
                if (st or "").strip().lower() in DEVSTART_ST:
                    dev_idx = i
                    break
            if dev_idx is not None:
                # [P2v3-1] The counter counts RETURNS to refinement (a
                # transition into a refinement status while outside it);
                # the creation counts as the first (free) entry. Worked
                # examples: straight flow = 0; one back-and-forth = 1.
                cycles = 0
                in_ref = True   # an item begins its life in refinement
                for dt, st in ev[:dev_idx]:
                    low = (st or "").strip().lower()
                    if low in _CLAR_RETURN_ST or low == "created":
                        if not in_ref:
                            cycles += 1     # a RETURN to refinement
                        in_ref = True
                    elif low in DEVSTART_ST:
                        break               # anchor event
                    else:
                        in_ref = False      # groomed/ready state
                pm_clarcycle_items.append({
                    "key": m.get("issue_key", ""),
                    "cycles": cycles,
                    "dev_start": ev[dev_idx][0].isoformat(),
                })
        # Review Cycle Count ------------------------------------------------
        if _typ in _reviewcycle_types:
            # Gate: the item's CURRENT status must be in the done set.
            if (m.get("status") or "").strip().lower() in DONE_ST:
                # Anchor = the LAST transition into done.
                last_done = None
                for dt, st in ev:
                    if (st or "").strip().lower() in DONE_ST:
                        last_done = dt
                entries = 0
                for dt, st in ev:
                    if last_done and dt > last_done:
                        break
                    if (st or "").strip().lower() in _REVIEW_ST:
                        entries += 1
                if entries >= 1:
                    pm_reviewcycle_items.append({
                        "key": m.get("issue_key", ""),
                        "count": entries - 1,
                        "dev_start": last_done.isoformat(),
                    })

    def _rework_rate(d):
        total = d.get("total", 0)
        if not total:
            return None
        return round(d.get("reworked", 0) / total * 100.0, 1)

    req_rework_periods = sorted(req_rework_by_period.keys())
    req_rework_trend = [
        {"period": p, "rate": _rework_rate(req_rework_by_period[p]),
         "reworked": req_rework_by_period[p]["reworked"],
         "total": req_rework_by_period[p]["total"]}
        for p in req_rework_periods[-5:]
    ]
    req_rework_overall = _rework_rate(
        {"reworked": sum(v["reworked"] for v in req_rework_by_period.values()),
         "total": sum(v["total"] for v in req_rework_by_period.values())})
    req_rework_by_team_rows = sorted(
        ({"team": t, "rate": _rework_rate(v), "reworked": v["reworked"],
          "total": v["total"]}
         for t, v in req_rework_by_team.items()),
        key=lambda r: (r["rate"] is None, -(r["rate"] or 0)))
    req_rework_by_project_rows = sorted(
        ({"project": p, "rate": _rework_rate(v), "reworked": v["reworked"],
          "total": v["total"]}
         for p, v in req_rework_by_project.items()),
        key=lambda r: (r["rate"] is None, -(r["rate"] or 0)))

    # Scope Change Volume — number of CHANGED work items (Story/Task/Bug) per
    # period. A change is any status transition recorded in the issue changelog
    # (e.g. New -> Open, Open -> In Progress, In Progress -> Resolved).
    #   * If sprints exist -> count changed issues per sprint.
    #   * If no sprints  -> count changed issues per 2-week (biweekly) period.
    # An issue is counted once per period in which it had at least one status
    # change (deduplicated by (issue, period)).
    def _status_history_timestamps(doc_text):
        """Parse 'Status history:' lines from a document into a list of datetimes."""
        out = []
        if not doc_text or "Status history:" not in doc_text:
            return out
        section = doc_text.split("Status history:", 1)[1]
        for line in section.splitlines():
            line = line.strip()
            if not line or ":" not in line.split(" -> ")[0]:
                continue
            ts = line.split(":", 1)[0].strip()
            dt = _dt(ts)
            if dt:
                out.append(dt)
        return out

    # Sprint membership per issue (only when sprints are present).
    # Metadata does not store sprint ids currently; if a future sync stores
    # 'sprint' metadata we use it, otherwise we fall back to 2-week periods.
    has_sprints = any((m.get("sprint") or "") for m in meta)

    scope_change_2wk = Counter()   # keyed by 2-week period (no sprints)
    scope_change_sprint = Counter()  # keyed by sprint name (when sprints exist)
    for m, doc in zip(meta, docs):
        if m.get("type", "").lower() not in work_types:
            continue
        chg_times = _status_history_timestamps(doc)
        if not chg_times:
            # No changelog captured: fall back to created/resolved timestamps
            # so the issue still contributes to scope churn.
            for raw in (m.get("created", ""), m.get("done_date", ""),
                        m.get("resolutiondate", "")):
                dt = _dt(raw)
                if dt:
                    chg_times.append(dt)
        if not chg_times:
            continue
        sprint = (m.get("sprint") or "").strip()
        if has_sprints and sprint:
            for _dt_ in set(chg_times):
                scope_change_sprint[sprint] += 1
        else:
            for _dt_ in set(chg_times):
                scope_change_2wk[_biweek(_dt_)] += 1

    # Average Scope Change Volume: mean number of changed Story/Task/Bug issues
    # per period. Per sprint when sprints exist, otherwise per 2-week period.
    avg_scope_change_sprint = (
        round(sum(scope_change_sprint.values()) / len(scope_change_sprint), 1)
        if scope_change_sprint else None)
    avg_scope_change_2wk = (
        round(sum(scope_change_2wk.values()) / len(scope_change_2wk), 1)
        if scope_change_2wk else None)

    # ---- Additional extractable metrics (from labels / metadata) ----
    # 1) Defect containment / production leakage: bugs tagged 'Prod' indicate
    #    defects found in production (leaked past QA). Leakage rate =
    #    prod bugs / total bugs.
    prod_bugs = []
    all_bugs = []
    for m in meta:
        if m.get("type", "").lower() in ("bug", "sub-bug"):
            all_bugs.append(m)
            labels = (m.get("labels") or "").lower()
            if "prod" in labels:
                prod_bugs.append(m)
    prod_bug_keys = [m.get("issue_key") for m in prod_bugs]
    defect_leakage_rate = (len(prod_bugs) / len(all_bugs) * 100
                           if all_bugs else None)

    # 2) Security posture: SAST/CWE-labeled issues and security-type issues.
    sast_prefixes = ("sast", "gitleaks", "checkmarx", "snyk", "cwe-")
    sast_issues = []
    for m in meta:
        labels = (m.get("labels") or "").lower()
        if any(p in labels for p in sast_prefixes):
            sast_issues.append(m)
    sec_type_issues = [m for m in meta
                       if m.get("type", "").lower() in ("security issue",
                                                        "vulnerability",
                                                        "security")]
    # CWE type distribution (from labels)
    cwe_by_code = Counter()
    sast_by_tool = Counter()
    for m in sast_issues:
        labels = (m.get("labels") or "")
        for lab in labels.split(","):
            lab = lab.strip()
            if lab.lower().startswith("cwe-"):
                cwe_by_code[lab] += 1
            elif lab.lower() in ("sast", "gitleaks", "checkmarx_cxsast",
                                 "snyksast"):
                tool = {"sast": "SAST", "gitleaks": "Gitleaks",
                        "checkmarx_cxsast": "Checkmarx CxSAST",
                        "snyksast": "Snyk SAST"}.get(lab.lower(), lab)
                sast_by_tool[tool] += 1
    # security issues still open (not closed)
    sec_open = [m for m in sec_type_issues
                if status_group(m.get("status")) != "Closed"]

    # 3) Work distribution by component (top areas)
    by_component = Counter()
    for m in meta:
        comp = m.get("components") or ""
        if comp:
            for c in [x.strip() for x in comp.split(",") if x.strip()]:
                by_component[c] += 1

    return {
        "total": n,
        "team_fields": sorted(_team_field_names),
        "team_undefined_count": sum(
            1 for i in pm_raw_items if i.get("teams") == [_TEAM_UNDEF]),
        "by_type": by_type,
        "by_status": by_status,
        "by_priority": by_priority,
        "by_group": by_group,
        "by_component": by_component,
        "by_month": by_month,
        "by_week": by_week,
        "opened_by_week": opened_by_week,
        "resolved_by_week": resolved_by_week,
        "opened_by_2wk": opened_by_2wk,
        "resolved_by_2wk": resolved_by_2wk,
        "resolved_by_2wk": resolved_by_2wk,
        "velocity_by_week": velocity_by_week,
        "velocity_by_2wk": velocity_by_2wk,
        "scope_change_2wk": scope_change_2wk,
        "scope_change_sprint": scope_change_sprint,
        "avg_scope_change_2wk": avg_scope_change_2wk,
        "avg_scope_change_sprint": avg_scope_change_sprint,
        "has_sprints": has_sprints,
        "bug_new_by_week": bug_new_by_week,
        "bug_resolved_by_week": bug_resolved_by_week,
        "open_bugs": open_bugs,
        "open_bug_by_prio": open_bug_by_prio,
        "defect_age": dict(defect_age),
        "bugs": bugs,
        "security": security,
        "backlog_ready": backlog_ready,
        "open_count": len(open_issues),
        "open_issues": open_issues,
        "aging": aging,
        "cfd_series": cfd_series,
        "cycle_times": cycle_times,
        "lead_times": lead_times,
        "avg_cycle": (sum(cycle_times) / len(cycle_times)) if cycle_times else None,
        "avg_lead": (sum(lead_times) / len(lead_times)) if lead_times else None,
        # Bug-specific cycle / lead time metrics (Bug & Sub-Bug only).
        "bug_cycle_times": bug_cycle_times,
        "bug_lead_times": bug_lead_times,
        "avg_bug_cycle": (sum(bug_cycle_times) / len(bug_cycle_times))
                         if bug_cycle_times else None,
        "avg_bug_lead": (sum(bug_lead_times) / len(bug_lead_times))
                        if bug_lead_times else None,
        "bug_cycle_count": len(bug_cycle_times),
        # Requirements Cycle Time (created -> entering development)
        "req_cycle_overall": req_cycle_overall,
        "req_cycle_trend": req_cycle_trend,
        "req_cycle_by_team": req_cycle_by_team_rows,
        "req_cycle_by_project": req_cycle_by_project_rows,
        "req_cycle_by_type": req_cycle_by_type_rows,
        "req_cycle_items": req_cycle_items,
        # Per-issue items for the combined "Process Metrics - Trends" widget
        "pm_cycle_items": pm_cycle_items,
        "pm_lead_items": pm_lead_items,
        "pm_flow_items": pm_flow_items,
        "pm_throughput_items": pm_throughput_items,
        "pm_velocity_items": pm_velocity_items,
        "pm_backlog_items": pm_backlog_items,
        "pm_bugflow_items": pm_bugflow_items,
        "pm_leakage_items": pm_leakage_items,
        "pm_bugfix_items": pm_bugfix_items,
        "pm_incident_items": pm_incident_items,
        "pm_qa_items": pm_qa_items,
        "pm_defect_density_items": pm_defect_density_items,
        "pm_wip_items": pm_wip_items,
        "pm_floweff_items": pm_floweff_items,
        "pm_issue_dir": pm_issue_dir,
        "pm_raw_items": pm_raw_items,
        "pm_sprint_catalog": sprint_catalog(pm_sprint_records),
        "pm_sprint_coverage": {
            "total": len(pm_raw_items),
            "populated": sum(bool(r["has_sprint"]) for r in pm_raw_items),
        },
        "pm_settings": _auto_seed_settings(S, pm_raw_items),
        # [P2v3-1/2] New metrics: Python ground truth for the parity harness.
        "pm_clarcycle_items": pm_clarcycle_items,
        "pm_reviewcycle_items": pm_reviewcycle_items,
        # Requirements Rework Rate (returned to backlog after dev started)
        "req_rework_overall": req_rework_overall,
        "req_rework_trend": req_rework_trend,
        "req_rework_by_team": req_rework_by_team_rows,
        "req_rework_by_project": req_rework_by_project_rows,
        "req_rework_items": req_rework_items,
        # Additional extractable metrics
        "total_bugs": len(all_bugs),
        "prod_bugs": len(prod_bugs),
        "prod_bug_keys": prod_bug_keys,
        "defect_leakage_rate": defect_leakage_rate,
        "sast_issues": len(sast_issues),
        "sast_by_tool": dict(sast_by_tool),
        "cwe_by_code": dict(cwe_by_code),
        "sec_type_issues": len(sec_type_issues),
        "sec_open": len(sec_open),
        "sec_open_issues": sec_open,
        "by_component": dict(by_component),
    }
