import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import create_app


RUN = {
    "run_id": "run_test",
    "run_started_at": "2026-08-01T12:00:00+05:30",
    "file_name": "gmail_alerts_2026-08-01_120000.xlsx",
    "drive_url": "https://drive.google.com/file/d/test/view",
    "summary": {"run_id": "run_test", "messages_read": 2},
    "rows": [{"job_record_id": "job-1", "company": "Example"}],
    "job_columns": ["job_record_id", "company"],
    "editable_columns": ["company"],
    "application_statuses": ["not_started"],
    "experience_fit_statuses": ["unknown"],
}


class _FakeConnection:
    frontend_url = "http://localhost:8000"

    def __init__(self):
        self.completed = False
        self.discarded = False

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

    def complete(self, *, code, state):
        self.completed = bool(code and state)

    def discard_pending(self, state):
        self.discarded = bool(state)


class _FakeWorkflow:
    def __init__(self, workbook_path):
        self.workbook_path_value = workbook_path
        self.last_options = None

    def defaults(self):
        return {
            "source_tabs": [
                "run_setup",
                "job_queue",
                "network_reviews",
            ]
        }

    def workspace(self):
        return {"root_url": "", "source_url": ""}

    def latest(self):
        return dict(RUN)

    def run(self, options):
        self.last_options = options
        return dict(RUN)

    def get(self, run_id):
        if run_id != "run_test":
            raise FileNotFoundError("missing")
        return dict(RUN)

    def save(self, run_id, rows):
        result = dict(RUN)
        result["rows"] = list(rows)
        return result

    def workbook_path(self, run_id):
        if run_id != "run_test":
            raise FileNotFoundError("missing")
        return self.workbook_path_value


class _FakeNetwork:
    def search(self, **options):
        return {
            "rows": [
                {
                    "connection_id": "connection-1",
                    "name": "Asha Leader",
                    "first_name": "Asha",
                    "current_company": "Example",
                    "company": "Example",
                    "position": "Director of Machine Learning",
                    "email_address": "asha@example.com",
                    "linkedin_profile": "https://www.linkedin.com/in/asha",
                    "connected_on": "2025-01-01",
                    "registry_company": "Example",
                    "registry_category": "Product",
                    "referral_status": "Target-company connection",
                    "match_method": "Exact",
                    "official_careers_page": "https://example.com/careers",
                    "direct_job_portal": "https://example.com/jobs",
                    "relevance_score": 100,
                    "category": "AI/ML leadership",
                    "recommended": True,
                    "leadership": True,
                    "relevance_reason": "Relevant leader",
                    "profile_review_message": "Hi Asha",
                }
            ],
            "total_matching": 1,
            "offset": options.get("offset", 0),
            "limit": options.get("limit", 50),
            "all_connections": 1,
            "all_profiles": 1,
            "email_connections": 1,
            "recommended_profiles": 1,
            "leadership_profiles": 1,
            "categories": ["AI/ML leadership"],
            "target_roles": options.get("target_roles", ""),
            "source": "offline_linkedin_export",
        }


