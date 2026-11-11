# Data Extraction & Delivery Analytics Agent (DEDAA)

**DEDAA** — автономный пакет Python CLI-утилит для (1) **извлечения данных** из
корпоративных источников Atlassian (Jira / Confluence) в изолированную папку
ChromaDB и (2) **генерации интерактивного HTML-дашборда** с аналитикой по этим
данным.

**DEDAA** is an autonomous Python CLI toolkit that (1) **extracts data** from
corporate Atlassian sources (Jira / Confluence) into an isolated ChromaDB
folder and (2) **generates an interactive HTML analytics dashboard** from that
local data.

---

## Overview / Обзор

The toolkit is delivered as **two independent, autonomous CLI utilities** that
run unchanged in any environment, with any AI orchestrator, or manually from a
terminal:

| Tool | Skill | Purpose |
|------|-------|---------|
| [`sync_agent.py`](sync_agent.py) | #1 | Download Jira/Confluence → per-project ChromaDB folder |
| [`analyze_agent.py`](analyze_agent.py) | #2 | Read project ChromaDB → interactive dashboard + OLAP cube |

Both tools:
- Are thin CLI entry points (all logic in `lib/`) with built-in `--help`
  that works without the heavy dependencies installed.
- Resolve the project ChromaDB folder from `--db-path` / `--alias` / `.env`
  (`PROJECT_ALIAS`, `JIRA_PROJECT`, `DB_PATH`).
- Access ChromaDB **directly via the Python `chromadb` library** (no MCP, no
  extra tokens).
- **Auto-install missing Python dependencies** on startup.
- Load credentials/config from a local `.env` (git-ignored).
- Support `--dry-run`.

---

## Project Structure / Структура проекта

```
DEDAA/
├── sync_agent.py              # Skill #1 — thin CLI: parse → deps → run_sync
├── analyze_agent.py           # Skill #2 — thin CLI: parse → deps → run_dashboard/run_olap
├── requirements.txt           # Python dependencies
├── .env.example               # Configuration template (copy to .env)
├── .gitignore                 # Ignores .env*, venvs, runtime artifacts
├── README.md                  # This file
├── skills_manifest.md         # Full rules manifest for external AI agents (EN+RU)
├── lib/                       # Shared sub-package (both skills)
│   ├── config.py              #   dotenv, CLI parsers, dep management, db-path resolution
│   ├── chromadb_utils.py      #   ChromaDB loading / collection resolution
│   ├── date_utils.py          #   Date parsing, bucketing, status grouping
│   ├── compute_jira.py        #   PM metrics from Jira issues (Skill #2)
│   ├── metric_settings.py     #   Metric settings schema + validation
│   ├── compute_product.py     #   compute_product(), compute_reports()
│   ├── compute_artifacts.py   #   Confluence text scanning (Skill #2)
│   ├── compute_profile.py     #   Jira data profile (field density, workflows)
│   ├── compute_events.py      #   Event-driven analytics (bug triggers, sync)
│   ├── compute_crosslink.py   #   Cross-linkage / SDLC waste analysis
│   ├── dashboard_helpers.py   #   esc(), js_list(), json_str() helpers
│   ├── dashboard_html.py      #   Dashboard shell assembly
│   ├── olap_analyser.py       #   OLAP cube: load_issues(), time-in-status, pivot
│   ├── runners.py             #   run_olap(), run_dashboard() orchestration
│   ├── atlassian_api.py       #   AtlassianAPI HTTP client (Skill #1)
│   ├── sync_jira.py           #   Jira issues + versions + reports
│   ├── sync_confluence.py     #   Confluence pages/space/images
│   ├── sync_ingest.py         #   Ingest + incremental-sync markers
│   ├── sync_runners.py        #   run_sync() dispatch
│   └── dashboard/             #   Dashboard renderer sub-package
│       ├── prepare.py         #     build_dashboard() render context (Tab 1/3)
│       ├── trends_data.py     #     Trends widget data prep (Tab 2)
│       ├── scripts_tab3.py    #     Tab 3 inline scripts
│       ├── chart_config.py    #     RC_CFG / RC_TIP / RC_TIP_BOX / RC_REF_LINES
│       ├── chart_render.py    #     rcApply() — aggregation, state, rendering
│       ├── derive.py          #     rcDeriveAll() — per-metric item derivation
│       ├── granularity.py     #     buckets, dims, rcItemTeams
│       ├── settings_metric.py #     Metric settings panel + rcTipFor/rcFormulaText
│       ├── settings_widget.py #     Widget settings panel
│       ├── cfd_widget.py      #     Cumulative Flow Diagram widget
│       └── shell.py           #     HTML shell, tabs, CSS
├── tests/                     # Portable Jira Trends regression tests
└── vector_dbs/                # One folder PER project (git-ignored, never committed)
    └── <project-folder>/      #   created per project key / alias — ALL of the
        ├── chroma.sqlite3     #   project's data lives here (see § Per-project
        ├── assets/            #   isolation below for the folder contents)
        └── …
```

