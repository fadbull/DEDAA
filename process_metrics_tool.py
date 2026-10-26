#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
process_metrics_tool.py
=======================

A reusable tool that converts any Tab 2 "Process Metrics" widget into an
interactive trend chart and registers it in the combined widget
"Process Metrics - Trends" (the same combined widget that currently hosts
"Requirements Cycle Time" and "Requirements Rework Rate").

It captures the exact pattern used to convert "Requirements Rework Rate"
into "Requirements Rework Rate - Trend" and generalises it so ANY metric can
be added by declaring a small, declarative *metric spec*.

---------------------------------------------------------------------------
HOW THE EXISTING "REWORK RATE -> TREND" CONVERSION WORKS (the pattern)
---------------------------------------------------------------------------
For each metric we need FOUR pieces. This tool generates all four from one spec.

1) INPUT DATA  (per-issue items, computed in compute_jira() in analyze_agent.py)
   Each item is a flat dict with:
     - a numeric field used for aggregation (e.g. 'days' for cycle time,
       or 'reworked' 0/1 for rework)
     - a timestamp field 'dev_start' (ISO) used for period bucketing
     - dimension fields: 'project', 'team', 'epic', 'person', 'type'
   Example item (rework):
     {"key": "EPMRLCT-1453", "reworked": false,
      "dev_start": "2025-12-01T00:00:00", "period": "2025-W49-50",
      "project": "EPMRLCT", "team": "B_Run-Business",
      "epic": "No Epic", "person": "d@epam.com", "type": "Task"}

2) PROCESSING  (JS aggregation in rcApply())
   - Filter items by custom From/To date range (if set).
   - Filter by dimension multi-select (project/team/epic/person).
   - Bucket by 2-week period (rcPeriKey) using dev_start.
   - Aggregate per period:
        * 'avg'    -> mean of a numeric field (e.g. cycle days)
        * 'rate'   -> (count_true / total) * 100  (e.g. rework %)
        * 'sum'    -> sum of a numeric field
        * 'count'  -> number of items
   - Show the last N periods (Periods select maps 2w->1,1m->2,3m->5,6m->13,1y->26).
   - Linear regression for the trend line + conclusion (Improving/Stable/Degrading).

3) OUTPUT DATA  (chart rendering)
   - Chart.js line chart on the shared canvas with a trend line overlay.
   - Y-axis title, axis note, dataset label/color, conclusion threshold.

4) EMBEDDING  (registration in the combined widget)
   - A <button id="rcM-<metric>"> in the left metric list.
   - A tooltip entry in RC_TIP (switches with the selected metric).
   - A data variable (e.g. RR_ITEMS) serialised into the JS.
   - The metric-driven branch in rcApply() (rcActiveItems + aggregation).

---------------------------------------------------------------------------
USAGE
---------------------------------------------------------------------------
    from process_metrics_tool import MetricSpec, register_metric, generate_all

    spec = MetricSpec(
        id="cycle",                          # unique id (used for button id)
        label="Requirements Cycle Time",      # button label
        units="avg days",                     # for axis/labels
        aggregation="avg",                    # avg | rate | sum | count
        value_field="days",                   # numeric field on each item
        color="#2563eb",                      # chart line color
        y_axis="Requirements Cycle Time (days)",
        axis_note="Y-axis: Requirements Cycle Time (days) · X-axis: period ...",
        tooltip="...",                        # info tooltip (switches on click)
        trend_threshold=0.05,                 # slope threshold for conclusion
        y_min=None, y_max=None,               # optional fixed Y range
    )
    # Register (adds to the combined widget's metric list + JS + compute template)
    register_metric(spec)

    # Print the Python compute block + JS registration + HTML button to embed:
    print(generate_all())

The tool prints ready-to-paste snippets; a `--apply` mode can patch
analyze_agent.py automatically (see APPLY mode at the bottom).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Metric registry
# ---------------------------------------------------------------------------
METRICS: List["MetricSpec"] = []


