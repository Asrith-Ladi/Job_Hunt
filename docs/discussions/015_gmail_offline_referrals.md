# 015 - Gmail offline referral suggestions

## Request

For Gmail-alert jobs, use the previously supplied LinkedIn connections export to find a suitable same-company referral contact without online scraping. Show the contact and a precise LinkedIn referral request in React, explain the user's relevant resume evidence, and provide one-click message copying.

## Approved implementation

This enhancement is deterministic and offline:

- read the canonical registry workbook's `LinkedIn Connections` snapshot;
- access only connection name, exported company, position, profile URL, and connection date;
- never read, return, log, or export connection email/phone values;
- match only cautious canonical-company equivalents;
- rank recruiting contacts first, technical contacts second, and other same-company contacts afterward;
- expose every ranked same-company candidate in React while retaining the top candidate and
  total count in the flat Excel-compatible row;
- mark every candidate as `offline_company_match_unverified` because the snapshot cannot prove current employment or willingness to refer;
- keep Gmail ingestion working with blank referral fields if the registry is missing or invalid.

No Gmail scope, employer login, LLM, public search, or portal scraping is added.

## Gmail run fields

Seven Gmail-only columns were added without changing the legacy Google Sheet schema or discovery workbooks:

- `referral_count`
- `referral_name`
- `referral_position`
- `referral_profile_url`
- `referral_match_status`
- `referral_eligibility`
- `referral_message`

Older 25-column Gmail run workbooks remain readable. The next explicit save rewrites that same run file with the expanded 32-column schema.

## Eligibility and message boundary

The eligibility text uses only verified, contact-free resume facts already stored in code: 5.8 years of documented experience and relevant technical evidence selected from the alert title. It is always labeled `Preliminary alert-only fit` and explicitly says official job-description requirements were not checked.

The generated LinkedIn request:

- addresses the suggested contact by first name;
- states the role, employer, 5+ years of relevant experience, and two role-specific strengths;
- includes the visible official job URL when available, otherwise the alert URL;
- directly and respectfully asks for a referral;
- offers to share the resume and makes declining easy;
- never implies a close relationship.

## React and Excel behavior

- Every ranked same-company referral name opens the saved LinkedIn profile, with the best-ranked
  match first and all alternatives available in the expanded job record.
- Each candidate has a separately personalized copy action. Messages preserve paragraph breaks
  and include the visible job URL.
- Search includes referral name and position.
- A `Referral leads` metric shows how many displayed jobs have a candidate.
- Excel makes the referral name/profile clickable and links the message cell to the job URL.
- Referral fields are read-only and are recalculated server-side during save.

## Verification

- The real registry snapshot yielded 3,256 usable company-tagged connections with LinkedIn profile URLs.
- The current 116-row local Gmail artifact received 71 offline same-company referral leads.
- 104 Python tests pass, including privacy, ranking, message, legacy-workbook, and hyperlink coverage.
- Focused Ruff checks pass for every changed Python file.
- The React TypeScript production build passes.
- No browser was attached to this Codex session, so an interactive click-through is not claimed.

## Status

Implementation is complete. On the next app load, the latest local Gmail workbook is enriched on screen without rereading Gmail. Use `Save Excel + Drive` only when ready to persist the new fields into that same workbook and its Drive copy.

### 2026-08-17 extension

The user explicitly requested all matching profiles rather than only the best-ranked profile so
they can contact more than one person. The runtime API now returns a contact-free candidate list
per Gmail job, and React renders a profile link and copy-ready request for every match. The seven
flat workbook columns remain stable and retain the top-ranked match plus the total count.

Verification for this extension: all 127 Python tests and full Ruff checks pass, and the React
production build completes. No in-app browser was connected, so a visual click-through was not
claimed.
