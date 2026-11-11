# Process Metrics – Trends: Data Contract

This contract describes a single interactive widget that displays Jira-derived process measurements over time, supports filtering and issue-level drilldown, and consumes issue fields, status transitions, optional Sprint metadata and issue time totals. It does not describe the rest of the dashboard.

## 2. Widget scope

The following 20 measurements are included, grouped by their process phase:

- **Requirements:** Requirements Cycle Time, Requirements Rework Rate, Clarification Cycle Count.

- **Design:** Design Review Turnaround.

- **Flow:** Opened vs Resolved, Work in Progress, Flow Efficiency.

- **Development:** Cycle Time, Issue Lead Time (avg days), Issue Velocity (completed items per period), Throughput.

- **Backlog:** Backlog Health.

- **Defects:** Bug Growth (new vs resolved), Bug Fixing Time Allocation.

- **Testing:** Production Leakage Rate, Defect Density, Time in QA.

- **Review:** Defect Escape Rate (Review → QA), Review Cycle Count.

- **Operations:** Incident Frequency.

This contract excludes Delivery, Scope & Predictability, Quality & Tech Debt, Jira Reports, Product Info, Jira Data Profile and OLAP constructors. The widget contains no baseline, no As-Is assessment and no confidence tiers; it does not consume DORA metrics, lines-of-code metrics, code-repository data, deployment data or external-tool signals.

## 3. Data source

Jira is the only data source. Field discovery supplies custom field identifiers; paginated issue search supplies issue fields and expanded changelogs. Current sync reads Jira's aggregated Time Spent field, not individual worklog entries. A separate worklog endpoint is not required for the existing computation. A complete extraction must retrieve any changelog pages omitted from the search expansion; the current sync does not establish that completeness.

Preserve Jira ISO-8601 offsets at extraction. Sprint catalogue timestamps with offsets are normalized to UTC. The browser uses exact original field timestamps for real-Sprint anchors where available; status event timestamps are parsed as instants. Created is also truncated without offset and resolutiondate to date for existing calendar and duration paths; calendar bucket boundaries use browser-local dates. Do not assume a single timezone interpretation across these paths.

## 4. The issue record

The browser receives one normalized record per keyed issue. Empty or null optional values are supported; a missing signal may prevent a particular calculation. Bug is displayed as Defect, Sub-Bug as Sub-bug, and Sub-task as Sub-task. The cache can retain both sides of each status transition; the browser receives chronological timestamp and destination pairs.

| Field | Type | Required | Role |
| --- | --- | --- | --- |
| key | string | Yes | Jira issue key; joins the issue directory and derived records. |
| type | string | Yes | Jira issue type; Bug becomes Defect, Sub-Bug becomes Sub-bug and Sub-task is displayed as Sub-task. |
| project | string | Yes | Project identifier; missing values become Unknown. |
| team | string | No | First component-derived value; also used by the Component dimension. |
| teams | array of strings | No | Precomputed team signals; live Team selection resolves from fieldvals or labels instead. |
| fieldvals | object mapping field name to string or null | No | Discovered team field values by display name, read from issue text. |
| epic | string | No | Epic link, otherwise parent key, otherwise No Epic. |
| person | string | No | Assignee display value; missing assignees are grouped as unassigned. |
| status | string | No | Current issue status; compared case-insensitively with configured sets. |
| created | string | No | Creation timestamp truncated to the first 19 characters, without its offset; calendar derivation uses this value. |
| resolutiondate | string | No | Resolution date truncated to YYYY-MM-DD. |
| created_ts | string | No | Original Jira creation timestamp used as the precise Sprint membership anchor. |
| resolved_ts | string | No | Original Jira resolution timestamp used as the precise Sprint membership anchor. |
| updated_ts | string | No | Original Jira update timestamp used when determining the snapshot cutoff. |
| has_sprint | boolean | Yes | Whether the Sprint field was populated, including values without a usable identity or date. |
| sprint_ids | array of strings | Yes | Distinct Jira sprint IDs assigned to this issue, in observed order. |
| labels | string | No | Delimited Jira labels used for team membership, production and escape roles. |
| priority | string | No | Priority mapped to severity; an unmatched value becomes Minor. |
| sp | number or null | No | Story Points parsed from the issue text; absent or unparseable is null. |
| timeSpent | number or null | No | Issue total time spent in seconds; absent or unparseable is null. |
| events | array of [timestamp, destination status] pairs | Yes | Status transitions sorted chronologically; source status is not present in the browser record. |

A separate issue directory provides URL, type, summary, current status, creation and update dates, and days in status for drilldown. A project-level Sprint catalogue carries IDs, names, board IDs, state, start, planned end, completion, effective finish, usability and conflict flags. Coverage carries total issue count and populated-Sprint count.

## 5. Settings — two layers

Settings are applied from defaults plus overrides and persisted locally in the browser. Type aliases and status sets belong to the shared settings data; a metric may reference them or use an explicit value.

