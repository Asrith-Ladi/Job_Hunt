"""Drive-backed persistence for jobs the user explicitly chooses to track.

Search results are intentionally absent from this repository.  A record enters the
queue only through an explicit UI action such as Save for later, a status change,
or a review-note save.
"""

from __future__ import annotations

import hashlib
import threading
from copy import deepcopy
from datetime import datetime
from typing import Any, Iterable, Mapping

from job_hunt.integrations.drive_storage import (
    build_drive_service,
    download_drive_file,
    drive_file_url,
    ensure_job_hunt_folders,
    find_child_file,
    upload_or_update_file,
)
from job_hunt.runtime.files import read_json, write_json_atomic
from job_hunt.runtime.google import GoogleConnectionService
from job_hunt.runtime.paths import APPLICATION_QUEUE_NAME, AppPaths, TIME_ZONE


APPLICATION_QUEUE_VERSION = 1
APPLICATION_QUEUE_MIME_TYPE = "application/json"
APPLICATION_SOURCES = {"gmail", "company_portals", "ats_sources"}
MAX_ROW_FIELDS = 100
MAX_FIELD_NAME_LENGTH = 100
MAX_FIELD_VALUE_LENGTH = 100_000


def _now() -> str:
    return datetime.now(TIME_ZONE).replace(microsecond=0).isoformat()


def _clean_scalar(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if value == value else None
    return str(value)[:MAX_FIELD_VALUE_LENGTH]


def _clean_row(value: Mapping[str, Any]) -> dict[str, Any]:
    if len(value) > MAX_ROW_FIELDS:
        raise ValueError("The job record contains too many fields.")
    row: dict[str, Any] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key).strip()
        if not key or len(key) > MAX_FIELD_NAME_LENGTH:
            raise ValueError("The job record contains an invalid field name.")
        if isinstance(raw_value, (Mapping, list, tuple, set)):
            raise ValueError(f"The job field '{key}' must contain a scalar value.")
        row[key] = _clean_scalar(raw_value)
    return row


def _source_record_id(row: Mapping[str, Any]) -> str:
    supplied = str(row.get("job_record_id") or row.get("external_job_id") or "").strip()
    if supplied:
        return supplied[:500]
    identity = "|".join(
        str(row.get(key) or "").strip().casefold()
        for key in (
            "official_url",
            "source_url",
            "company",
            "title",
            "location",
        )
    )
    if not identity.strip("|"):
        raise ValueError("The job needs a record ID or enough identity fields to save it.")
    return f"derived-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}"


def _application_id(source: str, source_record_id: str) -> str:
    digest = hashlib.sha256(f"{source}|{source_record_id}".encode("utf-8")).hexdigest()
    return f"application-{digest[:24]}"


