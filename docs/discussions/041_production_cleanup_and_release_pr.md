# 041 - Production cleanup and release PR

Date: 2026-09-01
Queue item: Q-051
Status: implementation in progress

## Request

Remove unused code and files, verify the complete accumulated application change set, open a
well-described pull request, and merge it.

## Cleanup boundary

- Delete only files and selectors proven unused by the supported React/FastAPI application.
- Preserve ignored credentials, OAuth tokens, private Gmail/resume/LinkedIn inputs, Drive
  caches, generated user artifacts, historical discussion records, and compatibility readers.
- Keep supported registry, workbook-migration, fixture-sanitization, and diagnostic utilities
  when they still have imports, tests, or an explicit recovery purpose.

## Implemented cleanup

- Removed the retired `legacy/streamlit_app.py` executable and its legacy-folder README.
- Removed stale CSS for retired navigation, discovery panels, tables, planned pages, duplicate
  search controls, and obsolete popover containers while retaining dynamic status selectors.
- Removed an unused React map callback parameter.
- Enabled TypeScript `noUnusedLocals` and `noUnusedParameters` so future dead declarations fail
  the production build.
- Removed stale ignored JavaScript/type outputs previously emitted beside `vite.config.ts`.
- Updated durable documentation so numbered migration discussions remain the rollback history
  instead of shipping an unused executable application.

## Verification and release

Pending final full-suite verification, branch creation, commit, remote pull request, required
check review, and merge. No secrets or private runtime files may enter the commit.
