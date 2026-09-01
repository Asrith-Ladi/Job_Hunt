# Issues and fixes

This log records mistakes, project incidents, durable fixes, and prevention rules that may help future work.

## Entry format

```text
### I-NNN — Short title
- Date:
- Status: open | mitigated | resolved
- Area:
- Symptom:
- Cause:
- Fix:
- Prevention:
- Evidence/related task:
```

## Recorded issues

### I-001 — Oversized plan treated as fixed context

- Date: 2026-07-19
- Status: resolved
- Area: documentation/context cost
- Symptom: The detailed automation plan was too large for routine reading and contained earlier design assumptions that could become stale.
- Cause: It was originally labeled the permanent source of truth.
- Fix: Created concise operating, brief, task, queue, and memory documents; reclassified the large plan as selective reference.
- Prevention: Read the active discussion and brief first; search the reference plan only for relevant sections.
- Evidence/related task: `PROJECT_BRIEF.md`, `memory.md`, `reference/JOB_AUTOMATION_PLAN.md`.

### I-002 — Ambiguous document move

- Date: 2026-07-19
- Status: resolved
- Area: file operations
- Symptom: A request mentioning `*_implementation.md` did not match an existing file, while the intended file was `JOB_AUTOMATION_PLAN.md`.
- Cause: The likely filename was assumed before the exact path was confirmed.
- Fix: The user supplied the exact path and the plan was placed under the `job_hunt` project.
- Prevention: Resolve and show exact source/target paths before moving an ambiguously named file.
- Evidence/related task: Project file history.

### I-003 — Broad recursive workspace scans stalled

- Date: 2026-07-19
- Status: resolved
- Area: tooling
- Symptom: Recursive PowerShell searches across `D:\Projects` timed out.
- Cause: The workspace contains many unrelated projects.
- Fix: Restrict searches to `D:\Projects\job_hunt` and use exact paths or `rg --files` filters.
- Prevention: Never scan the entire workspace when the active project root is known.
- Evidence/related task: Documentation organization.

### I-004 — PowerShell foreach output was piped directly

- Date: 2026-07-19
- Status: resolved
- Area: tooling
- Symptom: Read-only validation commands failed with “An empty pipe element is not allowed.”
- Cause: A PowerShell `foreach` statement was piped without first assigning its output.
- Fix: Assign `foreach` output to a task-specific results variable, then pipe that variable.
- Prevention: Use `$results = foreach (...) { ... }` followed by `$results | ...`.
- Evidence/related task: Documentation validation.

### I-005 — Reference plan could not be renamed by the current sandbox identity

- Date: 2026-07-19
- Status: resolved
- Area: filesystem permissions
- Symptom: Windows denied `Move-Item` for the large plan while other documentation moved normally.
- Cause: Likely ownership/ACL inherited from an earlier sandbox identity; the file remained readable and was not read-only.
- Fix: Copied it into `docs/reference/`, verified matching SHA-256 hashes, then removed the redundant root copy through the patch workflow.
- Prevention: Create new project files under the active project identity and verify hashes before any copy/delete workaround.
- Evidence/related task: `reference/JOB_AUTOMATION_PLAN.md`; no root-level duplicate remains.

### I-006 — Installed Python is below current integration requirements

- Date: 2026-07-19
- Status: resolved
- Area: local runtime
- Symptom: The machine exposes Python 3.8 and does not have Streamlit or Google client libraries installed.
- Cause: Current Streamlit and Google's current Gmail Python quickstart require newer Python versions.
- Fix: Python 3.12 and the project-local virtual environment are installed; the Streamlit and Google integrations run successfully.
- Prevention: Record and verify the supported runtime before dependency installation; keep dependency-free core tests runnable where practical.
- Evidence/related task: `README.md`, Discussion 001.

### I-007 — Real alert layouts are not available as safe fixtures

- Date: 2026-07-19
- Status: resolved
- Area: parsing fidelity/privacy
- Symptom: The conservative parsers can extract direct supported job links but cannot reliably map company, location, experience, or portal redirect links.
- Cause: LinkedIn and Naukri alert email layouts vary and no redacted samples have been supplied.
- Fix: One raw EML per source was staged under neutral Git-ignored names, sanitized derivatives were created, and minimal synthetic regression fixtures now cover both observed card layouts.
- Prevention: Never infer unstable email markup; require sanitized fixtures and keep private recipients, tokens, and tracking parameters out of Git.
- Evidence/related task: Discussion 001 parser-fixture blocker.

