"""Chroma ingestion for Skill #1 (sync): upsert documents + incremental
sync markers.

Extracted 1:1 from the original monolithic sync_agent.py."""
import json
import os
import time
from datetime import datetime, timezone

import chromadb

# Sidecar file (per collection) that stores the last successful sync timestamp
# (ISO-8601 UTC). Kept next to the ChromaDB so --update can compute the
# incremental window without scanning every document.
SYNC_MARKER = "_sync_marker.json"


def _sync_marker_path(db_path, collection):
    return os.path.join(db_path, collection, SYNC_MARKER)


def _get_last_sync(db_path, collection):
    """Return the last recorded sync timestamp (ISO-8601 UTC string) or None."""
    path = _sync_marker_path(db_path, collection)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return (json.load(fh) or {}).get("last_sync")
    except Exception:
        return None


def _record_sync(db_path, collection, ts):
    """Persist the sync timestamp for a collection (ISO-8601 UTC string)."""
    path = _sync_marker_path(db_path, collection)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"last_sync": ts}, fh)


def _get_max_updated(db_path, collection):
    """Return the max 'updated' value already stored in the collection (Jira
    issues), or None if the collection is empty / has no 'updated' metadata."""
    try:
        client = chromadb.PersistentClient(path=db_path)
        col = client.get_collection(name=collection)
        res = col.get(include=["metadatas"], limit=10000)
        metas = res.get("metadatas") or []
        vals = [m.get("updated") for m in metas if m.get("updated")]
        return max(vals) if vals else None
    except Exception:
        return None


def ingest(docs, db_path, collection, batch_size, dry_run, update=False):
    if not docs:
        print("[Chroma] No documents to ingest.")
        return 0
    if dry_run:
        print(f"[Chroma] DRY-RUN: would {'update' if update else 'upsert'} "
              f"{len(docs)} docs into collection '{collection}' at '{db_path}'")
        return len(docs)

    os.makedirs(db_path, exist_ok=True)
    client = chromadb.PersistentClient(path=db_path)
    col = client.get_or_create_collection(name=collection)

    total = 0
    for i in range(0, len(docs), batch_size):
        batch = docs[i:i + batch_size]
        col.upsert(
            ids=[d["id"] for d in batch],
            documents=[d["text"] for d in batch],
            metadatas=[d["metadata"] for d in batch],
        )
        total += len(batch)
        print(f"  -> upserted {len(batch)} docs (running total {total})")
        time.sleep(0.5)
    print(f"[Chroma] Done. Collection '{collection}' count: {col.count()}")

    # Record the sync timestamp so subsequent --update runs stay incremental.
    _record_sync(db_path, collection,
                 datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return total
