"""Widget settings panel (shared, cross-metric) + status-set helpers."""

WIDGET_JS = ("""

// ---- Metric settings: gear panel (per-metric), persistence, Apply ------
// The gear opens settings for the CURRENTLY SELECTED metric only (same
// scope as the info tooltip). Every parameter is a select/checkbox populated
// from the actual Jira project data (statuses from the changelog, issue
// types, labels, priorities) — no free-text input. Manual input remains
// only for unique parameters with no values in the project (e.g. the Prod
// label when the project has no labels). Persisted in localStorage;
// Export/Import produce the same JSON as the --metric-settings CLI flag.
var RC_LS_KEY = 'dedaa_metric_settings';
var RC_SETTINGS_DEFAULT = JSON.parse(JSON.stringify(RC_SETTINGS));

function rcSettingsLoad(){
  try{
    var raw=window.localStorage && window.localStorage.getItem(RC_LS_KEY);
    if(!raw) return;
    var user=JSON.parse(raw);
    if(!user || typeof user!=='object') return;
    // [P5-TP] One-time schema v1→v2 migration: when a stored metric's types
    // still equal the OLD default ("req" / ["Story","Task"]), drop them so
    // the merge falls back to the NEW default (the "work" alias). Custom
    // user selections are kept untouched.
    var MIGRATED_METRICS = {
      cycletime:   ['req', ['Story','Task']],
      qa:          ['req', ['Story','Task']],
      floweff:     ['req', ['Story','Task']],
      reviewcycle: [['Story','Task']]
    };
    Object.keys(MIGRATED_METRICS).forEach(function(mk){
      if(!user.metrics || !user.metrics[mk]) return;
      var cur=user.metrics[mk].types;
      if(cur===undefined||cur===null) return;
      var olds=MIGRATED_METRICS[mk];
      for(var i=0;i<olds.length;i++){
        var o=olds[i];
        var isOld=(typeof o==='string' && cur===o) ||
                  (Array.isArray(o) && Array.isArray(cur)
                   && o.length===cur.length
                   && o.every(function(v,j){ return v===cur[j]; }));
        if(isOld){ delete user.metrics[mk].types; break; }
      }
    });
    user._schema = 2;
    RC_SETTINGS=rcMergeSettings(RC_SETTINGS_DEFAULT, user);
    rcSettingsSave();
  }catch(e){ /* corrupted storage -> keep defaults */ }
}
function rcSettingsSave(){
  try{ window.localStorage.setItem(RC_LS_KEY, JSON.stringify(RC_SETTINGS)); }
  catch(e){ /* storage unavailable (file://) — settings stay session-only */ }
}
// Deep-merge a user patch over base (lists replace, objects merge).
function rcMergeSettings(base, user){
  var out=JSON.parse(JSON.stringify(base));
  (function deep(b,o){
    Object.keys(o||{}).forEach(function(k){
      if(o[k]&&typeof o[k]==='object'&&!Array.isArray(o[k])
         &&b[k]&&typeof b[k]==='object'&&!Array.isArray(b[k])){
        deep(b[k],o[k]);
      } else {
        b[k]=JSON.parse(JSON.stringify(o[k]));
      }
    });
  })(out, user||{});
  return out;
}
function rcRebuildData(){
  var derived=rcDeriveAll();
  Object.keys(derived).forEach(function(mk){ PM_DATA[mk]=derived[mk]; });
}
function rcSettingsToggle(){
  var panel=document.getElementById('rcSettingsPanel');
  if(!panel) return;
  panel.classList.toggle('hidden');
  if(!panel.classList.contains('hidden')){
    // open: start a fresh draft from the committed settings
    rcDraftBase=JSON.parse(JSON.stringify(RC_SETTINGS));
    rcDraft=JSON.parse(JSON.stringify(RC_SETTINGS));
    rcSettingsRender();
  } else {
    rcDraft=null; rcDraftBase=null;   // close discards unsaved edits
  }
}
function rcSettingsClose(){
  var panel=document.getElementById('rcSettingsPanel');
  if(panel) panel.classList.add('hidden');
  // [P0-B7] Closing the panel discards the draft — the committed settings
  // stay untouched (rcSettingsApply is the only commit path).
  rcDraft=null; rcDraftBase=null;
}
// ---- Widget settings (shared, cross-metric) ------------------------------
// Second gear: opens the Widget settings panel — global settings shared by
// every metric (Team dimension, workflow status sets, production label,
// severity map). Same draft lifecycle as the metric panel.
function rcWidgetSettingsToggle(){
  var panel=document.getElementById('rcWidgetSettingsPanel');
  if(!panel) return;
  panel.classList.toggle('hidden');
  if(!panel.classList.contains('hidden')){
    rcDraftBase=JSON.parse(JSON.stringify(RC_SETTINGS));
    rcDraft=JSON.parse(JSON.stringify(RC_SETTINGS));
    rcWidgetSettingsRender();
  } else {
    rcDraft=null; rcDraftBase=null;   // close discards unsaved edits
  }
}
function rcWidgetSettingsClose(){
  var panel=document.getElementById('rcWidgetSettingsPanel');
  if(panel) panel.classList.add('hidden');
  rcDraft=null; rcDraftBase=null;
}
function rcWidgetSettingsRender(){
  var host=document.getElementById('rcWidgetSettingsBody');
  if(!host) return;
  var S=rcDraft||RC_SETTINGS, V=rcVocab();
  var h='';
  // ---- Team dimension (widget-level) -------------------------------------
  var tc=S.teamConfig||{};
  var tcSrc=tc.source||'none';
  h+='<div class="mb-4 pb-3 border-b"><div class="text-xs font-semibold text-gray-500 uppercase mb-1">Team dimension</div>'
    +'<div class="mb-2"><span class="text-xs text-gray-600 mr-1">Source</span>'
    +'<select id="rcTeamSource" class="border rounded px-1 py-0.5 text-xs" onchange="rcTeamSourceChanged()">'
    +'<option value="none"'+(tcSrc==='none'?' selected':'')+'>Not configured</option>'
    +TEAM_FIELDS.map(function(f){
        return '<option value="field:'+rcEsc(f)+'"'+(tcSrc==='field'&&tc.fieldName===f?' selected':'')+'>Custom field: '+rcEsc(f)+'</option>';
      }).join('')
    +'<option value="labels"'+(tcSrc==='labels'?' selected':'')+'>Labels (pick teams from project labels)</option>'
    +'</select></div>';
  if(tcSrc==='field'){
    var fn=tc.fieldName||'';
    h+='<div class="mb-2"><div class="text-xs text-gray-500 mb-1">Team field</div>'
      +'<select id="rcTeamField" class="border rounded px-1 py-0.5 text-xs" onchange="rcTeamSourceChanged()">';
    TEAM_FIELDS.forEach(function(f){
      h+='<option value="'+rcEsc(f)+'"'+(fn===f?' selected':'')+'>'+rcEsc(f)+'</option>';
    });
    h+='</select>'
      +'<div class="text-xs text-gray-400 mt-1">'+(TEAM_FIELDS.length
        ?'Discovered Team fields in this project (native Team field or custom fields).'
        :'No Team field is populated in this project — pick Labels instead.')+'</div></div>';
  }
  if(tcSrc==='labels'){
    h+='<div class="mb-2"><div class="text-xs text-gray-500 mb-1">Teams = selected labels (an issue counts in EVERY matching team)</div>'
      +'<div>'+rcCbGroup('rcTeamLbl_', V.labels, tc.labels||[])+'</div></div>';
  }
  h+='<div class="text-xs text-gray-400 mb-1">'+rcTeamCoverage(S)+'</div>';
  h+='<div class="text-xs text-gray-400 mb-3">Issues with no resolved team are grouped as "Team is not defined" (included by default, filterable in the Team dimension).</div>';
  // ---- Workflow statuses (global status sets, shared by all metrics) ----
  h+='<div class="text-xs font-semibold text-gray-500 uppercase mb-1">Workflow statuses (from project history)</div>'
    +'<div class="text-xs text-gray-400 mb-2">Shared between the metrics that reference them.</div>';
  // [P23-F4] The ready status has a SINGLE editor: Metrics settings →
  // Backlog Health (it is the only metric reading statusSets.ready). The
  // multi-select here would silently overwrite the metric-level value.
  h+='<div class="text-xs text-gray-400 mb-2">Ready status (set: ready) is configured in the Backlog Health metric settings.</div>';
  // [FIX-A0] qaSet added to the workflow status sets (Leakage denominator).
  RC_SET_NAMES.forEach(function(name){
    h+='<div class="mb-2"><div class="text-xs text-gray-500">'+rcEsc(RC_SET_TITLES[name]||name)+'</div>'
      +'<div>'+rcCbGroup('rcSetWSt_'+name+'_', V.statuses, S.statusSets[name]||[])+'</div></div>';
  });
  // [P3-1] Heading follows the renamed metric.
  h+='<div class="mb-2"><div class="text-xs text-gray-500 mb-1">Production label (Production Leakage Rate / Incident Frequency)</div>'+rcProdLabelCtl()+'</div>';
  // [P3-2] Sprint data availability: auto-detect by data, or an explicit
  // user statement. Feeds the Backlog Health auto state (see rcSprintsAvail).
  var sd=((rcDraft||RC_SETTINGS)||{}).sprintData||'auto';
  var effSprints=rcSprintsAvail();
  h+='<div class="mb-2"><div class="text-xs text-gray-500 mb-1">Sprint data availability</div>'
    +'<select id="rcSet_sprintData" class="border rounded px-1 py-0.5 text-xs" onchange="rcPanelChanged()">'
    +'<option value="auto"'+(sd==='auto'?' selected':'')+'>Auto-detect (currently '+(RC_HAS_SPRINTS_DATA?'Sprints available':'No sprints')+')</option>'
    +'<option value="available"'+(sd==='available'?' selected':'')+'>Sprints available</option>'
    +'<option value="none"'+(sd==='none'?' selected':'')+'>No sprints</option>'
    +'</select>'
    +'<div class="text-xs text-gray-400 mt-1">Controls which Backlog Health state the Auto rule picks. auto: detect from the project data (any item carrying a sprint field); available/none: your explicit statement.</div></div>';
  // ---- [P1-1] Person min cohort -------------------------------------------
  var pmc=(S.personMinCohort!==undefined&&S.personMinCohort!==null)?S.personMinCohort:5;
  h+='<div class="mb-2"><div class="text-xs text-gray-500 mb-1">Person min cohort (Dimension: Person)</div>'
    +'<select id="rcPersonMinCohort" class="border rounded px-1 py-0.5 text-xs" onchange="rcWidgetPanelChanged()">'
    +['3','5','8','10'].map(function(v){
        return '<option value="'+v+'"'+(String(pmc)===v?' selected':'')+'>'+v+'</option>';
      }).join('')
    +'</select>'
    +'<div class="text-xs text-gray-400 mt-1">Persons with fewer issues than this threshold are aggregated as "Other (K persons)" in the Person dimension.</div></div>';
  // ---- Severity map (global default; per-metric override still wins) -----
  h+='<div class="text-xs font-semibold text-gray-500 uppercase mt-3 mb-1">Severity map (from project priorities)</div>';
  ['Critical','Major','Minor'].forEach(function(g){
    var cur=(S.severityMap||{})[g]||[];
    h+='<div class="mb-1"><div class="text-xs text-gray-500">'+g+'</div>'
      +'<div>'+rcCbGroup('rcSetSev_'+g+'_', V.priorities, cur)+'</div></div>';
  });
  h+='<div class="text-xs text-gray-400 mb-2">Minor: empty group = all other priorities. A metric-level severity map (Metrics settings → Incident Frequency) overrides this default.</div>';
  // [P2-3] Live distribution of the prod-labelled bugs over the severity
  // groups (current window) + a >80% skew warning. UI-only hint: it never
  // enters the metric numbers, tooltip, conclusion, legend or axis.
  // Incident items carry the resolved `severity` (derive applies the map).
  var cnt={Critical:0,Major:0,Minor:0};
  (PM_DATA.incident||[]).forEach(function(it){
    var g=String(it.severity||'Minor');
    if(cnt[g]!==undefined) cnt[g]++;
  });
  var tot=cnt.Critical+cnt.Major+cnt.Minor;
  var skewed=(tot>0 && (cnt.Critical/tot>0.8 || cnt.Major/tot>0.8 || cnt.Minor/tot>0.8));
  h+='<div class="mb-2 text-xs '+(skewed?'text-amber-700':'text-gray-500')+'">'
    +'Current distribution: Critical '+cnt.Critical+', Major '+cnt.Major+', Minor '+cnt.Minor+' ('+tot+' total)'
    +(skewed
      ? ' — ⚠ Distribution is skewed — one severity group contains over 80% of prod bugs. Review the severity map below.'
      : '')+'</div>';
  host.innerHTML=h;
}
// Collect the widget panel's controls into a settings patch.
// [P2-I15] Only the fields this panel actually fills — the dead empty
// metrics:{} is gone (the widget panel never edits per-metric settings).
function rcCollectWidgetPanel(){
  var user={statusSets:{}};
  function checkedVals(prefix){
    var out=[];
    Array.prototype.forEach.call(
      document.querySelectorAll('input[id^="'+prefix+'"]:checked'),
      function(cb){ out.push(cb.value); });
    return out;
  }
  // [FIX-A0] qaSet collected with the other workflow status sets.
  RC_SET_NAMES.forEach(function(name){
    user.statusSets[name]=checkedVals('rcSetWSt_'+name+'_');
  });
  var pl=rcVal('rcSet_prodLabel');
  if(pl!==undefined&&pl.trim()) user.prodLabel=pl.trim();
  // [P3-2] Sprint data availability (auto | available | none).
  var sd=rcVal('rcSet_sprintData');
  if(sd!==undefined&&sd!=='') user.sprintData=sd;
  // [P1-1] Person min cohort (3/5/8/10).
  var pmc=rcVal('rcPersonMinCohort');
  if(pmc!==undefined&&pmc!==''){ var pv=parseInt(pmc,10); if(!isNaN(pv)) user.personMinCohort=pv; }
  // ---- Severity map (global default; per-metric override still wins) -----
  var sm={};
  ['Critical','Major','Minor'].forEach(function(g){
    sm[g]=checkedVals('rcSetSev_'+g+'_');
  });
  user.severityMap=sm;
  // Team dimension (source select + labels chips).
  var tsrc=rcVal('rcTeamSource');
  if(tsrc!==undefined){
    var tc={source:'none', fieldName:'', labels:[]};
    if(tsrc==='labels'){
      tc.source='labels';
      tc.labels=rcTeamLabelsChecked();
    } else if(tsrc.indexOf('field:')===0){
      tc.source='field';
      tc.fieldName=tsrc.slice(6);
      var tfs=rcVal('rcTeamField');
      if(tfs!==undefined&&tfs!=='') tc.fieldName=tfs;
    }
    user.teamConfig=tc;
  }
  return user;
}
// Any widget-panel control change: refresh the draft + coverage note.
function rcWidgetPanelChanged(){
  if(!rcDraft) return;
  rcDraft=rcMergeSettings(rcDraftBase, rcCollectWidgetPanel());
  rcWidgetSettingsRender();
}
// Apply/Reset/Export/Import for the widget panel: same commit semantics as
// the metric panel (the draft holds the whole RC_SETTINGS).
function rcWidgetSettingsApply(){
  if(!rcDraft) rcDraft=JSON.parse(JSON.stringify(RC_SETTINGS));
  RC_SETTINGS=rcDraft;
  rcSettingsSave();
  rcRebuildData();
  rcSetMetric(rcMetric);
  rcWidgetSettingsClose();
  rcDraft=null; rcDraftBase=null;
}
function rcWidgetSettingsReset(){
  rcSettingsReset();
}
function rcWidgetSettingsExport(){
  rcSettingsExport();
}
function rcWidgetSettingsImport(){
  rcSettingsImport();
}
// Status-set names referenced by a metric's formula (walk start/end/
// membership/anchor/returnTo/active/total anchors).
function rcMetricSets(mk){
  var m=(RC_SETTINGS.metrics||{})[mk]||{}, out={};
  (function scan(o){
    if(!o||typeof o!=='object') return;
    if(o.kind==='status'&&o.set) out[o.set]=1;
    Object.keys(o).forEach(function(k){
      if(o[k]&&typeof o[k]==='object') scan(o[k]);
    });
  })(m);
  return Object.keys(out);
}
var RC_SET_TITLES={
  devStart:'Dev start statuses (set: devStart)',
  done:'Done statuses (set: done)',
  qaEntry:'QA entry statuses (set: qaEntry)',
  qaSet:'QA statuses (set: qaSet)',
  qaExit:'QA passed / QA-exit statuses (set: qaExit)',
  ready:'Ready statuses (set: ready)',
  backlog:'Backlog statuses (set: backlog)',
  refinement:'Refinement / rework return-to (set: refinement)',
  review:'Review statuses (set: review)'   // [P2v3-2] Review Cycle Count
};   // [FIX-A0] qaSet added · [P0v3-F2] qaExit added · [P2v3-2] review added
// Status sets shown in "Widget settings → Workflow statuses" (multi-select
// from the actual project statuses). [FIX-A0] qaSet included.
// [P23-F4] 'ready' is NOT in this list: it has a single editor (Metrics
// settings → Backlog Health) — the Widget-settings multi-select would
// overwrite the metric-level value. RC_SET_TITLES.ready and the
// statusSets.ready default remain (the value stays meaningful).
var RC_SET_NAMES=['devStart','done','qaEntry','qaSet','qaExit','backlog','refinement','review'];
// Is the project's ready status actually present in the Jira history?
// (Backlog Health: 'Ready for development' is the default ready status;
// when it is absent the settings ask the user to assign one.)
function rcReadyStatusUsed(){
  var set=(RC_SETTINGS.statusSets||{}).ready||[];
  if(!set.length) return false;
  var low={}; set.forEach(function(s){ low[String(s).toLowerCase()]=1; });
  return (RC_RAW||[]).some(function(r){
    if(low[String(r.status||'').toLowerCase()]) return true;
    return (r.events||[]).some(function(e){ return low[String(e[1]||'').toLowerCase()]; });
  });
}
// Display form of the current ready status (first of the 'ready' set).
function rcReadyStatusDisp(){
  var set=(rcDraft||RC_SETTINGS).statusSets||{};
  var vals=set.ready||[];
  return vals.length?vals[0]:'ready for development';
}
// Does the defect workflow (Bug/Sub-bug) actually use a ready status? True
// when any defect in the project history has EVER been in the ready set
// (event transition or current status). Used by the Backlog Health
// defects=auto mode (module-level: also referenced by the settings panel).
function rcDefectReadySeen(){
  var set=(RC_SETTINGS.statusSets||{}).ready||[];
  if(!set.length) return false;
  var low={}; set.forEach(function(s){ low[String(s).toLowerCase()]=1; });
  return (RC_RAW||[]).some(function(r){
    var t=String(r.type||'').toLowerCase();
    var isDef=(t==='bug'||t==='sub-bug'||t==='defect'||t==='sub-bug');
    if(!isDef) return false;
    if(low[String(r.status||'').toLowerCase()]) return true;
    return (r.events||[]).some(function(e){
      return low[String(e[1]||'').toLowerCase()];
    });
  });
}
// Vocabulary from the actual Jira project data (RC_RAW): statuses seen in
// changelog transitions + current statuses, labels, priorities.
function rcVocab(){
  var st={}, lb={}, pr={};
  (RC_RAW||[]).forEach(function(r){
    if(r.status) st[String(r.status).trim()]=1;
    (r.events||[]).forEach(function(e){
      var s=String(e[1]||'').trim(); if(s) st[s]=1;
    });
    String(r.labels||'').split(',').forEach(function(x){
      var t=x.trim(); if(t) lb[t]=1;
    });
    if(r.priority) pr[String(r.priority).trim()]=1;
  });
  return { statuses:Object.keys(st).sort(), labels:Object.keys(lb).sort(),
           priorities:Object.keys(pr).sort() };
}
// Effective production label. The DEFAULT value ('prod') resolves to the
// FIRST project label containing 'prod' (case-insensitive, e.g.
// 'Production') so projects that tag production defects differently work
// out of the box; an explicitly chosen non-default value always wins.
function rcProdLabelEff(val, S){
  S=S||rcDraft||RC_SETTINGS;
  var def=String((RC_SETTINGS_DEFAULT||{}).prodLabel||'prod');
  var v=(val!==undefined&&val!==null&&String(val)!=='')
    ? String(val) : String(S.prodLabel||def);
  if(v.toLowerCase()!==def.toLowerCase()) return v;   // explicit override
  var V=rcVocab();
  for(var i=0;i<V.labels.length;i++){
    if(String(V.labels[i]).toLowerCase().indexOf('prod')>=0) return V.labels[i];
  }
  return v;
}
// Select control: options from the project data; current value is
// pre-selected (added as an option if missing, e.g. custom imported value).
function rcSelCtl(id, options, current){
  var h='<select id="'+id+'" class="border rounded px-1 py-0.5 text-xs" onchange="rcPanelChanged()">';
  var seen={};
  (options||[]).forEach(function(o){
    var v=String(o);
    seen[v]=1;
    h+='<option value="'+rcEsc(v)+'"'+(v===String(current)?' selected':'')+'>'+rcEsc(v)+'</option>';
  });
  if(current!==undefined&&current!==null&&!seen[String(current)]){
    h+='<option value="'+rcEsc(current)+'" selected>'+rcEsc(current)+'</option>';
  }
  return h+'</select>';
}
// [P1-STATES] Select with per-option display labels: options = [[value,label],…].
function rcSelCtlLabeled(id, options, current){
  var h='<select id="'+id+'" class="border rounded px-1 py-0.5 text-xs" onchange="rcPanelChanged()">';
  var seen={};
  (options||[]).forEach(function(o){
    var v=String(o[0]), lbl=String(o[1]===undefined?o[0]:o[1]);
    seen[v]=1;
    h+='<option value="'+rcEsc(v)+'"'+(v===String(current)?' selected':'')+'>'+rcEsc(lbl)+'</option>';
  });
  if(current!==undefined&&current!==null&&!seen[String(current)]){
    h+='<option value="'+rcEsc(current)+'" selected>'+rcEsc(current)+'</option>';
  }
  return h+'</select>';
}
// Checkbox group: options/selected are display-case strings; matching is
// case-insensitive (settings store display case, derivation lowercases).
function rcCbGroup(idPrefix, options, selected){
  var sel={};
  (selected||[]).forEach(function(v){ sel[String(v).toLowerCase()]=1; });
  var h='';
  options.forEach(function(o){
    var c=!!sel[String(o).toLowerCase()];
    h+='<label class="inline-flex items-center gap-1 text-xs border rounded px-2 py-0.5 mr-1 mb-1 cursor-pointer">'
      +'<input type="checkbox" id="'+idPrefix+'" value="'+rcEsc(o)+'" onchange="rcPanelChanged()"'+(c?' checked':'')+'>'
      +'<span>'+rcEsc(o)+'</span></label>';
  });
  return h;
}
// Production-label control: a select of the labels that actually exist in
// the project; manual input only when the project has no labels at all.
function rcProdLabelCtl(){
  var V=rcVocab();
  var cur=rcProdLabelEff(undefined, rcDraft||RC_SETTINGS);
  if(V.labels.length){
    var opts=V.labels.slice();
    var found=opts.some(function(l){ return l.toLowerCase()===cur.toLowerCase(); });
    if(!found) opts.push(cur);
    opts.sort();
    return rcSelCtl('rcSet_prodLabel', opts, cur)
      +'<span class="text-xs text-gray-400 ml-1">from project labels</span>';
  }
  return '<input id="rcSet_prodLabel" class="border rounded px-2 py-1 text-xs w-40" value="'+rcEsc(cur)+'" onchange="rcPanelChanged()">'
    +'<span class="text-xs text-gray-400 ml-1">no labels in project — manual entry</span>';
}
""")
