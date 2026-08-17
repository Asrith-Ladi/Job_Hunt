# Job Hunt — Project Brief

## Status

- Project type: personal job-search utility first.
- Future direction: support additional users only after the personal workflow is reliable.
- Current phase: a unified React/FastAPI Run Setup and Job Queue cover Gmail, registry-driven Company Portals, and documented public ATS; offline Network Reviews and explicit per-job official-JD/eligibility/tailored-resume actions are also implemented locally. Private internet deployment and scheduling remain later decisions.
- Implementation authorization: granted on 2026-07-19 for Discussion 001.
- Detailed background: `reference/JOB_AUTOMATION_PLAN.md` is reference only.

## Main task

Build a manually triggered, UI-configurable tool with one conditional Run Setup for Gmail, Company Portals, and ATS Sources, one unified Job Queue, and a separate Network Reviews workspace. Gmail normalizes approved LinkedIn and Naukri alerts and adds offline, unverified same-company referral suggestions from the saved LinkedIn snapshot. Company Portals rotates through small selections from the company registry. ATS Sources reads documented public Greenhouse, Lever, Workable, and SmartRecruiters endpoints. The three job-source phases deduplicate and create dated Excel workbooks independently; their latest source rows are reviewed together without destructive merging. Network Reviews uses the offline connection snapshot for profile-review outreach without creating a run workbook. Any result row can open a separate manual job tool; paid official research and tailored-resume generation never run as part of the source phases.

## Why this is the first MVP

- It avoids direct scraping of protected job portals.
- Gmail consolidates alerts the user already receives.
- One Google authorization flow can support Gmail, Sheets, and Drive.
- A manual **Run now** action is easier to inspect and adjust while parsers and fields are evolving.
- The same processing pipeline can later be invoked by GitHub Actions without replacing the UI.

## Proposed user flow

1. Open the React UI served by FastAPI; validate it locally before private hosting.
2. In Run Setup, check Gmail, Company Portals, ATS Sources, or any useful combination.
3. Review shared intent plus only the conditional settings needed by the checked sources. Company Portal and ATS searches accept comma-separated job titles or keywords as alternatives.
4. Run Gmail and/or at most 10 selected public companies/sources; each source completes independently.
5. Normalize fields, preserve uncertainty/date provenance, and deduplicate within each source phase's run history. Keep every current public-source match visible and classify it as new, changed, or previously seen.
6. Create and upload one timestamped Excel workbook per successful source under the current date's Drive folder.
7. Review all latest source rows in Job Queue. Keep possible matches grouped but unmerged, and save supported edits back to their originating workbook and Drive file.
8. Optionally open one job's manual tool, verify an official candidate and separate eligibility score, document any real but previously unrecorded skill evidence, then generate reviewed application drafts only when requested.

## Recommended architecture for the personal version

```text
React + TypeScript UI
        |
        v
FastAPI / server-side Google OAuth
        |
        v
Gmail reader ---------> alert parsers ---------+
Company registry -----> public source discovery +--> normalize + deduplicate
Public ATS adapters --> documented endpoints --+              |
                                                               v
                                                   dated Excel file in Drive

One selected job --> private cache --> Luna official research --> eligibility
                                                   |
Private baseline DOCX --> contact-free evidence ---+--> verified DOCX draft
Confirmed gap notes --> exact truthful keywords ---+
```

- UI: React + TypeScript + Vite with a conditional multi-source Run Setup, unified verification-first Job Queue, source evidence, useful saved views, and supported status/note editing.
- Runtime: FastAPI on Python 3.12 serves both the API and compiled React application; validate locally and then deploy privately so daily use does not require the user's laptop.
- Gmail: Gmail API with read-only access and a dedicated label/query.
- Authentication: direct Google Web OAuth in application code; no Codex plugin or MCP runtime dependency.
- Company filtering: an optional UI allowlist; alerts with missing/uncertain company parsing remain visible in a review state instead of being silently discarded.
- Output: one timestamped Gmail workbook per manual run under an app-created date folder; the current run is fully reviewable in React.
- State: normalized Gmail job fingerprints are stored in a small non-secret state file under app-owned Drive `Job Hunt/Source`; Gmail messages are never modified.
- Public discovery: use structured providers first; otherwise inspect only bounded official feeds, JSON-LD, permitted static links, or sitemaps. Never treat undocumented internal ATS endpoints as official APIs.
- Public discovery state: Company Portals and ATS Sources each keep their own non-secret fingerprints and user review fields under `Job Hunt/Source`.
- Public discovery visibility: fingerprints determine new/changed/previously-seen status but do not remove currently matching jobs from the dated workbook or unified queue.
- Referral enrichment: Gmail uses only saved connection name, company, position, profile URL, and connection date; it excludes contact data and labels current-employer matching as unverified.
- Network outreach: the offline tab lists every saved connection, ranks relevant technical reviewers from exported role text, and personalizes the approved resume-review request without an LLM. It may display the 111 exported emails only in this explicitly approved private screen; it never automates contact or sends those values to an LLM/log.
- Job intelligence: an explicit per-row modal checks cached official-job research first, keeps alert-to-posting identity separate from resume eligibility, and never runs in the background.
- Resume tailoring: a second explicit Luna action receives only contact-free professional evidence. The local editor preserves the private original, changes the professional summary, reorders existing skills/work bullets, and may add one deterministic Skills line containing only exact JD labels backed by explicit user-confirmed notes. Confirmed notes are kept in the private Drive Resume Library; every draft requires user review.
- Scheduling: none initially; GitHub Actions can be added after manual runs are stable.

