"""Manual official-job analysis and truth-preserving resume orchestration."""

from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from job_hunt.intelligence.usage import AIUsageLedger
from job_hunt.resumes.outputs import (
    build_cover_letter_docx,
    build_job_description_docx,
    convert_docx_to_pdf,
)
from job_hunt.jobs.enrichment import personal_resume_profile, score_official_posting
from job_hunt.integrations.ashby_postings import (
    ExactPostingResolution,
    resolve_exact_ashby_posting,
)
from job_hunt.integrations.openai_research import (
    OfficialJobResearcher,
    OpenAIResearchError,
)
from job_hunt.integrations.official_descriptions import (
    OfficialDescriptionResolution,
    clean_description,
    resolve_official_description,
)
from job_hunt.intelligence.config import OpenAISettings, load_openai_settings
from job_hunt.runtime.files import read_json, write_json_atomic
from job_hunt.resumes.docx import (
    extract_resume_evidence,
    extract_resume_identity,
    extract_resume_text,
    resume_sha256,
    tailor_resume_docx,
)
from job_hunt.resumes.library import (
    DOCX_MIME_TYPE,
    JSON_MIME_TYPE,
    MARKDOWN_MIME_TYPE,
    PDF_MIME_TYPE,
    DriveResumeLibrary,
)
from job_hunt.resumes.references import extract_reference_evidence
from job_hunt.runtime.google import GoogleConnectionService
from job_hunt.runtime.paths import AppPaths, TIME_ZONE
from job_hunt.jobs.skills import (
    map_job_skills_to_evidence,
    normalize_skill_text,
    resume_evidence_items,
    skill_placement,
)


MAX_SUMMARY_WORDS = 100
MAX_CONFIRMED_SKILL_EVIDENCE = 20
RESUME_PLAN_VERSION = 3
OUTPUT_RESUME_DOCX = "resume_docx"
OUTPUT_RESUME_PDF = "resume_pdf"
OUTPUT_COVER_LETTER = "cover_letter"
APPLICATION_RESUME_STEM = "Asrith_Ladi_AI_ML_Engineer_6Y"
APPLICATION_COVER_LETTER_NAME = f"{APPLICATION_RESUME_STEM}_Cover_Letter.docx"
APPLICATION_JOB_DESCRIPTION_NAME = "Job_Description.md"
APPLICATION_JOB_DESCRIPTION_DOCX_NAME = "Job_Description.docx"
APPLICATION_DETAILS_NAME = "Application_Details.json"
APPLICATION_PACKAGE_VERSION = 2
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
                    "bullet_rewrites": {
                        "type": "array",
                        "maxItems": 12,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "bullet_id": {"type": "string"},
                                "text": {"type": "string"},
                            },
                            "required": ["bullet_id", "text"],
                        },
                    },
                },
                "required": ["section_id", "bullet_order", "bullet_rewrites"],
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
relevance; IDs must be copied exactly. Preserve every evidence bullet, but you may provide
a natural one-sentence rewrite in bullet_rewrites when it preserves the original meaning.
When supported_jd_keyword_evidence cites an experience-bullet ID in direct_evidence_ids,
reframe the strongest
one to four relevant bullets with the employer's exact wording; use an empty rewrite list
when no bullet-specific mapping exists. Keep every original metric and technology claim
unchanged. Add an exact JD phrase to a bullet only when direct_evidence_ids cites that
same bullet. A summary may synthesize any supported_jd_keyword_evidence, but it must not
expand beyond the cited facts. Otherwise leave the wording unchanged. Avoid keyword
stuffing: prefer one or two
high-value exact phrases in the most relevant sentences. change_notes must describe only
truthful positioning changes, and keyword_alignment may contain only phrases supported by
documented or explicitly user-confirmed evidence.
Reference points are additional verified evidence, not permission to invent new facts;
select only their supplied IDs. Do not move a reference point into a work-experience bullet
because that could misattribute it to an employer. user_confirmed_skill_evidence contains
professional facts the user explicitly confirmed; you may use those facts and exact skill
labels naturally, but you may not expand beyond the supplied note. Skill placement in the
DOCX is deterministic, so do not create new skill-section prose. If cover_letter_requested
is true, write 3-4 concise,
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


