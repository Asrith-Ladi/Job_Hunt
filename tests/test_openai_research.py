import json
import unittest

from job_hunt.integrations.openai_research import (
    OfficialJobResearcher,
    OpenAIResearchError,
    pending_research_jobs,
)


def _candidate(url, title="Senior Machine Learning Engineer"):
    return {
        "company": "Example Company",
        "title": title,
        "location": "Hyderabad",
        "experience_text": "5-8 years",
        "experience_min": 5,
        "experience_max": 8,
        "workplace_type": "hybrid",
        "employment_type": "full-time",
        "active_status": "active",
        "requisition_id": "REQ-123",
        "published_at": "2026-07-20",
        "official_url": url,
        "description_summary": "Build and operate production machine-learning systems.",
        "required_skills": ["Python", "Machine Learning"],
        "preferred_skills": ["AWS"],
        "evidence_confidence": "high",
        "source_notes": "Public employer ATS posting.",
        "match_status": "exact_candidate",
        "match_score": 95,
        "match_reason": "Company, title, and location match.",
    }


class _FakeResponse:
    def __init__(self, value):
        self.output_text = json.dumps(value)


class _FakeResponses:
    def __init__(self, value):
        self.value = value
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(self.value)


class _FakeClient:
    def __init__(self, value):
        self.responses = _FakeResponses(value)


class _SequenceResponses:
    def __init__(self, values):
        self.values = list(values)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return _FakeResponse(value)


class _SequenceClient:
    def __init__(self, values):
        self.responses = _SequenceResponses(values)


