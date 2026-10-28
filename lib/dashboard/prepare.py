"""Dashboard data preparation: build_dashboard() computes every chart
series / fragment and returns the render context (split from
lib/dashboard_html.py; output is byte-identical to the monolith)."""
import os
from datetime import datetime
from ..dashboard_helpers import (esc, js_list, json_str, _tip,
    _dir_size_mb, _read_sync_marker, _fmt_ts, _rework_health_html)
from ..chromadb_utils import dir_size_mb, collection_folder
from .shell import _render_html_shell

def build_dashboard(jm, product_pages, db_path, reports_data=None,
                    artifacts=None, jprofile=None, event_analytics=None,
                    cross_linkage=None, collection_map=None, output_path=None,
                    metric_settings=None):
    import os
    reports_data = reports_data or {}
    artifacts = artifacts or {}
    jprofile = jprofile or {}
    event_analytics = event_analytics or {}
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
    ready_rows = "".join(
        f"<tr><td>{esc(k)}</td><td>{esc(s)}</td>"
        f"<td><a href='{esc(u)}' target='_blank'>link</a></td></tr>"
        for k, s, p, u in jm["backlog_ready"][:15]
    ) or "<tr><td colspan='3'>None</td></tr>"

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

    # [P17] Each link opens EXACTLY the issues the widget's metric counts.
    jql_links = {
        # open bugs (any priority, not resolved) — the open-bug population
        "open_bugs": _jql_link(
            "issuetype in (Bug, Sub-bug) AND resolution is EMPTY",
            "Open defects"),
        # defect age: the same open-bug population feeds the age stats
        "defect_age": _jql_link(
            "issuetype in (Bug, Sub-bug) AND resolution is EMPTY",
            "Open defects (age source)"),
        # production leakage: exactly the prod-labelled (leaked) defects
        "leakage": _jql_link(
            "labels = prod AND issuetype in (Bug, Sub-bug)",
            "Leaked (prod-tagged) defects"),
        # security posture: SAST-tool labels OR security-type issues
        "security": _jql_link(
            'labels in (sast, gitleaks, checkmarx, checkmarx_cxsast, snyk) '
            'OR issuetype in ("Security Issue", "Vulnerability", "Security")',
            "SAST/security issues"),
        # CWE findings: only the CWE-labelled findings feed the CWE widget
        "cwe": _jql_link(
            'labels starts with "cwe-"',
            "CWE findings"),
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
    jp_assignee_comp = jprofile.get("assignee_component", {})
    jp_reporter_prio = jprofile.get("reporter_priority", {})
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

    # --- 3a) Assignee <-> Component ownership grid ---
    ac_rows = "".join(
        f"<tr><td class='py-1'>{esc(a)}</td><td class='py-1'>{esc(c)}</td>"
        f"<td class='py-1'>{n}</td></tr>"
        for (a, c), n in jp_assignee_comp.items()) or \
        "<tr><td colspan='3'>N/A</td></tr>"

    # --- 3b) Reporter -> Priority escalation ---
    rp_rows = "".join(
        f"<tr><td class='py-1'>{esc(r)}</td><td class='py-1'>{esc(p)}</td>"
        f"<td class='py-1'>{n}</td></tr>"
        for (r, p), n in jp_reporter_prio.items()) or \
        "<tr><td colspan='3'>N/A</td></tr>"

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

    # 4e) OLAP Slice & Dice constructor data
    import json as _json
    jp_olap_dims = jprofile.get("olap_dims", [])
    jp_olap_rows = jprofile.get("olap_rows", [])
    def _olap_options(dim):
        seen = []
        for r in jp_olap_rows:
            v = r.get(dim, "")
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
    olap_rows_json = _json.dumps(jp_olap_rows)

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
    olap_link_rows_json = _json.dumps(jp_olap_link_rows)

    # ==================================================================
    # SDLC PROCESS MATRIX — Issue Type x Status (heatmap) + VSM Gaps
    # ==================================================================
    jp_sdlc_matrix = jprofile.get("sdlc_matrix", {})
    jp_sdlc_statuses = jprofile.get("sdlc_statuses", [])
    jp_sdlc_types = jprofile.get("sdlc_types", [])
    jp_vsm = jprofile.get("vsm_findings", [])
    jp_backlog = jprofile.get("backlog_stagnation", {})
    jp_sec = jprofile.get("security_in_progress", {})
    jp_subbug_ratio = jprofile.get("subbug_story_ratio")

    # --- Heatmap: rows = issue types, cols = statuses, cell = % ---
    sdlc_head = ("<tr class='text-left border-b'><th class='py-2'>Issue Type</th>"
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
            if v:
                alpha = 0.15 + 0.85 * (v / sdlc_max)
                cells += (f"<td class='px-1 py-1 text-center text-xs' "
                          f"style='background:rgba(16,185,129,{alpha:.2f}); "
                          f"color:rgba(6,78,59,{1 if alpha>0.45 else 0.8})' "
                          f"title='{esc(t)} · {esc(s)}: {v}%'>{v}%</td>")
            else:
                cells += "<td class='px-1 py-1 text-center text-gray-300'>·</td>"
        sdlc_body += f"<tr><td class='py-1 font-medium text-xs'>{esc(t)}</td>{cells}</tr>"
    sdlc_heatmap_html = (
        "<div class='overflow-x-auto'><table class='w-full text-xs'>"
        f"<thead>{sdlc_head}</thead><tbody>{sdlc_body}</tbody></table></div>"
        if jp_sdlc_matrix else "<div class='na-box'>N/A</div>")

    # --- Value Stream Mapping Gaps: heuristic risk findings ---
    vsm_cards = ""
    if jp_vsm:
        for f in jp_vsm:
            color = "#b45309" if f["level"] == "warning" else "#dc2626"
            icon = "⚠️" if f["level"] == "warning" else "🔴"
            vsm_cards += (
                f"<div class='widget border-l-4' style='border-left-color:{color}'>"
                f"<h3 class='font-medium mb-1'>{icon} {esc(f['kind'])}</h3>"
                f"<p class='text-sm text-gray-700'>{esc(f['message'])}</p>"
                f"<p class='text-xs text-gray-400 mt-1'>metric value: "
                f"{esc(f['value'])}</p></div>")
    else:
        vsm_cards = (
            "<div class='widget'><h3 class='font-medium mb-2'>Value Stream "
            "Mapping Gaps</h3><div class='na-box'>N/A — no risk flags "
            "detected</div></div>")

    # --- Backlog Stagnation detail table (per type) ---
    stag_rows = "".join(
        f"<tr><td class='py-1'>{esc(b['type'])}</td>"
        f"<td class='py-1'>{b['count']}</td></tr>"
        for b in jp_backlog.get("by_type", [])) or \
        "<tr><td colspan='2'>N/A</td></tr>"

    # ==================================================================
    # EVENT-DRIVEN ANALYTICS (Tab 3) — advanced event/trigger analysis
    # ==================================================================
    import json as _event_json
    ev_m1 = event_analytics.get("module1", {})
    ev_m2 = event_analytics.get("module2", {})
    ev_m3 = event_analytics.get("module3", {})

    # --- Module 1: Jira Defect Causality & SDLC Triggers -------------------
    # Three sub-widgets: (a) Story Status at Defect Birth, (b) Parent-Child
    # Closure Sync Tracker, (c) Sub-Bug Creation Constraints Validation.
    m1a = ev_m1.get("module1a", {})
    m1b = ev_m1.get("module1b", {})
    m1c = ev_m1.get("module1c", {})

    # --- Widget (a): Story Status at Defect Birth (Doughnut) ---
    m1a_dist = m1a.get("distribution_pct", [])
    if m1a.get("na"):
        module1a_html = ("<div class='widget'><h3 class='font-medium mb-2'>"
                         "Story Status at Defect Birth" +
                         _tip("For every Bug/Sub-Bug, the parent feature (Story/Task) is resolved via hard linkage: Sub-Bugs use the system parent field; Bugs use issuelinks (blocked-by / relates-to / associated / depends) to a Story/Task. The doughnut shows the parent's status at the exact second the defect was created (from the parent's changelog). Answers: 'in which phases do our stories generate bugs?'") +
                         "</h3><div class='na-box'>N/A — no resolvable defect-parent links</div></div>")
        module1a_js = ""
    else:
        m1a_labels = _event_json.dumps([d["status"] for d in m1a_dist])
        m1a_counts = _event_json.dumps([d["count"] for d in m1a_dist])
        m1a_colors = _event_json.dumps(
            ["#2563eb", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6", "#06b6d4",
             "#f97316", "#14b8a6", "#6366f1", "#ec4899"][:max(1, len(m1a_dist))])
        module1a_html = (
            "<div class='widget'><h3 class='font-medium mb-2'>Story Status at "
            "Defect Birth" +
            _tip("For every Bug/Sub-Bug, the parent feature (Story/Task) is resolved via hard linkage: Sub-Bugs use the system parent field; Bugs use issuelinks (blocked-by / relates-to / associated / depends) to a Story/Task. The doughnut shows the parent's status at the exact second the defect was created (from the parent's changelog). Answers: 'in which phases do our stories generate bugs?'") +
            "</h3>"
            f"<p class='text-xs text-gray-500 mb-2'>Defects with a resolvable "
            f"parent: <strong>{m1a.get('with_parent', 0)}</strong> of "
            f"{m1a.get('total_bugs', 0)}</p>"
            "<div style='height:280px'><canvas id='evM1Doughnut'></canvas></div>"
            "</div>")
        module1a_js = (
            "var ctxM1=document.getElementById('evM1Doughnut');"
            "if(ctxM1){new Chart(ctxM1,{type:'doughnut',"
            "data:{labels:" + m1a_labels + ",datasets:[{data:" + m1a_counts + ","
            "backgroundColor:" + m1a_colors + "}]},"
            "options:{responsive:true,maintainAspectRatio:false,"
            "plugins:{legend:{position:'right'},tooltip:{"
            "callbacks:{label:function(c){var t=c.label||'';var v=c.parsed||0;"
            "var tot=c.dataset.data.reduce(function(a,b){return a+b;},0);"
            "var p=tot?Math.round(v/tot*100):0;return t+' ('+p+'%) — '+v+' defects';}}}}}});}")

    # --- Widget (b): Parent-Child Closure Sync Tracker (stuck-parents table) --
    m1b_stuck = m1b.get("stuck", [])
    m1b_stuck_rows = "".join(
        "<tr>"
        f"<td class='py-1'>{esc(r.get('type'))}</td>"
        f"<td class='py-1'><a class='text-blue-600' href='{esc(r.get('url'))}' "
        f"target='_blank'>{esc(r.get('key'))}</a></td>"
        f"<td class='py-1'>{esc(r.get('status'))}</td>"
        f"<td class='py-1 text-right font-mono'>{r.get('latency_hrs', 0)} h</td>"
        "</tr>"
        for r in m1b_stuck) or "<tr><td colspan='4'>None</td></tr>"
    module1b_html = (
        "<div class='widget'><h3 class='font-medium mb-2'>Parent-Child Closure "
        "Sync Tracker — Stuck Parents" +
        _tip("For every parent (ANY issue type) with Sub-task / Sub-Bug children, computes T_last_child = max(updated) among children that reached Closed/Resolved. A parent is flagged as STUCK when it has NO status transition strictly after T_last_child — i.e. it did not advance to its next workflow status (in testing / resolved / closed / done / ...) once all its children closed. Latency = hours elapsed since the last child closed (still stuck).") +
        "</h3>"
        "<p class='text-xs text-gray-500 mb-3'>Parents whose status did not "
        "change after the last Sub-task / Sub-Bug closed, even though their "
        "workflow (section 2) expects a move to the next status. "
        "<strong>" + str(m1b.get("stuck_count", 0)) + "</strong> of "
        "<strong>" + str(m1b.get("parents_analyzed", 0)) + "</strong> "
        "analyzed parents are stuck.</p>"
        "<div class='overflow-x-auto'><table class='w-full text-sm'>"
        "<thead><tr class='text-left border-b'><th class='py-2'>Issue Type (Parent)</th>"
        "<th>Issue</th><th>Parent Status</th><th class='text-right'>Latency (h)</th>"
        "</tr></thead><tbody>" + m1b_stuck_rows + "</tbody></table></div></div>")
    module1b_js = ""

    # --- Widget (c): Sub-Bug Creation Constraints Validation (data grid) ---
    m1c_dist = m1c.get("distribution", [])
    if m1c.get("na"):
        module1c_html = ("<div class='widget'><h3 class='font-medium mb-2'>"
                         "Sub-Bug Creation Constraints Validation" +
                         _tip("For every [Story/Task/Bug → Sub-Bug] pair, captures the parent's status at the exact second the Sub-Bug was created. Tests the hypothesis that Sub-Bugs are only created while the parent is in 'In Testing' (100%).") +
                         "</h3><div class='na-box'>N/A — no Sub-Bug pairs found</div></div>")
        module1c_js = ""
    else:
        it_pct = m1c.get("in_testing_pct", 0)
        hypothesis_ok = (it_pct == 100.0)
        verdict = ("✅ Hypothesis CONFIRMED — Sub-Bugs are created only while "
                   "the parent is In Testing."
                   if hypothesis_ok else
                   "⚠️ Hypothesis REJECTED — Sub-Bugs are also created while "
                   "the parent is in other statuses.")
        dist_rows = "".join(
            f"<tr><td class='py-1'>{esc(d['status'])}</td>"
            f"<td class='py-1 text-right font-mono'>{d['pct']}%</td>"
            f"<td class='py-1 text-right font-mono'>{d['count']}</td></tr>"
            for d in m1c_dist) or "<tr><td colspan='3'>N/A</td></tr>"
        module1c_html = (
            "<div class='widget'><h3 class='font-medium mb-2'>Sub-Bug Creation "
            "Constraints Validation" +
            _tip("For every [Story/Task/Bug → Sub-Bug] pair, captures the parent's status at the exact second the Sub-Bug was created. Tests the hypothesis that Sub-Bugs are only created while the parent is in 'In Testing' (100%).") +
            "</h3>"
            "<p class='text-xs text-gray-500 mb-2'>Is it true that a Sub-Bug is "
            "created only when the parent is in <strong>In Testing</strong>?</p>"
            "<p class='text-sm mb-3'>" + verdict + "</p>"
            "<table class='w-full text-sm'><thead><tr class='text-left border-b'>"
            "<th class='py-2'>Parent status at Sub-Bug creation</th><th>%</th>"
            "<th>Count</th></tr></thead><tbody>" + dist_rows + "</tbody></table>"
            "<p class='text-xs text-gray-500 mt-2'>Pairs analyzed: <strong>" +
            str(m1c.get("total_pairs", 0)) + "</strong> · In Testing: <strong>" +
            str(m1c.get("in_testing_pct", 0)) + "%</strong></p></div>")
        module1c_js = ""

    module1_html = module1a_html + module1b_html + module1c_html
    module1_js = module1a_js + module1b_js + module1c_js

    # --- Module 3: Bubble chart — labels vs cycle time / ping-pong ---
    m3_base = ev_m3.get("baseline", {})
    m3_cohorts = ev_m3.get("cohorts", [])
    m3_risk = ev_m3.get("risk_labels", [])
    if not m3_cohorts:
        module3_html = ("<div class='widget'><h3 class='font-medium mb-2'>"
                        "Metadata Impact (Labels & Custom Fields)" +
                        _tip("Splits issues into cohorts by label (labels appearing in ≥3 issues only), computing each cohort's median cycle time and ping-pong (rework) rate versus the project baseline.") +
                        "</h3><div class='na-box'>N/A — no label cohorts (labels "
                        "appearing in ≥3 issues)</div></div>")
        module3_js = ""
    else:
        m3_bubbles = []
        for c in m3_cohorts:
            m3_bubbles.append({
                "x": c.get("cycle_days") or 0,
                "y": c.get("pingpong") or 0,
                "r": max(4, min(24, (c.get("count") or 1) * 1.2)),
                "label": c.get("label"),
                "count": c.get("count"),
                "risk": c.get("risk", False),
            })
        m3_bubbles_json = _event_json.dumps(m3_bubbles)
        m3_base_x = m3_base.get("cycle_days")
        m3_base_y = m3_base.get("pingpong")
        risk_block = ""
        if m3_risk:
            risk_block = (
                "<div class='widget' style='border-color:#fecaca;background:#fef2f2'>"
                "<h3 class='font-medium mb-2 text-red-700'>⚠️ High Risk Scope "
                "Detected</h3><ul class='list-disc pl-5 text-sm text-red-800'>" +
                "".join(f"<li>{esc(lab)}</li>" for lab in m3_risk) +
                "</ul><p class='text-xs text-gray-500 mt-2'>These label cohorts "
                "sit above the project baseline in BOTH median cycle time and "
                "ping-pong (rework) rate.</p></div>")
        m3_base_x_s = f"{m3_base_x}d" if m3_base_x is not None else "N/A"
        m3_base_y_s = f"{m3_base_y}" if m3_base_y is not None else "N/A"
        module3_html = (
            "<div class='widget'><h3 class='font-medium mb-2'>Metadata Impact "
            "(Labels & Custom Fields)" +
            _tip("Splits issues into cohorts by label (labels appearing in ≥3 issues only), computing each cohort's median cycle time and ping-pong (rework) rate versus the project baseline. Cohorts above baseline in BOTH dimensions are flagged High Risk Scope.") +
            "</h3>"
            "<p class='text-xs text-gray-500 mb-2'>Baseline (no label): "
            "median cycle <strong>" + m3_base_x_s +
            "</strong> · ping-pong <strong>" + m3_base_y_s +
            "</strong> per issue. Bubble size = issue count.</p>"
            "<div style='height:320px'><canvas id='evM3Bubble'></canvas></div>"
            "<div class='mt-3'>" + risk_block + "</div></div>")
        module3_js = (
            "var ctxM3=document.getElementById('evM3Bubble');"
            "if(ctxM3){var bubbles=" + m3_bubbles_json + ";"
            "new Chart(ctxM3,{type:'bubble',"
            "data:{datasets:[{label:'Label cohorts',data:bubbles,"
            "backgroundColor:function(ctx){return ctx.raw&&ctx.raw.risk?"
            "'rgba(239,68,68,0.6)':'rgba(37,99,235,0.6)';},"
            "borderColor:function(ctx){return ctx.raw&&ctx.raw.risk?'#dc2626':'#2563eb';}"
            "}]},"
            "options:{responsive:true,maintainAspectRatio:false,"
            "scales:{x:{title:{display:true,text:'Median Cycle Time (days)'}},"
            "y:{title:{display:true,text:'Ping-Pong Count per Issue'}}},"
            "plugins:{tooltip:{callbacks:{label:function(c){var r=c.raw;"
            "return r.label+' ('+r.count+' issues) — cycle '+r.x+'d, ping-pong '+r.y;}}}"
            "}}});}")
 
    # ==================================================================
    # JIRA CROSS-LINKAGE & SDLC WASTE (Tab 3) — issuelinks 4-category
    # ==================================================================
    cl_summary = cross_linkage.get("summary", {})
    cl_total = cross_linkage.get("total_links", 0)
    cl_a = cross_linkage.get("category_a", {})
    cl_b = cross_linkage.get("category_b", {})
    cl_c = cross_linkage.get("category_c", {})
    cl_d = cross_linkage.get("category_d", {})

    # Per-category colors
    cl_colors = {"A": "#ef4444", "B": "#f59e0b", "C": "#8b5cf6", "D": "#06b6d4"}
    cl_names = {"A": "A · Hard Blockers", "B": "B · Process Rework",
                "C": "C · Scope Duplication", "D": "D · Soft Associations"}

    # --- Callout cards per category (N/A if category absent) ---
    def _cl_callout(cat, title, subtitle, body_html):
        col = cl_colors[cat]
        return ("<div class='widget' style='border-left:4px solid " + col + ";'>"
                "<div class='flex items-center justify-between mb-1'>"
                "<h3 class='font-medium'>" + title + "</h3>"
                "<span class='text-xs font-mono px-2 py-0.5 rounded-full' "
                "style='background:" + col + "22;color:" + col + "'>" +
                str(cl_summary.get(cat, 0)) + " links</span></div>"
                "<p class='text-xs text-gray-500 mb-2'>" + subtitle + "</p>"
                + body_html + "</div>")

    # Category A callout
    if cl_a.get("na"):
        cl_a_html = _cl_callout("A", "Hard Blockers", "blocks / is blocked by / Depend",
                                "<div class='na-box'>N/A — no hard blocker links</div>")
    else:
        a_rate = cl_a.get("blocker_stagnation_rate")
        a_rate_s = f"{a_rate}%" if a_rate is not None else "N/A"
        a_react = cl_a.get("avg_reaction_hrs")
        a_react_s = (f"{a_react} h" if a_react is not None else "N/A")
        cl_a_html = _cl_callout(
            "A", "Hard Blockers", "Blocker reaction & stagnation",
            "<table class='w-full text-sm'><tbody>"
            "<tr><td class='py-1'>Blocker reaction (avg)</td>"
            "<td class='text-right font-mono'>" + a_react_s + "</td></tr>"
            "<tr><td class='py-1'>Stagnation rate (>24h)</td>"
            "<td class='text-right font-mono'>" + a_rate_s + "</td></tr>"
            "<tr><td class='py-1'>Stagnant blockers</td>"
            "<td class='text-right font-mono'>" + str(cl_a.get("stagnant_count", 0)) +
            "</td></tr></tbody></table>")

    # Category B callout
    if cl_b.get("na"):
        cl_b_html = _cl_callout("B", "Process Rework", "causes / is caused by",
                                "<div class='na-box'>N/A — no cause/rework links</div>")
    else:
        cl_b_html = _cl_callout(
            "B", "Process Rework", "Escaped defects (cause after source closed)",
            "<table class='w-full text-sm'><tbody>"
            "<tr><td class='py-1'>Escaped causes</td>"
            "<td class='text-right font-mono'>" + str(cl_b.get("escaped_causes", 0)) +
            "</td></tr>"
            "<tr><td class='py-1'>Avg escaped / project</td>"
            "<td class='text-right font-mono'>" +
            str(cl_b.get("avg_escaped_per_project", 0)) +
            "</td></tr></tbody></table>")

    # Category C callout
    if cl_c.get("na"):
        cl_c_html = _cl_callout("C", "Scope Duplication", "duplicates / clones / Cloners",
                                "<div class='na-box'>N/A — no duplication links</div>")
    else:
        cl_c_html = _cl_callout(
            "C", "Scope Duplication", "Waste scope (sunk hours in duplicates)",
            "<table class='w-full text-sm'><tbody>"
            "<tr><td class='py-1'>Sunk hours</td>"
            "<td class='text-right font-mono'>" + str(cl_c.get("sunk_hours", 0)) +
            "</td></tr>"
            "<tr><td class='py-1'>Sunk days</td>"
            "<td class='text-right font-mono'>" + str(cl_c.get("sunk_days", 0)) +
            "</td></tr>"
            "<tr><td class='py-1'>Closed as duplicate</td>"
            "<td class='text-right font-mono'>" + str(cl_c.get("closed_duplicates", 0)) +
            "</td></tr></tbody></table>")

    # Category D callout
    if cl_d.get("na"):
        cl_d_html = _cl_callout("D", "Soft Associations", "relates to / Related To / Part of",
                                "<div class='na-box'>N/A — no soft-association links</div>")
    else:
        d_sync = cl_d.get("sync_ratio")
        d_sync_s = f"{d_sync}%" if d_sync is not None else "N/A"
        cl_d_html = _cl_callout(
            "D", "Soft Associations", "Closure sync matrix",
            "<table class='w-full text-sm'><tbody>"
            "<tr><td class='py-1'>Same-month closure</td>"
            "<td class='text-right font-mono'>" + str(cl_d.get("in_same_month", 0)) +
            "</td></tr>"
            "<tr><td class='py-1'>Closure sync ratio</td>"
            "<td class='text-right font-mono'>" + d_sync_s + "</td></tr>"
            "<tr><td class='py-1'>Spread closures</td>"
            "<td class='text-right font-mono'>" + str(cl_d.get("spread", 0)) +
            "</td></tr></tbody></table>")

    # --- Doughnut: category distribution ---
    cl_dist_labels = _event_json.dumps([cl_names[c] for c in "ABCD"])
    cl_dist_counts = _event_json.dumps([cl_summary.get(c, 0) for c in "ABCD"])
    cl_dist_colors = _event_json.dumps([cl_colors[c] for c in "ABCD"])
    cl_dist_js = (
        "var ctxCL=document.getElementById('clDoughnut');"
        "if(ctxCL){new Chart(ctxCL,{type:'doughnut',"
        "data:{labels:" + cl_dist_labels + ",datasets:[{data:" + cl_dist_counts +
        ",backgroundColor:" + cl_dist_colors + "}]},"
        "options:{responsive:true,maintainAspectRatio:false,"
        "plugins:{legend:{position:'right'},tooltip:{"
        "callbacks:{label:function(c){var t=c.label||'';var v=c.parsed||0;"
        "var tot=c.dataset.data.reduce(function(a,b){return a+b;},0);"
        "var p=tot?Math.round(v/tot*100):0;return t+' ('+p+'%) — '+v+' links';}}}}}});}")

    crosslink_widget_html = """
      <div class="widget">
        <h3 class="font-medium mb-2">Jira Cross-Linkage & SDLC Waste Dashboard""" + _tip("Classifies every issuelinks record across ALL issues (horizontal links, not just parent/child) into 4 macro-categories of SDLC waste. <b>A · Hard Blockers</b> (blocks / is blocked by / Depend) — links that stop other work; 'avg reaction' = hours from blocker creation to the blocked issue reaching In Progress, 'stagnation' = % of blocked targets stuck >24h (higher = more blocked pipeline). <b>B · Process Rework</b> (causes / is caused by) — 'escaped causes' = defects created AFTER their source issue was already closed (rework that should have been caught earlier). <b>C · Scope Duplication</b> (duplicates / clones / Cloners) — 'sunk hours' = time spent In Progress on issues later closed as Duplicate/Won't Fix (wasted effort); 'closed dupes' = count of such issues. <b>D · Soft Associations</b> (relates to / Related To / Part of) — 'closure sync' = % of linked pairs closed within the same month (higher = better coordinated delivery). The doughnut shows the share of each category among all links; each callout card reports the key metric for its category.") + """</h3>
        <p class="text-xs text-gray-500 mb-3">Classified <strong>""" + str(cl_total) + """</strong> issue
        links across all issues into 4 macro-categories of SDLC waste.</p>
        <div class="grid md:grid-cols-2 gap-4">
          <div style="height:260px"><canvas id="clDoughnut"></canvas></div>
          <div>""" + cl_a_html + """</div>
        </div>
        <div class="grid md:grid-cols-3 gap-4 mt-4">
          """ + cl_b_html + """
          """ + cl_c_html + """
          """ + cl_d_html + """
        </div>
      </div>
    """

    event_section_html = """
       <section id="d-events" class="scroll-mt-24">
         <h2 class="text-lg font-semibold mb-3">8. Event-Driven Analytics</h2>
         <p class="text-xs text-gray-500 mb-3">Advanced event analysis: defect
         causality (story status at defect birth, parent-child closure sync,
         sub-bug creation constraints), the impact of labels / custom fields on
         cycle time and rework, and the Jira Cross-Linkage & SDLC Waste
         classifier.</p>
         <div class="grid md:grid-cols-2 gap-4">
           """ + module1a_html + """
           """ + module1c_html + """
         </div>
         <div class="mt-4">
           """ + module1b_html + """
         </div>
         <div class="mt-4">
           """ + module3_html + """
         </div>
         <div class="mt-4">
           """ + crosslink_widget_html + """
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
        <a href="#d-heuristics" class="sidebar-link block px-3 py-2 rounded-lg">3. Heuristic Associations</a>
        <a href="#d-sdlc" class="sidebar-link block px-3 py-2 rounded-lg">3b. SDLC Process Matrix</a>
        <a href="#d-dependencies" class="sidebar-link block px-3 py-2 rounded-lg">4. Field Dependencies & Trends</a>
        <a href="#d-transitions" class="sidebar-link block px-3 py-2 rounded-lg">5. Transition Frequency</a>
        <a href="#d-timestatus" class="sidebar-link block px-3 py-2 rounded-lg">6. Time-in-Status</a>
        <a href="#d-olap" class="sidebar-link block px-3 py-2 rounded-lg">7. OLAP Slice & Dice</a>
        <a href="#d-events" class="sidebar-link block px-3 py-2 rounded-lg">8. Event-Driven Analytics</a>
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

      <section id="d-heuristics" class="scroll-mt-24">
        <h2 class="text-lg font-semibold mb-3">3. Heuristic & Structural Associations</h2>
        <div class="grid md:grid-cols-2 gap-4">
          <div class="widget"><h3 class="font-medium mb-2">Assignee → Component (Ownership)""" + _tip("Cross-tabulation of who (Assignee) works on which Component, with the number of issues. Highlights ownership concentration: a single assignee owning many components (or a component with many assignees) can indicate bus-factor risk or unclear ownership.") + """</h3>
            <table class="w-full text-sm"><thead><tr class="text-left border-b"><th class="py-2">Assignee</th><th>Component</th><th>Issues</th></tr></thead><tbody>""" + ac_rows + """</tbody></table></div>
          <div class="widget"><h3 class="font-medium mb-2">Reporter → Priority (Escalation)""" + _tip("Cross-tabulation of who (Reporter) raises issues at which Priority level. Reveals escalation patterns and which reporters tend to open high-priority work — useful for triage and stakeholder management.") + """</h3>
            <table class="w-full text-sm"><thead><tr class="text-left border-b"><th class="py-2">Reporter</th><th>Priority</th><th>Issues</th></tr></thead><tbody>""" + rp_rows + """</tbody></table></div>
        </div>
      </section>

      <section id="d-sdlc" class="scroll-mt-24">
        <h2 class="text-lg font-semibold mb-3">3b. SDLC Process Matrix — Issue Type vs Status Dependencies</h2>
        <p class="text-xs text-gray-500 mb-3">Cross-tabulation of every Issue Type against the key SDLC statuses. Each cell shows the % of that type's issues currently in that status. The Value Stream Mapping Gaps panel renders automatic heuristic risk flags for delivery health.</p>
        <div class="widget mb-4"><h3 class="font-medium mb-2">Issue Type × Status Distribution (% of issues)""" + _tip("For each Issue Type, the share of its issues currently sitting in each SDLC status. Computed as: (issues of the type in that status) ÷ (all issues of that type) × 100. Reveals where work concentrates across the value stream (e.g. a type stuck mostly in Analysis/Backlog vs mostly in Testing).") + """</h3>""" + sdlc_heatmap_html + """</div>
        <div class="grid md:grid-cols-3 gap-4">
          <div class="widget md:col-span-2">
            <h3 class="font-medium mb-2">Value Stream Mapping Gaps (heuristic risk flags)""" + _tip("Automatic heuristic flags for delivery-health risks: e.g. too much work in early stages (Analysis/Backlog) vs too little in review, high rework, or unbalanced WIP across statuses. Each card lists the affected type, the rule that fired, and its severity.") + """</h3>
            <div class="space-y-3">""" + vsm_cards + """</div>
          </div>
          <div class="widget">
            <h3 class="font-medium mb-2">Backlog Stagnation — Open >180 days (by type)""" + _tip("Counts issues that have been sitting in an Open/Backlog status for more than 180 days (from their created date), grouped by Issue Type. High stagnation means requirements are aging in the backlog without being groomed, prioritized, or started.") + """</h3>
            <table class="w-full text-sm"><thead><tr class="text-left border-b"><th class="py-2">Type</th><th>Stagnant Open</th></tr></thead><tbody>""" + stag_rows + """</tbody></table>
            <p class="text-xs text-gray-500 mt-2">Total: <strong>""" + str(jp_backlog.get("total", 0)) + """</strong> issues in Open >180 days.</p>
          </div>
        </div>
      </section>

      <section id="d-dependencies" class="scroll-mt-24">
        <h2 class="text-lg font-semibold mb-3">4. Field Dependencies & Trends</h2>
        <p class="text-xs text-gray-500 mb-3">Co-fill matrix shows what % of issues populate both fields (field correlation). Trend charts show how often each optional field is left empty over biweekly periods — a drop signals fields being neglected.</p>
        <div class="widget mb-4"><h3 class="font-medium mb-2">Field Co-fill Correlation Matrix (% both populated)""" + _tip("For every pair of fields, the % of issues that populate BOTH fields simultaneously. Computed as: (issues where both fields are non-empty) ÷ (issues where at least one is populated) × 100. High co-fill between fields that should be independent may indicate redundant data entry; low co-fill between related fields suggests they are filled inconsistently.") + """</h3>""" + field_corr_html + """</div>
        <div class="grid md:grid-cols-2 gap-4">""" + trend_series_html + """</div>
      </section>

      <section id="d-transitions" class="scroll-mt-24">
        <h2 class="text-lg font-semibold mb-3">5. Transition Frequency & Intensity</h2>
        <p class="text-xs text-gray-500 mb-3">Heatmap of status-to-status transition counts from the changelog. The "ping-pong" table flags back-and-forth jumps (rework / churn) such as Closed ⇄ Reopened.</p>
        <div class="widget mb-4"><h3 class="font-medium mb-2">Transition Frequency Heatmap (From → To)""" + _tip("Counts, for every ordered status pair (From → To), how many times the team moved work that way, derived from the issue changelog. High-frequency cells reveal the dominant workflow path; unexpected jumps (e.g. To Do → Done) expose bypassed process steps.") + """</h3>""" + heatmap_html + """</div>
        <div class="widget"><h3 class="font-medium mb-2">Ping-Pong (rework) Status Jumps""" + _tip("Identifies back-and-forth status churn (A→B then B→A), such as Closed ⇄ Reopened or In Testing ⇄ In Progress. Each row shows both directions plus the total. Frequent ping-pong is a strong signal of rework, unclear requirements, or process instability.") + """</h3>
          <table class="w-full text-sm"><thead><tr class="text-left border-b"><th class="py-2">Pair</th><th>A→B</th><th>B→A</th><th>Total</th></tr></thead><tbody>""" + pingpong_rows + """</tbody></table></div>
      </section>

      <section id="d-timestatus" class="scroll-mt-24">
        <h2 class="text-lg font-semibold mb-3">6. Time-in-Status (Median Days per Status)</h2>
        <p class="text-xs text-gray-500 mb-3">Median time issues spend in each status, per issue type. Red bars flag "stagnant" statuses where work typically dies (>60 days) — candidates for process intervention.</p>
        <div class="grid md:grid-cols-2 gap-4">""" + tis_widgets + """</div>
      </section>

      <section id="d-olap" class="scroll-mt-24">
        <h2 class="text-lg font-semibold mb-3">7. Interactive OLAP Slice & Dice Constructor""" + _tip("Interactive multidimensional analysis: pick any combination of dimensions (Issue Type, Assignee, Priority, Status, Component) and the table recomputes, for each slice, the task count and the average lifecycle in days (Resolution − Created). Use it to drill into where time and effort actually go.") + """</h2>
        <p class="text-xs text-gray-500 mb-3">Slice the issue data cube by any combination of dimensions (Issue Type, Assignee, Priority, Status, Component). The table below shows task count and average lifecycle (resolution − created, days) for each slice. Use the filters to drill down.</p>
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
        </div>
      </section>

      """ + event_section_html + """

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
    ctx['module3_js'] = module3_js
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
    ctx['cl_dist_js'] = cl_dist_js
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
    ctx['module1_js'] = module1_js
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