### I-008 — Initial Sheet scope was broader than the create-only MVP needs

- Date: 2026-07-19
- Status: resolved
- Area: OAuth permissions
- Symptom: The first scaffold requested the all-spreadsheets scope while also offering arbitrary existing-Sheet IDs.
- Cause: Existing-Sheet convenience was combined with the create-a-Sheet MVP before the access surface was reviewed.
- Fix: Use `drive.file`, create and remember an app-owned Sheet, and defer arbitrary file selection to a per-file Picker flow.
- Prevention: Review a permission matrix before the first live consent and treat every scope expansion as a user decision.
- Evidence/related task: `src/job_hunt/integrations/google_auth.py`, Q-006.

### I-009 — Nested PowerShell quoting broke a validation search

- Date: 2026-07-19
- Status: resolved
- Area: tooling
- Symptom: A read-only `rg` validation command failed because PowerShell reported an unterminated string.
- Cause: A double-quoted regular expression contained an embedded quote across the command-encoding layers.
- Fix: Re-ran the expression in PowerShell single quotes.
- Prevention: Prefer single-quoted PowerShell regex patterns for `rg` when the pattern contains punctuation or quotes.
- Evidence/related task: Final scaffold validation.

### I-010 — No authorized Gmail read path is currently available

- Date: 2026-07-19
- Status: resolved
- Area: external access
- Symptom: The requested test-label messages cannot be retrieved from Gmail.
- Cause: The Web OAuth client now exists, but this project process still has no credential-path environment variable, supported Python runtime, or local OAuth token.
- Fix: The direct read-only Web OAuth flow is connected and a live dry run successfully read only the two approved labels.
- Prevention: Run an access-presence audit before attempting mailbox ingestion and keep development-tool access separate from deployed-app authorization.
- Evidence/related task: Discussion 001 access audit.

### I-011 — Development Gmail connector was confused with product authorization

- Date: 2026-07-19
- Status: resolved
- Area: architecture/access guidance
- Symptom: A Gmail plugin or browser connection was suggested as one way to unblock the product's mailbox ingestion.
- Cause: Development-time mailbox inspection and the deployed application's runtime authorization were treated as interchangeable.
- Fix: The application now uses direct Google Web OAuth and Gmail API code. A Codex Gmail plugin may assist an interactive chat session but is never a product dependency.
- Prevention: For every connector, state whether it belongs to development tooling or the deployed runtime before recommending it.
- Evidence/related task: `memory.md` rules 15–16 and Discussion 001.

### I-012 — OAuth consent succeeded but the token exchange failed

- Date: 2026-07-19
- Status: resolved
- Area: Google Web OAuth / PKCE
- Symptom: Google showed the consent approval, then the app reported that authorization could not be completed and created no token.
- Cause: `google-auth-oauthlib` generated a PKCE code challenge automatically, but the app rebuilt the callback flow without restoring the matching short-lived code verifier.
- Fix: Persist the verifier beside the one-time OAuth state, consume both within ten minutes, and pass the verifier into the authorization-code exchange.
- Prevention: A regression test now confirms the generated verifier survives the callback round trip and is forwarded to the exchange flow.
- Evidence/related task: `tests/test_google_auth.py`; Discussion 001.

### I-013 — First sanitizer pass retained profile-context text

- Date: 2026-07-19
- Status: resolved
- Area: fixture privacy
- Symptom: Names and addresses were redacted, but a LinkedIn footer still retained the recipient's profile-headline context in the first sanitized derivative.
- Cause: The initial sanitizer targeted direct identifiers and tracking values but not the complete “email was intended for” context sentence.
- Fix: The entire footer context is replaced with `REDACTED_PROFILE_CONTEXT`; the derivative was regenerated and searched for the removed terms.
- Prevention: A regression test covers the full footer removal, and sanitized files must pass contextual privacy searches before structural inspection.
- Evidence/related task: `scripts/sanitize_eml_fixture.py`, `tests/test_sanitize_eml_fixture.py`.

### I-014 — Project virtual environment referenced a missing Python installation

