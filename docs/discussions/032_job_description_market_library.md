# 032 - Private job-description market library

Date: 2026-08-25
Queue item: Q-042
Status: discussion / awaiting implementation approval

## Request

Retain job descriptions and responsibilities after the application has gathered them so the
user can analyze recurring market expectations, prioritize skill development, and improve
future resume evidence. Also provide useful AI/ML search terms as editable defaults.

## Decision brief

### Immediate outcome

Build a private, deduplicated evidence library from verified official postings. Temporary
Gmail, Company Portal, and ATS search results remain temporary. A record enters this library
only after the user explicitly runs **Find official JD + score** and an official candidate is
successfully validated.

### Recommended approach

1. Reuse the already-gathered official posting; do not make a second LLM or web-search call.
2. Upsert by provider job ID or canonical official URL. Record `first_seen_at`, `last_seen_at`,
   capture time, active status, and a description hash. Preserve a new version only when the
   verified description changes.
3. Store a compact Drive index at `Job Hunt/Source/jd_market_index.json` and private versioned
   snapshots under `Job Hunt/Market Intelligence/JDs`. This avoids repeatedly rewriting one
   increasingly large file and keeps the storage implementation replaceable later.
4. Store company, title, location, provider, official URL, requisition ID, publication date,
   experience evidence/range, employment/workplace type, description summary,
   responsibilities, required/preferred qualifications, required/preferred skills with
   evidence, and the source-confidence/provenance fields.
5. Store full description text only when it was actually returned by a permitted official
   public page/feed. When exact text was not available, save only the grounded structured
   evidence already returned; never invent or reconstruct the missing text.
6. Add a later **Market Insights** view with filters for time window, role family, location,
   company group, and experience range. Calculate skill/responsibility frequency,
   co-occurrence, and experience distributions deterministically before considering any
   optional LLM narrative.
7. Label every result with its sample size and source coverage. Present it as evidence from
   the user's collected postings, not as a universal market standard.

### Alternatives and tradeoffs

- Saving every search result would collect more data but would violate the approved temporary
  search lifecycle and retain many partial or false matches.
- One large JSON file is simpler, but every new JD would require downloading and uploading the
  entire growing corpus. A compact index plus immutable snapshots scales more safely.
- A Google Sheet is convenient for manual review but is a poor canonical store for long job
  descriptions and version history. A later CSV/XLSX export can be generated from the index.
- An LLM-generated market summary can be useful later, but deterministic counts are cheaper,
  reproducible, and should come first.

### Access and privacy

- No new Google scope is required; the existing `drive.file` permission covers app-created
  library files.
- No Gmail body, LinkedIn connection, contact detail, resume text, prompt, or OAuth secret is
  stored in the market library.
- The snapshots remain private and are for personal analysis; they must not be republished as
  a public job-description dataset.

## Search defaults implemented now

Run Setup starts with editable, comma-separated alternatives covering the current target role
family: AI Engineer, AI/ML Engineer, machine learning, ML Engineer, generative AI, GenAI, LLM,
large language model, agentic AI, AI agent, applied AI, Applied Scientist, Data Scientist,
MLOps, ML platform, NLP, natural language processing, computer vision, deep learning, and
Research Engineer. Phrase-aware OR matching still applies across the title, description, and
department fields exposed by each official source. Removing all text intentionally disables
the keyword filter.

## Decision needed

Approve or revise the recommended automatic save boundary, Drive layout, and deterministic
Market Insights scope before implementation begins.
