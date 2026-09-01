import json
import unittest

import httpx

from job_hunt.discovery.http_client import SafeHttpClient
from job_hunt.integrations.official_descriptions import (
    clean_description,
    resolve_official_description,
)


class OfficialDescriptionTests(unittest.TestCase):
    def test_structured_description_is_flattened_without_container_repr(self):
        value = {
            "description": "Build reliable AI systems.",
            "responsibilities": ["Own evaluations", "Improve retrieval"],
            "qualifications": {"content": "Five years of Python experience."},
        }

        result = clean_description(value)

        self.assertIn("Build reliable AI systems.", result)
        self.assertIn("## Responsibilities", result)
        self.assertIn("- Own evaluations", result)
        self.assertIn("Five years of Python experience.", result)
        self.assertNotIn("{'", result)

    def test_public_json_ld_job_description_is_captured_as_full(self):
        posting = {
            "title": "AI Agent Engineer",
            "requisition_id": "REQ-36",
            "official_url": "https://careers.example.com/jobs/req-36",
        }
        job_posting = {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "identifier": "REQ-36",
            "title": "AI Agent Engineer",
            "description": (
                "<h2>About the role</h2><p>Build production AI agents.</p>"
                "<h2>Requirements</h2><ul><li>Python</li><li>Evaluation pipelines</li></ul>"
            ),
        }

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                text=(
                    "<html><body><script type='application/ld+json'>"
                    f"{json.dumps(job_posting)}"
                    "</script><main>Careers page</main></body></html>"
                ),
                request=request,
            )

        client = SafeHttpClient(
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            resolver=lambda _host: ["93.184.216.34"],
        )
        try:
            result = resolve_official_description(posting, http_client=client)
        finally:
            client.close()

        self.assertEqual(result.completeness, "full")
        self.assertEqual(result.source, "captured_official_json_ld")
        self.assertIn("Build production AI agents.", result.description)
        self.assertIn("- Python", result.description)

    def test_protected_alert_url_is_not_requested(self):
        result = resolve_official_description(
            {
                "title": "AI Engineer",
                "official_url": "https://www.linkedin.com/jobs/view/123",
            }
        )

        self.assertEqual(result.description, "")
        self.assertEqual(result.completeness, "summary_only")
        self.assertIn("not an official employer page", result.warning)


if __name__ == "__main__":
    unittest.main()