- Date: 2026-07-19
- Status: resolved
- Area: local runtime
- Symptom: `.venv\Scripts\python.exe` could not start while beginning the six-alert pilot.
- Cause: The virtual environment still referenced a removed standalone Python 3.12 path.
- Fix: Rebound the environment to the existing Conda Python 3.12 installation and verified the project launcher, Google libraries, Streamlit, and full test suite.
- Prevention: Verify `.venv\pyvenv.cfg` and the interpreter path before diagnosing application code; prefer a stable Python installation for project environments.
- Evidence/related task: Discussion 003; 38 tests pass through `.venv\Scripts\python.exe`.

### I-015 — A merged title crossed the dated tab's frozen-column boundary

- Date: 2026-07-19
- Status: resolved
- Area: Google Sheets formatting
- Symptom: Google created the sample workbook and accepted its values, but rejected the atomic formatting batch with `You can't merge frozen and non-frozen columns`.
- Cause: The title and subtitle attempted to merge columns A:S while columns A:C were frozen.
- Fix: Keep the three useful review columns frozen and style the full title rows without cross-boundary merges; repair and verify the original recoverable workbook rather than create a duplicate.
- Prevention: Do not merge a range across a frozen row or column boundary in Sheets API formatting requests.
- Evidence/related task: `scripts/create_sample_sheet.py`; Discussion 004.

### I-016 — Resume DOCX could not be visually rendered locally

- Date: 2026-07-20
- Status: resolved on 2026-08-03
- Area: resume evidence / document tooling
- Symptom: The supplied resume could not complete the required DOCX-to-page render check.
- Cause: The project environment lacks the render dependency and no LibreOffice or Poppler executable is available.
- Fix: Initially used structural extraction only. The manual resume feature now verifies private DOCX files through Microsoft Word's invisible PDF export, renders every page locally, visually inspects all pages, and retains structural/evidence checks as a second layer.
- Prevention: Require Word/LibreOffice open-and-render verification plus page inspection before claiming a generated resume is usable; keep contact-free extraction and OOXML integrity checks in automated tests.
- Evidence/related task: `scripts/extract_resume_evidence.py`, `src/job_hunt/resumes/docx.py`; Discussions 005 and 018.

### I-017 — Cold-message verifier rejected the improved sign-off

- Date: 2026-07-20
- Status: resolved
- Area: production tracker verification
- Symptom: The refreshed Google tracker was written, but final verification reported zero structured cold messages when 126 were expected.
- Cause: Message generation changed from `Thanks` to the more human `Thank you for your time`, while the verifier still required the old exact ending.
- Fix: Align the verifier with the new structured sign-off and rerun the same dated tracker; all 126 messages then passed.
- Prevention: Treat message structure and its verification predicate as one contract, and update their regression expectations together.
- Evidence/related task: `src/job_hunt/jobs/enrichment.py`, `scripts/build_production_tracker.py`, Discussion 008.

### I-018 — Legacy seed marked new production alerts as already researched

- Date: 2026-07-20
- Status: resolved
- Area: OpenAI research cache / truthfulness
- Symptom: The first full run parsed 500 current alerts but reported all 500 as cache reuse and made zero research calls, even though only a small legacy batch had official mappings.
- Cause: The run overwrote the dated Gmail snapshot before legacy-cache initialization; initialization then copied every ID from that new snapshot into the old research document's checked list.
- Fix: Remove alert-snapshot-based seeding. A no-result cache entry is now trusted only when it has a SHA-256 fingerprint of the normalized company/title/location/experience fields; existing official mappings remain trusted evidence. Repair the private cache with zero API calls, mark 492 current alerts `research_pending`, rebuild the live Sheet, and re-export Excel.
- Prevention: Never infer research completion from membership in an input file. Cache reuse must carry verifiable per-record evidence or a matching input fingerprint, and generated outputs must distinguish `research_pending` from `no_official_result`.
- Evidence/related task: `src/job_hunt/integrations/openai_research.py`, `tests/test_openai_research.py`, `tests/test_production_tracker.py`, Discussion 008.

### I-019 — Assumed job-search paths had moved while the careers homepages remained valid

