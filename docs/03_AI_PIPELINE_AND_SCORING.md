# BidPilot UAE — AI Pipeline, Citations, Matching, and Scoring

## 1. Design principle

The LLM extracts and explains. Application code validates and decides.

Do not ask one giant prompt to read the document and produce the final report. Use a staged pipeline with persisted intermediate records.

## 2. Pipeline

```text
Upload
  ↓
Validation and hashing
  ↓
Page-aware text extraction
  ↓
Page quality assessment
  ↓
Document segmentation
  ↓
Tender metadata extraction
  ↓
Requirement extraction by section/batch
  ↓
Schema validation and normalization
  ↓
Citation verification
  ↓
Duplicate merging
  ↓
Company-evidence matching
  ↓
Risk extraction
  ↓
Deterministic score
  ↓
Narrative report from validated records
  ↓
Human review
```

## 3. Source representation

Preserve each PDF page separately:

```json
{
  "document_id": "uuid",
  "page_number": 14,
  "text": "...",
  "character_count": 2712,
  "extraction_method": "native",
  "quality_score": 0.92
}
```

Normalize whitespace for search while preserving the raw extracted page text.

## 4. Chunking

Prefer section-aware chunks:

- Detect headings using font size and text patterns where possible.
- Keep page boundaries in chunk metadata.
- Target roughly 1,200–2,500 tokens per extraction batch.
- Include a small overlap only when a requirement crosses boundaries.
- Never create a citation that spans unknown pages.

For the first version, page-group batches are acceptable if section detection is unreliable.

## 5. Structured requirement schema

The provider must return a strict object similar to:

```json
{
  "requirements": [
    {
      "original_text": "The bidder shall maintain a valid ISO 9001 certificate.",
      "normalized_text": "Hold a valid ISO 9001 certification.",
      "category": "certification",
      "obligation": "mandatory",
      "expected_evidence": ["ISO 9001 certificate", "expiry date"],
      "source_page": 14,
      "source_quote": "The bidder shall maintain a valid ISO 9001 certificate.",
      "confidence": 0.97
    }
  ]
}
```

Allowed obligation values:

- `mandatory`
- `optional`
- `uncertain`

Reject unknown enums and invalid page numbers.

## 6. Citation verification

A finding becomes canonical only when:

1. Page exists.
2. Quote is not empty.
3. Normalized quote is found on the claimed page, or fuzzy similarity exceeds a documented threshold.
4. Quote supports the normalized requirement.

Implement normalization:

- Unicode normalization.
- Collapse whitespace.
- Normalize curly quotes and hyphens.
- Case-insensitive comparison.

Fallback fuzzy matching can use token similarity. Store:

- `citation_verified`.
- `citation_match_method`.
- `citation_match_score`.

If verification fails:

- Retry once with the exact page text and request correction.
- If still invalid, persist as rejected or uncertain, not canonical.

## 7. Duplicate merging

Requirements may repeat across instructions, scope, and appendices.

Use a two-stage approach:

1. Deterministic candidate generation using normalized text or embeddings.
2. LLM or rule-assisted merge decision with source citations retained.

A merged requirement can have multiple source citations.

Do not delete evidence of repetition; repeated clauses may increase importance.

## 8. Company evidence

For the portfolio version, company facts can be entered manually and optionally extracted from evidence files.

Evidence fact schema:

```json
{
  "fact_type": "certification",
  "name": "ISO 9001",
  "value": "Certified",
  "valid_from": "2025-01-01",
  "valid_until": "2028-01-01",
  "source_document_id": "uuid-or-null",
  "source_page": 1,
  "verified_by_user": true
}
```

Only user-verified facts should be treated as approved evidence.

## 9. Matching

The evidence matcher returns:

- `met`
- `partially_met`
- `not_met`
- `needs_clarification`

It must include:

- Matched evidence IDs.
- Explanation.
- Confidence.
- Missing evidence.

