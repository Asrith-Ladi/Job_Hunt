# 017 - Network review columns and reusable templates

## Request

Show every LinkedIn connection rather than only profiles with valid URLs. Initially display every proposed review/workflow column so the user can inspect the real layout and later choose which columns should be hidden. Keep the LinkedIn profile inside the Name column, split the outreach message into a shared personalized greeting and a common editable body, and provide a per-row Copy message action.

The user subsequently explicitly requested the exported connection email address as an additional private-UI column and asked for its availability count.

## Implemented behavior

- The API returns all 3,486 named connection rows, including the 38 rows without a usable saved LinkedIn URL.
- Names open LinkedIn when a valid saved profile URL exists; otherwise the name remains plain text.
- All 18 columns are visible initially and can be toggled through the Columns chooser.
- The first 17 are the approved LinkedIn/registry/review/workflow columns; `Email address` is the explicitly requested eighteenth column.
- The shared greeting and common message body are separate editable boxes.
- The default greeting places the name, well-wish, connection note, and company/role context on separate paragraphs for clean LinkedIn copy/paste formatting; the earlier one-line default migrates automatically.
- Supported placeholders are `{first_name}`, `{name}`, `{company}`, `{position}`, and `{connected_on}`.
- Each row's Copy message button combines and personalizes the two template boxes at copy time.
- Greeting/body text and sparse outreach status, date, and notes edits persist in the current browser's local storage for this review stage.
- All-connections is the default view; relevance ranking still places useful AI/ML and technical reviewers first, and optional recommended/manager filters remain available.

## Columns

1. Name (LinkedIn link when available)
2. Current role
3. Current company
4. Connected on
5. Reviewer type
6. Copy message
7. Outreach status
8. Last contacted
9. Notes
10. Why relevant
11. Relevance score
12. Registry company
13. Registry category
14. Referral status
15. Match method
16. Official careers page
17. Direct job portal
18. Email address

## Email boundary

The connection export contains 111 unique nonblank emails, or 3.2% of 3,486 connections. Email is returned only for the explicitly requested private Network Reviews screen. Gmail referral enrichment still receives the contact-free `Connection` model. The app does not automatically email anyone and does not send connection emails to an LLM or log their values.

## Verification

- Real-data API result: 3,486 connections, 3,448 LinkedIn links, 111 email addresses, and 3,486 rows when filters are off.
- The API returns JSON with the email field present without printing real values during verification.
- Explicit-email and contact-free referral-loader regression tests pass.
- 109 Python tests pass and focused Ruff checks pass.
- The React TypeScript/Vite production build passes.
- No browser is attached to this Codex session, so an interactive visual click-through is not claimed.

## Status

Implementation is complete. The user will review all columns and later choose the desired default visible/hidden set. A FastAPI restart and browser hard refresh are required because the previously running backend predates the network API route.
