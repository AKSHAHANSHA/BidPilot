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

- `id`
- `owner_user_id`
- `legal_name`
- `trade_license_activities` JSON
- `emirate`
- `years_in_business`
- `employee_count`
- `services` JSON
- `preferred_contract_min`
- `preferred_contract_max`
- `notes`
- timestamps

### EvidenceItem

- `id`
- `company_profile_id`
- `type`
- `name`
- `description`
- `value_json`
- `valid_from`
- `valid_until`
- `source_document_id` nullable
- `source_page` nullable
- `verified_by_user`
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

```text
GET    /company
PUT    /company
GET    /company/evidence
POST   /company/evidence
PATCH  /company/evidence/{evidence_id}
DELETE /company/evidence/{evidence_id}
```

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
