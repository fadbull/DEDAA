"""Atlassian REST client (403 bypass) and shared value/text helpers.

Extracted 1:1 from the original monolithic sync_agent.py (Skill #1)."""
import json

import requests
from bs4 import BeautifulSoup

# Corporate-block bypass: send a browser-like User-Agent
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


class AtlassianAPI:
    """Minimal REST client for Jira/Confluence with a browser-like
    User-Agent so corporate 403 blocks are bypassed."""

    def __init__(self, url, username, token):
        if not url:
            raise ValueError("No URL provided (--url or .env).")
        if not token:
            raise ValueError("No token provided (--token or .env).")
        self.base = url.rstrip("/")
        self.session = requests.Session()
        self.session.auth = (username or "", token)
        self.session.headers.update(HEADERS)

    def get(self, path, params=None):
        r = self.session.get(self.base + path, params=params, timeout=60)
        r.raise_for_status()
        return r.json()

    def get_bytes(self, path, params=None):
        """Fetch a binary resource (image/attachment) and return the raw bytes."""
        r = self.session.get(self.base + path, params=params, timeout=60)
        r.raise_for_status()
        return r.content


def scalar(value):
    """Normalize any Jira/Confluence field value to a plain string."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        for k in ("name", "value", "displayName", "key"):
            if k in value and value[k] is not None:
                return str(value[k])
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return ", ".join(s for s in (scalar(v) for v in value) if s)
    return str(value)


def strip_html_to_text(html):
    """Convert an HTML fragment (Confluence storage format) to clean text."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    lines = [ln.strip() for ln in soup.get_text(separator="\n").splitlines()]
    return "\n".join(ln for ln in lines if ln)
