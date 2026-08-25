# 025 - Gmail run history and historical application tracking

## Request

Keep cross-run deduplication enabled, but let the user navigate earlier Gmail job files when
the newest run contains no new or changed jobs.

## Implemented behavior

- Job Queue includes a **Previous Gmail runs** menu with the saved workbook name, run time,
  exported-job count, unchanged-job count, and Gmail-message count.
- Each available run can be loaded back into the on-screen queue or downloaded as Excel.
  A direct Drive action is shown whenever its saved Drive identity is known.
- The menu remains available in the zero-row queue state, so a successful empty incremental
  run does not hide earlier useful results.
- Loading a previous run reads its existing workbook only. It does not query Gmail, reset or
  update fingerprints, mark old jobs as new, or create another output file.
- Previous-run Gmail rows remain actionable because collection date is not application status.
  The user can edit `application_status` and `notes` and save them back to that run's original
  local/Drive workbook.
- For previous runs, every other job field is rebuilt from the stored workbook instead of the
  browser submission. This protects company/title/URL/parser evidence while allowing application
  tracking to change.
- Loading a Gmail history item replaces only the Gmail portion of the unified queue. Current
  Company Portal and ATS results remain present.

## Persistence and migration

- New successful runs append sanitized artifact metadata to `gmail_seen_state.json`, which is
  already synchronized under the app-owned Drive `Job Hunt/Source` folder.
- The history index stores no Gmail bodies, connection data, OAuth material, or resume content.
- Existing local `outputs/gmail_runs/<date>/gmail_alerts_*.xlsx` files are backfilled into the
  menu automatically, so runs created before this feature remain usable.
- A previous file that is no longer local can be restored from Drive when its stored Drive
  file ID is available. Its workbook run ID is verified before it is displayed.
- When an older local workbook predates the history index, its first save resolves the app-owned
  dated Drive folder and exact filename, updates that original file, and durably records its Drive
  identity for later navigation.

## Verification

- The real local history lists eight prior Gmail workbooks, including the 2026-08-17 11:23 run
  with 269 saved jobs.
- Loading that workbook returns all 269 rows and marks it as a previous run without disabling
  application tracking.
- A regression test edits status/notes on an older run, rejects a submitted protected-field
  change, preserves Gmail fingerprints, and leaves the latest-run pointer unchanged.
- All 131 Python unit/API tests pass, Ruff passes, and the React TypeScript/Vite production
  build passes.

## Status

- Status: implemented locally on 2026-08-17.
- Queue: `Q-035`.