_ATS_IGNORED_KEYWORD_TOKENS = frozenset(
    {
        "a",
        "an",
        "and",
        "experience",
        "for",
        "in",
        "knowledge",
        "of",
        "or",
        "proficiency",
        "skill",
        "skills",
        "strong",
        "the",
        "to",
        "using",
        "with",
    }
)


def _normalize_ats_text(value: object) -> str:
    value = str(value or "").casefold().replace("&", " and ")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+#]+", " ", value)).strip()


def _unique_skill_labels(values: Iterable[object]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        label = re.sub(r"\s+", " ", str(value or "").strip())[:160]
        key = _normalize_text(label)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(label)
    return result


def _ats_keyword_matches(
    label: str,
    normalized_resume: str,
    resume_tokens: set[str],
) -> bool:
    """Match one extracted JD term using documented, deterministic text rules."""

    normalized_label = _normalize_ats_text(label)
    if not normalized_label:
        return False
    padded_resume = f" {normalized_resume} "
    alternatives = [
        value.strip()
        for value in re.split(r"\s+or\s+", normalized_label)
        if value.strip()
    ]
    for alternative in alternatives:
        if f" {alternative} " in padded_resume:
            return True
        tokens = [
            token
            for token in alternative.split()
            if token not in _ATS_IGNORED_KEYWORD_TOKENS
        ]
        if tokens and all(token in resume_tokens for token in tokens):
            return True
    return False


def score_ats_alignment(
    posting: Mapping[str, Any],
    resume_text: str,
) -> dict[str, Any]:
    """Estimate transparent JD-keyword coverage; this is not an employer ATS score."""

    required = _unique_skill_labels(posting.get("required_skills") or [])
    preferred = _unique_skill_labels(posting.get("preferred_skills") or [])
    normalized_resume = _normalize_ats_text(resume_text)
    resume_tokens = set(normalized_resume.split())

    matched_required = [
        label
        for label in required
        if _ats_keyword_matches(label, normalized_resume, resume_tokens)
    ]
    matched_preferred = [
        label
        for label in preferred
        if _ats_keyword_matches(label, normalized_resume, resume_tokens)
    ]
    missing_required = [label for label in required if label not in matched_required]
    missing_preferred = [label for label in preferred if label not in matched_preferred]
    required_coverage = (
        round(100 * len(matched_required) / len(required)) if required else None
    )
    preferred_coverage = (
        round(100 * len(matched_preferred) / len(preferred)) if preferred else None
    )

    if required and preferred:
        score = round(0.8 * int(required_coverage or 0) + 0.2 * int(preferred_coverage or 0))
        weighting = "Required terms 80%; preferred terms 20%."
    elif required:
        score = int(required_coverage or 0)
        weighting = "Required terms 100%; the JD supplied no preferred terms."
    elif preferred:
        score = int(preferred_coverage or 0)
        weighting = "Preferred terms 100%; the JD supplied no required terms."
    else:
        score = None
        weighting = "The verified JD supplied no reliable skill terms to score."

    if score is None:
        band = "Not scorable"
    elif score >= 80:
        band = "Strong keyword alignment"
    elif score >= 60:
        band = "Moderate keyword alignment"
    elif score >= 40:
        band = "Limited keyword alignment"
    else:
        band = "Low keyword alignment"

    required_summary = f"{len(matched_required)}/{len(required)} required"
    preferred_summary = f"{len(matched_preferred)}/{len(preferred)} preferred"
    return {
        "score": score,
        "band": band,
        "required_coverage": required_coverage,
        "preferred_coverage": preferred_coverage,
        "matched_required": matched_required,
        "missing_required": missing_required,
        "matched_preferred": matched_preferred,
        "missing_preferred": missing_preferred,
        "breakdown": f"Matched {required_summary} and {preferred_summary}. {weighting}",
    }


def _safe_text(value: object, limit: int) -> str:
    return str(value or "").strip()[:limit]


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


def _markdown_table_value(value: object) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "").strip()).replace("|", "\\|")
    return cleaned or "Not available"


def _markdown_bullets(values: Iterable[object]) -> str:
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    return "\n".join(f"- {value}" for value in cleaned) or "- Not available"


