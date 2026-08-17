"""Normalized models for non-Gmail job discovery sources."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from job_hunt.experience import classify_experience_fit, extract_experience_range


MAX_DESCRIPTION_CHARS = 6000


def clean_text(value: Any, *, limit: int | None = None) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if limit is not None:
        text = text[:limit]
    return text


def canonical_public_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw or len(raw) > 4096:
        return ""
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError:
        return ""
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        return ""
    if parsed.username or parsed.password or (port and port != 443):
        return ""
    host = parsed.hostname.casefold()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit(("https", host, path, parsed.query, ""))


def stable_discovery_id(
    provider: str,
    company: str,
    external_id: str,
    official_url: str,
) -> str:
    identity = "|".join(
        [
            clean_text(provider).casefold(),
            clean_text(company).casefold(),
            clean_text(external_id).casefold(),
            canonical_public_url(official_url),
        ]
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def parse_iso_datetime(value: Any) -> datetime | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class DiscoveryFilters:
    keyword: str = ""
    location: str = ""
    posted_within_days: int = 15
    include_unknown_dates: bool = True
    max_jobs_per_source: int = 100
    target_experience_min_years: float = 5.0
    target_experience_max_years: float = 8.0
    strict_experience_filter: bool = False

    def validate(self) -> None:
        if not 1 <= int(self.posted_within_days) <= 90:
            raise ValueError("Posted-within days must be between 1 and 90.")
        if not 1 <= int(self.max_jobs_per_source) <= 250:
            raise ValueError("Maximum jobs per source must be between 1 and 250.")
        if self.target_experience_min_years < 0:
            raise ValueError("Target minimum experience cannot be negative.")
        if self.target_experience_max_years < self.target_experience_min_years:
            raise ValueError("Target maximum experience must be at least the minimum.")

    def matches_text(self, *values: str) -> bool:
        query = clean_text(self.keyword).casefold()
        if not query:
            return True

        def normalized(value: str) -> str:
            text = clean_text(value).casefold().replace("_", " ")
            return re.sub(r"[^\w+#.]+", " ", text, flags=re.UNICODE).strip()

        searchable = f" {' '.join(normalized(value) for value in values)} "
        searchable_tokens = searchable.split()
        compact_token_groups = {
            "".join(searchable_tokens[index : index + size])
            for size in (2, 3)
            for index in range(0, max(0, len(searchable_tokens) - size + 1))
        }
        terms = [normalized(term) for term in re.split(r"[,\n]", query)]

        def token_matches(requested: str, candidate: str) -> bool:
            if requested == candidate:
                return True
            if len(requested) < 4 or not candidate.startswith(requested):
                return False
            return candidate[len(requested) :] in {"s", "es", "ic", "ics", "ing"}

        def term_matches(term: str) -> bool:
            requested_tokens = term.split()
            if not requested_tokens:
                return False
            width = len(requested_tokens)
            for index in range(0, len(searchable_tokens) - width + 1):
                candidate_tokens = searchable_tokens[index : index + width]
                if all(
                    token_matches(requested, candidate)
                    for requested, candidate in zip(requested_tokens, candidate_tokens)
                ):
                    return True
            return width == 1 and len(term) >= 4 and term in compact_token_groups

        return any(
            term and term_matches(term)
            for term in terms
        )

    def matches_location(self, location: str) -> bool:
        requested = clean_text(self.location).casefold()
        if not requested:
            return True
        terms = [term for term in re.split(r"[,\n]", requested) if term.strip()]
        candidate = clean_text(location).casefold()
        return any(term.strip() in candidate for term in terms)

    def matches_date(self, posted_at: str) -> bool:
        parsed = parse_iso_datetime(posted_at)
        if parsed is None:
            return self.include_unknown_dates
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.posted_within_days)
        return parsed >= cutoff


@dataclass(frozen=True)
class SourceConfig:
    company: str
    provider: str
    identifier: str
    category: str = "Manual"
    careers_url: str = ""
    portal_url: str = ""
    public_feed_url: str = ""
    region: str = "global"
    company_id: str = ""
    fallback: str = ""
    source_type_label: str = ""


@dataclass
class DiscoveryJob:
    job_record_id: str
    company: str
    title: str
    location: str
    provider: str
    source_identifier: str
    source_type: str
    external_job_id: str
    official_url: str
    apply_url: str
    source_url: str
    description: str
    department: str
    employment_type: str
    workplace_type: str
    experience_text: str
    experience_min_years: float | None
    experience_max_years: float | None
    experience_fit: str
    posted_at: str
    updated_at: str
    date_provenance: str
    discovered_at: str
    first_seen_at: str
    last_seen_at: str
    source_confidence: str
    source_status: str
    application_status: str = "not_started"
    notes: str = ""

    @classmethod
    def create(
        cls,
        *,
        company: str,
        title: str,
        provider: str,
        source_identifier: str,
        source_type: str,
        external_job_id: str,
        official_url: str,
        discovered_at: str,
        filters: DiscoveryFilters,
        location: str = "",
        apply_url: str = "",
        source_url: str = "",
        description: str = "",
        department: str = "",
        employment_type: str = "",
        workplace_type: str = "",
        posted_at: str = "",
        updated_at: str = "",
        date_provenance: str = "unknown",
        source_confidence: str = "high",
        source_status: str = "active",
    ) -> "DiscoveryJob":
        clean_description = clean_text(description, limit=MAX_DESCRIPTION_CHARS)
        experience = extract_experience_range(clean_description)
        experience_text = ""
        if experience:
            minimum = (
                str(int(experience.minimum))
                if experience.minimum.is_integer()
                else str(experience.minimum)
            )
            if experience.maximum is None:
                experience_text = f"{minimum}+ years"
            else:
                maximum = (
                    str(int(experience.maximum))
                    if experience.maximum.is_integer()
                    else str(experience.maximum)
                )
                experience_text = f"{minimum}-{maximum} years"
        fit = classify_experience_fit(
            experience_text,
            filters.target_experience_min_years,
            filters.target_experience_max_years,
        )
        safe_official = canonical_public_url(official_url)
        safe_apply = canonical_public_url(apply_url)
        safe_source = canonical_public_url(source_url)
        return cls(
            job_record_id=stable_discovery_id(
                provider,
                company,
                external_job_id,
                safe_official,
            ),
            company=clean_text(company, limit=300),
            title=clean_text(title, limit=500),
            location=clean_text(location, limit=500),
            provider=clean_text(provider, limit=80).casefold(),
            source_identifier=clean_text(source_identifier, limit=300),
            source_type=clean_text(source_type, limit=80),
            external_job_id=clean_text(external_job_id, limit=300),
            official_url=safe_official,
            apply_url=safe_apply,
            source_url=safe_source,
            description=clean_description,
            department=clean_text(department, limit=500),
            employment_type=clean_text(employment_type, limit=200),
            workplace_type=clean_text(workplace_type, limit=200),
            experience_text=experience_text,
            experience_min_years=experience.minimum if experience else None,
            experience_max_years=experience.maximum if experience else None,
            experience_fit=fit,
            posted_at=clean_text(posted_at, limit=100),
            updated_at=clean_text(updated_at, limit=100),
            date_provenance=clean_text(date_provenance, limit=100) or "unknown",
            discovered_at=discovered_at,
            first_seen_at=discovered_at,
            last_seen_at=discovered_at,
            source_confidence=source_confidence,
            source_status=source_status,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceCheck:
    company: str
    category: str
    provider: str
    source_identifier: str
    strategy: str
    source_url: str
    status: str
    jobs_found: int
    jobs_exported: int
    warning: str
    fallback: str
    checked_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
