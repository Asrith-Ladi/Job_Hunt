# 042 - Searchable company directory worksheet

Date: 2026-09-16

## Requested outcome

Add one compact worksheet to the canonical company registry so the user can quickly find a
company and open its official careers or direct job-search page without navigating across five
detailed category tabs.

## Implemented design

The workbook now opens on `Company Directory`, an alphabetically sorted, filterable table with
one row for each of the 279 unique employers. It includes:

- company;
- registry category;
- sector;
- priority;
- clickable official careers page;
- clickable direct job portal;
- ATS/source type;
- India-jobs availability;
- verification status; and
- last-checked date.

The company name links to the exact row in its detailed category worksheet. The two URL fields
open the official external pages. Users can use Excel table filters or `Ctrl+F` for quick lookup.

## Source-of-truth boundary

`Company Directory` is a generated convenience index. The five detailed category worksheets
remain authoritative for app loading and manual source edits, so the new sheet does not change
the existing Drive-registry contract or introduce duplicate company records.

## Verification

- The directory contains 279 alphabetically sorted company rows and reconciles exactly to the
  five category worksheets.
- All 837 expected company, careers-page, and direct-portal hyperlinks are present.
- The table range is `A4:J283`, with filters and the header frozen at `A5`.
- The application registry loader still reads exactly 279 authoritative entries.
- Workbook ZIP integrity, formula-error scanning, targeted visual review, Ruff, and the relevant
  unit tests pass.

