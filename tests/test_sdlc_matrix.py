import unittest

from lib.compute_profile import compute_jira_profile


def issue(typ, status):
    return {"type": typ, "status": status, "created": "2025-01-01T00:00:00Z"}


class SdlcMatrixTests(unittest.TestCase):
    def test_all_types_statuses_and_full_denominators(self):
        issues = [issue("Story", "In Review"), issue("Story", "Blocked"),
                  issue("Bug", "Ready for Demo"), issue("Support Request", "Closed"),
                  issue("Spike", ""), issue("", None)]
        result = compute_jira_profile(issues, [""] * len(issues))
        self.assertIn("Support Request", result["sdlc_types"])
        self.assertIn("Spike", result["sdlc_types"])
        self.assertIn("Unknown (missing)", result["sdlc_types"])
        self.assertIn("Unknown (missing)", result["sdlc_statuses"])
        self.assertEqual(result["sdlc_counts"]["Story"]["In Review"], 1)
        self.assertEqual(result["sdlc_matrix"]["Story"]["In Review"], 50)
        self.assertEqual(result["sdlc_matrix"]["Story"]["Blocked"], 50)
        self.assertEqual(result["sdlc_matrix"]["Bug"]["Ready for Demo"], 100)
        self.assertEqual(result["sdlc_totals"]["Story"], 2)
        self.assertEqual(sum(result["sdlc_totals"].values()), len(issues))
        self.assertEqual(result["sdlc_counts"]["Spike"]["Unknown (missing)"], 1)

    def test_distinct_labels_and_empty_data(self):
        issues = [issue("Story", "In Review"), issue("Story", "In Testing"),
                  issue("Story", " In Review ")]
        result = compute_jira_profile(issues, [""] * len(issues))
        self.assertEqual(result["sdlc_counts"]["Story"]["In Review"], 2)
        self.assertEqual(result["sdlc_counts"]["Story"]["In Testing"], 1)
        self.assertEqual(compute_jira_profile([], [])["sdlc_matrix"], {})

    def test_backlog_empty_zero_vs_unknown(self):
        complete = {"status_history_complete": True,
                    "jira_snapshot_at": "2025-02-01T00:00:00Z"}
        self.assertEqual(compute_jira_profile([issue("Story", "Closed")], [""])
                         ["backlog_stagnation"]["total"], 0)
        known = {**issue("Story", "Open"), **complete}
        unknown = issue("Story", "New")
        result = compute_jira_profile([known, unknown], ["", ""])["backlog_stagnation"]
        self.assertEqual((result["total"], result["unknown"]), (0, 1))

    def test_security_and_subbug_are_descriptive(self):
        issues = [issue("Security issue", "Closed"), issue("Story", "Open"),
                  issue("Sub-Bug", "Open")]
        result = compute_jira_profile(issues, [""] * len(issues))
        self.assertEqual(result["security_in_progress"]["pct"], 0)
        self.assertFalse(any(f["kind"] == "Isolated Security Loop"
                             for f in result["vsm_findings"]))
        self.assertNotIn("низкого качества", str(result["vsm_findings"]))
        self.assertIsNone(result["backlog_stagnation"]["total"])

    def test_subbug_threshold_uses_unrounded_ratio(self):
        for stories, subbugs, level in [(5, 0, "warning"), (5, 1, "warning"),
                                        (1000, 201, "success"), (5, 2, "success")]:
            with self.subTest(stories=stories, subbugs=subbugs):
                issues = [issue("Story", "Closed")] * stories + [issue("Sub-Bug", "Closed")] * subbugs
                result = compute_jira_profile(issues, [""] * len(issues))
                finding = next(f for f in result["vsm_findings"]
                               if f["kind"] == "Sub-Bug / Story ratio")
                self.assertEqual(finding["level"], level)
                self.assertEqual(finding["value"], subbugs / stories)


if __name__ == "__main__":
    unittest.main()
