"""Cost-aware official-employer job research using the OpenAI Responses API.

Only normalized job-alert facts are sent to the API. Gmail bodies, protected job-board
pages, resume contact details, and LinkedIn connection data stay outside this module.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import date
from math import ceil
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from job_hunt.enrichment import canonical_company, normalize_text
from job_hunt.experience import extract_experience_range


DEFAULT_OPENAI_MODEL = "gpt-5.6-luna"
MAX_ALERTS_PER_COMPANY_CALL = 8
MAX_CANDIDATES_PER_ALERT = 3
MAX_EXACT_DESCRIPTION_CHARS = 40_000

_BLOCKED_SOURCE_DOMAINS = {
    "adzuna.com",
    "bing.com",
    "duckduckgo.com",
    "glassdoor.com",
    "google.com",
    "indeed.com",
    "linkedin.com",
    "monster.com",
    "naukri.com",
    "rocketreach.co",
    "search.yahoo.com",
    "simplyhired.com",
    "ziprecruiter.com",
}
_TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
    "trk",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}
_ACTIVE_STATUSES = {"active", "closed", "filled", "inactive", "unknown"}
_MATCH_STATUSES = {
    "exact_candidate",
    "active_candidate",
    "active_related",
    "closed_reference",
}


RESEARCH_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "alert_record_id": {"type": "string"},
                    "candidates": {
                        "type": "array",
                        "maxItems": MAX_CANDIDATES_PER_ALERT,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "company": {"type": "string"},
                                "title": {"type": "string"},
                                "location": {"type": "string"},
                                "experience_text": {"type": "string"},
                                "experience_min": {"type": ["number", "null"]},
                                "experience_max": {"type": ["number", "null"]},
                                "workplace_type": {"type": "string"},
                                "employment_type": {"type": "string"},
                                "active_status": {
                                    "type": "string",
                                    "enum": sorted(_ACTIVE_STATUSES),
                                },
                                "requisition_id": {"type": "string"},
                                "published_at": {"type": "string"},
                                "official_url": {"type": "string"},
                                "description_summary": {"type": "string"},
                                "required_skills": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "preferred_skills": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "evidence_confidence": {
                                    "type": "string",
                                    "enum": ["high", "medium", "low"],
                                },
                                "source_notes": {"type": "string"},
                                "match_status": {
                                    "type": "string",
                                    "enum": sorted(_MATCH_STATUSES),
                                },
                                "match_score": {
                                    "type": "integer",
                                    "minimum": 0,
                                    "maximum": 100,
                                },
                                "match_reason": {"type": "string"},
                            },
                            "required": [
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
                                "evidence_confidence",
                                "source_notes",
                                "match_status",
                                "match_score",
                                "match_reason",
                            ],
                        },
                    },
                },
                "required": ["alert_record_id", "candidates"],
            },
        }
    },
    "required": ["results"],
}

SKILL_EVIDENCE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "label": {"type": "string"},
        "evidence": {"type": "string"},
    },
    "required": ["label", "evidence"],
}

EXACT_POSTING_EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "description_summary": {"type": "string"},
        "experience_evidence": {"type": "string"},
        "required_skills": {
            "type": "array",
            "maxItems": 20,
            "items": SKILL_EVIDENCE_SCHEMA,
        },
        "preferred_skills": {
            "type": "array",
            "maxItems": 12,
            "items": SKILL_EVIDENCE_SCHEMA,
        },
    },
    "required": [
        "description_summary",
        "experience_evidence",
        "required_skills",
        "preferred_skills",
    ],
}


SYSTEM_INSTRUCTIONS = """You research current public job postings for a personal job tracker.

For each supplied Gmail-alert record, use web search to find zero to three plausible current
postings on the employer's own careers site or the employer's official ATS tenant. Prefer the
exact company, title, and location; closely related current official openings may be included
when clearly labelled active_related.