- Date: 2026-07-31
- Status: resolved
- Area: company-source registry
- Symptom: Several initially assembled direct portal URLs returned 404 or DNS errors even though the companies still had active official career sites.
- Cause: A stable-looking URL pattern was treated as current without following the official careers page's present job-search destination.
- Fix: Re-resolve the job-search link from each official company page and replace moved paths for Deloitte, KPMG, NTT DATA, DXC, Genpact, Publicis Sapient, and TCS before exporting the registry.
- Prevention: Store `Last Checked` and `Verification Status`, distinguish automated blocking from broken links, and revalidate a portal before enabling its adapter.
- Evidence/related task: `scripts/build_company_source_registry.py`; Discussion 009.

### I-020 - Overlapping worksheet and table filters caused Excel repair

- Date: 2026-07-31
- Status: resolved
- Area: company-source registry / Excel OOXML
- Symptom: Desktop Excel opened the registry with a repair warning and removed the table and AutoFilter features from both category sheets.
- Cause: Each category range had both a worksheet-level AutoFilter and an Excel-table-owned AutoFilter over the same cells. The duplicate filter definitions were valid enough for the writer library but not accepted by desktop Excel.
- Fix: Rebuild every category sheet independently and retain only the table-owned AutoFilter. Add OOXML checks that reject worksheet-level filters on table sheets, then open the final workbook in desktop Excel read-only and verify that all five table objects remain present.
- Prevention: Do not assign `worksheet.auto_filter.ref` to a range already represented by an Excel table; require structural, rendered, and desktop-Excel checks before replacing the canonical workbook.
- Evidence/related task: `scripts/build_company_source_registry.py`, `tests/test_company_source_registry.py`; Discussion 009.

### I-021 - LinkedIn application export repeated the applicant's own contact details

- Date: 2026-08-01
- Status: resolved
- Area: LinkedIn export privacy / workbook design
- Symptom: The LinkedIn job-application CSV included email and phone columns on every application row, which could be mistaken for recruiter contact information and unnecessarily duplicated the account owner's self-contact data.
- Cause: Those fields are part of LinkedIn's application record schema, not evidence of an employer or referral contact.
- Fix: Exclude application email, phone, screening questions, and screening answers from the workbook; retain only application date, company, title, original job URL, resume filename, and conservative registry linkage.
- Prevention: Treat export field names as untrusted semantics until their role is confirmed, apply a documented allowlist per imported file, and test that excluded self-contact headers do not appear in generated sheets.
- Evidence/related task: `scripts/linkedin_export_workbook.py`, `tests/test_linkedin_export_workbook.py`; Discussion 010.

### I-022 - React backend requires a new exact Google OAuth callback

- Date: 2026-08-01
- Status: awaiting user configuration
- Area: React/FastAPI migration / Google Web OAuth
- Symptom: The existing Web OAuth client authorizes the former Streamlit callback, while FastAPI receives callbacks at a different port and path.
- Cause: Google Web OAuth redirect URIs are exact; migrating the HTTP boundary changes the callback even though the requested scopes do not change.
- Fix: Add `http://localhost:8000/api/auth/google/callback` to the existing Web OAuth client's authorized redirect URIs, then reconnect once through React.
- Prevention: Treat the callback URI as a deployment-specific setting, keep it in `JOB_HUNT_OAUTH_REDIRECT_URI`, and update Google Cloud before switching UI runtimes or hosts.
- Evidence/related task: `src/job_hunt/api/main.py`, `docs/setup/GOOGLE_ACCESS.md`; Discussion 013.

### I-023 - ATS detection positional fields shifted into the wrong properties

- Date: 2026-08-02
- Status: resolved
- Area: ATS source auto-detection
- Symptom: Provider URLs raised a missing-field error or placed evidence text in `adapter_ready` instead of a Boolean.
- Cause: `DetectionResult` gained an `adapter_ready` field while several constructors still used the older positional argument order.
- Fix: Use explicit keyword arguments for every detection result and add contract tests for documented and detection-only provider URL patterns.
- Prevention: Prefer named construction for multi-field source/security records and test every supported hostname family.
- Evidence/related task: `src/job_hunt/discovery/detection.py`, `tests/test_discovery_sources.py`; Discussion 014.

### I-024 - Workable compatibility endpoint redirected outside the initial allowlist

