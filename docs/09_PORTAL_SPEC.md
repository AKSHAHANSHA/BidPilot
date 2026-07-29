# 09 — Two-Sided Portal Specification

This document pins the contract for the marketplace layer added on top of the original
single-vendor analysis product. It is the authority for anything the code does not yet say;
where this document and the code disagree, the code is a bug.

## 1. What changed conceptually

The original product had one kind of user: a bidder analysing a tender document they had been
sent. The portal adds the other side of the transaction.

| Concept | Original | Portal |
| --- | --- | --- |
| `User` | one role | `account_type` ∈ {`company`, `vendor`}, fixed at registration |
| `Tender` | a vendor's **private** analysis workspace, unchanged | — |
| `TenderListing` | — | a buyer's **public** opportunity |
| `Application` | — | a vendor's bid on a listing |
| `ApplicationScreening` | — | OCR + deterministic scoring of that bid's documents |

`Tender` and `TenderListing` are deliberately separate tables. Merging them would put a
vendor's private uploads one predicate away from the public feed.

## 2. Roles

- **company** — publishes listings, defines the document checklist, reviews applicants, decides.
- **vendor** — browses listings, applies, uploads documents, tracks outcomes.

`account_type` is immutable. `Organisation.account_type` caches it and is never updated.

Route guards live in `app/api/dependencies.py` beside `CurrentUser`:

```python
CurrentCompany = Annotated[User, Depends(require_company)]
CurrentVendor  = Annotated[User, Depends(require_vendor)]
```

Both raise `ForbiddenError` (403) — never 404 — when the account is on the wrong side. The
resource exists; the caller simply may not act on it.

## 3. Endpoints

All paths are under `settings.api_v1_prefix` (`/api/v1`). Every list endpoint returns the
existing `Page[T]` envelope from `app/schemas/common.py`.

### 3.1 Public — no authentication

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/public/listings` | Paginated catalogue. Filters: `category`, `emirate`, `q`, `budget_min`, `budget_max`, `closing_within_days`, `sort` ∈ {`deadline`,`newest`,`budget_high`,`budget_low`}. Only `status='published'`. |
| GET | `/public/listings/{listing_id}` | One published listing plus its document checklist and buyer organisation. |
| GET | `/public/categories` | All 30 `TenderCategory` members with a display label and a live count of published listings. Categories with zero listings are still returned — the landing page renders the full taxonomy. |
| POST | `/public/search` | AI-assisted natural-language match. §5. |
| GET | `/public/stats` | Hero counters: published listings, distinct buyers, total published value, category count. |

Public responses never include: `owner_user_id`, draft/cancelled listings, applicant
identities, or any `estimated_cost`.

### 3.2 Authentication

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/auth/register` | Body gains `account_type` and a required `organisation` object. Creates user + organisation in one transaction. |
| POST | `/auth/password-reset/request` | Always 202, whether or not the address exists — a differing response is an account-enumeration oracle. Rate limited per email+IP. |
| POST | `/auth/password-reset/confirm` | `{token, new_password}`. Single-use; consuming it revokes every refresh session for that user. |
| GET | `/auth/me` | Gains `account_type` and an `organisation` summary. |

### 3.3 Company

| Method | Path |
| --- | --- |
| POST | `/listings` (creates a draft) |
| GET | `/listings` (own listings; filter `status`) |
| GET/PATCH | `/listings/{id}` |
| PUT | `/listings/{id}/requirements` (replaces the whole checklist) |
| POST | `/listings/{id}/publish` · `/listings/{id}/close` |
| GET | `/listings/{id}/applications` (applicants, ranked by screening score) |
| PATCH | `/applications/{id}/decision` (`{status, note}` — `shortlisted`/`approved`/`rejected`) |

### 3.4 Vendor

| Method | Path |
| --- | --- |
| POST | `/applications` (draft against a published listing) |
| GET | `/applications` (own; filter `status`) |
| GET/PATCH | `/applications/{id}` |
| POST | `/applications/{id}/documents` (multipart; one file per call) |
| DELETE | `/applications/{id}/documents/{document_id}` |
| POST | `/applications/{id}/submit` (validates, then enqueues screening) |
| POST | `/applications/{id}/withdraw` |
| GET | `/applications/{id}/screening` (status + findings; poll while `pending`/`processing`) |
| GET | `/applications/stats` (dashboard aggregates — §6) |

