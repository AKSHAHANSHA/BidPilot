# BidPilot UAE — Testing, Demo, and Deployment

## 1. Test strategy

### Unit tests

Test pure logic:

- Score calculation.
- Hard-blocker rules.
- Deadline scoring.
- Citation normalization.
- Quote matching.
- File validation.
- Requirement status mapping.

### Integration tests

Test:

- PostgreSQL repositories.
- Alembic migrations.
- Auth refresh and revocation.
- Ownership enforcement.
- Upload and page extraction.
- Worker state transitions.

Use real PostgreSQL and Redis through Docker for integration tests where practical.

### Provider contract tests

Mock provider responses to verify:

- Valid structured output accepted.
- Invalid enum rejected.
- Missing citation rejected.
- Timeout retried within limit.
- Provider error converted to safe application error.

Do not make normal CI depend on paid live API calls.

### Evaluation tests

Run manually or in an optional CI job using real APIs and sample tenders.

Save:

- Model.
- Prompt version.
- Date.
- Metrics.
- Estimated cost.

### Frontend tests

- Component tests for status controls and error states.
- API mocking with MSW.
- Playwright critical journey.

## 2. Required test cases

### Security

- Wrong password returns generic error.
- Expired token rejected.
- Revoked refresh token rejected.
- User cannot fetch another user’s tender.
- Path traversal filename does not affect storage path.
- Oversized file rejected.
- Non-PDF renamed as PDF rejected.
- Prompt-injection text remains source content.

### Documents

- Text PDF extracts pages.
- Empty PDF returns clear failure.
- Duplicate upload detected.
- Correct page numbers preserved.

### AI

- Malformed JSON does not persist partial canonical findings.
- Hallucinated page number rejected.
- Quote on wrong page rejected.
- “Not found” is not converted into definitive absence.

### Scoring

- Deterministic for same input.
- Scores remain in range.
- Hard blocker overrides label.
- Human override requires reason.

## 3. Make commands

Recommended:

```text
make dev
make api
make worker
make migrate
make seed
make lint
make format
make typecheck
make test
make test-integration
make eval
make openapi
make check
make demo-reset
```

`make check` should run formatting check, lint, type check, unit tests, and safe integration tests.

## 4. Demo dataset

Create:

- One fictional facilities-management company.
- 8–12 evidence items.
- One 25–50 page fictional or public sample tender.
- Expected requirements file.
- Expected risk examples.

Company example:

- Dubai-based FM provider.
- ISO 9001 valid.
- ISO 14001 missing.
- Two similar projects when tender asks for three.
- Trade licence matches cleaning and maintenance.
- Bid bond availability unknown.

This creates a convincing conditional-bid result.

## 5. Live demo script

1. Open tender desk.
2. Show company evidence.
3. Create tender and upload PDF.
4. Explain real background stages.
5. Open completed seeded analysis if live API latency becomes unpredictable.
6. Show mandatory requirements.
7. Click one citation and show source page.
8. Show missing ISO 14001 and partial experience match.
9. Explain deterministic score.
10. Override one finding with a reason.
11. Export CSV.
12. Open engineering-notes page.

Always keep a completed seeded analysis available as a fallback. This is demo resilience, not deception; state that live processing may depend on external API latency.

## 6. Interview talking points

### Why modular monolith?

The project has one developer and one deployment boundary. Microservices would add networking, deployment, and data-consistency cost without improving the product. Modules and adapters preserve future extraction paths.

### Why background jobs?

PDF extraction and multiple model calls are long-running and failure-prone. A worker keeps HTTP responsive and supports retries and visible stages.

### Why not let the LLM score?

A numeric recommendation must be repeatable and explainable. The model extracts evidence; Python applies explicit rules and weights.

### How are hallucinations reduced?

Strict schemas, page-aware context, exact source quotes, citation verification, retry on invalid citations, and rejection of unsupported findings.

### What would change for commercial production?

- Organization tenancy and stronger RBAC.
- S3 storage and malware scanning.
- Privacy and retention controls.
- Enterprise observability.
- Higher-scale workers.
- Legal review and formal security testing.
- Billing and support workflows.

## 7. README requirements

Include:

- Problem and screenshots.
- Architecture diagram.
- AI pipeline diagram.
- Local setup.
- Environment variables.
- Demo credentials or seed instructions.
- API documentation link.
- Test commands.
- Evaluation results.
- Security and limitations.
- Future roadmap.

## 8. Deployment checklist

- Production secret values configured.
- Debug disabled.
- CORS restricted to frontend origin.
- HTTPS used.
- Secure cookie flags configured if cookies are used.
- Database migrations run.
- Worker running.
- Redis accessible only to services.
- Upload size bounded.
- Logs reviewed for sensitive content.
- API docs optionally protected or left public intentionally for portfolio use.
- Demo sample documents contain no confidential information.
