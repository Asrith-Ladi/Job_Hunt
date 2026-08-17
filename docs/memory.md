# Fixed project memory

This file contains only explicit, durable instructions approved by the user. It is project documentation, not hidden model memory. Latest explicit user instructions always take precedence.

## Fixed instructions

1. `D:\Projects\job_hunt` is the main folder for all further work.
2. The project is personal-first; if it succeeds, it may later scale to more users.
3. Build clean user, source, parser, and storage boundaries now, but do not build multi-user infrastructure prematurely.
4. Superseded by rules 34–36: the first MVP originally wrote Gmail alert jobs to a Google Sheet in Drive.
5. The UI should support company filtering and optional displayed/exported fields.
6. Core normalized fields remain stable; UI customization must not silently redefine identifiers, dates, or deduplication keys.
7. Do not scrape protected LinkedIn or Naukri pages, bypass controls, or automate job applications.
8. Prefer least-privilege access, keep Gmail read-only initially, and never put secrets in chat, Git, docs, or logs.
9. `docs/reference/JOB_AUTOMATION_PLAN.md` is evolving reference material, not a fixed implementation mandate.
10. Before a material task or architecture/access decision, share a short decision brief and discuss it with the user.
11. Keep task discussions in permanent numeric sequence under `docs/discussions/`.
12. Add new ideas to `docs/queue.md`, not directly to active scope.
13. Record mistakes, incidents, causes, fixes, and prevention in `docs/issues_and_fixes.md`.
14. Superseded for live runs by rule 25: retain `Job_Alerts/link_test` and `Job_Alerts/nau_test` as test/fixture labels.
15. The product must connect to Gmail directly through code and Google OAuth; a Codex plugin or MCP server must never be a deployed-app dependency.
16. The personal MVP must ultimately run through a private internet deployment without requiring the user's laptop; local execution is only the validation stage.
17. Keep the staged raw LinkedIn and Naukri email samples until the user explicitly approves their removal; never commit them.
18. Superseded by rules 34–36: the earlier design reused one master Google Sheet and did not create a separate workbook for every run.
19. Keep alert and official-job URLs visible and clickable in all user-facing Google Sheet outputs.
20. Name the normalized email-derived job tab `Gmail_Alerts`; keep employer-careers-page results in the separate `Official_Jobs` tab.
21. Keep official-job identity confidence separate from resume eligibility; never present one score as the other.
22. For LinkedIn connection exports, exclude email addresses from Sheets, match cautiously by current exported company, and never imply relationship strength or willingness to refer.
23. The real dated application queue may contain multiple official candidates for one Gmail alert; label uncertainty and keep unmatched alerts visible for manual review.
24. Display referral names as clickable LinkedIn profile links, and keep the job URL visible and clickable inside referral cold messages so it remains useful when copied.
25. Use `Job_Alerts/LinkedIn` and `Job_Alerts/Naukari` for production Gmail alerts, with a rolling `newer_than:30d` query instead of maintaining separate last-30-days labels.
26. Format referral cold messages as readable, multi-paragraph, copy-paste-ready text; keep the visible job URL clickable.
27. Keep Sheet title and summary rows wrapped and compact, and freeze no more than one left-hand column so the tracker leaves useful horizontal review space.
28. Superseded by rule 34: the earlier single Streamlit run combined Gmail ingestion, official-job research, scoring/referrals, Sheet refresh, and Excel export.
29. Superseded for the separately approved manual resume workflow by rules 43–45: official research originally allowed only normalized alert record ID, company, title, location, and experience text; Gmail bodies/identifiers, alert URLs, resume contact details, and connection/contact data remain prohibited.
30. Use `gpt-5.6-luna` as the cost-conscious default, research only uncached alerts by default, and require an explicit UI choice to refresh cached research.
31. Superseded by rules 35–36: the earlier design kept the Google Sheet as the durable master and exported one `job_hunt.xlsx` mirror.
32. Referral messages must sound human and respectful, directly request a referral, include the visible job URL, and make it easy for the recipient to decline.
33. Superseded in UI framework by rule 37: if official-job research resumes, the application backend must process it through Luna in durable batches without Codex involvement, save every completed batch, and resume only unfinished alerts after interruption.
34. Superseded in UI framework by rule 37: keep three independent source tabs in this order—Gmail Alerts, Company Portals from the Excel registry, and structured ATS sources—and finish and approve Gmail before implementing the other two.
35. Each successful Gmail run creates a timestamped `gmail_alerts_YYYY-MM-DD_HHMMSS.xlsx` under the app-owned Drive `Job Hunt/YYYY-MM-DD` folder, displays all exported rows on screen, and rewrites that same local/Drive file only when the user explicitly saves edits.
36. Keep the canonical company registry and non-secret incremental Gmail state under app-owned Drive `Job Hunt/Source`; never upload OAuth credentials, tokens, raw email bodies, or other secrets there.
37. Superseded by rule 42: use React + TypeScript + Vite as the primary frontend and FastAPI as the backend while retaining the existing Python Gmail/parser/deduplication/workbook/Drive modules; Streamlit was temporary until explicit user retirement approval.
38. Implement the Company Portals and ATS Sources tabs as independent manual phases after Gmail: use selected registry batches and official/public structured sources first, keep undocumented ATS endpoints company-specific, and never require employer login or scan all companies on every run.
39. Enrich Gmail-alert rows offline from the saved LinkedIn connection snapshot: show a cautious top same-company referral candidate with a clickable profile, preliminary resume evidence, and a concise copy-ready LinkedIn request; exclude connection email/phone data and require the user to verify current employment before messaging.
40. Superseded for private Network Reviews email display by rule 41: keep Network Reviews as an offline, no-LLM React tab using saved connection data, personalize the user-approved resume-review template, and require profile verification before sending.
41. Display exported connection emails in the private Network Reviews UI because the user explicitly requested them, but do not send them to an LLM or logs, automate email/contact, or add them to Gmail referral enrichment; initially show all 18 requested columns and let the user choose the default hidden set after reviewing the UI.
42. React/FastAPI is the only supported active application runtime as of 2026-08-03. Keep the final Streamlit implementation only under `legacy/` as a short-term rollback/reference artifact; do not add new product behavior or dependencies to it.
43. Manual official-job research may send normalized job record ID, company, title, location, experience text, and a validated public official-employer URL hint only after an explicit per-job action. Never send Gmail bodies/identifiers, alert/source URLs, connection/contact data, or resume contact details.
44. Manual tailored-resume planning may additionally send only contact-free Professional Summary, Technical Skills, and Work Experience evidence plus the selected public official job and deterministic eligibility result. Keep official-job identity and resume eligibility separate, use `gpt-5.6-luna`, cache both phases, and require separate explicit research and resume-generation actions.
45. Generate each resume from a private baseline DOCX without sending the document itself: preserve the original contact/header and verified evidence, replace only a validated professional summary, reorder only existing skills/work bullets, require user review, and never submit an application. Keep drafts private locally with optional app-owned Drive upload.
46. Use one conditional `Run Setup` interface for Gmail, Company Portals, and ATS Sources, followed by one unified `Job Queue` with consistent core columns. Preserve all source rows, group only likely duplicates as unverified until the user confirms them, and retain both the Gmail alert URL and official-employer job URL.
47. Keep the supported React/FastAPI product visually premium but workflow-focused: every prominent block must support an action, decision, status, or evidence review. Maintain replaceable storage/service boundaries for later migration and remove only code proven unused without deleting personal inputs or rollback evidence that still requires approval.
48. For every Company Portal and ATS source, treat comma-separated job titles or keywords as word/phrase-aware alternatives and keep all currently matching jobs visible. Preserve incremental fingerprints by labelling rows new, changed, or previously seen instead of hiding unchanged matches.
49. When a selected job has a validated official URL, never substitute a related opening for JD extraction or eligibility scoring. Prefer the exact public ATS record by provider job identifier, retain only skills supported by evidence from that exact description, and return no candidate when exact identity cannot be verified.
50. Extend rule 45 only for explicit user-confirmed evidence: a missing exact JD skill may be added to the generated copy's Technical Skills section after the user supplies a factual note and confirms its accuracy. Keep the baseline immutable, reject arbitrary/unconfirmed additions, store confirmed notes privately in the Drive resume library, and require review of every draft.

## How to update memory

- Add or change a rule only after an explicit user instruction or approval.
- Date material changes and link the related discussion when practical.
- If a rule becomes obsolete, mark it superseded instead of erasing useful history.
- Do not copy temporary implementation details or speculative ideas here.
