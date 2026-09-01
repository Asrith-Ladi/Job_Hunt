import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from job_hunt.api.main import create_app


RUN = {
    "run_id": "company_portals-test",
    "mode": "company_portals",
    "run_started_at": "2026-08-01T12:00:00+05:30",
    "file_name": "company_portals_2026-08-01_120000.xlsx",
    "drive_url": "https://drive.google.com/file/d/test/view",
    "summary": {"sources_checked": 1, "jobs_found": 1},
    "rows": [{"job_record_id": "job-1", "application_status": "not_started"}],
    "source_checks": [{"company": "Example", "status": "success"}],
    "job_columns": ["job_record_id", "application_status"],
    "editable_columns": ["application_status", "notes"],
    "application_statuses": ["not_started", "reviewing"],
    "experience_fit_statuses": ["unknown"],
}


class _Connection:
    frontend_url = "http://localhost:8000"

    def status(self):
        return {
            "connected": True,
            "credentials_file_available": True,
            "reconnect_required": False,
            "message": "connected",
            "redirect_uri": "http://localhost:8000/api/auth/google/callback",
        }

    def start(self):
        return {"authorization_url": "https://accounts.google.com/example"}

    def complete(self, **_kwargs):
        return None

    def discard_pending(self, _state):
        return None


class _Gmail:
    def defaults(self):
        return {
            "source_tabs": [
                "run_setup",
                "job_queue",
                "applications",
                "network_reviews",
            ]
        }

    def workspace(self):
        return {"root_url": "", "source_url": ""}

    def latest(self):
        return None


class _Discovery:
    def __init__(self, workbook):
        self.workbook = workbook
        self.last_options = None

    def registry(self):
        return [
            {
                "company_id": "company-1",
                "company": "Example",
                "adapter_ready": True,
            }
        ]

    def registry_snapshot(self):
        companies = self.registry()
        return {
            "companies": companies,
            "count": len(companies),
            "registry_status": {
                "sync_status": "drive_current",
                "source": "google_drive",
                "warning": "",
                "drive_url": "https://drive.example/registry",
                "drive_modified_time": "2026-08-20T10:00:00Z",
                "synced_at": "2026-08-20T10:00:01Z",
            },
        }

    def latest(self, mode):
        value = dict(RUN)
        value["mode"] = mode
        return value

    def run(self, options):
        self.last_options = options
        value = dict(RUN)
        value["mode"] = options.mode
        return value

    def search(self, options, *, progress_callback=None):
        self.last_options = options
        if progress_callback:
            progress_callback(
                {
                    "stage": "source_complete",
                    "message": "Example: 4 extracted → 1 matched via greenhouse.",
                    "current_item": "Example",
                    "completed_items": 1,
                    "total_items": 1,
                    "matches_found": 1,
                }
            )
        value = dict(RUN)
        value.update({
            "mode": options.mode,
            "file_name": "",
            "drive_url": "",
            "transient": True,
        })
        return value

    def get(self, mode, run_id):
        if run_id != "company_portals-test":
            raise FileNotFoundError("missing")
        value = dict(RUN)
        value["mode"] = mode
        return value

    def save(self, mode, run_id, rows):
        value = self.get(mode, run_id)
        value["rows"] = list(rows)
        return value

    def workbook_path(self, _mode, _run_id):
        return self.workbook


class DiscoveryApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        workbook = root / "run.xlsx"
        workbook.write_bytes(b"workbook")
        self.discovery = _Discovery(workbook)
        self.client = TestClient(
            create_app(
                gmail_service=_Gmail(),
                discovery_service=self.discovery,
                google_connection=_Connection(),
                static_dir=root / "missing",
            )
        )

    def tearDown(self):
        self.client.close()
        self.temporary.cleanup()

    def test_registry_detection_and_both_latest_routes(self):
        registry = self.client.get("/api/registry/companies")
        self.assertEqual(registry.status_code, 200)
        self.assertEqual(registry.json()["count"], 1)
        self.assertEqual(registry.json()["registry_status"]["source"], "google_drive")
        detection = self.client.post(
            "/api/sources/detect",
            json={"careers_url": "https://jobs.lever.co/example"},
        )
        self.assertEqual(detection.status_code, 200)
        self.assertEqual(detection.json()["detection"]["provider"], "lever")
        self.assertTrue(self.client.get("/api/company-portals/runs/latest").json()["run"])
        self.assertEqual(
            self.client.get("/api/ats-sources/runs/latest").json()["run"]["mode"],
            "ats_sources",
        )

    def test_company_and_manual_ats_requests_map_to_separate_modes(self):
        company = self.client.post(
            "/api/search/company-portals",
            json={"company_ids": ["company-1"], "filters": {"keyword": "ML"}},
        )
        self.assertEqual(company.status_code, 200)
        self.assertEqual(self.discovery.last_options.mode, "company_portals")
        self.assertEqual(self.discovery.last_options.filters.keyword, "ML")

        ats = self.client.post(
            "/api/search/ats-sources",
            json={
                "company_ids": [],
                "manual_sources": [
                    {
                        "company": "Acme",
                        "provider": "lever",
                        "identifier": "acme",
                        "region": "eu",
                    }
                ],
            },
        )
        self.assertEqual(ats.status_code, 200)
        self.assertEqual(self.discovery.last_options.mode, "ats_sources")
        self.assertEqual(self.discovery.last_options.manual_sources[0].region, "eu")

        self.assertTrue(ats.json()["run"]["transient"])
        self.assertEqual(ats.json()["run"]["file_name"], "")

    def test_company_search_exposes_source_level_progress(self):
        progress_id = "company-progress-test-123"
        response = self.client.post(
            "/api/search/company-portals",
            headers={"X-Job-Hunt-Progress-ID": progress_id},
            json={"company_ids": ["company-1"]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["progress"]["status"], "completed")
        progress = self.client.get(f"/api/search/progress/{progress_id}").json()["progress"]
        self.assertEqual(progress["source"], "company_portals")
        self.assertEqual(progress["completed_items"], 1)
        self.assertTrue(
            any(event["stage"] == "source_complete" for event in progress["recent_events"])
        )

    def test_source_limits_legacy_write_disable_and_download_identity(self):
        too_many = self.client.post(
            "/api/search/company-portals",
            json={"company_ids": [f"company-{index}" for index in range(11)]},
        )
        self.assertEqual(too_many.status_code, 422)
        disabled = self.client.put(
            "/api/company-portals/runs/company_portals-test/jobs",
            json={"rows": [{"job_record_id": "job-1", "application_status": "reviewing"}]},
        )
        self.assertEqual(disabled.status_code, 404)
        download = self.client.get("/api/company-portals/runs/company_portals-test/download")
        self.assertEqual(download.content, b"workbook")


if __name__ == "__main__":
    unittest.main()
