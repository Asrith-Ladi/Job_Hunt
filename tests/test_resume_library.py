import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from job_hunt.runtime.paths import AppPaths
from job_hunt.runtime.files import read_json
from job_hunt.resumes.library import DriveResumeLibrary
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
                "job_hunt.resumes.library.find_child_file",
                return_value=None,
            ), patch(
                "job_hunt.resumes.library.upload_or_update_file",
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

    def test_generated_documents_use_company_first_application_folders(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library = self._library(root)
            artifact = root / "Asrith_Ladi_AI_ML_Engineer_6Y.docx"
            artifact.write_bytes(b"generated-resume")
            folder_calls = []

            def fake_ensure_folder(_drive, name, *, parent_id=None):
                folder_calls.append((name, parent_id))
                return {"id": f"folder-{len(folder_calls)}", "name": name}

            with patch(
                "job_hunt.resumes.library.ensure_job_hunt_folders",
                return_value={"root": {"id": "job-hunt"}, "source": {"id": "source"}},
            ), patch(
                "job_hunt.resumes.library.ensure_folder",
                side_effect=fake_ensure_folder,
            ), patch(
                "job_hunt.resumes.library.upload_or_update_file",
                return_value={"id": "resume-file", "webViewLink": "https://drive.example/file"},
            ) as upload:
                result = library.upload_artifact(
                    artifact,
                    company_name="Sarvam AI",
                    role_name="Agent Engineer / Platform",
                    prepared_on="2026-08-17",
                    mime_type=(
                        "application/vnd.openxmlformats-officedocument."
                        "wordprocessingml.document"
                    ),
                )

            self.assertEqual(
                folder_calls,
                [
                    ("Resumes", "job-hunt"),
                    ("Sarvam AI", "folder-1"),
                    ("2026-08-17_Agent_Engineer_Platform", "folder-2"),
                ],
            )
            self.assertEqual(upload.call_args.kwargs["parent_id"], "folder-3")
            self.assertEqual(
                result["folder_path"],
                "Job Hunt/Resumes/Sarvam AI/2026-08-17_Agent_Engineer_Platform",
            )
            self.assertEqual(result["folder_url"], "https://drive.google.com/drive/folders/folder-3")

            with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
                library.upload_artifact(
                    artifact,
                    company_name="Sarvam AI",
                    role_name="Agent Engineer",
                    prepared_on="17-08-2026",
                    mime_type="application/test",
                )


if __name__ == "__main__":
    unittest.main()
