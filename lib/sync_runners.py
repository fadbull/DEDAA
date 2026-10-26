"""Skill #1 orchestration: run_sync() dispatches Jira / reports / Confluence
sync runs and ingests the resulting documents.

Extracted 1:1 from the original monolithic sync_agent.py (main + _run_*)."""
import os

from .atlassian_api import AtlassianAPI
from .config import (
    DEFAULT_COLLECTION_CONFLUENCE,
    DEFAULT_COLLECTION_JIRA,
    DEFAULT_COLLECTION_JIRA_REPORTS,
    DEFAULT_JIRA_DAYS,
    resolve_sync_db_path,
)
from .sync_confluence import sync_confluence
from .sync_ingest import _get_last_sync, _get_max_updated, ingest
from .sync_jira import fetch_field_meta, sync_jira, sync_jira_reports, \
    sync_jira_versions


def run_sync(args):
    """Resolve credentials/config and dispatch the requested sync service(s).
    This is the body of the original sync_agent.main() (minus parsing)."""
    service = args.service
    # For 'all' we pull both Jira and Confluence, so resolve credentials for
    # each available source individually.
    url = args.url or os.environ.get("JIRA_URL") or os.environ.get("CONFLUENCE_URL")
    token = args.token or os.environ.get("JIRA_TOKEN") or os.environ.get("CONFLUENCE_TOKEN")
    username = args.username or os.environ.get(
        "JIRA_USERNAME") or os.environ.get("CONFLUENCE_USERNAME", default="")
    # Resolve the Jira project key early (used to auto-name the DB folder).
    project_key = args.project_key or os.environ.get("JIRA_PROJECT")
    # Decide the ChromaDB folder: an explicit --db-path / DB_PATH env wins;
    # otherwise each project (or its alias) gets its OWN isolated folder under
    # ./vector_dbs/ so the vector DB is portable and can be handed to the customer.
    db_path = resolve_sync_db_path(args, project_key)

    if args.collection:
        # An explicit --collection only makes sense for a single service.
        collection = args.collection
    elif service == "jira-reports":
        collection = DEFAULT_COLLECTION_JIRA_REPORTS
    elif service == "confluence":
        collection = DEFAULT_COLLECTION_CONFLUENCE
    elif service == "all":
        collection = None  # per-source collections resolved inside the dispatch
    else:
        collection = DEFAULT_COLLECTION_JIRA

    print("=" * 70)
    print(f" sync_agent (Skill #1) — service={service}")
    print(f" db_path    : {db_path}")
    print(f" collection : {collection}")
    print(f" url        : {url}")
    print(f" project_key: {project_key or '(from --jql)'}")
    print(f" days       : {args.days if args.days is not None else DEFAULT_JIRA_DAYS}")
    print(f" dry_run    : {args.dry_run}")
    print("=" * 70)

    if args.dry_run:
        # F1: a dry run must not touch the network. Print the plan and stop
        # before constructing AtlassianAPI (which would hit the API on 401
        # with dummy credentials).
        print("[DRY-RUN] Plan only — no network calls, no writes. Details:")
        print(f"  service     : {service}")
        print(f"  db_path     : {db_path}")
        print(f"  collection  : {collection or '(per-source collections)'}")
        print(f"  url         : {url or '(not set — would fail without --url/.env)'}")
        print(f"  project_key : {project_key or os.environ.get('JIRA_PROJECT') or '(none)'}")
        print(f"  jql         : {args.jql or '(default: project + updated window)'}")
        print(f"  days        : {args.days if args.days is not None else DEFAULT_JIRA_DAYS}")
        print(f"  space_key   : {args.space_key or os.environ.get('CONFLUENCE_SPACE_KEY') or '(none)'}")
        print(f"  page_id     : {args.page_id or os.environ.get('CONFLUENCE_PAGE_ID') or '(none)'}")
        print(f"  update      : {args.update}")
        print(f"  batch_size  : {args.batch_size}")
        print("[DRY-RUN] Done — nothing was fetched or written.")
        return

    api = AtlassianAPI(url, username, token)

    if service == "all":
        # Pull EVERYTHING available from .env: Jira issues + related params,
        # issue links, Jira board reports, project versions/releases, and
        # Confluence pages. Each source goes into its own collection.
        print("[Sync All] Pulling all available data sources...")

        # --- Jira: issues + versions/releases ---
        if args.project_key or os.environ.get("JIRA_PROJECT"):
            jira_col = args.collection or DEFAULT_COLLECTION_JIRA
            _run_jira(api, args, db_path, jira_col,
                      os.environ.get("JIRA_PROJECT"))
            _run_jira_reports(api, args, db_path)
        else:
            print("[Sync All] No JIRA_PROJECT in .env — skipping Jira issues "
                  "and reports.")

        # --- Confluence: space or page tree ---
        if os.environ.get("CONFLUENCE_SPACE_KEY") or \
           os.environ.get("CONFLUENCE_PAGE_ID") or args.space_key or args.page_id:
            _run_confluence(api, args, db_path)
        else:
            print("[Sync All] No Confluence source in .env — skipping "
                  "Confluence pages.")
    elif service == "jira-reports":
        _run_jira_reports(api, args, db_path)
    elif service == "jira":
        _run_jira(api, args, db_path, collection,
                  args.project_key or os.environ.get("JIRA_PROJECT"))
    else:
        _run_confluence(api, args, db_path)


