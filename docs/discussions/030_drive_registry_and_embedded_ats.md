# Drive registry authority and embedded ATS discovery

Date: 2026-08-20
Queue item: Q-040
Status: implemented

## Request

CRED had a visible `fund settlements` opening at `https://careers.cred.club/openings`,
but a Company Portal search returned no result after the careers URL was corrected in Excel.
The user also confirmed that the deployed site should depend on the app-owned Drive registry,
not a repository-local workbook.

## Cause

Two independent gaps combined:

1. The CRED page's server HTML exposes its openings inside public Next.js JSON rather than
   ordinary job-card anchors. The existing generic parser read JSON-LD and static links but
   ignored `__NEXT_DATA__`.
2. The backend read the local registry and uploaded it to Drive during Gmail and discovery
   runs. This made the supposed cache authoritative and could overwrite a newer Drive edit.

## Implementation

- `Job Hunt/Source/Company_Source_Registry.xlsx` is now authoritative.
- The backend checks the app-visible Drive file metadata and MD5 checksum whenever the
  registry is loaded or a selected company run begins.
- A changed remote workbook is downloaded to a candidate file, validated as the complete
  five-table/210-company registry, and only then atomically replaces the private runtime cache.
- A failed download or validation retains the last validated cache and returns a visible
  warning instead of corrupting the active registry.
- Normal Gmail, Company Portal, and ATS runs no longer upload the registry. The bootstrap
  script uploads the seed only when the Drive file does not exist.
- Run Setup shows whether Drive or the fallback cache is active, links to the Drive workbook,
  and provides an explicit **Refresh registry** action.
- The generic public-page parser now recognizes exact Lever-shaped job records inside public
  Next.js/application JSON, normalizes them through the same Lever record builder, and still
  applies the user's keyword, location, recency, and experience settings.

The local `.xlsx` is therefore an implementation cache required by the Python Excel parser,
not the durable source of truth.

## CRED verification

The real app-owned Drive registry loaded as `drive_current` and contained CRED's corrected
`https://careers.cred.club/openings` URL. A live production-class search for `fund` returned
one exact result through `embedded_structured_json`:

- title: `fund settlements`
- location: `bengaluru`
- provider: `lever`
- official URL: `https://jobs.lever.co/cred/7aba55a4-0457-47b7-bb49-9d9ecf514cc1`

No browser login, page JavaScript execution, API key, LLM, or protected-site scraping was used.

## Verification

- 152 Python tests pass, including changed/current/invalid Drive registry cases and an embedded
  Lever regression fixture.
- Full Ruff checks pass.
- The React TypeScript/Vite production build passes.
- The live Drive registry revision and live CRED `fund` result were verified on 2026-08-20.
