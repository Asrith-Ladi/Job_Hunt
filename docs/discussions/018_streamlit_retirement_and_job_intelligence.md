# 018 - Streamlit retirement and manual job intelligence

> 2026-08-17 update: the dated resume destination described below is historical. Generated
> application documents now use the company-first hierarchy in Discussion 024.

## Request

Proceed with pending item 7 (retire Streamlit after the React migration) and item 6
(add a manual per-job action for official JD retrieval, eligibility analysis, and a
tailored resume). Keep the application independent of Codex, cost-conscious, truthful,
and suitable for later private deployment.

## Decision brief

The user approved both actions. They were implemented in this order:

1. React/FastAPI became the only supported runtime. The final Streamlit file moved to
   `legacy/streamlit_app.py`; its dependency and active tests/run instructions were removed.
2. Each Gmail, Company Portal, and ATS result row gained an `Official JD + resume` button.
3. Opening the panel is free. Official research and resume generation are separate explicit
   actions so a resume call never happens merely because a job was viewed.

## Official-job and eligibility behavior

- Server configuration prefers `OPENAI_API_KEY`/`OPENAI_MODEL`, then the Git-ignored `.env`.
  The old `.streamlit/secrets.toml` fallback was removed during the production package
  refactor after its supported values were migrated without exposing the key.
- `gpt-5.6-luna` remains the cost-conscious default.
- The existing official-job researcher is reused. It sends only allowlisted normalized job
  facts and, when present, a validated official-employer URL hint; alert/source URLs and
  private Gmail fields are excluded.
- Research is cached by normalized facts. Reopening an unchanged job reuses the cache;
  `Refresh with Luna` requires an explicit confirmation.
- Up to three official candidates may be returned. Every candidate shows active status,
  official URL, JD summary, requirements, dates/experience when available, and evidence
  confidence.
- Alert-to-official identity score and resume eligibility score remain separate and are
  labelled independently in the UI.
- Eligibility remains deterministic and explainable, showing component points, documented
  matches, experience context, and honest gaps.

## Tailored-resume behavior

- The existing baseline was copied to the Git-ignored `.secrets/base_resume.docx`. The React
  panel can safely replace it with another validated `.docx` for later use/deployment.
- Resume generation is a second explicit action after selecting an official candidate.
- OpenAI receives only contact-free Professional Summary, Technical Skills, and Work
  Experience evidence plus public official-job details and the deterministic eligibility
  result. It does not receive the DOCX, name, contact header, profile links, Gmail content,
  or connection/contact data.
- The model returns a strict plan: one supported summary, an ordering of existing skill IDs,
  an ordering of existing work-bullet IDs, supported keyword alignment, and change notes.
- Server validation rejects unsupported numeric claims or explicit missing-skill claims and
  falls back to the original summary when necessary.
- The DOCX editor copies the original package, preserves the contact/header and formatting,
  replaces only the summary, and reorders only existing skill/work-bullet paragraphs.
  Evidence cannot be created, rewritten, or removed by the model.
- Drafts stay under private `.secrets/job_intelligence/tailored_resumes`, are downloadable,
  and can optionally upload to `Job Hunt/YYYY-MM-DD/Resumes` through the existing `drive.file`
  permission. The UI always labels them as requiring user review; no application is submitted.

## API/UI surface

- `GET /api/job-intelligence/status`
- `POST /api/job-intelligence/baseline-resume`
- `POST /api/job-intelligence/analyze`
- `POST /api/job-intelligence/resumes`
- `GET /api/job-intelligence/resumes/{resume_id}/download`

The React client never receives the OpenAI key, Google token, raw resume path, analysis cache
path, or private document contents other than the explicitly downloaded generated DOCX.

## Verification

- 117 Python tests pass, including configuration precedence, private input allowlisting,
  cache/service behavior, API routes, DOCX validation, evidence preservation, unsafe-summary
  fallback, and tailored-resume download.
- Focused Ruff checks pass.
- The React TypeScript/Vite production build passes.
- The real private baseline and a structurally tailored copy both open in Microsoft Word and
  export to PDF. Both render as two pages; all four pages were visually inspected with no
  clipping, overlap, broken bullets, missing contact/header content, or layout corruption.
- Section audit confirms one A4 portrait section with the original margins. Style lint shows
  the template's existing direct formatting/Aptos design; tailoring did not introduce a new
  style system.
- The in-app browser was unavailable in this session, so no interactive browser click-through
  is claimed. FastAPI direct health/status checks, route tests, and the production build pass.
- No live Luna research or resume-planning call was made during implementation verification,
  so no paid job action was triggered by Codex.

## Status

Implementation is complete locally. Restart FastAPI and hard-refresh the browser to load the
new backend routes and compiled React assets. A real user-triggered job analysis remains the
final live acceptance check before private deployment.
