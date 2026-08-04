"""Run configuration supplied by the UI rather than committed YAML."""

from dataclasses import dataclass, field
from typing import List, Optional


SUPPORTED_SOURCES = ("linkedin", "naukri")


@dataclass
class RunConfig:
    gmail_query: str
    owner_id: str = "personal"
    active_sources: List[str] = field(default_factory=lambda: list(SUPPORTED_SOURCES))
    company_allowlist: List[str] = field(default_factory=list)
    include_unmatched_companies: bool = True
    lookback_days: int = 30
    dry_run: bool = True
    spreadsheet_id: Optional[str] = None
    max_messages: int = 500
    target_experience_min_years: float = 5.0
    target_experience_max_years: float = 8.0
    experience_filter_mode: str = "show_all"

    def validate(self):
        self.owner_id = self.owner_id.strip()
        if not self.owner_id:
            raise ValueError("Owner ID cannot be empty.")
        if not self.gmail_query.strip():
            raise ValueError("Gmail query cannot be empty.")
        unknown_sources = sorted(set(self.active_sources) - set(SUPPORTED_SOURCES))
        if unknown_sources:
            raise ValueError("Unsupported sources: {0}".format(", ".join(unknown_sources)))
        if not self.active_sources:
            raise ValueError("Select at least one alert source.")
        if not 1 <= self.lookback_days <= 90:
            raise ValueError("Lookback must be between 1 and 90 days.")
        if not 1 <= self.max_messages <= 5000:
            raise ValueError("Maximum messages must be between 1 and 5000.")
        if self.target_experience_min_years < 0:
            raise ValueError("Target minimum experience cannot be negative.")
        if self.target_experience_max_years < self.target_experience_min_years:
            raise ValueError("Target maximum experience must be at least the minimum.")
        if self.experience_filter_mode not in {"show_all", "exclude_outside"}:
            raise ValueError("Unsupported experience filter mode.")

        self.company_allowlist = sorted(
            {company.strip() for company in self.company_allowlist if company.strip()},
            key=str.casefold,
        )