def _run_jira(api, args, db_path, collection, project_key):
    """Fetch Jira issues + versions/releases and ingest into their collections."""
    if not project_key and not args.jql:
        raise SystemExit("Jira requires --project-key (or .env JIRA_PROJECT) "
                         "or a custom --jql.")
    days = args.days if args.days is not None else DEFAULT_JIRA_DAYS
    if args.update:
        # Incremental update: narrow the JQL window to changes since the
        # last recorded sync (or the latest 'updated' already in the DB).
        last = _get_last_sync(db_path, collection) or \
            _get_max_updated(db_path, collection)
        if last:
            jql = (args.jql or
                   f'project={project_key} AND updated >= "{last}"')
            print(f"[Jira] UPDATE mode — incremental from {last}")
        else:
            jql = args.jql or (
                f'project={project_key} AND updated >= -{days}d')
            print("[Jira] UPDATE mode — no prior sync found; "
                  "falling back to full window")
    else:
        jql = args.jql or (f'project={project_key} AND updated >= -{days}d')
    print(f"[Jira] JQL: {jql}")
    field_names = fetch_field_meta(api)
    docs = sync_jira(api, project_key, jql, field_names, api.base, days)
    ingest(docs, db_path, collection, args.batch_size, args.dry_run,
           update=args.update)
    # Also fetch and store the project's RELEASE / VERSION metadata.
    version_docs = sync_jira_versions(api, project_key, api.base)
    if version_docs:
        ingest(version_docs, db_path, args.versions_collection,
               args.batch_size, args.dry_run, update=args.update)


def _run_jira_reports(api, args, db_path):
    """Fetch Jira board reports and ingest into product_jira_reports."""
    project_key = args.project_key or os.environ.get("JIRA_PROJECT")
    if not project_key:
        raise SystemExit("jira-reports requires --project-key (or .env "
                         "JIRA_PROJECT).")
    board_ids = None
    if args.board_ids:
        board_ids = [x.strip() for x in args.board_ids.split(",") if x.strip()]
    docs = sync_jira_reports(api, project_key, api.base, board_ids=board_ids)
    ingest(docs, db_path, args.collection or DEFAULT_COLLECTION_JIRA_REPORTS,
           args.batch_size, args.dry_run, update=args.update)


def _run_confluence(api, args, db_path):
    """Fetch Confluence pages (space or page tree) and ingest."""
    space_key = args.space_key or os.environ.get("CONFLUENCE_SPACE_KEY")
    page_id = args.page_id or os.environ.get("CONFLUENCE_PAGE_ID")
    if not space_key and not page_id:
        raise SystemExit(
            "Confluence requires --space-key (or .env CONFLUENCE_SPACE_KEY) "
            "to extract a whole space, or --page-id (or .env "
            "CONFLUENCE_PAGE_ID) for a page tree.")
    docs = sync_confluence(
        api, str(page_id) if page_id else None, api.base,
        depth=args.depth,
        follow_links=args.follow_links,
        save_images=args.save_images,
        assets_dir=args.assets_dir,
        db_path=db_path,
        space_key=space_key,
    )
    ingest(docs, db_path, args.collection or DEFAULT_COLLECTION_CONFLUENCE,
           args.batch_size, args.dry_run, update=args.update)
