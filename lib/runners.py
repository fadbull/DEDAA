"""Orchestration: run_olap() and run_dashboard()."""
import os
import pandas as pd
from .chromadb_utils import load_collection, collection_folder
from .compute_jira import compute_jira
from .compute_product import compute_product, compute_reports
from .compute_artifacts import compute_artifacts
from .compute_profile import compute_jira_profile
from .compute_crosslink import (compute_cross_linkage,
    _print_crosslink_summary, _link_category)
from .dashboard_html import build_dashboard
from .olap_analyser import (load_issues, compute_time_in_status,
    compute_transition_frequency)

def run_olap(db_path, collection, cube_out, dry_run):
    """Run the OLAP analyser (inlined) and save the cube CSV."""
    print("=" * 70)
    print(" OLAP Analyser (Skill #2 companion)")
    print(f" db_path    : {db_path}")
    print(f" collection : {collection}")
    print("=" * 70)

    rows = load_issues(db_path=db_path, collection=collection)
    print(f"[OLAP] Loaded {len(rows)} issues from ChromaDB.\n")
    if not rows:
        print("[OLAP] No issues found in collection — skipping cube.")
        return

    import pandas as pd
    df = pd.DataFrame(rows)

    print("--- 1 & 5. FIELD DENSITY / DEPENDENCIES BY ISSUE TYPE ---")
    density = df.groupby("type").agg(
        total=("key", "count"),
        with_components=("components", lambda s: s.notna().sum()),
        with_labels=("labels", lambda s: s.notna().sum()),
        with_assignee=("assignee", lambda s: s.notna().sum()),
        with_resolution=("resolution", lambda s: s.notna().sum()),
    )
    print(density)
    print()

    print("--- 2 & 3. STATUS FREQUENCY (popularity of states) ---")
    print(df["status"].value_counts())
    print()

    print("--- 4. MEDIAN TIME IN DEVELOPMENT (In Progress -> Done) ---")
    df["days_in_dev"] = None
    for i, r in df.iterrows():
        if r["in_progress"] and r["done"]:
            df.at[i, "days_in_dev"] = (r["done"] - r["in_progress"]).days
    print(df.groupby("type")["days_in_dev"].median().fillna("N/A"))
    print()

    print("--- TIME-IN-STATUS (median days per status per type) ---")
    tis = compute_time_in_status(rows)
    if tis:
        tdf = pd.DataFrame(tis)
        pivot = tdf.pivot_table(values="days", index="status", columns="type",
                                aggfunc="median")
        print(pivot.round(2).fillna("N/A"))
    print()

    print("--- TRANSITION FREQUENCY (from -> to, top 20) ---")
    trans = compute_transition_frequency(rows)
    for (fr, to), c in trans.most_common(20):
        print(f"  {fr} -> {to}: {c}")
    print()

    print("--- 6. MULTIDIMENSIONAL CUBE (Issue Type x Status -> count) ---")
    data_cube = pd.pivot_table(df, values="key", index=["type"],
                               columns=["status"], aggfunc="count",
                               fill_value=0)
    if dry_run:
        print(f"[OLAP] DRY-RUN: would write cube to {cube_out}")
    else:
        os.makedirs(os.path.dirname(cube_out), exist_ok=True)
        data_cube.to_csv(cube_out)
        print(f"[OLAP] Cube saved to {cube_out}")
    print("Columns (statuses):", list(data_cube.columns))
    print()

    print("--- 7. CROSS-LINKAGE CUBE (Issue Type x Link Category -> count) ---")
    try:
        col = load_collection(db_path, collection)
        cl_meta = col.get("metadatas", [])
        import json as _olap_json
        cl_rows = []
        for m in cl_meta:
            src = m.get("issue_key")
            typ = m.get("type")
            raw = m.get("issuelinks")
            if not raw:
                continue
            try:
                recs = _olap_json.loads(raw)
            except Exception:
                continue
            for r in recs:
                tgt = r.get("target_key")
                if not tgt:
                    continue
                cat = _link_category(r.get("type"))
                if cat:
                    cl_rows.append({"key": src, "type": typ, "category": cat})
        if cl_rows:
            cl_df = pd.DataFrame(cl_rows)
            cl_cube = pd.pivot_table(cl_df, values="key", index=["type"],
                                     columns=["category"], aggfunc="count",
                                     fill_value=0)
            # Reorder columns A/B/C/D
            for c in "ABCD":
                if c not in cl_cube.columns:
                    cl_cube[c] = 0
            cl_cube = cl_cube[["A", "B", "C", "D"]]
            print(cl_cube)
            if not dry_run:
                cl_cube_out = cube_out.replace(".csv", "_crosslink.csv")
                cl_cube.to_csv(cl_cube_out)
                print(f"[OLAP] Cross-linkage cube saved to {cl_cube_out}")
        else:
            print("[OLAP] No classified links found.")
    except Exception as e:
        print(f"[OLAP] Cross-linkage cube failed: {e}")
    print()