class MetricSpec:
    """Declarative description of one trend metric.

    Attributes mirror exactly the fields the combined widget needs.
    """

    def __init__(
        self,
        id: str,
        label: str,
        aggregation: str = "avg",          # avg | rate | sum | count
        value_field: str = "days",         # numeric field on each item
        units: str = "avg days",
        color: str = "#2563eb",
        y_axis: str = "",
        axis_note: str = "",
        tooltip: str = "",
        trend_threshold: float = 0.05,
        y_min: Optional[float] = None,
        y_max: Optional[float] = None,
        # Python compute snippet: function(meta, docs) -> list[dict items]
        # The default builds an item from metadata only; for metrics needing
        # status-history parsing (like rework) provide `compute_py`.
        compute_py: Optional[str] = None,
        data_var: str = "",                # JS variable name, e.g. RR_ITEMS
    ):
        self.id = id
        self.label = label
        self.aggregation = aggregation
        self.value_field = value_field
        self.units = units
        self.color = color
        self.y_axis = y_axis or f"{label} ({units})"
        self.axis_note = axis_note or (
            f"Y-axis: {self.y_axis} · X-axis: period (sprint / 2-week bucket). "
            "Default shows the last 5 periods with project activity.")
        self.tooltip = tooltip
        self.trend_threshold = trend_threshold
        self.y_min = y_min
        self.y_max = y_max
        self.compute_py = compute_py
        self.data_var = data_var or f"{id.upper()}_ITEMS"

    # -- helpers ---------------------------------------------------------
    @property
    def button_id(self) -> str:
        return f"rcM-{self.id}"

    @property
    def is_rate(self) -> bool:
        return self.aggregation == "rate"


def register_metric(spec: MetricSpec) -> None:
    """Add a metric to the registry (deduplicates by id)."""
    for i, m in enumerate(METRICS):
        if m.id == spec.id:
            METRICS[i] = spec
            return
    METRICS.append(spec)


# ---------------------------------------------------------------------------
# 1) GENERATE: Python compute block (per-issue items) for analyze_agent.py
# ---------------------------------------------------------------------------
_DEFAULT_COMPUTE = '''    # --- Metric: {label} (per-issue items for the interactive chart) ---
    {id}_items = []
    for m in meta:
        # (customise the filter / value computation here)
        {id}_items.append({{
            "key": m.get("issue_key", ""),
            "{value_field}": <value>,
            "dev_start": <dev_start_iso>,
            "period": _biweek(<dev_start_dt>),
            "project": m.get("project") or "Unknown",
            "team": <team>,
            "epic": m.get("parent_key") or "No Epic",
            "person": m.get("assignee") or "Unassigned",
            "type": m.get("type") or "Unknown",
        }})
    # add to jm return dict:
    #   "{id}_items": {id}_items,
'''


def gen_compute_block(spec: MetricSpec) -> str:
    """Return the Python compute snippet to paste into compute_jira()."""
    if spec.compute_py:
        return spec.compute_py
    return _DEFAULT_COMPUTE.format(
        id=spec.id, label=spec.label, value_field=spec.value_field)


# ---------------------------------------------------------------------------
# 2) GENERATE: JS registration (data var + tooltip + button wiring)
# ---------------------------------------------------------------------------
def gen_js_data_var(spec: MetricSpec) -> str:
    """Return the JS line declaring the metric's data variable."""
    return (
        f'var {spec.data_var} = """ + _json.dumps(jm.get("{spec.id}_items") '
        f'or []) + """;'
    )


def gen_js_tooltip_entry(spec: MetricSpec) -> str:
    """Return the RC_TIP entry (escaped for embedding into the JS object)."""
    tip = spec.tooltip.replace("\\", "\\\\").replace('"', '\\"')
    return f'  {spec.id}: "{tip}",'


def gen_js_button(spec: MetricSpec) -> str:
    """Return the <button> HTML for the left metric list."""
    return (
        f'<button onclick="rcSetMetric(\'{spec.id}\')" '
        f'id="{spec.button_id}" '
        f'class="block w-full text-left px-3 py-2 mb-2 rounded border text-sm">'
        f'{spec.label}</button>'
    )


