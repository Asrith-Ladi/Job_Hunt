"""Read-only Gmail adapter that converts API payloads into safe internal messages."""

import base64
import binascii
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

from job_hunt.jobs.models import AlertMessage


GMAIL_BATCH_SIZE = 25
GMAIL_HTTP_TIMEOUT_SECONDS = 30
ProgressCallback = Callable[[Mapping[str, Any]], None]


class GmailApiError(Exception):
    """Safe public failure for Gmail list/download operations."""


def _require_google_api():
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "Google API client is not installed. Use Python 3.12 and `pip install -e .`."
        ) from exc
    return build


def _authorized_http(credentials):
    try:
        from google_auth_httplib2 import AuthorizedHttp
        from httplib2 import Http
    except ImportError as exc:
        raise RuntimeError(
            "Google HTTP support is not installed. Use Python 3.12 and `pip install -e .`."
        ) from exc
    return AuthorizedHttp(
        credentials,
        http=Http(timeout=GMAIL_HTTP_TIMEOUT_SECONDS),
    )


def _emit(progress_callback: ProgressCallback | None, **values: Any) -> None:
    if progress_callback is not None:
        progress_callback(values)


def _decode_body(data):
    if not data:
        return ""
    padding = "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode((data + padding).encode("ascii")).decode(
            "utf-8", errors="replace"
        )
    except (binascii.Error, ValueError, UnicodeError):
        return ""


def _collect_parts(part, plain_parts, html_parts):
    if part.get("filename"):
        return
    mime_type = (part.get("mimeType") or "").casefold()
    data = (part.get("body") or {}).get("data")
    if mime_type == "text/plain" and data:
        plain_parts.append(_decode_body(data))
    elif mime_type == "text/html" and data:
        html_parts.append(_decode_body(data))
    for child in part.get("parts") or []:
        _collect_parts(child, plain_parts, html_parts)


def _headers(payload):
    return {
        (item.get("name") or "").casefold(): item.get("value") or ""
        for item in payload.get("headers") or []
    }


def alert_message_from_api(raw):
    payload = raw.get("payload") or {}
    headers = _headers(payload)
    plain_parts = []
    html_parts = []
    _collect_parts(payload, plain_parts, html_parts)
    timestamp_ms = int(raw.get("internalDate") or 0)
    received_at = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat()
    return AlertMessage(
        message_id=raw.get("id") or "",
        thread_id=raw.get("threadId") or "",
        sender=headers.get("from", ""),
        subject=headers.get("subject", ""),
        received_at=received_at,
        text_body="\n".join(plain_parts),
        html_body="\n".join(html_parts),
    )


class GoogleGmailReader:
    def __init__(self, service):
        self.service = service

    @classmethod
    def from_credentials(cls, credentials):
        build = _require_google_api()
        return cls(
            build(
                "gmail",
                "v1",
                http=_authorized_http(credentials),
                cache_discovery=False,
            )
        )

    def _message_request(self, message_id: str):
        return self.service.users().messages().get(
            userId="me",
            id=message_id,
            format="full",
        )

    def _load_message_batch(self, references: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
        """Fetch one bounded group, retrying any partial batch failures once."""

        batch_factory = getattr(self.service, "new_batch_http_request", None)
        if not callable(batch_factory):
            try:
                return [self._message_request(str(item["id"])).execute() for item in references]
            except Exception as exc:
                raise GmailApiError(
                    "Gmail could not download the matching alert messages. Try again."
                ) from exc

        responses: dict[str, dict[str, Any]] = {}
        failures: dict[str, Exception] = {}

        def completed(request_id: str, response: dict[str, Any], exception: Exception | None):
            if exception is not None:
                failures[request_id] = exception
            elif response is not None:
                responses[request_id] = response

        batch = batch_factory()
        for index, reference in enumerate(references):
            batch.add(
                self._message_request(str(reference["id"])),
                callback=completed,
                request_id=str(index),
            )
        try:
            batch.execute()
        except Exception as exc:
            raise GmailApiError(
                "Gmail did not respond while downloading alert messages. Try again."
            ) from exc

        for request_id in failures:
            try:
                reference = references[int(request_id)]
                responses[request_id] = self._message_request(str(reference["id"])).execute()
            except Exception as exc:
                raise GmailApiError(
                    "Gmail could not download all matching alert messages. Try again."
                ) from exc

        if len(responses) != len(references):
            raise GmailApiError(
                "Gmail returned an incomplete alert-message batch. Try again."
            )
        return [responses[str(index)] for index in range(len(references))]

    def list_alerts(
        self,
        query,
        max_messages=500,
        progress_callback: ProgressCallback | None = None,
    ):
        messages = []
        page_token = None
        while len(messages) < max_messages:
            page_size = min(100, max_messages - len(messages))
            try:
                response = (
                    self.service.users()
                    .messages()
                    .list(
                        userId="me",
                        q=query,
                        maxResults=page_size,
                        pageToken=page_token,
                    )
                    .execute()
                )
            except Exception as exc:
                raise GmailApiError(
                    "Gmail did not respond while listing approved alert messages. Try again."
                ) from exc

            references = list(response.get("messages") or [])
            try:
                result_estimate = max(0, int(response.get("resultSizeEstimate") or 0))
            except (TypeError, ValueError):
                result_estimate = 0
            expected_total = min(
                max_messages,
                max(len(messages) + len(references), result_estimate),
            )
            _emit(
                progress_callback,
                stage="gmail_fetch",
                message=(
                    f"Gmail found {expected_total} matching alert message"
                    f"{'s' if expected_total != 1 else ''}. Downloading content in batches."
                ),
                current_item="Preparing Gmail message batches",
                completed_items=len(messages),
                total_items=expected_total,
                matches_found=0,
            )

            for start in range(0, len(references), GMAIL_BATCH_SIZE):
                group = references[start : start + GMAIL_BATCH_SIZE]
                for raw in self._load_message_batch(group):
                    messages.append(alert_message_from_api(raw))
                _emit(
                    progress_callback,
                    stage="gmail_fetch",
                    message=(
                        f"Downloaded {len(messages)} of {expected_total} matching Gmail alerts."
                    ),
                    current_item=f"Gmail messages {max(1, len(messages) - len(group) + 1)}-{len(messages)}",
                    completed_items=len(messages),
                    total_items=expected_total,
                    matches_found=0,
                )
                if len(messages) >= max_messages:
                    break
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return messages
