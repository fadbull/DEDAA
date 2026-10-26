"""Autonomous artifact extraction from Confluence page text."""
import re

# ---------------------------------------------------------------------------
# Autonomous artifact extraction (no AI assumptions — pure text scanning)
# ---------------------------------------------------------------------------
# Artifact categories and the keywords used to detect them inside page text.
# Each category collects the exact lines/values found plus the source page URL.
ARTIFACT_RULES = {
    "metrics": {
        "label": "Metrics / Analytics tools",
        "keywords": ["amplitude", "google analytics", "amplitude, google",
                     "product metrics", "key metrics", "metrics register",
                     "bi reports", "product analytics"],
        "line_hint": "metric",
    },
    "success_criteria": {
        "label": "Success Criteria",
        "keywords": ["success criteria"],
        "section_start": "Success criteria",
        "section_end": "Competitive analysis",
    },
    "tools": {
        "label": "Tools / Integrations",
        "keywords": ["integration with", "link to app", "link to admin",
                     "link to product analytics", "jira space", "kb space",
                     "onehome", "hrms", "cpe", "opsbot", "relocator"],
        "line_hint": "link",
    },
    "stakeholders": {
        "label": "Stakeholders",
        "keywords": ["stakeholder", "sponsor", "product manager",
                     "delivery manager", "business analyst"],
        "line_hint": "manager",
    },
    "capabilities": {
        "label": "Capabilities",
        "keywords": ["capability", "integration"],
        "line_hint": "capability",
    },
    "links": {
        "label": "Links / References",
        "keywords": ["http", "https", "kb.epam.com", "jiraeu.epam.com",
                     "opportunities.epam.com", "relocator.epam.com"],
        "line_hint": "http",
    },
    "team": {
        "label": "Team / Contacts",
        "keywords": ["developer", "qa", "designer", "support coordinator",
                     "solution architect", "client representative"],
        "line_hint": "@epam.com",
    },
}


def _clean_line(line):
    return line.strip().lstrip("-*#").strip()


def compute_artifacts(docs_meta, docs):
    """Autonomously scan all Confluence pages and extract a structured list of
    'Found Artifacts' — metrics/tools, success criteria, capabilities,
    stakeholders, links and team contacts — each with the source page URL.
    Pure text scanning: no AI inference or gap assumptions."""
    import re
    artifacts = {cat: [] for cat in ARTIFACT_RULES}
    for m, doc in zip(docs_meta, docs):
        title = m.get("title", "")
        url = m.get("url", "")
        text = doc or ""
        for cat, rule in ARTIFACT_RULES.items():
            label = rule["label"]
            kws = rule["keywords"]
            low = text.lower()
            # Section-based extraction (e.g. success criteria block)
            if rule.get("section_start"):
                start = low.find(rule["section_start"].lower())
                if start >= 0:
                    s = start + len(rule["section_start"])
                    end = low.find(rule["section_end"].lower(), s)
                    block = text[s:end if end > 0 else s + 1200]
                    items = []
                    for ln in block.splitlines():
                        c = _clean_line(ln)
                        if len(c) > 8 and not c.lower().startswith(
                                ("specify", "identify", "make sure",
                                 "articulate", "provide", "in addition",
                                 "for new products", "internally")):
                            items.append(c[:300])
                    if items:
                        artifacts[cat].append({
                            "title": title, "url": url, "label": label,
                            "items": items[:15],
                        })
                continue
            # Line-based extraction: collect lines containing a keyword
            collected = []
            for ln in text.splitlines():
                c = _clean_line(ln)
                if len(c) < 3:
                    continue
                cl = c.lower()
                if any(k in cl for k in kws):
                    # skip template instruction lines
                    if cl.startswith(("identify and describe", "make sure",
                                      "articulate", "specify what",
                                      "provide a link", "don't put",
                                      "please review", "for products")):
                        continue
                    collected.append(c[:300])
            # Deduplicate preserving order
            seen = set()
            uniq = []
            for c in collected:
                key = c.lower()
                if key not in seen:
                    seen.add(key)
                    uniq.append(c)
            if uniq:
                artifacts[cat].append({
                    "title": title, "url": url, "label": label,
                    "items": uniq[:15],
                })
    return artifacts
