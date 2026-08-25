import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from job_hunt.intelligence.usage import AIUsageLedger, response_usage_event


class _Usage:
    input_tokens = 10_000
    output_tokens = 2_000
    total_tokens = 12_000
    input_tokens_details = {
        "cached_tokens": 2_000,
        "cache_write_tokens": 1_000,
    }
    output_tokens_details = {"reasoning_tokens": 500}


class _Response:
    usage = _Usage()
    output = [
        {"type": "message", "id": "message-1"},
        {"type": "web_search_call", "id": "search-1"},
        {"type": "web_search_call", "id": "search-1"},
    ]


class AIUsageTests(unittest.TestCase):
    def test_response_usage_event_calculates_luna_tokens_cache_and_search(self):
        event = response_usage_event(
            _Response(),
            operation="official_job_research",
            model="gpt-5.6-luna",
            context={
                "job_record_id": "job-1",
                "company": "Example",
                "title": "ML Engineer",
                "private_prompt": "must not be retained",
            },
            recorded_at=datetime(
                2026,
                8,
                17,
                12,
                0,
                tzinfo=ZoneInfo("Asia/Kolkata"),
            ),
        )

        self.assertEqual(event["cached_input_tokens"], 2_000)
        self.assertEqual(event["cache_write_tokens"], 1_000)
        self.assertEqual(event["uncached_input_tokens"], 7_000)
        self.assertEqual(event["reasoning_tokens"], 500)
        self.assertEqual(event["web_search_calls"], 1)
        self.assertAlmostEqual(event["token_cost_usd"], 0.00409, places=8)
        self.assertAlmostEqual(event["calculated_cost_usd"], 0.01409, places=8)
        self.assertNotIn("private_prompt", event)

    def test_ledger_reports_action_period_totals_and_rolling_estimates(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = AIUsageLedger(Path(temporary) / "ai_usage.json")
            event = ledger.record_response(
                _Response(),
                operation="official_job_research",
                model="gpt-5.6-luna",
                context={"job_record_id": "job-1", "company": "Example"},
            )
            report = ledger.report()
            action = ledger.action_summary(
                [event],
                cache_reused=False,
                expected_api_calls=1,
            )
            cached = ledger.action_summary(
                [],
                cache_reused=True,
                expected_api_calls=0,
            )

            self.assertEqual(report["all_time"]["api_calls"], 1)
            self.assertEqual(report["today"]["web_search_calls"], 1)
            self.assertEqual(report["estimates"]["official_job"]["source"], "recent_average")
            self.assertEqual(report["storage"]["drive_path"], "Job Hunt/Source/ai_usage.json")
            self.assertTrue(action["tracking_complete"])
            self.assertAlmostEqual(action["calculated_cost_usd"], 0.01409, places=8)
            self.assertEqual(cached["calculated_cost_usd"], 0)
            self.assertTrue(cached["tracking_complete"])

    def test_unknown_model_is_marked_unpriced_instead_of_free(self):
        event = response_usage_event(
            _Response(),
            operation="resume_plan",
            model="unknown-model",
        )

        self.assertIsNone(event["calculated_cost_usd"])
        self.assertFalse(event["pricing_supported"])


if __name__ == "__main__":
    unittest.main()
