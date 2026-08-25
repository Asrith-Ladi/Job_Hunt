import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from job_hunt.jobs.models import JobRecord, PipelineResult, RunSummary

from job_hunt.gmail.service import (
    GmailRunOptions,
    GmailWorkflowService,
    build_gmail_query,
)
from job_hunt.gmail.workbook import read_gmail_run_workbook, write_gmail_run_workbook
from job_hunt.integrations.sheets import JOB_COLUMNS
from job_hunt.runtime.state import load_local_state, save_local_state
from job_hunt.runtime.files import read_json
from job_hunt.runtime.google import GoogleConnectionService
from job_hunt.runtime.paths import AppPaths


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
    def test_search_reads_current_alerts_without_writing_workbooks_or_seen_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = AppPaths.from_project_root(Path(temporary))
            workflow = GmailWorkflowService(paths, _ConnectionStub())
            job = JobRecord(
                job_record_id="job-1",
                alert_source="linkedin",
                gmail_message_id="message-1",
                email_subject="ML role",
                email_received_at="2026-08-20T10:00:00+00:00",
                company="Example",
                title="Machine Learning Engineer",
                location="Hyderabad",
                experience_text="5-8 years",
                alert_posted_at=None,
                source_url="https://linkedin.example/jobs/1",
                official_url=None,
                first_seen_at="2026-08-20T10:00:00+00:00",
                last_seen_at="2026-08-20T10:00:00+00:00",
                parse_confidence="high",
                parse_status="parsed",
            )
            summary = RunSummary(
                run_id="run_search",
                started_at="2026-08-20T10:00:00+00:00",
                finished_at="2026-08-20T10:00:01+00:00",
                status="completed",
                messages_read=1,
                messages_supported=1,
                jobs_parsed=1,
                jobs_after_deduplication=1,
                jobs_filtered_out=0,
                rows_inserted=0,
                rows_updated=0,
                parsing_warnings=0,
                dry_run=True,
            )
            with (
                patch(
                    "job_hunt.gmail.service.GoogleGmailReader.from_credentials",
                    return_value=object(),
                ),
                patch(
                    "job_hunt.gmail.service.run_pipeline",
                    return_value=PipelineResult(summary=summary, jobs=[job]),
                ),
                patch(
                    "job_hunt.gmail.service.enrich_gmail_referrals",
                    side_effect=lambda rows, _path: (rows, {"referral_jobs_with_matches": 0}),
                ),
            ):
                result = workflow.search(GmailRunOptions(sources=("linkedin",)))

            self.assertTrue(result["transient"])
            self.assertEqual(result["file_name"], "")
            self.assertEqual(result["drive_url"], "")
            self.assertEqual(result["rows"][0]["job_record_id"], "job-1")
            self.assertEqual(result["summary"]["persistence"], "temporary_search")
            self.assertFalse(paths.run_output_root.exists())
            self.assertFalse(paths.gmail_seen_state_path.exists())

    def test_artifact_exposes_ranked_referrals_separately_from_workbook_rows(self):
        row = _job_row()
        row["referral_candidates"] = [
            {
                "name": "Asha Example",
                "position": "ML Lead",
                "profile_url": "https://www.linkedin.com/in/asha-example",
                "message": "Hi Asha, could you please refer me?",
                "email_address": "must-not-leave-the-server@example.com",
            }
        ]

        artifact = GmailWorkflowService._artifact_payload(
            {"run_id": "run_example", "local_path": "gmail.xlsx"},
            [row],
            {"run_id": "run_example"},
        )

        self.assertNotIn("referral_candidates", artifact["rows"][0])
        self.assertEqual(
            artifact["referral_candidates"]["job-1"][0]["name"],
            "Asha Example",
        )
        self.assertNotIn("email_address", artifact["referral_candidates"]["job-1"][0])

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
            workbook_path = (
                paths.run_output_root
                / "2026-08-01"
                / "gmail_alerts_2026-08-01_100000.xlsx"
            )
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

    def test_history_lists_and_loads_prior_runs_without_reprocessing_gmail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = AppPaths.from_project_root(root)
            workflow = GmailWorkflowService(paths, _ConnectionStub())
            from datetime import datetime

            first_path = (
                paths.run_output_root
                / "2026-08-17"
                / "gmail_alerts_2026-08-17_112358.xlsx"
            )
            second_path = (
                paths.run_output_root
                / "2026-08-17"
                / "gmail_alerts_2026-08-17_135250.xlsx"
            )
            write_gmail_run_workbook(
                first_path,
                [_job_row("job-old")],
                {
                    "run_id": "run_old",
                    "messages_read": 64,
                    "jobs_after_deduplication": 319,
                    "jobs_unchanged_from_prior_runs": 48,
                    "jobs_exported_this_run": 1,
                    "status": "completed",
                },
                run_started_at=datetime(2026, 8, 17, 11, 23, 58),
            )
            write_gmail_run_workbook(
                second_path,
                [],
                {
                    "run_id": "run_current",
                    "messages_read": 64,
                    "jobs_after_deduplication": 314,
                    "jobs_unchanged_from_prior_runs": 312,
                    "jobs_exported_this_run": 0,
                    "status": "completed",
                },
                run_started_at=datetime(2026, 8, 17, 13, 52, 50),
            )
            save_local_state(
                paths.app_state_path,
                {
                    "last_gmail_run": {
                        "run_id": "run_current",
                        "local_path": str(second_path),
                        "run_started_at": "2026-08-17T13:52:50+05:30",
                        "drive_url": "https://drive.example/current",
                    }
                },
            )

            history = workflow.history()
            self.assertEqual(
                [record["run_id"] for record in history],
                ["run_current", "run_old"],
            )
            self.assertEqual(history[0]["rows_exported"], 0)
            self.assertEqual(history[1]["rows_exported"], 1)
            self.assertEqual(history[1]["unchanged_jobs"], 48)
            historical = workflow.get("run_old")
            self.assertTrue(historical["historical"])
            self.assertFalse(historical["review_only"])
            self.assertEqual(historical["rows"][0]["job_record_id"], "job-old")
            self.assertEqual(workflow.workbook_path("run_old"), first_path.resolve())
            historical["rows"][0]["application_status"] = "applied"
            historical["rows"][0]["notes"] = "Application submitted manually."
            historical["rows"][0]["company"] = "Protected field change"

            def upload_result(_drive, local_path, **_kwargs):
                if Path(local_path).name == "gmail_seen_state.json":
                    return {"id": "seen-state-file"}
                return {
                    "id": "historical-workbook-file",
                    "webViewLink": "https://drive.example/historical",
                }

            folders = {
                "root": {"id": "root-folder"},
                "source": {"id": "source-folder"},
                "date": {"id": "date-folder"},
            }
            seen_state = {
                "version": 2,
                "last_successful_run_at": "2026-08-17T13:52:50+05:30",
                "job_fingerprints": {"job-old": "fingerprint"},
                "run_history": [],
            }
            with (
                patch("job_hunt.gmail.service.build_drive_service", return_value=object()),
                patch("job_hunt.gmail.service.ensure_job_hunt_folders", return_value=folders),
                patch("job_hunt.gmail.service.upload_or_update_file", side_effect=upload_result),
                patch.object(
                    workflow,
                    "_load_seen_state_from_drive",
                    return_value=(seen_state, ""),
                ),
            ):
                saved = workflow.save("run_old", historical["rows"])

            self.assertTrue(saved["historical"])
            self.assertFalse(saved["review_only"])
            self.assertEqual(saved["rows"][0]["application_status"], "applied")
            self.assertEqual(saved["rows"][0]["notes"], "Application submitted manually.")
            self.assertEqual(saved["rows"][0]["company"], "Example")
            workbook_rows, _ = read_gmail_run_workbook(first_path)
            self.assertEqual(workbook_rows[0]["application_status"], "applied")
            self.assertEqual(workbook_rows[0]["company"], "Example")
            persisted_seen = read_json(paths.gmail_seen_state_path)
            self.assertEqual(persisted_seen["job_fingerprints"], {"job-old": "fingerprint"})
            self.assertEqual(
                persisted_seen["run_history"][0]["drive_file_id"],
                "historical-workbook-file",
            )
            self.assertEqual(
                load_local_state(paths.app_state_path)["last_gmail_run"]["run_id"],
                "run_current",
            )

    def test_google_status_does_not_expose_tokens_or_credentials_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = AppPaths.from_project_root(Path(temporary))
            service = GoogleConnectionService(paths)
            with patch(
                "job_hunt.runtime.google.load_stored_credentials",
                return_value=object(),
            ):
                status = service.status()
            self.assertTrue(status["connected"])
            self.assertNotIn("token", status)
            self.assertNotIn("credentials_path", status)


if __name__ == "__main__":
    unittest.main()
