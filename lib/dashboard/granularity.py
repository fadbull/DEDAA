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
function rcCalTouchedMemReset(){ rcCalTouchedMem={}; rcCalTouched=false; }
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
    // [P22-T1] The weekly key is a Monday DATE string (YYYY-MM-DD) — see
    // rcBucketKey. The old code parsed it as an ISO-week key (YYYY-Wnn),
    // producing NaN for every weekly bucket. Bucket end = Monday + 7 days
    // minus 1 ms.
    var wd=new Date(key+'T00:00:00');
    wd.setDate(wd.getDate()+7);
    return wd.getTime()-1;
  }
  if(gran==='sprint'){
    // sprint key: YYYY-Wnn-mm (two ISO weeks starting at week nn)
    // [P24-P2] Local time throughout (rcBucketKey / rcBucketStart bucket in
    // LOCAL time) — the old Date.UTC + setUTCDate mix shifted the bucket end
    // by the UTC offset for viewers outside UTC.
    var wk2=parseInt(key.split('-W')[1],10);
    var mon2=rcIsoWeekMonday(new Date(y,0,4));
    mon2.setDate(mon2.getDate()+(wk2-1)*7+14);
    return mon2.getTime()-1;
  }
  if(gran==='monthly'){ var m2=new Date(y, parseInt(key.slice(5),10), 1); return m2.getTime()-1; }
  if(gran==='quarterly'){ var q=parseInt(key.slice(6),10); return new Date(y, (q)*3, 1).getTime()-1; }
  if(gran==='annual'){ return new Date(y+1, 0, 1).getTime()-1; }
  return new Date(y, parseInt(key.slice(5),10), 1).getTime()-1;
}
// [P24-A] Project activity anchor — ONE anchor shared by every metric.
// Activity = every Jira event of the project (created, resolution date,
// status transitions) in RC_RAW, restricted to the current dimension
// selection. The anchor is the LAST bucket of the selected granularity
// whose activity reaches RC_ANCHOR_MIN_SHARE of the median activity of the
// non-empty buckets — stray late events (a handful of closures months after
// the project ended) do not move the window into empty periods.
var RC_ANCHOR_MIN_SHARE = 0.1;
var rcAnchorCache = {};
function rcProjectAnchor(gran){
  var dimEl=document.getElementById('rcDim');
  var dim=dimEl?dimEl.value:'project';
  var sel=(typeof rcSelected==='function')?rcSelected():null;
  var ck=gran+'|'+dim+'|'+(sel?Object.keys(sel).sort().join(','):'*')
        +'|'+((RC_SETTINGS.teamConfig||{}).source||'');
  if(rcAnchorCache.hasOwnProperty(ck)) return rcAnchorCache[ck]?new Date(rcAnchorCache[ck]):null;
  function collect(useSel){
    var cnt={}, lastIn={};
    (RC_RAW||[]).forEach(function(r){
      if(useSel && sel && !rcDimMatch(r, dim, sel)) return;
      var ds=[];
      if(r.created) ds.push(new Date(r.created));
      if(r.resolutiondate) ds.push(new Date(r.resolutiondate+'T00:00:00'));
      (r.events||[]).forEach(function(e){ ds.push(new Date(e[0])); });
      ds.forEach(function(d){
        if(isNaN(d)) return;
        var k=rcBucketKey(d, gran);
        cnt[k]=(cnt[k]||0)+1;
        if(!lastIn[k] || d>lastIn[k]) lastIn[k]=d;
      });
    });
    return {cnt:cnt, lastIn:lastIn};
  }
  var A=collect(true);
  if(!Object.keys(A.cnt).length) A=collect(false);
  var keys=Object.keys(A.cnt).sort();
  var res=null;
  if(keys.length){
    var vals=keys.map(function(k){ return A.cnt[k]; }).sort(function(a,b){ return a-b; });
    var med=vals[Math.floor((vals.length-1)/2)];
    var minAct=Math.max(1, Math.ceil(med*RC_ANCHOR_MIN_SHARE));
    for(var i=keys.length-1;i>=0;i--){
      if(A.cnt[keys[i]]>=minAct){ res=A.lastIn[keys[i]]; break; }
    }
    if(!res) res=A.lastIn[keys[keys.length-1]];
  }
  rcAnchorCache[ck]=res?res.getTime():null;
  return res?new Date(res):null;
}
// Last-N bucket keys ending at the bucket containing lastD (contiguous).
function rcLastBucketKeys(lastD, n, gran){
  var keys=[], guard=0;
  var cur=rcBucketStart(lastD, gran);
  var step=(gran==='daily')?1:(gran==='weekly')?7:(gran==='sprint')?14
          :(gran==='monthly')?1:(gran==='quarterly')?3:12;
  while(keys.length<n && guard<2000){
    keys.push(rcBucketKey(cur, gran));
    if(gran==='daily'||gran==='weekly'||gran==='sprint') cur.setDate(cur.getDate()-step);
    else if(gran==='annual') cur.setFullYear(cur.getFullYear()-step);
    else cur.setMonth(cur.getMonth()-step);
    guard++;
  }
  return keys.reverse();
}
// Default window (From/To dates) for a granularity: the last N CONTIGUOUS
// periods ending at the project activity anchor (rcProjectAnchor) — the
// SAME window for every metric (N = the metric's defaultN, else 5). Empty
// periods inside the window stay on the axis (0 for count/flow/grouped/
// snapshot metrics, a gap for averages and rates).
function rcDefaultWindow(gran){
  var last=rcProjectAnchor(gran);
  if(!last){
    rcActiveItems().forEach(function(it){
      var t=new Date(it.dev_start);
      if(!isNaN(t) && (!last || t>last)) last=t;
    });
  }
  if(!last || isNaN(last)) return null;
  last=new Date(last); last.setHours(0,0,0,0);
  var mEff=((rcDraft||RC_SETTINGS).metrics||{})[rcMetric]||{};
  var N=(mEff.defaultN!==undefined&&mEff.defaultN!==null)?mEff.defaultN:RC_DEFAULT_N;
  var cur=rcBucketStart(last, gran);
  var step = (gran==='daily')?1:(gran==='weekly')?7:(gran==='sprint')?14
            :(gran==='monthly')?1:(gran==='quarterly')?3:12;
  var from=new Date(cur);
  for(var i=0;i<N-1;i++){
    if(gran==='daily'||gran==='weekly'||gran==='sprint') from.setDate(from.getDate()-step);
    else if(gran==='annual') from.setFullYear(from.getFullYear()-step);
    else from.setMonth(from.getMonth()-step);
  }
  // To = the END of the anchor period (last ms of its last day).
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
function rcLinearTrend(points, allowNeg){
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
      // [P24-E] A signed series (flow balance) may legitimately go negative.
      var y=intercept + slope*i;
      return allowNeg ? y : Math.max(0, y);
    })
  };
}
// [P24-C] Trend verdict — ONE rule for every single-series metric.
//   change% = OLS slope × (span of the periods with data) ÷ |mean| × 100
//           = the relative change of the fitted trend across the window.
//   |change%| ≤ stablePct          → 🟡 Stable
//   otherwise the sign + the metric's trend direction → 🟢 Improving / 🔴 Degrading.
// At least RC_TREND_MIN_POINTS periods with data are required; fewer →
// no verdict ("not enough data"). An all-zero series is Stable.
var RC_TREND_MIN_POINTS = 3;
function rcStablePct(mk, S){
  var m=(((S||rcDraft||RC_SETTINGS).metrics)||{})[mk]||{};
  var v=m.stablePct;
  if(v===undefined||v===null||isNaN(v)){ v=((RC_CFG[mk]||{}).stable_pct); }
  return (v===undefined||v===null||isNaN(v))?10:Number(v);
}
function rcTrendVerdict(vals, dir, stablePct){
  var pts=[];
  (vals||[]).forEach(function(v,i){ if(v!==null&&v!==undefined&&!isNaN(v)) pts.push([i,v]); });
  if(pts.length<RC_TREND_MIN_POINTS) return {ok:false, n:pts.length, reason:'few'};
  var mean=pts.reduce(function(s,p){ return s+p[1]; },0)/pts.length;
  var allZero=pts.every(function(p){ return p[1]===0; });
  // A flat zero series (e.g. 0% rework in every period) is a measurement,
  // not missing data: Stable.
  if(allZero) return {ok:true, n:pts.length, change:0, cls:'stable', slope:0, zero:true};
  var tr=rcLinearTrend(vals);
  if(!tr) return {ok:false, n:pts.length, reason:'few'};
  var span=pts[pts.length-1][0]-pts[0][0];
  var base=Math.abs(mean);
  var chg = base ? tr.slope*span/base*100 : 0;
  var thr=(stablePct===undefined||stablePct===null)?10:stablePct;
  var cls;
  if(Math.abs(chg)<=thr) cls='stable';
  else if(dir==='up') cls = chg>0 ? 'improving' : 'degrading';
  else cls = chg<0 ? 'improving' : 'degrading';
  return {ok:true, n:pts.length, change:chg, cls:cls, slope:tr.slope};
}
function rcVerdictWord(cls){
  return cls==='improving' ? '🟢 Improving' : cls==='degrading' ? '🔴 Degrading'
       : cls==='recovering' ? '🟡 Recovering' : cls==='slowing' ? '🟡 Slowing' : '🟡 Stable';
}
// [P24-E] Flow / Bug Flow verdict. The net LEVEL over the window sets the
// colour; the resolved−opened balance trend can only soften it to 🟡, never
// flip it (a growing backlog is never «Improving», a shrinking one never
// «Degrading»):
//   net%   = Σ(resolved − opened) ÷ Σ(resolved + opened) × 100
//   trend% = balance OLS slope × (n−1) ÷ mean per-series flow per period × 100
//               | balance rising | flat        | falling
//   net < −band | 🟡 Recovering  | 🔴 Degrading | 🔴 Degrading
//   |net| ≤ band| 🟢 Improving   | 🟡 Stable    | 🔴 Degrading
//   net > +band | 🟢 Improving   | 🟢 Improving | 🟡 Slowing
function rcFlowVerdict(opened, resolved, stablePct){
  var n=opened.length;
  var oSum=opened.reduce(function(a,b){return a+b;},0);
  var rSum=resolved.reduce(function(a,b){return a+b;},0);
  var T=oSum+rSum, net=rSum-oSum;
  if(!T) return {ok:false, reason:'empty', n:n, net:0};
  var balance=opened.map(function(v,i){ return resolved[i]-v; });
  var bt=rcLinearTrend(balance, true);
  if(n<RC_TREND_MIN_POINTS || !bt) return {ok:false, reason:'few', n:n, net:net};
  var band=(stablePct===undefined||stablePct===null)?10:stablePct;
  var netPct=net/T*100;
  var trPct=bt.slope*(n-1)/(T/(2*n))*100;
  var lvl = netPct>band ? 'pos' : (netPct<-band ? 'neg' : 'bal');
  var tr  = trPct>band ? 'up' : (trPct<-band ? 'down' : 'flat');
  var cls;
  if(lvl==='neg') cls = tr==='up' ? 'recovering' : 'degrading';
  else if(lvl==='pos') cls = tr==='down' ? 'slowing' : 'improving';
  else cls = tr==='up' ? 'improving' : (tr==='down' ? 'degrading' : 'stable');
  return {ok:true, n:n, net:net, netPct:netPct, trPct:trPct, lvl:lvl, tr:tr, cls:cls};
}
// "Trend over window" fragment of the conclusion line.
function rcTrendText(v, nPeriods){
  if(!v || !v.ok){
    return 'Not enough data for a trend ('+(v?v.n:0)+' of '+nPeriods+' periods with data; ≥ '+RC_TREND_MIN_POINTS+' needed)';
  }
  if(v.zero) return rcVerdictWord(v.cls)+' · 0 in all '+v.n+' periods with data';
  var s=v.change>=0?'+':'−';
  return rcVerdictWord(v.cls)+' · trend over '+v.n+' periods '+s+Math.abs(v.change).toFixed(0)+'% of the window mean';
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
  // [P22-T7] The issuetype dimension was removed (it is a split, not a
  // filter, and is broken for role-based/flow/grouped/coverage/snapshot
  // metrics). Issue types remain accessible via the top Issue Types
  // multi-checkbox and the metric-settings type list.
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
  // avg — [P24-F] Flow Efficiency items are objects ({eff, active, total}):
  // the period value is the SAME ratio as the box — Σ active ÷ Σ total ×
  // 100 — so bars, trend and the window average share one formula.
  if(a.length && a[0] && typeof a[0]==='object' && a[0].total!==undefined){
    var fa=0, ft=0;
    a.forEach(function(v){ if(v && v.total!==undefined && v.total!==null){ fa+=(v.active||0); ft+=v.total; } });
    return ft>0 ? fa/ft*100 : null;
  }
  var nums=a.map(function(v){ return (v&&typeof v==='object'&&v.eff!==undefined)?v.eff:v; });
  return nums.reduce(function(s,v){return s+v;},0)/nums.length;
}
"""