> Both agents are **thin CLI entry points**; all logic lives in the `lib/`
> sub-package (compute_*, dashboard/, sync_* modules). Portable regression
> tests live in `tests/` and use synthetic Jira records.
>
> **Per-project isolation:** every project (alias / key) gets its own folder
> `./vector_dbs/<alias|project-key>/`. The ChromaDB, the generated dashboard
> `<project>_analytics_dashboard.html` and the OLAP cube
> `<project>_jira_data_cube.csv` are all
> written **inside that project folder** — so data from different projects never
> mix. Re-running the tools for the same project updates that folder; a new
> project creates a new folder.

---

## Environment / Окружение

### Dependencies / Зависимости

```
python -m pip install -r requirements.txt
```

Required packages:
- `requests`, `beautifulsoup4` — Skill #1 (HTTP + HTML parsing)
- `chromadb` — shared (ChromaDB vector store, Python client)
- `pandas` — Skill #2 (analytics / OLAP)

> Both agents auto-install any missing packages on startup. The
> `requirements.txt` is for explicit setup (CI / clean machines).

### Configuration / Конфигурация (.env)

Copy `.env.example` to `.env` and fill in your credentials:

```
JIRA_URL=https://jira.example.com
JIRA_USERNAME=you@company.com
JIRA_TOKEN=<token>
JIRA_PROJECT=<PROJECT_KEY>

CONFLUENCE_URL=https://confluence.example.com
CONFLUENCE_USERNAME=you@company.com
CONFLUENCE_TOKEN=<token>
CONFLUENCE_PAGE_ID=<page-id>
CONFLUENCE_SPACE_KEY=<SPACE_KEY>   # optional: extract whole space

PROJECT_ALIAS=<folder-alias>       # optional: folder alias
# DB_PATH=./vector_dbs/<PROJECT_KEY>   # optional: explicit folder
```

> **Security:** every `.env*` file is git-ignored. Never commit credentials.

---

## Skill #1 — `sync_agent.py` (Data Extraction)

Downloads Jira issues / Confluence pages into an isolated, portable ChromaDB
folder (one folder per project). See [`skills_manifest.md`](skills_manifest.md)
for the full specification.

**Default behavior:** run with no `--service` (and a populated `.env`) to pull
**EVERYTHING available** — Jira issues + related parameters, issue links,
issue comments, Jira board reports, project versions/releases, and Confluence
pages — each into its own collection.

```bash
# SYNC ALL (default) — pull every data source configured in .env
python sync_agent.py

# Jira — folder auto-named ./vector_dbs/<PROJECT_KEY> (by project key)
python sync_agent.py --service jira --project-key <PROJECT_KEY>

# Same project under a customer-facing alias folder -> ./vector_dbs/<alias>
python sync_agent.py --service jira --project-key <PROJECT_KEY> --project-alias <folder-alias>

# Confluence — extract an ENTIRE space (all pages via CQL search)
python sync_agent.py --service confluence --space-key <SPACE_KEY>

# Confluence — page tree under a root page
python sync_agent.py --service confluence --page-id <page-id>

# Jira board reports (control chart, epic report, ...) -> product_jira_reports
python sync_agent.py --service jira-reports --project-key <PROJECT_KEY>

# The `jira` service ALSO fetches the project's release/version metadata
# (name, dates, released/archived/overdue) -> product_jira_versions
python sync_agent.py --service jira --project-key <PROJECT_KEY>

# INCREMENTAL UPDATE — merge only changes since the last sync into the
# existing DB (upsert by id), preserving all previously stored documents.
python sync_agent.py --service jira --project-key <PROJECT_KEY> --update

# Show all options
python sync_agent.py --help
```

**Key arguments & defaults:**

