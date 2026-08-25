# Project working rules

## Context order

Use this order when deciding what to do:

1. The user's latest explicit instruction and approved decisions.
2. `docs/discussions/031_transient_search_and_application_queue.md` for the active search/persistence lifecycle, `docs/discussions/017_network_review_columns_and_templates.md` for the network table/template design, `docs/discussions/015_gmail_offline_referrals.md` for Gmail referral enrichment, `docs/discussions/014_company_portals_and_ats_sources.md` for public discovery, `docs/discussions/013_react_fastapi_migration.md` for the UI boundary, then `docs/discussions/001_gmail_alerts_to_google_sheet.md` for the Gmail foundation.
3. `docs/PROJECT_BRIEF.md` for stable project direction and boundaries.
4. `docs/memory.md` for user-approved fixed project instructions.
5. `docs/queue.md` for proposed/new work and its status.
6. `docs/reference/JOB_AUTOMATION_PLAN.md` only as detailed, non-binding reference.

Do not read the full automation plan by default. Search it by heading or keyword and load only the relevant section.

## Current project posture

- This is a personal project first, with clean boundaries that can support more users later.
- Do not build multi-tenant infrastructure before the personal workflow works.
- The personal MVP is a manually triggered React UI with Search, Results & Applications, and offline Network Reviews. Gmail, selected Company Portal, and public ATS searches are temporary; only explicit job-tracking actions write to the canonical Drive application queue. Historical Gmail workbooks remain reviewable compatibility artifacts.
- Do not scrape protected LinkedIn or Naukri pages; alerts and user-provided links are discovery inputs.
- Do not submit job applications.
- Gmail review rows may use the saved LinkedIn export snapshot for deterministic same-company referral suggestions; never read or expose connection emails, and always label the match as unverified.
- Network Reviews may display the saved LinkedIn export's explicitly requested email field in the private UI in addition to name, role, company, profile URL, and connection date; never send it to an LLM/log, never automate contact, and keep Gmail referral enrichment contact-free. Its relevance ranking is a review aid, not proof of current employment, relationship strength, or willingness to help.

## Decision gate

Before starting a new implementation phase or making a material architecture/access decision, give the user a concise decision brief containing:

- the immediate outcome;
- the recommended approach;
- meaningful alternatives and tradeoffs;
- required access and privacy implications;
- the exact decision needed from the user.

Wait for explicit approval when the active discussion file shows implementation as unapproved.

## Security and maintenance

- Never request or store secrets in chat, committed YAML, source files, or logs.
- Prefer least-privilege Google OAuth scopes and explain any scope increase first.
- Keep email content, resume content, tokens, and personal data out of logs.
- Treat email HTML and links as untrusted input.
- Keep core normalized fields stable; UI-selected custom fields are optional display/export fields.
- Update the active numbered discussion after approved work changes status, scope, or next steps.
- Add new ideas to `docs/queue.md`; do not silently expand the active task.
- Update `docs/memory.md` only for explicit, durable user instructions.
- Record mistakes and reusable fixes in `docs/issues_and_fixes.md`.
- Update `docs/PROJECT_BRIEF.md` only when the user approves a durable direction change.
