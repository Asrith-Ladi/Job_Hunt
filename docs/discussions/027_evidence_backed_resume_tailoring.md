# Evidence-backed resume tailoring

Date: 2026-08-17
Queue item: Q-037
Status: implemented

## Request

Avoid treating a JD keyword as unsupported when the active resume already documents the same capability with different wording. When a genuinely new JD skill is supported by a factual user note, place it in the relevant Technical Skills category instead of a generic `Additional Skills` line. Also use supported JD wording naturally in the generated resume summary or work bullets so the result remains readable to both ATS parsers and people.

## Decision

The application distinguishes three states:

1. **Exact wording**: the literal JD term is already present in the baseline.
2. **Equivalent documented evidence**: a conservative, auditable alias/concept mapping finds the same capability in the baseline even though the employer uses different words.
3. **Unsupported gap**: neither exact nor equivalent evidence exists; the term stays excluded unless the user supplies a factual note and explicitly confirms it.

Equivalent matching is deterministic and local. It does not add an LLM call. The literal before/after ATS estimate continues to count only terms that actually occur in the corresponding DOCX text.

## Generated resume behavior

- Supported equivalent terms and explicitly confirmed terms are placed under an existing relevant Technical Skills sub-heading when possible; otherwise a specific category such as `Backend & APIs` or `Cloud & DevOps` is created.
- The existing single Luna planning call may naturally reframe the professional summary and up to a small number of relevant work bullets.
- A work bullet may receive an exact JD phrase only when that same source bullet independently supports the whole phrase. Whole-resume evidence may justify a skill-section term but cannot be used to misattribute facts to one employer.
- Validation preserves every numeric claim and rejects target-employer insertion, contact data, placeholders, excessive expansion, or a rewrite that moves too far from its source evidence.
- Reference documents and user-confirmed notes may support truthful positioning, but they do not authorize inventing achievements or assigning unrelated evidence to a past employer.
- The private baseline is never edited; every output is a generated copy requiring user review.

## Product interpretation

This improves transparent keyword coverage and human readability, but it cannot guarantee selection by a proprietary employer ATS. Unsupported requirements remain visible as honest gaps rather than being silently inserted.
