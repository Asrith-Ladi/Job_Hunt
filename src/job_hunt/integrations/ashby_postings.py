"""Resolve an exact public Ashby posting without searching for related jobs."""

from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.parse import unquote, urlsplit

from job_hunt.discovery.adapters import html_to_text
from job_hunt.discovery.http_client import PublicSourceError, SafeHttpClient
from job_hunt.discovery.models import canonical_public_url, clean_text


ASHBY_API_HOST = "api.ashbyhq.com"
ASHBY_JOB_HOST = "jobs.ashbyhq.com"
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
ASHBY_LINK_PATTERN = re.compile(
    r"https://jobs\.ashbyhq\.com/([^/\"'?#<>]+)/"
    r"([0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})"
    r"(?:/application)?",
    re.IGNORECASE,
)
BOARD_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")


@dataclass(frozen=True)
class ExactPostingResolution:
    """Outcome of checking whether a supplied URL is backed by an Ashby job board."""

    recognized: bool
    posting: dict[str, Any] | None = None
    warning: str = ""


def _path_parts(value: str) -> list[str]:
    try:
        return [unquote(part) for part in urlsplit(value).path.split("/") if part]
    except ValueError:
        return []


def _job_uuid(value: str) -> str:
    for part in _path_parts(value):
        if UUID_PATTERN.fullmatch(part):
            return part.casefold()
    return ""


def _direct_ashby_identity(value: str) -> tuple[str, str] | None:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if (parsed.hostname or "").casefold() != ASHBY_JOB_HOST:
        return None
    parts = _path_parts(value)
    if len(parts) < 2 or not BOARD_PATTERN.fullmatch(parts[0]):
        return None
    if not UUID_PATTERN.fullmatch(parts[1]):
        return None
    return parts[0], parts[1].casefold()


def _embedded_ashby_identity(page: str, expected_job_id: str) -> tuple[str, str] | None:
    decoded = html.unescape(str(page or "")).replace(r"\/", "/")
    for match in ASHBY_LINK_PATTERN.finditer(decoded):
        board, job_id = unquote(match.group(1)), match.group(2).casefold()
        if job_id == expected_job_id and BOARD_PATTERN.fullmatch(board):
            return board, job_id
    return None


def _source_fingerprint(board: str, item: Mapping[str, Any]) -> str:
    fields = {
        "board": board.casefold(),
        "id": clean_text(item.get("id")).casefold(),
        "title": clean_text(item.get("title")),
        "published_at": clean_text(item.get("publishedAt")),
        "description": clean_text(item.get("descriptionPlain")),
    }
    encoded = json.dumps(fields, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _display_enum(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text).replace("_", " ").strip()


class AshbyExactPostingResolver:
    """Map one supplied job URL to the same UUID in Ashby's public posting feed."""

    def __init__(self, http_client: SafeHttpClient) -> None:
        self.http = http_client

    def resolve(self, job: Mapping[str, Any]) -> ExactPostingResolution:
        official_url = canonical_public_url(job.get("official_url"))
        expected_job_id = _job_uuid(official_url)
        if not official_url or not expected_job_id:
            return ExactPostingResolution(False)

        identity = _direct_ashby_identity(official_url)
        if identity is None:
            try:
                hostname = (urlsplit(official_url).hostname or "").casefold()
                response = self.http.get(
                    official_url,
                    allowed_hosts={hostname},
                    accept="text/html, application/xhtml+xml",
                )
            except PublicSourceError:
                return ExactPostingResolution(False)
            identity = _embedded_ashby_identity(response.text, expected_job_id)
            if identity is None:
                return ExactPostingResolution(False)

        board, job_id = identity
        endpoint = f"https://{ASHBY_API_HOST}/posting-api/job-board/{board}"
        try:
            payload = self.http.get(
                endpoint,
                allowed_hosts={ASHBY_API_HOST},
                accept="application/json",
            ).json()
        except PublicSourceError as exc:
            return ExactPostingResolution(
                True,
                warning=f"The exact Ashby job feed is currently unavailable: {exc}",
            )

        jobs = payload.get("jobs") if isinstance(payload, dict) else None
        if not isinstance(jobs, list):
            return ExactPostingResolution(
                True,
                warning="The exact Ashby job feed returned an unsupported payload.",
            )
        exact = next(
            (
                item
                for item in jobs
                if isinstance(item, dict)
                and clean_text(item.get("id")).casefold() == job_id
            ),
            None,
        )
        if exact is None:
            return ExactPostingResolution(
                True,
                warning="The exact Ashby job ID is no longer present in the public job feed.",
            )

        description = clean_text(exact.get("descriptionPlain"))
        if not description:
            description = html_to_text(exact.get("descriptionHtml"))
        if not description:
            return ExactPostingResolution(
                True,
                warning="The exact Ashby job is active, but its public description is empty.",
            )

        return ExactPostingResolution(
            True,
            posting={
                "provider": "ashby",
                "board": board,
                "external_job_id": job_id,
                "company": clean_text(job.get("company")),
                "title": clean_text(exact.get("title")),
                "location": clean_text(exact.get("location")),
                "department": clean_text(exact.get("department") or exact.get("team")),
                "employment_type": _display_enum(exact.get("employmentType")),
                "workplace_type": _display_enum(exact.get("workplaceType")),
                "published_at": clean_text(exact.get("publishedAt")),
                "official_url": official_url,
                "ats_job_url": canonical_public_url(exact.get("jobUrl")),
                "apply_url": canonical_public_url(exact.get("applyUrl")),
                "description": description,
                "description_html": str(exact.get("descriptionHtml") or "")[:100_000],
                "source_url": endpoint,
                "source_fingerprint": _source_fingerprint(board, exact),
            },
        )


def resolve_exact_ashby_posting(
    job: Mapping[str, Any],
    *,
    client_factory: Callable[[], SafeHttpClient] = SafeHttpClient,
) -> ExactPostingResolution:
    """Resolve one job and always close the owned bounded HTTP client."""

    client = client_factory()
    try:
        return AshbyExactPostingResolver(client).resolve(job)
    finally:
        client.close()
