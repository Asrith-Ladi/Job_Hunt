# 013 - React and FastAPI migration

## Request

Replace Streamlit as the primary interface because the daily review workflow needs more layout control, compact filtering, wrapped cells, and a clearer editing experience. Preserve the implemented Gmail behavior and keep company portals and ATS sources as separate, inactive phases.

## Approved decision

The user approved this exact stack on 2026-08-01:

- React + TypeScript + Vite for the browser interface.
- FastAPI for the application API and Google OAuth boundary.
- Existing Python Gmail readers, deterministic parsers, deduplication, workbook generation, and Drive adapters remain authoritative.
- Streamlit remains a temporary fallback until the React Gmail phase completes a real connected run and the user approves parity.

The migration changes the interface, not the source priority, workbook schema, Drive layout, or privacy boundary.

## Implemented outcome

The React application keeps three independent source tabs:

1. `Gmail alerts` - active.
2. `Company portals` - visible placeholder only.
3. `ATS sources` - visible placeholder only.

The Gmail screen provides:

- source, Gmail-label, lookback, message-limit, company, and 5-8-year filters;
- a generated Gmail query with an explicit advanced override;
- Google connection status and a backend-owned OAuth flow;
- run metrics, text search, source/status filters, and optional visible columns;
- wrapped table cells with only one frozen left column;
- clickable alert and official URLs;
- editing only for the approved workbook fields;
- explicit `Save Excel + Drive`, which preserves row identities and updates the same file;
- direct Excel download and Drive-file navigation.

FastAPI also serves the compiled React bundle, so ordinary local use needs one process at `http://localhost:8000`. Vite on port 5173 is only required while changing frontend code.

## Backend API boundary

The implemented routes are:

- `GET /api/health`
- `GET /api/config`
- `GET /api/auth/google/status`
- `POST /api/auth/google/start`
- `GET /api/auth/google/callback`
- `GET /api/drive/workspace`
- `GET /api/gmail/runs/latest`
- `POST /api/gmail/runs`
- `GET /api/gmail/runs/{run_id}`
- `PUT /api/gmail/runs/{run_id}/jobs`
- `GET /api/gmail/runs/{run_id}/download`

Google tokens, OAuth client contents, raw Gmail bodies, and Drive credentials never enter the React application. The API returns normalized rows, safe summaries, and app-owned links. Mutating Gmail runs are locked so two run/save operations cannot overlap in the personal process.

## Access and privacy

No new Google scope is required. The app still requests only:

- `gmail.readonly`
- `drive.file`

The Google Cloud OAuth client must now include this exact local redirect URI:

```text
http://localhost:8000/api/auth/google/callback
```

The previously saved refresh token still returns `invalid_grant`, so one user reconnection is required before a live React Gmail run. The current backend is for local validation only. Do not expose it directly to the public internet until private access control, HTTPS, a durable session secret, and persistent encrypted OAuth/state storage are selected.

## Verification

- The React TypeScript production build succeeds.
- FastAPI serves the compiled React root and live health/config endpoints.
- The existing 79 Python tests continue to pass.
- Nine new application-service and API tests pass.
- Focused Ruff checks pass for all new backend/service/test files.
- The live API correctly reports the existing Google connection as requiring reconnection and restores the latest local Gmail workbook without exposing its filesystem path.
- Browser connection discovery returned no available browser, so an interactive visual click-through is not claimed. The production bundle, HTTP surface, TypeScript compiler, and API behavior were verified independently.

## Status and next checkpoint

Implementation is complete for local React/FastAPI parity at the code and automated-test level. The next checkpoint is:

1. add the new callback URI in Google Cloud;
2. start the FastAPI app and reconnect Google once;
3. run the real Gmail labels;
4. edit one supported field and save it to the same Excel/Drive file;
5. obtain user approval before retiring Streamlit or starting the company-portal phase.
