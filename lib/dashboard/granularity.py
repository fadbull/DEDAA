"""Time granularity helpers + filters + aggregation (JS)."""

GRAN_JS = """// ---- Time granularity (Periods select) --------------------------------
// daily | weekly | sprint (2-week bucket; Sprint fallback when Sprints are
// unavailable from Jira) | monthly | quarterly | annual.
var RC_GRAN_LABEL = {
  daily:'Day', weekly:'Week', sprint:'Sprint (2 weeks)',
  monthly:'Month', quarterly:'Quarter', annual:'Year'
};
// Default number of buckets shown when no calendar range is applied:
// ALWAYS the last 5 active periods, for every granularity (daily / weekly /
// sprint / monthly / quarterly / annual). Matches the widget spec: the
// project closed at end-2025, so "last 5 active sprints" is the natural
// default window. The per-metric defaultN setting (RC_SETTINGS_DEFAULT)
// takes precedence; this constant is only the last-resort fallback.
// [P9-P2-2] The per-granularity object (daily:1, weekly:1, …) was dead code
// that contradicted the spec — removed in favour of this single constant.
var RC_DEFAULT_N = 5;
// [P1-I10] «The user manually edited the calendar» is remembered PER
// METRIC (session scope): a metric the user never edited keeps syncing its
// own default window; a metric the user edited keeps its manual window.
// The old global flag is kept as a compatibility alias (read-only).
var rcCalTouchedMem={};
function rcCalTouchedCur(){ return !!rcCalTouchedMem[rcMetric]; }
function rcCalTouchedSet(){ rcCalTouchedMem[rcMetric]=true; }
function rcCalTouchedMemReset(){ rcCalTouchedMem={}; }
var rcCalTouched = false;

function rcPad2(v){ return String(v).padStart(2,'0'); }
function rcDateStr(d){
  return d.getFullYear()+'-'+rcPad2(d.getMonth()+1)+'-'+rcPad2(d.getDate());
}
function rcIsoWeekMonday(d){
  var t=new Date(d); t.setHours(0,0,0,0);
  t.setDate(t.getDate()-((t.getDay()+6)%7)); // Monday of the ISO week
  return t;
}
function rcIsoWeekNum(monday){
  var yr=monday.getFullYear();
  return Math.ceil((((monday-new Date(yr,0,1))/86400000)+1)/7);
}
// Monday that starts the 2-week (sprint) bucket containing d.
// Uses the SAME Thursday-based ISO week number as rcBucketKey so sprint
// boundaries stay consistent across ISO year boundaries (a naive
// Monday-based week number disagrees with ISO near Dec/Jan, which used to
// shift the default window by one sprint and drop the newest bucket's
// items from the chart).
function rcSprintStart(d){
  var mon=rcIsoWeekMonday(d);
  var thu=new Date(mon); thu.setDate(thu.getDate()+3); // Thursday of this ISO week
  var wk=Math.ceil((((thu-new Date(thu.getFullYear(),0,1))/86400000)+1)/7);
  if(wk%2===0) mon.setDate(mon.getDate()-7); // sprint starts on an odd ISO week
  return mon;
}
// Bucket key for a date at the given granularity. Keys sort chronologically.
function rcBucketKey(d, gran){
  var t=new Date(d); t.setHours(0,0,0,0);
  if(gran==='daily') return rcDateStr(t);
  if(gran==='weekly') return rcDateStr(rcIsoWeekMonday(t));
  if(gran==='monthly') return t.getFullYear()+'-'+rcPad2(t.getMonth()+1);
  if(gran==='quarterly') return t.getFullYear()+'-Q'+(Math.floor(t.getMonth()/3)+1);
  if(gran==='annual') return String(t.getFullYear());
  // sprint (default): 2-week ISO bucket (weeks 1-2, 3-4, ...)
  var tmp=new Date(t);
  tmp.setDate(tmp.getDate()+3-((tmp.getDay()+6)%7)); // Thursday of ISO week
  var w1=tmp.getFullYear();
  var wk=Math.ceil((((tmp-new Date(w1,0,1))/86400000)+1)/7);
  var bucket=((wk-1)>>1)*2+1;
  return w1+'-W'+String(bucket).padStart(2,'0')+'-'+String(bucket+1).padStart(2,'0');
}
// First bucket-start date of the bucket containing d.
function rcBucketStart(d, gran){
  var t=new Date(d); t.setHours(0,0,0,0);
  if(gran==='daily') return t;
  if(gran==='weekly') return rcIsoWeekMonday(t);
  if(gran==='sprint') return rcSprintStart(t);
  if(gran==='monthly') return new Date(t.getFullYear(), t.getMonth(), 1);
  if(gran==='quarterly') return new Date(t.getFullYear(), Math.floor(t.getMonth()/3)*3, 1);
  if(gran==='annual') return new Date(t.getFullYear(), 0, 1);
  return rcSprintStart(t);
}
// Generate ALL bucket keys covering [fromD .. toD] at the granularity.
function rcAxisRange(fromD, toD, gran){
  var keys=[], guard=0, cur=rcBucketStart(fromD, gran);
  var step = (gran==='daily')?1:(gran==='weekly')?7:(gran==='sprint')?14
            :(gran==='monthly')?1:(gran==='quarterly')?3:12;
  while(cur<=toD && guard<2000){
    keys.push(rcBucketKey(cur, gran));
    if(gran==='daily'||gran==='weekly'||gran==='sprint') cur.setDate(cur.getDate()+step);
    else if(gran==='annual') cur.setFullYear(cur.getFullYear()+step);
    else cur.setMonth(cur.getMonth()+step);
    guard++;
  }
  return keys;
}
// Legacy 2-week (sprint) bucket key — kept for compatibility.
function rcPeriKey(d){
  return rcBucketKey(d, 'sprint');
}
// End timestamp (last ms) of the bucket with key `key` at granularity
// `gran` — the Backlog Health snapshot control point.
function rcBucketEnd(key, gran){
  var y=parseInt(key.slice(0,4),10);
  if(gran==='daily'){
    var d=new Date(key+'T00:00:00'); d.setDate(d.getDate()+1);
    return d.getTime()-1;
  }
  if(gran==='weekly'){
    // ISO week key: YYYY-Wnn
    var wk=parseInt(key.split('-W')[1],10);
    var mon=rcIsoWeekMonday(new Date(Date.UTC(y,0,4)));
    mon.setUTCDate(mon.getUTCDate()+(wk-1)*7+7);
    return mon.getTime()-1;
  }
  if(gran==='sprint'){
    // sprint key: YYYY-Wnn-mm (two ISO weeks starting at week nn)
    var wk2=parseInt(key.split('-W')[1],10);
    var mon2=rcIsoWeekMonday(new Date(Date.UTC(y,0,4)));
    mon2.setUTCDate(mon2.getUTCDate()+(wk2-1)*7+14);
    return mon2.getTime()-1;
  }
  if(gran==='monthly'){ var m2=new Date(y, parseInt(key.slice(5),10), 1); return m2.getTime()-1; }
  if(gran==='quarterly'){ var q=parseInt(key.slice(6),10); return new Date(y, (q)*3, 1).getTime()-1; }
  if(gran==='annual'){ return new Date(y+1, 0, 1).getTime()-1; }
  return new Date(y, parseInt(key.slice(5),10), 1).getTime()-1;
}
// Default window (From/To dates) for a granularity, anchored at the last
// active date of the current metric's items.
function rcDefaultWindow(gran){
  var last=null;
  // [P1v3-1b] Backlog Health anchors on the READY side only: the latest
  // readiness start (readyFrom) among the ready population. Fallbacks:
  // latest creation among the metric's numerator types → latest creation
  // among all Jira items. The completion history is a denominator, not a
  // time reference for the axis.
  if(rcMetric==='backlog'){
    (PM_DATA.backlog||[]).forEach(function(it){
      var t=(it.readyFrom!==undefined&&it.readyFrom!==null)?new Date(it.readyFrom):new Date(it.dev_start);
      if(!isNaN(t) && (!last || t>last)) last=t;
    });
    if(!last){
      rcActiveItems().forEach(function(it){
        var t=new Date(it.dev_start);
        if(!isNaN(t) && (!last || t>last)) last=t;
      });
    }
    if(!last){
      (RC_RAW||[]).forEach(function(r){
        var t=r.created?new Date(r.created):null;
        if(!isNaN(t) && (!last || t>last)) last=t;
      });
    }
    if(!last || isNaN(last)) return null;
    last.setHours(0,0,0,0);
    var mEff0=((rcDraft||RC_SETTINGS).metrics||{})[rcMetric]||{};
    var N0=(mEff0.defaultN!==undefined&&mEff0.defaultN!==null)?mEff0.defaultN:5;
    var cur0=rcBucketStart(last, gran);
    var step0 = (gran==='daily')?1:(gran==='weekly')?7:(gran==='sprint')?14
              :(gran==='monthly')?1:(gran==='quarterly')?3:12;
    var from0=new Date(cur0);
    for(var i0=0;i0<N0-1;i0++){
      if(gran==='daily'||gran==='weekly'||gran==='sprint') from0.setDate(from0.getDate()-step0);
      else if(gran==='annual') from0.setFullYear(from0.getFullYear()-step0);
      else from0.setMonth(from0.getMonth()-step0);
    }
    var next0=new Date(cur0);
    if(gran==='daily'||gran==='weekly'||gran==='sprint') next0.setDate(next0.getDate()+step0);
    else if(gran==='annual') next0.setFullYear(next0.getFullYear()+step0);
    else next0.setMonth(next0.getMonth()+step0);
    var to0=new Date(next0); to0.setDate(to0.getDate()-1); to0.setHours(23,59,59,999);
    return {from:from0, to:to0};
  }
  // Anchor at the last active date of items that pass the metric's DEFAULT
  // type filter AND the currently applied Issue Type selection (so e.g.
  // "Opened vs Resolved" + Defect/Sub-bug filter anchors on the same data as
  // Bug Growth, keeping the two metrics comparable).
  // [P5-TP] The default window anchors on the metric's RUNTIME type pool
  // (rcTypesFor — aliases resolved), not the static display config.
  var defTypes=rcTypesFor(rcMetric);
  var typeSel=rcTypeSelected();
  var dim=document.getElementById('rcDim').value;
  var sel=rcSelected();
  rcActiveItems().forEach(function(it){
    if(defTypes.length && defTypes.indexOf(rcTypeLabel(it.type))<0) return;
    if(typeSel && !typeSel[rcTypeLabel(it.type)]) return;
    if(!rcDimMatch(it, dim, sel)) return;
    var t=new Date(it.dev_start);
    if(!isNaN(t) && (!last || t>last)) last=t;
  });
  if(!last || isNaN(last)) return null;
  last.setHours(0,0,0,0);
  // [P1-2] EVERY granularity defaults to the last N periods INCLUDING the
  // active one (N = the metric's saved defaultN, else 5). Previously only
  // sprint returned a 5-bucket window — daily/weekly/monthly/quarterly/
  // annual collapsed to the single active period, killing the trend view.
  var mEff=((rcDraft||RC_SETTINGS).metrics||{})[rcMetric]||{};
  var N=(mEff.defaultN!==undefined&&mEff.defaultN!==null)?mEff.defaultN:5;
  // Walk back to the bucket start of the OLDEST of the last N periods
  // (same step table as rcAxisRange).
  var cur=rcBucketStart(last, gran);
  var step = (gran==='daily')?1:(gran==='weekly')?7:(gran==='sprint')?14
            :(gran==='monthly')?1:(gran==='quarterly')?3:12;
  var from=new Date(cur);
  for(var i=0;i<N-1;i++){
    if(gran==='daily'||gran==='weekly'||gran==='sprint') from.setDate(from.getDate()-step);
    else if(gran==='annual') from.setFullYear(from.getFullYear()-step);
    else from.setMonth(from.getMonth()-step);
  }
  // To = the END of the active period (last ms of its last day).
  var next=new Date(cur);
  if(gran==='daily'||gran==='weekly'||gran==='sprint') next.setDate(next.getDate()+step);
  else if(gran==='annual') next.setFullYear(next.getFullYear()+step);
  else next.setMonth(next.getMonth()+step);
  var to=new Date(next); to.setDate(to.getDate()-1); to.setHours(23,59,59,999);
  return {from:from, to:to};
}
// Pre-fill the calendar inputs with the default window while the user has
// not manually edited them (default state per spec).
function rcSyncCalendar(){
  // [P1-I10] The flag is PER METRIC now; the global rcCalTouched stays as a
  // legacy fallback for callers that still read it.
  if(rcCalTouchedMem[rcMetric] || rcCalTouched) return;
  var gran=document.getElementById('rcPeriods').value || 'sprint';
  var w=rcDefaultWindow(gran);
  if(w){
    document.getElementById('rcFrom').value=rcDateStr(w.from);
    document.getElementById('rcTo').value=rcDateStr(w.to);
  }
}
function rcPeriodsChanged(){
  // Keep the calendar in sync with the default window of the selected
  // granularity until the user edits the dates manually. The chart is NOT
  // recalculated here — the user confirms the change with Apply (the same
  // applies to the Dimensions select and the multi-select checkboxes).
  rcSyncCalendar();
  rcMarkPending();
}
// Pending-change indicator: highlight Apply until the user confirms.
function rcMarkPending(){
  var b=document.getElementById('rcApplyBtn');
  if(b){ b.classList.add('ring-2','ring-blue-400'); }
}
function rcClearPending(){
  var b=document.getElementById('rcApplyBtn');
  if(b){ b.classList.remove('ring-2','ring-blue-400'); }
}
function rcLinearTrend(points){
  // Rule 1 — collect only valid points for the fit.
  var idx=[], valid=[];
  for(var i=0;i<points.length;i++){
    var v=points[i];
    if(v!==null && v!==undefined && !isNaN(v)){ idx.push(i); valid.push(v); }
  }
  // Empty series — no trend.
  if(valid.length<2) return null;
  // OLS over the valid points, using their REAL x positions.
  var n=valid.length;
  var sx=0,sy=0,sxy=0,sxx=0;
  for(var k=0;k<n;k++){
    var x=idx[k], y=valid[k];
    sx+=x; sy+=y; sxy+=x*y; sxx+=x*x;
  }
  var denom=n*sxx-sx*sx;
  if(!denom) return null;
  var slope=(n*sxy-sx*sy)/denom;
  var intercept=(sy - slope*sx)/n;
  // Rules 2 & 3 — null outside [first,last]; fitted value inside.
  var first=idx[0], last=idx[idx.length-1];
  return {
    slope: slope,
    line: points.map(function(_,i){
      if(i<first || i>last) return null;
      return Math.max(0, intercept + slope*i);
    })
  };
}
// An item's team(s), resolved LIVE from the widget-level teamConfig (so a
// source change in the settings takes effect immediately):
//   source=none   -> ["Team is not defined"]
//   source=field  -> the selected field's value (from `fieldvals` in the
//                    raw records, parsed from the issue document text)
//   source=labels -> EVERY selected label present on the issue
//                    (multi-membership); none matched -> undefined group.
// An item's team(s), resolved LIVE from the widget-level teamConfig (so a
// source change in the settings takes effect immediately):
//   source=none   -> ["Team is not defined"]
//   source=field  -> the selected field's value (from `fieldvals` in the
//                    raw records, parsed from the issue document text)
//   source=labels -> EVERY selected label present on the issue
//                    (multi-membership); none matched -> undefined group.
// [P12-P3] The optional S argument lets rcTeamCoverage pass the DRAFT
// settings; every other caller omits it and keeps rcDraft||RC_SETTINGS.
function rcItemTeams(it, S){
  var tc=((S||rcDraft||RC_SETTINGS).teamConfig)||{}, src=tc.source||'none';
  var UNDEF='Team is not defined';
  if(src==='labels'){
    var sel={};
    (tc.labels||[]).forEach(function(l){ sel[String(l).trim().toLowerCase()]=1; });
    var out=[];
    String(it.labels||'').split(',').forEach(function(l){
      var v=l.trim();
      if(v&&sel[v.toLowerCase()]) out.push(v);
    });
    return out.length?out:[UNDEF];
  }
  if(src==='field'&&tc.fieldName){
    var v=(it.fieldvals||{})[tc.fieldName];
    return v?[String(v)]:[UNDEF];
  }
  return [UNDEF];
}
// Dimension value field for an item: `component` maps to the record's
// `team` field (the issue's first component — the pre-settings dim).
function rcDimField(dim){
  // [P1-I13] 'issuetype' has no data field — the values come from the
  // item's normalized type (rcDimValues handles it directly).
  return dim==='component' ? 'team' : dim;
}
function rcDimValues(dim){
  var seen={}, out=[];
  // [P1-I13] Issue Type dimension: unique normalized types of the ACTIVE
  // items (already narrowed by the calendar + the top type filter), sorted.
  if(dim==='issuetype'){
    rcActiveItems().forEach(function(it){
      var v=rcTypeLabel(it.type);
      if(v && !seen[v]){ seen[v]=1; out.push(v); }
    });
    return out.sort();
  }
  rcActiveItems().forEach(function(it){
    if(dim==='team'){
      rcItemTeams(it).forEach(function(v){
        if(!seen[v]){ seen[v]=1; out.push(v); }
      });
      return;
    }
    var v=it[rcDimField(dim)]||'';
    if(!seen[v]){ seen[v]=1; out.push(v); }
  });
  return out.sort();
}
function rcPopulateDim(){
  var dim=document.getElementById('rcDim').value;
  var wrap=document.getElementById('rcDimList');
  if(dim==='project'){
    wrap.innerHTML='<span class="text-xs text-gray-500">Project: single value — all data</span>';
    return;
  }
  if(dim==='team' &&
     ((RC_SETTINGS.teamConfig||{}).source||'none')==='none'){
    // Default message when the Team source is not configured.
    wrap.innerHTML='<span class="text-xs text-gray-500">Team is not defined — configure the source in widget settings (gear icon → Widget settings → Team dimension).</span>';
    return;
  }
  var vals=rcDimValues(dim);
  wrap.innerHTML='';
  // [P1-1] Person: coaching-only warning banner above the checkboxes.
  var pmc=(((rcDraft||RC_SETTINGS).personMinCohort!==undefined)?(rcDraft||RC_SETTINGS).personMinCohort:5);
  if(dim==='person'){
    wrap.innerHTML='<div class="mb-2 p-2 bg-amber-50 border border-amber-300 rounded text-xs text-amber-800">'
      +'⚠️ Person-level breakdown is for coaching only, never for performance evaluation. '
      +'Cohorts smaller than '+pmc+' are aggregated as "Other (N persons)".</div>';
  }
  // [P1-1] Person min cohort: persons whose issue count (under the current
  // type/calendar filters) is below the threshold are NOT rendered; one
  // checkbox "Other (K persons)" represents them together.
  var otherSet={};
  if(dim==='person'){
    var typeSel0=rcTypeSelected();
    var cnt={};
    rcActiveItems().forEach(function(it){
      if(typeSel0 && !typeSel0[rcTypeLabel(it.type)]) return;
      var p=it.person||'(unassigned)';
      cnt[p]=(cnt[p]||0)+1;
    });
    Object.keys(cnt).forEach(function(p){
      if(cnt[p]<pmc) otherSet[p]=1;
    });
    rcPersonOtherSet=otherSet;
  } else { rcPersonOtherSet={}; }
  var otherK=Object.keys(otherSet).length;
  vals.forEach(function(v){
    if(dim==='person' && otherSet[v]) return;   // hidden into "Other"
    var lb=document.createElement('label');
    lb.className='inline-flex items-center gap-1 text-xs border rounded px-2 py-1 cursor-pointer';
    var cb=document.createElement('input');
    cb.type='checkbox'; cb.value=v; cb.className='rcDimCb'; cb.checked=true;
    cb.onchange=rcMarkPending;
    lb.appendChild(cb); lb.appendChild(document.createTextNode(v));
    wrap.appendChild(lb);
  });
  if(dim==='person' && otherK>0){
    var lb=document.createElement('label');
    lb.className='inline-flex items-center gap-1 text-xs border rounded px-2 py-1 cursor-pointer bg-gray-100';
    var cb=document.createElement('input');
    cb.type='checkbox'; cb.value='__other__'; cb.className='rcDimCb'; cb.checked=true;
    cb.onchange=rcMarkPending;
    lb.appendChild(cb); lb.appendChild(document.createTextNode('Other ('+otherK+' persons)'));
    wrap.appendChild(lb);
  }
}
// [P1-1] Persons aggregated into "Other (K persons)" (below min cohort).
// Rebuilt by rcPopulateDim on every dimension/settings change.
var rcPersonOtherSet={};
// Does the item pass the dimension filter? Team is multi-membership:
// the item matches if ANY of its teams is selected.
function rcDimMatch(it, dim, sel){
  if(!sel) return true;
  // [P1-I13] Issue Type dimension: the item matches when its normalized
  // type is among the selected values.
  if(dim==='issuetype'){
    return !!sel[rcTypeLabel(it.type)];
  }
  if(dim==='team'){
    return rcItemTeams(it).some(function(v){ return sel[v]; });
  }
  if(dim==='person'){
    // [P1-1] '__other__' matches any person aggregated into Other (below
    // the min cohort); named persons match directly.
    var p=it[rcDimField(dim)]||'(unassigned)';
    if(sel['__other__'] && rcPersonOtherSet[p]) return true;
    return !!sel[p];
  }
  return !!sel[it[rcDimField(dim)]];
}
function rcSelected(){
  var dim=document.getElementById('rcDim').value;
  if(dim==='project') return null; // no filtering (all)
  var cbs=document.querySelectorAll('#rcDimList .rcDimCb:checked');
  var set={};
  Array.prototype.forEach.call(cbs,function(cb){ set[cb.value]=1; });
  return set;
}
function rcAggValue(cfg, a){
  if(a===null||a===undefined) return null;
  if(cfg.rateMode==='spDensity'){
    // [FIX-A1] Defect Density: raw ratio (SP of defects ÷ SP completed, or
    // #defects ÷ #(Story+Task)) — NOT a percentage.
    return a.total ? (a.n/a.total) : null;
  }
  if(cfg.rateMode==='roles'){
    // [FIX-A2] Leakage escape rate, %.
    return a.total ? (a.n/a.total*100) : null;
  }
  if(cfg.aggregation==='allocation'){
    // [FIX-A5] timespent allocation, %.
    return a.total ? (a.n/a.total*100) : null;
  }
  if(cfg.aggregation==='rate') return a.total ? (a.n/a.total*100) : null;
  if(cfg.aggregation==='sum')  return a;
  if(cfg.aggregation==='count') return a;
  // avg — [P0-TYPES] Flow Efficiency items are objects ({eff, active,
  // total}); map them to their eff value so the per-period mean keeps
  // working for bars/trend/conclusion.
  var nums=a.map(function(v){ return (v&&typeof v==='object'&&v.eff!==undefined)?v.eff:v; });
  return nums.reduce(function(s,v){return s+v;},0)/nums.length;
}
"""
