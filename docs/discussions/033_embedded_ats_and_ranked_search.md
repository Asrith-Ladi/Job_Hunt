# Embedded ATS detection and ranked role search

Date: 2026-08-25
Queue item: Q-043
Status: implemented

## Request

Observe.AI visibly listed an `AI Agent Engineer` job, but Company Portal search returned
zero results for `agent engineer`. The user asked for a reusable fix across companies and
confirmed that broader results are acceptable when company-specific titles make strict search
unsafe.

## Cause

The configured Observe.AI source was `generic`. Its public careers page renders its jobs from
an embedded Greenhouse board, so the server HTML did not expose ordinary static job anchors
that the generic parser could reliably use. Search also used one field for both role titles and
JD capabilities, which made it impossible to rank a direct title match above a role that only
mentioned the same term in its description.

## Decision and implementation

- Inspect public careers-page markup for explicit Greenhouse, Lever, Workable, and
  SmartRecruiters board identities.
- Hand a detected identity to the existing documented public adapter. Undocumented internal
  endpoints are not promoted to official APIs and access controls are never bypassed.
- Extract the structured job set before applying role, location, date, or experience filters.
- Keep two editable search inputs:
  - target role phrases, matched against the title first;
  - capabilities/JD terms, matched as a broader fallback against title, department, and
    available description text.
- Treat comma-separated values as OR alternatives, preserve broad capability-only results,
  and rank them below direct title matches.
- Attach deterministic `match_type`, `matched_terms`, and `match_score` evidence to temporary
  results. No LLM is used for discovery matching.
- Show per-source `extracted → matched` diagnostics and the detected provider in the UI.

## Live verification

On 2026-08-25 the real `https://www.observe.ai/careers` page was detected as Greenhouse board
`observeai`. Its documented public feed returned 17 active records. A focused verification
using role phrase `agent engineer` plus broad terms `agentic AI, AI agents` returned two direct
title matches first, followed by lower-ranked capability matches. This confirms that a broad
search can retain noisy leads without hiding or demoting the strongest role-title evidence.

## Safety and maintenance

Detection requires an explicit provider hostname, public endpoint URL, or board-token widget
configuration. If the embedded API becomes unavailable, the existing official JSON, sitemap,
static-HTML, Gmail-alert, and manual-link fallbacks remain available. Provider changes are
reported in source diagnostics rather than silently classified as zero matching jobs.
