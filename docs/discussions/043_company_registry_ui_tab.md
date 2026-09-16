# 043 - Company registry UI tab

Date: 2026-09-16

## Requested outcome

Expose the company source registry as the fifth primary tab in the React interface so the user
can browse and use the registry without opening the workbook for every search.

## Implemented design

The primary navigation now includes `05 Companies`. The page reuses the existing
`/api/registry/companies` response and therefore keeps the app-owned Drive workbook authoritative.
No separate company database or duplicated registry endpoint was introduced.

The page provides:

- five category tabs: MNC, Product Companies, Startups, Mid-Sized Companies, and Other Companies;
- registry counts and accessibility summaries;
- category-scoped text search across company, sector, provider, India availability, and status;
- clickable official careers and direct job-portal links;
- provider, priority, India-jobs, and verification context;
- Drive-registry refresh and direct workbook access; and
- company selection that carries into the existing Company Portal search, preserving the
  configured ten-source limit.

Each category area also provides `Select all shown` and `Clear area` controls. Bulk selection
respects the same ten-source search limit; when an area contains more companies, it fills only
the remaining available slots instead of creating an invalid search request. The Company Portal
and ATS selectors on the Search page use the same bulk-selection behaviour.

The page is responsive: category tabs scroll horizontally on narrow screens and the company
table retains deliberate horizontal scrolling for its source fields.

## Verification

- The production TypeScript/Vite build passes.
- Nineteen API and discovery tests pass.
- The running API returns all 279 Drive-backed registry entries, with the expected category
  counts and no missing careers or portal URLs.
- The in-app browser was unavailable during implementation, so final interactive visual
  confirmation remains a local manual check at `/?tab=company_registry`.
