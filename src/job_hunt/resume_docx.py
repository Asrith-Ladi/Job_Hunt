"""Truth-preserving tailoring of a private baseline resume DOCX.

The OpenAI planner may write a new professional summary and rank existing evidence,
but it never receives or rewrites contact details. The DOCX editor preserves the
original package and formatting, changes one summary paragraph, reorders existing
skill and experience-bullet paragraphs, and may add one deterministic Skills line
containing only user-confirmed exact JD keywords.
"""

from __future__ import annotations

import copy
import hashlib
import io
import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree


WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"
W = f"{{{WORD_NAMESPACE}}}"
MAX_BASE_RESUME_BYTES = 8 * 1024 * 1024

_SECTION_NAMES = {
    "summary": "professional summary",
    "skills": "technical skills",
    "experience": "work experience",
    "projects": "personal projects",
    "education": "education",
}
_DATE_HEADING = re.compile(r"\b(?:19|20)\d{2}\b")
_DIRECT_CONTACT = (
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)"),
    re.compile(r"\b(?:linkedin|github)\.com/", re.IGNORECASE),
)


class ResumeTemplateError(ValueError):
    """Raised when a file is not a supported or safe resume template."""


@dataclass
class _ParagraphRecord:
    index: int
    text: str
    element: ElementTree.Element
    parent: ElementTree.Element
    item_id: str = ""


@dataclass
class _ResumeStructure:
    root: ElementTree.Element
    summary: _ParagraphRecord
    skills: list[_ParagraphRecord]
    experience_sections: list[dict[str, Any]]


