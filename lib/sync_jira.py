"""Jira sync (Skill #1): issues, versions/releases and board reports.

Extracted 1:1 from the original monolithic sync_agent.py."""
import json
import os

from .atlassian_api import scalar, strip_html_to_text


def fetch_field_meta(api):
    return {f["id"]: f["name"] for f in api.get("/rest/api/2/field")}


def build_issue_text(key, fields, field_names):
    parent = fields.get("parent")
    parent_line = f"Parent: {scalar(parent)}" if parent else None
    lines = [
        f"Issue: {key}",
        f"Summary: {scalar(fields.get('summary'))}",
        f"Type: {scalar(fields.get('issuetype'))}",
    ]
    if parent_line:
        lines.append(parent_line)
    lines += [
        f"Status: {scalar(fields.get('status'))}",
        f"Priority: {scalar(fields.get('priority'))}",
        f"Resolution: {scalar(fields.get('resolution'))}",
        f"Assignee: {scalar(fields.get('assignee'))}",
        f"Reporter: {scalar(fields.get('reporter'))}",
        f"Creator: {scalar(fields.get('creator'))}",
        f"Created: {fields.get('created')}",
        f"Updated: {fields.get('updated')}",
        f"Due date: {fields.get('duedate')}",
        f"Resolution date: {fields.get('resolutiondate')}",
        f"Labels: {scalar(fields.get('labels'))}",
        f"Components: {scalar(fields.get('components'))}",
        f"Fix versions: {scalar(fields.get('fixVersions'))}",
        f"Versions: {scalar(fields.get('versions'))}",
        f"Linked issues: {scalar(fields.get('issuelinks'))}",
        "Issue links:",
    ]
    parsed = parse_issuelinks(fields.get("issuelinks"))
    if parsed:
        for lk in parsed:
            lines.append(
                f"  {lk['type']} ({lk['direction']}) -> {lk['target_key']} "
                f"[{lk['target_type']} / {lk['target_status']}] "
                f"{lk['target_summary']}")
    lines += [
        f"Subtasks: {scalar(fields.get('subtasks'))}",
        "Description:",
    ]
    desc = fields.get("description")
    lines.append(scalar(desc) if desc else "(no description)")
    for fid, fname in field_names.items():
        if not fid.startswith("customfield_"):
            continue
        val = fields.get(fid)
        if val in (None, "", []):
            continue
        s = scalar(val)
        if s:
            lines.append(f"{fname}: {s}")
    return "\n".join(lines)


def parse_issuelinks(links):
    """Normalize a Jira `issuelinks` array into a flat list of structured link
    records: {type, inward, outward, direction, target_key, target_summary,
    target_status, target_type}. Each raw link has an outwardIssue and/or an
    inwardIssue; 'direction' tells which role THIS issue plays:
      'outward' -> this issue is the outward (source) side
      'inward'  -> this issue is the inward (target) side
    The counterpart key is the *other* issue in the link."""
    out = []
    for l in links or []:
        if not isinstance(l, dict):
            continue
        lt = l.get("type") or {}
        lname = (lt.get("name") or "").strip() or "Unknown"
        inward_label = (lt.get("inward") or "").strip()
        outward_label = (lt.get("outward") or "").strip()
        # Outward side: this issue depends on / blocks the outward issue.
        outward = l.get("outwardIssue") or {}
        inward = l.get("inwardIssue") or {}
        if outward:
            out.append({
                "type": lname, "inward": inward_label, "outward": outward_label,
                "direction": "outward",
                "target_key": outward.get("key"),
                "target_summary": scalar(outward.get("fields", {}).get("summary")),
                "target_status": scalar(outward.get("fields", {}).get("status")),
                "target_type": scalar(outward.get("fields", {}).get("issuetype")),
            })
        if inward:
            out.append({
                "type": lname, "inward": inward_label, "outward": outward_label,
                "direction": "inward",
                "target_key": inward.get("key"),
                "target_summary": scalar(inward.get("fields", {}).get("summary")),
                "target_status": scalar(inward.get("fields", {}).get("status")),
                "target_type": scalar(inward.get("fields", {}).get("issuetype")),
            })
    return out


def extract_status_timestamps(changelog):
    """From an issue changelog, extract key status-transition timestamps.
    Returns dict with 'in_progress' (first In Progress), 'done' (first Done/
    Closed/Resolved) and a compact status history list."""
    first_in_progress = None
    first_done = None
    history = []
    for h in changelog or []:
        created = h.get("created")
        for item in h.get("items", []):
            if item.get("field") != "status":
                continue
            to = item.get("toString", "")
            history.append({"t": created, "from": item.get("fromString"),
                            "to": to})
            low = to.strip().lower()
            if first_in_progress is None and low == "in progress":
                first_in_progress = created
            if first_done is None and low in ("closed", "done", "resolved",
                                              "complete", "completed",
                                              "verified", "released"):
                first_done = created
    return {
        "in_progress": first_in_progress,
        "done": first_done,
        "history": history,
    }


