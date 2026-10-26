"""Jira Cross-Linkage & SDLC Waste analysis (Tab 3)."""
from collections import Counter, defaultdict
from datetime import datetime
import json
from .date_utils import _dt_full, status_group

# ============================================================================
# Jira Cross-Linkage & SDLC Waste analysis (Tab 3)
# ----------------------------------------------------------------------------
# Classifies every `issuelinks` record across ALL issues into 4 macro-categories
# and computes delivery-impact metrics per category:
#   A. Hard Blockers   (blocks / is blocked by / Depend)
#   B. Process Rework  (causes / is caused by) -> escaped defects
#   C. Scope Duplication (duplicates / clones / Cloners) -> sunk hours
#   D. Soft Associations (relates to / Related To / Part of) -> sync matrix
# ============================================================================

# Link-type -> category keyword matching (case-insensitive substring).
LINK_CATEGORY_RULES = {
    "A": ["block", "depend", "required by", "depends on"],
    "B": ["caus"],
    "C": ["duplic", "clone", "cloners"],
    "D": ["relates", "related", "part of", "associated", "done before/after"],
}


def _link_category(link_type):
    """Map a raw link type string to a macro-category letter (A/B/C/D)."""
    t = (link_type or "").strip().lower()
    for cat, keywords in LINK_CATEGORY_RULES.items():
        for kw in keywords:
            if kw in t:
                return cat
    return None


def _linked_status(meta_by_key, key):
    """Return the status of a linked issue (looked up in the local DB)."""
    if not key:
        return None
    m = meta_by_key.get(key)
    return (m or {}).get("status")


def compute_cross_linkage(meta, docs):
    """Compute the Jira Cross-Linkage & SDLC Waste analytics.

    Returns a dict:
      summary: per-category counts {A: n, B: n, C: n, D: n} + total links
      category_A: {count, blocker_stagnation_rate, avg_reaction_hrs, pairs:[..]}
      category_B: {count, escaped_causes, avg_escaped_per_project, pairs:[..]}
      category_C: {count, sunk_hours, sunk_days, closed_duplicates, pairs:[..]}
      category_D: {count, sync_ratio, in_same_month, spread, pairs:[..]}
      network: [{source, target, category, type}]  (for the graph widget)
    """
    import json

    meta_by_key = {}
    for m in meta:
        k = m.get("issue_key")
        if k:
            meta_by_key[k] = m

    # Collect all link records across all issues.
    links = []  # {source, type, direction, target, category}
    for m in meta:
        src = m.get("issue_key")
        raw = m.get("issuelinks")
        if not raw:
            continue
        try:
            recs = json.loads(raw)
        except Exception:
            continue
        for r in recs:
            tgt = r.get("target_key")
            if not tgt or not src:
                continue
            cat = _link_category(r.get("type"))
            if not cat:
                continue
            links.append({
                "source": src, "type": r.get("type"),
                "direction": r.get("direction"), "target": tgt,
                "category": cat,
            })

    # ---- Category A: Hard Blockers ----------------------------------------
    # Reaction time = T_target_in_progress - T_unblocked. We approximate with
    # the blocker's created -> the blocked issue's in_progress (if both known).
    cat_a = [l for l in links if l["category"] == "A"]
    a_reactions = []   # hours between blocker created and target in_progress
    a_stagnant = 0     # targets that stayed in backlog > 24h after blocker
    a_pairs = []
    for l in cat_a:
        src_m = meta_by_key.get(l["source"])
        tgt_m = meta_by_key.get(l["target"])
        if not src_m or not tgt_m:
            continue
        blocker_created = _dt_full(src_m.get("created"))
        tgt_ip = _dt_full(tgt_m.get("in_progress_date"))
        if blocker_created and tgt_ip and tgt_ip > blocker_created:
            hrs = (tgt_ip - blocker_created).total_seconds() / 3600.0
            a_reactions.append(hrs)
            a_pairs.append({
                "blocker": l["source"], "blocked": l["target"],
                "reaction_hrs": round(hrs, 1),
                "stagnant": hrs > 24,
            })
            if hrs > 24:
                a_stagnant += 1
        elif blocker_created and not tgt_ip:
            # Blocked issue never started -> stagnation candidate.
            a_stagnant += 1
            a_pairs.append({
                "blocker": l["source"], "blocked": l["target"],
                "reaction_hrs": None, "stagnant": True,
            })
    a_count = len(cat_a)
    a_stagn_rate = round(a_stagnant / a_count * 100, 1) if a_count else None
    a_avg_react = (sum(a_reactions) / len(a_reactions)) if a_reactions else None
    category_a = {
        "count": a_count,
        "blocker_stagnation_rate": a_stagn_rate,
        "avg_reaction_hrs": round(a_avg_react, 1) if a_avg_react is not None
        else None,
        "stagnant_count": a_stagnant,
        "pairs": sorted(a_pairs, key=lambda p: -(
            p["reaction_hrs"] or 0))[:15],
        "na": a_count == 0,
    }

    # ---- Category B: Process Rework / Causes (escaped defects) ------------
    # If the cause (bug/task) was created AFTER the source issue closed, it is
    # an "Escaped Defect".
    cat_b = [l for l in links if l["category"] == "B"]
    b_escaped = 0
    b_pairs = []
    for l in cat_b:
        src_m = meta_by_key.get(l["source"])
        tgt_m = meta_by_key.get(l["target"])
        if not src_m or not tgt_m:
            continue
        cause_created = _dt_full(src_m.get("created"))
        src_done = _dt_full(src_m.get("done_date")) or _dt_full(
            src_m.get("resolutiondate"))
        # The 'cause' is the issue that triggered the rework; the source is the
        # originating task. Escaped if the cause appeared after the source done.
        if cause_created and src_done and cause_created > src_done:
            b_escaped += 1
            b_pairs.append({
                "cause": l["source"], "source": l["target"],
                "escaped": True,
                "cause_created": src_m.get("created"),
                "source_done": src_m.get("done_date"),
            })
    b_count = len(cat_b)
    category_b = {
        "count": b_count,
        "escaped_causes": b_escaped,
        "avg_escaped_per_project": round(b_escaped, 2),
        "pairs": b_pairs[:15],
        "na": b_count == 0,
    }

    # ---- Category C: Scope Duplication (sunk hours) -----------------------
    cat_c = [l for l in links if l["category"] == "C"]
    # Sunk hours: for Closed issues with resolution Duplicate, sum the time
    # spent In Progress before being closed as duplicate.
    sunk_days = 0.0
    c_closed_dupes = 0
    c_pairs = []
    for m in meta:
        res = (m.get("resolution") or "").strip().lower()
        if res not in ("duplicate", "duplicated", "won't fix"):
            continue
        st = (m.get("status") or "").strip().lower()
        if st not in ("closed", "done", "resolved"):
            continue
        c_closed_dupes += 1
        # Time in progress = done_date - in_progress_date (if both known).
        ip = _dt_full(m.get("in_progress_date"))
        dn = _dt_full(m.get("done_date"))
        if ip and dn and dn > ip:
            days = (dn - ip).total_seconds() / 86400.0
            sunk_days += days
            c_pairs.append({
                "issue": m.get("issue_key"), "sunk_days": round(days, 2),
                "type": m.get("type"),
            })
    c_count = len(cat_c)
    category_c = {
        "count": c_count,
        "sunk_hours": round(sunk_days * 24, 1),
        "sunk_days": round(sunk_days, 1),
        "closed_duplicates": c_closed_dupes,
        "pairs": sorted(c_pairs, key=lambda p: -p["sunk_days"])[:15],
        "na": c_count == 0 and c_closed_dupes == 0,
    }

    # ---- Category D: Soft Associations (sync matrix) ----------------------
    cat_d = [l for l in links if l["category"] == "D"]
    d_in_same_month = 0
    d_total_pairs = 0
    d_spread = 0
    d_pairs = []
    for l in cat_d:
        src_m = meta_by_key.get(l["source"])
        tgt_m = meta_by_key.get(l["target"])
        if not src_m or not tgt_m:
            continue
        s_done = _dt_full(src_m.get("done_date")) or _dt_full(src_m.get(
            "resolutiondate"))
        t_done = _dt_full(tgt_m.get("done_date")) or _dt_full(tgt_m.get(
            "resolutiondate"))
        if s_done and t_done:
            d_total_pairs += 1
            same = abs((s_done.year * 12 + s_done.month) -
                       (t_done.year * 12 + t_done.month)) <= 1
            if same:
                d_in_same_month += 1
            else:
                d_spread += 1
            d_pairs.append({
                "a": l["source"], "b": l["target"],
                "a_done": src_m.get("done_date"),
                "b_done": tgt_m.get("done_date"),
                "same_month": same,
            })
    d_count = len(cat_d)
    d_sync_ratio = round(d_in_same_month / d_total_pairs * 100, 1) \
        if d_total_pairs else None
    category_d = {
        "count": d_count,
        "sync_ratio": d_sync_ratio,
        "in_same_month": d_in_same_month,
        "spread": d_spread,
        "pairs": d_pairs[:15],
        "na": d_count == 0,
    }

    # ---- Network (for the interdependence graph) --------------------------
    network = [{
        "source": l["source"], "target": l["target"],
        "category": l["category"], "type": l["type"],
    } for l in links[:400]]

    from collections import Counter as _C
    cat_summary = {c: sum(1 for l in links if l["category"] == c)
                   for c in "ABCD"}
    return {
        "summary": cat_summary,
        "total_links": len(links),
        "category_a": category_a,
        "category_b": category_b,
        "category_c": category_c,
        "category_d": category_d,
        "network": network,
    }


