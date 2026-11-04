import unittest

from lib.compute_jira import compute_jira


def issue(key, labels):
    return {
        "issue_key": key,
        "type": "Bug",
        "status": "Open",
        "labels": labels,
        "created": "2025-01-01",
    }


class ProductionLabelTests(unittest.TestCase):
    def test_default_rejects_non_production_words(self):
        for label in ("product", "non-prod", "preprod"):
            with self.subTest(label=label):
                result = compute_jira([issue("SYN-1", label)], [""])
                self.assertEqual(result["pm_incident_items"], [])
                self.assertEqual(result["pm_leakage_items"], [])

    def test_default_accepts_production_tokens(self):
        for label in ("prod", "production", "prod_bug", "PROD"):
            with self.subTest(label=label):
                result = compute_jira([issue("SYN-1", label)], [""])
                self.assertEqual(len(result["pm_incident_items"]), 1)
                self.assertEqual(
                    [item["leaked"] for item in result["pm_leakage_items"]], [0, 1]
                )

    def test_unrelated_label_does_not_hide_real_production_label(self):
        issues = [issue("SYN-1", "product"), issue("SYN-2", "prod_bug")]
        result = compute_jira(issues, ["", ""])
        self.assertEqual([item["key"] for item in result["pm_incident_items"]], ["SYN-2"])
        self.assertEqual(
            [item["key"] for item in result["pm_leakage_items"] if item["leaked"]],
            ["SYN-2"],
        )

    def test_default_matches_multiple_production_label_variants(self):
        issues = [
            issue("SYN-1", "prod_bug"),
            issue("SYN-2", "production"),
            issue("SYN-3", "prod"),
        ]
        result = compute_jira(issues, ["", "", ""])
        self.assertEqual(
            [item["key"] for item in result["pm_incident_items"]],
            ["SYN-1", "SYN-2", "SYN-3"],
        )

    def test_explicit_custom_production_label_is_preserved(self):
        result = compute_jira(
            [issue("SYN-1", "product")], [""], {"prodLabel": "product"}
        )
        self.assertEqual(len(result["pm_incident_items"]), 1)
        self.assertEqual(
            [item["leaked"] for item in result["pm_leakage_items"]], [0, 1]
        )


if __name__ == "__main__":
    unittest.main()