class ResumePlanner:
    """Create a small structured ranking plan; DOCX edits remain deterministic."""

    def __init__(self, api_key: str, model: str, client=None):
        if client is None:
            OpenAI = _require_openai_client()
            client = OpenAI(api_key=str(api_key).strip())
        self.client = client
        self.model = str(model).strip()
        self._usage_recorder: Callable[..., dict[str, Any]] | None = None
        self._usage_context: dict[str, Any] = {}

    def configure_usage_recording(
        self,
        recorder: Callable[..., dict[str, Any]],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        """Attach privacy-safe response metering for this manual plan action."""

        self._usage_recorder = recorder
        self._usage_context = dict(context or {})

    def _record_usage(self, response: object) -> None:
        if self._usage_recorder is None:
            return
        try:
            self._usage_recorder(
                response,
                operation="resume_plan",
                model=self.model,
                context=self._usage_context,
            )
        except Exception:
            # A usage-ledger failure must not discard a paid planning response.
            return

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
            self._record_usage(response)
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


def _supported_keyword_mappings(evidence: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        normalize_skill_text(item.get("skill")): dict(item)
        for item in evidence.get("supported_jd_keyword_evidence") or []
        if isinstance(item, Mapping) and normalize_skill_text(item.get("skill"))
    }


def _exact_keyword_occurs(label: object, value: object) -> bool:
    normalized_value = f" {_normalize_ats_text(value)} "
    normalized_label = _normalize_ats_text(label)
    return any(
        f" {alternative.strip()} " in normalized_value
        for alternative in re.split(r"\s+or\s+", normalized_label)
        if alternative.strip()
    )


def _bullet_rewrite_is_supported(
    rewritten: str,
    source_bullet: Mapping[str, Any],
    posting: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> tuple[bool, str]:
    source = re.sub(r"\s+", " ", str(source_bullet.get("text") or "").strip())
    text = re.sub(r"\s+", " ", str(rewritten or "").strip())
    if not 6 <= len(text.split()) <= 70 or len(text) > 500:
        return False, "the rewritten bullet length was outside the safe range"
    if re.search(r"\b(?:I|my|me)\b", text, re.IGNORECASE):
        return False, "resume bullets must not introduce first-person wording"
    if _contains_contact(text):
        return False, "the rewritten bullet introduced contact or web information"
    if re.search(r"\[[A-Z][A-Z0-9_ -]+\]|\{\{.+?\}\}", text):
        return False, "the rewritten bullet introduced an unresolved placeholder"

    source_numbers = set(re.findall(r"\d+(?:\.\d+)?%?\+?", source))
    rewritten_numbers = set(re.findall(r"\d+(?:\.\d+)?%?\+?", text))
    if rewritten_numbers != source_numbers:
        return False, "the rewritten bullet added, removed, or changed a numeric claim"

    target_company = _normalize_text(posting.get("company"))
    if (
        target_company
        and target_company not in _normalize_text(source)
        and target_company in _normalize_text(text)
    ):
        return False, "the rewritten bullet incorrectly claimed the target employer"

    bullet_id = str(source_bullet.get("id") or "")
    supported = _supported_keyword_mappings(evidence)
    for skill in [
        *(posting.get("required_skills") or []),
        *(posting.get("preferred_skills") or []),
    ]:
        if not _exact_keyword_occurs(skill, text) or _exact_keyword_occurs(skill, source):
            continue
        mapping = supported.get(normalize_skill_text(skill), {})
        direct_ids = {
            str(value) for value in mapping.get("direct_evidence_ids") or []
        }
        if bullet_id not in direct_ids:
            return False, f"the exact JD phrase {skill} was not supported by this bullet"

    source_tokens = {
        token
        for token in _normalize_ats_text(source).split()
        if token not in _ATS_IGNORED_KEYWORD_TOKENS and len(token) > 1
    }
    rewritten_tokens = set(_normalize_ats_text(text).split())
    if source_tokens:
        retained = len(source_tokens.intersection(rewritten_tokens)) / len(source_tokens)
        if retained < 0.6:
            return False, "the rewrite moved too far from the original evidence"
    if len(text.split()) > len(source.split()) + 12:
        return False, "the rewrite added too much wording beyond the original evidence"
    return True, ""


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
    supported_keywords = _supported_keyword_mappings(evidence)
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
        if (
            not _exact_keyword_occurs(skill, evidence_text)
            and _exact_keyword_occurs(skill, summary)
            and normalize_skill_text(skill) not in supported_keywords
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
    supported_keywords = _supported_keyword_mappings(evidence)
    for skill in [
        *(posting.get("required_skills") or []),
        *(posting.get("preferred_skills") or []),
    ]:
        if (
            not _exact_keyword_occurs(skill, source)
            and _exact_keyword_occurs(skill, text)
            and normalize_skill_text(skill) not in supported_keywords
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
    for value in raw.get("validation_warnings") or []:
        prior_warning = _safe_text(value, 500)
        if prior_warning and prior_warning not in warnings:
            warnings.append(prior_warning)
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
        bullets_by_id = {
            str(item.get("id") or ""): dict(item)
            for item in section.get("bullets") or []
            if str(item.get("id") or "")
        }
        bullet_ids = list(bullets_by_id)
        requested = raw_sections.get(section_id, {}).get("bullet_order") or []
        accepted_rewrites: list[dict[str, str]] = []
        seen_rewrites: set[str] = set()
        for rewrite in raw_sections.get(section_id, {}).get("bullet_rewrites") or []:
            if not isinstance(rewrite, Mapping):
                continue
            bullet_id = str(rewrite.get("bullet_id") or "")
            rewritten = re.sub(r"\s+", " ", str(rewrite.get("text") or "").strip())
            if bullet_id not in bullets_by_id or bullet_id in seen_rewrites:
                continue
            is_supported, rewrite_warning = _bullet_rewrite_is_supported(
                rewritten,
                bullets_by_id[bullet_id],
                posting,
                evidence,
            )
            if is_supported and rewritten != bullets_by_id[bullet_id]["text"]:
                accepted_rewrites.append({"bullet_id": bullet_id, "text": rewritten})
                seen_rewrites.add(bullet_id)
            elif not is_supported:
                warnings.append(
                    f"One experience-bullet rewrite was rejected because {rewrite_warning}; "
                    "the original bullet was retained."
                )
        experience_sections.append(
            {
                "section_id": section_id,
                "bullet_order": _normalize_order(requested, bullet_ids),
                "bullet_rewrites": accepted_rewrites,
            }
        )

    reference_ids = [
        str(item.get("id") or "") for item in evidence.get("reference_points") or []
    ]
    reference_evidence_ids = _normalize_selection(
        raw.get("reference_evidence_ids"), reference_ids
    )[:8]
    evidence_text = _normalize_text(_evidence_text(evidence))
    supported_keywords = _supported_keyword_mappings(evidence)
    keyword_alignment = []
    for value in raw.get("keyword_alignment") or []:
        text = _safe_text(value, 120)
        supported = (
            _normalize_text(text) in evidence_text
            or normalize_skill_text(text) in supported_keywords
        )
        if text and supported and text not in keyword_alignment:
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
    baseline_missing = [
        _safe_text(value, 120)
        for value in evidence.get("baseline_missing_jd_keywords") or []
        if _safe_text(value, 120)
    ]
    documented_equivalent_skills = [
        skill
        for skill in baseline_missing
        if normalize_skill_text(skill) in supported_keywords
        and normalize_skill_text(skill)
        not in {normalize_skill_text(value) for value in confirmed_skills}
    ]
    skill_addition_labels: list[str] = []
    seen_additions: set[str] = set()
    for skill in documented_equivalent_skills + confirmed_skills:
        key = normalize_skill_text(skill)
        if key and key not in seen_additions:
            seen_additions.add(key)
            skill_addition_labels.append(skill)
            if skill not in keyword_alignment:
                keyword_alignment.append(skill)
    skill_additions = [
        skill_placement(skill, evidence.get("skills") or [])
        for skill in skill_addition_labels
    ]
    change_notes = []
    for value in raw.get("change_notes") or []:
        text = _safe_text(value, 240)
        if text and text not in change_notes:
            change_notes.append(text)
        if len(change_notes) >= 8:
            break
    if confirmed_skills:
        confirmed_change_note = (
            "Placed user-confirmed JD keyword(s) in relevant Technical Skills categories: "
            + ", ".join(confirmed_skills)
            + "."
        )
        if confirmed_change_note not in change_notes:
            change_notes.append(confirmed_change_note)
    if documented_equivalent_skills:
        equivalent_note = (
            "Added exact JD wording backed by equivalent documented evidence to relevant "
            "Technical Skills categories: "
            + ", ".join(documented_equivalent_skills)
            + "."
        )
        if equivalent_note not in change_notes:
            change_notes.append(equivalent_note)
    rewrite_count = sum(
        len(section.get("bullet_rewrites") or []) for section in experience_sections
    )
    if rewrite_count:
        change_notes.append(
            f"Reframed {rewrite_count} existing experience bullet(s) with supported JD wording "
            "without changing the underlying facts or metrics."
        )

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
        "documented_equivalent_skills_added": documented_equivalent_skills,
        "skill_additions": skill_additions,
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
        usage_ledger=None,
        pdf_converter=convert_docx_to_pdf,
        cover_letter_builder=build_cover_letter_docx,
        job_description_builder=build_job_description_docx,
        description_resolver: (
            Callable[[Mapping[str, Any]], OfficialDescriptionResolution] | None
        ) = None,
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
        self.job_description_builder = job_description_builder
        self.description_resolver = description_resolver or resolve_official_description
        self.root = paths.runtime_root / "job_intelligence"
        self.usage_ledger = usage_ledger or AIUsageLedger(
            self.root / "ai_usage.json",
            google_connection,
        )
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

    def _configure_usage_recording(
        self,
        component: object,
        *,
        context: Mapping[str, Any],
        captured: list[dict[str, Any]],
    ) -> None:
        configure = getattr(component, "configure_usage_recording", None)
        if not callable(configure):
            return

        def recorder(
            response: object,
            *,
            operation: str,
            model: str,
            context: Mapping[str, Any] | None = None,
        ) -> dict[str, Any]:
            merged_context = dict(context or {})
            event = self.usage_ledger.record_response(
                response,
                operation=operation,
                model=model,
                context=merged_context,
            )
            captured.append(event)
            return event

        configure(recorder, context=context)

    def ai_usage(self, *, limit: int = 20) -> dict[str, Any]:
        return self.usage_ledger.report(limit=limit)

    def status(self) -> dict[str, Any]:
        settings = self._settings()
        library = self.resume_library.status()
        return {
            "openai_configured": settings.configured,
            "model": settings.model,
            "configuration_source": settings.source,
            "manual_only": True,
            "contact_data_sent_to_openai": False,
            "ai_usage": self.ai_usage(limit=5),
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
            usage_events: list[dict[str, Any]] = []
            self._configure_usage_recording(
                researcher,
                context=facts,
                captured=usage_events,
            )
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
            library_status = self.resume_library.status()
            baseline_evidence_items = None
            if library_status.get("baseline_resume_configured"):
                try:
                    scoring_inputs = self.resume_library.materialize_inputs()
                    scoring_evidence = extract_resume_evidence(
                        Path(scoring_inputs["baseline_path"])
                    )
                    baseline_evidence_items = resume_evidence_items(scoring_evidence)
                except Exception:
                    # Official-job analysis remains available if Drive materialization fails.
                    baseline_evidence_items = None
            candidates: list[dict[str, Any]] = []
            for mapping in research.get("matches", {}).get(facts["job_record_id"], []):
                posting = postings.get(str(mapping.get("official_job_id") or ""))
                if not posting:
                    continue
                eligibility = score_official_posting(
                    posting,
                    personal_resume_profile(),
                    evidence_items=baseline_evidence_items,
                )
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
            api_calls = int(stats.get("api_calls") or 0)
            analysis = {
                "analysis_id": analysis_id,
                "status": "completed" if candidates else "no_official_match",
                "job": facts,
                "candidates": candidates,
                "verified_at": verified_at,
                "model": settings.model,
                "cached": api_calls == 0,
                "research_stats": stats,
                "ai_usage": self.usage_ledger.action_summary(
                    usage_events,
                    cache_reused=api_calls == 0,
                    expected_api_calls=api_calls,
                ),
                "warnings": analysis_warnings,
                "baseline_resume_configured": bool(
                    library_status.get("baseline_resume_configured")
                ),
                "eligibility_evidence_source": (
                    "active_baseline_resume"
                    if baseline_evidence_items is not None
                    else "verified_profile_snapshot"
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
            f"v{RESUME_PLAN_VERSION}\0{analysis_id}\0{official_job_id}\0"
            f"{resume_sha256(base_resume)}\0"
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
            ats_before = score_ats_alignment(posting, extract_resume_text(base_resume))
            reference_points = extract_reference_evidence(
                inputs.get("references") or [],
                posting,
            )
            evidence["reference_points"] = reference_points
            evidence["user_confirmed_skill_evidence"] = confirmed_evidence
            job_skills = _unique_skill_labels(
                [
                    *(posting.get("required_skills") or []),
                    *(posting.get("preferred_skills") or []),
                ]
            )
            evidence["supported_jd_keyword_evidence"] = map_job_skills_to_evidence(
                job_skills,
                resume_evidence_items(evidence),
            )
            evidence["baseline_missing_jd_keywords"] = _unique_skill_labels(
                [
                    *(ats_before.get("missing_required") or []),
                    *(ats_before.get("missing_preferred") or []),
                ]
            )
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
            usage_events: list[dict[str, Any]] = []
            if not plan_cached:
                planner = self.planner_factory(settings.api_key, settings.model)
                self._configure_usage_recording(
                    planner,
                    context={
                        "job_record_id": str(
                            (analysis.get("job") or {}).get("job_record_id") or ""
                        ),
                        "official_job_id": str(official_job_id),
                        "company": posting.get("company"),
                        "title": posting.get("title"),
                    },
                    captured=usage_events,
                )
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
            company_name = _safe_text(posting.get("company"), 160) or "Unknown Company"
            role_name = _safe_text(posting.get("title"), 200) or "Role"
            generation_id = "generation_" + hashlib.sha256(
                f"{plan_key}\0{now.isoformat()}".encode("utf-8")
            ).hexdigest()[:22]
            generation_root = self.output_root / now.date().isoformat() / generation_id
            generation_root.mkdir(parents=True, exist_ok=True)
            warnings = list(plan.get("validation_warnings") or [])
            artifact_specs: list[tuple[str, Path, str]] = []
            working_resume: Path | None = None
            ats_after: dict[str, Any] | None = None
            if {OUTPUT_RESUME_DOCX, OUTPUT_RESUME_PDF}.intersection(requested_outputs):
                resume_name = f"{APPLICATION_RESUME_STEM}.docx"
                working_resume = generation_root / resume_name
                tailor_resume_docx(base_resume, working_resume, dict(plan))
                ats_after = score_ats_alignment(posting, extract_resume_text(working_resume))
                if OUTPUT_RESUME_DOCX in requested_outputs:
                    artifact_specs.append((OUTPUT_RESUME_DOCX, working_resume, DOCX_MIME_TYPE))
            if OUTPUT_RESUME_PDF in requested_outputs:
                if working_resume is None:  # pragma: no cover - guarded above
                    raise RuntimeError("The tailored resume DOCX was not created.")
                pdf_path = working_resume.with_suffix(".pdf")
                self.pdf_converter(working_resume, pdf_path)
                artifact_specs.append((OUTPUT_RESUME_PDF, pdf_path, PDF_MIME_TYPE))
            if OUTPUT_COVER_LETTER in requested_outputs:
                cover_path = generation_root / APPLICATION_COVER_LETTER_NAME
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
                    company_name=company_name,
                    role_name=role_name,
                    prepared_on=now.date().isoformat(),
                    mime_type=mime_type,
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
                            "folder_path",
                        )
                        if key in record
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
            before_score = ats_before.get("score")
            after_score = ats_after.get("score") if ats_after else None
            score_delta = (
                int(after_score) - int(before_score)
                if before_score is not None and after_score is not None
                else None
            )
            return {
                "generation_id": generation_id,
                "generated_at": now.isoformat(),
                "artifacts": artifacts,
                "model": settings.model,
                "plan_cached": plan_cached,
                "ai_usage": self.usage_ledger.action_summary(
                    usage_events,
                    cache_reused=plan_cached,
                    expected_api_calls=int(not plan_cached),
                ),
                "change_notes": list(plan.get("change_notes") or []),
                "keyword_alignment": list(plan.get("keyword_alignment") or []),
                "confirmed_skills_added": list(plan.get("confirmed_skills") or []),
                "documented_equivalent_skills_added": list(
                    plan.get("documented_equivalent_skills_added") or []
                ),
                "skill_placements": list(plan.get("skill_additions") or []),
                "experience_bullets_reframed": sum(
                    len(section.get("bullet_rewrites") or [])
                    for section in plan.get("experience_sections") or []
                ),
                "reference_points_used": references_used,
                "warnings": warnings,
                "requires_user_review": True,
                "ats_alignment": {
                    "before": ats_before,
                    "after": ats_after,
                    "delta": score_delta,
                    "methodology": (
                        "Local deterministic coverage of required and preferred terms "
                        "extracted from the verified JD. This is not a score from an "
                        "employer or ATS vendor."
                    ),
                },
                "baseline_unchanged": resume_sha256(base_resume)
                == str((inputs.get("baseline") or {}).get("sha256") or ""),
            }
        finally:
            self._lock.release()

    def archive_application_package(
        self,
        analysis_id: str,
        official_job_id: str,
        generation_id: str,
        *,
        source_job: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Archive verified job evidence beside generated documents after manual application."""

        analysis = self._load_analysis(analysis_id)
        posting = self._selected_posting(analysis, str(official_job_id).strip())
        generation_id = _safe_identifier(generation_id, "generation_")
        index = read_json(self.artifact_index_path, default={}) or {}
        generated_records = [
            dict(record)
            for record in index.values()
            if isinstance(record, Mapping)
            and str(record.get("generation_id") or "") == generation_id
            and str(record.get("analysis_id") or "") == analysis_id
            and str(record.get("official_job_id") or "") == official_job_id
        ]
        if not generated_records:
            raise FileNotFoundError(
                "The generated resume package is unavailable. Generate documents again."
            )

        first_artifact = generated_records[0]
        folder_id = str(first_artifact.get("folder_id") or "").strip()
        folder_url = str(first_artifact.get("folder_url") or "").strip()
        if not folder_id:
            match = re.search(r"/folders/([A-Za-z0-9_-]+)", folder_url)
            folder_id = match.group(1) if match else ""
        folder_path = str(first_artifact.get("folder_path") or "").strip()
        if not folder_id or not folder_path:
            raise JobIntelligenceError(
                "The generated resume folder cannot be verified. Generate documents again."
            )
        if any(
            str(record.get("folder_id") or folder_id).strip() != folder_id
            or str(record.get("folder_path") or folder_path).strip() != folder_path
            for record in generated_records
        ):
            raise JobIntelligenceError(
                "The generated documents do not share one verified Drive folder."
            )

        exact_description = clean_description(posting.get("description"))
        collected_description = clean_description(
            source_job.get("description")
            or source_job.get("job_description")
            or source_job.get("jd_text")
        )
        capture_warning = ""
        if exact_description:
            description = exact_description
            description_source = "verified_official_description"
            description_completeness = "full"
        elif collected_description:
            description = collected_description
            description_source = "collected_source_description"
            description_completeness = "partial"
            capture_warning = (
                "The saved text came from the discovery record and may omit sections from "
                "the official job page."
            )
        else:
            exact_resolution = self.exact_posting_resolver(posting)
            exact_ats_description = clean_description(
                (exact_resolution.posting or {}).get("description_html")
                or (exact_resolution.posting or {}).get("description")
            )
            if exact_ats_description:
                description = exact_ats_description
                description_source = "captured_exact_ats_description"
                description_completeness = "full"
                capture_warning = exact_resolution.warning
            else:
                resolved = self.description_resolver(posting)
                description = clean_description(resolved.description)
                description_source = resolved.source
                description_completeness = resolved.completeness
                capture_warning = " ".join(
                    value
                    for value in (exact_resolution.warning, resolved.warning)
                    if value
                )
            if not description:
                description = clean_description(posting.get("description_summary"))
                description_source = "verified_description_summary"
                description_completeness = "summary_only"
                capture_warning = " ".join(
                    value
                    for value in (
                        capture_warning,
                        (
                            "Only a verified summary was available. Open the official URL "
                            "before relying on this file as the complete JD."
                        ),
                    )
                    if value
                )

        package_root = self.root / "application_packages" / generation_id
        package_root.mkdir(parents=True, exist_ok=True)
        details_path = package_root / APPLICATION_DETAILS_NAME
        previous = read_json(details_path, default={}) or {}
        now = datetime.now(TIME_ZONE).replace(microsecond=0)
        applied_at = str(previous.get("applied_at") or now.isoformat())
        job_details = {
            key: posting.get(key)
            for key in (
                "official_job_id",
                "company",
                "title",
                "location",
                "experience_text",
                "experience_min",
                "experience_max",
                "workplace_type",
                "employment_type",
                "active_status",
                "requisition_id",
                "published_at",
                "official_url",
                "description_summary",
                "required_skills",
                "preferred_skills",
                "required_skill_evidence",
                "preferred_skill_evidence",
                "evidence_confidence",
                "source_notes",
                "eligibility",
            )
        }
        source_context = {
            key: _safe_text(source_job.get(key), 4096)
            for key in (
                "job_record_id",
                "provider",
                "alert_source",
                "source_url",
                "apply_url",
                "source_confidence",
                "match_type",
                "matched_terms",
                "experience_fit",
            )
            if _safe_text(source_job.get(key), 4096)
        }
        generated_documents = [
            {
                key: record.get(key)
                for key in ("artifact_id", "kind", "file_name", "drive_url", "sha256")
                if record.get(key)
            }
            for record in generated_records
        ]
        details = {
            "schema_version": APPLICATION_PACKAGE_VERSION,
            "application_status": "applied",
            "applied_at": applied_at,
            "updated_at": now.isoformat(),
            "analysis_id": analysis_id,
            "generation_id": generation_id,
            "description_source": description_source,
            "description_completeness": description_completeness,
            "full_description_available": description_completeness == "full",
            "capture_warning": capture_warning,
            "description": description,
            "job": job_details,
            "source_context": source_context,
            "generated_documents": generated_documents,
        }
        write_json_atomic(details_path, details)

        markdown = "\n".join(
            [
                f"# {_safe_text(posting.get('title'), 500) or 'Job description'}",
                "",
                "| Field | Value |",
                "| --- | --- |",
                f"| Company | {_markdown_table_value(posting.get('company'))} |",
                f"| Role | {_markdown_table_value(posting.get('title'))} |",
                f"| Location | {_markdown_table_value(posting.get('location'))} |",
                f"| Experience | {_markdown_table_value(posting.get('experience_text'))} |",
                f"| Employment type | {_markdown_table_value(posting.get('employment_type'))} |",
                f"| Workplace type | {_markdown_table_value(posting.get('workplace_type'))} |",
                f"| Requisition ID | {_markdown_table_value(posting.get('requisition_id'))} |",
                f"| Published | {_markdown_table_value(posting.get('published_at'))} |",
                f"| Official URL | {_markdown_table_value(posting.get('official_url'))} |",
                f"| Capture quality | {_markdown_table_value(description_completeness.replace('_', ' ').title())} |",
                f"| Capture source | {_markdown_table_value(description_source.replace('_', ' ').title())} |",
                "",
                *(
                    [f"> **Review note:** {capture_warning}", ""]
                    if capture_warning
                    else []
                ),
                "## Job description",
                "",
                description or "The public source did not provide description text.",
                "",
                (
                    "This private evidence file was saved after the user confirmed a manual "
                    "application. Eligibility, generated-document metadata, and application "
                    "state remain in Application_Details.json."
                ),
                "",
            ]
        )
        description_path = package_root / APPLICATION_JOB_DESCRIPTION_NAME
        description_path.write_text(markdown, encoding="utf-8")
        description_docx_path = package_root / APPLICATION_JOB_DESCRIPTION_DOCX_NAME
        self.job_description_builder(
            description_docx_path,
            posting=posting,
            description=description,
            completeness=description_completeness,
            description_source=description_source,
            capture_warning=capture_warning,
        )

        if not self._lock.acquire(blocking=False):
            raise JobIntelligenceError("Another job-intelligence action is already running.")
        try:
            package_files = []
            for kind, local_path, mime_type in (
                ("job_description_document", description_docx_path, DOCX_MIME_TYPE),
                ("job_description", description_path, MARKDOWN_MIME_TYPE),
                ("application_details", details_path, JSON_MIME_TYPE),
            ):
                uploaded = self.resume_library.upload_application_file(
                    local_path,
                    folder_id=folder_id,
                    folder_url=folder_url,
                    folder_path=folder_path,
                    mime_type=mime_type,
                )
                package_files.append(
                    {
                        "kind": kind,
                        "file_name": local_path.name,
                        "sha256": hashlib.sha256(local_path.read_bytes()).hexdigest(),
                        **uploaded,
                    }
                )
        finally:
            self._lock.release()

        return {
            "application_status": "applied",
            "applied_at": applied_at,
            "official_url": str(posting.get("official_url") or ""),
            "description_source": description_source,
            "description_completeness": description_completeness,
            "full_description_available": details["full_description_available"],
            "capture_warning": capture_warning,
            "folder_url": folder_url,
            "folder_path": folder_path,
            "files": package_files,
        }

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
