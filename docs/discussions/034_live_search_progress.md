# Live search progress

Date: 2026-08-25
Queue item: Q-044
Status: implemented

## Request

Long public-source searches displayed only `Searching ATS...`, so the user could not tell
whether the app was actively reading a feed, inspecting a careers page, trying a fallback, or
stuck. The user requested meaningful progress highlights for every search type.

## Decision

Keep the existing single search request and result semantics, but publish a second bounded,
pollable progress channel. This avoids splitting one logical source run into multiple frontend
requests or changing Drive persistence and deduplication behavior.

The UI displays:

- active search type and processing stage;
- current company, feed, Gmail parsing step, or result-combination step;
- completed versus total work units;
- matching jobs found so far;
- elapsed active time and the most recent safe progress events.

Company and ATS searches report registry loading, the active employer/provider, public API or
careers-page strategy, fallback attempts, extracted-to-matched counts, and final deduplication.
Gmail reports approved-label reading, message parsing counts, deduplication, deterministic
filters, and offline referral matching.

## Privacy and deployment boundary

Progress records contain no Gmail subjects, bodies, message IDs, job descriptions, resume
content, credentials, or connection details. They are held in a thread-safe in-memory store,
limited to 100 records and automatically expire after 30 minutes. Random request IDs make the
polling route unguessable for this personal single-process deployment.

If the application later runs multiple API workers, this ephemeral store must move to an
authenticated shared service such as Redis so the POST worker and polling worker see the same
snapshot. Search results themselves remain temporary and unchanged.

## Verification

- API contract tests cover completed Gmail and company progress snapshots.
- Gmail pipeline tests cover safe stage emission without message identifiers.
- Company/ATS service events use source names and aggregate counts only.
- Full Python, Ruff, and React production-build verification remains required before release.
