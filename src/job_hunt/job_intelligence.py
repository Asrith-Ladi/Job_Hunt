"""Manual official-job analysis and truth-preserving tailored-resume generation."""

from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from job_hunt.document_outputs import build_cover_letter_docx, convert_docx_to_pdf
from job_hunt.enrichment import personal_resume_profile, score_official_posting
from job_hunt.gmail_service import AppPaths, GoogleConnectionService, TIME_ZONE
from job_hunt.integrations.ashby_postings import (
    ExactPostingResolution,
    resolve_exact_ashby_posting,
)
from job_hunt.integrations.openai_research import (
    OfficialJobResearcher,
    OpenAIResearchError,
)
from job_hunt.openai_config import OpenAISettings, load_openai_settings
from job_hunt.private_io import read_json, write_json_atomic
from job_hunt.resume_docx import (
    extract_resume_evidence,
    extract_resume_identity,
    resume_sha256,
    tailor_resume_docx,
)
from job_hunt.resume_library import (
    DOCX_MIME_TYPE,
    PDF_MIME_TYPE,
    DriveResumeLibrary,
)
from job_hunt.resume_references import extract_reference_evidence


MAX_SUMMARY_WORDS = 100
MAX_CONFIRMED_SKILL_EVIDENCE = 20
OUTPUT_RESUME_DOCX = "resume_docx"
OUTPUT_RESUME_PDF = "resume_pdf"
OUTPUT_COVER_LETTER = "cover_letter"
SUPPORTED_OUTPUTS = frozenset(
    {OUTPUT_RESUME_DOCX, OUTPUT_RESUME_PDF, OUTPUT_COVER_LETTER}
)

RESUME_PLAN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "skill_order": {"type": "array", "items": {"type": "string"}},
        "experience_sections": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "section_id": {"type": "string"},
                    "bullet_order": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["section_id", "bullet_order"],
            },
        },
        "reference_evidence_ids": {"type": "array", "items": {"type": "string"}},
        "cover_letter_paragraphs": {"type": "array", "items": {"type": "string"}},
        "keyword_alignment": {"type": "array", "items": {"type": "string"}},
        "change_notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "summary",
        "skill_order",
        "experience_sections",
        "reference_evidence_ids",
        "cover_letter_paragraphs",
        "keyword_alignment",
        "change_notes",
    ],
}

RESUME_PLANNER_INSTRUCTIONS = """You tailor one resume for one verified official job.

Use only facts explicitly present in resume_evidence. Never invent or upgrade skills,
years, employers, titles, dates, metrics, education, certifications, ownership, or impact.
Do not claim a job requirement that is absent from resume_evidence. Write a concise
45-75 word professional summary. Rank every supplied skill ID and every bullet ID by
relevance; IDs must be copied exactly. You may reorder evidence but may not create,
rewrite, or omit evidence bullets. change_notes must describe only truthful positioning
changes, and keyword_alignment may contain only phrases already supported by the evidence.
Reference points are additional verified evidence, not permission to invent new facts;
select only their supplied IDs. user_confirmed_skill_evidence contains professional facts
the user explicitly confirmed; you may use those facts and exact skill labels naturally,
but you may not expand beyond the supplied note. If cover_letter_requested is true, write 3-4 concise,
human paragraphs (roughly 180-300 words total) for the named role and company. Do not add
contact details, a candidate name, placeholders, or unsupported claims. If it is false,
return an empty cover_letter_paragraphs array.
"""


class JobIntelligenceError(RuntimeError):
    """Sanitized failure suitable for the React API boundary."""


def _require_openai_client():
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - dependency boundary
        raise RuntimeError("The OpenAI SDK is not installed. Run `pip install -e .`.") from exc
    return OpenAI


def _normalize_text(value: object) -> str:
    value = str(value or "").casefold().replace("&", " and ")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+#.]+", " ", value)).strip()


def _safe_text(value: object, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _safe_filename(value: object, fallback: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip()).strip("._-")
    return (text[:70] or fallback).strip("._-")


_USER_EVIDENCE_DIRECT_CONTACT = (
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"\b(?:https?://|www\.)", re.IGNORECASE),
    re.compile(r"\b(?:linkedin|github)\.com/", re.IGNORECASE),
)
_USER_EVIDENCE_PHONE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")


def _contains_contact(value: str) -> bool:
    if any(pattern.search(value) for pattern in _USER_EVIDENCE_DIRECT_CONTACT):
        return True
    return any(
        sum(character.isdigit() for character in match.group(0)) >= 9
        for match in _USER_EVIDENCE_PHONE.finditer(value)
    )


