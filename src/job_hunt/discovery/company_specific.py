"""Bounded adapters for public employer JSON that is not a documented ATS API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit

from job_hunt.discovery.adapters import html_to_text
from job_hunt.discovery.http_client import PublicSourceError, SafeHttpClient
from job_hunt.discovery.models import (
    DiscoveryFilters,
    DiscoveryJob,
    SourceConfig,
    canonical_public_url,
    clean_text,
    parse_iso_datetime,
)


INFOSYS_CAREERS_HOSTS = {"career.infosys.com"}
INFOSYS_DATA_HOSTS = {"intapgateway.infosysapps.com"}
INFOSYS_CONFIG_PATH = "/assets/environments/environment.json"
INFOSYS_DATA_PATH = "/careersci/search/intapjbsrch"
INFOSYS_MAX_RESPONSE_BYTES = 8 * 1024 * 1024
INFOSYS_TIMEOUT_SECONDS = 60.0
INFOSYS_MAX_JOBS = 5_000


@dataclass(frozen=True)
class CompanyStructuredOutcome:
    jobs: list[DiscoveryJob]
    strategy: str
    source_url: str
    provider: str
    identifier: str
    warning: str = ""


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _sequence(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _host(value: str) -> str:
    try:
        return (urlsplit(value).hostname or "").casefold().rstrip(".")
    except ValueError:
        return ""


def _description(item: dict[str, Any]) -> str:
    minimum = clean_text(item.get("minExperienceLevel"))
    maximum = clean_text(item.get("maxExperienceLevel"))
    experience = ""
    if minimum and maximum:
        experience = f"Required experience: {minimum}-{maximum} years."
    elif minimum:
        experience = f"Required experience: {minimum}+ years."

    values = [
        experience,
        item.get("postingDescription"),
        item.get("technicalRequirement"),
        item.get("rolesResponsibilities"),
        item.get("additionalResponsibility"),
        item.get("preferredSkills"),
        item.get("genericSkills"),
        item.get("educationalRequirement"),
    ]
    return clean_text(" ".join(html_to_text(value) for value in values if value))


def _not_expired(item: dict[str, Any], discovered_at: str) -> bool:
    expiry = parse_iso_datetime(clean_text(item.get("expiryDate")))
    if expiry is None:
        return True
    observed = parse_iso_datetime(discovered_at) or datetime.now(timezone.utc)
    return expiry >= observed


def _infosys_jobs(
    http: SafeHttpClient,
    source: SourceConfig,
    filters: DiscoveryFilters,
    *,
    page_url: str,
    discovered_at: str,
) -> CompanyStructuredOutcome:
    config_url = urljoin(page_url, INFOSYS_CONFIG_PATH)
    config = _mapping(
        http.get(
            config_url,
            allowed_hosts=INFOSYS_CAREERS_HOSTS,
            accept="application/json",
        ).json()
    )
    data_base = canonical_public_url(config.get("JobsUnAuthUrl"))
    parsed_base = urlsplit(data_base)
    if (
        _host(data_base) not in INFOSYS_DATA_HOSTS
        or parsed_base.path.rstrip("/") != INFOSYS_DATA_PATH
    ):
        raise PublicSourceError("Infosys did not publish an approved careers-data endpoint.")

    query = urlencode({"sourceId": "1", "searchText": "ALL"})
    endpoint = f"{data_base.rstrip('/')}/getCareerSearchJobs?{query}"
    payload = http.get(
        endpoint,
        allowed_hosts=INFOSYS_DATA_HOSTS,
        accept="application/json",
        max_response_bytes=INFOSYS_MAX_RESPONSE_BYTES,
        timeout_seconds=INFOSYS_TIMEOUT_SECONDS,
    ).json()
    if not isinstance(payload, list):
        raise PublicSourceError("The Infosys careers-data response had an unsupported format.")

    jobs: list[DiscoveryJob] = []
    detail_base = "https://career.infosys.com/jobdesc"
    for raw in _sequence(payload)[:INFOSYS_MAX_JOBS]:
        item = _mapping(raw)
        title = clean_text(item.get("postingTitle"))
        reference = clean_text(item.get("referenceCode"))
        external_id = reference or clean_text(item.get("postingId"))
        if not title or not external_id or not _not_expired(item, discovered_at):
            continue
        official_url = f"{detail_base}?{urlencode({'jobReferenceCode': reference})}"
        if not reference:
            official_url = canonical_public_url(page_url)
        job = DiscoveryJob.create(
            company=source.company,
            title=title,
            location=clean_text(item.get("location")),
            provider="infosys",
            source_identifier="career.infosys.com",
            source_type="official_company_json",
            external_job_id=external_id,
            official_url=official_url,
            apply_url=official_url,
            source_url=endpoint,
            description=_description(item),
            department=clean_text(item.get("functionalArea") or item.get("unit")),
            employment_type="",
            workplace_type="",
            posted_at=clean_text(item.get("createdOn")),
            updated_at="",
            date_provenance="employer_createdOn",
            discovered_at=discovered_at,
            filters=filters,
            source_confidence="high",
        )
        jobs.append(job)

    return CompanyStructuredOutcome(
        jobs=jobs,
        strategy="official_company_json",
        source_url=endpoint,
        provider="infosys",
        identifier="career.infosys.com",
        warning=(
            "Infosys exposes this JSON to its public careers page, but it is undocumented "
            "and may change without notice; the official careers page remains the fallback."
        ),
    )


def discover_company_structured_source(
    http: SafeHttpClient,
    source: SourceConfig,
    filters: DiscoveryFilters,
    *,
    page_url: str,
    discovered_at: str,
) -> CompanyStructuredOutcome | None:
    """Return a supported employer-specific result, or ``None`` for generic handling."""

    if _host(page_url) in INFOSYS_CAREERS_HOSTS:
        return _infosys_jobs(
            http,
            source,
            filters,
            page_url=page_url,
            discovered_at=discovered_at,
        )
    return None
