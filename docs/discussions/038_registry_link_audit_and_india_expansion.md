# 038 - Registry link audit and India company expansion

Date: 2026-08-31

## Requested outcome

Re-test every official company job link, make genuinely inaccessible rows red, make rows requiring browser review or a company-specific/manual adapter blue, and broaden the registry with India-focused product, startup, and mid-sized employers.

## Classification contract

- `Accessible`: the public job/careers URL returned a successful response and does not require a known company-specific adapter. Only the status cell is green.
- `Manual required`: the public page exists but automated access is restricted, the request times out or has a TLS issue, or the ATS/source needs browser review or a company-specific adapter. The complete row is blue.
- `Inaccessible`: the source returns HTTP 404/410, fails DNS, is missing, or redirects to an evident error page. The complete row is red.

This distinction prevents bot protection from being reported as a dead careers page.

## Audit result

The public audit covered all 246 mutually exclusive company rows. After correcting obsolete routes, the final classifications are:

- 155 accessible;
- 91 manual/company-specific;
- 0 remaining inaccessible.

Corrections made during the audit include the current TCS iBegin portal, PwC India careers page, American Express Oracle careers experience, Honeywell Oracle job search, Toyota India careers site, and Redis first-party current-openings page. Redis's former Greenhouse root returned 404 and is no longer configured as a live structured source.

## India-focused expansion

Thirty-six employers were added without cross-category duplicates:

- Product companies: Paytm, MakeMyTrip, IndiaMART, Jio Platforms, MapmyIndia, Juspay, Clear, Games24x7, BookMyShow, MobiKwik, Policybazaar, and Practo.
- Startups: Krutrim AI Labs, Qure.ai, Pixxel, Skyroot Aerospace, Agnikul Cosmos, Atlan, Neysa, Ema, SpotDraft, Sprinto, SuperOps, and Rocketlane.
- Mid-sized companies: Whatfix, Icertis, Mindtickle, CleverTap, MoEngage, Gupshup, Amagi, Hasura, LeadSquared, Darwinbox, Wingify, and GreyOrange.

The resulting category counts are 65 MNCs, 87 product companies, 37 startups, 37 mid-sized companies, and 20 other companies.

## Verification

- Source catalog validation confirms 246 unique HTTPS-based company assignments.
- All 36 added direct job/careers links returned HTTP 200 during the bounded public audit.
- The documented Paytm and Sprinto Lever feeds plus IndiaMART, BookMyShow, and Mindtickle SmartRecruiters endpoints returned HTTP 200.
- Python compilation and Ruff checks pass for the modified generator, registry loader, and tests.
- Canonical XLSX rebuild, visual verification, and Drive replacement remain the final publishing step.

## Infosys dynamic-catalog follow-up — 2026-09-15

The current Infosys India portal renders its job cards from a public, unauthenticated JSON
catalog after the Angular page loads. The initial HTML contains no job records, so the generic
HTML/JSON-LD/sitemap path incorrectly returned zero jobs even though the default role terms
already included `machine learning engineer` and `machine learning`.

The Company Portals flow now recognizes the official `career.infosys.com` host, reads its public
runtime configuration, permits only the expected Infosys careers-data host/path, downloads the
catalog within explicit 8 MiB and 60-second bounds, and applies the existing role, capability,
location, recency, and experience filters locally. This is classified as
`official_company_json`, not as a documented public API, and retains the official careers page as
the fallback because the endpoint can change without notice.

The live catalog check contained 1,654 Infosys Limited postings. It included the Hyderabad
`Senior Machine Learning Engineer` posting (`INFSYS-EXTERNAL-251525`), created 2026-08-22 with a
5–8-year range, so it qualifies under the default 30-day and experience settings as of this
follow-up date. A regression fixture now proves that the default role/capability terms return this
record and preserve its exact official job-detail URL.

## LinkedIn-export employer expansion — 2026-09-15

The private LinkedIn export contains 3,486 connection records and 88 followed-company records,
but 1,946 distinct raw employer strings. The raw values must not be imported blindly because they
include aliases, training providers, recruiter pages, self-employment labels, confidential
employers, and unrelated content pages.

A controlled pass selected 33 additional employers that have useful LinkedIn connection/follow
signals and an official India presence or India-relevant job route:

- MNCs: Verizon, Evernorth Health Services, Optum, Hexaware Technologies, S&P Global, Bristol
  Myers Squibb, Carelon Global Solutions, GlobalLogic, ZF Group, Centific, Chubb, Straive, UBS,
  ICICI Bank, Lloyds Technology Centre India, Sutherland, ADP, Amgen, Novartis, Warner Bros.
  Discovery, Concentrix, The Hartford India, Zensar Technologies, and YASH Technologies.
- Product companies: Splunk, Myntra, National Payments Corporation of India (NPCI), and Phenom.
- Mid-sized companies: ValueLabs, Innominds, Grid Dynamics, Impetus, and Tezo.

Official India job routes were preferred where available. Company-specific Workday, Oracle,
Phenom, SAP SuccessFactors, Zoho Recruit, and Trakstar pages remain documented as such instead of
being misclassified as official public APIs. ValueLabs and Sutherland have public
SmartRecruiters boards; Splunk is retained as a distinct Cisco-owned search brand because it is a
meaningful employer name in the export.

Aliases now map employment-brand variants back to existing registry rows, including LTM to
LTIMindtree, AWS to Amazon, Fractal to Fractal Analytics, JPMorganChase to JPMorgan Chase, and
Infosys BPM to Infosys. This avoids duplicate company rows while preserving the raw LinkedIn
company text in the LinkedIn sheet.

The expanded source catalog contains 279 unique employers: 89 MNCs, 91 product companies, 37
startups, 42 mid-sized companies, and 20 other companies. Against the supplied export, registry
matching rises from 949 to 1,127 connection records and from 37 to 46 followed-company records.
The bounded public audit classified 20 new routes as directly accessible, 13 as browser/manual or
company-specific, and none as inaccessible. Redirect checks also replaced the intermediate
Hexaware, ICICI Bank, and Warner Bros. Discovery links with their current job routes. The
generator, aliases, source counts, HTTPS checks, and representative adapter assertions are
updated.

## Publishing completion - 2026-09-16

The canonical workbook was regenerated with OpenPyXL, structurally checked as an XLSX archive,
and visually reviewed across all 14 worksheets. The complete 279-employer audit classifies 175
routes as directly accessible, 104 as browser/manual or company-specific, and none as
inaccessible. All 23 configured public endpoints responded successfully during validation.

The validated workbook replaced the local source cache and the existing app-owned Drive file in
place. A Drive download read-back produced the same SHA-256 digest as the generated workbook, so
the published content is byte-for-byte verified without creating a duplicate registry file.
