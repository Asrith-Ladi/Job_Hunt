# 010 - LinkedIn export tabs under the company registry

## Request

Use the previously supplied LinkedIn data export to gather job-search-useful information and add it as separate tabs in the same canonical company-source workbook so the registry, referral network, prior activity, and discovery signals remain under one umbrella.

## Decision

- Read the supplied export locally; do not alter the raw folder or archive.
- Add only information that supports company discovery, referral outreach, duplicate-application prevention, job-alert configuration, or evidence-based profile review.
- Match companies conservatively by normalized exact name or an explicit alias. Do not use fuzzy identity guesses.
- Keep unmatched followed companies visible as registry candidates instead of silently adding them to a category.
- Do not enrich connection records from external people-search sites or scrape LinkedIn.
- Keep the canonical workbook path unchanged so downstream Streamlit work has one stable input.

## Delivered tabs

1. `LinkedIn Overview` - aggregate referral coverage, activity counts, category coverage, and leading registry companies by connection count.
2. `LinkedIn Profile` - populated job-relevant profile, preference, experience, education, and skill fields.
3. `LinkedIn Connections` - 3,486 exported connections with clickable LinkedIn profiles, supplied email links where present, conservative registry matches, and official careers/job portals.
4. `LinkedIn Applications` - 37 prior applications with original job URLs and current matched official portals.
5. `LinkedIn Saved Jobs` - 12 saved jobs with original URLs and current matched official portals.
6. `LinkedIn Job Alerts` - 8 normalized alert configurations with keywords, frequency, radius, workplace modes, channels, and non-sensitive export identifiers.
7. `Followed Companies` - 88 followed organizations, including registry status and official portals when matched.

The snapshot found 841 connections at companies already in the 210-company registry, spanning 96 registry companies. The supplied export itself contained 111 connection email values; no email or phone discovery was performed.

## Privacy boundary

The workbook excludes private messages, invitations, search and advertising history, inference files, birth date, home/street address, the account owner's direct phone/email fields, saved job-screening questions and answers, and other unrelated export files. Blank export fields are omitted from the profile view. Connection emails appear only when they were already present in the user-supplied export.

## Verification

- Four automated registry/LinkedIn workbook tests passed.
- Static style checks passed.
- All 13 sheets were rendered and visually inspected.
- The final OOXML contains 10 table-owned filters and no overlapping worksheet-level filters.
- Desktop Excel opened the canonical workbook read-only with 13 worksheets and 10 intact tables, without a repair warning.

## Status

Complete. The workbook remains the single canonical Excel umbrella for company sources and the selected LinkedIn export snapshot.
