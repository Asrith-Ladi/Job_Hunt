"""Privacy-safe profile-review outreach from the offline LinkedIn export."""

from __future__ import annotations

import hashlib
import re
import threading
from pathlib import Path
from typing import Any

from job_hunt.jobs.enrichment import Connection, normalize_text
from job_hunt.network.referrals import (
    RegistryConnectionRecord,
    load_registry_connection_records,
)


DEFAULT_TARGET_ROLES = "AI Engineer, ML Engineer, and Generative AI Engineer"
MAX_TARGET_ROLES_LENGTH = 200

_RECRUITING = re.compile(
    r"\b(recruit|talent acquisition|human resources|people partner|hr business|hiring)\b",
    re.IGNORECASE,
)
_AI_ML = re.compile(
    r"\b(ai|artificial intelligence|machine learning|ml|gen ai|generative ai|genai|"
    r"llm|deep learning|nlp|natural language|computer vision|data scientist)\b",
    re.IGNORECASE,
)
_TECHNICAL = re.compile(
    r"\b(software|engineering|engineer|developer|data|analytics|cloud|platform|"
    r"technology|technical|architect|devops|python)\b",
    re.IGNORECASE,
)
_LEADERSHIP = re.compile(
    r"\b(manager|director|head|chief|vice president|vp|leader|lead|principal|staff|"
    r"architect)\b",
    re.IGNORECASE,
)
_SENIOR = re.compile(
    r"\b(senior|sr|principal|staff|lead|architect|manager|director|head|vp)\b",
    re.IGNORECASE,
)


def profile_review_message(connection: Connection, target_roles: str) -> str:
    """Personalize the user-approved profile-review template."""

    roles = " ".join(str(target_roles or "").split())[:MAX_TARGET_ROLES_LENGTH]
    roles = roles or DEFAULT_TARGET_ROLES
    return (
        f"Hi {connection.first_name}, hope you're doing well.\n\n"
        f"I'm currently preparing for {roles} opportunities and trying to understand "
        "where I currently stand compared with industry expectations.\n\n"
        "Since you're working in this area, I wanted to ask whether you would be "
        "comfortable reviewing my resume and sharing a few honest suggestions. I'm "
        "mainly looking for feedback on:\n\n"
        "• How my profile is positioned for AI/ML roles\n"
        "• Technical areas or projects I should strengthen\n"
        "• Any improvements needed in my job-search approach\n\n"
        "Even two or three points from your experience would be very helpful. I can "
        "share my resume here if that's okay with you."
    )


def connection_review_relevance(connection: Connection) -> dict[str, Any]:
    """Rank technical reviewers without implying willingness or relationship strength."""

    position = connection.position
    is_recruiting = bool(_RECRUITING.search(position))
    is_ai_ml = bool(_AI_ML.search(position))
    is_technical = bool(_TECHNICAL.search(position))
    is_leadership = bool(_LEADERSHIP.search(position))
    is_senior = bool(_SENIOR.search(position))

    if is_recruiting:
        score = 10
        category = "Recruiting / HR"
        reason = "Recruiting contact; not prioritized for technical profile feedback."
    elif is_ai_ml and is_leadership:
        score = 100
        category = "AI/ML leadership"
        reason = "AI/ML leader who may offer role-level and technical feedback."
    elif is_ai_ml:
        score = 85 if is_senior else 78
        category = "AI/ML practitioner"
        reason = "Works directly in AI/ML and may offer relevant technical feedback."
    elif is_technical and is_leadership:
        score = 75
        category = "Technical leadership"
        reason = "Technical manager or leader with relevant hiring and growth perspective."
    elif is_technical and is_senior:
        score = 65
        category = "Senior technical"
        reason = "Senior technical professional who may offer useful profile feedback."
    elif is_technical:
        score = 45
        category = "Technical practitioner"
        reason = "Technical connection; relevance to AI/ML should be reviewed manually."
    elif is_leadership:
        score = 30
        category = "Other leadership"
        reason = "Leadership role, but direct AI/ML relevance is not established."
    else:
        score = 0
        category = "Other"
        reason = "No clear AI/ML or technical-review signal in the exported role."

    return {
        "relevance_score": score,
        "category": category,
        "recommended": score >= 65,
        "leadership": is_leadership and not is_recruiting,
        "relevance_reason": reason,
    }


