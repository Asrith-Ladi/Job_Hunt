"""Deterministic enrichment helpers for the personal production tracker.

The module deliberately keeps official-job matching separate from resume eligibility.
An employer/title/location match answers "is this probably the same opening?" while an
eligibility score answers "how well does the documented resume fit this posting?".
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from itertools import islice
from pathlib import Path


@dataclass(frozen=True)
class ResumeProfile:
    years_experience: float
    skills: frozenset[str]
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class Connection:
    first_name: str
    last_name: str
    linkedin_url: str
    company: str
    position: str
    connected_on: str

    @property
    def full_name(self) -> str:
        return " ".join(part for part in (self.first_name, self.last_name) if part).strip()


def personal_resume_profile() -> ResumeProfile:
    """Return the contact-free evidence previously verified from the user's resume."""

    return ResumeProfile(
        years_experience=5.8,
        skills=frozenset(
            {
                "Python",
                "SQL",
                "Pandas",
                "NumPy",
                "scikit-learn",
                "TensorFlow",
                "Machine Learning",
                "Generative AI",
                "LLMs",
                "AI Agents",
                "LangGraph",
                "LangChain",
                "RAG",
                "MCP",
                "REST APIs",
                "System Design",
                "Distributed Systems",
                "Event-Driven Architecture",
                "AWS",
                "Cloud",
                "Docker",
                "Kubernetes",
                "CI/CD",
                "PostgreSQL",
                "Vector Databases",
                "Time Series",
                "Statistics",
                "NLP",
                "Deep Learning",
                "Data Engineering",
            }
        ),
        evidence=(
            "5+ years: ML Engineer since Mar 2023 and Python Developer since Sep 2020.",
            "Production GenAI and agentic systems using LangGraph/LangChain, RAG and MCP/FastMCP.",
            "Python/SQL ML stack with TensorFlow, scikit-learn, pandas, NumPy and PostgreSQL/pgvector.",
            "AWS, Docker, Kubernetes, CI/CD, distributed/event-driven APIs and production monitoring.",
            "M.Tech Software Systems (2024) and AWS Cloud Practitioner.",
        ),
    )


_COMPANY_PATTERNS = (
    ("Accenture", r"\baccenture\b"),
    ("Affine Analytics", r"\baffine(?: analytics)?\b"),
    ("Algoleap Technologies", r"\balgoleap\b"),
    ("Amgen", r"\bamgen\b"),
    ("Arohak Technologies", r"\barohak\b"),
    ("ARRISE", r"\barrise\b|\bpragmatic play\b"),
    ("Carrier", r"\bcarrier\b"),
    ("Clean Harbors", r"\bclean harbors\b"),
    ("Cohere Health", r"\bcohere health\b"),
    ("Cornerstone", r"\bcornerstone(?: ondemand)?\b"),
    ("Covalense Global", r"\bcovalense\b"),
    ("DataNimbus", r"\bdatanimbus\b"),
    ("Deloitte", r"\bdeloitte\b"),
    ("Dun & Bradstreet", r"\bdun (?:and|&) bradstreet\b"),
    ("Evernorth", r"\bevernorth\b|\bthe cigna group\b|^cigna$"),
    ("EY", r"^ey$|\bernst (?:and|&) young\b"),
    ("First Due", r"\bfirst due\b"),
    ("G-P", r"^g p$|\bglobalization partners\b"),
    ("Globant", r"\bglobant\b"),
    ("Harjai Computers", r"\bharjai\b"),
    ("JPMorgan Chase", r"\bjpmorgan(?:chase)?\b|\bj p morgan\b|\bjp morgan\b"),
    ("Kantar", r"\bkantar\b"),
    ("LTM", r"^ltm$|\bltimindtree\b"),
    ("Microsoft", r"\bmicrosoft\b"),
    ("Mobile Programming", r"\bmobile programming\b"),
    ("Newbie Soft Solutions", r"\bnewbie soft\b"),
    ("NR Consulting", r"^nr consulting$"),
    ("PepsiCo", r"\bpepsico\b"),
    ("Proxelera", r"\bproxelera\b"),
    ("Qentelli", r"\bqentelli\b"),
    ("Quess", r"\bquess\b"),
    ("Real", r"^real$|^real brokerage$"),
    ("S&P Global", r"\bs (?:and )?p global\b"),
    ("Solenis", r"\bsolenis\b"),
    ("Teradata", r"\bteradata\b"),
    ("ValueMomentum", r"\bvaluemomentum\b"),
    ("Vanguard", r"\bvanguard\b"),
    ("Vrinda Global", r"\bvrinda global\b"),
    ("Warner Bros. Discovery", r"\bwarner bros\b|^wbd$"),
    ("Wonderbiz Technologies", r"\bwonderbiz\b"),
    ("ZF", r"^zf(?: group| india| friedrichshafen)?$|\bzf india\b"),
)

