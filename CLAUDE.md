# BidPilot Claude Code Rules

## Project purpose

BidPilot UAE helps a UAE contractor decide **whether to bid on a tender before preparing a full
submission**. A user uploads a tender PDF; the system extracts its requirements and risks, compares
them against the user's own company evidence, and produces a **cited, explainable bid-readiness
score** computed by explicit Python rules — never guessed by a model. Every material finding is
backed by a verified quote from a real page. It is a production-minded **personal portfolio
project** (reliable, explainable, testable, secure enough for a public demo, maintainable by one
developer), not enterprise SaaS. Advisory only — it never produces legal conclusions or submits bids.

Status: **complete** (Phases 0–12). Feature-complete and verified locally; deployment config exists
but nothing is deployed. See `docs/PROJECT_MEMORY.md` for full history/handoff (read only when the
task needs it). Design specs live in `docs/00`–`docs/07`; decisions in `docs/08_ENGINEERING_DECISIONS.md`.

## Current architecture

Modular monolith. **Backend** (`backend/`): FastAPI + Pydantic v2 + SQLAlchemy 2 async (asyncpg) +
Alembic; PostgreSQL; Redis; Dramatiq worker. **Frontend** (`frontend/`): React 19 + TypeScript
(strict) + Vite 6 + Tailwind v4 + React Router 7 + TanStack Query 5 + openapi-fetch (types generated
from the backend OpenAPI schema).

- Route handlers hold **no** business logic and never call LLMs directly — logic lives in services;
  the pipeline lives in the worker.
- Analysis runs as an ordered stage registry in `app/workers/pipeline.py`, enqueued to Redis and
  consumed by Dramatiq; each stage commits so DB status reflects real progress (no fake percentages).
- Storage behind a `StorageBackend` protocol: `local` filesystem (dev default) or `s3`
  (Supabase/MinIO/AWS) selected by `STORAGE_BACKEND`. Object keys are server-generated and opaque.
- Errors use RFC 7807 problem+json; tracebacks/provider messages are logged, never serialized.
- Do **not** introduce microservices, Kubernetes, Kafka, SSO, billing, or multi-tenancy.

## Local run commands

One-time setup (from `backend/`):
```
py -3.12 -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
./make.ps1 up          # Postgres + Redis via Docker
./make.ps1 migrate     # alembic upgrade head
./make.ps1 seed        # fictional demo company
```
Then three long-running processes, one per terminal:
```
cd backend && ./make.ps1 api        # FastAPI on http://127.0.0.1:8000
cd backend && ./make.ps1 worker     # Dramatiq worker
cd frontend && npm install && npm run dev
```
Demo sign-in: `demo@fm-demo.ae` / demo passphrase from the seed fixture. Reset: `./make.ps1 demo-reset`.
(POSIX equivalents: `make up`, `make migrate`, … `make.ps1` is the Windows shim with identical targets.)

## Test / verification commands

Backend (from `backend/`):
```
./make.ps1 check            # ruff format --check + ruff check + mypy app + unit/API tests
./make.ps1 test             # unit + API tests (no external services)
./make.ps1 test-integration # needs Postgres + Redis (run ./make.ps1 up first)
./make.ps1 eval             # gold-set evaluation, mocked, zero cost
./make.ps1 eval-live        # gold-set evaluation, real OpenAI, cost-capped $1.00
./make.ps1 openapi          # regenerate the OpenAPI artifact
```
Frontend (from `frontend/`): `npm run typecheck`, `npm run lint`, `npm run build`,
`npx playwright test` (needs the stack running + `npx playwright install chromium` once).

Do not claim something works without running its verification command; add/update tests with any
behavior change; keep README, OpenAPI, migrations, and `.env.example` current.

## Deployment architecture

Free single-service shape (config + docs only; not deployed). See `deploy/DEPLOYMENT.md`.
- Frontend: **Vercel Hobby** (static Vite build; only env var is `VITE_API_BASE`).
- Backend: **one Render Free Web Service** running `backend/scripts/start.sh`, which migrates,
  launches the Dramatiq worker in the background, then serves uvicorn with `--proxy-headers`.
  `render.yaml` defines a single free service — no separate paid worker.
