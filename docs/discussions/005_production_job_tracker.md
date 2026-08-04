# Discussion 005: Production job tracker

- Date: 2026-07-20
- Status: completed for the current Gmail-alert batch
- Related queue items: Q-003, Q-008, Q-009, Q-011, Q-012, Q-013

## Outcome

The existing private master workbook is now the real tracker rather than a sample-only
workbook. The dated production tab is `2026-07-20`, and the previous dated pilot is retained
as `Sample_2026-07-19`.

The run processed five approved-label Gmail messages into 47 unique alert jobs. Public
employer sources produced 25 official postings and 55 alert-to-official or no-result rows.
Twenty-five alerts did not have a current public official result; those rows remain visible
with `no_official_result` rather than being silently dropped or matched to an aggregator.

## Workbook tabs

1. `2026-07-20` is the user-facing application queue. It combines the Gmail alert, official
   candidate, description summary, two separate scores, resume evidence, referral count,
   top referral candidates, a tailored cold message, and application tracking fields.
2. `Gmail_Alerts` contains one normalized row per unique email-derived job.
3. `Official_Jobs` contains the unique public employer postings used by the run.
4. `Job_Matches` records each alert-to-official candidate relationship and its evidence.
5. `Connections` contains at most the three highest-relevance same-company connections for
   each queue row, with a tailored message and no exported email address.
6. `Resume_Scoring` makes the resume evidence, weights, and guardrails visible.
7. `Runs` records production counts and status. Its separate `O:R` side panel contains six
   manual contact-lookup tools; it does not alter the audit table.
8. `Sample_2026-07-19` preserves the original six-alert pilot for reference.

All URL fields are visible and clickable. Referral names now display as named LinkedIn
profile links in `Connections`, and each displayed name in the dated queue is individually
linked to the corresponding profile. The visible job URL inside each cold message is a
rich-text link to the official career posting when one is available (otherwise it retains
the alert discovery URL). Keeping the URL visible also lets it survive copying into a
LinkedIn message.

The completed workbook contains 395 verified hyperlink formulas, including 90 named
referral-profile links and six contact-tool links, plus 216 verified in-cell referral/job
links and 126 verified multi-paragraph cold messages. It has no formula errors and no
connection-email leakage.

## Score separation

`official_match_score` measures whether an employer posting is likely related to the Gmail
alert. It uses company, title, location, active state, and requisition evidence. It does not
measure the candidate.

`eligibility_score` measures documented resume evidence against one official posting:

- experience fit: 30 points;
- required-skill coverage: 40 points;
- role/title alignment: 15 points;
- production/cloud alignment: 10 points;
- education/certification: 5 points.

If no official description is available, the preliminary score is capped at 60 and marked
low confidence. Missing requirements are not invented. Closed or filled postings remain as
history and are assigned `Skip` priority even when the resume skills overlap.

## Referral design

The supplied LinkedIn export is copied only into the Git-ignored private sample area. The
normalizer discards exported email addresses, maps cautious employer aliases, and ranks
same-company connections by recruiting/technical-role relevance. A referral count is the
number of same-company export matches; it is not a claim about relationship strength or a
person's willingness to refer.

The dated queue shows the full count and up to three suggested people. The `Connections`
tab holds the corresponding job-specific cold messages. The run produced 90 ranked rows
from 3,256 usable connection records. Clicking a displayed referral name opens that
person's exported LinkedIn profile URL; clicking the URL within a cold message opens the
job page used to draft that message.

## Source boundary and limitations

Only public employer career pages and official public ATS postings were used for official
descriptions. Protected LinkedIn and Naukri job pages were not scraped. Where a public
employer page exposed multiple plausible requisitions, all useful candidates were retained
and labeled `active_candidate` or `active_related`; none is claimed as the original alert
without requisition evidence.

Resume content was structurally extracted from the supplied DOCX. Contact and direct-profile
lines were excluded. Visual DOCX rendering was unavailable in the local environment, so the
current scoring relies on structural text plus explicit dated role evidence.

## Implementation

- `src/job_hunt/enrichment.py` contains company normalization, referral ranking, experience
  scoring, eligibility scoring, and cold-message generation.
- `scripts/build_production_tracker.py` builds, formats, and verifies the existing workbook.
- `local_samples/private/official_research_2026-07-20.json` is the ignored research snapshot
  for this dated run.
- `tests/test_enrichment.py` covers the deterministic enrichment rules.
- `tests/test_sheets.py` covers named hyperlink formulas and UTF-16-safe rich-text link
  ranges used by Google Sheets.
- `tests/test_production_tracker.py` verifies the contact-tool panel and its manual-use
  guardrails.

The production generator preserves user-maintained priority, application status, and notes
when rerun against the same dated tab and the same alert/official-job key.

## Presentation update — 2026-07-20

- Cold messages use short paragraphs with a greeting, role context, a separately visible job
  URL, candidate context, referral request, and sign-off so they can be copied directly into
  LinkedIn without manual reformatting.
- The title and summary rows wrap in a wide banner outside the narrow frozen priority
  column, the application summary is shorter, and only that first column remains frozen
  horizontally.
- Queue and referral rows are taller so the structured message is readable while the cell
  still retains its clickable in-text job link.