class OpenAIResearchTests(unittest.TestCase):
    def test_exact_posting_extraction_keeps_only_skills_with_exact_jd_evidence(self):
        client = _FakeClient(
            {
                "description_summary": "Build and operate production agents for customers.",
                "experience_evidence": "from 3+ years of experience",
                "required_skills": [
                    {"label": "AI agents", "evidence": "production agents"},
                    {"label": "Python", "evidence": "Strong Python"},
                    {"label": "MCP", "evidence": "MCP servers at scale"},
                ],
                "preferred_skills": [],
            }
        )
        researcher = OfficialJobResearcher("unused", client=client)

        posting = researcher.extract_exact_posting(
            {"company": "Sarvam AI"},
            {
                "board": "sarvam",
                "external_job_id": "36f89b00-2010-4d23-aae3-17a2f53d9eaa",
                "title": "Agent Engineer",
                "location": "Bengaluru",
                "official_url": (
                    "https://www.sarvam.ai/careers/jobs/"
                    "36f89b00-2010-4d23-aae3-17a2f53d9eaa"
                ),
                "description": (
                    "We hire from 3+ years of experience. Build production agents. "
                    "Strong Python and cloud infrastructure."
                ),
                "source_fingerprint": "fingerprint",
            },
        )

        self.assertEqual(posting["required_skills"], ["AI agents", "Python"])
        self.assertNotIn("MCP", posting["required_skill_evidence"])
        self.assertEqual(posting["experience_min"], 3)
        self.assertIsNone(posting["experience_max"])
        self.assertNotIn("tools", client.responses.calls[0])

    def test_exact_posting_extraction_emits_privacy_safe_usage_hook(self):
        client = _FakeClient(
            {
                "description_summary": "Build Python services.",
                "experience_evidence": "",
                "required_skills": [
                    {"label": "Python", "evidence": "Python services"}
                ],
                "preferred_skills": [],
            }
        )
        calls = []
        researcher = OfficialJobResearcher("unused", client=client)
        researcher.configure_usage_recording(
            lambda response, **metadata: calls.append((response, metadata)) or {},
            context={"job_record_id": "job-1", "company": "Example"},
        )

        researcher.extract_exact_posting(
            {"company": "Example"},
            {
                "board": "example",
                "external_job_id": "job-1",
                "title": "ML Engineer",
                "location": "Remote",
                "official_url": "https://careers.example.com/jobs/job-1",
                "description": "Build Python services.",
                "source_fingerprint": "fingerprint",
            },
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]["operation"], "exact_jd_extraction")
        self.assertEqual(calls[0][1]["context"]["job_record_id"], "job-1")

    def test_exact_only_research_rejects_a_related_job_url(self):
        selected_id = "36f89b00-2010-4d23-aae3-17a2f53d9eaa"
        related_id = "30259734-50c3-4f1c-81cd-8bff07e585e7"
        selected_url = f"https://careers.example.com/jobs/{selected_id}"
        related = _candidate(f"https://careers.example.com/jobs/{related_id}")
        related["match_status"] = "active_related"
        client = _FakeClient(
            {
                "results": [
                    {"alert_record_id": "alert-1", "candidates": [related]}
                ]
            }
        )

        research = OfficialJobResearcher("unused", client=client).research(
            [
                {
                    "job_record_id": "alert-1",
                    "company": "Example Company",
                    "title": "Agent Engineer",
                    "official_url": selected_url,
                }
            ],
            exact_only=True,
        )

        self.assertNotIn("alert-1", research["matches"])
        system_prompt = client.responses.calls[0]["input"][0]["content"]
        self.assertIn("Do not return a related", system_prompt)

    def test_research_sends_only_normalized_facts_and_rejects_social_urls(self):
        result_payload = {
            "results": [
                {
                    "alert_record_id": "alert-1",
                    "candidates": [
                        _candidate("https://jobs.example.com/req-123?utm_source=linkedin"),
                        _candidate("https://www.linkedin.com/jobs/view/123"),
                    ],
                }
            ]
        }
        client = _FakeClient(result_payload)
        researcher = OfficialJobResearcher("unused", client=client)
        jobs = [
            {
                "job_record_id": "alert-1",
                "company": "Example Company",
                "title": "Senior Machine Learning Engineer",
                "location": "Hyderabad",
                "experience_text": "5-8 years",
                "source_url": "https://linkedin.com/private-alert",
                "gmail_message_id": "secret-message-id",
                "email_subject": "private subject",
            }
        ]

        research = researcher.research(jobs)

        self.assertEqual(research["research_stats"]["api_calls"], 1)
        self.assertEqual(len(research["postings"]), 1)
        posting = research["postings"][0]
        self.assertEqual(posting["official_url"], "https://jobs.example.com/req-123")
        self.assertTrue(posting["official_job_id"].startswith("official_"))
        serialized_call = json.dumps(client.responses.calls[0])
        self.assertNotIn("private-alert", serialized_call)
        self.assertNotIn("secret-message-id", serialized_call)
        self.assertNotIn("private subject", serialized_call)

    def test_only_a_valid_official_url_is_sent_as_a_research_hint(self):
        client = _FakeClient({"results": [{"alert_record_id": "alert-1", "candidates": []}]})
        researcher = OfficialJobResearcher("unused", client=client)

        researcher.research(
            [
                {
                    "job_record_id": "alert-1",
                    "company": "Example Company",
                    "title": "ML Engineer",
                    "official_url": "https://careers.example.com/jobs/123?utm_source=alert",
                    "source_url": "https://www.linkedin.com/jobs/view/123",
                }
            ]
        )

        serialized_call = json.dumps(client.responses.calls[0])
        self.assertIn("https://careers.example.com/jobs/123", serialized_call)
        self.assertNotIn("utm_source", serialized_call)
        self.assertNotIn("linkedin.com/jobs", serialized_call)

    def test_checked_alert_is_reused_without_an_api_call(self):
        jobs = [
            {
                "job_record_id": "alert-1",
                "company": "Example Company",
                "title": "ML Engineer",
                "location": "Hyderabad",
            }
        ]
        first_client = _FakeClient({"results": []})
        first = OfficialJobResearcher("unused", client=first_client).research(jobs)
        client = _FakeClient({"results": []})
        researcher = OfficialJobResearcher("unused", client=client)

        research = researcher.research(jobs, first)

        self.assertEqual(client.responses.calls, [])
        self.assertEqual(research["verified_at"], first["verified_at"])
        self.assertEqual(research["research_stats"]["alerts_reused_from_cache"], 1)

    def test_legacy_checked_id_without_fingerprint_is_not_trusted(self):
        client = _FakeClient({"results": []})
        researcher = OfficialJobResearcher("unused", client=client)
        jobs = [
            {
                "job_record_id": "alert-1",
                "company": "Example Company",
                "title": "ML Engineer",
                "location": "Hyderabad",
            }
        ]
        existing = {
            "verified_at": "2026-07-19",
            "checked_alert_ids": ["alert-1"],
            "postings": [],
            "matches": {},
        }

        research = researcher.research(jobs, existing)

        self.assertEqual(len(client.responses.calls), 1)
        self.assertIn("alert-1", research["checked_alert_fingerprints"])

    def test_changed_alert_facts_invalidate_a_cached_check(self):
        original_jobs = [
            {
                "job_record_id": "alert-1",
                "company": "Example Company",
                "title": "ML Engineer",
                "location": "Hyderabad",
            }
        ]
        first = OfficialJobResearcher("unused", client=_FakeClient({"results": []})).research(
            original_jobs
        )
        changed_jobs = [{**original_jobs[0], "title": "Senior ML Engineer"}]
        client = _FakeClient({"results": []})

        OfficialJobResearcher("unused", client=client).research(changed_jobs, first)

        self.assertEqual(len(client.responses.calls), 1)

    def test_same_company_alerts_are_batched_together(self):
        client = _FakeClient(
            {
                "results": [
                    {"alert_record_id": "alert-1", "candidates": []},
                    {"alert_record_id": "alert-2", "candidates": []},
                ]
            }
        )
        researcher = OfficialJobResearcher("unused", client=client)
        jobs = [
            {
                "job_record_id": "alert-1",
                "company": "Example Company",
                "title": "ML Engineer",
            },
            {
                "job_record_id": "alert-2",
                "company": "Example Company",
                "title": "AI Engineer",
            },
        ]

        research = researcher.research(jobs)

        self.assertEqual(len(client.responses.calls), 1)
        self.assertEqual(research["checked_alert_ids"], ["alert-1", "alert-2"])

    def test_pending_jobs_excludes_matching_fingerprints(self):
        jobs = [
            {
                "job_record_id": "alert-1",
                "company": "Example Company",
                "title": "ML Engineer",
            },
            {
                "job_record_id": "alert-2",
                "company": "Another Company",
                "title": "AI Engineer",
            },
        ]
        cached = OfficialJobResearcher(
            "unused", client=_FakeClient({"results": []})
        ).research(jobs[:1])

        pending = pending_research_jobs(jobs, cached)

        self.assertEqual(
            [item["job_record_id"] for item in pending],
            ["alert-2"],
        )

    def test_full_backlog_is_checkpointed_and_completed(self):
        jobs = [
            {
                "job_record_id": f"alert-{index}",
                "company": f"Company {index}",
                "title": "ML Engineer",
            }
            for index in range(1, 6)
        ]
        client = _FakeClient({"results": []})
        checkpoints = []
        progress = []
        researcher = OfficialJobResearcher("unused", client=client)

        research = researcher.research_in_batches(
            jobs,
            batch_size=2,
            checkpoint=lambda value, completed, total: checkpoints.append(
                (completed, total, dict(value["research_stats"]))
            ),
            progress=lambda *values: progress.append(values),
        )

        self.assertEqual(len(client.responses.calls), 5)
        self.assertEqual([(item[0], item[1]) for item in checkpoints], [(1, 3), (2, 3), (3, 3)])
        self.assertEqual(research["research_stats"]["alerts_processed_this_run"], 5)
        self.assertEqual(research["research_stats"]["alerts_waiting_for_future_run"], 0)
        self.assertEqual(research["research_stats"]["checkpoint_batches_completed"], 3)
        self.assertTrue(progress)

        resumed_client = _FakeClient({"results": []})
        resumed = OfficialJobResearcher(
            "unused", client=resumed_client
        ).research_in_batches(jobs, research, batch_size=2)
        self.assertEqual(resumed_client.responses.calls, [])
        self.assertEqual(resumed["research_stats"]["alerts_reused_from_cache"], 5)

    def test_limited_batch_run_leaves_remaining_alerts_queued(self):
        jobs = [
            {
                "job_record_id": f"alert-{index}",
                "company": f"Company {index}",
                "title": "ML Engineer",
            }
            for index in range(1, 6)
        ]
        researcher = OfficialJobResearcher(
            "unused", client=_FakeClient({"results": []})
        )

        research = researcher.research_in_batches(
            jobs,
            batch_size=2,
            max_new_alerts=3,
        )

        self.assertEqual(research["research_stats"]["alerts_targeted_this_run"], 3)
        self.assertEqual(research["research_stats"]["checkpoint_batches_total"], 2)
        self.assertEqual(research["research_stats"]["alerts_waiting_for_future_run"], 2)

    def test_failed_backlog_run_resumes_after_last_checkpoint(self):
        jobs = [
            {
                "job_record_id": f"alert-{index}",
                "company": f"Company {index}",
                "title": "ML Engineer",
            }
            for index in range(1, 6)
        ]
        first_client = _SequenceClient(
            [
                {"results": []},
                {"results": []},
                RuntimeError("temporary API failure"),
            ]
        )
        checkpoints = []

        with self.assertRaises(OpenAIResearchError):
            OfficialJobResearcher(
                "unused", client=first_client
            ).research_in_batches(
                jobs,
                batch_size=2,
                checkpoint=lambda value, _completed, _total: checkpoints.append(
                    json.loads(json.dumps(value))
                ),
            )

        self.assertEqual(len(checkpoints), 1)
        self.assertEqual(checkpoints[0]["research_stats"]["alerts_processed_this_run"], 2)

        resumed_client = _FakeClient({"results": []})
        resumed = OfficialJobResearcher(
            "unused", client=resumed_client
        ).research_in_batches(jobs, checkpoints[0], batch_size=2)

        self.assertEqual(len(resumed_client.responses.calls), 3)
        self.assertEqual(resumed["research_stats"]["alerts_waiting_for_future_run"], 0)


if __name__ == "__main__":
    unittest.main()