# ---------------------------------------------------------------------------
# 3) GENERATE: metric-driven aggregation branch in rcApply()
# ---------------------------------------------------------------------------
def gen_js_aggregation_branch(spec: MetricSpec) -> str:
    """Return the JS snippet for the aggregation branch inside rcApply().

    Must be inserted where the current code does:
        var isRework = rcMetric==='rework';
        ... if(isRework){...} else {...}
    This tool's snippet replaces that hard-coded pair with a data-driven
    lookup so the SAME rcApply() handles any registered metric.
    """
    agg = spec.aggregation
    if agg == "rate":
        body = (
            "if(!agg[key]) agg[key]={n:0,total:0};\n"
            "      agg[key].total++;\n"
            f"      if(it.{spec.value_field}) agg[key].n++;"
        )
        value = (
            "var a=agg[p]; return a.total ? (a.n/a.total*100) : null;"
        )
    elif agg == "avg":
        body = (
            f"if(!agg[key]) agg[key]=[];\n"
            f"      agg[key].push(it.{spec.value_field});"
        )
        value = (
            "var a=agg[p]; return a.reduce(function(s,v){return s+v;},0)/a.length;"
        )
    elif agg == "sum":
        body = (
            f"if(!agg[key]) agg[key]=0;\n"
            f"      agg[key]+=it.{spec.value_field};"
        )
        value = "return agg[p]||0;"
    elif agg == "count":
        body = "if(!agg[key]) agg[key]=0; agg[key]++;"
        value = "return agg[p]||0;"
    else:
        raise ValueError(f"Unknown aggregation: {agg}")

    return (
        "if(rcMetric==='" + spec.id + "'){\n"
        "      " + body + "\n"
        "    } else {\n"
        "      if(!agg[key]) agg[key]=[];\n"
        "      agg[key].push(it.days);\n"
        "    }"
    )


def gen_js_metric_config(spec: MetricSpec) -> str:
    """Return the JS config object entries for this metric (label,color,etc)."""
    return (
        f"  {spec.id}: {{label:'{spec.label} ({spec.units})', "
        f"color:'{spec.color}', y_axis:'{spec.y_axis}', "
        f"axis_note:'{spec.axis_note}', threshold:{spec.trend_threshold}, "
        f"y_min:{spec.y_min if spec.y_min is not None else 'null'}, "
        f"y_max:{spec.y_max if spec.y_max is not None else 'null'}, "
        f"aggregation:'{spec.aggregation}'}},"
    )


