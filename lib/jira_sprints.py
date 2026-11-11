"""Normalize Jira Sprint fields without requiring a new sync of legacy caches."""
import json
import logging
import re
from datetime import datetime, timezone

LOG = logging.getLogger(__name__)
_ATTR = re.compile(
    r"(?:^|,)\s*(id|name|state|startDate|endDate|completeDate|"
    r"rapidViewId|originBoardId|goal|activatedDate|autoStartStop|"
    r"incompleteIssuesDestinationId|sequence|synced)\s*="
)


def _instant(value):
    if not value or str(value).strip().lower() in {"null", "<null>", "none"}:
        return None
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        return None
    return stamp.astimezone(timezone.utc).isoformat()


def normalize_sprints(value):
    """Return (field populated, normalized records); names alone have no ID."""
    if value is None:
        return False, []
    if isinstance(value, (list, tuple)):
        present, records = False, []
        for part in value:
            found, normalized = normalize_sprints(part)
            present = present or found
            records.extend(normalized)
        return present, records
    if isinstance(value, str):
        value = value.strip()
        if value.lower() in {"", "null", "<null>", "none", "[]"}:
            return False, []
        if value.startswith(("[", "{")):
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, (list, dict)):
                return normalize_sprints(decoded)
        objects = re.findall(r"(?:[\w.$]+\.)?Sprint@[^\[\s]*\[(.*?)(?=\](?:\s*,\s*(?:[\w.$]+\.)?Sprint@|\s*$))",
                             value)
        records = []
        for body in objects:
            attrs = list(_ATTR.finditer(body))
            if len({match[1] for match in attrs}) != len(attrs):
                LOG.warning("Ambiguous attributes in a legacy Jira Sprint value")
                continue
            fields = {
                match[1]: body[match.end():attrs[i + 1].start()
                               if i + 1 < len(attrs) else len(body)].strip()
                for i, match in enumerate(attrs)
            }
            records.extend(normalize_sprints(fields)[1])
        return True, records
    if not isinstance(value, dict) or not value:
        return bool(value), []
    ident = value.get("id")
    if ident is None or not str(ident).strip().isdigit():
        return True, []
    board = value.get("originBoardId", value.get("rapidViewId"))
    return True, [{
        "id": str(int(ident)),
        "name": str(value.get("name") or f"Sprint {ident}"),
        "board": str(board) if board not in (None, "", "<null>", "null") else "",
        "state": str(value.get("state") or "").lower(),
        "start": _instant(value.get("startDate")),
        "end": _instant(value.get("endDate")),
        "complete": _instant(value.get("completeDate")),
    }]


def issue_sprints(metadata, document):
    """New structured metadata is authoritative; legacy text remains readable."""
    if "sprints_json" in metadata:
        return normalize_sprints(metadata["sprints_json"])
    for key in ("sprints", "sprint"):
        if metadata.get(key):
            return normalize_sprints(metadata[key])
    lines = re.findall(r"^Sprint:\s*([^\n]*)", document or "", re.MULTILINE)
    return normalize_sprints(lines[-1] if lines else None)


def sprint_catalog(records):
    """Merge matching IDs, retaining unusable/conflicting entries for diagnostics."""
    catalog = {}
    for record in records:
        ident = record["id"]
        if ident not in catalog:
            catalog[ident] = dict(record)
            continue
        merged = catalog[ident]
        for key in ("board", "start", "end", "complete"):
            if record.get(key) and merged.get(key) and record[key] != merged[key]:
                merged["conflict"] = True
            elif record.get(key):
                merged[key] = record[key]
        # A later closed observation can complete an earlier active observation.
        if record.get("state") == "closed" or not merged.get("state"):
            merged["state"] = record["state"]
    for entry in catalog.values():
        start = entry["start"]
        complete = entry["complete"]
        planned = entry["end"]
        end = complete if (
            (entry["state"] == "closed" or not entry["state"])
            and start and complete and complete > start) else None
        end = end or (planned if start and planned and planned > start else None)
        entry["closed"] = entry["state"] == "closed" or (
            not entry["state"] and bool(start and complete and complete > start))
        entry["finish"] = end
        entry["usable"] = bool(
            not entry.get("conflict") and entry["start"] and
            (not entry["closed"] or end and end > entry["start"]))
        if entry.get("conflict"):
            LOG.warning("Conflicting Jira sprint boundaries for sprint %s", entry["id"])
        elif not entry["usable"]:
            LOG.warning("Missing or invalid Jira sprint dates for sprint %s", entry["id"])
    return sorted(catalog.values(), key=lambda entry: (entry["start"] or "", entry["id"]))
