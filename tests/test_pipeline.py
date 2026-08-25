import unittest

from job_hunt.gmail.config import RunConfig
from job_hunt.jobs.models import AlertMessage
from job_hunt.gmail.pipeline import run_pipeline


class FakeReader:
    def list_alerts(self, query, max_messages=500):
        return [
            AlertMessage(
                message_id="m1",
                thread_id="t1",
                sender="alerts@linkedin.com",
                subject="LinkedIn alert",
                received_at="2026-07-19T00:00:00+00:00",
                html_body=(
                    '<a href="https://linkedin.com/jobs/view/123?utm_source=email">'
                    "Data Engineer</a>"
                ),
            ),
            AlertMessage(
                message_id="m2",
                thread_id="t2",
                sender="alerts@linkedin.com",
                subject="LinkedIn alert again",
                received_at="2026-07-19T01:00:00+00:00",
                html_body='<a href="https://www.linkedin.com/jobs/view/123/">View job</a>',
            ),
        ]


class FakeStore:
    def __init__(self):
        self.spreadsheet_id = "sheet-123"
        self.jobs = []
        self.summary = None

    def upsert_jobs(self, jobs):
        self.jobs = list(jobs)
        return len(self.jobs), 0

    def append_run(self, summary):
        self.summary = summary


class OutsideExperienceReader:
    def list_alerts(self, query, max_messages=500):
        return [
            AlertMessage(
                message_id="m-outside",
                thread_id="t-outside",
                sender="alerts@naukri.com",
                subject="Naukri jobs",
                received_at="2026-07-19T00:00:00+00:00",
                html_body=(
                    '<a href="https://naukri.com/jd/job-listings-example-'
                    'hyderabad-9-to-12-years-123">Example Engineer</a>'
                ),
            )
        ]


class PipelineTests(unittest.TestCase):
    def test_dry_run_deduplicates_without_store(self):
        config = RunConfig(
            gmail_query=(
                "{label:Job_Alerts/link_test label:Job_Alerts/nau_test} "
                "newer_than:15d"
            ),
            owner_id="local-user",
            dry_run=True,
        )
        result = run_pipeline(
            config,
            FakeReader(),
            now="2026-07-19T02:00:00+00:00",
        )
        self.assertEqual(result.summary.messages_read, 2)
        self.assertEqual(result.summary.jobs_parsed, 2)
        self.assertEqual(result.summary.jobs_after_deduplication, 1)
        self.assertEqual(result.jobs[0].title, "Data Engineer")
        self.assertEqual(result.jobs[0].owner_id, "local-user")
        self.assertEqual(result.jobs[0].evidence_message_ids, ["m1", "m2"])

    def test_summary_keeps_deduplicated_count_separate_from_filter_count(self):
        config = RunConfig(
            gmail_query=(
                "{label:Job_Alerts/link_test label:Job_Alerts/nau_test} "
                "newer_than:15d"
            ),
            company_allowlist=["Example"],
            include_unmatched_companies=False,
            dry_run=True,
        )
        result = run_pipeline(
            config,
            FakeReader(),
            now="2026-07-19T02:00:00+00:00",
        )
        self.assertEqual(result.summary.jobs_after_deduplication, 1)
        self.assertEqual(result.summary.jobs_filtered_out, 1)
        self.assertEqual(result.jobs, [])

    def test_write_mode_passes_jobs_and_run_summary_to_store(self):
        store = FakeStore()
        result = run_pipeline(
            RunConfig(gmail_query="label:Job_Alerts/link_test", dry_run=False),
            FakeReader(),
            sheets_store=store,
            now="2026-07-19T02:00:00+00:00",
        )
        self.assertEqual(len(store.jobs), 1)
        self.assertIs(store.summary, result.summary)
        self.assertEqual(result.summary.rows_inserted, 1)
        self.assertEqual(result.summary.spreadsheet_id, "sheet-123")

    def test_strict_experience_filter_excludes_only_known_outside_roles(self):
        result = run_pipeline(
            RunConfig(
                gmail_query="label:Job_Alerts/nau_test",
                active_sources=["naukri"],
                experience_filter_mode="exclude_outside",
                dry_run=True,
            ),
            OutsideExperienceReader(),
            now="2026-07-19T02:00:00+00:00",
        )

        self.assertEqual(result.jobs, [])
        self.assertEqual(result.summary.jobs_after_deduplication, 1)
        self.assertEqual(result.summary.jobs_filtered_out, 1)


if __name__ == "__main__":
    unittest.main()
