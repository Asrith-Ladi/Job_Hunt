# Discussion 001 — Gmail Alerts to Google Sheet

## Task status

> 2026-08-01 update: the latest output design is documented in Discussion 012 and the approved React/FastAPI migration in Discussion 013. The Gmail phase creates a timestamped Excel workbook under an app-owned dated Drive folder and displays/edits it in React. The earlier one-master-Google-Sheet output remains historical and is not invoked by the Gmail-only tab.

- Task ID: `MVP-001`
- Phase: approved implementation; live Gmail dry run and core-field parsing complete, Sheet write pending.
- Scope approved by user: **Yes, 2026-07-19**.
- Implementation approved: **Yes**.
- Coding: **Foundation, Web OAuth, and template-aware parsers implemented and live-tested**.
- Google Cloud OAuth client: **Configured by user as a Web application**.
- OAuth consent and live Gmail calls: **Complete for the personal test account**.

## Proposed outcome

A personal, manually triggered UI reads LinkedIn and Naukri notification emails from Gmail, extracts and deduplicates job entries, and upserts them into a Google Sheet stored in Drive.

## Recommended first vertical slice

1. Streamlit UI with **Run now**, validated locally before private hosting.
2. Gmail API using `gmail.readonly` and a dedicated label/query.
3. LinkedIn-alert and Naukri-alert parsers built from redacted fixtures.
4. Stable normalized job fields with separate unknown/confidence markers and an optional company allowlist.
5. Deduplication using Gmail message ID, normalized link, and a conservative company/title/location fingerprint.
6. One Google Sheet with:
   - `Gmail_Alerts`: canonical rows extracted from Gmail alert messages;
   - `Runs`: run counts and errors;
   - `AlertEvidence` remains optional and is deferred until the two core tabs are proven.
7. Manual run summary in the UI.

## Approved decisions

| Decision | Recommendation | Reason |
|---|---|---|
| Execution | Manual UI first | Fast feedback while alerts and fields evolve |
| UI | Streamlit; local validation, then private hosting | One personal interface that can later run without the user's laptop |
| Mail access | Gmail read-only | Least privilege; processed IDs can live outside Gmail |
| Gmail selection | Dedicated label plus sender/query filter | Reduces unrelated email exposure and parser noise |
| Output | One app-created Google Sheet in the user's Drive | Narrow per-file access, easy review, and reliable local ID reuse |
| Core schema | Fixed normalized fields | Reliable dedupe and later migration |
| Customization | Optional visible/export columns | Flexibility without breaking the data model |
| Company list | Optional allowlist; retain uncertain companies for review | Custom filtering without silently losing parsing failures |
| Raw email storage | Off by default | Reduces privacy and security risk |
| Portal pages | Do not scrape | Use alert content and links only |
| Scheduling | Defer | Add unattended execution only after manual runs are stable |
| Multi-user | Design boundaries only | Avoid premature infrastructure while preventing a rewrite |

## Current access decision and next checkpoint

The recommended personal access boundary is `gmail.readonly` plus `drive.file`. The app creates and remembers its own Sheet; arbitrary existing-Sheet and folder selection is deferred to Q-006 so the first version does not request all-spreadsheets or all-Drive access. The Sheet can be moved manually to the preferred Drive folder after creation.

Python 3.12, project dependencies, direct Web OAuth, and the first read-only Gmail dry run are complete. The app auto-detects the Git-ignored local Web OAuth client for validation. The next checkpoint is a user-reviewed non-dry run that creates the app-owned Sheet; private cloud token/state storage remains a later hosting decision.

Redacted fixtures must remove recipient addresses, unrelated personal information, unsubscribe identifiers, and tracking query values. See `../setup/GOOGLE_ACCESS.md` for the full setup checklist.

## Implementation snapshot

- `app.py`: manual Streamlit runner with direct Web OAuth, callback state validation, Gmail query, source/company filters, dry-run control, and UI-selected preview fields.
- `src/job_hunt/`: stable models, owner boundary, MIME decoding, source parsers, URL privacy normalization, deduplication, local Sheet-ID state, and Google adapters.
- Sheet behavior: `Gmail_Alerts` and `Runs` tabs, app-owned file access, stable core headers with trailing custom columns allowed, and reruns that preserve manual application status/notes and first-seen evidence.
- Verification: all Python files compile and 32 tests pass; a live read-only run processed five approved-label messages and 47 deduplicated jobs with zero parsing warnings.
- Live field result: 17/17 LinkedIn jobs and 30/30 Naukri jobs have title, company, and location.
- Unverified boundary: no live Google Sheet has been created or updated because validation remains in dry-run mode.

## Access audit — 2026-07-19

This was the initial pre-authorization audit and is retained as history.

- Connected browser session: unavailable.
- `JOB_HUNT_GOOGLE_CREDENTIALS` in the project process: not configured.
- `.secrets/google_token.json`: not present.
- Local LinkedIn/Naukri sample files: none present.
- Result: no Gmail messages were read, copied, or modified.
- Prepared local destinations: `local_samples/linkedin/` and `local_samples/naukri/`.
- Google Cloud milestone: the user confirmed the Web OAuth client, test user, scopes, and local redirect URI are configured.
- Code milestone: the prior Desktop OAuth flow was replaced with a Web OAuth callback flow.
- OAuth correction: the PKCE verifier now persists across the Streamlit browser redirect; the local round-trip smoke test passes.

## Live validation — 2026-07-19

- Direct application OAuth: connected with `gmail.readonly` and `drive.file`.
- Gmail scope read: production labels `Job_Alerts/LinkedIn` and `Job_Alerts/Naukari` use a
  rolling 30-day query; `link_test` and `nau_test` remain fixture labels. A label-only count
  on 2026-07-20 found 93 LinkedIn and 11 Naukari messages (104 combined), below the current
  500-message run limit.
- Result: five messages read, 47 deduplicated jobs, 47 complete core-field records, and zero parser warnings.
- Sheet writes: none; the validation run used `dry_run=true`.
- Local samples: one raw EML per source is staged under neutral names in Git-ignored storage; removal requires explicit user approval.

## Work sequence after approval

- [x] Approve the task scope and begin the foundation stage.
- [x] Inspect sanitized LinkedIn and Naukri alert formats.
- [x] Define the stable schema, owner boundary, and parser contracts.
- [x] Scaffold the local Streamlit application and UI-selected preview fields.
- [x] Add the direct Web OAuth flow and read-only Gmail adapter code.
- [x] Add conservative link parsers, company filtering, and within-run deduplication tests.
- [x] Add app-created Sheet output and review-safe idempotent upsert code.
- [x] Run dependency-free offline tests with fake alert inputs.
- [x] Install the supported runtime/dependencies and complete the first OAuth dry run.
- [x] Refine LinkedIn/Naukri field extraction from sanitized fixtures.
- [x] Review the core-field dry-run result.
- [ ] Obtain user approval for the first non-dry Sheet write, then verify idempotent reruns.
- [ ] Evaluate GitHub Actions only after repeated successful manual runs.

## Definition of done for MVP-001

- A manual run processes only the approved Gmail alert scope.
- LinkedIn and Naukri alert jobs are parsed with visible confidence/errors.
- Rerunning the same messages creates no duplicate job rows.
- The Sheet is created/updated in the approved Drive location.
- No protected job portal is scraped and no application is submitted.
- Logs and Sheet rows contain no OAuth tokens or full raw emails.
- The user can change companies/filters and optional displayed fields through the UI without changing code.
