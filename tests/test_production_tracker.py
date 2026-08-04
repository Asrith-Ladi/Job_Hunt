import tempfile
import unittest
from pathlib import Path

from scripts.build_production_tracker import (
    CONTACT_TOOL_HEADERS,
    CONTACT_TOOL_SOURCES,
    _build_tracker_data,
    _contact_tool_payload,
    _sheet_payload,
)


class ProductionTrackerTests(unittest.TestCase):
    def _tracker_data(self, research):
        alert_payload = {
            "summary": {"messages_read": 1},
            "jobs": [
                {
                    "job_record_id": "alert-1",
                    "alert_source": "linkedin",
                    "company": "Example Company",
                    "title": "ML Engineer",
                    "location": "Hyderabad",
                    "source_url": "https://linkedin.com/jobs/view/1",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            connections = Path(temporary_directory) / "Connections.csv"
            connections.write_text(
                "Notes\nGenerated export\n\n"
                "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n",
                encoding="utf-8",
            )
            return _build_tracker_data(alert_payload, research, connections)

    def test_contact_tool_panel_has_named_links_and_guardrails(self):
        payload = _contact_tool_payload()

        self.assertEqual(payload[2], CONTACT_TOOL_HEADERS)
        self.assertEqual(len(payload[3:]), len(CONTACT_TOOL_SOURCES))
        self.assertTrue(all(str(row[0]).startswith("=HYPERLINK(") for row in payload[3:]))
        self.assertIn("do not upload", str(payload[1][1]).lower())
        self.assertEqual([row[2] for row in payload[3:]], list(range(1, 7)))

    def test_sheet_banner_starts_outside_the_frozen_first_column(self):
        payload = _sheet_payload("Title", "Summary", ["first", "second"], [])

        self.assertEqual(payload[0], ["", "Title"])
        self.assertEqual(payload[1], ["", "Summary"])
        self.assertEqual(payload[2], ["first", "second"])

    def test_unchecked_alert_is_pending_not_claimed_as_no_result(self):
        data = self._tracker_data({"verified_at": "2026-07-20", "postings": [], "matches": {}})

        self.assertEqual(data["stats"]["alerts_pending_research"], 1)
        self.assertEqual(data["stats"]["alerts_without_official_result"], 0)
        self.assertEqual(data["main"][0]["official_match_status"], "research_pending")

    def test_checked_alert_without_match_is_an_explicit_no_result(self):
        data = self._tracker_data(
            {
                "verified_at": "2026-07-20",
                "checked_alert_ids": ["alert-1"],
                "postings": [],
                "matches": {},
            }
        )

        self.assertEqual(data["stats"]["alerts_pending_research"], 0)
        self.assertEqual(data["stats"]["alerts_without_official_result"], 1)
        self.assertEqual(data["main"][0]["official_match_status"], "no_official_result")


if __name__ == "__main__":
    unittest.main()
