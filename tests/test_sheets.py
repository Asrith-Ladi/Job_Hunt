import unittest

from job_hunt.integrations.sheets import (
    GMAIL_ALERTS_SHEET,
    JOB_COLUMNS,
    hyperlink_formula,
    job_url_formula_updates,
    merge_existing_job_row,
    rich_text_link_runs,
    updated_range_start_row,
)


def _row(**values):
    return [values.get(column, "") for column in JOB_COLUMNS]


class SheetsMergeTests(unittest.TestCase):
    def test_sheet_schema_uses_user_facing_experience_name_and_provenance(self):
        self.assertEqual(GMAIL_ALERTS_SHEET, "Gmail_Alerts")
        self.assertIn("years_of_experience", JOB_COLUMNS)
        self.assertIn("experience_source", JOB_COLUMNS)
        self.assertNotIn("experience_text", JOB_COLUMNS)

    def test_rerun_preserves_review_fields_and_accumulates_evidence(self):
        existing = _row(
            job_record_id="job-1",
            owner_id="personal",
            gmail_message_id="message-1",
            email_subject="First alert",
            email_received_at="2026-07-18T00:00:00+00:00",
            company="Example",
            title="Data Engineer",
            first_seen_at="2026-07-18T01:00:00+00:00",
            last_seen_at="2026-07-18T01:00:00+00:00",
            parse_confidence="high",
            application_status="applied",
            notes="Follow up Tuesday",
            evidence_message_ids="message-1",
        )
        incoming = _row(
            job_record_id="job-1",
            owner_id="personal",
            gmail_message_id="message-2",
            email_subject="Later alert",
            email_received_at="2026-07-19T00:00:00+00:00",
            title="",
            first_seen_at="2026-07-19T01:00:00+00:00",
            last_seen_at="2026-07-19T01:00:00+00:00",
            parse_confidence="low",
            application_status="not_started",
            notes="",
            evidence_message_ids="message-2",
        )

        merged = dict(zip(JOB_COLUMNS, merge_existing_job_row(existing, incoming)))

        self.assertEqual(merged["gmail_message_id"], "message-1")
        self.assertEqual(merged["title"], "Data Engineer")
        self.assertEqual(merged["first_seen_at"], "2026-07-18T01:00:00+00:00")
        self.assertEqual(merged["last_seen_at"], "2026-07-19T01:00:00+00:00")
        self.assertEqual(merged["parse_confidence"], "high")
        self.assertEqual(merged["application_status"], "applied")
        self.assertEqual(merged["notes"], "Follow up Tuesday")
        self.assertEqual(merged["evidence_message_ids"], "message-1,message-2")

    def test_job_urls_are_written_as_clickable_visible_hyperlinks(self):
        row = _row(
            source_url="https://linkedin.com/jobs/view/123",
            official_url="https://careers.example.com/jobs/456",
        )

        updates = job_url_formula_updates(7, row)

        self.assertEqual(
            updates,
            [
                {
                    "range": "Gmail_Alerts!L7",
                    "values": [[
                        '=HYPERLINK("https://linkedin.com/jobs/view/123",'
                        '"https://linkedin.com/jobs/view/123")'
                    ]],
                },
                {
                    "range": "Gmail_Alerts!M7",
                    "values": [[
                        '=HYPERLINK("https://careers.example.com/jobs/456",'
                        '"https://careers.example.com/jobs/456")'
                    ]],
                },
            ],
        )

    def test_hyperlink_formula_rejects_non_web_values_and_escapes_quotes(self):
        self.assertIsNone(hyperlink_formula("not a URL"))
        self.assertEqual(
            hyperlink_formula('https://example.com/?q="role"'),
            '=HYPERLINK("https://example.com/?q=""role""",'
            '"https://example.com/?q=""role""")',
        )

    def test_hyperlink_formula_can_show_a_person_name(self):
        self.assertEqual(
            hyperlink_formula(
                "https://linkedin.com/in/sandhya-example",
                'Sandhya "Example"',
            ),
            '=HYPERLINK("https://linkedin.com/in/sandhya-example",'
            '"Sandhya ""Example""")',
        )

    def test_rich_text_runs_link_only_the_requested_substrings(self):
        text = "Hi 🙂 — Job posting: https://careers.example/jobs/1 Thanks"
        url = "https://careers.example/jobs/1"
        start = text.index(url)

        runs = rich_text_link_runs(text, [(start, start + len(url), url)])

        self.assertEqual(runs[0], {"startIndex": 0, "format": {}})
        self.assertEqual(
            runs[1]["startIndex"],
            len(text[:start].encode("utf-16-le")) // 2,
        )
        self.assertEqual(runs[1]["format"]["link"]["uri"], url)
        self.assertEqual(
            runs[2]["startIndex"],
            len(text[: start + len(url)].encode("utf-16-le")) // 2,
        )

    def test_rich_text_runs_reject_overlapping_links(self):
        with self.assertRaises(ValueError):
            rich_text_link_runs(
                "abcdefgh",
                [(1, 5, "https://one.example"), (4, 7, "https://two.example")],
            )

    def test_updated_range_start_row_parses_quoted_sheet_range(self):
        self.assertEqual(updated_range_start_row("'Gmail_Alerts'!A12:Y14"), 12)
        self.assertIsNone(updated_range_start_row(""))


if __name__ == "__main__":
    unittest.main()
