# 026 — AI usage and calculated cost tracking

Status: `implemented`

## Approved outcome

Show where Luna is used, estimate the cost before an explicit paid action, and record
calculated token/tool cost after each Responses API call. Cache hits must be visible as
`$0 new API cost` rather than being mixed with paid calls.

## Implemented boundary

The active application has three metered operations:

1. `official_job_research`: official-employer research with optional web search.
2. `exact_jd_extraction`: structured extraction from one exact public ATS description;
   no web-search tool is configured for this operation.
3. `resume_plan`: one truth-preserving resume/optional-cover-letter plan.

Gmail parsing, public Company Portal and ATS adapters, referrals, Network Reviews,
deterministic eligibility/ATS alignment, DOCX/PDF assembly, Excel, and Drive operations
remain non-LLM work.

## Accounting design

- Capture `input_tokens`, cached/cache-write input, output tokens, reasoning-token detail,
  total tokens, and actual web-search-call records from each API response.
- Calculate USD using a versioned backend price snapshot. The UI labels this as a
  calculated API cost, not an invoice; the OpenAI billing dashboard remains authoritative.
- Initial pre-run ranges are conservative. After measured calls exist, estimates use the
  most recent 20 calculated costs for the matching action area.
- Cached research or planning reports zero new calls and zero new API cost.
- Unknown/unpriced models and missing response usage are reported as incomplete, never as
  free.
- Calls made before this feature was enabled cannot be reconstructed by the app and are
  excluded from its totals.

## Persistence and privacy

The local private mirror is `.secrets/job_intelligence/ai_usage.json`. When Google is
connected, a best-effort durable copy is written to `Job Hunt/Source/ai_usage.json` using
the existing `drive.file` scope. A Drive failure does not discard a paid AI result; the
local record remains available for later synchronization.

The ledger contains only timestamps, operation/model names, token/tool counts, calculated
costs, and public job identifiers such as company/title. It never stores prompts, model
responses, Gmail content, resume/document content, contacts, API keys, OAuth credentials,
or tokens.

## UI

The manual job-intelligence panel now shows:

- today and current-month calculated cost/call totals;
- cached tokens and web-search tool fees;
- recent metered operations;
- a pre-run range on official-JD and document-generation actions;
- the calculated cost for the completed action, or `$0` when its cache was reused;
- the price-snapshot and non-invoice disclaimer.

## Verification

- Python unit suite: 136 passing tests.
- Ruff: passing for all changed Python files.
- React TypeScript production build: passing.