- Date: 2026-08-02
- Status: resolved
- Area: Workable public adapter / redirect safety
- Symptom: The documented `www.workable.com/api/accounts/...` request stopped safely before returning jobs.
- Cause: Workable currently redirects that compatibility URL to its public widget endpoint on `apply.workable.com`, while the first provider allowlist contained only `www.workable.com`.
- Fix: Add only `apply.workable.com` as a second Workable-owned allowed host and retain HTTPS, public-DNS, size, and redirect-count validation on every hop.
- Prevention: Verify documented compatibility redirects during bounded live pilots; expand provider allowlists only to confirmed provider-owned hosts, never arbitrary destinations.
- Evidence/related task: `src/job_hunt/discovery/adapters.py`; Discussion 014.

### I-025 - First discovery response and workbook used different date/number representations

- Date: 2026-08-02
- Status: resolved
- Area: discovery workbook edit/save contract
- Symptom: A save immediately after a run could report a protected-field change even when the user edited only status or notes.
- Cause: The first API response used in-memory timezone/numeric values, while the subsequent save baseline was reread from Excel's canonical cell representation.
- Fix: After writing and verifying a discovery workbook, reread its rows/checks/summary and return that canonical representation to React.
- Prevention: Use the persisted artifact, not a pre-serialization object, as the editor's immutable baseline; retain the end-to-end run/save regression test.
- Evidence/related task: `src/job_hunt/discovery/service.py`, `tests/test_discovery_service.py`; Discussion 014.

### I-026 - PowerShell policy blocked the npm script shim

- Date: 2026-08-03
- Status: resolved
- Area: React build verification on Windows
- Symptom: `npm run build` stopped before npm started because PowerShell was not allowed to execute `npm.ps1`.
- Cause: Windows command resolution selected the PowerShell shim while the current execution policy disallowed scripts.
- Fix: Run `npm.cmd run build`, which uses the signed Windows command wrapper and completed the TypeScript/Vite production build.
- Prevention: Use `npm.cmd` in this project's Windows PowerShell setup and verification commands.
- Evidence/related task: `README.md`; Discussion 015.

### I-027 - Stale FastAPI process returned frontend HTML to a JSON request

- Date: 2026-08-03
- Status: resolved
- Area: React/FastAPI local runtime
- Symptom: Network Reviews displayed `Unexpected token '<', "<!doctype" ... is not valid JSON` and zero connections.
- Cause: The compiled React page was newer than the still-running FastAPI process. The old backend did not have `/api/network/connections`, so its frontend catch-all returned `index.html` with HTTP 200.
- Fix: Restart FastAPI after backend changes. The shared React request helper now rejects non-JSON success responses with a clear restart instruction instead of exposing a JSON parser error.
- Prevention: Restart the Python process after backend route changes, hard-refresh the browser after a new frontend build, and validate API response content type in the client.
- Evidence/related task: `frontend/src/api.ts`; Discussion 017.

### I-028 - OOXML serializer dropped Word compatibility namespaces

- Date: 2026-08-03
- Status: resolved
- Area: tailored resume / Word compatibility
- Symptom: The first tailored DOCX passed ZIP/XML and evidence checks, but Microsoft Word reported that the file was corrupt and refused the PDF export.
- Cause: Python's standard XML serializer removed unused namespace declarations from `w:document` even though `mc:Ignorable` still referenced those prefixes. The XML remained well formed but violated Word's compatibility expectations.
- Fix: Preserve every original root `xmlns:*` declaration when serializing the edited `word/document.xml`, then regenerate the copy. Word opened the corrected document without repair and exported it successfully.
- Prevention: Never treat ZIP/XML parsing as sufficient DOCX acceptance. Retain original compatibility namespaces and require a real Word/LibreOffice open/export plus visual page verification for the representative template.
- Evidence/related task: `src/job_hunt/resumes/docx.py`, `tests/test_resume_docx.py`; Discussion 018.

### I-029 - Related official job was scored as the selected job

- Date: 2026-08-15
- Status: resolved
- Area: manual official-JD research / eligibility identity
- Symptom: Sarvam `Agent Engineer` displayed OAuth, MCP, RAG, database, and Redis requirements from a different Sarvam role and calculated eligibility against them.
- Cause: Company discovery retained the correct employer URL, but the later Luna web-search call could not read that exact dynamic page and was allowed to return an `active_related` opening. The UI auto-selected the related candidate without making the identity difference prominent.
- Fix: Resolve the exact UUID through Ashby's documented public Job Postings API, extract from that description without web search, require exact-description evidence per skill, cache by exact-source fingerprint, and prohibit related candidates whenever a selected official URL is present.
- Prevention: Treat provider job identity as a hard boundary for JD/eligibility work; related roles may be discovery suggestions only and must never supply requirements or scores for another job.
- Evidence/related task: `src/job_hunt/integrations/ashby_postings.py`, `src/job_hunt/integrations/openai_research.py`, `src/job_hunt/intelligence/service.py`; Discussion 021.

