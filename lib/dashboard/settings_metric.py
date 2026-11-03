"""Metric settings panel: formula display, anchor editors, collect/apply."""

SETTINGS_JS = """// Build the panel DOM for the CURRENTLY SELECTED metric only. All controls
// are populated from the project's actual values — no free text (except the
// Prod label fallback when the project has no labels).
// ---- Formula display (live) + anchor editors ---------------------------
// The settings panel shows the metric's formula as human-readable text
// built from the CURRENT draft settings, and offers structured anchor
// editors (source select + status-set select). Every control change
// updates a draft copy and refreshes the formula line live; Apply commits
// the draft (re-derive + persist). No free-text input anywhere.
var rcDraft = null;        // working copy while the panel is open
var rcDraftBase = null;    // RC_SETTINGS snapshot taken when panel opened

function rcDispStatus(v){
  var V=rcVocab(), map={};
  V.statuses.forEach(function(s){ map[String(s).toLowerCase()]=s; });
  var low=String(v||'').toLowerCase();
  if(map[low]) return map[low];
  return String(v||'').replace(/\b\w/g,function(c){return c.toUpperCase();});
}
function rcSetListText(setName, S){
  var vals=((S.statusSets||{})[setName]||[]);
  return '['+(vals.length?vals.map(rcDispStatus).join(', '):setName)+']';
}
function rcTypesText(mk, key, S){
  var m=(S.metrics||{})[mk]||{};
  var ref=key?m[key]:m.types;
  if(typeof ref==='string') ref=(S.types||{})[ref]||[];
  return '['+((ref||[]).join(', ')||'—')+']';
}
function rcAnchorText(a, S){
  if(!a||!a.kind) return '?';
  if(a.kind==='field') return a.field==='resolutiondate'?'Resolution date':'Created';
  var txt='first transition to '+rcSetListText(a.set, S);
  if(a.fallback==='resolutiondate') txt+=' (fallback: Resolution date)';
  return txt;
}
// Formula text for a metric, projected from its settings (S = draft or
// committed settings). One grammar per metric family.
function rcFormulaText(mk, S){
  S=S||RC_SETTINGS;
  var m=(S.metrics||{})[mk]||{};
  function T(key){ return rcTypesText(mk, key, S); }
  function A(a){ return rcAnchorText(a, S); }
  switch(mk){
    case 'cycle':
      return 'avg( '+A(m.end)+' − '+A(m.start)+' ) for '+T();
    case 'cycletime':
    case 'qa':
      return 'avg( '+A(m.end)+' − '+A(m.start)+' ) for '+T();
    case 'lead':
      var endTxt=(m.end&&m.end.kind==='field'&&m.end.field==='resolutiondate')
        ? 'Resolution date'
        : '('+A(m.end)+' || Resolution date)';
      return 'avg( '+endTxt+' − '+A(m.start)+' ) for '+T();
    case 'bugfix':
      // [FIX-A5] worklog allocation (falls through from lead was dead code:
      // bugfix has no start/end anchors — it is an allocation metric).
      return 'allocation( Σ(timespent on '+T()+') ÷ Σ(timespent on all completed work) × 100% ) per period — requires Jira worklog';
    case 'floweff':
      return 'avg( ('+A(m.active.end)+' − '+A(m.active.start)
        +') ÷ ('+A(m.total.end)+' − '+A(m.total.start)+') × 100% ) for '+T();
    case 'throughput':
    case 'velocity':
      return 'count( '+A(m.start)+' ) for '+T();
    case 'wip':
      // [FIX-A4] Snapshot formula.
      return 'wip( enterDev ≤ endOf(P) < leaveDev ) — snapshot at each period end for '+T()
        +' (enterDev: '+A(m.start)+'; leaveDev: '+A(m.end)+')';
    case 'defectdensity':
      // [FIX-A1] Mode-dependent formula.
      // [P7-DD] The numerator is the COUNT of defects found in QA in both
      // modes — only the denominator switches (SP ÷ count).
      var mode=rcDensityMode();
      return mode==='per_sp'
        ? 'rate( #defects found in QA ÷ Σ(SP of completed Story/Task) ) per period'
        : 'rate( #defects found in QA ÷ #(Story+Task completed) ) per period (per_item — no story points)';
    case 'leakage':
      // [P3-LK] The formula names the UNION (QA-entered ∪ prod-labelled) —
      // the full-population wording is gone.
      return 'rate( bugs labeled ['+rcProdLabelEff(String(m.prodLabel||S.prodLabel||'prod'), S)+'] ÷ (QA-entered defects ∪ prod-labelled defects) ) for '+T()
        +' · bucket: '+(m.bucketBy||'created');
    case 'backlog':
      var den=(m.denominator||'auto');
      var denTxt = den==='throughput' ? 'Average Throughput (issues) per period'
                 : den==='velocity_sp' ? 'Average Velocity (story points) per period'
                 : 'Average Velocity (SP) per period when the project has sprints and story points, else Average Throughput (issues) per period (auto)';
      return 'coverage( ready items ∈ '+rcSetListText(m.membership&&m.membership.set,S)
        +' at each period end ÷ '+denTxt
        +' ) — sprints of ready work; healthy band '+
        ((m.targetMin!==undefined&&m.targetMin!==null)?m.targetMin:2)+'–'+
        ((m.targetMax!==undefined&&m.targetMax!==null)?m.targetMax:3);
    case 'rework':
      return 'rate( returned to '+rcSetListText(m.returnTo&&m.returnTo.set,S)+' after '+A(m.anchor)+' ) for '+T();
    case 'flow':
      return 'series: opened = '+A(m.series&&m.series.opened)+'; resolved = '+A(m.series&&m.series.resolved)+' for '+T();
    case 'bugflow':
      return 'series: new = '+A(m.series&&m.series.new)+'; resolved = '+A(m.series&&m.series.resolved)+' for '+T();
    case 'incident':
      return 'count( bugs labeled ['+rcProdLabelEff(String(m.prodLabel||S.prodLabel||'prod'), S)+'] ) stacked by severity( priority ) for '+T();
    // [P4-3] Label-driven escape rate.
    case 'escapereview':
      return 'rate( defects labeled ['+(m.qaLabel||'—')+'] ÷ (defects labeled ['+(m.reviewLabel||'—')+'] + ['+(m.qaLabel||'—')+']) ) for '+T();
    // [P4-4] Status-driven design review turnaround.
    case 'designreview':
      return 'avg( first ['+(m.reviewDone||'—')+'] − first ['+(m.designStart||'—')+'] ) for '+T()+' — zero-day intervals excluded';
    // [P2v3-1] Clarification Cycle Count.
    case 'clarcycle':
      return 'avg( count of returns to refinement before first dev start ) for '+T();
    // [P2v3-2] Review Cycle Count.
    case 'reviewcycle':
      return 'avg( count of re-review cycles ) for '+T();
    default:
      return '';
  }
}
// Anchor specs of a metric (walk the config tree; returns editable rows).
function rcMetricAnchors(mk){
  var m=((rcDraft||RC_SETTINGS).metrics||{})[mk]||{}, out=[];
  (function scan(o, path){
    if(!o||typeof o!=='object') return;
    if(o.kind==='field'||o.kind==='status'){
      out.push({ path:path.slice(), spec:o });
    }
    Object.keys(o).forEach(function(k){
      if(o[k]&&typeof o[k]==='object') scan(o[k], path.concat(k));
    });
  })(m, []);
  return out;
}
function rcAnchorLabel(path){
  var names={start:'Start anchor', end:'End anchor',
             membership:'Membership (current status)', anchor:'Rework anchor',
             returnTo:'Return-to statuses', opened:'Series "opened"',
             resolved:'Series "resolved"', active:'Active interval',
             total:'Total interval', new:'New', created:'Created',
             resolutiondate:'Resolution date'};
  return path.map(function(p){ return names[p]||p; }).join(' → ');
}
// Anchor spec -> value for the source select ('created'|'resolutiondate'|'status').
function rcAnchorKind(a){
  if(!a) return 'created';
  if(a.kind==='status') return 'status';
  return a.field==='resolutiondate' ? 'resolutiondate' : 'created';
}
// Team-source coverage note: how many issues get a team vs undefined.
function rcTeamCoverage(S){
  var tc=(S||{}).teamConfig||{}, src=tc.source||'none';
  var total=(RC_RAW||[]).length, withTeam=0;
  (RC_RAW||[]).forEach(function(r){
    // [P12-P3] Pass S through: the coverage note describes the config the
    // panel is showing (draft in the widget settings, committed elsewhere).
    var ts=rcItemTeams(r, S);
    if(!(ts.length===1&&ts[0]==='Team is not defined')) withTeam++;
  });
  if(src==='none'){
    return 'Team source is not configured: all '+total+' issues are in "Team is not defined".';
  }
  return withTeam+' of '+total+' issues get a team; '+(total-withTeam)+' → "Team is not defined".';
}
// Selected team labels (source=labels chips).
function rcTeamLabelsChecked(){
  var out=[];
  Array.prototype.forEach.call(
    document.querySelectorAll('input[id^="rcTeamLbl_"]:checked'),
    function(cb){ out.push(cb.value); });
  return out;
}
// Team-source picker changed: update the draft teamConfig + re-render.
function rcTeamSourceChanged(){
  if(!rcDraft) return;
  var v=rcVal('rcTeamSource')||'none';
  var tc=rcDraft.teamConfig=rcDraft.teamConfig||{};
  if(v==='none'){
    tc.source='none'; tc.fieldName=''; tc.labels=[];
  } else if(v==='labels'){
    tc.source='labels';
  } else if(v.indexOf('field:')===0){
    tc.source='field';
    tc.fieldName=v.slice(6);
  }
  // The field select (visible only for source=field) may override.
  var fs=rcVal('rcTeamField');
  if(tc.source==='field'&&fs!==undefined&&fs!==''){ tc.fieldName=fs; }
  if(tc.source==='labels'){ tc.labels=rcTeamLabelsChecked(); }
  else { tc.labels=[]; }
  rcWidgetSettingsRender();   // re-render: coverage note + labels chips
}
// Trend rule for a metric: a read-only semantic property of its DEFINITION
// (which direction of the slope means "Improving"). Flow/bugflow use the
// resolved-minus-opened balance; grouped (incident) trends the total.
function rcTrendRule(mk, S){
  S=S||RC_SETTINGS;
  var m=(S.metrics||{})[mk]||{};
  var band=rcStablePct(mk, S);
  var dir=m.trendDir||((RC_CFG[mk]||{}).trend_dir)||'down';
  if(m.aggregation==='coverage'){
    var lo=(m.targetMin!==undefined&&m.targetMin!==null)?m.targetMin:2;
    var hi=(m.targetMax!==undefined&&m.targetMax!==null)?m.targetMax:3;
    return 'Trend: band rule — '+lo+'–'+hi+' sprints of ready work = Healthy (🟢), below '+lo+' = Under-stocked (🔴), above '+hi+' = Over-stocked (🟡).';
  }
  var common=' Needs ≥ '+RC_TREND_MIN_POINTS+' periods with data. Δ = last period vs the previous one.';
  if(m.aggregation==='flow'){
    // [P19-B1] The bugflow series is new-vs-resolved — the balance word
    // must match the series name ('new'), not 'opened'.
    var openWord=(mk==='bugflow')?'new':'opened';
    // [P24-C/E] Net level + balance trend.
    return 'Trend: net = Σ(resolved − '+openWord+') over the window. Net below −'+band+'% of the total flow (backlog growing) = Degrading (🔴) unless the resolved−'+openWord+' balance is clearly rising; net above +'+band+'% = Improving (🟢) unless the balance is clearly falling; otherwise a rising balance = Improving, falling = Degrading, within ±'+band+'% = Stable (🟡).'+common;
  }
  var rule=' Change = relative change of the fitted trend line across the window (slope × periods ÷ window mean); within ±'+band+'% = Stable (🟡).';
  if(dir==='up'){
    return 'Trend: higher is better — rising = Improving (🟢), falling = Degrading (🔴).'+rule+common;
  }
  return 'Trend: lower is better — falling = Improving (🟢), rising = Degrading (🔴).'+rule+common;
}

function rcSettingsRender(){
  var host=document.getElementById('rcSettingsBody');
  if(!host) return;
  var S=rcDraft||RC_SETTINGS, mk=rcMetric, m=(S.metrics||{})[mk]||{};
  var V=rcVocab();
  function effTypes(ref){
    if(typeof ref==='string') ref=(S.types||{})[ref]||[];
    return (ref||[]).slice();
  }
  var h='';
  h+='<div class="text-xs text-gray-400 mb-3">Team dimension, workflow statuses, production label and severity map are shared across all metrics — edit them in Widget settings (the second gear).</div>';
  h+='<div class="text-sm font-medium mb-1">'+rcEsc(m.label||mk)+'</div>';
  // ---- Live formula (read-only; updates on every control change) ----
  h+='<div class="mb-3 p-2 bg-gray-50 border rounded"><div class="text-xs font-semibold text-gray-500 uppercase mb-1">Formula</div>'
    +'<div id="rcFormulaText" class="text-xs font-mono text-gray-700 break-words">'+rcEsc(rcFormulaText(mk, S))+'</div>'
    +'<div id="rcTrendRule" class="text-xs text-gray-500 mt-1">'+rcEsc(rcTrendRule(mk, S))+'</div>'
    +'<div class="text-xs text-gray-400 mt-1">Edits below update the formula live; Apply commits them. Trend direction is fixed by the metric definition (not editable).</div></div>';
  h+='<div class="text-xs text-gray-400 mb-3">Values are offered from the actual Jira project data. Status sets are shared between the metrics that reference them.</div>';
  // ---- Formula anchors (structured editors, no free text) ----
  var anchors=rcMetricAnchors(mk);
  if(anchors.length){
    h+='<div class="text-xs font-semibold text-gray-500 uppercase mb-1">Formula anchors</div>';
    anchors.forEach(function(a, i){
      var pathKey=a.path.join('.');
      var kind=rcAnchorKind(a.spec);
      h+='<div class="mb-2"><div class="text-xs text-gray-500">'+rcEsc(rcAnchorLabel(a.path))+'</div><div class="flex flex-wrap gap-2 items-center">'
        +'<select id="rcSetAncKind_'+i+'" class="border rounded px-1 py-0.5 text-xs" onchange="rcAnchorChanged('+i+')">'
        +'<option value="created"'+(kind==='created'?' selected':'')+'>Created date</option>'
        +'<option value="resolutiondate"'+(kind==='resolutiondate'?' selected':'')+'>Resolution date</option>'
        +'<option value="status"'+(kind==='status'?' selected':'')+'>Status transition</option>'
        +'</select>';
      if(kind==='status'){
        h+='<select id="rcSetAncSet_'+i+'" class="border rounded px-1 py-0.5 text-xs" onchange="rcAnchorSetChanged('+i+')">';
        // [FIX-A0] qaSet offered in the anchor set selects too.
        RC_SET_NAMES.forEach(function(sn){
          h+='<option value="'+sn+'"'+(a.spec.set===sn?' selected':'')+'>'+rcEsc(sn)+'</option>';
        });
        h+='</select>';
      }
      h+='</div></div>';
    });
  }
  // NOTE: workflow status sets moved to Widget settings (shared across all
  // metrics); this panel keeps only metric-specific controls. The sets this
  // metric references are listed read-only below the Formula box.
  var usedSets=rcMetricSets(mk);
  if(usedSets.length){
    h+='<div class="text-xs text-gray-400 mb-3">Uses status sets: '+usedSets.map(function(n){return rcEsc(RC_SET_TITLES[n]||n);}).join(' · ')
      +' — edit them in Widget settings (the second gear).</div>';
  }
  // ---- Issue types (checkboxes from project data) ----
  h+='<div class="mb-2"><div class="text-xs text-gray-500 mb-1">Issue types</div>'
    +'<div>'+rcCbGroup('rcSetTy_'+mk+'_', ISSUE_TYPES, effTypes(m.types))+'</div></div>';
  // ---- Aggregation (read-only) / threshold / window (selects) ----
  // NOTE: trend direction is NOT editable — it is a semantic property of
  // the metric's definition (derived from its formula/conditions). It is
  // shown as a read-only rule in the Formula box below.
  h+='<div class="flex flex-wrap gap-2 items-center mb-2 text-sm">';
  // [P0-2] Aggregation is a semantic property of the metric (rcApply pins
  // each metric to its own computation branch) — shown read-only, no select.
  h+='<span class="text-xs text-gray-600" title="Aggregation is a semantic property of the metric definition — not editable.">Aggregation: '+(m.aggregation||'—')+' (fixed)</span>';
  // [P24-C] Stable band of the relative trend rule (% of the window mean).
  // Backlog Health uses its healthy band instead (no slope verdict).
  if(m.aggregation!=='coverage'){
    h+='<label class="text-xs text-gray-600" title="Trend over the window within ± this % of the window mean = Stable">Stable band ±% '+rcSelCtl('rcSet_'+mk+'_stablePct', ['5','10','15','20','25','30'], String(rcStablePct(mk, S)))+'</label>';
  }
  if(m.defaultN!==undefined){
    h+='<label class="text-xs text-gray-600">Default N '+rcSelCtl('rcSet_'+mk+'_defaultN', ['1','2','3','4','5','6','7','8','9','10'], m.defaultN)+'</label>';
  }
  h+='</div>';
  if(mk==='wip'){
    // [P1-3] WIP mode: absolute total (default) or per-developer.
    h+='<div class="mb-2"><span class="text-xs text-gray-600 mr-1">WIP mode</span>'
      +rcSelCtl('rcSet_wip_wipMode', ['total','per_developer'], m.wipMode||'total')+'</div>'
      +'<div class="text-xs text-gray-400 mb-1">per_developer normalizes WIP by the number of unique assignees (developers) per period; the dashed line marks ≤ 1.5 per dev.</div>';
  }
  if(mk==='backlog'){
    // Coverage-specific: ready status + defect mode + denominator + band.
    // 'Ready for development' is the DEFAULT ready status for Story/Task;
    // when the project history has NO ready status at all, ask the user to
    // assign one (here — this panel is the SINGLE editor of the ready set,
    // [P23-F4]).
    // [P2-I15] The top-level V (rcVocab) is reused — no duplicate V2 copy.
    var readyUsed=rcReadyStatusUsed();
    h+='<div class="mb-2"><span class="text-xs text-gray-600 mr-1">Ready status (Story/Task)</span>'
      +rcSelCtl('rcSet_backlog_readyStatus', V.statuses, rcReadyStatusDisp())+'</div>';
    // [P23-F4] This panel is the single source for the ready status.
    h+='<div class="text-xs text-gray-400 mb-2">This is the single place where the ready status is edited (the set: ready used by Backlog Health).</div>';
    // [P23-F4] Transparency: a persisted MULTI-value ready set will be
    // collapsed to the chosen single value on save.
    var curReady=((rcDraft||RC_SETTINGS).statusSets||{}).ready||[];
    if(curReady.length>1){
      h+='<div class="mb-2 p-2 bg-amber-50 border border-amber-200 rounded text-xs text-amber-700">'
        +'Multiple ready statuses were previously configured; selecting a single value will replace them.</div>';
    }
    if(!readyUsed){
      // [P19-B3] The canonical reason string (single source with
      // rcMetricState('backlog').reason) — no quotes, no /defect.
      // [P23-F4] The editor is THIS panel now (Widget settings no longer
      // renders the ready set).
      h+='<div class="mb-2 p-2 bg-amber-50 border border-amber-200 rounded text-xs text-amber-700">'
        +'No ready status present in the project history. Assign the status that marks a story/task as ready to start in the Ready status selector above (set: ready).</div>';
    }
    h+='<div class="mb-2"><span class="text-xs text-gray-600 mr-1">Defects</span>'
      +rcSelCtl('rcSet_backlog_defects', ['exclude','auto','include'], m.defects||'exclude')
      +'<span class="text-xs text-gray-400 ml-1">'+(rcDefectReadySeen()
        ?'defect workflow uses a ready status — defects can be counted (auto/include).'
        :'no ready status in the defect workflow — defects are excluded (auto).')
      +' Default: excluded.</span></div>';
    // [P1-STATES] Live auto-result in the selector.
    var bhSt=rcMetricState('backlog');
    var bhAutoLbl = (m.denominator||'auto')==='auto'
      ? 'Auto (currently '+(bhSt.state==='velocity_sp'?'Velocity SP':'Throughput')+')'
      : 'Auto (choose based on data availability)';
    h+='<div class="mb-2"><span class="text-xs text-gray-600 mr-1">Team speed (denominator)</span>'
      +rcSelCtlLabeled('rcSet_backlog_denominator',
        [['auto',bhAutoLbl],['velocity_sp','Velocity SP (story points)'],['throughput','Throughput (issues)']],
        m.denominator||'auto')+'</div>'
      +'<div class="text-xs text-gray-400 mb-1">auto: Average Velocity (story points) per period only when the project has sprints AND story points (ready SP sum ÷ avg Velocity SP); with story points but no sprints — issue counts (ready issues ÷ avg Throughput per period), no mixed units; no story points — issues as well.</div>';
    h+='<div class="flex flex-wrap gap-2 items-center mb-2 text-sm">'
      +'<label class="text-xs text-gray-600">Healthy min '+rcSelCtl('rcSet_backlog_targetMin', ['0.5','1','1.5','2','2.5','3'], m.targetMin!==undefined?m.targetMin:2)+'</label>'
      +'<label class="text-xs text-gray-600">Healthy max '+rcSelCtl('rcSet_backlog_targetMax', ['2','2.5','3','3.5','4','5'], m.targetMax!==undefined?m.targetMax:3)+'</label>'
      +'<span class="text-xs text-gray-400">sprints of ready backlog</span></div>';
  }
  if(mk==='incident'){
    h+='<div class="text-xs text-gray-400 mb-2">Production label and the severity map are edited in Widget settings (shared defaults; a metric-level map would override).</div>';
  }
  if(mk==='defectdensity'){
    // [FIX-A1] Density mode selector + read-only SP fill-rate indicator.
    // [P1-STATES] Descriptive option labels + the live auto-result.
    // [P7-DD] The auto per_item fallback is surfaced with an amber notice.
    var den=(PM_DATA.defectdensity||[]).filter(function(it){ return it.role==='denominator'; });
    var filled=den.filter(function(it){ return (it.sp||0)>0; }).length;
    var fr=den.length? Math.round(filled/den.length*100) : 0;
    var ddSt=rcMetricState('defectdensity');
    var ddAutoLbl = (m.densityMode||'auto')==='auto'
      ? 'Auto (currently '+(ddSt.state==='sp_weighted'?'per story point':'per item')+')'
      : 'Auto (choose based on data availability)';
    h+='<div class="mb-2"><span class="text-xs text-gray-600 mr-1">Density mode</span>'
      +rcSelCtlLabeled('rcSet_dd_mode',
        [['auto',ddAutoLbl],['per_sp','Per story point (#defects ÷ SP)'],['per_item','Per item (#defects ÷ #items)']],
        m.densityMode||'auto')
      +'<span class="text-xs text-gray-400 ml-1">auto: per_sp when the SP fill-rate ≥ 50%, else per_item.</span></div>';
    h+='<div class="mb-2 text-xs text-gray-500">SP fill-rate: <span class="font-mono">'+(den.length?Math.round(filled/den.length*100):0)+'%</span> ('+filled+' of '+den.length+' items)</div>';
    if(m.densityMode==='per_sp' && filled===0){
      h+='<div class="mb-2 text-xs text-amber-700">⚠ Forced SP-weighted state: no story points in the current window — the metric shows N/A (no count-formula fallback).</div>';
    }
    // [P7-DD] Auto-fallback notice: the engine switched to the count
    // denominator because the window carries no story points.
    if((m.densityMode||'auto')==='auto' && filled===0){
      h+='<div class="mb-2 text-xs text-amber-700">⚠ No story points found in the current window — the metric automatically uses the count-based denominator (#defects ÷ #(Story+Task)). To force N/A instead, choose "Per story point (#defects ÷ SP)" above.</div>';
    }
  }
  if(mk==='velocity'){
    // [P1-STATES] Velocity state: issue counts (default) or story points.
    var vSt=rcMetricState('velocity');
    var velAutoLbl = (m.velocityMode||'auto')==='auto'
      ? 'Auto (currently '+(vSt.state==='sp'?'Story Point Velocity':'Issue Velocity')+')'
      : 'Auto (choose based on data availability)';
    h+='<div class="mb-2"><span class="text-xs text-gray-600 mr-1">Velocity mode</span>'
      +rcSelCtlLabeled('rcSet_vel_mode',
        [['auto',velAutoLbl],['items','Issue Velocity (issue counts)'],['sp','Story Point Velocity (story points)']],
        m.velocityMode||'auto')
      +'<span class="text-xs text-gray-400 ml-1">auto: Story Point Velocity when ≥ 50% of the completed items in the window carry story points, else issue counts.</span></div>';
    if(m.velocityMode==='sp' && !rcWindowHasSP()){
      h+='<div class="mb-2 text-xs text-amber-700">⚠ Forced Story Point Velocity: no story points in the current window — the metric shows N/A (no count fallback).</div>';
    }
  }
  if(mk==='bugfix'){
    // [FIX-A5] Read-only timespent fill-rate + the fixed allocation mode.
    var bf=(PM_DATA.bugfix||[]);
    var withTs=bf.filter(function(it){ return (it.timeSpent||0)>0; }).length;
    var bfr=bf.length? Math.round(withTs/bf.length*100) : 0;
    h+='<div class="mb-2"><span class="text-xs text-gray-600 mr-1">Aggregation</span>'
      +'<span class="text-xs font-mono text-gray-500">allocation (fixed)</span></div>';
    h+='<div class="mb-2 text-xs text-gray-500">Timespent fill-rate: <span class="font-mono">'+bfr+'%</span> ('+bf.filter(function(it){return (it.timeSpent||0)>0;}).length+' of '+bf.length+' items)'
      +(bfr>=20?'':' — below 20%: the metric shows N/A (no worklog).')+'</div>';
  }
  // [P4-3] Defect Escape Rate: two label selects (offered from the labels
  // actually present on the metric's bug-typed items) + the live N/A reason.
  if(mk==='escapereview'){
    var bugLbls={};
    (RC_RAW||[]).forEach(function(r){
      // Only the labels found on the metric's bug-typed items (user decision).
      if(!effTypes(m.types).some(function(t){ return String(t).toLowerCase()===String(r.type).toLowerCase(); })) return;
      String(r.labels||'').split(',').forEach(function(l){
        l=l.trim(); if(l) bugLbls[l]=1;
      });
    });
    var bugLblList=Object.keys(bugLbls).sort();
    var erSt=rcMetricState('escapereview');
    h+='<div class="mb-2"><div class="text-xs text-gray-500 mb-1">Label marking defects found in code review</div>'
      +'<select id="rcSet_er_reviewLabel" class="border rounded px-1 py-0.5 text-xs" onchange="rcPanelChanged()">'
      +'<option value=""'+(!m.reviewLabel?' selected':'')+'>— not selected —</option>'
      +bugLblList.map(function(l){ return '<option value="'+rcEsc(l)+'"'+(m.reviewLabel===l?' selected':'')+'>'+rcEsc(l)+'</option>'; }).join('')
      +'</select></div>';
    h+='<div class="mb-2"><div class="text-xs text-gray-500 mb-1">Label marking defects found in QA</div>'
      +'<select id="rcSet_er_qaLabel" class="border rounded px-1 py-0.5 text-xs" onchange="rcPanelChanged()">'
      +'<option value=""'+(!m.qaLabel?' selected':'')+'>— not selected —</option>'
      +bugLblList.map(function(l){ return '<option value="'+rcEsc(l)+'"'+(m.qaLabel===l?' selected':'')+'>'+rcEsc(l)+'</option>'; }).join('')
      +'</select></div>';
    if(erSt.state==='na' && erSt.reason){
      h+='<div class="mb-2 p-2 bg-amber-50 border border-amber-200 rounded text-xs text-amber-700">'+rcEsc(erSt.reason)+'</div>';
    }
  }
  // [P4-4] Design Review Turnaround: two status single-selects.
  if(mk==='designreview'){
    var drSt=rcMetricState('designreview');
    h+='<div class="mb-2"><div class="text-xs text-gray-500 mb-1">Design start status</div>'
      +'<select id="rcSet_dr_designStart" class="border rounded px-1 py-0.5 text-xs" onchange="rcPanelChanged()">'
      +'<option value=""'+(!m.designStart?' selected':'')+'>— not selected —</option>'
      +V.statuses.map(function(s){ return '<option value="'+rcEsc(s)+'"'+(m.designStart===s?' selected':'')+'>'+rcEsc(rcDispStatus(s))+'</option>'; }).join('')
      +'</select></div>';
    h+='<div class="mb-2"><div class="text-xs text-gray-500 mb-1">Review done status</div>'
      +'<select id="rcSet_dr_reviewDone" class="border rounded px-1 py-0.5 text-xs" onchange="rcPanelChanged()">'
      +'<option value=""'+(!m.reviewDone?' selected':'')+'>— not selected —</option>'
      +V.statuses.map(function(s){ return '<option value="'+rcEsc(s)+'"'+(m.reviewDone===s?' selected':'')+'>'+rcEsc(rcDispStatus(s))+'</option>'; }).join('')
      +'</select></div>';
    if(drSt.state==='na' && drSt.reason){
      h+='<div class="mb-2 p-2 bg-amber-50 border border-amber-200 rounded text-xs text-amber-700">'+rcEsc(drSt.reason)+'</div>';
    }
  }
  host.innerHTML=h;
}
// Collect the panel's current control values into a settings patch
// (used by rcPanelChanged to update the live draft).
function rcCollectPanel(){
  // [P2-I15] The metric patch is declared ONCE (the old dead `var m={}`
  // before the real one is removed).
  var mk=rcMetric, user={statusSets:{},metrics:{}};
  function checkedVals(prefix){
    var out=[];
    Array.prototype.forEach.call(
      document.querySelectorAll('input[id^="'+prefix+'"]:checked'),
      function(cb){ out.push(cb.value); });
    return out;
  }
  // NOTE: status sets are collected by rcCollectWidgetPanel (Widget
  // settings) — collecting them here from the (no longer rendered)
  // rcSetSt_ checkboxes would WIPE the committed sets with empty lists.
  var m={types:checkedVals('rcSetTy_'+mk+'_')};
  // [P0-2] aggregation is a fixed semantic property — not read from the UI.
  var th=rcVal('rcSet_'+mk+'_stablePct');
  if(th!==undefined&&th!==''){ var f=parseFloat(th); if(!isNaN(f)) m.stablePct=f; }
  var dn=rcVal('rcSet_'+mk+'_defaultN');
  if(dn!==undefined&&dn!==''){ var i2=parseInt(dn,10); if(!isNaN(i2)) m.defaultN=i2; }
  if(mk==='wip'){
    // [P1-3] WIP mode (total | per_developer).
    var wm=rcVal('rcSet_wip_wipMode');
    if(wm!==undefined&&wm!=='') m.wipMode=wm;
  }
  if(mk==='backlog'){
    // Ready status: assign the status that marks work ready to start
    // (single-select from the project's statuses; stored in the 'ready'
    // status set — the membership set of this metric).
    var rs=rcVal('rcSet_backlog_readyStatus');
    if(rs!==undefined&&rs!==''){ user.statusSets.ready=[rs]; }
    var dv=rcVal('rcSet_backlog_defects');
    if(dv!==undefined&&dv!=='') m.defects=dv;
    var dv2=rcVal('rcSet_backlog_denominator');
    if(dv2!==undefined&&dv2!=='') m.denominator=dv2;
    var tmi=rcVal('rcSet_backlog_targetMin'), tma=rcVal('rcSet_backlog_targetMax');
    if(tmi!==undefined&&tmi!==''){ var f1=parseFloat(tmi); if(!isNaN(f1)) m.targetMin=f1; }
    if(tma!==undefined&&tma!==''){ var f2=parseFloat(tma); if(!isNaN(f2)) m.targetMax=f2; }
  }
  if(mk==='defectdensity'){
    // [FIX-A1] Density mode (per_sp / per_item / auto).
    var dm=rcVal('rcSet_dd_mode');
    if(dm!==undefined&&dm!=='') m.densityMode=dm;
  }
  if(mk==='velocity'){
    // [P1-STATES] Velocity state (auto / items / sp).
    var vm3=rcVal('rcSet_vel_mode');
    if(vm3!==undefined&&vm3!=='') m.velocityMode=vm3;
  }
  // [P4-3] Escape-rate labels (single-selects; empty = N/A state).
  if(mk==='escapereview'){
    var erRl=rcVal('rcSet_er_reviewLabel');
    if(erRl!==undefined) m.reviewLabel=erRl;
    var erQl=rcVal('rcSet_er_qaLabel');
    if(erQl!==undefined) m.qaLabel=erQl;
  }
  // [P4-4] Design Review Turnaround statuses.
  if(mk==='designreview'){
    var ds2=rcVal('rcSet_dr_designStart');
    if(ds2!==undefined) m.designStart=ds2;
    var rd2=rcVal('rcSet_dr_reviewDone');
    if(rd2!==undefined) m.reviewDone=rd2;
  }
  user.metrics[mk]=m;
  // NOTE: workflow status sets, production label, severity map and the Team
  // dimension moved to Widget settings (rcCollectWidgetPanel) — this panel
  // collects only metric-specific controls.
  return user;
}
function rcUpdateFormula(){
  var f=document.getElementById('rcFormulaText');
  if(f) f.innerHTML=rcEsc(rcFormulaText(rcMetric, rcDraft||RC_SETTINGS));
  var tr=document.getElementById('rcTrendRule');
  if(tr) tr.innerHTML=rcEsc(rcTrendRule(rcMetric, rcDraft||RC_SETTINGS));
}
function rcAnchorChanged(i){
  if(!rcDraft) return;
  var anchors=rcMetricAnchors(rcMetric);
  if(!anchors[i]) return;
  var kind=rcVal('rcSetAncKind_'+i);
  var spec=anchors[i].spec;
  if(kind==='created') spec={kind:'field', field:'created'};
  else if(kind==='resolutiondate') spec={kind:'field', field:'resolutiondate'};
  else spec={kind:'status', set:(spec&&spec.set)||'devStart'};
  rcDraftSetAnchor(rcMetric, anchors[i].path, spec);
  rcSettingsRender();   // show/hide the set select + refresh formula
}
function rcAnchorSetChanged(i){
  var sn=rcVal('rcSetAncSet_'+i);
  var anchors=rcMetricAnchors(rcMetric);
  if(!anchors[i]||sn===undefined) return;
  var spec=JSON.parse(JSON.stringify(anchors[i].spec));
  spec.set=sn;
  rcDraftSetAnchor(rcMetric, anchors[i].path, spec);
  rcSettingsRender();
}
function rcDraftSetAnchor(mk, path, spec){
  var m=(rcDraft.metrics=rcDraft.metrics||{})[mk]
        ||((rcDraft.metrics||{})[mk]={});
  var o=m;
  for(var i=0;i<path.length-1;i++){
    if(!o[path[i]]||typeof o[path[i]]!=='object') o[path[i]]={};
    o=o[path[i]];
  }
  o[path[path.length-1]]=spec;
}
// [P0-B7] Any control change: PATCH-MERGE the current draft — only the
// CURRENT metric's patch (user.metrics[mk]) and the shared statusSets (when
// present) are merged into the existing draft. Edits made earlier for other
// metrics in the same open-panel session accumulate instead of being wiped
// by a full rebuild from rcDraftBase. Closing without Apply still discards
// everything (rcDraft is dropped); Reset/Export/Import are unchanged.
function rcPanelChanged(){
  if(!rcDraft) return;
  var patch=rcCollectPanel();
  var next=JSON.parse(JSON.stringify(rcDraft));
  if(patch.metrics && patch.metrics[rcMetric]){
    next.metrics=next.metrics||{};
    next.metrics[rcMetric]=rcMergeSettings(next.metrics[rcMetric]||{}, patch.metrics[rcMetric]);
  }
  if(patch.statusSets && Object.keys(patch.statusSets).length){
    next.statusSets=rcMergeSettings(next.statusSets||{}, patch.statusSets);
  }
  rcDraft=next;
  rcUpdateFormula();
}
// Apply: commit the draft (re-derive + persist) and close the panel.
function rcSettingsApply(){
  if(!rcDraft) rcDraft=JSON.parse(JSON.stringify(RC_SETTINGS));
  RC_SETTINGS=rcDraft;
  rcSettingsSave();
  // [P1-I9] The metric-settings types changed → drop the session memory
  // for this metric so the new default seeds the checkboxes.
  if(typeof rcTypeMemReset==='function'){ rcTypeMemReset(rcMetric); }
  // [P1-I10] The committed settings may change the default window →
  // clear the per-metric calendar flag so the default re-syncs.
  if(typeof rcCalTouchedMemReset==='function'){ rcCalTouchedMemReset(); }
  rcRebuildData();
  rcSetMetric(rcMetric);
  rcSettingsClose();
  rcDraft=null; rcDraftBase=null;
}
function rcVal(id){
  var el=document.getElementById(id);
  return el?el.value:undefined;
}
function rcSettingsReset(){
  RC_SETTINGS=JSON.parse(JSON.stringify(RC_SETTINGS_DEFAULT));
  try{ window.localStorage.removeItem(RC_LS_KEY); }catch(e){}
  // [P1-I9]/[P1-I10] Reset restores the defaults: drop the session type
  // memory and the per-metric calendar-touched flags.
  if(typeof rcTypeMemReset==='function'){ rcTypeMemReset(); }
  if(typeof rcCalTouchedMemReset==='function'){ rcCalTouchedMemReset(); }
  rcRebuildData();
  rcSetMetric(rcMetric);
  rcSettingsClose();
}
function rcSettingsExport(){
  var blob=new Blob([JSON.stringify(RC_SETTINGS,null,2)],{type:'application/json'});
  var a=document.createElement('a');
  a.href=URL.createObjectURL(blob);
  a.download='metric-settings.json';
  document.body.appendChild(a); a.click(); a.remove();
}
function rcSettingsImport(){
  var inp=document.createElement('input');
  inp.type='file'; inp.accept='.json,application/json';
  inp.onchange=function(){
    var f=inp.files[0]; if(!f) return;
    var rd=new FileReader();
    rd.onload=function(){
      try{
        var user=JSON.parse(rd.result);
        RC_SETTINGS=rcMergeSettings(RC_SETTINGS_DEFAULT, user);
        rcSettingsSave();
        rcRebuildData();
        rcSetMetric(rcMetric);
        rcSettingsClose();
      }catch(e){ alert('Import failed: '+e.message); }
    };
    rd.readAsText(f);
  };
  inp.click();
}
"""
