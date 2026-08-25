import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from job_hunt.runtime.application_queue import ApplicationQueueService
from job_hunt.runtime.files import read_json
from job_hunt.runtime.paths import AppPaths


class _Connection:
    def require_credentials(self):
        return object()


class ApplicationQueueTests(unittest.TestCase):
    def test_explicit_updates_create_one_deduplicated_drive_record(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = AppPaths.from_project_root(Path(directory))
            service = ApplicationQueueService(
                paths,
                _Connection(),
                drive_service_factory=lambda _credentials: object(),
            )
            uploads = []

            def upload(_drive, local_path, **_kwargs):
                uploads.append(Path(local_path).read_text(encoding="utf-8"))
                return {
                    "id": "application-queue-file",
                    "webViewLink": "https://drive.example/application-queue",
                }

            folders = {"root": {"id": "root"}, "source": {"id": "source"}}
            row = {
                "job_record_id": "job-1",
                "company": "Example",
                "title": "ML Engineer",
                "application_status": "saved",
                "notes": "",
            }
            with (
                patch(
                    "job_hunt.runtime.application_queue.ensure_job_hunt_folders",
                    return_value=folders,
                ),
                patch(
                    "job_hunt.runtime.application_queue.find_child_file",
                    return_value=None,
                ),
                patch(
                    "job_hunt.runtime.application_queue.upload_or_update_file",
                    side_effect=upload,
                ),
            ):
                first = service.upsert("company_portals", row)
                row["application_status"] = "applied"
                row["notes"] = "Submitted manually"
                second = service.upsert("company_portals", row)
                listed = service.list()

            self.assertEqual(first["application"]["application_id"], second["application"]["application_id"])
            self.assertEqual(second["count"], 1)
            self.assertEqual(listed["count"], 1)
            self.assertEqual(listed["applications"][0]["row"]["application_status"], "applied")
            self.assertEqual(listed["applications"][0]["row"]["notes"], "Submitted manually")
            self.assertEqual(len(uploads), 2)
            self.assertFalse((paths.project_root / "outputs").exists())

    def test_nested_or_unidentifiable_rows_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = AppPaths.from_project_root(Path(directory))
            service = ApplicationQueueService(paths, _Connection())
            with self.assertRaises(ValueError):
                service.upsert("gmail", {"job_record_id": "job-1", "nested": {"raw": "mail"}})

    def test_failed_first_drive_upload_does_not_appear_as_persisted_local_state(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = AppPaths.from_project_root(Path(directory))
            service = ApplicationQueueService(
                paths,
                _Connection(),
                drive_service_factory=lambda _credentials: object(),
            )
            folders = {"root": {"id": "root"}, "source": {"id": "source"}}
            with (
                patch(
                    "job_hunt.runtime.application_queue.ensure_job_hunt_folders",
                    return_value=folders,
                ),
                patch(
                    "job_hunt.runtime.application_queue.find_child_file",
                    return_value=None,
                ),
                patch(
                    "job_hunt.runtime.application_queue.upload_or_update_file",
                    side_effect=OSError("Drive unavailable"),
                ),
            ):
                with self.assertRaises(OSError):
                    service.upsert(
                        "gmail",
                        {
                            "job_record_id": "job-1",
                            "company": "Example",
                            "application_status": "saved",
                        },
                    )

            value = read_json(paths.application_queue_path)
            self.assertEqual(value["applications"], {})


if __name__ == "__main__":
    unittest.main()
