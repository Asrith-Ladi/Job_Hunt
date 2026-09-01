# Personal Job Hunt

The supported interface is React + TypeScript with a FastAPI backend. `Search` conditionally configures Gmail alerts, Company Portals, and public ATS sources, then searches only the checked sources. `Results` contains only the current or explicitly loaded search records. `Applications` contains only the permanent Drive-backed queue, with saved-for-later, preparing, applied, and closed views. Likely duplicates are only grouped visually until the user verifies them. Search itself creates no Drive workbook: Save for later, status changes, notes, and confirmed official URLs upsert one source record into `Job Hunt/Source/application_queue.json`. Existing dated Gmail files remain available as history. Every job row also has an optional manual official-JD, eligibility, and truth-preserving resume tool. `Network Reviews` searches the saved LinkedIn export without creating a run workbook.

The active search/persistence design is in [Discussion 031](docs/discussions/031_transient_search_and_application_queue.md), with embedded-ATS/ranked search and live progress in Discussions 033 and 034. The Gmail foundation, React/FastAPI migration, public discovery, manual job-intelligence boundary, unified workflow, and AI cost accounting remain documented in Discussions 001, 013, 014, 018, 019, and 026. The large [automation plan](docs/reference/JOB_AUTOMATION_PLAN.md) remains background reference only.

The Python application is organized as bounded production packages rather than flat or
demo modules. See [Production architecture](docs/ARCHITECTURE.md).

## Current status

- React production build: passing.
- Python source is divided into tested `gmail`, `jobs`, `network`, `resumes`, `intelligence`, `runtime`, `discovery`, `integrations`, and `parsers` packages.
- FastAPI application-service and HTTP boundary: implemented and tested.
- Gmail parsing and within-search deduplication are implemented; legacy cross-run workbooks remain reviewable but the active search path does not create or filter through them.
- Explicit tracking actions upsert `Job Hunt/Source/application_queue.json`; ordinary source searches create no dated Drive artifact.
- `Job Hunt/Source/Company_Source_Registry.xlsx` is the authoritative company registry. The backend downloads a changed Drive revision into a validated private runtime cache; normal Gmail, Company Portal, and ATS runs never upload that cache over the Drive workbook.
- Search shares role phrases, broader JD capability terms, location, recency, experience, and result-limit intent while revealing only the settings needed by checked sources. One primary action starts the selected sources; lower-frequency recency, experience, and source-limit controls stay under Advanced filters. Each source completes or fails independently without creating a per-search artifact.
- Results supports current-search review, while Applications supports permanent text/source/stage views and status updates. Both wrap long content, keep official and alert links clickable, preserve every source row, and visually group unverified possible duplicates.
- Gmail rows are enriched offline from the saved LinkedIn snapshot with a cautious same-company referral lead, clickable profile, preliminary resume evidence, and a copy-ready LinkedIn request; connection emails and phones are excluded.
- Company Portals loads all 246 unique registry companies, limits each manual batch to 10, prefers a documented structured source, then uses bounded official feed/embedded ATS JSON/JSON-LD/static/sitemap fallbacks. Public Next.js data that contains exact Lever postings is normalized without executing page JavaScript.
- The official-employer selector has counted filters for the five canonical workbook groups plus All and Selected views; category changes preserve the current batch and combine with company/provider search.
- ATS Sources supports Greenhouse, Lever, Workable, and SmartRecruiters public adapters plus explicit detection-only fallbacks for undocumented company-specific platforms.
- Manual analysis resolves UUID-based Ashby employer pages through the exact documented public posting feed, prohibits related-job substitution, and retains only skill labels backed by evidence from that exact JD.
- Company Portal and ATS role phrases use title-first word/phrase-aware matching; broader capability terms search available title, department, and JD evidence and rank below direct title matches. Commas remain OR alternatives, and short terms such as `ai` do not match inside unrelated words.
- Every currently matching Company Portal or ATS job is included in the temporary result set. Saved jobs survive later searches and reloads through stable application IDs.
- Network Reviews lists all 3,486 saved connections, including 3,448 LinkedIn profile links and 111 explicitly requested exported emails. All 18 columns are initially visible, names open LinkedIn, shared greeting/body templates support placeholders, and every row has a Copy message action; no LLM or Google connection is used.
- Live search progress shows the active stage/company or Gmail step, completed count, matches, elapsed time, and recent safe events. Source checks and run summaries remain on screen for the current search; no public-discovery workbook is created by the active UI.
- Temporary result sets remain independent for Gmail, Company Portals, and ATS Sources while their rows are reviewed together; permanent application status is overlaid from the canonical queue by stable source identity.
- Every Gmail, Company Portal, and ATS result row has a manual `Official JD + resume` action. Opening it is free; official research and resume tailoring are separate explicit Luna actions with private caches.
- After generated documents are reviewed and the user applies manually, `I applied — save JD & details` writes a readable `Job_Description.docx`, clean `Job_Description.md`, and machine-readable `Application_Details.json` into that exact Drive resume folder and then marks the canonical tracked job applied. The capture is explicitly labeled full, partial, or summary-only; a summary is never presented as a complete JD. The application status selector routes post-application stages through this evidence-package action when no package exists.
- Every Luna response records token/cache/reasoning and web-search usage without prompts or private documents. The manual panel shows pre-run ranges, per-action calculated cost, cache hits at zero new cost, and daily/monthly totals; the private ledger is mirrored to `Job Hunt/Source/ai_usage.json` when Drive is connected.
- Official-posting identity and resume eligibility remain separate scores. Eligibility uses the active baseline when available and separates literal JD matches, cautious evidence-backed equivalents, and unsupported gaps.
- The private immutable baseline and references are stored in the app-owned Drive Resume Library. For an unsupported exact JD skill, the UI accepts a factual note and explicit confirmation; only confirmed, contact-free evidence may cross the resume-planning boundary.
- Generated DOCX drafts preserve the original package/contact header, naturally reframe only validated summary/work-bullet evidence, and place supported exact JD wording under the relevant Technical Skills sub-heading. Every metric and underlying fact is preserved, unsupported terms stay excluded, and the baseline is never modified.
- Generated drafts can be downloaded or uploaded to `Job Hunt/Resumes/<Company>/<YYYY-MM-DD>_<Role>/` and always require user review; the app never submits applications.
- Python verification, full Ruff checks, and the React TypeScript production build pass; package-boundary, Drive-registry synchronization, transient-search, application-queue, runtime-path, Word open/export, visual render, and DOCX structural checks remain covered by the test suite.
- Live bounded adapter checks passed for all four enabled public ATS providers on 2026-08-02.
- Streamlit and its retired rollback implementation have been removed. React/FastAPI is the only application runtime shipped by this repository.

