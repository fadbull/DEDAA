"""Process Metrics - Trends: data block (PM_DATA, RC_RAW, RC_SETTINGS).

F3-B: the 16 per-metric arrays are intentionally EMPTY here. The legacy
Python-side items (metadata-date based, unfiltered by metric type) were dead
weight: the widget's boot chain (rcBoot -> rcRebuildData -> rcDeriveAll)
overwrites PM_DATA from RC_RAW + RC_SETTINGS before anything renders. The
settings-driven JS derivation is the single source of truth; embedding the
legacy snapshot only bloated the HTML (~1.6 MB) and misled parity tests.
"""


def build_trends_data(jm, _json):
    return ("""  clarcycle: [],
  reviewcycle: [],
  cycle: [],
  cycletime: [],
  rework: [],
  lead: [],
  flow: [],
  throughput: [],
  velocity: [],
  backlog: [],
  bugflow: [],
  leakage: [],
  bugfix: [],
  incident: [],
  qa: [],
  defectdensity: [],
  wip: [],
  floweff: [],
  escapereview: [],
  designreview: [],
  clarcycle: [],
  reviewcycle: []
};
// Issue directory for the widget's issues table (key -> display fields).
var RC_ISSUE_DIR = """ + _json.dumps(jm.get("pm_issue_dir") or {}) + """;
// Raw per-issue records for settings-driven metric derivation: the gear
// panel re-derives every metric from these events using RC_SETTINGS.
var RC_RAW = """ + _json.dumps(jm.get("pm_raw_items") or []) + """;
var RC_SPRINT_CATALOG = """ + _json.dumps(jm.get("pm_sprint_catalog") or []) + """;
var RC_SPRINT_COVERAGE = """ + _json.dumps(jm.get("pm_sprint_coverage") or {"total": 0, "populated": 0}) + """;
// Discovered Team fields in the project (native Team field / custom fields
// rendered as "Team: value" lines) — offered as Team sources in the widget
// settings. Empty list = no Team field is populated in this project.
var TEAM_FIELDS = """ + _json.dumps(jm.get("team_fields") or []) + """;
// Does the project have sprints (sprint metadata present in the Jira data)?
// Backlog Health uses it in denominator=auto: Average Velocity (story
// points) is only a valid team-speed unit when sprints exist; without
// sprints the coverage falls back to issue counts (no mixed units).
var RC_HAS_SPRINTS = RC_SPRINT_COVERAGE.total > 0 &&
  RC_SPRINT_COVERAGE.populated / RC_SPRINT_COVERAGE.total > 0.5;
// [P3-2] Explicit role name: this flag is the AUTO-DETECT input for the
// Widget settings «Sprint data availability» (sprintData: auto resolves
// from it; available/none override it).
var RC_HAS_SPRINTS_DATA = RC_HAS_SPRINTS;
// Effective metric settings (defaults; the gear panel may override them in
// the browser and persist to localStorage).
var RC_SETTINGS = """ + _json.dumps(jm.get("pm_settings") or {}) + """;""")
