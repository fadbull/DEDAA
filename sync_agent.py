#!/usr/bin/env python3
"""
================================================================================
 sync_agent.py  —  Skill #1 (Synchronizer / Data Ingestion Agent)
================================================================================
Downloads content from a corporate Atlassian instance (Jira / Confluence) and
stores it as clean text into an isolated, project-specific ChromaDB folder so
the resulting vector database is portable and can be handed to other agents.

The script is designed to be portable:
  * Works through `requests` and bypasses corporate 403 blocks by sending a
    browser-like User-Agent header.
  * Each project's data is stored in its OWN physical folder — by default
    named after the project key or --project-alias under ./vector_dbs/.
  * Accepts credentials via CLI flags, a local .env file, or defaults.

Usage examples
--------------
  # Jira: last 90 days of updates into the default DB folder
  python sync_agent.py --service jira --url https://jiraeu.epam.com \
        --token <TOKEN> --project-key EPMRLCT

  # Confluence: download a page tree into an isolated project folder
  python sync_agent.py --service confluence --url https://kb.epam.com \
        --token <TOKEN> --page-id 2676801962 \
        --db-path ./vector_dbs/project_v1 --collection product_knowledge

  # Use credentials from .env instead of typing them
  python sync_agent.py --service jira --project-key EPMRLCT

  # Show this help
  python sync_agent.py --help
================================================================================
"""
from lib.config import build_sync_parser, load_dotenv
from lib.config import REQUIRED_DEPS_SYNC, _require_deps
from lib.sync_runners import run_sync


def main():
    args = build_sync_parser().parse_args()

    # Only require heavy deps when actually running a sync (not for --help)
    _require_deps(REQUIRED_DEPS_SYNC)

    # Load .env as a default source of credentials
    load_dotenv(args.env_file)

    run_sync(args)


if __name__ == "__main__":
    main()