### 3.5 Notifications

`GET /notifications` (filter `unread_only`) · `POST /notifications/{id}/read` ·
`POST /notifications/read-all`

## 4. Screening pipeline

Triggered by `POST /applications/{id}/submit`. Runs as a Dramatiq job through the existing
`JobQueue` protocol, which gains a second method:

```python
async def enqueue_screening(self, screening_id: uuid.UUID) -> None: ...
```

Stages, each committing its transition exactly like `app/workers/pipeline.py`:

1. **validating** — at least one document; listing still open.
2. **extracting_text** — PyMuPDF native text per page (`app/documents/extraction.py`).
3. **ocr** — pages whose native text is below the readable threshold are re-read with OCR
   (§7). Pages that remain unreadable increment `pages_needing_ocr`; they are never silently
   treated as blank.
4. **classifying** — the LLM proposes, per checklist requirement, which uploaded document
   satisfies it, with `source_page` and a verbatim `evidence_quote`.
5. **verifying** — every proposed quote is re-checked against the stored page text using the
   existing three-tier matcher in `app/domain/citation.py`. A quote that does not verify
   demotes the finding to `missing`. A `source_page` outside the batch is dropped, exactly as
   requirement extraction already does.
6. **scoring** — `app/domain/screening.py`, pure Python (§8).
7. **completed** — writes the score, then the notifications.

Failure sets `ScreeningStatus.FAILED` with an `AnalysisErrorCode`. The vendor may resubmit.

**The model never produces the score.** It only proposes matches; Python counts verified ones.

## 5. Natural-language search

`POST /public/search {query, limit}` where `query` is text like *"we do MEP fit-out in Sharjah,
about 30 staff"*.

1. The query is untrusted input. It is passed as the **user** message between the standard
   `DOCUMENT_DELIMITER` markers with the injection guard on the system prompt, never
   interpolated into the system prompt.
2. The model returns only a **structured interpretation** — categories, emirates, a budget
   band, keywords — validated by a Pydantic model with `extra="forbid"`.
3. Ranking is deterministic Python over that interpretation. The model does not order results
   and never sees the listing set, so it cannot invent a listing.
4. `interpretation` is echoed back so the UI can show what was understood and let the user
   correct it.

With no API key configured the provider factory returns a keyword provider that derives the
same structured interpretation with plain text processing. Search degrades in quality; it does
not break, and it never pretends a model ran.

## 6. Vendor dashboard aggregates

`GET /applications/stats` returns counts by status (`draft`, `submitted`, `under_review`,
`shortlisted`, `approved`, `rejected`, `withdrawn`), a `waiting` roll-up
(`ApplicationStatus.open_states()`), and money:

- `total_bid_value` — sum of `bid_amount` over approved applications.
- `total_margin` — sum of `bid_amount - estimated_cost` over approved applications where both
  are present.
- `margin_percentage` — `total_margin / total_bid_value`, null when the denominator is zero.
- `win_rate` — approved ÷ (approved + rejected), null when nothing has been decided.

Applications missing a figure are excluded from that figure's aggregate and counted in
`incomplete_financials`, so a partly-filled dashboard is visibly partial rather than quietly
wrong.

## 7. OCR

`app/documents/ocr.py` defines an `OcrEngine` protocol with one method. Two implementations:

- `TesseractOcrEngine` — renders the page with PyMuPDF and runs Tesseract. Used when
  `settings.ocr_enabled` and the binary is present.
- `NullOcrEngine` — the default. Returns nothing and reports `available = False`.

A page is sent to OCR only when its native text is shorter than
`settings.ocr_min_native_chars`. When no engine is available those pages are counted in
`pages_needing_ocr` and reported to the vendor as "could not be read" — never as "missing".

## 8. Deterministic screening score

`app/domain/screening.py`, pure functions over dataclasses, no ORM and no I/O — the same shape
as `app/domain/completion.py`.

