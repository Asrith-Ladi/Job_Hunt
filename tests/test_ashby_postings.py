import unittest

import httpx

from job_hunt.discovery.http_client import SafeHttpClient
from job_hunt.integrations.ashby_postings import AshbyExactPostingResolver


JOB_ID = "36f89b00-2010-4d23-aae3-17a2f53d9eaa"
OTHER_ID = "30259734-50c3-4f1c-81cd-8bff07e585e7"


def _client(handler):
    raw = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    safe = SafeHttpClient(client=raw, resolver=lambda _host: ["8.8.8.8"])
    return safe, raw


class AshbyExactPostingTests(unittest.TestCase):
    def test_custom_employer_url_is_matched_to_the_same_ashby_uuid(self):
        requests = []

        def handler(request):
            requests.append(str(request.url))
            if request.url.host == "sarvam.example":
                return httpx.Response(
                    200,
                    text=(
                        '<a href="https://jobs.ashbyhq.com/sarvam/'
                        f'{JOB_ID}/application">Apply</a>'
                    ),
                    headers={"content-type": "text/html"},
                )
            return httpx.Response(
                200,
                json={
                    "apiVersion": "1",
                    "jobs": [
                        {
                            "id": OTHER_ID,
                            "title": "Related role",
                            "descriptionPlain": "OAuth MCP Redis",
                        },
                        {
                            "id": JOB_ID,
                            "title": "Agent Engineer",
                            "location": "Bengaluru",
                            "department": "Engineering",
                            "employmentType": "FullTime",
                            "workplaceType": "OnSite",
                            "publishedAt": "2026-08-11T11:18:55.645+00:00",
                            "jobUrl": f"https://jobs.ashbyhq.com/sarvam/{JOB_ID}",
                            "applyUrl": (
                                f"https://jobs.ashbyhq.com/sarvam/{JOB_ID}/application"
                            ),
                            "descriptionPlain": (
                                "Build production agents with prompts, tool integrations, "
                                "and evals. Strong Python and cloud infrastructure."
                            ),
                        },
                    ],
                },
            )

        safe, raw = _client(handler)
        try:
            result = AshbyExactPostingResolver(safe).resolve(
                {
                    "company": "Sarvam AI",
                    "official_url": f"https://sarvam.example/careers/jobs/{JOB_ID}",
                }
            )
        finally:
            raw.close()

        self.assertTrue(result.recognized)
        self.assertIsNotNone(result.posting)
        self.assertEqual(result.posting["external_job_id"], JOB_ID)
        self.assertEqual(result.posting["title"], "Agent Engineer")
        self.assertNotIn("OAuth", result.posting["description"])
        self.assertEqual(result.posting["employment_type"], "Full Time")
        self.assertEqual(
            requests,
            [
                f"https://sarvam.example/careers/jobs/{JOB_ID}",
                "https://api.ashbyhq.com/posting-api/job-board/sarvam",
            ],
        )

    def test_recognized_ashby_job_never_falls_back_when_uuid_is_missing(self):
        def handler(_request):
            return httpx.Response(200, json={"apiVersion": "1", "jobs": []})

        safe, raw = _client(handler)
        try:
            result = AshbyExactPostingResolver(safe).resolve(
                {
                    "company": "Example",
                    "official_url": f"https://jobs.ashbyhq.com/example/{JOB_ID}",
                }
            )
        finally:
            raw.close()

        self.assertTrue(result.recognized)
        self.assertIsNone(result.posting)
        self.assertIn("no longer present", result.warning)


if __name__ == "__main__":
    unittest.main()
