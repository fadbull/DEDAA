#!/usr/bin/env python3
"""
analyze_agent.py — Skill #2 (Analyst / Dashboard Generation Agent)
Thin CLI entry point. All logic lives in the DEDAA/lib/ sub-package.

Usage examples
--------------
  python analyze_agent.py
  python analyze_agent.py --alias EMPRelocation
  python analyze_agent.py --db-path ./vector_dbs/EPMRLCT
  python analyze_agent.py --skip-olap
  python analyze_agent.py --help
"""
import os
from lib.config import build_parser, load_dotenv, resolve_db_path, _require_deps
from lib.runners import run_olap, run_dashboard


def main():
    args = build_parser().parse_args()

    # Load .env as a default source of config (no heavy deps needed for --help)
    load_dotenv(args.env_file)

    # Auto-install required Python libs (chromadb, pandas) if missing.
    _require_deps()

    db_path = resolve_db_path(args)
    # Resolve dashboard + cube outputs INSIDE the project folder so all of a
    # project's artifacts stay together (never mixed across projects).
    output = (os.path.join(db_path, args.output)
              if not os.path.isabs(args.output) else args.output)
    cube_out = (os.path.join(db_path, args.cube_out)
                if not os.path.isabs(args.cube_out) else args.cube_out)
    print("=" * 70)
    print(" analyze_agent (Skill #2)")
    print(f" db_path    : {db_path}")
    print(f" output     : {output}")
    print(f" cube       : {cube_out}")
    print("=" * 70)

    if not os.path.isdir(db_path):
        raise SystemExit(
            f"ChromaDB folder not found: {db_path}\n"
            "Run sync_agent.py first to populate it, or pass a correct "
            "--db-path / --alias.")

    if not args.skip_olap:
        run_olap(db_path, args.jira_collection, cube_out, args.dry_run)
    else:
        print("[analyze_agent] Skipping OLAP analysis (--skip-olap).")

    if not args.skip_dashboard:
        metric_settings = None
        if getattr(args, "metric_settings", None):
            from lib.metric_settings import load_settings, validate_settings
            metric_settings = load_settings(args.metric_settings)
            problems = validate_settings(metric_settings)
            if problems:
                raise SystemExit("Invalid metric settings:\n  - "
                                 + "\n  - ".join(problems))
            print(f"[analyze_agent] Metric settings loaded: "
                  f"{args.metric_settings}")
        run_dashboard(db_path, output,
                      args.jira_collection, args.reports_collection,
                      args.confluence_collection, args.dry_run,
                      metric_settings=metric_settings)
    else:
        print("[analyze_agent] Skipping dashboard generation (--skip-dashboard).")

    print("\n[analyze_agent] Done.")


if __name__ == "__main__":
    main()
