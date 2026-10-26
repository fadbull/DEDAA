"""HTML/JS rendering helpers for the dashboard."""
import os
from datetime import datetime

def esc(s):
    amp = chr(38) + "amp;"
    lt = chr(38) + "lt;"
    gt = chr(38) + "gt;"
    quot = chr(38) + "quot;"
    return (str(s).replace(chr(38), amp).replace(chr(60), lt)
            .replace(chr(62), gt).replace(chr(34), quot))


def js_list(items):
    return "[" + ",".join(json_str(i) for i in items) + "]"


def json_str(v):
    if v is None:
        return "null"
    s = str(v).replace("\\", "\\\\").replace('"', '\\"')
    return '"' + s + '"'


def _tip(text, align="left"):
    """Return an info-icon span with a CSS hover tooltip explaining a widget.

    `text` is the tooltip body (may contain simple HTML). `align` controls the
    tooltip horizontal alignment ('left'|'right') to avoid clipping near the
    viewport edge. Pure CSS (no JS), so it works everywhere.
    """
    body = esc(text) if isinstance(text, str) else esc(str(text))
    return ("<span class='tip-wrap' data-align='" + align + "'>"
            "<span class='tip-icon' title=''>ⓘ</span>"
            "<span class='tip-box'>" + body + "</span></span>")


def _dir_size_mb(path):
    """Return the total size of a directory in MB (rounded to 2 decimals)."""
    import os
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return round(total / (1024 * 1024), 2)


def _read_sync_marker(db_path, collection):
    """Read the last-sync timestamp recorded by sync_agent for a collection
    (ISO-8601 UTC string), or None if not present."""
    import json as _json
    path = os.path.join(db_path, collection, "_sync_marker.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return (_json.load(fh) or {}).get("last_sync")
    except Exception:
        return None


def _fmt_ts(ts):
    """Format an ISO-8601 timestamp for display (UTC), or 'N/A'."""
    if not ts:
        return "N/A"
    try:
        from datetime import timezone
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return str(ts)


def _rework_health_html(rate):
    """Render the Requirements Rework Rate health badge: <10% healthy,
    10–20% watch, >20% requirements quality issue."""
    if rate is None:
        return "N/A"
    if rate < 10:
        return f"{rate:.1f}% · 🟢 Healthy (<10%)"
    if rate <= 20:
        return f"{rate:.1f}% · 🟠 Watch (10–20%)"
    return f"{rate:.1f}% · 🔴 Requirements quality issue (>20%)"

