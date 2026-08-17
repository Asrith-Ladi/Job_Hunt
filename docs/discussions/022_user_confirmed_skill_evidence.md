# 022 - User-confirmed JD skill evidence

## Request

When exact JD keywords appear as honest resume gaps, let the user explain experience that
is real but absent from the baseline/reference documents. Use only explicitly confirmed
notes to improve a tailored resume, and include the exact supported JD terms in Technical
Skills so literal keyword matching is not lost.

## Approved decision

- Show a factual evidence-note field for every exact missing required skill.
- Require at least 20 characters and an explicit accuracy confirmation.
- Ignore unconfirmed notes and never add every gap automatically.
- Add confirmed exact JD labels to a deterministic `Additional Skills` line in the generated
  copy; never edit the immutable baseline.
- Allow Luna to use the confirmed, contact-free note as professional evidence when positioning
  the summary or cover letter, without expanding beyond the supplied fact.
- Save confirmed notes in the private Drive Resume Library for reuse when the same skill is a
  gap in a later job.

## Validation and privacy boundary

- The API accepts at most 20 notes, each no longer than 1,200 characters.
- The backend canonicalizes each supplied label to an exact missing skill in the selected
  posting. An arbitrary skill or a non-gap label is rejected.
- Notes containing email addresses, profile/web links, or phone-like values are rejected
  before the Luna boundary.
- Luna still does not receive the baseline DOCX, resume header/contact details, Gmail content,
  alert URLs, or LinkedIn connection data.
- Notes and generated artifacts use the app-owned Drive library under the existing
  `drive.file` scope; no new Google permission or employer login is required.

## DOCX safety

- Existing summary validation and skill/work-evidence preservation checks remain active.
- The editor clones the final Technical Skills paragraph's formatting and inserts exactly one
  `Additional Skills: ...` line containing the server-validated labels.
- Structural verification requires every original skill and work bullet to remain present and
  rejects any extra Skills content beyond that expected line.
- Generated DOCX/PDF/cover-letter files remain review-required drafts and are never submitted.

## Verification

- 126 Python unit/API tests pass.
- Full Ruff checks pass.
- React TypeScript/Vite production build passes.
- Synthetic DOCX verification confirms the original evidence remains unchanged while the
  confirmed keyword line is present.
- No live Luna call was made during implementation verification.
- The in-app browser was unavailable, so the evidence textarea/checkbox flow still needs one
  user click-through after restarting FastAPI and refreshing the compiled UI.

## Status

- Status: implemented locally on 2026-08-15.
- Queue: `Q-032`.
