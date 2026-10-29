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
  var items=rcActiveItems();
  var isCoverage = cfg.aggregation==='coverage';
  var isWipSnap = cfg.aggregation==='wipSnapshot';   // [FIX-A4]
  var isAlloc = cfg.aggregation==='allocation';      // [FIX-A5] timespent share
  var isClarcycle = rcMetric==='clarcycle';           // [FIX-P0-1]
  var isReviewcycle = rcMetric==='reviewcycle';       // [FIX-P0-1]
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
  items.forEach(function(it){
    if(!rcDimMatch(it, dim, sel)) return;
    if(typeSel && !typeSel[rcTypeLabel(it.type)]) return;
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
      var rf=(it.readyFrom!==undefined&&it.readyFrom!==null)?it.readyFrom:(new Date(it.dev_start)).getTime();
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
      covReady.push({rf:rf, rl:rl, sp:(it.sp!==undefined&&it.sp!==null)?it.sp:0});
      return;
    }
    var t=new Date(it.dev_start);
    if(from&&t<from) return;
    if(to&&t>to) return;
    usedKeys[it.key]=1;
    var key=rcBucketKey(t, gran);
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
      // [P1-STATES] Velocity SP state: sum the story points instead of
      // counting issues (Story Point Velocity). Items state / auto → count.
      if(rcMetric==='velocity' && rcMetricState('velocity').state==='sp'){
        agg[key]+=(it.sp||0);
      } else {
        agg[key]++;
      }
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
    // [P3-2]/[P10-P0-2] The sprint gate follows the Widget settings
    // (sprintData: auto-detect / available / none) with the SAME precedence
    // rcSprintsAvail() applies — but read DIRECTLY: rcSprintsAvail()
    // prefers the previous pass's snapshot, and using it here would make
    // the auto decision depend on a stale snapshot (circular read).
    var S2=rcDraft||RC_SETTINGS;
    var sd2=(S2&&S2.sprintData)||'auto';
    var sprGate = sd2==='available' ? true
                : sd2==='none' ? false
                : (typeof RC_HAS_SPRINTS_DATA==='undefined') ? true : !!RC_HAS_SPRINTS_DATA;
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
      var t=new Date(v.dev_start);
      if(isNaN(t)) return;
      if(from&&t<from) return;
      if(to&&t>to) return;
      if(!rcDimMatch(v, dim, sel)) return;
      if(!BH_DEN_TYPES[rcTypeLabel(v.type)]) return;
      // [P1v3-1d] The denominator items participate in the calculation —
      // they enter the issues table alongside the ready items.
      usedKeys[v.key]=1;
      var k=rcBucketKey(t, gran);
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
      if((v.sp||0)<=0) return false;
      if(!rcDimMatch(v, dim, sel)) return false;
      if(typeSel && !typeSel[rcTypeLabel(v.type)]) return false;
      return true;
    });
    var bfIts=filteredItems.filter(function(it){ return it.timeSpent!==undefined; });
    var w2=0; bfIts.forEach(function(it){ if((it.timeSpent||0)>0) w2++; });
    var sd=(rcDraft||RC_SETTINGS||{}).sprintData||'auto';
    var vm2=(((rcDraft||RC_SETTINGS).metrics||{}).velocity||{}).velocityMode||'auto';
    return {
      ddMode: ddMode, ddFillRate: ddFillRate, ddFilled: ddFilled, ddTotal: ddTotal,
      hasSP: hasSP,
      sprintsAvail: (sd==='available') ? true : (sd==='none') ? false
        : (typeof RC_HAS_SPRINTS_DATA==='undefined') ? true : !!RC_HAS_SPRINTS_DATA,
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
  // [P1-STATES] Velocity: forced SP state without story points → N/A.
  var vForcedNA = rcMetric==='velocity' && (function(){
    var vm=((rcDraft||RC_SETTINGS).metrics||{}).velocity||{};
    return vm.velocityMode==='sp' && !rcWindowHasSP();
  })();
  // [FIX-A4] Last-N bucket keys ENDING at the bucket containing lastD —
  // the WIP snapshot axis (periods without completions still appear).
  function rcLastBuckets(lastD, n){
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
  var periods;
  if(isCoverage){
    // [P1v3-1b] The default window anchors on the READY side only — the
    // latest readiness start among the ready population (Backlog Health
    // describes the ready backlog; the completion history is a denominator,
    // not a time reference). Fallbacks: latest creation among the metric's
    // numerator types → latest creation among all Jira items. Then the same
    // last-N-buckets walk the WIP snapshot uses — buckets without
    // completions stay in the axis (rendered as zero bars, P1v3-1e).
    periods=null;
  }
  else if(isWipSnap){
    // [FIX-A4] Bucket-ends from the AXIS (rcAxisRange / last-N buckets),
    // NOT from the items — periods without completions still get a point.
    periods=null;
  }
  else if(isFlow){ periods=[].concat.apply([],Object.keys(seriesAgg).map(function(s){return Object.keys(seriesAgg[s]);})); }
  else if(isGrouped){ periods=Object.keys(groupAgg); }
  else { periods=Object.keys(agg); }
  if(periods!==null) periods=Array.from(new Set(periods)).sort();
  var granLabel = RC_GRAN_LABEL[gran] || 'Sprint (2 weeks)';
  var rangeUsed = false;
  if(hasCustom){
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
  } else if(periods===null){
    // [P0-2] Effective window size: the metric's defaultN setting wins over
    // the per-metric defaultN setting wins; RC_DEFAULT_N is the fallback.
    var effN=(mEff.defaultN!==undefined&&mEff.defaultN!==null)?mEff.defaultN:RC_DEFAULT_N;
    if(isCoverage){
      // [P1v3-1b] Backlog Health, no calendar: the anchor is the LATEST
      // readiness start among the ready population (ready side only).
      // Fallbacks: latest creation among the metric's numerator types →
      // latest creation among all Jira items → empty state.
      var lastReady=null;
      covReady.forEach(function(iv){ if(!lastReady||iv.rf>lastReady) lastReady=iv.rf; });
      var anchorD = lastReady ? new Date(lastReady) : null;
      if(!anchorD){
        (PM_DATA.backlog||[]).forEach(function(it){
          var t=new Date(it.dev_start);
          if(!isNaN(t)&&(!anchorD||t>anchorD)) anchorD=t;
        });
      }
      if(!anchorD){
        (RC_RAW||[]).forEach(function(r){
          var t=r.created?new Date(r.created):null;
          if(!isNaN(t)&&(!anchorD||t>anchorD)) anchorD=t;
        });
      }
      periods = anchorD ? rcLastBuckets(anchorD, effN) : [];
    } else if(isClarcycle || isReviewcycle){
      // [P2v3-1/2] Default window anchors: clarcycle — the latest dev-start
      // transition among the metric's items; reviewcycle — the latest done
      // transition among the reviewed items. Fallbacks: latest item date →
      // latest creation → empty state.
      var lastA=null;
      items.forEach(function(it){
        var t=new Date(it.dev_start);
        if(!isNaN(t)&&(!lastA||t>lastA)) lastA=t;
      });
      if(!lastA){
        (PM_DATA[rcMetric]||[]).forEach(function(it){
          var t=new Date(it.dev_start);
          if(!isNaN(t)&&(!lastA||t>lastA)) lastA=t;
        });
      }
      periods = lastA ? rcLastBuckets(lastA, effN) : [];
    } else {
    // [FIX-A4] WIP snapshot, no calendar: the last N buckets ending at the
    // bucket containing the latest WIP activity.
    // [P6-B1] The anchor = max(enterDev, leaveDev) — an item that entered
    // dev earlier but LEFT inside a later bucket must keep that bucket in
    // the window (the WIP population last changed at the leave transition).
    var lastWip=null;
    wipItems.forEach(function(it){
      var tE=(it.enterDev!==null&&it.enterDev!==undefined)?it.enterDev:null;
      var tL=(it.leaveDev!==null&&it.leaveDev!==undefined)?it.leaveDev:null;
      var t=new Date(Math.max(tE||0, tL||0));
      if(!isNaN(t)&&(!lastWip||t>lastWip)) lastWip=t;
    });
    // [P0-2] Effective window size: the metric's defaultN setting wins over
    // the per-granularity static default.
    periods = lastWip ? rcLastBuckets(lastWip, effN) : [];
    }
  } else {
    // No calendar: Sprint -> last N sprints (settings), other granularities
    // -> the last active bucket (day / week / month / quarter / year).
    // [P0-2] Effective window size: the metric's defaultN setting wins over
    // the RC_DEFAULT_N fallback.
    var effN=(mEff.defaultN!==undefined&&mEff.defaultN!==null)?mEff.defaultN:RC_DEFAULT_N;
    periods = periods.slice(-(effN));
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
      var pe=rcBucketEnd(p, gran);
      var ready=0, readySP=0;
      covReady.forEach(function(iv){
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
      var endP=rcBucketEnd(p, gran);
      var cnt=0, devs={};
      wipItems.forEach(function(it){
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
  var sKeys=Object.keys(seriesAgg||{});
  var openKey = sKeys.indexOf('opened')>=0 ? 'opened'
              : (sKeys.indexOf('new')>=0 ? 'new' : (sKeys[0]||'opened'));
  var resolKey = sKeys.indexOf('resolved')>=0 ? 'resolved'
               : (sKeys.filter(function(k){ return k!==openKey; })[0] || null);
  var openLabel = openKey==='new' ? 'New' : (openKey==='opened' ? 'Opened' : openKey);
  var resolLabel = resolKey==='resolved' ? 'Resolved' : (resolKey||'Resolved');
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
      var wipSum=0; wipVals.forEach(function(v){ wipSum+=v; });
      avgText = periods.length ? 'Avg: '+rcFmtAvg(wipSum/periods.length,'')+'/period' : 'Avg: n/a';
    } else if(cfg.rateMode==='spDensity'){
      // [FIX-A1] Defect Density box: weighted ratio over the window.
      // [P1-STATES] The unit label follows the ACTIVE state.
      // [P7-DD] The unit names the count numerator; the auto per_item
      // fallback is surfaced with the '(no SP in data)' note.
      if(ddForcedNA){
        avgText = 'n/a — no story points in data';
      } else {
        var dn2=0,dt2=0; periods.forEach(function(p){ dn2+=(agg[p]&&agg[p].n)||0; dt2+=(agg[p]&&agg[p].total)||0; });
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
  var labels=periods;
  var datasets=[], trend=null;
  var balTrend=null;   // [P0-3] single source of truth: flow trend = balance
  // [P1-I13] Issue Type dimension: one series per selected type. The
  // per-type aggregation is a second pass over the FILTERED items (the
  // same population as agg); the avg box / conclusion / trend keep
  // working on the AGGREGATE as for every other dimension. Reference
  // lines are drawn ONCE; N/A fires when ALL selected types are empty.
  var typeAgg={}, typeKeys=[];
  if(dim==='issuetype'){
    (sel?Object.keys(sel):[]).forEach(function(t){ typeKeys.push(t); });
    typeKeys.forEach(function(tk){ typeAgg[tk]={}; });
    items.forEach(function(it){
      if(!rcDimMatch(it, dim, sel)) return;
      if(typeSel && !typeSel[rcTypeLabel(it.type)]) return;
      var t=rcTypeLabel(it.type);
      if(typeKeys.indexOf(t)<0) return;
      var t2=new Date(it.dev_start);
      if(from&&t<from) return;
      if(to&&t>to) return;
      var key=rcBucketKey(t, gran);
      var a=typeAgg[t]||(typeAgg[t]={});
      if(!a[key]) a[key]=(cfg.aggregation==='avg')?[]:(cfg.rateMode||cfg.aggregation==='allocation'?{n:0,total:0}:0);
      if(cfg.aggregation==='avg'){
        a[key].push(rcMetric==='floweff' ? it : it[cfg.field]);
      } else if(cfg.aggregation==='sum'){
        a[key]+=(it[cfg.field]||0);
      } else if(cfg.aggregation==='count'){
        a[key]+=1;
      } else {
        // rate / roles / spDensity / allocation: n/total by role.
        if(it.role==='numerator') a[key].n++;
        if(it.role==='denominator') a[key].total++;
        if(cfg.aggregation==='rate'){ a[key].total++; if(it[cfg.field]) a[key].n++; }
      }
    });
  }
  if(isFlow){
    // Guard both series lookups: a window may contain only one series (or
    // none after type/dimension filtering) — missing series render as 0.
    var openedVals=periods.map(function(p){return (seriesAgg[openKey]&&seriesAgg[openKey][p])||0;});
    var resolvedVals=periods.map(function(p){return (seriesAgg[resolKey]&&seriesAgg[resolKey][p])||0;});
    // [P0-3] ONE trend quantity for both the chart line and the conclusion:
    // the net balance (Resolved − Opened). The old ratio trend (opened ÷
    // resolved) could point the opposite way from the conclusion.
    var balance=openedVals.map(function(v,i){ return resolvedVals[i]-v; });
    balTrend=rcLinearTrend(balance);
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
    trend = rcLinearTrend(totals);
    if(trend){ datasets.push({type:'line', label:'Trend', data:trend.line, borderColor:'#ef4444',
      borderDash:[6,4], fill:false, tension:0, pointRadius:0, borderWidth:2}); }
  } else if(isCoverage){
    // Backlog Health (coverage): bar per control point + healthy band
    // reference lines (2–3 sprints of ready backlog by default).
    var mS=((rcDraft||RC_SETTINGS).metrics||{})[rcMetric]||{};
    var tMin=(mS.targetMin!==undefined&&mS.targetMin!==null)?mS.targetMin:2;
    var tMax=(mS.targetMax!==undefined&&mS.targetMax!==null)?mS.targetMax:3;
    var bhVals=covVals.map(function(v){ return v===null?0:Math.round(v*100)/100; });
    trend=rcLinearTrend(bhVals);
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
    trend=rcLinearTrend(wipVals);
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
    // [P1-I13] Issue Type dimension: one bar series per selected type
    // (grouped bars, one color per type); the trend/conclusion/box stay on
    // the AGGREGATE; reference lines are drawn ONCE after the series.
    if(dim==='issuetype' && typeKeys.length){
      var PALETTE=['#2563eb','#10b981','#f59e0b','#8b5cf6','#ec4899','#06b6d4','#f97316','#64748b'];
      typeKeys.forEach(function(t, ti){
        var a=typeAgg[t]||{};
        var vals=periods.map(function(p){ return rcAggValue(cfg, a[p]); });
        datasets.push({type:'bar', label:t, data:vals,
          backgroundColor:PALETTE[datasets.length%PALETTE.length]+'99',
          borderColor:PALETTE[datasets.length], borderWidth:1});
      });
      var aggVals=periods.map(function(p){ return rcAggValue(cfg, agg[p]); });
      // [P12-P4] No trend over an empty selection or an all-null series
      // (a flat 0-trend produces a false «Stable» verdict).
      var hasAnyAgg=aggVals.some(function(v){ return v!==null && v!==undefined; });
      trend = (emptyTypes || noTypesSelected || !hasAnyAgg)
        ? null
        : rcLinearTrend(aggVals);
    } else {
    var values=periods.map(function(p){ return rcAggValue(cfg, agg[p]); });
    // [P0-TYPES] Empty type selection in the metric settings -> no trend
    // line (a flat 0-trend over an empty selection is misleading). An empty
    // result from the calendar/dimension filters keeps the trend.
    // [P12-P4] Same gate for the TOP Issue Type checkboxes: with every
    // checkbox unchecked the series is all-null — no trend, no verdict.
    var hasAnyValue=values.some(function(v){ return v!==null && v!==undefined; });
    trend = (emptyTypes || noTypesSelected || !hasAnyValue)
      ? null
      : rcLinearTrend(values);
    datasets=[
      {type:'bar', label:cfg.label, data:values,
       backgroundColor:cfg.color+'99', borderColor:cfg.color, borderWidth:1}
    ];
    if(trend){ datasets.push({type:'line', label:'Trend', data:trend.line, borderColor:'#ef4444',
      borderDash:[6,4], fill:false, tension:0, pointRadius:0, borderWidth:2}); }
    }
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
  // [P0-2] Effective threshold: the metric settings win, static config is the
  // fallback — the SAME value rcTrendRule renders in the tooltip.
  var thr=(mEff.threshold!==undefined&&mEff.threshold!==null)?mEff.threshold:(cfg.threshold||0.05);
  // [P1-4] Δ% vs prev: percentage change of the last period's value against
  // the previous one. prev=0 -> 'Δ n/a' (no division by zero); fewer than
  // two periods with data -> no Δ block. dec = decimals (1 default, 0 for
  // the integer flow counters).
  function rcDeltaPct(last, prev, dec){
    if(last===null||last===undefined||prev===null||prev===undefined) return '';
    if(prev===0) return 'Δ n/a';
    var d=(last-prev)/prev*100;
    var s=d>=0?'+':'−';
    return 'Δ '+s+(Math.abs(d)).toFixed(dec===undefined?1:dec)+'% vs prev';
  }
  function rcLastTwo(vals){
    var def=vals.filter(function(v){ return v!==null&&v!==undefined; });
    if(def.length<2) return null;
    return {last:def[def.length-1], prev:def[def.length-2]};
  }
  // [P0-TYPES] Empty type selection in the metric settings -> no conclusion
  // at all (uniform N/A behaviour). NOTE: an empty result caused by the
  // calendar/dimension filters still renders the trend conclusion (the
  // selection is legitimate — the metric simply has no data in range).
  var emptyTypes = Array.isArray(mEff.types) && mEff.types.length===0;
  // [P12-P4] The TOP Issue Type checkboxes may also be emptied — with
  // typeSel={} every item is skipped, the series is all-null and a flat
  // 0-trend would produce a false «Stable» verdict.
  var noTypesSelected = typeSel && Object.keys(typeSel).length===0;
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
  } else if(isFlow && openedVals.length>1){
    // [P0-3] Reuse the SAME balTrend the chart line was drawn from.
    if(balTrend && balTrend.slope!==null){
      var c = balTrend.slope > thr ? '🟢 Improving' : (balTrend.slope < -thr ? '🔴 Degrading' : '🟡 Stable');
      // [P1-4] Two Δ blocks: one per series (integer counters).
      var oD=rcDeltaPct(openedVals[openedVals.length-1], openedVals[openedVals.length-2], 0);
      var rD=rcDeltaPct(resolvedVals[resolvedVals.length-1], resolvedVals[resolvedVals.length-2], 0);
      if(oD) c += ' · '+openLabel+' '+oD;
      if(rD) c += ' · '+resolLabel+' '+rD;
      conclEl.textContent = c;
    } else { conclEl.textContent = ''; }
  } else if(isCoverage){
    // [P1v3-1e] The band judgement uses the MOST RECENT COMPUTABLE control
    // point (ready>0 && velocity>0) — not the last bucket: a zero bar is a
    // modelling placeholder, not a measurement. When the last bucket is
    // non-computable but an older one is computable, the line states which
    // period the judgement refers to. No computable point → the standard
    // empty-state (no fabricated under-stocked verdict).
    var lastIdx=-1;
    for(var ci=covComputable.length-1;ci>=0;ci--){ if(covComputable[ci]){ lastIdx=ci; break; } }
    if(lastIdx<0){
      conclEl.textContent='';
    } else {
      var lastV=covVals[lastIdx];
      var lastP=periods[lastIdx];
      var covD=(function(){ var d=rcLastTwo(covVals); return d?rcDeltaPct(d.last,d.prev,1):''; })();
      var perTxt=(lastIdx===periods.length-1)?'':' · judged on '+lastP;
      if(lastV>=tMin&&lastV<=tMax){
        conclEl.textContent='🟢 Healthy coverage ('+(Math.round(lastV*10)/10)+' sprints of ready work)'+(covD?' · '+covD:'')+perTxt;
      } else if(lastV<tMin){
        conclEl.textContent='🔴 Under-stocked ('+(Math.round(lastV*10)/10)+' sprints of ready work — starvation risk)'+(covD?' · '+covD:'')+perTxt;
      } else {
        conclEl.textContent='🟡 Over-stocked ('+(Math.round(lastV*10)/10)+' sprints of ready work — grooming waste)'+(covD?' · '+covD:'')+perTxt;
      }
    }
  } else if(!isFlow && trend && trend.slope!==null){
    // Trend direction is a semantic property of the metric DEFINITION
    // (which slope direction means "Improving") — read from the metric
    // definition in the settings (schema), with the display config as a
    // fallback. It is NOT a user-editable setting.
    var up = (((RC_SETTINGS.metrics||{})[rcMetric]||{}).trendDir
              || cfg.trend_dir || 'down') === 'up';
    var slope = trend.slope;
    var c = (up ? (slope > thr ? '🟢 Improving' : (slope < -thr ? '🔴 Degrading' : '🟡 Stable'))
                : (slope < -thr ? '🟢 Improving' : (slope > thr ? '🔴 Degrading' : '🟡 Stable')));
    // [P1-4] Δ% vs prev from the same per-period values the bars use.
    var serVals=null;
    if(isWipSnap){ serVals=wipVals; }
    else if(isGrouped){ serVals=periods.map(function(p){ var s=0; (cfg.groups||['Critical','Major','Minor']).forEach(function(g){ s+=(groupAgg[p]&&groupAgg[p][g])||0; }); return s; }); }
    else if(cfg.rateMode==='spDensity'||cfg.rateMode==='roles'||cfg.aggregation==='rate'||cfg.aggregation==='allocation'){
      serVals=periods.map(function(p){ return rcAggValue(cfg, agg[p]); });
    } else {
      serVals=periods.map(function(p){ var arr=agg[p]||[]; if(!arr.length) return null; var s=0; arr.forEach(function(v){ s+=(v&&typeof v==='object'&&v.eff!==undefined)?v.eff:v; }); return s/arr.length; });
    }
    var dd=rcLastTwo(serVals);
    if(dd) c += ' · '+rcDeltaPct(dd.last, dd.prev, 1);
    conclEl.textContent = c;
  } else { conclEl.textContent = ''; }
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
      (rangeUsed ? ' (calendar range applied)' :
        (gran==='sprint' ? ' · Default: last 5 sprints with project activity'
                         : ' · Default: last active ' + granLabel.toLowerCase()));
    if(rcMetric==='wip'){
      note.textContent += ' · Snapshot at the end of each period; for the customary daily WIP snapshot set Periods = Daily.';
    }
  }
  rcClearPending();
  // Issues table: unique issues that participated in this calculation.
  RC_TABLE.rows=Object.keys(usedKeys);
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
  var rows=RC_TABLE.rows.map(function(k){ var r=D[k]||null; if(r){ r.__key=k; } return r; }).filter(Boolean);
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
      '<td class="py-1.5 px-2">'+(r.days_in_status===null||r.days_in_status===undefined?'—':rcEsc(r.days_in_status))+'</td>'+
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
  else { RC_TABLE.sortKey=key; RC_TABLE.sortDir=(key==='created'||key==='updated'||key==='days_in_status'||key==='id')?-1:1; }
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
  // [P1-I13] Issue Type dimension: unique normalized types of the CFD items.
  if(dim==='issuetype'){
    (PM_DATA.cfd||[]).forEach(function(it){
      var v=rcTypeLabel(it.type);
      if(v && !seen[v]){ seen[v]=1; out.push(v); }
    });
    return out.sort();
  }
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
  // [P1-I13] Issue Type dimension: each status band splits into per-type
  // segments (legend shows the types; the sum of the per-type segments
  // equals the unsplit band). The stacking order keeps the band grouping:
  // all Backlog segments, then all In-Progress, then all Done.
  if(dim==='issuetype'){
    var CFD_TYPES=(function(){ var s={}; items.forEach(function(it){ var v=rcTypeLabel(it.type); if(v) s[v]=1; }); return Object.keys(s).sort(); })();
    var CFD_COLORS=['#2563eb','#10b981','#f59e0b','#8b5cf6','#ec4899','#06b6d4','#f97316','#64748b'];
    [['backlog', bands.backlog, 'Backlog', 'rgba(37,99,235,0.35)', '#2563eb'],
     ['ip',      bands.ip,      'In Progress', 'rgba(245,158,11,0.35)', '#f59e0b'],
     ['done',    bands.done, 'Done', 'rgba(16,185,129,0.35)', '#10b981']].forEach(function(bd){
      if(!bd[1]) return;
      CFD_TYPES.forEach(function(t, ti){
        var vals=keys.map(function(k){
          var endP=rcBucketEnd(k, gran);
          var c=0;
          items.forEach(function(it){
            if(rcTypeLabel(it.type)!==t) return;
            if(cfdStatusAt(it.events, endP, bandSets)===bd[0]) c++;
          });
          return c;
        });
        var col=CFD_COLORS[CFD_TYPES.indexOf(t)%CFD_COLORS.length];
        datasets.push({label:bd[2]+' · '+t, data:vals,
          borderColor:bd[4], backgroundColor:bd[3], fill: (datasets.length===0?'origin':'-1')});
      });
    });
  } else {
  if(bands.backlog) datasets.push({label:'Backlog', data:backlog, borderColor:'#2563eb', backgroundColor:'rgba(37,99,235,0.35)', fill:'origin'});
  if(bands.ip)      datasets.push({label:'In Progress', data:ip, borderColor:'#f59e0b', backgroundColor:'rgba(245,158,11,0.35)', fill:'-1'});
  if(bands.done)    datasets.push({label:'Done', data:done, borderColor:'#10b981', backgroundColor:'rgba(16,185,129,0.35)', fill:'-1'});
  }
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