```
mandatory_ratio = Σ weight(met mandatory)  / Σ weight(all mandatory)
optional_ratio  = Σ weight(met optional)   / Σ weight(all optional)

score = round(100 * (0.8 * mandatory_ratio + 0.2 * optional_ratio))
```

- A listing with no optional requirements scores on mandatory alone (the optional term is
  dropped and the mandatory weight renormalised to 1.0).
- `present_expired` counts as **half** its weight: the document exists, so this is a renewal
  problem, not a gap.
- `present_unreadable` scores **zero** but is reported separately from `missing`, because the
  two need different actions from the vendor.
- `not_applicable` is removed from both numerator and denominator.
- Any unmet mandatory requirement sets `has_blocking_gap`. The score is still shown: a buyer
  is entitled to see that an otherwise strong bid is missing one certificate.

Weights are declared in a module-level table with an import-time guard, following
`app/domain/completion.py`.

## 8a. Certificate verification

A vendor can print any number on a PDF. A certificate is therefore worth what the issuing
register says about it, not what the document claims, and screening checks the two against each
other.

**The register.** `certificate_registry` holds the accreditation records screening looks up:
a normalised `certificate_number` (unique), the `display_number` as printed, the standard, who
it was issued to, the issuing body, validity dates, and a `CertificateStatus`. It is reference
data — no account owns a row, nothing is created through the API. In a real deployment this
would be a call to the issuing body's public register; reproducing it locally is what lets
screening run offline and deterministically.

**The check**, in `app/domain/certificates.py` — pure, no ORM, no I/O:

1. `extract_certificate_numbers` reads candidate numbers out of the extracted page text of the
   document that matched the requirement. The pattern is `ISO` + a 4–5 digit standard + a
   two-letter country + a 4–6 digit serial, tolerant of separators and case because the text
   came out of a PDF. It is deliberately *not* tolerant of structure: matching a bare digit run
   would collect invoice numbers and page footers.
2. The pipeline looks the normalised number up in the register — one query for the whole
   submission, not one per candidate.
3. `assess_certificate` turns the pair into a verdict.

| Register says | Verdict | Credit |
| --- | --- | --- |
| Found, active, in date | `present` | full |
| Found, past `expires_on` | `present_expired` | half |
| Found, suspended or withdrawn | `present_unverified` | **none** |
| Number not in the register | `present_unverified` | **none** |
| No number could be read from the document | `present_unverified` | **none** |

`present_unverified` is a distinct verdict, not a rebadged `missing`, because the two need
different actions: the vendor *did* upload a file, and telling them it is missing would send
them to find a document they already sent. The finding's note records the number that was
checked and why it failed, so the failure is actionable rather than mysterious.

Expiry is decided from `expires_on`, not from the stored `status`: any register refreshed on a
schedule contains rows whose status has not caught up with their dates. The date is the fact.

A register lookup that errors must not fail the run — a register outage is not the vendor's
fault. The screening completes with the document reported as unverified.

Which requirement types are credential-checked is a module-level constant. Today it is
`ISO_CERTIFICATION`; insurance certificates and trade licences are the obvious next entries.

## 9. Notifications written

| Event | Recipient | Type |
| --- | --- | --- |
| vendor submits | listing owner | `application_received` |
| screening completes | listing owner (with score) and vendor | `screening_completed` |
| screening fails | vendor | `screening_failed` |
| buyer decides | vendor | `application_status_changed` |
| listing closes | every applicant | `listing_closed` |

## 10. Hard rules this layer must not break

From `CLAUDE.md`, restated where the portal could plausibly violate them:

1. Route handlers translate HTTP and nothing else. Every decision lives in a service.
2. Every user-owned query filters by the authenticated user. Public endpoints are the sole
   exception and are restricted to `status='published'`.
3. Uploaded documents and search queries are untrusted evidence, never instructions.
4. No material finding without a verified citation — a `present` verdict must name a document.
5. The LLM does not calculate the score.
6. "Not found" is not proof of non-existence — wording in every missing-document message must
   say what was searched, not assert the vendor lacks the document.
7. No fabricated progress percentages; poll real stage names.
8. `estimated_cost` is vendor-private and must never appear in a buyer-facing schema.
