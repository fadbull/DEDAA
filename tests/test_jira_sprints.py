import json
import unittest

from lib.compute_jira import compute_jira
from lib.jira_sprints import issue_sprints, normalize_sprints, sprint_catalog
from lib.metric_settings import merge_settings, validate_settings


def sprint(ident=1, **overrides):
    return dict(id=ident, name="Team sprint", state="closed",
                startDate="2025-01-01T10:00:00+02:00",
                endDate="2025-01-15T10:00:00+02:00",
                completeDate="2025-01-16T10:00:00+02:00",
                originBoardId=7, **overrides)


class SprintTests(unittest.TestCase):
    def test_structured_and_json_values(self):
        value = [sprint(), dict(id=2, name="Undated")]
        present, records = normalize_sprints(json.dumps(value))
        self.assertTrue(present)
        self.assertEqual([r["id"] for r in records], ["1", "2"])
        self.assertEqual(records[0]["start"], "2025-01-01T08:00:00+00:00")
        catalog = sprint_catalog(records)
        dated = next(s for s in catalog if s["id"] == "1")
        self.assertEqual(dated["finish"], "2025-01-16T08:00:00+00:00")
        self.assertTrue(dated["closed"])
        self.assertFalse(next(s for s in catalog if s["id"] == "2")["usable"])

    def test_legacy_objects_arbitrary_order_and_punctuation(self):
        text = (
            "Sprint: com.atlassian.greenhopper.service.sprint.Sprint@abc["
            "goal=Deliver [A], B,name=Team, phase [1],id=32,state=CLOSED,"
            "endDate=2025-01-15T10:00:00.000+0200,"
            "startDate=2025-01-01T10:00:00.000+0200,rapidViewId=7], "
            "com.atlassian.greenhopper.service.sprint.Sprint@def["
            "id=33,name=Next,state=FUTURE,startDate=<null>,endDate=<null>]"
        )
        populated, records = issue_sprints({}, text)
        self.assertTrue(populated)
        self.assertEqual([r["id"] for r in records], ["32", "33"])
        self.assertEqual(records[0]["name"], "Team, phase [1]")
        self.assertEqual(records[0]["board"], "7")
        self.assertEqual(records[0]["state"], "closed")

    def test_field_presence_is_independent_of_dates_or_ids(self):
        for value in ("Undated sprint", [{"id": 8}], ["Sprint without ID"]):
            self.assertTrue(normalize_sprints(value)[0])
        for value in (None, "", [], "null", [None, ""]):
            self.assertFalse(normalize_sprints(value)[0])

    def test_merge_and_conflict_are_explicit(self):
        records = normalize_sprints([sprint(), dict(id=1, name="Team sprint")])[1]
        self.assertTrue(sprint_catalog(records)[0]["usable"])
        changed = sprint()
        changed["startDate"] = "2025-01-02T10:00:00+02:00"
        with self.assertLogs("lib.jira_sprints", level="WARNING"):
            catalog = sprint_catalog(records + normalize_sprints(changed)[1])
        self.assertFalse(catalog[0]["usable"])

    def test_compute_transports_presence_membership_and_exact_timestamps(self):
        meta = [
            dict(issue_key="SYN-1", type="Story", status="Done",
                 created="2025-01-02T23:30:00-03:00",
                 resolutiondate="2025-01-15T08:30:00+00:00",
                 sprints_json=json.dumps([sprint()])),
            dict(issue_key="SYN-2", type="Story", status="Open"),
        ]
        result = compute_jira(meta, ["", ""])
        self.assertEqual(result["pm_sprint_coverage"], {"total": 2, "populated": 1})
        record = result["pm_raw_items"][0]
        self.assertEqual(record["sprint_ids"], ["1"])
        self.assertEqual(record["created_ts"], meta[0]["created"])
        self.assertEqual(record["resolved_ts"], meta[0]["resolutiondate"])
        self.assertEqual(len(result["pm_sprint_catalog"]), 1)

    def test_structured_empty_field_overrides_old_text(self):
        self.assertEqual(issue_sprints({"sprints_json": "[]"}, "Sprint: Old"), (False, []))

    def test_invalid_completion_falls_back_to_valid_end(self):
        value = sprint()
        value["completeDate"] = "2024-01-01T00:00:00Z"
        result = sprint_catalog(normalize_sprints(value)[1])[0]
        self.assertTrue(result["usable"])
        self.assertEqual(result["finish"], "2025-01-15T08:00:00+00:00")

    def test_sprint_settings_validate_without_changing_existing_values(self):
        for value in ("auto", "available", "none"):
            settings = merge_settings({"sprintData": value})
            self.assertEqual(settings["sprintData"], value)
            self.assertEqual(validate_settings(settings), [])
        with self.assertRaisesRegex(ValueError, "sprintData"):
            merge_settings({"sprintData": "invented"})


if __name__ == "__main__":
    unittest.main()
