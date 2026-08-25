import unittest

from job_hunt.jobs.dedupe import canonicalize_url, company_match, deduplicate
from job_hunt.jobs.models import JobRecord


def _job(record_id, url, message_id="m1", title=None):
    return JobRecord(
        job_record_id=record_id,
        alert_source="linkedin",
        gmail_message_id=message_id,
        email_subject="alert",
        email_received_at="2026-07-19T00:00:00+00:00",
        company=None,
        title=title,
        location=None,
        experience_text=None,
        alert_posted_at=None,
        source_url=url,
        official_url=None,
        first_seen_at="2026-07-19T00:00:00+00:00",
        last_seen_at="2026-07-19T00:00:00+00:00",
        parse_confidence="low",
        parse_status="partial_needs_fixture",
        evidence_message_ids=[message_id],
    )


class DedupeTests(unittest.TestCase):
    def test_direct_job_url_drops_all_query_values(self):
        value = canonicalize_url(
            "http://www.linkedin.com/jobs/view/123/?utm_source=email&currentJobId=123&trk=mail"
        )
        self.assertEqual(value, "https://linkedin.com/jobs/view/123")

    def test_generic_url_keeps_non_tracking_query_values(self):
        value = canonicalize_url("https://careers.example.com/jobs?id=123&utm_source=email")
        self.assertEqual(value, "https://careers.example.com/jobs?id=123")

    def test_regional_linkedin_host_normalizes_for_deduplication(self):
        value = canonicalize_url("https://in.linkedin.com/jobs/view/123?secret=tracking")
        self.assertEqual(value, "https://linkedin.com/jobs/view/123")

    def test_naukri_jd_link_drops_personal_tracking_query(self):
        value = canonicalize_url(
            "https://www.naukri.com/jd/opaque-job-token?uid=private&alertId=private"
        )
        self.assertEqual(value, "https://naukri.com/jd/opaque-job-token")

    def test_url_credentials_are_rejected(self):
        self.assertEqual(
            canonicalize_url("https://user:secret@linkedin.com/jobs/view/123"),
            "",
        )

    def test_same_canonical_url_merges_evidence_and_fields(self):
        first = _job("a", "https://linkedin.com/jobs/view/123?utm_source=email", "m1")
        second = _job("b", "https://www.linkedin.com/jobs/view/123/", "m2", "Data Engineer")
        merged = deduplicate([first, second])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].title, "Data Engineer")
        self.assertEqual(merged[0].evidence_message_ids, ["m1", "m2"])

    def test_dedupe_replaces_unknown_experience_provenance(self):
        first = _job("a", "https://linkedin.com/jobs/view/123", "m1")
        second = _job("b", "https://linkedin.com/jobs/view/123", "m2")
        second.experience_source = "alert_url"

        merged = deduplicate([first, second])

        self.assertEqual(merged[0].experience_source, "alert_url")

    def test_company_match_is_explicit_when_parsing_is_unknown(self):
        self.assertEqual(company_match(None, ["Example"]), "unknown")
        self.assertEqual(company_match("Example", ["example"]), "matched")
        self.assertEqual(company_match("Different", ["Example"]), "unmatched")


if __name__ == "__main__":
    unittest.main()
