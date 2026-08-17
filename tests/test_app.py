import unittest
from datetime import datetime
import tempfile
from pathlib import Path

from job_hunt.gmail_service import (
    AppPaths,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_SOURCE_LABELS,
    GmailWorkflowService,
    build_gmail_query,
)


class AppQueryTests(unittest.TestCase):
    def test_production_defaults_use_rolling_thirty_day_labels(self):
        self.assertEqual(DEFAULT_LOOKBACK_DAYS, 30)
        self.assertEqual(
            build_gmail_query(
                ["linkedin", "naukri"],
                DEFAULT_SOURCE_LABELS,
                DEFAULT_LOOKBACK_DAYS,
            ),
            (
                "{label:Job_Alerts/LinkedIn label:Job_Alerts/Naukari} "
                "newer_than:30d"
            ),
        )

    def test_two_source_labels_use_gmail_or_group(self):
        query = build_gmail_query(
            ["linkedin", "naukri"],
            {
                "linkedin": "Job_Alerts/link_test",
                "naukri": "Job_Alerts/nau_test",
            },
            15,
        )
        self.assertEqual(
            query,
            "{label:Job_Alerts/link_test label:Job_Alerts/nau_test} newer_than:15d",
        )

    def test_single_source_uses_only_its_label(self):
        query = build_gmail_query(
            ["linkedin"],
            {
                "linkedin": "Job_Alerts/link_test",
                "naukri": "Job_Alerts/nau_test",
            },
            7,
        )
        self.assertEqual(query, "label:Job_Alerts/link_test newer_than:7d")

    def test_react_workspace_tabs_and_dated_run_path_are_stable(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = GmailWorkflowService(
                AppPaths.from_project_root(Path(temporary)),
                google_connection=None,
            )
            defaults = service.defaults()
            path = service._run_workbook_path(datetime(2026, 8, 1, 14, 30, 5))
        self.assertEqual(
            defaults["source_tabs"],
            ["run_setup", "job_queue", "network_reviews"],
        )
        self.assertEqual(path.parent.name, "2026-08-01")
        self.assertEqual(path.name, "gmail_alerts_2026-08-01_143005.xlsx")


if __name__ == "__main__":
    unittest.main()
