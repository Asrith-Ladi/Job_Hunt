"""Read-only Gmail adapter that converts API payloads into safe internal messages."""

import base64
import binascii
from datetime import datetime, timezone

from job_hunt.models import AlertMessage


def _require_google_api():
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "Google API client is not installed. Use Python 3.12 and `pip install -e .`."
        ) from exc
    return build


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
        return cls(build("gmail", "v1", credentials=credentials, cache_discovery=False))

    def list_alerts(self, query, max_messages=500):
        messages = []
        page_token = None
        while len(messages) < max_messages:
            page_size = min(100, max_messages - len(messages))
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
            for reference in response.get("messages") or []:
                raw = (
                    self.service.users()
                    .messages()
                    .get(userId="me", id=reference["id"], format="full")
                    .execute()
                )
                messages.append(alert_message_from_api(raw))
                if len(messages) >= max_messages:
                    break
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return messages