Critical rule:

> Failure to find evidence is `needs_clarification` or `not_met_for_current_profile`, not proof that the company lacks the capability.

Use deterministic matching first for exact certifications, dates, geography, and numeric thresholds. Use an LLM for semantic capability and project-experience matching.

## 10. Risk extraction

Extract only clauses with source evidence. The model should not provide legal advice.

Output language:

- “Requires review.”
- “May create exposure.”
- “The clause appears to require…”

Avoid:

- “This clause is illegal.”
- “The company will lose money.”
- Definitive legal conclusions.

## 11. Readiness scoring

The final score is calculated in Python from verified records.

### Suggested weights

| Dimension | Weight |
|---|---:|
| Eligibility fit | 25 |
| Mandatory compliance | 25 |
| Capability and experience | 15 |
| Evidence completeness | 15 |
| Deadline feasibility | 10 |
| Contract risk | 10 |
| **Total** | **100** |

Each dimension returns 0–100 before weighting.

### Example rules

#### Eligibility fit

- All verified eligibility conditions met: 100.
- One unclear non-blocking item: 75.
- One unmet mandatory eligibility condition: 20.
- Multiple blockers: 0.

#### Mandatory compliance

```text
met = 1.0
partially_met = 0.5
needs_clarification = 0.25
not_met = 0.0
```

Calculate weighted completion across mandatory requirements.

#### Capability and experience

Use matched technical and experience requirements. Apply a confidence penalty to low-confidence semantic matches.

#### Evidence completeness

Percentage of expected evidence items that have approved, current evidence.

#### Deadline feasibility

Example:

- More than 21 days: 100.
- 14–21 days: 80.
- 7–13 days: 55.
- 3–6 days: 25.
- Under 3 days or passed: 0.

Allow configuration because tender complexity varies.

#### Contract risk

Start at 100 and deduct:

- Critical risk: 30 each.
- High risk: 15 each.
- Medium risk: 7 each.
- Low risk: 2 each.

Floor at zero. Cap duplicate deductions for the same clause family.

## 12. Hard blockers

A hard blocker can override the numerical label:

- Submission deadline passed.
- Explicit mandatory registration not met.
- Mandatory certification missing and no alternative permitted.
- Required geography or licence activity does not match.
- Bid bond required but company marks it unavailable.

Hard blockers produce `do_not_bid` or `conditional_bid` depending on whether remediation is realistically possible before the deadline.

## 13. Decision labels

Suggested mapping:

- 80–100: `strong_bid`
- 60–79: `conditional_bid`
- 40–59: `weak_bid`
- 0–39: `do_not_bid`
- Missing critical information: `insufficient_information`

Hard-blocker rules take precedence.

## 14. Narrative report

Generate the narrative only from persisted, validated records. Pass a compact structured summary, not the complete raw tender.

Required sections:

- Executive recommendation.
- Top reasons.
- Hard blockers.
- Major evidence gaps.
- Material risks.
- Immediate next actions.
- Assumptions and limitations.

Every factual tender statement in the report must map to a finding ID and citation.

## 15. Prompt versioning

Store:

- Prompt name.
- Prompt version.
- Provider.
- Model.
- Temperature.
- Schema version.
- Execution timestamp.
- Token usage.

Keep prompt templates in code files, not only in a remote dashboard.

## 16. Evaluation

Create a small gold dataset of 3–5 sample tenders with manually labelled requirements.

Metrics:

- Mandatory-requirement recall.
- Requirement precision.
- Citation page accuracy.
- Quote-verification rate.
- Category accuracy.
- Mandatory/optional accuracy.
- Risk recall on selected clauses.
- Evidence-match agreement.

Primary metric: mandatory-requirement recall.

Targets for a portfolio demo:

- Mandatory recall: at least 85% on the sample set.
- Verified citation rate: at least 90%.
- Invalid canonical citations: 0.

The evaluation script should print results and save a JSON report.
