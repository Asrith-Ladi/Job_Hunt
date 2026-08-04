# Discussion 002 — Job descriptions and LinkedIn network signals

## Task status

- Requested: **Yes, 2026-07-19**.
- Feasibility probe: **Complete**.
- Schema/enrichment implementation: **Decision pending**.

## Requested outcome

Try one LinkedIn and one Naukri job link, place an available job description in a new Sheet column, and retain useful LinkedIn connection information when safely accessible.

## Safe-access findings

- The exact LinkedIn sample job page was not anonymously retrievable through the safe web fetch.
- Naukri blocks automated access under its robots rules; the project will not bypass that restriction.
- Covalense Global's official public careers page contains the matching **Gen AI Engineer** role and a short employer-provided description.
- EY's official careers search contains similarly named Digital-Senior roles, but no exact official match to the supplied Hyderabad LinkedIn job was established. A third-party description must not be silently attached to it.
- The LinkedIn alert email itself exposes per-job summary signals such as connection counts or company-alumni counts, but it does not contain the underlying list of people.
- An authenticated LinkedIn connections-list query is outside the approved no-portal-scraping boundary. A user-requested LinkedIn export or emailed copy can be parsed separately when received.

## Recommendation

Add these stable optional fields:

- `job_description`: employer-provided description text when obtained from the alert itself or an official public employer page;
- `network_signal`: LinkedIn alert text such as `30 connections` or `3,771 company alumni`.

Description source policy:

1. description included directly in the approved alert email;
2. exact official employer job page or official public careers feed;
3. blank when no exact official source is available.

Do not fetch descriptions from authenticated LinkedIn/Naukri pages, bypass robots or access controls, or substitute uncertain third-party descriptions. Preserve the official URL as provenance when official enrichment is later automated.

## Tradeoff

This policy will leave some description cells blank, but it avoids attaching the wrong description, depending on unstable protected pages, or violating the project's access boundary.

## Decision required

Approve adding `job_description` and `network_signal`, with descriptions populated only from alert content or an exact official employer source and no portal scraping.
