"""Metric settings for the "Process Metrics - Trends" widget and the static
process-metric widgets.

Single source of truth for:
- global status sets (which statuses count as "start of development",
  "done", "QA entry", "backlog", "refinement/requirements"),
- per-metric formula parameters (issue types, start/end anchors,
  aggregation, default window, trend direction/stable band %, display),
- unique extras (production label, priority->severity map, series names,
  numerator/denominator type sets, dual intervals).

Used by:
- compute_jira()      — Python-side recomputation (static widgets + Trends
                        items) when settings are passed via
                        --metric-settings;
- dashboard_html.py   — embeds the settings as RC_SETTINGS so the browser can
                        re-derive every metric from raw changelog events
                        (RC_RAW) when the user edits settings in the gear
                        panel.
"""
import copy
import json

# ---------------------------------------------------------------------------
# Default settings — byte-compatible with the previous hardcoded behaviour.
# ---------------------------------------------------------------------------
DEFAULT_SETTINGS = {
    # Global status sets (lowercase comparisons). Referenced by metrics via
    # the set name; per-metric overrides may point at a different set.
    "statusSets": {
        "devStart": ["in progress"],
        "done": ["closed", "done", "resolved", "complete", "completed",
                 "verified", "released"],
        "qaEntry": ["ready for qa", "in testing", "in qa", "testing", "qa"],
        # [P0v3-F2] QA-exit set — the statuses that mark the work as PASSED
        # QA (NOT the final closure): Time in QA ends at the first transition
        # into one of these. Editable in Widget settings alongside the others.
        "qaExit": ["ready for demo", "resolved", "closed"],
        # QA statuses (set: qaSet) — the Defect Containment denominator set:
        # a bug counts as "tested" when it has EVER transitioned into one of
        # these statuses (or carries the prod label). Case-insensitive.
        "qaSet": ["ready for qa", "in testing", "in qa", "testing", "qa"],
        # "Ready" set — the status that marks a Story/Task (or Defect, when
        # the defect workflow has such a status) as READY FOR DEVELOPMENT.
        # This is the Backlog Health membership set (NOT the backlog set).
        "ready": ["ready for development"],
        "backlog": ["new", "open", "to do", "backlog", "reopened",
                    "ready for development", "ready for grooming",
                    "ready for demo", "analysis", "design"],
        # Refinement / rework return-to set. The "ready*" gate statuses
        # (Ready for Development / Ready for Demo) and the analysis/design
        # working statuses are NOT refinement-queue statuses by default:
        # returning to them is normal flow, not requirements rework.
        "refinement": ["new", "open", "to do", "backlog", "reopened",
                       "ready for grooming", "refinement", "requirements",
                       "backlog refinement", "grooming"],
        # [P2-M] Review statuses (Review Cycle Count). Default empty: the
        # settings-generation auto-seed fills it from the project vocabulary
        # (statuses containing 'review'); empty set = the metric's N/A state.
        "review": [],
    },
    # Issue-type label used by the UI filter; raw Jira types are normalized
    # (Bug->Defect, Sub-Bug->Sub-bug) before comparison.
    "types": {
        # "delivery" now means Story/Task/Defect (Throughput default).
        # Opened vs Resolved and Backlog Health get their own narrower sets.
        "delivery": ["Story", "Task", "Defect"],
        "req": ["Story", "Task"],
        # [P2-1] The bug alias covers BOTH defect types — consistent with the
        # other bug-metric defaults (incident/leakage/defectdensity/bugfix).
        "bug": ["Defect", "Sub-bug"],
        # [P0v3-F4] Velocity/Throughput: NO child defect type (Sub-bug) —
        # child defects are counted through their parent defect's completion;
        # counting them again at the child level double-counts the work.
        "velocity": ["Story", "Task", "Defect"],
        # Opened vs Resolved: requirements flow only (Story+Task).
        "flow": ["Story", "Task"],
        # Backlog Health: ready STORY/TASK backlog (Defects follow the
        # separate 'defects' auto/include/exclude switch).
        "backlog": ["Story", "Task"],
        # [P5-TP] Generic work items: every type the status-driven time/flow
        # metrics apply to (In Progress→Done, QA, active/total, PR review).
        # The top-level Issue Type filter can narrow to Defect+Sub-bug (Bug
        # Cycle Time) without touching metric settings.
        "work": ["Story", "Task", "Defect", "Sub-bug"],
    },
    # Widget-level Team dimension configuration (NOT a per-metric setting).
    # source:
    #   "none"   — Team is not configured: every issue belongs to the
    #              "Team is not defined" group (the default);
    #   "field"  — a Jira field named Team / Team Name (native Team field or
    #              a custom field); `fieldName` is the exact field NAME as
    #              rendered in the issue text ("Team: <value>" lines);
    #   "labels" — each label in `labels` is a team; an issue belongs to
    #              EVERY matching label (multi-membership).
    # Issues with no resolved team fall into the "Team is not defined" group
    # (visible and included by default, filterable).
    "teamConfig": {
        "source": "none",     # none | field | labels
        "fieldName": "",      # source=field: exact field name (e.g. "Team")
        "labels": [],         # source=labels: selected labels = team names
    },
    # Label marking a bug as escaped to production. Default 'prod' matches
    # the prod token, prod_* / prod-* and production, case-insensitively;
    # an explicit non-default value overrides the widget-level default.
    "prodLabel": "prod",
    # [P3-2] Sprint data availability (widget-level): auto | available | none.
    # auto: actual Sprint periods when >50% of all project issues have Sprint;
    # available forces real sprints; none forces two-week calendar periods.
    # Also controls sprint availability for the Backlog Health auto state.
    "sprintData": "auto",
    # priority (lowercase) -> severity group for Incident Frequency.
    # Minor is explicit (Normal/Trivial); anything not listed anywhere still
    # falls back to Minor.
    # [P2-3] Unambiguous default mapping: each Jira priority lands in
    # exactly one group. Major = genuinely elevated (high/major) — the
    # default Jira priority ('major'/'medium') must not inflate it.
    "severityMap": {
        "Critical": ["blocker", "critical", "highest"],
        "Major": ["high", "major"],
        "Minor": ["medium", "normal", "low", "minor", "trivial"],
    },
    "metrics": {
        # ---- Time-based -------------------------------------------------
        "cycle": {  # Requirements Cycle Time
            "types": "req",
            "start": {"kind": "field", "field": "created"},
            "end": {"kind": "status", "set": "devStart"},
            "aggregation": "avg", "value": "days",
            "granularity": "sprint", "defaultN": 5,
            "trendDir": "down", "stablePct": 10,
            "label": "Requirements Cycle Time (avg days)",
        },
        "cycletime": {  # Cycle Time (active phase)
            # [P5-TP] "work": In Progress→Done applies to every work type —
            # the top filter can narrow to Defect+Sub-bug (Bug Cycle Time).
            "types": "work",
            "start": {"kind": "status", "set": "devStart"},
            "end": {"kind": "status", "set": "done"},
            "aggregation": "avg", "value": "days",
            "granularity": "sprint", "defaultN": 5,
            "trendDir": "down", "stablePct": 10,
            "label": "Cycle Time (avg days)",
        },
        # [FIX-A3] Lead Time = Work Item Lead Time (created → done) for ANY
        # Issue Type — pick Defect+Sub-bug in the top filter for Bug Lead
        # Time, Story+Task for Story/Task Lead Time. Bucket = created.
        "lead": {
            "types": ["Story", "Task", "Defect", "Sub-bug"],
            "start": {"kind": "field", "field": "created"},
            "end": {"kind": "status", "set": "done", "fallback": "resolutiondate"},
            "aggregation": "avg", "value": "days",
            "granularity": "sprint", "defaultN": 5,
            "trendDir": "down", "stablePct": 10,
            "label": "Lead Time (avg days)",
        },
        "qa": {  # Time in QA
            # [P5-TP] "work": defects pass QA too — the top filter can narrow.
            "types": "work",
            "start": {"kind": "status", "set": "qaEntry"},
            # [P0v3-F2] The end anchor is the QA-EXIT set (the work PASSED
            # QA), not the general done set — post-QA statuses (between the
            # QA exit and the final Done) must not count as QA time.
            "end": {"kind": "status", "set": "qaExit"},
            "aggregation": "avg", "value": "days",
            "granularity": "sprint", "defaultN": 5,
            "trendDir": "down", "stablePct": 10,
            "label": "Time in QA (avg days)",
        },
        # [FIX-A5] Bug Fixing Time Allocation = Σ(timespent on Bug/Sub-bug)
        # ÷ Σ(timespent on ALL completed work) × 100% per period (Jira
        # worklog). N/A when the timespent fill-rate < 20%.
        "bugfix": {
            "types": ["Defect", "Sub-bug"],
            "aggregation": "allocation",
            "requires": "timeSpent",
            "granularity": "sprint", "defaultN": 5,
            "trendDir": "down", "stablePct": 10,
            "label": "Bug Fixing Time Allocation (%)",
        },
        # [FIX-A4] WIP = point-in-time SNAPSHOT at each period end:
        # wip(P) = # items with enterDev ≤ endOf(P) < leaveDev, where
        # enterDev = first transition into devStart, leaveDev = first
        # transition into done AFTER enterDev (QA statuses do NOT close
        # WIP). Buckets come from the axis range, not from completions.
        "wip": {
            "types": ["Story", "Task", "Defect", "Sub-bug"],
            "start": {"kind": "status", "set": "devStart"},
            "end": {"kind": "status", "set": "done"},
            "aggregation": "wipSnapshot",
            "granularity": "sprint", "defaultN": 5,
            "trendDir": "down", "stablePct": 10,
            "label": "Work in Progress (WIP)",
        },
        "floweff": {  # Flow Efficiency — unique: two intervals
            # [P5-TP] "work": active/total applies to every work type.
            "types": "work",
            "active": {"start": {"kind": "status", "set": "devStart"},
                       "end": {"kind": "status", "set": "done"}},
            "total": {"start": {"kind": "field", "field": "created"},
                      "end": {"kind": "status", "set": "done"}},
            "aggregation": "avg", "value": "eff",
            "granularity": "sprint", "defaultN": 5,
            "trendDir": "up", "stablePct": 10, "avgUnit": "%",
            "label": "Flow Efficiency (%)",
        },
        # ---- Count & rate ------------------------------------------------
        "throughput": {
            "types": "delivery",
            "start": {"kind": "field", "field": "resolutiondate"},
            "aggregation": "count",
            "granularity": "sprint", "defaultN": 5,
            "trendDir": "up", "stablePct": 10,
            "label": "Throughput (completed)",
        },
        "velocity": {
            "types": "velocity",
            "start": {"kind": "field", "field": "resolutiondate"},
            "aggregation": "count",
            "granularity": "sprint", "defaultN": 5,
            "trendDir": "up", "stablePct": 10,
            # [P1-STATES] Velocity state: auto picks SP velocity when the
            # window carries story points, else issue counts.
            "velocityMode": "auto",
            "label": "Issue Velocity (completed items per period)",
        },
        "backlog": {  # unique: coverage = ready items ÷ team speed
            # Backlog Health measures HOW MANY SPRINTS of ready work the
            # backlog holds (optimal 2–3), not the raw ready-item count:
            #   issues READY FOR DEVELOPMENT (the 'ready' status set) at
            #   each period end ÷ Average Velocity in story points per
            #   period (fallback: Average Throughput when no story points).
            # Defects are EXCLUDED by default (defects = auto | include |
            # exclude); set 'auto' to let the defect workflow decide.
            "types": "backlog",
            "membership": {"kind": "status", "set": "ready"},
            "defects": "exclude",   # exclude | auto | include
            "start": {"kind": "field", "field": "created"},
            "aggregation": "coverage",
            # Team-speed denominator. auto = Average Velocity (story points)
            # per period ONLY when the project has sprints AND story points
            # (ready SP sum ÷ avg Velocity SP — consistent units); when the
            # project has story points but NO sprints the calculation falls
            # back to issue counts (ready issues ÷ avg Throughput issues per
            # period) to avoid mixing units; no story points -> issues.
            "denominator": "auto",   # auto | velocity_sp | throughput
            "targetMin": 2, "targetMax": 3,   # healthy band (sprints)
            "granularity": "sprint", "defaultN": 5,
            "trendDir": "down", "stablePct": 10,
            "label": "Backlog Health (sprints of ready work)",
        },
        "rework": {  # unique: "returned to set" flag after dev start
            "types": "req",
            "anchor": {"kind": "status", "set": "devStart"},
            "returnTo": {"kind": "status", "set": "refinement"},
            "aggregation": "rate",
            "granularity": "sprint", "defaultN": 5,
            "trendDir": "down", "stablePct": 10,
            "label": "Requirements Rework Rate (%)",
        },
        # [FIX-A1] Defect Density — two-level formula:
        #   per_sp:   Σ(story points of Bug+Sub-bug created in the period) ÷
        #             Σ(story points of Story+Task completed in the period)
        #   per_item: #defects ÷ #(Story+Task) — fallback when story points
        #             are absent or their fill-rate < 50% in the window.
        # densityMode=auto picks per_sp when the SP fill-rate ≥ 50%.
        "defectdensity": {
            # [P0-TYPES] The metric's OWN type list. Internally split:
            # bug-like types (Defect/Sub-bug) feed the numerator, work-like
            # ones (Story/Task/…) the denominator. Defaults reproduce the
            # pre-fix behaviour.
            "types": ["Story", "Task", "Defect", "Sub-bug"],
            "densityMode": "auto",   # auto | per_sp | per_item
            "rateMode": "spDensity",
            "aggregation": "rate",
            "granularity": "sprint", "defaultN": 5,
            "trendDir": "down", "stablePct": 10,
            "label": "Defect Density",
        },
        # [FIX-A2] Defect Containment / Production Leakage — escape-rate
        # semantics: prod-labelled bugs ÷ (bugs that entered a QA status
        # (set: qaSet) + prod-labelled bugs), each bug counted once,
        # bucketed by Created date.
        "leakage": {
            "types": ["Defect", "Sub-bug"],
            "rateMode": "roles",
            "qaSet": "qaSet",
            "start": {"kind": "field", "field": "created"},
            "prodLabel": "prod",
            "bucketBy": "created",   # created | resolutiondate
            "aggregation": "rate",
            "granularity": "sprint", "defaultN": 5,
            "trendDir": "down", "stablePct": 10,
            # [P3-1] Renamed: the metric shows leakage, not containment.
            "label": "Production Leakage Rate (%)",
        },
        # ---- Flow & grouped ----------------------------------------------
        "flow": {  # unique: two series
            "types": "flow",
            "series": {
                "opened": {"kind": "field", "field": "created"},
                "resolved": {"kind": "field", "field": "resolutiondate"},
            },
            "aggregation": "flow",
            "granularity": "sprint", "defaultN": 5,
            "trendDir": "up", "stablePct": 10,
            "label": "Opened vs Resolved",
        },
        "bugflow": {
            "types": "bug",
            "series": {
                "new": {"kind": "field", "field": "created"},
                "resolved": {"kind": "field", "field": "resolutiondate"},
            },
            "aggregation": "flow",
            "granularity": "sprint", "defaultN": 5,
            "trendDir": "up", "stablePct": 10,
            "label": "Bug Growth (new vs resolved)",
        },
        "incident": {  # unique: prod label + severity map
            # [P0-TYPES] Own type list — explicit Defect+Sub-bug (the "bug"
            # alias resolved to Defect only, silently dropping Sub-bug).
            "types": ["Defect", "Sub-bug"],
            "start": {"kind": "field", "field": "created"},
            "prodLabel": "prod",
            "groupBy": "severity",
            # [P2-3] Same unambiguous default as the widget-level map.
            "severityMap": {
                "Critical": ["blocker", "critical", "highest"],
                "Major": ["high", "major"],
                "Minor": ["medium", "normal", "low", "minor", "trivial"],
            },
            "aggregation": "grouped",
            "granularity": "sprint", "defaultN": 5,
            "trendDir": "down", "stablePct": 10,
            "label": "Incident Frequency",
        },
        # ---- P4 new metrics ------------------------------------------------
        # [P4-3] Defect Escape Rate (Review → QA): label-driven rate.
        # Empty labels = the N/A state (no fallback formula).
        "escapereview": {
            "types": "bug",
            "reviewLabel": "",   # label marking defects found in code review
            "qaLabel": "",       # label marking defects found in QA
            "start": {"kind": "field", "field": "created"},
            "bucketBy": "created",
            "aggregation": "rate", "rateMode": "labels",
            "granularity": "sprint", "defaultN": 5,
            "trendDir": "down", "stablePct": 10,
            "label": "Defect Escape Rate (Review → QA) (%)",
        },
        # [P4-4] Design Review Turnaround: status-driven avg-days metric.
        # Empty statuses = the N/A state; the type list must stay non-empty.
        "designreview": {
            "types": ["Story", "Task"],
            "designStart": "",   # status name (single)
            "reviewDone": "",    # status name (single)
            "aggregation": "avg", "value": "days",
            "granularity": "sprint", "defaultN": 5,
            "trendDir": "down", "stablePct": 10,
            "label": "Design Review Turnaround (avg days)",
        },
        # ---- P2 new metrics -------------------------------------------------
        # [P2v3-1] Clarification Cycle Count: returns to refinement BEFORE
        # the first dev-start (complementary to Rework Rate = AFTER start).
        "clarcycle": {
            "types": ["Story", "Task"],
            "start": {"kind": "field", "field": "created"},
            "end": {"kind": "status", "set": "devStart"},
            "returnTo": {"kind": "status", "set": "refinement"},
            "aggregation": "avg", "value": "count",
            "granularity": "sprint", "defaultN": 5,
            "trendDir": "down", "stablePct": 10,
            "label": "Clarification Cycle Count (avg cycles)",
        },
        # [P2v3-2] Review Cycle Count: re-review cycles per reviewed item
        # that reached done. Empty review set = the N/A state.
        "reviewcycle": {
            # [P5-TP] "work": PR review applies to every work type.
            "types": "work",
            "end": {"kind": "status", "set": "done"},
            "aggregation": "avg", "value": "count",
            "granularity": "sprint", "defaultN": 5,
            "trendDir": "down", "stablePct": 10,
            "label": "Review Cycle Count (avg re-reviews)",
        },
    },
}


