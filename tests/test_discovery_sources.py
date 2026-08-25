import json
import unittest
from pathlib import Path

import httpx

from job_hunt.discovery.adapters import adapter_for
from job_hunt.discovery.detection import detect_from_url, detect_source
from job_hunt.discovery.generic import GenericPublicDiscovery
from job_hunt.discovery.http_client import (
    AccessStoppedError,
    PublicSourceError,
    SafeHttpClient,
    validate_public_https_url,
)
from job_hunt.discovery.models import DiscoveryFilters, SourceConfig
from job_hunt.discovery.registry import load_company_registry


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = PROJECT_ROOT / "outputs" / "mnc_registry_2026-07-31" / "Company_Source_Registry.xlsx"


def _safe_client(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    return SafeHttpClient(client=client, resolver=lambda _host: ["8.8.8.8"]), client


class DiscoverySourceTests(unittest.TestCase):
    def test_titles_and_keywords_are_word_and_phrase_aware_alternatives(self):
        filters = DiscoveryFilters(
            keyword="agent, data scientist, MLOps, machine-learning, AI"
        )
        self.assertTrue(filters.matches_text("Agent Engineer"))
        self.assertTrue(filters.matches_text("Agentic AI Engineer"))
        self.assertTrue(filters.matches_text("Applied AI Engineer, Sarvam Agents"))
        self.assertTrue(filters.matches_text("Senior Data Scientists"))
        self.assertTrue(filters.matches_text("ML Ops Engineer"))
        self.assertTrue(filters.matches_text("Platform Role", "Build machine-learning systems"))
        self.assertTrue(filters.matches_text("Researcher", "", "AI Platform"))
        self.assertFalse(DiscoveryFilters(keyword="ai").matches_text("Email Specialist"))
        self.assertFalse(DiscoveryFilters(keyword="agent").matches_text("Engagement Manager"))

    def test_registry_reads_only_the_five_public_company_tables(self):
        entries = load_company_registry(REGISTRY)
        self.assertEqual(len(entries), 210)
        self.assertEqual(len({entry.company.casefold() for entry in entries}), 210)
        self.assertEqual(
            {entry.category for entry in entries},
            {
                "MNC",
                "Product Companies",
                "Startups",
                "Mid-Sized Companies",
                "Other Companies",
            },
        )
        self.assertTrue(any(entry.adapter_ready for entry in entries))
        self.assertNotIn("email", entries[0].to_dict())
        self.assertNotIn("profile_url", entries[0].to_dict())

    def test_high_confidence_detection_and_detection_only_platforms(self):
        cases = {
            "https://boards.greenhouse.io/example": ("greenhouse", "example", True),
            "https://jobs.eu.lever.co/acme": ("lever", "acme", True),
            "https://apply.workable.com/rocket/": ("workable", "rocket", True),
            "https://jobs.smartrecruiters.com/ExampleCo": (
                "smartrecruiters",
                "ExampleCo",
                True,
            ),
            "https://example.wd5.myworkdayjobs.com/Careers": (
                "workday",
                "",
                False,
            ),
            "https://jobs.example.successfactors.com/career": (
                "successfactors",
                "",
                False,
            ),
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                result = detect_from_url(url)
                self.assertIsNotNone(result)
                self.assertEqual(
                    (result.provider, result.identifier, result.adapter_ready),
                    expected,
                )
        override = detect_source(
            source_type_label="Greenhouse",
            identifier="manual-token",
            urls=("https://example.com/careers",),
        )
        self.assertEqual(override.identifier, "manual-token")
        self.assertIn("explicit identifier", override.evidence)

    def test_public_http_boundary_blocks_private_redirects_and_access_controls(self):
        with self.assertRaises(PublicSourceError):
            validate_public_https_url(
                "https://private.example/jobs",
                resolver=lambda _host: ["127.0.0.1"],
            )
        with self.assertRaises(PublicSourceError):
            validate_public_https_url(
                "http://public.example/jobs",
                resolver=lambda _host: ["8.8.8.8"],
            )

        requests = []

        def redirect_handler(request):
            requests.append(str(request.url))
            return httpx.Response(302, headers={"location": "https://localhost/private"})

        transport = httpx.Client(
            transport=httpx.MockTransport(redirect_handler),
            follow_redirects=False,
        )
        client = SafeHttpClient(
            client=transport,
            resolver=lambda host: ["127.0.0.1"] if host == "localhost" else ["8.8.8.8"],
        )
        try:
            with self.assertRaises(PublicSourceError):
                client.get("https://public.example/jobs")
        finally:
            transport.close()
        self.assertEqual(len(requests), 1)

        denied, raw = _safe_client(lambda _request: httpx.Response(403))
        try:
            with self.assertRaises(AccessStoppedError):
                denied.get("https://public.example/jobs")
        finally:
            raw.close()

        malformed_size, raw = _safe_client(
            lambda _request: httpx.Response(
                200,
                content=b"safe",
                headers={"content-length": "not-a-number"},
            )
        )
        try:
            with self.assertRaises(PublicSourceError):
                malformed_size.get("https://public.example/jobs")
        finally:
            raw.close()

    def test_all_four_documented_adapters_normalize_public_payloads(self):
        filters = DiscoveryFilters(
            keyword="machine learning",
            posted_within_days=90,
            include_unknown_dates=True,
            max_jobs_per_source=5,
        )
        self.assertIn("apply.workable.com", adapter_for("workable", None).allowed_hosts)

        greenhouse_payload = {
            "jobs": [
                {
                    "id": 1,
                    "title": "Machine Learning Engineer",
                    "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                    "location": {"name": "Hyderabad"},
                    "content": "<p>Build models. 5-8 years of experience.</p>",
                    "departments": [{"name": "AI"}],
                }
            ]
        }
        lever_payload = [
            {
                "id": "lever-1",
                "text": "Machine Learning Engineer",
                "hostedUrl": "https://jobs.lever.co/acme/lever-1",
                "applyUrl": "https://jobs.lever.co/acme/lever-1/apply",
                "descriptionPlain": "Machine learning systems, 5-8 years experience.",
                "categories": {"location": "Bengaluru", "team": "AI"},
            }
        ]
        workable_payload = {
            "jobs": [
                {
                    "id": "workable-1",
                    "shortcode": "ABC",
                    "title": "Machine Learning Engineer",
                    "shortlink": "https://apply.workable.com/acme/j/ABC/",
                    "description": "Machine learning platform; 5-8 years.",
                    "location": {"city": "Remote"},
                }
            ]
        }

        payloads = {
            "greenhouse": greenhouse_payload,
            "lever": lever_payload,
            "workable": workable_payload,
        }
        for provider, payload in payloads.items():
            with self.subTest(provider=provider):
                safe, raw = _safe_client(
                    lambda _request, value=payload: httpx.Response(200, json=value)
                )
                try:
                    source = SourceConfig(
                        company="Acme",
                        provider=provider,
                        identifier="acme",
                    )
                    jobs = adapter_for(provider, safe).fetch(source, filters)
                finally:
                    raw.close()
                self.assertEqual(len(jobs), 1)
                self.assertEqual(jobs[0].source_type, "official_public_api")
                self.assertEqual(jobs[0].experience_min_years, 5)
                self.assertTrue(jobs[0].official_url.startswith("https://"))

        def smart_handler(request):
            if str(request.url).endswith("/postings/smart-1"):
                return httpx.Response(
                    200,
                    json={
                        "jobAdUrl": "https://jobs.smartrecruiters.com/Acme/smart-1",
                        "jobAd": {
                            "sections": {
                                "jobDescription": {
                                    "text": "Machine learning systems. 5-8 years experience."
                                }
                            }
                        },
                    },
                )
            return httpx.Response(
                200,
                json={
                    "content": [
                        {
                            "id": "smart-1",
                            "name": "Machine Learning Engineer",
                            "location": {"city": "Hyderabad", "remote": True},
                        }
                    ],
                    "totalFound": 1,
                },
            )

        safe, raw = _safe_client(smart_handler)
        try:
            jobs = adapter_for("smartrecruiters", safe).fetch(
                SourceConfig(
                    company="Acme",
                    provider="smartrecruiters",
                    identifier="Acme",
                ),
                filters,
            )
        finally:
            raw.close()
        self.assertEqual(len(jobs), 1)
        self.assertIn("Machine learning systems", jobs[0].description)
        self.assertEqual(jobs[0].workplace_type, "remote")

    def test_generic_discovery_uses_json_ld_then_a_bounded_sitemap(self):
        posting = {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": "Machine Learning Engineer",
            "description": "Build ML systems. 5-8 years.",
            "url": "https://careers.example.com/jobs/ml-engineer",
            "jobLocation": {"address": {"addressLocality": "Hyderabad"}},
        }
        html = (
            '<html><script type="application/ld+json">' + json.dumps(posting) + "</script></html>"
        )
        safe, raw = _safe_client(
            lambda _request: httpx.Response(
                200,
                text=html,
                headers={"content-type": "text/html"},
            )
        )
        try:
            source = SourceConfig(
                company="Example",
                provider="generic",
                identifier="example",
                careers_url="https://careers.example.com/jobs",
            )
            jobs, strategy, warning = GenericPublicDiscovery(safe).discover(
                source,
                DiscoveryFilters(keyword="machine learning"),
                discovered_at="2026-08-01T10:00:00+05:30",
            )
        finally:
            raw.close()
        self.assertEqual(strategy, "static_html")
        self.assertEqual(warning, "")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].source_type, "official_static_jsonld")

    def test_generic_next_data_extracts_embedded_public_lever_job(self):
        payload = {
            "props": {
                "pageProps": {
                    "jobs": [
                        {
                            "id": "fund-job-id",
                            "text": "fund settlements",
                            "categories": {
                                "location": "bengaluru",
                                "team": "Kuvera",
                                "commitment": "full time",
                            },
                            "descriptionPlain": "Own fund settlement operations.",
                            "lists": [
                                {
                                    "text": "what we are looking for",
                                    "content": "<ul><li>5+ years in operations</li></ul>",
                                }
                            ],
                            "urls": {
                                "show": "https://jobs.lever.co/cred/fund-job-id",
                                "apply": "https://jobs.lever.co/cred/fund-job-id/apply",
                            },
                            "workplaceType": "onsite",
                        }
                    ]
                }
            }
        }
        html = (
            '<html><script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(payload)
            + "</script></html>"
        )
        safe, raw = _safe_client(
            lambda _request: httpx.Response(
                200,
                text=html,
                headers={"content-type": "text/html"},
            )
        )
        try:
            jobs, strategy, warning = GenericPublicDiscovery(safe).discover(
                SourceConfig(
                    company="CRED",
                    provider="generic",
                    identifier="",
                    careers_url="https://careers.cred.club/openings",
                ),
                DiscoveryFilters(keyword="fund", location="bengaluru"),
                discovered_at="2026-08-20T10:00:00+05:30",
            )
        finally:
            raw.close()
        self.assertEqual(strategy, "embedded_structured_json")
        self.assertEqual(warning, "")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].title, "fund settlements")
        self.assertEqual(jobs[0].provider, "lever")
        self.assertEqual(jobs[0].source_identifier, "cred")
        self.assertEqual(jobs[0].source_type, "official_embedded_ats_json")
        self.assertEqual(jobs[0].experience_text, "5+ years")
        self.assertEqual(
            jobs[0].official_url,
            "https://jobs.lever.co/cred/fund-job-id",
        )


if __name__ == "__main__":
    unittest.main()
