"""Extract a small, externally safe evidence set from private reference documents."""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from pathlib import Path
from typing import Any, Iterable, Mapping
from xml.etree import ElementTree


WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{WORD_NAMESPACE}}}"
MAX_REFERENCE_POINTS = 18

_DIRECT_CONTACT = (
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)"),
    re.compile(r"\b(?:linkedin|github)\.com/", re.IGNORECASE),
)
_UNSAFE_NOTES = (
    "quantify:",
    "do not claim",
    "don't claim",
    "don't invent",
    "estimated",
    "inferred",
    "in progress",
    "in-progress",
    "roadmap",
    "not yet",
    "currently integrating",
    "planned / integrating",
    "how to use",
)
_INTERNAL_MARKERS = (
    "rdar://",
    "apple's",
    "apple internal",
    "aos monitoring data platform",
    "internal pypi",
    "_support_group",
)
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "their",
    "this",
    "to",
    "using",
    "with",
}


def _normalized(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _paragraph_text(paragraph: ElementTree.Element) -> str:
    values: list[str] = []
    for node in paragraph.iter():
        if node.tag == W + "t":
            values.append(node.text or "")
        elif node.tag == W + "tab":
            values.append("\t")
        elif node.tag in {W + "br", W + "cr"}:
            values.append("\n")
    return re.sub(r"\s+", " ", "".join(values)).strip()


def _docx_paragraphs(path: Path) -> list[str]:
    try:
        with zipfile.ZipFile(path) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise ValueError("A resume reference DOCX could not be read.") from exc
    return [text for paragraph in root.iter(W + "p") if (text := _paragraph_text(paragraph))]


def _clean_markdown(value: str) -> str:
    text = re.sub(r"^\s*(?:[-*]|\d+[.)])\s+", "", value.strip())
    text = re.sub(r"[`*_]+", "", text)
    text = re.sub(r"\s*→\s*quantify:.*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    if "Result / signal:" in text:
        text = text.split("Result / signal:", 1)[0].strip()
    text = text.replace("What I did:", "").replace("How it helps:", " ")
    return re.sub(r"\s+", " ", text).strip(" -")


def _markdown_blocks(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8-sig", errors="strict")
    blocks: list[str] = []
    current: list[str] = []
    allow_section = True
    quick_pick_generic = False

    def flush() -> None:
        nonlocal current
        if current and allow_section and quick_pick_generic is not False:
            cleaned = _clean_markdown(" ".join(current))
            if cleaned:
                blocks.append(cleaned)
        current = []

    is_resume_points = path.name.casefold() == "resume_points.md"
    if not is_resume_points:
        quick_pick_generic = True
    for raw_line in text.splitlines():
        line = raw_line.strip()
        lowered = line.casefold()
        if line.startswith("## "):
            flush()
            if is_resume_points:
                if "section a" in lowered:
                    allow_section = False
                    quick_pick_generic = False
                elif "section b" in lowered:
                    allow_section = True
                    quick_pick_generic = True
                elif "quick-pick" in lowered:
                    allow_section = True
                    quick_pick_generic = False
            continue
        if is_resume_points and lowered == "**internal:**":
            flush()
            quick_pick_generic = False
            continue
        if is_resume_points and lowered == "**genericized:**":
            flush()
            quick_pick_generic = True
            continue
        if re.match(r"^(?:[-*]|\d+[.)])\s+", line):
            flush()
            current = [line]
        elif current and line and not line.startswith(("#", ">", "---")):
            current.append(line)
        elif not line:
            flush()
    flush()
    return blocks


def _docx_candidates(path: Path) -> list[str]:
    paragraphs = _docx_paragraphs(path)
    result: list[str] = []
    shipped_only = False
    saw_shipped_marker = False
    for paragraph in paragraphs:
        lowered = _normalized(paragraph)
        if "shipped / real" in lowered or "safe to claim" in lowered:
            shipped_only = True
            saw_shipped_marker = True
            continue
        if saw_shipped_marker and (
            "in-progress" in lowered or "roadmap" in lowered or "if the field is short" in lowered
        ):
            shipped_only = False
            if "if the field is short" not in lowered:
                continue
        if saw_shipped_marker and not shipped_only and "if the field is short" not in lowered:
            if not re.match(r"^(?:built|implemented|secured|delivered|engineered|added|shipped)", lowered):
                continue
        if len(paragraph.split()) >= 8:
            result.append(paragraph)
    return result


def _safe_candidate(value: str) -> str:
    text = re.sub(r"\s+", " ", value).strip(" -")
    lowered = text.casefold()
    if not 35 <= len(text) <= 650:
        return ""
    if any(pattern.search(text) for pattern in _DIRECT_CONTACT):
        return ""
    if any(marker in lowered for marker in _UNSAFE_NOTES):
        return ""
    if any(marker in lowered for marker in _INTERNAL_MARKERS):
        return ""
    return text


def _kind_for_name(name: str) -> str:
    lowered = name.casefold()
    if "personal" in lowered or "project" in lowered:
        return "project_reference"
    return "work_reference"


def _tokens(value: object) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9+#.]{2,}", _normalized(value))
        if token not in _STOP_WORDS
    }


def _job_tokens(posting: Mapping[str, Any]) -> set[str]:
    values: list[object] = [
        posting.get("title"),
        posting.get("description_summary"),
        posting.get("experience_text"),
    ]
    values.extend(posting.get("required_skills") or [])
    values.extend(posting.get("preferred_skills") or [])
    return _tokens("\n".join(str(value or "") for value in values))


def extract_reference_evidence(
    records: Iterable[Mapping[str, Any]],
    posting: Mapping[str, Any],
    *,
    limit: int = MAX_REFERENCE_POINTS,
) -> list[dict[str, Any]]:
    """Return contact-free, externally safe reference points ranked for one job."""

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    wanted = _job_tokens(posting)
    for record in records:
        path = Path(str(record.get("local_path") or ""))
        original_name = Path(str(record.get("original_name") or path.name)).name
        if not path.is_file():
            continue
        suffix = path.suffix.casefold()
        if suffix == ".docx":
            values = _docx_candidates(path)
        elif suffix in {".md", ".txt"}:
            values = _markdown_blocks(path)
        else:
            continue
        for value in values:
            text = _safe_candidate(value)
            normalized = _normalized(text)
            if not text or normalized in seen:
                continue
            seen.add(normalized)
            overlap = wanted.intersection(_tokens(text))
            score = len(overlap) * 10 + min(len(text.split()), 60) / 60
            digest = hashlib.sha256(
                f"{record.get('sha256')}\0{text}".encode("utf-8")
            ).hexdigest()[:14]
            candidates.append(
                {
                    "id": f"reference_{digest}",
                    "text": text,
                    "source_kind": _kind_for_name(original_name),
                    "relevance_score": round(score, 3),
                }
            )
    candidates.sort(
        key=lambda item: (-float(item["relevance_score"]), str(item["id"]))
    )
    return [
        {
            "id": item["id"],
            "text": item["text"],
            "source_kind": item["source_kind"],
        }
        for item in candidates[: max(0, min(int(limit), MAX_REFERENCE_POINTS))]
    ]
