"""Metric display config: RC_CFG, RC_TIP, tooltips, issue types."""

CONFIG_JS = """
var rcChart = null;
var rcMetric = 'cycle';
var RC_CFG = {
  cycle: {label:'Requirements Cycle Time (avg days)', color:'#2563eb', aggregation:'avg',
    field:'days', y_axis:'Requirements Cycle Time (days)', threshold:0.05, y_min:null, y_max:null,
    types:['Story','Task'],
    axis_note:'Y-axis: Requirements Cycle Time (days) · X-axis: period (sprint / 2-week bucket). Default shows the last 5 periods with project activity.', trend_dir:'down'},
  rework: {label:'Requirements Rework Rate (%)', color:'#7c3aed', aggregation:'rate',
    field:'reworked', y_axis:'Requirements Rework Rate (%)', threshold:0.1, y_min:0, y_max:100,
    types:['Story','Task'],
    axis_note:'Y-axis: Requirements Rework Rate (%) · X-axis: period (sprint / 2-week bucket). Default shows the last 5 periods with project activity.', trend_dir:'down'},
  // [FIX-A3] Lead Time: any Issue Type via the top filter (Defect+Sub-bug =
  // Bug Lead Time; Story+Task = Story/Task Lead Time).
  // [P1-STATES] Renamed to 'Issue Lead Time' — the number is the Jira issue
  // lifecycle (Created → Done), NOT the DORA Lead Time for Changes.
  lead: {label:'Issue Lead Time (avg days)', color:'#0ea5e9', aggregation:'avg',
    field:'days', y_axis:'Issue Lead Time (days)', threshold:0.05, y_min:null, y_max:null,
    types:['Story','Task','Defect','Sub-bug'],
    axis_note:'Y-axis: Lead Time (days) · X-axis: period (sprint / 2-week bucket). Default shows the last 5 periods with project activity.', trend_dir:'down'},
  flow: {label:'Opened vs Resolved', color:'#2563eb', aggregation:'flow',
    field:'series', y_axis:'Issues', threshold:0.1, y_min:0, y_max:null,
    types:['Story','Task'],
    axis_note:'Y-axis: Issues opened/resolved · X-axis: period (sprint / 2-week bucket). Default shows the last 5 periods with project activity.'},
  throughput: {label:'Throughput (completed)', color:'#10b981', aggregation:'count',
    field:null, y_axis:'Completed issues', threshold:0.1, y_min:0, y_max:null,
    types:['Story','Task','Defect'], trend_dir:'up',
    axis_note:'Y-axis: Completed issues · X-axis: period (sprint / 2-week bucket). Default shows the last 5 periods with project activity.'},
  // [P1-STATES] Explicit unit naming: issue counts by default, SP state
  // available via the metric settings (velocityMode).
  velocity: {label:'Issue Velocity (completed items per period)', color:'#8b5cf6', aggregation:'count',
    field:null, y_axis:'Completed items per period (issue count)', threshold:0.1, y_min:0, y_max:null,
    types:['Story','Task','Defect'], trend_dir:'up',
    // [P9-P2-1] The UI type label is Defect (rcTypeLabel normalises Bug).
    axis_note:'Y-axis: Completed Story/Task/Defect · X-axis: period (sprint / 2-week bucket). Default shows the last 5 periods with project activity.'},
  // [P5-TP] Cycle Time: derivation gates on THIS metric's type list, which
  // defaults to "work" = [Story, Task, Defect, Sub-bug]. The top Issue Type
  // filter can narrow to Defect+Sub-bug (Bug Cycle Time) or Story+Task
  // (Story/Task Cycle Time) without touching metric settings.
  cycletime: {label:'Cycle Time (avg days)', color:'#f59e0b', aggregation:'avg',
    field:'days', y_axis:'Cycle Time (days)', threshold:0.05, y_min:null, y_max:null,
    types:['Story','Task','Defect','Sub-bug'],
    axis_note:'Y-axis: Cycle Time (days) · X-axis: period (sprint / 2-week bucket). Default shows the last 5 periods with project activity.', trend_dir:'down'},
  // [P11-A] Backlog Health: band metric — the trend verdict is the
  // under/over-stocked band judgement, not a directional slope.
  backlog: {label:'Backlog Health (sprints of ready work)', color:'#14b8a6', aggregation:'coverage',
    field:null, y_axis:'Sprints of ready backlog', threshold:0.1, y_min:0, y_max:null,
    types:['Story','Task'], trend_dir:'down',
    axis_note:'Y-axis: sprints of ready backlog (ready items ÷ avg team speed per period) · X-axis: period (sprint / 2-week bucket). Healthy band: 2–3 sprints of coverage. Default shows the last 5 periods with project activity.'},
  // [P4-4] Design Review Turnaround: avg days design-start → review-done.
  // N/A until two DIFFERENT statuses are configured (P1 N/A-state pattern).
  designreview: {label:'Design Review Turnaround (avg days)', color:'#0d9488', aggregation:'avg',
    field:'days', y_axis:'Design review turnaround (days)', threshold:0.05, y_min:null, y_max:null,
    types:['Story','Task'], avg_unit:' days',
    axis_note:'Y-axis: Design review turnaround (days) · X-axis: period (sprint / 2-week bucket). Works on the design start and review done statuses selected in the metric settings. Items with zero-day interval are excluded from the average. Default shows the last 5 periods with project activity.', trend_dir:'down'},
  // [P0v3-F4] The type list matches the runtime 'bug' alias (Defect+Sub-bug).
  // [P11-A] Bug Growth: the flow verdict reads the resolved-minus-opened
  // BALANCE slope (balance up = defect backlog shrinking = Improving).
  bugflow: {label:'Bug Growth (new vs resolved)', color:'#ef4444', aggregation:'flow',
    field:'series', y_axis:'Bugs', threshold:0.1, y_min:0, y_max:null,
    types:['Defect','Sub-bug'],
    axis_note:'Y-axis: Bugs new/resolved · X-axis: period (sprint / 2-week bucket). Default shows the last 5 periods with project activity.', trend_dir:'up'},
  // [FIX-A2] Leakage: escape-rate semantics (roles rate mode, qaSet denominator).
  // [P3-1] Renamed to «Production Leakage Rate» — containment is only a
  // one-line note in the tooltip (the metric shows leakage, not containment).
  leakage: {label:'Production Leakage Rate (%)', color:'#ec4899', aggregation:'rate',
    rateMode:'roles', field:null, y_axis:'Production leakage rate (%)', threshold:0.1, y_min:0, y_max:100,
    types:['Defect','Sub-bug'],
    axis_note:'Y-axis: % of tested-or-prod bugs leaked to production · X-axis: period (sprint / 2-week bucket). The metric works on the production label from Widget settings. Default shows the last 5 periods with project activity.', trend_dir:'down'},
  // [FIX-A5] Bug Fixing Time Allocation: worklog-based % (N/A without timeSpent).
  bugfix: {label:'Bug Fixing Time Allocation', color:'#f97316', aggregation:'allocation',
    requires:'timeSpent', field:null, y_axis:'Allocation (%)', threshold:0.05, y_min:0, y_max:100,
    types:['Defect','Sub-bug'],
    axis_note:'Y-axis: % of logged work time spent on Bug/Sub-bug · X-axis: period (sprint / 2-week bucket). Requires Jira worklog. Healthy: < 20%. Default shows the last 5 periods with project activity.', trend_dir:'down'},
  incident: {label:'Incident Frequency', color:'#f43f5e', aggregation:'grouped',
    field:'severity', y_axis:'Prod bugs', threshold:0.1, y_min:0, y_max:null,
    groups:['Critical','Major','Minor'], colors:{Critical:'#dc2626',Major:'#f59e0b',Minor:'#10b981'},
    trend_dir:'down',
    // [P0-TYPES] Consistent bug-pool default (Defect+Sub-bug) — same pool
    // as Defect Density / Bug Fixing; the user can narrow it via checkboxes.
    types:['Defect','Sub-bug'],
    axis_note:'Y-axis: Production bugs (incidents) · X-axis: period (sprint / 2-week bucket). Stacked by severity (Critical/Major/Minor). Default shows the last 5 periods with project activity.'},
  qa: {label:'Time in QA (avg days)', color:'#06b6d4', aggregation:'avg',
    field:'days', y_axis:'Time in QA (days)', threshold:0.05, y_min:null, y_max:null,
    // [P5-TP] "work": defects pass QA too — the top filter can narrow.
    types:['Story','Task','Defect','Sub-bug'],
    // [P0v3-F2] The end anchor is the QA-exit set (QA passed), not Done.
    axis_note:'Y-axis: Time in QA (days) · X-axis: period (sprint / 2-week bucket). Time from entering QA (Ready for QA / In Testing) to the first QA-passed status (Ready for DEMO / Resolved / Closed by default — editable in widget settings). Default shows the last 5 periods with project activity.', trend_dir:'down'},
  // [FIX-A1] Defect Density: per_sp / per_item two-level formula.
  // [P7-DD] The numerator is the COUNT of defects (per SP or per item).
  defectdensity: {label:'Defect Density', color:'#8b5cf6', aggregation:'rate',
    rateMode:'spDensity', field:null, y_axis:'Defects per SP (or per item without SP)', threshold:0.1, y_min:0, y_max:null,
    types:['Story','Task','Defect','Sub-bug'], trend_dir:'down',
    axis_note:'Y-axis: #defects found in QA ÷ SP of completed Story/Task (or #defects ÷ #(Story+Task) when story points are not available) per period · X-axis: period (sprint / 2-week bucket). High density signals messy logic / rushed coding / high cyclomatic complexity. Default shows the last 5 periods with project activity.'},
  // [FIX-A4] WIP: point-in-time snapshot at each bucket end (NOT inflow).
  wip: {label:'Work in Progress (WIP)', color:'#f59e0b', aggregation:'wipSnapshot',
    field:null, y_axis:'WIP items (snapshot)', threshold:0.1, y_min:0, y_max:null,
    types:['Story','Task','Defect','Sub-bug'],
    // [P1-STATES] Explicit snapshot-granularity note.
    // [P11-B] The chart shows the TEAM TOTAL; the per-developer target needs
    // the team size (state it explicitly — the Person dimension may be off).
    axis_note:'Y-axis: WIP items (snapshot, team total) · X-axis: period (sprint / 2-week bucket). Snapshot at the end of each period; for the customary daily WIP snapshot set Periods = Daily. High WIP → high context switching → slower flow. Target: ≤ 1.5 WIP items per developer — the chart shows the team total, divide it by the team size for the per-developer view. Default shows the last 5 periods with project activity.', trend_dir:'down'},
  floweff: {label:'Flow Efficiency (%)', color:'#10b981', aggregation:'avg',
    field:'eff', y_axis:'Flow Efficiency (%)', threshold:0.5, y_min:0, y_max:100,
    // [P5-TP] "work": active/total applies to every work type.
    types:['Story','Task','Defect','Sub-bug'], trend_dir:'up', avg_unit:'%',
    axis_note:'Y-axis: Active work time ÷ total elapsed × 100% · X-axis: period (sprint / 2-week bucket). Active = In Progress → Done; total = Created → Done. Default shows the last 5 periods with project activity.'},
  // [P4-3] Defect Escape Rate (Review → QA): label-driven rate metric
  // (two configurable labels; N/A until two DIFFERENT labels are set).
  escapereview: {label:'Defect Escape Rate (Review → QA) (%)', color:'#e11d48', aggregation:'rate',
    rateMode:'roles', field:null, y_axis:'Defect escape rate (review → QA) (%)', threshold:0.1, y_min:0, y_max:100,
    types:['Defect','Sub-bug'],
    axis_note:'Y-axis: % of review-found defects that escaped review into QA · X-axis: period (sprint / 2-week bucket). Works on the review/QA labels selected in the metric settings. Default shows the last 5 periods with project activity.', trend_dir:'down'},
  // [P2v3-1] Clarification Cycle Count: returns to refinement BEFORE dev start.
  clarcycle: {label:'Clarification Cycle Count (avg cycles)', color:'#8b5cf6', aggregation:'avg',
    field:'cycles', y_axis:'Clarification cycles (count)', threshold:0.1, y_min:null, y_max:null,
    types:['Story','Task'], avg_unit:' cycles',
    axis_note:'Y-axis: Clarification cycles (count) · X-axis: period (sprint / 2-week bucket). Counts returns to refinement BEFORE development starts; Requirements Rework Rate counts returns AFTER dev start. Default shows the last 5 periods with project activity.', trend_dir:'down'},
  // [P2v3-2] Review Cycle Count: re-review cycles per reviewed item reaching done.
  reviewcycle: {label:'Review Cycle Count (avg re-reviews)', color:'#14b8a6', aggregation:'avg',
    field:'count', y_axis:'Re-review cycles (count)', threshold:0.1, y_min:null, y_max:null,
    // [P5-TP] "work": PR review applies to every work type.
    types:['Story','Task','Defect','Sub-bug'], avg_unit:' re-reviews', trend_dir:'down',
    axis_note:'Y-axis: Re-review cycles (count) · X-axis: period (sprint / 2-week bucket). Works on the review statuses configured in widget settings. Default shows the last 5 periods with project activity.'}
};
var RC_TIP = {
  // [P2-2] Zero-day rule noted in every time-metric tooltip.
  // [P12-P6] Neutral status wording: the concrete statuses come from the
  // configured statusSets (the dynamic Formula: section shows them).
  cycle: "Requirements Cycle Time = avg(first dev-start status − Created) for Story/Task. Measures how long a requirement waits to enter development (queue/refinement time). Items with zero-day interval are excluded from the average. HEALTHY < 14 days (1 sprint). The blue box (top-right) shows the weighted average over the selected window: total days ÷ number of items, respecting all filters.",
  rework: "Requirements Rework Rate = % of started Story/Task that return to requirements/refinement AFTER dev started. Formula: (returned to refinement after dev start) ÷ (total started) × 100. HEALTHY < 10%; >20% = requirements-quality problem. DIFFERENCE vs Scope Change: Scope Change counts ANY status change; Rework counts ONLY returns to refinement after dev start. The box shows the weighted average = total reworked ÷ total started over the window.",
  // [FIX-A3] Lead Time: any Issue Type, no DORA references.
  // [P1-STATES] 'Issue Lead Time': the Jira issue lifecycle, NOT the DORA
  // Lead Time for Changes (no commit/production wording).
  // [P2v3-1/2] The new count metrics build their tooltips dynamically
  // (rcTipFor) — no static entries needed here.
  // [P1v3-4] No external metric family: the comparison sentence is removed.
  lead: "Issue Lead Time = average time from creation to the first done-style status (the set is editable in widget settings; Resolved is used when no done transition exists — the resolutiondate fallback) for any selected Issue Type. Items with zero-day interval are excluded (including the resolutiondate fallback). Includes queue and backlog wait. HEALTHY < 30 days. The box shows the weighted average over the window: total days ÷ number of items.",
  // [P9-P2-1] The UI type label is Defect (rcTypeLabel normalises Bug).
  velocity: "Issue Velocity = number of completed Story/Task/Defect issues per period. Measures team throughput in issue counts, not story points. Higher is better: a rising trend is Improving, a falling trend is Degrading. The box shows the average completed per period over the window.",
  // [P12-P1] Granularity-neutral wording: the period follows the Periods
  // selector (daily … annual), not a hardcoded 2-week bucket.
  flow: "Opened vs Resolved per selected period for requirements work (Story/Task by default — broaden via the Issue Type filter). If Opened persistently > Resolved the backlog grows (demand > capacity); the reverse means the team is burning down outstanding work. The box shows the average per period for each series (Avg Opened / Avg Resolved) over the window.",
  throughput: "Throughput = number of issues completed per selected period (Story/Task/Defect by default — broaden via the Issue Type filter). A raw capacity measure; Velocity is a filtered, more refined version. Higher is better: a rising trend is Improving, a falling trend is Degrading. The box shows the average completed per period over the window.",
  // [FIX-A6] Cycle Time works for any Issue Type via the top filter.
  cycletime: "Cycle Time = avg(first done-style status − first dev-start status) for any selected Issue Type — pick Defect + Sub-bug to see Bug Cycle Time; pick Story + Task to see Story/Task Cycle Time. Measures only the active execution phase (excludes queue/backlog wait). Items with zero-day interval are excluded from the average. HEALTHY < 14 days. The box shows the weighted average over the window: total days ÷ number of items.",
  backlog: "Backlog Health = HOW MANY SPRINTS of ready work the backlog holds. Formula: ready items (Story+Task in 'Ready for development'; Defects excluded by default) at each period end ÷ team speed per period. Team speed = Average Velocity in story points per period ONLY when the project has sprints AND story points (numerator = story-point SUM of the ready items, SP ÷ SP); with story points but NO sprints the calculation uses issue counts (ready issues ÷ Average Throughput per period) to avoid mixing units; no story points — issues as well. The sprint availability behind the auto rule is set in Widget settings → Sprint data availability. Optimal range: 2–3 sprints of coverage — below 2 the team risks starving for startable work, above 3 the grooming effort is wasted. The box shows the AVG of the per-period values (control points): sum of Backlog Health at each period end ÷ number of control points in the window.",
  // [P2-1] State the default type set explicitly + the narrowing hint.
  bugflow: "Bug Growth = new vs resolved Defects and Sub-bugs per selected period (both defect types are included by default; narrow the set via the Issue Type checkboxes). When new bugs outpace resolved the defect backlog grows and quality deteriorates. The box shows the average per period for each series (Avg New / Avg Resolved) over the window.",
  // [P0v3-F1] The tooltip describes the REAL formula: prod-labelled defects
  // [P3-LK] The denominator = QA-entered ∪ prod-labelled defects; the
  // opening follows the Defect Escape Rate template ('share of defects
  // that passed QA … and were found in production').
  leakage: "Production Leakage Rate = the share of defects that passed QA (or were production-labelled) and were found in production. Computed as production-labelled defects ÷ (defects with a QA transition + production-labelled defects) × 100%, bucketed by creation date. Defects found before QA (code review, development, etc.) are excluded from both the numerator and the denominator. Lower is better — healthy is below 15%; high leakage means testing fails to contain defects. The complementary value (100% − leakage) is defect containment, not shown separately. The box shows the weighted average = total leaked ÷ total (QA-entered + prod) over the window.",
  // [P4-4] Design Review Turnaround: status-driven time metric.
  designreview: "Design Review Turnaround = avg(review done − design start) — how long the review of a design document / architectural solution takes. Target ≤ 2 business days for standard decisions. Both transitions must exist in the issue history and review-done must be later; items with zero-day interval are excluded from the average. Configure the two statuses in the metric settings; without them (or with an empty window) the metric shows N/A. The box shows the weighted average over the window: total days ÷ number of items.",
  // [P1v3-5] The tooltip body is built DYNAMICALLY (rcTipFor) — the static
  // fallback below is kept only for surfaces that cannot call functions.
  bugfix: "Bug Fixing Time Allocation = percentage of logged work time attributed to the numerator types relative to all completed work, per period. Requires Jira worklog. Healthy: < 20%. Not available when the project does not log work time (timespent fill-rate < 20%).",
  incident: "Incident Frequency = number of production Defects (tagged 'Prod') per selected period, stacked by severity (Critical/Major/Minor derived from priority). A rising frequency — especially Critical — indicates production stability is degrading. The box shows the average total incidents per period over the window.",
  // [P0v3-F2] The end anchor is the QA-exit set (QA passed) — not Done.
  qa: "Time in QA = average time from first QA-entry status to the first QA-exit status (e.g. Ready for DEMO / Resolved / Closed by default — editable in widget settings) for Story/Task with a QA transition. Measures how long work sits in the testing phase; statuses after the QA exit do not count. Items with zero-day interval are excluded from the average. HEALTHY < 1 sprint (<14 days). The box shows the weighted average over the window: total days ÷ number of items.",
  // [FIX-A1] Defect Density: mode-dependent base tooltip (the active variant
  // is picked in rcTipFor based on densityMode / SP fill-rate).
  // [P6-B5] The numerator counts QA-found defects only — prod-labelled ones
  // belong to Production Leakage (the two populations must not overlap).
  // [P7-DD] The numerator is the COUNT of defects in both modes.
  defectdensity: "Defect Density (per story point) = Number of defects found in QA ÷ Story points of completed Story/Task per period. Defects carrying the production label are excluded here — they are counted in Production Leakage instead. High density = messy logic / rushed coding / high cyclomatic complexity. Lower is better.",
  defectdensity_per_item: "Defect Density (per item) = Defects found in QA ÷ (Story + Task) per period. This is a count-based fallback used when story points are not available in the project (or the SP fill-rate is below 50%). The denominator uses issue counts. Defects carrying the production label are excluded here — they are counted in Production Leakage instead. Lower is better.",
  // [FIX-A4] WIP: point-in-time snapshot (no 'inflow' wording).
  wip: "WIP = number of items in a dev status at each period end (point-in-time snapshot). Target ≤ 1.5 WIP items per developer — the chart shows the team total, divide it by the team size for the per-developer view. High WIP → high context switching → slower flow. Lower is better. The box shows the average snapshot WIP per period over the window. Granularity of the snapshot follows the Periods selector; a daily snapshot requires Periods = Daily.",
  bugfix_na: "Not available — the project does not log work time (timespent fill-rate < 20%).",
  floweff: "Flow Efficiency = Active work time ÷ Total elapsed time × 100%. Active = In Progress → Done; Total = Created → Done. Items with a zero-day total interval are excluded from the average. Measures what fraction of lead time is actual work vs waiting. Higher is better (e.g. >50% is good, <25% is poor). The box shows the weighted average over the window: total active ÷ total elapsed.",
  // [P4-3] Defect Escape Rate (Review → QA): label-driven rate metric.
  escapereview: "Defect Escape Rate (Review → QA) = % of defects that passed code review but were found in QA — a high value means weak review. Formula: defects labeled [found in QA] ÷ (defects labeled [found in review] + defects labeled [found in QA]) × 100%, bucketed by Created date. Both labels are configured in the metric settings (offered from the project's bug labels); the default type set is Defect + Sub-bug. Without the configured labels (or with an empty window) the metric shows N/A. The box shows the weighted average = total escaped ÷ total (review + QA) over the window."
};
// [P1-5] Healthy reference lines (NOT roadmap targets — static guidance
// levels). Rendered as dashed horizontal lines on the single-series charts.
// Style [2,3]/1.5 is deliberately distinct from the trend line ([6,4]/2).
// Metrics whose healthy range is context-dependent (throughput, velocity,
// flow, bugflow, incident, defectdensity) intentionally have NO lines.
var RC_REF_LINES = {
  cycle:     [{label:'< 14d', level:14, color:'#10b981'}],
  cycletime: [{label:'< 14d', level:14, color:'#10b981'}],
  // [P9-P1-1] Issue Lead Time: the tooltip already promises HEALTHY < 30
  // days — the dashed line makes that threshold visible on the chart.
  lead:      [{label:'< 30d', level:30, color:'#10b981'}],
  qa:        [{label:'< 14d', level:14, color:'#10b981'}],
  rework:    [{label:'Healthy < 10%', level:10, color:'#10b981', trend_dir:'down'},
              {label:'Problem > 20%', level:20, color:'#ef4444'}],
  floweff:   [{label:'Poor < 25%', level:25, color:'#ef4444'},
              {label:'Good > 50%', level:50, color:'#10b981'}],
  leakage:   [{label:'< 15%', level:15, color:'#10b981'}],
  bugfix:    [{label:'< 20%', level:20, color:'#10b981'}],
  // [P1-I11] Design Review Turnaround: the 2-day target for standard
  // decisions (same green dashed style as the Cycle Time line).
  designreview: [{label:'≤ 2d', level:2, color:'#10b981'}],
  // [P4v3-RL] The two count metrics: healthy ≤ 2 cycles per item (same
  // green dashed style as the Design Review Turnaround line).
  clarcycle:  [{label:'≤ 2', level:2, color:'#10b981'}],
  reviewcycle:[{label:'≤ 2', level:2, color:'#10b981'}]
};
// Issue Types offered in the multi-select filter: the canonical five first,
// then every other type actually present in the data (so no item type is
// impossible to select — e.g. Test / Security issue / Epic / Improvement).
// then every other type actually present in the data (so no item type is
// impossible to select — e.g. Test / Security issue / Epic / Improvement).
var ISSUE_TYPES = (function(){
  var out=['Story','Task','Defect','Sub-bug','Sub-task'], seen={};
  out.forEach(function(t){ seen[t]=1; });
  Object.keys(PM_DATA).forEach(function(mk){
    (PM_DATA[mk]||[]).forEach(function(it){
      var lbl=rcTypeLabel(it.type);
      if(lbl && !seen[lbl]){ seen[lbl]=1; out.push(lbl); }
    });
  });
  return out;
})();
// [P1-I9] Per-metric Issue Type selection memory (SESSION scope — a page
// reload resets every metric to its config defaults; no localStorage).
// The metric-settings types list seeds the FIRST visit; the top-panel
// checkboxes hold the user's in-session choice per metric.
var rcTypeSelMem={};
// [P0v3-F3] The checkbox seed for a metric = the RUNTIME metric settings
// (RC_SETTINGS.metrics[mk].types, aliases resolved) — the single source of
// truth — NOT the static display config. An empty runtime list renders
// EMPTY checkboxes (the chart shows N/A, not zero bars).
// [P5-TP] SINGLE SOURCE for the metric's type pool: the runtime metric
// settings (aliases resolved, RC_CFG as the display fallback). Consumers:
// rcDeriveAll (via mtypes), rcDefaultWindow, rcPopulateTypes, the settings
// panel. Returns [] when the metric's type list is empty (metric disabled).
function rcTypesFor(mk){
  var S=rcDraft||RC_SETTINGS;
  var m=((S.metrics||{})[mk])||{};
  var ref=m.types;
  if(ref===undefined||ref===null) ref=(RC_CFG[mk]||{}).types;
  if(typeof ref==='string') ref=(S.types||{})[ref]||[];
  if(!Array.isArray(ref)) return [];
  return ref.slice();
}
// Backwards-compat alias.
function rcTypeDefaults(mk){ return rcTypesFor(mk); }
function rcPopulateTypes(){
  var wrap=document.getElementById('rcTypeWrap');
  if(!wrap) return;
  wrap.innerHTML='';
  // [P5-TP] The pool = rcTypesFor(metric) — the top filter renders ONLY the
  // derivation pool. A type outside the pool must not be clickable: the
  // view filter can narrow but never widen (clicking an out-of-pool type
  // produced an empty chart — Cycle Time + Defect).
  var pool=rcTypesFor(rcMetric);
  var defaults=rcTypeSelMem[rcMetric];
  if(!defaults){
    defaults=pool.slice();
    rcTypeSelMem[rcMetric]=defaults.slice();
  }
  // Stale session memory: drop types that left the pool.
  defaults=defaults.filter(function(t){ return pool.indexOf(t)>=0; });
  pool.forEach(function(t){
    var lb=document.createElement('label');
    lb.className='inline-flex items-center gap-1 text-xs border rounded px-2 py-1 cursor-pointer';
    var cb=document.createElement('input');
    cb.type='checkbox'; cb.value=t; cb.className='rcTypeCb';
    cb.onchange=function(){ rcTypeMemChanged(); rcMarkPending(); };
    cb.checked = defaults.indexOf(t) >= 0;
    lb.appendChild(cb); lb.appendChild(document.createTextNode(t));
    wrap.appendChild(lb);
  });
  // The pool is narrower than the canonical list → point at the settings.
  if(pool.length < ISSUE_TYPES.length){
    var hint=document.createElement('span');
    hint.className='text-xs text-gray-400 italic';
    hint.textContent='(add more types in metric settings → Issue types)';
    wrap.appendChild(hint);
  }
}
// [P1-I9] Store the user's checkbox choice for the CURRENT metric.
function rcTypeMemChanged(){
  var cbs=document.querySelectorAll('#rcTypeWrap .rcTypeCb:checked');
  var out=[];
  Array.prototype.forEach.call(cbs,function(cb){ out.push(cb.value); });
  rcTypeSelMem[rcMetric]=out;
}
// [P1-I9] Apply commits new metric-settings types → drop the session
// memory for this metric so the new default takes effect.
function rcTypeMemReset(mk){
  if(mk===undefined){ rcTypeSelMem={}; return; }
  delete rcTypeSelMem[mk];
}
function rcTypeSelected(){
  var cbs=document.querySelectorAll('#rcTypeWrap .rcTypeCb:checked');
  var set={};
  Array.prototype.forEach.call(cbs,function(cb){ set[cb.value]=1; });
  return set;
}
function rcTipHtml(text){
  return '<span class="tip-wrap" data-align="left">'+
    '<span class="tip-icon" title="">ⓘ</span>'+
    '<span class="tip-box">'+text+'</span></span>';
}
// How the top-right box value is computed (per metric; static semantics).
var RC_TIP_BOX = {
  cycle: 'Box (top-right): weighted average over the window = total days ÷ number of items, respecting all filters.',
  cycletime: 'Box (top-right): weighted average over the window = total days ÷ number of items.',
  lead: 'Box (top-right): weighted average over the window = total days ÷ number of items.',
  qa: 'Box (top-right): weighted average over the window = total days ÷ number of items.',
  bugfix: 'Box (top-right): weighted allocation % over the window = Σ bug timespent ÷ Σ all timespent.',   // [FIX-A5]
  floweff: 'Box (top-right): weighted average = total active days ÷ total elapsed days over the window.',
  wip: 'Box (top-right): average snapshot WIP per period over the window.',   // [FIX-A4]
  throughput: 'Box (top-right): average completed per period over the window.',
  velocity: 'Box (top-right): average completed per period over the window.',
  // [P1v3-1e] The box averages COMPUTABLE control points only.
  backlog: 'Box (top-right): arithmetic mean over the COMPUTABLE control points of the window (ready backlog > 0 AND team speed > 0) = typical sprints of ready backlog; zero bars do not enter the average; the label states the number of computable points.',
  rework: 'Box (top-right): weighted average = total reworked ÷ total started over the window.',
  // [P12-P5] defectdensity is resolved DYNAMICALLY (rcTipBoxFor) — the Box
  // section must describe the ACTIVE density mode, not both at once.
  defectdensity: '',
  leakage: 'Box (top-right): weighted average = total leaked ÷ total (QA-entered + prod) over the window.',   // [FIX-A2]
  incident: 'Box (top-right): average total incidents per period over the window.',
  flow: 'Box (top-right): average per period for each series (Avg Opened / Avg Resolved) over the window.',
  bugflow: 'Box (top-right): average per period for each series (Avg New / Avg Resolved) over the window.',
  // [P4-3]/[P4-4]
  escapereview: 'Box (top-right): weighted average = total escaped (QA label) ÷ total (review + QA labels) over the window.',
  designreview: 'Box (top-right): weighted average over the window = total days ÷ number of items with both transitions.',
  // [P2v3-1/2]
  clarcycle: 'Box (top-right): arithmetic mean over the requirements that entered development in the window = expected clarification rounds per requirement; items that started without any clarification rounds contribute zero.',
  reviewcycle: 'Box (top-right): arithmetic mean over the reviewed items that reached done in the window = average re-review cycles per reviewed item; items approved on the first review participate as zero.'
};
// [P12-P5] The Box section resolver: defectdensity describes the ACTIVE
// density mode (per_sp vs the count-based fallback); every other metric
// falls through to the static RC_TIP_BOX text.
function rcTipBoxFor(mk){
  if(mk==='defectdensity'){
    return rcDensityMode()==='per_sp'
      ? 'Box (top-right): weighted ratio over the window = Σ #defects found in QA ÷ Σ story points of completed Story/Task.'
      : 'Box (top-right): weighted ratio over the window = Σ #defects found in QA ÷ Σ completed Story/Task (count-based — no SP in data).';
  }
  return RC_TIP_BOX[mk] || '';
}
// Inclusion conditions ("Counted: …") generated from the current settings.
function rcTipCounted(mk){
  var S=RC_SETTINGS, m=(S.metrics||{})[mk]||{};
  function types(ref){
    if(ref===undefined) ref=m.types;
    if(typeof ref==='string') ref=(S.types||{})[ref]||[];
    return (ref||[]).join(', ')||'—';
  }
  var prod=rcProdLabelEff(String(m.prodLabel||S.prodLabel||'prod'), S);
  if(mk==='defectdensity'){
    // [FIX-A1] Counted text follows the effective density mode.
    // [P6-B5] The prod-label exclusion is named explicitly.
    // [P7-DD] The numerator is the COUNT of defects found in QA in both
    // modes — only the denominator switches (SP ÷ count).
    var mode=rcDensityMode();
    return (mode==='per_sp'
      ? 'Counted: per period — #defects found in QA (Bug/Sub-bug, by Created) ÷ Σ(story points of completed Story/Task, by Done)'
      : 'Counted: per period — #defects found in QA (Bug/Sub-bug, by Created) ÷ #(Story+Task completed, by Done)')
      +'; prod-labelled defects are excluded from the numerator (they count in Production Leakage).';
  }
  if(mk==='leakage'){
    // [P3-LK] Counted text = the union: QA-entered OR prod-labelled; the
    // pre-QA defects are excluded. Same rule as the tooltip/Formula/box.
    return 'Counted: per period — defects carrying the production label ['+prod+'] ÷ (defects that transitioned into a QA status OR carry the production label [prod]), bucketed by Created date; defects caught before QA are excluded from both sides.';
  }
  // [P4-3] Label-driven escape rate.
  if(mk==='escapereview'){
    return 'Counted: per period — defects labeled ['+(m.qaLabel||'—')+'] ÷ (defects labeled ['+(m.reviewLabel||'—')+'] + ['+(m.qaLabel||'—')+']), bucketed by Created date.';
  }
  // [P0v3-F2] Time in QA: the anchors are named explicitly (qaEntry → qaExit).
  if(mk==='qa'){
    var qaEntryTxt=((S.statusSets||{})[((m.start||{}).set||'qaEntry')]||[]).join(', ')||'—';
    var qaExitTxt=((S.statusSets||{})[((m.end||{}).set||'qaExit')]||[]).join(', ')||'—';
    return 'Counted: per period — avg(first transition into ['+qaExitTxt+'] − first transition into ['+qaEntryTxt+']) for '+types()+'; zero-day intervals excluded. The QA-exit statuses are editable in widget settings.';
  }
  // [P4-4] Status-driven design review turnaround.
  if(mk==='designreview'){
    return 'Counted: per period — avg(first ['+(m.reviewDone||'—')+'] − first ['+(m.designStart||'—')+']) for '+types()+'; zero-day intervals excluded.';
  }
  // [P2v3-1] Clarification Cycle Count.
  if(mk==='clarcycle'){
    return 'Counted: per requirement that entered development in the period — count of transitions out of refinement into a groomed state, between creation and the first transition into the dev-start status set. Items that never entered development are excluded.';
  }
  // [P2v3-2] Review Cycle Count.
  if(mk==='reviewcycle'){
    var rvTxt=((S.statusSets||{}).review||[]).join(', ')||'—';
    return 'Counted: per reviewed item that reached done in the period — number of transitions into the review status set (['+rvTxt+']) minus one. Items that never entered review are excluded; items reviewed exactly once count as zero.';
  }
  if(m.aggregation==='flow'){
    var ser=(mk==='flow')?'opened = Created, resolved = Resolution date'
                         :'new = Created, resolved = Resolution date';
    return 'Counted: per period, two series for '+types()+' — '+ser+'.';
  }
  var bits=[];
  if(mk==='incident'){
    bits.push(types()+' labeled ['+prod+']');
    bits.push('stacked by severity from priority (Critical/Major/Minor)');
  } else if(mk==='backlog'){
    // [P1v3-1] Both sides named: ready items (numerator, the top Issue Type
    // filter) and completed velocity items (denominator), with the
    // EFFECTIVE denominator selection.
    var stB=rcMetricState('backlog');
    var denEffTxt = stB.state==='velocity_sp'
      ? 'Velocity story points (SP)' : 'Throughput issue counts';
    bits.push('ready items ('+types()+') AT each period end (numerator) ÷ completed velocity items per period (denominator, '+denEffTxt+')');
  } else if(mk==='rework'){
    bits.push(types()+' that returned to ['+((S.statusSets[(m.returnTo||{}).set]||[]).join(', ')||'—')+'] after dev start');
  } else if(mk==='bugfix'){
    // [FIX-A5]
    bits.push('Σ(timespent on '+types()+') ÷ Σ(timespent on all completed work) × 100, bucketed by Done date');
  } else {
    bits.push(types());
  }
  return 'Counted: '+bits.join('; ')+'.';
}
// [FIX-A1] Effective Defect Density mode: the explicit setting wins; 'auto'
// picks per_sp when the SP fill-rate of the denominator items (Story/Task
// completed) is ≥ 50%, else per_item.
// [P1-STATES] Explicit two-state pattern for metrics whose formula/unit
// depends on data availability. Returns {state, label, forced, computable}
// for the CURRENT window (recomputed on every rcApply — no page reload).
function rcMetricState(mk){
  var m=((rcDraft||RC_SETTINGS).metrics||{})[mk]||{};
  if(mk==='defectdensity'){
    var dm=m.densityMode||'auto';
    // [P7-DD] Prefer the FILTERED-window snapshot (RC_WIN_STATE.ddMode),
    // committed at the end of every rcApply — the state must agree with
    // the chart after a filter change. The global recompute is the boot
    // fallback only (before the first rcApply).
    var effMode = (RC_WIN_STATE && RC_WIN_STATE.ddMode)
      ? RC_WIN_STATE.ddMode
      : (dm==='per_item' ? 'per_item'
        : dm==='per_sp' ? 'per_sp'
        : (rcDensityFillRate()>=0.5 ? 'per_sp' : 'per_item'));
    var filled = (RC_WIN_STATE && RC_WIN_STATE.ddFilled!==undefined)
      ? RC_WIN_STATE.ddFilled
      : (function(){
          var den=(PM_DATA.defectdensity||[]).filter(function(it){return it.role==='denominator';});
          return den.filter(function(it){ return (it.sp||0)>0; }).length;
        })();
    var state = effMode==='per_sp' ? 'sp_weighted' : 'item_count';
    var forced = dm!=='auto';
    // Forced SP-weighted without any story points in the window → the
    // metric cannot be computed (NO count-formula fallback).
    var computable = !(state==='sp_weighted' && filled===0);
    // [P7-DD] Auto-fallback: the user chose auto and the engine fell back
    // to per_item because story points are absent from the current window —
    // surfaced as a notice (tooltip/settings), never silent.
    var fallback = (dm==='auto' && state==='item_count' && filled===0);
    return {state:state, forced:forced, computable:computable, fallback:fallback,
            label: state==='sp_weighted' ? 'per story point' : 'per item'};
  }
  if(mk==='backlog'){
    // [P19-B3] If the project history contains no ready status at all, the
    // metric cannot be computed — return the standard N/A state with the
    // canonical reason. rcReadyStatusUsed() scans RC_RAW; it is the single
    // source of truth used by the settings panel's amber warning too.
    if(!rcReadyStatusUsed()){
      return { state:'na', forced:false, computable:false, label:'N/A',
               reason:'No ready status present in the project history. '+
                      'Assign the status that marks a story/task as ready to start in '+
                      'Widget settings → Workflow statuses → Ready statuses (set: ready).' };
    }
    // [P10-P0-2] The snapshot carries the ACTUAL coverage decision
    // (covUseSP / covSPMissing) computed in rcApply from the FILTERED
    // window — the state must agree with the chart. The parallel
    // re-derivation below is the boot fallback only (first paint, before
    // the first rcApply has committed a snapshot).
    var den=m.denominator||'auto';
    // (covUseSP / covSPMissing) computed in rcApply from the FILTERED
    // window — the state must agree with the chart. The parallel
    // re-derivation below is the boot fallback only (first paint, before
    // the first rcApply has committed a snapshot).
    var den=m.denominator||'auto';
    if(RC_WIN_STATE && RC_WIN_STATE.covUseSP !== undefined && RC_WIN_STATE.covUseSP !== null){
      var useSP = RC_WIN_STATE.covUseSP;
      var state = useSP ? 'velocity_sp' : 'throughput';
      var forced = den !== 'auto';
      var missing = RC_WIN_STATE.covSPMissing || '';
      if(state === 'velocity_sp' && missing){
        return {state:'na', forced:true, computable:false, label:'N/A',
                reason:'the forced Story-Point coverage cannot be computed — the '+missing+' side carries no story points in the window'};
      }
      return {state:state, forced:forced, computable:true,
              label: useSP ? 'Velocity SP' : 'Throughput'};
    }
    // Boot fallback only (first paint, before the first rcApply).
    var hasSP2=rcWindowHasSP();
    var spr2=rcSprintsAvail();
    var state2 = den==='velocity_sp' ? 'velocity_sp'
               : den==='throughput' ? 'throughput'
               : (hasSP2 && spr2 ? 'velocity_sp' : 'throughput');
    return {state:state2, forced: den!=='auto', computable:true,
            label: state2==='velocity_sp' ? 'Velocity SP' : 'Throughput'};
  }
  // [P4-3] Defect Escape Rate (Review → QA): computable only when two
  // DIFFERENT labels are configured AND the window holds at least one
  // labelled defect (the P1 N/A-state pattern — no fallback formula).
  if(mk==='escapereview'){
    var rl=String(m.reviewLabel||''), ql=String(m.qaLabel||'');
    var erState='ok', erReason='';
    if(!rl || !ql){
      erState='na';
      erReason='Configure the review and QA labels in metric settings to enable this metric.';
    } else if(rl.toLowerCase()===ql.toLowerCase()){
      erState='na';
      erReason='The review and QA labels must be different — with the same label the numerator equals the denominator.';
    } else if(!(PM_DATA.escapereview||[]).length){
      erState='na';
      erReason='No defects with the configured labels in the current window.';
    }
    return {state:erState, forced:false, computable:erState==='ok',
            label:erState==='ok'?'ok':'N/A', reason:erReason};
  }
  // [P2v3-2] Review Cycle Count: N/A until at least one review status is
  // configured (widget settings → Workflow statuses).
  if(mk==='reviewcycle'){
    var rvSet=((rcDraft||RC_SETTINGS).statusSets||{}).review||[];
    if(!rvSet.length){
      return {state:'na', forced:false, computable:false, label:'N/A',
              reason:'Configure at least one review status in widget settings to enable this metric.'};
    }
    return {state:'ok', forced:false, computable:true, label:'ok'};
  }
  // [P2v3-1] Clarification Cycle Count: computable whenever items exist;
  // an empty window renders the standard hidden-average state.
  if(mk==='clarcycle'){
    return {state:'ok', forced:false, computable:true, label:''};
  }
  // [P4-4] Status-driven design review turnaround.
  if(mk==='designreview'){
    var ds=String(m.designStart||''), rd2=String(m.reviewDone||'');
    var drState='ok', drReason='';
    if(!ds || !rd2){
      drState='na';
      drReason='Configure the design start and review done statuses in metric settings to enable this metric.';
    } else if(ds===rd2){
      drState='na';
      drReason='Design start and review done must be different statuses — with the same status every interval is zero days.';
    } else if(!(PM_DATA.designreview||[]).length){
      drState='na';
      drReason='No items with both transitions in the current window.';
    }
    return {state:drState, forced:false, computable:drState==='ok',
            label:drState==='ok'?'ok':'N/A', reason:drReason};
  }
  if(mk==='velocity'){
    // [P1-STATES] Auto resolves to issue counts (Issue Velocity) — the
    // count formula is computable on any data; SP velocity is opt-in via
    // the forced 'sp' state (N/A when the window carries no story points).
    var vm2=m.velocityMode||'auto';
    var hasSP=rcWindowHasSP();
    var state = vm2==='sp' ? 'sp' : 'items';
    var forced = vm2==='sp';
    var computable = !(state==='sp' && !hasSP);
    return {state:state, forced:forced, computable:computable,
            label: state==='sp' ? 'Story Point Velocity' : 'Issue Velocity'};
  }
  if(mk==='bugfix'){
    var ok=rcHasTimespent();
    return {state: ok?'ok':'na', forced:false, computable:ok,
            label: ok ? 'ok' : 'N/A — no worklog in data'};
  }
  return {state:'single', forced:false, computable:true, label:''};
}
// SP fill-rate of the Defect Density denominator items (Story/Task
// completed) in the CURRENT window — the auto-rule input.
function rcDensityFillRate(){
  var den=(PM_DATA.defectdensity||[]).filter(function(it){ return it.role==='denominator'; });
  var filled=den.filter(function(it){ return (it.sp||0)>0; }).length;
  return den.length ? filled/den.length : 0;
}
// [P1-B6] Window-state snapshot: built in rcApply AFTER the window is
// filtered (calendar/dimension/types) — every state-reading surface
// (tooltip, title, y-axis, axis-note, settings panel, conclusion) reads
// THIS instead of recomputing from the global population. Boot fallback:
// when the snapshot is absent, the readers recompute from the global data
// (page boot before the first rcApply).
var RC_WIN_STATE=null;
// Does the CURRENT window carry any story points (velocity items)?
// [P1-B6] Reads the window snapshot when present (the snapshot reflects
// the FILTERED window the chart was drawn from), else the global data.
function rcWindowHasSP(){
  if(RC_WIN_STATE) return !!RC_WIN_STATE.hasSP;
  return (PM_DATA.velocity||[]).some(function(v){ return (v.sp||0)>0; });
}
// [P3-2] Effective sprint availability: the Widget settings statement
// (sprintData: auto | available | none); auto resolves from the project
// data flag (RC_HAS_SPRINTS_DATA, computed by the Python derivation).
// [P1-B6] The snapshot's value wins — it is the one the chart used.
function rcSprintsAvail(){
  if(RC_WIN_STATE && RC_WIN_STATE.sprintsAvail!==undefined) return !!RC_WIN_STATE.sprintsAvail;
  var S=rcDraft||RC_SETTINGS;
  var sd=(S&&S.sprintData)||'auto';
  if(sd==='available') return true;
  if(sd==='none') return false;
  return (typeof RC_HAS_SPRINTS_DATA==='undefined') ? true : !!RC_HAS_SPRINTS_DATA;
}
function rcDensityMode(){
  // [P1-B6] The snapshot's effective mode (computed on the WINDOW items)
  // wins — the global recompute is only the boot fallback.
  var m=((rcDraft||RC_SETTINGS).metrics||{}).defectdensity||{};
  if(RC_WIN_STATE && RC_WIN_STATE.ddMode) return RC_WIN_STATE.ddMode;
  var den=(PM_DATA.defectdensity||[]).filter(function(it){ return it.role==='denominator'; });
  var filled=den.filter(function(it){ return (it.sp||0)>0; }).length;
  var rate=den.length? filled/den.length : 0;
  return m.densityMode==='per_item' ? 'per_item'
       : m.densityMode==='per_sp' ? 'per_sp'
       : (den.length && rate>=0.5 ? 'per_sp' : 'per_item');
}
// [FIX-A5] Does the project log work time? (timespent fill-rate ≥ 20% over
// the Bug Fixing items — numerator + denominator roles.) [P1-B6] Reads the
// window snapshot when present (the same data the chart was drawn from).
function rcHasTimespent(){
  if(RC_WIN_STATE && RC_WIN_STATE.hasTimespent!==undefined) return !!RC_WIN_STATE.hasTimespent;
  var its=PM_DATA.bugfix||[];
  if(!its.length) return false;
  var withTs=0;
  its.forEach(function(it){ if((it.timeSpent||0)>0) withTs++; });
  return withTs/Math.max(1,its.length)>=0.2;
}
// [P5-TP] The duplicate rcSprintsAvail/rcDensityMode/rcHasTimespent
// definitions that used to sit here are REMOVED — they shadowed the
// RC_WIN_STATE-aware versions above (the snapshot's value must win).
// [P1-STATES] Display name of a metric for the CURRENT state (used by the
// tooltip header, the settings panel header and the axis-note).
function rcMetricDisplayName(mk){
  var cfg=RC_CFG[mk]||{};
  var st=rcMetricState(mk);
  if(mk==='defectdensity'){
    // [P7-DD] The auto per_item fallback is named in the header.
    var suffix = st.label;
    if(st.fallback) suffix += ' — no SP in data';
    return 'Defect Density ('+suffix+')';
  }
  if(mk==='backlog') return st.state==='velocity_sp'
    ? 'Backlog Health (story points of ready work ÷ Velocity SP per period)'
    : 'Backlog Health (ready issues ÷ Throughput per period)';
  if(mk==='velocity') return st.state==='sp'
    ? 'Story Point Velocity (SP per period)'
    : 'Issue Velocity (completed items per period)';
  if(mk==='bugfix' && st.state==='na') return 'Bug Fixing Time Allocation (N/A — no worklog)';
  return cfg.label||mk;
}
// Unified tooltip: interpretation + Formula + Counted + Trend + Box.
function rcTipFor(mk){
  var S=RC_SETTINGS;
  // [FIX-A1] Defect Density: the base text follows the effective mode;
  // [FIX-A5] Bugfix: N/A text when the project has no worklog.
  var base=RC_TIP[mk]||'';
  if(mk==='defectdensity'&&rcDensityMode()==='per_item'){
    base=RC_TIP.defectdensity_per_item||base;
  }
  if(mk==='bugfix'&&rcHasTimespent()===false){
    base=RC_TIP.bugfix_na||base;
  }
  var st=rcMetricState(mk);
  if(mk==='defectdensity'){
    // [P7-DD] The numerator is the COUNT of defects found in QA in both
    // modes; the denominator switches SP ÷ count. The auto per_item
    // fallback is surfaced as a notice, never silent.
    base='Defect Density ('+st.label+') = '+(st.state==='sp_weighted'
      ? 'number of defects found in QA ÷ story points of completed Story/Task per period'
      : 'number of defects found in QA ÷ number of completed Story/Task per period')
      +'. '
      +(st.fallback
        ? '⚠️ Story points are absent from the current window (or the SP fill-rate is below 50%) — the metric has automatically switched to the count-based denominator. Switch the mode in metric settings to force N/A instead. '
        : '')
      +'High density = messy logic / rushed coding. Lower is better.';
    if(st.forced && !st.computable){
      base += ' NOTE: the forced state cannot be computed on the current data (no story points) — the metric shows N/A instead of silently falling back to the other formula.';
    }
  }
  if(mk==='backlog'){
    // [P3-2] The reason text follows the EFFECTIVE sprint availability and
    // the setting source (auto-detect vs explicit statement) — no hardcoded
    // project sentence.
    // [P2-I12] sprEff is computed ONCE; the auto state text states WHERE
    // the decision came from (auto-detect by data vs the explicit Widget
    // settings statement). Forced states need no source note.
    var sprEff=rcSprintsAvail();
    var sdSrc=(((rcDraft||RC_SETTINGS)||{}).sprintData)||'auto';
    // [P2-I12] The decision source is stated ONLY for the auto rule (the
    // user picked forced states explicitly — no note needed there).
    var sprSrcTxt = st.forced ? '' : (
      (sdSrc==='auto')
        ? ' (source: auto-detect — sprints '+(sprEff?'present':'absent')+' by data)'
        : (sdSrc==='available'
          ? ' (source: explicit — sprints present per Widget settings)'
          : ' (source: explicit — no sprints per Widget settings)'));
    var sprTxt = st.state==='velocity_sp'
      ? 'team speed measured in average Velocity story points per period'
        +(!sprEff ? ' (no sprint data — the team speed is measured per calendar period, not per sprint; switch the state or Widget settings → Sprint data availability to change this)'
              : '')
      : 'team speed measured in average Throughput issues per period'
        +(!sprEff ? ' — no sprint data (per Widget settings → Sprint data availability), so the auto rule uses issue counts (no mixed units)' : '');
    base = st.state==='velocity_sp'
      ? 'Backlog Health (story points of ready work ÷ Velocity SP per period) = how many sprints of ready work the backlog holds, with '+sprTxt+'.'
      : 'Backlog Health (ready issues ÷ Throughput per period) = HOW MANY SPRINTS of ready work the backlog holds, with '+sprTxt+'.';
    // [P2-I12] The decision source is appended only for the auto rule.
    if(!st.forced && sprSrcTxt){
      base += ' '+sprSrcTxt;
    }
    // [P1v3-1] The numerator honours the top Issue Type filter; the
    // denominator uses the Velocity metric's configured type list (distinct
    // settings — not one shared set). The auto rule needs story points on
    // BOTH sides; zero bars do not feed the average.
    base += ' Numerator: ready items of the SELECTED issue types; denominator: team speed over the type list configured for the Velocity metric (a distinct setting — not the Backlog Health type selection).';
    base += ' Auto rule: Story-Point coverage requires story points on BOTH sides (ready items and completed velocity items); sprint availability applies. Buckets with no ready backlog or no completed work render as zero bars on the chart but do not enter the average.';
    if(st.forced && !st.computable){
      base += ' NOTE: the forced Velocity SP state cannot be computed on the current data (no story points in the window) — the metric shows N/A instead of silently falling back to issue counts.';
    }
  }
  // [P1v3-1e] The box/conclusion rules for Backlog Health.
  if(mk==='backlog'){
    base += ' Box: the average is computed only over control points where both the ready backlog and the team-speed denominator are non-zero; zero bars do not enter the average; the number of computable control points is shown in the box label. The band judgement uses the most recent computable control point (the line names the period when it is not the last bucket); with no computable control point the conclusion shows the empty state. The trend line uses every bucket of the window, including zero-valued ones.';
  }
  // [P4-3]/[P4-4] N/A-state reasons surface in the tooltip.
  if((mk==='escapereview'||mk==='designreview') && st.reason){
    base = st.reason;
  }
  // [P0-B4] velocity writes the INTRO text (base), not the assembled tip —
  // the standard Formula/Counted/Trend/Box sections must survive. The
  // bugfix N/A modifier also runs BEFORE the final assembly (it used to
  // overwrite base after tip was built and never took effect).
  if(mk==='velocity'){
    // [P9-P2-1] The UI type label is Defect (rcTypeLabel normalises Bug).
    base = (st.state==='sp'
      ? 'Story Point Velocity = story points of completed Story/Task/Defect issues per period. Measures team throughput in story points.'
      : 'Issue Velocity = number of completed Story/Task/Defect issues per period. Measures team throughput in issue counts, not story points.')
      +'. Higher is better: a rising trend is Improving, a falling trend is Degrading. The box shows the average completed per period over the window.';
    if(st.forced && !st.computable){
      base += ' NOTE: the forced SP state cannot be computed on the current data (no story points) — N/A.';
    }
  }
  // [P2v3-1/2] The count metrics write the INTRO text (base) — the standard
  // Formula/Counted/Trend/Box sections survive the assembly.
  if(mk==='clarcycle'){
    // [P9-P1-2] The tooltip names the healthy threshold the ref line draws.
    base = 'Clarification Cycle Count = the average number of times a requirement was returned from a groomed state back to refinement before development started, measured per requirement that entered development during the period. Lower is better. Items that started without any clarification rounds contribute zero to the average; the metric reports the expected number of clarification rounds per requirement that entered development. Relationship: this metric counts returns BEFORE development starts; Requirements Rework Rate counts returns AFTER development starts — both metrics are meaningful together. Healthy: ≤ 2 cycles per requirement.';
  }
  if(mk==='reviewcycle'){
    base = 'Review Cycle Count = the average number of times an item was returned from the review phase for changes before approval, measured per reviewed item that reached done during the period. Items approved on the first review contribute zero; items never reviewed are excluded. Lower is better — healthy is ≤ 2 re-reviews per item. The review status set is editable in widget settings; without at least one review status configured, the metric renders N/A.';
  }
  // [P4-3]/[P4-4]/[P2v3-2]/[P19-B3] N/A-state reasons surface in the tooltip.
  if((mk==='escapereview'||mk==='designreview'||mk==='reviewcycle'||mk==='backlog') && st.reason){
    base = st.reason;
  }
  // [P1v3-5] The bugfix body names the CONFIGURED numerator types (the same
  // rendering the counted line uses) — the hard-coded pair is gone.
  if(mk==='bugfix'){
    var S3=rcDraft||RC_SETTINGS, m3=((S3.metrics||{})[mk])||{};
    var bfTypes=(typeof m3.types==='string')?((S3.types||{})[m3.types]||[]):(m3.types||[]);
    base = 'Bug Fixing Time Allocation = Σ(timespent on '+((bfTypes.join(', '))||'—')+') ÷ Σ(timespent on all completed work) × 100% per period. Requires Jira worklog. Healthy: < 20%.'
      +(st.state==='na' ? ' '+(RC_TIP.bugfix_na||'') : '');
  }
  var tip=(base||'')
    +' Formula: '+rcFormulaText(mk, S)+'.'
    +' '+rcTipCounted(mk)
    +' '+rcTrendRule(mk, S)
    +' '+rcTipBoxFor(mk);
  // [P1-5] Healthy reference reminder for metrics with reference lines.
  if(RC_REF_LINES[mk]){
    tip += ' Healthy reference: '+RC_REF_LINES[mk].map(function(r){return r.label;}).join(', ')+'.';
  }
  // [P1-3] WIP per_developer mode explanation + [P1-STATES] granularity note.
  if(mk==='wip'){
    var wm=(((rcDraft||RC_SETTINGS).metrics||{}).wip||{}).wipMode||'total';
    if(wm==='per_developer'){
      tip += ' Current mode: per_developer — WIP is normalized by the number of unique assignees (developers) per period; the dashed line marks ≤ 1.5 per dev.';
    } else {
      tip += ' Mode: total (absolute WIP). Switch to per_developer in metric settings to normalize by the number of active developers.';
    }
    // [P1-STATES] The snapshot follows the Periods selector.
    tip += ' Granularity of the snapshot follows the Periods selector; a daily snapshot requires Periods = Daily.';
  }
  // [P1-1] Person-dimension coaching reminder.
  if(document.getElementById('rcDim') && document.getElementById('rcDim').value==='person'){
    tip += ' Person view is for coaching only — never for performance evaluation.';
  }
  return tip;
}
function rcSetTip(){
  var box=document.getElementById('rcTipBox');
  if(box){ box.innerHTML = rcTipHtml(rcTipFor(rcMetric)); }
}
function rcActiveItems(){ return PM_DATA[rcMetric]||[]; }
function rcSetMetric(m){
  rcMetric = m;
  Object.keys(RC_CFG).forEach(function(k){
    var b=document.getElementById('rcM-'+k);
    if(b){ b.classList.toggle('bg-blue-600', m===k); b.classList.toggle('text-white', m===k); }
  });
  // [P1-B8] The tooltip is NOT built here — rcApply rebuilds it at the END
  // (after the window is computed and the state snapshot exists), so the
  // tooltip always describes the state the chart actually shows.
  rcPopulateDim();
  rcPopulateTypes();
  // The settings panel is per-metric: if it is open, re-render it so it
  // follows the newly selected metric (same behavior as the info tooltip).
  var _sp=document.getElementById('rcSettingsPanel');
  if(_sp && !_sp.classList.contains('hidden')){ rcSettingsRender(); }
  // Default state: keep the calendar aligned with the current metric's
  // default window until the user edits the dates manually.
  rcSyncCalendar();
  rcApply();
}
"""
