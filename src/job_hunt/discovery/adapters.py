"""Documented public ATS adapters for published employer jobs."""

from __future__ import annotations

import html
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote, urlencode

from job_hunt.discovery.http_client import PublicSourceError, SafeHttpClient
from job_hunt.discovery.models import (
    DiscoveryFilters,
    DiscoveryJob,
    SourceConfig,
    canonical_public_url,
    clean_text,
    parse_iso_datetime,
)


IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
MAX_SCAN_JOBS = 500


class _PlainTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.casefold() in {"script", "style", "noscript"}:
            self.ignored_depth += 1

    def handle_endtag(self, tag):
        if tag.casefold() in {"script", "style", "noscript"} and self.ignored_depth:
            self.ignored_depth -= 1

    def handle_data(self, data):
        if not self.ignored_depth:
            self.parts.append(data)


def html_to_text(value: Any) -> str:
    parser = _PlainTextParser()
    try:
        parser.feed(html.unescape(str(value or "")))
        parser.close()
    except Exception:
        return clean_text(html.unescape(str(value or "")))
    return clean_text(" ".join(parser.parts))


def _identifier(value: str) -> str:
    cleaned = clean_text(value)
    if not IDENTIFIER_PATTERN.fullmatch(cleaned):
        raise ValueError("The ATS identifier contains unsupported characters.")
    return cleaned


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _sequence(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _location_text(value: Any) -> str:
    if isinstance(value, str):
        return clean_text(value)
    item = _mapping(value)
    direct = item.get("location_str") or item.get("name")
    if direct:
        return clean_text(direct)
    parts = [
        item.get("city"),
        item.get("region") or item.get("state") or item.get("region_code"),
        item.get("country") or item.get("country_name"),
    ]
    return ", ".join(clean_text(part) for part in parts if clean_text(part))


def _passes_non_relevance(job: DiscoveryJob, filters: DiscoveryFilters) -> bool:
    if not filters.matches_location(job.location):
        return False
    if not filters.matches_date(job.posted_at):
        return False
    if filters.strict_experience_filter and job.experience_fit == "outside_target":
        return False
    return True


def filter_and_rank_jobs(
    jobs: list[DiscoveryJob],
    filters: DiscoveryFilters,
) -> list[DiscoveryJob]:
    """Apply shared filters once, preserving why each result was selected."""

    matched: list[DiscoveryJob] = []
    for job in jobs:
        relevance = filters.relevance_match(
            title=job.title,
            description=job.description,
            department=job.department,
        )
        if relevance is None or not _passes_non_relevance(job, filters):
            continue
        match_type, terms, score = relevance
        job.match_type = match_type
        job.matched_terms = ", ".join(dict.fromkeys(terms))
        job.match_score = score
        matched.append(job)

    def sort_key(job: DiscoveryJob) -> tuple[int, float, str, str]:
        posted = parse_iso_datetime(job.posted_at)
        timestamp = posted.timestamp() if posted else 0.0
        return (-job.match_score, -timestamp, job.title.casefold(), job.official_url)

    return sorted(matched, key=sort_key)[: filters.max_jobs_per_source]


class AtsAdapter(ABC):
    provider = ""
    official_public_api = True

    def __init__(self, http_client: SafeHttpClient) -> None:
        self.http = http_client

    @abstractmethod
    def endpoint(self, source: SourceConfig) -> str:
        raise NotImplementedError

    @abstractmethod
    def fetch(
        self,
        source: SourceConfig,
        filters: DiscoveryFilters,
    ) -> list[DiscoveryJob]:
        raise NotImplementedError


class GreenhouseAdapter(AtsAdapter):
    provider = "greenhouse"
    allowed_hosts = {"boards-api.greenhouse.io"}

    def endpoint(self, source: SourceConfig) -> str:
        token = quote(_identifier(source.identifier), safe="")
        return f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"

    def fetch(self, source: SourceConfig, filters: DiscoveryFilters) -> list[DiscoveryJob]:
        endpoint = self.endpoint(source)
        payload = self.http.get(endpoint, allowed_hosts=self.allowed_hosts).json()
        jobs = _sequence(_mapping(payload).get("jobs"))
        discovered_at = _now()
        results: list[DiscoveryJob] = []
        for raw in jobs[:MAX_SCAN_JOBS]:
            item = _mapping(raw)
            external_id = clean_text(item.get("id"))
            official_url = canonical_public_url(item.get("absolute_url"))
            if not external_id or not official_url:
                continue
            departments = ", ".join(
                clean_text(entry.get("name"))
                for entry in _sequence(item.get("departments"))
                if isinstance(entry, dict) and clean_text(entry.get("name"))
            )
            posted_at = clean_text(item.get("first_published"))
            job = DiscoveryJob.create(
                company=source.company,
                title=clean_text(item.get("title")),
                location=_location_text(item.get("location")),
                provider=self.provider,
                source_identifier=source.identifier,
                source_type="official_public_api",
                external_job_id=external_id,
                official_url=official_url,
                apply_url=official_url,
                source_url=endpoint,
                description=html_to_text(item.get("content")),
                department=departments,
                employment_type="",
                workplace_type="",
                posted_at=posted_at,
                updated_at=clean_text(item.get("updated_at")),
                date_provenance=("first_published" if posted_at else "unknown"),
                discovered_at=discovered_at,
                filters=filters,
            )
            if job.title:
                results.append(job)
        return results


def build_lever_job(
    item: dict[str, Any],
    source: SourceConfig,
    filters: DiscoveryFilters,
    *,
    discovered_at: str,
    source_url: str,
    source_type: str = "official_public_api",
    posted_at: str = "",
    updated_at: str = "",
    date_provenance: str = "unknown",
) -> DiscoveryJob | None:
    """Normalize one public Lever-shaped record from an API or employer page."""

    categories = _mapping(item.get("categories"))
    urls = _mapping(item.get("urls"))
    description_parts = [item.get("descriptionPlain"), item.get("additionalPlain")]
    for section in _sequence(item.get("lists")):
        if isinstance(section, dict):
            description_parts.extend([section.get("text"), html_to_text(section.get("content"))])
    official_url = canonical_public_url(item.get("hostedUrl") or urls.get("show"))
    external_id = clean_text(item.get("id"))
    if not official_url or not external_id:
        return None
    return DiscoveryJob.create(
        company=source.company,
        title=clean_text(item.get("text") or item.get("title")),
        location=clean_text(categories.get("location")),
        provider="lever",
        source_identifier=source.identifier,
        source_type=source_type,
        external_job_id=external_id,
        official_url=official_url,
        apply_url=canonical_public_url(item.get("applyUrl") or urls.get("apply"))
        or official_url,
        source_url=source_url,
        description=" ".join(clean_text(part) for part in description_parts if part),
        department=clean_text(categories.get("department") or categories.get("team")),
        employment_type=clean_text(categories.get("commitment")),
        workplace_type=clean_text(item.get("workplaceType")),
        posted_at=posted_at,
        updated_at=updated_at,
        date_provenance=date_provenance,
        discovered_at=discovered_at,
        filters=filters,
    )


class LeverAdapter(AtsAdapter):
    provider = "lever"
    allowed_hosts = {"api.lever.co", "api.eu.lever.co"}

    def endpoint(self, source: SourceConfig) -> str:
        slug = quote(_identifier(source.identifier), safe="")
        host = "api.eu.lever.co" if source.region.casefold() == "eu" else "api.lever.co"
        return f"https://{host}/v0/postings/{slug}"

    def fetch(self, source: SourceConfig, filters: DiscoveryFilters) -> list[DiscoveryJob]:
        base = self.endpoint(source)
        discovered_at = _now()
        results: list[DiscoveryJob] = []
        scanned = 0
        skip = 0
        page_size = 100
        while scanned < MAX_SCAN_JOBS:
            query = urlencode({"mode": "json", "skip": skip, "limit": page_size})
            page_url = f"{base}?{query}"
            payload = self.http.get(page_url, allowed_hosts=self.allowed_hosts).json()
            page = _sequence(payload)
            for raw in page:
                item = _mapping(raw)
                job = build_lever_job(
                    item,
                    source,
                    filters,
                    discovered_at=discovered_at,
                    source_url=page_url,
                )
                if job is not None and job.title:
                    results.append(job)
            scanned += len(page)
            if len(page) < page_size:
                break
            skip += page_size
        return results


class WorkableAdapter(AtsAdapter):
    provider = "workable"
    # The documented compatibility endpoint currently redirects to Workable's
    # public widget endpoint. Both hosts are Workable-owned and are validated
    # again on every redirect by SafeHttpClient.
    allowed_hosts = {"www.workable.com", "apply.workable.com"}

    def endpoint(self, source: SourceConfig) -> str:
        subdomain = quote(_identifier(source.identifier), safe="")
        return f"https://www.workable.com/api/accounts/{subdomain}?details=true"

    def fetch(self, source: SourceConfig, filters: DiscoveryFilters) -> list[DiscoveryJob]:
        endpoint = self.endpoint(source)
        payload = self.http.get(endpoint, allowed_hosts=self.allowed_hosts).json()
        mapping = _mapping(payload)
        jobs = _sequence(mapping.get("jobs") or mapping.get("results"))
        discovered_at = _now()
        results: list[DiscoveryJob] = []
        for raw in jobs[:MAX_SCAN_JOBS]:
            item = _mapping(raw)
            external_id = clean_text(item.get("id") or item.get("shortcode"))
            shortcode = clean_text(item.get("shortcode"))
            fallback_url = (
                f"https://apply.workable.com/{quote(source.identifier, safe='')}/j/{quote(shortcode, safe='')}/"
                if shortcode
                else ""
            )
            official_url = canonical_public_url(
                item.get("shortlink") or item.get("url") or fallback_url
            )
            if not external_id or not official_url:
                continue
            description = " ".join(
                html_to_text(item.get(key))
                for key in ["description", "requirements", "benefits"]
                if item.get(key)
            )
            posted_at = clean_text(item.get("created_at"))
            job = DiscoveryJob.create(
                company=source.company,
                title=clean_text(item.get("title") or item.get("full_title")),
                location=_location_text(item.get("location")),
                provider=self.provider,
                source_identifier=source.identifier,
                source_type="official_public_api",
                external_job_id=external_id,
                official_url=official_url,
                apply_url=canonical_public_url(item.get("application_url")) or official_url,
                source_url=endpoint,
                description=description,
                department=clean_text(item.get("department")),
                employment_type=clean_text(item.get("employment_type")),
                workplace_type=clean_text(
                    _mapping(item.get("location")).get("workplace_type")
                    or item.get("workplace_type")
                ),
                posted_at=posted_at,
                updated_at=clean_text(item.get("updated_at")),
                date_provenance=("provider_created_at" if posted_at else "unknown"),
                discovered_at=discovered_at,
                filters=filters,
            )
            if job.title:
                results.append(job)
        return results


def _smart_description(detail: dict[str, Any]) -> str:
    job_ad = _mapping(detail.get("jobAd"))
    sections = _mapping(job_ad.get("sections"))
    values: list[str] = []
    for key in [
        "companyDescription",
        "jobDescription",
        "qualifications",
        "additionalInformation",
    ]:
        section = _mapping(sections.get(key))
        if section.get("text"):
            values.append(html_to_text(section["text"]))
    return " ".join(values)


class SmartRecruitersAdapter(AtsAdapter):
    provider = "smartrecruiters"
    allowed_hosts = {"api.smartrecruiters.com"}

    def endpoint(self, source: SourceConfig) -> str:
        identifier = quote(_identifier(source.identifier), safe="")
        return f"https://api.smartrecruiters.com/v1/companies/{identifier}/postings"

    def fetch(self, source: SourceConfig, filters: DiscoveryFilters) -> list[DiscoveryJob]:
        base = self.endpoint(source)
        discovered_at = _now()
        results: list[DiscoveryJob] = []
        offset = 0
        page_size = 100
        scanned = 0
        while scanned < MAX_SCAN_JOBS:
            page_url = f"{base}?{urlencode({'limit': page_size, 'offset': offset})}"
            payload = _mapping(self.http.get(page_url, allowed_hosts=self.allowed_hosts).json())
            page = _sequence(payload.get("content"))
            for raw in page:
                item = _mapping(raw)
                title = clean_text(item.get("name"))
                location = _location_text(item.get("location"))
                posted_at = clean_text(item.get("releasedDate"))
                department = clean_text(_mapping(item.get("department")).get("label"))
                if not filters.matches_location(location) or not filters.matches_date(posted_at):
                    continue
                external_id = clean_text(item.get("id"))
                if not external_id:
                    continue
                detail_url = f"{base}/{quote(external_id, safe='')}"
                detail = _mapping(
                    self.http.get(detail_url, allowed_hosts=self.allowed_hosts).json()
                )
                official_url = canonical_public_url(
                    detail.get("jobAdUrl")
                    or detail.get("applyUrl")
                    or f"https://jobs.smartrecruiters.com/{quote(source.identifier, safe='')}/{quote(external_id, safe='')}"
                )
                if not official_url:
                    continue
                job = DiscoveryJob.create(
                    company=source.company,
                    title=title or clean_text(detail.get("name")),
                    location=location or _location_text(detail.get("location")),
                    provider=self.provider,
                    source_identifier=source.identifier,
                    source_type="official_public_api",
                    external_job_id=external_id,
                    official_url=official_url,
                    apply_url=canonical_public_url(detail.get("applyUrl")) or official_url,
                    source_url=detail_url,
                    description=_smart_description(detail),
                    department=department,
                    employment_type=clean_text(_mapping(item.get("typeOfEmployment")).get("label")),
                    workplace_type=(
                        "remote" if _mapping(item.get("location")).get("remote") else ""
                    ),
                    posted_at=posted_at,
                    updated_at="",
                    date_provenance=("releasedDate" if posted_at else "unknown"),
                    discovered_at=discovered_at,
                    filters=filters,
                )
                if job.title:
                    results.append(job)
            scanned += len(page)
            total = int(payload.get("totalFound") or 0)
            offset += len(page)
            if not page or len(page) < page_size or (total and offset >= total):
                break
        return results


ADAPTER_TYPES = {
    "greenhouse": GreenhouseAdapter,
    "lever": LeverAdapter,
    "workable": WorkableAdapter,
    "smartrecruiters": SmartRecruitersAdapter,
}


def adapter_for(provider: str, http_client: SafeHttpClient) -> AtsAdapter:
    adapter_type = ADAPTER_TYPES.get(clean_text(provider).casefold())
    if adapter_type is None:
        raise PublicSourceError("No documented public adapter is enabled for this provider.")
    return adapter_type(http_client)


def supported_providers() -> list[str]:
    return list(ADAPTER_TYPES)
