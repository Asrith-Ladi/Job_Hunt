import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from job_hunt.network_reviews import (
    NetworkReviewService,
    connection_review_relevance,
    profile_review_message,
)
from job_hunt.enrichment import Connection
from job_hunt.gmail_referrals import (
    load_registry_connection_profiles,
    load_registry_connection_records,
)


HEADERS = [
    "Connection Name",
    "Current Company",
    "Current Position",
    "Registry Company",
    "Registry Category",
    "Referral Status",
    "Email Address",
    "LinkedIn Profile",
    "Connected On",
    "Contact Options",
    "Match Method",
    "Official Careers Page",
    "Direct Job Portal",
]


def _write_registry(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "LinkedIn Connections"
    sheet.append(["LinkedIn Connections for Referral Discovery"])
    sheet.append(["Offline snapshot"])
    sheet.append(["Verify current roles"])
    sheet.append(HEADERS)
    sheet.append(
        [
            "Asha Leader",
            "Example AI",
            "Director of Machine Learning",
            "Example AI",
            "Product",
            "Target-company connection",
            "private-asha@example.com",
            "https://www.linkedin.com/in/asha-leader",
            "2025-01-01",
            "LinkedIn",
            "Exact",
            "",
            "",
        ]
    )
    sheet.append(
        [
            "Bala Engineer",
            "Data Example",
            "Senior Data Engineer",
            "",
            "",
            "",
            "private-bala@example.com",
            "https://www.linkedin.com/in/bala-engineer",
            "2025-02-01",
            "LinkedIn",
            "",
            "",
            "",
        ]
    )
    sheet.append(
        [
            "Chitra Recruiter",
            "Hiring Example",
            "Talent Acquisition Partner",
            "",
            "",
            "",
            "private-chitra@example.com",
            "https://www.linkedin.com/in/chitra-recruiter",
            "2025-03-01",
            "LinkedIn",
            "",
            "",
            "",
        ]
    )
    sheet.append(
        [
            "Dev Profile",
            "",
            "",
            "",
            "",
            "",
            "private-dev@example.com",
            "",
            "2025-04-01",
            "LinkedIn",
            "",
            "",
            "",
        ]
    )
    workbook.save(path)


class NetworkReviewTests(unittest.TestCase):
    def test_relevance_prioritizes_ai_leadership_and_not_recruiting(self):
        leader = Connection(
            "Asha",
            "Leader",
            "https://www.linkedin.com/in/asha",
            "Example",
            "Director of Machine Learning",
            "",
        )
        recruiter = Connection(
            "Chitra",
            "Recruiter",
            "https://www.linkedin.com/in/chitra",
            "Example",
            "AI Talent Acquisition Partner",
            "",
        )
        leader_result = connection_review_relevance(leader)
        recruiter_result = connection_review_relevance(recruiter)
        self.assertEqual(leader_result["category"], "AI/ML leadership")
        self.assertTrue(leader_result["recommended"])
        self.assertTrue(leader_result["leadership"])
        self.assertEqual(recruiter_result["category"], "Recruiting / HR")
        self.assertFalse(recruiter_result["recommended"])

    def test_template_personalizes_name_and_roles_without_overclaiming(self):
        connection = Connection(
            "Asha",
            "Leader",
            "https://www.linkedin.com/in/asha",
            "Example",
            "Director of Machine Learning",
            "",
        )
        message = profile_review_message(connection, "AI Engineer and ML Engineer")
        self.assertTrue(message.startswith("Hi Asha, hope you're doing well."))
        self.assertIn("AI Engineer and ML Engineer opportunities", message)
        self.assertIn("• How my profile is positioned for AI/ML roles", message)
        self.assertIn("I can share my resume here", message)
        self.assertNotIn("close connection", message.casefold())

    def test_service_returns_all_profiles_but_defaults_to_recommended(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.xlsx"
            _write_registry(path)
            service = NetworkReviewService(path)

            recommended = service.search(target_roles="Generative AI Engineer")
            all_profiles = service.search(
                recommended_only=False,
                target_roles="Generative AI Engineer",
                limit=20,
            )
            managers = service.search(
                recommended_only=False,
                leadership_only=True,
                target_roles="Generative AI Engineer",
            )

        self.assertEqual(all_profiles["all_connections"], 4)
        self.assertEqual(all_profiles["all_profiles"], 3)
        self.assertEqual(all_profiles["email_connections"], 4)
        self.assertEqual(len(all_profiles["rows"]), 4)
        self.assertEqual(recommended["total_matching"], 2)
        self.assertEqual(managers["total_matching"], 1)
        self.assertEqual(recommended["rows"][0]["name"], "Asha Leader")
        self.assertIn(
            "Generative AI Engineer opportunities", recommended["rows"][0]["profile_review_message"]
        )
        self.assertEqual(all_profiles["rows"][0]["email_address"], "private-asha@example.com")
        self.assertEqual(all_profiles["rows"][-1]["linkedin_profile"], "")

    def test_email_loading_is_explicit_and_referral_profiles_remain_contact_free(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.xlsx"
            _write_registry(path)
            default_records = load_registry_connection_records(path)
            network_records = load_registry_connection_records(path, include_email=True)
            referral_profiles = load_registry_connection_profiles(path)

        self.assertTrue(all(not record.email_address for record in default_records))
        self.assertEqual(network_records[0].email_address, "private-asha@example.com")
        self.assertEqual(len(referral_profiles), 3)
        self.assertFalse(hasattr(referral_profiles[0], "email_address"))


if __name__ == "__main__":
    unittest.main()
