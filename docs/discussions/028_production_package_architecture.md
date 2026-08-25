# Production package architecture

Date: 2026-08-18
Queue item: Q-038
Status: implemented

## Request

The application is a real production-targeted project, not a demo. Organize the Python
source into folders by responsibility and remove the growing flat collection of feature
modules from `src/job_hunt`.

## Decision

Use capability-oriented packages rather than cosmetic folders or duplicate forwarding
modules:

- `jobs`: framework-independent records, matching, experience, and eligibility rules;
- `gmail`: Gmail run configuration, ingestion, state, workbooks, and service;
- `network`: offline connection/referral and profile-review workflows;
- `resumes`: immutable resume library, DOCX evidence/editor, references, and outputs;
- `intelligence`: explicit AI configuration, usage, and per-job orchestration;
- `runtime`: deployment paths, private state/files, and Google OAuth lifecycle;
- `api`: the packaged FastAPI composition root and sanitized HTTP boundary;
- existing `discovery`, `integrations`, and `parsers` packages remain focused boundaries.

All API, script, test, and documentation imports use the new canonical modules. Old flat
modules were moved rather than retained as compatibility wrappers, preventing two supported
locations for the same implementation.

## Production safeguards

- `AppPaths` and Google OAuth no longer live inside the Gmail feature service, so discovery,
  resumes, and intelligence do not depend on Gmail merely to access runtime infrastructure.
- `.secrets` remains the Git-ignored local default only. `JOB_HUNT_RUNTIME_DIR` can point a
  deployment at an encrypted persistent mount; output and registry paths are configurable as
  well.
- An architecture regression test rejects new root-level feature modules and reverse imports
  from the deterministic `jobs` domain.
- Package/project versions are aligned at `0.2.0`, and full-directory lint verification
  replaces a hand-picked file list.
- The FastAPI application is packaged under `job_hunt.api`, so the built wheel contains the
  deployable API instead of depending on an unpackaged repository-level `backend` folder.
- The retired `.streamlit/secrets.toml` fallback was removed after its supported local
  OpenAI values were migrated to the Git-ignored `.env` without displaying the key.

## Deliberately unchanged

This refactor does not change Gmail queries, OAuth scopes, Drive content, workbook schemas,
job matching, resume generation, public-source behavior, or React API responses. It also
does not delete private runtime data or historical scripts without a separate verified
cleanup decision.

## Verification

All 148 Python tests, Ruff checks across source/tests/scripts, package imports, and
the React production build pass after the move.
