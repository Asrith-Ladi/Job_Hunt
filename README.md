# Personal Job Hunt

The supported interface is React + TypeScript with a FastAPI backend. `Run Setup` conditionally configures Gmail alerts, Company Portals, and public ATS sources, then runs only the checked sources. `Job Queue` presents their latest results in one verification-first workspace while preserving every underlying source row and workbook. Likely duplicates are only grouped visually until the user verifies them. Gmail evidence keeps its alert URL separate from the official employer URL. Every job row also has an optional manual tool for official-JD research, separate eligibility scoring, and a truth-preserving tailored-resume draft. `Network Reviews` searches the saved LinkedIn export without creating a run workbook.

The approved Gmail foundation is in [Discussion 001](docs/discussions/001_gmail_alerts_to_google_sheet.md), the dated-workbook behavior in [Discussion 012](docs/discussions/012_streamlit_gmail_run_workbooks.md), the React/FastAPI migration in [Discussion 013](docs/discussions/013_react_fastapi_migration.md), the public-discovery phases in [Discussion 014](docs/discussions/014_company_portals_and_ats_sources.md), the manual job-intelligence boundary in [Discussion 018](docs/discussions/018_streamlit_retirement_and_job_intelligence.md), and the unified workflow in [Discussion 019](docs/discussions/019_unified_run_setup_and_job_queue.md). The large [automation plan](docs/reference/JOB_AUTOMATION_PLAN.md) remains background reference only.

## Current status

- React production build: passing.
- Existing Python Gmail/parsing/workbook modules: retained.
- FastAPI application-service and HTTP boundary: implemented and tested.
- Gmail parsing, within-run deduplication, and cross-run new/changed filtering: implemented.
- Each successful run creates `Job Hunt/YYYY-MM-DD/gmail_alerts_YYYY-MM-DD_HHMMSS.xlsx` in Drive.
- `Job Hunt/Source` stores the canonical company registry and non-secret Gmail seen state; OAuth credentials, tokens, and raw email bodies are excluded.
- Run Setup shares role, location, recency, experience, and result-limit intent while revealing only the settings needed by checked sources; each source completes or fails independently.
- Job Queue supports search and useful review views, wraps long content, keeps official and alert links clickable, preserves every source row, visually groups unverified possible duplicates, and saves supported edits back to the correct source workbook and Drive file.
- Gmail rows are enriched offline from the saved LinkedIn snapshot with a cautious same-company referral lead, clickable profile, preliminary resume evidence, and a copy-ready LinkedIn request; connection emails and phones are excluded.
- Company Portals loads all 210 unique registry companies, limits each manual batch to 10, prefers a documented structured source, then uses bounded official feed/JSON-LD/static/sitemap fallbacks.
- ATS Sources supports Greenhouse, Lever, Workable, and SmartRecruiters public adapters plus explicit detection-only fallbacks for undocumented company-specific platforms.
- Manual analysis resolves UUID-based Ashby employer pages through the exact documented public posting feed, prohibits related-job substitution, and retains only skill labels backed by evidence from that exact JD.
- Company Portal and ATS title/keyword filters use comma-separated alternatives with word/phrase-aware matching against available title, description, and department evidence; short terms such as `ai` do not match inside unrelated words.
- Every currently matching Company Portal or ATS job is included in the dated workbook and Job Queue with a `new`, `changed`, or `previously_seen` run status. Incremental fingerprints classify jobs but no longer hide valid targeted-search results.
- Network Reviews lists all 3,486 saved connections, including 3,448 LinkedIn profile links and 111 explicitly requested exported emails. All 18 columns are initially visible, names open LinkedIn, shared greeting/body templates support placeholders, and every row has a Copy message action; no LLM or Google connection is used.
- Both public-discovery workbooks contain `Jobs`, `Source Checks`, and `Run Summary`; only application status and notes are editable.
- Incremental state and generated Excel artifacts remain independent for Gmail, Company Portals, and ATS Sources even though their latest rows are reviewed together; current public-source matches remain visible without being mislabelled as new.
- Every Gmail, Company Portal, and ATS result row has a manual `Official JD + resume` action. Opening it is free; official research and resume tailoring are separate explicit Luna actions with private caches.
- Official-posting identity and resume eligibility remain separate scores. The React panel shows the verified official URL, JD summary, requirements, documented matches, and honest gaps.
- The private immutable baseline and references are stored in the app-owned Drive Resume Library. For an exact missing JD skill, the UI accepts a factual note and explicit confirmation; only confirmed, contact-free evidence may cross the resume-planning boundary.
- Generated DOCX drafts preserve the original package/contact header, replace only the summary, reorder existing skills/work bullets, and may add one verified `Additional Skills` line containing the confirmed exact JD keywords. The baseline is never modified.
- Generated drafts can be downloaded or optionally uploaded to `Job Hunt/YYYY-MM-DD/Resumes` and always require user review; the app never submits applications.
- Python verification: 126 tests pass. Full Ruff checks and the React TypeScript production build pass; the existing Word open/export, two-page visual render, and DOCX structural checks remain covered by the test suite.
- Live bounded adapter checks passed for all four enabled public ATS providers on 2026-08-02.
- Streamlit is retired from the runtime and dependency list. Its final implementation remains only in [legacy/streamlit_app.py](legacy/streamlit_app.py) as a rollback/reference artifact.

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
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open `http://localhost:8000`, configure the checked sources in **Run Setup**, and start a focused manual run. Completed source results open in **Job Queue**; a failure in one checked source does not discard the others. Expand a job unit to inspect every preserved source record, verify possible duplicate groups, compare the Gmail alert URL with the official employer URL, edit status/notes, and save changes to their original Excel/Drive workbooks. Gmail records show offline referral suggestions when a cautious same-company match exists. Network Reviews needs no Google connection: filter the offline profiles, verify a saved profile, and copy the personalized resume-review request.