| Flag | Purpose | Default |
|------|---------|---------|
| `--service` | `all`, `jira`, `jira-reports`, or `confluence` (`all` = pull every source in `.env`) | `all` |
| `--url` | Base URL of the instance | from `.env` (`JIRA_URL`/`CONFLUENCE_URL`) |
| `--token` | API token | from `.env` (`JIRA_TOKEN`/`CONFLUENCE_TOKEN`) |
| `--username` | Login (email) | from `.env` (`JIRA_USERNAME`/`CONFLUENCE_USERNAME`) |
| `--db-path` | Explicit ChromaDB folder (auto-created) | `./vector_dbs/<project-key>` or `./vector_dbs/<alias>` |
| `--project-alias` | Friendly folder alias | from `.env` (`PROJECT_ALIAS`) |
| `--collection` | Chroma collection name | `product_jira` / `product_knowledge` / `product_jira_reports` |
| `--project-key` | Jira project key | from `.env` (`JIRA_PROJECT`) |
| `--jql` | Custom JQL (overrides `--days`) | built from key + days |
| `--days` | How many days back to fetch | `90` |
| `--space-key` | Confluence SPACE key (whole space) | from `.env` (`CONFLUENCE_SPACE_KEY`) |
| `--page-id` | Confluence root page id | from `.env` (`CONFLUENCE_PAGE_ID`) |
| `--depth` | Deep-crawl depth (0 = tree only) | `0` |
| `--follow-links` | Follow in-page Confluence links | off |
| `--save-images` | Download image/attachment artifacts | off |
| `--assets-dir` | Assets folder (under db-path) | `assets` |
| `--board-ids` | Board ids for `jira-reports` | all boards |
| `--versions-collection` | Chroma collection for Jira release/version metadata | `product_jira_versions` |
| `--batch-size` | Items per ingest batch | `15` |
| `--update` | Incremental update: merge only changes since the last sync (upsert by id), preserving existing docs | off |
| `--dry-run` | Print only, do not write | off |

---

## Skill #2 — `analyze_agent.py` (Analytics & Dashboard)

