"""Export normalized Gmail alert jobs to a private JSON research input."""

import argparse
import json
from collections import Counter
from pathlib import Path

from job_hunt.gmail.config import RunConfig
from job_hunt.integrations.gmail import GoogleGmailReader
from job_hunt.integrations.google_auth import load_stored_credentials
from job_hunt.gmail.pipeline import run_pipeline


DEFAULT_QUERY = (
    "{label:Job_Alerts/LinkedIn label:Job_Alerts/Naukari} newer_than:30d"
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", type=Path, default=Path(".secrets/google_token.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--max-messages", type=int, default=500)
    args = parser.parse_args()

    credentials = load_stored_credentials(args.token)
    reader = GoogleGmailReader.from_credentials(credentials)
    config = RunConfig(
        gmail_query=args.query,
        dry_run=True,
        max_messages=args.max_messages,
        target_experience_min_years=5,
        target_experience_max_years=8,
        experience_filter_mode="show_all",
    )
    result = run_pipeline(config, reader)
    jobs = [job.to_dict() for job in result.jobs]
    jobs.sort(
        key=lambda job: (
            str(job.get("alert_source") or "").casefold(),
            str(job.get("company") or "").casefold(),
            str(job.get("title") or "").casefold(),
            str(job.get("source_url") or ""),
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {"summary": result.summary.to_dict(), "jobs": jobs},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    by_source = Counter(job.get("alert_source") or "unknown" for job in jobs)
    print(
        json.dumps(
            {
                "messages_read": result.summary.messages_read,
                "jobs_parsed": result.summary.jobs_parsed,
                "unique_jobs": len(jobs),
                "jobs_by_source": dict(sorted(by_source.items())),
                "missing_company": sum(not job.get("company") for job in jobs),
                "missing_title": sum(not job.get("title") for job in jobs),
                "missing_location": sum(not job.get("location") for job in jobs),
                "output_bytes": args.output.stat().st_size,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
