# Discussion 006: Referral contact lookup and enrichment

- Date: 2026-07-20
- Status: discussion — lookup links added; contact enrichment is not approved
- Related queue items: Q-013, Q-014

## Immediate outcome

The `Runs` tab now has a separate `O:R` panel with clickable links for Hunter, Apollo,
RocketReach, Lusha, ContactOut, and SignalHire. The panel records the typical available
data, recommended lookup order, and a caution note. It is generated on every production
rebuild and was verified with six working `HYPERLINK` formulas.

No external contact database was scraped, queried, or given the supplied Connections
export. No email address or phone number was added to Google Sheets.

## Recommendation

For the personal MVP, use one-person manual lookups for only the strongest referral
candidates. If enrichment becomes repetitive, accept a small user-exported vendor CSV and
match it locally by LinkedIn profile URL. This is simpler, lower-risk, and easier to audit
than giving the application a contact-database API key.

Do not scrape provider websites or use unauthorized LinkedIn overlays. A later automated
integration must use one selected provider's documented API, its permitted use case, and
its rate/credit limits.

## Alternatives and tradeoffs

1. **Manual lookup** — no new project credentials and minimal disclosure, but requires a
   few clicks per candidate.
2. **User-exported vendor CSV** — repeatable local import without long-lived vendor access,
   but the user must export results and the file contains sensitive contact data.
3. **Official provider API** — convenient automation and verification metadata, but adds
   API credentials, recurring credits/cost, vendor dependency, and third-party disclosure.
4. **Website scraping** — rejected because it is unstable, may bypass provider controls or
   terms, and is inappropriate for collecting personal contact data.

## Required access and privacy implications

An API integration would require a vendor account/API key stored only in deployment
secrets. Each lookup would disclose at least a name and employer or LinkedIn profile URL to
that vendor. Phone numbers and personal emails are more sensitive than professional work
emails and should not be stored by default.

The current fixed rule excludes connection email addresses from Sheets. Adding any contact
value therefore requires explicit user approval and a revised storage rule. If approved,
contact data should live only in the private `Connections` tab with `contact_type`,
`contact_source`, `confidence`, and `verified_at`; it should not be duplicated into the
dated application queue.

## Decision required before implementation

The user must choose:

1. manual vendor CSV import or one named provider's official API;
2. professional work email only, or whether phone/personal email may also be stored; and
3. permission to revise the existing no-email-in-Sheets rule.

Until those choices are approved, the project remains manual lookup only.
