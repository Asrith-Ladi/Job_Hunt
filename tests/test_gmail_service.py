import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from job_hunt.gmail_service import (
    AppPaths,
    GmailRunOptions,
    GmailWorkflowService,
    GoogleConnectionService,
    build_gmail_query,
)
from job_hunt.gmail_workbook import write_gmail_run_workbook
from job_hunt.integrations.sheets import JOB_COLUMNS
from job_hunt.local_state import save_local_state


class _ConnectionStub:
    def require_credentials(self):
        return object()


def _job_row(record_id="job-1"):
    row = {column: "" for column in JOB_COLUMNS}
    row.update(
        {
            "job_record_id": record_id,
            "owner_id": "personal",
            "alert_source": "linkedin",
            "company": "Example",
            "title": "Machine Learning Engineer",
            "source_url": "https://example.com/jobs/1",
            "application_status": "not_started",
            "experience_fit": "inside_target",
        }
    )
    return row


class GmailServiceTests(unittest.TestCase):
    def test_query_generation_uses_selected_labels_and_lookback(self):
        query = build_gmail_query(
            ["linkedin", "naukri"],
            {"linkedin": "Job_Alerts/LinkedIn", "naukri": "Job_Alerts/Naukari"},
            30,
        )
        self.assertEqual(
            query,
            "{label:Job_Alerts/LinkedIn label:Job_Alerts/Naukari} newer_than:30d",
        )

    def test_options_allow_an_explicit_query_override(self):
        options = GmailRunOptions(
            gmail_query="label:Job_Alerts/link_test newer_than:2d",
            lookback_days=30,
        )
        self.assertEqual(
            options.resolved_query(),
            "label:Job_Alerts/link_test newer_than:2d",
        )

    def test_latest_loads_only_workbooks_below_the_run_output_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = AppPaths.from_project_root(root)
            workflow = GmailWorkflowService(paths, _ConnectionStub())
            workbook_path = paths.run_output_root / "2026-08-01" / "gmail.xlsx"
            summary = {"run_id": "run_example", "messages_read": 1}
            from datetime import datetime

            write_gmail_run_workbook(
                workbook_path,
                [_job_row()],
                summary,
                run_started_at=datetime(2026, 8, 1, 10, 0, 0),
            )
            save_local_state(
                paths.app_state_path,
                {
                    "last_gmail_run": {
                        "run_id": "run_example",
                        "local_path": str(workbook_path),
                        "run_started_at": "2026-08-01T10:00:00+05:30",
                        "drive_url": "https://drive.google.com/file/d/example/view",
                    }
                },
            )

            artifact = workflow.latest()
            self.assertEqual(artifact["run_id"], "run_example")
            self.assertEqual(len(artifact["rows"]), 1)
            self.assertNotIn("local_path", artifact)
            self.assertIn("referral_message", artifact["job_columns"])
            self.assertEqual(
                artifact["rows"][0]["referral_match_status"],
                "connections_unavailable",
            )

            save_local_state(
                paths.app_state_path,
                {"last_gmail_run": {"local_path": str(root / "outside.xlsx")}},
            )
            self.assertIsNone(workflow.latest())

    def test_google_status_does_not_expose_tokens_or_credentials_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = AppPaths.from_project_root(Path(temporary))
            service = GoogleConnectionService(paths)
            with patch(
                "job_hunt.gmail_service.load_stored_credentials",
                return_value=object(),
            ):
                status = service.status()
            self.assertTrue(status["connected"])
            self.assertNotIn("token", status)
            self.assertNotIn("credentials_path", status)


if __name__ == "__main__":
    unittest.main()