# ---------------------------------------------------------------------------
# 3b) GENERATE: a fully data-driven rcApply() that works for ANY metric
# ---------------------------------------------------------------------------
def gen_generic_rcapply() -> str:
    """Return a drop-in replacement for the metric-driven rcApply() that reads
    everything (aggregation, label, color, axis, threshold) from a RC_CFG
    object, so adding a new metric requires ONLY a RC_CFG entry + a data var
    + a button — no editing of the aggregation branch.

    Paste this into the JS replacing the current rcApply(), and add the
    RC_CFG entries from gen_js_metric_config().
    """
    return r'''function rcAggValue(agg, a){
  if(!a) return null;
  if(agg==='rate') return a.total ? (a.n/a.total*100) : null;
  if(agg==='sum')  return a;
  if(agg==='count') return a;
  // avg
  return a.reduce(function(s,v){return s+v;},0)/a.length;
}
function rcApply(){
  var fromInput=document.getElementById('rcFrom').value;
  var toInput=document.getElementById('rcTo').value;
  var hasCustom = fromInput || toInput;
  var from=null, to=null;
  if(fromInput&&toInput){ from=new Date(fromInput+'T00:00:00'); to=new Date(toInput+'T23:59:59'); }
  else if(fromInput){ from=new Date(fromInput+'T00:00:00'); to=null; }
  else if(toInput){ from=null; to=new Date(toInput+'T23:59:59'); }
  var dim=document.getElementById('rcDim').value;
  var sel=rcSelected();
  var cfg=RC_CFG[rcMetric];
  var items=rcActiveItems();
  var agg=cfg.aggregation;
  var bucket={};
  items.forEach(function(it){
    var t=new Date(it.dev_start);
    if(from&&t<from) return;
    if(to&&t>to) return;
    if(sel && !sel[it[dim]]) return;
    var key=rcPeriKey(t);
    if(agg==='rate'){
      if(!bucket[key]) bucket[key]={n:0,total:0};
      bucket[key].total++;
      if(it[cfg.field]) bucket[key].n++;
    } else if(agg==='avg'){
      if(!bucket[key]) bucket[key]=[];
      bucket[key].push(it[cfg.field]);
    } else if(agg==='sum'){
      if(!bucket[key]) bucket[key]=0;
      bucket[key]+=it[cfg.field];
    } else { // count
      if(!bucket[key]) bucket[key]=0;
      bucket[key]++;
    }
  });
  var periods=Object.keys(bucket).sort();
  if(!hasCustom){
    var p=document.getElementById('rcPeriods').value;
    var n={ '2w':1, '1m':2, '3m':5, '6m':13, '1y':26 }[p]||5;
    periods=periods.slice(-n);
  }
  var labels=periods, values=periods.map(function(p){ return rcAggValue(agg, bucket[p]); });
  var trend=rcLinearTrend(values.map(function(v){ return v===null?0:v; }));
  var datasets=[
    {label:cfg.label, data:values, borderColor:cfg.color,
     backgroundColor:cfg.color+'33', fill:true, tension:0.3,
     pointRadius:4, pointBackgroundColor:cfg.color}
  ];
  if(trend){ datasets.push({label:'Trend', data:trend.line, borderColor:'#ef4444',
    borderDash:[6,4], fill:false, tension:0, pointRadius:0}); }
  var conclEl=document.getElementById('rcConclusion');
  if(trend&&trend.slope!==null){
    var thr=cfg.threshold||0.05;
    var c = trend.slope < -thr ? '🟢 Improving' : (trend.slope > thr ? '🔴 Degrading' : '🟡 Stable');
    conclEl.textContent = c;
  } else { conclEl.textContent = ''; }
  var note=document.getElementById('rcAxisNote');
  if(note){ note.textContent = cfg.axis_note; }
  if(rcChart){ rcChart.destroy(); }
  var ctx=document.getElementById('rcChart');
  if(!ctx) return;
  var yOpts={title:{display:true,text:cfg.y_axis}};
  if(cfg.y_min!==null&&cfg.y_min!==undefined){ yOpts.suggestedMin=cfg.y_min; }
  if(cfg.y_max!==null&&cfg.y_max!==undefined){ yOpts.suggestedMax=cfg.y_max; }
  rcChart=new Chart(ctx,{type:'line',data:{labels:labels,datasets:datasets},
    options:{responsive:true,maintainAspectRatio:false,
      scales:{y:yOpts, x:{title:{display:true,text:'Period (sprint / 2-week)'}}},
      plugins:{legend:{position:'bottom'}}}});
}
rcSetMetric('cycle');'''


# ---------------------------------------------------------------------------
# 4) GENERATE: full combined-widget embedding (all metrics at once)
# ---------------------------------------------------------------------------
def generate_all() -> Dict[str, str]:
    """Return all generated snippets keyed by destination.

    Returns:
        {
          "compute":  Python compute blocks (paste into compute_jira()),
          "js_data":  JS data-var declarations,
          "js_tip":   RC_TIP entries,
          "js_config": RC_CFG entries (metric config),
          "js_buttons": HTML buttons for the left metric list,
        }
    """
    return {
        "compute": "\n".join(gen_compute_block(m) for m in METRICS),
        "js_data": "\n".join(gen_js_data_var(m) for m in METRICS),
        "js_tip": "\n".join(gen_js_tooltip_entry(m) for m in METRICS),
        "js_config": "\n".join(gen_js_metric_config(m) for m in METRICS),
        "js_buttons": "\n".join(gen_js_button(m) for m in METRICS),
        "rcapply": gen_generic_rcapply(),
    }


