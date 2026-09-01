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
| Q-025 | done | 1 | Add all ranked offline same-company referral suggestions, preliminary eligibility context, clickable profiles, and per-person LinkedIn message copying to Gmail review rows | `discussions/015_gmail_offline_referrals.md` |
| Q-026 | done | 1 | Add an offline Network Reviews tab with all saved LinkedIn profiles, relevant reviewer ranking, profile links, and personalized copy-ready resume-review requests | `discussions/016_network_profile_reviews.md` |
| Q-027 | done | 1 | Show all network rows and all 18 review columns, add reusable greeting/body templates, per-row copy actions, optional outreach tracking, and explicitly requested private email display | `discussions/017_network_review_columns_and_templates.md` |
| Q-028 | done | 1 | Add explicit per-job official-JD research, separate eligibility analysis, private baseline-resume upload, and truth-preserving tailored DOCX download/optional Drive upload | `discussions/018_streamlit_retirement_and_job_intelligence.md` |
| Q-029 | done | 1 | Consolidate source configuration into Run Setup and provide a premium unified Job Queue that preserves source rows and groups possible duplicates until user verification | `discussions/019_unified_run_setup_and_job_queue.md` |
| Q-030 | done | 1 | Keep all current Company Portal and ATS matches visible, classify new/changed/previously-seen rows, and support word/phrase-aware comma-separated titles or keywords globally | `discussions/020_global_current_matches_and_keyword_search.md` |
| Q-031 | done | 1 | Resolve UUID-based Ashby jobs through the exact public feed record, prohibit related-job substitution, and ground every displayed skill in the selected JD | `discussions/021_exact_ashby_job_descriptions.md` |
| Q-032 | done | 1 | Let the user justify exact missing JD skills, persist explicitly confirmed evidence privately, and add only those keywords to generated resume copies | `discussions/022_user_confirmed_skill_evidence.md` |
| Q-033 | done | 1 | Compare transparent ATS keyword alignment before and after resume tailoring without claiming a proprietary employer ATS score | `discussions/023_before_after_ats_alignment.md` |
| Q-034 | done | 1 | Organize generated documents by company and dated role while keeping professional neutral filenames for HR sharing | `discussions/024_application_document_storage.md` |
| Q-035 | done | 1 | List and load earlier Gmail workbooks, allow status/notes tracking in their original files, and preserve cross-run deduplication | `discussions/025_gmail_run_history.md` |
| Q-036 | done | 1 | Record privacy-safe Luna token/tool usage, calculate versioned API cost, show pre-run estimates and per-action/daily/monthly totals, and mirror the ledger to app-owned Drive | `discussions/026_ai_usage_cost_tracking.md` |
| Q-037 | done | 1 | Recognize evidence-backed equivalent JD wording, place supported exact terms in relevant skill categories, and safely reframe supported resume sentences without changing facts | `discussions/027_evidence_backed_resume_tailoring.md` |
| Q-038 | done | 1 | Refactor the flat Python source into production capability packages, enforce dependency boundaries, and make private runtime paths deployment-configurable | `discussions/028_production_package_architecture.md` |
| Q-039 | done | 1 | Filter the official-employer selector by the canonical MNC, product, startup, mid-sized, and other-company registry groups while preserving cross-group selections | `discussions/029_company_category_filters.md` |
| Q-040 | done | 1 | Make the app-owned Drive company registry authoritative, retain only a validated local cache, and recognize public Lever jobs embedded by custom careers pages | `discussions/030_drive_registry_and_embedded_ats.md` |
| Q-041 | done | 1 | Keep source searches temporary and persist only explicitly tracked jobs in one canonical Drive application queue | `discussions/031_transient_search_and_application_queue.md` |
| Q-042 | discussion | 1 | Build a private, deduplicated official-JD evidence library and deterministic Market Insights view | `discussions/032_job_description_market_library.md` |
| Q-043 | done | 1 | Detect supported public ATS boards embedded on custom careers pages, separate title phrases from JD capabilities, rank title evidence first, and expose extracted-to-matched counts | `discussions/033_embedded_ats_and_ranked_search.md` |
| Q-044 | done | 1 | Show live, source-safe search stages, current item, completed count, matches, elapsed time, and recent progress for Gmail, company portals, and ATS sources | `discussions/034_live_search_progress.md` |
| Q-045 | done | 1 | Separate temporary Results from a persistent Applications tab with saved, preparing, applied, and closed lifecycle views | `discussions/035_persistent_applications_tab.md` |
| Q-046 | done | 1 | After manual application, save the verified JD and structured application snapshot beside the generated resume before marking the job applied | `discussions/036_applied_job_evidence_package.md` |
| Q-047 | done | 1 | Batch Gmail alert-message downloads with live counts and recover Network Reviews from valid Drive/Excel workbooks without cached worksheet dimensions | `discussions/037_gmail_batching_and_network_recovery.md` |
| Q-048 | in progress | 1 | Re-audit every company job link, color inaccessible rows red and manual/company-specific rows blue, and expand India-focused product, startup, and mid-sized coverage | `discussions/038_registry_link_audit_and_india_expansion.md` |
| Q-049 | done | 1 | Refresh the React interface with a premium, clearer visual hierarchy and simpler copy while preserving the private job-search lifecycle | `discussions/039_premium_ui_refresh.md` |
| Q-050 | done | 1 | Save a readable, completeness-labeled JD package after manual application and simplify Search to one primary action with advanced filters collapsed | `discussions/040_clean_jd_archives_and_simplified_actions.md` |
| Q-051 | in_progress | 1 | Remove proven-unused production code/files, verify the accumulated release, open a descriptive PR, and merge it | `discussions/041_production_cleanup_and_release_pr.md` |

## Adding an item

Use the next permanent `Q-NNN` ID and record:

- requested outcome;
- why it matters;
- dependencies/access implications;
- relationship to active work;
- user approval status.

Do not store credentials, private email content, or resume content in this file.
