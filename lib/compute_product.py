"""Extract product content + Jira reports from ChromaDB documents."""
import json

def compute_product(docs_meta, docs):
    """Extract product content from Confluence pages, including any downloaded
    image/attachment artifacts (architecture / workflow schemas) recorded in
    the 'images' metadata field."""
    import json
    pages = {}
    for m, d in zip(docs_meta, docs):
        images = []
        raw = m.get("images") or ""
        if raw:
            try:
                images = json.loads(raw)
            except Exception:
                images = []
        pages[m.get("title", "")] = {
            "text": d,
            "url": m.get("url", ""),
            "images": images,
        }
    return pages


def compute_reports(docs_meta, docs):
    """Parse Jira board reports stored in ChromaDB (control chart, epic report,
    velocity, CFD, scope change, forecast, sprint). Returns a dict keyed by
    report kind, each with per-board parsed payloads. Reports that were never
    fetched (not available on the instance) are absent -> rendered N/A."""
    import json
    reports = {}
    for m, d in zip(docs_meta, docs):
        kind = m.get("report", "")
        board_id = m.get("board_id")
        board_name = m.get("board_name", f"board-{board_id}")
        try:
            payload = json.loads(d) if d else {}
        except Exception:
            payload = {}
        reports.setdefault(kind, []).append({
            "board_id": board_id,
            "board_name": board_name,
            "board_type": m.get("board_type"),
            "url": m.get("url", ""),
            "payload": payload,
        })
    return reports