Safety and evidence rules:
- Use only publicly accessible employer or official ATS pages.
- Never use, open, or return LinkedIn, Naukri, aggregator, people-search, or search-result URLs.
- Do not bypass login, bot protection, robots controls, or other access controls.
- Do not invent a job, requisition, date, experience range, skill, description, or status.
- Return an empty candidates list when no public official posting can be verified.
- Mark closed or inactive evidence as closed_reference; never call it active.
- Keep description_summary to three to six concise paraphrased sentences.
- The official match score measures alert-to-posting identity only, not resume eligibility.
- Empty strings, empty arrays, or null numeric ranges are required when evidence is absent.
"""

EXACT_POSTING_INSTRUCTIONS = """You extract structured facts from one exact official job
description supplied by the application. Do not search for or mention another job.

Evidence rules:
- Use only the supplied exact_description.
- Every required or preferred skill must include a short verbatim evidence fragment that occurs
  in exact_description. Do not infer adjacent technologies, tools, databases, frameworks, or
  credentials.
- Treat skills in explicit requirements/qualifications as required. Treat only explicitly
  optional, preferred, or bonus qualifications as preferred.
- experience_evidence must be a verbatim fragment containing an explicitly stated numeric years
  requirement, or an empty string when none is stated.
- description_summary must be a concise three-to-six-sentence paraphrase of this exact role.
- Empty arrays are correct when reliable skill evidence is absent.
"""

EXACT_ONLY_RESEARCH_INSTRUCTIONS = """

Exact-job policy for this request:
- An official_url_hint identifies the selected job. Return only that exact URL or a URL carrying
  the same provider job identifier.