## Install

The project uses Python 3.12 and Node.js 22.

```powershell
cd D:\Projects\job_hunt
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .

cd frontend
npm.cmd install
npm.cmd run build
cd ..
```

The compiled frontend is served by FastAPI, so Vite is not needed for normal daily use.

## Google preparation

1. Enable Gmail API and Google Drive API in the existing Google Cloud project.
2. Keep the OAuth client type as **Web application**.
3. Add this exact authorized redirect URI:

   ```text
   http://localhost:8000/api/auth/google/callback
   ```

4. Keep `oauth-client.json` in the project root or set `JOB_HUNT_GOOGLE_CREDENTIALS` to its external path. It is Git-ignored and must not be shared.
5. Keep the production Gmail labels `Job_Alerts/LinkedIn` and `Job_Alerts/Naukari`. The app generates a rolling `newer_than:30d` query by default.

The Google scopes remain `gmail.readonly` and `drive.file`. The React client never receives Google tokens, OAuth client contents, raw email bodies, or Drive credentials.

See [Google access setup](docs/setup/GOOGLE_ACCESS.md) for PowerShell and Command Prompt commands.

## Run the React application

```powershell
cd D:\Projects\job_hunt
.\.venv\Scripts\python.exe -m uvicorn job_hunt.api.main:app --host 127.0.0.1 --port 8000
```

Open `http://localhost:8000`, configure checked sources in **Search**, and start a focused search. After editing the registry workbook in `Job Hunt/Source`, select **Refresh registry**; the site downloads and validates the changed Drive file before replacing its cache. Completed source records open in **Results**; a failure in one checked source does not discard the others. Expand a job unit to inspect source evidence, verify possible duplicates, compare alert and official URLs, then use **Save for later**, change status, or save a note when the job should persist. Only that explicit action updates the canonical Drive application queue and makes the job available in **Applications** after refresh. Gmail records show offline referral suggestions when a cautious same-company match exists.

Use **Official JD + resume** only for a job you want to inspect. The first button reuses a cached result, resolves an exact supported public ATS record, or performs one exact-only Luna web-research call; it does not automatically generate a resume. Review the official candidate and separate eligibility score. Exact wording already present, equivalent documented evidence, and still-unsupported gaps are shown separately. For a listed unsupported skill you truly used, add a factual note and tick the accuracy confirmation; otherwise leave it unconfirmed and it will remain excluded. Generate only the selected DOCX, PDF, and/or cover-letter outputs when wanted. The tailored copy places supported terms in relevant skill categories and may conservatively reframe directly supported sentences while preserving facts and metrics. Confirmed notes are saved to the private Drive Resume Library for later reuse, and the baseline remains immutable. After applying manually, use the post-generation action to archive a readable JD, clean text, and structured details in the same folder. Exact ATS capture and a bounded public official-page capture are attempted before any summary-only fallback, and the UI shows the resulting quality warning; the software never submits the application. See [OpenAI access setup](docs/setup/OPENAI_ACCESS.md).

The same panel shows the initial or rolling pre-run cost range and the calculated cost after each call. Costs use the versioned price snapshot shown in the UI and are not a replacement for the OpenAI billing dashboard. Application totals begin with the first call made after usage metering was enabled; earlier calls are not reconstructed.

Normal Gmail, Company Portal, ATS, and Network runs do not invoke an LLM. Luna runs only behind the explicit per-job buttons; it never receives Gmail bodies/identifiers, alert URLs, resume contact details, or connection/contact data. The app does not log into employer sites, execute careers-page JavaScript, bypass access controls, modify Gmail, or submit applications. Company and ATS runs stop safely on authorization blocks and retain an auditable fallback in `Source Checks`.

## Frontend development

FastAPI serves the last compiled frontend. While changing React code, run the two development processes separately:

```powershell
# Terminal 1
cd D:\Projects\job_hunt
.\.venv\Scripts\python.exe -m uvicorn job_hunt.api.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2
cd D:\Projects\job_hunt\frontend
npm.cmd run dev
```

Open `http://127.0.0.1:5173`. Rebuild with `npm.cmd run build` before using the one-process FastAPI version again.

## Verification

```powershell
cd D:\Projects\job_hunt
.\.venv\Scripts\python.exe -m unittest discover -s tests -t .
.\.venv\Scripts\ruff.exe check src tests scripts

cd frontend
npm.cmd run build
```

Do not expose the current local server directly to the public internet. Private deployment still needs an approved access-control layer, HTTPS, persistent encrypted OAuth/state storage, and a stable `JOB_HUNT_SESSION_SECRET`. Set `JOB_HUNT_RUNTIME_DIR` to the private persistent mount; `.secrets` is only the local default.
