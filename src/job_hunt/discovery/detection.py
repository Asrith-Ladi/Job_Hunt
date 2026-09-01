"""High-confidence ATS detection without invoking undocumented endpoints."""

from __future__ import annotations

import html
import re
from dataclasses import asdict, dataclass
from typing import Iterable
from urllib.parse import parse_qs, unquote, urlsplit

from job_hunt.discovery.models import clean_text


DOCUMENTED_PROVIDERS = {"greenhouse", "lever", "workable", "smartrecruiters"}
EMBEDDED_URL_PATTERN = re.compile(r"(?:https?:)?//[^\s\"'<>\\]+", re.IGNORECASE)
EMBEDDED_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
COMPANY_SPECIFIC_PROVIDERS = {
    "workday",
    "oracle",
    "successfactors",
    "icims",
    "taleo",
    "phenom",
    "eightfold",
    "darwinbox",
}


@dataclass(frozen=True)
class DetectionResult:
    provider: str
    identifier: str
    confidence: float
    official_public_api: bool
    adapter_ready: bool
    evidence: str
    risk: str
    fallback: str
    region: str = "global"

    def to_dict(self):
        return asdict(self)


def _path_parts(url: str) -> list[str]:
    try:
        path = urlsplit(url).path
    except ValueError:
        return []
    return [unquote(part) for part in path.split("/") if part]


def detect_from_url(url: str) -> DetectionResult | None:
    raw_url = str(url or "").strip()
    if raw_url.startswith("//"):
        raw_url = f"https:{raw_url}"
    try:
        parsed = urlsplit(raw_url)
    except ValueError:
        return None
    host = (parsed.hostname or "").casefold()
    parts = _path_parts(raw_url)
    query = parse_qs(parsed.query)
    if not host:
        return None

    greenhouse_identifier = ""
    if host == "boards-api.greenhouse.io" and len(parts) >= 3:
        if parts[0].casefold() == "v1" and parts[1].casefold() == "boards":
            greenhouse_identifier = parts[2]
    elif host in {"boards.greenhouse.io", "job-boards.greenhouse.io"}:
        greenhouse_identifier = clean_text((query.get("for") or [""])[0])
        if not greenhouse_identifier and parts and parts[0].casefold() != "embed":
            greenhouse_identifier = parts[0]
    if greenhouse_identifier and EMBEDDED_IDENTIFIER_PATTERN.fullmatch(greenhouse_identifier):
        return DetectionResult(
            provider="greenhouse",
            identifier=greenhouse_identifier,
            confidence=0.99,
            official_public_api=True,
            adapter_ready=True,
            evidence=f"hostname {host}",
            risk="low",
            fallback="official hosted job board or sitemap",
        )
    lever_identifier = ""
    if host in {"api.lever.co", "api.eu.lever.co"} and len(parts) >= 3:
        if parts[0].casefold() == "v0" and parts[1].casefold() == "postings":
            lever_identifier = parts[2]
    elif host in {"jobs.lever.co", "jobs.eu.lever.co"} and parts:
        lever_identifier = parts[0]
    if lever_identifier and EMBEDDED_IDENTIFIER_PATTERN.fullmatch(lever_identifier):
        region = "eu" if host in {"jobs.eu.lever.co", "api.eu.lever.co"} else "global"
        return DetectionResult(
            provider="lever",
            identifier=lever_identifier,
            confidence=0.99,
            official_public_api=True,
            adapter_ready=True,
            evidence=f"hostname {host}",
            risk="low-medium",
            fallback="Lever hosted postings page or sitemap",
            region=region,
        )
    workable_identifier = ""
    if host == "www.workable.com" and len(parts) >= 3:
        if parts[0].casefold() == "api" and parts[1].casefold() == "accounts":
            workable_identifier = parts[2]
    elif host == "apply.workable.com" and parts:
        workable_identifier = parts[0]
    if workable_identifier and EMBEDDED_IDENTIFIER_PATTERN.fullmatch(workable_identifier):
        return DetectionResult(
            provider="workable",
            identifier=workable_identifier,
            confidence=0.99,
            official_public_api=True,
            adapter_ready=True,
            evidence="hostname apply.workable.com",
            risk="medium",
            fallback="Workable hosted careers page",
        )
    if host.endswith(".workable.com") and host not in {"www.workable.com", "apply.workable.com"}:
        return DetectionResult(
            provider="workable",
            identifier=host[: -len(".workable.com")],
            confidence=0.9,
            official_public_api=True,
            adapter_ready=True,
            evidence="Workable tenant hostname",
            risk="medium",
            fallback="Workable hosted careers page",
        )
    smartrecruiters_identifier = ""
    if host == "api.smartrecruiters.com" and len(parts) >= 4:
        if parts[0].casefold() == "v1" and parts[1].casefold() == "companies":
            smartrecruiters_identifier = parts[2]
    elif host in {"jobs.smartrecruiters.com", "careers.smartrecruiters.com"} and parts:
        smartrecruiters_identifier = parts[0]
    if (
        smartrecruiters_identifier
        and EMBEDDED_IDENTIFIER_PATTERN.fullmatch(smartrecruiters_identifier)
    ):
        return DetectionResult(
            provider="smartrecruiters",
            identifier=smartrecruiters_identifier,
            confidence=0.99,
            official_public_api=True,
            adapter_ready=True,
            evidence=f"hostname {host}",
            risk="low-medium",
            fallback="SmartRecruiters hosted careers page",
        )

    patterns = [
        ("myworkdayjobs.com", "workday"),
        ("oraclecloud.com", "oracle"),
        ("successfactors.com", "successfactors"),
        ("icims.com", "icims"),
        ("taleo.net", "taleo"),
        ("phenompeople.com", "phenom"),
        ("phenom.com", "phenom"),
        ("eightfold.ai", "eightfold"),
        ("darwinbox.in", "darwinbox"),
        ("darwinbox.com", "darwinbox"),
    ]
    for suffix, provider in patterns:
        if host == suffix or host.endswith(f".{suffix}"):
            return DetectionResult(
                provider=provider,
                identifier="",
                confidence=0.95,
                official_public_api=False,
                adapter_ready=False,
                evidence=f"hostname pattern {suffix}",
                risk="high",
                fallback="official sitemap, permitted static HTML, Gmail alert, or manual link",
            )
    return None