### 5.1 Widget-level settings

| Setting | Default | Consumers and purpose |
| --- | --- | --- |
| statusSets.devStart | ["in progress"] | cycle, rework, clarcycle, cycletime, wip, floweff: Workflow status set. Selected from observed workflow statuses. |
| statusSets.done | ["closed", "done", "resolved", "complete", "completed", "verified", "released"] | lead, cycletime, wip, floweff, bugfix, defectdensity, reviewcycle: Workflow status set. Selected from observed workflow statuses. |
| statusSets.qaEntry | ["ready for qa", "in testing", "in qa", "testing", "qa"] | qa: Workflow status set. Selected from observed workflow statuses. |
| statusSets.qaExit | ["ready for demo", "resolved", "closed"] | qa: Workflow status set. Selected from observed workflow statuses. |
| statusSets.qaSet | ["ready for qa", "in testing", "in qa", "testing", "qa"] | leakage, defectdensity: Workflow status set. Selected from observed workflow statuses. |
| statusSets.ready | ["ready for development"] | backlog: Workflow status set. The only UI editor is in Backlog Health metric settings. |
| statusSets.backlog | ["new", "open", "to do", "backlog", "reopened", "ready for development", "ready for grooming", "ready for demo", "analysis", "design"] | Referenced when selected as an anchor set.: Workflow status set. Selected from observed workflow statuses. |
| statusSets.refinement | ["new", "open", "to do", "backlog", "reopened", "ready for grooming", "refinement", "requirements", "backlog refinement", "grooming"] | rework, clarcycle: Workflow status set. Selected from observed workflow statuses. |
| statusSets.review | [] | reviewcycle: Workflow status set. Selected from observed workflow statuses. |
| types.delivery | ["Story", "Task", "Defect"] | ['throughput']: Named issue-type pool resolved by metrics that reference this alias. |
| types.req | ["Story", "Task"] | ['cycle', 'rework']: Named issue-type pool resolved by metrics that reference this alias. |
| types.bug | ["Defect", "Sub-bug"] | ['bugflow', 'escapereview']: Named issue-type pool resolved by metrics that reference this alias. |
| types.velocity | ["Story", "Task", "Defect"] | ['velocity']: Named issue-type pool resolved by metrics that reference this alias. |
| types.flow | ["Story", "Task"] | ['flow']: Named issue-type pool resolved by metrics that reference this alias. |
| types.backlog | ["Story", "Task"] | ['backlog']: Named issue-type pool resolved by metrics that reference this alias. |
| types.work | ["Story", "Task", "Defect", "Sub-bug"] | ['cycletime', 'floweff', 'qa', 'reviewcycle']: Named issue-type pool resolved by metrics that reference this alias. |
| teamConfig.source | "none" | ['cycle', 'rework', 'backlog', 'designreview', 'flow', 'cycletime', 'lead', 'velocity', 'throughput', 'wip', 'floweff', 'leakage', 'defectdensity', 'incident', 'bugflow', 'bugfix', 'qa', 'escapereview', 'clarcycle', 'reviewcycle']: Live team source. |
| teamConfig.fieldName | "" | ['cycle', 'rework', 'backlog', 'designreview', 'flow', 'cycletime', 'lead', 'velocity', 'throughput', 'wip', 'floweff', 'leakage', 'defectdensity', 'incident', 'bugflow', 'bugfix', 'qa', 'escapereview', 'clarcycle', 'reviewcycle']: Exact display name of the field used in field mode. |
| teamConfig.labels | [] | ['cycle', 'rework', 'backlog', 'designreview', 'flow', 'cycletime', 'lead', 'velocity', 'throughput', 'wip', 'floweff', 'leakage', 'defectdensity', 'incident', 'bugflow', 'bugfix', 'qa', 'escapereview', 'clarcycle', 'reviewcycle']: Selected labels used as team names in labels mode. |
| prodLabel | "prod" | ['leakage', 'incident', 'defectdensity']: Default prod matches prod, prod_ and prod- prefixes and production, case-insensitively; a metric override can win. |
| sprintData | "auto" | ['cycle', 'rework', 'backlog', 'designreview', 'flow', 'cycletime', 'lead', 'velocity', 'throughput', 'wip', 'floweff', 'leakage', 'defectdensity', 'incident', 'bugflow', 'bugfix', 'qa', 'escapereview', 'clarcycle', 'reviewcycle']: Controls Sprint period source and Backlog Health automatic denominator. |
| severityMap | {"Critical": ["blocker", "critical", "highest"], "Major": ["high", "major"], "Minor": ["medium", "normal", "low", "minor", "trivial"]} | ['incident']: Priority mapping; a metric map takes precedence and an unmatched priority is Minor. |
| personMinCohort | 5 | ['cycle', 'rework', 'backlog', 'designreview', 'flow', 'cycletime', 'lead', 'velocity', 'throughput', 'wip', 'floweff', 'leakage', 'defectdensity', 'incident', 'bugflow', 'bugfix', 'qa', 'escapereview', 'clarcycle', 'reviewcycle']: Minimum derived-record count for a named person in the selector; smaller groups become Other. |

