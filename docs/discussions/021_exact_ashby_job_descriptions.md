# 021 - Exact Ashby job descriptions and grounded eligibility

## Problem confirmed

The selected Sarvam `Agent Engineer` record carried the correct employer URL and UUID, but
manual job analysis returned a different Sarvam opening, `Applied AI Engineer, Sarvam Agents`.
The web-research result was labelled `active_related`, yet the UI displayed that related role's
OAuth, MCP, RAG, PostgreSQL/MySQL, and Redis requirements as though they belonged to the
selected job. The resulting eligibility score was therefore not valid for the selected role.

## User direction

- Resolve the selected job through Ashby's public job-postings feed.
- Match the exact provider job UUID.
- Do not replace a selected official job with a related opening while collecting its JD.

## Approved implementation

- Inspect a UUID-based employer job page only for a matching public Ashby application URL.
- Query Ashby's documented anonymous Job Postings API and match the exact UUID.
- Keep the employer URL as the selected official URL while retaining the Ashby URL as source
  metadata.
- Send only that exact description to Luna in a structured extraction call without web search.
- Require a verbatim description fragment for every extracted required/preferred skill and
  discard skills whose evidence is absent.
- Parse numeric experience only from an evidence fragment found in the exact description.
- Cache the extraction by the feed's exact-job fingerprint; description or publication changes
  invalidate the cache.
- If Ashby recognizes the board but the exact UUID is missing or the feed fails, show an exact
  source warning and return no candidate. Never substitute a related posting.
- For other selected official URLs, web fallback is exact-only: a candidate must use the same URL
  or provider job identifier.

## Access and privacy

- Ashby's public Job Postings API requires no API key for published job-board data.
- No Google scope, employer login, protected-page access, or new secret is required.
- Gmail content, connection data, and resume evidence are not sent during JD extraction.
- Luna receives the exact public job description only after the user's per-job analysis action.

## Status

- Status: implemented and verified on 2026-08-15.
- Queue: `Q-031`.

## Verification

- The live resolver returned `Agent Engineer`, UUID
  `36f89b00-2010-4d23-aae3-17a2f53d9eaa`, publication timestamp
  `2026-08-11T11:18:55.645+00:00`, and the 6,177-character exact public description.
- The live exact description contains Python and does not contain MCP.
- Regression tests reject a related UUID and discard any skill whose evidence fragment is absent
  from the exact description.
- 124 Python tests passed, full Ruff checks passed, and the React production build passed.