_RECRUITING_TERMS = re.compile(
    r"\b(recruit|talent acquisition|human resources|people partner|hr business|hiring)\b",
    re.IGNORECASE,
)
_TECH_TERMS = re.compile(
    r"\b(ai|artificial intelligence|machine learning|ml|data|software|engineering|"
    r"technology|analytics|cloud|platform)\b",
    re.IGNORECASE,
)
_LEADERSHIP_TERMS = re.compile(
    r"\b(lead|manager|director|head|principal|architect|vice president|vp)\b",
    re.IGNORECASE,
)


def normalize_text(value: object) -> str:
    """Return a lowercase, punctuation-insensitive comparison value."""

    text = str(value or "").strip().lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def canonical_company(value: object) -> str:
    """Map alert/export company variants to one cautious canonical employer name."""

    normalized = normalize_text(value)
    for canonical, pattern in _COMPANY_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            return canonical
    return str(value or "").strip()


def load_connections(path: Path) -> list[Connection]:
    """Read a LinkedIn Connections.csv export without retaining email addresses."""

    path = Path(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(islice(handle, 3, None))
        connections = []
        for row in rows:
            connection = Connection(
                first_name=(row.get("First Name") or "").strip(),
                last_name=(row.get("Last Name") or "").strip(),
                linkedin_url=(row.get("URL") or "").strip(),
                company=(row.get("Company") or "").strip(),
                position=(row.get("Position") or "").strip(),
                connected_on=(row.get("Connected On") or "").strip(),
            )
            if connection.full_name and connection.company:
                connections.append(connection)
    return connections


def connection_relevance(connection: Connection) -> int:
    """Rank likely referral usefulness without claiming relationship strength."""

    score = 0
    if _RECRUITING_TERMS.search(connection.position):
        score += 100
    if _TECH_TERMS.search(connection.position):
        score += 50
    if _LEADERSHIP_TERMS.search(connection.position):
        score += 20
    if connection.linkedin_url.startswith(("https://", "http://")):
        score += 5
    return score


def company_connections(connections: list[Connection], company: object) -> list[Connection]:
    """Return exact canonical-company matches, highest-relevance first."""

    target = canonical_company(company)
    matches = [item for item in connections if canonical_company(item.company) == target]
    return sorted(
        matches,
        key=lambda item: (
            -connection_relevance(item),
            normalize_text(item.position),
            normalize_text(item.full_name),
        ),
    )


def experience_points(candidate_years: float, minimum, maximum) -> tuple[int, str]:
    """Score documented experience against a stated range, out of 30."""

    minimum = float(minimum) if minimum not in (None, "") else None
    maximum = float(maximum) if maximum not in (None, "") else None
    if minimum is None and maximum is None:
        return 15, "Official posting does not state a numeric experience range."
    if minimum is not None and candidate_years < minimum:
        gap = minimum - candidate_years
        points = 18 if gap <= 1 else 8 if gap <= 2 else 0
        return points, f"Resume is about {gap:.1f} year(s) below the stated minimum."
    if maximum is not None and candidate_years > maximum:
        gap = candidate_years - maximum
        points = 23 if gap <= 1 else 12 if gap <= 2 else 5
        return points, f"Resume is about {gap:.1f} year(s) above the stated maximum."
    return 30, "Documented experience is within the stated range."


def _role_points(title: str) -> tuple[int, str | None]:
    normalized = normalize_text(title)
    points = 5
    gap = None
    if re.search(
        r"\b(machine learning|ml|artificial intelligence|ai|gen ai|data scientist)\b", normalized
    ):
        points = 15
    elif "data engineer" in normalized:
        points = 10
    elif "technical analyst" in normalized or "operations management" in normalized:
        points = 5
    if re.search(r"\b(manager|principal|architect|technical lead|director)\b", normalized):
        points = min(points, 7)
        gap = "Role seniority may require formal people or architecture leadership evidence."
    return points, gap


def score_official_posting(posting: dict, profile: ResumeProfile) -> dict[str, object]:
    """Return an explainable 100-point resume-to-posting assessment."""

    experience, experience_reason = experience_points(
        profile.years_experience,
        posting.get("experience_min"),
        posting.get("experience_max"),
    )
    required = [str(item) for item in posting.get("required_skills") or []]
    required_keys = {normalize_text(item): item for item in required if normalize_text(item)}
    resume_keys = {normalize_text(item) for item in profile.skills}
    matched = [label for key, label in required_keys.items() if key in resume_keys]
    missing = [label for key, label in required_keys.items() if key not in resume_keys]
    skills = round(40 * len(matched) / len(required_keys)) if required_keys else 20

    role, seniority_gap = _role_points(posting.get("title") or "")
    infrastructure_terms = {
        "aws",
        "azure",
        "gcp",
        "cloud",
        "docker",
        "kubernetes",
        "ci cd",
        "mlops",
    }
    posting_infra = infrastructure_terms.intersection(required_keys)
    resume_infra = infrastructure_terms.intersection(resume_keys)
    production = 10 if not posting_infra or resume_infra else 4
    education = 5
    total = int(experience + skills + role + production + education)

    gaps = list(missing)
    if seniority_gap:
        gaps.insert(0, seniority_gap)
    if "healthcare" in required_keys and "healthcare" not in resume_keys:
        gaps = [item for item in gaps if normalize_text(item) != "healthcare"]
        gaps.insert(0, "Healthcare-domain experience is not documented in the resume.")
    if "management" in required_keys and "management" not in resume_keys:
        gaps = [item for item in gaps if normalize_text(item) != "management"]
        gaps.insert(0, "Formal people-management experience is not documented in the resume.")

    if posting.get("active_status") in {"closed", "filled", "inactive"}:
        band = "Closed / reference only"
    elif total >= 85:
        band = "Strong"
    elif total >= 70:
        band = "Good"
    elif total >= 55:
        band = "Possible"
    else:
        band = "Stretch"

    component_text = (
        f"Experience {experience}/30; skills {skills}/40; role {role}/15; "
        f"production/cloud {production}/10; education {education}/5."
    )
    return {
        "score": total,
        "band": band,
        "confidence": posting.get("evidence_confidence") or "medium",
        "matched_skills": matched,
        "missing_skills": missing,
        "gaps": gaps,
        "experience_reason": experience_reason,
        "components": component_text,
    }


def score_alert_only(alert: dict, profile: ResumeProfile) -> dict[str, object]:
    """Produce a deliberately capped preliminary score when no official JD exists."""

    experience, experience_reason = experience_points(
        profile.years_experience,
        alert.get("experience_min_years"),
        alert.get("experience_max_years"),
    )
    role, seniority_gap = _role_points(alert.get("title") or "")
    relevance = 10 if role >= 10 else 5
    location = (
        5
        if "hyderabad" in normalize_text(alert.get("location"))
        or "remote" in normalize_text(alert.get("location"))
        else 2
    )
    total = min(60, int(experience + role + relevance + location))
    gaps = ["Official job description was not located; required-skill coverage is unscored."]
    if seniority_gap:
        gaps.append(seniority_gap)
    return {
        "score": total,
        "band": "Preliminary only",
        "confidence": "low",
        "matched_skills": [],
        "missing_skills": [],
        "gaps": gaps,
        "experience_reason": experience_reason,
        "components": (
            f"Experience {experience}/30; role {role}/15; title relevance {relevance}/10; "
            f"location {location}/5; official requirements unscored."
        ),
    }


def cold_referral_message(
    connection: Connection,
    company: str,
    title: str,
    job_url: str,
    matched_skills: list[str],
    experience_note: str = "",
) -> str:
    """Draft a concise LinkedIn referral request without implying closeness."""

    strengths = matched_skills[:2] or ["production AI/ML", "Python and cloud delivery"]
    strength_text = " and ".join(strengths)
    alignment = f" {experience_note.strip()}" if experience_note.strip() else ""
    return (
        f"Hi {connection.first_name},\n\n"
        f"I'm applying for the {title} role at {company}. I have 5+ years of ML and "
        f"Python engineering experience, including {strength_text}.{alignment}\n\n"
        f"Job: {job_url}\n\n"
        "If you think my profile is suitable, could you please refer me for this role? "
        "I can share my resume and any additional details. I completely understand if "
        "it isn't possible.\n\n"
        "Thank you,\nAsrith"
    )
