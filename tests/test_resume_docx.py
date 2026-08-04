import tempfile
import unittest
from pathlib import Path

from job_hunt.job_intelligence import normalize_resume_plan
from job_hunt.resume_docx import (
    ResumeTemplateError,
    extract_resume_evidence,
    tailor_resume_docx,
    validate_resume_docx,
)
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


if __name__ == "__main__":
    unittest.main()