def _connection_id(record: RegistryConnectionRecord) -> str:
    if record.linkedin_url:
        identity = f"linkedin|{record.linkedin_url}"
    elif record.email_address:
        identity = f"email|{record.email_address}"
    else:
        identity = "|".join(
            (
                "snapshot",
                record.full_name,
                record.current_company,
                record.current_position,
                record.connected_on,
            )
        )
    value = identity.casefold().encode("utf-8")
    return hashlib.sha256(value).hexdigest()[:20]


class NetworkReviewService:
    """Read and filter the local connection snapshot for the React UI."""

    def __init__(self, registry_path: Path) -> None:
        self.registry_path = Path(registry_path)
        self._cache_signature: tuple[int, int] | None = None
        self._cache: list[tuple[RegistryConnectionRecord, dict[str, Any]]] = []
        self._cache_lock = threading.Lock()

    def _profiles(self) -> list[tuple[RegistryConnectionRecord, dict[str, Any]]]:
        if not self.registry_path.is_file():
            raise FileNotFoundError("The LinkedIn connection registry is unavailable.")
        stat = self.registry_path.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
        with self._cache_lock:
            if signature != self._cache_signature:
                connections = load_registry_connection_records(
                    self.registry_path,
                    include_email=True,
                )
                self._cache = [
                    (record, connection_review_relevance(record.as_connection()))
                    for record in connections
                ]
                self._cache.sort(
                    key=lambda item: (
                        -int(item[1]["relevance_score"]),
                        normalize_text(item[0].current_position),
                        normalize_text(item[0].full_name),
                    )
                )
                self._cache_signature = signature
            return list(self._cache)

    def search(
        self,
        *,
        query: str = "",
        category: str = "",
        recommended_only: bool = True,
        leadership_only: bool = False,
        target_roles: str = DEFAULT_TARGET_ROLES,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        profiles = self._profiles()
        all_count = len(profiles)
        profile_link_count = sum(bool(record.linkedin_url) for record, _ in profiles)
        email_count = sum(bool(record.email_address) for record, _ in profiles)
        recommended_count = sum(bool(metadata["recommended"]) for _, metadata in profiles)
        leadership_count = sum(bool(metadata["leadership"]) for _, metadata in profiles)
        categories = sorted({str(metadata["category"]) for _, metadata in profiles})

        needle = normalize_text(query)
        selected: list[tuple[RegistryConnectionRecord, dict[str, Any]]] = []
        for record, metadata in profiles:
            if recommended_only and not metadata["recommended"]:
                continue
            if leadership_only and not metadata["leadership"]:
                continue
            if category and metadata["category"] != category:
                continue
            if needle:
                haystack = normalize_text(
                    " ".join(
                        (
                            record.full_name,
                            record.current_company,
                            record.current_position,
                            record.registry_company,
                            record.registry_category,
                            record.email_address,
                        )
                    )
                )
                if needle not in haystack:
                    continue
            selected.append((record, metadata))

        offset = max(0, int(offset))
        limit = min(200, max(1, int(limit)))
        page = selected[offset : offset + limit]
        rows = []
        for record, metadata in page:
            connection = record.as_connection()
            rows.append(
                {
                    "connection_id": _connection_id(record),
                    "name": record.full_name,
                    "first_name": record.first_name,
                    "current_company": record.current_company,
                    "company": record.current_company or record.registry_company,
                    "position": record.current_position,
                    "email_address": record.email_address,
                    "linkedin_profile": record.linkedin_url,
                    "connected_on": record.connected_on,
                    "registry_company": record.registry_company,
                    "registry_category": record.registry_category,
                    "referral_status": record.referral_status,
                    "match_method": record.match_method,
                    "official_careers_page": record.official_careers_page,
                    "direct_job_portal": record.direct_job_portal,
                    **metadata,
                    "profile_review_message": profile_review_message(
                        connection,
                        target_roles,
                    ),
                }
            )

        return {
            "rows": rows,
            "total_matching": len(selected),
            "offset": offset,
            "limit": limit,
            "all_connections": all_count,
            "all_profiles": profile_link_count,
            "email_connections": email_count,
            "recommended_profiles": recommended_count,
            "leadership_profiles": leadership_count,
            "categories": categories,
            "target_roles": " ".join(str(target_roles or "").split()) or DEFAULT_TARGET_ROLES,
            "source": "offline_linkedin_export",
        }
