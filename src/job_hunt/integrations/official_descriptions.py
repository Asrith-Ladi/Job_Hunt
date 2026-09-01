"""Deterministically capture readable descriptions from public official job pages."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

from job_hunt.discovery.http_client import PublicSourceError, SafeHttpClient


MAX_DESCRIPTION_CHARACTERS = 100_000
PROTECTED_JOB_HOSTS = {
    "linkedin.com",
    "naukri.com",
    "indeed.com",
    "glassdoor.com",
}
DESCRIPTION_KEYS = (
    "description",
    "jobdescription",
    "job_description",
    "responsibilities",
    "requirements",
    "qualifications",
    "preferredqualifications",
    "preferred_qualifications",
    "skills",
    "abouttherole",
    "about_the_role",
)
SECTION_LABELS = {
    "jobdescription": "Job description",
    "job_description": "Job description",
    "responsibilities": "Responsibilities",
    "requirements": "Requirements",
    "qualifications": "Qualifications",
    "preferredqualifications": "Preferred qualifications",
    "preferred_qualifications": "Preferred qualifications",
    "skills": "Skills",
    "abouttherole": "About the role",
    "about_the_role": "About the role",
}
_MOJIBAKE_REPLACEMENTS = {
    "â€™": "’",
    "â€˜": "‘",
    "â€œ": "“",
    "â€": "”",
    "â€“": "–",
    "â€”": "—",
    "â€¢": "•",
    "Â": "",
}


@dataclass(frozen=True)
class OfficialDescriptionResolution:
    """One public description capture with an explicit completeness classification."""

    description: str = ""
    source: str = ""
    completeness: str = "summary_only"
    warning: str = ""


def _repair_text(value: str) -> str:
    text = html.unescape(str(value or ""))
    for broken, repaired in _MOJIBAKE_REPLACEMENTS.items():
        text = text.replace(broken, repaired)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:MAX_DESCRIPTION_CHARACTERS]


class _ReadableHtmlParser(HTMLParser):
    """Extract scripts and conservative main/article/body prose without navigation."""

    BLOCK_TAGS = {
        "article",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "main",
        "p",
        "section",
        "tr",
    }
    IGNORED_TAGS = {"button", "footer", "form", "header", "nav", "noscript", "style"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.json_scripts: list[str] = []
        self._script_parts: list[str] | None = None
        self._ignored_depth = 0
        self._content_depth = 0
        self._body_depth = 0
        self._visible_parts: list[str] = []
        self._list_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        name = tag.casefold()
        attributes = {str(key).casefold(): str(value or "") for key, value in attrs}
        if name == "script":
            script_type = attributes.get("type", "").casefold()
            if "ld+json" in script_type or script_type == "application/json":
                self._script_parts = []
            return
        if name in self.IGNORED_TAGS:
            self._ignored_depth += 1
        if name == "body":
            self._body_depth += 1
        if name in {"main", "article"}:
            self._content_depth += 1
        if name in {"ul", "ol"}:
            self._list_depth += 1
        if self._is_visible() and name in self.BLOCK_TAGS:
            if name == "li":
                self._visible_parts.append("\n- ")
            else:
                self._visible_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        name = tag.casefold()
        if name == "script" and self._script_parts is not None:
            self.json_scripts.append("".join(self._script_parts))
            self._script_parts = None
            return
        if self._is_visible() and name in self.BLOCK_TAGS:
            self._visible_parts.append("\n")
        if name in {"ul", "ol"} and self._list_depth:
            self._list_depth -= 1
        if name in {"main", "article"} and self._content_depth:
            self._content_depth -= 1
        if name == "body" and self._body_depth:
            self._body_depth -= 1
        if name in self.IGNORED_TAGS and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._script_parts is not None:
            self._script_parts.append(data)
        elif self._is_visible():
            value = " ".join(data.split())
            if value:
                self._visible_parts.append(value)

    def _is_visible(self) -> bool:
        return self._ignored_depth == 0 and (self._content_depth > 0 or self._body_depth > 0)

    @property
    def visible_text(self) -> str:
        return _repair_text(" ".join(self._visible_parts))


def _value_text(value: Any) -> str:
    """Flatten supported structured description values without serializing containers."""

    if value is None:
        return ""
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return ""
        if "<" in raw and ">" in raw:
            parser = _ReadableHtmlParser()
            parser.feed(f"<main>{raw}</main>")
            parser.close()
            return parser.visible_text
        return _repair_text(raw)
    if isinstance(value, (int, float, bool)):
        return _repair_text(str(value))
    if isinstance(value, (list, tuple, set)):
        parts = [_value_text(item) for item in value]
        return _repair_text("\n".join(f"- {part}" for part in parts if part))
    if isinstance(value, Mapping):
        sections: list[str] = []
        normalized = {str(key).casefold(): item for key, item in value.items()}
        for key in DESCRIPTION_KEYS:
            if key not in normalized:
                continue
            content = _value_text(normalized[key])
            if not content:
                continue
            label = SECTION_LABELS.get(key)
            sections.append(f"## {label}\n\n{content}" if label else content)
        if sections:
            return _repair_text("\n\n".join(sections))
        for key in ("text", "content", "value"):
            content = _value_text(normalized.get(key))
            if content:
                return content
    return ""


def clean_description(value: Any) -> str:
    """Return readable description text; unsupported containers safely become empty."""

    return _value_text(value)[:MAX_DESCRIPTION_CHARACTERS]


def _walk(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _is_job_posting(value: Mapping[str, Any]) -> bool:
    item_type = value.get("@type")
    types = item_type if isinstance(item_type, list) else [item_type]
    return any(str(item or "").casefold() == "jobposting" for item in types)


def _identity_score(value: Mapping[str, Any], posting: Mapping[str, Any]) -> int:
    expected_title = " ".join(str(posting.get("title") or "").casefold().split())
    expected_id = str(posting.get("requisition_id") or "").casefold().strip()
    supplied_title = " ".join(
        str(value.get("title") or value.get("name") or "").casefold().split()
    )
    supplied_id = str(
        value.get("identifier")
        or value.get("id")
        or value.get("jobId")
        or value.get("requisitionId")
        or ""
    ).casefold()
    score = 0
    if expected_id and expected_id in supplied_id:
        score += 3
    if expected_title and supplied_title:
        if expected_title == supplied_title:
            score += 3
        elif expected_title in supplied_title or supplied_title in expected_title:
            score += 2
        elif len(set(expected_title.split()) & set(supplied_title.split())) >= 2:
            score += 1
    return score


def _description_from_scripts(
    scripts: Iterable[str], posting: Mapping[str, Any]
) -> tuple[str, str]:
    candidates: list[tuple[int, str, str]] = []
    for raw in scripts:
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        for mapping in _walk(payload):
            description = clean_description(mapping)
            if not description:
                continue
            if _is_job_posting(mapping):
                candidates.append((10 + _identity_score(mapping, posting), description, "json_ld"))
                continue
            score = _identity_score(mapping, posting)
            if score >= 2:
                candidates.append((score, description, "embedded_json"))
    if not candidates:
        return "", ""
    candidates.sort(key=lambda item: (item[0], len(item[1])), reverse=True)
    _, description, source = candidates[0]
    return description, source


def _looks_like_description(value: str) -> bool:
    normalized = value.casefold()
    words = re.findall(r"[a-z0-9+#.]+", normalized)
    signals = sum(
        marker in normalized
        for marker in (
            "responsibilit",
            "requirement",
            "qualification",
            "about the role",
            "what you will",
            "what you'll",
            "experience",
        )
    )
    return len(words) >= 80 and signals >= 1


def _hostname(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").casefold().rstrip(".")
    except ValueError:
        return ""


def _is_protected(url: str) -> bool:
    host = _hostname(url)
    return any(host == item or host.endswith(f".{item}") for item in PROTECTED_JOB_HOSTS)


def resolve_official_description(
    posting: Mapping[str, Any],
    *,
    http_client: SafeHttpClient | None = None,
) -> OfficialDescriptionResolution:
    """Fetch one verified official URL without login, bypasses, or LLM reconstruction."""

    official_url = str(posting.get("official_url") or "").strip()
    if not official_url:
        return OfficialDescriptionResolution(warning="No official job URL was available.")
    if _is_protected(official_url):
        return OfficialDescriptionResolution(
            warning="The alert URL is not an official employer page; automatic capture was skipped."
        )

    owns_client = http_client is None
    client = http_client or SafeHttpClient(timeout_seconds=15.0)
    try:
        response = client.get(
            official_url,
            accept="text/html, application/xhtml+xml, application/json;q=0.9",
        )
    except PublicSourceError as exc:
        return OfficialDescriptionResolution(
            warning=f"The official page description could not be captured: {exc}"
        )
    finally:
        if owns_client:
            client.close()

    content_type = response.headers.get("content-type", "").casefold()
    if "json" in content_type:
        try:
            payload = response.json()
        except PublicSourceError as exc:
            return OfficialDescriptionResolution(warning=str(exc))
        candidates = [
            (_identity_score(mapping, posting), clean_description(mapping))
            for mapping in _walk(payload)
        ]
        candidates = [item for item in candidates if item[1]]
        if candidates:
            candidates.sort(key=lambda item: (item[0], len(item[1])), reverse=True)
            return OfficialDescriptionResolution(
                description=candidates[0][1],
                source="captured_official_json",
                completeness="full",
            )

    parser = _ReadableHtmlParser()
    parser.feed(response.text)
    parser.close()
    scripted_description, scripted_source = _description_from_scripts(
        parser.json_scripts, posting
    )
    if scripted_description:
        return OfficialDescriptionResolution(
            description=scripted_description,
            source=f"captured_official_{scripted_source}",
            completeness="full",
        )
    if _looks_like_description(parser.visible_text):
        return OfficialDescriptionResolution(
            description=parser.visible_text,
            source="captured_official_html",
            completeness="partial",
            warning=(
                "The official page exposed readable text but no structured JobPosting; "
                "review the saved description for page chrome or omitted sections."
            ),
        )
    return OfficialDescriptionResolution(
        warning="The official page did not expose a reliable public job description."
    )
