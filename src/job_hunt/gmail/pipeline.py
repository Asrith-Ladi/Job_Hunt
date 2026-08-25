"""Manual Gmail ingestion orchestration with injectable boundaries for testing."""

import uuid
from datetime import datetime, timezone

from job_hunt.jobs.dedupe import company_match, deduplicate
from job_hunt.jobs.experience import classify_experience_fit
from job_hunt.jobs.models import PipelineResult, RunSummary
from job_hunt.parsers import select_parser


def _utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_pipeline(config, gmail_reader, sheets_store=None, parsers=None, now=None):
    config.validate()
    started_at = now or _utc_now()
    run_id = "run_{0}".format(uuid.uuid4().hex[:12])
    messages = gmail_reader.list_alerts(config.gmail_query, max_messages=config.max_messages)

    parsed_jobs = []
    warnings = []
    supported_messages = 0
    for message in messages:
        parser = select_parser(message, config.active_sources, parsers=parsers)
        if parser is None:
            warnings.append("Unsupported sender/format for message {0}.".format(message.message_id))
            continue
        supported_messages += 1
        parsed = parser.parse(message, observed_at=started_at)
        parsed_jobs.extend(parsed.jobs)
        warnings.extend(parsed.warnings)

    deduped = deduplicate(parsed_jobs)
    included = []
    filtered_out = 0
    for job in deduped:
        job.owner_id = config.owner_id
        job.company_match = company_match(job.company, config.company_allowlist)
        job.experience_fit = classify_experience_fit(
            job.experience_text,
            config.target_experience_min_years,
            config.target_experience_max_years,
        )
        if job.company_match == "unmatched" and not config.include_unmatched_companies:
            filtered_out += 1
            continue
        if job.company_match == "unknown" and not config.include_unmatched_companies:
            filtered_out += 1
            continue
        if (
            config.experience_filter_mode == "exclude_outside"
            and job.experience_fit == "outside_target"
        ):
            filtered_out += 1
            continue
        included.append(job)

    inserted = 0
    updated = 0
    spreadsheet_id = None
    if not config.dry_run:
        if sheets_store is None:
            raise ValueError("A Sheets store is required when dry_run is false.")
        inserted, updated = sheets_store.upsert_jobs(included)
        spreadsheet_id = sheets_store.spreadsheet_id

    finished_at = _utc_now()
    summary = RunSummary(
        run_id=run_id,
        started_at=started_at,
        finished_at=finished_at,
        status="completed_with_warnings" if warnings else "completed",
        messages_read=len(messages),
        messages_supported=supported_messages,
        jobs_parsed=len(parsed_jobs),
        jobs_after_deduplication=len(deduped),
        jobs_filtered_out=filtered_out,
        rows_inserted=inserted,
        rows_updated=updated,
        parsing_warnings=len(warnings),
        dry_run=config.dry_run,
        spreadsheet_id=spreadsheet_id,
    )
    if not config.dry_run:
        sheets_store.append_run(summary)
    return PipelineResult(summary=summary, jobs=included)
