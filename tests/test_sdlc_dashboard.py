import re
import unittest
from html.parser import HTMLParser

from lib.compute_jira import compute_jira
from lib.compute_profile import compute_jira_profile
from lib.dashboard_html import build_dashboard


class DashboardSections(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.ids = {}
        self.links = []
        self.sections = []
        self.headings = []
        self.heading = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"img", "input", "br", "meta", "link", "hr"}:
            return
        if tag == "a" and attrs.get("href", "").startswith("#"):
            self.links.append(attrs["href"][1:])
        if "id" in attrs:
            self.ids.setdefault(attrs["id"], []).append(tuple(self.stack))
        if tag == "section":
            self.sections.append((attrs.get("id"), tuple(self.stack)))
        self.stack.append((tag, attrs.get("id")))
        if tag in {"h2", "h3"}:
            self.heading = [tag, tuple(self.stack), ""]

    def handle_endtag(self, tag):
        if self.heading and self.heading[0] == tag:
            self.headings.append(self.heading)
            self.heading = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.heading:
            self.heading[2] += data


class SdlcDashboardTests(unittest.TestCase):
    def test_sections_and_tooltips(self):
        issues = [
            {"issue_key": "A", "type": "Story", "status": "In Review",
             "created": "2025-01-01T00:00:00Z"},
            {"issue_key": "B", "type": "Security issue", "status": "Closed",
             "created": "2025-01-01T00:00:00Z"},
            {"issue_key": "C", "type": "Story", "status": "Open",
             "created": "2025-01-01T00:00:00Z"},
        ]
        docs = [""] * len(issues)
        html = build_dashboard(compute_jira(issues, docs), {}, ".",
                               jprofile=compute_jira_profile(issues, docs))
        tree = DashboardSections()
        tree.feed(html)
        tab2_sections = [name for name, ancestors in tree.sections
                         if ("div", "tab2") in ancestors]
        tab3_sections = [name for name, ancestors in tree.sections
                         if ("div", "tab3") in ancestors]
        self.assertEqual(tab2_sections[-1], "m-sdlc")
        self.assertNotIn("m-sdlc", tab3_sections)
        self.assertNotIn("d-sdlc", tree.ids)
        self.assertNotIn("d-heuristics", tree.ids)
        self.assertEqual(len(tree.ids["m-sdlc"]), 1)
        self.assertIn("m-sdlc", tree.links)
        headings = [text for _, _, text in tree.headings]
        self.assertIn("7. Event-Driven Analytics (under work)", headings)
        self.assertNotIn("Assignee → Component (Ownership)", html)
        self.assertNotIn("Reporter → Priority (Escalation)", html)
        self.assertIn("Value Stream Mapping Gaps (under work)", html)
        self.assertNotIn("Value Stream Mapping Gaps (heuristic risk flags)", html)
        self.assertNotIn("Backlog Stagnation — Open >180 days", html)
        self.assertIn("including missing statuses", html)
        self.assertIn("not evidence of neglect", html)
        self.assertIn("yellow at or below 0.2, green above 0.2", html)
        self.assertFalse(any(len(entries) > 1 for key, entries in tree.ids.items()
                             if key in {"m-sdlc", "d-events"}))
        self.assertEqual(len(re.findall(r'href="#m-sdlc"', html)), 1)

    def test_subbug_indicator_at_threshold_and_without_stories(self):
        for stories, subbugs, expected in [(5, 0, "⚠️"), (5, 1, "⚠️"),
                                            (1000, 201, "🟢"), (5, 2, "🟢"),
                                            (0, 1, None)]:
            with self.subTest(stories=stories, subbugs=subbugs):
                issues = ([{"type": "Story", "status": "Closed"}] * stories
                          + [{"type": "Sub-Bug", "status": "Closed"}] * subbugs)
                docs = [""] * len(issues)
                profile = compute_jira_profile(issues, docs)
                html = build_dashboard(compute_jira(issues, docs), {}, ".", jprofile=profile)
                section = html.split('<section id="m-sdlc"', 1)[1].split("</section>", 1)[0]
                self.assertNotIn("Backlog Stagnation — Open >180 days", section)
                if expected:
                    self.assertIn(f"{expected} Sub-Bug / Story ratio", section)
                    self.assertNotIn(("🟢" if expected == "⚠️" else "⚠️")
                                     + " Sub-Bug / Story ratio", section)
                else:
                    self.assertIn("Sub-Bug / Story ratio: N/A — no Story issues", section)
                    self.assertNotIn("⚠️ Sub-Bug / Story ratio", section)
                    self.assertNotIn("🟢 Sub-Bug / Story ratio", section)

    def test_backlog_observation_does_not_add_a_yellow_sign(self):
        issues = [
            {"type": "Story", "status": "Open", "created": "2024-01-01T00:00:00Z",
             "status_history_complete": True, "jira_snapshot_at": "2025-01-01T00:00:00Z"},
            {"type": "Sub-Bug", "status": "Closed"},
        ]
        docs = [""] * len(issues)
        html = build_dashboard(compute_jira(issues, docs), {}, ".",
                               jprofile=compute_jira_profile(issues, docs))
        section = html.split('<section id="m-sdlc"', 1)[1].split("</section>", 1)[0]
        self.assertIn("🟢 Sub-Bug / Story ratio", section)
        self.assertIn("Backlog Stagnation", section)
        self.assertNotIn("⚠️", section)


if __name__ == "__main__":
    unittest.main()