The ready status is shared settings data but is edited only in the Backlog Health metric panel. This avoids two competing editors. A project may auto-seed review statuses from its observed vocabulary.

### 5.2 Metric-level settings

Each metric owns an issue-type pool, an untouched default window size, a stable-band setting where a slope verdict applies, and the relevant anchors and modes. Initially the window is five periods and the stable band is 10%; the panel offers 1–10 periods and stable bands of 5–30% in five-point steps. Aggregation and trend direction are semantic settings displayed as fixed in the panel. The top selector filters pre-derived records; Bug Fixing has a separately derived denominator pool, and Backlog Health handles its velocity denominator separately. The JSON settings section provides every field, allowed value and exact default.

| Metric | Default pool | Metric-specific defaults |
| --- | --- | --- |
| cycle | Story, Task | start: created; end: devStart |
| rework | Story, Task | anchor: devStart; returnTo: refinement |
| backlog | Story, Task | start: created; membership: ready; defects: exclude; denominator: auto; targetMin: 2; targetMax: 3 |
| designreview | Story, Task | designStart: not configured; reviewDone: not configured |
| flow | Story, Task | series: opened created; resolved resolutiondate |
| cycletime | Story, Task, Defect, Sub-bug | start: devStart; end: done |
| lead | Story, Task, Defect, Sub-bug | start: created; end: done with resolution-date fallback |
| velocity | Story, Task, Defect | start: resolutiondate; velocityMode: auto |
| throughput | Story, Task, Defect | start: resolutiondate |
| wip | Story, Task, Defect, Sub-bug | start: devStart; end: done; wipMode: total |
| floweff | Story, Task, Defect, Sub-bug | active: start devStart; end done; total: start created; end done |
| leakage | Defect, Sub-bug | start: created; prodLabel: prod |
| defectdensity | Story, Task, Defect, Sub-bug | densityMode: auto |
| incident | Defect, Sub-bug | start: created; prodLabel: prod; severityMap: metric map initially matches the shared default |
| bugflow | Defect, Sub-bug | series: new created; resolved resolutiondate |
| bugfix | Defect, Sub-bug | No additional mode control. |
| qa | Story, Task, Defect, Sub-bug | start: qaEntry; end: qaExit |
| escapereview | Defect, Sub-bug | start: created; reviewLabel: not configured; qaLabel: not configured |
| clarcycle | Story, Task | start: created; end: devStart; returnTo: refinement |
| reviewcycle | Story, Task, Defect, Sub-bug | end: done |

Anchor values reference a creation or resolution field or a named workflow status set. Backlog Health has a ready selector, defect inclusion mode, denominator and band; WIP has total or per-developer mode; Velocity and Defect Density select automatic or forced units; the escape and design metrics each require their own labels or statuses.

## 6. The shared pipeline

All 20 metrics use one shared pipeline. Metric-specific derivation and aggregation branches are inputs to this pipeline, not separate widget architectures.

### 6.1 Periods

The selector offers daily, weekly, sprint, monthly, quarterly and annual; Sprint and five periods are the UI defaults, with per-metric defaultN. Auto uses Jira sprint IDs when more than 50% of all loaded issues have a populated Sprint value, including undated values; available forces Jira sprints and none forces two-week ISO calendar buckets. Real Sprint uses the latest N completed usable sprints with dimension-matched project activity. Activity includes an issue whose lifetime overlaps the sprint or a status event in it. Manual dates select whole intersecting active sprint periods, including unfinished ones; incomplete periods are excluded from comparative trend verdicts. Sprint IDs remain separate even across overlapping boards. A derived event belongs only to its issue's single usable sprint containing its anchor; no membership, no matching boundary or ambiguous membership excludes it. WIP and ready snapshots instead resolve membership at the sprint's end control point and require a unique match there. Intervals are start-inclusive and end-exclusive. A closed sprint uses valid completeDate, otherwise valid endDate; dates are not invented. The active sprint cutoff is the latest captured project timestamp or closed sprint finish. For calendar periods, the common project anchor is the last bucket with at least max(1, ceil(10% of the lower median of nonempty buckets)) creation, resolution and status events under the selected dimension, with project-wide fallback. The default window contains N contiguous buckets ending there, so some may be empty; the same anchor is shared, but metric-specific anchor events determine which derived records enter each period. For a project that ended in late 2025, anchoring on its recorded activity naturally retains historical periods instead of moving the default to today's date. A manual calendar range covers all intersecting buckets; if one side is missing, it is inferred from the filtered metric items. Manual ranges are remembered by metric and granularity and reset on metric-settings Apply.

### 6.2 Dimensions

