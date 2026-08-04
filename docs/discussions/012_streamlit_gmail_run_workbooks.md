# 012 - Streamlit Gmail run workbooks and separated source tabs

> 2026-08-01 update: Discussion 013 supersedes Streamlit as the primary UI. The workbook, Drive layout, deduplication, and explicit-save behavior defined here remain active and are now exposed through React + FastAPI. Streamlit is retained temporarily as a fallback.

## Request

Finish and clean the partially implemented Gmail phase before adding scheduling or the other job-discovery sources. Keep three separate Streamlit tabs for Gmail alerts, company portals from the Excel registry, and structured ATS sources. A Gmail run must show its results on screen, create one dated Excel artifact in Google Drive, and save supported UI edits back into that same file.

## Approved design

- Continue with Streamlit for the personal MVP. It provides sufficient forms, metrics, editable data tables, download actions, and manual execution without a frontend rewrite.
- Keep the tabs independent:
  1. `Gmail Alerts` — implemented now.
  2. `Company Portals` — visible placeholder for the second phase.
  3. `ATS Sources` — visible placeholder for the third phase.
- A Gmail-only run must not invoke OpenAI, official-portal research, resume scoring, referral generation, or the older Google Sheet tracker.
- Use an explicit `Save changes to Excel and Drive` action instead of uploading on every keystroke.

## Drive and file layout

```text
Job Hunt/
  Source/
    Company_Source_Registry.xlsx
    gmail_seen_state.json
  YYYY-MM-DD/
    gmail_alerts_YYYY-MM-DD_HHMMSS.xlsx
```

The registry and non-secret incremental seen-state are synchronized into `Source`. OAuth client JSON, refresh tokens, full raw email bodies, and raw private mail are never uploaded there. The dated folder is created only when an actual Gmail run occurs. Multiple runs on one date receive different timestamped filenames.

## Gmail run behavior

1. Read only the selected Gmail labels/query.
2. Parse LinkedIn and Naukri alert cards through the existing deterministic parsers.
3. Deduplicate within the run by normalized URL, with a conservative company/title/location fallback.
4. Compare stable job IDs and normalized content fingerprints with the non-secret prior-run state.
5. Export only new or changed jobs; report unchanged prior jobs separately.
6. Create a workbook containing `Gmail Alerts` and `Run Summary`.
7. Upload it to the current date folder and display all exported rows in Streamlit.
8. Permit corrections to company, title, location, experience, official URL, application status, and notes.
9. Preserve internal IDs and prevent adding/removing rows through the editor.
10. On explicit save, atomically rewrite the same local workbook and update the same Drive file ID.

The Gmail workbook keeps clickable alert/official URLs, table-owned filters, wrapped text, typed experience values and dates, one frozen left column, application-status validation, and visible run metrics.

## Access and current blocker

No new OAuth scope is required: `gmail.readonly` reads approved alerts and `drive.file` creates/updates only app-owned files. The saved Google refresh token returned `invalid_grant` during the live Drive bootstrap attempt on 2026-08-01. The user must reconnect Google once in Streamlit; the app will then create or reuse `Job Hunt/Source` and perform the first dated upload.

## Verification

- All 79 project tests pass.
- Focused Ruff checks pass for the changed application, workbook, state, Drive, and test files.
- The Gmail verification workbook was rendered and visually inspected.
- Desktop Excel opened the workbook read-only with two worksheets and one intact table, without a repair warning.
- The Streamlit server starts successfully. No interactive browser backend was connected, so a visual click-through was not claimed; Streamlit harness and source-level UI tests cover the stable tab/path configuration.

## Status

Implementation complete. Live Drive folder creation and the first real Gmail run are pending one user Google reconnection.
