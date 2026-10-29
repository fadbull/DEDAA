"""Dashboard HTML shell: ctx unpacking + head / Tab 1 / Tab 2 assembly.

The final HTML is assembled from the pre-computed fragments (ctx) plus
the JS fragment modules (scripts_tab3, trends_data, derive, settings,
chart config / granularity / render). Fragment text is byte-identical
to the pre-split monolith.
"""
from ..dashboard_helpers import esc, js_list, _tip
from . import scripts_tab3, trends_data, derive, settings_widget, \
    settings_metric, chart_config, granularity, chart_render


def _render_html_shell(ctx):
    """Assemble the final dashboard HTML from pre-computed fragments."""
    # (extracted from build_dashboard for maintainability)
    import json as _json
    import json as _event_json
    jm = ctx['jm']
    artifacts = ctx['artifacts']
    done = ctx['done']
    opened = ctx['opened']
    resolved = ctx['resolved']
    total = ctx['total']
    velocity = ctx['velocity']
    weeks = ctx['weeks']
    module3_js = ctx['module3_js']
    tab1_assets_mtime = ctx['tab1_assets_mtime']
    tab1_assets_size_mb = ctx['tab1_assets_size_mb']
    tab1_total_size_mb = ctx['tab1_total_size_mb']
    tab2_total_size_mb = ctx['tab2_total_size_mb']
    aging_rows = ctx['aging_rows']
    artifact_sections = ctx['artifact_sections']
    avg_cycle = ctx['avg_cycle']
    avg_lead = ctx['avg_lead']
    avg_velocity2 = ctx['avg_velocity2']
    bug_new = ctx['bug_new']
    bug_res = ctx['bug_res']
    cap_rows = ctx['cap_rows']
    cfd_backlog = ctx['cfd_backlog']
    cfd_chart_html = ctx['cfd_chart_html']
    cfd_done = ctx['cfd_done']
    cfd_ip = ctx['cfd_ip']
    cfd_weeks = ctx['cfd_weeks']
    cl_dist_js = ctx['cl_dist_js']
    control_chart_html = ctx['control_chart_html']
    db_path = ctx['db_path']
    db_size_mb = ctx['db_size_mb']
    defect_age_rows = ctx['defect_age_rows']
    epic_report_html = ctx['epic_report_html']
    forecast_chart_html = ctx['forecast_chart_html']
    link_caps = ctx['link_caps']
    link_kt = ctx['link_kt']
    link_vision = ctx['link_vision']
    module1_js = ctx['module1_js']
    olap_link_rows_json = ctx['olap_link_rows_json']
    olap_rows_json = ctx['olap_rows_json']
    opened2 = ctx['opened2']
    jql_links = ctx['jql_links']
    problem = ctx['problem']
    ready_count = ctx['ready_count']
    ready_rows = ctx['ready_rows']
    resolved2 = ctx['resolved2']
    scope_change2 = ctx['scope_change2']
    scope_change_html = ctx['scope_change_html']
    sprint_report_html = ctx['sprint_report_html']
    tab1_folder_label = ctx['tab1_folder_label']
    tab1_ts = ctx['tab1_ts']
    tab2_ts = ctx['tab2_ts']
    tab3_html = ctx['tab3_html']
    tis_js = ctx['tis_js']
    trend_js = ctx['trend_js']
    value_prop = ctx['value_prop']
    velocity2 = ctx['velocity2']
    velocity_chart_html = ctx['velocity_chart_html']
    vision = ctx['vision']
    week2_labels = ctx['week2_labels']
    week_labels = ctx['week_labels']
    page_images_html = ctx['page_images_html']

    html = ("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Product Intelligence Dashboard — EPMRLCT</title>
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script>
  document.addEventListener("DOMContentLoaded", function(){
    if (window.mermaid) { mermaid.initialize({ startOnLoad:false, theme:'neutral', securityLevel:'loose' }); }
  });
</script>
<style>
  .nav-btn.active { background:#2563eb; color:#fff; }
  .sidebar-link.active { background:#e2e8f0; color:#0f172a; font-weight:600; }
  .widget { border:1px solid #e2e8f0; border-radius:12px; padding:16px; background:#fff; }
  .na-box { display:flex; align-items:center; justify-content:center; height:180px; color:#94a3b8; font-size:1.2rem; border:1px dashed #cbd5e1; border-radius:8px; }
  .tab-panel { display:none; }
  .tab-panel.active { display:block; }
  /* ---- Info-icon hover tooltips (Tab 3) ---- */
  .tip-wrap { position:relative; display:inline-flex; align-items:center; margin-left:6px; vertical-align:middle; }
  .tip-icon { display:inline-flex; align-items:center; justify-content:center; width:16px; height:16px; font-size:12px; line-height:1; border-radius:50%; background:#e2e8f0; color:#475569; cursor:help; }
  .tip-box { visibility:hidden; opacity:0; position:absolute; top:calc(100% + 8px); left:0; z-index:60; width:260px; padding:10px 12px; background:#0f172a; color:#e2e8f0; font-size:11px; line-height:1.5; font-weight:400; border-radius:8px; box-shadow:0 8px 20px rgba(0,0,0,0.25); text-align:left; transition:opacity .15s ease; pointer-events:none; }
  .tip-wrap[data-align="right"] .tip-box { left:auto; right:0; }
  .tip-box::before { content:""; position:absolute; bottom:100%; left:12px; border:6px solid transparent; border-bottom-color:#0f172a; }
  .tip-wrap[data-align="right"] .tip-box::before { left:auto; right:12px; }
  .tip-wrap:hover .tip-box { visibility:visible; opacity:1; }
</style>
</head>
<body class="bg-gray-50 font-sans text-gray-900">
<header class="bg-white shadow-sm sticky top-0 z-30">
  <div class="max-w-7xl mx-auto px-4 py-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
    <div>
      <h1 class="text-xl font-bold">Product Intelligence Dashboard</h1>
      <p class="text-sm text-gray-500">EPMRLCT · Auto-generated by Zoo Code Skill #2</p>
      <p class="text-xs text-gray-400 font-mono mt-1">Chroma DB: <span class="text-gray-600">""" + esc(db_path) + """</span> · Folder size: <span class="text-gray-600">""" + str(db_size_mb) + """ MB</span></p>
    </div>
    <div class="flex gap-2 flex-wrap">
      <button id="tab1btn" onclick="switchTab(1)" class="nav-btn px-4 py-2 rounded-lg bg-gray-100 text-sm font-medium">🧠 Product Info</button>
      <button id="tab2btn" onclick="switchTab(2)" class="nav-btn px-4 py-2 rounded-lg bg-gray-100 text-sm font-medium">📊 Process Metrics</button>
      <button id="tab3btn" onclick="switchTab(3)" class="nav-btn px-4 py-2 rounded-lg bg-gray-100 text-sm font-medium">🧬 Jira Data Profile</button>
    </div>
  </div>
</header>

<div class="max-w-7xl mx-auto px-4 py-6">
<!-- ================= TAB 1 ================= -->
<div id="tab1" class="tab-panel active">
  <div class="widget mb-4 text-xs text-gray-500 font-mono">
    <strong class="text-gray-700">Data source (Tab 1):</strong> Chroma DB: <span class="text-gray-600">""" + esc(db_path) + """</span> · Collection: <span class="text-gray-600">product_knowledge</span> · Folder: <span class="text-gray-600">""" + esc(tab1_folder_label) + """</span> · Size: <span class="text-gray-600">""" + (f"{tab1_total_size_mb} MB" if tab1_total_size_mb is not None else "n/a") + """</span> · Assets: <span class="text-gray-600">""" + (f"{tab1_assets_size_mb} MB" if tab1_assets_size_mb is not None else "n/a") + """</span> · Last update: <span class="text-gray-600">""" + tab1_ts + """</span> · Assets updated: <span class="text-gray-600">""" + tab1_assets_mtime + """</span>
  </div>
  <div class="flex gap-6">
    <nav class="w-56 shrink-0 hidden md:block">
      <div class="sticky top-20 space-y-1 text-sm">
        <a href="#s-strategy" class="sidebar-link block px-3 py-2 rounded-lg">1. Strategy</a>
        <a href="#s-architecture" class="sidebar-link block px-3 py-2 rounded-lg">2. Architecture</a>
        <a href="#s-requirements" class="sidebar-link block px-3 py-2 rounded-lg">3. Requirements</a>
        <a href="#s-artifacts" class="sidebar-link block px-3 py-2 rounded-lg">4. Found Artifacts</a>
      </div>
    </nav>
    <div class="flex-1 space-y-8">
      <section id="s-strategy" class="scroll-mt-24">
        <h2 class="text-lg font-semibold mb-3">1. Strategy — Executive Product Vision</h2>
        <div class="widget space-y-2">
          <p><strong>Product:</strong> IMR (Internal Mobility Request) — Part of Opportunities.epam.com</p>
          <p><strong>Core Value Proposition:</strong> """ + (esc(value_prop) or "N/A") + """</p>
          <p><strong>Problem Statement:</strong> """ + (esc(problem) or "N/A") + """</p>
          <p><strong>Vision:</strong> """ + (esc(vision) or "N/A") + """</p>
          <p><em>Source: """ + link_vision + """</em></p>
        </div>
      </section>

      <section id="s-architecture" class="scroll-mt-24">
        <h2 class="text-lg font-semibold mb-3">2. Architecture — Modules & Integrations</h2>
        <div class="widget">
          <p class="text-gray-500">Architecture blueprint is captured in the KT: Delivery page (C4 model: context/container/component/deployment views) and the linked architecture pages (Cloud Infrastructure, Integrations, Branching Strategy, Data Hub, Observability, External Resources).</p>
          <p class="mt-2"><em>Source: """ + link_kt + """</em></p>
          """ + (page_images_html("KT: Delivery")
                 + page_images_html("Cloud Infrastructure")
                 + page_images_html("Integrations")
                 + page_images_html("[BE] Branching Strategy")
                 + page_images_html("Data Hub Integration")
                 + page_images_html("Observability")
                 + page_images_html("External Resources")) + """
        </div>
      </section>

      <section id="s-requirements" class="scroll-mt-24">
        <h2 class="text-lg font-semibold mb-3">3. Requirements — Product Capabilities</h2>
        <div class="widget">
          <table class="w-full text-sm"><thead><tr class="text-left border-b"><th class="py-2">Capability</th><th>Description</th></tr></thead><tbody>""" + cap_rows + """</tbody></table>
          <p class="mt-2"><em>Source: """ + link_caps + """</em></p>
          """ + page_images_html("Product capabilities register") + """
        </div>
      </section>

      <section id="s-artifacts" class="scroll-mt-24">
        <h2 class="text-lg font-semibold mb-3">4. Found Artifacts</h2>
        <p class="text-xs text-gray-500 mb-3">All valuable artifacts (metrics, tools, success criteria, capabilities, stakeholders, links, team contacts) autonomously extracted from the Confluence pages in the <span class="font-mono">product_knowledge</span> collection — each with a direct link to its source document. No AI inference or gap assumptions are made.</p>
        <div class="grid md:grid-cols-2 gap-4">
          """ + artifact_sections + """
        </div>
      </section>
    </div>
  </div>
</div>

<!-- ================= TAB 2 ================= -->
<div id="tab2" class="tab-panel">
  <div class="widget mb-4 text-xs text-gray-500 font-mono">
    <strong class="text-gray-700">Data source (Tab 2):</strong> Chroma DB: <span class="text-gray-600">""" + esc(db_path) + """</span> · Collections: <span class="text-gray-600">product_jira + product_jira_reports</span> · Size: <span class="text-gray-600">""" + (f"{tab2_total_size_mb} MB" if tab2_total_size_mb is not None else "n/a") + """</span> · Last update: <span class="text-gray-600">""" + tab2_ts + """</span>
  </div>
  <div class="flex gap-6">
    <nav class="w-56 shrink-0 hidden md:block">
      <div class="sticky top-20 space-y-1 text-sm">
        <a href="#m-delivery" class="sidebar-link block px-3 py-2 rounded-lg">Delivery</a>
        <a href="#m-scope" class="sidebar-link block px-3 py-2 rounded-lg">Scope & Predictability</a>
        <a href="#m-quality" class="sidebar-link block px-3 py-2 rounded-lg">Quality & Tech Debt</a>
        <a href="#m-reports" class="sidebar-link block px-3 py-2 rounded-lg">Project Jira Reports</a>
      </div>
    </nav>
    <div class="flex-1 space-y-8">

      <section id="m-delivery" class="scroll-mt-24">
        <h2 class="text-lg font-semibold mb-3">Delivery""" + _tip("Delivery health at a glance: work-in-progress flow (CFD) and how long work takes to actually complete (Cycle Time) vs its total lifetime (Lead Time) — see the Process Metrics - Trends widget below.") + """</h2>
        <div class="grid md:grid-cols-2 gap-4">
          <div class="widget md:col-span-2">
            <div class="flex items-center justify-between mb-2">
              <h3 class="font-medium mb-0">Cumulative Flow Diagram""" + _tip("A stacked area chart of Backlog, In Progress and Done over time. The vertical gap between adjacent bands is the work-in-progress (WIP); a widening band signals congestion, while a narrowing one signals flow. Flat 'In Progress' band = work is queued, not being done. Use the controls below to slice the diagram by period, calendar range, dimension and issue type.") + """</h3>
              <button onclick="cfdSettingsToggle()" class="text-gray-400 hover:text-gray-600" title="CFD settings">⚙</button>
            </div>
            <div id="cfdSettingsPanel" class="hidden mb-2 p-3 border rounded bg-gray-50">
              <div class="text-xs font-semibold text-gray-500 uppercase mb-1">CFD settings</div>
              <div class="flex flex-wrap gap-3 text-xs items-center">
                <span class="text-gray-500">Bands:</span>
                <label class="inline-flex items-center gap-1"><input type="checkbox" id="cfdBand_backlog" checked onchange="cfdMarkPending()"> Backlog</label>
                <label class="inline-flex items-center gap-1"><input type="checkbox" id="cfdBand_ip" checked>In Progress</label>
                <label class="inline-flex items-center gap-1"><input type="checkbox" id="cfdBand_done" checked> Done</label>
                <span class="text-gray-400">Status groups come from Widget settings (Trends gear → Widget settings → Workflow statuses).</span>
                <button onclick="cfdApply()" class="px-2 py-1 rounded bg-blue-600 text-white text-xs">Apply</button>
              </div>
            </div>
            <div class="flex flex-wrap items-center gap-3 mb-2 text-sm">
              <label class="flex items-center gap-1">Periods
                <select id="cfdPeriods" onchange="cfdPeriodsChanged()" class="border rounded px-2 py-1 text-sm">
                  <option value="daily">Daily</option>
                  <option value="weekly">Weekly</option>
                  <option value="sprint" selected>Sprint (2 weeks)</option>
                  <option value="monthly">Monthly</option>
                  <option value="quarterly">Quarterly</option>
                  <option value="annual">Annual</option>
                </select>
              </label>
              <label class="flex items-center gap-1">From
                <input type="date" id="cfdFrom" onchange="cfdCalTouched=true;cfdMarkPending()" class="border rounded px-2 py-1 text-sm">
              </label>
              <label class="flex items-center gap-1">To
                <input type="date" id="cfdTo" onchange="cfdCalTouched=true;cfdMarkPending()" class="border rounded px-2 py-1 text-sm">
              </label>
              <label class="flex items-center gap-1">Dimensions
                <select id="cfdDim" onchange="cfdPopulateDim();cfdMarkPending()" class="border rounded px-2 py-1 text-sm">
                  <option value="project">Project (default)</option>
                  <option value="team">Team</option>
                  <option value="component">Component</option>
                  <option value="epic">Epic</option>
                  <option value="person">Person</option>
                  <option value="issuetype">Issue Type</option>
                </select>
              </label>
              <label class="flex items-center gap-1">Select (multi)
                <span id="cfdDimWrap" class="inline-flex flex-wrap gap-2 items-center"></span>
              </label>
              <label class="flex items-center gap-1">Issue Type (multi)
                <span id="cfdTypeWrap" class="inline-flex flex-wrap gap-2 items-center"></span>
              </label>
              <button id="cfdApplyBtn" onclick="cfdApply()" class="px-3 py-1 rounded bg-blue-600 text-white text-sm">Apply</button>
              <span id="cfdPending" class="hidden text-xs text-amber-600 font-medium">· pending changes</span>
            </div>
            <div id="cfdDimList" class="flex flex-wrap gap-2 mb-2 text-sm"></div>
            <div class="h-64"><canvas id="cfdChart"></canvas></div>
            <p id="cfdAxisNote" class="text-xs text-gray-500 mt-1">Stacked areas: Backlog / In Progress / Done at each period end. X-axis: sprint buckets · Default: last 5 periods with project activity.</p>
          </div>
          <!-- [P8] The duplicate flowChart widget (a second canvas with the
               same id) is removed — Chart.js initialized only the first one,
               the duplicate stayed empty. -->
          <!-- [P8] The static snapshot cards (Cycle Time / Requirements
               Cycle Time / Lead Time) are removed: they were generated once
               at report build time, ignored every filter and disagreed with
               the dynamic Trends widget below — the single source of truth
               for these metrics now. -->
          <div class="widget md:col-span-2 relative"><h3 class="font-medium mb-2 flex items-center justify-between"><span class="inline-flex items-center gap-1">Process Metrics - Trends<span id="rcTipBox"></span></span><span class="inline-flex items-center gap-3 text-sm"><button onclick="rcWidgetSettingsToggle()" title="Widget settings" class="inline-flex items-center gap-1 text-gray-500 hover:text-gray-800 leading-none"><span class="text-lg">&#9881;</span>Widget settings</button><button onclick="rcSettingsToggle()" title="Metrics settings" aria-label="Metrics settings" class="text-gray-400 hover:text-gray-700 leading-none"><span class="text-lg">&#9881;</span>Metrics settings</button></span></h3>
            <!-- Widget settings slide-over panel (shared, cross-metric) -->
            <div id="rcWidgetSettingsPanel" class="hidden fixed inset-y-0 right-0 w-[26rem] max-w-full bg-white border-l shadow-xl z-50 overflow-y-auto">
              <div class="flex items-center justify-between px-4 py-3 border-b sticky top-0 bg-white">
                <span class="font-semibold text-sm">Widget settings</span>
                <button onclick="rcWidgetSettingsClose()" class="text-gray-400 hover:text-gray-600 text-xl leading-none" aria-label="Close">&times;</button>
              </div>
              <div id="rcWidgetSettingsBody" class="px-4 py-2"></div>
              <div class="sticky bottom-0 bg-white border-t px-4 py-3 flex flex-wrap gap-2">
                <button onclick="rcWidgetSettingsApply()" class="px-3 py-1.5 rounded bg-blue-600 text-white text-sm">Apply</button>
                <button onclick="rcWidgetSettingsReset()" class="px-3 py-1.5 rounded border text-sm">Reset to defaults</button>
                <button onclick="rcWidgetSettingsExport()" class="px-3 py-1.5 rounded border text-sm">Export JSON</button>
                <button onclick="rcWidgetSettingsImport()" class="px-3 py-1.5 rounded border text-sm">Import</button>
                <span class="text-xs text-gray-400 self-center ml-auto">Shared across all metrics</span>
              </div>
            </div>
            <!-- Metric settings slide-over panel -->
            <div id="rcSettingsPanel" class="hidden fixed inset-y-0 right-0 w-[26rem] max-w-full bg-white border-l shadow-xl z-50 overflow-y-auto">
              <div class="flex items-center justify-between px-4 py-3 border-b sticky top-0 bg-white">
                <span class="font-semibold text-sm">Metrics settings</span>
                <button onclick="rcSettingsClose()" class="text-gray-400 hover:text-gray-600 text-xl leading-none" aria-label="Close">&times;</button>
              </div>
              <div id="rcSettingsBody" class="px-4 py-2"></div>
              <div class="sticky bottom-0 bg-white border-t px-4 py-3 flex flex-wrap gap-2">
                <button onclick="rcSettingsApply()" class="px-3 py-1.5 rounded bg-blue-600 text-white text-sm">Apply</button>
                <button onclick="rcSettingsReset()" class="px-3 py-1.5 rounded border text-sm">Reset to defaults</button>
                <button onclick="rcSettingsExport()" class="px-3 py-1.5 rounded border text-sm">Export JSON</button>
                <button onclick="rcSettingsImport()" class="px-3 py-1.5 rounded border text-sm">Import</button>
                <span class="text-xs text-gray-400 self-center ml-auto">Applies to Trends + used on regeneration via --metric-settings</span>
              </div>
            </div>
            <div class="flex flex-wrap md:flex-nowrap gap-4">
              <div class="w-full md:w-56 shrink-0">
                <div class="text-xs font-semibold text-gray-500 mb-2">Metric</div>
                <button onclick="rcSetMetric('cycle')" id="rcM-cycle" class="block w-full text-left px-3 py-2 mb-2 rounded border text-sm">Requirements Cycle Time</button>
                <button onclick="rcSetMetric('rework')" id="rcM-rework" class="block w-full text-left px-3 py-2 mb-2 rounded border text-sm">Requirements Rework Rate</button>
                <button onclick="rcSetMetric('backlog')" id="rcM-backlog" class="block w-full text-left px-3 py-2 mb-2 rounded border text-sm">Backlog Health</button>
                <button onclick="rcSetMetric('designreview')" id="rcM-designreview" class="block w-full text-left px-3 py-2 mb-2 rounded border text-sm">Design Review Turnaround</button>
                <button onclick="rcSetMetric('flow')" id="rcM-flow" class="block w-full text-left px-3 py-2 mb-2 rounded border text-sm">Opened vs Resolved</button>
                <button onclick="rcSetMetric('cycletime')" id="rcM-cycletime" class="block w-full text-left px-3 py-2 mb-2 rounded border text-sm">Cycle Time</button>
                <button onclick="rcSetMetric('lead')" id="rcM-lead" class="block w-full text-left px-3 py-2 mb-2 rounded border text-sm">Issue Lead Time (avg days)</button>
                <button onclick="rcSetMetric('velocity')" id="rcM-velocity" class="block w-full text-left px-3 py-2 mb-2 rounded border text-sm">Issue Velocity (completed items per period)</button>
                <button onclick="rcSetMetric('throughput')" id="rcM-throughput" class="block w-full text-left px-3 py-2 mb-2 rounded border text-sm">Throughput</button>
                <button onclick="rcSetMetric('wip')" id="rcM-wip" class="block w-full text-left px-3 py-2 mb-2 rounded border text-sm">Work in Progress</button>
                <button onclick="rcSetMetric('floweff')" id="rcM-floweff" class="block w-full text-left px-3 py-2 mb-2 rounded border text-sm">Flow Efficiency</button>
                <button onclick="rcSetMetric('leakage')" id="rcM-leakage" class="block w-full text-left px-3 py-2 mb-2 rounded border text-sm">Production Leakage Rate</button>
                <button onclick="rcSetMetric('defectdensity')" id="rcM-defectdensity" class="block w-full text-left px-3 py-2 mb-2 rounded border text-sm">Defect Density</button>
                <button onclick="rcSetMetric('incident')" id="rcM-incident" class="block w-full text-left px-3 py-2 mb-2 rounded border text-sm">Incident Frequency</button>
                <button onclick="rcSetMetric('bugflow')" id="rcM-bugflow" class="block w-full text-left px-3 py-2 mb-2 rounded border text-sm">Bug Growth (new vs resolved)</button>
                <button onclick="rcSetMetric('bugfix')" id="rcM-bugfix" class="block w-full text-left px-3 py-2 mb-2 rounded border text-sm">Bug Fixing Time Allocation</button>
                <button onclick="rcSetMetric('qa')" id="rcM-qa" class="block w-full text-left px-3 py-2 mb-2 rounded border text-sm">Time in QA</button>
                <button onclick="rcSetMetric('escapereview')" id="rcM-escapereview" class="block w-full text-left px-3 py-2 mb-2 rounded border text-sm">Defect Escape Rate (Review → QA)</button>
                <button onclick="rcSetMetric('clarcycle')" id="rcM-clarcycle" class="block w-full text-left px-3 py-2 mb-2 rounded border text-sm">Clarification Cycle Count</button>
                <button onclick="rcSetMetric('reviewcycle')" id="rcM-reviewcycle" class="block w-full text-left px-3 py-2 mb-2 rounded border text-sm">Review Cycle Count</button>
              </div>
              <div class="w-full">
                <div class="flex flex-wrap items-center gap-3 mb-3 text-sm">
                  <label class="flex items-center gap-1">Periods
                    <select id="rcPeriods" onchange="rcPeriodsChanged()" class="border rounded px-2 py-1 text-sm">
                      <option value="daily">Daily</option>
                      <option value="weekly">Weekly</option>
                      <option value="sprint" selected>Sprint (2 weeks)</option>
                      <option value="monthly">Monthly</option>
                      <option value="quarterly">Quarterly</option>
                      <option value="annual">Annual</option>
                    </select>
                  </label>
                  <label class="flex items-center gap-1">From
                    <input type="date" id="rcFrom" onchange="rcCalTouchedSet();rcCalTouched=true;rcMarkPending()" class="border rounded px-2 py-1 text-sm">
                  </label>
                  <label class="flex items-center gap-1">To
                    <input type="date" id="rcTo" onchange="rcCalTouchedSet();rcMarkPending()" class="border rounded px-2 py-1 text-sm">
                  </label>
                  <label class="flex items-center gap-1">Dimensions
                    <select id="rcDim" onchange="rcPopulateDim();rcMarkPending()" class="border rounded px-2 py-1 text-sm">
                      <option value="project">Project (default)</option>
                      <option value="team">Team</option>
                      <option value="component">Component</option>
                      <option value="epic">Epic</option>
                      <option value="person">Person</option>
                      <option value="issuetype">Issue Type</option>
                    </select>
                  </label>
                  <label class="flex items-center gap-1">Select (multi)
                    <span id="rcDimWrap" class="inline-flex flex-wrap gap-2 items-center"></span>
                  </label>
                  <label class="flex items-center gap-1">Issue Type (multi)
                    <span id="rcTypeWrap" class="inline-flex flex-wrap gap-2 items-center"></span>
                  </label>
                  <button id="rcApplyBtn" onclick="rcApply()" class="px-3 py-1 rounded bg-blue-600 text-white text-sm">Apply</button>
                  <span id="rcConclusion" class="ml-auto font-medium text-sm"></span>
                </div>
                <!-- Weighted average over the selected window (top-right, under the trend conclusion) -->
                <div class="flex justify-end mb-2">
                  <span id="rcAvgBox" class="hidden font-semibold text-sm px-3 py-1.5 rounded border border-blue-200 bg-blue-50 text-blue-800"></span>
                </div>
                <div id="rcDimList" class="flex flex-wrap gap-2 mb-2 text-sm"></div>
                <div class="h-80"><canvas id="rcChart"></canvas></div>
                <p id="rcAxisNote" class="text-xs text-gray-500 mt-1">Y-axis: Requirements Cycle Time (days) · X-axis: period (sprint / 2-week bucket). Default shows the last 5 periods with project activity.</p>
                <!-- Issues participating in the current calculation -->
                <div class="mt-3">
                  <div class="flex items-center justify-between mb-1">
                    <div class="text-xs font-semibold text-gray-500">Issues in calculation</div>
                    <div id="rcTblCount" class="text-xs text-gray-500"></div>
                  </div>
                  <div class="overflow-auto border rounded" style="max-height:26rem;">
                    <table class="w-full text-sm">
                      <thead class="sticky top-0 bg-gray-50 text-xs text-gray-600">
                        <tr>
                          <th class="py-1.5 px-2 text-left cursor-pointer select-none" onclick="rcSortTable('id')">ID</th>
                          <th class="py-1.5 px-2 text-left cursor-pointer select-none" onclick="rcSortTable('type')">Issue Type</th>
                          <th class="py-1.5 px-2 text-left cursor-pointer select-none" onclick="rcSortTable('summary')">Issue</th>
                          <th class="py-1.5 px-2 text-left cursor-pointer select-none" onclick="rcSortTable('status')">Status</th>
                          <th class="py-1.5 px-2 text-left cursor-pointer select-none" onclick="rcSortTable('created')">Created</th>
                          <th class="py-1.5 px-2 text-left cursor-pointer select-none" onclick="rcSortTable('updated')">Updated</th>
                          <th class="py-1.5 px-2 text-left cursor-pointer select-none" onclick="rcSortTable('days_in_status')">Days in Status</th>
                        </tr>
                      </thead>
                      <tbody id="rcTableBody"></tbody>
                    </table>
                  </div>
                  <div class="flex items-center justify-between mt-1">
                    <span id="rcPageInfo" class="text-xs text-gray-500"></span>
                    <span>
                      <button onclick="rcPage(-1)" id="rcPrevBtn" class="px-2 py-0.5 border rounded text-xs">Prev</button>
                      <button onclick="rcPage(1)" id="rcNextBtn" class="px-3 py-0.5 border rounded text-xs">Next</button>
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="m-scope" class="scroll-mt-24">
        <h2 class="text-lg font-semibold mb-3">Scope & Predictability""" + _tip("How predictable the delivery pipeline is: scope-change churn and aging work. Together these reveal whether delivery is stable or slipping.") + """</h2>
        <div class="grid md:grid-cols-2 gap-4">
          <div class="widget"><h3 class="font-medium mb-2">Sprint Scope Stability""" + _tip("How stable committed sprint scope is (added vs removed items). High instability means the team commits to work that is later dropped or expanded mid-sprint — a predictability risk.") + """</h3><div class="na-box">N/A (no sprints)</div></div>
          <div class="widget md:col-span-2"><h3 class="font-medium mb-2">Scope Change Volume by 2-week period (changed issues)""" + _tip("Per-period count of issues (Story/Task/Bug) that changed status AT LEAST ONCE — ANY transition (New→Open, Open→In Progress, In Progress→Resolved, ...). This is a BROAD 'churn' metric: it counts every issue that moved, including normal forward progress. Spikes show periods of heavy rework/scope drift; a flat low line reflects a stable pipeline. DIFFERENCE vs Requirements Rework Rate: Scope Change counts ALL status changes (any direction), while Rework Rate counts ONLY returns to requirements/refinement (New/Open/To Do/Backlog/Reopened/Analysis/Design/Ready for Dev) AFTER dev started. So Scope Change is always larger — it is a volume of movement, not a rate of rework.") + """</h3><div class="h-48"><canvas id="scopeChangeChart"></canvas></div></div>
          <div class="widget"><h3 class="font-medium mb-2">Top Areas / Components (work)""" + _tip("Where the work is concentrated: the top 12 components by issue count. Helps spot overloaded areas and understand the shape of the delivery portfolio.") + """</h3>
            <table class="w-full text-sm"><thead><tr class="text-left border-b"><th class="py-2">Component</th><th>Issues</th></tr></thead><tbody>
            """ + ("".join(f"<tr><td>{esc(k)}</td><td>{v}</td></tr>" for k, v in list(jm.get('by_component', {}).items())[:12]) or "<tr><td colspan='2'>N/A</td></tr>") + """</tbody></table></div>
          <div class="widget md:col-span-2"><h3 class="font-medium mb-2">Aging Issues (>30 days)""" + _tip("Issues that have stayed open for more than 30 days: key, summary, priority, current status, link and age in days (oldest first). Aging work is at risk of becoming stale, blocked, or forgotten — a candidate for escalation or de-scoping.") + """</h3>
            <table class="w-full text-sm"><thead><tr class="text-left border-b"><th class="py-2">Issue</th><th>Summary</th><th>Priority</th><th>Status</th><th>Link</th><th>Age</th></tr></thead><tbody>""" + aging_rows + """</tbody></table></div>
        </div>
        <div class="widget mt-4 md:col-span-2"><h3 class="font-medium mb-2">Ready for Development — Items""" + _tip("The actual list of issues sitting in 'Ready for Development': key, summary, priority and a link to each. This is the groomed, startable queue the team should pull from next.") + """</h3>
          <table class="w-full text-sm"><thead><tr class="text-left border-b"><th class="py-2">Issue</th><th>Summary</th><th>Priority</th><th>Link</th></tr></thead><tbody>""" + ready_rows + """</tbody></table>
        </div>
      </section>

      <section id="m-quality" class="scroll-mt-24">
        <h2 class="text-lg font-semibold mb-3">Quality & Technical Debt""" + _tip("The cost of quality: bug trends, defect aging, production leakage, and security findings. High values here erode velocity and inflate future maintenance.") + """</h2>
        <div class="grid md:grid-cols-2 gap-4">
          <div class="widget md:col-span-2"><h3 class="font-medium mb-2">Bug Growth (new vs resolved)""" + _tip("Compares new bugs opened vs bugs resolved over time (weekly). When new bugs outpace resolved, the defect backlog grows and quality is deteriorating.") + """</h3><div class="h-64"><canvas id="bugChart"></canvas></div></div>
          <div class="widget"><h3 class="font-medium mb-2">Open Bugs by Priority""" + _tip("Distribution of currently-open bugs across priority levels. A heavy high-priority slice means urgent defects are competing for capacity with planned work. The Jira link opens exactly the open defects counted here.") + """</h3>""" + jql_links.get("open_bugs", "") + """<div class="h-48"><canvas id="bugPrioChart"></canvas></div></div>
          <div class="widget"><h3 class="font-medium mb-2">Average Defect Age by Priority""" + _tip("For open bugs of each priority, how old they are on average (days since created). Critical/High defects aging for a long time signal that serious issues are being neglected. The Jira link opens exactly the open defects the age stats are computed from.") + """</h3>""" + jql_links.get("defect_age", "") + """
            <table class="w-full text-sm"><thead><tr class="text-left border-b"><th class="py-2">Priority</th><th>Count</th><th>Avg Age</th></tr></thead><tbody>""" + defect_age_rows + """</tbody></table></div>
          <div class="widget"><h3 class="font-medium mb-2">Production Leakage Rate""" + _tip("Bugs tagged 'Prod' indicate defects found in production (leaked past QA). The leakage rate = prod bugs ÷ total bugs × 100. A high rate means defects are escaping testing and reaching end users. The Jira link opens exactly the leaked (prod-tagged) defects.") + """</h3>""" + jql_links.get("leakage", "") + """
            <div class="na-box">""" + (
              f"{jm['defect_leakage_rate']:.1f}% leaked ({jm['prod_bugs']}/{jm['total_bugs']} prod bugs)"
              if jm.get('defect_leakage_rate') is not None else "N/A (no prod-tagged bugs)"
            ) + """</div></div>
          <div class="widget"><h3 class="font-medium mb-2">Security Posture (SAST/CWE)""" + _tip("SAST/CWE-labeled findings and open security issues. Counts the number of static-analysis findings, security-type issues, and how many remain open — a proxy for application security debt. The Jira link opens exactly the SAST/security issues counted here.") + """</h3>""" + jql_links.get("security", "") + """
            <div class="na-box">""" + (
              f"{jm.get('sast_issues', 0)} SAST/CWE findings · {jm.get('sec_type_issues', 0)} security issues ({jm.get('sec_open', 0)} open)"
              if jm.get('sast_issues') else "N/A (no SAST/security data)"
            ) + """</div></div>
          <div class="widget"><h3 class="font-medium mb-2">Security Findings by CWE""" + _tip("Security findings grouped by CWE (Common Weakness Enumeration) code. Grouping by CWE reveals which vulnerability classes recur most and should be fixed at the root. The Jira link opens exactly the CWE-labelled findings counted here.") + """</h3>""" + jql_links.get("cwe", "") + """
            <table class="w-full text-sm"><thead><tr class="text-left border-b"><th class="py-2">CWE</th><th>Count</th></tr></thead><tbody>
            """ + ("".join(f"<tr><td>{esc(k)}</td><td>{v}</td></tr>" for k, v in list(jm.get('cwe_by_code', {}).items())[:10]) or "<tr><td colspan='2'>N/A</td></tr>") + """</tbody></table></div>
        </div>
      </section>

      <section id="m-reports" class="scroll-mt-24">
        <h2 class="text-lg font-semibold mb-3">Project Jira Reports""" + _tip("Native Jira Agile/GreenHopper reports (Control Chart, Epic, Velocity, CFD, Scope Change, Forecast, Sprint) fetched from the Jira API and stored in the product_jira_reports Chroma collection. Reports the API does not expose for this project render N/A.") + """</h2>
        <p class="text-xs text-gray-500 mb-3">Reports fetched from the Jira Agile/GreenHopper API and stored in the <span class="font-mono">product_jira_reports</span> Chroma collection. Reports not available via the API for this project render <strong>N/A</strong>.</p>
        <div class="grid md:grid-cols-2 gap-4">
          <div class="widget"><h3 class="font-medium mb-2">Control Chart (cycle time)""" + _tip("Scatter/percentile chart of each completed issue's cycle time. The median and 85th-percentile lines help set realistic cycle-time expectations and spot outliers that took far longer than normal.") + """</h3><div class="overflow-x-auto">""" + control_chart_html + """</div></div>
          <div class="widget"><h3 class="font-medium mb-2">Epic Report""" + _tip("Progress of Epics: how many of their stories/issues are completed vs outstanding. Shows whether large bodies of work are on track or stalled.") + """</h3><div class="overflow-x-auto">""" + epic_report_html + """</div></div>
          <div class="widget"><h3 class="font-medium mb-2">Velocity Chart""" + _tip("Jira's velocity report: completed story points (or issue counts) per sprint, with the average. Used to calibrate how much the team can commit to in future sprints.") + """</h3><div class="overflow-x-auto">""" + velocity_chart_html + """</div></div>
          <div class="widget"><h3 class="font-medium mb-2">Cumulative Flow Diagram (report)""" + _tip("Jira's CFD: cumulative counts of issues across statuses over time. Band widths reveal WIP and cycle-time pressure per status.") + """</h3><div class="overflow-x-auto">""" + cfd_chart_html + """</div></div>
          <div class="widget"><h3 class="font-medium mb-2">Scope Change Chart""" + _tip("Jira's scope-change report: how much work was added to or removed from sprints after commitment. Large changes signal scope instability and reduce predictability.") + """</h3><div class="overflow-x-auto">""" + scope_change_html + """</div></div>
          <div class="widget"><h3 class="font-medium mb-2">Forecast Chart""" + _tip("Jira's forecast: projects how many sprints/iterations are needed to complete the remaining backlog based on observed velocity. A planning aid, not a guarantee.") + """</h3><div class="overflow-x-auto">""" + forecast_chart_html + """</div></div>
          <div class="widget"><h3 class="font-medium mb-2">Sprint Report""" + _tip("Details of each sprint: committed vs completed scope, start/end dates, and whether the sprint goal was met. Reveals completion rate and the gap between commitment and delivery.") + """</h3><div class="overflow-x-auto">""" + sprint_report_html + """</div></div>
        </div>
      </section>

    </div>
  </div>
</div>
</div>

""" + tab3_html
        + scripts_tab3.build_scripts_part1(
            jm, cfd_weeks, cfd_done, cfd_ip, cfd_backlog,
            week2_labels, opened2, resolved2, velocity2, scope_change2,
            week_labels, bug_new, bug_res, trend_js, tis_js,
            module1_js, module3_js, cl_dist_js, olap_rows_json,
            olap_link_rows_json)
        + trends_data.build_trends_data(jm, _json)
        + derive.DERIVE_JS
        + settings_widget.WIDGET_JS
        + settings_metric.SETTINGS_JS
        + chart_config.CONFIG_JS
        + granularity.GRAN_JS
        + chart_render.RENDER_JS)
    return html
