"""OLAP data-cube analysis (field density, transitions, time-in-status)."""
import os
from collections import Counter
from datetime import datetime
import pandas as pd
import chromadb
from .chromadb_utils import load_collection

# olap_analyser.py lives in lib/, so the project root is the PARENT directory.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB_PATH = os.path.abspath(
    os.path.join(_PROJECT_ROOT, ".vscode", "chroma_vector_db"))
COLLECTION = "product_jira"
OUTPUT_CUBE = os.path.abspath(
    os.path.join(_PROJECT_ROOT, "vector_dbs", "jira_data_cube.csv"))


def _parse_dt(s):
    """Parse an ISO datetime string to a datetime (or None)."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s)[:19])
    except Exception:
        return None


def _status_history_timestamps(doc_text):
    """Parse 'Status history:' lines from a document into a list of
    (datetime, from_status, to_status) tuples."""
    out = []
    if not doc_text or "Status history:" not in doc_text:
        return out
    section = doc_text.split("Status history:", 1)[1]
    for line in section.splitlines():
        line = line.strip()
        if "->" not in line:
            continue
        # Format: 2025-11-04T11:44:47.633+0000: New -> Open
        try:
            ts_str, _, frto = line.partition(": ")
            dt = _parse_dt(ts_str)
            if dt and "->" in frto:
                fr, to = [x.strip() for x in frto.split("->")]
                out.append((dt, fr, to))
        except Exception:
            continue
    return out


def load_issues(db_path=DEFAULT_DB_PATH, collection=COLLECTION):
    """Load all issues from ChromaDB into a list of normalized dicts."""
    client = chromadb.PersistentClient(path=db_path)
    col = client.get_collection(name=collection)
    results = col.get(include=["metadatas", "documents"])
    meta_list = results["metadatas"]
    doc_list = results["documents"]

    rows = []
    for meta, doc in zip(meta_list, doc_list):
        history = _status_history_timestamps(doc)
        rows.append({
            "key": meta.get("issue_key"),
            "type": meta.get("type"),
            "status": meta.get("status"),
            "priority": meta.get("priority"),
            "assignee": meta.get("assignee"),
            "reporter": meta.get("reporter"),
            "components": meta.get("components"),
            "labels": meta.get("labels"),
            "resolution": meta.get("resolution"),
            "created": _parse_dt(meta.get("created")),
            "in_progress": _parse_dt(meta.get("in_progress_date")),
            "done": _parse_dt(meta.get("done_date")),
            "updated": _parse_dt(meta.get("updated")),
            "history": history,
        })
    return rows


def compute_time_in_status(rows):
    """Compute exact time (days) each issue spent in each status, from the
    status-history timestamps. Returns a list of (issue_key, type, status,
    days)."""
    records = []
    for r in rows:
        hist = r["history"]
        if not hist:
            continue
        # Build a timeline: [(status, dt)] from transitions (to-status at dt)
        timeline = []
        for dt, _fr, to in hist:
            timeline.append((to, dt))
        # Sort by time
        timeline.sort(key=lambda x: x[1])
        # Add final status at 'updated' to close the last interval
        end_dt = r["updated"] or (r["done"] or r["created"])
        for i, (st, dt) in enumerate(timeline):
            nxt_dt = timeline[i + 1][1] if i + 1 < len(timeline) else end_dt
            if nxt_dt > dt:
                days = (nxt_dt - dt).total_seconds() / 86400.0
                records.append({
                    "key": r["key"], "type": r["type"],
                    "status": st, "days": round(days, 2),
                })
    return records


def compute_transition_frequency(rows):
    """Count transitions between statuses (from -> to), including
    back-and-forth 'ping-pong' moves."""
    trans = Counter()
    for r in rows:
        for _dt, fr, to in r["history"]:
            trans[(fr, to)] += 1
    return trans


