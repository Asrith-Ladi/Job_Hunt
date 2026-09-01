# 036 - Applied-job evidence package

## Decision

An application should retain the job evidence used to prepare its documents, but ordinary
searches and merely generated drafts must remain temporary/private. Add one explicit action
after document generation: **I applied — save JD & details**.

The action is available only after at least one resume/cover-letter artifact has been generated.
It clearly states that the software does not submit an application and asks the user to confirm
that submission was completed manually.

## Storage and order

1. Resolve the exact Drive folder identity recorded for the generated artifacts.
2. Upload or replace `Job_Description.md` and `Application_Details.json` in that same folder.
3. Use the full verified official description when available, otherwise the collected source
   description, otherwise the grounded verified summary. Record which level was available.
4. Include company, role, location, experience, workplace/employment type, requisition,
   publication date, official/source URLs, required/preferred skills, eligibility snapshot,
   generated-document identities, application time, and provenance. Exclude Gmail bodies,
   contacts, resume content, prompts, secrets, and OAuth values.
5. Only after both Drive support files succeed, upsert `application_status=applied`, `applied_at`,
   the folder identity, and the two file links into the canonical application queue.

The upload is idempotent because files are updated by fixed name inside the verified folder.
If queue persistence fails after the files were uploaded, repeating the action safely repairs
the status/link update. Direct UI selection of applied/interviewing/offer opens this workflow
when no evidence package exists.

This package is an application record, not yet the cross-job Market Insights library described
in Discussion 032.