- Do not return a related, similar, replacement, or alternative opening.
- If the exact posting cannot be verified, return an empty candidates list.
- Never use match_status active_related for this request.
"""


class OpenAIResearchError(RuntimeError):
    """A sanitized official-job research failure suitable for the UI boundary."""


def _require_openai_client():
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - dependency boundary
        raise RuntimeError("The OpenAI SDK is not installed. Run `pip install -e .`.") from exc
    return OpenAI


def _chunks(values: list[dict], size: int) -> Iterable[list[dict]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _host_is_blocked(hostname: str) -> bool:
    hostname = hostname.casefold().removeprefix("www.")
    return any(
        hostname == blocked or hostname.endswith("." + blocked)
        for blocked in _BLOCKED_SOURCE_DOMAINS
    )


def _clean_official_url(value: object) -> str:
    raw = str(value or "").strip()
    try:
        parts = urlsplit(raw)
    except ValueError:
        return ""
    hostname = (parts.hostname or "").casefold()
    if (
        parts.scheme not in {"http", "https"}
        or not hostname
        or parts.username
        or parts.password
        or _host_is_blocked(hostname)
    ):
        return ""
    query = urlencode(
        [
            (key, item)
            for key, item in parse_qsl(parts.query, keep_blank_values=True)
            if key.casefold() not in _TRACKING_QUERY_KEYS
        ],
        doseq=True,
    )
    return urlunsplit(("https", parts.netloc, parts.path, query, ""))


def _same_company(expected: object, actual: object) -> bool:
    left = normalize_text(canonical_company(expected))
    right = normalize_text(canonical_company(actual))
    if not left or not right:
        return False
    if left == right:
        return True
    return min(len(left), len(right)) >= 5 and (left in right or right in left)


def stable_official_job_id(url: str) -> str:
    digest = hashlib.sha256(url.casefold().encode("utf-8")).hexdigest()[:16]
    return f"official_{digest}"


def _stable_official_job_id(url: str) -> str:
    """Backward-compatible internal alias."""

    return stable_official_job_id(url)


def _safe_list(value: object, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    seen = set()
    for item in value:
        text = str(item or "").strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _job_path_identifier(value: object) -> str:
    try:
        parts = [part for part in urlsplit(str(value or "")).path.split("/") if part]
    except ValueError:
        return ""
    uuid_pattern = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        re.IGNORECASE,
    )
    for part in parts:
        if uuid_pattern.fullmatch(part):
            return part.casefold()
    ignored = {"apply", "application", "job", "jobs", "careers"}
    for part in reversed(parts):
        normalized = part.casefold()
        if normalized not in ignored:
            return normalized
    return ""


def _same_job_identity(expected: object, actual: object) -> bool:
    left = _clean_official_url(expected)
    right = _clean_official_url(actual)
    if not left or not right:
        return False
    if left.casefold().rstrip("/") == right.casefold().rstrip("/"):
        return True
    left_id = _job_path_identifier(left)
    right_id = _job_path_identifier(right)
    return bool(left_id and right_id and left_id == right_id)


def _normalized_grounding(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def _evidence_occurs(evidence: object, description: object) -> bool:
    needle = _normalized_grounding(evidence)
    haystack = _normalized_grounding(description)
    return len(needle) >= 2 and needle in haystack


def _grounded_skills(
    values: object,
    description: str,
    limit: int,
) -> tuple[list[str], dict[str, str]]:
    if not isinstance(values, list):
        return [], {}
    labels: list[str] = []
    evidence_by_label: dict[str, str] = {}
    seen: set[str] = set()
    for value in values:
        item = value if isinstance(value, Mapping) else {}
        label = str(item.get("label") or "").strip()[:120]
        evidence = str(item.get("evidence") or "").strip()[:500]
        key = normalize_text(label)
        if not label or not key or key in seen or not _evidence_occurs(evidence, description):
            continue
        seen.add(key)
        labels.append(label)
        evidence_by_label[label] = evidence
        if len(labels) >= limit:
            break
    return labels, evidence_by_label


def _fallback_exact_summary(description: str) -> str:
    sentences = [
        item.strip()
        for item in re.split(r"(?<=[.!?])\s+", str(description or "").strip())
        if item.strip()
    ]
    return " ".join(sentences[:4])[:1200]


def _numeric_or_none(value: object):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalized_alert(job: dict, *, exact_only: bool = False) -> dict[str, object]:
    """Return the only alert fields that may leave the local application."""

    normalized = {
        "alert_record_id": str(job.get("job_record_id") or "").strip(),
        "company": str(job.get("company") or "").strip(),
        "title": str(job.get("title") or "").strip(),
        "location": str(job.get("location") or "").strip(),
        "experience_text": str(job.get("experience_text") or "").strip(),
    }
    official_url_hint = _clean_official_url(job.get("official_url"))
    if official_url_hint:
        normalized["official_url_hint"] = official_url_hint
    normalized["match_policy"] = "exact_only" if exact_only else "related_allowed"
    return normalized


def _alert_fingerprint(alert: dict) -> str:
    stable_fields = {
        key: alert.get(key)
        for key in (
            "company",
            "title",
            "location",
            "experience_text",
            "official_url_hint",
            "match_policy",
        )
    }
    serialized = json.dumps(
        stable_fields,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def pending_research_jobs(
    jobs: list[dict],
    existing_research: dict | None = None,
) -> list[dict]:
    """Return current jobs whose normalized facts are not in the trusted cache."""

    existing = dict(existing_research or {})
    stored_fingerprints = {
        str(alert_id): str(fingerprint)
        for alert_id, fingerprint in (existing.get("checked_alert_fingerprints") or {}).items()
        if fingerprint
    }
    pending_by_id = {}
    for job in jobs:
        alert = _normalized_alert(job)
        alert_id = str(alert.get("alert_record_id") or "")
        if not alert_id or alert_id in pending_by_id:
            continue
        fingerprint = _alert_fingerprint(alert)
        if stored_fingerprints.get(alert_id) == fingerprint:
            continue
        pending_by_id[alert_id] = dict(job)

    return sorted(
        pending_by_id.values(),
        key=lambda item: (
            normalize_text(canonical_company(item.get("company"))),
            normalize_text(item.get("title")),
            str(item.get("job_record_id") or ""),
        ),
    )


class OfficialJobResearcher:
    """Research only new alert records and merge them into a reusable private cache."""

    def __init__(self, api_key: str, model: str = DEFAULT_OPENAI_MODEL, client=None):
        if not str(api_key or "").strip() and client is None:
            raise ValueError("OPENAI_API_KEY is not configured.")
        self.model = str(model or DEFAULT_OPENAI_MODEL).strip()
        if client is None:
            OpenAI = _require_openai_client()
            client = OpenAI(api_key=str(api_key).strip())
        self.client = client

    def _research_company_batch(self, alerts: list[dict], *, exact_only: bool = False) -> dict:
        company = str(alerts[0].get("company") or "unknown employer")
        prompt = (
            f"Research date: {date.today().isoformat()}\n"
            f"Employer batch: {company}\n"
            "Return one results item for every supplied alert_record_id.\n\n"
            + json.dumps(alerts, ensure_ascii=False, indent=2)
        )
        try:
            response = self.client.responses.create(
                model=self.model,
                input=[
                    {
                        "role": "system",
                        "content": SYSTEM_INSTRUCTIONS
                        + (EXACT_ONLY_RESEARCH_INSTRUCTIONS if exact_only else ""),
                    },
                    {"role": "user", "content": prompt},
                ],
                tools=[{"type": "web_search"}],
                reasoning={"effort": "low"},
                text={
                    "verbosity": "low",
                    "format": {
                        "type": "json_schema",
                        "name": "official_job_research",
                        "strict": True,
                        "schema": RESEARCH_RESPONSE_SCHEMA,
                    },
                },
                store=False,
            )
            output_text = str(getattr(response, "output_text", "") or "").strip()
            if not output_text:
                raise ValueError("The model returned no structured output.")
            return json.loads(output_text)
        except Exception as exc:
            raise OpenAIResearchError(
                f"Official-job research failed for {company} ({type(exc).__name__})."
            ) from exc

    def extract_exact_posting(
        self,
        job: Mapping[str, Any],
        exact_source: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Extract only evidence grounded in one exact ATS description."""

        description = str(exact_source.get("description") or "").strip()
        if not description:
            raise OpenAIResearchError("The exact official posting has no public description.")
        description = description[:MAX_EXACT_DESCRIPTION_CHARS]
        prompt = json.dumps(
            {
                "company": str(job.get("company") or "").strip(),
                "exact_title": str(exact_source.get("title") or "").strip(),
                "exact_location": str(exact_source.get("location") or "").strip(),
                "exact_description": description,
            },
            ensure_ascii=False,
            indent=2,
        )
        try:
            response = self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": EXACT_POSTING_INSTRUCTIONS},
                    {"role": "user", "content": prompt},
                ],
                reasoning={"effort": "low"},
                text={
                    "verbosity": "low",
                    "format": {
                        "type": "json_schema",
                        "name": "exact_official_job_extraction",
                        "strict": True,
                        "schema": EXACT_POSTING_EXTRACTION_SCHEMA,
                    },
                },
                store=False,
            )
            output_text = str(getattr(response, "output_text", "") or "").strip()
            if not output_text:
                raise ValueError("The model returned no exact-job extraction.")
            raw = json.loads(output_text)
        except Exception as exc:
            raise OpenAIResearchError(
                f"Exact official-job extraction failed ({type(exc).__name__})."
            ) from exc

        required, required_evidence = _grounded_skills(
            raw.get("required_skills"), description, 20
        )
        preferred, preferred_evidence = _grounded_skills(
            raw.get("preferred_skills"), description, 12
        )
        experience_text = ""
        experience_min = None
        experience_max = None
        experience_evidence = str(raw.get("experience_evidence") or "").strip()[:500]
        if _evidence_occurs(experience_evidence, description):
            experience = extract_experience_range(experience_evidence)
            if experience is not None:
                experience_text = experience_evidence
                experience_min = experience.minimum
                experience_max = experience.maximum

        summary = str(raw.get("description_summary") or "").strip()[:1200]
        if not summary:
            summary = _fallback_exact_summary(description)
        official_url = _clean_official_url(exact_source.get("official_url"))
        if not official_url:
            raise OpenAIResearchError("The exact official posting URL is invalid.")
        board = str(exact_source.get("board") or "").strip()
        return {
            "official_job_id": stable_official_job_id(official_url),
            "company": canonical_company(job.get("company")),
            "title": str(exact_source.get("title") or "").strip(),
            "location": str(exact_source.get("location") or "").strip(),
            "experience_text": experience_text,
            "experience_min": experience_min,
            "experience_max": experience_max,
            "workplace_type": str(exact_source.get("workplace_type") or "").strip(),
            "employment_type": str(exact_source.get("employment_type") or "").strip(),
            "active_status": "active",
            "requisition_id": str(exact_source.get("external_job_id") or "").strip(),
            "published_at": str(exact_source.get("published_at") or "").strip(),
            "official_url": official_url,
            "description_summary": summary,
            "required_skills": required,
            "preferred_skills": preferred,
            "required_skill_evidence": required_evidence,
            "preferred_skill_evidence": preferred_evidence,
            "evidence_confidence": "high",
            "source_notes": (
                f"Exact job ID matched in Ashby's official public job-postings feed"
                f"{f' for board {board}' if board else ''}. Skills without exact-JD evidence "
                "were discarded."
            ),
            "exact_source_fingerprint": str(
                exact_source.get("source_fingerprint") or ""
            ).strip(),
        }

    def research(
        self,
        jobs: list[dict],
        existing_research: dict | None = None,
        *,
        refresh_existing: bool = False,
        max_new_alerts: int | None = None,
        progress: Callable[[int, int, str], None] | None = None,
        exact_only: bool = False,
    ) -> dict:
        """Research missing alerts and return a merged, validated cache document."""

        existing = dict(existing_research or {})
        postings_by_id = {
            str(item.get("official_job_id")): dict(item)
            for item in existing.get("postings") or []
            if item.get("official_job_id")
        }
        matches = {
            str(alert_id): [dict(item) for item in rows]
            for alert_id, rows in (existing.get("matches") or {}).items()
        }
        alerts = [_normalized_alert(job, exact_only=exact_only) for job in jobs]
        alerts = [item for item in alerts if item["alert_record_id"]]
        alerts_by_id = {str(item["alert_record_id"]): item for item in alerts}
        current_fingerprints = {
            alert_id: _alert_fingerprint(alert) for alert_id, alert in alerts_by_id.items()
        }
        stored_fingerprints = {
            str(alert_id): str(fingerprint)
            for alert_id, fingerprint in (existing.get("checked_alert_fingerprints") or {}).items()
            if fingerprint
        }
        trusted_checked = {
            alert_id
            for alert_id, fingerprint in current_fingerprints.items()
            if stored_fingerprints.get(alert_id) == fingerprint
        }
        checked = set(stored_fingerprints) | set(matches)
        initially_checked = set(trusted_checked)

        if refresh_existing:
            all_pending = list(alerts)
        else:
            all_pending = [
                item for item in alerts if item["alert_record_id"] not in trusted_checked
            ]
        pending = list(all_pending)
        if max_new_alerts is not None:
            pending = pending[: max(0, int(max_new_alerts))]
        waiting_for_future_run = len(all_pending) - len(pending)

        searchable = []
        checked_without_search = 0
        for alert in pending:
            alert_id = str(alert["alert_record_id"])
            if not alert.get("company") or not alert.get("title"):
                matches.pop(alert_id, None)
                checked.add(alert_id)
                stored_fingerprints[alert_id] = current_fingerprints[alert_id]
                checked_without_search += 1
                continue
            searchable.append(alert)

        grouped: dict[str, list[dict]] = defaultdict(list)
        for alert in searchable:
            company_key = normalize_text(canonical_company(alert.get("company")))
            grouped[company_key or str(alert["alert_record_id"])].append(alert)

        batches = [
            batch
            for company_alerts in grouped.values()
            for batch in _chunks(company_alerts, MAX_ALERTS_PER_COMPANY_CALL)
        ]
        submitted_ids = {str(item["alert_record_id"]) for item in searchable}
        for alert_id in submitted_ids:
            matches.pop(alert_id, None)

        for completed, batch in enumerate(batches, start=1):
            raw = self._research_company_batch(batch, exact_only=exact_only)
            batch_by_id = {str(item["alert_record_id"]): item for item in batch}
            seen_ids = set()
            for result in raw.get("results") or []:
                alert_id = str(result.get("alert_record_id") or "")
                alert = batch_by_id.get(alert_id)
                if alert is None or alert_id in seen_ids:
                    continue
                seen_ids.add(alert_id)
                mapping_rows = []
                for candidate in (result.get("candidates") or [])[:MAX_CANDIDATES_PER_ALERT]:
                    if not _same_company(alert.get("company"), candidate.get("company")):
                        continue
                    official_url = _clean_official_url(candidate.get("official_url"))
                    if not official_url:
                        continue
                    expected_url = _clean_official_url(alert.get("official_url_hint"))
                    if exact_only and (
                        not expected_url or not _same_job_identity(expected_url, official_url)
                    ):
                        continue
                    if exact_only:
                        official_url = expected_url
                    official_id = _stable_official_job_id(official_url)
                    active_status = str(candidate.get("active_status") or "unknown")
                    if active_status not in _ACTIVE_STATUSES:
                        active_status = "unknown"
                    match_status = str(candidate.get("match_status") or "active_candidate")
                    if match_status not in _MATCH_STATUSES:
                        match_status = "active_candidate"
                    if active_status in {"closed", "filled", "inactive"}:
                        match_status = "closed_reference"
                    try:
                        match_score = max(0, min(100, int(candidate.get("match_score") or 0)))
                    except (TypeError, ValueError):
                        match_score = 0
                    if exact_only and match_status != "closed_reference":
                        match_status = "exact_candidate"
                        match_score = 100

                    posting = {
                        "official_job_id": official_id,
                        "company": canonical_company(candidate.get("company")),
                        "title": str(candidate.get("title") or "").strip(),
                        "location": str(candidate.get("location") or "").strip(),
                        "experience_text": str(candidate.get("experience_text") or "").strip(),
                        "experience_min": _numeric_or_none(candidate.get("experience_min")),
                        "experience_max": _numeric_or_none(candidate.get("experience_max")),
                        "workplace_type": str(candidate.get("workplace_type") or "").strip(),
                        "employment_type": str(candidate.get("employment_type") or "").strip(),
                        "active_status": active_status,
                        "requisition_id": str(candidate.get("requisition_id") or "").strip(),
                        "published_at": str(candidate.get("published_at") or "").strip(),
                        "official_url": official_url,
                        "description_summary": str(
                            candidate.get("description_summary") or ""
                        ).strip(),
                        "required_skills": _safe_list(candidate.get("required_skills"), 20),
                        "preferred_skills": _safe_list(candidate.get("preferred_skills"), 12),
                        "evidence_confidence": (
                            str(candidate.get("evidence_confidence") or "low")
                            if str(candidate.get("evidence_confidence") or "low")
                            in {"high", "medium", "low"}
                            else "low"
                        ),
                        "source_notes": str(candidate.get("source_notes") or "").strip(),
                    }
                    postings_by_id[official_id] = posting
                    mapping_rows.append(
                        {
                            "official_job_id": official_id,
                            "match_status": match_status,
                            "match_score": match_score,
                            "match_reason": (
                                "Exact provider job identifier matched the selected official URL."
                                if exact_only
                                else str(candidate.get("match_reason") or "").strip()
                            ),
                        }
                    )
                if mapping_rows:
                    matches[alert_id] = sorted(
                        mapping_rows,
                        key=lambda item: -int(item.get("match_score") or 0),
                    )
                checked.add(alert_id)

            # A successful structured response with an omitted/empty result is still a check.
            for alert_id in batch_by_id:
                checked.add(alert_id)
                stored_fingerprints[alert_id] = current_fingerprints[alert_id]
            if progress:
                progress(completed, len(batches), str(batch[0].get("company") or ""))

        research_performed = bool(batches)
        verified_at = (
            date.today().isoformat()
            if research_performed
            else str(existing.get("verified_at") or "")
        )
        current_ids = set(alerts_by_id)
        reused = 0 if refresh_existing else len(current_ids.intersection(initially_checked))
        return {
            "verified_at": verified_at,
            "research_model": self.model,
            "checked_alert_ids": sorted(checked),
            "checked_alert_fingerprints": dict(sorted(stored_fingerprints.items())),
            "postings": sorted(
                postings_by_id.values(),
                key=lambda item: (
                    normalize_text(item.get("company")),
                    normalize_text(item.get("title")),
                    item.get("official_url") or "",
                ),
            ),
            "matches": dict(sorted(matches.items())),
            "research_stats": {
                "current_alerts": len(alerts),
                "alerts_submitted": len(submitted_ids),
                "alerts_checked_without_search": checked_without_search,
                "api_calls": len(batches),
                "alerts_reused_from_cache": reused,
                "alerts_waiting_for_future_run": waiting_for_future_run,
            },
        }

    def research_in_batches(
        self,
        jobs: list[dict],
        existing_research: dict | None = None,
        *,
        refresh_existing: bool = False,
        batch_size: int = 10,
        max_new_alerts: int | None = None,
        progress: Callable[[int, int, int, int, str], None] | None = None,
        checkpoint: Callable[[dict, int, int], None] | None = None,
    ) -> dict:
        """Research a backlog in resumable batches and checkpoint each completed batch.

        ``batch_size`` controls the durable checkpoint interval. Individual API requests
        remain grouped by company and bounded by ``MAX_ALERTS_PER_COMPANY_CALL``.
        """

        try:
            batch_size = int(batch_size)
        except (TypeError, ValueError) as exc:
            raise ValueError("Research batch size must be a whole number.") from exc
        if batch_size < 1:
            raise ValueError("Research batch size must be at least 1.")

        current = dict(existing_research or {})
        current_jobs_by_id = {}
        for job in jobs:
            alert_id = str(_normalized_alert(job).get("alert_record_id") or "")
            if alert_id and alert_id not in current_jobs_by_id:
                current_jobs_by_id[alert_id] = dict(job)
        valid_current_ids = set(current_jobs_by_id)
        if refresh_existing:
            pending = list(current_jobs_by_id.values())
            pending.sort(
                key=lambda item: (
                    normalize_text(canonical_company(item.get("company"))),
                    normalize_text(item.get("title")),
                    str(item.get("job_record_id") or ""),
                )
            )
        else:
            pending = pending_research_jobs(jobs, current)

        pending_before = len(pending)
        if max_new_alerts is not None:
            try:
                maximum = max(0, int(max_new_alerts))
            except (TypeError, ValueError) as exc:
                raise ValueError("Maximum research alerts must be a whole number.") from exc
            pending = pending[:maximum]

        target_count = len(pending)
        total_batches = ceil(target_count / batch_size) if target_count else 0
        completed_alerts = 0
        total_api_calls = 0
        total_submitted = 0
        total_checked_without_search = 0
        initially_reused = 0 if refresh_existing else len(valid_current_ids) - pending_before

        def apply_run_stats(completed_batches: int) -> None:
            current["research_stats"] = {
                "current_alerts": len(valid_current_ids),
                "alerts_pending_before_run": pending_before,
                "alerts_targeted_this_run": target_count,
                "alerts_processed_this_run": completed_alerts,
                "alerts_submitted": total_submitted,
                "alerts_checked_without_search": total_checked_without_search,
                "api_calls": total_api_calls,
                "alerts_reused_from_cache": max(0, initially_reused),
                "alerts_waiting_for_future_run": max(0, pending_before - completed_alerts),
                "checkpoint_batches_completed": completed_batches,
                "checkpoint_batches_total": total_batches,
                "checkpoint_batch_size": batch_size,
            }

        if not pending:
            current = self.research(
                jobs,
                current,
                refresh_existing=refresh_existing,
                max_new_alerts=0,
            )
            apply_run_stats(0)
            return current

        for batch_number, batch in enumerate(_chunks(pending, batch_size), start=1):

            def report_company_progress(_completed, _total, company):
                if progress:
                    progress(
                        batch_number - 1,
                        total_batches,
                        completed_alerts,
                        target_count,
                        company,
                    )

            current = self.research(
                batch,
                current,
                refresh_existing=refresh_existing,
                progress=report_company_progress,
            )
            batch_stats = current.get("research_stats") or {}
            total_api_calls += int(batch_stats.get("api_calls") or 0)
            total_submitted += int(batch_stats.get("alerts_submitted") or 0)
            total_checked_without_search += int(
                batch_stats.get("alerts_checked_without_search") or 0
            )
            completed_alerts += len(batch)
            apply_run_stats(batch_number)
            if checkpoint:
                checkpoint(current, batch_number, total_batches)
            if progress:
                progress(
                    batch_number,
                    total_batches,
                    completed_alerts,
                    target_count,
                    "",
                )

        return current
