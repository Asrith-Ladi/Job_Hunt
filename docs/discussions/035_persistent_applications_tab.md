# 035 - Persistent Applications tab

## Decision

Separate temporary discovery output from long-lived application tracking in the primary
navigation:

- **Results** contains only records from the current search or a Gmail run the user explicitly
  loaded for review.
- **Applications** contains only jobs already written to the canonical Drive application queue.
- Saving a result, changing its status, saving a note, or confirming an official URL continues
  to upsert the same source record in `Job Hunt/Source/application_queue.json`.
- The new tab is a view over the existing queue, not another workbook, JSON file, or copy of a
  job.

## Application workflow

Applications provides filters for:

1. all tracked jobs;
2. saved for later (`not_started` or `saved`);
3. preparing (`reviewing` or `shortlisted`);
4. applied/later (`applied`, `interviewing`, or `offer`);
5. closed (`rejected`, `withdrawn`, or `expired`).

Every tracked job retains the existing source evidence, alert and official links, referral
context, notes, status selector, and explicit JD/resume actions. `interviewing` and `offer` are
added as valid lifecycle statuses so a submitted application can continue to be tracked.

## Persistence boundary

Current searches remain browser-session state. Applications is reconstructed from Drive on
startup and therefore survives refresh, a new search, and deployment to another device using
the same connected account. Cross-source records remain separate until the user verifies that
they represent one official job.
