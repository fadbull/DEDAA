"""Date / status helpers shared across the compute modules."""
from datetime import datetime, timezone

# Status groupings (must match sync_agent.py).
CLOSED = {"closed", "done", "resolved", "complete", "completed", "cancelled",
          "canceled", "verified", "released", "won't do", "wont do", "duplicate"}
IN_PROGRESS = {"in progress", "in review", "in testing", "in qa", "review",
               "ready for development", "design", "analysis", "ready for grooming"}
BACKLOG = {"new", "open", "to do", "backlog", "reopened"}

def _dt(s):
    try:
        return datetime.fromisoformat(s[:10])
    except Exception:
        return None


def _dt_full(s):
    """Parse a full ISO datetime INCLUDING time (needed for sub-day event
    analytics such as the 5-minute automation trigger window). Falls back to
    the date-only parser if the full timestamp cannot be parsed."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return _dt(s)


def _biweek(dt):
    """Return a 2-week period key (e.g. '2025-W21-22') for a datetime."""
    iso = dt.isocalendar()
    year, week = iso[0], iso[1]
    # Group consecutive weeks into 2-week buckets: weeks 1-2, 3-4, ...
    bucket = ((week - 1) // 2) * 2 + 1
    return f"{year}-W{bucket:02d}-{bucket + 1:02d}"


def status_group(status):
    s = (status or "").strip().lower()
    if s in CLOSED:
        return "Closed"
    if s in IN_PROGRESS:
        return "In Progress"
    if s in BACKLOG:
        return "Backlog"
    return "Other"


def _status_events_from_text(doc_text):
    """Return sorted [(datetime, to_status)] parsed from a 'Status history:'
    section in a Chroma document."""
    ev = []
    if not doc_text or "Status history:" not in doc_text:
        return ev
    sec = doc_text.split("Status history:", 1)[1]
    for line in sec.splitlines():
        line = line.strip()
        if "->" not in line:
            continue
        ts_str, _, frto = line.partition(": ")
        dt = _dt_full(ts_str)
        if dt and "->" in frto:
            to = [x.strip() for x in frto.split("->")][1]
            ev.append((dt, to))
    ev.sort(key=lambda x: x[0])
    return ev


def _status_transitions_from_text(doc_text):
    """Parse observed status transitions, normalized to UTC."""
    events = []
    if not doc_text or "Status history:" not in doc_text:
        return events
    for line in doc_text.split("Status history:", 1)[1].splitlines():
        timestamp, separator, change = line.strip().partition(": ")
        if not separator or "->" not in change:
            continue
        before, after = (part.strip() for part in change.split("->", 1))
        dt = _utc_instant(timestamp)
        if not dt or not before or not after or before == "None" or after == "None":
            continue
        events.append((dt, before, after))
    return sorted(events, key=lambda event: event[0])


def _utc_datetime(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _utc_instant(value):
    if not value or len(str(value)) < 16 or str(value)[10] not in ("T", " "):
        return None
    return _utc_datetime(value)