### I-030 - Empty incremental Gmail run hid earlier useful jobs in the UI

- Date: 2026-08-17
- Status: resolved
- Area: Gmail cross-run history / Job Queue navigation
- Symptom: After the first large Gmail run, later identical runs correctly exported few or zero changed jobs, but Job Queue exposed only the latest workbook and offered no way to reopen earlier results.
- Cause: Cross-run fingerprinting intentionally withheld unchanged rows, while the React startup and backend artifact API tracked only `last_gmail_run` even though earlier timestamped workbooks remained on disk and Drive.
- Fix: Add a sanitized durable run-history index, local-workbook backfill, list/load/download APIs, and a Previous Gmail runs menu that remains visible in the zero-row state. Loading an earlier artifact cannot alter deduplication.
- Prevention: Treat incremental state and artifact navigation as separate concerns: deduplicate collection, but always retain a bounded, non-secret index of user-created run artifacts.
- Evidence/related task: `src/job_hunt/gmail/state.py`, `src/job_hunt/gmail/service.py`, `frontend/src/JobQueueTab.tsx`; Discussion 025.

### I-031 - Previous-run safeguard disabled valid application tracking

- Date: 2026-08-17
- Status: resolved
- Area: Gmail run history / application status
- Symptom: After loading an older Gmail workbook, Application status and Review notes were disabled for every job even though the user had not applied yet.
- Cause: The initial history implementation incorrectly equated an older collection artifact with completed/read-only application work.
- Fix: Keep the previous-run indicator, but enable status and notes and save only those two fields back to the selected original workbook. Rebuild all protected job evidence from the workbook, preserve fingerprint state, and do not replace the latest-run pointer.
- Prevention: Separate collection immutability from application lifecycle edits; collection date never determines whether a candidate has reviewed or applied to a job.
- Evidence/related task: `src/job_hunt/gmail/service.py`, `frontend/src/JobQueueTab.tsx`, `tests/test_gmail_service.py`; Discussion 025.

### I-032 - Exact-only comparison treated documented equivalents as unsupported

- Date: 2026-08-17
- Status: resolved
- Area: resume eligibility / tailored resume generation
- Symptom: A JD term could appear as a gap and request user justification even when the active baseline documented the same capability using equivalent wording. Confirmed terms were also collected under a generic `Additional Skills` line, and work bullets were only reordered rather than carefully aligned to supported JD language.
- Cause: Eligibility used a fixed profile and literal labels, while DOCX mutation supported only skill reordering plus one generic appended line. The planner had no validated bullet-rewrite contract.
- Fix: Score against contact-free evidence from the active baseline when available, distinguish exact/equivalent/unsupported terms with an auditable local concept map, place supported terms under relevant skill headings, and allow a small set of source-bullet-specific Luna rewrites guarded by fact, metric, employer, contact, and similarity checks. Keep the literal before/after ATS estimate separate.
- Prevention: Require evidence attribution for every newly inserted JD phrase, distinguish whole-resume support from sentence-level support, invalidate cached plans when the tailoring contract changes, and retain DOCX structural plus behavior tests.
- Evidence/related task: `src/job_hunt/jobs/skills.py`, `src/job_hunt/intelligence/service.py`, `src/job_hunt/resumes/docx.py`, `tests/test_skill_alignment.py`, `tests/test_resume_docx.py`; Discussion 027.

### I-033 - Local registry upload could overwrite a newer Drive edit

