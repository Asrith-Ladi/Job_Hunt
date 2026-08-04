import tempfile
import unittest
from pathlib import Path

from job_hunt.gmail_service import AppPaths
from job_hunt.job_intelligence import JobIntelligenceService
from job_hunt.openai_config import OpenAISettings
from tests.docx_fixture import create_resume_docx


POSTING = {
    "official_job_id": "official_example123",
    "company": "Example Company",
    "title": "Senior Machine Learning Engineer",
    "location": "Hyderabad",
    "experience_text": "5-8 years",
    "experience_min": 5,
    "experience_max": 8,
    "workplace_type": "hybrid",
    "employment_type": "full-time",
    "active_status": "active",
    "requisition_id": "REQ-123",
    "published_at": "2026-08-02",
    "official_url": "https://careers.example.com/jobs/123",
    "description_summary": "Build production machine-learning systems using Python and AWS.",
    "required_skills": ["Python", "Machine Learning", "AWS"],
    "preferred_skills": ["Docker"],
    "evidence_confidence": "high",
    "source_notes": "Official employer careers page.",
}


class _FakeResearcher:
    def __init__(self):
        self.jobs = []

    def research(self, jobs, existing, **_options):
        self.jobs = jobs
        job_id = jobs[0]["job_record_id"]
        return {
            "verified_at": "2026-08-03",
            "research_model": "test-model",
            "checked_alert_ids": [job_id],
            "checked_alert_fingerprints": {job_id: "fingerprint"},
            "postings": [dict(POSTING)],
            "matches": {
                job_id: [
                    {
                        "official_job_id": POSTING["official_job_id"],
                        "match_status": "exact_candidate",
                        "match_score": 96,
                        "match_reason": "Company, title, and location match.",
                    }
                ]
            },
            "research_stats": {"api_calls": 1},
        }


class _FakePlanner:
    def __init__(self):
        self.evidence = None

    def plan(self, _posting, evidence, _eligibility):
        self.evidence = evidence
        return {
            "summary": evidence["current_summary"],
            "skill_order": [item["id"] for item in reversed(evidence["skills"])],
            "experience_sections": [
                {
                    "section_id": section["section_id"],
                    "bullet_order": [item["id"] for item in section["bullets"]],
                }
                for section in evidence["experience_sections"]
            ],
            "keyword_alignment": ["Python", "AWS"],
            "change_notes": ["Prioritized the most relevant documented skills."],
            "validation_warnings": [],
        }


class JobIntelligenceTests(unittest.TestCase):
    def test_manual_analysis_and_resume_generation_are_private_and_cached(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = AppPaths.from_project_root(root)
            create_resume_docx(paths.secrets_root / "base_resume.docx")
            researcher = _FakeResearcher()
            planner = _FakePlanner()
            service = JobIntelligenceService(
                paths,
                settings_loader=lambda _root: OpenAISettings(
                    "test-secret", "test-model", "test"
                ),
                researcher_factory=lambda _key, _model: researcher,
                planner_factory=lambda _key, _model: planner,
            )

            analysis = service.analyze(
                {
                    "job_record_id": "alert-1",
                    "company": "Example Company",
                    "title": "Senior Machine Learning Engineer",
                    "location": "Hyderabad",
                    "experience_text": "5-8 years",
                    "official_url": "https://careers.example.com/jobs/123",
                    "source_url": "https://linkedin.com/private-job",
                    "gmail_message_id": "private-message-id",
                }
            )

            self.assertEqual(analysis["candidates"][0]["official_match_score"], 96)
            self.assertGreater(analysis["candidates"][0]["eligibility"]["score"], 0)
            self.assertNotIn("source_url", researcher.jobs[0])
            self.assertNotIn("gmail_message_id", researcher.jobs[0])
            result = service.generate_resume(
                analysis["analysis_id"],
                POSTING["official_job_id"],
                upload_to_drive=False,
            )

            self.assertTrue(service.resume_path(result["resume_id"]).is_file())
            serialized_evidence = str(planner.evidence)
            self.assertNotIn("candidate@example.com", serialized_evidence)
            self.assertNotIn("99999", serialized_evidence)
            self.assertTrue(result["requires_user_review"])


if __name__ == "__main__":
    unittest.main()
