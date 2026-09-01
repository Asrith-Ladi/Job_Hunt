"""Manual Gmail ingestion orchestration with injectable boundaries for testing."""

import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from job_hunt.jobs.dedupe import company_match, deduplicate
from job_hunt.jobs.experience import classify_experience_fit
from job_hunt.jobs.models import PipelineResult, RunSummary
from job_hunt.parsers import select_parser


def _utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


ProgressCallback = Callable[[Mapping[str, Any]], None]


def _emit(progress_callback: ProgressCallback | None, **values: Any) -> None:
    if progress_callback is not None:
        progress_callback(values)


def run_pipeline(
    config,
    gmail_reader,
    sheets_store=None,
    parsers=None,
    now=None,
    progress_callback: ProgressCallback | None = None,
):
    config.validate()
    started_at = now or _utc_now()
    run_id = "run_{0}".format(uuid.uuid4().hex[:12])
    source_names = " + ".join(source.title() for source in config.active_sources)
    _emit(
        progress_callback,
        stage="gmail_read",
        message="Reading approved Gmail alert labels.",
        current_item=f"{source_names} alerts",
        completed_items=0,
        total_items=len(config.active_sources),
        matches_found=0,
    )
    messages = gmail_reader.list_alerts(
        config.gmail_query,
        max_messages=config.max_messages,
        progress_callback=progress_callback,
    )
    _emit(
        progress_callback,
        stage="gmail_parse",
        message=f"Found {len(messages)} messages. Parsing supported job alerts.",
        current_item="Preparing alert parsers",
        completed_items=0,
        total_items=len(messages),
        matches_found=0,
    )

    parsed_jobs = []
    warnings = []
    supported_messages = 0
    progress_interval = max(1, len(messages) // 20)
    for index, message in enumerate(messages, start=1):
        parser = select_parser(message, config.active_sources, parsers=parsers)
        if parser is None:
            warnings.append("Unsupported sender/format for message {0}.".format(message.message_id))
        else:
            supported_messages += 1
            parsed = parser.parse(message, observed_at=started_at)
            parsed_jobs.extend(parsed.jobs)
            warnings.extend(parsed.warnings)
        if index == 1 or index == len(messages) or index % progress_interval == 0:
            _emit(
                progress_callback,
                stage="gmail_parse",
                message=f"Parsing Gmail alerts: {index} of {len(messages)} checked.",
                current_item=f"Alert {index} of {len(messages)}",
                completed_items=index,
                total_items=len(messages),
                matches_found=len(parsed_jobs),
            )

    _emit(
        progress_callback,
        stage="gmail_deduplicate",
        message=f"Parsed {len(parsed_jobs)} job rows. Removing duplicate alerts.",
        current_item="Deduplicating parsed jobs",
        completed_items=len(messages),
        total_items=len(messages),
        matches_found=len(parsed_jobs),
    )
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

    _emit(
        progress_callback,
        stage="gmail_filter",
        message=f"Prepared {len(included)} matching jobs after deduplication and filters.",
        current_item="Applying company and experience settings",
        completed_items=len(messages),
        total_items=len(messages),
        matches_found=len(included),
    )

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
