# BidPilot UAE — Product Requirements

**Version:** 2.0  
**Status:** Build specification  
**Scope:** Production-minded personal portfolio project

## 1. Problem

SMEs may receive long tender documents containing eligibility rules, mandatory certificates, deadlines, submission instructions, contractual risks, and evidence requirements. Initial review is slow and inconsistent. Missing one mandatory condition can waste the entire bid effort.

BidPilot converts an unstructured tender into a reviewable decision workspace.

## 2. Initial user

The first persona is a business-development or tender coordinator at a UAE facilities-management SME.

Typical company:

- 10–100 employees.
- Reviews several tenders each month.
- Has no dedicated legal or proposal-analysis team.
- Reuses licences, certificates, case studies, and staff CVs.
- Needs a fast bid/no-bid recommendation but remains responsible for the final decision.

For the portfolio version, one authenticated user and one company profile are sufficient. The domain model should not prevent future organizations, but full multi-tenancy is not required.

## 3. Core user journey

1. User registers or signs in.
2. User creates a company profile.
3. User records company evidence and capabilities.
4. User creates a tender project.
5. User uploads a tender PDF.
6. Backend processes the file asynchronously.
7. User sees real processing stages.
8. System extracts metadata, requirements, and risks with citations.
9. System compares requirements against approved company facts.
10. Backend calculates a decomposed readiness score.
11. User reviews findings and can override statuses with a reason.
12. User exports or presents the final report.

## 4. MVP features

### Required

- Email/password authentication.
- One user-owned company profile.
- Tender project CRUD.
- PDF upload with type and size validation.
- Text-based PDF extraction using PyMuPDF.
- Page-aware source preservation.
- OCR fallback for scanned pages if time permits; otherwise return a clear unsupported-quality warning.
- Tender metadata extraction.
- Requirement extraction using structured outputs.
- Requirement categories and mandatory status.
- Source-page and source-quote citations.
- Citation verification.
- Company evidence matching.
- Risk-clause detection.
- Deterministic readiness score.
- Human review and override.
- Processing status and error reporting.
- JSON and CSV export; PDF export is optional.
- API documentation.
- Automated tests.
- Docker-based local setup.
- Deployable frontend and backend.

### Strong portfolio additions

- Retry failed analysis.
- Duplicate file detection with SHA-256.
- Token and estimated AI cost tracking.
- Analysis version history.
- Side-by-side citation viewer.
- Evaluation dataset with expected requirements.
- GitHub Actions checks.
- Demo seed script.

### Explicitly postponed

- Billing and subscriptions.
- Enterprise SSO.
- Complex organization invitations.
- Kubernetes.
- Kafka or event streaming.
- Multiple independent microservices.
- Automated tender submission.
- Procurement-portal scraping.
- Live collaborative editing.
- Legal conclusions.
- Fine-tuned models.
- Autonomous agents negotiating or changing bids.

## 5. Functional requirements

### Company profile

Capture:

- Legal company name.
- Trade-licence activities.
- Emirate and operating geography.
- Years in business.
- Employee count.
- Certifications and expiry dates.
- Services and capabilities.
- Similar completed projects.
- Maximum preferred contract value.
- Available bid team.
- Free-text notes.

### Tender project

Capture:

- Tender title.
- Buyer.
- Tender reference.
- Submission deadline.
- Industry.
- Status.
- Uploaded file.
- Analysis version.

### Extracted requirement

Each canonical requirement must include:

- Original requirement text.
- Normalized requirement.
- Category.
- Mandatory, optional, or uncertain.
- Source page.
- Exact source quote.
- Confidence.
- Expected evidence.
- Match status.
- Human review state.

Categories:

- Legal and registration.
- Certification.
- Technical capability.
- Experience.
- Staffing.
- Financial.
- Insurance.
- Bid bond or performance guarantee.
- Submission instruction.
- Deadline.
- Commercial.
- Contractual.
- Health, safety, and environment.
- Data and cybersecurity.
- Other.

### Compliance statuses

- `unreviewed`
- `met`
- `partially_met`
- `not_met`
- `needs_clarification`
- `not_applicable`

### Risk finding

Include:

- Risk type.
- Severity.
- Clause summary.
- Source page and quote.
- Why it matters.
- Suggested human review action.

Risk types:

- Liquidated damages.
- Indemnity and liability.
- Termination.
- Payment terms.
- Performance guarantee.
- Bid bond.
- Insurance.
- Data/privacy.
- Intellectual property.
- Unclear scope.
- Aggressive deadline.
- Other.

## 6. Non-functional requirements

### Reliability

- Long-running analysis must not block HTTP requests.
- Jobs must have explicit states.
- Model calls require timeouts and bounded retries.
- Malformed model output must not corrupt persisted analysis.
- Processing should be repeatable using versioned inputs and prompts.

### Security

- Secrets only in environment variables.
- Passwords hashed with Argon2 or bcrypt.
- JWT access token plus secure refresh approach, or secure cookie sessions.
- API keys never sent to the browser.
- Uploads restricted by extension, MIME type, and size.
- Filenames sanitized; storage paths generated by the server.
- Uploaded content treated as untrusted data, never instructions.
- Logs must not include passwords, keys, full document text, or raw tokens.

### Explainability

- Every material finding must expose its evidence.
- “Not found” means the application did not find evidence; it does not prove absence.
- Scores expose dimensions, weights, inputs, and blockers.
- Human overrides require a reason and do not erase the original machine finding.

### Performance targets for demo

- API health response under 500 ms locally.
- Upload endpoint returns quickly after saving and queuing.
- A 30–80 page text PDF should complete within a reasonable live-demo window depending on API latency.
- Frontend remains responsive during processing.

## 7. Success criteria

The project is complete when a reviewer can:

1. Sign in.
2. Create or load a company profile.
3. Upload a sample tender.
4. Observe processing stages.
5. Inspect at least ten cited requirements.
6. Open the source page for a finding.
7. See evidence matches and gaps.
8. Understand the readiness calculation.
9. Override one finding.
10. Export or download the result.

## 8. Portfolio narrative

Use this explanation:

> I built BidPilot as a production-minded modular monolith. I deliberately avoided microservices because the workload did not justify them. The difficult engineering work is in reliable document processing, schema-constrained extraction, citation verification, deterministic scoring, background jobs, and human-review workflows. The architecture is small enough for one developer to operate but disciplined enough to extend.