- Date: 2026-08-20
- Status: resolved
- Area: company registry / deployment storage boundary
- Symptom: Editing an official careers URL in the Drive registry did not reliably change the site, while every Gmail or discovery run could upload the older local workbook over that Drive file.
- Cause: The repository workbook was treated as the read source and run setup synchronized in the wrong direction, local to Drive. The app had no Drive revision check or visible refresh action.
- Fix: Make the app-created Drive workbook authoritative, compare its metadata/content checksum, download changed content to a candidate, validate all canonical tables before atomically replacing the private local cache, remove registry uploads from normal runs, and expose Drive status plus a manual refresh control in React.
- Prevention: Keep source-of-truth direction explicit in storage services and tests; only seed Drive when the registry is absent, never overwrite it during ordinary processing, and retain the last validated cache when a remote download is invalid or unavailable.
- Evidence/related task: `src/job_hunt/discovery/registry.py`, `src/job_hunt/discovery/service.py`, `src/job_hunt/gmail/service.py`, `frontend/src/RunSetupTab.tsx`, `tests/test_registry_sync.py`; Discussion 030.

### I-034 - Search activity created permanent files before user intent

- Date: 2026-08-20
- Status: resolved
- Area: search lifecycle / Drive persistence
- Symptom: Every Gmail, Company Portal, or ATS search created another dated Drive workbook even when the user was only exploring and had not decided to track or apply to a job.
- Cause: Collection artifacts and application state shared one run-oriented persistence boundary; the UI treated source execution as an export rather than a read-only search.
- Fix: Add non-persisting search service/API paths, keep current results in React memory, and introduce one Drive-backed application queue that is updated only by Save for later, status, note, or confirmed-official-URL actions. Keep old Gmail workbooks as unchanged history.
- Prevention: Model discovery results and tracked applications as different lifecycles. Tests must prove that search creates no workbook/seen-state output and that repeated explicit saves upsert one stable application record.
- Evidence/related task: `src/job_hunt/runtime/application_queue.py`, `src/job_hunt/gmail/service.py`, `src/job_hunt/discovery/service.py`, `frontend/src/App.tsx`; Discussion 031.

### I-035 - Updated search UI called a stale FastAPI process

- Date: 2026-08-20
- Status: resolved
- Area: local runtime / frontend-backend compatibility
- Symptom: Company Portal search reported `Method Not Allowed` even though the selected source was valid.
- Cause: The newly built React bundle called `POST /api/search/company-portals`, but port 8000 was still owned by a pre-change Anaconda Python process whose route table did not include the transient-search endpoint.
- Fix: Stop the stale process and start API version 0.4.0 from the project's `.venv`; verify the route with a real Sarvam `agent` search. The API client now translates a 404/405 from new search routes into an explicit UI/backend version-mismatch instruction.
- Prevention: Restart FastAPI after backend route changes, launch it through the documented project virtual environment, and verify `/api/openapi.json` exposes the expected search method before UI acceptance.
- Evidence/related task: `frontend/src/api.ts`, `src/job_hunt/api/main.py`; Discussion 031.

### I-036 - Dynamic careers page hid an embedded public ATS board

- Date: 2026-08-25
- Status: resolved
- Area: company portal discovery / relevance filtering
- Symptom: Observe.AI visibly listed an `AI Agent Engineer` opening, but a Company Portal search for `agent engineer` returned zero jobs.
- Cause: The registry correctly pointed to the employer careers page, but that page rendered 17 jobs from an embedded Greenhouse board. Generic static HTML discovery found no job records. A single search field also gave title phrases and description-only capabilities equal relevance.
- Fix: Detect explicit supported ATS board identities in public careers-page markup, fetch the documented public feed before filtering, split role-title phrases from broader capability terms, rank direct title evidence first, and show extracted-to-matched counts with the detected provider.
- Prevention: Add provider-independent embedded-widget fixtures, verify live public-page detection when a new pattern is introduced, and never report a filtered zero without retaining the upstream extracted count.
- Evidence/related task: `src/job_hunt/discovery/detection.py`, `src/job_hunt/discovery/generic.py`, `src/job_hunt/discovery/adapters.py`, `frontend/src/RunSetupTab.tsx`, `tests/test_discovery_sources.py`; Discussion 033.

### I-037 - Long searches looked frozen while backend work continued

- Date: 2026-08-25
- Status: resolved
- Area: search observability / React-FastAPI interaction
- Symptom: A ten-company ATS or slow careers-page search displayed only `Searching ATS...`; users could not distinguish active work from a stalled request.
- Cause: Search endpoints returned one final response and exposed no intermediate state. The frontend had only a source-level boolean, while useful provider and per-company stages existed inside synchronous service loops.
- Fix: Add a bounded thread-safe progress store and polling endpoint, emit privacy-safe stages from Gmail and discovery services, and render the current item, completed count, matches, elapsed time, progress bar, and recent events in Search.
- Prevention: Every newly introduced long-running search phase must emit a safe stage transition; progress events must never include message content, job descriptions, resumes, credentials, or personal contact data.
- Evidence/related task: `src/job_hunt/runtime/search_progress.py`, `src/job_hunt/gmail/pipeline.py`, `src/job_hunt/discovery/service.py`, `frontend/src/RunSetupTab.tsx`, `tests/test_api.py`; Discussion 034.

