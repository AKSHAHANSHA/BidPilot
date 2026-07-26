# BidPilot UAE — API Contract and Data Model

## 1. API conventions

Base path:

```text
/api/v1
```

Use:

- JSON for application data.
- Multipart upload or signed upload depending on deployment.
- Cursor or simple page pagination; simple page pagination is acceptable for this project.
- RFC 7807-compatible errors.
- UTC ISO 8601 timestamps.
- UUID identifiers.

## 2. Core entities

### User

- `id`
- `email`
- `password_hash`
- `display_name`
- `is_active`
- `created_at`
- `updated_at`

### RefreshSession

- `id`
- `user_id`
- `token_hash`
- `expires_at`
- `revoked_at`
- `created_at`
- `user_agent`
- `ip_hash` optional

### CompanyProfile

**Implemented in Phase 2** (migration `0003`). One per user, enforced by
`UNIQUE (owner_user_id)`.

- `id`, `owner_user_id` → `users.id` `ON DELETE CASCADE`
- `legal_name`, `trading_name` nullable, `description`, `industry`
- `emirate` (check constraint, seven values), `country`
- `year_established`, `employee_count`, `years_of_experience`
- `trade_licence_number`, `trade_licence_expiry`, `licence_activities` `text[]`
- `website` nullable, `contact_email`, `contact_phone` nullable
- `annual_revenue_range` nullable (check constraint), `preferred_contract_value_min` /
  `_max` `numeric(14,2)` nullable
- `service_categories` `text[]`, `geographic_coverage` `text[]` — both non-empty
- `profile_completion_percentage`, `completion_version` — recalculated on every write; reads
  serve a freshly calculated score
- timestamps
- `UNIQUE (id, owner_user_id)` exists only to support the children's composite foreign key

### CompanyEvidence

**Implemented in Phase 2.** Named `company_evidence`, not `evidence_items`.

- `id`, `owner_user_id`, `company_profile_id`
- `FOREIGN KEY (company_profile_id, owner_user_id)` → `company_profiles (id, owner_user_id)`
  `ON DELETE CASCADE` — this is what makes cross-user attachment unrepresentable
- `title`, `category` (check constraint, twelve values), `issuing_organisation` nullable,
  `reference_number` nullable, `description`
- `issue_date` nullable, `expiry_date` nullable, `CHECK (issue_date <= expiry_date)`
- `verification_status` (check constraint: `unverified` | `verified` | `rejected`),
  `verification_notes` nullable
- `tags` `text[]`, normalized to lower case, GIN indexed
- timestamps

Expiry state is **not a column**. It is derived per request from `expiry_date` and
`verification_status` — see `docs/08` D29. File-storage columns arrive with Phase 3; the API
already returns a stable `attachment: null`.

### CompanyProject

**Implemented in Phase 2.** A separate entity rather than an evidence subtype, so contract
value, dates, location, and delivered services are filterable columns (`docs/08` D26).

- `id`, `owner_user_id`, `company_profile_id` with the same composite foreign key
- `client_name`, `project_title`, `industry`, `description`
- `contract_value` `numeric(14,2)` nullable, `currency`
- `start_date`, `end_date` nullable, `status` (`completed` | `current`)
- `CHECK (start_date <= end_date)` and `CHECK` that a `current` project has no end date while a
  `completed` one must have one
- `location`, `services_delivered` `text[]` non-empty and GIN indexed, `outcome` nullable
- `client_reference_available`, `is_confidential`
- timestamps

### Tender

- `id`
- `owner_user_id`
- `title`
- `buyer`
- `reference`
- `industry`
- `submission_deadline`
- `status`
- timestamps

### Document

- `id`
- `tender_id`
- `original_filename`
- `stored_filename`
- `storage_key`
- `mime_type`
- `size_bytes`
- `sha256`
- `page_count`
- `extraction_status`
- timestamps

### DocumentPage

- `id`
- `document_id`
- `page_number`
- `text`
- `normalized_text`
- `quality_score`
- `extraction_method`

### Analysis

- `id`
- `tender_id`
- `version`
- `status`
- `current_stage`
- `error_code`
- `started_at`
- `completed_at`
- `provider`
- `model`
- `prompt_version`
- `input_tokens`
- `output_tokens`
- `estimated_cost`
- timestamps

### TenderMetadata

- `analysis_id`
- `buyer`
- `reference`
- `submission_deadline`
- `contract_duration`
- `estimated_value`
- `currency`
- `summary`
- citations JSON

### Requirement

- `id`
- `analysis_id`
- `category`
- `obligation`
- `original_text`
- `normalized_text`
- `expected_evidence` JSON
- `confidence`
- `machine_status`
- `reviewed_status`
- `review_reason`
- `reviewed_at`
- timestamps

### RequirementCitation

- `id`
- `requirement_id`
- `document_id`
- `page_number`
- `source_quote`
- `verified`
- `match_method`
- `match_score`

### RequirementEvidenceMatch

- `id`
- `requirement_id`
- `evidence_item_id` nullable
- `status`
- `explanation`
- `confidence`
- `missing_evidence` JSON

### RiskFinding