# ---------------------------------------------------------------------------
# Example specs (the two already in the combined widget)
# ---------------------------------------------------------------------------
def _demo_specs():
    register_metric(MetricSpec(
        id="cycle", label="Requirements Cycle Time", units="avg days",
        aggregation="avg", value_field="days", color="#2563eb",
        y_axis="Requirements Cycle Time (days)",
        trend_threshold=0.05,
        tooltip=("Requirements Cycle Time (created → entering development) per "
                 "period. avg(In Progress − Created) for Story/Task."),
    ))
    register_metric(MetricSpec(
        id="rework", label="Requirements Rework Rate", units="%",
        aggregation="rate", value_field="reworked", color="#7c3aed",
        y_axis="Requirements Rework Rate (%)",
        trend_threshold=0.1, y_min=0, y_max=100,
        tooltip=("Requirements Rework Rate (% of stories returning to "
                 "requirements/refinement after dev started)."),
    ))
    # Example of adding a brand-new Tab 2 metric: "Lead Time".
    # (value_field 'lead_days' must be populated in the compute block.)
    register_metric(MetricSpec(
        id="lead", label="Lead Time", units="avg days",
        aggregation="avg", value_field="lead_days", color="#0ea5e9",
        y_axis="Lead Time (days)",
        trend_threshold=0.05,
        tooltip=("Lead Time (created → done) per period. avg(Done − Created) "
                 "for Story/Task. Total lifetime incl. queue wait."),
    ))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--metric", action="append", default=[],
                   help="Metric id to generate (repeatable); default = all demo")
    p.add_argument("--list", action="store_true", help="List registered metrics")
    p.add_argument("--json", action="store_true",
                   help="Emit generated snippets as JSON")
    p.add_argument("--rcapply", action="store_true",
                   help="Also print the fully data-driven rcApply() replacement")
    p.add_argument("--sample-leadtime", action="store_true",
                   help="Generate only the 'Lead Time' example metric")
    args = p.parse_args()

    _demo_specs()
    if args.sample_leadtime:
        METRICS[:] = [m for m in METRICS if m.id == "lead"]
    if args.list:
        for m in METRICS:
            print(f"{m.id:12s} {m.label}  (agg={m.aggregation}, var={m.data_var})")
        return

    if args.metric:
        keep = {x for x in args.metric}
        METRICS[:] = [m for m in METRICS if m.id in keep]

    out = generate_all()
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    print("#" * 70)
    print("# 1) PYTHON COMPUTE BLOCK  (paste into compute_jira() in analyze_agent.py)")
    print("#" * 70)
    print(out["compute"])
    print()
    print("#" * 70)
    print("# 2) JS DATA VARIABLES  (paste near 'var RC_ITEMS = ...')")
    print("#" * 70)
    print(out["js_data"])
    print()
    print("#" * 70)
    print("# 3) JS TOOLTIP ENTRIES  (add into the RC_TIP object)")
    print("#" * 70)
    print(out["js_tip"])
    print()
    print("#" * 70)
    print("# 4) JS METRIC CONFIG  (add into the RC_CFG object)")
    print("#" * 70)
    print(out["js_config"])
    print()
    print("#" * 70)
    print("# 5) HTML BUTTONS  (add to the left metric list)")
    print("#" * 70)
    print(out["js_buttons"])
    if args.rcapply:
        print()
        print("#" * 70)
        print("# 6) DATA-DRIVEN rcApply()  (replaces the metric-driven rcApply();")
        print("#     needs RC_CFG + a data var per metric — no more editing")
        print("#     the aggregation branch when adding a metric)")
        print("#" * 70)
        print(out["rcapply"])


if __name__ == "__main__":
    main()
