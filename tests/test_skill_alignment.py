import unittest

from job_hunt.jobs.skills import (
    map_job_skills_to_evidence,
    match_skill_to_evidence,
    skill_placement,
)


EVIDENCE = [
    {"id": "skill-ai", "kind": "skill", "text": "AI: LLMs, LangGraph, RAG, MCP"},
    {
        "id": "bullet-validation",
        "kind": "experience_bullet",
        "text": "Automated model validation and quality checks for production AI services.",
    },
    {
        "id": "bullet-context",
        "kind": "experience_bullet",
        "text": "Designed retrieval context and prompt inputs for an agent workflow.",
    },
    {"id": "skill-cloud", "kind": "skill", "text": "Cloud: AWS, Docker, Kubernetes"},
]


class SkillAlignmentTests(unittest.TestCase):
    def test_equivalent_compound_skill_requires_documented_concepts(self):
        matched = match_skill_to_evidence("LLMs and agents", EVIDENCE)
        unsupported = match_skill_to_evidence(
            "Production engineering and ownership",
            EVIDENCE,
        )

        self.assertTrue(matched["matched"])
        self.assertEqual(matched["match_type"], "equivalent")
        self.assertIn("skill-ai", matched["evidence_ids"])
        self.assertFalse(unsupported["matched"])

    def test_context_and_evaluation_synonyms_are_supported_but_new_tools_are_not(self):
        mappings = map_job_skills_to_evidence(
            ["Context engineering", "Evaluations", "OAuth"],
            EVIDENCE,
        )
        by_skill = {item["skill"]: item for item in mappings}

        self.assertEqual(by_skill["Context engineering"]["match_type"], "equivalent")
        self.assertEqual(by_skill["Evaluations"]["match_type"], "equivalent")
        self.assertEqual(
            by_skill["Context engineering"]["direct_evidence_ids"],
            ["bullet-context"],
        )
        self.assertEqual(
            by_skill["Evaluations"]["direct_evidence_ids"],
            ["bullet-validation"],
        )
        self.assertNotIn("OAuth", by_skill)

    def test_compound_whole_resume_support_does_not_authorize_unrelated_bullet(self):
        evidence = [
            {"id": "llm", "kind": "skill", "text": "AI: Large Language Models"},
            {
                "id": "agent-bullet",
                "kind": "experience_bullet",
                "text": "Designed an autonomous agent workflow.",
            },
        ]

        mapping = map_job_skills_to_evidence(["LLMs and agents"], evidence)[0]

        self.assertTrue(mapping["matched"])
        self.assertEqual(mapping["match_type"], "equivalent")
        self.assertEqual(mapping["direct_evidence_ids"], [])

    def test_skill_placement_uses_relevant_existing_heading_or_specific_new_heading(self):
        lines = [
            {"id": "ai", "text": "AI: RAG, MCP"},
            {"id": "data", "text": "Data & Databases: SQL, PostgreSQL"},
        ]

        self.assertEqual(skill_placement("Prompting", lines)["target_skill_id"], "ai")
        self.assertEqual(skill_placement("Redis", lines)["target_skill_id"], "data")
        self.assertEqual(skill_placement("OAuth", lines)["category"], "Backend & APIs")


if __name__ == "__main__":
    unittest.main()
