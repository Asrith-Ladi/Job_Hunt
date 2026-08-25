# 023 - Before/after ATS keyword alignment

## Request

Show an ATS score before and after the resume is updated for a verified official job.

## Approved implementation

- Label the result `ATS keyword alignment estimate`; do not claim access to an employer's
  proprietary ATS score or ranking algorithm.
- Read the actual selected baseline DOCX locally and compare its visible text with the exact
  required and preferred terms extracted from the verified official JD.
- After generating a DOCX or PDF resume, read the actual generated DOCX and apply the same
  deterministic calculation.
- Weight required terms at 80% and preferred terms at 20% when both lists are available. If
  only one list exists, that list supplies 100% of the estimate.
- Display the baseline score, tailored-copy score, numeric change, alignment bands, newly
  covered terms, and an expandable methodology/breakdown in the React result panel.
- Reordering content does not increase keyword coverage. An increase can come only from
  supported summary wording or exact skill terms backed by explicit user-confirmed evidence.
- If the user generates only a cover letter, keep the after score unavailable because no
  tailored resume copy was produced.

## Privacy and safety

- The calculation runs locally on the backend and makes no additional model call.
- No resume text, score, or private contact data is sent to an ATS vendor or employer.
- The immutable baseline and existing generated-document verification remain unchanged.

## Verification

- 128 Python unit/API tests pass.
- Full Ruff checks pass.
- React TypeScript/Vite production build passes.
- Regression coverage verifies a baseline score of 80, a supported tailored score of 100,
  and a +20 change after the confirmed exact JD term is added.
- No live Luna call was made.

## Status

- Status: implemented locally on 2026-08-17.
- Queue: `Q-033`.
