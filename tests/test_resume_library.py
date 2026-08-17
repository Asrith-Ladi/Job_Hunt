import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from job_hunt.gmail_service import AppPaths
from job_hunt.private_io import read_json
from job_hunt.resume_library import DriveResumeLibrary
from tests.docx_fixture import create_resume_docx


class DriveResumeLibraryTests(unittest.TestCase):
    def _library(self, root: Path):
        paths = AppPaths.from_project_root(root)
        library = DriveResumeLibrary(paths, object())
        folders = {
            "root": {"id": "root"},
            "source": {"id": "source"},
            "library": {"id": "library"},
            "baselines": {"id": "baselines"},
            "references": {"id": "references"},
        }
        drive = object()
        library._require_drive = lambda: drive
        library._ensure_folders = lambda _drive: folders

        def load_manifest(_drive, _folders):
            if not library.manifest_cache_path.is_file():
                return {
                    "schema_version": 1,
                    "active_baseline_sha256": "",
                    "baselines": [],
                    "references": [],
                    "confirmed_skill_evidence": [],
                    "artifacts": {},
                    "updated_at": "",
                }, ""
            return read_json(library.manifest_cache_path), "manifest-id"

        library._load_manifest = load_manifest
        return library

    def test_baseline_and_references_are_versioned_and_materialized_by_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library = self._library(root)
            baseline = create_resume_docx(root / "Asrith_Ladi_AI_ML_Resume.docx")
            baseline_bytes = baseline.read_bytes()
            work_reference = (
                b"# Work highlights\n\n"
                b"- Built production Python machine-learning services with AWS and Docker.\n"
            )
            project_reference_path = create_resume_docx(root / "Personal project.docx")
            project_reference = project_reference_path.read_bytes()
            upload_names = []

            def fake_upload(_drive, local_path, **_options):
                name = Path(local_path).name
                upload_names.append(name)
                return {
                    "id": f"id-{len(upload_names)}",
                    "webViewLink": f"https://drive.example/{len(upload_names)}",
                }

            with patch(
                "job_hunt.resume_library.find_child_file",
                return_value=None,
            ), patch(
                "job_hunt.resume_library.upload_or_update_file",
                side_effect=fake_upload,
            ):
                baseline_status = library.store_baseline(
                    baseline_bytes,
                    "Asrith_Ladi_AI_ML_Resume.docx",
                )
                reference_status = library.store_references(
                    [
                        ("WORK_HIGHLIGHTS.md", work_reference),
                        ("Personal project.docx", project_reference),
                    ]
                )
                # Reusing identical baseline bytes updates only the active manifest.
                library.store_baseline(
                    baseline_bytes,
                    "Asrith_Ladi_AI_ML_Resume.docx",
                )
                evidence_status = library.store_confirmed_skill_evidence(
                    [
                        {
                            "skill": "Context engineering",
                            "note": "Designed retrieval context for a production agent workflow.",
                        }
                    ]
                )
                materialized = library.materialize_inputs()

            expected_baseline_hash = hashlib.sha256(baseline_bytes).hexdigest()
            self.assertTrue(baseline_status["baseline_immutable"])
            self.assertEqual(
                reference_status["baseline_resume_sha256"],
                expected_baseline_hash,
            )
            self.assertEqual(reference_status["reference_document_count"], 2)
            self.assertEqual(evidence_status["confirmed_skill_evidence_count"], 1)
            self.assertEqual(
                evidence_status["confirmed_skill_evidence"][0]["skill"],
                "Context engineering",
            )
            self.assertEqual(
                Path(materialized["baseline_path"]).read_bytes(),
                baseline_bytes,
            )
            self.assertEqual(len(materialized["references"]), 2)
            self.assertEqual(len(materialized["reference_digest"]), 64)
            self.assertEqual(
                len([name for name in upload_names if name.startswith("base_")]),
                1,
            )
            self.assertEqual(
                len([name for name in upload_names if name.startswith("ref_")]),
                2,
            )

    def test_invalid_input_types_are_rejected_before_drive_use(self):
        with tempfile.TemporaryDirectory() as temporary:
            library = self._library(Path(temporary))
            with self.assertRaisesRegex(ValueError, "DOCX"):
                library.store_baseline(b"plain text", "resume.txt")
            with self.assertRaisesRegex(ValueError, "Reference files"):
                library.store_references([("reference.pdf", b"%PDF")])


if __name__ == "__main__":
    unittest.main()
