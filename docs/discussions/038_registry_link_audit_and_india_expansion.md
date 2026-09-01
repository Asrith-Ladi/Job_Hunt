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
