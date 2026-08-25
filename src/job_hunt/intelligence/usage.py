"""Privacy-safe OpenAI usage accounting for the manual job workflow.

The ledger stores only API metering fields and public job identifiers. Prompts,
responses, resume content, Gmail content, contact data, and credentials are never
written here.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from job_hunt.integrations.drive_storage import (
    build_drive_service,
    download_drive_file,
    ensure_job_hunt_folders,
    find_child_file,
    upload_or_update_file,
)
from job_hunt.runtime.files import read_json, write_json_atomic


TIME_ZONE = ZoneInfo("Asia/Kolkata")
LEDGER_SCHEMA_VERSION = 1
LEDGER_FILE_NAME = "ai_usage.json"
LEDGER_DRIVE_PATH = f"Job Hunt/Source/{LEDGER_FILE_NAME}"
JSON_MIME_TYPE = "application/json"
PRICING_VERSION = "openai-2026-08-17"
PRICING_SOURCE_URL = "https://developers.openai.com/api/docs/models/gpt-5.6-luna"
WEB_SEARCH_PRICE_SOURCE_URL = "https://developers.openai.com/api/docs/pricing"
LONG_CONTEXT_THRESHOLD_TOKENS = 272_000

# USD per one million tokens. Cache writes are priced at 1.25x normal input.
MODEL_PRICING = {
    "gpt-5.6-luna": {
        "input_per_million": Decimal("0.20"),
        "cached_input_per_million": Decimal("0.02"),
        "cache_write_per_million": Decimal("0.25"),
        "output_per_million": Decimal("1.20"),
    }
}
WEB_SEARCH_PER_CALL = Decimal("0.01")

OPERATION_LABELS = {
    "official_job_research": "Official-job web research",
    "exact_jd_extraction": "Exact public ATS JD extraction",
    "resume_plan": "Resume and cover-letter planning",
}

DEFAULT_ESTIMATES = {
    "official_job": {
        "low_usd": 0.003,
        "estimated_usd": 0.015,
        "high_usd": 0.04,
        "web_search_possible": True,
    },
    "resume_plan": {
        "low_usd": 0.003,
        "estimated_usd": 0.007,
        "high_usd": 0.02,
        "web_search_possible": False,
    },
}


def _field(value: object, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _token_count(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.00000001")))


def _pricing_for_model(model: str) -> Mapping[str, Decimal] | None:
    normalized = str(model or "").strip().casefold()
    for name, pricing in MODEL_PRICING.items():
        if normalized == name or normalized.startswith(f"{name}-"):
            return pricing
    return None


def _web_search_calls(response: object) -> int:
    output = _field(response, "output", []) or []
    if not isinstance(output, (list, tuple)):
        return 0
    calls: set[str] = set()
    for index, item in enumerate(output):
        if str(_field(item, "type", "")).strip() != "web_search_call":
            continue
        calls.add(str(_field(item, "id", "") or f"call-{index}"))
    return len(calls)


def _safe_context(context: Mapping[str, Any] | None) -> dict[str, str]:
    source = dict(context or {})
    limits = {
        "job_record_id": 200,
        "official_job_id": 200,
        "company": 300,
        "title": 300,
    }
    return {
        key: str(source.get(key) or "").strip()[:limit]
        for key, limit in limits.items()
        if str(source.get(key) or "").strip()
    }


def response_usage_event(
    response: object,
    *,
    operation: str,
    model: str,
    context: Mapping[str, Any] | None = None,
    recorded_at: datetime | None = None,
) -> dict[str, Any]:
    """Extract billable usage without retaining any model input or output."""

    now = (recorded_at or datetime.now(TIME_ZONE)).astimezone(TIME_ZONE).replace(
        microsecond=0
    )
    usage = _field(response, "usage")
    input_details = _field(usage, "input_tokens_details", {}) or {}
    output_details = _field(usage, "output_tokens_details", {}) or {}
    input_tokens = _token_count(_field(usage, "input_tokens"))
    cached_tokens = min(
        input_tokens,
        _token_count(_field(input_details, "cached_tokens")),
    )
    cache_write_tokens = min(
        max(0, input_tokens - cached_tokens),
        _token_count(
            _field(
                input_details,
                "cache_write_tokens",
                _field(usage, "cache_write_tokens"),
            )
        ),
    )
    uncached_tokens = max(0, input_tokens - cached_tokens - cache_write_tokens)
    output_tokens = _token_count(_field(usage, "output_tokens"))
    reasoning_tokens = min(
        output_tokens,
        _token_count(_field(output_details, "reasoning_tokens")),
    )
    total_tokens = _token_count(_field(usage, "total_tokens"))
    if not total_tokens and usage is not None:
        total_tokens = input_tokens + output_tokens
    search_calls = _web_search_calls(response)
    pricing = _pricing_for_model(model)
    long_context = input_tokens > LONG_CONTEXT_THRESHOLD_TOKENS
    calculated_cost: float | None = None
    token_cost: float | None = None
    search_cost = _money(WEB_SEARCH_PER_CALL * search_calls)
    if usage is not None and pricing is not None:
        input_multiplier = Decimal("2") if long_context else Decimal("1")
        output_multiplier = Decimal("1.5") if long_context else Decimal("1")
        million = Decimal(1_000_000)
        token_total = input_multiplier * (
            (Decimal(uncached_tokens) / million) * pricing["input_per_million"]
            + (Decimal(cached_tokens) / million)
            * pricing["cached_input_per_million"]
            + (Decimal(cache_write_tokens) / million)
            * pricing["cache_write_per_million"]
        ) + output_multiplier * (
            (Decimal(output_tokens) / million) * pricing["output_per_million"]
        )
        token_cost = _money(token_total)
        calculated_cost = _money(token_total + WEB_SEARCH_PER_CALL * search_calls)

    return {
        "event_id": f"usage_{uuid.uuid4().hex}",
        "recorded_at": now.isoformat(),
        "operation": str(operation or "unknown").strip()[:80],
        "operation_label": OPERATION_LABELS.get(
            str(operation or "").strip(), "OpenAI operation"
        ),
        "model": str(model or "").strip()[:120],
        **_safe_context(context),
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_tokens,
        "cache_write_tokens": cache_write_tokens,
        "uncached_input_tokens": uncached_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "total_tokens": total_tokens,
        "web_search_calls": search_calls,
        "token_cost_usd": token_cost,
        "web_search_cost_usd": search_cost,
        "calculated_cost_usd": calculated_cost,
        "currency": "USD",
        "pricing_version": PRICING_VERSION,
        "pricing_supported": pricing is not None,
        "long_context_pricing": long_context,
        "usage_available": usage is not None,
    }


def _default_ledger() -> dict[str, Any]:
    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "events": [],
        "updated_at": "",
    }


def _normalized_ledger(value: object) -> dict[str, Any]:
    source = dict(value) if isinstance(value, Mapping) else {}
    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "events": [
            dict(item)
            for item in source.get("events") or []
            if isinstance(item, Mapping) and str(item.get("event_id") or "").strip()
        ],
        "updated_at": str(source.get("updated_at") or ""),
    }


def _period_totals(events: list[dict[str, Any]]) -> dict[str, Any]:
    priced = [
        float(item["calculated_cost_usd"])
        for item in events
        if item.get("calculated_cost_usd") is not None
    ]
    return {
        "api_calls": len(events),
        "calculated_cost_usd": round(sum(priced), 8),
        "unpriced_calls": len(events) - len(priced),
        "input_tokens": sum(_token_count(item.get("input_tokens")) for item in events),
        "cached_input_tokens": sum(
            _token_count(item.get("cached_input_tokens")) for item in events
        ),
        "output_tokens": sum(_token_count(item.get("output_tokens")) for item in events),
        "reasoning_tokens": sum(
            _token_count(item.get("reasoning_tokens")) for item in events
        ),
        "total_tokens": sum(_token_count(item.get("total_tokens")) for item in events),
        "web_search_calls": sum(
            _token_count(item.get("web_search_calls")) for item in events
        ),
    }


def _rolling_estimate(
    events: list[dict[str, Any]],
    *,
    operations: set[str],
    fallback: Mapping[str, Any],
) -> dict[str, Any]:
    costs = [
        float(item["calculated_cost_usd"])
        for item in events
        if str(item.get("operation") or "") in operations
        and item.get("calculated_cost_usd") is not None
    ][-20:]
    if not costs:
        return {
            **dict(fallback),
            "source": "initial_range",
            "sample_size": 0,
            "cache_cost_usd": 0.0,
        }
    average = sum(costs) / len(costs)
    return {
        "low_usd": round(min(min(costs), average * 0.75), 6),
        "estimated_usd": round(average, 6),
        "high_usd": round(max(max(costs), average * 1.25), 6),
        "web_search_possible": any(
            _token_count(item.get("web_search_calls")) > 0
            for item in events
            if str(item.get("operation") or "") in operations
        ),
        "source": "recent_average",
        "sample_size": len(costs),
        "cache_cost_usd": 0.0,
    }


class AIUsageLedger:
    """Keep a local usage mirror and best-effort app-owned Drive copy."""

    def __init__(
        self,
        local_path: Path,
        google_connection=None,
        *,
        drive_factory=build_drive_service,
    ) -> None:
        self.local_path = Path(local_path)
        self.google_connection = google_connection
        self.drive_factory = drive_factory
        self._lock = threading.RLock()
        self._drive_sync_succeeded: bool | None = None
        self._restore_attempted = False

    def _drive(self):
        if self.google_connection is None:
            return None
        credentials = self.google_connection.require_credentials()
        return self.drive_factory(credentials)

    def _restore_from_drive_if_needed(self) -> None:
        if self.local_path.is_file() or self._restore_attempted:
            return
        self._restore_attempted = True
        try:
            drive = self._drive()
            if drive is None:
                return
            folders = ensure_job_hunt_folders(drive)
            remote = find_child_file(
                drive,
                LEDGER_FILE_NAME,
                parent_id=str(folders["source"]["id"]),
                mime_type=JSON_MIME_TYPE,
            )
            if remote:
                download_drive_file(drive, str(remote["id"]), self.local_path)
        except Exception:
            # Usage reporting must never block the paid user action it measures.
            self._drive_sync_succeeded = False

    def _read(self) -> dict[str, Any]:
        self._restore_from_drive_if_needed()
        return _normalized_ledger(read_json(self.local_path, default=_default_ledger()))

    def _write(self, ledger: Mapping[str, Any]) -> None:
        value = _normalized_ledger(ledger)
        value["updated_at"] = datetime.now(TIME_ZONE).replace(microsecond=0).isoformat()
        write_json_atomic(self.local_path, value)

    def _sync_drive(self) -> bool:
        try:
            drive = self._drive()
            if drive is None:
                self._drive_sync_succeeded = None
                return False
            folders = ensure_job_hunt_folders(drive)
            existing = find_child_file(
                drive,
                LEDGER_FILE_NAME,
                parent_id=str(folders["source"]["id"]),
                mime_type=JSON_MIME_TYPE,
            )
            upload_or_update_file(
                drive,
                self.local_path,
                parent_id=str(folders["source"]["id"]),
                existing_file_id=str((existing or {}).get("id") or ""),
                mime_type=JSON_MIME_TYPE,
            )
            self._drive_sync_succeeded = True
            return True
        except Exception:
            self._drive_sync_succeeded = False
            return False

    def record_response(
        self,
        response: object,
        *,
        operation: str,
        model: str,
        context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = response_usage_event(
            response,
            operation=operation,
            model=model,
            context=context,
        )
        with self._lock:
            ledger = self._read()
            ledger["events"].append(event)
            self._write(ledger)
            self._sync_drive()
        return dict(event)

    @staticmethod
    def action_summary(
        events: list[Mapping[str, Any]],
        *,
        cache_reused: bool,
        expected_api_calls: int = 0,
    ) -> dict[str, Any]:
        prepared = [dict(item) for item in events if isinstance(item, Mapping)]
        totals = _period_totals(prepared)
        tracking_complete = len(prepared) >= max(0, int(expected_api_calls))
        if cache_reused and not expected_api_calls:
            tracking_complete = True
        return {
            **totals,
            "events": prepared,
            "cache_reused": bool(cache_reused),
            "expected_api_calls": max(0, int(expected_api_calls)),
            "tracking_complete": tracking_complete,
            "calculated_not_invoice": True,
        }

    def report(self, *, limit: int = 20) -> dict[str, Any]:
        with self._lock:
            ledger = self._read()
        events = [dict(item) for item in ledger.get("events") or []]
        now = datetime.now(TIME_ZONE)
        today_key = now.date().isoformat()
        month_key = now.strftime("%Y-%m")
        today_events = [
            item for item in events if str(item.get("recorded_at") or "")[:10] == today_key
        ]
        month_events = [
            item for item in events if str(item.get("recorded_at") or "")[:7] == month_key
        ]
        by_operation = {
            operation: _period_totals(
                [item for item in events if item.get("operation") == operation]
            )
            for operation in OPERATION_LABELS
        }
        return {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "currency": "USD",
            "calculated_not_invoice": True,
            "tracking_started_at": str((events[0] if events else {}).get("recorded_at") or ""),
            "includes_calls_before_feature_enabled": False,
            "all_time": _period_totals(events),
            "today": _period_totals(today_events),
            "current_month": _period_totals(month_events),
            "by_operation": by_operation,
            "estimates": {
                "official_job": _rolling_estimate(
                    events,
                    operations={"official_job_research", "exact_jd_extraction"},
                    fallback=DEFAULT_ESTIMATES["official_job"],
                ),
                "resume_plan": _rolling_estimate(
                    events,
                    operations={"resume_plan"},
                    fallback=DEFAULT_ESTIMATES["resume_plan"],
                ),
            },
            "recent_events": list(reversed(events[-max(1, min(int(limit), 100)) :])),
            "pricing": {
                "version": PRICING_VERSION,
                "model": "gpt-5.6-luna",
                "input_per_million_usd": 0.20,
                "cached_input_per_million_usd": 0.02,
                "cache_write_per_million_usd": 0.25,
                "output_per_million_usd": 1.20,
                "web_search_per_call_usd": 0.01,
                "source_url": PRICING_SOURCE_URL,
                "web_search_source_url": WEB_SEARCH_PRICE_SOURCE_URL,
            },
            "storage": {
                "local_file": self.local_path.name,
                "drive_path": LEDGER_DRIVE_PATH,
                "drive_sync_enabled": self.google_connection is not None,
                "last_drive_sync_succeeded": self._drive_sync_succeeded,
                "stores_prompts_or_documents": False,
            },
        }
