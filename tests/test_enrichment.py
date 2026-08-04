import tempfile
import unittest
from pathlib import Path

from job_hunt.enrichment import (
    Connection,
    ResumeProfile,
    canonical_company,
    cold_referral_message,
    company_connections,
    experience_points,
    load_connections,
    personal_resume_profile,
    score_alert_only,
    score_official_posting,
)


class EnrichmentTests(unittest.TestCase):
    def test_company_aliases_are_cautious_and_useful(self):
        self.assertEqual(canonical_company("Accenture in India"), "Accenture")
        self.assertEqual(canonical_company("Amgen Inc"), "Amgen")
        self.assertEqual(canonical_company("S&P Global Market Intelligence"), "S&P Global")
        self.assertEqual(canonical_company("Ernst & Young"), "EY")
        self.assertEqual(canonical_company("RealPage"), "RealPage")

    def test_connections_export_skips_preamble_and_drops_email(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "Connections.csv"
            source.write_text(
                "Notes\nGenerated export\n\n"
                "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
                "Alex,Example,https://linkedin.com/in/alex,alex@example.com,Accenture,Recruiter,01 Jan 2026\n",
                encoding="utf-8",
            )
            connections = load_connections(source)
        self.assertEqual(len(connections), 1)
        self.assertEqual(connections[0].full_name, "Alex Example")
        self.assertFalse(hasattr(connections[0], "email"))

    def test_referral_ranking_prefers_recruiting_then_technical_roles(self):
        connections = [
            Connection(
                "General", "Person", "https://example.com/1", "Microsoft", "Finance Analyst", ""
            ),
            Connection("Tech", "Person", "https://example.com/2", "Microsoft", "ML Engineer", ""),
            Connection(
                "Talent", "Person", "https://example.com/3", "Microsoft", "Talent Acquisition", ""
            ),
        ]
        ranked = company_connections(connections, "Microsoft")
        self.assertEqual([item.first_name for item in ranked], ["Talent", "Tech", "General"])

    def test_experience_points_distinguish_range_and_gap(self):
        self.assertEqual(experience_points(5.8, 5, 8)[0], 30)
        self.assertEqual(experience_points(5.8, 6.5, 10)[0], 18)
        self.assertEqual(experience_points(5.8, 10, 14)[0], 0)
        self.assertEqual(experience_points(5.8, None, None)[0], 15)

    def test_official_eligibility_is_explainable_and_separate_from_matching(self):
        profile = ResumeProfile(
            years_experience=5.8,
            skills=frozenset({"Python", "SQL", "Machine Learning", "AWS", "Docker"}),
            evidence=("Production ML",),
        )
        posting = {
            "title": "Senior Machine Learning Engineer",
            "experience_min": 5,
            "experience_max": 8,
            "required_skills": ["Python", "SQL", "Machine Learning", "AWS", "Healthcare"],
            "active_status": "active",
            "evidence_confidence": "high",
        }
        result = score_official_posting(posting, profile)
        self.assertEqual(result["score"], 92)
        self.assertEqual(result["band"], "Strong")
        self.assertTrue(any("healthcare" in item.lower() for item in result["gaps"]))
        self.assertIn("Experience 30/30", result["components"])

    def test_alert_only_score_is_capped_and_low_confidence(self):
        profile = ResumeProfile(5.8, frozenset({"Python"}), ("Evidence",))
        alert = {
            "title": "Machine Learning Engineer",
            "location": "Hyderabad",
            "experience_min_years": 5,
            "experience_max_years": 8,
        }
        result = score_alert_only(alert, profile)
        self.assertLessEqual(result["score"], 60)
        self.assertEqual(result["band"], "Preliminary only")
        self.assertEqual(result["confidence"], "low")

    def test_personal_profile_contains_only_verified_resume_evidence(self):
        profile = personal_resume_profile()
        self.assertEqual(profile.years_experience, 5.8)
        self.assertIn("Python", profile.skills)
        self.assertTrue(any("GenAI" in item for item in profile.evidence))

    def test_cold_message_uses_job_and_does_not_overclaim_relationship(self):
        connection = Connection(
            "Alex", "Example", "https://linkedin.com/in/alex", "Real", "ML Engineer", ""
        )
        message = cold_referral_message(
            connection,
            "Real",
            "Senior Machine Learning Engineer",
            "https://jobs.example/1",
            ["Python", "RAG"],
        )
        self.assertTrue(message.startswith("Hi Alex"))
        self.assertIn("Python and RAG", message)
        self.assertIn("could you please refer me for this role", message)
        self.assertIn("I completely understand if it isn't possible", message)
        self.assertIn("\n\nJob: https://jobs.example/1\n\n", message)
        self.assertTrue(message.endswith("Thank you,\nAsrith"))
        self.assertNotIn("close connection", message.lower())


if __name__ == "__main__":
    unittest.main()