- `id`
- `analysis_id`
- `risk_type`
- `severity`
- `summary`
- `why_it_matters`
- `suggested_action`
- `confidence`
- review fields

### RiskCitation

Same core fields as requirement citation.

### ReadinessAssessment

- `analysis_id`
- `overall_score`
- `decision_label`
- `dimension_scores` JSON
- `hard_blockers` JSON
- `assumptions` JSON
- `calculation_version`
- `human_override_label` nullable
- `human_override_reason` nullable

### AuditEvent

- `id`
- `owner_user_id`
- `entity_type`
- `entity_id`
- `action`
- `before_json`
- `after_json`
- `created_at`

For a portfolio system, audit only meaningful review and state transitions. Do not create an enterprise audit platform.

## 3. Endpoint set

### Authentication

```text
POST   /auth/register
POST   /auth/login
POST   /auth/refresh
POST   /auth/logout
GET    /auth/me
```

Optional:

```text
POST   /auth/forgot-password
POST   /auth/reset-password
```

### Company

As implemented in Phase 2. `PATCH` replaces the originally planned `PUT` because updates are
partial, and `POST`/`DELETE` on the profile plus the full project set were added.

```text
POST   /company
GET    /company
PATCH  /company
DELETE /company                       cascades to evidence and projects

GET    /company/evidence              ?category= &verification_status= &expiry_state=
                                      &search= &tag= &limit= &offset=
POST   /company/evidence
GET    /company/evidence/{evidence_id}
PATCH  /company/evidence/{evidence_id}
DELETE /company/evidence/{evidence_id}

GET    /company/projects              ?status= &search= &service= &limit= &offset=
POST   /company/projects
GET    /company/projects/{project_id}
PATCH  /company/projects/{project_id}
DELETE /company/projects/{project_id}
```

List responses use an offset-pagination envelope: `{ items, total, limit, offset }`, where
`total` ignores `limit`/`offset`.

### Tenders

```text
GET    /tenders
POST   /tenders
GET    /tenders/{tender_id}
PATCH  /tenders/{tender_id}
DELETE /tenders/{tender_id}
```

### Documents

```text
POST   /tenders/{tender_id}/documents
GET    /tenders/{tender_id}/documents
GET    /documents/{document_id}
GET    /documents/{document_id}/pages/{page_number}
DELETE /documents/{document_id}
```

### Analysis

```text
POST   /tenders/{tender_id}/analyses
GET    /tenders/{tender_id}/analyses
GET    /analyses/{analysis_id}
POST   /analyses/{analysis_id}/retry
GET    /analyses/{analysis_id}/events
```

The `events` endpoint may use SSE. Polling every 2–3 seconds is an acceptable fallback.

### Requirements

```text
GET    /analyses/{analysis_id}/requirements
GET    /requirements/{requirement_id}
PATCH  /requirements/{requirement_id}/review
```

Query filters:

- category.
- obligation.
- status.
- confidence range.
- citation verified.

### Risks

```text
GET    /analyses/{analysis_id}/risks
PATCH  /risks/{risk_id}/review
```

### Readiness

```text
GET    /analyses/{analysis_id}/readiness
PATCH  /analyses/{analysis_id}/readiness/override
```

### Reports

```text
GET    /analyses/{analysis_id}/report
POST   /analyses/{analysis_id}/exports
GET    /exports/{export_id}
GET    /exports/{export_id}/download
```

Start with JSON and CSV exports. PDF can be added after the core workflow.

## 4. Response examples

### Analysis summary

```json
{
  "id": "...",
  "status": "processing",
  "current_stage": "verifying_citations",
  "stage_message": "Verifying 42 extracted requirements against source pages.",
  "started_at": "2026-07-26T12:00:00Z",
  "completed_at": null,
  "can_retry": false
}
```

### Readiness

```json
{
  "overall_score": 68.4,
  "decision_label": "conditional_bid",
  "dimensions": [
    {
      "key": "eligibility_fit",
      "label": "Eligibility fit",
      "raw_score": 75,
      "weight": 25,
      "weighted_score": 18.75,
      "explanation": "One mandatory certification requires clarification."
    }
  ],
  "hard_blockers": [],
  "assumptions": [
    "Only evidence marked verified by the user was used."
  ],
  "human_override": null
}
```

## 5. Ownership rules

Every tender, document, analysis, requirement, risk, report, and evidence record must be reachable through the authenticated owner.

Do not accept `owner_user_id` from request bodies.

Repository methods should require the authenticated user ID:

```python
get_tender_for_user(tender_id, user_id)
```

Never fetch by tender ID and check ownership later in an unrelated layer.

## 6. Database constraints

Add:

- Unique user email.
- Unique `(tender_id, analysis_version)`.
- Unique document SHA within a tender where appropriate.
- Check confidence between 0 and 1.
- Check scores between 0 and 100.
- Foreign-key cascades intentionally chosen.
- Indexes on ownership, tender, analysis, status, category, and deadline.

## 7. OpenAPI and frontend contract

Generate `openapi.json` in CI or through a Make command. Generate TypeScript types/client from the contract rather than manually duplicating backend interfaces.
