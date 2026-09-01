"""Bounded in-memory progress snapshots for active personal search requests."""

from __future__ import annotations

import re
import threading
import time
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping


PROGRESS_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{12,100}$")
PROGRESS_TTL_SECONDS = 30 * 60
MAX_PROGRESS_ENTRIES = 100
MAX_RECENT_EVENTS = 8


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def validate_progress_id(value: str) -> str:
    progress_id = str(value or "").strip()
    if not PROGRESS_ID_PATTERN.fullmatch(progress_id):
        raise ValueError("The search progress identifier is invalid.")
    return progress_id


def _text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


class SearchProgressStore:
    """Keep small polling snapshots without retaining mailbox or job-description content."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, dict[str, Any]] = {}

    def _prune_locked(self) -> None:
        cutoff = time.monotonic() - PROGRESS_TTL_SECONDS
        expired = [
            progress_id
            for progress_id, entry in self._entries.items()
            if float(entry.get("_updated_monotonic") or 0) < cutoff
        ]
        for progress_id in expired:
            self._entries.pop(progress_id, None)
        if len(self._entries) <= MAX_PROGRESS_ENTRIES:
            return
        oldest = sorted(
            self._entries,
            key=lambda progress_id: float(
                self._entries[progress_id].get("_updated_monotonic") or 0
            ),
        )
        for progress_id in oldest[: len(self._entries) - MAX_PROGRESS_ENTRIES]:
            self._entries.pop(progress_id, None)

    @staticmethod
    def _public(entry: Mapping[str, Any]) -> dict[str, Any]:
        return {
            key: deepcopy(value)
            for key, value in entry.items()
            if not key.startswith("_")
        }

    def start(
        self,
        progress_id: str,
        *,
        source: str,
        message: str,
        total_items: int = 0,
    ) -> dict[str, Any]:
        progress_id = validate_progress_id(progress_id)
        now = _now()
        entry = {
            "progress_id": progress_id,
            "source": _text(source, 50),
            "status": "running",
            "stage": "starting",
            "message": _text(message, 500),
            "current_item": "",
            "completed_items": 0,
            "total_items": max(0, int(total_items)),
            "matches_found": 0,
            "started_at": now,
            "updated_at": now,
            "recent_events": [],
            "_updated_monotonic": time.monotonic(),
        }
        with self._lock:
            self._prune_locked()
            self._entries[progress_id] = entry
            self._append_event_locked(entry)
            return self._public(entry)

    @staticmethod
    def _append_event_locked(entry: dict[str, Any]) -> None:
        event = {
            "stage": entry["stage"],
            "message": entry["message"],
            "current_item": entry["current_item"],
            "completed_items": entry["completed_items"],
            "total_items": entry["total_items"],
            "matches_found": entry["matches_found"],
            "at": entry["updated_at"],
        }
        events = list(entry.get("recent_events") or [])
        identity = (event["stage"], event["message"], event["current_item"])
        if events:
            previous = events[-1]
            previous_identity = (
                previous.get("stage"),
                previous.get("message"),
                previous.get("current_item"),
            )
            if identity == previous_identity:
                events[-1] = event
            else:
                events.append(event)
        else:
            events.append(event)
        entry["recent_events"] = events[-MAX_RECENT_EVENTS:]

    def update(self, progress_id: str, values: Mapping[str, Any]) -> dict[str, Any] | None:
        progress_id = validate_progress_id(progress_id)
        with self._lock:
            entry = self._entries.get(progress_id)
            if entry is None:
                return None
            if "stage" in values:
                entry["stage"] = _text(values.get("stage"), 80)
            if "message" in values:
                entry["message"] = _text(values.get("message"), 500)
            if "current_item" in values:
                entry["current_item"] = _text(values.get("current_item"), 300)
            for key in ("completed_items", "total_items", "matches_found"):
                if key in values:
                    entry[key] = max(0, int(values.get(key) or 0))
            entry["updated_at"] = _now()
            entry["_updated_monotonic"] = time.monotonic()
            self._append_event_locked(entry)
            return self._public(entry)

    def finish(
        self,
        progress_id: str,
        *,
        status: str,
        message: str,
        matches_found: int | None = None,
    ) -> dict[str, Any] | None:
        progress_id = validate_progress_id(progress_id)
        with self._lock:
            entry = self._entries.get(progress_id)
            if entry is None:
                return None
            entry["status"] = status if status in {"completed", "failed"} else "completed"
            entry["stage"] = entry["status"]
            entry["message"] = _text(message, 500)
            entry["current_item"] = ""
            if matches_found is not None:
                entry["matches_found"] = max(0, int(matches_found))
            if entry["status"] == "completed" and entry["total_items"]:
                entry["completed_items"] = entry["total_items"]
            entry["updated_at"] = _now()
            entry["_updated_monotonic"] = time.monotonic()
            self._append_event_locked(entry)
            return self._public(entry)

    def get(self, progress_id: str) -> dict[str, Any] | None:
        progress_id = validate_progress_id(progress_id)
        with self._lock:
            self._prune_locked()
            entry = self._entries.get(progress_id)
            return self._public(entry) if entry is not None else None
