import tempfile
import unittest
from pathlib import Path

from job_hunt.intelligence.service import normalize_resume_plan
from job_hunt.resumes.docx import (
    ResumeTemplateError,
    extract_resume_evidence,
    tailor_resume_docx,
    validate_resume_docx,
)
from job_hunt.jobs.skills import map_job_skills_to_evidence, resume_evidence_items
from tests.docx_fixture import create_resume_docx


class ResumeDocxTests(unittest.TestCase):
    def test_tailoring_changes_summary_and_only_reorders_existing_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = create_resume_docx(root / "base.docx")
            evidence = extract_resume_evidence(base)
            summary = (
                "Machine Learning Engineer with 5+ years of experience delivering "
                "production AI systems with Python, AWS, Docker, Kubernetes, RAG, "
                "LangGraph, and MCP, including model validation and cloud automation."
            )
            plan = {
                "summary": summary,
                "skill_order": [item["id"] for item in reversed(evidence["skills"])],
                "experience_sections": [
                    {
                        "section_id": section["section_id"],
                        "bullet_order": [
                            item["id"] for item in reversed(section["bullets"])
                        ],
                    }
                    for section in evidence["experience_sections"]
                ],
            }

            output = tailor_resume_docx(base, root / "tailored.docx", plan)
            tailored = extract_resume_evidence(output)

            self.assertEqual(tailored["current_summary"], summary)
            self.assertEqual(
                [item["text"] for item in tailored["skills"]],
                [item["text"] for item in reversed(evidence["skills"])],
            )
            self.assertEqual(validate_resume_docx(output), output.resolve())

    def test_contact_inside_professional_sections_stops_model_use(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = create_resume_docx(
                Path(temporary) / "base.docx",
                contact_in_skills=True,
            )
            with self.assertRaises(ResumeTemplateError):
                extract_resume_evidence(base)

    def test_tailoring_places_user_confirmed_keywords_in_relevant_skill_heading(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = create_resume_docx(root / "base.docx")
            evidence = extract_resume_evidence(base)
            plan = {
                "summary": evidence["current_summary"],
                "skill_order": [item["id"] for item in evidence["skills"]],
                "experience_sections": [
                    {
                        "section_id": section["section_id"],
                        "bullet_order": [item["id"] for item in section["bullets"]],
                    }
                    for section in evidence["experience_sections"]
                ],
                "confirmed_skills": ["Context engineering", "Evaluation pipelines"],
            }

            output = tailor_resume_docx(base, root / "tailored.docx", plan)
            tailored = extract_resume_evidence(output)

            ai_line = next(
                item["text"] for item in tailored["skills"] if item["text"].startswith("AI:")
            )
            self.assertIn("Context engineering", ai_line)
            self.assertIn("Evaluation pipelines", ai_line)
            self.assertFalse(
                any(item["text"].startswith("Additional Skills:") for item in tailored["skills"])
            )

    def test_equivalent_evidence_adds_exact_keyword_and_reframes_relevant_bullet(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = create_resume_docx(root / "base.docx")
            evidence = extract_resume_evidence(base)
            posting = {"required_skills": ["Evaluations"], "preferred_skills": []}
            mappings = map_job_skills_to_evidence(
                posting["required_skills"],
                resume_evidence_items(evidence),
            )
            evidence["supported_jd_keyword_evidence"] = mappings
            evidence["baseline_missing_jd_keywords"] = ["Evaluations"]
            validation_bullet = next(
                item
                for section in evidence["experience_sections"]
                for item in section["bullets"]
                if "model validation" in item["text"]
            )
            raw_sections = []
            for section in evidence["experience_sections"]:
                rewrites = []
                if validation_bullet in section["bullets"]:
                    rewrites.append(
                        {
                            "bullet_id": validation_bullet["id"],
                            "text": (
                                "Improved model Evaluations through automated validation, "
                                "reducing manual testing effort by 80%."
                            ),
                        }
                    )
                raw_sections.append(
                    {
                        "section_id": section["section_id"],
                        "bullet_order": [item["id"] for item in section["bullets"]],
                        "bullet_rewrites": rewrites,
                    }
                )
            plan = normalize_resume_plan(
                {
                    "summary": evidence["current_summary"],
                    "skill_order": [item["id"] for item in evidence["skills"]],
                    "experience_sections": raw_sections,
                    "reference_evidence_ids": [],
                    "cover_letter_paragraphs": [],
                    "keyword_alignment": ["Evaluations"],
                    "change_notes": [],
                },
                posting,
                evidence,
            )

            output = tailor_resume_docx(base, root / "tailored.docx", plan)
            tailored = extract_resume_evidence(output)

            self.assertEqual(plan["documented_equivalent_skills_added"], ["Evaluations"])
            self.assertEqual(plan["experience_sections"][0]["bullet_rewrites"], [
                {
                    "bullet_id": validation_bullet["id"],
                    "text": (
                        "Improved model Evaluations through automated validation, "
                        "reducing manual testing effort by 80%."
                    ),
                }
            ])
            self.assertTrue(
                any("Evaluations" in item["text"] for item in tailored["skills"])
            )
            self.assertTrue(
                any(
                    "Improved model Evaluations" in item["text"]
                    for section in tailored["experience_sections"]
                    for item in section["bullets"]
                )
            )

    def test_unsupported_skill_in_generated_summary_keeps_original(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = create_resume_docx(Path(temporary) / "base.docx")
            evidence = extract_resume_evidence(base)
            raw = {
                "summary": (
                    "Machine Learning Engineer with 5+ years of experience delivering "
                    "production AI systems using Python, AWS, Docker, Kubernetes, and "
                    "Azure across reliable cloud platforms and model operations."
                ),
                "skill_order": [],
                "experience_sections": [],
                "keyword_alignment": ["Azure", "Python"],
                "change_notes": ["Prioritized relevant experience."],
            }
            posting = {
                "required_skills": ["Python", "Azure"],
                "preferred_skills": [],
            }

            plan = normalize_resume_plan(raw, posting, evidence)

            self.assertEqual(plan["summary"], evidence["current_summary"])
            self.assertNotIn("Azure", plan["keyword_alignment"])
            self.assertTrue(plan["validation_warnings"])

    def test_bullet_rewrite_rejects_changed_metrics_and_unrelated_keyword_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = create_resume_docx(Path(temporary) / "base.docx")
            evidence = extract_resume_evidence(base)
            validation_bullet = next(
                item
                for section in evidence["experience_sections"]
                for item in section["bullets"]
                if "model validation" in item["text"]
            )
            evidence["supported_jd_keyword_evidence"] = [
                {
                    "skill": "Context engineering",
                    "matched": True,
                    "match_type": "equivalent",
                    "evidence_ids": ["resume_summary"],
                    "evidence_kinds": ["summary"],
                }
            ]
            section = evidence["experience_sections"][0]
            raw = {
                "summary": evidence["current_summary"],
                "skill_order": [],
                "experience_sections": [
                    {
                        "section_id": section["section_id"],
                        "bullet_order": [item["id"] for item in section["bullets"]],
                        "bullet_rewrites": [
                            {
                                "bullet_id": validation_bullet["id"],
                                "text": (
                                    "Applied Context engineering to automated model validation, "
                                    "reducing manual testing effort by 90%."
                                ),
                            }
                        ],
                    }
                ],
                "keyword_alignment": [],
                "change_notes": [],
            }

            plan = normalize_resume_plan(
                raw,
                {"required_skills": ["Context engineering"]},
                evidence,
            )

            self.assertEqual(plan["experience_sections"][0]["bullet_rewrites"], [])
            self.assertTrue(
                any("rewritten bullet" in warning for warning in plan["validation_warnings"])
            )


if __name__ == "__main__":
    unittest.main()