def sync_jira(api, project_key, jql, field_names, url_base, days):
    print(f"[Jira] Querying issues for project '{project_key}'...")
    issues, start, page = [], 0, 100
    while True:
        d = api.get("/rest/api/2/search", params={
            "jql": jql, "startAt": start, "maxResults": page,
            "expand": "renderedFields,changelog", "fields": "*all",
        })
        issues.extend(d["issues"])
        total = d.get("total", 0)
        print(f"  fetched {len(issues)}/{total}")
        if start + len(d["issues"]) >= total:
            break
        start += len(d["issues"])
    print(f"[Jira] Total issues: {len(issues)}")

    docs = []
    for iss in issues:
        ts = extract_status_timestamps(
            (iss.get("changelog") or {}).get("histories", []))
        parent_key = None
        parent = iss["fields"].get("parent")
        if isinstance(parent, dict):
            parent_key = parent.get("key") or scalar(parent)
        issuelinks = parse_issuelinks(iss["fields"].get("issuelinks"))
        comments = (iss["fields"].get("comment") or {}).get("comments") or []
        comments_meta = []
        for c in comments:
            body = c.get("body")
            if isinstance(body, dict):
                body = scalar(body)
            if body:
                body = strip_html_to_text(body)
            comments_meta.append({
                "author": scalar(c.get("author")),
                "created": c.get("created"),
                "body": body,
            })
        meta = {
            "source": "jira",
            "project": project_key,
            "issue_key": iss["key"],
            "issue_id": iss.get("id"),
            "summary": scalar(iss["fields"].get("summary")),
            "type": scalar(iss["fields"].get("issuetype")),
            "status": scalar(iss["fields"].get("status")),
            "priority": scalar(iss["fields"].get("priority")),
            "resolution": scalar(iss["fields"].get("resolution")),
            "resolutiondate": iss["fields"].get("resolutiondate"),
            "assignee": scalar(iss["fields"].get("assignee")),
            "reporter": scalar(iss["fields"].get("reporter")),
            "components": scalar(iss["fields"].get("components")),
            "labels": scalar(iss["fields"].get("labels")),
            "duedate": iss["fields"].get("duedate"),
            "created": iss["fields"].get("created"),
            "updated": iss["fields"].get("updated"),
            "in_progress_date": ts["in_progress"],
            "done_date": ts["done"],
            "parent_key": parent_key,
            # Epic linkage: Jira stores the epic key in customfield_14500
            # ("Epic Link"). Fall back to parent_key if the custom field is
            # absent (e.g. subtasks linked via the parent field).
            "epic": scalar(iss["fields"].get("customfield_14500")) or parent_key,
            "issuelinks": json.dumps(issuelinks, ensure_ascii=False)
            if issuelinks else None,
            "comment_count": len(comments_meta),
            "comments": json.dumps(comments_meta, ensure_ascii=False)
            if comments_meta else None,
            "url": f"{url_base}/browse/{iss['key']}",
        }
        # Append status history to the document text for traceability
        text = build_issue_text(iss["key"], iss["fields"], field_names)
        if ts["history"]:
            hlines = ["", "Status history:"]
            for h in ts["history"]:
                hlines.append(f"  {h['t']}: {h['from']} -> {h['to']}")
            text += "\n" + "\n".join(hlines)
        docs.append({"id": f"jira_{iss['key']}", "text": text,
                     "metadata": meta})
    return docs


def sync_jira_versions(api, project_key, url_base):
    """Fetch the project's RELEASE / VERSION metadata from Jira
    (/rest/api/2/project/{key}/versions) and return Chroma documents — one per
    version. Each document carries the release name, description, start/release
    dates, and flags (released / archived / overdue). This is the authoritative
    list of releases for the project (separate from the per-issue fixVersions
    that are already embedded in issue documents)."""
    print(f"[JiraVersions] Fetching versions for project '{project_key}'...")
    try:
        versions = api.get(f"/rest/api/2/project/{project_key}/versions")
    except Exception as exc:
        print(f"[JiraVersions] Failed to fetch versions: {exc.__class__.__name__}: "
              f"{exc}")
        return []
    if not versions:
        print("[JiraVersions] No versions/releases found.")
        return []

    docs = []
    for v in versions:
        vid = v.get("id")
        name = v.get("name") or f"version-{vid}"
        released = bool(v.get("released"))
        archived = bool(v.get("archived"))
        overdue = bool(v.get("overdue"))
        desc = v.get("description") or ""
        text = (f"Jira Release/Version: {name}\n"
                f"ID: {vid}\n"
                f"Project: {project_key}\n"
                f"Description: {desc}\n"
                f"Start date: {v.get('startDate') or 'N/A'}\n"
                f"Release date: {v.get('releaseDate') or 'N/A'}\n"
                f"Released: {released}\n"
                f"Archived: {archived}\n"
                f"Overdue: {overdue}\n"
                f"URL: {url_base}/projects/{project_key}?selectedItem=com.atlassian.jira.jira-projects-plugin:release-page&status=unreleased")
        docs.append({
            "id": f"jira_version_{vid}",
            "text": text,
            "metadata": {
                "source": "jira",
                "project": project_key,
                "doc_type": "version",
                "version_id": vid,
                "name": name,
                "description": desc,
                "start_date": v.get("startDate"),
                "release_date": v.get("releaseDate"),
                "released": released,
                "archived": archived,
                "overdue": overdue,
                "url": url_base,
            },
        })
    print(f"[JiraVersions] Stored {len(docs)} versions/releases.")
    return docs