Project is the default and selects all project records. Team resolves live: none gives Team is not defined; field gives one value; labels can assign one issue to every selected matching label; unresolved issues use Team is not defined. Component reads the record's component-derived team value; Epic uses epic or parent fallback; Person uses assignee. Person is for coaching only, never performance evaluation. At selector population, persons with fewer than personMinCohort derived records after the current type selection are grouped into Other; the selector count is not restricted by the calendar range. An issue drilldown provides work-item detail; it is not an additional dimension selector.

### 6.3 Issue-type filter

The top-panel selection is session-local per metric and is seeded by its metric type pool. It filters already-derived records; it cannot create numerator records beyond the metric pool. Bug Fixing's independently derived denominator can admit additional types when selected, while Backlog Health's velocity denominator is handled separately.

### 6.4 Average box

- **avg:** Arithmetic average of eligible values per period and across the window; floweff instead divides summed active days by summed total days at both levels.
- **rate:** Counted successes divided by total, times 100; the average box divides window totals. Role-based rates use numerator and denominator roles. Density divides defects by the selected denominator without multiplying by 100 and only computable periods enter its box.
- **allocation:** Sum numerator time divided by denominator time times 100 per period and over the window.
- **count:** Counts per period, including zeros; Velocity may sum SP instead. The box is total divided by number of periods, but is hidden if its total is zero.
- **flow:** Counts each of two series per period, including zeros; box reports each series total divided by number of periods.
- **grouped:** Counts by severity, with zero-filled periods; box reports total incidents divided by number of periods.
- **wipSnapshot:** At each period end count active intervals; per-developer mode divides by unique assignees and returns null with none. Box averages defined snapshots.
- **coverage:** Divide the ready snapshot by same-period completed speed in matching units. Display zero when speed is zero; box averages only control points with positive numerator and denominator.

### 6.5 Tooltips

Each metric has its own explanatory tooltip. Formula, current types, effective states, counted population, trend rule, Sprint notices and person-use notices can be rebuilt from settings or the active window; static explanatory text and reference lines remain fixed where present.

### 6.6 Healthy reference lines

Static guidance appears for cycle, rework, designreview, cycletime, lead, floweff, leakage, bugfix, qa, clarcycle and reviewcycle; WIP has a line in per-developer mode. Backlog Health uses its configurable band. Other metrics have no guidance line.

### 6.7 Trend verdict

Single-series verdicts require three defined completed-period values. Ordinary least-squares slope times the span of defined period indices, divided by absolute mean and multiplied by 100, is compared to stablePct, default 10. An all-zero series is stable; otherwise the configured up/down direction determines improving or degrading. Delta compares adjacent last and previous completed values and is unavailable if either is missing or the previous value is zero. Flow and bugflow instead use net resolved-minus-opened level and signed balance trend: the trend can soften an unfavourable or favourable net, but cannot reverse it. Backlog Health judges the most recent computable completed control point against its configured band rather than using a slope verdict.

## 7. The metrics

### Requirements Cycle Time (`cycle`)

**Phase and aggregation:** Requirements; avg. **Default types:** Story, Task.

**What it measures and derivation:** For each selected requirement, subtract creation date from its first devStart transition; bucket by that transition and average whole days.

**Jira data:** created, events. **Unit:** days.

**Zero-day rule:** Intervals under one whole day and nonpositive intervals are excluded.

**Trend:** Lower is improving under the shared relative rule.

**Healthy reference:** Less than 14 days.

**N/A and edge cases:** No metric-specific reason; an empty denominator or absent eligible items can leave a gap or hide the average. The shared real-Sprint no-period condition also applies. Missing either anchor excludes the item.

**Dimensions:** Project, Team, Component, Epic, Person and Time; issue detail is available through drilldown.

### Requirements Rework Rate (`rework`)

**Phase and aggregation:** Requirements; rate. **Default types:** Story, Task.

**What it measures and derivation:** Among items with a first devStart event, divide those with a later transition into refinement by all started items, times 100; bucket at devStart.

**Jira data:** events. **Unit:** percent.

**Zero-day rule:** Not a duration; zero rework is included.

**Trend:** Lower is improving under the shared relative rule.

**Healthy reference:** Below 10%; above 20% is a warning.

**N/A and edge cases:** No metric-specific reason; an empty denominator or absent eligible items can leave a gap or hide the average. The shared real-Sprint no-period condition also applies. Only events after the anchor count; a missing start excludes the item.

**Dimensions:** Project, Team, Component, Epic, Person and Time; issue detail is available through drilldown.

### Backlog Health (`backlog`)

**Phase and aggregation:** Backlog; coverage. **Default types:** Story, Task.

**What it measures and derivation:** At each period end count ready items or sum their points, then divide by the completed velocity item count or points in that same period. Auto SP requires Sprint availability and positive SP on both sides.

**Jira data:** created, status, events, sp, sprint_ids. **Unit:** ready work periods.

