"""Configuration, .env handling, dependency management and CLI."""
import argparse
import os
import re
import sys
import subprocess

# ----------------------------------------------------------------------------
# Defaults (must match sync_agent.py)
# ----------------------------------------------------------------------------
# config.py lives in lib/, so the project root is the PARENT directory.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB_ROOT = os.path.abspath(
    os.path.join(_PROJECT_ROOT, "vector_dbs"))
DEFAULT_DB_PATH = os.path.abspath(
    os.path.join(_PROJECT_ROOT, ".vscode", "chroma_vector_db"))
# Dashboard + OLAP cube are written INSIDE the resolved project folder, so that
# ALL artifacts of one project (ChromaDB + cube CSV + dashboard HTML) live
# together in ./vector_dbs/<alias|project-key>/ — never mixed across projects.
# [P14] The DEFAULT artifact names carry the project prefix — the ChromaDB
# folder basename (whatever identified the project at first extraction:
# alias / project key / DB_PATH folder) — so dashboards and cubes accumulated
# across many projects are distinguishable at a glance.
DEFAULT_OUTPUT = "analytics_dashboard.html"
DEFAULT_CUBE = "jira_data_cube.csv"
# Legacy root folder (no project identity) keeps the unprefixed names.
_LEGACY_DB_DIRNAME = os.path.basename(DEFAULT_DB_PATH)


def project_artifact_prefix(db_path):
    """[P14] The project prefix for default artifact names: the ChromaDB
    folder basename (the same identity that named the folder), slugified.
    Empty for the legacy root, '.' or an empty path (no project identity)."""
    raw = os.path.basename(os.path.normpath(str(db_path or "")))
    if not raw or raw == "." or raw == _LEGACY_DB_DIRNAME:
        return ""
    return _slugify(raw)


def default_dashboard_name(db_path):
    """[P14] `<project>_analytics_dashboard.html` (unprefixed fallback)."""
    prefix = project_artifact_prefix(db_path)
    return (prefix + "_" + DEFAULT_OUTPUT) if prefix else DEFAULT_OUTPUT


def default_cube_name(db_path):
    """[P14] `<project>_jira_data_cube.csv` (unprefixed fallback)."""
    prefix = project_artifact_prefix(db_path)
    return (prefix + "_" + DEFAULT_CUBE) if prefix else DEFAULT_CUBE