def run_dashboard(db_path, output, jc, rc, cc, dry_run, metric_settings=None):
    """Generate the interactive dashboard (all logic inlined)."""
    print("=" * 70)
    print(" Dashboard generation (Skill #2)")
    print(f" db_path    : {db_path}")
    print("=" * 70)

    jira = load_collection(db_path, jc)
    conf = load_collection(db_path, cc)
    reports = load_collection(db_path, rc)

    if jira and jira.get("ids"):
        jm = compute_jira(jira["metadatas"], jira["documents"],
                          settings=metric_settings)
        jprofile = compute_jira_profile(jira["metadatas"], jira["documents"])
        # [P25] The Event-Driven Analytics section was removed from the
        # dashboard; compute_cross_linkage stays (OLAP crosslink cube +
        # console summary).
        cross_linkage = compute_cross_linkage(jira["metadatas"],
                                              jira["documents"])
        print(f"[Skill#2] Jira issues: {jm['total']}")
        print(f"[Skill#2] Cross-linkage links: "
              f"{cross_linkage['total_links']} "
              f"(A:{cross_linkage['summary']['A']} "
              f"B:{cross_linkage['summary']['B']} "
              f"C:{cross_linkage['summary']['C']} "
              f"D:{cross_linkage['summary']['D']})")
        _print_crosslink_summary(cross_linkage)
    else:
        print(f"[Skill#2] WARNING: '{jc}' empty/not found.")
        jm, jprofile = None, {}
        cross_linkage = {}

    if conf and conf.get("ids"):
        pages = compute_product(conf["metadatas"], conf["documents"])
        artifacts = compute_artifacts(conf["metadatas"], conf["documents"])
        print(f"[Skill#2] Confluence pages: {len(pages)}")
    else:
        print(f"[Skill#2] WARNING: '{cc}' empty/not found.")
        pages, artifacts = {}, {}

    if reports and reports.get("ids"):
        reports_data = compute_reports(reports["metadatas"], reports["documents"])
        print(f"[Skill#2] Jira reports: {len(reports['ids'])} docs")
    else:
        print(f"[Skill#2] WARNING: '{rc}' empty/not found.")
        reports_data = {}

    if jm is None:
        raise SystemExit("Cannot build dashboard without Jira data.")

    collection_map = {
        "product_knowledge": collection_folder(db_path, cc),
        "product_jira": collection_folder(db_path, jc),
        "product_jira_reports": collection_folder(db_path, rc),
    }
    out = os.path.abspath(output)
    html = build_dashboard(jm, pages, db_path, reports_data=reports_data,
                           artifacts=artifacts, jprofile=jprofile,
                           cross_linkage=cross_linkage,
                           collection_map=collection_map, output_path=out,
                           metric_settings=metric_settings)
    if dry_run:
        print(f"[Skill#2] DRY-RUN: would write dashboard to {out}")
    else:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(html)
        print(f"[Skill#2] Dashboard written to: {out}")
        print(f"[Skill#2] Open it with:  open {out}")

