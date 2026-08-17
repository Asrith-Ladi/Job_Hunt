import hashlib
import tempfile
import unittest
from pathlib import Path

from job_hunt.gmail_service import AppPaths
from job_hunt.integrations.ashby_postings import ExactPostingResolution
from job_hunt.job_intelligence import JobIntelligenceService, _confirmed_skill_evidence
from job_hunt.openai_config import OpenAISettings
from job_hunt.resume_docx import extract_resume_evidence, resume_sha256
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
    "required_skills": ["Python", "Machine Learning", "AWS", "Context engineering"],
    "preferred_skills": ["Docker"],
    "evidence_confidence": "high",
    "source_notes": "Official employer careers page.",
}


class _FakeResearcher:
    def __init__(self):
        self.jobs = []

    def research(self, jobs, _existing, **_options):
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


class _FakeExactResearcher(_FakeResearcher):
    model = "test-model"

    def __init__(self):
        super().__init__()
        self.exact_calls = 0

    def extract_exact_posting(self, job, source):
        self.exact_calls += 1
        return {
            "official_job_id": "official_exact123",
            "company": job["company"],
            "title": source["title"],
            "location": source["location"],
            "experience_text": "3+ years",
            "experience_min": 3,
            "experience_max": None,
            "workplace_type": "On Site",
            "employment_type": "Full Time",
            "active_status": "active",
            "requisition_id": source["external_job_id"],
            "published_at": source["published_at"],
            "official_url": source["official_url"],
            "description_summary": "Build reliable production agents.",
            "required_skills": ["AI agents", "Python"],
            "preferred_skills": [],
            "required_skill_evidence": {
                "AI agents": "production agents",
                "Python": "Strong Python",
            },
            "preferred_skill_evidence": {},
            "evidence_confidence": "high",
            "source_notes": "Exact Ashby job ID matched.",
            "exact_source_fingerprint": source["source_fingerprint"],
        }


class _FakePlanner:
    def __init__(self):
        self.evidence = None
        self.cover_letter_requested = False
        self.calls = 0

    def plan(
        self,
        _posting,
        evidence,
        _eligibility,
        *,
        cover_letter_requested=False,
    ):
        self.calls += 1
        self.evidence = evidence
        self.cover_letter_requested = cover_letter_requested
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
            "reference_evidence_ids": [
                item["id"] for item in evidence.get("reference_points") or []
            ],
            # An empty model letter intentionally exercises the conservative local fallback.
            "cover_letter_paragraphs": [],
            "keyword_alignment": ["Python", "AWS"],
            "change_notes": ["Prioritized the most relevant documented skills."],
        }


class _FakeResumeLibrary:
    def __init__(self, root: Path):
        self.root = root / "drive_library"
        self.baseline = create_resume_docx(self.root / "baseline.docx")
        self.baseline_hash = resume_sha256(self.baseline)
        self.reference = self.root / "WORK_HIGHLIGHTS.md"
        self.reference.write_text(
            "# Work highlights\n\n"
            "- Built production Python and AWS machine-learning pipelines with automated "
            "quality validation and Docker deployment support.\n",
            encoding="utf-8",
        )
        self.reference_hash = hashlib.sha256(self.reference.read_bytes()).hexdigest()
        self.records = {}
        self.confirmed_evidence = []

    def status(self):
        return {
            "drive_connected": True,
            "drive_backed": True,
            "baseline_resume_configured": True,
            "baseline_resume_name": "baseline.docx",
            "baseline_resume_sha256": self.baseline_hash,
            "baseline_uploaded_at": "2026-08-04T12:00:00+05:30",
            "baseline_drive_url": "https://drive.example/baseline",
            "baseline_immutable": True,
            "reference_documents": [
                {
                    "original_name": self.reference.name,
                    "sha256": self.reference_hash,
                    "uploaded_at": "2026-08-04T12:00:00+05:30",
                    "drive_url": "https://drive.example/reference",
                }
            ],
            "reference_document_count": 1,
            "confirmed_skill_evidence": list(self.confirmed_evidence),
            "confirmed_skill_evidence_count": len(self.confirmed_evidence),
            "library_url": "https://drive.example/library",
            "message": "",
        }

    def materialize_inputs(self):
        return {
            "baseline_path": self.baseline,
            "baseline": {
                "sha256": self.baseline_hash,
                "original_name": self.baseline.name,
            },
            "references": [
                {
                    "sha256": self.reference_hash,
                    "original_name": self.reference.name,
                    "local_path": str(self.reference),
                }
            ],
            "reference_digest": hashlib.sha256(
                self.reference_hash.encode("utf-8")
            ).hexdigest(),
            "library_url": "https://drive.example/library",
        }

    def upload_artifact(self, local_path, run_date, _mime_type):
        return {
            "file_id": f"drive-{Path(local_path).stem}",
            "drive_url": f"https://drive.example/files/{Path(local_path).name}",
            "folder_url": f"https://drive.example/{run_date}/Resumes",
        }

    def store_confirmed_skill_evidence(self, entries):
        self.confirmed_evidence = [dict(item) for item in entries]
        return self.status()

    def record_artifacts(self, records):
        self.records.update({record["artifact_id"]: dict(record) for record in records})

    def materialize_artifact(self, artifact_id):
        record = self.records[artifact_id]
        return Path(record["local_path"]), dict(record)