def _confirmed_skill_evidence(
    values: Iterable[Mapping[str, Any]],
    posting: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Accept only explicitly confirmed evidence for exact missing JD skill labels."""

    eligibility = dict(posting.get("eligibility") or {})
    missing = [str(value).strip() for value in eligibility.get("missing_skills") or []]
    if not missing:
        matched = {
            _normalize_text(value)
            for value in eligibility.get("matched_skills") or []
            if _normalize_text(value)
        }
        missing = [
            str(value).strip()
            for value in posting.get("required_skills") or []
            if str(value).strip() and _normalize_text(value) not in matched
        ]
    allowed = {_normalize_text(value): value for value in missing if _normalize_text(value)}
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in list(values or [])[:MAX_CONFIRMED_SKILL_EVIDENCE]:
        if not isinstance(raw, Mapping) or not bool(raw.get("confirmed")):
            continue
        supplied_skill = _safe_text(raw.get("skill"), 120)
        key = _normalize_text(supplied_skill)
        if not key or key not in allowed:
            raise ValueError(
                "Confirmed evidence may be added only for a missing skill from the selected JD."
            )
        note = re.sub(r"\s+", " ", _safe_text(raw.get("note"), 1200)).strip()
        if len(note) < 20:
            raise ValueError(
                f"Add a short factual evidence note before confirming {allowed[key]}."
            )
        if _contains_contact(note):
            raise ValueError(
                "Remove contact details and profile/web links from confirmed evidence notes."
            )
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "id": "confirmed_"
                + hashlib.sha256(f"{key}\0{note}".encode("utf-8")).hexdigest()[:12],
                "skill": allowed[key],
                "note": note,
            }
        )
    return result


def _public_job_facts(job: Mapping[str, Any]) -> dict[str, Any]:
    """Allowlist the only job facts accepted by the manual model boundary."""

    company = _safe_text(job.get("company"), 300)
    title = _safe_text(job.get("title"), 300)
    if not company or not title:
        raise ValueError("Company and job title are required for official-job research.")
    supplied_id = _safe_text(job.get("job_record_id"), 200)
    if not supplied_id:
        digest = hashlib.sha256(f"{company}\0{title}".encode("utf-8")).hexdigest()[:18]
        supplied_id = f"manual_{digest}"
    return {
        "job_record_id": supplied_id,
        "company": company,
        "title": title,
        "location": _safe_text(job.get("location"), 300),
        "experience_text": _safe_text(job.get("experience_text"), 500),
        "official_url": _safe_text(job.get("official_url"), 4096),
    }


def _analysis_id(job: Mapping[str, Any], candidates: list[dict[str, Any]], verified_at: str) -> str:
    value = {
        "job": dict(job),
        "official_job_ids": [item.get("official_job_id") for item in candidates],
        "verified_at": verified_at,
    }
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return "analysis_" + hashlib.sha256(encoded).hexdigest()[:22]


def _safe_identifier(value: object, prefix: str) -> str:
    text = str(value or "").strip()
    if not re.fullmatch(rf"{re.escape(prefix)}[a-zA-Z0-9_-]{{8,80}}", text):
        raise ValueError("The requested generated artifact identifier is invalid.")
    return text


class ResumePlanner:
    """Create a small structured ranking plan; DOCX edits remain deterministic."""

    def __init__(self, api_key: str, model: str, client=None):
        if client is None:
            OpenAI = _require_openai_client()
            client = OpenAI(api_key=str(api_key).strip())
        self.client = client
        self.model = str(model).strip()

    def plan(
        self,
        posting: Mapping[str, Any],
        evidence: Mapping[str, Any],
        eligibility: Mapping[str, Any],
        *,
        cover_letter_requested: bool = False,
    ) -> dict[str, Any]:
        prompt = json.dumps(
            {
                "official_job": {
                    key: posting.get(key)
                    for key in (
                        "company",
                        "title",
                        "location",
                        "experience_text",
                        "description_summary",
                        "required_skills",
                        "preferred_skills",
                    )
                },
                "eligibility": {
                    key: eligibility.get(key)
                    for key in ("score", "band", "matched_skills", "gaps")
                },
                "resume_evidence": evidence,
                "cover_letter_requested": bool(cover_letter_requested),
            },
            ensure_ascii=False,
            indent=2,
        )
        try:
            response = self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": RESUME_PLANNER_INSTRUCTIONS},
                    {"role": "user", "content": prompt},
                ],
                reasoning={"effort": "low"},
                text={
                    "verbosity": "low",
                    "format": {
                        "type": "json_schema",
                        "name": "truthful_resume_plan",
                        "strict": True,
                        "schema": RESUME_PLAN_SCHEMA,
                    },
                },
                store=False,
            )
            output = str(getattr(response, "output_text", "") or "").strip()
            if not output:
                raise ValueError("The model returned no resume plan.")
            value = json.loads(output)
        except Exception as exc:
            raise JobIntelligenceError(
                f"Tailored-resume planning failed ({type(exc).__name__})."
            ) from exc
        return normalize_resume_plan(
            value,
            posting,
            evidence,
            cover_letter_requested=cover_letter_requested,
            eligibility=eligibility,
        )


def _normalize_order(requested: object, allowed: list[str]) -> list[str]:
    values = requested if isinstance(requested, list) else []
    allowed_set = set(allowed)
    result: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if item in allowed_set and item not in result:
            result.append(item)
    result.extend(item for item in allowed if item not in result)
    return result


def _normalize_selection(requested: object, allowed: list[str]) -> list[str]:
    values = requested if isinstance(requested, list) else []
    allowed_set = set(allowed)
    result: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if item in allowed_set and item not in result:
            result.append(item)
    return result


def _evidence_text(evidence: Mapping[str, Any]) -> str:
    return "\n".join(
        [str(evidence.get("current_summary") or "")]
        + [str(item.get("text") or "") for item in evidence.get("skills") or []]
        + [
            str(item.get("text") or "")
            for section in evidence.get("experience_sections") or []
            for item in section.get("bullets") or []
        ]
        + [str(item.get("text") or "") for item in evidence.get("reference_points") or []]
        + [
            f"{item.get('skill') or ''}: {item.get('note') or ''}"
            for item in evidence.get("user_confirmed_skill_evidence") or []
        ]
    )


def _summary_is_supported(
    summary: str,
    posting: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> tuple[bool, str]:
    if not 25 <= len(summary.split()) <= MAX_SUMMARY_WORDS:
        return False, "The generated summary length was outside the safe range."
    evidence_text = _evidence_text(evidence)
    source_numbers = set(re.findall(r"\d+(?:\.\d+)?%?\+?", evidence_text))
    generated_numbers = set(re.findall(r"\d+(?:\.\d+)?%?\+?", summary))
    if not generated_numbers.issubset(source_numbers):
        return False, "The generated summary introduced an unsupported numeric claim."

    if re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", summary, re.IGNORECASE):
        return False, "The generated summary introduced contact information."
    if re.search(r"\b(?:linkedin|github)\.com/", summary, re.IGNORECASE):
        return False, "The generated summary introduced a profile URL."

    normalized_evidence = _normalize_text(evidence_text)
    normalized_summary = _normalize_text(summary)
    target_company = _normalize_text(posting.get("company"))
    if (
        target_company
        and target_company not in normalized_evidence
        and target_company in normalized_summary
    ):
        return False, "The generated summary incorrectly claimed the target employer."
    for skill in [
        *(posting.get("required_skills") or []),
        *(posting.get("preferred_skills") or []),
    ]:
        normalized_skill = _normalize_text(skill)
        if (
            len(normalized_skill) >= 2
            and normalized_skill not in normalized_evidence
            and normalized_skill in normalized_summary
        ):
            return False, f"The generated summary claimed unsupported skill: {skill}."
    return True, ""


def _fallback_cover_letter(
    posting: Mapping[str, Any],
    evidence: Mapping[str, Any],
    eligibility: Mapping[str, Any],
) -> list[str]:
    title = _safe_text(posting.get("title"), 200) or "the advertised role"
    company = _safe_text(posting.get("company"), 200) or "your organization"
    summary = re.sub(r"\s+", " ", str(evidence.get("current_summary") or "").strip())
    bullets = [
        re.sub(r"\s+", " ", str(item.get("text") or "").strip())
        for section in evidence.get("experience_sections") or []
        for item in section.get("bullets") or []
        if str(item.get("text") or "").strip()
    ][:2]
    matches = [
        _safe_text(value, 80)
        for value in eligibility.get("matched_skills") or []
        if _safe_text(value, 80)
    ][:4]
    first = f"I am applying for the {title} position at {company}. {summary}"
    evidence_sentences = " ".join(bullets)
    second = (
        "My relevant documented experience includes the following work. "
        f"{evidence_sentences}"
        if evidence_sentences
        else "My background includes production AI/ML delivery and Python-based systems."
    )
    alignment = ", ".join(matches)
    third = (
        f"The role's focus aligns with my documented experience in {alignment}. "
        if alignment
        else "The role aligns with my documented machine-learning engineering experience. "
    )
    third += (
        "I would welcome the opportunity to discuss how this background could support "
        "your team's goals. Thank you for your consideration."
    )
    return [first, second, third]


def _cover_letter_is_supported(
    paragraphs: list[str],
    posting: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> tuple[bool, str]:
    if not 2 <= len(paragraphs) <= 5:
        return False, "The generated cover letter did not contain a safe paragraph structure."
    text = "\n".join(paragraphs)
    if not 100 <= len(text.split()) <= 400:
        return False, "The generated cover letter length was outside the safe range."
    if re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text, re.IGNORECASE):
        return False, "The generated cover letter introduced contact information."
    if re.search(r"\b(?:linkedin|github)\.com/|https?://", text, re.IGNORECASE):
        return False, "The generated cover letter introduced a URL."
    if re.search(r"\[[A-Z][A-Z0-9_ -]+\]|\{\{.+?\}\}", text):
        return False, "The generated cover letter contained an unresolved placeholder."
    source = _evidence_text(evidence)
    source_numbers = set(re.findall(r"\d+(?:\.\d+)?%?\+?", source))
    generated_numbers = set(re.findall(r"\d+(?:\.\d+)?%?\+?", text))
    if not generated_numbers.issubset(source_numbers):
        return False, "The generated cover letter introduced an unsupported numeric claim."
    normalized_source = _normalize_text(source)
    normalized_text = _normalize_text(text)
    for skill in [
        *(posting.get("required_skills") or []),
        *(posting.get("preferred_skills") or []),
    ]:
        normalized_skill = _normalize_text(skill)
        if (
            len(normalized_skill) >= 2
            and normalized_skill not in normalized_source
            and normalized_skill in normalized_text
        ):
            return False, f"The generated cover letter claimed unsupported skill: {skill}."
    return True, ""


def normalize_resume_plan(
    raw: Mapping[str, Any],
    posting: Mapping[str, Any],
    evidence: Mapping[str, Any],
    *,
    cover_letter_requested: bool = False,
    eligibility: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate model output and fall back to source evidence for unsafe prose."""

    original_summary = str(evidence.get("current_summary") or "").strip()
    summary = re.sub(r"\s+", " ", str(raw.get("summary") or "").strip())
    supported, warning = _summary_is_supported(summary, posting, evidence)
    warnings: list[str] = []
    if not supported:
        summary = original_summary
        warnings.append(warning + " The original summary was retained.")

    skill_ids = [str(item.get("id") or "") for item in evidence.get("skills") or []]
    skill_order = _normalize_order(raw.get("skill_order"), skill_ids)
    raw_sections = {
        str(item.get("section_id") or ""): item
        for item in raw.get("experience_sections") or []
        if isinstance(item, Mapping)
    }
    experience_sections = []
    for section in evidence.get("experience_sections") or []:
        section_id = str(section.get("section_id") or "")
        bullet_ids = [str(item.get("id") or "") for item in section.get("bullets") or []]
        requested = raw_sections.get(section_id, {}).get("bullet_order") or []
        experience_sections.append(
            {
                "section_id": section_id,
                "bullet_order": _normalize_order(requested, bullet_ids),
            }
        )

    reference_ids = [
        str(item.get("id") or "") for item in evidence.get("reference_points") or []
    ]
    reference_evidence_ids = _normalize_selection(
        raw.get("reference_evidence_ids"), reference_ids
    )[:8]
    evidence_text = _normalize_text(_evidence_text(evidence))
    keyword_alignment = []
    for value in raw.get("keyword_alignment") or []:
        text = _safe_text(value, 120)
        if text and _normalize_text(text) in evidence_text and text not in keyword_alignment:
            keyword_alignment.append(text)
        if len(keyword_alignment) >= 12:
            break
    confirmed_skills = [
        _safe_text(item.get("skill"), 120)
        for item in evidence.get("user_confirmed_skill_evidence") or []
        if _safe_text(item.get("skill"), 120)
    ][:MAX_CONFIRMED_SKILL_EVIDENCE]
    for skill in confirmed_skills:
        if skill not in keyword_alignment:
            keyword_alignment.append(skill)
    change_notes = []
    for value in raw.get("change_notes") or []:
        text = _safe_text(value, 240)
        if text and text not in change_notes:
            change_notes.append(text)
        if len(change_notes) >= 8:
            break
    if confirmed_skills:
        confirmed_change_note = (
            "Added user-confirmed JD keyword(s) to Technical Skills: "
            + ", ".join(confirmed_skills)
            + "."
        )
        if confirmed_change_note not in change_notes:
            change_notes.append(confirmed_change_note)

    cover_letter_paragraphs: list[str] = []
    if cover_letter_requested:
        requested_paragraphs = [
            re.sub(r"\s+", " ", str(value or "").strip())
            for value in raw.get("cover_letter_paragraphs") or []
            if str(value or "").strip()
        ][:5]
        cover_supported, cover_warning = _cover_letter_is_supported(
            requested_paragraphs,
            posting,
            evidence,
        )
        if cover_supported:
            cover_letter_paragraphs = requested_paragraphs
        else:
            cover_letter_paragraphs = _fallback_cover_letter(
                posting,
                evidence,
                eligibility or {},
            )
            warnings.append(cover_warning + " A conservative local letter was used instead.")
    return {
        "summary": summary,
        "skill_order": skill_order,
        "experience_sections": experience_sections,
        "reference_evidence_ids": reference_evidence_ids,
        "cover_letter_paragraphs": cover_letter_paragraphs,
        "keyword_alignment": keyword_alignment,
        "confirmed_skills": confirmed_skills,
        "change_notes": change_notes,
        "validation_warnings": warnings,
    }


class JobIntelligenceService:
    """Coordinate paid per-job actions without exposing private credentials."""

    def __init__(
        self,
        paths: AppPaths,
        google_connection: GoogleConnectionService | None = None,
        *,
        settings_loader: Callable[[Path], OpenAISettings] = load_openai_settings,
        researcher_factory: Callable[[str, str], OfficialJobResearcher] | None = None,
        planner_factory: Callable[[str, str], ResumePlanner] | None = None,
        exact_posting_resolver: (
            Callable[[Mapping[str, Any]], ExactPostingResolution] | None
        ) = None,
        resume_library=None,
        pdf_converter=convert_docx_to_pdf,
        cover_letter_builder=build_cover_letter_docx,
    ) -> None:
        self.paths = paths
        self.google_connection = google_connection
        self.settings_loader = settings_loader
        self.researcher_factory = researcher_factory or (
            lambda key, model: OfficialJobResearcher(key, model=model)
        )
        self.planner_factory = planner_factory or (
            lambda key, model: ResumePlanner(key, model=model)
        )
        self.exact_posting_resolver = exact_posting_resolver or resolve_exact_ashby_posting
        self.resume_library = resume_library or DriveResumeLibrary(paths, google_connection)
        self.pdf_converter = pdf_converter
        self.cover_letter_builder = cover_letter_builder
        self.root = paths.secrets_root / "job_intelligence"
        self.research_cache_path = self.root / "official_research_cache.json"
        self.analysis_root = self.root / "analyses"
        self.plan_root = self.root / "resume_plans"
        self.output_root = self.root / "generated_documents"
        self.artifact_index_path = self.root / "artifact_index.json"
        self._lock = threading.Lock()

    @staticmethod
    def _exact_research(
        facts: Mapping[str, Any],
        resolution: ExactPostingResolution,
        existing: Mapping[str, Any],
        researcher: OfficialJobResearcher,
        *,
        refresh: bool,
    ) -> tuple[dict[str, Any], list[str]]:
        """Merge an exact Ashby posting into the shared private research cache."""

        research = dict(existing or {})
        job_id = str(facts.get("job_record_id") or "")
        postings_by_id = {
            str(item.get("official_job_id") or ""): dict(item)
            for item in research.get("postings") or []
            if item.get("official_job_id")
        }
        matches = {
            str(alert_id): [dict(item) for item in rows]
            for alert_id, rows in (research.get("matches") or {}).items()
        }
        exact_fingerprints = {
            str(alert_id): str(value)
            for alert_id, value in (
                research.get("exact_posting_fingerprints") or {}
            ).items()
            if value
        }
        checked_fingerprints = {
            str(alert_id): str(value)
            for alert_id, value in (
                research.get("checked_alert_fingerprints") or {}
            ).items()
            if value
        }
        checked_ids = {
            str(value) for value in research.get("checked_alert_ids") or [] if value
        }
        warnings = [resolution.warning] if resolution.warning else []
        source = dict(resolution.posting or {})
        source_fingerprint = str(source.get("source_fingerprint") or "")
        cached_posting = None
        if source and not refresh and exact_fingerprints.get(job_id) == source_fingerprint:
            for mapping in matches.get(job_id, []):
                candidate = postings_by_id.get(str(mapping.get("official_job_id") or ""))
                if candidate and str(candidate.get("exact_source_fingerprint") or "") == (
                    source_fingerprint
                ):
                    cached_posting = candidate
                    break

        api_calls = 0
        if source:
            posting = cached_posting
            if posting is None:
                posting = researcher.extract_exact_posting(facts, source)
                api_calls = 1
            official_id = str(posting.get("official_job_id") or "")
            postings_by_id[official_id] = dict(posting)
            matches[job_id] = [
                {
                    "official_job_id": official_id,
                    "match_status": "exact_candidate",
                    "match_score": 100,
                    "match_reason": (
                        "Exact Ashby job UUID matched the selected official employer URL."
                    ),
                }
            ]
            exact_fingerprints[job_id] = source_fingerprint
        else:
            matches.pop(job_id, None)
            exact_fingerprints.pop(job_id, None)

        fingerprint_payload = json.dumps(
            {
                "company": facts.get("company"),
                "title": facts.get("title"),
                "official_url": facts.get("official_url"),
                "policy": "exact_only",
                "exact_source": source_fingerprint,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        checked_fingerprints[job_id] = hashlib.sha256(
            fingerprint_payload.encode("utf-8")
        ).hexdigest()
        checked_ids.add(job_id)
        today = datetime.now(TIME_ZONE).date().isoformat()
        research.update(
            {
                "verified_at": today,
                "research_model": researcher.model,
                "checked_alert_ids": sorted(checked_ids),
                "checked_alert_fingerprints": dict(sorted(checked_fingerprints.items())),
                "exact_posting_fingerprints": dict(sorted(exact_fingerprints.items())),
                "postings": sorted(
                    postings_by_id.values(),
                    key=lambda item: (
                        _normalize_text(item.get("company")),
                        _normalize_text(item.get("title")),
                        item.get("official_url") or "",
                    ),
                ),
                "matches": dict(sorted(matches.items())),
                "research_stats": {
                    "current_alerts": 1,
                    "alerts_submitted": 0,
                    "alerts_checked_without_search": 0 if source else 1,
                    "api_calls": api_calls,
                    "alerts_reused_from_cache": int(cached_posting is not None),
                    "alerts_waiting_for_future_run": 0,
                    "exact_feed_matches": int(bool(source)),
                    "related_candidates_allowed": 0,
                },
            }
        )
        return research, warnings

    def _settings(self) -> OpenAISettings:
        return self.settings_loader(self.paths.project_root)

    def status(self) -> dict[str, Any]:
        settings = self._settings()
        library = self.resume_library.status()
        return {
            "openai_configured": settings.configured,
            "model": settings.model,
            "configuration_source": settings.source,
            "manual_only": True,
            "contact_data_sent_to_openai": False,
            **library,
        }

    def store_baseline_resume(
        self,
        content: bytes,
        original_name: str = "base_resume.docx",
    ) -> dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            raise JobIntelligenceError("Another job-intelligence action is already running.")
        try:
            library = self.resume_library.store_baseline(content, original_name)
        finally:
            self._lock.release()
        settings = self._settings()
        return {
            "openai_configured": settings.configured,
            "model": settings.model,
            "configuration_source": settings.source,
            "manual_only": True,
            "contact_data_sent_to_openai": False,
            **library,
        }

    def store_reference_documents(
        self,
        files: Iterable[tuple[str, bytes]],
    ) -> dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            raise JobIntelligenceError("Another job-intelligence action is already running.")
        try:
            library = self.resume_library.store_references(files)
        finally:
            self._lock.release()
        settings = self._settings()
        return {
            "openai_configured": settings.configured,
            "model": settings.model,
            "configuration_source": settings.source,
            "manual_only": True,
            "contact_data_sent_to_openai": False,
            **library,
        }

    def analyze(self, job: Mapping[str, Any], *, refresh: bool = False) -> dict[str, Any]:
        facts = _public_job_facts(job)
        settings = self._settings()
        if not settings.configured:
            raise JobIntelligenceError(
                "OpenAI is not configured on the server. Add OPENAI_API_KEY and restart FastAPI."
            )
        if not self._lock.acquire(blocking=False):
            raise JobIntelligenceError("Another job-intelligence action is already running.")
        try:
            existing = read_json(self.research_cache_path, default={}) or {}
            researcher = self.researcher_factory(settings.api_key, settings.model)
            resolution = (
                self.exact_posting_resolver(facts)
                if facts.get("official_url")
                else ExactPostingResolution(False)
            )
            analysis_warnings: list[str] = []
            if resolution.recognized:
                research, analysis_warnings = self._exact_research(
                    facts,
                    resolution,
                    existing,
                    researcher,
                    refresh=bool(refresh),
                )
            else:
                research = researcher.research(
                    [facts],
                    existing,
                    refresh_existing=bool(refresh),
                    max_new_alerts=1,
                    exact_only=bool(facts.get("official_url")),
                )
            write_json_atomic(self.research_cache_path, research)
            postings = {
                str(item.get("official_job_id") or ""): dict(item)
                for item in research.get("postings") or []
            }
            candidates: list[dict[str, Any]] = []
            for mapping in research.get("matches", {}).get(facts["job_record_id"], []):
                posting = postings.get(str(mapping.get("official_job_id") or ""))
                if not posting:
                    continue
                eligibility = score_official_posting(posting, personal_resume_profile())
                candidates.append(
                    {
                        **posting,
                        "official_match_status": str(mapping.get("match_status") or ""),
                        "official_match_score": int(mapping.get("match_score") or 0),
                        "official_match_reason": str(mapping.get("match_reason") or ""),
                        "eligibility": eligibility,
                    }
                )
            candidates.sort(
                key=lambda item: (
                    -int(item.get("official_match_score") or 0),
                    -int((item.get("eligibility") or {}).get("score") or 0),
                )
            )
            verified_at = str(research.get("verified_at") or "")
            analysis_id = _analysis_id(facts, candidates, verified_at)
            stats = dict(research.get("research_stats") or {})
            library_status = self.resume_library.status()
            analysis = {
                "analysis_id": analysis_id,
                "status": "completed" if candidates else "no_official_match",
                "job": facts,
                "candidates": candidates,
                "verified_at": verified_at,
                "model": settings.model,
                "cached": int(stats.get("api_calls") or 0) == 0,
                "research_stats": stats,
                "warnings": analysis_warnings,
                "baseline_resume_configured": bool(
                    library_status.get("baseline_resume_configured")
                ),
                "privacy": {
                    "gmail_content_sent": False,
                    "contact_data_sent": False,
                    "connection_data_sent": False,
                    "reference_evidence_sent": False,
                },
            }
            write_json_atomic(self.analysis_root / f"{analysis_id}.json", analysis)
            return analysis
        except OpenAIResearchError:
            raise
        finally:
            self._lock.release()

    def _load_analysis(self, analysis_id: str) -> dict[str, Any]:
        analysis_id = _safe_identifier(analysis_id, "analysis_")
        value = read_json(self.analysis_root / f"{analysis_id}.json")
        if not isinstance(value, dict):
            raise FileNotFoundError("The requested job analysis is unavailable.")
        return value

    @staticmethod
    def _selected_posting(analysis: Mapping[str, Any], official_job_id: str) -> dict[str, Any]:
        for candidate in analysis.get("candidates") or []:
            if str(candidate.get("official_job_id") or "") == official_job_id:
                return dict(candidate)
        raise FileNotFoundError("The selected official job is not part of this analysis.")

    def _plan_cache_key(
        self,
        analysis_id: str,
        official_job_id: str,
        base_resume: Path,
        reference_digest: str,
        confirmed_evidence_digest: str,
        model: str,
        cover_letter_requested: bool,
    ) -> str:
        value = (
            f"{analysis_id}\0{official_job_id}\0{resume_sha256(base_resume)}\0"
            f"{reference_digest}\0{confirmed_evidence_digest}\0{model}\0"
            f"{int(cover_letter_requested)}"
        )
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _requested_outputs(values: Iterable[str]) -> list[str]:
        requested = {str(value or "").strip() for value in values}
        unsupported = requested.difference(SUPPORTED_OUTPUTS)
        if unsupported:
            raise ValueError("One or more requested document formats are unsupported.")
        if not requested:
            raise ValueError("Select at least one output: DOCX, PDF, or cover letter.")
        return [
            value
            for value in (OUTPUT_RESUME_DOCX, OUTPUT_RESUME_PDF, OUTPUT_COVER_LETTER)
            if value in requested
        ]

    def generate_documents(
        self,
        analysis_id: str,
        official_job_id: str,
        *,
        outputs: Iterable[str],
        confirmed_skill_evidence: Iterable[Mapping[str, Any]] = (),
        refresh_plan: bool = False,
    ) -> dict[str, Any]:
        analysis = self._load_analysis(analysis_id)
        posting = self._selected_posting(analysis, str(official_job_id).strip())
        confirmed_evidence = _confirmed_skill_evidence(
            confirmed_skill_evidence,
            posting,
        )
        requested_outputs = self._requested_outputs(outputs)
        cover_letter_requested = OUTPUT_COVER_LETTER in requested_outputs
        settings = self._settings()
        if not settings.configured:
            raise JobIntelligenceError(
                "OpenAI is not configured on the server. Add OPENAI_API_KEY and restart FastAPI."
            )
        if not self._lock.acquire(blocking=False):
            raise JobIntelligenceError("Another job-intelligence action is already running.")
        try:
            inputs = self.resume_library.materialize_inputs()
            base_resume = Path(inputs["baseline_path"])
            evidence = extract_resume_evidence(base_resume)
            reference_points = extract_reference_evidence(
                inputs.get("references") or [],
                posting,
            )
            evidence["reference_points"] = reference_points
            evidence["user_confirmed_skill_evidence"] = confirmed_evidence
            if confirmed_evidence:
                self.resume_library.store_confirmed_skill_evidence(confirmed_evidence)
            eligibility = dict(posting.get("eligibility") or {})
            confirmed_evidence_digest = hashlib.sha256(
                json.dumps(
                    confirmed_evidence,
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            plan_key = self._plan_cache_key(
                analysis_id,
                str(official_job_id),
                base_resume,
                str(inputs.get("reference_digest") or ""),
                confirmed_evidence_digest,
                settings.model,
                cover_letter_requested,
            )
            plan_path = self.plan_root / f"{plan_key}.json"
            plan = None if refresh_plan else read_json(plan_path)
            plan_cached = isinstance(plan, dict)
            if not plan_cached:
                planner = self.planner_factory(settings.api_key, settings.model)
                plan = planner.plan(
                    posting,
                    evidence,
                    eligibility,
                    cover_letter_requested=cover_letter_requested,
                )
            plan = normalize_resume_plan(
                dict(plan or {}),
                posting,
                evidence,
                cover_letter_requested=cover_letter_requested,
                eligibility=eligibility,
            )
            if not plan_cached:
                write_json_atomic(plan_path, plan)

            now = datetime.now(TIME_ZONE).replace(microsecond=0)
            company = _safe_filename(posting.get("company"), "company")
            title = _safe_filename(posting.get("title"), "role")
            generation_id = "generation_" + hashlib.sha256(
                f"{plan_key}\0{now.isoformat()}".encode("utf-8")
            ).hexdigest()[:22]
            suffix = generation_id[-6:]
            generation_root = self.output_root / now.date().isoformat() / generation_id
            generation_root.mkdir(parents=True, exist_ok=True)
            warnings = list(plan.get("validation_warnings") or [])
            artifact_specs: list[tuple[str, Path, str]] = []
            working_resume: Path | None = None
            if {OUTPUT_RESUME_DOCX, OUTPUT_RESUME_PDF}.intersection(requested_outputs):
                resume_name = (
                    f"{company}_{title}_Resume_{now.strftime('%Y-%m-%d')}_{suffix}.docx"
                )
                working_resume = generation_root / resume_name
                tailor_resume_docx(base_resume, working_resume, dict(plan))
                if OUTPUT_RESUME_DOCX in requested_outputs:
                    artifact_specs.append((OUTPUT_RESUME_DOCX, working_resume, DOCX_MIME_TYPE))
            if OUTPUT_RESUME_PDF in requested_outputs:
                if working_resume is None:  # pragma: no cover - guarded above
                    raise RuntimeError("The tailored resume DOCX was not created.")
                pdf_path = working_resume.with_suffix(".pdf")
                self.pdf_converter(working_resume, pdf_path)
                artifact_specs.append((OUTPUT_RESUME_PDF, pdf_path, PDF_MIME_TYPE))
            if OUTPUT_COVER_LETTER in requested_outputs:
                cover_name = (
                    f"{company}_{title}_Cover_Letter_"
                    f"{now.strftime('%Y-%m-%d')}_{suffix}.docx"
                )
                cover_path = generation_root / cover_name
                self.cover_letter_builder(
                    cover_path,
                    identity=extract_resume_identity(base_resume),
                    posting=posting,
                    paragraphs=list(plan.get("cover_letter_paragraphs") or []),
                    generated_on=now.date(),
                )
                artifact_specs.append((OUTPUT_COVER_LETTER, cover_path, DOCX_MIME_TYPE))

            artifacts: list[dict[str, Any]] = []
            stored_records: list[dict[str, Any]] = []
            for kind, local_path, mime_type in artifact_specs:
                artifact_id = "artifact_" + hashlib.sha256(
                    f"{generation_id}\0{kind}".encode("utf-8")
                ).hexdigest()[:22]
                uploaded = self.resume_library.upload_artifact(
                    local_path,
                    now.date().isoformat(),
                    mime_type,
                )
                record = {
                    "artifact_id": artifact_id,
                    "generation_id": generation_id,
                    "kind": kind,
                    "local_path": str(local_path),
                    "file_name": local_path.name,
                    "mime_type": mime_type,
                    "sha256": resume_sha256(local_path),
                    "analysis_id": analysis_id,
                    "official_job_id": str(official_job_id),
                    "generated_at": now.isoformat(),
                    **uploaded,
                }
                stored_records.append(record)
                artifacts.append(
                    {
                        key: record[key]
                        for key in (
                            "artifact_id",
                            "kind",
                            "file_name",
                            "mime_type",
                            "drive_url",
                            "folder_url",
                        )
                    }
                )
            self.resume_library.record_artifacts(stored_records)
            index = read_json(self.artifact_index_path, default={}) or {}
            index.update({record["artifact_id"]: record for record in stored_records})
            write_json_atomic(self.artifact_index_path, index)

            reference_by_id = {
                str(item.get("id") or ""): str(item.get("text") or "")
                for item in reference_points
            }
            references_used = [
                reference_by_id[item_id]
                for item_id in plan.get("reference_evidence_ids") or []
                if item_id in reference_by_id
            ]
            return {
                "generation_id": generation_id,
                "generated_at": now.isoformat(),
                "artifacts": artifacts,
                "model": settings.model,
                "plan_cached": plan_cached,
                "change_notes": list(plan.get("change_notes") or []),
                "keyword_alignment": list(plan.get("keyword_alignment") or []),
                "confirmed_skills_added": list(plan.get("confirmed_skills") or []),
                "reference_points_used": references_used,
                "warnings": warnings,
                "requires_user_review": True,
                "baseline_unchanged": resume_sha256(base_resume)
                == str((inputs.get("baseline") or {}).get("sha256") or ""),
            }
        finally:
            self._lock.release()

    def artifact(self, artifact_id: str) -> tuple[Path, dict[str, Any]]:
        artifact_id = _safe_identifier(artifact_id, "artifact_")
        index = read_json(self.artifact_index_path, default={}) or {}
        metadata = index.get(artifact_id)
        if isinstance(metadata, Mapping):
            path = Path(str(metadata.get("local_path") or "")).resolve()
            try:
                path.relative_to(self.output_root.resolve())
            except ValueError:
                path = Path()
            if path.is_file() and resume_sha256(path) == str(metadata.get("sha256") or ""):
                return path, dict(metadata)
        path, remote = self.resume_library.materialize_artifact(artifact_id)
        return path, dict(remote)
