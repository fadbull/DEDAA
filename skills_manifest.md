# DEDAA — Skills Manifest

**Data Extraction & Delivery Analytics Agent (DEDAA)**

Единый текстовый манифест правил для внешних ИИ-агентов / A single text
manifest of rules for external AI agents. Bilingual: English (EN) + Русский (RU).

---

## Table of Contents / Содержание

1. [Environment / Окружение](#1-environment--окружение)
2. [Skill #1 — Synchronizer (Data Extraction)](#2-skill-1--synchronizer-data-extraction)
3. [Skill #2 — Analyst (Dashboard Generation)](#3-skill-2--analyst-dashboard-generation)

---

## 1. Environment / Окружение

### 1.1 Dependencies / Зависимости

To build the environment, install the Python dependencies:

```bash
python -m pip install -r requirements.txt
```

Required packages:

| Package | Used by | Purpose |
|---------|---------|---------|
| `requests` | Skill #1 | HTTP calls to Jira/Confluence (with browser-like User-Agent to bypass 403) |
| `beautifulsoup4` | Skill #1 | Parse Confluence HTML / extract links & images |
| `chromadb` | Both | Vector store — read/write via the Python client (no MCP) |
| `pandas` | Skill #2 | Analytics / OLAP data cubes |

> **Auto-install:** Both agents check for missing Python libs on startup and
> auto-install them into the current environment (`python -m pip install ...`).
> `requirements.txt` is for explicit setup (CI / clean machines).

### 1.2 Configuration / Конфигурация (`.env`)

Copy `.env.example` to `.env` and fill in your real values:

```bash
cp .env.example .env
```

Example `.env`:

```
# Jira
JIRA_URL=https://jira.example.com
JIRA_USERNAME=you@company.com
JIRA_TOKEN=<token>
JIRA_PROJECT=<PROJECT_KEY>

# Confluence
CONFLUENCE_URL=https://confluence.example.com
CONFLUENCE_USERNAME=you@company.com
CONFLUENCE_TOKEN=<token>
CONFLUENCE_PAGE_ID=<page-id>
CONFLUENCE_SPACE_KEY=<SPACE_KEY>   # optional: extract whole space

# ChromaDB folder
PROJECT_ALIAS=<folder-alias>       # optional: folder alias
# DB_PATH=./vector_dbs/<PROJECT_KEY>   # optional: explicit folder
```

**Folder resolution priority (both tools):**
1. `--db-path` (explicit)
2. `DB_PATH` (.env)
3. `--alias` → `./vector_dbs/<alias>`
4. `PROJECT_ALIAS` (.env) → `./vector_dbs/<alias>`
5. `JIRA_PROJECT` (.env) → `./vector_dbs/<project-key>`
6. legacy default `./.vscode/chroma_vector_db`

> **Security:** every `.env*` file is git-ignored. Never commit credentials.
> Provide a `.env.example` template for documentation instead.

---

## 2. Skill #1 — Synchronizer (Data Extraction)

**Tool:** [`sync_agent.py`](sync_agent.py)

Downloads Jira issues or a Confluence page tree/space and stores clean text into
an isolated, project-specific ChromaDB folder (collection + metadata with URLs).
Each project gets its OWN folder so the vector DB is portable and can be handed
to other agents or the customer.

### 2.1 CLI Command Templates / Шаблоны CLI-команд

```bash
# Jira — folder auto-named ./vector_dbs/<PROJECT_KEY> (by project key)
python sync_agent.py --service jira --project-key <PROJECT_KEY>

# Same project under a customer-facing alias folder
python sync_agent.py --service jira --project-key <PROJECT_KEY> --project-alias <folder-alias>

# Confluence — extract an ENTIRE space (all pages via CQL search)
python sync_agent.py --service confluence --space-key <SPACE_KEY>

# Confluence — page tree under a root page
python sync_agent.py --service confluence --page-id <page-id>

# Confluence — page tree with deep-link crawling + image extraction
python sync_agent.py --service confluence --page-id <page-id> \
  --follow-links --depth 2 --save-images

# Jira reports — board reports (Control Chart, Epic Report, Velocity, CFD,
# Scope Change, Forecast, Sprint) via the Agile/GreenHopper API
python sync_agent.py --service jira-reports --project-key <PROJECT_KEY>

# SYNC ALL (default) — pull every data source configured in .env:
# Jira issues + related parameters, issue links, issue comments,
# board reports, project versions/releases, and Confluence pages.
python sync_agent.py

# Use credentials from .env only
python sync_agent.py --service jira --project-key <PROJECT_KEY>

# Custom time window
python sync_agent.py --service jira --project-key <PROJECT_KEY> --days 180

# Full custom JQL
python sync_agent.py --service jira --jql 'project=<PROJECT_KEY> AND updated >= -90d'

# Dry-run (print only, no DB writes)
python sync_agent.py --service jira --project-key <PROJECT_KEY> --dry-run

# Show all options
python sync_agent.py --help
```

### 2.2 Key Arguments / Ключевые аргументы

| Flag | Purpose | Default |
|------|---------|---------|
| `--service` | `all`, `jira`, `jira-reports`, or `confluence` (`all` = pull every source in `.env`) | `all` |
| `--url` | Base URL of the instance | from `.env` |
| `--token` | API token | from `.env` |
| `--username` | Login (email) | from `.env` |
| `--db-path` | Explicit ChromaDB folder | auto (see resolution) |
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
| `--env-file` | `.env` path | `./.env` |
| `--dry-run` | Print only, do not write | off |

### 2.3 Behavior Notes / Примечания по поведению

- **Per-project folders (default):** each project is stored in its own isolated
  ChromaDB folder under `./vector_dbs/`, auto-named by the project key or
  `--project-alias`. Pass `--db-path` (or `DB_PATH` in `.env`) to override.
- **Confluence whole-space extraction:** with `--space-key <KEY>` the ENTIRE
  space is downloaded (all pages via the paginated CQL search API), overriding
  `--page-id`.
- **Changelog extraction:** `sync_agent.py` requests `expand=changelog` and
  fetches ALL custom fields (`customfield_XXXXX`) so Skill #2 can compute
  cycle/lead time, time-in-status, and transition graphs.
- **Issue links extraction:** `sync_agent.py` normalizes the raw `issuelinks`
  array into structured records (type, inward/outward, direction, target key /
  summary / status / type) and stores them as a JSON string in the `issuelinks`
  metadata field. This powers the **Jira Cross-Linkage & SDLC Waste** analysis
  (Module 4) in Skill #2.
- **Image / schema extraction:** with `--save-images`, downloads image
  attachments (architecture/workflow schemas) into `<db-path>/<assets-dir>` and
  records local path + source URL in the page metadata.
- If the DB folder does not exist, it is created automatically.
- Missing Python deps are auto-installed on startup.

---

## 3. Skill #2 — Analyst (Dashboard Generation)

**Tool:** [`analyze_agent.py`](analyze_agent.py)

Reads the project's local ChromaDB **from the local DB only** (no live API
calls) and produces:
1. **Interactive HTML dashboard** → `<project>_analytics_dashboard.html`
2. **OLAP data cube** → `<project>_jira_data_cube.csv`

> **[P14] Project-prefixed defaults:** the default artifact names carry the
> project prefix (the ChromaDB folder basename — alias or Jira key), so
> dashboards/cubes accumulated across many investigated projects are
> distinguishable. An explicit `--output` / `--cube-out` overrides the
> default verbatim.

Both outputs are written **inside the resolved project folder**
(`./vector_dbs/<alias|project-key>/`), together with the ChromaDB itself — so
all data of one project lives in one place and never mixes with other projects.
Re-running for the same project updates that folder; a new project gets a new
folder.

### 3.1 CLI Command Templates / Шаблоны CLI-команд

```bash
# Generate dashboard + OLAP cube for the project alias from .env
python analyze_agent.py

# Explicit alias (overrides .env) -> ./vector_dbs/<folder-alias>
python analyze_agent.py --alias <folder-alias>

# Explicit ChromaDB folder
python analyze_agent.py --db-path ./vector_dbs/<PROJECT_KEY>

# Only regenerate the dashboard (skip OLAP)
python analyze_agent.py --skip-olap

# OLAP cube only
python analyze_agent.py --skip-dashboard

# Dry-run (print only, no files written)
python analyze_agent.py --dry-run

# Show all options
python analyze_agent.py --help
```

### 3.2 Key Arguments / Ключевые аргументы

| Flag | Purpose | Default |
|------|---------|---------|
| `--db-path` | Explicit ChromaDB folder | auto (see resolution) |
| `--alias` | Project alias folder | from `.env` (`PROJECT_ALIAS`) |
| `--output` | Dashboard output path (relative → inside project folder) | `<project>_analytics_dashboard.html` |
| `--cube-out` | OLAP cube CSV path (relative → inside project folder) | `<project>_jira_data_cube.csv` |
| `--jira-collection` | Jira collection | `product_jira` |
| `--reports-collection` | Jira reports collection | `product_jira_reports` |
| `--confluence-collection` | Confluence collection | `product_knowledge` |
| `--env-file` | `.env` path | `./.env` |
| `--skip-olap` | Skip OLAP analysis | off |
| `--skip-dashboard` | Skip dashboard generation | off |
| `--dry-run` | Print only, do not write | off |

### 3.3 Dashboard Architecture & Widget Registry

The generated dashboard is a fully interactive, standalone HTML file with three
tabs (Tailwind CSS + Chart.js + Mermaid.js via CDN):

- **Tab 1 — Product Analytics (product view):** Strategy, Architecture (with
  images), Requirements, Found Artifacts (pure text extraction, source links
  mandatory).
- **Tab 2 — Metrics & Delivery (PM):** the **Process Metrics — Trends** widget
  (20 Jira-derived metrics with per-metric settings, metric-specific reference
  bands where applicable, trend conclusions and Δ% — see below), CFD,
  Cycle/Lead Time (from changelog),
  Throughput, Velocity, Backlog Health, Scope Change Volume, Bug Growth,
  Defect Age, Quality Debts, Project Jira Reports.
- **Tab 3 — Jira Data Profile:** Schema & Field Usage, Core Workflows (Mermaid),
  Heuristic Associations, SDLC Process Matrix (Issue Type × Status), Field
  Dependencies & Trends, Transition Frequency, Time-in-Status, OLAP
  Slice & Dice constructor, and **Event-Driven Analytics** (section 8).

**Process Metrics — Trends (Tab 2):** 20 metrics defined in
`lib/dashboard/chart_config.py` (`RC_CFG`), derived per item in
`lib/dashboard/derive.py` (`rcDeriveAll`), aggregated and rendered in
`lib/dashboard/chart_render.py` (`rcApply`). Every metric supports the
Periods selector (Daily / Weekly / Sprint / Monthly / Quarterly / Annual), the
dimension selector (project / team / component / epic / person), an Issue Type
filter, and two settings levels (Widget settings + Metric settings, persisted
to `localStorage['dedaa_metric_settings']`). The Issue Type filter is not a
dimension split. By default, every metric uses the same contiguous five-period
window ending at the project's latest active two-week period. The Sprint
option currently always uses fixed two-week ISO buckets, not actual Jira
sprint boundaries, even when sprint fields are present. The selected
granularity and calendar range apply consistently across metrics. Team
filtering uses the configured field or labels for every metric. The default
production label `prod` matches production tokens, not unrelated words such
as `product` or `non-prod`; custom labels remain configurable.

Trend-based metrics require at least three periods with data. Their fitted
trend's relative change across the window is compared with a per-metric stable
band (default ±10% of the window mean; configurable from ±5% to ±30%).
Flow and Bug Growth use a separate net-balance rule: the sign of
Σ(resolved − opened/new) relative to the stable band determines whether the
backlog grew or shrank; a growing backlog is Degrading (or Recovering if its
balance trend is improving), while a shrinking backlog is Improving (or
Slowing if its balance trend is worsening). The balance trend cannot reverse
the net verdict. A balanced net uses the balance trend: rising = Improving,
falling = Degrading, and within the stable band = Stable. Backlog Health uses
its configured healthy coverage band rather than the standard slope verdict.
Δ compares the last period with the adjacent previous period. Empty selections
and insufficient data do not produce fabricated trend verdicts (`RC_WIN_STATE`
keeps the chart, tooltip, avg-box, conclusion and settings panel describing
the same filtered-window state). The widget displays Jira-derived
measurements only; it does not establish an as-is assessment or baseline.

### 3.4 Event-Driven Analytics (Tab 3, section 8)

Advanced event/trigger analysis computed from the Jira changelog + parent-child
relationships. Requires `parent_key` in the Jira metadata (populated by
`sync_agent.py`). If no parent data is present, the affected widgets render
"N/A" gracefully.

- **Module 1 — Jira Defect Causality & SDLC Triggers** (three sub-widgets).
  The parent ("Target Scope") of every defect is resolved by **hard linkage**:
  - **Sub-Bug** → uses the system `parent` field (its Bug/Story/Task).
  - **Bug** → if `parent` is empty, scans `issuelinks` for a linked Story/Task
    (`is blocked by` / `relates to` / `associated` / `depends`); the first such
    Story/Task becomes the parent feature.
  - **(a) Story Status at Defect Birth (Doughnut):** for each Bug/Sub-Bug, the
    parent's status at the exact second the defect was created (from the
    parent's changelog, defaulting to `Open`). Answers "in which phases do our
    stories generate bugs?".
  - **(b) Sub-task Closure Automation Tracker (Callout cards + Mermaid flow):**
    for each Story/Task with Sub-task children, `T_last_child = max(updated)`
    among children in `Closed`/`Resolved`; if the parent's status changed within
    **≤600 s (10 min)** it is an **automation trigger**, otherwise **Manual
    Stagnation** (broken automation). Shows `X% auto / Y% stuck`.
  - **(c) Sub-Bug Creation Constraints Validation (Data grid):** for each
    `[Story/Task/Bug → Sub-Bug]` pair, captures the parent's status at the
    Sub-Bug's creation second and tests the hypothesis that Sub-Bugs are created
    only while the parent is `In Testing` (100%). Rejects the hypothesis with
    the real status distribution if not 100%.
- **Module 2 — Auto-transit / Parent-Child sync (Stacked bar + Mermaid flow):**
  groups Sub-tasks by parent; for each parent finds the last closed child's
  timestamp, then measures how long the parent takes to change status afterward.
  A transition within **≤300 s (5 min)** is an **Automation Rule (auto)**;
  otherwise it is **Manual Leakage (manual)**. Renders a target-status flow graph
  with the auto/manual split on each edge.
- **Module 3 — Metadata impact (Bubble chart):** splits issues into cohorts by
  label (labels appearing in ≥3 issues only), computing each cohort's **median
  cycle time** and **ping-pong (rework) rate** versus the project baseline.
  Cohorts above baseline in BOTH dimensions are flagged **⚠️ High Risk Scope**
  and highlighted red.
- **Module 4 — Jira Cross-Linkage & SDLC Waste (Doughnut + callout cards +
  Mermaid network):** classifies every `issuelinks` record across ALL issues
  (horizontal links, not just the vertical parent/child hierarchy) into 4
  macro-categories of SDLC waste:
  - **A · Hard Blockers** (`blocks`, `is blocked by`, `Depend`) — computes
    **blocker reaction time** (blocker created → blocked issue In Progress) and
    the **stagnation rate** for targets that stayed in backlog **>24 working
    hours**.
  - **B · Process Rework** (`causes`, `is caused by`) — counts **escaped
    defects** (a cause created *after* its source issue was closed).
  - **C · Scope Duplication** (`duplicates`, `clones`, `Cloners`) — computes
    **Waste Scope** = sunk hours/days spent In Progress on issues later closed
    with resolution `Duplicate`/`Won't Fix`.
  - **D · Soft Associations** (`relates to`, `Related To`, `Part of`) — builds a
    **closure sync matrix** (ratio of linked pairs closed within the same
    month).
  Renders a category-distribution doughnut, one **Process Waste callout card**
  per category (each shows "N/A" when the category is absent), and an
  **interdependence network** (Mermaid graph, edges colored by category, capped
  at 60 visible / 400 collected). Requires `issuelinks` metadata (populated by
  `sync_agent.py`).

**Mandatory rules:**
- **Source links:** every finding/claim must carry a clickable source `url`
  from metadata; if unavailable, render "N/A".
- **Per-tab data-source header:** each tab shows the Chroma DB path, collection,
  HNSW folder id, and folder size in MB.
- **Data completeness:** if data is missing, render "N/A" inside the widget —
  never guess or break the layout.
- **Configurable granularity:** the Process Metrics — Trends widget defaults
  to fixed two-week periods, anchored on the latest active period, and shows
  the latest five periods. Actual Jira sprint boundaries are not yet used.
  The Periods selector switches to Daily / Weekly / Sprint / Monthly /
  Quarterly / Annual; tooltips stay granularity-neutral («per selected
  period»).
- **Configurable status sets:** Cycle Time / Lead Time / QA / review metrics
  read their start/end statuses from the Widget settings status sets (the
  tooltip's dynamic Formula: section always shows the ACTUAL configured
  statuses; the base tooltips use neutral wording like «first dev-start
  status» / «first QA-exit status»).

### 3.5 OLAP Analyser

The OLAP analyser lives in `lib/olap_analyser.py` and runs automatically
(unless `--skip-olap`). It computes field density, status frequency, median
time-in-status, transition frequency (incl. ping-pong), and a multidimensional
pivot cube (`Issue Type × Status → count`) saved to CSV. It additionally emits a
**cross-linkage cube** (`Issue Type × Link Category A/B/C/D → count`) saved to
`<cube>_crosslink.csv` when `issuelinks` metadata is present.

---

## 4. General Rules / Общие правила

- **Always cite sources:** attach the source `url` to every claim.
- **Respect "N/A":** if a widget shows "N/A", do not fabricate numbers.
- **Configurable lens:** the Trends widget supports Daily…Annual periods —
  match the narrative to the selected granularity instead of assuming a fixed
  period length.
- **Actionable, not generic:** tie every recommendation to a specific metric
  and its source.

---

*DEDAA — Data Extraction & Delivery Analytics Agent. Autonomous CLI utilities
for Atlassian data extraction and analytics dashboard generation.*
