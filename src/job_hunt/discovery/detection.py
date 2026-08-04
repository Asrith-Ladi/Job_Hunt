"""High-confidence ATS detection without invoking undocumented endpoints."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable
from urllib.parse import unquote, urlsplit

from job_hunt.discovery.models import clean_text


DOCUMENTED_PROVIDERS = {"greenhouse", "lever", "workable", "smartrecruiters"}
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
    try:
        parsed = urlsplit(str(url or "").strip())
    except ValueError:
        return None
    host = (parsed.hostname or "").casefold()
    parts = _path_parts(url)
    if not host:
        return None

    if host in {"boards.greenhouse.io", "job-boards.greenhouse.io"} and parts:
        return DetectionResult(
            provider="greenhouse",
            identifier=parts[0],
            confidence=0.99,
            official_public_api=True,
            adapter_ready=True,
            evidence=f"hostname {host}",
            risk="low",
            fallback="official hosted job board or sitemap",
        )
    if host in {"jobs.lever.co", "jobs.eu.lever.co"} and parts:
        region = "eu" if host == "jobs.eu.lever.co" else "global"
        return DetectionResult(
            provider="lever",
            identifier=parts[0],
            confidence=0.99,
            official_public_api=True,
            adapter_ready=True,
            evidence=f"hostname {host}",
            risk="low-medium",
            fallback="Lever hosted postings page or sitemap",
            region=region,
        )
    if host == "apply.workable.com" and parts:
        return DetectionResult(
            provider="workable",
            identifier=parts[0],
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
    if host in {"jobs.smartrecruiters.com", "careers.smartrecruiters.com"} and parts:
        return DetectionResult(
            provider="smartrecruiters",
            identifier=parts[0],
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
