# 040 - Clean JD archives and simplified actions

Date: 2026-09-01
Queue item: Q-050
Status: implemented locally; deployment and live-link validation pending

## Request

Correct applied-job evidence so a user can read the actual job description instead of a
JSON-shaped record or an unlabeled short summary. Also simplify the highest-friction UI
areas without replacing the established Search, Results, Applications, and Network flow.

## Decision

- Keep JSON as machine metadata, not the primary human-readable JD.
- Store a readable DOCX and clean Markdown beside the application resume.
- Classify every capture as `full`, `partial`, or `summary_only`; never label a summary as
  a complete job description.
- Before falling back to a summary, retry an exact supported ATS record and then make one
  bounded fetch of the public official employer URL. Never fetch protected LinkedIn,
  Naukri, Indeed, or Glassdoor pages for this purpose.
- Keep the four product workspaces. Simplify the Search page to one primary Search action
  and move recency, experience, and source limits into an advanced section.

## Implemented outcome

- Added deterministic public official-description capture from exact Ashby records,
  JSON-LD `JobPosting`, matching embedded JSON, and conservative static official-page text.
- Normalized HTML, lists, structured mappings, and common mojibake without serializing
  Python/JSON containers as JD prose.
- Application folders now contain `Job_Description.docx`, `Job_Description.md`, and
  `Application_Details.json` alongside the neutral generated resume files.
- Reduced the Markdown file to job metadata, capture-quality warning, and JD text. Skills,
  eligibility, document metadata, and lifecycle state remain in the JSON record.
- Added completeness, source, and warning fields to the API and canonical application row.
- Added readable file labels and capture-quality warnings to the application workspace.
- Removed the decorative Search stepper and duplicate bottom Search button; one top action
  now starts the selected sources.
- Collapsed advanced recency, experience, unknown-date, strict-range, and source-limit
  controls while leaving roles, capabilities, and location immediately editable.

## Verification

- Deterministic description parsing and protected-host tests pass.
- Application package, FastAPI route, resume, and API tests pass.
- TypeScript validation and the Vite production build pass.
- Live visual browser review remains pending because no in-app browser session was attached.

## Deferred boundary

Q-048 remains open. The user will validate deployed company links and report broken or
manual-only sources; those findings will be repaired in bounded batches rather than delaying
the personal deployment on a full registry audit.