Use **Official JD + resume** only for a job you want to inspect. The first button reuses a cached result, resolves an exact supported public ATS record, or performs one exact-only Luna web-research call; it does not automatically generate a resume. Review the official candidate and separate eligibility score. For a listed missing skill you truly used, add a factual note and tick the accuracy confirmation; otherwise leave it unconfirmed and it will remain excluded. Generate only the selected DOCX, PDF, and/or cover-letter outputs when wanted. Confirmed notes are saved to the private Drive Resume Library for later reuse, and the baseline remains immutable. See [OpenAI access setup](docs/setup/OPENAI_ACCESS.md).

Normal Gmail, Company Portal, ATS, and Network runs do not invoke an LLM. Luna runs only behind the explicit per-job buttons; it never receives Gmail bodies/identifiers, alert URLs, resume contact details, or connection/contact data. The app does not log into employer sites, execute careers-page JavaScript, bypass access controls, modify Gmail, or submit applications. Company and ATS runs stop safely on authorization blocks and retain an auditable fallback in `Source Checks`.

## Frontend development

FastAPI serves the last compiled frontend. While changing React code, run the two development processes separately:

```powershell
# Terminal 1
cd D:\Projects\job_hunt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2
cd D:\Projects\job_hunt\frontend
npm.cmd run dev
```

Open `http://127.0.0.1:5173`. Rebuild with `npm.cmd run build` before using the one-process FastAPI version again.

## Verification

```powershell
cd D:\Projects\job_hunt
.\.venv\Scripts\python.exe -m unittest discover -s tests -t .
.\.venv\Scripts\ruff.exe check backend\main.py src\job_hunt\job_intelligence.py src\job_hunt\openai_config.py src\job_hunt\resume_docx.py src\job_hunt\integrations\openai_research.py tests\test_api.py tests\test_job_intelligence.py tests\test_openai_config.py tests\test_resume_docx.py

cd frontend
npm.cmd run build
```

Do not expose the current local server directly to the public internet. Private deployment still needs an approved access-control layer, HTTPS, persistent encrypted OAuth/state storage, and a stable `JOB_HUNT_SESSION_SECRET`.
