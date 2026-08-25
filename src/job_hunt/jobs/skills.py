"""Evidence-backed exact and equivalent job-skill matching.

This module intentionally uses a small, auditable vocabulary rather than embeddings or
another model call. Exact ATS coverage remains separate: equivalent evidence can justify
adding the employer's exact wording to a tailored copy, but it is not counted as an exact
resume keyword until that wording is actually present in the generated document.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping


_IGNORED_TOKENS = frozenset(
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

_SINGULAR = {
    "agents": "agent",
    "apis": "api",
    "databases": "database",
    "evaluations": "evaluation",
    "frameworks": "framework",
    "llms": "llm",
    "metrics": "metric",
    "models": "model",
    "pipelines": "pipeline",
    "services": "service",
    "systems": "system",
    "tools": "tool",
}

# One concept may have explicit product names as evidence. Matching a job label that
# contains a concept requires at least one corresponding alias in documented evidence.
_CONCEPT_ALIASES: dict[str, tuple[str, ...]] = {
    "ai_ml": (
        "artificial intelligence",
        "machine learning",
        "generative ai",
        "gen ai",
        "ai",
        "ml",
    ),
    "llm": (
        "large language model",
        "foundation model",
        "llm",
    ),
    "agent": (
        "ai agent",
        "agentic ai",
        "agentic system",
        "autonomous agent",
        "llm agent",
        "langgraph",
        "langchain",
        "agent",
    ),
    "agent_framework": (
        "agentic framework",
        "agent framework",
        "langgraph",
        "langchain",
        "crewai",
        "autogen",
    ),
    "rag": (
        "retrieval augmented generation",
        "retrieval augmented",
        "rag",
    ),
    "prompting": (
        "prompt engineering",
        "prompt design",
        "prompting",
        "prompt",
    ),
    "context_engineering": (
        "context engineering",
        "retrieval context",
        "prompt context",
        "context window",
        "context management",
        "prompt input",
    ),
    "tool_integration": (
        "tool integration",
        "tool calling",
        "function calling",
        "model context protocol",
        "fastmcp",
        "mcp",
    ),
    "evaluation": (
        "evaluation pipeline",
        "evaluation metric",
        "model evaluation",
        "model validation",
        "quality validation",
        "evaluation",
    ),
    "api": (
        "rest api",
        "web api",
        "api",
    ),
    "backend": (
        "backend service",
        "backend engineering",
        "server side",
        "microservice",
        "rest api",
    ),
    "data_pipeline": (
        "data pipeline",
        "data engineering",
        "etl",
        "data orchestration",
        "stream processing",
    ),
    "cloud": (
        "cloud infrastructure",
        "cloud platform",
        "cloud engineering",
        "kubernetes",
        "docker",
        "aws",
        "azure",
        "gcp",
        "cloud",
    ),
    "production": (
        "production engineering",
        "production system",
        "production deployment",
        "production support",
        "production",
    ),
    "ownership": (
        "end to end ownership",
        "technical ownership",
        "owned",
        "ownership",
    ),
    "engineering_discipline": (
        "engineering discipline",
        "software engineering practices",
        "code review",
        "ci cd",
        "automated testing",
        "quality engineering",
    ),
    "customer_collaboration": (
        "customer engineering collaboration",
        "customer collaboration",
        "client collaboration",
        "customer facing",
        "stakeholder collaboration",
    ),
    "open_source_model": (
        "open source model",
        "open weight model",
        "hugging face model",
    ),
    "closed_source_model": (
        "closed source model",
        "proprietary model",
        "hosted model api",
    ),
    "oauth": ("oauth", "oauth2"),
    "postgresql": ("postgresql", "postgres", "pgvector"),
    "mysql": ("mysql",),
    "redis": ("redis",),
}

_CATEGORY_CONCEPTS = {
    "AI & Machine Learning": {
        "ai_ml",
        "llm",
        "agent",
        "agent_framework",
        "rag",
        "prompting",
        "context_engineering",
        "evaluation",
        "open_source_model",
        "closed_source_model",
    },
    "Data & Databases": {"data_pipeline", "postgresql", "mysql", "redis"},
    "Backend & APIs": {"api", "backend", "oauth", "tool_integration"},
    "Cloud & DevOps": {"cloud", "production", "ownership", "engineering_discipline"},
}

_CATEGORY_PREFIX_ALIASES = {
    "AI & Machine Learning": {
        "ai",
        "artificial intelligence",
        "machine learning",
        "ml",
        "genai",
        "generative ai",
        "data science",
    },
    "Data & Databases": {
        "data",
        "database",
        "databases",
        "storage",
    },
    "Backend & APIs": {
        "backend",
        "api",
        "apis",
        "integration",
        "integrations",
        "web",
    },
    "Cloud & DevOps": {
        "cloud",
        "devops",
        "infrastructure",
        "deployment",
        "platform",
    },
    "Languages": {"language", "languages", "programming"},
    "Tools & Platforms": {"tool", "tools", "platforms", "other"},
}

_LANGUAGE_SKILLS = {
    "c",
    "c++",
    "c#",
    "go",
    "java",
    "javascript",
    "kotlin",
    "python",
    "r",
    "rust",
    "scala",
    "sql",
    "typescript",
}


def _tokens(value: object) -> list[str]:
    normalized = str(value or "").casefold().replace("&", " and ")
    raw = re.findall(r"[a-z0-9+#.]+", normalized)
    return [_SINGULAR.get(token, token) for token in raw]


def normalize_skill_text(value: object) -> str:
    return " ".join(_tokens(value))


def _contains_phrase(text_tokens: list[str], phrase: str) -> bool:
    phrase_tokens = _tokens(phrase)
    if not phrase_tokens or len(phrase_tokens) > len(text_tokens):
        return False
    width = len(phrase_tokens)
    return any(
        text_tokens[offset : offset + width] == phrase_tokens
        for offset in range(len(text_tokens) - width + 1)
    )


def _entry(value: object, index: int) -> dict[str, str] | None:
    if isinstance(value, Mapping):
        text = str(value.get("text") or "").strip()
        item_id = str(value.get("id") or f"evidence_{index}").strip()
        kind = str(value.get("kind") or "evidence").strip()
    else:
        text = str(value or "").strip()
        item_id = f"evidence_{index}"
        kind = "evidence"
    if not text:
        return None
    return {"id": item_id[:160], "text": text[:4000], "kind": kind[:80]}


def _prepared_evidence(values: Iterable[object]) -> list[dict[str, Any]]:
    result = []
    for index, value in enumerate(values or []):
        item = _entry(value, index)
        if item:
            result.append({**item, "tokens": _tokens(item["text"])})
    return result


def _concepts_and_leftovers(label: str) -> tuple[list[str], list[str]]:
    label_tokens = _tokens(label)
    concepts: list[str] = []
    covered_positions: set[int] = set()
    for concept, aliases in _CONCEPT_ALIASES.items():
        matched_positions: set[int] = set()
        for alias in aliases:
            alias_tokens = _tokens(alias)
            width = len(alias_tokens)
            for offset in range(max(0, len(label_tokens) - width + 1)):
                if label_tokens[offset : offset + width] == alias_tokens:
                    matched_positions.update(range(offset, offset + width))
        if matched_positions:
            concepts.append(concept)
            covered_positions.update(matched_positions)
    leftovers = [
        token
        for index, token in enumerate(label_tokens)
        if index not in covered_positions and token not in _IGNORED_TOKENS
    ]
    return concepts, leftovers


def _match_alternative(
    alternative: str,
    evidence: list[dict[str, Any]],
) -> dict[str, Any] | None:
    alternative_tokens = _tokens(alternative)
    for item in evidence:
        if _contains_phrase(item["tokens"], alternative):
            return {
                "match_type": "exact",
                "evidence_ids": [item["id"]],
                "evidence_kinds": [item["kind"]],
            }

    concepts, leftovers = _concepts_and_leftovers(alternative)
    evidence_ids: list[str] = []
    evidence_kinds: list[str] = []
    for concept in concepts:
        matching = [
            item
            for item in evidence
            if any(
                _contains_phrase(item["tokens"], alias)
                for alias in _CONCEPT_ALIASES[concept]
            )
        ]
        if not matching:
            return None
        for item in matching[:2]:
            if item["id"] not in evidence_ids:
                evidence_ids.append(item["id"])
                evidence_kinds.append(item["kind"])

    if leftovers:
        for token in leftovers:
            matching = [item for item in evidence if token in item["tokens"]]
            if not matching:
                return None
            item = matching[0]
            if item["id"] not in evidence_ids:
                evidence_ids.append(item["id"])
                evidence_kinds.append(item["kind"])

    if not concepts and not leftovers:
        return None
    if not evidence_ids and alternative_tokens:
        return None
    return {
        "match_type": "equivalent",
        "evidence_ids": evidence_ids,
        "evidence_kinds": evidence_kinds,
    }


def match_skill_to_evidence(
    label: object,
    evidence_items: Iterable[object],
) -> dict[str, Any]:
    """Return exact/equivalent documented support for one JD skill label."""

    skill = re.sub(r"\s+", " ", str(label or "").strip())[:160]
    evidence = _prepared_evidence(evidence_items)
    alternatives = [
        value.strip()
        for value in re.split(r"\s+or\s+", normalize_skill_text(skill))
        if value.strip()
    ] or [skill]
    for alternative in alternatives:
        matched = _match_alternative(alternative, evidence)
        if matched:
            return {"skill": skill, "matched": True, **matched}
    return {
        "skill": skill,
        "matched": False,
        "match_type": "",
        "evidence_ids": [],
        "evidence_kinds": [],
    }


def map_job_skills_to_evidence(
    skills: Iterable[object],
    evidence_items: Iterable[object],
) -> list[dict[str, Any]]:
    prepared = list(evidence_items or [])
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for skill in skills or []:
        key = normalize_skill_text(skill)
        if not key or key in seen:
            continue
        seen.add(key)
        matched = match_skill_to_evidence(skill, prepared)
        if matched["matched"]:
            # Whole-resume support may legitimately combine two evidence items (for
            # example, one documenting LLMs and another documenting agents). Sentence
            # rewrites are stricter: one item must independently support the full label.
            direct_ids: list[str] = []
            direct_kinds: list[str] = []
            for index, value in enumerate(prepared):
                item = _entry(value, index)
                if not item:
                    continue
                direct = match_skill_to_evidence(skill, [item])
                if direct["matched"] and item["id"] not in direct_ids:
                    direct_ids.append(item["id"])
                    direct_kinds.append(item["kind"])
            matched["direct_evidence_ids"] = direct_ids
            matched["direct_evidence_kinds"] = direct_kinds
            result.append(matched)
    return result


def resume_evidence_items(evidence: Mapping[str, Any]) -> list[dict[str, str]]:
    """Flatten contact-free resume/reference evidence into stable, attributable items."""

    result = [
        {
            "id": "resume_summary",
            "text": str(evidence.get("current_summary") or ""),
            "kind": "summary",
        }
    ]
    result.extend(
        {
            "id": str(item.get("id") or ""),
            "text": str(item.get("text") or ""),
            "kind": "skill",
        }
        for item in evidence.get("skills") or []
    )
    result.extend(
        {
            "id": str(item.get("id") or ""),
            "text": str(item.get("text") or ""),
            "kind": "experience_bullet",
        }
        for section in evidence.get("experience_sections") or []
        for item in section.get("bullets") or []
    )
    result.extend(
        {
            "id": str(item.get("id") or ""),
            "text": str(item.get("text") or ""),
            "kind": "reference",
        }
        for item in evidence.get("reference_points") or []
    )
    result.extend(
        {
            "id": str(item.get("id") or ""),
            "text": f"{item.get('skill') or ''}: {item.get('note') or ''}",
            "kind": "user_confirmed",
        }
        for item in evidence.get("user_confirmed_skill_evidence") or []
    )
    return [item for item in result if item["id"] and item["text"].strip()]


def _skill_concepts(skill: object) -> set[str]:
    concepts, _leftovers = _concepts_and_leftovers(str(skill or ""))
    return set(concepts)


def preferred_skill_category(skill: object) -> str:
    concepts = _skill_concepts(skill)
    for category, category_concepts in _CATEGORY_CONCEPTS.items():
        if concepts.intersection(category_concepts):
            return category
    tokens = set(_tokens(skill))
    if tokens.intersection(_LANGUAGE_SKILLS):
        return "Languages"
    return "Tools & Platforms"


def skill_placement(
    skill: object,
    skill_lines: Iterable[Mapping[str, Any]],
) -> dict[str, str]:
    """Choose a relevant existing skills sub-heading or a specific new heading."""

    category = preferred_skill_category(skill)
    aliases = _CATEGORY_PREFIX_ALIASES[category]
    for item in skill_lines or []:
        text = str(item.get("text") or "")
        prefix = text.split(":", 1)[0].strip()
        prefix_tokens = _tokens(prefix)
        if any(_contains_phrase(prefix_tokens, value) for value in aliases):
            return {
                "skill": re.sub(r"\s+", " ", str(skill or "").strip())[:120],
                "target_skill_id": str(item.get("id") or ""),
                "category": prefix,
            }
    return {
        "skill": re.sub(r"\s+", " ", str(skill or "").strip())[:120],
        "target_skill_id": "",
        "category": category,
    }
