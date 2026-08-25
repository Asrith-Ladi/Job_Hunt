# 024 - Professional application-document storage

## Request

Make generated resumes easy to find later by company, date, and role, while keeping the
filename shared with recruiters neutral so it does not advertise per-job tailoring.

## Approved structure

```text
Job Hunt/
  Resumes/
    <Company>/
      <YYYY-MM-DD>_<Role>/
        Asrith_Ladi_AI_ML_Engineer_6Y.docx
        Asrith_Ladi_AI_ML_Engineer_6Y.pdf
        Asrith_Ladi_AI_ML_Engineer_6Y_Cover_Letter.docx
```

- The folder date is the document preparation/generation date. Actual application status and
  application timing remain tracker data and must not be inferred from document creation.
- Company folders remain readable; unsafe path characters are removed.
- Role names use filesystem-safe underscores inside the dated application folder.
- Company and role never appear in the downloadable document filenames.
- A rerun for the same company, role, and date updates the current fixed-name application
  pack in that folder. Different companies, roles, or dates remain separated.
- The generated artifact response includes the readable Drive folder path and direct folder
  URL so the UI can show where the pack was stored.

## Access and migration

- The hierarchy remains inside the app-owned `Job Hunt` Drive tree and uses the existing
  `drive.file` permission; no new Google scope or local-machine dependency is introduced.
- Existing files under the earlier `Job Hunt/<date>/Resumes` hierarchy are not moved or
  deleted automatically. New generations use the new hierarchy.
- Internal generated-document working folders remain isolated by generation ID so concurrent
  backend operations do not collide before Drive upload.

## Verification

- Folder-construction tests verify `Resumes`, company, and dated-role parent relationships.
- Generation tests verify all three neutral filenames and company/role upload context.
- 129 Python unit/API tests pass.
- Full Ruff checks pass.
- React TypeScript/Vite production build passes.

## Status

- Status: implemented locally on 2026-08-17.
- Queue: `Q-034`.
