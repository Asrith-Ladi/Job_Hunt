# Production architecture

The active product is a React application served by a FastAPI backend. Python source is
organized by business capability; feature modules are not placed directly in the
`job_hunt` package root.

## Source packages

```text
src/job_hunt/
  api/            FastAPI schemas, routes, and application composition root
  discovery/      official company and public ATS discovery
  gmail/          Gmail alert search plus historical run/workbook compatibility
  integrations/   Google, Drive, Gmail, Sheets, Ashby, and OpenAI adapters
  intelligence/   explicit AI usage accounting and job/resume orchestration
  jobs/           framework-independent job models, matching, and eligibility rules
  network/        offline connection review and referral workflows
  parsers/        LinkedIn/Naukri email parsers
  resumes/        DOCX evidence, immutable Drive library, and generated outputs
  runtime/        deployment paths, OAuth lifecycle, private state, and application queue
```

`src/job_hunt/api/main.py` is the HTTP composition root. It constructs feature services and keeps
credentials, raw Gmail messages, private resumes, and provider clients behind the server
boundary. The React client receives only sanitized application DTOs.

## Dependency direction

- `jobs` contains deterministic domain rules and cannot import application features.
- `parsers` depend on `jobs`, not on storage or HTTP services.
- `gmail`, `discovery`, `network`, and `resumes` compose domain rules with explicit
  runtime/integration boundaries.
- `intelligence` is an explicit, user-triggered orchestration layer and may use verified
  job, resume, runtime, and provider services.
- `api` is the outer composition layer and must not hold business rules.

`tests/test_package_architecture.py` prevents flat feature modules and reverse imports from
being silently reintroduced.

## Private runtime storage

`.secrets` is only the local development default; it is not a Streamlit dependency. A
deployment must set `JOB_HUNT_RUNTIME_DIR` to a persistent private mount. Optional
`JOB_HUNT_OUTPUT_DIR` and `JOB_HUNT_GMAIL_RUN_DIR` values move generated artifacts;
`JOB_HUNT_REGISTRY_PATH` moves only the validated local registry cache. The authoritative
registry remains the app-created `Job Hunt/Source/Company_Source_Registry.xlsx` Drive file.
The backend compares its Drive revision, downloads only when changed, validates before an
atomic cache replacement, and never uploads the cache during a normal run. OAuth tokens and
private caches must not be stored in Git or a public image layer. The normalized, contact-free
application tracker is intentionally persisted as `Job Hunt/Source/application_queue.json`;
ordinary source searches never create Drive workbooks or update that file.

When the wheel is installed outside the repository checkout, set `JOB_HUNT_PROJECT_ROOT`
to the deployment directory containing `frontend/dist` and non-secret application assets.

## Deployment boundary

Before internet deployment, provide HTTPS, authenticated private access, a stable
`JOB_HUNT_SESSION_SECRET`, environment-managed API/OAuth credentials, and persistent
encrypted runtime storage. Local `.secrets` and `outputs` directories remain Git-ignored
development adapters, not the production persistence design.
