"""<script> part 1: Tab switcher, Tab 2 charts, Tab 3 charts, OLAP."""
from ..dashboard_helpers import js_list


def build_scripts_part1(jm, cfd_weeks, cfd_done, cfd_ip, cfd_backlog,
                        week2_labels, opened2, resolved2, velocity2,
                        scope_change2, week_labels, bug_new, bug_res,
                        trend_js, tis_js, module1_js, module3_js,
                        cl_dist_js, olap_rows_json, olap_link_rows_json):
    return ("""
<script>
function switchTab(n){
  document.getElementById('tab1').classList.toggle('active', n===1);
  document.getElementById('tab2').classList.toggle('active', n===2);
  document.getElementById('tab3').classList.toggle('active', n===3);
  document.getElementById('tab1btn').classList.toggle('active', n===1);
  document.getElementById('tab2btn').classList.toggle('active', n===2);
  document.getElementById('tab3btn').classList.toggle('active', n===3);
  // refresh charts when shown
  if(n===2){ setTimeout(()=>{ Object.values(Chart.instances||{}).forEach(c=>c.resize()); }, 50); }
  // render mermaid diagrams when tab 3 is shown (only unprocessed ones)
  if(n===3 && window.mermaid){
    setTimeout(()=>{
      var nodes = Array.prototype.filter.call(document.querySelectorAll('#tab3 .mermaid'),
        function(el){ return !el.getAttribute('data-processed'); });
      if(nodes.length){ mermaid.run({ nodes: nodes }); }
    }, 50);
  }
}
document.querySelectorAll('.sidebar-link').forEach(a=>{
  a.addEventListener('click', ()=>{ document.querySelectorAll('.sidebar-link').forEach(x=>x.classList.remove('active')); a.classList.add('active'); });
});

// [CFD] The static CFD chart was replaced by the interactive cfdApply()
// (Periods / calendar / dimensions / issue types / band settings) which
// renders into the same #cfdChart canvas from the RC_RAW status timelines
// during the widget boot chain (see chart_render.py).

// [P15] The static Opened vs Resolved / Throughput / Velocity widgets were
// removed — the interactive Process Metrics - Trends widget (rcM-flow /
// rcM-throughput / rcM-velocity) is the single source of truth for them.

// Scope Change Volume (changed Story/Task/Bug per 2-week period)
new Chart(document.getElementById('scopeChangeChart'), { type:'bar', data:{
  labels:""" + week2_labels + """,
  datasets:[{label:'Changed issues', data:""" + scope_change2 + """, backgroundColor:'#f59e0b'}]
  }, options:{responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}} });

// Bug growth
new Chart(document.getElementById('bugChart'), { type:'line', data:{
  labels:""" + week_labels + """,
  datasets:[
    {label:'New Bugs', data:""" + bug_new + """, borderColor:'#ef4444'},
    {label:'Resolved Bugs', data:""" + bug_res + """, borderColor:'#10b981'}
  ]}, options:{responsive:true, maintainAspectRatio:false, plugins:{legend:{position:'bottom'}}} });

// Open bugs by priority
new Chart(document.getElementById('bugPrioChart'), { type:'doughnut', data:{
  labels:""" + js_list(list(jm["open_bug_by_prio"].keys())) + """,
  datasets:[{data:""" + js_list(list(jm["open_bug_by_prio"].values())) + """, backgroundColor:['#ef4444','#f59e0b','#2563eb','#94a3b8']}]
  }, options:{responsive:true, maintainAspectRatio:false, plugins:{legend:{position:'bottom'}}} });

// ---- Tab 3: Field fill-rate trend charts ----
""" + trend_js + """
// ---- Tab 3: Time-in-Status charts ----
""" + tis_js + """
// ---- Tab 3: Event-Driven Analytics charts ----
""" + module1_js + """
""" + module3_js + """
// ---- Tab 3: Jira Cross-Linkage & SDLC Waste charts ----
""" + cl_dist_js + """
// ---- Tab 3: OLAP Slice & Dice constructor ----
var OLAP_ROWS = """ + olap_rows_json + """;
var OLAP_PAGE_SIZE = 200, olapPageIndex = 0, olapLinkPageIndex = 0;
function olapEscape(value){
  return String(value).replace(/[&<>"']/g, function(c){
    return {'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c];
  });
}
function olapSetPagination(prefix, page, total){
  var start = total ? page * OLAP_PAGE_SIZE + 1 : 0;
  var end = Math.min((page + 1) * OLAP_PAGE_SIZE, total);
  document.getElementById(prefix + 'Prev').disabled = page === 0;
  document.getElementById(prefix + 'Next').disabled = end >= total;
  return ' · showing ' + start + '–' + end + ' of ' + total + ' slices';
}
function olapDistinct(rows, dim){
  var seen = new Set(); var out = [];
  rows.forEach(function(r){
    var values = dim === 'component' ? r.components : [r[dim]];
    values.forEach(function(v){ if(v && !seen.has(v)){ seen.add(v); out.push(v); } });
  });
  return out.sort();
}
function olapFillSelect(id, dim){
  var sel = document.getElementById(id);
  var cur = sel.value;
  sel.innerHTML = '<option value="">All</option>';
  olapDistinct(OLAP_ROWS, dim).forEach(function(v){
    var o = document.createElement('option'); o.value = v; o.text = v;
    if(v === cur){ o.selected = true; }
    sel.appendChild(o);
  });
}
function olapApply(keepPage){
  if(keepPage !== true) olapPageIndex = 0;
  var f = {};
  f.type = document.getElementById('olapType').value;
  f.assignee = document.getElementById('olapAssignee').value;
  f.priority = document.getElementById('olapPriority').value;
  f.status = document.getElementById('olapStatus').value;
  f.component = document.getElementById('olapComponent').value;
  // filter rows
  var filtered = OLAP_ROWS.filter(function(r){
    return (!f.type || r.type === f.type) &&
           (!f.assignee || r.assignee === f.assignee) &&
           (!f.priority || r.priority === f.priority) &&
           (!f.status || r.status === f.status) &&
           (!f.component || r.components.indexOf(f.component) !== -1);
  });
  // aggregate by (type, assignee, priority, status, component)
  var agg = Object.create(null);
  filtered.forEach(function(r){
    r.components.filter(function(c){ return !f.component || c === f.component; }).forEach(function(component){
      var key = JSON.stringify([r.type, r.assignee, r.priority, r.status, component]);
      if(!agg[key]){ agg[key] = {type:r.type, assignee:r.assignee, priority:r.priority,
        status:r.status, component:component, count:0, lifeSum:0, lifeN:0}; }
      agg[key].count++;
      if(r.life !== null && r.life !== undefined){ agg[key].lifeSum += r.life; agg[key].lifeN++; }
    });
  });
  var rows = Object.keys(agg).map(function(k){ return agg[k]; });
  rows.sort(function(a,b){ return b.count - a.count || JSON.stringify(a).localeCompare(JSON.stringify(b)); });
  olapPageIndex = Math.min(olapPageIndex, Math.max(0, Math.ceil(rows.length / OLAP_PAGE_SIZE) - 1));
  var body = document.getElementById('olapBody');
  if(!rows.length){
    body.innerHTML = '<tr><td colspan="7" class="py-4 text-gray-400">N/A — no issues match the selected slice</td></tr>';
  } else {
    body.innerHTML = rows.slice(olapPageIndex * OLAP_PAGE_SIZE, (olapPageIndex + 1) * OLAP_PAGE_SIZE).map(function(r){
      var avg = r.lifeN ? (r.lifeSum/r.lifeN).toFixed(1) : 'N/A';
      return "<tr><td class='py-1'>"+olapEscape(r.type)+"</td><td class='py-1'>"+olapEscape(r.assignee)+
        "</td><td class='py-1'>"+olapEscape(r.priority)+"</td><td class='py-1'>"+olapEscape(r.status)+
        "</td><td class='py-1'>"+olapEscape(r.component)+"</td><td class='py-1 font-medium'>"+r.count+
        "</td><td class='py-1'>"+avg+"</td></tr>";
    }).join('');
  }
  document.getElementById('olapSummary').textContent =
    rows.length + " slice(s) · " + filtered.length + " unique issue(s) match the current filter" +
    olapSetPagination('olap', olapPageIndex, rows.length);
}
function olapPage(delta){ olapPageIndex += delta; olapApply(true); }
// populate dimension dropdowns + first render
olapFillSelect('olapType', 'type');
olapFillSelect('olapAssignee', 'assignee');
olapFillSelect('olapPriority', 'priority');
olapFillSelect('olapStatus', 'status');
olapFillSelect('olapComponent', 'component');
olapApply();

// ---- Tab 3: Issue-Links OLAP Slice & Dice constructor ----
var OLAP_LINK_ROWS = """ + olap_link_rows_json + """;
function olapLinkDistinct(dim){
  var seen = new Set(); var out = [];
  OLAP_LINK_ROWS.forEach(function(r){ var v = r[dim]||''; if(v && !seen.has(v)){ seen.add(v); out.push(v); } });
  return out.sort();
}
function olapLinkFillSelect(id, dim){
  var sel = document.getElementById(id);
  var cur = sel.value;
  sel.innerHTML = '<option value="">All</option>';
  olapLinkDistinct(dim).forEach(function(v){
    var o = document.createElement('option'); o.value = v; o.text = v;
    if(v === cur){ o.selected = true; }
    sel.appendChild(o);
  });
}
function olapLinkApply(keepPage){
  if(keepPage !== true) olapLinkPageIndex = 0;
  var f = {};
  f.link_type = document.getElementById('olapLinkType').value;
  f.direction = document.getElementById('olapLinkDir').value;
  f.source_type = document.getElementById('olapLinkSType').value;
  f.target_type = document.getElementById('olapLinkTType').value;
  f.source_status = document.getElementById('olapLinkSStatus').value;
  f.target_status = document.getElementById('olapLinkTStatus').value;
  // filter rows
  var filtered = OLAP_LINK_ROWS.filter(function(r){
    return (!f.link_type || r.link_type === f.link_type) &&
           (!f.direction || r.direction === f.direction) &&
           (!f.source_type || r.source_type === f.source_type) &&
           (!f.target_type || r.target_type === f.target_type) &&
           (!f.source_status || r.source_status === f.source_status) &&
           (!f.target_status || r.target_status === f.target_status);
  });
  // aggregate by (link_type, direction, source_type, target_type, source_status, target_status)
  var agg = Object.create(null);
  filtered.forEach(function(r){
    var key = JSON.stringify([r.link_type, r.direction, r.source_type, r.target_type, r.source_status, r.target_status]);
    if(!agg[key]){ agg[key] = {link_type:r.link_type, direction:r.direction,
      source_type:r.source_type, target_type:r.target_type, source_status:r.source_status,
      target_status:r.target_status, count:0}; }
    agg[key].count++;
  });
  var rows = Object.keys(agg).map(function(k){ return agg[k]; });
  rows.sort(function(a,b){ return b.count - a.count || JSON.stringify(a).localeCompare(JSON.stringify(b)); });
  olapLinkPageIndex = Math.min(olapLinkPageIndex, Math.max(0, Math.ceil(rows.length / OLAP_PAGE_SIZE) - 1));
  var body = document.getElementById('olapLinkBody');
  if(!rows.length){
    body.innerHTML = '<tr><td colspan="7" class="py-4 text-gray-400">N/A — no links match the selected slice</td></tr>';
  } else {
    body.innerHTML = rows.slice(olapLinkPageIndex * OLAP_PAGE_SIZE, (olapLinkPageIndex + 1) * OLAP_PAGE_SIZE).map(function(r){
      return "<tr><td class='py-1'>"+olapEscape(r.link_type)+"</td><td class='py-1'>"+olapEscape(r.direction)+
        "</td><td class='py-1'>"+olapEscape(r.source_type)+
        "</td><td class='py-1'>"+olapEscape(r.target_type)+"</td><td class='py-1'>"+olapEscape(r.source_status)+
        "</td><td class='py-1'>"+olapEscape(r.target_status)+"</td><td class='py-1 font-medium'>"+r.count+
        "</td></tr>";
    }).join('');
  }
  document.getElementById('olapLinkSummary').textContent =
    rows.length + " slice(s) · " + filtered.length + " link record(s) match the current filter" +
    olapSetPagination('olapLink', olapLinkPageIndex, rows.length);
}
function olapLinkPage(delta){ olapLinkPageIndex += delta; olapLinkApply(true); }
// ---- Process Metrics - Trends interactive charts (data-driven) ----
var PM_DATA = {
""")
