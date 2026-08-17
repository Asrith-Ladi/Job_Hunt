# 020 - Global current matches and flexible keyword search

## Problem confirmed

On 2026-08-15, a Sarvam AI Company Portal run using `agent` successfully found matching official jobs, but the latest workbook and Job Queue showed zero rows because every match was already present in the cross-run seen-state. The source check completed successfully; collection and filtering were not the failure.

The current `rows ready` wording incorrectly means only new or changed rows. It makes a valid targeted search appear empty and replaces the prior Company Portal queue with an empty latest-run result.

## User direction

- Apply the correction globally, not only to Sarvam AI.
- The user will enter a mixture of company-specific job titles and broader keywords because employers use different role names.
- Comma-separated values are alternatives; a match on any title or keyword should retain the job.
- Matching jobs must remain visible even when they were seen in an earlier run.

## Approved implementation

- Use one `Job titles or keywords` input for Company Portal and ATS discovery.
- Normalize punctuation and use whole-word or phrase-aware, case-insensitive matching instead of unrestricted substrings. This prevents short terms such as `ai` from matching inside unrelated words such as `email`.
- Match against the public title plus available description and department evidence. Provider payload limitations remain explicit; no protected page or employer login is added.
- Classify every current match as `new`, `changed`, or `previously_seen` using the existing non-secret fingerprint state.
- Write every current match to the dated run workbook and return it to Job Queue. Deduplication continues to prevent a job from being mislabelled as new, but no longer hides it from a targeted run.
- Preserve separate counts for current matches, new/changed matches, and previously seen matches.
- Keep older discovery workbooks readable after the schema gains the run-change classification.

## Access and cost

- No new Google scope, ATS key, account login, LLM call, or protected-site scraping is required.
- This applies to all Company Portal sources and all enabled public ATS adapters through their shared filter/state/workbook pipeline.

## Status

- Status: implemented and verified on 2026-08-15.
- Queue: `Q-030`.

## Delivered outcome

- The correction is implemented in the shared discovery filter/state/service/workbook path, so it applies to all Company Portal companies and all enabled ATS adapters rather than a Sarvam-specific branch.
- Comma-separated entries use case-insensitive word/phrase matching with safe plural/`agentic`-style suffix handling and compact aliases such as `MLOps` ↔ `ML Ops`.
- Every current match is returned to React and written to the dated Excel workbook. Existing fingerprints classify each row as `new`, `changed`, or `previously_seen`.
- Run Setup reports `current matches · new/changed`; Job Queue reports current versus previously seen counts and shows the classification on expanded source evidence.
- Existing discovery workbooks without the new classification column remain readable and are labelled `new_or_changed` when loaded.

## Verification

- Replayed `agent` against the user's earlier 62-row Sarvam workbook and matched `Agent Engineer` without accessing Drive or creating a run.
- Added regression coverage for exact words, phrases, plurals, `agentic`, `MLOps`/`ML Ops`, description/department evidence, and false-positive prevention (`ai` does not match `email`).
- `118` Python tests passed.
- Full Ruff checks passed.
- React TypeScript/Vite production build passed (`35` modules).
