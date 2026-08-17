"""Canonical models kept independent of Gmail, Streamlit, and Google Sheets."""

from dataclasses import asdict, dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class AlertMessage:
    message_id: str
    thread_id: str
    sender: str
    subject: str
    received_at: str
    text_body: str = ""
    html_body: str = ""


@dataclass
class JobRecord:
    job_record_id: str
    alert_source: str
    gmail_message_id: str
    email_subject: str
    email_received_at: str
    company: Optional[str]
    title: Optional[str]
    location: Optional[str]
    experience_text: Optional[str]
    alert_posted_at: Optional[str]
    source_url: str
    official_url: Optional[str]
    first_seen_at: str
    last_seen_at: str
    parse_confidence: str
    parse_status: str
    owner_id: str = "personal"
    company_match: str = "not_configured"
    application_status: str = "not_started"
    notes: str = ""
    evidence_message_ids: List[str] = field(default_factory=list)
    experience_min_years: Optional[float] = None
    experience_max_years: Optional[float] = None
    experience_fit: str = "unknown"
    experience_source: str = "unknown"

    def to_dict(self):
        value = asdict(self)
        value["years_of_experience"] = value.get("experience_text")
        value["evidence_message_ids"] = ",".join(self.evidence_message_ids)
        return value


@dataclass
class ParseResult:
    source: str
    jobs: List[JobRecord] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class RunSummary:
    run_id: str
    started_at: str
    finished_at: str
    status: str
    messages_read: int
    messages_supported: int
    jobs_parsed: int
    jobs_after_deduplication: int
    jobs_filtered_out: int
    rows_inserted: int
    rows_updated: int
    parsing_warnings: int
    dry_run: bool
    spreadsheet_id: Optional[str] = None

    def to_dict(self):
        return asdict(self)


@dataclass
class PipelineResult:
    summary: RunSummary
    jobs: List[JobRecord]
