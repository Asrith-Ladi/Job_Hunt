# 016 - Offline network profile-review outreach

## Request

Use the previously supplied LinkedIn connections export to show connection names, current exported roles, companies, and saved LinkedIn profile links. Prioritize AI/ML practitioners and relevant technical managers, personalize the user's approved resume-review message, and make each message easy to copy from the React UI.

## Approved implementation

This is a fourth, offline React tab named `Network reviews`:

- load every connection with a valid saved LinkedIn profile from the canonical registry workbook's `LinkedIn Connections` tab;
- use only connection name, current exported company, current exported position, saved profile URL, and connection date;
- never read, return, log, or display connection email addresses or phone numbers;
- rank AI/ML leaders, AI/ML practitioners, technical leaders, and senior technical professionals deterministically;
- keep recruiting/HR and unrelated profiles available through filters, but exclude them from the default recommended view;
- support name, company, role, category, recommended-only, and manager/lead filters;
- allow the target-role phrase to be changed once and regenerate all visible messages;
- open the saved LinkedIn profile from the connection name and copy the personalized message with one action.

No LinkedIn scraping, employer access, Google access, LLM call, or API charge is involved.

## Message contract

The message uses the user's approved text. Only the connection's first name and the target-role phrase are substituted. It asks permission to share the resume and requests two or three honest suggestions about positioning, technical/project gaps, and job-search approach. It does not imply relationship strength, current employment, or willingness to help.

## Ranking boundary

Ranking is a navigation aid based only on the exported position text. It is not an eligibility score or a statement that someone will respond. The UI warns that exported roles may be stale and asks the user to review the profile before sending.

## Verification

- The real offline workbook contains 3,448 valid saved LinkedIn profiles.
- Deterministic ranking identifies 1,538 default recommended profiles and 406 non-recruiting manager/lead profiles.
- API output contains only the approved non-contact fields; email and phone keys are absent.
- Backend privacy, ranking, filtering, pagination, and message tests pass.
- The React TypeScript production build passes.
- No browser was attached to this Codex session, so an interactive click-through is not claimed.

## Status

Implementation is complete and subsequently expanded by Discussion 017. Discussion 017 supersedes this file's email-exclusion rule only for the explicitly requested private Network Reviews table; Gmail referral matching remains contact-free.
