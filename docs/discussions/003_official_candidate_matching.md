# Discussion 003 — Official candidate matching and experience filtering

## Task status

- Requested: **Yes, 2026-07-19**.
- Limited pilot approved: **Yes — top three LinkedIn and top three Naukri jobs**.
- Alert experience extraction and UI target classification: **Implemented**.
- Interactive official-source pilot: **Complete**.
- Deployed automatic official-source discovery: **Decision pending**.

## Requested outcome

For the first three jobs in each approved Gmail test label:

1. retain the extracted LinkedIn or Naukri URL;
2. search by company, title, and location;
3. keep multiple official employer candidates for user review;
4. extract experience and other useful fields when the official portal supplies them;
5. prioritize roles suited to a current target of **5–8 years**.

No LinkedIn/Naukri page scraping, authenticated browser automation, CAPTCHA bypass, or
automatic application is permitted.

## Experience policy

The application preserves the internal raw experience text and exports it through the
user-facing `years_of_experience` column. It also adds `experience_source`, numeric
minimum/maximum values, and one of these review labels:

- `preferred`: the posting's minimum experience is between 5 and 8 years;
- `possible_overlap`: a broader or more junior range still overlaps 5–8 years;
- `outside_target`: the known range does not overlap 5–8 years;
- `unknown`: experience was not supplied by the alert.

The UI defaults to showing every result. A strict checkbox can exclude only known
`outside_target` jobs; unknown roles remain visible to avoid false rejection.

For the current templates, Naukri URL-derived ranges use `experience_source=alert_url`.
LinkedIn remains blank with `experience_source=unknown` until an exact official source is
matched. Future official enrichment will use `experience_source=official_portal`.

## Six-alert pilot

### LinkedIn 1 and 2 — EY, Digital Senior, Hyderabad

Alert URLs:

- `https://linkedin.com/comm/jobs/view/4439237316`
- `https://linkedin.com/comm/jobs/view/4439241132`

The two LinkedIn IDs are retained separately, although their company/title/location
fingerprints are nearly identical. The generic alert title is insufficient to establish an
exact EY requisition. Official review candidates include:

1. `Digital- GEN AI Nvidia- Senior`, Hyderabad, requisition `1671460`, 6–9 years:
   `https://careers.ey.com/ey/job/Hyderabad-Digital-GEN-AI-Nvidia-Senior-TG-500081/1283178001/`
2. `EY - GDS Consulting - AIA - Python Full stack AI Engineer - Senior`, Hyderabad,
   requisition `1703723`, employer experience not clearly stated:
   `https://careers.ey.com/ey/job/Hyderabad-EY-GDS-Consulting-AIA-Python-Full-stack-AI-Engineer-Senior-TG-500081/1411524633/`

Result: **related official candidates found; exact match requires user review**. These must
not be silently written as the exact official URL for either LinkedIn job.

### LinkedIn 3 — Real, Senior Machine Learning Engineer, India remote

Alert URL:

- `https://linkedin.com/comm/jobs/view/4423231055`

Exact official ATS posting:

- `https://jobs.ashbyhq.com/real/d36a6c61-ff2d-4530-bcb7-f3cead4b2bac/`

Extractable official fields include title, India remote location, full-time employment,
Research & Development department, remote workplace type, description, and **5+ years**
of AI/ML experience.

Result: **high-confidence exact official match; preferred for 5–8 years**.

### Naukri 1 — Covalense Global, Gen AI Engineer, Hyderabad

Alert URL:

- `https://naukri.com/jd/job-listings-gen-ai-engineer-covalense-global-hyderabad-2-to-6-years-130726503094`

Official careers source:

- `https://www.covalenseglobal.com/careers`

The employer page exposes the exact title, Hyderabad location, remote workplace type, and
a short description. It does not expose a reliable experience range or requisition ID.
The alert URL explicitly encodes **2–6 years**, classified as `possible_overlap`.

Result: **high-confidence official role match; experience provenance remains the alert**.

### Naukri 2 — Accenture, AI / ML Engineer, Hyderabad

Alert URL:

- `https://naukri.com/jd/job-listings-ai-ml-engineer-accenture-solutions-pvt-ltd-hyderabad-3-to-8-years-130726930566`

The alert URL explicitly encodes **3–8 years**, classified as `possible_overlap`. Accenture
currently exposes several official same-title/same-location requisitions suited to the
target, so they remain distinct review candidates rather than being merged:

1. `ATCI-5118203-S1894954`, Machine Learning, 5–10 years / minimum 5:
   `https://www.accenture.com/in-en/careers/jobdetails?id=ATCI-5118203-S1894954_en`
2. `ATCI-5094709-S1885176`, Large Language Models, 5–10 years / minimum 5:
   `https://www.accenture.com/in-en/careers/jobdetails?id=ATCI-5094709-S1885176_en`
3. `ATCI-5223735-S1923454`, Machine Learning Operations, 5–10 years / minimum 7.5:
   `https://www.accenture.com/in-en/careers/jobdetails?id=ATCI-5223735-S1923454_en`
4. `ATCI-5291800-S1933742`, Data Science, minimum 7.5:
   `https://www.accenture.com/in-en/careers/jobdetails?id=ATCI-5291800-S1933742_en`

Result: **four strong official candidates; the alert cannot be tied to one requisition
without an alert-provided employer ID or manual review**.

### Naukri 3 — Proxelera, AI/ML Engineer, Hyderabad

Alert URL:

- `https://naukri.com/jd/job-listings-ai-ml-engineer-proxelera-hyderabad-2-to-5-years-170726502402`

Official careers source:

- `https://proxelera.com/proxelera-careers/`

The official page says the company is hiring but does not expose a structured job title,
description, experience, requisition, or application URL for this role. The alert URL
explicitly encodes **2–5 years**, classified as `possible_overlap` at the five-year boundary.

Result: **no exact official posting confirmed**. A saved copy or public URL of a detailed
official Proxelera job page would be the next useful company template if one is visible to
the user.

## Recommended official-candidate columns

Use a separate `Official Candidates` table rather than adding four repeated URL groups to a
single alert row:

- source alert record ID and `source_url`;
- candidate rank;
- company, title, and location;
- `official_url` and official source type;
- requisition ID;
- experience text, minimum, maximum, and fit label;
- employment type, workplace type, department, and primary skill when supplied;
- published/updated date when explicitly supplied;
- job description or a concise description field;
- match status, score, reasons, and last verification time;
- user review and application status.

## Runtime decision still required

The pilot's web search was interactive development research and is not a dependency the
deployed Streamlit application can silently reuse. Automatic daily discovery requires one
of these approved paths:

1. **Recommended:** a small company-source registry plus official ATS/feed/sitemap/static
   page adapters. This is precise and avoids paying for broad search, but new ATS templates
   require incremental adapter work.
2. A programmable search API used only to discover official employer URLs. This covers
   unknown companies faster but introduces an API key, usage cost, result variability, and
   provider terms that require a separate access decision.

Until that decision, the app can safely parse alert experience and the pilot can retain
manually verified official candidates, but it should not pretend that interactive search is
automated production behavior.