**Zero-day rule:** Not a duration; zero bars can denote a non-computable control point.

**Trend:** Uses the most recent computable completed point against the configured band.

**Healthy reference:** Configured band, by default 2–3 periods.

**N/A and edge cases:** Ready status absent: No configured ready status appears in current status or captured history.; Forced SP ready side: Forced velocity_sp and no positive SP on participating ready items.; Forced SP completed side: Forced velocity_sp, ready SP present, but no positive SP on qualifying completed velocity items. The shared real-Sprint no-period condition also applies. The average and verdict use computable points only. A current ready status without a captured entry is clamped to the window or Jira snapshot. The speed population is velocity records restricted to Story, Task, Defect, independent of the numerator type selection.

**Dimensions:** Project, Team, Component, Epic, Person and Time; issue detail is available through drilldown.

### Design Review Turnaround (`designreview`)

**Phase and aggregation:** Design; avg. **Default types:** Story, Task.

**What it measures and derivation:** Average whole days from the first configured design-start transition to the first configured review-done transition; bucket at review completion.

**Jira data:** events. **Unit:** days.

**Zero-day rule:** Nonpositive and under-one-whole-day intervals are excluded.

**Trend:** Lower is improving under the shared relative rule.

**Healthy reference:** At most 2 days.

**N/A and edge cases:** Unconfigured statuses: Either status is empty.; Equal statuses: Configured strings are identical.; No derived items: The global derived designreview array is empty; the message mentions the current window, but the check is global. The shared real-Sprint no-period condition also applies. Both configured statuses must be different; elapsed calendar time is used, not business-day arithmetic.

**Dimensions:** Project, Team, Component, Epic, Person and Time; issue detail is available through drilldown.

### Opened vs Resolved (`flow`)

**Phase and aggregation:** Flow; flow. **Default types:** Story, Task.

**What it measures and derivation:** Count created and resolved requirements separately per period; compare the net resolved minus opened balance.

**Jira data:** created, resolutiondate. **Unit:** issues.

**Zero-day rule:** Not a duration; empty periods are zero-filled.

**Trend:** Uses the shared balance-level and trend rule.

**Healthy reference:** None.

**N/A and edge cases:** No metric-specific reason; an empty denominator or absent eligible items can leave a gap or hide the average. The shared real-Sprint no-period condition also applies. A single issue can contribute to both series, in different periods.

**Dimensions:** Project, Team, Component, Epic, Person and Time; issue detail is available through drilldown.

### Cycle Time (`cycletime`)

**Phase and aggregation:** Development; avg. **Default types:** Story, Task, Defect, Sub-bug.

**What it measures and derivation:** Average whole days from first devStart to first done transition; bucket at done.

**Jira data:** events. **Unit:** days.

**Zero-day rule:** Nonpositive and under-one-whole-day intervals are excluded.

**Trend:** Lower is improving under the shared relative rule.

**Healthy reference:** Less than 14 days.

**N/A and edge cases:** No metric-specific reason; an empty denominator or absent eligible items can leave a gap or hide the average. The shared real-Sprint no-period condition also applies. Both transitions must exist and be ordered.

**Dimensions:** Project, Team, Component, Epic, Person and Time; issue detail is available through drilldown.

### Issue Lead Time (avg days) (`lead`)

**Phase and aggregation:** Development; avg. **Default types:** Story, Task, Defect, Sub-bug.

**What it measures and derivation:** Average whole days from creation to first done; if missing, use resolution date; bucket at the end anchor.

**Jira data:** created, resolutiondate, events. **Unit:** days.

**Zero-day rule:** Nonpositive and under-one-whole-day intervals are excluded, including fallback.

**Trend:** Lower is improving under the shared relative rule.

**Healthy reference:** Less than 30 days.

**N/A and edge cases:** No metric-specific reason; an empty denominator or absent eligible items can leave a gap or hide the average. The shared real-Sprint no-period condition also applies. Missing or reversed anchors exclude the item.

**Dimensions:** Project, Team, Component, Epic, Person and Time; issue detail is available through drilldown.

### Issue Velocity (completed items per period) (`velocity`)

**Phase and aggregation:** Development; count. **Default types:** Story, Task, Defect.

**What it measures and derivation:** Count completed items or sum their points by resolution date. Auto selects SP when at least half the qualifying completed items have positive points and SP is available.

**Jira data:** resolutiondate, sp. **Unit:** story points or items per period.

**Zero-day rule:** Not a duration; empty periods are zero-filled.

**Trend:** Higher is improving under the shared relative rule.

**Healthy reference:** None.

**N/A and edge cases:** Forced SP absent: Forced sp mode with no qualifying positive story points in the filtered window. The shared real-Sprint no-period condition also applies. A forced SP mode without window SP is N/A; missing points contribute zero in SP mode.

**Dimensions:** Project, Team, Component, Epic, Person and Time; issue detail is available through drilldown.