def _print_crosslink_summary(cl):
    """Print a terminal summary table for all 4 cross-linkage categories."""
    s = cl.get("summary", {})
    a = cl.get("category_a", {})
    b = cl.get("category_b", {})
    c = cl.get("category_c", {})
    d = cl.get("category_d", {})

    def _fmt(v, suffix=""):
        return ("N/A" if v is None else f"{v}{suffix}")

    print("\n" + "=" * 78)
    print(" JIRA CROSS-LINKAGE & SDLC WASTE SUMMARY")
    print("=" * 78)
    print(f" {'Cat':<4}{'Macro-Category':<22}{'Links':>6}  Key Metric")
    print("-" * 78)
    print(f" {'A':<4}{'Hard Blockers':<22}{s.get('A', 0):>6}  "
          f"stagnation {_fmt(a.get('blocker_stagnation_rate'), '%')} · "
          f"avg reaction {_fmt(a.get('avg_reaction_hrs'), 'h')}")
    print(f" {'B':<4}{'Process Rework':<22}{s.get('B', 0):>6}  "
          f"escaped causes {b.get('escaped_causes', 0)}")
    print(f" {'C':<4}{'Scope Duplication':<22}{s.get('C', 0):>6}  "
          f"sunk hours {_fmt(c.get('sunk_hours'))} · "
          f"closed dupes {c.get('closed_duplicates', 0)}")
    print(f" {'D':<4}{'Soft Associations':<22}{s.get('D', 0):>6}  "
          f"closure sync {_fmt(d.get('sync_ratio'), '%')} · "
          f"same-month {d.get('in_same_month', 0)}")
    print("-" * 78)
    print(f" TOTAL links: {cl.get('total_links', 0)}")
    print("=" * 78)

