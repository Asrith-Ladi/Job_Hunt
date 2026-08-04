# Discussion 008: OpenAI-enabled Streamlit full workflow

- Date: 2026-07-20
- Status: implemented and locally validated; cloud deployment remains Q-007
- Related queue item: Q-015

## Outcome

The Streamlit `Run complete workflow` action now performs the personal MVP end to end:

1. Read only the approved LinkedIn and Naukri Gmail labels through Google OAuth.
2. Parse, normalize, filter, and deduplicate the rolling 30-day alerts.
3. Research only uncached alerts through the OpenAI Responses API and web search.
4. Accept only public official employer or official ATS job URLs after local validation.
5. Build official matches, full-description summaries, deterministic resume eligibility,
   same-company referral candidates, and copy-ready referral messages.
6. Refresh the existing dated Google Sheet tracker while preserving user-maintained fields.
7. Export that same tracker to `D:\Projects\job_hunt\job_hunt.xlsx` and expose a download
   button in Streamlit.

`Preview only` stops after Gmail parsing and performs no OpenAI, Sheet, or Excel writes.

## LLM choice and cost controls

- Default model: `gpt-5.6-luna`, with low reasoning effort.
- The app groups same-company alerts into bounded calls.
- A private research cache records checked alert IDs, including alerts for which no official
  result was found. Normal daily runs research only new IDs.
- Full-backlog mode processes all uncached alerts in durable checkpoint batches of 10 by
  default; limited-run mode provides an optional smaller boundary.
- `Refresh all cached official-job research` is opt-in because it can create many paid calls.
- Resume scoring, referral ranking, and cold-message construction remain deterministic. The
  LLM is used for public official-job research and structured extraction, not every step.

## Resumable backlog batching

- `Process all remaining Luna research in this run` is the default full-run scope.
- The checkpoint batch size defaults to 10 alerts and remains configurable in the UI.
- Same-company work is still grouped into bounded API calls inside each checkpoint batch.
- The private research cache and dated research snapshot are written atomically after every
  successful checkpoint batch.
- A failed, stopped, or restarted run can be launched again from Streamlit; fingerprinted
  cached alerts are skipped and only the remaining backlog is submitted to Luna.
- The UI reports planned alerts/batches, live company progress, saved checkpoints, total API
  calls, and the remaining queue. Sheet and Excel refresh occurs after the selected research
  scope finishes.

## Privacy boundary

Only these normalized fields may be sent to OpenAI:

- internal alert record ID;
- company;
- title;
- location;
- alert experience text.

The module does not send Gmail bodies, Gmail message IDs, email subjects, alert URLs, resume
contact details, LinkedIn connections, connection emails, or phone numbers. It never asks the
model to open LinkedIn or Naukri pages. Returned LinkedIn, Naukri, aggregator, people-search,
search-result, or malformed URLs are rejected locally.

## Referral-message design

Messages are multi-paragraph and request a referral directly but politely. They include the
visible job URL, relevant documented strengths, an offer to share the resume, and language
that makes it easy for the recipient to decline. They do not claim a close relationship or a
willingness to refer.

## Output behavior

- One Google Sheet remains the durable master tracker.
- The main tab is named `YYYY-MM-DD`; reruns on that date preserve priority, application
  status, and notes for matching rows.
- Supporting tabs are refreshed from the latest generated data.
- The local `job_hunt.xlsx` is replaced atomically with an export of the same Google Sheet.
- On cloud hosts, the Google Sheet is durable. A local XLSX requires persistent storage or
  downloading after the run because many hosts use ephemeral filesystems.

## Verification

- OpenAI credential and `gpt-5.6-luna` request: passed.
- Structured web-search/JSON-schema path: passed with validated official candidates.
- Python tests: 67 passed, including full-backlog completion, limited runs, cache reuse, and
  interruption/resume behavior.
- Streamlit native authenticated baseline test: zero exceptions with Google and OpenAI
  connected; the current UI replaces its old run button with explicit full-backlog and
  limited-batch actions.
- Latest Google tracker: 500 alerts, 10 currently mapped official postings, 502 queue rows,
  721 referral rows, and 492 alerts truthfully marked `research_pending`.
- Workbook safeguards: 2,488 formula links, 1,739 rich links, 1,018 structured cold messages, zero
  formula errors, and zero connection-email leaks.
- Local export: `job_hunt.xlsx` created successfully from the refreshed Google Sheet.

The first real 500-alert click exposed and resolved a legacy-cache migration issue. Cached
no-result checks are now reusable only when the normalized alert fingerprint matches; an old
bare checked-ID list cannot suppress new research. The repair made zero LLM calls and kept
the 492-alert backlog visible rather than falsely labeling it checked.

## Remaining deployment decision

Q-007 still owns hosting, private authentication, persistent Google token/research-cache
storage, durable audit history, and an optional scheduler. The current implementation is the
local validation stage and does not make a Codex plugin or MCP server a runtime dependency.
