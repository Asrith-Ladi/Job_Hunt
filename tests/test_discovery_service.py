import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from job_hunt.discovery.detection import DetectionResult
from job_hunt.discovery.http_client import SafeHttpClient
from job_hunt.discovery.models import DiscoveryFilters
from job_hunt.discovery.registry import CompanyRegistryEntry
from job_hunt.discovery.service import (
    COMPANY_PORTALS,
    DiscoveryRunOptions,
    DiscoveryWorkflowService,
)
from job_hunt.gmail_service import AppPaths


class _Connection:
    def require_credentials(self):
        return object()


def _entry():
    return CompanyRegistryEntry(
        company_id="company-1",
        company="Example",
        category="Product Companies",
        sector="Software",
        priority="High",
        careers_url="https://boards.greenhouse.io/example",
        portal_url="https://boards.greenhouse.io/example",
        source_type_label="Greenhouse",
        source_identifier="example",
        public_feed_url=("https://boards-api.greenhouse.io/v1/boards/example/jobs?content=true"),
        api_key_required="No",
        india_jobs="Yes",
        active="Yes",
        last_checked="2026-08-01",
        verification_status="Verified",
        fallback="hosted board",
        notes="",
        detection=DetectionResult(
            provider="greenhouse",
            identifier="example",
            confidence=0.99,
            official_public_api=True,
            adapter_ready=True,
            evidence="test",
            risk="low",
            fallback="hosted board",
        ),
    )


class DiscoveryServiceTests(unittest.TestCase):
    def test_company_run_save_and_cross_run_incremental_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry_path = root / "Company_Source_Registry.xlsx"
            registry_path.write_bytes(b"registry")
            paths = AppPaths(
                project_root=root,
                run_output_root=root / "outputs" / "gmail_runs",
                registry_path=registry_path,
                secrets_root=root / ".secrets",
            )
            payload = {
                "jobs": [
                    {
                        "id": 1,
                        "title": "Machine Learning Engineer",
                        "absolute_url": "https://boards.greenhouse.io/example/jobs/1",
                        "location": {"name": "Hyderabad"},
                        "content": "5-8 years building machine learning systems.",
                    }
                ]
            }
            raw = httpx.Client(
                transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=payload)),
                follow_redirects=False,
            )
            service = DiscoveryWorkflowService(
                paths,
                _Connection(),
                registry_loader=lambda _path: [_entry()],
                http_client_factory=lambda: SafeHttpClient(
                    client=raw,
                    resolver=lambda _host: ["8.8.8.8"],
                ),
                drive_service_factory=lambda _credentials: object(),
            )

            folders = {
                "root": {"id": "root"},
                "source": {"id": "source"},
                "date": {"id": "date"},
            }

            def upload(_drive, local_path, **_kwargs):
                return {
                    "id": f"id-{Path(local_path).name}",
                    "webViewLink": "https://drive.google.com/file/d/test/view",
                }

            options = DiscoveryRunOptions(
                mode=COMPANY_PORTALS,
                company_ids=("company-1",),
                filters=DiscoveryFilters(keyword="machine learning"),
            )
            try:
                with (
                    patch(
                        "job_hunt.discovery.service.ensure_job_hunt_folders",
                        return_value=folders,
                    ),
                    patch(
                        "job_hunt.discovery.service.find_child_file",
                        return_value=None,
                    ),
                    patch(
                        "job_hunt.discovery.service.upload_or_update_file",
                        side_effect=upload,
                    ),
                ):
                    first = service.run(options)
                    self.assertEqual(len(first["rows"]), 1)
                    self.assertEqual(first["source_checks"][0]["status"], "success")
                    self.assertTrue((root / "outputs" / "company_portal_runs").is_dir())
                    latest = service.latest(COMPANY_PORTALS)
                    self.assertEqual(latest["run_id"], first["run_id"])

                    edited = [dict(first["rows"][0])]
                    edited[0]["application_status"] = "reviewing"
                    edited[0]["notes"] = "Apply after review"
                    saved = service.save(COMPANY_PORTALS, first["run_id"], edited)
                    self.assertEqual(saved["rows"][0]["notes"], "Apply after review")

                    second = service.run(options)
                    self.assertEqual(second["rows"], [])
                    self.assertEqual(
                        second["summary"]["jobs_unchanged_from_prior_runs"],
                        1,
                    )
            finally:
                raw.close()


if __name__ == "__main__":
    unittest.main()
