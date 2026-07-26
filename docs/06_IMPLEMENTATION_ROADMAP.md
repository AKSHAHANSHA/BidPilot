# BidPilot UAE — Implementation Roadmap

## Rule

Do not ask Claude Code to build everything in one pass. Complete and verify one phase before beginning the next.

## Phase 0 — Repository foundation

Deliver:

- Backend and frontend folders.
- Docker Compose for PostgreSQL and Redis.
- FastAPI health endpoint.
- Typed settings.
- SQLAlchemy and Alembic.
- Ruff, type checking, pytest.
- `.env.example`.
- Makefile.
- CI checks.

Exit test:

- Backend starts.
- Migration runs.
- Health and readiness pass.
- `make check` passes.

## Phase 1 — Authentication and ownership

Deliver:

- Register/login/refresh/logout/me.
- Password hashing.
- User model.
- Ownership dependency and repository rules.
- Basic rate limiting.
- Auth integration tests.

Exit test:

- User A cannot access User B’s tender.

## Phase 2 — Company profile and evidence

Deliver:

- Company profile CRUD.
- Evidence CRUD.
- Expiry dates and verification status.
- Seed data.

Exit test:

- Demo company can be created through API and UI.

## Phase 3 — Tender and upload

Deliver:

- Tender CRUD.
- PDF upload.
- MIME, extension, size, and hash validation.
- Local storage adapter.
- Document records.
- Duplicate warning.

Exit test:

- Valid PDF is stored and invalid file is rejected with problem details.

## Phase 4 — Page-aware extraction

Deliver:

- PyMuPDF extraction.
- Page records.
- Page quality score.
- Empty/scanned PDF detection.
- Extracted page API.

Exit test:

- Every page in sample PDF is retrievable with correct numbering.

## Phase 5 — Background jobs and progress

Deliver:

- Redis broker.
- Worker.
- Persistent analysis state machine.
- Retry.
- SSE or polling endpoint.

Exit test:

- API remains responsive while sample job processes.

## Phase 6 — Requirement extraction

Deliver:

- LLM provider adapter.
- Strict schemas.
- Prompt templates.
- Batched extraction.
- Persistence.
- Token/cost tracking.

Exit test:

- At least ten structured requirements extracted from the sample tender.

## Phase 7 — Citation verification

Deliver:

- Exact and normalized quote matching.
- Fuzzy fallback.
- Correction retry.
- Rejected-finding handling.

Exit test:

- No canonical requirement has an invalid citation.

## Phase 8 — Evidence matching and risks

Deliver:

- Deterministic exact match rules.
- Semantic match adapter.
- Risk extraction and citations.
- Human review status.

Exit test:

- ISO, geography, and experience examples produce explainable statuses.

## Phase 9 — Readiness and report

Deliver:

- Versioned scoring function.
- Dimension output.
- Hard blockers.
- Decision label.
- Narrative from validated records.
- Human override.

Exit test:

- Same structured inputs always produce the same numerical score.

## Phase 10 — Frontend core

Deliver:

- Auth.
- Tender desk.
- Company profile.
- New tender.
- Processing timeline.
- Command center.
- Compliance matrix.
- Source viewer.
- Risk register.
- Readiness report.

Exit test:

- Complete demo path works without API tools.

## Phase 11 — Evaluation and polish

Deliver:

- Gold sample set.
- Evaluation script.
- CSV export.
- Engineering-notes page.
- README architecture diagram.
- Demo seed/reset script.
- Playwright critical journey.

Exit test:

- Evaluation report saved.
- Demo can be reset in one command.

## Phase 12 — Deployment

Recommended lightweight deployment:

- Frontend: Vercel or Cloudflare Pages.
- Backend and worker: Render or Railway.
- PostgreSQL: Neon, Supabase, Render, or Railway.
- Redis: Upstash, Render, or Railway.
- Storage: S3-compatible or persistent disk for a controlled demo.

Exit test:

- Public demo works with sample documents.
- CORS and cookie/token behavior verified.
- Secrets absent from repository.

## Priority if time becomes limited

Must keep:

1. Page-aware extraction.
2. Structured requirements.
3. Citation verification.
4. Deterministic scoring.
5. Human review.
6. End-to-end frontend.

Can postpone:

- OCR.
- Anthropic provider.
- pgvector.
- PDF export.
- Password reset.
- Advanced audit history.
