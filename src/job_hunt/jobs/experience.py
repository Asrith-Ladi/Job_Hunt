"""Small, deterministic helpers for job-experience ranges and target fit."""

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import unquote, urlsplit


NUMBER = r"\d+(?:\.\d+)?"
RANGE_PATTERN = re.compile(
    rf"(?P<minimum>{NUMBER})(?:\s*[-–—]\s*|\s*-?\s*to\s*-?\s*)"
    rf"(?P<maximum>{NUMBER})\s*-?\s*year(?:s|\(s\))?",
    re.IGNORECASE,
)
MINIMUM_PATTERN = re.compile(
    rf"(?:minimum(?:\s+of)?|at\s+least)?\s*(?P<minimum>{NUMBER})\s*\+?\s*"
    rf"year(?:s|\(s\))?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ExperienceRange:
    minimum: float
    maximum: Optional[float] = None


def _searchable_text(value):
    text = unquote(str(value or ""))
    text = text.replace("–", "-").replace("—", "-")
    return re.sub(r"[_/]+", " ", text)


def extract_experience_range(value):
    """Return a conservative range from text or a descriptive job URL."""

    text = _searchable_text(value)
    range_match = RANGE_PATTERN.search(text)
    if range_match:
        minimum = float(range_match.group("minimum"))
        maximum = float(range_match.group("maximum"))
        if minimum <= maximum:
            return ExperienceRange(minimum=minimum, maximum=maximum)

    minimum_match = MINIMUM_PATTERN.search(text)
    if minimum_match:
        return ExperienceRange(minimum=float(minimum_match.group("minimum")))
    return None


def _format_number(value):
    return str(int(value)) if float(value).is_integer() else str(value).rstrip("0").rstrip(".")


def experience_text_from_url(url):
    """Extract only an explicitly encoded experience range from a job URL path."""

    try:
        path = urlsplit(url).path
    except ValueError:
        return None
    parsed = extract_experience_range(path)
    if parsed is None:
        return None
    minimum = _format_number(parsed.minimum)
    if parsed.maximum is None:
        return "{0}+ years".format(minimum)
    return "{0}-{1} years".format(minimum, _format_number(parsed.maximum))


def classify_experience_fit(value, target_minimum, target_maximum):
    """Classify a role without discarding broad or missing experience ranges."""

    parsed = extract_experience_range(value)
    if parsed is None:
        return "unknown"
    if parsed.maximum is not None and parsed.maximum < target_minimum:
        return "outside_target"
    if parsed.minimum > target_maximum:
        return "outside_target"
    if target_minimum <= parsed.minimum <= target_maximum:
        return "preferred"
    return "possible_overlap"
