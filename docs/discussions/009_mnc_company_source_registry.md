# 009 - Company-source registry

## Request

Create one Excel workbook that records companies and their official careers pages, direct job portals, and known ATS/API sources. Repair the workbook that Excel was opening by removing unreadable table content, remove unnecessary duplicate companies between categories, and add useful company groups beyond MNCs and established product companies.

## Approved approach

- Maintain one canonical workbook rather than separate MNC and product-company files.
- Classify each company into one primary category so the same employer does not appear on multiple tabs.
- Use five practical categories: `MNC`, `Product Companies`, `Startups`, `Mid-Sized Companies`, and `Other Companies`.
- Treat the catalog as a broad India-relevant search universe, not as a claim to list every company worldwide.
- Keep official careers pages and direct job portals as separate clickable fields.
- Record ATS/source type, stable identifier, and a public API/feed only when confirmed.
- Prefer a live first-party careers page over a stale inferred API or old ATS path.
- Preserve automated-access restrictions and TLS/timeouts as review statuses rather than misclassifying them as missing companies.
- Use the registry before search-engine or LLM-assisted source discovery.

## Delivered workbook

- Canonical path: `outputs/mnc_registry_2026-07-31/Company_Source_Registry.xlsx`
- Registry sheets: `Coverage`, `MNC`, `Product Companies`, `Startups`, `Mid-Sized Companies`, and `Other Companies`.
- LinkedIn export sheets: `LinkedIn Overview`, `LinkedIn Profile`, `LinkedIn Connections`, `LinkedIn Applications`, `LinkedIn Saved Jobs`, `LinkedIn Job Alerts`, and `Followed Companies`.
- Category counts: 65 MNCs, 75 established product companies, 25 startups, 25 mid-sized companies, and 20 other relevant employers.
- Total: 210 unique companies with no duplicate category assignments.
- Final portal check on 2026-08-01: 189 verified live, 12 reachable but restricting automated access, and 9 requiring browser review because of TLS, timeout, or transient server behavior.
- No stored direct job URL returned HTTP 404 in the final pass.
- All 16 stored public API/feed endpoints returned HTTP 200 in the final pass.
- Links are clickable; category tables include filters, frozen headers, wrapped text, validation lists, and status highlighting.
- The `Coverage` tab defines the scope, category rules, counts, live-status totals, and the one-category duplicate rule.
- The two superseded registry workbooks were removed after the canonical file passed verification.

## Excel repair

The damaged workbook wrote one worksheet-level AutoFilter over the same rows already filtered by an Excel table. Excel treated the overlapping filter definitions as unreadable and removed both the table and its filter. The generator now creates each table sheet independently and uses only the table-owned AutoFilter. The extended final file opened in desktop Excel with 13 worksheets and all 10 tables intact.

## Registry fields

`Company`, `Sector`, `Priority`, `Official Careers Page`, `Direct Job Portal`, `ATS / Source Type`, `Source Identifier`, `Public Jobs API / Feed`, `API Key Required`, `India Jobs`, `Active`, `Last Checked`, `Verification Status`, `Fallback`, and `Notes`.

## Coverage rule

There is no finite authoritative list of every MNC or product company worldwide. Coverage verification therefore means that every company in the approved 210-company catalog has exactly one category, HTTPS source links, and a recorded reachability result. New companies remain incremental additions to this maintained catalog.

## Status

Complete. The canonical workbook, generator, LinkedIn export integration, automated tests, rendered previews, OOXML checks, and desktop-Excel compatibility check all passed.