def load_dotenv(path=".env"):
    """Load KEY=VALUE pairs from a .env file into os.environ (no overwrite)."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _slugify(name):
    """Turn a project key / alias into a safe folder name."""
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(name or "").strip())
    safe = safe.strip("._")
    return safe or "project"


def resolve_db_path(args):
    """Resolve the ChromaDB folder for the project (mirrors sync_agent.py)."""
    if args.db_path:
        return os.path.abspath(args.db_path)
    env_db = os.environ.get("DB_PATH")
    if env_db:
        return os.path.abspath(env_db)
    alias = args.alias or os.environ.get("PROJECT_ALIAS") or ""
    if alias:
        return os.path.join(DEFAULT_DB_ROOT, _slugify(alias))
    project_key = os.environ.get("JIRA_PROJECT")
    if project_key:
        return os.path.join(DEFAULT_DB_ROOT, _slugify(project_key))
    return DEFAULT_DB_PATH


REQUIRED_DEPS = ["chromadb", "pandas"]

# Sync (Skill #1) dependency set: HTTP + ChromaDB + HTML parsing.
# ("import_name", "pip_name") tuples when the import differs from the pip name.
REQUIRED_DEPS_SYNC = [
    "requests",
    "chromadb",
    ("bs4", "beautifulsoup4"),
]


def _pip_install(packages):
    """Install the given pip packages into the current Python environment."""
    import subprocess
    print(f"[deps] Installing missing packages: {', '.join(packages)} ...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet"] + packages)
        print("[deps] Installation complete.")
        return True
    except Exception as exc:
        print(f"[deps] Auto-install failed: {exc.__class__.__name__}: {exc}")
        print("[deps] Please install manually with:\n"
              "  python -m pip install " + " ".join(packages))
        return False


def _require_deps(deps=None):
    """Check that required Python libs are importable; auto-install any that
    are missing (fully autonomous).

    `deps` is an optional list of import names to verify. When omitted the
    Skill #2 (analyze) set is used. Skill #1 (sync) passes its own list via
    REQUIRED_DEPS_SYNC. Import names are installed under the same name; use a
    tuple ("import_name", "pip_name") when they differ (e.g. bs4)."""
    if deps is None:
        deps = REQUIRED_DEPS
    missing = []
    for dep in deps:
        pip_name = dep
        if isinstance(dep, (tuple, list)):
            dep, pip_name = dep
        try:
            __import__(dep)  # noqa: F401
        except ImportError:
            missing.append(pip_name)
    if missing:
        if not _pip_install(missing):
            sys.exit(f"Missing dependencies: {', '.join(missing)}. "
                     "Install them and re-run.")


def build_parser():
    p = argparse.ArgumentParser(
        prog="analyze_agent.py",
        description=(
            "Skill #2 Analyst: read a project's local ChromaDB and generate "
            "the interactive analytics dashboard + OLAP data cube."
        ),
        epilog=(
            "Examples:\n"
            "  # Generate dashboard + OLAP cube for the project alias from .env\n"
            "  python analyze_agent.py\n"
            "\n"
            "  # Explicit alias (overrides .env) -> ./vector_dbs/EMPRelocation\n"
            "  python analyze_agent.py --alias EMPRelocation\n"
            "\n"
            "  # Explicit ChromaDB folder\n"
            "  python analyze_agent.py --db-path ./vector_dbs/EPMRLCT\n"
            "\n"
            "  # Only regenerate the dashboard (skip the OLAP cube)\n"
            "  python analyze_agent.py --skip-olap\n"
            "\n"
            "The target ChromaDB folder is resolved in this priority order:\n"
            "  1. --db-path   2. DB_PATH (.env)   3. --alias\n"
            "  4. PROJECT_ALIAS (.env)  5. JIRA_PROJECT (.env)  6. legacy\n"
            "\n"
            "Credentials/defaults can come from a local .env file:\n"
            "  JIRA_PROJECT=EPMRLCT\n"
            "  PROJECT_ALIAS=EMPRelocation\n"
            "  DB_PATH=./vector_dbs/EMPRelocation\n"
            "Keep every .env file out of git (add .env* to .gitignore)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    p.add_argument(
        "--db-path",
        help=(
            "Physical ChromaDB folder for the project. All outputs (dashboard "
            "HTML + OLAP cube CSV) are written inside this folder. "
            "[default: resolved from --alias / PROJECT_ALIAS / JIRA_PROJECT / .env]"
        ),
        default=None,
    )
    p.add_argument(
        "--alias",
        help=(
            "Project alias used to locate its ChromaDB folder: "
            "./vector_dbs/<alias>. Read from .env (PROJECT_ALIAS) if not provided."
        ),
        default=None,
    )
    p.add_argument(
        "--output",
        help=(
            "Output dashboard path. A relative path is resolved inside the "
            "project folder. [P14] The DEFAULT name is prefixed with the "
            "project (the ChromaDB folder basename): "
            "<project>_analytics_dashboard.html — pass an explicit --output "
            "to override it verbatim."
        ),
        default=DEFAULT_OUTPUT,
    )
    p.add_argument(
        "--cube-out",
        help=(
            "Output OLAP cube CSV path. A relative path is resolved inside the "
            "project folder. [P14] The DEFAULT name is prefixed with the "
            "project: <project>_jira_data_cube.csv inside the project folder."
        ),
        default=DEFAULT_CUBE,
    )
    p.add_argument(
        "--jira-collection",
        help="Chroma collection with Jira issues. [default: product_jira]",
        default="product_jira",
    )
    p.add_argument(
        "--reports-collection",
        help="Chroma collection with Jira reports. [default: product_jira_reports]",
        default="product_jira_reports",
    )
    p.add_argument(
        "--confluence-collection",
        help="Chroma collection with Confluence pages. [default: product_knowledge]",
        default="product_knowledge",
    )
    p.add_argument(
        "--env-file",
        help="Path to the .env file to load defaults from. [default: ./.env]",
        default=".env",
    )
    p.add_argument(
        "--skip-olap",
        action="store_true",
        help="Skip the OLAP data-cube analysis (dashboard only).",
    )
    p.add_argument(
        "--skip-dashboard",
        action="store_true",
        help="Skip dashboard generation (OLAP cube only).",
    )
    p.add_argument(
        "--metric-settings",
        dest="metric_settings",
        default=None,
        metavar="FILE",
        help="Path to a metric-settings JSON file (status sets, per-metric "
             "formula parameters) applied to the process metrics. See "
             "lib/metric_settings.py for the schema; the dashboard's gear "
             "panel can export the same format.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print what would be done without writing any files.",
    )
    return p


# ----------------------------------------------------------------------------
# Skill #1 (sync) configuration: defaults, db-path resolution, CLI.
# ----------------------------------------------------------------------------
DEFAULT_COLLECTION_JIRA = "product_jira"
DEFAULT_COLLECTION_JIRA_REPORTS = "product_jira_reports"
DEFAULT_COLLECTION_JIRA_VERSIONS = "product_jira_versions"
DEFAULT_COLLECTION_CONFLUENCE = "product_knowledge"
DEFAULT_JIRA_DAYS = 90  # fetch issues updated within the last N days by default
DEFAULT_BATCH_SIZE = 15
DEFAULT_ASSETS_DIR = "assets"


def resolve_sync_db_path(args, project_key):
    """Decide the ChromaDB folder for a sync run.

    Priority (mirrors the original sync_agent.py):
      1. --db-path (explicit, fully honoured)
      2. DB_PATH from .env
      3. --project-alias (or PROJECT_ALIAS from .env) -> ./vector_dbs/<alias>
      4. project_key -> ./vector_dbs/<project-key>   (for jira / jira-reports)
      5. legacy DEFAULT_DB_PATH
    """
    if args.db_path:
        return os.path.abspath(args.db_path)
    env_db = os.environ.get("DB_PATH")
    if env_db:
        return os.path.abspath(env_db)
    # Project alias (explicit) wins over the raw project key for folder naming.
    alias = args.project_alias or os.environ.get("PROJECT_ALIAS") or ""
    if alias:
        return os.path.join(DEFAULT_DB_ROOT, _slugify(alias))
    if project_key:
        return os.path.join(DEFAULT_DB_ROOT, _slugify(project_key))
    return DEFAULT_DB_PATH


def build_sync_parser():
    """CLI for sync_agent.py (Skill #1). Flags, defaults and help texts are
    kept 1:1 with the original monolithic script."""
    p = argparse.ArgumentParser(
        prog="sync_agent.py",
        description=(
            "Skill #1 Synchronizer: download Jira/Confluence content and store "
            "clean text into an isolated, portable ChromaDB folder."
        ),
        epilog=(
            "Examples:\n"
            "  # Jira into ./vector_dbs/EPMRLCT (folder auto-named by project key)\n"
            "  python sync_agent.py --service jira --project-key EPMRLCT\n"
            "\n"
            "  # Same project under a customer-facing alias folder\n"
            "  python sync_agent.py --service jira --project-key EPMRLCT "
            "--project-alias my-customer\n"
            "\n"
            "  # Confluence: extract an ENTIRE space (all pages via CQL search)\n"
            "  python sync_agent.py --service confluence --space-key KT "
            "--project-alias my-customer\n"
            "\n"
            "  # Confluence: page tree into an explicit isolated folder\n"
            "  python sync_agent.py --service confluence --page-id 2676801962 "
            "--db-path ./vector_dbs/project_v1\n"
            "\n"
            "Each project is stored in its OWN ChromaDB folder so the vector DB\n"
            "is portable and can be handed to other agents or the customer.\n"
            "\n"
            "Missing Python dependencies (requests, chromadb, beautifulsoup4)\n"
            "are auto-installed into the current environment on startup.\n"
            "\n"
            "Credentials & defaults can also be provided via a local .env file:\n"
            "  JIRA_URL=https://jiraeu.epam.com\n"
            "  JIRA_USERNAME=you@company.com\n"
            "  JIRA_TOKEN=<token>\n"
            "  JIRA_PROJECT=EPMRLCT\n"
            "  CONFLUENCE_URL=https://kb.epam.com\n"
            "  CONFLUENCE_USERNAME=you@company.com\n"
            "  CONFLUENCE_TOKEN=<token>\n"
            "  CONFLUENCE_PAGE_ID=2676801962\n"
            "  CONFLUENCE_SPACE_KEY=KT     # optional: extract whole space\n"
            "  PROJECT_ALIAS=my-customer   # optional folder alias\n"
            "  DB_PATH=./vector_dbs/EPMRLCT # optional explicit folder\n"
            "Keep every .env file out of git (add .env* to .gitignore)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    p.add_argument(
        "--service",
        choices=["all", "jira", "jira-reports", "confluence"],
        help=(
            "Which Atlassian service(s) to pull data from. "
            "'all' (default) -> pull EVERYTHING available from .env: Jira "
            "issues + related parameters, issue links, Jira board reports, "
            "project versions/releases, and Confluence pages. "
            "jira -> issues via JQL; jira-reports -> board reports "
            "(control chart, epic report, and any other report available via "
            "the GreenHopper/Agile API); confluence -> page tree via page-id. "
            "[default: all]"
        ),
        default="all",
    )
    p.add_argument(
        "--url",
        help=(
            "Base URL of the corporate instance, e.g. "
            "https://jiraeu.epam.com or https://kb.epam.com. "
            "Read from .env (JIRA_URL / CONFLUENCE_URL) if not provided."
        ),
        default=None,
    )
    p.add_argument(
        "--token",
        help=(
            "API token (or password) for basic auth. "
            "Read from .env (JIRA_TOKEN / CONFLUENCE_TOKEN) if not provided."
        ),
        default=None,
    )
    p.add_argument(
        "--username",
        help=(
            "Username (email) for basic auth. "
            "Read from .env (JIRA_USERNAME / CONFLUENCE_USERNAME) if not provided."
        ),
        default=None,
    )
    p.add_argument(
        "--db-path",
        help=(
            "Physical folder where the ChromaDB for THIS project is stored. "
            "It is created automatically if missing. "
            "[default: ./vector_dbs/<project-key> or ./vector_dbs/<alias>]"
        ),
        default=None,
    )
    p.add_argument(
        "--project-alias",
        help=(
            "A short, human-friendly name (alias) for the project, used to name "
            "its isolated ChromaDB folder: ./vector_dbs/<alias>. Useful when the "
            "Jira key is cryptic or you want a customer-facing folder name. "
            "Read from .env (PROJECT_ALIAS) if not provided. Overrides the "
            "default folder naming based on the project key."
        ),
        default=None,
    )
    p.add_argument(
        "--collection",
        help=(
            "Name of the Chroma collection inside the DB folder. "
            "[default: product_jira for jira, product_knowledge for confluence]"
        ),
        default=None,
    )

    # Jira-specific
    p.add_argument(
        "--project-key",
        help=(
            "Jira project key to pull issues from, e.g. EPMRLCT. "
            "Read from .env (JIRA_PROJECT) if not provided."
        ),
        default=None,
    )
    p.add_argument(
        "--jql",
        help=(
            "Full custom JQL query. If omitted, a default query is built: "
            "project=<project-key> AND updated >= -<days>d. Overrides --days."
        ),
        default=None,
    )
    p.add_argument(
        "--days",
        type=int,
        help=(
            "How many days back to fetch Jira issues (updated >= -Nd). "
            "[default: 90]"
        ),
        default=None,
    )

    # Confluence-specific
    p.add_argument(
        "--space-key",
        help=(
            "Confluence SPACE key to extract (e.g. KT, ENG, DOCS). When given, "
            "the ENTIRE space is downloaded (all pages via CQL search) instead "
            "of a single page tree. Read from .env (CONFLUENCE_SPACE_KEY) if "
            "not provided. Overrides --page-id."
        ),
        default=None,
    )
    p.add_argument(
        "--page-id",
        help=(
            "Confluence root page id. Its whole child tree is downloaded. "
            "Read from .env (CONFLUENCE_PAGE_ID) if not provided."
        ),
        default=None,
    )
    p.add_argument(
        "--depth",
        type=int,
        help=(
            "How many levels deep to crawl Confluence links from the pages "
            "(0 = only the page tree, 1+ = also follow in-page links to other "
            "Confluence pages). [default: 0]"
        ),
        default=0,
    )
    p.add_argument(
        "--follow-links",
        action="store_true",
        help=(
            "Follow external/Confluence links found inside page bodies and "
            "fetch the linked pages' text (deep crawl). "
        ),
    )
    p.add_argument(
        "--assets-dir",
        help=(
            "Local folder where downloaded images/attachments (architecture "
            "schemas, workflow diagrams, etc.) are saved, relative to db-path. "
            f"[default: {DEFAULT_ASSETS_DIR}]"
        ),
        default=DEFAULT_ASSETS_DIR,
    )
    p.add_argument(
        "--save-images",
        action="store_true",
        help=(
            "Download images/attachments found in Confluence pages (schemas, "
            "diagrams) to the assets folder and record them in Chroma metadata."
        ),
    )

    # Jira reports-specific
    p.add_argument(
        "--board-ids",
        help=(
            "Comma-separated board ids to fetch reports for (jira-reports only). "
            "If omitted, all boards are attempted (from API or local boards.json)."
        ),
        default=None,
    )
    p.add_argument(
        "--versions-collection",
        help=(
            "Chroma collection where Jira release/version metadata is stored "
            "(fetched for the jira service). "
            f"[default: {DEFAULT_COLLECTION_JIRA_VERSIONS}]"
        ),
        default=DEFAULT_COLLECTION_JIRA_VERSIONS,
    )

    # Behavior
    p.add_argument(
        "--batch-size",
        type=int,
        help=f"Number of items per ingest batch. [default: {DEFAULT_BATCH_SIZE}]",
        default=DEFAULT_BATCH_SIZE,
    )
    p.add_argument(
        "--env-file",
        help="Path to the .env file to load defaults from. [default: ./.env]",
        default=".env",
    )
    p.add_argument(
        "--update",
        action="store_true",
        help=(
            "Incremental update mode: fetch only the changes since the last "
            "sync and MERGE them into the existing ChromaDB (upsert by id), "
            "preserving all previously stored documents. For Jira, the JQL "
            "window is narrowed to issues updated since the last recorded "
            "sync (or the last 'updated' value already in the DB). A sync "
            "timestamp is recorded so subsequent --update runs stay "
            "incremental and consistent."
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the sync plan (service, collections, JQL, sources) and "
             "exit WITHOUT any network access or writes.",
    )
    return p



