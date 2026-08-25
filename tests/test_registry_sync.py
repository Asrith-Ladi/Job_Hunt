import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from job_hunt.discovery.registry import CompanyRegistryRepository
from job_hunt.runtime.paths import AppPaths, REGISTRY_FILE_NAME


class _Connection:
    def require_credentials(self):
        return object()


def _paths(root: Path) -> AppPaths:
    return AppPaths(
        project_root=root,
        run_output_root=root / "outputs" / "gmail_runs",
        registry_path=root / ".runtime" / "source_cache" / REGISTRY_FILE_NAME,
        runtime_root=root / ".runtime",
    )


def _loader(path: Path):
    value = Path(path).read_bytes()
    if value == b"invalid":
        raise ValueError("invalid registry")
    return [value.decode("utf-8")]


class RegistrySyncTests(unittest.TestCase):
    def test_changed_drive_registry_replaces_validated_local_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = _paths(Path(directory))
            paths.registry_path.parent.mkdir(parents=True)
            paths.registry_path.write_bytes(b"old")
            remote = {
                "id": "registry-id",
                "webViewLink": "https://drive.example/registry",
                "modifiedTime": "2026-08-20T10:00:00Z",
                "md5Checksum": hashlib.md5(b"new", usedforsecurity=False).hexdigest(),
            }

            def download(_drive, _file_id, output_path):
                Path(output_path).write_bytes(b"new")

            repository = CompanyRegistryRepository(
                paths,
                _Connection(),
                registry_loader=_loader,
                drive_service_factory=lambda _credentials: object(),
            )
            with (
                patch(
                    "job_hunt.discovery.registry.ensure_job_hunt_folders",
                    return_value={"source": {"id": "source-id"}},
                ),
                patch("job_hunt.discovery.registry.find_child_file", return_value=remote),
                patch("job_hunt.discovery.registry.download_drive_file", side_effect=download),
                patch("job_hunt.discovery.registry.upload_or_update_file") as upload,
            ):
                snapshot = repository.load()

            self.assertEqual(snapshot.entries, ["new"])
            self.assertEqual(snapshot.sync_status, "drive_refreshed")
            self.assertEqual(snapshot.source, "google_drive")
            self.assertEqual(paths.registry_path.read_bytes(), b"new")
            upload.assert_not_called()

    def test_unchanged_drive_registry_reuses_cache_without_download(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = _paths(Path(directory))
            paths.registry_path.parent.mkdir(parents=True)
            paths.registry_path.write_bytes(b"same")
            remote = {
                "id": "registry-id",
                "modifiedTime": "2026-08-20T10:00:00Z",
                "md5Checksum": hashlib.md5(b"same", usedforsecurity=False).hexdigest(),
            }
            repository = CompanyRegistryRepository(
                paths,
                _Connection(),
                registry_loader=_loader,
                drive_service_factory=lambda _credentials: object(),
            )
            with (
                patch(
                    "job_hunt.discovery.registry.ensure_job_hunt_folders",
                    return_value={"source": {"id": "source-id"}},
                ),
                patch("job_hunt.discovery.registry.find_child_file", return_value=remote),
                patch("job_hunt.discovery.registry.download_drive_file") as download,
            ):
                snapshot = repository.load()

            self.assertEqual(snapshot.entries, ["same"])
            self.assertEqual(snapshot.sync_status, "drive_current")
            download.assert_not_called()

    def test_invalid_drive_registry_keeps_last_validated_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = _paths(Path(directory))
            paths.registry_path.parent.mkdir(parents=True)
            paths.registry_path.write_bytes(b"valid")
            remote = {
                "id": "registry-id",
                "modifiedTime": "2026-08-20T10:00:00Z",
                "md5Checksum": hashlib.md5(b"invalid", usedforsecurity=False).hexdigest(),
            }

            def download(_drive, _file_id, output_path):
                Path(output_path).write_bytes(b"invalid")

            repository = CompanyRegistryRepository(
                paths,
                _Connection(),
                registry_loader=_loader,
                drive_service_factory=lambda _credentials: object(),
            )
            with (
                patch(
                    "job_hunt.discovery.registry.ensure_job_hunt_folders",
                    return_value={"source": {"id": "source-id"}},
                ),
                patch("job_hunt.discovery.registry.find_child_file", return_value=remote),
                patch("job_hunt.discovery.registry.download_drive_file", side_effect=download),
            ):
                snapshot = repository.load()

            self.assertEqual(snapshot.entries, ["valid"])
            self.assertEqual(snapshot.sync_status, "local_fallback")
            self.assertIn("failed download or validation", snapshot.warning)
            self.assertEqual(paths.registry_path.read_bytes(), b"valid")


if __name__ == "__main__":
    unittest.main()