Reads the project's local ChromaDB and produces BOTH the interactive dashboard
(`<project>_analytics_dashboard.html`) AND the OLAP data cube
(`<project>_jira_data_cube.csv`) — the project prefix (the ChromaDB folder
basename: alias or Jira key) keeps dashboards/cubes of many investigated
projects distinguishable.
Both outputs are written **inside the resolved project folder**
(`./vector_dbs/<alias|project-key>/`), so all of a project's data stays in one
place. The dashboard's **Process Metrics — Trends** widget (Metrics & Delivery
tab) renders 20 Jira-derived process metrics — Requirements Cycle/Rework,
Issue Lead Time, Throughput, Velocity, Cycle Time, Backlog Health, Design
Review Turnaround, Bug Growth, Production Leakage, Bug Fixing Allocation,
Incident Frequency, Time in QA, Defect Density, WIP, Flow Efficiency, Defect
Escape Rate, Clarification/Review Cycle Count — with configurable periods
(Daily…Annual), dimensions, Issue Type filters, two settings levels (Widget +
Metric), and trend conclusions with Δ%. By default, all metrics use the same
five-period window (or the metric's configured Default N).
For Sprint, Widget settings → Sprint data availability controls the source:
`auto` uses real Jira sprints when **more than 50% of all project issues**
have a populated Sprint field, before dimension/type/date filters. Undated
Sprint values count toward that threshold but cannot supply timeline periods.
`available` forces real sprints; `none` forces two-week ISO calendar buckets.
Auto below the threshold also uses those calendar buckets. Actual sprint
IDs, names and irregular boundaries are preserved; closed sprints use their
completion date, falling back to a valid planned end. Existing text caches
are supported without a Jira re-sync.

The real-sprint default is the latest N **completed** sprints with project
activity. Manual dates select whole intersecting sprint periods, including
unfinished ones; their partial data is excluded from comparative trends and
snapshots never extend past the captured Jira data. Issues without Sprint,
unusable sprint dates and ambiguous overlapping memberships are excluded
from real-sprint calculations and explained in the existing tooltip.
Unavailable real-sprint periods show N/A, not invented two-week sprints.
Calendar granularities retain all eligible issues, including those without
Sprint, and keep the latest active contiguous N-period window.
Both widget and per-metric settings, units, anchors and issue-type filters
remain effective. The separate Delivery CFD retains its calendar periods.
Team filters resolve the configured field or labels for all metric records.
The default production label `prod` matches production tokens such as `prod`,
`production`, and `prod_bug`, but not `product` or `non-prod`; an explicit
custom label remains supported. Trend verdicts require at
least three periods with data; the configurable stable band defaults to ±10%
of the window mean. Flow and Bug Growth verdicts compare the net
resolved-minus-opened balance with that stable band: a growing backlog is
Degrading (or Recovering if its balance trend is improving), while a shrinking
backlog is Improving (or Slowing if its balance trend is worsening). The
balance trend cannot reverse the net verdict. The widget reports Jira-derived measurements only;
it does not establish an as-is assessment or baseline. The **Jira Data Profile**
tab counts observed Jira status transitions and same-issue returns. Time-in-status
uses timestamped intervals with known boundaries; initial and final intervals
require complete history and, for the latter, a trustworthy Jira snapshot time.
The current synchronizer does not establish a common project snapshot time, so
parent-child closure timing is N/A for its snapshots rather than calculated to
today. Parent status is Unknown if history completeness is unverified.
The Issue and Link OLAP tables paginate all slices; issues may belong to
several component slices while their overall count remains unique. Lifecycle
uses the Jira resolution date, and link totals count directed records.
Cross-Linkage classifies link records into four categories; unavailable unblock
timing is N/A, duplicate elapsed time is calendar time rather than logged effort,
and associations do not prove causation. The OLAP
analyser also emits a cross-linkage cube (`jira_data_cube_crosslink.csv`).
See [`skills_manifest.md`](skills_manifest.md) for the full specification.

```bash
# Generate dashboard + OLAP cube for the project alias from .env
# -> ./vector_dbs/<folder-alias>/{
#      <folder-alias>_analytics_dashboard.html,
#      <folder-alias>_jira_data_cube.csv}
python analyze_agent.py

# Explicit alias (overrides .env) -> ./vector_dbs/<folder-alias>
python analyze_agent.py --alias <folder-alias>

# Explicit ChromaDB folder (outputs land inside it)
python analyze_agent.py --db-path ./vector_dbs/<PROJECT_KEY>

# Only regenerate the dashboard (skip OLAP)
python analyze_agent.py --skip-olap

# OLAP cube only
python analyze_agent.py --skip-dashboard

# Show all options
python analyze_agent.py --help
```

**Key arguments & defaults:**

| Flag | Purpose | Default |
|------|---------|---------|
| `--db-path` | Project ChromaDB folder (outputs written inside it) | auto: `--alias` / `PROJECT_ALIAS` / `JIRA_PROJECT` / `.env` |
| `--alias` | Project alias folder | from `.env` (`PROJECT_ALIAS`) |
| `--output` | Dashboard path (relative → inside project folder) | `<project>_analytics_dashboard.html` |
| `--cube-out` | OLAP cube CSV path (relative → inside project folder) | `<project>_jira_data_cube.csv` |
| `--jira-collection` | Jira collection | `product_jira` |
| `--reports-collection` | Jira reports collection | `product_jira_reports` |
| `--confluence-collection` | Confluence collection | `product_knowledge` |
| `--env-file` | `.env` path | `./.env` |
| `--skip-olap` | Skip OLAP analysis (dashboard only) | off |
| `--skip-dashboard` | Skip dashboard generation (OLAP only) | off |
| `--dry-run` | Print only, do not write | off |

### Regression tests

From the project root, run the portable tests with Python 3 and Node.js 18 or
newer; they use only standard libraries and do not require Jira data:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/test_trends_regressions.js tests/test_profile_olap.js
```

The Node.js test loads the embedded JavaScript through `python3`. Set `PYTHON`
to a Python executable if it is not available under that name.
The suites cover Sprint parsing/coverage, all metric families, settings
lifecycle, snapshot membership, chart/drilldown agreement and Jira Data Profile
transition, timing, link and OLAP regressions. To also execute
locally regenerated HTML, set `DEDAA_DASHBOARDS` to a JSON array of
`{"path":"<local HTML path>","source":"jira"}` entries (`"calendar"` for a
fallback project) before the Node command. Missing explicitly requested files
fail the integration test; without this variable, only that optional
private-data integration test is skipped. Do not commit the input dashboards.

---

## License / Лицензия

Internal tooling. See repository policy.
