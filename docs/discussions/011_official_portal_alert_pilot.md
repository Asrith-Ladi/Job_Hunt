# 011 - Official portal and job-alert pilot

## Request

Use the existing company registry to check current AI/ML roles and determine whether job alerts can be enabled on selected official company portals, using Google sign-in where the portal supports it.

## Pilot scope

The first five companies were chosen from strong LinkedIn referral coverage and relevant product hiring:

| Company | Registry referrals | Portal audit result | Native alert result | Activation state |
| --- | ---: | --- | --- | --- |
| Wipro | 60 | No exact confirmed 5-8-year match; two nearby live roles | Yes, through a Wipro careers profile | Pending connected browser and Wipro account |
| Cognizant | 54 | One confirmed role overlapping the target range | Yes, through the India talent community | Pending connected browser and form review |
| Infosys | 45 | JavaScript-driven India portal needs interactive confirmation | Not confirmed for India | Pending connected browser |
| Accenture | 41 | One strong confirmed Hyderabad match | No native alert control confirmed | Use saved-job, Gmail, or daily scanner fallback |
| Google | 23 | Three confirmed roles fitting or closely overlapping the target | Yes, through Google Careers | Pending connected browser and Google sign-in |

The target used for this audit was AI/ML, machine learning, GenAI, and data-science work at 5-8 years of experience in India, with Hyderabad and Bengaluru prioritized.

## Official evidence retained in the workbook

- Wipro alert registration: `https://careers.wipro.com/talentcommunity/subscribe/?locale=en_US`
- Cognizant India talent community: `https://careers.cognizant.com/india-en/talent-community/`
- Cognizant confirmed role: `https://careers.cognizant.com/global-en/jobs/00067230902/sr-associate-data-science/`
- Accenture confirmed role: `https://www.accenture.com/in-en/careers/jobdetails?id=ATCI-4822102-S1848464_en&title=AI+%2F+ML+Engineer`
- Google job alerts: `https://www.google.com/about/careers/applications/jobs/alerts`
- Google confirmed best match: `https://www.google.com/about/careers/applications/jobs/results/136390105332884166-senior-software-engineer-aiml-ai-garage`

The workbook records current public evidence separately from interactive activation state. An indexed role is not counted as live when its official detail page says it is unavailable.

## Workbook design

The canonical workbook now includes a `Portal Alert Pilot` tab with one filterable row per pilot company. It stores:

- the official job portal and alert-setup URL;
- alert support, login requirement, and Google-sign-in support as separate fields;
- the intended query, locations, and experience target;
- activation status and last-checked date;
- confirmed current-role count and a clickable best-match URL;
- real registry-matched LinkedIn referral counts;
- the exact manual action still required and evidence notes.

No alert is marked `Enabled` until the employer portal confirms it in an interactive browser session.

## Access boundary

No browser backend was connected during this run, so authenticated forms and alert buttons could not be opened or submitted. Passwords, CAPTCHA, and two-factor authentication remain user-only steps. Gmail addresses may be usable as ordinary email addresses on some portals, but that is not the same as a supported Google sign-in flow.

## Verification

- All 71 project tests passed.
- Registry-specific Ruff checks passed.
- The canonical workbook contains 14 worksheets and 11 table-owned filters.
- Every worksheet preview was rendered and visually inspected.
- Desktop Excel opened the workbook read-only with all 14 worksheets and 11 tables intact and without a repair warning.

## Status

The public audit and workbook tracking are complete. Interactive alert activation remains pending until a browser session is connected and the user is signed in to the chosen accounts.