- PostgreSQL: **Supabase** (pooled `postgresql+asyncpg://…?ssl=require`).
- Redis: **Upstash** (TLS `rediss://`).
- Storage: **Supabase private bucket** via its S3-compatible API.
- Production cookies are cross-site: `REFRESH_COOKIE_SAMESITE=none` + `REFRESH_COOKIE_SECURE=true`;
  CORS is an exact allowlist (`FRONTEND_ORIGIN`), never a wildcard.

## Critical security rules

- Never expose provider keys, database secrets, refresh tokens, or storage credentials to the
  frontend. The frontend receives only `VITE_API_BASE`.
- The access token lives in memory only (never localStorage); the refresh token is an HttpOnly,
  Secure, rotated cookie.
- Every user-owned query enforces authenticated ownership via the composite `(id, owner_user_id)`
  key / `OwnedRepository` base. Another user's record returns 404, never a confirmation it exists.
- Uploaded documents are untrusted evidence, **never instructions**. Files are served only through
  authenticated endpoints — never public or pre-signed URLs.
- Logs exclude passwords, tokens, keys, full document text, and complete prompts.

## LLM and citation rules

- The LLM only performs schema-constrained (strict `json_schema`) extraction; output is validated
  against Pydantic models before it can become a persisted finding.
- No canonical material finding without a **verified source citation**: each quote is checked against
  the cited page's text (exact → normalized → fuzzy ≥ 0.90); unverifiable quotes are rejected.
- Preserve document and page provenance throughout analysis.
- "Not found" does **not** prove non-existence — absence yields `not_met`/`needs_clarification`.
- Narrative reports are assembled from validated structured records, not raw-document analysis.
- Keep OpenAI usage cost-controlled; the Anthropic fallback stays disabled by default.

## Deterministic scoring rule

The final readiness score is computed by **deterministic Python** (`app/domain/scoring.py`, six
weighted dimensions, hard blockers, versioned by `SCORING_VERSION`) over citation-verified findings
only — the LLM never scores. Human overrides require a reason and preserve the original machine
result. Evidence matching (`app/domain/matching.py`) and citation verification are pure, testable
functions.

## Major completed milestones

- Phase 0–1: repo foundation, fail-fast config, RFC 7807 errors, health checks; Argon2id auth with
  rotating refresh sessions, Redis rate limiting, ownership-enforcing repositories.
- Phase 2–3: company profile, evidence (12 categories, derived expiry), projects; tender CRUD and
  secure page-validated PDF upload with SHA-256 dedupe.
- Phase 4–5: page-aware PyMuPDF extraction + quality scoring; Dramatiq worker, analysis state
  machine, retry, idempotent re-runs.
- Phase 6–9: OpenAI structured extraction; citation verification; deterministic evidence matching +
  cited risks + human review; deterministic readiness scoring, report, and override.
- Phase 10: full React frontend ("Procurement Ledger" design), command center, company/evidence/
  project CRUD, client-side export.
- Phase 11: gold-set evaluation harness + metrics (mock citation validity 0.975, evidence-match 0.96;
  live citation validity 0.988; live gold-set cost ~$0.35); demo-reset; Playwright journey.
- Phase 12: free single-service deployment config (Vercel + Render + Supabase + Upstash) and docs.

## Known limitations

- No OCR (scanned PDFs return a clear unsupported-quality warning); no evidence file attachments yet
  (`attachment: null` is contract-stable); no password reset; no upload virus scanning.
- Single user / single company profile; no multi-tenancy or RBAC.
- Server-side signed exports are future work (current export is client-side).
- Matcher cannot distinguish a *specific* certificate from *any* certificate in the same category
  (surfaced by the eval, not hidden).
- Free-tier: Render cold starts (~1 min), API+worker restart together, Supabase pauses after ~1 week
  idle, Upstash caps apply, OpenAI is not free without credits, container disk is ephemeral.

## Files that must never be committed

- `backend/.env`, any real `.env` (only `*.env.example` templates are committed).
- Real secrets of any kind: `JWT_SECRET`, `DATABASE_URL`, `REDIS_URL`, `OPENAI_API_KEY`, all `S3_*`
  values — they live only in host dashboards / git-ignored local env.
- Uploaded or private documents, `backend/data/` uploads, coverage output (`.coverage`, `htmlcov/`).
- `.venv/`, `node_modules/`, `frontend/dist/`, timestamped `backend/eval/reports/evaluation_*`.
  (Note: `backend/artifacts/openapi.json` **is** committed intentionally — the frontend generates
  its types from it.)
