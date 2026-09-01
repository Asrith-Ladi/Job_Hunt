"""Bounded official feed, sitemap, JSON-LD, and static HTML discovery."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree

from job_hunt.discovery.adapters import adapter_for, build_lever_job, html_to_text
from job_hunt.discovery.detection import detect_embedded_sources
from job_hunt.discovery.http_client import (
    AccessStoppedError,
    PublicSourceError,
    SafeHttpClient,
)
from job_hunt.discovery.models import (
    DiscoveryFilters,
    DiscoveryJob,
    SourceConfig,
    canonical_public_url,
    clean_text,
)


JOB_PATH_MARKERS = (
    "/job",
    "/jobs/",
    "/career/",
    "/careers/",
    "/position",
    "/positions/",
    "/opening",
    "/vacancy",
    "/requisition",
)
KNOWN_ATS_HOSTS = {
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
    "jobs.lever.co",
    "jobs.eu.lever.co",
    "apply.workable.com",
    "jobs.smartrecruiters.com",
    "careers.smartrecruiters.com",
    "myworkdayjobs.com",
    "successfactors.com",
    "icims.com",
    "taleo.net",
    "eightfold.ai",
}
PROTECTED_OR_AGGREGATOR_HOSTS = {
    "linkedin.com",
    "naukri.com",
    "indeed.com",
    "glassdoor.com",
}
MAX_SITEMAP_URLS = 2000
MAX_SITEMAP_CHILDREN = 5
MAX_GENERIC_JOBS = 500


@dataclass(frozen=True)
class GenericDiscoveryOutcome:
    jobs: list[DiscoveryJob]
    strategy: str
    warning: str = ""
    source_url: str = ""
    detected_provider: str = ""
    detected_identifier: str = ""

    def __iter__(self):
        """Preserve the former three-value result contract for internal callers."""

        yield self.jobs
        yield self.strategy
        yield self.warning


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].casefold()


def _date_text(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        return text
    if parsed.tzinfo is None:
        from datetime import timezone

        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def _external_id(url: str, supplied: Any = "") -> str:
    clean_supplied = clean_text(supplied)
    if clean_supplied:
        return clean_supplied
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]


def _url_title(url: str) -> str:
    path = urlsplit(url).path.rstrip("/")
    slug = path.rsplit("/", 1)[-1]
    slug = re.sub(r"[-_]+", " ", slug)
    slug = re.sub(r"\b\d{5,}\b", "", slug)
    return clean_text(slug).title()


def _hostname(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").casefold()
    except ValueError:
        return ""


def _host_allowed(host: str, allowed: set[str]) -> bool:
    if not host:
        return False
    if any(
        host == blocked or host.endswith(f".{blocked}") for blocked in PROTECTED_OR_AGGREGATOR_HOSTS
    ):
        return False
    return any(
        host == item or host.endswith(f".{item}") or item.endswith(f".{host}") for item in allowed
    )


def _allowed_hosts(source: SourceConfig) -> set[str]:
    hosts = {
        _hostname(url)
        for url in [source.careers_url, source.portal_url, source.public_feed_url]
        if _hostname(url)
    }
    hosts.update(KNOWN_ATS_HOSTS)
    return hosts


def _is_job_like(url: str) -> bool:
    path = urlsplit(url).path.casefold()
    return any(marker in path for marker in JOB_PATH_MARKERS)


class _CareerHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._current_href = ""
        self._link_parts: list[str] = []
        self._json_kind = ""
        self._json_parts: list[str] = []
        self.json_ld: list[str] = []
        self.structured_json: list[str] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag.casefold() == "a" and attributes.get("href"):
            self._current_href = str(attributes["href"])
            self._link_parts = []
        if tag.casefold() == "script":
            script_type = str(attributes.get("type") or "").casefold()
            script_id = str(attributes.get("id") or "").casefold()
            if "ld+json" in script_type:
                self._json_kind = "json_ld"
                self._json_parts = []
            elif script_id == "__next_data__" or script_type == "application/json":
                self._json_kind = "structured_json"
                self._json_parts = []

    def handle_data(self, data):
        if self._current_href:
            self._link_parts.append(data)
        if self._json_kind:
            self._json_parts.append(data)

    def handle_endtag(self, tag):
        if tag.casefold() == "a" and self._current_href:
            self.links.append((self._current_href, clean_text(" ".join(self._link_parts))))
            self._current_href = ""
            self._link_parts = []
        if tag.casefold() == "script" and self._json_kind:
            target = self.json_ld if self._json_kind == "json_ld" else self.structured_json
            target.append("".join(self._json_parts))
            self._json_kind = ""
            self._json_parts = []


def _walk_json_ld(value: Any):
    if isinstance(value, list):
        for item in value:
            yield from _walk_json_ld(item)
    elif isinstance(value, dict):
        if "@graph" in value:
            yield from _walk_json_ld(value["@graph"])
        item_type = value.get("@type")
        types = item_type if isinstance(item_type, list) else [item_type]
        if any(clean_text(item).casefold() == "jobposting" for item in types):
            yield value


def _walk_mappings(value: Any):
    if isinstance(value, list):
        for item in value:
            yield from _walk_mappings(item)
    elif isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk_mappings(item)


def _lever_job_identity(value: Any) -> tuple[str, str, str] | None:
    url = canonical_public_url(value)
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold()
    if host not in {"jobs.lever.co", "jobs.eu.lever.co"}:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None
    slug, job_id = parts[:2]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}", slug):
        return None
    return slug, job_id, ("eu" if host == "jobs.eu.lever.co" else "global")


def _json_ld_location(value: Any) -> str:
    locations = value if isinstance(value, list) else [value]
    output: list[str] = []
    for location in locations:
        if not isinstance(location, dict):
            continue
        address = location.get("address")
        if isinstance(address, dict):
            parts = [
                address.get("addressLocality"),
                address.get("addressRegion"),
                address.get("addressCountry"),
            ]
            text = ", ".join(clean_text(part) for part in parts if clean_text(part))
        else:
            text = clean_text(address or location.get("name"))
        if text:
            output.append(text)
    return "; ".join(dict.fromkeys(output))


class GenericPublicDiscovery:
    def __init__(self, http_client: SafeHttpClient) -> None:
        self.http = http_client

    def discover(
        self,
        source: SourceConfig,
        filters: DiscoveryFilters,
        *,
        discovered_at: str,
    ) -> GenericDiscoveryOutcome:
        warnings: list[str] = []
        if source.public_feed_url:
            try:
                jobs = self._feed(source, filters, discovered_at)
            except PublicSourceError as exc:
                warnings.append(str(exc))
            else:
                if jobs:
                    return GenericDiscoveryOutcome(
                        jobs=jobs,
                        strategy="public_feed",
                        source_url=source.public_feed_url,
                    )

        page_url = source.portal_url or source.careers_url
        if page_url:
            try:
                page_outcome = self._static_page(source, page_url, filters, discovered_at)
            except PublicSourceError as exc:
                warnings.append(str(exc))
            else:
                if page_outcome.warning:
                    warnings.append(page_outcome.warning)
                if page_outcome.jobs or page_outcome.detected_provider:
                    return replace(
                        page_outcome,
                        warning="; ".join(dict.fromkeys(warnings)),
                    )

            try:
                jobs = self._sitemaps(source, page_url, filters, discovered_at)
            except PublicSourceError as exc:
                warnings.append(str(exc))
            else:
                if jobs:
                    return GenericDiscoveryOutcome(
                        jobs=jobs,
                        strategy="sitemap",
                        warning="; ".join(dict.fromkeys(warnings)),
                        source_url=jobs[0].source_url,
                    )
        return GenericDiscoveryOutcome(
            jobs=[],
            strategy="manual_review",
            warning="; ".join(dict.fromkeys(warnings)),
            source_url=source.public_feed_url or source.portal_url or source.careers_url,
        )

    def _feed(
        self,
        source: SourceConfig,
        filters: DiscoveryFilters,
        discovered_at: str,
    ) -> list[DiscoveryJob]:
        endpoint = source.public_feed_url
        response = self.http.get(
            endpoint, accept="application/rss+xml, application/atom+xml, application/xml, text/xml"
        )
        try:
            root = ElementTree.fromstring(response.content)
        except ElementTree.ParseError as exc:
            raise PublicSourceError("The configured public feed is not valid XML.") from exc
        jobs: list[DiscoveryJob] = []
        for entry in root.iter():
            if _local_name(entry.tag) not in {"item", "entry"}:
                continue
            fields: dict[str, str] = {}
            for child in list(entry):
                name = _local_name(child.tag)
                if name == "link":
                    fields[name] = clean_text(child.attrib.get("href") or child.text)
                elif name in {
                    "title",
                    "description",
                    "summary",
                    "pubdate",
                    "published",
                    "updated",
                    "guid",
                    "location",
                }:
                    fields[name] = clean_text("".join(child.itertext()))
            official_url = canonical_public_url(fields.get("link"))
            title = fields.get("title", "")
            if not official_url or not title:
                continue
            posted_at = _date_text(fields.get("pubdate") or fields.get("published"))
            description = html_to_text(fields.get("description") or fields.get("summary"))
            job = DiscoveryJob.create(
                company=source.company,
                title=title,
                location=fields.get("location", ""),
                provider=source.provider or "generic",
                source_identifier=source.identifier,
                source_type="official_public_feed",
                external_job_id=_external_id(official_url, fields.get("guid")),
                official_url=official_url,
                apply_url=official_url,
                source_url=endpoint,
                description=description,
                posted_at=posted_at,
                updated_at=_date_text(fields.get("updated")),
                date_provenance=("feed_published" if posted_at else "unknown"),
                discovered_at=discovered_at,
                filters=filters,
                source_confidence="medium-high",
            )
            jobs.append(job)
            if len(jobs) >= MAX_GENERIC_JOBS:
                break
        return jobs

    def _static_page(
        self,
        source: SourceConfig,
        page_url: str,
        filters: DiscoveryFilters,
        discovered_at: str,
    ) -> GenericDiscoveryOutcome:
        response = self.http.get(page_url, accept="text/html, application/xhtml+xml")
        parser = _CareerHtmlParser()
        try:
            parser.feed(response.text)
            parser.close()
        except Exception as exc:
            raise PublicSourceError("The public careers HTML could not be parsed safely.") from exc

        embedded_warnings: list[str] = []
        empty_embedded_outcome: GenericDiscoveryOutcome | None = None
        for detected in detect_embedded_sources(response.text):
            detected_source = replace(
                source,
                provider=detected.provider,
                identifier=detected.identifier,
                region=detected.region,
            )
            adapter = adapter_for(detected.provider, self.http)
            endpoint = adapter.endpoint(detected_source)
            try:
                ats_jobs = adapter.fetch(detected_source, filters)
            except (AccessStoppedError, PublicSourceError, ValueError) as exc:
                embedded_warnings.append(
                    f"Embedded {detected.provider} source was unavailable: {clean_text(exc)}"
                )
                continue
            outcome = GenericDiscoveryOutcome(
                jobs=ats_jobs,
                strategy="embedded_public_ats_api",
                source_url=endpoint,
                detected_provider=detected.provider,
                detected_identifier=detected.identifier,
            )
            if ats_jobs:
                return outcome
            if empty_embedded_outcome is None:
                empty_embedded_outcome = outcome

        if empty_embedded_outcome is not None:
            return replace(
                empty_embedded_outcome,
                warning="; ".join(dict.fromkeys(embedded_warnings)),
            )

        embedded_jobs = self._embedded_lever_jobs(
            parser.structured_json,
            source,
            filters,
            discovered_at=discovered_at,
            source_url=response.url,
        )
        if embedded_jobs:
            return GenericDiscoveryOutcome(
                jobs=embedded_jobs,
                strategy="embedded_structured_json",
                warning="",
                source_url=response.url,
                detected_provider="lever",
                detected_identifier=embedded_jobs[0].source_identifier,
            )

        jobs: list[DiscoveryJob] = []
        seen: set[str] = set()
        for script in parser.json_ld:
            try:
                value = json.loads(script)
            except json.JSONDecodeError:
                continue
            for posting in _walk_json_ld(value):
                official_url = canonical_public_url(posting.get("url") or page_url)
                title = clean_text(posting.get("title"))
                if not official_url or not title or official_url in seen:
                    continue
                seen.add(official_url)
                organization = posting.get("hiringOrganization")
                company = (
                    clean_text(organization.get("name"))
                    if isinstance(organization, dict)
                    else source.company
                )
                posted_at = clean_text(posting.get("datePosted"))
                job = DiscoveryJob.create(
                    company=company or source.company,
                    title=title,
                    location=_json_ld_location(posting.get("jobLocation")),
                    provider=source.provider or "generic",
                    source_identifier=source.identifier,
                    source_type="official_static_jsonld",
                    external_job_id=_external_id(official_url, posting.get("identifier")),
                    official_url=official_url,
                    apply_url=official_url,
                    source_url=response.url,
                    description=html_to_text(posting.get("description")),
                    employment_type=clean_text(posting.get("employmentType")),
                    workplace_type=clean_text(posting.get("jobLocationType")),
                    posted_at=posted_at,
                    updated_at=clean_text(posting.get("validThrough")),
                    date_provenance=("schema_datePosted" if posted_at else "unknown"),
                    discovered_at=discovered_at,
                    filters=filters,
                    source_confidence="high",
                )
                jobs.append(job)
                if len(jobs) >= MAX_GENERIC_JOBS:
                    return GenericDiscoveryOutcome(
                        jobs=jobs,
                        strategy="static_html",
                        warning="; ".join(dict.fromkeys(embedded_warnings)),
                        source_url=response.url,
                    )

        allowed = _allowed_hosts(source)
        for href, label in parser.links:
            absolute = canonical_public_url(urljoin(response.url, href))
            host = _hostname(absolute)
            if (
                not absolute
                or absolute in seen
                or not _host_allowed(host, allowed)
                or not _is_job_like(absolute)
            ):
                continue
            title = label or _url_title(absolute)
            if not title or title.casefold() in {"jobs", "careers", "view jobs", "search jobs"}:
                continue
            seen.add(absolute)
            job = DiscoveryJob.create(
                company=source.company,
                title=title,
                location="",
                provider=source.provider or "generic",
                source_identifier=source.identifier,
                source_type="official_static_html",
                external_job_id=_external_id(absolute),
                official_url=absolute,
                apply_url=absolute,
                source_url=response.url,
                description="",
                posted_at="",
                updated_at="",
                date_provenance="unknown",
                discovered_at=discovered_at,
                filters=filters,
                source_confidence="medium",
                source_status="discovery_only",
            )
            jobs.append(job)
            if len(jobs) >= MAX_GENERIC_JOBS:
                break
        return GenericDiscoveryOutcome(
            jobs=jobs,
            strategy="static_html",
            warning="; ".join(dict.fromkeys(embedded_warnings)),
            source_url=response.url,
        )

    def _embedded_lever_jobs(
        self,
        scripts: list[str],
        source: SourceConfig,
        filters: DiscoveryFilters,
        *,
        discovered_at: str,
        source_url: str,
    ) -> list[DiscoveryJob]:
        jobs: list[DiscoveryJob] = []
        seen: set[str] = set()
        for script in scripts:
            try:
                value = json.loads(script)
            except json.JSONDecodeError:
                continue
            for item in _walk_mappings(value):
                urls = item.get("urls") if isinstance(item.get("urls"), dict) else {}
                official_url = canonical_public_url(item.get("hostedUrl") or urls.get("show"))
                identity = _lever_job_identity(official_url)
                title = clean_text(item.get("text") or item.get("title"))
                if identity is None or not title or official_url in seen:
                    continue
                slug, job_id, region = identity
                normalized = dict(item)
                normalized.setdefault("id", job_id)
                detected_source = replace(
                    source,
                    provider="lever",
                    identifier=slug,
                    region=region,
                )
                job = build_lever_job(
                    normalized,
                    detected_source,
                    filters,
                    discovered_at=discovered_at,
                    source_url=source_url,
                    source_type="official_embedded_ats_json",
                )
                if job is None or not job.title:
                    continue
                seen.add(official_url)
                jobs.append(job)
                if len(jobs) >= MAX_GENERIC_JOBS:
                    return jobs
        return jobs

    def _sitemaps(
        self,
        source: SourceConfig,
        page_url: str,
        filters: DiscoveryFilters,
        discovered_at: str,
    ) -> list[DiscoveryJob]:
        parsed = urlsplit(page_url)
        origin = f"https://{parsed.hostname}"
        candidates = [f"{origin}/sitemap.xml"]
        try:
            robots = self.http.get(f"{origin}/robots.txt", accept="text/plain")
        except PublicSourceError:
            pass
        else:
            for line in robots.text.splitlines():
                if line.casefold().startswith("sitemap:"):
                    candidate = canonical_public_url(line.split(":", 1)[1].strip())
                    if candidate:
                        candidates.insert(0, candidate)
        visited: set[str] = set()
        urls: list[tuple[str, str, str]] = []
        for candidate in candidates[: MAX_SITEMAP_CHILDREN + 1]:
            self._collect_sitemap(candidate, visited, urls, source_sitemap=candidate)
            if len(urls) >= MAX_SITEMAP_URLS:
                break

        allowed = _allowed_hosts(source)
        jobs: list[DiscoveryJob] = []
        for url, lastmod, source_sitemap in urls:
            if not _is_job_like(url) or not _host_allowed(_hostname(url), allowed):
                continue
            title = _url_title(url)
            if not title:
                continue
            job = DiscoveryJob.create(
                company=source.company,
                title=title,
                location="",
                provider=source.provider or "generic",
                source_identifier=source.identifier,
                source_type="official_sitemap",
                external_job_id=_external_id(url),
                official_url=url,
                apply_url=url,
                source_url=source_sitemap,
                description="",
                posted_at="",
                updated_at=lastmod,
                date_provenance="sitemap_lastmod_not_publication" if lastmod else "unknown",
                discovered_at=discovered_at,
                filters=filters,
                source_confidence="low-medium",
                source_status="discovery_only",
            )
            jobs.append(job)
            if len(jobs) >= MAX_GENERIC_JOBS:
                break
        return jobs

    def _collect_sitemap(
        self,
        url: str,
        visited: set[str],
        output: list[tuple[str, str, str]],
        *,
        source_sitemap: str,
    ) -> None:
        if url in visited or len(visited) > MAX_SITEMAP_CHILDREN:
            return
        visited.add(url)
        response = self.http.get(url, accept="application/xml, text/xml")
        try:
            root = ElementTree.fromstring(response.content)
        except ElementTree.ParseError as exc:
            raise PublicSourceError("An official sitemap returned invalid XML.") from exc
        root_name = _local_name(root.tag)
        if root_name == "sitemapindex":
            children = []
            for item in list(root):
                location = next(
                    (
                        clean_text(child.text)
                        for child in list(item)
                        if _local_name(child.tag) == "loc"
                    ),
                    "",
                )
                if canonical_public_url(location):
                    children.append(canonical_public_url(location))
            for child in children[:MAX_SITEMAP_CHILDREN]:
                self._collect_sitemap(
                    child,
                    visited,
                    output,
                    source_sitemap=child,
                )
            return
        for item in list(root):
            fields = {_local_name(child.tag): clean_text(child.text) for child in list(item)}
            location = canonical_public_url(fields.get("loc"))
            if location:
                output.append((location, fields.get("lastmod", ""), source_sitemap))
                if len(output) >= MAX_SITEMAP_URLS:
                    break
