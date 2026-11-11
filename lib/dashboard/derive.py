"""Settings-driven metric derivation (JS): rcTypeLabel + rcDeriveAll."""

DERIVE_JS = """
// ---- Settings-driven metric derivation --------------------------------
// Re-derives every metric's per-issue items from RC_RAW using RC_SETTINGS
// (status sets, anchors, types, prod label, severity map). Mirrors the
// Python derivation in compute_jira() so default settings produce charts
// identical to the pre-settings pipeline.
function rcTypeLabel(t){
  if(!t) return '';
  var low=String(t).toLowerCase();
  if(low==='bug') return 'Defect';
  if(low==='sub-bug') return 'Sub-bug';
  if(low==='sub-task') return 'Sub-task';
  return String(t);
}
// [P24-P2] Label match by TOKEN (case-insensitive), not by substring:
// "prod" matches the labels prod / PROD / Prod and the prefixed family
// prod_* / prod-* (e.g. prod_issue), and the long form "production";
// it does NOT match "product", "non-prod" or "preprod".
function rcLabelHas(labels, want){
  want=String(want||'').trim().toLowerCase();
  if(!want) return false;
  return String(labels||'').split(/[,;\\s]+/).some(function(l){
    var v=l.trim().toLowerCase();
    if(!v) return false;
    if(v===want) return true;
    if(v.indexOf(want+'_')===0 || v.indexOf(want+'-')===0) return true;
    return want==='prod' && v==='production';
  });
}
function rcDeriveAll(){
  var S=RC_SETTINGS, sets=S.statusSets||{};
  function stSet(name){
    var o={};
    (sets[name]||[]).forEach(function(v){ o[String(v).toLowerCase()]=1; });
    return o;
  }
  var DONE=stSet('done'), DEV=stSet('devStart'), QA=stSet('qaEntry'),
      BACKLOG=stSet('backlog'), REFIN=stSet('refinement'), READY=stSet('ready'),
      QASET=stSet('qaSet'),   // [FIX-A2] QA statuses for the Leakage denominator
      REVIEW=stSet('review');   // [P2v3-2] Review statuses (Review Cycle Count)
      QAEXIT=stSet('qaExit'); // [P0v3-F2] QA-passed statuses (Time in QA end)
  var PROD=rcProdLabelEff(S.prodLabel, S).toLowerCase();
  var SEV=S.severityMap||{};
  function mcfg(mk){ return (S.metrics||{})[mk]||{}; }
  function mtypes(mk, key){
    var ref=mcfg(mk)[key||'types'];
    if(ref===null||ref===undefined) return {};
    if(typeof ref==='string') ref=(S.types||{})[ref]||[];
    var o={}; ref.forEach(function(t){ o[String(t).toLowerCase()]=1; });
    return o;
  }
  function normType(t){
    var low=String(t||'').toLowerCase();
    return low==='bug'?'defect':low;
  }
  function firstEv(ev, set){
    for(var i=0;i<ev.length;i++){
      if(set[String(ev[i][1]||'').toLowerCase()]) return ev[i][0];
    }
    return null;
  }
  function pad(v){ return String(v).length<2?'0'+v:String(v); }
  // Render in UTC wall-clock: the source timestamps carry a +00:00 offset
  // and the Python derivation compares UTC-naive wall times. Using local
  // getters shifted dates for viewers outside UTC (events near midnight).
  function iso(d){
    return d.getUTCFullYear()+'-'+('0'+(d.getUTCMonth()+1)).slice(-2)+'-'+('0'+d.getUTCDate()).slice(-2)
      +'T'+('0'+d.getUTCHours()).slice(-2)+':'+('0'+d.getUTCMinutes()).slice(-2)+':'+('0'+d.getUTCSeconds()).slice(-2);
  }
  // Truncate toward zero (Math.floor on non-negative deltas) to mirror the
  // Python derivation's timedelta.days semantics (17.9d -> 17, not 18).
  function days(a,b){ return Math.max(0, Math.floor((b-a)/86400000)); }

  var out={cycle:[],cycletime:[],rework:[],lead:[],flow:[],throughput:[],
           velocity:[],backlog:[],bugflow:[],leakage:[],bugfix:[],incident:[],
           qa:[],defectdensity:[],wip:[],floweff:[],cfd:[],
           escapereview:[],designreview:[],
           clarcycle:[],reviewcycle:[]};   // [P2v3-1/2]
  // ---- Anchor-driven derivation ----
  // Every metric reads its anchors from its settings (start/end/membership/
  // anchor/returnTo/active/total/series). A spec {kind:'field',field} points
  // at a date field; {kind:'status',set} resolves to the first transition
  // into that status set. Defaults reproduce the pre-settings pipeline.
  var SETMAP={devStart:DEV, done:DONE, qaEntry:QA, qaSet:QASET, qaExit:QAEXIT,
              backlog:BACKLOG, refinement:REFIN, ready:READY,
              review:REVIEW};   // [FIX-A0] · [P2v3-2] review added
  function midn(d){
    var result=new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
    result.jiraTimestamp=d.jiraTimestamp;
    return result;
  }
  function anc(ev, cd, rd, spec){
    if(!spec) return null;
    if(spec.kind==='field'){
      // Field anchors are DATE-ONLY in the Python derivation (_dt parses
      // s[:10] -> midnight), so truncate here too: calendar-day semantics.
      return spec.field==='resolutiondate' ? rd : midn(cd);
    }
    return firstEv(ev, SETMAP[spec.set]||{});
  }
  // First transition into a status set, returning the event INDEX (for
  // "any later event" scans like rework).
  function firstEvIdx(ev, set){
    for(var i=0;i<ev.length;i++){
      if(set[String(ev[i][1]||'').toLowerCase()]) return i;
    }
    return -1;
  }
  function ancWithFallback(ev, cd, rd, spec){
    var d=anc(ev, cd, rd, spec);
    if(d===null&&spec&&spec.fallback==='resolutiondate') d=rd;
    return d;
  }
  (RC_RAW||[]).forEach(function(r){
    var lbl=normType(r.type);
    var cd=r.created?new Date(r.created):null;
    var rd=r.resolutiondate?new Date(r.resolutiondate+'T00:00:00'):null;
    if(cd) cd.jiraTimestamp=r.created_ts||r.created;
    if(rd) rd.jiraTimestamp=r.resolved_ts||r.resolutiondate;
    var ev=(r.events||[]).map(function(e){ return [new Date(e[0]), e[1]]; });
    var isBug=!!mtypes('bugflow')[lbl],
        isVel=!!mtypes('velocity')[lbl];   // [P0-TYPES] isReq removed — every time-based metric gates on its own types now
    var ip=firstEv(ev,DEV), dn=firstEv(ev,DONE);
    function item(devDate, extra){
      var it={key:r.key, project:r.project, team:r.team, epic:r.epic,
              person:r.person, type:r.type, labels:r.labels,
              fieldvals:r.fieldvals, has_sprint:r.has_sprint, sprint_ids:r.sprint_ids||[],
              anchor_ts:devDate.jiraTimestamp||devDate.toISOString(),
              dev_start:iso(devDate)};
      if(extra) Object.keys(extra).forEach(function(k){ it[k]=extra[k]; });
      return it;
    }
    // ---- Time-based ----
    // [P0-TYPES] Every time-based metric now gates on its OWN type list
    // (mtypes(<metric>)[lbl]) instead of the shared isReq gate
    // (mtypes('cycle') = the 'req' alias). Previously the Requirements
    // Cycle Time type list silently decided membership for cycletime / qa
    // / floweff / rework too, so their own Issue-Type checkboxes (e.g.
    // "pick Defect + Sub-bug to see Bug Cycle Time") were ignored.
    // Requirements Cycle Time: start -> end (bucket = end anchor)
    // [P2-2] Zero-day rule: an item with a zero-day interval does not enter
    // the average (no real duration information — a calendar-day artefact).
    if(!!mtypes('cycle')[lbl]){
      var cS=anc(ev,cd,rd,mcfg('cycle').start), cE=anc(ev,cd,rd,mcfg('cycle').end);
      if(cS&&cE){
        var cDays=Math.max(0,Math.floor((cE-cS)/86400000));
        // [P2-2] Zero-day rule: floor(<24h)=0 → the item is excluded.
        if(cE>cS && cDays>0){
          out.cycle.push(item(cE,{days:cDays}));
        }
      }
    }
    // Cycle Time: start -> end. [P24-B] Bucket = END anchor (completion):
    // a completed-item time metric is reported in the period the item
    // finishes — bucketing by the start keeps only the fast finishers in
    // the recent periods (survivorship bias → false «Improving»).
    if(!!mtypes('cycletime')[lbl]){
      var ctS=anc(ev,cd,rd,mcfg('cycletime').start), ctE=anc(ev,cd,rd,mcfg('cycletime').end);
      if(ctS&&ctE&&ctE>ctS){
        var ctDays=Math.max(0,Math.floor((ctE-ctS)/86400000));
        // [P2-2] Zero-day rule (uniform across all time metrics).
        if(ctDays>0) out.cycletime.push(item(ctE,{days:ctDays}));
      }
    }
    // Time in QA: start -> end. [P24-B] Bucket = QA exit (completion).
    if(!!mtypes('qa')[lbl]){
      var qaS=anc(ev,cd,rd,mcfg('qa').start), qaE=anc(ev,cd,rd,mcfg('qa').end);
      if(qaS&&qaE&&qaE>qaS){
        var qaDays=Math.max(0,Math.floor((qaE-qaS)/86400000));
        // [P2-2] Zero-day rule.
        if(qaDays>0) out.qa.push(item(qaE,{days:qaDays}));
      }
    }
    // Flow Efficiency: active / total intervals. [P24-B] Bucket = the
    // total-interval END (completion).
    if(!!mtypes('floweff')[lbl]){
      var fa0=anc(ev,cd,rd,mcfg('floweff').active.start), fa1=anc(ev,cd,rd,mcfg('floweff').active.end);
      var ft0=anc(ev,cd,rd,mcfg('floweff').total.start), ft1=anc(ev,cd,rd,mcfg('floweff').total.end);
      if(fa0&&fa1&&ft0&&ft1&&fa1>fa0&&ft1>ft0){
        var act=Math.max(0,Math.floor((fa1-fa0)/86400000));
        var tot=Math.max(0,Math.floor((ft1-ft0)/86400000));
        if(tot>0) out.floweff.push(item(ft1,{eff:act/tot*100.0,
          active:act, total:tot}));   // [P0-TYPES] raw days for the weighted avg box
      }
    }
    // Rework: any event after the anchor into the returnTo set
    if(!!mtypes('rework')[lbl]){
      var rwA=anc(ev,cd,rd,mcfg('rework').anchor);
      if(rwA){
        var rset=SETMAP[(mcfg('rework').returnTo||{}).set]||REFIN;
        var aIdx=firstEvIdx(ev, SETMAP[(mcfg('rework').anchor||{}).set]||DEV);
        var rw=false;
        for(var j=aIdx+1;j<ev.length;j++){
          if(rset[String(ev[j][1]||'').toLowerCase()]){ rw=true; break; }
        }
        out.rework.push(item(rwA,{reworked:rw}));
      }
    }
    // [P2v3-1] Clarification Cycle Count: back-and-forths BEFORE the first
    // dev-start (complementary to Rework Rate = AFTER start). The counter
    // counts RETURNS to refinement (a transition into a refinement status
    // while the item was outside it) — the worked examples: straight flow =
    // 0; one back-and-forth = 1; two = 2. The creation transition counts as
    // the first (free) entry into refinement. Count 0 participates; bucket =
    // the first dev-start transition.
    if(!!mtypes('clarcycle')[lbl]){
      var ccIdx=-1;
      for(var ci=0;ci<ev.length;ci++){
        if(DEV[String(ev[ci][1]||'').toLowerCase()]){ ccIdx=ci; break; }
      }
      if(ccIdx>=0){
        // [P6-B2] The return-to set follows the metric settings (the same
        // SETMAP pattern the Rework Rate uses) — no hardcoded refinement.
        var clarRset=SETMAP[(mcfg('clarcycle').returnTo||{}).set]||REFIN;
        var ccCycles=0, ccInRef=true;   // an item begins its life in refinement
        for(var cj=0;cj<ccIdx;cj++){
          var ccLow=String(ev[cj][1]||'').toLowerCase();
          if(clarRset[ccLow] || ccLow==='created'){
            if(!ccInRef){ ccCycles++; }   // a RETURN to refinement = 1 cycle
            ccInRef=true;
          } else if(DEV[ccLow]){ break; } // anchor event
          else { ccInRef=false; }          // groomed/ready state
        }
        out.clarcycle.push(item(ev[ccIdx][0],{cycles:ccCycles}));
      }
    }
    // [P2v3-2] Review Cycle Count: review-set entries − 1 per reviewed item
    // whose CURRENT status is in the done set; anchor = the LAST done
    // transition (the count is only final there).
    if(!!mtypes('reviewcycle')[lbl]){
      var rcSet=SETMAP[((mcfg('reviewcycle').end||{}).set)]||DONE;
      var rvLow=String(r.status||'').toLowerCase();
      if(rcSet[rvLow]){
        var rcLast=null;
        for(var rj=0;rj<ev.length;rj++){
          if(rcSet[String(ev[rj][1]||'').toLowerCase()]) rcLast=ev[rj][0];
        }
        var rcEntries=0;
        for(var rk=0;rk<ev.length;rk++){
          if(rcLast && ev[rk][0]>rcLast) break;
          if(REVIEW[String(ev[rk][1]||'').toLowerCase()]) rcEntries++;
        }
        if(rcEntries>=1){
          out.reviewcycle.push(item(rcLast,{count:rcEntries-1}));
        }
      }
    }
    // [FIX-A3] Lead Time: Work Item Lead Time (created → done) for ANY
    // Issue Type — the top Issue Type filter picks the slice (Defect+Sub-bug
    // = Bug Lead Time, Story+Task = Story/Task Lead Time). [P24-B] Bucket =
    // the END anchor (completion) — not created (survivorship bias).
    if(!!mtypes('lead')[lbl]){
      // [P2-2] Zero-day items are excluded (incl. the resolutiondate
      // fallback — a 0-day fallback interval is not a real duration).
      var lS=anc(ev,cd,rd,mcfg('lead').start), lE=ancWithFallback(ev,cd,rd,mcfg('lead').end);
      if(lS&&lE&&lE>lS){
        var lDays=Math.max(0,Math.floor((lE-lS)/86400000));
        // [P2-2] Zero-day rule: floor(<24h)=0 → excluded.
        if(lDays>0) out.lead.push(item(lE,{days:lDays}));
      }
    }
    // [FIX-A4] WIP: point-in-time SNAPSHOT items — enterDev = first
    // transition into devStart; leaveDev = first transition into done AFTER
    // enterDev (QA statuses do NOT close WIP — the work is not complete).
    // leaveDev=null => the item is still in progress (+∞).
    if(!!mtypes('wip')[lbl]){
      var eDev=null, eDone=null;
      for(var wi=0;wi<ev.length;wi++){
        var wlow=String(ev[wi][1]||'').toLowerCase();
        if(eDev===null&&DEV[wlow]) eDev=ev[wi][0];
        else if(eDev!==null&&DONE[wlow]){ eDone=ev[wi][0]; break; }
      }
      if(eDev!==null){
        out.wip.push(item(new Date(eDev), {
          enterDev:new Date(eDev).getTime(),
          leaveDev:(eDone!==null)?new Date(eDone).getTime():null}));
      }
    }
    // ---- Flow: series anchors from config ----
    if(!!mtypes('flow')[lbl]){
      var fSer=mcfg('flow').series||{};
      var fO=anc(ev,cd,rd,fSer.opened), fR=anc(ev,cd,rd,fSer.resolved);
      if(fO) out.flow.push(item(fO,{series:'opened'}));
      if(fR) out.flow.push(item(fR,{series:'resolved'}));
    }
    // Throughput / Velocity: completed per period (start anchor)
    var tpA=anc(ev,cd,rd,mcfg('throughput').start);
    if(tpA&&!!mtypes('throughput')[lbl]) out.throughput.push(item(tpA));
    // Velocity carries the issue's story points so the denominator of the
    // Backlog Health coverage metric can average Velocity in SP.
    var vp=anc(ev,cd,rd,mcfg('velocity').start);
    if(vp&&isVel) out.velocity.push(item(vp,{sp:(r.sp!==undefined&&r.sp!==null)?r.sp:0}));
    // Backlog Health (coverage): ready-state SNAPSHOT semantics — the item
    // contributes "ready" from the moment it first enters the READY status
    // set ('Ready for development' by default) until it leaves it, so the
    // per-period value counts items that were ready AT each period end.
    // DEFECTS are included only when the defect workflow actually uses a
    // ready status: defects=auto checks whether ANY Bug/Sub-bug in the
    // project history has ever been in the ready set (or is now); defects=
    // include forces them in, exclude drops them.
    var blSet=SETMAP[(mcfg('backlog').membership||{}).set]||READY;
    var blDefMode=mcfg('backlog').defects||'auto';
    var isBlDef=mtypes('bugflow')[lbl];   // defect/sub-bug
    var blOK=!!mtypes('backlog')[lbl]&&(!isBlDef||blDefMode==='include'||(blDefMode==='auto'&&rcDefectReadySeen()));
    if(blOK&&cd){
      var readyFrom=null, readyLeft=null;
      for(var ei=0;ei<ev.length;ei++){
        var inSet=blSet[String(ev[ei][1]||'').toLowerCase()];
        if(inSet&&readyFrom===null){ readyFrom=ev[ei][0]; }
        else if(readyFrom!==null&&!inSet){ readyLeft=ev[ei][0]; break; }
      }
      if(readyFrom!==null){
        out.backlog.push(item(new Date(readyFrom),
          {readyFrom:new Date(readyFrom).getTime(),
           readyLeft:(readyLeft!==null&&readyLeft!==undefined)?new Date(readyLeft).getTime():null,
           sp:(r.sp!==undefined&&r.sp!==null)?r.sp:0}));
      } else if(blSet[String(r.status||'').toLowerCase()]&&cd){
        // [P1v3-1c] Currently in the ready set but no entry event in the
        // history: the readiness start is NOT event-verified (the creation
        // date is a placeholder). The chart clamps it to the window start
        // so the item never inflates historical periods.
        out.backlog.push(item(cd,{readyFrom:cd.getTime(),readyLeft:null,
          readyFromUnverified:true,
          sp:(r.sp!==undefined&&r.sp!==null)?r.sp:0}));
      }
    }
    // ---- Bug metrics ----
    // [P0-TYPES] Bug Growth keeps its own membership (mtypes('bugflow')).
    // Leakage and Incident moved OUT of this block: they now gate on their
    // OWN settings type lists (mtypes('leakage') / mtypes('incident')) —
    // previously the bugflow types silently decided their membership, so
    // the metrics' own Issue-Type checkboxes were ignored (Sub-bug never
    // passed the bugflow gate).
    if(isBug){
      var bSer=mcfg('bugflow').series||{};
      var bnA=anc(ev,cd,rd,bSer.new), brA=anc(ev,cd,rd,bSer.resolved);
      if(bnA) out.bugflow.push(item(bnA,{series:'new'}));
      if(brA) out.bugflow.push(item(brA,{series:'resolved'}));
    }
    // [P0v3-F1] Production Leakage: numerator = prod-labelled defects.
    // [P3-LK] Denominator = defects that REACHED CHECKING: at least one
    // transition into a QA-set status OR the production label (a defect can
    // reach production without an explicit QA transition). Defects caught
    // before QA (code review, development, etc.) enter NEITHER role — they
    // diluted the denominator and understated the leakage. Value =
    // prod-labelled ÷ (QA-entered ∪ prod-labelled) × 100, bucketed by
    // Created date for both roles.
    var lkLbl=rcProdLabelEff(String(mcfg('leakage').prodLabel||PROD), S).toLowerCase();
    var hasProd=rcLabelHas(r.labels, lkLbl);
    if(cd&&!!mtypes('leakage')[lbl]){
      var lkInQA=false;
      for(var lq=0;lq<ev.length;lq++){
        if(QASET[String(ev[lq][1]||'').toLowerCase()]){ lkInQA=true; break; }
      }
      if(lkInQA||hasProd){
        out.leakage.push(item(cd,{role:'denominator'}));
        if(hasProd) out.leakage.push(item(cd,{role:'numerator'}));
      }
    }
    // Incident Frequency: prod-labelled issues stacked by severity.
    // [P0-TYPES] Own type list (default Defect+Sub-bug, consistent with
    // Defect Density / Bug Fixing) — not the bugflow gate.
    if(cd&&hasProd&&!!mtypes('incident')[lbl]){
      var pl=String(r.priority||'').toLowerCase(), sev='Minor';
      var sevMapI=(mcfg('incident').severityMap)||SEV;
      ['Critical','Major'].forEach(function(name){
        var ps=((sevMapI[name])||[]).map(function(p){return String(p).toLowerCase();});
        if(ps.indexOf(pl)>=0) sev=name;
      });
      out.incident.push(item(cd,{severity:sev}));
    }
    // [P4-3] Defect Escape Rate (Review → QA): label-driven role items.
    //   numerator   = bug-typed items labeled [qaLabel];
    //   denominator = bug-typed items labeled [qaLabel] OR [reviewLabel]
    //                 (each issue counted once). Bucket = Created date.
    // N/A semantics live in rcMetricState — derive only produces role items
    // when BOTH labels are configured and different.
    var erQa=String((mcfg('escapereview')||{}).qaLabel||'').toLowerCase();
    var erRv=String((mcfg('escapereview')||{}).reviewLabel||'').toLowerCase();
    if(cd && erQa && erRv && erQa!==erRv && !!mtypes('escapereview')[lbl]){
      var rlHit=rcLabelHas(r.labels, erRv);
      var qlHit=rcLabelHas(r.labels, erQa);
      if(qlHit) out.escapereview.push(item(cd,{role:'numerator'}));
      if(qlHit||rlHit) out.escapereview.push(item(cd,{role:'denominator'}));
    }
    // [P4-4] Design Review Turnaround: first designStart → first
    // reviewDone; zero-day intervals excluded (the P2 rule). Derive only
    // runs when both statuses are configured and different.
    if(!!mtypes('designreview')[lbl]){
      var drCfg=mcfg('designreview')||{};
      var drSName=String(drCfg.designStart||'').toLowerCase();
      var drDName=String(drCfg.reviewDone||'').toLowerCase();
      if(drSName && drDName && drSName!==drDName){
        // Single-status sets built from the configured status names.
        var DR_S={}; DR_S[drSName]=1;
        var DR_D={}; DR_D[drDName]=1;
        var drS=firstEv(ev, DR_S), drE=firstEv(ev, DR_D);
        if(drS&&drE&&drE>drS){
          var drDays=Math.max(0,Math.floor((drE-drS)/86400000));
          // [P24-B] Bucketed by review completion (like every duration metric).
          if(drDays>0) out.designreview.push(item(drE,{days:drDays}));
        }
      }
    }
    // [FIX-A5] Bug Fixing Time Allocation: worklog role items —
    // [FIX-A5] Bug Fixing Time Allocation: worklog role items —
    //   numerator   = the metric's OWN type list (default Defect+Sub-bug)
    //                 completed in the bucket (Σ timeSpent);
    //                 [P0-TYPES] was hardcoded defect||sub-bug — the
    //                 metric's Issue-Type checkboxes were decorative.
    //   denominator = ALL completed work except Sub-task/Test (decomposition
    //                 is excluded from the effort base). INVARIANT to the
    //                 type selection — it is the full-effort base for the
    //                 percentage, not a filter.
    if(dn){
      var ts=(r.timeSpent!==undefined&&r.timeSpent!==null)?r.timeSpent:0;
      if(!!mtypes('bugfix')[lbl]){
        out.bugfix.push(item(dn,{role:'numerator', timeSpent:ts}));
      }
      if(r.type!=='Sub-task'&&r.type!=='Test'){
        out.bugfix.push(item(dn,{role:'denominator', timeSpent:ts}));
      }
    }
    // [FIX-A1] Defect Density: role-based items —
    //   numerator   = bug-like types of the metric's OWN list (defect/
    //                 sub-bug), bucketed by CREATED date;
    //   denominator = work-like types of the same list (Story/Task/…),
    //                 bucketed by COMPLETION (first done event, fallback
    //                 resolutiondate).
    // [P0-TYPES] The single checkbox set splits internally: a selected type
    // that is bug-like feeds the numerator, a work-like one the denominator.
    // Unchecking Sub-bug removes it from the numerator; adding Sub-task
    // extends the denominator. Empty denominator → n/a in rcApply.
    // [P0-B2] Defect Density numerator = defects FOUND IN QA only (a
    // transition into a qaSet status exists). Prod-only defects are
    // excluded here (they still count in Production Leakage). The
    // denominator (completed work) is unchanged.
    if(mtypes('defectdensity')[lbl]){
      if(lbl==='defect'||lbl==='sub-bug'){
        var ddInQA=false;
        for(var dqi=0;dqi<ev.length;dqi++){
          if(QASET[String(ev[dqi][1]||'').toLowerCase()]){ ddInQA=true; break; }
        }
        // [P6-B5] Prod-labelled defects are excluded from the DD numerator —
        // they belong to Production Leakage (the two populations must not
        // overlap: DD = found in QA, Leakage = leaked to prod).
        var ddProd=rcLabelHas(r.labels,
          rcProdLabelEff(String(mcfg('leakage').prodLabel||PROD), S).toLowerCase());
        if(cd&&ddInQA&&!ddProd) out.defectdensity.push(item(cd,{
          role:'numerator', sp:(r.sp!==undefined&&r.sp!==null)?r.sp:0
        }));
      } else if(dn){
        out.defectdensity.push(item(dn,{role:'denominator',
          sp:(r.sp!==undefined&&r.sp!==null)?r.sp:0}));
      }
    }
    // [CFD] Cumulative Flow Diagram: one record per issue carrying the FULL
    // status timeline ([ts, rawStatus] pairs, created date first). The CFD
    // render (cfdApply) snapshots each issue's status at every bucket end
    // and groups it via the SAME settings status sets the Trends widget
    // uses (backlog / devStart+qaEntry+refinement / done). ALL issue types
    // participate — the Issue Type filter narrows the slice at render time.
    if(cd){
      var cfdEv=[[cd.getTime(),'__created__']];
      for(var ci=0;ci<ev.length;ci++) cfdEv.push([ev[ci][0].getTime(), String(ev[ci][1]||'')]);
      out.cfd.push(item(cd,{events:cfdEv}));
    }
  });
  return out;
}
"""
