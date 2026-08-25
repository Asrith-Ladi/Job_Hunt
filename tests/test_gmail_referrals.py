import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from job_hunt.network.referrals import enrich_gmail_referrals, load_registry_connections


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


def _registry(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "LinkedIn Connections"
    sheet.append(["LinkedIn Connections for Referral Discovery"])
    sheet.append(["Offline snapshot"])
    sheet.append(["Verify before contacting"])
    sheet.append(HEADERS)
    sheet.append(
        [
            "Technical Person",
            "Accenture",
            "Machine Learning Engineer",
            "Accenture",
            "MNC",
            "Target-company connection",
            "sensitive-email@example.com",
            "https://www.linkedin.com/in/technical-person",
            "2025-01-01",
            "LinkedIn",
            "Exact",
            "",
            "",
        ]
    )
    sheet.append(
        [
            "Talent Person",
            "Accenture",
            "Senior Talent Acquisition Partner",
            "Accenture",
            "MNC",
            "Target-company connection",
            "second-sensitive@example.com",
            "https://www.linkedin.com/in/talent-person",
            "2025-02-01",
            "LinkedIn",
            "Exact",
            "",
            "",
        ]
    )
    workbook.save(path)


class GmailReferralTests(unittest.TestCase):
    def test_registry_loader_excludes_email_and_requires_linkedin_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.xlsx"
            _registry(path)
            connections = load_registry_connections(path)

        self.assertEqual(len(connections), 2)
        self.assertFalse(hasattr(connections[0], "email"))
        self.assertNotIn("sensitive-email", repr(connections))

    def test_enrichment_ranks_recruiter_and_builds_precise_copy_message(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.xlsx"
            _registry(path)
            rows, stats = enrich_gmail_referrals(
                [
                    {
                        "job_record_id": "job-1",
                        "company": "Accenture in India",
                        "title": "Senior Machine Learning Engineer",
                        "years_of_experience": "5-8 years",
                        "experience_min_years": 5,
                        "experience_max_years": 8,
                        "official_url": "https://careers.example/jobs/1",
                        "source_url": "https://linkedin.com/jobs/view/1",
                    }
                ],
                path,
            )

        row = rows[0]
        self.assertEqual(row["referral_count"], 2)
        self.assertEqual(row["referral_name"], "Talent Person")
        self.assertEqual(
            row["referral_profile_url"],
            "https://www.linkedin.com/in/talent-person",
        )
        self.assertEqual(
            row["referral_match_status"],
            "offline_company_match_unverified",
        )
        self.assertIn("5.8 years documented", row["referral_eligibility"])
        self.assertIn("Official JD requirements have not been checked", row["referral_eligibility"])
        self.assertIn("could you please refer me", row["referral_message"])
        self.assertIn("https://careers.example/jobs/1", row["referral_message"])
        candidates = row["referral_candidates"]
        self.assertEqual([candidate["name"] for candidate in candidates], [
            "Talent Person",
            "Technical Person",
        ])
        self.assertEqual(
            candidates[1]["profile_url"],
            "https://www.linkedin.com/in/technical-person",
        )
        self.assertTrue(candidates[1]["message"].startswith("Hi Technical"))
        self.assertNotIn("sensitive-email", str(row))
        self.assertEqual(stats["jobs_with_referral_candidate"], 1)
        self.assertEqual(stats["offline_connections_loaded"], 2)

    def test_unavailable_registry_never_blocks_gmail_rows(self):
        rows, stats = enrich_gmail_referrals(
            [{"job_record_id": "job-1", "company": "Example"}],
            Path("missing-registry.xlsx"),
        )
        self.assertEqual(rows[0]["referral_count"], 0)
        self.assertEqual(rows[0]["referral_candidates"], [])
        self.assertEqual(rows[0]["referral_match_status"], "connections_unavailable")
        self.assertEqual(stats["referral_enrichment_status"], "connections_unavailable")


if __name__ == "__main__":
    unittest.main()
