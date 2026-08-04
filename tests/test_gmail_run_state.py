import unittest

from job_hunt.gmail_run_state import (
    select_new_or_changed_gmail_jobs,
    update_gmail_run_state,
)


def _job(record_id, title="ML Engineer"):
    return {
        "job_record_id": record_id,
        "alert_source": "linkedin",
        "company": "Example",
        "title": title,
        "location": "Hyderabad",
        "years_of_experience": "5-8 years",
        "source_url": "https://linkedin.com/jobs/view/{0}".format(record_id),
        "official_url": "",
        "parse_status": "parsed",
    }


class GmailRunStateTests(unittest.TestCase):
    def test_first_run_selects_all_and_second_run_skips_unchanged(self):
        jobs = [_job("1"), _job("2")]
        selected, unchanged = select_new_or_changed_gmail_jobs(jobs, None)
        self.assertEqual(len(selected), 2)
        self.assertEqual(unchanged, 0)

        state = update_gmail_run_state(None, jobs, completed_at="2026-08-01T10:00:00Z")
        selected, unchanged = select_new_or_changed_gmail_jobs(jobs, state)
        self.assertEqual(selected, [])
        self.assertEqual(unchanged, 2)

    def test_changed_job_is_selected_again(self):
        original = [_job("1")]
        state = update_gmail_run_state(None, original, completed_at="one")
        selected, unchanged = select_new_or_changed_gmail_jobs(
            [_job("1", title="Senior ML Engineer")],
            state,
        )
        self.assertEqual(len(selected), 1)
        self.assertEqual(unchanged, 0)


if __name__ == "__main__":
    unittest.main()
