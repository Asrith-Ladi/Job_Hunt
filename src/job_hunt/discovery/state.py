"""Cross-run discovery fingerprints and user-maintained fields."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping


STATE_VERSION = 2
FINGERPRINT_FIELDS = (
    "company",
    "title",
    "location",
    "provider",
    "source_identifier",
    "official_url",
    "description",
    "posted_at",
    "updated_at",
    "source_status",
)
USER_FIELDS = ("application_status", "notes")


def empty_discovery_state() -> dict[str, Any]:
    return {
        "version": STATE_VERSION,
        "last_successful_run_at": "",
        "job_fingerprints": {},
        "user_fields": {},
        "seen_times": {},
    }


def normalize_discovery_state(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return empty_discovery_state()
    fingerprints = value.get("job_fingerprints")
    user_fields = value.get("user_fields")
    seen_times = value.get("seen_times")
    if not isinstance(fingerprints, Mapping):
        fingerprints = {}
    if not isinstance(user_fields, Mapping):
        user_fields = {}
    if not isinstance(seen_times, Mapping):
        seen_times = {}
    normalized_user_fields: dict[str, dict[str, str]] = {}
    for record_id, fields in user_fields.items():
        if not record_id or not isinstance(fields, Mapping):
            continue
        normalized_user_fields[str(record_id)] = {
            field: str(fields.get(field) or "") for field in USER_FIELDS
        }
    return {
        "version": STATE_VERSION,
        "last_successful_run_at": str(value.get("last_successful_run_at") or ""),
        "job_fingerprints": {
            str(key): str(fingerprint)
            for key, fingerprint in fingerprints.items()
            if key and fingerprint
        },
        "user_fields": normalized_user_fields,
        "seen_times": {
            str(record_id): {
                "first_seen_at": str(fields.get("first_seen_at") or ""),
                "last_seen_at": str(fields.get("last_seen_at") or ""),
            }
            for record_id, fields in seen_times.items()
            if record_id and isinstance(fields, Mapping)
        },
    }


def discovery_fingerprint(row: Mapping[str, Any]) -> str:
    payload = {
        field: " ".join(str(row.get(field) or "").casefold().split())
        for field in FINGERPRINT_FIELDS
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def apply_saved_user_fields(
    rows: Iterable[Mapping[str, Any]],
    state: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    normalized = normalize_discovery_state(state)
    saved = normalized["user_fields"]
    seen_times = normalized["seen_times"]
    output: list[dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        fields = saved.get(str(record.get("job_record_id") or ""), {})
        for field in USER_FIELDS:
            if fields.get(field):
                record[field] = fields[field]
        times = seen_times.get(str(record.get("job_record_id") or ""), {})
        if times.get("first_seen_at"):
            record["first_seen_at"] = times["first_seen_at"]
        record["last_seen_at"] = str(
            record.get("discovered_at") or record.get("last_seen_at") or ""
        )
        output.append(record)
    return output


def select_new_or_changed_jobs(
    rows: Iterable[Mapping[str, Any]],
    state: Mapping[str, Any] | None,
) -> tuple[list[dict[str, Any]], int]:
    normalized = normalize_discovery_state(state)
    fingerprints = normalized["job_fingerprints"]
    selected: list[dict[str, Any]] = []
    unchanged = 0
    for row in apply_saved_user_fields(rows, normalized):
        record_id = str(row.get("job_record_id") or "")
        if not record_id or fingerprints.get(record_id) != discovery_fingerprint(row):
            selected.append(row)
        else:
            unchanged += 1
    return selected, unchanged


def update_discovery_state(
    state: Mapping[str, Any] | None,
    rows: Iterable[Mapping[str, Any]],
    *,
    completed_at: str,
) -> dict[str, Any]:
    updated = normalize_discovery_state(state)
    fingerprints = dict(updated["job_fingerprints"])
    user_fields = dict(updated["user_fields"])
    seen_times = dict(updated["seen_times"])
    for row in rows:
        record_id = str(row.get("job_record_id") or "")
        if not record_id:
            continue
        fingerprints[record_id] = discovery_fingerprint(row)
        existing = dict(user_fields.get(record_id) or {})
        for field in USER_FIELDS:
            value = str(row.get(field) or "")
            if value:
                existing[field] = value
        user_fields[record_id] = existing
        existing_times = dict(seen_times.get(record_id) or {})
        first_seen = str(
            existing_times.get("first_seen_at")
            or row.get("first_seen_at")
            or row.get("discovered_at")
            or completed_at
        )
        last_seen = str(row.get("last_seen_at") or row.get("discovered_at") or completed_at)
        seen_times[record_id] = {
            "first_seen_at": first_seen,
            "last_seen_at": last_seen,
        }
    updated["job_fingerprints"] = fingerprints
    updated["user_fields"] = user_fields
    updated["seen_times"] = seen_times
    updated["last_successful_run_at"] = str(completed_at or "")
    return updated


def update_user_fields(
    state: Mapping[str, Any] | None,
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    updated = normalize_discovery_state(state)
    user_fields = dict(updated["user_fields"])
    for row in rows:
        record_id = str(row.get("job_record_id") or "")
        if not record_id:
            continue
        user_fields[record_id] = {field: str(row.get(field) or "") for field in USER_FIELDS}
    updated["user_fields"] = user_fields
    return updated
