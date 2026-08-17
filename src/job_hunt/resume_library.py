"""Drive-backed immutable resume inputs and generated-document records."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from job_hunt.gmail_service import AppPaths, GoogleConnectionService, TIME_ZONE
from job_hunt.integrations.drive_storage import (
    build_drive_service,
    download_drive_file,
    drive_file_url,
    drive_folder_url,
    ensure_folder,
    ensure_job_hunt_folders,
    find_child_file,
    upload_or_update_file,
)
from job_hunt.private_io import read_json, write_json_atomic
from job_hunt.resume_docx import (
    extract_resume_evidence,
    resume_sha256,
    validate_resume_docx,
    validate_resume_upload,
)


DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MIME_TYPE = "application/pdf"
MARKDOWN_MIME_TYPE = "text/markdown"
JSON_MIME_TYPE = "application/json"

LIBRARY_FOLDER_NAME = "Resume Library"
BASELINES_FOLDER_NAME = "Baselines"
REFERENCES_FOLDER_NAME = "References"
MANIFEST_NAME = "resume_library.json"
MANIFEST_VERSION = 2
MAX_REFERENCE_BYTES = 8 * 1024 * 1024
MAX_REFERENCE_FILES = 20
MAX_CONFIRMED_SKILL_EVIDENCE = 200


class ResumeLibraryError(RuntimeError):
    """Raised when a Drive-backed resume-library action cannot be completed."""


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _safe_original_name(value: object, fallback: str) -> str:
    name = Path(str(value or "").strip()).name
    name = re.sub(r"[\x00-\x1f<>:\"/\\|?*]+", "_", name).strip(" .")
    return (name[:160] or fallback).strip(" .")


def _safe_cache_name(sha256: str, original_name: str) -> str:
    suffix = Path(original_name).suffix.casefold()
    return f"{sha256}{suffix}"


def _default_manifest() -> dict[str, Any]:
    return {
        "schema_version": MANIFEST_VERSION,
        "active_baseline_sha256": "",
        "baselines": [],
        "references": [],
        "confirmed_skill_evidence": [],
        "artifacts": {},
        "updated_at": "",
    }


def _normalize_manifest(value: object) -> dict[str, Any]:
    source = dict(value) if isinstance(value, Mapping) else {}
    manifest = _default_manifest()
    manifest["active_baseline_sha256"] = str(
        source.get("active_baseline_sha256") or ""
    ).strip()
    manifest["baselines"] = [
        dict(item) for item in source.get("baselines") or [] if isinstance(item, Mapping)
    ][-50:]
    manifest["references"] = [
        dict(item) for item in source.get("references") or [] if isinstance(item, Mapping)
    ][:MAX_REFERENCE_FILES]
    manifest["confirmed_skill_evidence"] = [
        {
            "skill": str(item.get("skill") or "").strip()[:120],
            "note": str(item.get("note") or "").strip()[:1200],
            "confirmed_at": str(item.get("confirmed_at") or ""),
        }
        for item in source.get("confirmed_skill_evidence") or []
        if isinstance(item, Mapping)
        and str(item.get("skill") or "").strip()
        and str(item.get("note") or "").strip()
    ][-MAX_CONFIRMED_SKILL_EVIDENCE:]
    manifest["artifacts"] = {
        str(key): dict(item)
        for key, item in dict(source.get("artifacts") or {}).items()
        if isinstance(item, Mapping)
    }
    manifest["updated_at"] = str(source.get("updated_at") or "")
    return manifest


class DriveResumeLibrary:
    """Keep source documents and generated outputs durable in app-owned Drive."""

    def __init__(
        self,
        paths: AppPaths,
        google_connection: GoogleConnectionService | None,
        *,
        drive_factory=build_drive_service,
    ) -> None:
        self.paths = paths
        self.google_connection = google_connection
        self.drive_factory = drive_factory
        self.cache_root = paths.secrets_root / "job_intelligence" / "resume_library_cache"
        self.manifest_cache_path = self.cache_root / MANIFEST_NAME

    def _require_drive(self):
        if self.google_connection is None:
            raise ResumeLibraryError(
                "Connect Google before using the Drive-backed resume library."
            )
        try:
            credentials = self.google_connection.require_credentials()
            return self.drive_factory(credentials)
        except Exception as exc:
            raise ResumeLibraryError(
                "Connect or reconnect Google before using resume inputs and outputs."
            ) from exc

    @staticmethod
    def _ensure_folders(drive) -> dict[str, dict[str, Any]]:
        job_hunt = ensure_job_hunt_folders(drive)
        library = ensure_folder(
            drive,
            LIBRARY_FOLDER_NAME,
            parent_id=str(job_hunt["source"]["id"]),
        )
        baselines = ensure_folder(
            drive,
            BASELINES_FOLDER_NAME,
            parent_id=str(library["id"]),
        )
        references = ensure_folder(
            drive,
            REFERENCES_FOLDER_NAME,
            parent_id=str(library["id"]),
        )
        return {
            **job_hunt,
            "library": library,
            "baselines": baselines,
            "references": references,
        }

    def _load_manifest(self, drive, folders) -> tuple[dict[str, Any], str]:
        remote = find_child_file(
            drive,
            MANIFEST_NAME,
            parent_id=str(folders["library"]["id"]),
            mime_type=JSON_MIME_TYPE,
        )
        if not remote:
            return _default_manifest(), ""
        try:
            download_drive_file(
                drive,
                str(remote["id"]),
                self.manifest_cache_path,
            )
            return _normalize_manifest(read_json(self.manifest_cache_path)), str(remote["id"])
        except Exception as exc:
            raise ResumeLibraryError("The Drive resume-library manifest could not be read.") from exc

    def _save_manifest(
        self,
        drive,
        folders,
        manifest: Mapping[str, Any],
        manifest_file_id: str,
    ) -> dict[str, Any]:
        value = _normalize_manifest(manifest)
        value["updated_at"] = datetime.now(TIME_ZONE).replace(microsecond=0).isoformat()
        write_json_atomic(self.manifest_cache_path, value)
        result = upload_or_update_file(
            drive,
            self.manifest_cache_path,
            parent_id=str(folders["library"]["id"]),
            existing_file_id=str(manifest_file_id or ""),
            mime_type=JSON_MIME_TYPE,
        )
        return {**value, "manifest_file_id": str(result["id"])}

    def _cached_manifest(self) -> dict[str, Any]:
        return _normalize_manifest(read_json(self.manifest_cache_path, default={}) or {})

    @staticmethod
    def _active_baseline(manifest: Mapping[str, Any]) -> dict[str, Any] | None:
        active_sha = str(manifest.get("active_baseline_sha256") or "")
        for item in manifest.get("baselines") or []:
            if str(item.get("sha256") or "") == active_sha:
                return dict(item)
        return None

    def _status_payload(
        self,
        manifest: Mapping[str, Any],
        *,
        drive_connected: bool,
        library_url: str = "",
        message: str = "",
    ) -> dict[str, Any]:
        active = self._active_baseline(manifest)
        references = [
            {
                "original_name": str(item.get("original_name") or ""),
                "sha256": str(item.get("sha256") or ""),
                "uploaded_at": str(item.get("uploaded_at") or ""),
                "drive_url": str(item.get("drive_url") or ""),
            }
            for item in manifest.get("references") or []
        ]
        confirmed_skill_evidence = [
            {
                "skill": str(item.get("skill") or ""),
                "note": str(item.get("note") or ""),
                "confirmed_at": str(item.get("confirmed_at") or ""),
            }
            for item in manifest.get("confirmed_skill_evidence") or []
        ]
        return {
            "drive_connected": drive_connected,
            "drive_backed": True,
            "baseline_resume_configured": active is not None,
            "baseline_resume_name": str((active or {}).get("original_name") or ""),
            "baseline_resume_sha256": str((active or {}).get("sha256") or ""),
            "baseline_uploaded_at": str((active or {}).get("uploaded_at") or ""),
            "baseline_drive_url": str((active or {}).get("drive_url") or ""),
            "baseline_immutable": True,
            "reference_documents": references,
            "reference_document_count": len(references),
            "confirmed_skill_evidence": confirmed_skill_evidence,
            "confirmed_skill_evidence_count": len(confirmed_skill_evidence),
            "library_url": library_url,
            "message": message,
        }

    def store_confirmed_skill_evidence(
        self,
        entries: Iterable[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Persist user-confirmed professional evidence in the private Drive library."""

        prepared: list[dict[str, str]] = []
        confirmed_at = datetime.now(TIME_ZONE).replace(microsecond=0).isoformat()
        for entry in entries:
            skill = str(entry.get("skill") or "").strip()[:120]
            note = str(entry.get("note") or "").strip()[:1200]
            if skill and note:
                prepared.append(
                    {
                        "skill": skill,
                        "note": note,
                        "confirmed_at": confirmed_at,
                    }
                )
        if not prepared:
            return self.status()

        drive = self._require_drive()
        folders = self._ensure_folders(drive)
        manifest, manifest_file_id = self._load_manifest(drive, folders)
        by_skill = {
            re.sub(r"\s+", " ", str(item.get("skill") or "").strip()).casefold(): dict(item)
            for item in manifest.get("confirmed_skill_evidence") or []
            if str(item.get("skill") or "").strip()
        }
        for entry in prepared:
            key = re.sub(r"\s+", " ", entry["skill"]).casefold()
            by_skill[key] = entry
        manifest["confirmed_skill_evidence"] = list(by_skill.values())[
            -MAX_CONFIRMED_SKILL_EVIDENCE:
        ]
        saved = self._save_manifest(drive, folders, manifest, manifest_file_id)
        return self._status_payload(
            saved,
            drive_connected=True,
            library_url=drive_folder_url(str(folders["library"]["id"])),
        )

    def status(self) -> dict[str, Any]:
        try:
            drive = self._require_drive()
            folders = self._ensure_folders(drive)
            manifest, _manifest_file_id = self._load_manifest(drive, folders)
            return self._status_payload(
                manifest,
                drive_connected=True,
                library_url=drive_folder_url(str(folders["library"]["id"])),
            )
        except ResumeLibraryError as exc:
            return self._status_payload(
                self._cached_manifest(),
                drive_connected=False,
                message=str(exc),
            )

    def _cache_bytes(self, folder: str, sha256: str, original_name: str, content: bytes) -> Path:
        path = self.cache_root / folder / _safe_cache_name(sha256, original_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file() and _sha256_bytes(path.read_bytes()) == sha256:
            return path
        pending = path.with_suffix(path.suffix + ".pending")
        pending.write_bytes(content)
        if _sha256_bytes(pending.read_bytes()) != sha256:
            pending.unlink(missing_ok=True)
            raise ResumeLibraryError("A private resume-library cache write failed integrity checks.")
        pending.replace(path)
        return path

    @staticmethod
    def _immutable_drive_name(prefix: str, sha256: str, original_name: str) -> str:
        return f"{prefix}_{sha256[:12]}_{_safe_original_name(original_name, prefix)}"

    def store_baseline(self, content: bytes, original_name: str) -> dict[str, Any]:
        """Upload a new immutable baseline version and make it active."""

        validate_resume_upload(content)
        original_name = _safe_original_name(original_name, "base_resume.docx")
        if Path(original_name).suffix.casefold() != ".docx":
            raise ValueError("The baseline resume must be a Word .docx file.")
        sha256 = _sha256_bytes(content)
        local_path = self._cache_bytes("baselines", sha256, original_name, content)
        validate_resume_docx(local_path)
        extract_resume_evidence(local_path)

        drive = self._require_drive()
        folders = self._ensure_folders(drive)
        manifest, manifest_file_id = self._load_manifest(drive, folders)
        existing = next(
            (
                dict(item)
                for item in manifest["baselines"]
                if str(item.get("sha256") or "") == sha256
            ),
            None,
        )
        if existing is None:
            drive_name = self._immutable_drive_name("base", sha256, original_name)
            remote = find_child_file(
                drive,
                drive_name,
                parent_id=str(folders["baselines"]["id"]),
                mime_type=DOCX_MIME_TYPE,
            )
            if remote is None:
                upload_path = local_path.with_name(drive_name)
                if upload_path != local_path:
                    upload_path.write_bytes(content)
                try:
                    remote = upload_or_update_file(
                        drive,
                        upload_path,
                        parent_id=str(folders["baselines"]["id"]),
                        mime_type=DOCX_MIME_TYPE,
                    )
                finally:
                    if upload_path != local_path:
                        upload_path.unlink(missing_ok=True)
            existing = {
                "sha256": sha256,
                "original_name": original_name,
                "drive_name": drive_name,
                "file_id": str(remote["id"]),
                "drive_url": str(remote.get("webViewLink") or drive_file_url(remote["id"])),
                "uploaded_at": datetime.now(TIME_ZONE).replace(microsecond=0).isoformat(),
                "mime_type": DOCX_MIME_TYPE,
                "immutable": True,
            }
            manifest["baselines"].append(existing)
        manifest["active_baseline_sha256"] = sha256
        saved = self._save_manifest(drive, folders, manifest, manifest_file_id)
        return self._status_payload(
            saved,
            drive_connected=True,
            library_url=drive_folder_url(str(folders["library"]["id"])),
        )

    @staticmethod
    def _validate_reference(content: bytes, original_name: str) -> str:
        suffix = Path(original_name).suffix.casefold()
        if not content or len(content) > MAX_REFERENCE_BYTES:
            raise ValueError("Each reference file must be non-empty and smaller than 8 MB.")
        if suffix == ".docx":
            validate_resume_upload(content)
            return DOCX_MIME_TYPE
        if suffix in {".md", ".txt"}:
            try:
                content.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise ValueError("Markdown/text references must use UTF-8 encoding.") from exc
            return MARKDOWN_MIME_TYPE if suffix == ".md" else "text/plain"
        raise ValueError("Reference files must be .docx, .md, or .txt files.")

    def store_references(
        self,
        files: Iterable[tuple[str, bytes]],
    ) -> dict[str, Any]:
        values = list(files)
        if not values:
            raise ValueError("Choose at least one reference document.")
        if len(values) > MAX_REFERENCE_FILES:
            raise ValueError(f"Upload at most {MAX_REFERENCE_FILES} reference documents.")

        prepared: list[dict[str, Any]] = []
        for supplied_name, content in values:
            original_name = _safe_original_name(supplied_name, "reference")
            mime_type = self._validate_reference(content, original_name)
            sha256 = _sha256_bytes(content)
            local_path = self._cache_bytes("references", sha256, original_name, content)
            prepared.append(
                {
                    "content": content,
                    "original_name": original_name,
                    "mime_type": mime_type,
                    "sha256": sha256,
                    "local_path": local_path,
                }
            )

        drive = self._require_drive()
        folders = self._ensure_folders(drive)
        manifest, manifest_file_id = self._load_manifest(drive, folders)
        by_sha = {
            str(item.get("sha256") or ""): dict(item)
            for item in manifest["references"]
        }
        for item in prepared:
            sha256 = item["sha256"]
            if sha256 in by_sha:
                continue
            drive_name = self._immutable_drive_name(
                "ref", sha256, item["original_name"]
            )
            remote = find_child_file(
                drive,
                drive_name,
                parent_id=str(folders["references"]["id"]),
                mime_type=item["mime_type"],
            )
            if remote is None:
                upload_path = item["local_path"].with_name(drive_name)
                upload_path.write_bytes(item["content"])
                try:
                    remote = upload_or_update_file(
                        drive,
                        upload_path,
                        parent_id=str(folders["references"]["id"]),
                        mime_type=item["mime_type"],
                    )
                finally:
                    upload_path.unlink(missing_ok=True)
            record = {
                "sha256": sha256,
                "original_name": item["original_name"],
                "drive_name": drive_name,
                "file_id": str(remote["id"]),
                "drive_url": str(remote.get("webViewLink") or drive_file_url(remote["id"])),
                "uploaded_at": datetime.now(TIME_ZONE).replace(microsecond=0).isoformat(),
                "mime_type": item["mime_type"],
                "immutable": True,
            }
            manifest["references"].append(record)
            by_sha[sha256] = record

        saved = self._save_manifest(drive, folders, manifest, manifest_file_id)
        return self._status_payload(
            saved,
            drive_connected=True,
            library_url=drive_folder_url(str(folders["library"]["id"])),
        )

    def _materialize_record(self, drive, record: Mapping[str, Any], folder: str) -> Path:
        sha256 = str(record.get("sha256") or "")
        original_name = _safe_original_name(record.get("original_name"), "document")
        file_id = str(record.get("file_id") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", sha256) or not file_id:
            raise ResumeLibraryError("A Drive resume-library record is incomplete.")
        path = self.cache_root / folder / _safe_cache_name(sha256, original_name)
        if not path.is_file() or resume_sha256(path) != sha256:
            download_drive_file(drive, file_id, path)
        if resume_sha256(path) != sha256:
            path.unlink(missing_ok=True)
            raise ResumeLibraryError("A downloaded resume-library file failed integrity checks.")
        return path

    def materialize_inputs(self) -> dict[str, Any]:
        """Download the active baseline and references into an ephemeral private cache."""

        drive = self._require_drive()
        folders = self._ensure_folders(drive)
        manifest, _manifest_file_id = self._load_manifest(drive, folders)
        active = self._active_baseline(manifest)
        if active is None:
            raise FileNotFoundError(
                "Upload a baseline resume to the Drive resume library before generation."
            )
        baseline_path = self._materialize_record(drive, active, "baselines")
        validate_resume_docx(baseline_path)
        extract_resume_evidence(baseline_path)
        references = []
        for record in manifest.get("references") or []:
            path = self._materialize_record(drive, record, "references")
            references.append({**dict(record), "local_path": str(path)})
        reference_digest = hashlib.sha256(
            "\0".join(sorted(str(item.get("sha256") or "") for item in references)).encode(
                "utf-8"
            )
        ).hexdigest()
        return {
            "baseline_path": baseline_path,
            "baseline": active,
            "references": references,
            "reference_digest": reference_digest,
            "library_url": drive_folder_url(str(folders["library"]["id"])),
        }

    def upload_artifact(self, local_path: Path, run_date: str, mime_type: str) -> dict[str, Any]:
        """Upload one generated artifact into the dated Drive Resumes folder."""

        drive = self._require_drive()
        folders = ensure_job_hunt_folders(drive, run_date=str(run_date))
        resumes_folder = ensure_folder(
            drive,
            "Resumes",
            parent_id=str(folders["date"]["id"]),
        )
        uploaded = upload_or_update_file(
            drive,
            Path(local_path),
            parent_id=str(resumes_folder["id"]),
            mime_type=mime_type,
        )
        return {
            "file_id": str(uploaded["id"]),
            "drive_url": str(
                uploaded.get("webViewLink") or drive_file_url(uploaded["id"])
            ),
            "folder_url": drive_folder_url(str(resumes_folder["id"])),
        }

    def record_artifacts(self, records: Iterable[Mapping[str, Any]]) -> None:
        drive = self._require_drive()
        folders = self._ensure_folders(drive)
        manifest, manifest_file_id = self._load_manifest(drive, folders)
        artifacts = dict(manifest.get("artifacts") or {})
        for record in records:
            artifact_id = str(record.get("artifact_id") or "").strip()
            if artifact_id:
                artifacts[artifact_id] = dict(record)
        if len(artifacts) > 500:
            ordered = sorted(
                artifacts.items(),
                key=lambda pair: str(pair[1].get("generated_at") or ""),
            )[-500:]
            artifacts = dict(ordered)
        manifest["artifacts"] = artifacts
        self._save_manifest(drive, folders, manifest, manifest_file_id)

    def materialize_artifact(self, artifact_id: str) -> tuple[Path, dict[str, Any]]:
        drive = self._require_drive()
        folders = self._ensure_folders(drive)
        manifest, _manifest_file_id = self._load_manifest(drive, folders)
        record = dict((manifest.get("artifacts") or {}).get(artifact_id) or {})
        file_id = str(record.get("file_id") or "")
        file_name = _safe_original_name(record.get("file_name"), "generated_document")
        sha256 = str(record.get("sha256") or "")
        if not file_id or not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise FileNotFoundError("The requested generated document is unavailable.")
        path = self.cache_root / "artifacts" / f"{artifact_id}_{file_name}"
        if not path.is_file() or resume_sha256(path) != sha256:
            download_drive_file(drive, file_id, path)
        if resume_sha256(path) != sha256:
            path.unlink(missing_ok=True)
            raise ResumeLibraryError("The generated Drive document failed integrity checks.")
        return path, record
