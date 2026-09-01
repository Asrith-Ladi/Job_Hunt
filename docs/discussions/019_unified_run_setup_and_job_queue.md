# 019 - Unified run setup and verification-first job queue

## Request

Replace the separate daily source screens with a simpler workflow:

1. one `Run Setup` tab where Gmail, Company Portals, and ATS Sources can be enabled independently and configured conditionally;
2. one `Job Queue` tab with a consistent core job view across every enabled source;
3. a premium, motivating interface made from useful workflow blocks rather than decorative dashboard content.

The user approved implementation on 2026-08-14 and asked that the application remain ready to migrate from the personal deployment to a more scalable storage/runtime boundary.

## Approved decisions

- Keep Gmail, Company Portal, and ATS collection logic independent behind one parent run action. A failure in one source must not discard successful results from another source.
- Show only settings for sources that are checked.
- Use the same compact core columns for every source in the unified queue, with source-specific evidence available in the job detail view.
- Preserve every source row during the verification phase. Likely duplicates may share a visual job group, but they must not be deleted or silently merged.
- Label grouped records as unverified and preserve enough evidence for the user to confirm that they represent the same official job.
- Gmail rows must retain both the alert-provided LinkedIn/Naukri URL and the separately verified official-employer job URL.
- Existing public Greenhouse, Lever, Workable, and SmartRecruiters retrieval remains anonymous and requires only a public company identifier, not a secret API key.
- Keep Drive as durable document/output storage while maintaining replaceable service and repository boundaries for later database-backed deployment.
- Remove only files or branches proven unused by imports, builds, tests, documentation, and the supported React/FastAPI runtime. Preserve Git-ignored personal inputs and rollback evidence unless separately approved for deletion.

## Recommended interaction model

### Run Setup

- Shared role, location, experience, recency, and result-limit filters.
- Source cards with checkboxes and concise readiness/selection counts.
- Conditional Gmail labels/message limits, Company Registry selection, and ATS provider/manual-identifier controls.
- One `Run selected sources` action with independent progress and source-specific errors.

### Job Queue

- One normalized row per source record during verification.
- Collapsible possible-match groups, with ungrouped rows displayed normally.
- Source filters and useful saved views such as `Needs official match`, `Ready to apply`, and `Applied`.
- A focused job detail panel for source evidence, official candidates/JD, eligibility, documents, referrals, and activity.
- The default table remains compact; diagnostic and provenance fields stay available without dominating daily review.

## Access and privacy

- No new Google OAuth scope is required.
- No employer login, protected LinkedIn/Naukri scraping, automatic application, or background LLM action is added.
- Official-source and resume actions remain explicit, cached, and contact-free.
- OAuth tokens and API keys remain outside Drive and source control.

## Implementation status

- Status: implemented and verified on 2026-08-14.
- Queue: `Q-029`.

## Delivered outcome

- Replaced the three separate source screens with a conditional `Run Setup` while retaining the existing independent Gmail, Company Portal, and ATS services and workbooks.
- Added a unified `Job Queue` with consistent review summaries, source/run filters, application status and notes editing, source-correct saves, output links, and explicit per-job JD/resume actions.
- Added conservative possible-match grouping based on company plus requisition or normalized company/title/location. Every source row remains present and groups are labeled `Possible same job · not merged`.
- Kept Gmail alert URLs and verified official employer URLs as separate evidence fields in every expanded Gmail record.
- Added a useful-first product shell, meaningful readiness/status blocks, conditional configuration fields, responsive layouts, and stable `?tab=` links for direct reopening after deployment.
- Made initial loading resilient: an unavailable optional source no longer prevents the rest of the workspace from opening, while a missing core configuration produces a retryable error state.
- Removed the unused React `DiscoveryTab` branch and obsolete Google Sheet `drive_export` helper/test. The supported Drive workbooks, migration boundaries, and ignored private inputs remained intact. The temporary Streamlit rollback reference was later deleted in Discussion 041.

## Verification

- `117` Python unit tests passed.
- Full Ruff check of `backend`, `src`, and `tests` passed.
- React TypeScript/Vite production build passed (`35` modules).
- Desktop Run Setup and populated Job Queue renders were visually checked at `1440 × 1200`.
- Responsive Job Queue was checked at Edge's `500 × 844` minimum headless viewport; navigation, Drive action, cards, filters, and queue content fit without horizontal loss.
- No new Google scope, ATS API key, protected-site scraping, or automatic LLM action was introduced.
