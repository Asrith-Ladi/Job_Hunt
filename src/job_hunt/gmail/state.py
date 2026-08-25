"""Cross-run Gmail deduplication state without storing raw email content."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping


STATE_VERSION = 2
MAX_RUN_HISTORY = 200
RUN_HISTORY_FIELDS = (
    "run_id",
    "run_started_at",
    "file_name",
    "date_folder_id",
    "drive_file_id",
    "drive_url",
    "rows_exported",
    "messages_read",
    "unique_jobs",
    "unchanged_jobs",
    "status",
)
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


def _safe_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def empty_gmail_run_state() -> dict[str, Any]:
    return {
        "version": STATE_VERSION,
        "last_successful_run_at": "",
        "job_fingerprints": {},
        "run_history": [],
    }


def normalize_gmail_run_state(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return empty_gmail_run_state()
    fingerprints = value.get("job_fingerprints")
    if not isinstance(fingerprints, Mapping):
        fingerprints = {}
    history = value.get("run_history")
    if not isinstance(history, list):
        history = []
    normalized_history: list[dict[str, Any]] = []
    seen_run_ids: set[str] = set()
    for raw in reversed(history):
        if not isinstance(raw, Mapping):
            continue
        run_id = str(raw.get("run_id") or "").strip()
        if not run_id or run_id in seen_run_ids:
            continue
        seen_run_ids.add(run_id)
        normalized_history.append(
            {
                field: (
                    _safe_int(raw.get(field))
                    if field
                    in {"rows_exported", "messages_read", "unique_jobs", "unchanged_jobs"}
                    else str(raw.get(field) or "").strip()
                )
                for field in RUN_HISTORY_FIELDS
            }
        )
    normalized_history.reverse()
    return {
        "version": STATE_VERSION,
        "last_successful_run_at": str(value.get("last_successful_run_at") or ""),
        "job_fingerprints": {
            str(key): str(fingerprint)
            for key, fingerprint in fingerprints.items()
            if key and fingerprint
        },
        "run_history": normalized_history[-MAX_RUN_HISTORY:],
    }


def append_gmail_run_history(
    state: Mapping[str, Any] | None,
    record: Mapping[str, Any],
) -> dict[str, Any]:
    """Append one sanitized durable run reference without duplicating its ID."""

    updated = normalize_gmail_run_state(state)
    run_id = str(record.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("A Gmail run-history record requires a run ID.")
    existing = next(
        (
            dict(item)
            for item in updated["run_history"]
            if str(item.get("run_id") or "") == run_id
        ),
        {},
    )
    merged = {**existing, **dict(record), "run_id": run_id}
    history = [
        dict(item)
        for item in updated["run_history"]
        if str(item.get("run_id") or "") != run_id
    ]
    history.append(
        {
            field: (
                _safe_int(merged.get(field))
                if field in {"rows_exported", "messages_read", "unique_jobs", "unchanged_jobs"}
                else str(merged.get(field) or "").strip()
            )
            for field in RUN_HISTORY_FIELDS
        }
    )
    updated["run_history"] = history[-MAX_RUN_HISTORY:]
    return updated


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
