# Discussion 007: Deployment runtime and daily runs

- Date: 2026-07-20
- Status: discussion — local full workflow is complete; deployment is not approved
- Related queue item: Q-007

## Immediate outcome

Discussion 008 supersedes the earlier local-runtime limitation: the current Streamlit action
now performs Gmail parsing, cached public official-career research, job-description
enrichment, deterministic resume scoring, referral matching, production multi-tab refresh,
and local Excel export. This discussion still owns hosting, private authentication,
persistent secrets/state, and optional scheduling so the workflow can run without a laptop.

## Recommended approach

Keep one reusable Python pipeline as the product core. Host that pipeline with persistent
Google OAuth/state storage and a scheduler, and retain a small private Streamlit interface
for Run now, review, configuration, and error recovery. The local MVP uses a small/efficient
LLM for public official-job research and structured extraction while Gmail selection,
known-source parsing, deduplication, eligibility scoring, referral ranking, validation, and
Sheet writes remain deterministic. For personal/manual volume this runs in the explicit
Streamlit request; before scheduling or multi-user scale, move it to a durable worker so a
browser disconnect cannot interrupt processing.

An optional remote MCP server can expose the same backend operations to ChatGPT or Codex for
interactive commands and inspection. MCP is a tool interface, not the daily scheduler,
credential store, durable job queue, or user interface; it should not be the only production
runtime.

## Daily workbook behavior

- Reuse one master Google Sheet; do not create a new workbook every day.
- A first run on a new date creates a new `YYYY-MM-DD` application-queue tab and leaves older
  dated tabs available as history.
- A rerun on the same date rebuilds that date's generated data and preserves the user's
  priority, application status, and notes for matching rows.
- Supporting tabs such as `Gmail_Alerts`, `Official_Jobs`, `Job_Matches`, and `Connections`
  represent the latest generated run.
- The current production generator replaces the `Runs` tab with the current audit row. A
  later deployment task should append run history instead of replacing it.

## Alternatives and tradeoffs

1. Streamlit plus hosted pipeline: quickest personal MVP and easiest manual review, but
   Streamlit should not perform a long daily job inside the browser request itself.
2. API/worker plus scheduler, without Streamlit: reliable unattended processing, but loses
   the convenient personal review/configuration screen unless another UI is built.
3. Remote MCP plus the same backend: convenient conversational control, but still requires
   hosting, OAuth/state, permissions, and scheduling underneath.
4. LLM-first processing: flexible for changing templates, but higher cost and less
   predictable than deterministic adapters; use it only behind validation and fallbacks.

## Required access and privacy implications

Cloud deployment needs a private authenticated surface, encrypted persistent storage for
Google refresh tokens and processed-job/research-cache state, deployment secrets for the LLM
API key, and restricted logs that exclude raw email/resume/contact content. The approved LLM
boundary sends only alert ID, company, title, location, and experience text; Discussion 008
records its local enforcement and rejected-source rules.

## Decisions required before implementation

1. Choose a private hosting/runtime and persistent secret/state store.
2. Choose manual-only runs or a daily scheduler after the hosted manual flow is stable.
3. Decide whether an MCP interface is useful in addition to, rather than instead of, the
   hosted product runtime.