def merge_settings(user):
    """Deep-merge a user settings dict (partial) over DEFAULT_SETTINGS.

    Lists replace, dicts merge recursively. Returns a new dict; the default
    is never mutated."""
    if not user:
        return copy.deepcopy(DEFAULT_SETTINGS)
    if "sprintData" in user and user["sprintData"] not in ("auto", "available", "none"):
        raise ValueError("sprintData must be auto, available or none")

    def _merge(base, over):
        out = dict(base)
        for k, v in (over or {}).items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                out[k] = _merge(base[k], v)
            else:
                out[k] = copy.deepcopy(v)
        return out

    return _merge(copy.deepcopy(DEFAULT_SETTINGS), user)


def load_settings(path):
    """Load a settings JSON file; raises SystemExit with a clear message on
    invalid JSON or wrong top-level type."""
    try:
        with open(path, encoding="utf-8") as fh:
            user = json.load(fh)
    except OSError as e:
        raise SystemExit(f"Cannot read metric settings file {path}: {e}")
    except json.JSONDecodeError as e:
        raise SystemExit(f"Metric settings file {path} is not valid JSON: {e}")
    if not isinstance(user, dict):
        raise SystemExit(f"Metric settings file {path} must contain a JSON object")
    try:
        return merge_settings(user)
    except ValueError as e:
        raise SystemExit(f"Invalid metric settings in {path}: {e}") from e


