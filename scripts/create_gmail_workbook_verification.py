"""Create a small non-private Gmail workbook used for render and Excel QA."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from job_hunt.gmail_workbook import verify_gmail_run_workbook, write_gmail_run_workbook
from job_hunt.integrations.sheets import JOB_COLUMNS


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "outputs"
    / "gmail_phase_verification"
    / "Gmail_Alerts_Verification.xlsx"
)


def sample_row(record_id: str, source: str, company: str, title: str, url: str) -> dict:
    row = {column: "" for column in JOB_COLUMNS}
    row.update(
        {
            "job_record_id": record_id,
            "owner_id": "personal",
            "alert_source": source,
            "gmail_message_id": f"sample-message-{record_id}",
            "email_subject": f"Sample {title} alert",
            "email_received_at": "2026-08-01T09:00:00+00:00",
            "company": company,
            "title": title,
            "location": "Hyderabad, India",
            "years_of_experience": "5-8 years",
            "source_url": url,
            "first_seen_at": "2026-08-01T09:01:00+00:00",
            "last_seen_at": "2026-08-01T09:01:00+00:00",
            "parse_confidence": "high",
            "parse_status": "parsed",
            "company_match": "not_configured",
            "application_status": "reviewing",
            "notes": "Editable in Streamlit and saved back to this workbook.",
            "evidence_message_ids": f"sample-message-{record_id}",
            "experience_min_years": 5,
            "experience_max_years": 8,
            "experience_fit": "inside_target",
            "experience_source": "email",
        }
    )
    return row


def main() -> int:
    rows = [
        sample_row(
            "sample-linkedin",
            "linkedin",
            "Example Product Company",
            "Senior Machine Learning Engineer",
            "https://www.linkedin.com/jobs/view/123456",
        ),
        sample_row(
            "sample-naukri",
            "naukri",
            "Example Services Company",
            "AI / ML Engineer",
            "https://www.naukri.com/job-listings-example-123456",
        ),
    ]
    summary = {
        "run_id": "verification-run",
        "started_at": "2026-08-01T14:30:00+05:30",
        "finished_at": "2026-08-01T14:31:00+05:30",
        "status": "completed",
        "messages_read": 2,
        "messages_supported": 2,
        "jobs_parsed": 3,
        "jobs_after_deduplication": 2,
        "jobs_filtered_out": 0,
        "parsing_warnings": 0,
        "jobs_unchanged_from_prior_runs": 0,
        "jobs_exported_this_run": 2,
    }
    write_gmail_run_workbook(
        DEFAULT_OUTPUT,
        rows,
        summary,
        run_started_at=datetime(2026, 8, 1, 14, 30),
    )
    verify_gmail_run_workbook(DEFAULT_OUTPUT, expected_rows=2)
    print(DEFAULT_OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
