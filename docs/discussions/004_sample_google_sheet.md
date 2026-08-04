# Discussion 004: Sample Google Sheet

- Date: 2026-07-19
- Status: completed sample; superseded by the production tracker in Discussion 005
- Related queue item: Q-010

## Decision

Use one Google Sheet workbook for the personal MVP. Create or update one user-facing tab
per local run date (`YYYY-MM-DD`) and retain normalized backend tabs in the same workbook.
Multiple runs on the same date should update the existing dated tab instead of creating
duplicate date tabs.

## Verified sample

The private sample workbook `Personal Job Hunt - Sample - 2026-07-19` was created through
the project's direct Google Sheets API integration and verified after creation. Its tabs,
in order, are:

1. `2026-07-19` — flattened daily review with 11 ranked candidate rows for the six-alert pilot.
2. `Gmail_Alerts` — one normalized record per job extracted from a Gmail alert.
3. `Official_Jobs` — normalized jobs found on official employer sources.
4. `Job_Matches` — ranked alert-to-official-job candidate relationships.
5. `Runs` — run counts, status, and audit notes.

The dated tab includes the original alert URL, official candidate URL, experience text and
provenance, normalized minimum and maximum years, a formula-derived 5–8-year fit, match
status/score/reason, and application status. It deliberately preserves multiple official
candidates when an alert cannot be tied to one exact employer requisition.

Alert and official-job URLs remain visible as full URLs and are stored as explicit
`HYPERLINK` formulas. The verified sample contains 35 clickable URL cells across the dated
review, `Gmail_Alerts`, and `Official_Jobs` tabs. Future core `Gmail_Alerts` writes apply the same behavior
after both inserts and updates.

`Job_Matches` connects a `Gmail_Alerts` record to zero or more `Official_Jobs` records. Its
rank, score, status, and reasons help the user review candidates without silently claiming
an exact match. The sample's scores were assigned during the interactive six-job research
pilot; an approved, tested automatic scoring formula does not exist yet.

## Privacy and access

The sample remains private under the user's Google account. It was created with the
existing `drive.file` grant; no public or link-sharing permission was added. OAuth tokens,
private email bodies, and recipient details are not stored in this discussion.

## Implementation boundary

`scripts/create_sample_sheet.py` is a repeatable sample-data generator and verifier, not the
daily production pipeline. Production work must connect parser output and official-source
matching data to an idempotent upsert workflow before this sample becomes the live tracker.

That production transition was completed for the current batch on 2026-07-20. The pilot is
preserved as `Sample_2026-07-19`; see Discussion 005 for the live tab design and verification.