def validate_settings(s):
    """Light structural validation; returns a list of human-readable
    problems (empty list = OK)."""
    problems = []
    if s.get("sprintData", "auto") not in ("auto", "available", "none"):
        problems.append("sprintData must be auto, available or none")
    if not isinstance(s.get("statusSets"), dict) or not s["statusSets"]:
        problems.append("statusSets must be a non-empty object")
    for name, vals in (s.get("statusSets") or {}).items():
        if not isinstance(vals, list) or not all(isinstance(v, str) for v in vals):
            problems.append(f"statusSets.{name} must be a list of strings")
    if not isinstance(s.get("metrics"), dict) or not s["metrics"]:
        problems.append("metrics must be a non-empty object")
    for mk, cfg in (s.get("metrics") or {}).items():
        if not isinstance(cfg, dict):
            problems.append(f"metrics.{mk} must be an object")
            continue
        if "aggregation" in cfg and cfg["aggregation"] not in (
                "avg", "count", "rate", "flow", "grouped", "coverage",
                "wipSnapshot", "allocation"):   # [FIX-A4] [FIX-A5]
            problems.append(f"metrics.{mk}.aggregation '{cfg['aggregation']}' "
                            "is not one of avg|count|rate|flow|grouped|coverage|"
                            "wipSnapshot|allocation")
        if "trendDir" in cfg and cfg["trendDir"] not in ("up", "down"):
            problems.append(f"metrics.{mk}.trendDir must be 'up' or 'down'")
        for anchor in ("start", "end"):
            a = cfg.get(anchor)
            if isinstance(a, dict) and a.get("kind") not in ("field", "status", None):
                problems.append(f"metrics.{mk}.{anchor}.kind must be 'field' or 'status'")
    tc = s.get("teamConfig") or {}
    if not isinstance(tc, dict):
        problems.append("teamConfig must be an object")
    else:
        if tc.get("source", "none") not in ("none", "field", "labels"):
            problems.append("teamConfig.source must be one of none|field|labels")
        if tc.get("source") == "field" and not (tc.get("fieldName") or "").strip():
            problems.append("teamConfig.fieldName is required when source='field'")
        if tc.get("source") == "labels" and not (tc.get("labels") or []):
            problems.append("teamConfig.labels must be a non-empty list "
                            "when source='labels'")
        if not isinstance(tc.get("labels") or [], list):
            problems.append("teamConfig.labels must be a list of strings")
    return problems