### Throughput (`throughput`)

**Phase and aggregation:** Development; count. **Default types:** Story, Task, Defect.

**What it measures and derivation:** Count completed items by resolution date per period.

**Jira data:** resolutiondate. **Unit:** issues.

**Zero-day rule:** Not a duration; empty periods are zero-filled.

**Trend:** Higher is improving under the shared relative rule.

**Healthy reference:** None.

**N/A and edge cases:** No metric-specific reason; an empty denominator or absent eligible items can leave a gap or hide the average. The shared real-Sprint no-period condition also applies. A missing resolution date excludes the item.

**Dimensions:** Project, Team, Component, Epic, Person and Time; issue detail is available through drilldown.

### Work in Progress (`wip`)

**Phase and aggregation:** Flow; wipSnapshot. **Default types:** Story, Task, Defect, Sub-bug.

**What it measures and derivation:** Count items active at each period end from first devStart until first later done; optionally divide by unique assignees in the snapshot.

**Jira data:** events, person. **Unit:** items per developer or items.

**Zero-day rule:** Not a duration; zero total WIP is included.

**Trend:** Lower is improving under the shared relative rule.

**Healthy reference:** At most 1.5 items per developer when per_developer mode is selected.

**N/A and edge cases:** No metric-specific reason; an empty denominator or absent eligible items can leave a gap or hide the average. The shared real-Sprint no-period condition also applies. Without an assignee in per-developer mode the control point is null; unfinished work stays active. Derivation reads the shared devStart and done sets directly, rather than the stored WIP start/end anchor specifications.

**Dimensions:** Project, Team, Component, Epic, Person and Time; issue detail is available through drilldown.

### Flow Efficiency (`floweff`)

**Phase and aggregation:** Flow; avg. **Default types:** Story, Task, Defect, Sub-bug.

**What it measures and derivation:** Sum whole active days from devStart to done divided by summed whole elapsed days from creation to done, times 100; bucket at total interval end.

**Jira data:** created, events. **Unit:** percent.

**Zero-day rule:** Total must be positive in whole days; active days may be zero.

**Trend:** Higher is improving under the shared relative rule.

**Healthy reference:** Below 25% poor; above 50% good.

**N/A and edge cases:** No metric-specific reason; an empty denominator or absent eligible items can leave a gap or hide the average. The shared real-Sprint no-period condition also applies. Both intervals must be positive before flooring; aggregation is weighted by total days.

**Dimensions:** Project, Team, Component, Epic, Person and Time; issue detail is available through drilldown.

### Production Leakage Rate (`leakage`)

**Phase and aggregation:** Testing; rate. **Default types:** Defect, Sub-bug.

**What it measures and derivation:** Count production-labelled defects divided by the union of defects reaching qaSet or carrying the production label, times 100, by creation date.

**Jira data:** created, events, labels. **Unit:** percent.

**Zero-day rule:** Not a duration; an empty denominator is a gap.

**Trend:** Lower is improving under the shared relative rule.

**Healthy reference:** Below 15%.

**N/A and edge cases:** No metric-specific reason; an empty denominator or absent eligible items can leave a gap or hide the average. The shared real-Sprint no-period condition also applies. An issue in both groups is counted once in the denominator.

**Dimensions:** Project, Team, Component, Epic, Person and Time; issue detail is available through drilldown.

### Defect Density (`defectdensity`)

**Phase and aggregation:** Testing; rate. **Default types:** Story, Task, Defect, Sub-bug.

**What it measures and derivation:** Divide QA-transitioned, non-production defect count by completed non-defect work count or its story points. Defects use creation date; work uses first done transition.

**Jira data:** created, events, labels, sp. **Unit:** defects per item or story point.

**Zero-day rule:** Not a duration; an empty denominator is a gap.

**Trend:** Lower is improving under the shared relative rule.

**Healthy reference:** None.

**N/A and edge cases:** Forced SP absent: Forced per_sp mode and no positive story points among denominator records in the filtered window. The shared real-Sprint no-period condition also applies. Auto selects per_sp when at least 50% of denominator records have positive SP; forced per_sp without SP is N/A. Only computable periods feed the average.

**Dimensions:** Project, Team, Component, Epic, Person and Time; issue detail is available through drilldown.

### Incident Frequency (`incident`)

**Phase and aggregation:** Operations; grouped. **Default types:** Defect, Sub-bug.

**What it measures and derivation:** Count production-labelled selected issues by priority-derived Critical, Major or Minor severity, by creation date.

**Jira data:** created, labels, priority. **Unit:** issues.

**Zero-day rule:** Not a duration; empty periods are zero-filled.

**Trend:** Lower is improving under the shared relative rule.

**Healthy reference:** None.

**N/A and edge cases:** No metric-specific reason; an empty denominator or absent eligible items can leave a gap or hide the average. The shared real-Sprint no-period condition also applies. Unmapped priorities are Minor; the average is total incidents per period.

