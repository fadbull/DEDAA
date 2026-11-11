import json
import unittest

# [P25] compute_event_analytics tests were removed together with the
# Event-Driven Analytics section; the cross-linkage module stays (OLAP cube).
from lib.compute_crosslink import compute_cross_linkage
from lib.compute_profile import compute_jira_profile
from lib.sync_jira import sync_jira


def issue(key, **values):
    return {
        "issue_key": key, "type": "Story", "status": "Open",
        "created": "2025-01-01T00:00:00Z", **values,
    }


def history(*events):
    return "Status history:\n" + "\n".join(
        f"  {when}: {before} -> {after}" for when, before, after in events
    )


class ProfileRegressions(unittest.TestCase):
    def test_transition_and_same_issue_pingpong(self):
        issues = [issue("1"), issue("2")]
        docs = [
            history(("2025-01-01T01:00:00Z", "Open", "Doing"),
                    ("2025-01-01T02:00:00Z", "Doing", "Done")),
            history(("2025-01-01T01:00:00Z", "Done", "Doing"),
                    ("2025-01-01T03:00:00Z", "Doing", "Open")),
        ]
        result = compute_jira_profile(issues, docs)
        self.assertEqual(sum(map(sum, result["trans_matrix"])), 4)
        self.assertEqual(result["pingpong"], [])
        self.assertEqual(result["time_in_status_median"]["Doing__Story"], 0.06)

    def test_actual_return_and_resolution_component(self):
        doc = history(("2025-01-01T01:00:00Z", "Open", "Doing"),
                      ("2025-01-01T02:00:00Z", "Doing", "Open"))
        row = issue("1", components="first, second",
                    done_date="2025-01-04", resolutiondate="2025-01-06")
        result = compute_jira_profile([row], [doc])
        self.assertEqual(len(result["pingpong"]), 1)
        self.assertEqual(result["olap_rows"][0]["components"], ["first", "second"])
        self.assertEqual(result["olap_rows"][0]["life"], 5)

    def test_snapshot_and_discontinuous_history(self):
        row = issue("1", status="Done", status_history_complete=True,
                    jira_snapshot_at="2025-01-01T04:00:00Z")
        doc = history(("2025-01-01T01:00:00Z", "Open", "Doing"),
                      ("2025-01-01T02:00:00Z", "Review", "Done"))
        raw = compute_jira_profile([row], [doc])["time_in_status_raw"]
        self.assertEqual([(r["status"], round(r["days"] * 24)) for r in raw],
                         [("Open", 1), ("Done", 2)])

    def test_offsets_and_cofill_all_issue_denominator(self):
        rows = [issue("1", components="A", labels="x"), issue("2", components="A"),
                issue("3", labels="x"), issue("4")]
        doc = history(("2025-01-01T04:00:00+02:00", "Open", "Doing"),
                      ("2025-01-01T03:00:00Z", "Doing", "Done"))
        result = compute_jira_profile(rows, [doc, "", "", ""])
        self.assertEqual(result["field_corr"]["components|labels"], 25)
        self.assertEqual(round(result["time_in_status_raw"][0]["days"] * 24), 1)

    def test_backlog_uses_snapshot_and_last_entry(self):
        complete = {"status_history_complete": True,
                    "jira_snapshot_at": "2025-12-01T00:00:00Z"}
        rows = [issue("1", **complete), issue("2", **complete), issue("3")]
        docs = ["", history(("2025-11-01T00:00:00Z", "Doing", "Open")), ""]
        result = compute_jira_profile(rows, docs)["backlog_stagnation"]
        self.assertEqual((result["total"], result["unknown"]), (1, 1))
        self.assertIsNone(compute_jira_profile([issue("3")], [""])["backlog_stagnation"]["total"])

    def test_escaped_defect_uses_distinct_issues_and_deduplicates(self):
        outward = {"type": "Causes", "direction": "outward", "outward": "causes",
                   "target_key": "bug"}
        inward = {"type": "Causes", "direction": "inward", "inward": "is caused by",
                  "target_key": "story"}
        rows = [issue("story", resolutiondate="2025-01-02T00:00:00Z",
                      issuelinks=json.dumps([outward])),
                issue("bug", type="Bug", created="2025-01-03T00:00:00Z",
                      issuelinks=json.dumps([inward]))]
        result = compute_cross_linkage(rows, ["", ""])["category_b"]
        self.assertEqual((result["escaped_causes"], result["eligible_pairs"]), (1, 1))

    def test_crosslink_same_month_and_no_false_duplicate(self):
        link = json.dumps([{"type": "relates to", "direction": "outward",
                            "target_key": "b"}])
        rows = [issue("a", issuelinks=link, done_date="2025-01-31"),
                issue("b", done_date="2025-02-01"),
                issue("c", status="Done", resolution="Won't Fix")]
        result = compute_cross_linkage(rows, ["", "", ""])
        self.assertEqual(result["category_d"]["in_same_month"], 0)
        self.assertEqual(result["category_d"]["spread"], 1)
        self.assertEqual(result["category_c"]["closed_duplicates"], 0)

    def test_sync_marks_only_proven_complete_history(self):
        class Api:
            def get(self, url, params):
                return {"total": 2, "issues": [
                    {"key": "A", "fields": {"subtasks": [{"key": "C"}]},
                     "changelog": {"startAt": 0, "total": 0, "histories": []}},
                    {"key": "B", "fields": {}, "changelog": {"total": 2, "histories": []}},
                ]}
        docs = sync_jira(Api(), "P", "project=P", {}, "https://jira.invalid", 90)
        self.assertTrue(docs[0]["metadata"]["status_history_complete"])
        self.assertEqual(docs[0]["metadata"]["subtask_keys_json"], '["C"]')
        self.assertFalse(docs[1]["metadata"]["status_history_complete"])


if __name__ == "__main__":
    unittest.main()