class _FakeIntelligence:
    def __init__(self, root: Path):
        self.root = root
        self.generated = root / "tailored.docx"
        self.generated.write_bytes(b"tailored-resume")
        self.uploaded_bytes = b""
        self.uploaded_name = ""
        self.reference_files = []
        self.analyzed_job = None
        self.generation_options = {}

    def status(self):
        return {
            "openai_configured": True,
            "model": "gpt-test",
            "configuration_source": "test",
            "drive_connected": True,
            "drive_backed": True,
            "baseline_resume_configured": True,
            "baseline_resume_name": "base_resume.docx",
            "baseline_resume_sha256": "a" * 64,
            "baseline_uploaded_at": "2026-08-04T12:00:00+05:30",
            "baseline_drive_url": "https://drive.example/baseline",
            "baseline_immutable": True,
            "reference_documents": [],
            "reference_document_count": 0,
            "confirmed_skill_evidence": [],
            "confirmed_skill_evidence_count": 0,
            "library_url": "https://drive.example/library",
            "message": "",
            "manual_only": True,
            "contact_data_sent_to_openai": False,
        }

    def store_baseline_resume(self, content, original_name):
        self.uploaded_bytes = bytes(content)
        self.uploaded_name = original_name
        return self.status()

    def store_reference_documents(self, files):
        self.reference_files = [(name, bytes(content)) for name, content in files]
        value = self.status()
        value["reference_document_count"] = len(self.reference_files)
        return value

    def analyze(self, job, *, refresh=False):
        self.analyzed_job = dict(job)
        return {
            "analysis_id": "analysis_example123",
            "status": "completed",
            "job": dict(job),
            "candidates": [],
            "verified_at": "2026-08-03",
            "model": "gpt-test",
            "cached": not refresh,
            "research_stats": {"api_calls": int(refresh)},
            "baseline_resume_configured": True,
            "privacy": {
                "gmail_content_sent": False,
                "contact_data_sent": False,
                "connection_data_sent": False,
                "reference_evidence_sent": False,
            },
        }

    def generate_documents(self, analysis_id, official_job_id, **options):
        self.generation_options = dict(options)
        return {
            "generation_id": "generation_example123",
            "generated_at": "2026-08-03T12:00:00+05:30",
            "artifacts": [
                {
                    "artifact_id": "artifact_example123",
                    "kind": "resume_docx",
                    "file_name": self.generated.name,
                    "mime_type": (
                        "application/vnd.openxmlformats-officedocument."
                        "wordprocessingml.document"
                    ),
                    "drive_url": "https://drive.example/tailored",
                    "folder_url": "https://drive.example/Resumes",
                }
            ],
            "model": "gpt-test",
            "plan_cached": False,
            "change_notes": [],
            "keyword_alignment": [],
            "confirmed_skills_added": [],
            "reference_points_used": [],
            "warnings": [],
            "requires_user_review": True,
            "baseline_unchanged": True,
        }

    def artifact(self, artifact_id):
        if artifact_id != "artifact_example123":
            raise FileNotFoundError("missing")
        return self.generated, {
            "file_name": self.generated.name,
            "mime_type": (
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
        }


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        workbook = root / "gmail.xlsx"
        workbook.write_bytes(b"workbook")
        self.connection = _FakeConnection()
        self.workflow = _FakeWorkflow(workbook)
        self.intelligence = _FakeIntelligence(root)
        self.client = TestClient(
            create_app(
                gmail_service=self.workflow,
                google_connection=self.connection,
                network_service=_FakeNetwork(),
                job_intelligence_service=self.intelligence,
                static_dir=root / "missing-dist",
            )
        )

    def tearDown(self):
        self.client.close()
        self.temporary.cleanup()

    def test_health_config_and_connection_status(self):
        self.assertEqual(self.client.get("/api/health").json(), {"status": "ok"})
        self.assertEqual(
            self.client.get("/api/config").json()["source_tabs"],
            ["run_setup", "job_queue", "network_reviews"],
        )
        self.assertTrue(self.client.get("/api/auth/google/status").json()["connected"])

    def test_network_connections_are_served_from_the_offline_service(self):
        response = self.client.get(
            "/api/network/connections",
            params={
                "target_roles": "Generative AI Engineer",
                "leadership_only": "true",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["rows"][0]["name"], "Asha Leader")
        self.assertEqual(response.json()["rows"][0]["email_address"], "asha@example.com")
        self.assertEqual(response.json()["all_connections"], 1)
        self.assertEqual(response.json()["target_roles"], "Generative AI Engineer")

    def test_run_request_maps_to_the_python_service(self):
        response = self.client.post(
            "/api/gmail/runs",
            json={
                "sources": ["linkedin"],
                "labels_by_source": {"linkedin": "Job_Alerts/link_test"},
                "lookback_days": 7,
                "max_messages": 25,
                "target_experience_min_years": 5,
                "target_experience_max_years": 8,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["run"]["run_id"], "run_test")
        self.assertEqual(self.workflow.last_options.lookback_days, 7)
        self.assertEqual(self.workflow.last_options.sources, ("linkedin",))

    def test_invalid_experience_range_is_rejected_before_a_run(self):
        response = self.client.post(
            "/api/gmail/runs",
            json={
                "sources": ["linkedin"],
                "target_experience_min_years": 8,
                "target_experience_max_years": 5,
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertIsNone(self.workflow.last_options)

    def test_edit_and_download_routes_keep_the_run_identity(self):
        saved = self.client.put(
            "/api/gmail/runs/run_test/jobs",
            json={"rows": [{"job_record_id": "job-1", "company": "Edited"}]},
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["run"]["rows"][0]["company"], "Edited")

        download = self.client.get("/api/gmail/runs/run_test/download")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, b"workbook")

    def test_oauth_callback_redirects_without_exposing_callback_values(self):
        response = self.client.get(
            "/api/auth/google/callback?code=secret-code&state=state-value",
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "http://localhost:8000/?google=connected")
        self.assertTrue(self.connection.completed)

    def test_manual_job_intelligence_routes_keep_secrets_server_side(self):
        status = self.client.get("/api/job-intelligence/status")
        self.assertEqual(status.status_code, 200)
        self.assertTrue(status.json()["openai_configured"])
        self.assertNotIn("api_key", status.json())

        analyzed = self.client.post(
            "/api/job-intelligence/analyze",
            json={
                "job": {
                    "job_record_id": "job-1",
                    "company": "Example",
                    "title": "ML Engineer",
                    "location": "Hyderabad",
                }
            },
        )
        self.assertEqual(analyzed.status_code, 200)
        self.assertEqual(analyzed.json()["analysis"]["analysis_id"], "analysis_example123")
        self.assertEqual(self.intelligence.analyzed_job["company"], "Example")

        uploaded = self.client.post(
            "/api/job-intelligence/baseline-resume",
            files={
                "file": (
                    "resume.docx",
                    b"private-docx",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        self.assertEqual(uploaded.status_code, 200)
        self.assertEqual(self.intelligence.uploaded_bytes, b"private-docx")
        self.assertEqual(self.intelligence.uploaded_name, "resume.docx")

        references = self.client.post(
            "/api/job-intelligence/reference-documents",
            files=[
                ("files", ("WORK_HIGHLIGHTS.md", b"verified work", "text/markdown")),
                (
                    "files",
                    (
                        "project.docx",
                        b"verified project",
                        "application/vnd.openxmlformats-officedocument."
                        "wordprocessingml.document",
                    ),
                ),
            ],
        )
        self.assertEqual(references.status_code, 200)
        self.assertEqual(
            [name for name, _content in self.intelligence.reference_files],
            ["WORK_HIGHLIGHTS.md", "project.docx"],
        )

        generated = self.client.post(
            "/api/job-intelligence/resumes",
            json={
                "analysis_id": "analysis_example123",
                "official_job_id": "official_example123",
                "outputs": ["resume_docx", "resume_pdf", "cover_letter"],
                "confirmed_skill_evidence": [
                    {
                        "skill": "Context engineering",
                        "note": "Designed and tested retrieval context for an internal agent workflow.",
                        "confirmed": True,
                    }
                ],
            },
        )
        self.assertEqual(generated.status_code, 200)
        self.assertEqual(
            generated.json()["generation"]["artifacts"][0]["download_url"],
            "/api/job-intelligence/artifacts/artifact_example123/download",
        )
        self.assertEqual(
            self.intelligence.generation_options["confirmed_skill_evidence"][0]["skill"],
            "Context engineering",
        )
        download = self.client.get(
            "/api/job-intelligence/artifacts/artifact_example123/download"
        )
        self.assertEqual(download.content, b"tailored-resume")


if __name__ == "__main__":
    unittest.main()
