# 014 - Company portals and ATS sources

## Request

Plan and implement the two remaining React source phases after Gmail:

1. company portals from the canonical Excel registry;
2. structured ATS sources.

The user explicitly approved implementation on 2026-08-01 and asked to be told when additional access or information is required.

## Implementation decision

Keep both phases manual and independent. They reuse the Python/FastAPI boundary, React review experience, dated Excel artifacts, app-owned Drive folder, and explicit save behavior established for Gmail.

### Company portals

- Load the 210-company canonical registry from `Company_Source_Registry.xlsx`.
- Let the user search/filter the registry and select at most 10 companies per manual run.
- Prefer an official structured adapter when a high-confidence provider and identifier are available.
- Otherwise inspect only bounded public official feeds, sitemaps, JSON-LD, or static HTML links.
- Never execute page JavaScript, reuse browser cookies, solve CAPTCHA, spoof access, or continue after `401`, `403`, login, or challenge responses.
- Record one source-check row for every selected company, including failures and manual-review fallbacks.

### ATS sources

- Implement documented public adapters in this order: Greenhouse, Lever, Workable, SmartRecruiters.
- Derive identifiers from known public ATS URLs when high-confidence; allow an explicit manual identifier in the ATS tab.
- Detect Workday, Oracle Recruiting Cloud, SAP SuccessFactors, iCIMS, Taleo, Phenom, Eightfold, and Darwinbox, but do not classify their undocumented page endpoints as official APIs.
- Keep those company-specific providers in manual-review/fallback status until an exact public endpoint is separately qualified.

## Run defaults and safety limits

- Maximum selected companies/sources per run: 10.
- Sequential requests with bounded pagination and response sizes.
- Maximum normalized jobs per source: 100 by default.
- Full descriptions are normalized to plain text and bounded before storage/display.
- Unknown publication dates remain visible with explicit provenance; they are not silently treated as recent or expired.
- Keyword, location, and target experience filters are deterministic and optional.
- No LLM call, application submission, employer login, or new Google scope.
- Requests validate HTTPS destinations and block local/private/link-local network targets on every redirect.

## Output layout

```text
Job Hunt/
  Source/
    Company_Source_Registry.xlsx
    company_portal_seen_state.json
    ats_seen_state.json
  YYYY-MM-DD/
    company_portals_YYYY-MM-DD_HHMMSS.xlsx
    ats_sources_YYYY-MM-DD_HHMMSS.xlsx
```

Each workbook contains:

- `Jobs` - normalized, deduplicated jobs with official URLs, descriptions, dates/provenance, deterministic experience fit, application status, and notes;
- `Source Checks` - one auditable outcome per attempted company/source;
- `Run Summary` - counts, filters, run identity, and warnings.

The React screen shows all exported rows, supports search/filter/column selection, and permits only the approved user-maintained edits. An explicit save updates the same local and Drive file.

## Access required

No additional access is required for the first implementation and public-adapter pilots:

- Greenhouse, Lever, Workable public account endpoint, and anonymously available SmartRecruiters postings use no user-provided key.
- Existing `drive.file` permission is sufficient for dated workbooks and state files.

Later access is required only if the user chooses optional sources such as Adzuna, USAJOBS, authenticated Workable SPI, or a private employer integration. Those are out of scope now.

## Definition of done

- Registry browsing returns all 210 unique companies without private LinkedIn tabs.
- Provider detection has contract tests for documented and company-specific ATS patterns.
- Four documented adapters normalize fixture/live public payloads without applications or login.
- Company runs use structured sources first and safe public feed/sitemap/static fallbacks.
- Both phases create/read/update verified dated workbooks and Drive metadata.
- React tabs can run, review, filter, edit, save, download, and open Drive artifacts.
- Failures remain source-specific and never make other jobs appear expired.
- Tests, focused lint, React build, and bounded live pilots pass before handoff.

## Status

Implemented locally on 2026-08-02.

## Delivered

- React Company Portals tab with all 210 registry companies, search/category/provider filters, a 10-source cap, deterministic job filters, on-screen review, source-check diagnostics, edit/save, download, and Drive links.
- React ATS Sources tab with adapter-ready registry entries, optional detection-only rows, and explicit manual Greenhouse/Lever/Workable/SmartRecruiters identifiers.
- FastAPI registry, source-detection, run/latest/get/save/download endpoints kept separate by phase.
- Documented public adapters for Greenhouse, Lever, Workable, and SmartRecruiters; current Workable compatibility redirects are restricted to Workable's own public widget host.
- Structured-first Company Portal discovery with bounded official feed, JSON-LD/static HTML, and sitemap fallbacks.
- HTTPS-only request boundary with public-DNS checks, provider redirect allowlists, response/pagination caps, and safe stops for authorization blocks.
- Independent Drive state files and dated three-tab Excel artifacts for both phases.
- Protected workbook edits: browser updates can change only application status and notes, never source evidence or job identity.

## Verification

- 99 Python tests pass, including registry coverage, provider detection, SSRF/redirect controls, four adapter fixtures, generic JSON-LD discovery, incremental state, workbook structure, Drive-service flow, and API contracts.
- Focused Ruff checks pass.
- React TypeScript production build passes.
- Bounded anonymous live checks returned normalized jobs from Greenhouse, Lever, Workable, and SmartRecruiters.
- The in-app browser was unavailable in this session, so an optional visual click-through remains; it is not an implementation blocker.

## User input/access remaining

Nothing additional is required for the enabled phases. The existing Google connection and scopes are sufficient. Add a manual provider identifier in the ATS tab only when a desired company is missing or unresolved in the registry.