def _clean_referrals(values: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for value in values:
        candidate = {
            key: str(value.get(key) or "").strip()[:10_000]
            for key in ("name", "position", "profile_url", "message")
        }
        identity = (candidate["profile_url"].casefold(), candidate["name"].casefold())
        if not candidate["name"] or identity in seen:
            continue
        seen.add(identity)
        output.append(candidate)
    return output[:100]


def _empty_queue() -> dict[str, Any]:
    return {
        "version": APPLICATION_QUEUE_VERSION,
        "updated_at": "",
        "applications": {},
    }


def _normalize_queue(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return _empty_queue()
    applications = value.get("applications")
    if not isinstance(applications, Mapping):
        applications = {}
    normalized: dict[str, dict[str, Any]] = {}
    for _raw_id, raw_record in applications.items():
        if not isinstance(raw_record, Mapping) or not isinstance(raw_record.get("row"), Mapping):
            continue
        source = str(raw_record.get("source") or "").strip()
        if source not in APPLICATION_SOURCES:
            continue
        source_record_id = str(raw_record.get("source_record_id") or "").strip()
        if not source_record_id:
            try:
                source_record_id = _source_record_id(raw_record["row"])
            except ValueError:
                continue
        application_id = _application_id(source, source_record_id)
        try:
            normalized_row = _clean_row(raw_record["row"])
        except ValueError:
            continue
        normalized[application_id] = {
            "application_id": application_id,
            "source": source,
            "source_record_id": source_record_id,
            "saved_at": str(raw_record.get("saved_at") or ""),
            "updated_at": str(raw_record.get("updated_at") or ""),
            "row": normalized_row,
            "referral_candidates": _clean_referrals(
                raw_record.get("referral_candidates")
                if isinstance(raw_record.get("referral_candidates"), list)
                else []
            ),
        }
    return {
        "version": APPLICATION_QUEUE_VERSION,
        "updated_at": str(value.get("updated_at") or ""),
        "applications": normalized,
    }


class ApplicationQueueService:
    """Synchronize one canonical personal application queue with app-owned Drive."""

    def __init__(
        self,
        paths: AppPaths,
        google_connection: GoogleConnectionService,
        *,
        drive_service_factory=build_drive_service,
    ) -> None:
        self.paths = paths
        self.google_connection = google_connection
        self.drive_service_factory = drive_service_factory
        self._mutation_lock = threading.Lock()

    def _load(self) -> tuple[dict[str, Any], Any, str, str]:
        credentials = self.google_connection.require_credentials()
        drive_service = self.drive_service_factory(credentials)
        folders = ensure_job_hunt_folders(drive_service)
        source_folder_id = str(folders["source"]["id"])
        remote = find_child_file(
            drive_service,
            APPLICATION_QUEUE_NAME,
            parent_id=source_folder_id,
            mime_type=APPLICATION_QUEUE_MIME_TYPE,
        )
        if remote:
            download_drive_file(
                drive_service,
                str(remote["id"]),
                self.paths.application_queue_path,
            )
        value = _normalize_queue(read_json(self.paths.application_queue_path))
        return value, drive_service, source_folder_id, str((remote or {}).get("id") or "")

    @staticmethod
    def _payload(value: Mapping[str, Any], *, drive_file_id: str = "") -> dict[str, Any]:
        applications = value.get("applications") or {}
        rows = sorted(
            (dict(record) for record in applications.values()),
            key=lambda record: str(record.get("updated_at") or ""),
            reverse=True,
        )
        return {
            "applications": rows,
            "count": len(rows),
            "updated_at": str(value.get("updated_at") or ""),
            "drive_url": drive_file_url(drive_file_id) if drive_file_id else "",
        }

    def list(self) -> dict[str, Any]:
        with self._mutation_lock:
            value, _drive, _source_folder_id, file_id = self._load()
            return self._payload(value, drive_file_id=file_id)

    def upsert(
        self,
        source: str,
        row: Mapping[str, Any],
        referral_candidates: Iterable[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        source = str(source).strip()
        if source not in APPLICATION_SOURCES:
            raise ValueError("An unsupported application source was supplied.")
        cleaned_row = _clean_row(row)
        source_record_id = _source_record_id(cleaned_row)
        cleaned_referrals = _clean_referrals(referral_candidates)
        with self._mutation_lock:
            value, drive_service, source_folder_id, file_id = self._load()
            previous_value = deepcopy(value)
            application_id = _application_id(source, source_record_id)
            saved_at = str(
                (value["applications"].get(application_id) or {}).get("saved_at") or _now()
            )
            updated_at = _now()
            record = {
                "application_id": application_id,
                "source": source,
                "source_record_id": source_record_id,
                "saved_at": saved_at,
                "updated_at": updated_at,
                "row": cleaned_row,
                "referral_candidates": cleaned_referrals,
            }
            value["applications"][application_id] = record
            value["updated_at"] = updated_at
            write_json_atomic(self.paths.application_queue_path, value)
            try:
                uploaded = upload_or_update_file(
                    drive_service,
                    self.paths.application_queue_path,
                    parent_id=source_folder_id,
                    existing_file_id=file_id or None,
                    mime_type=APPLICATION_QUEUE_MIME_TYPE,
                )
            except Exception:
                write_json_atomic(self.paths.application_queue_path, previous_value)
                raise
            return {
                "application": record,
                "count": len(value["applications"]),
                "drive_url": uploaded.get("webViewLink")
                or drive_file_url(str(uploaded["id"])),
            }
