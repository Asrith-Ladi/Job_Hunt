# Safe alert fixture preparation

The parser uses representative LinkedIn and Naukri emails to learn reusable card structure without committing personal mail.

## Accepted workflow

1. In Gmail, use **Download message**, or **Show original → Download Original**, to save `.eml` files.
2. Stage originals only under neutral names in the Git-ignored folders:

   ```text
   local_samples/linkedin/linkedin_NN_raw.eml
   local_samples/naukri/naukri_NN_raw.eml
   ```

3. Do not upload raw emails to chat or commit them.
4. Generate local sanitized HTML/text derivatives with `scripts/sanitize_eml_fixture.py`.
5. Inspect only the sanitized structure in conversation output.
6. Create the smallest synthetic HTML needed for committed regression tests; never copy the full marketing email into tests.

The sanitizer removes addresses, recipient names, LinkedIn profile-footer context, scripts, unsafe attributes, long tokens, URL fragments, and URL query values while retaining job titles, companies, locations, public hosts, paths, and parameter names.

## Current retention rule

One raw sample per source is currently staged under neutral names. Both are ignored by Git and must remain until the user explicitly approves removal. The original Downloads files are also unchanged.

Before approving removal, verify that:

- synthetic tests cover every required field from each observed template;
- a live dry run confirms title, company, location, and job-link extraction;
- sanitized derivatives contain no recipient address, personal name, profile context, tracking-query value, or raw OAuth material.