# ----------------------------------------------------------------------------
# Jira reports (GreenHopper / Agile API)
# ----------------------------------------------------------------------------
# Report definitions: (report_key, human label, path builder).
# Each is attempted; reports not available on the instance return nothing and
# are stored as N/A in the dashboard.
REPORT_DEFS = [
    ("control_chart", "Control Chart",
     lambda bid: f"/rest/greenhopper/1.0/rapid/charts/controlchart?rapidViewId={bid}"),
    ("epic_report", "Epic Report",
     lambda bid: f"/rest/greenhopper/1.0/rapid/charts/epicreport?rapidViewId={bid}"),
    ("velocity_chart", "Velocity Chart",
     lambda bid: f"/rest/greenhopper/1.0/rapid/charts/velocitychart?rapidViewId={bid}"),
    ("cfd_chart", "Cumulative Flow Diagram",
     lambda bid: f"/rest/greenhopper/1.0/rapid/charts/cumulativedflowchart?rapidViewId={bid}"),
    ("scope_change_chart", "Scope Change Chart",
     lambda bid: f"/rest/greenhopper/1.0/rapid/charts/scopechangechart?rapidViewId={bid}"),
    ("forecast_chart", "Forecast Chart",
     lambda bid: f"/rest/greenhopper/1.0/rapid/charts/forecastchart?rapidViewId={bid}"),
    ("sprint_report", "Sprint Report",
     lambda bid: f"/rest/greenhopper/1.0/rapid/charts/sprintreport?rapidViewId={bid}"),
]


def _get_boards(api, project_key=None):
    """List all boards visible to the user via the Agile API, optionally
    filtered by project key/name."""
    boards, start, total = [], 0, None
    params = {"startAt": start, "maxResults": 50}
    if project_key:
        params["projectKeyOrId"] = project_key
    while True:
        try:
            d = api.get("/rest/agile/1.0/board", params=params)
        except Exception as exc:
            print(f"    [skip] board list: {exc.__class__.__name__}")
            return boards
        boards.extend(d.get("values", []))
        total = d.get("total", len(boards))
        if start + len(d.get("values", [])) >= total:
            break
        start += len(d.get("values", []))
        params["startAt"] = start
    return boards


def _known_boards_from_data(project_key):
    """Read board ids from the local data file if the API board listing is
    blocked (403). Returns a list of {id, name, type} dicts."""
    # lib/ is one level below the project root; boards.json lives in
    # <project root>/work/jira/data/boards.json.
    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "work", "jira", "data", "boards.json"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                out = []
                for item in raw:
                    b = item.get("board", item)
                    out.append({
                        "id": b.get("id"),
                        "name": b.get("name", f"board-{b.get('id')}"),
                        "type": b.get("type", "unknown"),
                    })
                return out
            except Exception:
                continue
    return []


def sync_jira_reports(api, project_key, url_base, board_ids=None):
    """Fetch all reports available via the Jira Agile/GreenHopper API for every
    board, and return Chroma documents (one per report per board). Reports that
    are not available on the instance are skipped (rendered N/A downstream)."""
    print(f"[JiraReports] Listing boards for project '{project_key}'...")
    boards = _get_boards(api, project_key)
    print(f"[JiraReports] Boards via API: {len(boards)}")
    if not boards:
        # Fall back to the known board ids so reports are still attempted.
        print("[JiraReports] API board list blocked; using local boards.json.")
        boards = _known_boards_from_data(project_key)
    if board_ids:
        wanted = set(int(x) for x in board_ids)
        boards = [b for b in boards if b.get("id") in wanted] or boards
    print(f"[JiraReports] Boards to process: {len(boards)}")

    docs = []
    for b in boards:
        bid = b.get("id")
        bname = b.get("name", f"board-{bid}")
        btype = b.get("type", "unknown")
        print(f"  board {bid} | {bname} ({btype})")
        for key, label, path_builder in REPORT_DEFS:
            path = path_builder(bid)
            try:
                data = api.get(path)
            except Exception as exc:
                print(f"    [skip] {key}: not available ({exc.__class__.__name__})")
                continue
            text = json.dumps(data, indent=2, ensure_ascii=False)
            docs.append({
                "id": f"jira_report_{bid}_{key}",
                "text": text,
                "metadata": {
                    "source": "jira_report",
                    "project": project_key,
                    "report": key,
                    "report_label": label,
                    "board_id": bid,
                    "board_name": bname,
                    "board_type": btype,
                    "url": f"{url_base}/secure/RapidBoard.jspa?rapidView={bid}",
                },
            })
            print(f"    [OK] {key}: {len(text)} chars")
    return docs