## Core fields

Keep these normalized fields stable even if the UI allows optional export columns:

- job record ID;
- alert source (`linkedin` or `naukri`);
- Gmail message ID;
- email subject and received time;
- company;
- job title;
- location;
- years of experience when supplied, its provenance, parsed numeric bounds, and target-fit status;
- alert-provided posting date when supplied;
- source job URL;
- official employer URL when the alert explicitly supplies one;
- current-run change status (`new`, `changed`, or `previously_seen`) for Company Portal and ATS jobs;
- first seen and last seen times;
- parse confidence/status;
- application status and user notes.

Email received time, alert-provided posting time, and system first-seen time must remain separate fields.

## Initial boundaries

- No direct LinkedIn or Naukri page scraping.
- No browser-login automation or CAPTCHA handling.
- No automatic applications.
- No automatic LLM analysis during Gmail/public-source runs. Deterministic referral context remains preliminary until the user explicitly checks an official JD; optional Luna analysis and resume tailoring run only in the separate per-job tool.
- No arbitrary user-defined replacement of core schema fields; custom columns may be added for display/export.
- No storage of full raw email bodies in the Sheet by default.
- No multi-user accounts, billing, shared tenant database, or unauthenticated public deployment yet.

## Design for future users without overbuilding now

The personal MVP should still use replaceable boundaries:

- an `owner_id` on stored records, set to `personal` for the first version;
- an email-source interface rather than Gmail logic inside parsers;
- separate LinkedIn and Naukri parser modules;
- a storage interface rather than Sheets logic inside parsing;
- per-user configuration and OAuth credentials later;
- no globally shared tokens or cross-user data.

When scaling, move from local state to a database, add authenticated user accounts and per-user OAuth consent, isolate data by tenant, add queues/background workers, and complete a privacy/security review. These are future requirements, not MVP work.

## Access that would eventually be required

- A Google Cloud project.
- Gmail and Google Drive APIs enabled for the current Gmail phase; Google Sheets is needed only by older tracker scripts.
- A Google OAuth client configured for the personal account/test user.
- User consent for the approved scopes.
- A dedicated Gmail label or search query for LinkedIn/Naukri alerts.
- An app-created `Job Hunt` Drive folder; the app creates its `Source` and date subfolders.

No credentials should be provided in chat or committed to Git. Access setup begins only after the design brief is approved.

## Current recommendation

Validate one real small-batch run for each checked source, verify possible-match groups in Job Queue, and confirm edits save to the correct source workbooks. No new API key or OAuth scope is required for the four enabled discovery ATS providers or the exact public Ashby posting lookup; OpenAI is required only for the explicit per-job intelligence actions. Selected official URLs are an identity boundary: exact public ATS records may supply their JD, but related openings cannot supply requirements or eligibility scores. React/FastAPI is now the only supported runtime, with the retired Streamlit file retained under `legacy/` for short-term rollback/reference. The unified UI still calls independent source services and storage boundaries, so a later database/worker migration does not require replacing the interaction model. Before private internet deployment, choose an access-control layer, HTTPS host, stable session secret, and persistent encrypted token/state/resume storage. Add scheduling only after several successful manual runs.

## Documentation roles

- `../AGENTS.md`: concise operating rules loaded first.
- `discussions/NNN_topic.md`: sequential task proposals, decisions, progress, and outcomes.
- `PROJECT_BRIEF.md`: durable direction and boundaries.
- `memory.md`: explicit fixed instructions.
- `queue.md`: unstarted ideas and future work.
- `issues_and_fixes.md`: mistakes, incidents, fixes, and prevention notes.
- `reference/JOB_AUTOMATION_PLAN.md`: detailed research and alternative future designs, consulted selectively.