def detect_embedded_sources(page: str) -> list[DetectionResult]:
    """Detect supported public ATS identities embedded in an employer careers page.

    Detection is intentionally limited to explicit public URLs and provider widget
    configuration. It never treats an undocumented network endpoint as an official API.
    """

    decoded = html.unescape(str(page or "")).replace(r"\/", "/")
    candidates: list[DetectionResult] = []

    for match in EMBEDDED_URL_PATTERN.finditer(decoded):
        detected = detect_from_url(match.group(0).rstrip(".,);]"))
        if detected and detected.adapter_ready and detected.identifier:
            candidates.append(detected)

    greenhouse_patterns = (
        re.compile(
            r"(?:boardToken|board_token)\s*[:=]\s*[\"']([A-Za-z0-9][A-Za-z0-9._-]{0,199})[\"']",
            re.IGNORECASE,
        ),
        re.compile(
            r"greenhouse[^\n\r]{0,500}?[?&]for=([A-Za-z0-9][A-Za-z0-9._-]{0,199})",
            re.IGNORECASE,
        ),
    )
    for pattern in greenhouse_patterns:
        for match in pattern.finditer(decoded):
            candidates.append(
                DetectionResult(
                    provider="greenhouse",
                    identifier=match.group(1),
                    confidence=0.98,
                    official_public_api=True,
                    adapter_ready=True,
                    evidence="embedded Greenhouse job-board configuration",
                    risk="low",
                    fallback="official hosted job board or sitemap",
                )
            )

    unique: dict[tuple[str, str, str], DetectionResult] = {}
    for candidate in candidates:
        key = (
            candidate.provider,
            candidate.identifier.casefold(),
            candidate.region,
        )
        existing = unique.get(key)
        if existing is None or candidate.confidence > existing.confidence:
            unique[key] = candidate
    return sorted(
        unique.values(),
        key=lambda item: (-item.confidence, item.provider, item.identifier.casefold()),
    )


def _provider_from_label(label: str) -> str:
    normalized = clean_text(label).casefold()
    aliases = [
        ("greenhouse", "greenhouse"),
        ("smartrecruiters", "smartrecruiters"),
        ("workable", "workable"),
        ("lever", "lever"),
        ("workday", "workday"),
        ("oracle", "oracle"),
        ("successfactors", "successfactors"),
        ("icims", "icims"),
        ("taleo", "taleo"),
        ("phenom", "phenom"),
        ("eightfold", "eightfold"),
        ("darwinbox", "darwinbox"),
    ]
    for marker, provider in aliases:
        if marker in normalized:
            return provider
    return ""


def detect_source(
    *,
    source_type_label: str = "",
    identifier: str = "",
    urls: Iterable[str] = (),
) -> DetectionResult:
    labelled_provider = _provider_from_label(source_type_label)
    clean_identifier = clean_text(identifier)
    if labelled_provider in DOCUMENTED_PROVIDERS and clean_identifier:
        return DetectionResult(
            provider=labelled_provider,
            identifier=clean_identifier,
            confidence=0.98,
            official_public_api=True,
            adapter_ready=True,
            evidence="registry source type and explicit identifier",
            risk="low" if labelled_provider in {"greenhouse", "lever"} else "medium",
            fallback="official hosted page, sitemap, static HTML, Gmail alert, or manual link",
        )

    for url in urls:
        detected = detect_from_url(url)
        if detected:
            if clean_identifier and not detected.identifier:
                return DetectionResult(
                    detected.provider,
                    clean_identifier,
                    detected.confidence,
                    detected.official_public_api,
                    detected.provider in DOCUMENTED_PROVIDERS,
                    f"{detected.evidence}; registry identifier",
                    detected.risk,
                    detected.fallback,
                    detected.region,
                )
            return detected

    if labelled_provider in COMPANY_SPECIFIC_PROVIDERS:
        return DetectionResult(
            provider=labelled_provider,
            identifier=clean_identifier,
            confidence=0.85,
            official_public_api=False,
            adapter_ready=False,
            evidence="registry source type",
            risk="high",
            fallback="official sitemap, permitted static HTML, Gmail alert, or manual link",
        )
    return DetectionResult(
        provider="generic",
        identifier=clean_identifier,
        confidence=0.4,
        official_public_api=False,
        adapter_ready=False,
        evidence="no high-confidence documented ATS signal",
        risk="medium-high",
        fallback="official feed, sitemap, permitted static HTML, Gmail alert, or manual link",
    )
