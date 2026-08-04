# Work queue

New ideas and requested work enter here before becoming implementation tasks. The queue prevents useful ideas from silently expanding current scope.

## Status values

`proposed` → `discussion` → `approved` → `in_progress` → `done`

Alternative terminal values: `deferred`, `rejected`, `cancelled`, or `superseded`.

## Queue

| ID | Status | Priority | Item | Discussion/reference |
|---|---|---:|---|---|
| Q-001 | done | 1 | Manual Gmail LinkedIn/Naukri alerts to Google Sheet in Drive | `discussions/001_gmail_alerts_to_google_sheet.md` |
| Q-002 | deferred | 2 | Scheduled GitHub Actions execution after manual runs are stable | `reference/JOB_AUTOMATION_PLAN.md` |
| Q-003 | done | 3 | Resume matching and truthful recommendations for the current production batch | `discussions/005_production_job_tracker.md` |
| Q-004 | deferred | 4 | Multi-user accounts and tenant-isolated storage | `PROJECT_BRIEF.md` |
| Q-005 | proposed | 5 | Additional email alert sources beyond LinkedIn and Naukri | Awaiting need |
| Q-006 | deferred | 6 | Select an existing Sheet or Drive folder through a per-file Google Picker flow | After the app-created Sheet workflow is stable |
| Q-007 | discussion | 2 | Private internet deployment with persistent OAuth/state storage | `discussions/007_deployment_runtime_and_daily_runs.md` |
| Q-008 | done | 2 | Official-source job descriptions and supplied LinkedIn connection-export signals | `discussions/005_production_job_tracker.md` |
| Q-009 | done | 2 | Official candidate matching and 5–8-year experience ranking | `discussions/005_production_job_tracker.md` |
| Q-010 | done | 2 | Create and verify a private dated-tab Google Sheet sample for the six-alert pilot | `discussions/004_sample_google_sheet.md` |
| Q-011 | done | 1 | Build and verify the real multi-tab tracker for all current Gmail alert jobs | `discussions/005_production_job_tracker.md` |
| Q-012 | done | 1 | Make displayed referral names and cold-message job URLs clickable | `discussions/005_production_job_tracker.md` |
| Q-013 | done | 2 | Add manual contact-lookup tool links to the `Runs` side panel | `discussions/006_contact_lookup_enrichment.md` |
| Q-014 | discussion | 2 | Enrich referral contacts through a user-provided vendor CSV or one official provider API; no scraping | `discussions/006_contact_lookup_enrichment.md` |
| Q-015 | done | 1 | One-click Streamlit flow with resumable, checkpoint-batched OpenAI official-job research, tracker refresh, and local Excel export | `discussions/008_openai_streamlit_full_workflow.md` |
| Q-016 | done | 1 | Create a reusable Excel registry of major MNC official career pages, direct job portals, and known ATS sources | `discussions/009_mnc_company_source_registry.md` |
| Q-017 | done | 1 | Add a matching `Product Companies` tab with curated product-led employers and current official portals | `discussions/009_mnc_company_source_registry.md` |
| Q-018 | done | 1 | Repair one canonical company registry, remove cross-category duplicates, and add startup, mid-sized, other-company, and coverage tabs | `discussions/009_mnc_company_source_registry.md` |
| Q-019 | done | 1 | Add privacy-conscious LinkedIn export tabs for referrals, profile signals, prior applications, saved jobs, alerts, and followed companies to the same registry workbook | `discussions/010_linkedin_export_workbook_tabs.md` |
| Q-020 | in progress | 1 | Audit five official portals for matching AI/ML jobs and alert support, then enable supported alerts after a browser session is connected | `discussions/011_official_portal_alert_pilot.md` |
| Q-021 | superseded | 1 | Complete the separated Streamlit Gmail phase with on-screen editing, cross-run deduplication, and dated Excel artifacts under the app-owned Drive folder | Superseded by the completed React/FastAPI workflow; `discussions/012_streamlit_gmail_run_workbooks.md` |
| Q-022 | done | 1 | Replace Streamlit with a React + TypeScript UI and FastAPI backend while preserving the Gmail workbook workflow; retire Streamlit after user approval | `discussions/013_react_fastapi_migration.md`, `discussions/018_streamlit_retirement_and_job_intelligence.md` |
| Q-023 | done | 1 | Implement the registry-driven Company Portals phase with selected batches, public structured-first discovery, safe sitemap/static fallbacks, and dated workbooks | `discussions/014_company_portals_and_ats_sources.md` |
| Q-024 | done | 1 | Implement Greenhouse, Lever, Workable, and SmartRecruiters ATS adapters plus detection-only fallbacks for company-specific platforms | `discussions/014_company_portals_and_ats_sources.md` |
| Q-025 | done | 1 | Add offline same-company referral suggestions, preliminary eligibility context, clickable profiles, and one-click LinkedIn message copying to Gmail review rows | `discussions/015_gmail_offline_referrals.md` |
| Q-026 | done | 1 | Add an offline Network Reviews tab with all saved LinkedIn profiles, relevant reviewer ranking, profile links, and personalized copy-ready resume-review requests | `discussions/016_network_profile_reviews.md` |
| Q-027 | done | 1 | Show all network rows and all 18 review columns, add reusable greeting/body templates, per-row copy actions, optional outreach tracking, and explicitly requested private email display | `discussions/017_network_review_columns_and_templates.md` |
| Q-028 | done | 1 | Add explicit per-job official-JD research, separate eligibility analysis, private baseline-resume upload, and truth-preserving tailored DOCX download/optional Drive upload | `discussions/018_streamlit_retirement_and_job_intelligence.md` |

## Adding an item

Use the next permanent `Q-NNN` ID and record:

- requested outcome;
- why it matters;
- dependencies/access implications;
- relationship to active work;
- user approval status.

Do not store credentials, private email content, or resume content in this file.
