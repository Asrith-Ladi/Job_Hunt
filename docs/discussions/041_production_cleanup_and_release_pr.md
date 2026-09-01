# 041 - Production cleanup and release PR

Date: 2026-09-01
Queue item: Q-051
Status: complete in PR #1

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

- `python -m unittest discover -s tests`: 171 tests passed.
- `python -m ruff check .`: passed.
- strict TypeScript unused-declaration check: passed.
- production Vite build: passed.
- `git diff --check`: passed with Windows line-ending notices only.
- staged private-data audit: no credentials, OAuth files, personal exports, generated documents,
  workbooks, or secret-key patterns were included.
- browser visual regression was attempted but unavailable because the Codex environment exposed
  no browser session; deployed visual and career-link review remains a rollout check.

The reviewed release was merged through
[PR #1](https://github.com/Asrith-Ladi/Job_Hunt/pull/1) on 2026-09-01 as merge commit
`21dbc5918a7d75dad37f841e288481f0078b1bfa`. GitHub reported the branch clean and mergeable,
with no repository status checks configured. That merge completes Q-051.