### I-038 - Gmail reads were sequential and the Drive registry lacked cached dimensions

- Date: 2026-08-25
- Status: resolved
- Area: Gmail search performance / Network Reviews workbook compatibility
- Symptom: A one-day Gmail search remained at `0 / 2` for more than two minutes, while Network Reviews returned only a generic operation failure.
- Cause: Gmail downloaded every full message through a separate HTTP round trip and emitted no progress until all downloads finished. Separately, the valid Drive-synced registry omitted worksheet dimension metadata, so openpyxl read-only mode exposed `max_row` and `max_column` as `None` and the Network loader raised a `TypeError`.
- Fix: Download full Gmail messages through bounded batches of 25 with one retry for partial failures, a 30-second per-request network timeout, and privacy-safe fetch counts. Force read-only worksheet-dimension calculation when the cache is absent, without rewriting the Drive-authoritative workbook.
- Prevention: Never assume spreadsheet dimension caches are present, and never place a potentially large sequence of remote item reads behind one opaque progress stage. Regression tests cover dimensionless XLSX input, Gmail batching, safe progress, and partial-batch retry.
- Evidence/related task: `src/job_hunt/integrations/gmail.py`, `src/job_hunt/network/referrals.py`, `tests/test_gmail_integration.py`, `tests/test_network_reviews.py`; Discussion 037.

### I-039 - A successful HTTP response could hide an obsolete or manual career source

- Date: 2026-08-31
- Status: resolved in generator; canonical workbook rebuild pending
- Area: company registry / source verification
- Symptom: An old ATS board could return `404`, a careers URL could redirect to a branded error page with HTTP `200`, and bot-protected or company-specific portals could be mistaken for dead links.
- Cause: Registry validation compressed all failures into broad reachability labels and formatted only the status cell. It did not distinguish a proven dead source from a public source that needs browser review or a company-specific adapter.
- Fix: Classify every checked row as `Accessible`, `Manual required`, or `Inaccessible`; detect HTTP 404/410, DNS failures, and error-page redirects as inaccessible; retain access restrictions, timeouts, and undocumented ATS pages as manual; color the entire inaccessible row red and the entire manual row blue. Replace obsolete American Express, Honeywell, Toyota India, and Redis routes with current official sources.
- Prevention: Re-run the bounded public audit before publishing a registry revision, never call an anti-bot response a dead employer page, and keep direct official portals separate from historical discovery metadata.
- Evidence/related task: `scripts/build_company_source_registry.py`, `tests/test_company_source_registry.py`; Discussion 038.

### I-040 - A summary or structured value was archived as the job description

- Date: 2026-09-01
- Status: resolved locally; deployment verification pending
- Area: applied-job evidence / Drive resume folder
- Symptom: `Job_Description.md` could contain only a short AI-generated summary, JSON/Python-shaped text, and unrelated eligibility/document sections, making the actual responsibilities difficult to find.
- Cause: The archive selected `description`, collected alert text, or `description_summary` with a truthy fallback and labeled every non-summary value as full. Generic string conversion serialized containers, and one mixed Markdown document tried to serve human review and machine metadata simultaneously.
- Fix: Normalize only supported description structures; retry an exact public ATS record and then a bounded official-page JSON-LD/embedded/static capture; classify evidence as full, partial, or summary-only; save a readable `Job_Description.docx` plus clean Markdown; retain eligibility and lifecycle metadata in `Application_Details.json`.
- Prevention: Every applied-job package test must assert the capture classification, readable DOCX, clean Markdown, and protected-host boundary. A summary must always carry an explicit review warning and `full_description_available=false`.
- Evidence/related task: `src/job_hunt/integrations/official_descriptions.py`, `src/job_hunt/intelligence/service.py`, `src/job_hunt/resumes/outputs.py`, `tests/test_official_descriptions.py`; Discussion 040.