def _fake_pdf_converter(_input_path: Path, output_path: Path) -> Path:
    output_path.write_bytes(b"%PDF-1.7\n" + (b"verified-test-pdf\n" * 100))
    return output_path


class JobIntelligenceTests(unittest.TestCase):
    def test_confirmed_skill_evidence_requires_an_exact_gap_and_contact_free_note(self):
        posting = {
            "required_skills": ["Context engineering"],
            "eligibility": {
                "matched_skills": [],
                "missing_skills": ["Context engineering"],
            },
        }
        with self.assertRaisesRegex(ValueError, "missing skill"):
            _confirmed_skill_evidence(
                [
                    {
                        "skill": "Unrelated keyword",
                        "note": "I used this elsewhere in a real and documented project.",
                        "confirmed": True,
                    }
                ],
                posting,
            )
        with self.assertRaisesRegex(ValueError, "contact details"):
            _confirmed_skill_evidence(
                [
                    {
                        "skill": "Context engineering",
                        "note": "Contact me at candidate@example.com about the workflow.",
                        "confirmed": True,
                    }
                ],
                posting,
            )

    def test_recognized_exact_source_failure_returns_no_related_candidate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            researcher = _FakeExactResearcher()
            service = JobIntelligenceService(
                AppPaths.from_project_root(root),
                settings_loader=lambda _root: OpenAISettings(
                    "test-secret", "test-model", "test"
                ),
                researcher_factory=lambda _key, _model: researcher,
                exact_posting_resolver=lambda _facts: ExactPostingResolution(
                    True,
                    warning="The exact Ashby job ID is no longer present.",
                ),
                resume_library=_FakeResumeLibrary(root),
            )

            analysis = service.analyze(
                {
                    "job_record_id": "missing-exact-job",
                    "company": "Sarvam AI",
                    "title": "Agent Engineer",
                    "official_url": (
                        "https://sarvam.example/careers/jobs/"
                        "36f89b00-2010-4d23-aae3-17a2f53d9eaa"
                    ),
                }
            )

            self.assertEqual(analysis["status"], "no_official_match")
            self.assertEqual(analysis["candidates"], [])
            self.assertEqual(
                analysis["warnings"],
                ["The exact Ashby job ID is no longer present."],
            )
            self.assertEqual(researcher.jobs, [])
            self.assertEqual(researcher.exact_calls, 0)

    def test_exact_ashby_analysis_uses_same_job_and_reuses_grounded_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = AppPaths.from_project_root(root)
            researcher = _FakeExactResearcher()
            library = _FakeResumeLibrary(root)
            job_id = "36f89b00-2010-4d23-aae3-17a2f53d9eaa"
            official_url = f"https://sarvam.example/careers/jobs/{job_id}"
            resolution = ExactPostingResolution(
                True,
                posting={
                    "provider": "ashby",
                    "board": "sarvam",
                    "external_job_id": job_id,
                    "company": "Sarvam AI",
                    "title": "Agent Engineer",
                    "location": "Bengaluru",
                    "employment_type": "Full Time",
                    "workplace_type": "On Site",
                    "published_at": "2026-08-11T11:18:55.645+00:00",
                    "official_url": official_url,
                    "description": "Build production agents. Strong Python.",
                    "source_fingerprint": "exact-fingerprint",
                },
            )
            service = JobIntelligenceService(
                paths,
                settings_loader=lambda _root: OpenAISettings(
                    "test-secret", "test-model", "test"
                ),
                researcher_factory=lambda _key, _model: researcher,
                exact_posting_resolver=lambda _facts: resolution,
                resume_library=library,
            )
            job = {
                "job_record_id": "sarvam-agent",
                "company": "Sarvam AI",
                "title": "Agent Engineer Bengaluru Full Time On-Site",
                "official_url": official_url,
            }

            first = service.analyze(job)
            second = service.analyze(job)

            candidate = first["candidates"][0]
            self.assertEqual(candidate["title"], "Agent Engineer")
            self.assertEqual(candidate["official_url"], official_url)
            self.assertEqual(candidate["official_match_status"], "exact_candidate")
            self.assertEqual(candidate["official_match_score"], 100)
            self.assertEqual(candidate["required_skills"], ["AI agents", "Python"])
            self.assertEqual(researcher.exact_calls, 1)
            self.assertFalse(first["cached"])
            self.assertTrue(second["cached"])
            self.assertEqual(researcher.jobs, [])

    def test_manual_analysis_and_document_generation_are_private_cached_and_immutable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = AppPaths.from_project_root(root)
            researcher = _FakeResearcher()
            planner = _FakePlanner()
            library = _FakeResumeLibrary(root)
            baseline_before = library.baseline.read_bytes()
            service = JobIntelligenceService(
                paths,
                settings_loader=lambda _root: OpenAISettings(
                    "test-secret", "test-model", "test"
                ),
                researcher_factory=lambda _key, _model: researcher,
                planner_factory=lambda _key, _model: planner,
                resume_library=library,
                pdf_converter=_fake_pdf_converter,
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
            result = service.generate_documents(
                analysis["analysis_id"],
                POSTING["official_job_id"],
                outputs=["resume_docx", "resume_pdf", "cover_letter"],
                confirmed_skill_evidence=[
                    {
                        "skill": "Context engineering",
                        "note": (
                            "Designed retrieval context and prompt inputs for a documented "
                            "agent workflow and evaluated the resulting responses."
                        ),
                        "confirmed": True,
                    }
                ],
            )

            self.assertEqual(
                {item["kind"] for item in result["artifacts"]},
                {"resume_docx", "resume_pdf", "cover_letter"},
            )
            self.assertTrue(result["baseline_unchanged"])
            self.assertEqual(library.baseline.read_bytes(), baseline_before)
            self.assertTrue(planner.cover_letter_requested)
            serialized_evidence = str(planner.evidence)
            self.assertNotIn("candidate@example.com", serialized_evidence)
            self.assertNotIn("99999", serialized_evidence)
            self.assertIn("production Python and AWS", serialized_evidence)
            self.assertIn("Designed retrieval context", serialized_evidence)
            self.assertTrue(result["reference_points_used"])
            self.assertEqual(result["confirmed_skills_added"], ["Context engineering"])
            self.assertEqual(library.confirmed_evidence[0]["skill"], "Context engineering")
            self.assertTrue(result["requires_user_review"])
            self.assertTrue(result["warnings"])

            first_artifact = result["artifacts"][0]
            path, metadata = service.artifact(first_artifact["artifact_id"])
            self.assertTrue(path.is_file())
            self.assertEqual(metadata["artifact_id"], first_artifact["artifact_id"])
            self.assertIn(
                "Additional Skills: Context engineering",
                [item["text"] for item in extract_resume_evidence(path)["skills"]],
            )

            cached = service.generate_documents(
                analysis["analysis_id"],
                POSTING["official_job_id"],
                outputs=["resume_docx", "resume_pdf", "cover_letter"],
                confirmed_skill_evidence=[
                    {
                        "skill": "Context engineering",
                        "note": (
                            "Designed retrieval context and prompt inputs for a documented "
                            "agent workflow and evaluated the resulting responses."
                        ),
                        "confirmed": True,
                    }
                ],
            )
            self.assertTrue(cached["plan_cached"])
            self.assertEqual(planner.calls, 1)


if __name__ == "__main__":
    unittest.main()
