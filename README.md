# Personal Job Hunt

The supported interface is React + TypeScript with a FastAPI backend. It keeps three independent job-source tabs—`Gmail alerts`, `Company portals`, and `ATS sources`—plus an offline `Network reviews` tab. Each job-source tab runs only when requested, creates its own timestamped Excel artifact under the current Google Drive date folder, and shows exported rows in an editable browser table. Every job row also has an optional manual tool for official-JD research, separate eligibility scoring, and a truth-preserving tailored-resume draft. Network Reviews searches the saved LinkedIn export without creating a run workbook.

The approved Gmail foundation is in [Discussion 001](docs/discussions/001_gmail_alerts_to_google_sheet.md), the dated-workbook behavior in [Discussion 012](docs/discussions/012_streamlit_gmail_run_workbooks.md), the React/FastAPI migration in [Discussion 013](docs/discussions/013_react_fastapi_migration.md), the public-discovery phases in [Discussion 014](docs/discussions/014_company_portals_and_ats_sources.md), and the manual job-intelligence boundary in [Discussion 018](docs/discussions/018_streamlit_retirement_and_job_intelligence.md). The large [automation plan](docs/reference/JOB_AUTOMATION_PLAN.md) remains background reference only.

## Current status

- React production build: passing.
- Existing Python Gmail/parsing/workbook modules: retained.
- FastAPI application-service and HTTP boundary: implemented and tested.
- Gmail parsing, within-run deduplication, and cross-run new/changed filtering: implemented.
- Each successful run creates `Job Hunt/YYYY-MM-DD/gmail_alerts_YYYY-MM-DD_HHMMSS.xlsx` in Drive.
- `Job Hunt/Source` stores the canonical company registry and non-secret Gmail seen state; OAuth credentials, tokens, and raw email bodies are excluded.
- The React screen supports search, filters, selectable columns, wrapped content, clickable links, approved field edits, Excel download, and explicit same-file Excel/Drive save.
- Gmail rows are enriched offline from the saved LinkedIn snapshot with a cautious same-company referral lead, clickable profile, preliminary resume evidence, and a copy-ready LinkedIn request; connection emails and phones are excluded.
- Company Portals loads all 210 unique registry companies, limits each manual batch to 10, prefers a documented structured source, then uses bounded official feed/JSON-LD/static/sitemap fallbacks.
- ATS Sources supports Greenhouse, Lever, Workable, and SmartRecruiters public adapters plus explicit detection-only fallbacks for undocumented company-specific platforms.
- Network Reviews lists all 3,486 saved connections, including 3,448 LinkedIn profile links and 111 explicitly requested exported emails. All 18 columns are initially visible, names open LinkedIn, shared greeting/body templates support placeholders, and every row has a Copy message action; no LLM or Google connection is used.
- Both public-discovery workbooks contain `Jobs`, `Source Checks`, and `Run Summary`; only application status and notes are editable.
- Incremental state is independent for Gmail, Company Portals, and ATS Sources, so unchanged jobs do not reappear as new rows.
- Every Gmail, Company Portal, and ATS result row has a manual `Official JD + resume` action. Opening it is free; official research and resume tailoring are separate explicit Luna actions with private caches.
- Official-posting identity and resume eligibility remain separate scores. The React panel shows the verified official URL, JD summary, requirements, documented matches, and honest gaps.
- The private baseline resume is stored under `.secrets`; only contact-free professional evidence may be sent for resume planning. Generated DOCX drafts preserve the original package/contact header, replace only the summary, and reorder only existing skills and work bullets.
- Generated drafts can be downloaded or optionally uploaded to `Job Hunt/YYYY-MM-DD/Resumes` and always require user review; the app never submits applications.
- Python verification: 117 tests pass. Focused Ruff checks, the React TypeScript production build, Word open/export, two-page visual render, and DOCX structural checks pass.
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

Open `http://localhost:8000` and choose a tab. For Gmail, Company Portals, or ATS Sources, review the settings and run a small manual batch. Gmail results show offline referral suggestions when a cautious same-company match exists; verify the person's current employer, open their profile, and use **Copy message**. Edit supported cells and use **Save Excel + Drive** to replace the same local and Drive workbook. Network Reviews needs no Google connection: filter the offline profiles, verify a saved profile, and copy the personalized resume-review request.

Use **Official JD + resume** only for a job you want to inspect. The first button reuses a cached result or performs one Luna web-research call; it does not automatically generate a resume. Review the official candidate and the separate eligibility score, then use **Generate tailored DOCX** only when wanted. The baseline resume can be replaced through the private DOCX upload control. See [OpenAI access setup](docs/setup/OPENAI_ACCESS.md).

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