def _normalized(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _stable_id(prefix: str, text: str, index: int) -> str:
    value = f"{index}\0{text}".encode("utf-8")
    return f"{prefix}_{hashlib.sha256(value).hexdigest()[:12]}"


def _paragraph_text(paragraph: ElementTree.Element) -> str:
    values: list[str] = []
    for node in paragraph.iter():
        if node.tag == W + "t":
            values.append(node.text or "")
        elif node.tag == W + "tab":
            values.append("\t")
        elif node.tag in {W + "br", W + "cr"}:
            values.append("\n")
    return "".join(values).strip()


def _parse_document(document_xml: bytes) -> ElementTree.Element:
    for _event, namespace in ElementTree.iterparse(
        io.BytesIO(document_xml), events=("start-ns",)
    ):
        prefix, uri = namespace
        try:
            ElementTree.register_namespace(prefix or "", uri)
        except ValueError:
            # ElementTree reserves automatically generated namespace prefixes.
            pass
    return ElementTree.fromstring(document_xml)


def _read_document(path: Path) -> tuple[ElementTree.Element, bytes]:
    validate_resume_docx(path)
    with zipfile.ZipFile(path) as archive:
        document_xml = archive.read("word/document.xml")
    return _parse_document(document_xml), document_xml


def validate_resume_docx(path: Path) -> Path:
    """Validate the size and minimum OOXML parts of a baseline resume."""

    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError("The baseline resume DOCX is unavailable.")
    if path.suffix.casefold() != ".docx":
        raise ResumeTemplateError("The baseline resume must be a .docx file.")
    size = path.stat().st_size
    if size < 100 or size > MAX_BASE_RESUME_BYTES:
        raise ResumeTemplateError("The baseline resume DOCX has an unsupported file size.")
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if archive.testzip() is not None:
                raise ResumeTemplateError("The baseline resume DOCX is damaged.")
            required = {"[Content_Types].xml", "word/document.xml"}
            if not required.issubset(names):
                raise ResumeTemplateError("The file is not a valid Word DOCX package.")
            ElementTree.fromstring(archive.read("word/document.xml"))
    except (zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise ResumeTemplateError("The file is not a valid Word DOCX package.") from exc
    return path


def validate_resume_upload(content: bytes) -> None:
    """Validate an uploaded DOCX before it is written to private storage."""

    if not 100 <= len(content) <= MAX_BASE_RESUME_BYTES:
        raise ResumeTemplateError("The uploaded resume must be a DOCX smaller than 8 MB.")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
            if archive.testzip() is not None:
                raise ResumeTemplateError("The uploaded resume DOCX is damaged.")
            if not {"[Content_Types].xml", "word/document.xml"}.issubset(names):
                raise ResumeTemplateError("The uploaded file is not a Word DOCX.")
            ElementTree.fromstring(archive.read("word/document.xml"))
    except (zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise ResumeTemplateError("The uploaded file is not a Word DOCX.") from exc


def resume_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _records(root: ElementTree.Element) -> list[_ParagraphRecord]:
    parent_map = {child: parent for parent in root.iter() for child in parent}
    result: list[_ParagraphRecord] = []
    for paragraph in root.iter(W + "p"):
        text = _paragraph_text(paragraph)
        if not text:
            continue
        parent = parent_map.get(paragraph)
        if parent is None:
            continue
        result.append(
            _ParagraphRecord(
                index=len(result),
                text=text,
                element=paragraph,
                parent=parent,
            )
        )
    return result


def _section_indices(records: list[_ParagraphRecord]) -> dict[str, int]:
    locations: dict[str, int] = {}
    wanted = {value: key for key, value in _SECTION_NAMES.items()}
    for offset, record in enumerate(records):
        key = wanted.get(_normalized(record.text))
        if key and key not in locations:
            locations[key] = offset
    required = {"summary", "skills", "experience", "projects"}
    if not required.issubset(locations):
        missing = ", ".join(sorted(required.difference(locations)))
        raise ResumeTemplateError(
            f"The baseline resume is missing required section heading(s): {missing}."
        )
    if not (
        locations["summary"] < locations["skills"] < locations["experience"]
        < locations["projects"]
    ):
        raise ResumeTemplateError("The baseline resume sections are in an unsupported order.")
    return locations


def _build_structure(root: ElementTree.Element) -> _ResumeStructure:
    records = _records(root)
    sections = _section_indices(records)

    summary_candidates = records[sections["summary"] + 1 : sections["skills"]]
    if not summary_candidates:
        raise ResumeTemplateError("The Professional Summary section is empty.")
    summary = summary_candidates[0]

    skills = records[sections["skills"] + 1 : sections["experience"]]
    if not skills:
        raise ResumeTemplateError("The Technical Skills section is empty.")
    for record in skills:
        record.item_id = _stable_id("skill", record.text, record.index)

    experience_records = records[sections["experience"] + 1 : sections["projects"]]
    experience_sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for record in experience_records:
        if _DATE_HEADING.search(record.text):
            current = {
                "section_id": _stable_id("role", record.text, record.index),
                "role": record.text,
                "company": "",
                "bullets": [],
            }
            experience_sections.append(current)
            continue
        if current is None:
            continue
        if not current["company"]:
            current["company"] = record.text
            continue
        record.item_id = _stable_id("bullet", record.text, record.index)
        current["bullets"].append(record)

    experience_sections = [item for item in experience_sections if item["bullets"]]
    if not experience_sections:
        raise ResumeTemplateError("No work-experience bullets were found in the baseline resume.")
    return _ResumeStructure(
        root=root,
        summary=summary,
        skills=skills,
        experience_sections=experience_sections,
    )


def extract_resume_evidence(path: Path) -> dict[str, Any]:
    """Return contact-free professional evidence suitable for a manual model call."""

    root, _document_xml = _read_document(path)
    structure = _build_structure(root)
    professional_text = [structure.summary.text]
    professional_text.extend(record.text for record in structure.skills)
    public_sections = []
    for section in structure.experience_sections:
        bullets = [
            {"id": record.item_id, "text": record.text}
            for record in section["bullets"]
        ]
        professional_text.extend([section["role"], section["company"]])
        professional_text.extend(item["text"] for item in bullets)
        public_sections.append(
            {
                "section_id": section["section_id"],
                "role": section["role"],
                "company": section["company"],
                "bullets": bullets,
            }
        )

    serialized = "\n".join(professional_text)
    if any(pattern.search(serialized) for pattern in _DIRECT_CONTACT):
        raise ResumeTemplateError(
            "Direct contact information appeared inside a professional resume section; "
            "review the template before using AI tailoring."
        )
    return {
        "baseline_sha256": resume_sha256(path),
        "current_summary": structure.summary.text,
        "skills": [
            {"id": record.item_id, "text": record.text} for record in structure.skills
        ],
        "experience_sections": public_sections,
    }


def extract_resume_identity(path: Path) -> dict[str, str]:
    """Read the local header for document assembly without sending it to a model."""

    root, _document_xml = _read_document(path)
    records = _records(root)
    sections = _section_indices(records)
    header = records[: sections["summary"]]
    if not header:
        raise ResumeTemplateError("The baseline resume header is empty.")
    name = header[0].text
    contact_line = next(
        (
            record.text
            for record in header[1:]
            if any(pattern.search(record.text) for pattern in _DIRECT_CONTACT)
        ),
        "",
    )
    headline = next(
        (
            record.text
            for record in header[1:]
            if record.text != contact_line
            and not any(pattern.search(record.text) for pattern in _DIRECT_CONTACT)
        ),
        "",
    )
    return {"name": name, "headline": headline, "contact_line": contact_line}


def _replace_paragraph_text(paragraph: ElementTree.Element, value: str) -> None:
    text_nodes = list(paragraph.iter(W + "t"))
    if not text_nodes:
        run = ElementTree.SubElement(paragraph, W + "r")
        text = ElementTree.SubElement(run, W + "t")
        text_nodes = [text]
    text_nodes[0].text = value
    if value[:1].isspace() or value[-1:].isspace():
        text_nodes[0].set(f"{{{XML_NAMESPACE}}}space", "preserve")
    else:
        text_nodes[0].attrib.pop(f"{{{XML_NAMESPACE}}}space", None)
    for text in text_nodes[1:]:
        text.text = ""


def _normalized_order(requested: Iterable[object], allowed: list[str]) -> list[str]:
    allowed_set = set(allowed)
    ordered: list[str] = []
    seen: set[str] = set()
    for value in requested:
        item_id = str(value or "").strip()
        if item_id in allowed_set and item_id not in seen:
            ordered.append(item_id)
            seen.add(item_id)
    ordered.extend(item_id for item_id in allowed if item_id not in seen)
    return ordered


def _reorder_contiguous(records: list[_ParagraphRecord], requested: Iterable[object]) -> None:
    if len(records) < 2:
        return
    parent = records[0].parent
    if any(record.parent is not parent for record in records):
        raise ResumeTemplateError("A resume evidence block crosses unsupported document containers.")
    children = list(parent)
    positions = sorted(children.index(record.element) for record in records)
    if positions != list(range(positions[0], positions[0] + len(positions))):
        raise ResumeTemplateError("A resume evidence block is not safely reorderable.")
    by_id = {record.item_id: record.element for record in records}
    allowed = [record.item_id for record in records]
    order = _normalized_order(requested, allowed)
    insertion_index = positions[0]
    for record in records:
        parent.remove(record.element)
    for offset, item_id in enumerate(order):
        parent.insert(insertion_index + offset, by_id[item_id])


def _confirmed_skill_line(values: Iterable[object]) -> str:
    skills: list[str] = []
    normalized: set[str] = set()
    for value in list(values or [])[:20]:
        skill = re.sub(r"\s+", " ", str(value or "").strip())[:120]
        key = _normalized(skill)
        if not skill or key in normalized:
            continue
        if any(pattern.search(skill) for pattern in _DIRECT_CONTACT):
            raise ResumeTemplateError("A confirmed skill contained contact information.")
        if re.search(r"\[[A-Z][A-Z0-9_ -]+\]|\{\{.+?\}\}", skill):
            raise ResumeTemplateError("A confirmed skill contained an unresolved placeholder.")
        normalized.add(key)
        skills.append(skill)
    return f"Additional Skills: {', '.join(skills)}" if skills else ""


def _append_confirmed_skills(
    structure: _ResumeStructure,
    values: Iterable[object],
) -> str:
    line = _confirmed_skill_line(values)
    if not line:
        return ""
    parent = structure.skills[0].parent
    if any(record.parent is not parent for record in structure.skills):
        raise ResumeTemplateError("The Technical Skills block crosses unsupported containers.")
    clone = copy.deepcopy(structure.skills[-1].element)
    _replace_paragraph_text(clone, line)
    children = list(parent)
    insertion_index = max(children.index(record.element) for record in structure.skills) + 1
    parent.insert(insertion_index, clone)
    return line


def _serialize_document(
    root: ElementTree.Element,
    original_document_xml: bytes,
) -> bytes:
    """Serialize edits while preserving Word's compatibility namespace declarations.

    ElementTree omits unused ``xmlns:*`` declarations. Word can still reference those
    prefixes from ``mc:Ignorable`` and will report the DOCX as corrupt if they vanish.
    Copy every namespace declaration from the original root element back onto the
    serialized root, including declarations with no currently materialized element.
    """

    serialized = ElementTree.tostring(root, encoding="unicode")
    root_end = serialized.find(">")
    if root_end < 0:
        raise ResumeTemplateError("The tailored Word document could not be serialized.")
    opening = serialized[:root_end]
    original_text = original_document_xml.decode("utf-8", errors="strict")
    original_start = original_text.find("<w:document")
    original_end = original_text.find(">", original_start)
    if original_start < 0 or original_end < 0:
        raise ResumeTemplateError("The baseline Word document root is invalid.")
    original_opening = original_text[original_start:original_end]
    declarations = re.findall(
        r"\s(xmlns(?::[A-Za-z_][\w.-]*)?)=(\"[^\"]*\"|'[^']*')",
        original_opening,
    )
    missing = [
        f" {name}={quoted}"
        for name, quoted in declarations
        if not re.search(rf"\s{re.escape(name)}=", opening)
    ]
    if missing:
        serialized = serialized[:root_end] + "".join(missing) + serialized[root_end:]
    declaration = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    return (declaration + serialized).encode("utf-8")


def tailor_resume_docx(base_path: Path, output_path: Path, plan: dict[str, Any]) -> Path:
    """Apply a validated ranking plan to a copy of the baseline DOCX."""

    base_path = validate_resume_docx(base_path)
    root, original_document_xml = _read_document(base_path)
    structure = _build_structure(root)
    summary = re.sub(r"\s+", " ", str(plan.get("summary") or "").strip())
    if not summary:
        raise ResumeTemplateError("A tailored professional summary is required.")
    _replace_paragraph_text(structure.summary.element, summary)
    _reorder_contiguous(structure.skills, plan.get("skill_order") or [])
    _append_confirmed_skills(structure, plan.get("confirmed_skills") or [])

    requested_sections = {
        str(item.get("section_id") or ""): item
        for item in plan.get("experience_sections") or []
        if isinstance(item, dict)
    }
    for section in structure.experience_sections:
        request = requested_sections.get(section["section_id"], {})
        _reorder_contiguous(section["bullets"], request.get("bullet_order") or [])

    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document_xml = _serialize_document(root, original_document_xml)
    with tempfile.NamedTemporaryFile(
        prefix=output_path.stem + ".",
        suffix=".pending.docx",
        dir=output_path.parent,
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with zipfile.ZipFile(base_path, "r") as source, zipfile.ZipFile(
            temporary_path, "w"
        ) as target:
            for info in source.infolist():
                content = (
                    document_xml
                    if info.filename == "word/document.xml"
                    else source.read(info.filename)
                )
                target.writestr(info, content)
        verify_tailored_resume(base_path, temporary_path, plan)
        temporary_path.replace(output_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return output_path


def verify_tailored_resume(
    base_path: Path,
    candidate_path: Path,
    plan: dict[str, Any],
) -> None:
    """Structurally verify that tailoring preserved every original evidence item."""

    validate_resume_docx(candidate_path)
    base_evidence = extract_resume_evidence(base_path)
    candidate_evidence = extract_resume_evidence(candidate_path)
    expected_summary = re.sub(r"\s+", " ", str(plan.get("summary") or "").strip())
    if candidate_evidence["current_summary"] != expected_summary:
        raise ResumeTemplateError("The tailored summary was not written correctly.")

    base_skills = sorted(item["text"] for item in base_evidence["skills"])
    candidate_skills = sorted(item["text"] for item in candidate_evidence["skills"])
    expected_skill_line = _confirmed_skill_line(plan.get("confirmed_skills") or [])
    expected_skills = sorted(base_skills + ([expected_skill_line] if expected_skill_line else []))
    if candidate_skills != expected_skills:
        raise ResumeTemplateError("Tailoring changed or added unconfirmed resume skills.")

    def experience_texts(value: dict[str, Any]) -> list[str]:
        return sorted(
            item["text"]
            for section in value["experience_sections"]
            for item in section["bullets"]
        )

    if experience_texts(base_evidence) != experience_texts(candidate_evidence):
        raise ResumeTemplateError("Tailoring changed or removed verified work evidence.")
    if re.search(r"\[[A-Z][A-Z0-9_ -]+\]|\{\{.+?\}\}", expected_summary):
        raise ResumeTemplateError("The tailored resume contains an unresolved placeholder.")
