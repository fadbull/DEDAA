"""Chart render pipeline (rcApply), issues table, boot chain."""

RENDER_JS = """function rcApply(){
  // Timeline selection: custom From/To calendar range, else the last N buckets
  // of the selected granularity (Sprint -> last 5, others -> last active one).
  var fromInput=document.getElementById('rcFrom').value;
  var toInput=document.getElementById('rcTo').value;
  var hasCustom = fromInput || toInput;
  var from=null, to=null;
  if(fromInput&&toInput){ from=new Date(fromInput+'T00:00:00'); to=new Date(toInput+'T23:59:59'); }
  else if(fromInput){ from=new Date(fromInput+'T00:00:00'); to=null; }
  else if(toInput){ from=null; to=new Date(toInput+'T23:59:59'); }
  // [P1-2] Guard: an empty select (or a mock without a default) falls back
  // to the widget's default granularity (sprint) instead of producing a
  // 12-month step and an empty window.
  var gran=document.getElementById('rcPeriods').value || 'sprint';
  var dim=document.getElementById('rcDim').value;
  var sel=rcSelected();
  var typeSel=rcTypeSelected();
  var cfg=RC_CFG[rcMetric];
  // [P0-2] Effective metric settings: the gear-panel values (rcDraft or the
  // committed RC_SETTINGS) win over the static display config.
  var mEff=((rcDraft||RC_SETTINGS).metrics||{})[rcMetric]||{};
  var periodContext=rcSprintContext(gran,from,to,rcCalTouchedCur());
  Array.prototype.forEach.call(document.getElementById('rcPeriods').options||[],function(option){
    if(option.value==='sprint') option.textContent=rcSprintSource(rcDraft||RC_SETTINGS)?'Sprint (Jira)':'Sprint (2 weeks)';
  });
  if(periodContext.real){
    from=null; to=null;
    if(!rcCalTouchedCur()){
      var calendarWindow=periodContext.window;
      document.getElementById('rcFrom').value=calendarWindow?rcDateStr(calendarWindow.from):'';
      document.getElementById('rcTo').value=calendarWindow?rcDateStr(calendarWindow.to):'';
    }
  }
  var items=rcActiveItems();
  var isCoverage = cfg.aggregation==='coverage';
  var isWipSnap = cfg.aggregation==='wipSnapshot';   // [FIX-A4]
  var isAlloc = cfg.aggregation==='allocation';      // [FIX-A5] timespent share
  var isClarcycle = rcMetric==='clarcycle';           // [FIX-P0-1]
  var isReviewcycle = rcMetric==='reviewcycle';       // [FIX-P0-1]
  function eventIncluded(it){
    if(periodContext.real) return periodContext.includes(it);
    var t=new Date(it.dev_start);
    return !isNaN(t)&&(!from||t>=from)&&(!to||t<=to);
  }
  function readyFrom(it){
    var rf=(it.readyFrom!==undefined&&it.readyFrom!==null)?it.readyFrom:Date.parse(it.dev_start);
    if(it.readyFromUnverified){
      if(periodContext.real) rf=Math.max(rf,periodContext.cutoff);
      else if(from) rf=Math.max(rf,from.getTime());
    }
    return rf;
  }
  function snapshotIncluded(it,p){
    if(!rcPeriodSnapshot(it,p,gran,periodContext)) return false;
    var E=rcPeriodEnd(p,gran,periodContext);
    if(isWipSnap) return it.enterDev!==null&&it.enterDev!==undefined&&
      it.enterDev<=E&&(it.leaveDev===null||it.leaveDev===undefined||it.leaveDev>E);
    return readyFrom(it)<=E&&(it.readyLeft===null||it.readyLeft===undefined||it.readyLeft>E);
  }
  function windowIncluded(it){
    if(periodContext.real&&(isCoverage||isWipSnap)){
      return periodContext.periods.some(function(p){ return snapshotIncluded(it,p.id); });
    }
    return eventIncluded(it);
  }
  var agg={}, seriesAgg=null, groupAgg=null;
  var isFlow = cfg.aggregation==='flow';
  var isGrouped = cfg.aggregation==='grouped';
  if(isFlow){ seriesAgg={}; }
  if(isGrouped){ groupAgg={}; }
  // [P10-P0-1] The snapshot inputs must describe the population the chart
  // is drawn from — a dim/type/calendar-filtered copy of items. The
  // aggregation loop below keeps iterating the raw `items` (metric-specific
  // interval rules); only the STATE computation reads filteredItems.
  var filteredItems = items.filter(function(it){
    if(!rcDimMatch(it, dim, sel)) return false;
    if(typeSel && !typeSel[rcTypeLabel(it.type)]) return false;
    if(periodContext.real) return windowIncluded(it);
    var t=new Date(it.dev_start);
    if(from && t<from) return false;
    if(to && t>to) return false;
    return true;
  });
  // [P10-P0-2] The Backlog Health coverage decision is computed inside the
  // isCoverage block below; hoisted here so the snapshot (committed after
  // that block) can carry it.
  var covUseSP = null, covSPMissing = '', hasSPReady = false, hasSPDen = false;
  // [FIX-A1] Defect Density effective mode + SP fill-rate (denominator
  // role = Story/Task items in the window).
  var ddMode=null, ddFillRate=0, ddFilled=0, ddTotal=0;
  var ddForcedNA=false;
  // [P10-P0-1] The ddMode/fill computation reads the FILTERED items — the
  // state must describe the population the chart is drawn from.
  var isDensity = rcMetric==='defectdensity' && cfg.rateMode==='spDensity';
  if(isDensity){
    var mDD=((rcDraft||RC_SETTINGS).metrics||{})[rcMetric]||{};
    var denItems=filteredItems.filter(function(it){ return it.role==='denominator'; });
    ddTotal=denItems.length;
    ddFilled=denItems.filter(function(it){ return (it.sp||0)>0; }).length;
    ddFillRate=ddTotal? ddFilled/ddTotal : 0;
    ddMode = mDD.densityMode==='per_item' ? 'per_item'
           : mDD.densityMode==='per_sp' ? 'per_sp'
           : (ddTotal && ddFilled/ddTotal>=0.5 ? 'per_sp' : 'per_item');
    // [P1-STATES] Forced SP-weighted with no story points in the window →
    // the metric shows N/A (empty chart, no count-formula fallback).
    ddForcedNA = (mDD.densityMode==='per_sp' && ddFilled===0);
  }
  // [P10-P0-1] The local RC_HAS_TIMESPENT IIFE is REMOVED — it iterated the
  // raw items and duplicated the snapshot's hasTimespent. The single source
  // is RC_WIN_STATE.hasTimespent (built from filteredItems below); the two
  // N/A readers use it.
  // Backlog Health (coverage): ready intervals + team-speed denominators.
  var covReady=[];   // {rf, rl} ready intervals of the filtered items
  var covDen={};     // per-period team speed: {sp: sum SP completed, n: count}
  var wipItems=[];   // [FIX-A4] filtered WIP snapshot items
  var usedKeys={};  // unique issue keys participating in this calculation
  var velSP={};    // [P24-D] Velocity: story points per bucket
  items.forEach(function(it){
    if(!rcDimMatch(it, dim, sel)) return;
    if(typeSel && !typeSel[rcTypeLabel(it.type)]) return;
    if(periodContext.real&&!windowIncluded(it)) return;
    // [P5-WIP] WIP snapshot: the item participates at every bucket end
    // inside [enterDev, leaveDev) — the same interval-overlap rule the
    // per-period aggregation below applies. The shared dev_start window
    // filter does NOT apply (an item that entered dev before the window
    // start and is still open is IN WIP at the window's bucket ends).
    if(isWipSnap){
      var eD=it.enterDev;
      var lD=it.leaveDev;
      if(eD===null||eD===undefined) return;
      if(to && eD>to.getTime()) return;
      if(from && lD!==null && lD!==undefined && lD<=from.getTime()) return;
      usedKeys[it.key]=1;
      wipItems.push(it);
      return;
    }
    // [P0-B1] Coverage (Backlog Health) must NOT apply the shared
    // dev_start window filter: an item that became ready BEFORE the window
    // start and is still ready inside it participates at every control
    // point. The item survives when its ready interval overlaps the
    // window [from, to]: rf <= to && (rl === null || rl > from).
    // usedKeys is set only AFTER the overlap check.
    if(isCoverage){
      var rf=readyFrom(it);
      var rl=(it.readyLeft===null||it.readyLeft===undefined)?null:it.readyLeft;
      // [P1v3-1c] "Currently ready, no transition event": the readiness
      // start is NOT event-verified (derive fell back to the creation date).
      // Clamp it to the window start so the item contributes only from the
      // current window onward — never to earlier historical periods.
      if(it.readyFromUnverified && from && rf<from.getTime()) rf=from.getTime();
      // Ready-interval overlap with the window [from, to]:
      //   rf <= to  (became ready no later than the window end)
      //   rl === null (still ready) OR rl > from (left ready inside/after it)
      if(to && rf>to.getTime()) return;
      if(from && rl!==null && rl<=from.getTime()) return;
      usedKeys[it.key]=1;
      covReady.push({it:it, rf:rf, rl:rl, sp:(it.sp!==undefined&&it.sp!==null)?it.sp:0});
      return;
    }
    var t=new Date(it.dev_start);
    if(from&&t<from) return;
    if(to&&t>to) return;
    usedKeys[it.key]=1;
    var key=rcPeriodKey(it, gran, periodContext);
    if(isFlow){
      var s=it.series||'opened';
      if(!seriesAgg[s]) seriesAgg[s]={};
      if(!seriesAgg[s][key]) seriesAgg[s][key]=0;
      seriesAgg[s][key]++;
      return;
    }
    if(isGrouped){
      var g=it[cfg.field]||'Other';
      if(!groupAgg[key]) groupAgg[key]={};
      if(!groupAgg[key][g]) groupAgg[key][g]=0;
      groupAgg[key][g]++;
      return;
    }
    if(cfg.rateMode==='spDensity'){
      // [FIX-A1] Defect Density (role-based): per_sp weights by story
      // points, per_item by issue count; value = n ÷ total (raw ratio).
      // [P7-DD] Architecture rule: the numerator is ALWAYS the COUNT of
      // defects found in QA. Story points apply ONLY to the denominator
      // (SP of completed Story/Task). per_item uses a count denominator
      // (1 per completed work item) — the metric therefore works on
      // projects with no story points.
      if(!agg[key]) agg[key]={n:0,total:0};
      if(it.role==='numerator')   agg[key].n     += 1;
      if(it.role==='denominator') agg[key].total += (ddMode==='per_sp' ? (it.sp||0) : 1);
      return;
    }
    if(cfg.rateMode==='roles'){
      // [FIX-A2] Leakage: numerator = prod-labelled bugs, denominator =
      // bugs entered QA or prod-labelled; value = n/total×100 (%).
      if(!agg[key]) agg[key]={n:0,total:0};
      if(it.role==='numerator') agg[key].n++;
      if(it.role==='denominator') agg[key].total++;
      return;
    }
    if(isAlloc){
      // [FIX-A5] Bug Fixing Time Allocation: Σ(timespent bugs) ÷
      // Σ(timespent all completed work) × 100 per bucket.
      if(!agg[key]) agg[key]={n:0,total:0};
      if(it.role==='numerator')   agg[key].n     += (it.timeSpent||0);
      if(it.role==='denominator') agg[key].total += (it.timeSpent||0);
      return;
    }
    if(cfg.aggregation==='rate'){
      if(!agg[key]) agg[key]={n:0,total:0};
      agg[key].total++;
      if(it[cfg.field]) agg[key].n++;
    } else if(cfg.aggregation==='avg'){
      if(!agg[key]) agg[key]=[];
      // [P0-TYPES] Flow Efficiency items carry the raw day counts so the
      // avg box can compute the WEIGHTED mean (Σactive ÷ Σtotal × 100);
      // every other avg metric pushes the plain number.
      agg[key].push(rcMetric==='floweff' ? it : it[cfg.field]);
    } else if(cfg.aggregation==='sum'){
      if(!agg[key]) agg[key]=0;
      agg[key]+=it[cfg.field];
    } else { // count
      if(!agg[key]) agg[key]=0;
      // [P1-STATES] Velocity: count issues here and collect the story points
      // separately. [P24-D] The SP/items state is resolved AFTER the window
      // snapshot (RC_WIN_STATE) — reading it here used the PREVIOUS pass's
      // snapshot, so the bars could be SP while the label said items.
      agg[key]++;
      if(rcMetric==='velocity'){ velSP[key]=(velSP[key]||0)+(it.sp||0); }
    }
  });
  // ---- Backlog Health (coverage): team-speed denominator ------------------
  // BH(P) = ready(P) ÷ avg team speed per period, where
  //   ready(P) = # items ready at the period end P (snapshot), and
  //   avg team speed = Average Velocity (story points) per period — used
  //   ONLY when the project has sprints AND story points (numerator = SP
  //   sum of the ready items); fallback: Average Throughput (issues) per
  //   period when the project has no sprints or no story points
  //   (denominator: auto|velocity_sp|throughput).
  if(isCoverage){
    // denominator=auto: Average Velocity (story points) per period is used
    // ONLY when the project has sprints AND story points — the numerator is
    // then the SP SUM of the ready items (SP ÷ SP, consistent units). When
    // the project has story points but NO sprints (or no SP at all), the
    // calculation falls back to issue counts (ready issues ÷ avg
    // Throughput issues per period) to avoid mixing units.
    // [P1v3-1a] BOTH sides must carry story points: the ready side AND the
    // completed velocity items of the window. A one-sided SP presence no
    // longer enables SP coverage (it produced an all-zero denominator).
    // [P9-P2-3] hasSPReady applies the SAME filters the per-period readySP
    // summation applies (dimension + top Issue Type checkboxes) — otherwise
    // a Story-with-SP in the pool keeps SP mode alive after the user
    // unchecks Story. hasSPDen applies the SAME type filter the covDen
    // computation uses (BH_DEN_TYPES = Story/Task/Defect) — a Test item
    // with SP must not flip the auto mode when the denominator loop
    // excludes it.
    // [P12-P2] hasSPReady reads covReady — the numerator intervals that
    // actually PARTICIPATE in the calculation (built in the filter loop
    // above with the real window-overlap rules), so the SP check is
    // window-scoped exactly like hasSPDen.
    var hasSPReady=covReady.some(function(iv){ return (iv.sp||0)>0; });
    var hasSPDen=(PM_DATA.velocity||[]).some(function(v){
      if(!eventIncluded(v)) return false;
      var t=new Date(v.dev_start);
      if(isNaN(t)) return false;
      if(from&&t<from) return false;
      if(to&&t>to) return false;
      if(!rcDimMatch(v, dim, sel)) return false;
      if(!{Story:1,Task:1,Defect:1}[rcTypeLabel(v.type)]) return false;
      return (v.sp||0)>0;
    });
    // [P0-2] denominator is read from the METRIC SETTINGS (auto|velocity_sp|
    // throughput) — cfg (RC_CFG) never carried this field, so the selector
    // had no effect before.
    var denEff=(mEff.denominator||'auto');
    // Resolve from effective settings, never a previous window snapshot.
    var sprGate=rcSprintSource(rcDraft||RC_SETTINGS);
    covUseSP = denEff==='velocity_sp' ? true
             : denEff==='throughput' ? false
             : (hasSPReady && hasSPDen && sprGate);
    // [P1v3-1a] Either side missing SP → the forced SP mode is NOT
    // computable (N/A with the reason — no silent fallback).
    covSPMissing = (denEff==='velocity_sp') ? (!hasSPReady ? 'ready' : (!hasSPDen ? 'completed velocity' : ''))
                  : '';
    // Per-period team speed from the velocity items (SP) or throughput count.
    // [P2-I17] The team speed is a TEAM characteristic — it must NOT follow
    // the Backlog Health numerator's type selection. The denominator uses
    // the FIXED velocity type set (Story, Task, Defect — the same default
    // the Issue Velocity metric uses); the calendar and dimension filters
    // still apply (they shape the window, not "what counts as work").
    var BH_DEN_TYPES={Story:1,Task:1,Defect:1};
    (PM_DATA.velocity||[]).forEach(function(v){
      if(!eventIncluded(v)) return;
      var t=new Date(v.dev_start);
      if(isNaN(t)) return;
      if(from&&t<from) return;
      if(to&&t>to) return;
      if(!rcDimMatch(v, dim, sel)) return;
      if(!BH_DEN_TYPES[rcTypeLabel(v.type)]) return;
      // [P1v3-1d] The denominator items participate in the calculation —
      // they enter the issues table alongside the ready items.
      usedKeys[v.key]=1;
      var k=rcPeriodKey(v, gran, periodContext);
      if(!covDen[k]) covDen[k]={spSum:0,n:0};
      covDen[k].n++;
      covDen[k].spSum+=(v.sp||0);
    });
  }
  // [P10-P0-1] The window snapshot is committed HERE — after the coverage
  // block (covUseSP/covSPMissing/hasSPReady/hasSPDen) and before the N/A
  // flags — so every state reader (rcMetricState / rcWindowHasSP /
  // rcHasTimespent / tooltip / title / y-axis / settings panel / conclusion)
  // sees the FILTERED-window state, including the Backlog Health decision.
  // Recomputed on EVERY rcApply; before the first rcApply the readers fall
  // back to the global recompute (boot fallback).
  RC_WIN_STATE = (function(){
    var mS=((rcDraft||RC_SETTINGS).metrics||{})[rcMetric]||{};
    // [P6-B4]/[P10-P0-1] Window-filtered state inputs: hasTimespent comes
    // from filteredItems (not the global population). hasSP keeps the
    // velocity-pool semantics (the completed velocity items the coverage
    // denominator uses — P1-1a): the raw `items` array is the CURRENT
    // metric's pool (for Backlog Health those are ready items whose SP must
    // not flip the forced-SP N/A rule), so the global velocity pool with
    // the dim/type selection is the correct window-scoped source here.
    var hasSP=(PM_DATA.velocity||[]).some(function(v){
      if(!eventIncluded(v)) return false;
      if((v.sp||0)<=0) return false;
      // [P22-T3] The snapshot must be window-scoped: SP outside the
      // from/to calendar range must not flip the forced-SP N/A rule.
      var tv=new Date(v.dev_start);
      if(isNaN(tv)) return false;
      if(from&&tv<from) return false;
      if(to&&tv>to) return false;
      if(!rcDimMatch(v, dim, sel)) return false;
      if(typeSel && !typeSel[rcTypeLabel(v.type)]) return false;
      return true;
    });
    // [P24-D] SP fill-rate of the window's velocity items (the auto rule:
    // Story Point Velocity only when ≥ 50% of the completed items carry
    // story points — the same 50% rule Defect Density uses).
    var velTot=0, velFilled=0;
    (PM_DATA.velocity||[]).forEach(function(v){
      if(!eventIncluded(v)) return;
      var tv=new Date(v.dev_start);
      if(isNaN(tv)) return;
      if(from&&tv<from) return;
      if(to&&tv>to) return;
      if(!rcDimMatch(v, dim, sel)) return;
      if(typeSel && !typeSel[rcTypeLabel(v.type)]){ return; }
      velTot++; if((v.sp||0)>0) velFilled++;
    });
    var bfIts=filteredItems.filter(function(it){ return it.timeSpent!==undefined; });
    var w2=0; bfIts.forEach(function(it){ if((it.timeSpent||0)>0) w2++; });
    var vm2=(((rcDraft||RC_SETTINGS).metrics||{}).velocity||{}).velocityMode||'auto';
    return {
      ddMode: ddMode, ddFillRate: ddFillRate, ddFilled: ddFilled, ddTotal: ddTotal,
      hasSP: hasSP,
      velSpFill: velTot ? velFilled/velTot : 0,
      sprintsAvail: rcSprintSource(rcDraft||RC_SETTINGS),
      periodSource: periodContext.real?'jira':'calendar',
      periodIds: periodContext.real?periodContext.periods.map(function(p){return p.id;}):[],
      velocityMode: vm2,
      hasTimespent: bfIts.length ? (w2/Math.max(1,bfIts.length)>=0.2) : false,
      // [P10-P0-2] The Backlog Health decision, computed in the isCoverage
      // block above from the FILTERED window — the single decision point.
      covUseSP: (typeof covUseSP === 'boolean') ? covUseSP : null,
      covSPMissing: (typeof covSPMissing === 'string') ? covSPMissing : '',
      hasSPReady: hasSPReady,
      hasSPDen: hasSPDen
    };
  })();
  // [P6-B4]/[P10-P0-1] The N/A flags run AFTER the snapshot commit —
  // rcMetricState / rcWindowHasSP now read the FRESH window state.
  var erNA = rcMetric==='escapereview' && !rcMetricState('escapereview').computable;
  var drNA = rcMetric==='designreview' && !rcMetricState('designreview').computable;
  // [P2v3-2] Review Cycle Count: N/A until at least one review status exists.
  var rcNA = rcMetric==='reviewcycle' && !rcMetricState('reviewcycle').computable;
  // [P19-B3] Backlog Health: N/A when no ready status exists in the history.
  var bhNA = rcMetric==='backlog' && !rcMetricState('backlog').computable;
  // [P24-D] Velocity in the Story Point state: the bars carry the SP sum
  // (resolved from the FRESH snapshot — the same state the label, axis and
  // Avg box read below).
  if(rcMetric==='velocity' && rcMetricState('velocity').state==='sp'){
    Object.keys(agg).forEach(function(k){ agg[k]=velSP[k]||0; });
  }
  // [P1-STATES] Velocity: forced SP state without story points → N/A.
  var vForcedNA = rcMetric==='velocity' && (function(){
    var vm=((rcDraft||RC_SETTINGS).metrics||{}).velocity||{};
    return vm.velocityMode==='sp' && !rcWindowHasSP();
  })();
  // [P24-A] The axis ALWAYS comes from the window (calendar range or the
  // shared default window) — never from the buckets that happen to carry
  // items, so empty periods stay visible and every metric shares the axis.
  var periods=[];
  var granLabel = periodContext.real?'Jira Sprint':(RC_GRAN_LABEL[gran] || 'Sprint (2 weeks)');
  var rangeUsed = false;
  if(periodContext.real){
    periods=periodContext.periods.map(function(p){return p.id;});
    rangeUsed=rcCalTouchedCur();
  } else if(hasCustom){
    // Calendar range applied: show a bar for EVERY bucket of the selected
    // granularity inside the range (X-axis = bucket timestamps).
    rangeUsed = true;
    var rangeFrom = from || null, rangeTo = to || null;
    if(!rangeFrom || !rangeTo){
      // Derive the missing side from the filtered items' date span.
      var minD=null, maxD=null;
      items.forEach(function(it){
        var t=new Date(it.dev_start);
        if(isNaN(t)) return;
        if(!rcDimMatch(it, dim, sel)) return;
        if(typeSel && !typeSel[rcTypeLabel(it.type)]) return;
        if(!minD||t<minD) minD=t;
        if(!maxD||t>maxD) maxD=t;
      });
      if(!rangeFrom && minD){ rangeFrom=rcBucketStart(minD, gran); }
      if(!rangeTo && maxD){ rangeTo=maxD; }
    }
    if(rangeFrom && rangeTo){
      periods = rcAxisRange(rangeFrom, rangeTo, gran);
    }
  } else {
    // [P24-A] No calendar: EVERY metric uses the same window — the last N
    // CONTIGUOUS periods ending at the project activity anchor
    // (rcProjectAnchor: last bucket with real project activity, stray late
    // events ignored). N = the metric's defaultN, else RC_DEFAULT_N.
    var effN=(mEff.defaultN!==undefined&&mEff.defaultN!==null)?mEff.defaultN:RC_DEFAULT_N;
    var anchorD=rcProjectAnchor(gran);
    if(!anchorD){
      items.forEach(function(it){
        var t=new Date(it.dev_start);
        if(!isNaN(t)&&(!anchorD||t>anchorD)) anchorD=t;
      });
    }
    periods = anchorD ? rcLastBucketKeys(anchorD, effN, gran) : [];
  }
  // ---- Backlog Health (coverage): per-period values -----------------------
  // BH(P) = ready(P) ÷ avg team speed per period:
  //   ready(P)  = # items ready AT the period end P (snapshot from the
  //               readyFrom/readyLeft intervals) — or their STORY POINT SUM
  //               when the Velocity (SP) denominator is active, so the
  //               units stay consistent (SP ÷ SP);
  //   team speed = Average Velocity in story points per period (only when
  //               the project has sprints AND story points) or Average
  //               Throughput (issues) per period otherwise (incl. the
  //               story-points-but-no-sprints case — no mixed units).
  // The box shows the AVG of the per-period BH values (control points).
  var covVals=null, covDenLabel='';
  // [P1v3-1e] Per-bucket computability: a control point is COMPUTABLE when
  // the ready snapshot > 0 AND the velocity denominator > 0. Bars always
  // carry a numeric value (0 when the ratio is not normalisable); the box
  // and the conclusion use the computable subset only.
  var covComputable=[];
  if(isCoverage){
    covVals = periods.map(function(p){
      // Period end timestamp for the snapshot.
      var pe=rcPeriodEnd(p, gran, periodContext);
      var ready=0, readySP=0;
      covReady.forEach(function(iv){
        if(!rcPeriodSnapshot(iv.it,p,gran,periodContext)) return;
        if(iv.rf<=pe && (iv.rl===null||iv.rl===undefined||iv.rl>pe)){
          ready++; readySP+=(iv.sp||0);
        }
      });
      var d=covDen[p]||{};
      var num   = covUseSP ? readySP : ready;
      var speed = covUseSP ? (d.spSum||0) : (d.n||0);
      // [P1v3-1e] Every bucket renders a NUMERIC value (0, never N/A):
      //   ready=0 → 0; ready>0 & velocity=0 → 0; both empty → 0.
      // The COMPUTABLE flag (ready>0 && speed>0) decides box/conclusion
      // membership — the trend line still uses every bucket.
      var computable = (num>0 && speed>0);
      covComputable.push(computable);
      if(!speed) return 0;
      return num/speed;
    });
    covDenLabel = covUseSP ? 'avg Velocity (SP)/period' : 'avg Throughput (issues)/period';
  }
  // ---- WIP (snapshot): per-period values ----------------------------------
  // [FIX-A4] wip(P) = |{ item : enterDev ≤ endOf(P) < leaveDev }| — a
  // point-in-time count at each bucket end (leaveDev=null => +∞). The
  // issues table lists every item that was in WIP at ≥1 bucket end.
  var wipVals=null;
  if(isWipSnap){
    // [P1-3] wipMode: 'total' (default) | 'per_developer'. In per_developer
    // mode each bucket value = WIP ÷ unique assignees among the in-WIP
    // items; zero assignees -> null (N/A), never a division by zero.
    var wipMode=((rcDraft||RC_SETTINGS).metrics||{}).wip &&
                ((rcDraft||RC_SETTINGS).metrics||{}).wip.wipMode || 'total';
    var wipPerDev=(wipMode==='per_developer');
    wipVals = periods.map(function(p){
      var endP=rcPeriodEnd(p, gran, periodContext);
      var cnt=0, devs={};
      wipItems.forEach(function(it){
        if(!rcPeriodSnapshot(it,p,gran,periodContext)) return;
        var eD=it.enterDev;
        if(eD===null||eD===undefined||eD>endP) return;
        if(it.leaveDev!==null&&it.leaveDev!==undefined&&it.leaveDev<=endP) return;
        usedKeys[it.key]=1;
        cnt++;
        if(wipPerDev && it.person) devs[it.person]=1;
      });
      if(wipPerDev){
        var devsN=Object.keys(devs).length;
        return devsN ? (cnt/devsN) : null;   // no assignees -> N/A
      }
      return cnt;
    });
  }
  // Resolve flow series keys/labels once (used by both the average box and the
  // flow chart branch). Flow series may be opened/resolved (Opened vs Resolved)
  // or new/resolved (Bug Growth).
  // [P24-A] FIXED series keys per metric — both series are always drawn
  // (0 in periods without items). The old data-driven pick fell back to
  // 'resolved' for BOTH series when the window held no opened items.
  var openKey = (rcMetric==='bugflow') ? 'new' : 'opened';
  var resolKey = 'resolved';
  var openLabel = openKey==='new' ? 'New' : 'Opened';
  var resolLabel = 'Resolved';
  // Weighted average over the selected window (top-right box).
  // avg-days: sum(days)/count(items); rate: total n / total total;
  // count: total per period / #periods; grouped: total per period / #periods;
  // flow: avg per period for each series (Opened/Resolved or New/Resolved).
  var avgEl=document.getElementById('rcAvgBox');
  function rcFmtAvg(v, unit){ return (Math.round(v*10)/10)+unit; }
  if(avgEl){
    var avgText='';
    if(isCoverage){
      // [P1v3-1e] The box = the arithmetic mean over the COMPUTABLE control
      // points only (ready>0 AND velocity>0). Zero bars render on the chart
      // but do NOT feed the average; the label states how many points fed it.
      var defined=[];
      covVals.forEach(function(v,i){ if(covComputable[i]) defined.push(v); });
      avgText = defined.length
        ? 'Avg: '+rcFmtAvg(defined.reduce(function(a,b){return a+b;},0)/defined.length,'')+' sprints (over '+defined.length+' computable control point'+(defined.length===1?'':'s')+')'
        : 'Avg: n/a';
    } else if(isFlow){
      var aSum=0,rSum=0;
      periods.forEach(function(p){ aSum+=(seriesAgg[openKey]?seriesAgg[openKey][p]||0:0); rSum+=(seriesAgg[resolKey]?seriesAgg[resolKey][p]||0:0); });
      avgText = periods.length
        ? 'Avg '+openLabel+': '+rcFmtAvg(aSum/periods.length,'')+' · Avg '+resolLabel+': '+rcFmtAvg(rSum/periods.length,'')
        : 'Avg: n/a';
    } else if(isGrouped){
      var totalSum=0; periods.forEach(function(p){ var s=0; Object.keys(groupAgg[p]||{}).forEach(function(g){ s+=groupAgg[p][g]; }); totalSum+=s; });
      // [P2-I14] The incident 0-state note is decided NUMERICALLY (periods
      // exist, the window total is zero) — not by string-matching the
      // formatted text. An empty window keeps the plain hidden n/a.
      if(rcMetric==='incident' && periods.length && totalSum===0){
        avgText = 'Avg: 0/period (0 prod-labelled bugs in window)';
      } else {
        avgText = periods.length ? 'Avg: '+rcFmtAvg(totalSum/periods.length,'')+'/period' : 'Avg: n/a';
      }
    } else if(isWipSnap){
      // [FIX-A4] Box = average snapshot WIP per period over the window.
      // [P22-T6] per_developer mode produces null buckets when no assignees
      // are present — nulls are NOT counted in the denominator.
      var wipDef=wipVals.filter(function(v){ return v!==null && v!==undefined; });
      avgText=wipDef.length
        ? 'Avg: '+rcFmtAvg(wipDef.reduce(function(a,b){return a+b;},0)/wipDef.length,'')+'/period'
        : 'Avg: n/a';
    } else if(cfg.rateMode==='spDensity'){
      // [FIX-A1] Defect Density box: weighted ratio over the window.
      // [P1-STATES] The unit label follows the ACTIVE state.
      // [P7-DD] The unit names the count numerator; the auto per_item
      // fallback is surfaced with the '(no SP in data)' note.
      if(ddForcedNA){
        avgText = 'n/a — no story points in data';
      } else {
        // [P24-D] Weighted over the COMPUTABLE periods only (denominator >
        // 0) — the same periods that carry a bar. Defects of a period
        // without completed work have no bar and must not feed the box.
        var dn2=0,dt2=0; periods.forEach(function(p){ if(agg[p]&&agg[p].total>0){ dn2+=agg[p].n||0; dt2+=agg[p].total; } });
        if(!dt2){
          avgText = 'Avg: n/a';
        } else {
          var unit = ddMode==='per_sp' ? ' defects/SP' : ' defects/item';
          var fallbackNote = (ddMode!=='per_sp' && ddFilled===0) ? ' (no SP in data)' : '';
          avgText = 'Avg: '+rcFmtAvg(dn2/dt2,'')+unit+fallbackNote;
        }
      }
    } else if(cfg.rateMode==='roles'||cfg.aggregation==='allocation'){
      var rn2=0,rt2=0; periods.forEach(function(p){ rn2+=(agg[p]&&agg[p].n)||0; rt2+=(agg[p]&&agg[p].total)||0; });
      // [P4-3] The escape-rate box names the quantity; [P3-1] the leakage
      // box names it too.
      var rateSuffix = rcMetric==='escapereview' ? ' (escaped review)'
                     : rcMetric==='leakage' ? ' (production leakage)' : '';
      avgText = rt2 ? 'Avg: '+rcFmtAvg(rn2/rt2*100,'%')+rateSuffix : 'Avg: n/a';
    } else if(cfg.aggregation==='rate'){
      var rn=0,rt=0; periods.forEach(function(p){ rn+=(agg[p]&&agg[p].n)||0; rt+=(agg[p]&&agg[p].total)||0; });
      avgText = rt ? 'Avg: '+rcFmtAvg(rn/rt*100,'%') : 'Avg: n/a';
    } else if(cfg.aggregation==='avg'){
      // [P0-1] The dead duplicate avg block (which read agg[p].n/.total —
      // fields that avg-metrics do not have, agg[p] is an ARRAY here) was
      // removed: it always produced 'Avg: n/a' and hid the box.
      // [P0-TYPES] Flow Efficiency: the tooltip promises the WEIGHTED mean
      // (Σ active days ÷ Σ total days × 100) — a plain mean of per-item
      // percentages diverges when items have different durations. The
      // items now carry active/total days (see derive), so the aggregate
      // ratio is computed directly. Bars/trend/conclusion stay per-period.
      if(rcMetric==='floweff'){
        // agg[p] holds the raw floweff ITEMS (not numbers) — read the
        // active/total day fields each item carries since [P0-TYPES].
        var faSum=0, ftSum=0;
        periods.forEach(function(p){ (agg[p]||[]).forEach(function(v){
          if(v && v.total!==undefined && v.total!==null){
            faSum+=(v.active||0); ftSum+=v.total;
          }
        }); });
        avgText = ftSum>0 ? 'Avg: '+rcFmtAvg(faSum/ftSum*100,'%') : 'Avg: n/a';
      } else {
      var allVals=[]; periods.forEach(function(p){ (agg[p]||[]).forEach(function(v){ allVals.push(v); }); });
      var sumVals=allVals.reduce(function(a,b){return a+b;},0);
      // Unit is per-metric: ' days' for time metrics, '%' for Flow Efficiency.
      // [P1-STATES] Issue Lead Time box carries the explicit unit label.
      var avgUnit = cfg.avg_unit !== undefined && cfg.avg_unit !== null ? cfg.avg_unit : ' days';
      if(rcMetric==='lead'){
        avgText = allVals.length ? 'Avg: '+rcFmtAvg(sumVals/allVals.length, avgUnit)+' (issue lead time)' : 'Avg: n/a';
      } else if(rcMetric==='designreview'){
        avgText = allVals.length ? 'Avg: '+rcFmtAvg(sumVals/allVals.length, avgUnit)+' (design review)' : 'Avg: n/a';
      // [P2v3-1/2] The count metrics name the population in the box label.
      } else if(rcMetric==='clarcycle'){
        avgText = allVals.length ? 'Avg: '+rcFmtAvg(sumVals/allVals.length, avgUnit)+' (over '+allVals.length+' requirement'+(allVals.length===1?'':'s')+')' : 'Avg: n/a';
      } else if(rcMetric==='reviewcycle'){
        avgText = allVals.length ? 'Avg: '+rcFmtAvg(sumVals/allVals.length, avgUnit)+' (over '+allVals.length+' reviewed item'+(allVals.length===1?'':'s')+')' : 'Avg: n/a';
      } else {
        avgText = allVals.length ? 'Avg: '+rcFmtAvg(sumVals/allVals.length, avgUnit) : 'Avg: n/a';
      }
      }
    } else { // count / sum
      // [P0-TYPES] Empty type selection -> n/a (not a misleading 0).
      // [P1-STATES] Velocity: unit follows the state (items vs SP); a forced
      // SP state without story points → n/a with the reason.
      var cntVals=0; periods.forEach(function(p){ cntVals+=(agg[p]||0); });
      if(rcMetric==='velocity'){
        var vSt=rcMetricState('velocity');
        if(vForcedNA){ avgText='n/a — no story points in data'; }
        else if(periods.length && cntVals>0){
          avgText = 'Avg: '+rcFmtAvg(cntVals/periods.length,'')+(vSt.state==='sp'? ' SP/period':' items/period');
        } else { avgText='Avg: n/a'; }
      } else if(rcMetric==='incident' && periods.length && cntVals===0){
        // [P2-I14] The 0-state note is decided NUMERICALLY (periods exist,
        // total is zero) — not by string-matching the formatted text, so a
        // rounding/locale change cannot break it. An empty window keeps the
        // plain hidden n/a (no zero-note).
        avgText = 'Avg: 0/period (0 prod-labelled bugs in window)';
      } else {
        avgText = (periods.length && cntVals>0) ? 'Avg: '+rcFmtAvg(cntVals/periods.length,'')+'/period' : 'Avg: n/a';
      }
    }
    avgEl.textContent = avgText;
    avgEl.classList.toggle('hidden', avgText.indexOf('n/a')>=0);
  }
  // [P24-C] Declared BEFORE the dataset branches that read them (they were
  // hoisted as undefined there).
  // [P0-TYPES] Empty type selection in the metric settings -> no conclusion
  // at all (uniform N/A behaviour). NOTE: an empty result caused by the
  // calendar/dimension filters still renders the trend conclusion (the
  // selection is legitimate — the metric simply has no data in range).
  var emptyTypes = Array.isArray(mEff.types) && mEff.types.length===0;
  // [P12-P4] The TOP Issue Type checkboxes may also be emptied — with
  // typeSel={} every item is skipped, the series is all-null and a flat
  // 0-trend would produce a false «Stable» verdict.
  var noTypesSelected = typeSel && Object.keys(typeSel).length===0;
  var labels=periodContext.real?periods.map(function(p){return periodContext.byId[p].label;}):periods;
  function completedValues(vals){
    return vals.map(function(v,i){return periodContext.partial[periods[i]]?null:v;});
  }
  var datasets=[], trend=null;
  var balTrend=null;   // [P0-3] single source of truth: flow trend = balance
  // [P1-I13] Issue Type dimension: one series per selected type. The
  // [P22-T7] The issuetype dimension was removed (a split, not a filter —
  // broken for role-based/flow/grouped/coverage/snapshot metrics). The
  // per-type second pass and the per-type dataset arm are gone; every
  // dimension renders through the single-series branch below.
  if(isFlow){
    // Guard both series lookups: a window may contain only one series (or
    // none after type/dimension filtering) — missing series render as 0.
    var openedVals=periods.map(function(p){return (seriesAgg[openKey]&&seriesAgg[openKey][p])||0;});
    var resolvedVals=periods.map(function(p){return (seriesAgg[resolKey]&&seriesAgg[resolKey][p])||0;});
    // [P0-3] ONE trend quantity for both the chart line and the conclusion:
    // the net balance (Resolved − Opened). The old ratio trend (opened ÷
    // resolved) could point the opposite way from the conclusion.
    var balance=openedVals.map(function(v,i){ return resolvedVals[i]-v; });
    balTrend=rcLinearTrend(completedValues(balance), true);
    var balLabel=(rcMetric==='bugflow') ? 'Trend (Resolved − New)' : 'Trend (Resolved − Opened)';
    datasets=[
      {type:'bar', label:openLabel, data:openedVals,
       backgroundColor:'rgba(37,99,235,0.6)', borderColor:'#2563eb', borderWidth:1},
      {type:'bar', label:resolLabel, data:resolvedVals,
       backgroundColor:'rgba(16,185,129,0.6)', borderColor:'#10b981', borderWidth:1}
    ];
    if(balTrend){ datasets.push({type:'line', label:balLabel, data:balTrend.line, borderColor:'#ef4444',
      borderDash:[6,4], fill:false, tension:0, pointRadius:0, borderWidth:2, yAxisID:'yBal'}); }
  } else if(isGrouped){
    // Stacked bars: one dataset per group (severity), counted per period.
    var groups = cfg.groups || ['Critical','Major','Minor'];
    var gcolors = cfg.colors || {};
    groups.forEach(function(g){
      var vals = periods.map(function(p){ return (groupAgg[p]&&groupAgg[p][g])||0; });
      datasets.push({type:'bar', label:g, data:vals,
        backgroundColor:(gcolors[g]||'#94a3b8')+'cc', borderColor:gcolors[g]||'#94a3b8',
        borderWidth:1, stack:'sev'});
    });
    // Total per period for the conclusion/trend.
    var totals = periods.map(function(p){ var s=0; groups.forEach(function(g){ s+=(groupAgg[p]&&groupAgg[p][g])||0; }); return s; });
    trend = rcLinearTrend(completedValues(totals));
    if(trend){ datasets.push({type:'line', label:'Trend', data:trend.line, borderColor:'#ef4444',
      borderDash:[6,4], fill:false, tension:0, pointRadius:0, borderWidth:2}); }
  } else if(isCoverage){
    // Backlog Health (coverage): bar per control point + healthy band
    // reference lines (2–3 sprints of ready backlog by default).
    var mS=((rcDraft||RC_SETTINGS).metrics||{})[rcMetric]||{};
    var tMin=(mS.targetMin!==undefined&&mS.targetMin!==null)?mS.targetMin:2;
    var tMax=(mS.targetMax!==undefined&&mS.targetMax!==null)?mS.targetMax:3;
    var bhVals=covVals.map(function(v){ return v===null?0:Math.round(v*100)/100; });
    trend=rcLinearTrend(completedValues(bhVals));
    datasets=[
      {type:'bar', label:cfg.label, data:bhVals,
       backgroundColor:cfg.color+'99', borderColor:cfg.color, borderWidth:1},
      {type:'line', label:'Healthy max ('+tMax+')', data:periods.map(function(){return tMax;}),
       borderColor:'#f59e0b', borderDash:[4,4], fill:false, pointRadius:0, borderWidth:1},
      {type:'line', label:'Min coverage ('+tMin+')', data:periods.map(function(){return tMin;}),
       borderColor:'#ef4444', borderDash:[6,4], fill:false, pointRadius:0, borderWidth:1}
    ];
    if(trend){ datasets.push({type:'line', label:'Trend', data:trend.line, borderColor:'#ef4444',
      borderDash:[6,4], fill:false, tension:0, pointRadius:0, borderWidth:2}); }
  } else if(isWipSnap){
    // [FIX-A4] WIP snapshot: one bar per bucket end (point-in-time count).
    // [P1-3] per_developer mode: value = WIP ÷ unique assignees per period.
    var wipMode=((rcDraft||RC_SETTINGS).metrics||{}).wip &&
                ((rcDraft||RC_SETTINGS).metrics||{}).wip.wipMode || 'total';
    var wipPerDev=(wipMode==='per_developer');
    trend=rcLinearTrend(completedValues(wipVals));
    datasets=[
      {type:'bar', label:cfg.label, data:wipVals,
       backgroundColor:cfg.color+'99', borderColor:cfg.color, borderWidth:1}
    ];
    if(wipPerDev){ datasets.push({type:'line', label:'≤ 1.5 per dev', data:periods.map(function(){return 1.5;}),
      borderColor:'#ef4444', borderDash:[2,3], fill:false, pointRadius:0, borderWidth:1.5}); }
    if(trend){ datasets.push({type:'line', label:'Trend', data:trend.line, borderColor:'#ef4444',
      borderDash:[6,4], fill:false, tension:0, pointRadius:0, borderWidth:2}); }
  // [P0-B5] The forced-SP N/A states of Defect Density and Velocity join
  // the same N/A render pattern (no zero-bars, no trend line).
  // [P10-P0-1] The single timespent source is the window snapshot.
  // [P10-P0-2] Backlog Health forced-SP with a missing side joins the same
  // N/A pattern (the snapshot carries covSPMissing).
  } else if((cfg.requires==='timeSpent' && !(RC_WIN_STATE&&RC_WIN_STATE.hasTimespent)) || erNA || drNA
            || ddForcedNA || vForcedNA || bhNA
            || (isCoverage && !!(RC_WIN_STATE&&RC_WIN_STATE.covSPMissing))){
    // [FIX-A5] Bug Fixing Time Allocation without worklog: render an empty
    // greyed-out chart (the metric stays in the list; the conclusion line
    // below shows the N/A reason). [P4-3]/[P4-4] The new metrics use the
    // same N/A pattern (labels/statuses not configured, or an empty window).
    // [P0-B5] Forced-SP without story points (Defect Density / Velocity)
    // uses the same pattern instead of drawing a misleading zero series.
    trend=null;
    datasets=[{type:'bar', label:cfg.label, data:periods.map(function(){return 0;}),
      backgroundColor:'rgba(148,163,184,0.25)', borderColor:'#94a3b8', borderWidth:1}];
  } else {
    // [P24-A] Count/sum metrics: a period without items is a measured 0
    // (nothing was completed), not a gap — the bars, Avg box, Δ and the
    // trend all read the same zero-filled series. Averages and rates keep
    // the gap (no items → no measurement).
    var zeroFill = (cfg.aggregation==='count'||cfg.aggregation==='sum') && !cfg.rateMode;
    var values=periods.map(function(p){
      var v=rcAggValue(cfg, agg[p]);
      return (zeroFill && (v===null||v===undefined)) ? 0 : v;
    });
    // [P0-TYPES] Empty type selection in the metric settings -> no trend
    // line (a flat 0-trend over an empty selection is misleading). An empty
    // result from the calendar/dimension filters keeps the trend.
    // [P12-P4] Same gate for the TOP Issue Type checkboxes: with every
    // checkbox unchecked the series is all-null — no trend, no verdict.
    var hasAnyValue=values.some(function(v){ return v!==null && v!==undefined; });
    trend = (emptyTypes || noTypesSelected || !hasAnyValue)
      ? null
      : rcLinearTrend(completedValues(values));
    datasets=[
      {type:'bar', label:(rcMetric==='velocity' ? rcMetricDisplayName('velocity') : cfg.label), data:values,
       backgroundColor:cfg.color+'99', borderColor:cfg.color, borderWidth:1}
    ];
    if(trend){ datasets.push({type:'line', label:'Trend', data:trend.line, borderColor:'#ef4444',
      borderDash:[6,4], fill:false, tension:0, pointRadius:0, borderWidth:2}); }
    // [P1-5] Healthy reference lines (NOT targets — static guidance levels).
    // Distinct style from the trend line: dash [2,3], width 1.5.
    // [P1-I13] Drawn ONCE per chart regardless of the number of type series.
    (RC_REF_LINES[rcMetric]||[]).forEach(function(r){
      datasets.push({type:'line', label:r.label, data:periods.map(function(){return r.level;}),
        borderColor:r.color, borderDash:[2,3], fill:false, pointRadius:0, borderWidth:1.5});
    });
  }
  // Conclusion — single-series: trend of the value itself.
  // Flow (Opened vs Resolved): trend of the net balance (resolved - opened).
  // A rising balance means resolved is catching up with opened => improving.
  // Backlog Health (coverage): BAND rule — value in [targetMin..targetMax]
  // sprints of coverage is healthy; below = under-stocked, above = over-stocked.
  // Flow (Opened vs Resolved): trend of the net balance (resolved - opened).
  // A rising balance means resolved is catching up with opened => improving.
  var conclEl=document.getElementById('rcConclusion');
  // [P24-C] Stable band (%) of the relative trend rule — the metric
  // settings win, the static config is the fallback (the SAME value
  // rcTrendRule renders in the tooltip).
  var stablePct=rcStablePct(rcMetric);
  var dirUp=((((RC_SETTINGS.metrics||{})[rcMetric]||{}).trendDir
              || cfg.trend_dir || 'down') === 'up');
  // [P1-4] Δ% = the LAST period of the window against the PREVIOUS
  // (adjacent) one. [P24-C] Never skips an empty period: when either of the
  // two has no data the Δ is n/a. prev=0 -> 'Δ n/a' (no division by zero).
  function rcDeltaPct(last, prev, dec){
    if(last===null||last===undefined||prev===null||prev===undefined) return 'Δ n/a';
    if(prev===0) return 'Δ n/a';
    var d=(last-prev)/prev*100;
    var s=d>=0?'+':'−';
    return 'Δ '+s+(Math.abs(d)).toFixed(dec===undefined?1:dec)+'% last vs prev period';
  }
  function rcLastTwo(vals){
    vals=completedValues(vals);
    if(!vals || vals.length<2) return null;
    return {last:vals[vals.length-1], prev:vals[vals.length-2]};
  }
  function rcDeltaText(vals, dec){
    var d=rcLastTwo(vals);
    return d ? rcDeltaPct(d.last, d.prev, dec) : '';
  }
  var trendOk=false;
  if((cfg.requires==='timeSpent' && !RC_WIN_STATE.hasTimespent) || erNA || drNA || rcNA || bhNA
     || ddForcedNA || vForcedNA
     || (isCoverage && !!(RC_WIN_STATE&&RC_WIN_STATE.covSPMissing))){
    // [FIX-A5] N/A: the project does not log work time.
    // [P4-3]/[P4-4] The new metrics surface their N/A reason verbatim.
    // [P0-B5] Forced-SP-without-SP states of Defect Density / Velocity use
    // the same N/A conclusion style.
    // [P10-P0-2] Backlog Health: the reason comes from the snapshot
    // (covSPMissing — the side that lacks story points).
    var naReason = erNA ? rcMetricState('escapereview').reason
                 : drNA ? rcMetricState('designreview').reason
                 : rcNA ? rcMetricState('reviewcycle').reason
                 : bhNA ? rcMetricState('backlog').reason
                 : ddForcedNA ? 'no story points in the current window (forced SP-weighted mode)'
                 : vForcedNA ? 'no story points in the current window (forced SP state)'
                 : (isCoverage && RC_WIN_STATE.covSPMissing)
                    ? ('the forced Story-Point coverage cannot be computed — the '+RC_WIN_STATE.covSPMissing+' side carries no story points in the window')
                 : null;
    conclEl.textContent = (erNA||drNA||rcNA||bhNA||ddForcedNA||vForcedNA
      || (isCoverage && !!(RC_WIN_STATE&&RC_WIN_STATE.covSPMissing)))
      ? 'ⓘ N/A — '+(naReason||'not computable on the current data')
      : 'ⓘ N/A — the project does not log work time (timespent fill-rate < 20%).';
  } else if(emptyTypes || noTypesSelected){
    // [P12-P4] No verdict on an empty selection (settings OR top checkboxes).
    conclEl.textContent='';
  } else if(isFlow){
    // [P24-E] rcFlowVerdict: the net level sets the colour, the balance
    // trend can only soften it to 🟡 (Recovering / Slowing).
    var completeOpened=openedVals.filter(function(v,i){return !periodContext.partial[periods[i]];});
    var completeResolved=resolvedVals.filter(function(v,i){return !periodContext.partial[periods[i]];});
    var fv=rcFlowVerdict(completeOpened, completeResolved, stablePct);
    var nP=completeOpened.length;
    if(!fv.ok && fv.reason==='empty'){
      conclEl.textContent='No activity in the window — no trend';
    } else if(!fv.ok){
      conclEl.textContent='Not enough data for a trend ('+nP+' of '+nP+' periods; ≥ '+RC_TREND_MIN_POINTS+' needed)';
    } else {
      var net=fv.net, lvl=fv.lvl, trPct=fv.trPct;
      trendOk=true;
      var ow=openLabel.toLowerCase();
      var netTxt = 'net '+(net>=0?'+':'−')+Math.abs(net)+' over window ('
        + (lvl==='neg' ? ow+' exceed resolved — backlog growing'
           : lvl==='pos' ? 'resolved exceed '+ow+' — backlog shrinking'
           : 'balanced')+')';
      var trWord = fv.tr==='up' ? 'improving' : (fv.tr==='down' ? 'worsening' : 'flat');
      var c = rcVerdictWord(fv.cls)+' · '+netTxt
        +' · balance trend '+(trPct>=0?'+':'−')+Math.abs(trPct).toFixed(0)+'% ('+trWord+')';
      // [P1-4] Two Δ blocks: one per series (integer counters).
      c += ' · '+openLabel+' '+rcDeltaText(openedVals, 0);
      c += ' · '+resolLabel+' '+rcDeltaText(resolvedVals, 0);
      conclEl.textContent = c;
    }
  } else if(isCoverage){
    // [P1v3-1e] The band judgement uses the MOST RECENT COMPUTABLE control
    // point (ready>0 && velocity>0) — not the last bucket: a zero bar is a
    // modelling placeholder, not a measurement. When the last bucket is
    // non-computable but an older one is computable, the line states which
    // period the judgement refers to. No computable point → the standard
    // empty-state (no fabricated under-stocked verdict).
    var lastIdx=-1;
    for(var ci=covComputable.length-1;ci>=0;ci--){ if(covComputable[ci]&&!periodContext.partial[periods[ci]]){ lastIdx=ci; break; } }
    if(lastIdx<0){
      conclEl.textContent='';
    } else {
      var lastV=covVals[lastIdx];
      var lastP=labels[lastIdx];
      // [P22-T5] Δ% must compare MEASUREMENTS, not placeholders: filter to
      // the computable control points before taking the last two.
      var covD=(function(){
        // [P24-C] Δ = last vs the ADJACENT previous period (n/a when either
        // control point is not computable or the previous one is 0).
        var compVals=covVals.map(function(v, i){ return covComputable[i]?v:null; });
        var d=rcLastTwo(compVals);
        return d?rcDeltaPct(d.last,d.prev,1):'';
      })();
      var perTxt=(lastIdx===periods.length-1)?'':' · judged on '+lastP;
      if(lastV>=tMin&&lastV<=tMax){
        conclEl.textContent='🟢 Healthy coverage ('+(Math.round(lastV*10)/10)+' sprints of ready work)'+(covD?' · '+covD:'')+perTxt;
      } else if(lastV<tMin){
        conclEl.textContent='🔴 Under-stocked ('+(Math.round(lastV*10)/10)+' sprints of ready work — starvation risk)'+(covD?' · '+covD:'')+perTxt;
      } else {
        conclEl.textContent='🟡 Over-stocked ('+(Math.round(lastV*10)/10)+' sprints of ready work — grooming waste)'+(covD?' · '+covD:'')+perTxt;
      }
    }
  } else if(!isFlow){
    // [P24-C] ONE relative trend rule for every single-series metric, read
    // from the SAME per-period values the bars show (rcTrendVerdict).
    var serVals=null;
    if(isWipSnap){ serVals=wipVals; }
    else if(isGrouped){ serVals=totals; }
    else { serVals=values; }
    var tv=rcTrendVerdict(completedValues(serVals||[]), dirUp?'up':'down', stablePct);
    trendOk=!!tv.ok;
    var c=rcTrendText(tv, (serVals||[]).length);
    var dTxt=rcDeltaText(serVals||[], 1);
    if(dTxt) c += ' · '+dTxt;
    conclEl.textContent = c;
  } else { conclEl.textContent = ''; }
  // [P24-C] The dashed trend line is drawn ONLY when the verdict rule has
  // enough data (≥ RC_TREND_MIN_POINTS periods) — a line without a verdict
  // would suggest a trend the rule does not support. Backlog Health keeps
  // its line (band rule, no slope verdict).
  if(!isCoverage && !trendOk){
    datasets=datasets.filter(function(d){ return !(d.type==='line' && /^Trend/.test(String(d.label||''))); });
  }
  // [P1-STATES] The state surfaces: title, y-axis, axis-note, avg-box unit
  // and the metric-list button suffix all follow the ACTIVE state.
  var rcSt = rcMetricState(rcMetric);
  var stateTitle = rcMetricDisplayName(rcMetric);
  var yAxisText = cfg.y_axis;
  if(rcMetric==='defectdensity'){
    // [P7-DD] The numerator is the COUNT of defects in both modes.
    yAxisText = ddForcedNA ? 'Defect density (n/a — no story points in data)'
      : (ddMode==='per_sp' ? 'Defects per 1 SP of completed work'
                           : 'Defects per completed Story/Task (no SP in data)');
  }
  if(rcMetric==='backlog'){
    yAxisText = rcSt.state==='velocity_sp'
      ? 'Sprints of ready backlog (SP ÷ Velocity SP per period)'
      : 'Sprints of ready backlog (issues ÷ Throughput issues per period)';
  }
  if(rcMetric==='velocity'){
    yAxisText = rcSt.state==='sp' ? 'Story points per period (SP)' : 'Completed items per period (issue count)';
  }
  if(rcMetric==='lead'){ yAxisText='Issue Lead Time (days)'; }
  var note=document.getElementById('rcAxisNote');
  if(note){
    // Keep the metric's Y-axis description; rebuild the X-axis part
    // dynamically from the selected granularity.
    var baseNote = cfg.axis_note.split(' X-axis:')[0];
    if(rcMetric==='defectdensity'){
      // [P7-DD] The numerator is the COUNT of defects in both modes.
      baseNote = 'Y-axis: '+(ddForcedNA ? 'n/a — no story points in data'
        : (ddMode==='per_sp' ? '#defects per 1 SP of completed work'
                             : '#defects per completed Story/Task (no SP in data)'));
    } else if(rcMetric==='backlog'){
      baseNote = 'Y-axis: '+(rcSt.state==='velocity_sp'
        ? 'Sprints of ready backlog (SP ÷ Velocity SP per period)'
        : 'Sprints of ready backlog (issues ÷ Throughput issues per period)')
        +' · Team speed measured in average '+(rcSt.state==='velocity_sp'?'Velocity story points':'Throughput issues')+' per period';
    } else if(rcMetric==='velocity'){
      baseNote = 'Y-axis: '+(rcSt.state==='sp' ? 'Story points per period (SP)' : 'Completed items per period (issue count)')
        +(rcSt.state==='sp' ? ' · Team speed measured in story points' : '');
    } else if(rcMetric==='lead'){
      baseNote = 'Y-axis: Issue Lead Time (days)';
    }
    note.textContent = baseNote + ' · X-axis: ' + granLabel + ' buckets' +
      ((rangeUsed && rcCalTouchedCur()) ? ' (calendar range applied)' :
        ' · Default: last '+periods.length+' '+(periodContext.real?'completed Jira sprints':gran==='sprint'?'sprints (2-week periods)':granLabel.toLowerCase()+' periods')
        +' up to the last active period of the project');
    if(rcMetric==='wip'){
      note.textContent += ' · Snapshot at the end of each period; for the customary daily WIP snapshot set Periods = Daily.';
    }
  }
  rcClearPending();
  // [P23-NEW] The issues table must show ONLY the items in the DISPLAYED
  // chart. usedKeys was collected during the aggregation pass — in the
  // default state (from/to null) it holds the metric's whole history while
  // `periods` is narrowed to the last N buckets. Rebuild usedKeys from the
  // finalized periods with per-family rules:
  //   WIP snapshot: [enterDev, leaveDev) overlaps ≥1 displayed bucket end.
  //   Coverage: numerator = ready interval overlaps a bucket end (same
  //     readyFromUnverified clamp as the first pass); denominator =
  //     PM_DATA.velocity items (from/to + dim + FIXED Story/Task/Defect
  //     gate) whose rcBucketKey is displayed.
  //   All other metrics: rcBucketKey(dev_start) is among the displayed
  //     buckets (same filters as the aggregation loop).
  // The rebuild iterates items (they carry .key) — never covReady (no .key).
  // [P24-T] Each used issue also records its own metric value (the per-item
  // contribution to the chart) for the table's Metric value column.
  var tblVals={};
  var velSpMode=(rcMetric==='velocity' && rcMetricState('velocity').state==='sp');
  function tblPut(it, kind){
    var v=rcTableItemValue(rcMetric, it, {velSp:velSpMode, ddMode:ddMode, kind:kind});
    if(!v) return;
    var cur=tblVals[it.key];
    if(!cur){ tblVals[it.key]={txt:[v.txt], num:v.num}; return; }
    if(cur.txt.indexOf(v.txt)<0) cur.txt.push(v.txt);
    if(v.num!==null && (cur.num===null || v.num>cur.num)) cur.num=v.num;
  }
  (function(){
    var periodSet={};
    periods.forEach(function(p){ periodSet[p]=1; });
    // [P24-T] The first aggregation pass may have added keys outside the
    // displayed buckets — the table is rebuilt from scratch here.
    usedKeys={};
    if(isWipSnap){
      wipItems.forEach(function(it){
        if(periods.some(function(p){ return snapshotIncluded(it,p); })){
          usedKeys[it.key]=1; tblPut(it,'wip');
        }
      });
    } else if(isCoverage){
      items.forEach(function(it){
        if(!rcDimMatch(it, dim, sel)) return;
        if(typeSel && !typeSel[rcTypeLabel(it.type)]) return;
        if(periods.some(function(p){ return snapshotIncluded(it,p); })){
          usedKeys[it.key]=1; tblPut(it,'ready');
        }
      });
      (PM_DATA.velocity||[]).forEach(function(v){
        if(!eventIncluded(v)) return;
        var t=new Date(v.dev_start);
        if(isNaN(t)) return;
        if(from&&t<from) return;
        if(to&&t>to) return;
        if(!rcDimMatch(v, dim, sel)) return;
        if(!BH_DEN_TYPES[rcTypeLabel(v.type)]) return;
        if(periodSet[rcPeriodKey(v, gran, periodContext)]){ usedKeys[v.key]=1; tblPut(v,'speed'); }
      });
    } else {
      items.forEach(function(it){
        if(!eventIncluded(it)) return;
        if(!rcDimMatch(it, dim, sel)) return;
        if(typeSel && !typeSel[rcTypeLabel(it.type)]) return;
        var t=new Date(it.dev_start);
        if(isNaN(t)) return;
        if(from&&t<from) return;
        if(to&&t>to) return;
        if(periodSet[rcPeriodKey(it, gran, periodContext)]){ usedKeys[it.key]=1; tblPut(it); }
      });
    }
  })();
  // Issues table: unique issues that participated in this calculation.
  RC_TABLE.rows=Object.keys(usedKeys);
  RC_TABLE.vals=tblVals;
  RC_WIN_STATE.periodNote=gran==='sprint'?rcSprintNote(periodContext):'';
  if(periodContext.real&&!periods.length){
    document.getElementById('rcConclusion').textContent='ⓘ N/A — no usable Jira sprint periods in this selection.';
  }
  var vHdr=document.getElementById('rcTableValHdr');
  if(vHdr){ vHdr.textContent=rcTableValueHeader(rcMetric, velSpMode); }
  RC_TABLE.page=0;
  rcRenderTable();
  if(rcChart){ rcChart.destroy(); }
  var ctx=document.getElementById('rcChart');
  if(!ctx) return;
  // [P1-STATES] The Y-axis title follows the ACTIVE state.
  var yOpts={title:{display:true,text:yAxisText}, beginAtZero:true};
  if(cfg.y_min!==null&&cfg.y_min!==undefined){ yOpts.suggestedMin=cfg.y_min; }
  if(cfg.y_max!==null&&cfg.y_max!==undefined){ yOpts.suggestedMax=cfg.y_max; }
  // [P1-5] Stretch the Y axis so healthy reference lines above the data stay
  // visible (applies to the single-series branch; WIP per_dev adds its own).
  if(!isCoverage && !isFlow && !isWipSnap){
    var refMax=0;
    (RC_REF_LINES[rcMetric]||[]).forEach(function(r){ if(r.level>refMax) refMax=r.level; });
    if(refMax>0){ yOpts.suggestedMax=Math.max(cfg.y_max||0, refMax*1.1); }
  }
  // [P1-3] WIP per_developer: y-axis title switches.
  if(isWipSnap && wipPerDev){ yOpts.title.text='WIP per developer'; }
  var scales={y:yOpts, x:{title:{display:true,text:'Period ('+granLabel+')'}}};
  if(isGrouped){ scales.y.stacked=true; scales.x.stacked=true; }
  if(isFlow){ scales.yBal={position:'right', title:{display:true,text:'Balance ('+resolLabel+' − '+openLabel+')'},
    beginAtZero:true, grid:{drawOnChartArea:false}}; }
  rcChart=new Chart(ctx,{type:'bar',data:{labels:labels,datasets:datasets},
    options:{responsive:true,maintainAspectRatio:false,
      scales:scales,
      plugins:{legend:{position:'bottom'}}}});
  // [P1-B8] The tooltip is rebuilt AFTER the window is computed and the
  // state snapshot exists — it always describes the state the chart shows
  // (Apply / dimension / types / settings changes all route through here).
  rcSetTip();
}
// ---- Issues table (issues participating in the current calculation) ----
var RC_TABLE = { rows: [], sortKey: 'created', sortDir: -1, page: 0, pageSize: 25 };
function rcEsc(s){
  return String(s===null||s===undefined?'':s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;');
}
// [P2-I16] Natural key comparison: the numeric suffix is compared as a
// number (EPMRLCT-45 < EPMRLCT-1000); non-matching keys fall back to the
// plain string compare. Shared by the ID column and the days_in_status
// tiebreak.
function rcNatCmp(ka, kb){
  var na=String(ka).match(/^(.*?)(\d+)$/), nb=String(kb).match(/^(.*?)(\d+)$/);
  if(na&&nb&&na[1]===nb[1]){
    var d=parseInt(na[2],10)-parseInt(nb[2],10);
    if(d!==0) return d<0?-1:1;
    return 0;
  }
  var a2=String(ka), b2=String(kb);
  return a2<b2 ? -1 : (a2>b2 ? 1 : 0);
}
// [P24-T] Per-item metric value shown in the issues table — what this
// issue contributes to the plotted metric (Jira data only).
function rcTableValueHeader(mk, velSp){
  var cfg=RC_CFG[mk]||{};
  var f=cfg.field;
  if(f==='days') return 'Value (days)';
  if(f==='eff') return 'Flow efficiency (%)';
  if(f==='cycles') return 'Clarification cycles';
  if(f==='count') return 'Re-review cycles';
  if(f==='reworked') return 'Reworked';
  if(f==='series') return 'Series';
  if(f==='severity') return 'Severity';
  if(cfg.aggregation==='coverage') return 'Role in Backlog Health';
  if(cfg.aggregation==='wipSnapshot') return 'WIP';
  if(mk==='velocity') return velSp?'Story points':'Completed';
  if(mk==='bugfix') return 'Role · time spent (h)';
  if(cfg.rateMode==='roles'||cfg.rateMode==='spDensity') return 'Role';
  return 'Counted';
}
function rcTableItemValue(mk, it, ctx){
  ctx=ctx||{};
  var cfg=RC_CFG[mk]||{};
  var f=cfg.field;
  function num(x){ return (x===null||x===undefined||isNaN(x))?null:Number(x); }
  function r1(x){ return Math.round(x*10)/10; }
  if(f==='days'){ var d=num(it.days); return {txt:d===null?'—':String(r1(d)), num:d}; }
  if(f==='eff'){ var e=num(it.eff); return {txt:e===null?'—':(r1(e)+'%'), num:e}; }
  if(f==='cycles'||f==='count'){ var c=num(it[f]); return {txt:c===null?'—':String(c), num:c}; }
  if(f==='reworked'){ return {txt:it.reworked?'Yes':'No', num:it.reworked?1:0}; }
  if(f==='series'){
    var sl=(it.series==='new')?'New':(it.series==='opened'?'Opened':'Resolved');
    return {txt:sl, num:null};
  }
  if(f==='severity'){ return {txt:String(it.severity||'—'), num:null}; }
  if(ctx.kind==='wip') return {txt:'In dev at period end', num:null};
  if(ctx.kind==='ready') return {txt:'Ready (numerator)', num:null};
  if(ctx.kind==='speed') return {txt:'Completed (team speed)', num:null};
  if(mk==='velocity'){
    if(ctx.velSp){ var sp=num(it.sp)||0; return {txt:String(sp), num:sp}; }
    return {txt:'1', num:1};
  }
  if(mk==='defectdensity'){
    if(it.role==='numerator') return {txt:'Defect found in QA', num:null};
    var dsp=num(it.sp)||0;
    return {txt:ctx.ddMode==='per_sp'?('Completed · '+dsp+' SP'):'Completed item', num:ctx.ddMode==='per_sp'?dsp:null};
  }
  if(mk==='bugfix'){
    var h=r1((num(it.timeSpent)||0)/3600);
    return {txt:(it.role==='numerator'?'Bug fix':'All work')+' · '+h+'h', num:h};
  }
  if(mk==='leakage'){ return {txt:it.role==='numerator'?'Leaked to prod':'QA-entered / prod', num:null}; }
  if(mk==='escapereview'){ return {txt:it.role==='numerator'?'Found in QA':'Review / QA defect', num:null}; }
  return {txt:'1', num:1};
}
function rcTableCmpVal(a, b, dir){
  var va=a.__valNum, vb=b.__valNum;
  var ea=(va===null||va===undefined), eb=(vb===null||vb===undefined);
  if(ea&&eb){
    var sa=String(a.__val||''), sb=String(b.__val||'');
    if(sa!==sb) return (sa<sb?-1:1)*dir;
    return rcNatCmp(a.__key, b.__key)*dir;
  }
  if(ea) return 1*dir;
  if(eb) return -1*dir;
  if(va!==vb) return (va-vb)*dir;
  return rcNatCmp(a.__key, b.__key)*dir;
}
// [P2-I16] The days_in_status comparator, factored out so the tiebreak
// semantics are testable and shared: empties last on ascending / first on
// descending; ties (incl. both-empty) resolve by the natural key.
function rcTableCmpDays(a, b, dir){
  var va=a.days_in_status, vb=b.days_in_status;
  var ea=(va===null||va===undefined), eb=(vb===null||vb===undefined);
  if(ea&&eb) return rcNatCmp(a.__key, b.__key)*dir;
  if(ea) return 1*dir;
  if(eb) return -1*dir;
  var dv=(va-vb);
  if(dv!==0) return dv*dir;
  return rcNatCmp(a.__key, b.__key)*dir;
}
function rcRenderTable(){
  var body=document.getElementById('rcTableBody');
  if(!body) return;
  var D=RC_ISSUE_DIR||{};
  var TV=RC_TABLE.vals||{};
  var rows=RC_TABLE.rows.map(function(k){ var r=D[k]||null; if(r){ r.__key=k;
    var tv=TV[k]; r.__val=tv?tv.txt.join(', '):''; r.__valNum=tv?tv.num:null; } return r; }).filter(Boolean);
  var sk=RC_TABLE.sortKey, sd=RC_TABLE.sortDir;
  rows.sort(function(a,b){
    var va, vb;
    if(sk==='id'){
      // Natural sort: compare the numeric suffix so EPMRLCT-45 < EPMRLCT-1000.
      var na=String(a.__key).match(/^(.*?)(\d+)$/), nb=String(b.__key).match(/^(.*?)(\d+)$/);
      if(na&&nb&&na[1]===nb[1]){ return (parseInt(na[2],10)-parseInt(nb[2],10))*sd; }
      va=a.__key; vb=b.__key;
    }
    else { va=a[sk]; vb=b[sk]; }
    // [P2-I16] days_in_status: empties are NOT mapped to a sentinel number.
    // Two numbers compare numerically; an empty sorts AFTER any number on
    // ascending (BEFORE it on descending — the sd factor flips it), and a
    // tie (including both-empty) falls through to the natural key sort.
    if(sk==='days_in_status'){
      return rcTableCmpDays(a, b, sd);
    }
    if(sk==='metric_value'){
      return rcTableCmpVal(a, b, sd);
    }
    va=String(va===null||va===undefined?'':va);
    vb=String(vb===null||vb===undefined?'':vb);
    var cmp = va<vb ? -1 : (va>vb ? 1 : 0);
    return cmp*sd;
  });
  // [P2-I16] The tiebreak is folded into the primary comparator (see the
  // days_in_status branch above): equal values — including two empties —
  // fall through to the natural key comparison below.
  var totalPages=Math.max(1, Math.ceil(rows.length/RC_TABLE.pageSize));
  if(RC_TABLE.page>=totalPages) RC_TABLE.page=totalPages-1;
  if(RC_TABLE.page<0) RC_TABLE.page=0;
  var page=rows.slice(RC_TABLE.page*RC_TABLE.pageSize, (RC_TABLE.page+1)*RC_TABLE.pageSize);
  var html='';
  page.forEach(function(r){
    html+='<tr class="border-t hover:bg-gray-50">'+
      '<td class="py-1 px-2"><a href="'+rcEsc(r.url)+'" target="_blank" class="text-blue-600 hover:underline">'+rcEsc(r.__key)+'</a></td>'+
      '<td class="py-1.5 px-2">'+rcEsc(r.type)+'</td>'+
      '<td class="py-1.5 px-2">'+rcEsc(r.summary)+'</td>'+
      '<td class="py-1.5 px-2">'+rcEsc(r.status)+'</td>'+
      '<td class="py-1.5 px-2">'+rcEsc(r.created)+'</td>'+
      '<td class="py-1.5 px-2">'+rcEsc(r.updated)+'</td>'+
      '<td class="py-1.5 px-2">'+(r.__val?rcEsc(r.__val):'—')+'</td>'+
      '</tr>';
  });
  body.innerHTML=html;
  var info=document.getElementById('rcPageInfo');
  if(info){ info.textContent = rows.length ? ('Showing '+(RC_TABLE.page*RC_TABLE.pageSize+1)+'-'+Math.min(rows.length,(RC_TABLE.page+1)*RC_TABLE.pageSize)+' of '+rows.length) : 'No issues in the current calculation'; }
  var cnt=document.getElementById('rcTblCount');
  if(cnt){ cnt.textContent = rows.length+' issues'; }
  var prev=document.getElementById('rcPrevBtn'), next=document.getElementById('rcNextBtn');
  if(prev){ prev.disabled = RC_TABLE.page<=0; }
  if(next){ next.disabled = RC_TABLE.page>=totalPages-1; }
}
function rcSortTable(key){
  if(RC_TABLE.sortKey===key){ RC_TABLE.sortDir=-RC_TABLE.sortDir; }
  else { RC_TABLE.sortKey=key; RC_TABLE.sortDir=(key==='created'||key==='updated'||key==='days_in_status'||key==='metric_value'||key==='id')?-1:1; }
  rcRenderTable();
}
function rcPage(delta){
  var maxPage=Math.max(0, Math.ceil(RC_TABLE.rows.length/RC_TABLE.pageSize)-1);
  RC_TABLE.page=Math.max(0, Math.min(maxPage, RC_TABLE.page+delta));
  rcRenderTable();
}
// ---- [CFD] Interactive Cumulative Flow Diagram (Delivery section) ---------
// Same control mechanics as the Trends widget but with an INDEPENDENT state
// (cfd* ids): Periods granularity + calendar + dimensions + issue types +
// band visibility. NO trend line / Delta / avg box (out of scope per plan).
var cfdCalTouched=false, cfdChartRef=null;
function cfdMarkPending(){
  var el=document.getElementById('cfdPending');
  if(el) el.classList.remove('hidden');
}
function cfdClearPending(){
  var el=document.getElementById('cfdPending');
  if(el) el.classList.add('hidden');
}
function cfdSettingsToggle(){
  var p=document.getElementById('cfdSettingsPanel');
  if(p) p.classList.toggle('hidden');
}
function cfdSetsToMap(list){
  var o={}; (list||[]).forEach(function(v){ o[String(v).toLowerCase()]=1; });
  return o;
}
// Band status sets, rebuilt from the committed settings on every apply —
// the SAME status sets the Trends widget uses (Widget settings -> Workflow
// statuses): done / devStart+qaEntry+refinement / backlog.
function cfdBandSets(){
  var sets=(rcDraft||RC_SETTINGS).statusSets||{};
  return {
    done: cfdSetsToMap(sets.done),
    ip:   cfdSetsToMap([].concat(sets.devStart||[], sets.qaEntry||[], sets.refinement||[])),
    backlog: cfdSetsToMap(sets.backlog)
  };
}
// Group a raw status into a band key ('done'|'ip'|'backlog').
// '__created__' (the synthetic first event) maps to Backlog.
function cfdGroup(st, bandSets){
  var low=String(st||'').toLowerCase();
  if(low==='__created__') return 'backlog';
  if(bandSets.done[low]) return 'done';
  if(bandSets.ip[low]) return 'ip';
  return 'backlog';
}
// Snapshot status of an issue at timestamp ts from its event timeline
// (last event <= ts; before the first event the issue is created -> Backlog).
function cfdStatusAt(events, ts, bandSets){
  var cur='backlog';
  for(var i=0;i<events.length;i++){
    if(events[i][0]<=ts) cur=cfdGroup(events[i][1], bandSets);
    else break;
  }
  return cur;
}
// Default window: the last 5 periods of activity of the CFD items (P1-2
// semantics; the CFD has no Default N setting — fixed at 5).
function cfdDefaultWindow(gran){
  var items=PM_DATA.cfd||[];
  var last=null;
  items.forEach(function(it){
    var t=new Date(it.dev_start);
    if(!isNaN(t)&&(!last||t>last)) last=t;
  });
  if(!last||isNaN(last)) return null;
  last.setHours(0,0,0,0);
  var cur=rcBucketStart(last, gran);
  var step=(gran==='daily')?1:(gran==='weekly')?7:(gran==='sprint')?14
          :(gran==='monthly')?1:(gran==='quarterly')?3:12;
  var from=new Date(cur);
  for(var i=0;i<4;i++){
    if(gran==='daily'||gran==='weekly'||gran==='sprint') from.setDate(from.getDate()-step);
    else if(gran==='annual') from.setFullYear(from.getFullYear()-step);
    else from.setMonth(from.getMonth()-step);
  }
  var next=new Date(cur);
  if(gran==='daily'||gran==='weekly'||gran==='sprint') next.setDate(next.getDate()+step);
  else if(gran==='annual') next.setFullYear(next.getFullYear()+step);
  else next.setMonth(next.getMonth()+step);
  var to=new Date(next); to.setDate(to.getDate()-1); to.setHours(23,59,59,999);
  return {from:from, to:to};
}
function cfdSyncCalendar(){
  var pEl=document.getElementById('cfdPeriods'),
      fEl=document.getElementById('cfdFrom'),
      tEl=document.getElementById('cfdTo');
  if(!pEl||!fEl||!tEl) return;   // CFD controls absent (e.g. trimmed DOM)
  if(cfdCalTouched) return;
  var gran=pEl.value||'sprint';
  var w=cfdDefaultWindow(gran);
  if(w){
    fEl.value=rcDateStr(w.from);
    tEl.value=rcDateStr(w.to);
  }
}
function cfdPeriodsChanged(){
  cfdSyncCalendar();
  cfdMarkPending();
}
// Dimension values for the CFD (same field mapping as Trends).
function cfdDimField(dim){ return dim==='component' ? 'team' : dim; }
function cfdDimValues(dim){
  var seen={}, out=[];
  // [P22-T7] The issuetype dimension was removed (see rcDimValues).
  (PM_DATA.cfd||[]).forEach(function(it){
    if(dim==='team'){
      rcItemTeams(it).forEach(function(v){ if(!seen[v]){seen[v]=1;out.push(v);} });
      return;
    }
    var v=it[rcDimField(dim)]||'';
    if(!seen[v]){ seen[v]=1; out.push(v); }
  });
  return out.sort();
}
function cfdPopulateDim(){
  var dEl=document.getElementById('cfdDim');
  var wrap=document.getElementById('cfdDimList');
  if(!dEl||!wrap) return;   // CFD controls absent → no-op
  var dim=dEl.value;
  if(dim==='project'){
    wrap.innerHTML='<span class="text-xs text-gray-500">Project: single value — all data</span>';
    return;
  }
  var vals=cfdDimValues(dim);
  wrap.innerHTML='';
  vals.forEach(function(v){
    var lb=document.createElement('label');
    lb.className='inline-flex items-center gap-1 text-xs border rounded px-2 py-1 cursor-pointer';
    var cb=document.createElement('input');
    cb.type='checkbox'; cb.value=v; cb.className='cfdDimCb'; cb.checked=true;
    cb.onchange=cfdMarkPending;
    lb.appendChild(cb); lb.appendChild(document.createTextNode(v));
    wrap.appendChild(lb);
  });
}
function cfdPopulateTypes(){
  var wrap=document.getElementById('cfdTypeWrap');
  if(!wrap) return;
  wrap.innerHTML='';
  ISSUE_TYPES.forEach(function(t){
    var lb=document.createElement('label');
    lb.className='inline-flex items-center gap-1 text-xs border rounded px-2 py-1 cursor-pointer';
    var cb=document.createElement('input');
    cb.type='checkbox'; cb.value=t; cb.className='cfdTypeCb'; cb.checked=true;
    cb.onchange=cfdMarkPending;
    lb.appendChild(cb); lb.appendChild(document.createTextNode(t));
    wrap.appendChild(lb);
  });
}
function cfdSelected(){
  var dim=document.getElementById('cfdDim').value;
  if(dim==='project') return null;   // no filtering (all)
  var cbs=document.querySelectorAll('#cfdDimList .cfdDimCb:checked');
  var set={};
  Array.prototype.forEach.call(cbs,function(cb){ set[cb.value]=1; });
  return set;
}
function cfdTypeSelected(){
  var wrap=document.getElementById('cfdTypeWrap');
  if(!wrap) return null;   // no type filter UI → no filtering
  var cbs=document.querySelectorAll('#cfdTypeWrap .cfdTypeCb:checked');
  var set={};
  Array.prototype.forEach.call(cbs,function(cb){ set[cb.value]=1; });
  return set;
}
var CFD_CHART=null;
function cfdApply(){
  var canvas=document.getElementById('cfdChart');
  var pEl=document.getElementById('cfdPeriods'),
      dEl=document.getElementById('cfdDim'),
      bEl=document.getElementById('cfdBand_backlog');
  if(!canvas||!pEl||!dEl||!bEl || !(PM_DATA.cfd&&PM_DATA.cfd.length)) return;
  var gran=pEl.value||'sprint';
  var dim=dEl.value;
  var sel=cfdSelected();
  var typeSel=cfdTypeSelected();
  var bands={
    backlog: document.getElementById('cfdBand_backlog').checked,
    ip: document.getElementById('cfdBand_ip').checked,
    done: document.getElementById('cfdBand_done').checked
  };
  var bandSets=cfdBandSets();
  // Calendar: manual range or the default last-5-periods window.
  var fromInput=document.getElementById('cfdFrom').value,
      toInput=document.getElementById('cfdTo').value;
  var from=null, to=null;
  if(fromInput&&toInput){ from=new Date(fromInput+'T00:00:00'); to=new Date(toInput+'T23:59:59'); }
  else if(fromInput){ from=new Date(fromInput+'T00:00:00'); to=null; }
  else if(toInput){ from=null; to=new Date(toInput+'T23:59:59'); }
  if(!from||!to){
    var w=cfdDefaultWindow(gran);
    if(w){ if(!from) from=w.from; if(!to) to=w.to; }
  }
  // Filter: dimension + issue type (the calendar applies to the X axis, not
  // the items — the snapshot counts every issue's status at each bucket end).
  var items=(PM_DATA.cfd||[]).filter(function(it){
    if(!rcDimMatch(it, dim, sel)) return false;
    if(typeSel && !typeSel[rcTypeLabel(it.type)]) return false;
    return true;
  });
  var keys=rcAxisRange(from, to, gran);
  var done=[], ip=[], backlog=[];
  keys.forEach(function(k){
    var endP=rcBucketEnd(k, gran);
    var c={done:0, ip:0, backlog:0};
    items.forEach(function(it){
      var st=cfdStatusAt(it.events, endP, bandSets);
      if(st==='done') c.done++;
      else if(st==='ip') c.ip++;
      else c.backlog++;
    });
    done.push(c.done); ip.push(c.ip); backlog.push(c.backlog);
  });
  var datasets=[];
  // [P22-T7] The issuetype split arm was removed — the three bands stack
  // as before for every remaining dimension.
  if(bands.backlog) datasets.push({label:'Backlog', data:backlog, borderColor:'#2563eb', backgroundColor:'rgba(37,99,235,0.35)', fill:'origin'});
  if(bands.ip)      datasets.push({label:'In Progress', data:ip, borderColor:'#f59e0b', backgroundColor:'rgba(245,158,11,0.35)', fill:'-1'});
  if(bands.done)    datasets.push({label:'Done', data:done, borderColor:'#10b981', backgroundColor:'rgba(16,185,129,0.35)', fill:'-1'});
  if(cfdChartRef){ cfdChartRef.destroy(); }
  cfdChartRef=new Chart(document.getElementById('cfdChart'), {
    type:'line',
    data:{labels:keys, datasets:datasets},
    options:{responsive:true, maintainAspectRatio:false,
      interaction:{mode:'index', intersect:false},
      plugins:{legend:{position:'bottom'}},
      scales:{y:{stacked:true, beginAtZero:true, title:{display:true,text:'Issues (cumulative)'}},
              x:{title:{display:true,text:'Period ('+(RC_GRAN_LABEL[gran]||gran)+')'}}}}
  });
  var note=document.getElementById('cfdAxisNote');
  if(note){
    var shown=[];
    if(bands.backlog) shown.push('Backlog');
    if(bands.ip) shown.push('In Progress');
    if(bands.done) shown.push('Done');
    note.textContent='Stacked areas: '+shown.join(' / ')+' at each period end'
      +' · X-axis: '+(RC_GRAN_LABEL[gran]||gran)+' buckets'
      +((from&&to)?' (calendar range applied)':' · Default: last 5 periods with project activity');
  }
  cfdClearPending();
}
// [FIX-A0] Boot chain: persisted settings -> PM_DATA rebuild from RC_RAW ->
// first metric render. Deferred to DOMContentLoaded while the DOM is still
// parsing; runs immediately when the script executes after the DOM is ready
// (the script sits at the end of <body>).
function rcBoot(){
  rcSettingsLoad();
  rcRebuildData();   // PM_DATA from RC_RAW + (possibly persisted) settings
  rcSetMetric('cycle');
  // [CFD] first render of the interactive CFD (controls + chart). All CFD
  // functions are null-guarded: when the Delivery controls are absent from
  // the DOM (trimmed pages / QA sandboxes) they are no-ops.
  cfdSyncCalendar();
  cfdPopulateDim();
  cfdPopulateTypes();
  cfdApply();
}
if(document.readyState==='loading'){
  document.addEventListener('DOMContentLoaded', rcBoot);
} else { rcBoot(); }
// [RC-BOOT-END] — QA scripts slice the widget code up to this marker.
// populate dimension dropdowns + first render
olapLinkFillSelect('olapLinkType', 'link_type');
olapLinkFillSelect('olapLinkDir', 'direction');
olapLinkFillSelect('olapLinkSType', 'source_type');
olapLinkFillSelect('olapLinkTType', 'target_type');
olapLinkFillSelect('olapLinkSStatus', 'source_status');
olapLinkFillSelect('olapLinkTStatus', 'target_status');
olapLinkApply();
</script>
</body>
</html>"""
