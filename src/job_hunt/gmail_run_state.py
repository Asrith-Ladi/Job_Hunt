"""Cross-run Gmail deduplication state without storing raw email content."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping


STATE_VERSION = 1
FINGERPRINT_FIELDS = (
    "alert_source",
    "company",
    "title",
    "location",
    "years_of_experience",
    "source_url",
    "official_url",
    "parse_status",
)


def empty_gmail_run_state() -> dict[str, Any]:
    return {
        "version": STATE_VERSION,
        "last_successful_run_at": "",
        "job_fingerprints": {},
    }


def normalize_gmail_run_state(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return empty_gmail_run_state()
    fingerprints = value.get("job_fingerprints")
    if not isinstance(fingerprints, Mapping):
        fingerprints = {}
    return {
        "version": STATE_VERSION,
        "last_successful_run_at": str(value.get("last_successful_run_at") or ""),
        "job_fingerprints": {
            str(key): str(fingerprint)
            for key, fingerprint in fingerprints.items()
            if key and fingerprint
        },
    }


def gmail_job_fingerprint(row: Mapping[str, Any]) -> str:
    payload = {
        field: " ".join(str(row.get(field) or "").casefold().split())
        for field in FINGERPRINT_FIELDS
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def select_new_or_changed_gmail_jobs(
    rows: Iterable[Mapping[str, Any]],
    state: Mapping[str, Any] | None,
) -> tuple[list[dict[str, Any]], int]:
    """Return only new/changed jobs plus the count skipped as unchanged."""

    normalized_state = normalize_gmail_run_state(state)
    fingerprints = normalized_state["job_fingerprints"]
    selected: list[dict[str, Any]] = []
    unchanged = 0
    for row in rows:
        record = dict(row)
        record_id = str(record.get("job_record_id") or "")
        fingerprint = gmail_job_fingerprint(record)
        if not record_id or fingerprints.get(record_id) != fingerprint:
            selected.append(record)
        else:
            unchanged += 1
    return selected, unchanged


def update_gmail_run_state(
    state: Mapping[str, Any] | None,
    rows: Iterable[Mapping[str, Any]],
    *,
    completed_at: str,
) -> dict[str, Any]:
    """Record a successful run after its workbook and Drive copy are durable."""

    updated = normalize_gmail_run_state(state)
    fingerprints = dict(updated["job_fingerprints"])
    for row in rows:
        record_id = str(row.get("job_record_id") or "")
        if record_id:
            fingerprints[record_id] = gmail_job_fingerprint(row)
    updated["job_fingerprints"] = fingerprints
    updated["last_successful_run_at"] = str(completed_at or "")
    return updated
