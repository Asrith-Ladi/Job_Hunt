import hashlib
import tempfile
import unittest
from pathlib import Path

from job_hunt.runtime.paths import AppPaths
from job_hunt.runtime.files import read_json, write_json_atomic
from job_hunt.integrations.ashby_postings import ExactPostingResolution
from job_hunt.integrations.official_descriptions import OfficialDescriptionResolution
from job_hunt.intelligence.service import (
    JobIntelligenceService,
    ResumePlanner,
    _confirmed_skill_evidence,
    score_ats_alignment,
)
from job_hunt.intelligence.config import OpenAISettings
from job_hunt.resumes.docx import extract_resume_evidence, resume_sha256
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
    "description": (
        "Build production machine-learning systems using Python and AWS. "
        "Own deployment quality and collaborate with product teams."
    ),
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
        self.upload_context = []
        self.package_upload_context = []

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

    def upload_artifact(
        self,
        local_path,
        *,
        company_name,
        role_name,
        prepared_on,
        mime_type,
    ):
        self.upload_context.append(
            {
                "file_name": Path(local_path).name,
                "company_name": company_name,
                "role_name": role_name,
                "prepared_on": prepared_on,
                "mime_type": mime_type,
            }
        )
        return {
            "file_id": f"drive-{Path(local_path).stem}",
            "drive_url": f"https://drive.example/files/{Path(local_path).name}",
            "folder_id": "application-folder-id",
            "folder_url": "https://drive.example/application-folder",
            "folder_path": (
                f"Job Hunt/Resumes/{company_name}/"
                f"{prepared_on}_{role_name.replace(' ', '_')}"
            ),
        }

    def upload_application_file(
        self,
        local_path,
        *,
        folder_id,
        folder_url,
        folder_path,
        mime_type,
    ):
        self.package_upload_context.append(
            {
                "file_name": Path(local_path).name,
                "folder_id": folder_id,
                "folder_url": folder_url,
                "folder_path": folder_path,
                "mime_type": mime_type,
            }
        )
        return {
            "file_id": f"drive-{Path(local_path).stem}",
            "drive_url": f"https://drive.example/files/{Path(local_path).name}",
            "folder_id": folder_id,
            "folder_url": folder_url,
            "folder_path": folder_path,
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
    def test_application_archive_recaptures_full_exact_ats_description(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = AppPaths.from_project_root(root)
            library = _FakeResumeLibrary(root)
            posting = {
                **POSTING,
                "description": "",
                "description_summary": "A short verified summary.",
            }
            service = JobIntelligenceService(
                paths,
                resume_library=library,
                exact_posting_resolver=lambda _posting: ExactPostingResolution(
                    True,
                    posting={
                        "description": (
                            "## Responsibilities\n\n- Build production AI agents.\n"
                            "- Own evaluation pipelines."
                        )
                    },
                ),
                description_resolver=lambda _posting: OfficialDescriptionResolution(),
            )
            analysis_id = "analysis_archive1234"
            generation_id = "generation_archive1234"
            write_json_atomic(
                service.analysis_root / f"{analysis_id}.json",
                {"analysis_id": analysis_id, "candidates": [posting]},
            )
            write_json_atomic(
                service.artifact_index_path,
                {
                    "artifact_archive1234": {
                        "artifact_id": "artifact_archive1234",
                        "generation_id": generation_id,
                        "analysis_id": analysis_id,
                        "official_job_id": posting["official_job_id"],
                        "kind": "resume_docx",
                        "file_name": "Asrith_Ladi_AI_ML_Engineer_6Y.docx",
                        "drive_url": "https://drive.example/resume",
                        "folder_id": "application-folder-id",
                        "folder_url": "https://drive.example/application-folder",
                        "folder_path": "Job Hunt/Resumes/Example Company/2026-08-03_Role",
                    }
                },
            )

            package = service.archive_application_package(
                analysis_id,
                posting["official_job_id"],
                generation_id,
                source_job={"job_record_id": "alert-1"},
            )

            self.assertEqual(package["description_completeness"], "full")
            self.assertEqual(package["description_source"], "captured_exact_ats_description")
            details = read_json(
                service.root / "application_packages" / generation_id / "Application_Details.json"
            )
            self.assertIn("Own evaluation pipelines", details["description"])

    def test_resume_planner_emits_usage_without_prompt_or_evidence_content(self):
        captured = []
        planner = ResumePlanner("unused", "gpt-5.6-luna", client=object())
        planner.configure_usage_recording(
            lambda response, **metadata: captured.append((response, metadata)) or {},
            context={
                "job_record_id": "job-1",
                "company": "Example",
                "title": "ML Engineer",
            },
        )

        response = object()
        planner._record_usage(response)

        self.assertEqual(captured[0][0], response)
        self.assertEqual(captured[0][1]["operation"], "resume_plan")
        self.assertEqual(captured[0][1]["context"]["company"], "Example")

    def test_ats_alignment_is_deterministic_and_distinct_from_vendor_scores(self):
        before = score_ats_alignment(
            POSTING,
            (
                "Machine Learning Engineer using Python and AWS. "
                "Technical Skills: Docker."
            ),
        )
        after = score_ats_alignment(
            POSTING,
            (
                "Machine Learning Engineer using Python and AWS. "
                "Technical Skills: Docker, Context engineering."
            ),
        )

        self.assertEqual(before["score"], 80)
        self.assertEqual(before["missing_required"], ["Context engineering"])
        self.assertEqual(after["score"], 100)
        self.assertIn("Required terms 80%", before["breakdown"])

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
            self.assertEqual(
                analysis["eligibility_evidence_source"],
                "active_baseline_resume",
            )
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
            names_by_kind = {
                item["kind"]: item["file_name"] for item in result["artifacts"]
            }
            self.assertEqual(
                names_by_kind,
                {
                    "resume_docx": "Asrith_Ladi_AI_ML_Engineer_6Y.docx",
                    "resume_pdf": "Asrith_Ladi_AI_ML_Engineer_6Y.pdf",
                    "cover_letter": (
                        "Asrith_Ladi_AI_ML_Engineer_6Y_Cover_Letter.docx"
                    ),
                },
            )
            self.assertTrue(
                all(
                    item["company_name"] == "Example Company"
                    and item["role_name"] == "Senior Machine Learning Engineer"
                    for item in library.upload_context
                )
            )
            self.assertTrue(
                all(
                    item["folder_path"].startswith(
                        "Job Hunt/Resumes/Example Company/"
                    )
                    for item in result["artifacts"]
                )
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
            self.assertEqual(result["skill_placements"][0]["category"], "AI")
            self.assertEqual(result["experience_bullets_reframed"], 0)
            self.assertEqual(result["ats_alignment"]["before"]["score"], 80)
            self.assertEqual(result["ats_alignment"]["after"]["score"], 100)
            self.assertEqual(result["ats_alignment"]["delta"], 20)
            self.assertEqual(library.confirmed_evidence[0]["skill"], "Context engineering")
            self.assertTrue(result["requires_user_review"])
            self.assertTrue(result["warnings"])

            package = service.archive_application_package(
                analysis["analysis_id"],
                POSTING["official_job_id"],
                result["generation_id"],
                source_job={
                    "job_record_id": "alert-1",
                    "provider": "greenhouse",
                    "source_url": "https://linkedin.com/private-job",
                },
            )
            self.assertEqual(package["application_status"], "applied")
            self.assertTrue(package["full_description_available"])
            self.assertEqual(
                {item["file_name"] for item in package["files"]},
                {
                    "Job_Description.docx",
                    "Job_Description.md",
                    "Application_Details.json",
                },
            )
            self.assertEqual(package["description_completeness"], "full")
            self.assertEqual(package["capture_warning"], "")
            self.assertTrue(
                all(
                    item["folder_id"] == "application-folder-id"
                    for item in library.package_upload_context
                )
            )
            package_root = (
                paths.runtime_root
                / "job_intelligence"
                / "application_packages"
                / result["generation_id"]
            )
            details = read_json(package_root / "Application_Details.json")
            self.assertEqual(details["application_status"], "applied")
            self.assertIn("Own deployment quality", details["description"])
            markdown = (package_root / "Job_Description.md").read_text(encoding="utf-8")
            self.assertIn(
                "Build production machine-learning systems",
                markdown,
            )
            self.assertNotIn("Eligibility snapshot", markdown)
            from docx import Document

            readable_jd = "\n".join(
                paragraph.text
                for paragraph in Document(package_root / "Job_Description.docx").paragraphs
            )
            self.assertIn("Build production machine-learning systems", readable_jd)

            first_artifact = result["artifacts"][0]
            path, metadata = service.artifact(first_artifact["artifact_id"])
            self.assertTrue(path.is_file())
            self.assertEqual(metadata["artifact_id"], first_artifact["artifact_id"])
            tailored_skill_lines = [
                item["text"] for item in extract_resume_evidence(path)["skills"]
            ]
            self.assertTrue(
                any("Context engineering" in line for line in tailored_skill_lines)
            )
            self.assertFalse(
                any(line.startswith("Additional Skills:") for line in tailored_skill_lines)
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
