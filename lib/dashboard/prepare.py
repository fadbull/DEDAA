"""Dashboard data preparation: build_dashboard() computes every chart
series / fragment and returns the render context (split from
lib/dashboard_html.py; output is byte-identical to the monolith)."""
import os
from datetime import datetime
from html import escape
from ..dashboard_helpers import (esc, js_list, json_str, _tip,
    _dir_size_mb, _read_sync_marker, _fmt_ts, _rework_health_html)
from ..chromadb_utils import dir_size_mb, collection_folder
from .shell import _render_html_shell

# [P25] The event_analytics parameter was removed together with the
# Event-Driven Analytics section; cross_linkage stays (OLAP cube data).
def build_dashboard(jm, product_pages, db_path, reports_data=None,
                    artifacts=None, jprofile=None,
                    cross_linkage=None, collection_map=None, output_path=None,
                    metric_settings=None):
    import os
    reports_data = reports_data or {}
    artifacts = artifacts or {}
    jprofile = jprofile or {}
    cross_linkage = cross_linkage or {}
    # Directory containing the generated HTML (used to resolve asset paths).
    out_dir = os.path.dirname(os.path.abspath(output_path)) if output_path else os.getcwd()
    db_path = os.path.abspath(db_path)
    db_size_mb = dir_size_mb(db_path) if os.path.isdir(db_path) else 0.0

    # Per-tab data source folder + size (collection -> its HNSW vector folder)
    collection_map = collection_map or {}
    tab1_folder = collection_map.get("product_knowledge")
    tab2_folder = collection_map.get("product_jira")
    tab2_reports_folder = collection_map.get("product_jira_reports")
    tab1_folder = tab1_folder or collection_folder(db_path, "product_knowledge")
    tab2_folder = tab2_folder or collection_folder(db_path, "product_jira")
    tab2_reports_folder = (tab2_reports_folder
                           or collection_folder(db_path, "product_jira_reports"))
    tab1_size_mb = (dir_size_mb(os.path.join(db_path, tab1_folder))
                    if tab1_folder and os.path.isdir(os.path.join(db_path, tab1_folder))
                    else None)
    tab2_size_mb = (dir_size_mb(os.path.join(db_path, tab2_folder))
                    if tab2_folder and os.path.isdir(os.path.join(db_path, tab2_folder))
                    else None)
    tab2_reports_size_mb = (dir_size_mb(os.path.join(db_path, tab2_reports_folder))
                            if tab2_reports_folder and os.path.isdir(
                                os.path.join(db_path, tab2_reports_folder))
                            else None)
    # Tab 2 aggregates BOTH Jira collections (product_jira + product_jira_reports).
    if tab2_size_mb is not None and tab2_reports_size_mb is not None:
        tab2_total_size_mb = round(tab2_size_mb + tab2_reports_size_mb, 2)
    else:
        tab2_total_size_mb = tab2_size_mb or tab2_reports_size_mb
    tab1_folder_label = (tab1_folder[:8] + "…" if tab1_folder else "n/a")
    tab2_folder_label = (tab2_folder[:8] + "…" if tab2_folder else "n/a")

    # Tab 1 also includes the Confluence 'assets' folder (downloaded images /
    # schemas). Its size + last-modified time are shown because --save-images
    # may be off during a Confluence sync, so the assets are a separate layer.
    assets_dir = os.path.join(db_path, "assets")
    if os.path.isdir(assets_dir):
        tab1_assets_size_mb = dir_size_mb(assets_dir)
        tab1_assets_mtime = _fmt_ts(
            datetime.fromtimestamp(os.path.getmtime(assets_dir))
            .isoformat())
    else:
        tab1_assets_size_mb = None
        tab1_assets_mtime = "N/A"
    # Tab 1 total = product_knowledge vector folder + assets folder.
    if tab1_size_mb is not None and tab1_assets_size_mb is not None:
        tab1_total_size_mb = round(tab1_size_mb + tab1_assets_size_mb, 2)
    else:
        tab1_total_size_mb = tab1_size_mb or tab1_assets_size_mb

    # Last-sync timestamps per collection (recorded by sync_agent).
    tab1_ts = _fmt_ts(_read_sync_marker(db_path, "product_knowledge"))
    tab2_ts = _fmt_ts(_read_sync_marker(db_path, "product_jira"))
    tab2_reports_ts = _fmt_ts(_read_sync_marker(db_path, "product_jira_reports"))
    tab3_ts = tab2_ts
    # ---------- Series data for charts ----------
    weeks = sorted(set(list(jm["opened_by_week"].keys()) +
                       list(jm["resolved_by_week"].keys()) +
                       list(jm["bug_new_by_week"].keys()) +
                       list(jm["bug_resolved_by_week"].keys())))
    week_labels = js_list(weeks)
    opened = js_list([jm["opened_by_week"].get(w, 0) for w in weeks])
    resolved = js_list([jm["resolved_by_week"].get(w, 0) for w in weeks])
    bug_new = js_list([jm["bug_new_by_week"].get(w, 0) for w in weeks])
    bug_res = js_list([jm["bug_resolved_by_week"].get(w, 0) for w in weeks])
    velocity = js_list([jm["velocity_by_week"].get(w, 0) for w in weeks])

    # Biweekly (2-week) period series
    weeks2 = sorted(set(list(jm["opened_by_2wk"].keys()) +
                        list(jm["resolved_by_2wk"].keys()) +
                        list(jm["velocity_by_2wk"].keys()) +
                        list(jm["scope_change_2wk"].keys())))
    week2_labels = js_list(weeks2)
    opened2 = js_list([jm["opened_by_2wk"].get(w, 0) for w in weeks2])
    resolved2 = js_list([jm["resolved_by_2wk"].get(w, 0) for w in weeks2])
    velocity2 = js_list([jm["velocity_by_2wk"].get(w, 0) for w in weeks2])
    scope_change2 = js_list([jm["scope_change_2wk"].get(w, 0) for w in weeks2])
    avg_velocity2 = (round(sum(jm["velocity_by_2wk"].values()) /
                          max(len(jm["velocity_by_2wk"]), 1), 1)
                     if jm["velocity_by_2wk"] else None)

    # CFD series
    cfd_weeks = js_list([c["week"] for c in jm["cfd_series"]])
    cfd_backlog = js_list([c.get("Backlog", 0) for c in jm["cfd_series"]])
    cfd_ip = js_list([c.get("In Progress", 0) for c in jm["cfd_series"]])
    cfd_done = js_list([c.get("Closed", 0) for c in jm["cfd_series"]])

    # Type/status/priority bars
    type_rows = "".join(
        f"<tr><td>{esc(k)}</td><td>{v}</td></tr>"
        for k, v in jm["by_type"].most_common())
    status_rows = "".join(
        f"<tr><td>{esc(k)}</td><td>{v}</td></tr>"
        for k, v in jm["by_status"].most_common())
    prio_rows = "".join(
        f"<tr><td>{esc(k)}</td><td>{v}</td></tr>"
        for k, v in jm["by_priority"].most_common())

    # Backlog health
    ready_count = len(jm["backlog_ready"])
    # [P18] Ready items: Issue | Summary | Priority | Link — the tuple is
    # (key, summary, prio, url); the old render shifted the fields (the
    # 'Priority' column actually showed the summary and the link was built
    # from the priority string). Mirrors the Aging Issues table format.
    ready_rows = "".join(
        f"<tr><td>{esc(k)}</td><td>{esc(sm)}</td><td>{esc(p)}</td>"
        f"<td><a href='{esc(u)}' target='_blank'>link</a></td></tr>"
        for k, sm, p, u in jm["backlog_ready"][:15]
    ) or "<tr><td colspan='4'>None</td></tr>"

    # [P17] Aging rows: Issue | Summary | Priority | Status | Link | Age.
    # The aging tuple is (age, key, summary, status, prio, url) — the old
    # render mislabeled summary as Status and priority as Priority and built
    # the link from the priority field. Priority sits BEFORE Status (the
    # widget is full-width now, so it fits); Age stays LAST.
    aging_rows = "".join(
        f"<tr><td>{esc(k)}</td><td>{esc(sm)}</td><td>{esc(p)}</td>"
        f"<td>{esc(s)}</td>"
        f"<td><a href='{esc(u)}' target='_blank'>link</a></td><td>{d}d</td></tr>"
        for d, k, sm, s, p, u in jm["aging"][:15]
    ) or "<tr><td colspan='6'>None</td></tr>"

    # Open bugs by priority
    open_bug_prio = jm["open_bug_by_prio"]
    defect_age_rows = "".join(
        f"<tr><td>{esc(p)}</td><td>{len(v)}</td>"
        f"<td>{sum(v)//len(v) if v else 0} days</td></tr>"
        for p, v in jm["defect_age"].items())
    if not defect_age_rows:
        defect_age_rows = "<tr><td colspan='3'>N/A</td></tr>"

    # ---- [P16] Uniform Jira deep links (JQL) for the Quality widgets ------
    def _jira_base():
        """The Jira base URL, derived from any issue's stored
        '<base>/browse/<key>' URL (no extra plumbing needed)."""
        for tup in (jm.get("bugs") or jm.get("open_issues") or []):
            u = tup[4] if len(tup) > 4 else None
            if u and "/browse/" in u:
                return u.rsplit("/browse/", 1)[0]
        return None

    def _proj_key():
        for tup in (jm.get("bugs") or jm.get("open_issues") or []):
            k = tup[0] if tup else None
            if k and "-" in str(k):
                return str(k).split("-")[0]
        return None

    def _jql_link(jql, label):
        """Uniform '<label> → Jira' link opening the JQL in Jira."""
        base = _jira_base()
        if not base:
            return ""
        from urllib.parse import quote
        pk = _proj_key()
        jql_full = (f"project = {pk} AND " + jql) if pk else jql
        return ('<a class="text-xs text-blue-600 hover:underline" '
                'target="_blank" href="' + esc(base) + '/issues/?jql='
                + quote(jql_full, safe="") + '">' + esc(label)
                + ' → Jira</a>')

    # [P17b] Each link opens EXACTLY the issues the widget's metric counts —
    # and every JQL is built from the PROJECT'S ACTUAL data so Jira never
    # rejects it: issue-type names come from jm["by_type"] (exact spellings,
    # quoted), SAST/CWE labels come from the labels actually present.
    # `labels starts with` is INVALID JQL (labels only support = / in) — the
    # CWE link enumerates the actual cwe-* labels instead.
    def _actual_types():
        return {str(t).strip() for t in (jm.get("by_type") or {}) if t}

    def _bug_types():
        """Exact names of the bug-ish types present in the project."""
        want = {"bug", "sub-bug", "subbug", "defect", "sub defect",
                "bug_sub-bug", "sub_bug"}
        return sorted(t for t in _actual_types()
                      if t.lower().replace("_", "-") in
                      {"bug", "sub-bug", "defect"})

    def _quoted(names):
        return ", ".join('"' + str(n).replace('"', '') + '"' for n in names)

    def _sec_types():
        """Security-ish types actually present in the project."""
        want = {"security issue", "vulnerability", "security"}
        return sorted(t for t in _actual_types() if t.lower() in want)

    def _sast_labels():
        """SAST tool labels that actually occur in the data."""
        tools = {"SAST": "sast", "Gitleaks": "gitleaks",
                 "Checkmarx CxSAST": "checkmarx_cxsast", "Snyk SAST": "snyk"}
        return sorted({tools.get(t, t).lower()
                       for t in (jm.get("sast_by_tool") or {})} | {"cwe-"})

    def _cwe_labels():
        return sorted(str(k) for k in (jm.get("cwe_by_code") or {}))

    def _jql_link(jql, label):
        """Uniform '<label> → Jira' link; returns '' when the population
        is empty (the widget renders N/A anyway) or Jira base is unknown."""
        if not jql:
            return ""
        base = _jira_base()
        if not base:
            return ""
        from urllib.parse import quote
        pk = _proj_key()
        jql_full = (f"project = {pk} AND " + jql) if pk else jql
        return ('<a class="text-xs text-blue-600 hover:underline" '
                'target="_blank" href="' + esc(base) + '/issues/?jql='
                + quote(jql_full, safe="") + '">' + esc(label)
                + ' → Jira</a>')

    _bug_t = _bug_types()
    _bug_in = ("issuetype in (" + ", ".join('"' + t + '"' for t in _bug_t)
               + ")" if _bug_t else None)
    _sec_t = sorted(t for t in _actual_types()
                    if t.lower() in {"security issue", "vulnerability",
                                     "security"})
    _sast_l = sorted({l for l in _sast_labels()}) if jm.get("sast_by_tool") else []
    _cwe_l = sorted(str(k) for k in (jm.get("cwe_by_code") or {}))

    jql_links = {
        # open defects: bug-ish types present in the project, unresolved
        "open_bugs": _jql_link(
            _bug_in + " AND resolution is EMPTY", "Open defects")
        if _bug_in else "",
        # defect age: the same open-bug population feeds the age stats
        "defect_age": _jql_link(
            _bug_in + " AND resolution is EMPTY",
            "Open defects (age source)") if _bug_in else "",
        # production leakage: exactly the prod-labelled (leaked) defects
        "leakage": _jql_link(
            "labels = prod AND " + _bug_in, "Leaked (prod-tagged) defects")
        if _bug_in else "",
        # security posture: SAST labels actually present OR actual sec types
        "security": _jql_link(
            " OR ".join(filter(None, [
                ("labels in (" + ", ".join(_sast_labels()) + ")")
                if _sast_labels() else "",
                ('issuetype in (' + ", ".join('"' + t + '"' for t in _sec_t)
                 + ")") if _sec_t else ""])),
            "SAST/security issues") if (_sast_labels() or _sec_t) else "",
        # CWE findings: labels in (actual cwe-* labels) — never `starts with`
        "cwe": _jql_link(
            "labels in (" + ", ".join('"' + l + '"' for l in _cwe_l) + ")"
            if _cwe_l else "",
            "CWE findings") if _cwe_l else "",
    }

    # Product content
    def page_text(title):
        pg = product_pages.get(title)
        return (pg["text"] if pg else ""), (pg["url"] if pg else "")

    # Render downloaded image/attachment artifacts for a page (architecture /
    # workflow schemas). Images are stored under db_path/assets/...; the HTML
    # lives at the workspace root, so resolve the relative path accordingly.
    def page_images_html(title):
        pg = product_pages.get(title)
        if not pg or not pg.get("images"):
            return ""
        parts = []
        for img in pg["images"]:
            rel = img.get("file", "")
            alt = img.get("alt") or os.path.basename(rel)
            src_url = img.get("url", "")
            # Relative path from the dashboard HTML location to the image file.
            img_rel = os.path.relpath(os.path.join(db_path, rel),
                                      start=out_dir)
            link = ('<a class="text-blue-600 text-xs" href="' + esc(src_url) +
                    '" target="_blank">source</a>')
            parts.append(
                "<figure class='mt-3'>"
                f"<img src='{esc(img_rel)}' alt='{esc(alt)}' "
                "class='rounded border border-gray-200 max-h-72' "
                "onerror=\"this.style.display='none'\">"
                f"<figcaption class='text-xs text-gray-500 mt-1'>"
                f"{esc(alt)} · {link}</figcaption>"
                "</figure>"
            )
        return "".join(parts)

    vtext, vurl = page_text("Product vision and strategy")
    ctext, ctext_url = page_text("Product capabilities register")
    stext, stext_url = page_text("Stakeholder Management")
    metext, metext_url = page_text("Business / Product metrics register")

    # Simple extraction for product summary
    def section_between(text, start, end):
        i = text.find(start)
        if i < 0:
            return ""
        i += len(start)
        j = text.find(end, i)
        return text[i:j if j > 0 else i + 600].strip()[:600]

    value_prop = section_between(vtext, "Value proposition statement:", "Project code:")
    problem = section_between(vtext, "Problem statement", "Motivational vision statement")
    vision = section_between(vtext, "Motivational vision statement", "Sponsor(s)")

    # Capabilities table
    cap_rows = ""
    cap_lines = ctext.splitlines()
    prev_name = None
    for ln in cap_lines:
        ln = ln.strip()
        if ln and not ln.startswith(("#", "Capability", "Description")) and \
           len(ln) > 3 and not ln.startswith(("Target", "Integration", "Link", "SMEs")):
            if len(ln) < 60 and prev_name is None:
                prev_name = ln
            elif prev_name is not None:
                cap_rows += (f"<tr><td><strong>{esc(prev_name)}</strong></td>"
                             f"<td>{esc(ln[:200])}</td></tr>")
                prev_name = None
    if not cap_rows:
        cap_rows = "<tr><td colspan='2'>N/A</td></tr>"

    # Health status
    total = jm["total"]
    done = jm["by_group"].get("Closed", 0)
    ip = jm["by_group"].get("In Progress", 0)
    bl = jm["by_group"].get("Backlog", 0)
    pct = (done / total * 100) if total else 0
    if pct >= 60:
        health = "HEALTHY"; hcolor = "#10b981"; hem = "🟢"
    elif pct >= 35:
        health = "AT RISK"; hcolor = "#f59e0b"; hem = "🟡"
    else:
        health = "CRITICAL"; hcolor = "#ef4444"; hem = "🔴"

    avg_cycle = jm["avg_cycle"]
    avg_lead = jm["avg_lead"]
    kt_delivery_url = page_text("KT: Delivery")[1]

    # Precomputed source links (avoids triple-quote termination in the HTML)
    link_vision = '<a class="text-blue-600" href="' + esc(vurl) + '" target="_blank">Product vision and strategy</a>'
    link_kt = '<a class="text-blue-600" href="' + esc(kt_delivery_url) + '" target="_blank">KT: Delivery</a>'
    link_caps = '<a class="text-blue-600" href="' + esc(ctext_url) + '" target="_blank">Product capabilities register</a>'
    link_stake = '<a class="text-blue-600" href="' + esc(stext_url) + '" target="_blank">Stakeholder Management</a>'
    link_metrics = '<a class="text-blue-600" href="' + esc(metext_url) + '" target="_blank">Business / Product metrics register</a>'

    # ------------------------------------------------------------------
    # Project Jira Reports (from product_jira_reports collection)
    # ------------------------------------------------------------------
    def report_boards(kind):
        return reports_data.get(kind, [])

    # Control Chart — available; show board workflow columns + per-board stats.
    cc_boards = report_boards("control_chart")
    control_chart_rows = ""
    if cc_boards:
        for rb in cc_boards:
            payload = rb.get("payload", {})
            columns = [c.get("name", "") for c in payload.get("columns", [])]
            issues = payload.get("issues", {})
            n_issues = len(issues) if isinstance(issues, dict) else 0
            rates = payload.get("workRateData", {}).get("rates", [])
            control_chart_rows += (
                "<tr>"
                f"<td>{esc(rb.get('board_name'))}</td>"
                f"<td>{esc(', '.join(columns))}</td>"
                f"<td>{n_issues}</td>"
                f"<td>{len(rates)}</td>"
                f"<td><a class='text-blue-600' href='{esc(rb.get('url'))}' "
                f"target='_blank'>board</a></td>"
                "</tr>"
            )
    control_chart_html = (
        "<table class='w-full text-sm'><thead><tr class='text-left border-b'>"
        "<th class='py-2'>Board</th><th>Workflow columns</th><th>Issues</th>"
        "<th>Work-rate periods</th><th>Source</th></tr></thead><tbody>"
        + (control_chart_rows or "<tr><td colspan='5'>N/A</td></tr>")
        + "</tbody></table>"
    )

    # Other reports — only render when actually stored; else N/A.
    def report_widget(kind, label):
        boards = report_boards(kind)
        if not boards:
            return ("<div class='na-box' title='Report not available via the "
                    "Jira API for this project.'>N/A</div>")
        rows = "".join(
            f"<tr><td>{esc(rb.get('board_name'))}</td>"
            f"<td><a class='text-blue-600' href='{esc(rb.get('url'))}' "
            f"target='_blank'>open</a></td></tr>"
            for rb in boards
        )
        return ("<table class='w-full text-sm'><thead><tr class='text-left "
                "border-b'><th class='py-2'>Board</th><th>Source</th></tr>"
                f"</thead><tbody>{rows}</tbody></table>")

    epic_report_html = report_widget("epic_report", "Epic Report")
    velocity_chart_html = report_widget("velocity_chart", "Velocity Chart")
    cfd_chart_html = report_widget("cfd_chart", "Cumulative Flow Diagram")
    scope_change_html = report_widget("scope_change_chart", "Scope Change Chart")
    forecast_chart_html = report_widget("forecast_chart", "Forecast Chart")
    sprint_report_html = report_widget("sprint_report", "Sprint Report")

    # ------------------------------------------------------------------
    # Found Artifacts (autonomous extraction from Confluence pages)
    # ------------------------------------------------------------------
    # Category display order and CSS accent.
    artifact_order = ["metrics", "success_criteria", "tools", "capabilities",
                      "stakeholders", "links", "team"]
    artifact_accent = {
        "metrics": "#2563eb", "success_criteria": "#10b981", "tools": "#f59e0b",
        "capabilities": "#8b5cf6", "stakeholders": "#ef4444", "links": "#0ea5e9",
        "team": "#14b8a6",
    }
    artifact_sections = ""
    for cat in artifact_order:
        entries = artifacts.get(cat, [])
        if not entries:
            continue
        label = entries[0].get("label", cat.replace("_", " ").title())
        accent = artifact_accent.get(cat, "#64748b")
        rows = ""
        for e in entries:
            src = ('<a class="text-blue-600" href="' + esc(e.get("url", "")) +
                   '" target="_blank">' + esc(e.get("title", "source")) +
                   '</a>')
            items = "".join(
                "<li>" + esc(it) + "</li>" for it in e.get("items", []))
            rows += (
                "<tr>"
                f"<td class='align-top py-2'><span style='color:{accent}'>●</span> "
                f"{src}</td>"
                f"<td class='align-top py-2'><ul class='list-disc pl-4 space-y-1'>"
                f"{items}</ul></td>"
                "</tr>"
            )
        artifact_sections += (
            f"<div class='widget'><h3 class='font-medium mb-2'>"
            f"{esc(label)}</h3>"
            "<table class='w-full text-sm'><thead><tr class='text-left "
            "border-b'><th class='py-2'>Source</th><th>Found</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div>"
        )
    if not artifact_sections:
        artifact_sections = (
            "<div class='widget'><h3 class='font-medium mb-2'>Found "
            "Artifacts</h3><div class='na-box'>N/A (no Confluence data)</div>"
            "</div>")

    # ==================================================================
    # TAB 3 — Jira Data Profile (Data & Workflow Architecture)
    # ==================================================================
    jp_types = jprofile.get("types", [])
    jp_type_counts = jprofile.get("type_counts", {})
    jp_field_density = jprofile.get("field_density", {})
    jp_data_types = jprofile.get("data_type_map", {})
    jp_sm = jprofile.get("state_machines", {})
    jp_alignment = jprofile.get("alignment_anomalies", [])
    jp_open_res = jprofile.get("open_with_resolution", [])

    # --- 1a) Field Density matrix: rows = fields, cols = issue types ---
    fd_fields = list(jp_field_density.keys())
    fd_head = ("<tr class='text-left border-b'><th class='py-2'>Field</th>"
               + "".join(f"<th class='py-2 px-2'>{esc(t)}</th>"
                         for t in jp_types) + "</tr>")
    fd_rows = ""
    for f in fd_fields:
        cells = "".join(
            f"<td class='px-2 py-1 text-center'>{jp_field_density[f].get(t, 0)}%</td>"
            for t in jp_types)
        fd_rows += f"<tr><td class='py-1 font-medium'>{esc(f)}</td>{cells}</tr>"
    field_density_html = (
        "<div class='overflow-x-auto'><table class='w-full text-sm'>"
        f"<thead>{fd_head}</thead><tbody>{fd_rows}</tbody></table></div>"
        if jp_types else "<div class='na-box'>N/A</div>")

    # --- 1b) Data Type Mapping ---
    dt_rows = "".join(
        f"<tr><td class='py-1 font-medium'>{esc(f)}</td>"
        f"<td>{esc(jp_data_types.get(f, 'Text'))}</td></tr>"
        for f in fd_fields)
    data_type_html = (
        "<table class='w-full text-sm'><thead><tr class='text-left border-b'>"
        "<th class='py-2'>Field</th><th>Data Type</th></tr></thead>"
        f"<tbody>{dt_rows}</tbody></table>")

    # --- 2a) State machines (Mermaid flowcharts per issue type) ---
    def mermaid_safe(s):
        return str(s).replace('"', "'").replace("&", "and").replace("(", "").replace(")", "")
    sm_widgets = ""
    for typ in jp_types:
        sm = jp_sm.get(typ, {})
        trans = sm.get("transitions", [])
        if not trans:
            sm_widgets += (
                f"<div class='widget'><h3 class='font-medium mb-2'>{esc(typ)} "
                f"({jp_type_counts.get(typ, 0)})</h3>"
                "<div class='na-box'>N/A (no status history)</div></div>")
            continue
        lines = ["graph TD"]
        node_id = {}
        node_counter = [0]
        def _nid(label):
            lab = mermaid_safe(label)
            if lab not in node_id:
                node_id[lab] = "N" + str(node_counter[0])
                node_counter[0] += 1
            return node_id[lab]
        for t in trans:
            fr = mermaid_safe(t["from"]); to = mermaid_safe(t["to"])
            lines.append(f'    {_nid(fr)}["{fr}"] -->|{t["count"]}| {_nid(to)}["{to}"]')
        mermaid_src = "\n".join(lines)
        sm_widgets += (
            f"<div class='widget'><h3 class='font-medium mb-2'>{esc(typ)} "
            f"({jp_type_counts.get(typ, 0)})</h3>"
            f"<div class='mermaid'>{mermaid_src}</div>"
            f"<p class='text-xs text-gray-500 mt-1'>{len(trans)} observed "
            "transitions</p></div>")

    # --- 2b) Resolution & Status alignment ---
    align_rows = "".join(
        f"<tr><td>{esc(a.get('key'))}</td><td>{esc(a.get('status'))}</td>"
        f"<td><a class='text-blue-600' href='{esc(a.get('url'))}' "
        f"target='_blank'>link</a></td></tr>"
        for a in jp_alignment) or "<tr><td colspan='3'>None</td></tr>"
    open_res_rows = "".join(
        f"<tr><td>{esc(a.get('key'))}</td><td>{esc(a.get('status'))}</td>"
        f"<td>{esc(a.get('resolution'))}</td>"
        f"<td><a class='text-blue-600' href='{esc(a.get('url'))}' "
        f"target='_blank'>link</a></td></tr>"
        for a in jp_open_res) or "<tr><td colspan='4'>None</td></tr>"

    # ==================================================================
    # NEW WIDGET DATA (OLAP / analytics additions to Tab 3)
    # ==================================================================
    # 4a) Field Dependencies (co-fill correlation matrix)
    jp_field_corr = jprofile.get("field_corr", {})
    jp_fill_trend = jprofile.get("field_fill_trend", {})
    corr_fields = ["components", "labels", "resolution", "duedate",
                   "in_progress_date", "done_date", "priority"]
    corr_head = ("<tr class='text-left border-b'><th class='py-2'>Field</th>"
                 + "".join(f"<th class='py-2 px-2'>{esc(c)}</th>"
                           for c in corr_fields) + "</tr>")
    corr_rows = ""
    for i, fa in enumerate(corr_fields):
        cells = ""
        for j, fb in enumerate(corr_fields):
            if i == j:
                cells += "<td class='px-2 py-1 text-center text-gray-300'>-</td>"
            elif i < j:
                val = jp_field_corr.get(f"{fa}|{fb}")
                cells += (f"<td class='px-2 py-1 text-center'>{val if val is not None else 'N/A'}%</td>"
                          if val is not None else "<td class='px-2 py-1 text-center'>N/A</td>")
            else:
                val = jp_field_corr.get(f"{fb}|{fa}")
                cells += (f"<td class='px-2 py-1 text-center'>{val if val is not None else 'N/A'}%</td>"
                          if val is not None else "<td class='px-2 py-1 text-center'>N/A</td>")
        corr_rows += f"<tr><td class='py-1 font-medium'>{esc(fa)}</td>{cells}</tr>"
    field_corr_html = (
        "<div class='overflow-x-auto'><table class='w-full text-sm'>"
        f"<thead>{corr_head}</thead><tbody>{corr_rows}</tbody></table></div>"
        if jp_field_corr else "<div class='na-box'>N/A</div>")

    # 4b) Field fill-rate trend over biweekly periods (line charts)
    trend_fields = ["components", "labels", "resolution", "duedate",
                    "in_progress_date"]
    trend_series_html = ""
    trend_js = ""
    for field in trend_fields:
        data = jp_fill_trend.get(field, {})
        if not data:
            continue
        labels = sorted(data.keys())
        values = [data[k] for k in labels]
        cid = "trend_" + field
        trend_series_html += (
            f"<div class='widget'><h3 class='font-medium mb-2'>Field fill-rate · "
            f"{esc(field)}</h3><div class='h-40'><canvas id='{cid}'></canvas></div></div>")
        trend_js += (
            f"new Chart(document.getElementById('{cid}'), {{ type:'line', data:{{"
            f"labels:{js_list(labels)}, datasets:[{{label:'% filled', "
            f"data:{js_list(values)}, borderColor:'#8b5cf6', fill:false, tension:0.2}}]"
            f"}}, options:{{responsive:true, maintainAspectRatio:false, "
            f"plugins:{{legend:{{display:false}}}}, scales:{{y:{{max:100, "
            f"title:{{display:true, text:'% filled'}}}}}}}} }});\n")

    # 4c) Transition Frequency heatmap matrix
    jp_trans_statuses = jprofile.get("trans_statuses", [])
    jp_trans_matrix = jprofile.get("trans_matrix", [])
    jp_pingpong = jprofile.get("pingpong", [])
    hm_head = ("<tr class='text-left border-b'><th class='py-2'>From \\ To</th>"
               + "".join(f"<th class='py-2 px-2 text-xs'>{esc(s)}</th>"
                         for s in jp_trans_statuses) + "</tr>")
    hm_rows = ""
    max_c = 1
    for row in jp_trans_matrix:
        for v in row:
            if v > max_c:
                max_c = v
    for i, s in enumerate(jp_trans_statuses):
        cells = ""
        for j in range(len(jp_trans_statuses)):
            v = jp_trans_matrix[i][j] if i < len(jp_trans_matrix) else 0
            if i == j:
                cells += "<td class='px-1 py-1 text-center text-gray-300'>-</td>"
            elif v:
                # color scale: light blue -> deep blue
                alpha = 0.15 + 0.85 * (v / max_c)
                cells += (f"<td class='px-1 py-1 text-center text-xs' "
                          f"style='background:rgba(37,99,235,{alpha:.2f}); "
                          f"color:rgba(15,23,42,{1 if alpha>0.5 else 0.75})' "
                          f"title='{esc(s)} -> {esc(jp_trans_statuses[j])}: {v}'>{v}</td>")
            else:
                cells += "<td class='px-1 py-1 text-center text-gray-300'>·</td>"
        hm_rows += f"<tr><td class='py-1 font-medium text-xs'>{esc(s)}</td>{cells}</tr>"
    heatmap_html = (
        "<div class='overflow-x-auto'><table class='w-full text-xs'>"
        f"<thead>{hm_head}</thead><tbody>{hm_rows}</tbody></table></div>"
        if jp_trans_statuses else "<div class='na-box'>N/A</div>")

    pingpong_rows = "".join(
        f"<tr><td class='py-1'>{esc(p['a'])} ⇄ {esc(p['b'])}</td>"
        f"<td class='py-1'>{p['ab']}</td><td class='py-1'>{p['ba']}</td>"
        f"<td class='py-1 font-medium'>{p['total']}</td></tr>"
        for p in jp_pingpong) or "<tr><td colspan='4'>N/A</td></tr>"

    # 4d) Time-in-Status widget (horizontal bars per issue type)
    jp_tis_series = jprofile.get("time_in_status_series", [])
    tis_widgets = ""
    tis_js = ""
    for series in jp_tis_series:
        typ = series["type"]
        items = series["items"]
        if not items:
            continue
        cid = "tis_" + typ.replace(" ", "_").replace("/", "_")
        labels = [it["status"] for it in items][:12]
        values = [it["median"] for it in items][:12]
        cols = ["#ef4444" if it["stagnant"] else "#2563eb" for it in items][:12]
        stagnant_note = (" · <span class='text-red-600'>stagnant >60d</span>"
                         if any(it["stagnant"] for it in items) else "")
        tis_widgets += (
            f"<div class='widget'><h3 class='font-medium mb-2'>Median time-in-status · "
            f"{esc(typ)}</h3>"
            f"<p class='text-xs text-gray-500 mb-2'>Median days per status. "
            f"Red = stagnant (>60 days).{stagnant_note}</p>"
            f"<div class='h-56'><canvas id='{cid}'></canvas></div></div>")
        tis_js += (
            f"new Chart(document.getElementById('{cid}'), {{ type:'bar', data:{{"
            f"labels:{js_list(labels)}, datasets:[{{label:'median days', "
            f"data:{js_list(values)}, backgroundColor:{js_list(cols)} }}]"
            f"}}, options:{{indexAxis:'y', responsive:true, "
            f"maintainAspectRatio:false, plugins:{{legend:{{display:false}}}}, "
            f"scales:{{x:{{title:{{display:true, text:'median days'}}}}}}}} }});\n")
    if not tis_widgets:
        tis_widgets = "<div class='na-box'>N/A — no status intervals with known boundaries</div>"

    # 4e) OLAP Slice & Dice constructor data
    import json as _json
    jp_olap_dims = jprofile.get("olap_dims", [])
    jp_olap_rows = jprofile.get("olap_rows", [])
    def _olap_options(dim):
        seen = []
        for r in jp_olap_rows:
            values = r.get("components", []) if dim == "component" else [r.get(dim, "")]
            for v in values:
                if v and v not in seen:
                    seen.append(v)
        seen.sort()
        return "".join(f"<option value='{esc(v)}'>{esc(v)}</option>"
                       for v in seen)
    olap_type_opts = _olap_options("type")
    olap_assignee_opts = _olap_options("assignee")
    olap_priority_opts = _olap_options("priority")
    olap_status_opts = _olap_options("status")
    olap_component_opts = _olap_options("component")
    # Proper JS array literal (NOT a quoted string) for the client-side cube.
    olap_rows_json = _json.dumps(jp_olap_rows).replace("<", "\\u003c")

    # 4f) Issue-Links OLAP Slice & Dice constructor data (cube over issuelinks)
    jp_olap_link_dims = jprofile.get("olap_link_dims", [])
    jp_olap_link_rows = jprofile.get("olap_link_rows", [])
    def _olap_link_options(dim):
        seen = []
        for r in jp_olap_link_rows:
            v = r.get(dim, "")
            if v and v not in seen:
                seen.append(v)
        seen.sort()
        return "".join(f"<option value='{esc(v)}'>{esc(v)}</option>"
                       for v in seen)
    olap_link_type_opts = _olap_link_options("link_type")
    olap_link_dir_opts = _olap_link_options("direction")
    olap_link_stype_opts = _olap_link_options("source_type")
    olap_link_ttype_opts = _olap_link_options("target_type")
    olap_link_sstatus_opts = _olap_link_options("source_status")
    olap_link_tstatus_opts = _olap_link_options("target_status")
    olap_link_rows_json = _json.dumps(jp_olap_link_rows).replace("<", "\\u003c")

    # ==================================================================
    # SDLC PROCESS MATRIX — Issue Type x Status (heatmap) + VSM Gaps
    # ==================================================================
    jp_sdlc_matrix = jprofile.get("sdlc_matrix", {})
    jp_sdlc_statuses = jprofile.get("sdlc_statuses", [])
    jp_sdlc_types = jprofile.get("sdlc_types", [])
    jp_sdlc_counts = jprofile.get("sdlc_counts", {})
    jp_sdlc_totals = jprofile.get("sdlc_totals", {})
    jp_vsm = jprofile.get("vsm_findings", [])
    jp_sec = jprofile.get("security_in_progress", {})
    jp_subbug_ratio = jprofile.get("subbug_story_ratio")

    # --- Heatmap: rows = issue types, cols = statuses, cell = % ---
    sdlc_head = ("<tr class='text-left border-b'><th class='py-2'>Issue Type</th><th>Total</th>"
                 + "".join(f"<th class='py-2 px-2 text-xs'>{esc(s)}</th>"
                           for s in jp_sdlc_statuses) + "</tr>")
    sdlc_body = ""
    sdlc_max = 1
    for t in jp_sdlc_types:
        row = jp_sdlc_matrix.get(t, {})
        for v in row.values():
            if v > sdlc_max:
                sdlc_max = v
    for t in jp_sdlc_types:
        row = jp_sdlc_matrix.get(t, {})
        cells = ""
        for s in jp_sdlc_statuses:
            v = row.get(s, 0)
            count = jp_sdlc_counts.get(t, {}).get(s, 0)
            if count:
                alpha = 0.15 + 0.85 * (v / sdlc_max)
                title = escape(f"{t} · {s}: {count} / {jp_sdlc_totals.get(t, 0)} ({v}%)", quote=True)
                cells += (f"<td class='px-1 py-1 text-center text-xs' "
                          f"style='background:rgba(16,185,129,{alpha:.2f}); "
                          f"color:rgba(6,78,59,{1 if alpha>0.45 else 0.8})' "
                          f"title='{title}'>{v}%</td>")
            else:
                cells += "<td class='px-1 py-1 text-center text-gray-300'>·</td>"
        sdlc_body += (f"<tr><td class='py-1 font-medium text-xs'>{esc(t)}</td>"
                      f"<td>{jp_sdlc_totals.get(t, 0)}</td>{cells}</tr>")
    sdlc_heatmap_html = (
        "<div class='overflow-x-auto'><table class='w-full text-xs'>"
        f"<thead>{sdlc_head}</thead><tbody>{sdlc_body}</tbody></table></div>"
        if jp_sdlc_matrix else "<div class='na-box'>N/A</div>")

    # --- Value Stream Mapping Gaps ---
    vsm_cards = ""
    if jp_vsm:
        for f in jp_vsm:
            color, icon = {
                "warning": ("#b45309", "⚠️"),
                "success": ("#16a34a", "🟢"),
                "info": ("#6b7280", ""),
            }[f["level"]]
            vsm_cards += (
                f"<div class='widget border-l-4' style='border-left-color:{color}'>"
                f"<h3 class='font-medium mb-1'>{icon} {esc(f['kind'])}</h3>"
                f"<p class='text-sm text-gray-700'>{esc(f['message'])}</p>"
                f"<p class='text-xs text-gray-400 mt-1'>metric value: "
                f"{esc(f['value'])}</p></div>")
    if jp_subbug_ratio is None:
        vsm_cards += "<p class='text-xs text-gray-500'>Sub-Bug / Story ratio: N/A — no Story issues.</p>"
    sec_total = jp_sec.get("total", 0)
    sec_rows = "".join(
        f"<li>{esc(status)}: {count} / {sec_total} ({count / sec_total * 100:.1f}%)</li>"
        for status, count in sorted(jp_sec.get("statuses", {}).items())
    ) or "<li>N/A — no Security issues</li>"
    vsm_cards += ("<p class='text-xs mt-2'>Security issue statuses at the Jira snapshot:</p>"
                  "<ul class='text-xs'>" + sec_rows + "</ul>")

    # ==================================================================
    # SDLC PROCESS MATRIX (Tab 2, section m-sdlc) — kept (NOT section 7).
    # ==================================================================
    sdlc_section_html = """
      <section id="m-sdlc" class="scroll-mt-24">
        <h2 class="text-lg font-semibold mb-3">SDLC Process Matrix — Issue Type vs Status Dependencies</h2>
        <p class="text-xs text-gray-500 mb-3">Distribution of the issue types and statuses in the Jira snapshot. Statuses are shown separately; missing values are Unknown (missing).</p>
        <div class="widget mb-4"><h3 class="font-medium mb-2">SDLC Process Matrix — Issue Type vs Status Dependencies""" + _tip("For each issue type and Jira status, the number of issues in that status divided by all issues of the same type, including missing statuses. Total is the issue count for the row. Jira status names are not grouped; Unknown (missing) indicates missing values. Percentages may not add to exactly 100% due to rounding. These are snapshot distributions, not evidence that work is stuck.") + """</h3>""" + sdlc_heatmap_html + """</div>
        <div class="widget">
          <h3 class="font-medium mb-2">Value Stream Mapping Gaps (under work)""" + _tip("Sub-Bug / Story is the count of all Sub-Bugs divided by all Stories. The sign is yellow at or below 0.2, green above 0.2, and absent when there are no Stories; the comparison uses the unrounded ratio. This illustrative threshold is not evidence of quality or causation. Security statuses are a snapshot distribution, not evidence of neglect. Backlog observations use only issues with known continuous Open/New time at a trustworthy snapshot; unknown cases are excluded.") + """</h3>
          <div class="space-y-3">""" + vsm_cards + """</div>
        </div>
      </section>
    """

    tab3_html = """
<!-- ================= TAB 3 ================= -->
<div id="tab3" class="tab-panel">
  <div class="widget mb-4 text-xs text-gray-500 font-mono">
    <strong class="text-gray-700">Data source (Tab 3):</strong> Chroma DB: <span class="text-gray-600">""" + esc(db_path) + """</span> · Collection: <span class="text-gray-600">product_jira</span> · Folder: <span class="text-gray-600">""" + esc(tab2_folder_label) + """</span> · Size: <span class="text-gray-600">""" + (f"{tab2_size_mb} MB" if tab2_size_mb is not None else "n/a") + """</span> · Last update: <span class="text-gray-600">""" + tab3_ts + """</span>
  </div>
  <div class="flex gap-6">
    <nav class="w-56 shrink-0 hidden md:block">
      <div class="sticky top-20 space-y-1 text-sm">
        <a href="#d-schema" class="sidebar-link block px-3 py-2 rounded-lg">1. Schema & Field Usage</a>
        <a href="#d-workflows" class="sidebar-link block px-3 py-2 rounded-lg">2. Core Workflows</a>
        <a href="#d-dependencies" class="sidebar-link block px-3 py-2 rounded-lg">3. Field Dependencies & Trends</a>
        <a href="#d-transitions" class="sidebar-link block px-3 py-2 rounded-lg">4. Transition Frequency</a>
        <a href="#d-timestatus" class="sidebar-link block px-3 py-2 rounded-lg">5. Time-in-Status</a>
        <a href="#d-olap" class="sidebar-link block px-3 py-2 rounded-lg">6. OLAP Slice & Dice</a>
      </div>
    </nav>
    <div class="flex-1 space-y-8">

      <section id="d-schema" class="scroll-mt-24">
        <h2 class="text-lg font-semibold mb-3">1. Schema & Field Usage Matrix</h2>
        <div class="widget mb-4"><h3 class="font-medium mb-2">Field Density (% populated by Issue Type)""" + _tip("For each Issue Type, what share of its issues actually populate each Jira field. Computed as: (issues where the field is non-empty) ÷ (total issues of that type) × 100. A low % for a required field signals poor data discipline.") + """</h3>""" + field_density_html + """</div>
        <div class="widget"><h3 class="font-medium mb-2">Data Type Mapping""" + _tip("Shows how each Jira field maps to its underlying data type (text, number, date, user, list, etc.). Useful for understanding which fields can be aggregated, charted, or sliced in the OLAP cube.") + """</h3>""" + data_type_html + """</div>
      </section>

      <section id="d-workflows" class="scroll-mt-24">
        <h2 class="text-lg font-semibold mb-3">2. Core Operational Workflows (Deterministic Flows)</h2>
        <p class="text-xs text-gray-500 mb-3">Issue Type state machines built from the observed status-transition history (changelog). Edge labels show transition counts.</p>
        <div class="grid md:grid-cols-2 gap-4">
          """ + sm_widgets + """
        </div>
        <div class="widget mt-4"><h3 class="font-medium mb-2">Resolution & Status Alignment""" + _tip("Detects data-integrity anomalies in the workflow: (1) issues that are Closed/Done but have no Resolution date set, and (2) issues still Open that nonetheless carry a Resolution value. Both are signs of sloppy or incomplete Jira hygiene that distorts downstream analytics.") + """</h3>
          <p class="text-xs text-gray-500 mb-2">Closed/Done issues missing a Resolution date (anomaly):</p>
          <table class="w-full text-sm"><thead><tr class="text-left border-b"><th class="py-2">Issue</th><th>Status</th><th>Link</th></tr></thead><tbody>""" + align_rows + """</tbody></table>
          <p class="text-xs text-gray-500 mt-3 mb-2">Open issues that carry a Resolution value (anomaly):</p>
          <table class="w-full text-sm"><thead><tr class="text-left border-b"><th class="py-2">Issue</th><th>Status</th><th>Resolution</th><th>Link</th></tr></thead><tbody>""" + open_res_rows + """</tbody></table>
        </div>
      </section>

      <section id="d-dependencies" class="scroll-mt-24">
        <h2 class="text-lg font-semibold mb-3">3. Field Dependencies & Trends</h2>
        <p class="text-xs text-gray-500 mb-3">Co-fill matrix shows what % of issues populate both fields (field correlation). Trend charts show how often each optional field is left empty over biweekly periods — a drop signals fields being neglected.</p>
        <div class="widget mb-4"><h3 class="font-medium mb-2">Field Co-fill Correlation Matrix (% both populated)""" + _tip("For every pair of fields, the % of all issues that populate BOTH fields simultaneously: (issues where both fields are non-empty) ÷ (all issues) × 100.") + """</h3>""" + field_corr_html + """</div>
        <div class="grid md:grid-cols-2 gap-4">""" + trend_series_html + """</div>
      </section>

      <section id="d-transitions" class="scroll-mt-24">
        <h2 class="text-lg font-semibold mb-3">4. Transition Frequency & Intensity</h2>
        <p class="text-xs text-gray-500 mb-3">Heatmap of status-to-status transition counts from the changelog. The "ping-pong" table flags back-and-forth jumps (rework / churn) such as Closed ⇄ Reopened.</p>
        <div class="widget mb-4"><h3 class="font-medium mb-2">Transition Frequency Heatmap (From → To)""" + _tip("Counts, for every ordered status pair (From → To), how many times the team moved work that way, derived from the issue changelog. High-frequency cells reveal the dominant workflow path; unexpected jumps (e.g. To Do → Done) expose bypassed process steps.") + """</h3>""" + heatmap_html + """</div>
        <div class="widget"><h3 class="font-medium mb-2">Ping-Pong (rework) Status Jumps""" + _tip("Counts consecutive A→B and B→A transitions on the same issue. Each detected return contributes one transition to each direction. This is a potential signal of rework, not proof of its cause.") + """</h3>
          <table class="w-full text-sm"><thead><tr class="text-left border-b"><th class="py-2">Pair</th><th>A→B</th><th>B→A</th><th>Total</th></tr></thead><tbody>""" + pingpong_rows + """</tbody></table></div>
      </section>

      <section id="d-timestatus" class="scroll-mt-24">
        <h2 class="text-lg font-semibold mb-3">5. Time-in-Status (Median Days per Status)</h2>
        <p class="text-xs text-gray-500 mb-3">Median of observed intervals with known start and end, per issue type. Incomplete histories and unknown snapshot times exclude intervals; results may not represent every issue. Red bars indicate medians over 60 days.</p>
        <div class="grid md:grid-cols-2 gap-4">""" + tis_widgets + """</div>
      </section>

      <section id="d-olap" class="scroll-mt-24">
        <h2 class="text-lg font-semibold mb-3">6. Interactive OLAP Slice & Dice Constructor""" + _tip("Interactive multidimensional analysis: pick any combination of dimensions (Issue Type, Assignee, Priority, Status, Component) and the table recomputes, for each slice, the task count and the average lifecycle in days (Resolution − Created). Use it to drill into where time and effort actually go.") + """</h2>
        <p class="text-xs text-gray-500 mb-3">Slice by Issue Type, Assignee, Priority, Status and Component. An issue may appear in multiple component slices; the total counts unique issues. Lifecycle is Resolution date − Created; missing resolution dates are excluded from the average.</p>
        <div class="widget">
          <div class="flex flex-wrap gap-3 mb-3">
            <label class="text-sm">Issue Type
              <select id="olapType" class="border rounded px-2 py-1 text-sm" onchange="olapApply()">
                <option value="">All</option>""" + olap_type_opts + """
              </select>
            </label>
            <label class="text-sm">Assignee
              <select id="olapAssignee" class="border rounded px-2 py-1 text-sm" onchange="olapApply()">
                <option value="">All</option>""" + olap_assignee_opts + """
              </select>
            </label>
            <label class="text-sm">Priority
              <select id="olapPriority" class="border rounded px-2 py-1 text-sm" onchange="olapApply()">
                <option value="">All</option>""" + olap_priority_opts + """
              </select>
            </label>
            <label class="text-sm">Status
              <select id="olapStatus" class="border rounded px-2 py-1 text-sm" onchange="olapApply()">
                <option value="">All</option>""" + olap_status_opts + """
              </select>
            </label>
            <label class="text-sm">Component
              <select id="olapComponent" class="border rounded px-2 py-1 text-sm" onchange="olapApply()">
                <option value="">All</option>""" + olap_component_opts + """
              </select>
            </label>
          </div>
          <div class="overflow-x-auto">
            <table class="w-full text-sm" id="olapTable">
              <thead><tr class="text-left border-b">
                <th class="py-2">Issue Type</th><th>Assignee</th><th>Priority</th>
                <th>Status</th><th>Component</th><th>Tasks</th><th>Avg Lifecycle (days)</th>
              </tr></thead>
              <tbody id="olapBody"><tr><td colspan="7" class="py-4 text-gray-400">Loading…</td></tr></tbody>
            </table>
          </div>
          <p class="text-xs text-gray-500 mt-2" id="olapSummary"></p>
          <div class="flex gap-2 mt-2"><button id="olapPrev" type="button" onclick="olapPage(-1)">Previous</button><button id="olapNext" type="button" onclick="olapPage(1)">Next</button></div>
        </div>

        <div class="widget mt-4">
          <h3 class="font-medium mb-2">Issue-Links OLAP Slice & Dice Constructor""" + _tip("Interactive multidimensional analysis over the issue-links (issuelinks) records: pick any combination of dimensions (Link Type, Direction, Source Issue Type, Target Issue Type, Source Status, Target Status) and the table recomputes, for each slice, the number of links. Use it to drill into how work is interconnected across any combination of these dimensions.") + """</h3>
          <p class="text-xs text-gray-500 mb-3">Slice the issue-links data cube by any combination of dimensions (Link Type, Direction, Source/Target Issue Type, Source/Target Status). Each row is one issuelinks record; the table shows the link count per slice.</p>
          <div class="flex flex-wrap gap-3 mb-3">
            <label class="text-sm">Link Type
              <select id="olapLinkType" class="border rounded px-2 py-1 text-sm" onchange="olapLinkApply()">
                <option value="">All</option>""" + olap_link_type_opts + """
              </select>
            </label>
            <label class="text-sm">Direction
              <select id="olapLinkDir" class="border rounded px-2 py-1 text-sm" onchange="olapLinkApply()">
                <option value="">All</option>""" + olap_link_dir_opts + """
              </select>
            </label>
            <label class="text-sm">Source Type
              <select id="olapLinkSType" class="border rounded px-2 py-1 text-sm" onchange="olapLinkApply()">
                <option value="">All</option>""" + olap_link_stype_opts + """
              </select>
            </label>
            <label class="text-sm">Target Type
              <select id="olapLinkTType" class="border rounded px-2 py-1 text-sm" onchange="olapLinkApply()">
                <option value="">All</option>""" + olap_link_ttype_opts + """
              </select>
            </label>
            <label class="text-sm">Source Status
              <select id="olapLinkSStatus" class="border rounded px-2 py-1 text-sm" onchange="olapLinkApply()">
                <option value="">All</option>""" + olap_link_sstatus_opts + """
              </select>
            </label>
            <label class="text-sm">Target Status
              <select id="olapLinkTStatus" class="border rounded px-2 py-1 text-sm" onchange="olapLinkApply()">
                <option value="">All</option>""" + olap_link_tstatus_opts + """
              </select>
            </label>
          </div>
          <div class="overflow-x-auto">
            <table class="w-full text-sm" id="olapLinkTable">
              <thead><tr class="text-left border-b">
                <th class="py-2">Link Type</th><th>Direction</th>
                <th>Source Type</th><th>Target Type</th><th>Source Status</th>
                <th>Target Status</th><th>Links</th>
              </tr></thead>
              <tbody id="olapLinkBody"><tr><td colspan="7" class="py-4 text-gray-400">Loading…</td></tr></tbody>
            </table>
          </div>
          <p class="text-xs text-gray-500 mt-2" id="olapLinkSummary"></p>
          <div class="flex gap-2 mt-2"><button id="olapLinkPrev" type="button" onclick="olapLinkPage(-1)">Previous</button><button id="olapLinkNext" type="button" onclick="olapLinkPage(1)">Next</button></div>
        </div>
      </section>

    </div>
  </div>
</div>
"""

    ctx = {}
    ctx['jm'] = jm
    ctx['artifacts'] = artifacts
    ctx['done'] = done
    ctx['opened'] = opened
    ctx['resolved'] = resolved
    ctx['total'] = total
    ctx['velocity'] = velocity
    ctx['weeks'] = weeks
    ctx['tab1_assets_mtime'] = tab1_assets_mtime
    ctx['tab1_assets_size_mb'] = tab1_assets_size_mb
    ctx['tab1_total_size_mb'] = tab1_total_size_mb
    ctx['tab2_total_size_mb'] = tab2_total_size_mb
    ctx['aging_rows'] = aging_rows
    ctx['artifact_sections'] = artifact_sections
    ctx['avg_cycle'] = avg_cycle
    ctx['avg_lead'] = avg_lead
    ctx['avg_velocity2'] = avg_velocity2
    ctx['bug_new'] = bug_new
    ctx['bug_res'] = bug_res
    ctx['cap_rows'] = cap_rows
    ctx['cfd_backlog'] = cfd_backlog
    ctx['cfd_chart_html'] = cfd_chart_html
    ctx['cfd_done'] = cfd_done
    ctx['cfd_ip'] = cfd_ip
    ctx['cfd_weeks'] = cfd_weeks
    ctx['control_chart_html'] = control_chart_html
    ctx['db_path'] = db_path
    ctx['db_size_mb'] = db_size_mb
    ctx['defect_age_rows'] = defect_age_rows
    ctx['jql_links'] = jql_links
    ctx['epic_report_html'] = epic_report_html
    ctx['forecast_chart_html'] = forecast_chart_html
    ctx['link_caps'] = link_caps
    ctx['link_kt'] = link_kt
    ctx['link_vision'] = link_vision
    ctx['olap_link_rows_json'] = olap_link_rows_json
    ctx['olap_rows_json'] = olap_rows_json
    ctx['opened2'] = opened2
    ctx['problem'] = problem
    ctx['ready_count'] = ready_count
    ctx['ready_rows'] = ready_rows
    ctx['resolved2'] = resolved2
    ctx['scope_change2'] = scope_change2
    ctx['scope_change_html'] = scope_change_html
    ctx['sprint_report_html'] = sprint_report_html
    ctx['tab1_folder_label'] = tab1_folder_label
    ctx['tab1_ts'] = tab1_ts
    ctx['tab2_ts'] = tab2_ts
    ctx['tab3_html'] = tab3_html
    ctx['sdlc_section_html'] = sdlc_section_html
    ctx['tis_js'] = tis_js
    ctx['trend_js'] = trend_js
    ctx['value_prop'] = value_prop
    ctx['velocity2'] = velocity2
    ctx['velocity_chart_html'] = velocity_chart_html
    ctx['vision'] = vision
    ctx['week2_labels'] = week2_labels
    ctx['week_labels'] = week_labels
    ctx['page_images_html'] = page_images_html
    return _render_html_shell(ctx)