**Dimensions:** Project, Team, Component, Epic, Person and Time; issue detail is available through drilldown.

### Bug Growth (new vs resolved) (`bugflow`)

**Phase and aggregation:** Defects; flow. **Default types:** Defect, Sub-bug.

**What it measures and derivation:** Count new and resolved defect issues separately by creation and resolution date; judge resolved minus new balance.

**Jira data:** created, resolutiondate. **Unit:** issues.

**Zero-day rule:** Not a duration; empty periods are zero-filled.

**Trend:** Uses the shared balance-level and trend rule.

**Healthy reference:** None.

**N/A and edge cases:** No metric-specific reason; an empty denominator or absent eligible items can leave a gap or hide the average. The shared real-Sprint no-period condition also applies. A single defect can contribute to both series.

**Dimensions:** Project, Team, Component, Epic, Person and Time; issue detail is available through drilldown.

### Bug Fixing Time Allocation (`bugfix`)

**Phase and aggregation:** Defects; allocation. **Default types:** Defect, Sub-bug.

**What it measures and derivation:** Divide total time spent on the metric's selected numerator types by time spent on denominator records, times 100; bucket at first done. Denominator records are initially derived from all completed types except Sub-task and Test.

**Jira data:** events, timeSpent, type. **Unit:** percent.

**Zero-day rule:** Not a duration; empty denominator is a gap.

**Trend:** Lower is improving under the shared relative rule.

**Healthy reference:** Below 20%.

**N/A and edge cases:** Insufficient time spent: Fewer than 20% of filtered allocation role records have positive time spent, or no records exist. The shared real-Sprint no-period condition also applies. The top Issue Type filter is applied to both numerator and denominator records during rendering; with the default defect-only selection, other work is filtered out of the denominator. Selecting other types can admit their already-derived denominator records without adding numerator records. Stored issue totals are assigned to the completion period, not individual worklog dates.

**Dimensions:** Project, Team, Component, Epic, Person and Time; issue detail is available through drilldown.

### Time in QA (`qa`)

**Phase and aggregation:** Testing; avg. **Default types:** Story, Task, Defect, Sub-bug.

**What it measures and derivation:** Average whole days between the first qaEntry and first qaExit transition, bucketed at qaExit.

**Jira data:** events. **Unit:** days.

**Zero-day rule:** Nonpositive and under-one-whole-day intervals are excluded.

**Trend:** Lower is improving under the shared relative rule.

**Healthy reference:** Less than 14 days.

**N/A and edge cases:** No metric-specific reason; an empty denominator or absent eligible items can leave a gap or hide the average. The shared real-Sprint no-period condition also applies. An exit preceding entry is excluded.

**Dimensions:** Project, Team, Component, Epic, Person and Time; issue detail is available through drilldown.

### Defect Escape Rate (Review → QA) (`escapereview`)

**Phase and aggregation:** Review; rate. **Default types:** Defect, Sub-bug.

**What it measures and derivation:** Divide issues with the configured QA label by the union carrying QA or review label, times 100, by creation date.

**Jira data:** created, labels. **Unit:** percent.

**Zero-day rule:** Not a duration; empty denominator is a gap.

**Trend:** Lower is improving under the shared relative rule.

**Healthy reference:** None.

**N/A and edge cases:** Unconfigured labels: Either label is empty.; Equal labels: Configured labels compare equal ignoring case.; No derived items: The global derived escapereview array is empty; the message mentions the current window, but the check is global. The shared real-Sprint no-period condition also applies. Both labels must be nonempty and different ignoring case; matching uses the label token rule.

**Dimensions:** Project, Team, Component, Epic, Person and Time; issue detail is available through drilldown.

### Clarification Cycle Count (`clarcycle`)

**Phase and aggregation:** Requirements; avg. **Default types:** Story, Task.

**What it measures and derivation:** Count returns to refinement before the first devStart transition; the initial refinement entry is free. Average counts for started items by devStart.

**Jira data:** events. **Unit:** cycles.

**Zero-day rule:** Not a duration; zero cycles are included.

**Trend:** Lower is improving under the shared relative rule.

**Healthy reference:** At most 2 cycles.

**N/A and edge cases:** No metric-specific reason; an empty denominator or absent eligible items can leave a gap or hide the average. The shared real-Sprint no-period condition also applies. Items with no devStart do not contribute. Derivation uses the shared devStart set directly rather than the stored start/end anchor specifications; returnTo is used.

**Dimensions:** Project, Team, Component, Epic, Person and Time; issue detail is available through drilldown.

### Review Cycle Count (`reviewcycle`)

**Phase and aggregation:** Review; avg. **Default types:** Story, Task, Defect, Sub-bug.

**What it measures and derivation:** For currently done items, count review-status entries through the last done transition minus one; average by last done.

**Jira data:** status, events. **Unit:** cycles.

