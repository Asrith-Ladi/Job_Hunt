# 031 - Transient search and canonical application queue

Date: 2026-08-20
Queue item: Q-041
Status: implemented

## Request

Use the first product tab to search and the second tab to filter/review the results. Do not
create a new Drive workbook for every search. Persist a job only after an explicit user
decision, especially an application-status change, while keeping the workflow safe for later
deployment.

## Approved decision

Use a hybrid lifecycle:

```text
Search selected sources -> temporary React results -> explicit review action
                                                   -> canonical Drive application queue
```

- Gmail, Company Portal, and ATS searches return normalized rows without creating a dated
  workbook or updating cross-search fingerprint state.
- Current search results remain available while the React application is open and the user
  moves between Search and Results. An ordinary page reload intentionally clears unsaved
  results.
- `Save for later`, an application-status change, a saved review note, or a confirmed official
  URL upserts that one source record into `Job Hunt/Source/application_queue.json`.
- The application key is deterministic per source and source record, so repeated saves update
  one record instead of appending duplicates. Cross-source evidence remains separate until the
  user verifies that two records are the same job.
- Saved jobs load from Drive at startup and are merged with matching current results while
  preserving the saved status, notes, and confirmed official URL.

## Compatibility and privacy

- Existing dated Gmail workbooks remain available through Previous Gmail runs; the active UI
  does not create new ones during search.
- Tracking actions on a loaded historical Gmail row now save to the canonical application
  queue, leaving the historical collection workbook unchanged.
- The company registry remains Drive-authoritative and may refresh its validated local cache.
  Public searches do not create per-run Drive artifacts.
- No Gmail body, OAuth secret, resume contact data, or connection email is added to the queue.
  Only normalized job fields and the already-approved contact-free referral candidates are
  stored.
- No new OAuth scope, API key, LLM call, protected-page scrape, or automatic application is
  introduced.

## Product behavior

- Navigation now presents **Search** followed by **Results & Applications**.
- Search cards say that results are temporary and the Results screen labels each source row as
  `Temporary result` or `Saved in Drive`.
- Results include Saved, possible-duplicate, official-link, source, text, and application-state
  filters.
- `Save for later` uses the explicit `saved` application status.
- Status changes persist immediately; review notes persist on field exit. A failed Drive save
  leaves the result visible and displays an error instead of claiming persistence.

## Implementation

- Added non-persisting Gmail and public-discovery service methods plus `/api/search/*` routes.
- Added `ApplicationQueueService` as the sole active search-to-Drive persistence boundary and
  exposed `GET/PUT /api/applications`.
- Kept read-only legacy history/load/download endpoints for compatibility. Removed the old
  HTTP run-creation and workbook-mutation routes so production clients cannot accidentally
  reintroduce per-search exports.
- Added deterministic merge behavior so saved application fields survive a later fresh search.

## Verification

- Search-service tests confirm no workbook, seen-state, or run-output file is created.
- Application-queue tests confirm repeat updates deduplicate and only explicit upserts upload.
- FastAPI route tests cover transient searches and the canonical application queue.
- All 158 Python tests, full Ruff checks, and the React TypeScript/Vite production build pass.
