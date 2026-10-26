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
- Are fully self-contained Python scripts with built-in `--help`.
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
├── sync_agent.py              # Skill #1 — Synchronizer (data extraction)
├── analyze_agent.py           # Skill #2 — Analyst (dashboard + OLAP) — fully self-contained
├── requirements.txt           # Python dependencies
├── .env.example               # Configuration template (copy to .env)
├── .gitignore                 # Ignores .env* and vector DBs
├── README.md                  # This file
├── skills_manifest.md         # Full rules manifest for external AI agents (EN+RU)
└── vector_dbs/                # One folder PER project (ChromaDB + dashboard + cube)
    └── EMPRelocation/         # Example project folder — ALL of its data lives here
        ├── chroma.sqlite3     #   ChromaDB (product_jira, product_knowledge, ...)
        ├── assets/            #   Confluence images
        ├── <hnsw-folders>/    #   Vector index segments
        ├── analytics_dashboard.html  #   Generated dashboard (Skill #2)
        └── jira_data_cube.csv        #   Generated OLAP cube (Skill #2)
```

> `analyze_agent.py` is a **single self-contained file (~2800 lines)** that inlines
> all Skill #2 logic (dashboard metric computations, HTML renderer, and the OLAP
> data-cube analyser). No separate modules are required.
>
> **Per-project isolation:** every project (alias / key) gets its own folder
> `./vector_dbs/<alias|project-key>/`. The ChromaDB, the generated dashboard
> `analytics_dashboard.html` and the OLAP cube `jira_data_cube.csv` are all
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
JIRA_URL=https://jiraeu.epam.com
JIRA_USERNAME=you@company.com
JIRA_TOKEN=<token>
JIRA_PROJECT=EPMRLCT

CONFLUENCE_URL=https://kb.epam.com
CONFLUENCE_USERNAME=you@company.com
CONFLUENCE_TOKEN=<token>
CONFLUENCE_PAGE_ID=2676801962
CONFLUENCE_SPACE_KEY=EPMRLMEIMR   # optional: extract whole space

PROJECT_ALIAS=EMPRelocation        # optional: folder alias
# DB_PATH=./vector_dbs/EPMRLCT    # optional: explicit folder
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

# Jira — folder auto-named ./vector_dbs/EPMRLCT (by project key)
python sync_agent.py --service jira --project-key EPMRLCT

# Same project under a customer-facing alias folder -> ./vector_dbs/EMPRelocation
python sync_agent.py --service jira --project-key EPMRLCT --project-alias EMPRelocation

# Confluence — extract an ENTIRE space (all pages via CQL search)
python sync_agent.py --service confluence --space-key EPMRLMEIMR

# Confluence — page tree under a root page
python sync_agent.py --service confluence --page-id 2676801962

# Jira board reports (control chart, epic report, ...) -> product_jira_reports
python sync_agent.py --service jira-reports --project-key EPMRLCT

# The `jira` service ALSO fetches the project's release/version metadata
# (name, dates, released/archived/overdue) -> product_jira_versions
python sync_agent.py --service jira --project-key EPMRLCT

# INCREMENTAL UPDATE — merge only changes since the last sync into the
# existing DB (upsert by id), preserving all previously stored documents.
python sync_agent.py --service jira --project-key EPMRLCT --update

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
(`analytics_dashboard.html`) AND the OLAP data cube (`jira_data_cube.csv`).
Both outputs are written **inside the resolved project folder**
(`./vector_dbs/<alias|project-key>/`), so all of a project's data stays in one
place. The dashboard's **Jira Data Profile** tab includes **Event-Driven
Analytics** — bug-creation triggers (parent status at bug creation), auto-transit
/ parent-child sync (automation rules vs manual leakage), label/custom-field
impact on cycle time and rework, and a **Jira Cross-Linkage & SDLC Waste
Dashboard** that classifies every `issuelinks` record into 4 macro-categories
(A Hard Blockers, B Process Rework, C Scope Duplication, D Soft Associations)
with per-category waste metrics, an interdependence network, and a terminal
summary table. The OLAP analyser also emits a cross-linkage cube
(`jira_data_cube_crosslink.csv`). See
[`skills_manifest.md`](skills_manifest.md) for the full specification.

```bash
# Generate dashboard + OLAP cube for the project alias from .env
# -> ./vector_dbs/EMPRelocation/{analytics_dashboard.html, jira_data_cube.csv}
python analyze_agent.py

# Explicit alias (overrides .env) -> ./vector_dbs/EMPRelocation
python analyze_agent.py --alias EMPRelocation

# Explicit ChromaDB folder (outputs land inside it)
python analyze_agent.py --db-path ./vector_dbs/EPMRLCT

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
| `--output` | Dashboard path (relative → inside project folder) | `analytics_dashboard.html` |
| `--cube-out` | OLAP cube CSV path (relative → inside project folder) | `jira_data_cube.csv` |
| `--jira-collection` | Jira collection | `product_jira` |
| `--reports-collection` | Jira reports collection | `product_jira_reports` |
| `--confluence-collection` | Confluence collection | `product_knowledge` |
| `--env-file` | `.env` path | `./.env` |
| `--skip-olap` | Skip OLAP analysis (dashboard only) | off |
| `--skip-dashboard` | Skip dashboard generation (OLAP only) | off |
| `--dry-run` | Print only, do not write | off |

---

## Role Models / Ролевые модели

How external AI agents should interpret the generated dashboard in the roles of
**Senior PO/BA** and **Senior PM** is described in
[`skills_manifest.md`](skills_manifest.md) (§ Role Models / Ролевые модели).

---

## License / Лицензия

Internal tooling. See repository policy.