**Zero-day rule:** Not a duration; a single review contributes zero.

**Trend:** Lower is improving under the shared relative rule.

**Healthy reference:** At most 2 cycles.

**N/A and edge cases:** Review statuses absent: The review status set is empty. The shared real-Sprint no-period condition also applies. Items with no review entry or no last done event are excluded; review statuses may be auto-seeded.

**Dimensions:** Project, Team, Component, Epic, Person and Time; issue detail is available through drilldown.

## 8. N/A states reference

Messages below reproduce the reason text emitted by the widget. The shared Sprint condition can override a metric-specific conclusion. A gap, hidden average, unavailable delta or insufficient trend points is distinct from a metric-level N/A message.

| Metric | State | Reason text | Actual trigger |
| --- | --- | --- | --- |
| all | No usable Jira sprint periods | no usable Jira sprint periods in this selection. | Real Sprint is selected and no eligible usable periods survive selection. |
| backlog | Ready status absent | No ready status present in the project history. Assign the status that marks a story/task as ready to start in the Backlog Health metric settings (Ready status selector, set: ready). | No configured ready status appears in current status or captured history. |
| backlog | Forced SP ready side | the forced Story-Point coverage cannot be computed — the ready side carries no story points in the window | Forced velocity_sp and no positive SP on participating ready items. |
| backlog | Forced SP completed side | the forced Story-Point coverage cannot be computed — the completed velocity side carries no story points in the window | Forced velocity_sp, ready SP present, but no positive SP on qualifying completed velocity items. |
| designreview | Unconfigured statuses | Configure the design start and review done statuses in metric settings to enable this metric. | Either status is empty. |
| designreview | Equal statuses | Design start and review done must be different statuses — with the same status every interval is zero days. | Configured strings are identical. |
| designreview | No derived items | No items with both transitions in the current window. | The global derived designreview array is empty; the message mentions the current window, but the check is global. |
| velocity | Forced SP absent | no story points in the current window (forced SP state) | Forced sp mode with no qualifying positive story points in the filtered window. |
| defectdensity | Forced SP absent | no story points in the current window (forced SP-weighted mode) | Forced per_sp mode and no positive story points among denominator records in the filtered window. |
| bugfix | Insufficient time spent | the project does not log work time (timespent fill-rate < 20%). | Fewer than 20% of filtered allocation role records have positive time spent, or no records exist. |
| escapereview | Unconfigured labels | Configure the review and QA labels in metric settings to enable this metric. | Either label is empty. |
| escapereview | Equal labels | The review and QA labels must be different — with the same label the numerator equals the denominator. | Configured labels compare equal ignoring case. |
| escapereview | No derived items | No defects with the configured labels in the current window. | The global derived escapereview array is empty; the message mentions the current window, but the check is global. |
| reviewcycle | Review statuses absent | Configure at least one review status in widget settings to enable this metric. | The review status set is empty. |

WIP in per-developer mode has null control points when no assignee is present; its average is unavailable if no point is defined. Backlog Health shows zero placeholder bars when speed is zero but suppresses its verdict if no control point is computable. An empty metric type selection suppresses a verdict. A trend needs at least three defined completed points and the delta needs adjacent values with a nonzero previous value.

## 9. Data quality — absent-data behaviour

### Teams

Detect source and discovered fields or matching labels; unresolved values are grouped as Team is not defined. No metric-level N/A.

### Story points

Positive SP fill among selected velocity or density denominator items determines automatic mode at 50%; Backlog Health additionally checks both sides and Sprint availability. Automatic modes fall back to item counts. Forced unsupported modes produce the corresponding recorded reason.

### Worklog

The browser counts allocation role records with positive issue timeSpent; fewer than 20% or none produces the bugfix reason. Individual worklog rows are not used.

### Sprint data

Populated Sprint values determine the project-wide auto threshold. Below or equal to 50% uses calendar buckets; available forces Jira periods, with the shared N/A reason if none are usable.

### Review statuses

An empty review set gives the reviewcycle reason; generation may seed statuses containing review.

### Escape labels

Missing, equal, or globally absent matching labels give the respective escapereview reason; no fallback formula.

### Design statuses

Missing, equal, or globally absent derived intervals give the respective designreview reason; no fallback formula.

### Ready status

No configured ready status in captured history or current status yields the backlog reason. An item currently ready without an entry transition uses a clamped, unverified start.

## 10. Contract guarantees

1. Exactly 20 metrics are described in the actual widget order.

2. All metrics share one pipeline and have widget-level and metric-level settings only.

3. Each metric specifies its inputs, calculation, units, trend, guidance, missing-data behaviour and dimensions.

4. The reason table records emitted metric-level reasons and identifies shared or non-message gaps separately.

5. The interface is limited to the named Jira signals and widget scope.

## 11. Version and change log

**1.0.0 — 2026-11-11:** Initial contract aligned to the current Process Metrics – Trends widget implementation.
