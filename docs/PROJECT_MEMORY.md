# BidPilot UAE — Project Memory & Handoff

Last updated: 2026-07-28
Current branch: main
Latest commit: fb2fefa — fix(deploy): escape percent signs in Alembic database URL
Project status: Phases 0–12 complete; backend + frontend feature-complete and verified locally; deployment configuration prepared but **not deployed** (no cloud accounts provisioned).

> A durable handoff summary of the whole BidPilot build. Sources: `BUILD_PROGRESS.md`,
> `docs/08_ENGINEERING_DECISIONS.md`, git history, `README.md`, and the development sessions.
> Contains **no** secrets — environment variables are listed by name only.

---

## 1. Product purpose and target user

BidPilot UAE helps a UAE contractor decide **whether to bid on a tender before spending days
preparing a submission**. A user uploads a tender PDF; the system extracts its requirements and
risks, compares them against the user's own company evidence, and produces a **cited, explainable
bid-readiness score**. The score is computed by explicit Python rules — never guessed by a model —
and every material finding is backed by a verified quote from a real page of the document.

**Target user:** a single owner/estimator at a small-to-mid UAE facilities-management contractor.
**Project identity:** a production-minded **personal portfolio project**, not enterprise SaaS —
reliable, explainable, testable, secure enough for a public demo, and maintainable by one developer
(see `CLAUDE.md`). Advisory only: it never produces legal conclusions or submits bids.

## 2. Final architecture

Modular monolith. **Backend:** FastAPI + Pydantic v2 + SQLAlchemy 2 (async, asyncpg) + Alembic;
PostgreSQL; Redis; Dramatiq worker. **Frontend:** React 19 + TypeScript (strict) + Vite 6 +
Tailwind CSS v4 + React Router 7 + TanStack Query 5 + openapi-fetch/openapi-typescript.

Hard rules that shaped everything: no microservices/Kubernetes/Kafka/SSO/billing/multi-tenancy;
route handlers hold no business logic and never call LLMs directly; provider keys/DB secrets/refresh
tokens/signed storage secrets are never exposed to the frontend; every user-owned query enforces
authenticated ownership; uploaded documents are untrusted evidence, never instructions; page
provenance is preserved throughout; no canonical finding without a verified citation; "not found"
never proves non-existence; the LLM never computes the final score; narrative reports use validated
structured records, not raw-document analysis; human overrides require a reason and preserve the
original machine result.

Request path: browser → FastAPI (API) → Postgres/Redis; uploads → storage (local or S3). Analysis
is enqueued to Redis and consumed by the Dramatiq worker, which runs the ordered pipeline and writes
findings back to Postgres. The frontend polls analysis status and renders real stage progress.

## 3. Phase 0 → Phase 12 summary

| Phase | Scope | Status |
|---|---|---|
| 0 | Repo foundation: typed config (fail-fast), JSON logging + request-id, RFC 7807 errors, async DB, Alembic baseline, health endpoints, CI, Makefile + `make.ps1` | Complete |
| 1 | Auth: Argon2id, JWT access + rotating HttpOnly refresh sessions, Redis rate limiting, ownership-enforcing repositories | Complete |
| 2 | Company profile, evidence (12 categories) with derived expiry, projects; profile completion scoring; demo seed | Complete |
| 3 | Tender CRUD; secure multipart PDF upload; storage adapter; SHA-256 duplicate detection | Complete |
| 4 | Page-aware PyMuPDF extraction; per-page records + normalized text; quality scoring; unsupported/scanned detection | Complete |
| 5 | Dramatiq + Redis worker; analysis state machine; real stage progress; retry; idempotent re-runs | Complete |
| 6 | OpenAI adapter; schema-constrained (strict) structured extraction; versioned prompts; token/cost accounting; requirements API | Complete |
| 7 | Citation verification: exact / normalized / fuzzy (difflib) matching; rejection of unsupported quotes | Complete |
| 8 | Deterministic evidence matching; cited risk extraction; human review of requirement status | Complete |
| 9 | Deterministic readiness scoring (6 weighted dimensions); hard blockers; report; human override with reason | Complete |
| 10 | Frontend: auth, tender desk, upload, command center (dial, compliance matrix, risk register, source drawer), company + evidence/project CRUD, client-side export | Complete |
| 11 | Gold-set evaluation harness + metrics (CSV/JSON), demo-reset, Playwright journey; matcher defect found & fixed | Complete |
| 12 | Deployment configuration + docs (Vercel + Render + Postgres + Redis + S3 storage); later reworked into a fully free single-service shape | Config ready, not deployed |

Exact commit hashes for the recent phases: Phase 10 core `11dcd52`, OpenAI strict fix `af1b6b0`,
Phase 10 tail `b7e6b4b`, Phase 11 `b3ba924`, Phase 12 portfolio config `5357a24`, auth-refresh fix
`fb4d258`, free-deployment `62c6b99`, Alembic `%` fix `fb2fefa`.

## 4. Important architectural decisions (see `docs/08_ENGINEERING_DECISIONS.md`, D1–D54)

- **Dramatiq over Celery** behind a small `JobQueue` protocol (DramatiqJobQueue in prod,
  EagerJobQueue in tests) — Redis-native, minimal ceremony.
- **Async everywhere, one DB driver** (asyncpg); worker actors are thin sync wrappers calling
  `asyncio.run`.
- **Argon2id** password hashing (no bcrypt 72-byte footgun).
- **Composite foreign-key ownership** `(entity_id, owner_user_id)` makes cross-user attachment
  unrepresentable at the database level; an `OwnedRepository` base requires `user_id` on every
  read/list/delete.
- **Deterministic scoring in pure Python** with a `SCORING_VERSION`; the LLM never scores.
- **Citation verification is pure functions** (exact → normalized → fuzzy, threshold 0.90) so a
  finding is canonical only when its quote verifies against extracted page text.
- **Pipeline as an ordered stage registry** (`app/workers/pipeline.py`); each stage commits
  immediately so DB status always reflects real progress.
- **RFC 7807 problem+json** error contract; tracebacks/provider messages are logged, never
  serialized.
- **Controlled vocabularies are DB check constraints** — extending one needs a small migration
  (deliberate: a typo'd category must not silently hide evidence).
- **Storage behind a `StorageBackend` protocol** — local FS for dev, S3-compatible for deploy (D14,
  D54).
- **Evaluation reuses the real pipeline** (no re-implemented rules); gold-replay provider gives a
  zero-cost mocked run, real OpenAI only under an explicit cost-capped command (D53).

## 5. Major bugs discovered and how they were fixed

- **Phase 4 — `document.id` None before flush:** DocumentPage rows referenced `document.id` before
  the flush that applies the UUID default → FK violation, masked by an over-broad
  `except IntegrityError` as a duplicate-SHA 409. Fixed by flushing the document first and narrowing
  the exception to the specific constraint.
- **Phase 4 — migration ordering:** autogenerated migration created `document_pages` before the
  unique constraint its composite FK references; reordered by hand.
- **Phase 6 — retry idempotency:** re-running an analysis hit unique constraints re-inserting
  metadata/requirements; added `_reset_findings` to clear prior findings first.
- **Phase 7 — fuzzy window misalignment:** a fixed-length sliding window mis-aligned on an inserted
  char (scored 0.88 < 0.90). Fixed by aligning to the longest common block via
  `SequenceMatcher.find_longest_match`.
- **Live OpenAI (gpt-5-mini) incompatibilities (`af1b6b0`):** the model rejects a custom
  `temperature` (omit it unless set) and strict structured outputs require every property in
  `required` with `additionalProperties:false` (added a recursive `_strictify`).
- **Phase 11 — matcher over-matching (D53):** the evaluation showed evidence-match accuracy 0.71
  because `match_requirement` returned `met` on **any** shared token, so a generic category noun
  ("insurance", "iso", "trade licence") alone counted as a match — inflating out-of-domain tenders.
  Fixed by requiring a *discriminating* shared token (`_GENERIC_MATCH_TOKENS`) and a punctuation-aware
  tokenizer; accuracy rose to 0.96. One integration fixture updated to a discriminating term.
- **Frontend — dead token-refresh (`fb4d258`):** the access token lives in memory and expires after
  15 min, but the `withRefresh` helper was never wired in, so an expired token surfaced as
  "Authentication is required". Fixed with auth middleware that clones each request and, on a 401,
  refreshes once and replays it; added `authedFetch` for the multipart upload; a definitively failed
  refresh clears the user and returns to sign-in. Verified live with a deliberately corrupted token.
- **Deploy — Alembic `%` interpolation (`fb2fefa`):** Supabase pooled connection passwords can
  contain `%`, which Alembic's ConfigParser interprets; escaped to `%%` in `migrations/env.py`.

## 6. Authentication and ownership design

Access token is a short-lived JWT (default 15 min) held **in memory only** on the frontend (never
localStorage — an XSS payload cannot read a persisted credential). The refresh token is an
**HttpOnly, Secure, SameSite-scoped** cookie, rotated on each use; refresh sessions are stored
server-side and revoked on use. Rate limiting (Redis) guards login and registration. Ownership is
enforced **inside every repository query** via the composite `(id, owner_user_id)` key and the
`OwnedRepository` base — requesting another user's record returns 404, never a confirmation it
exists. Cookie `Secure`/`SameSite` derive from `APP_ENV` (lax+insecure locally, none+secure when
deployed cross-site between Vercel and Render).

## 7. Company profile and evidence model

A single company profile per user (legal/trading name, industry, emirate, employee count, years of
experience, trade licence + expiry, licence activities, contacts, revenue range, preferred contract
value range, service categories, geographic coverage). **Evidence** items across 12 categories
(trade licence, certification, insurance, financial statement, previous project, client reference,
staff CV, technical capability, equipment asset, policy, registration, other), each with a
**derived expiry state** (active / expiring-soon / expired / no-expiry / unverified) computed on
read, never persisted. **Projects** capture past work (client, title, value, dates, services,
outcome). A **profile-completion percentage** is recomputed on read (a stale stored value is never
served). Only **user-verified** evidence counts in matching.

## 8. Tender upload and storage workflow

Create a tender (title, buyer, reference, submission deadline), then upload its PDF as multipart.
The file is validated by content (not filename), size- and page-bounded, and de-duplicated by
SHA-256 within a tender. Page-aware text is extracted **before persistence** (a corrupt/encrypted/
oversized PDF is rejected with no file and no row). The stored object key is server-generated and
opaque: `{user_id}/{tender_id}/{uuid}.pdf` — a client filename never becomes a key. Files are
served **only through authenticated backend endpoints**; no public or pre-signed URLs. Storage is
selected by `STORAGE_BACKEND`: `local` filesystem (dev default) or `s3` (Supabase Storage / MinIO /
AWS S3) via boto3 wrapped in `asyncio.to_thread`, private bucket, bounded retries and timeouts.

## 9. Extraction → jobs → LLM → citation → matching → scoring pipeline

Ordered stages (each commits its transition): `validating → extracting_text → assessing_quality →
extracting_metadata → extracting_requirements → verifying_citations → matching_evidence →
analysing_risks → scoring → generating_report → completed`.

- **Extraction (Phase 4):** PyMuPDF, page-aware, with normalized text and a per-page quality score;
  scanned/low-text pages flagged unsupported (no OCR).
- **Jobs (Phase 5):** Dramatiq consumes from Redis; the analysis state machine records real
  progress and supports retry and idempotent re-runs.
- **LLM (Phase 6):** OpenAI adapter behind a provider protocol; strict `json_schema` structured
  outputs validated against Pydantic models; versioned prompts; token/cost accounting. Anthropic
  fallback exists but is **disabled by default**.
- **Citation (Phase 7):** every extracted requirement/risk quote is verified against the cited
  page's text (exact → normalized → fuzzy ≥ 0.90); unverifiable quotes are rejected, not persisted
  as canonical.
- **Matching (Phase 8):** deterministic mapping of requirement categories to evidence categories,
  requiring a discriminating token overlap for `met`; absence yields `not_met`/`needs_clarification`,
  never a proven lack.
- **Scoring (Phase 9):** deterministic Python over citation-verified findings — 6 weighted
  dimensions (eligibility fit, mandatory compliance, capability/experience, evidence completeness,
  deadline feasibility, contract risk), hard blockers, an overall 0–100 score and decision label
  (do_not_bid / weak_bid / conditional_bid / strong_bid / insufficient_information). Humans can
  override the label with a mandatory reason; the machine result is preserved.

## 10. Frontend design system and completed screens

**"Procurement Ledger" identity:** paper tone `#fbfaf5`, signal red `#b51f26`, fonts
Newsreader / Source Sans 3 / IBM Plex Mono; hairline rules and editorial-red accents. Access token
in memory + silent refresh; TanStack Query for remote state; deep-link/hard-refresh restores the
session. **Screens:** auth (login/register); tender desk; new-tender + PDF upload; tender command
center (readiness dial + decision stamp, hard-blocker notices, six weighted dimension rows,
compliance matrix, risk register, slide-in source-citation drawer with quote highlighting, readiness
override); company workspace (profile with completion + edit modal, evidence table with live expiry
and CRUD, projects with CRUD, confirm dialogs); engineering-notes page. Accessible modal (focus
trap, Escape closes), RFC 7807 field-error mapping, loading/empty/error states, client-side CSV/JSON
export. Design was reviewed and approved by the user.

## 11. Evaluation metrics and real API costs

Gold set: one fictional FM company + **five fictional tenders** (`backend/eval/gold/`) spanning
do_not_bid → strong_bid, with ground-truth requirement/citation/risk annotations, mandatory flags,
expected evidence-match outcomes, and calibrated score bands. `t3` embeds a **citation trap** that
verification must reject.

- **Mocked run (`make eval`, $0):** requirement P/R 1.0/1.0, mandatory recall 1.0, citation validity
  0.975 (trap rejected), citation accuracy 1.0, risk P/R 1.0/1.0, evidence-match accuracy 0.96,
  determinism 1.0.
- **Live run (`make eval-live`, gpt-5-mini):** citation validity **0.988**, determinism 1.0, actual
  cost **$0.3536**. Requirement/risk lexical P/R (0.38/0.69, 0.31/0.87) are understated by the
  eval's strict lexical matcher (reworded-but-correct extractions count as misses); citation
  validity is the trustworthy real-world signal. `citation_accuracy` is meaningful only in the
  index-aligned mocked run.
- Earlier full end-to-end live analysis of the sample tender cost ~**$0.09**.
- **Test totals:** 506 backend tests pass (unit + API + integration, mocked providers); frontend
  typecheck/lint/build pass; Playwright journey 2 passed / 1 skipped. Committed sample report:
  `backend/eval/reports/sample_mock_evaluation.{json,csv}`.

## 12. Git and deployment status

All work is on `main`, latest `fb2fefa`, working tree clean. One commit per phase/change. Nothing
has been deployed: no cloud accounts created, no paid infrastructure provisioned. Deployment is
**configuration + documentation only**, ready for the user to apply manually.

## 13. Free student deployment plan (see `deploy/DEPLOYMENT.md`)

Completely free target: **Vercel Hobby** (frontend) + **one Render Free Web Service** that runs the
API and the Dramatiq worker in the same container (`backend/scripts/start.sh`) + **Supabase**
(PostgreSQL and a private S3-compatible Storage bucket) + **Upstash** (Redis, TLS `rediss://`) +
existing OpenAI key. `render.yaml` defines a single free service (no paid worker); `start.sh`
migrates, launches the worker in the background, then serves uvicorn with `--proxy-headers`,
forwarding SIGTERM for clean shutdown and keeping the API up if the worker dies. Verified locally:
`/health/live` 200, `/api/v1/health/ready` reports database+redis ok, worker and API co-located with
distinguishable logs, clean SIGTERM shutdown. Supabase: use the **pooled** connection string
(port 6543, `postgresql+asyncpg://…?ssl=require`) for runtime; migrations run via `start.sh`. Vercel
gets only `VITE_API_BASE`; **no backend secrets in Vercel**.

## 14. Environment variables (names only — never store values here)

**Backend (dev, `backend/.env.example`):** `APP_ENV`, `APP_NAME`, `API_V1_PREFIX`, `LOG_LEVEL`,
`FRONTEND_ORIGIN`, `DATABASE_URL`, `REDIS_URL`, `POSTGRES_HOST_PORT`, `REDIS_HOST_PORT`,
`JWT_SECRET`, `ACCESS_TOKEN_MINUTES`, `REFRESH_TOKEN_DAYS`, `PASSWORD_MIN_LENGTH`,
`REFRESH_COOKIE_NAME`, `EVIDENCE_EXPIRING_SOON_DAYS`, `LOGIN_MAX_ATTEMPTS`, `LOGIN_WINDOW_SECONDS`,
`REGISTER_MAX_ATTEMPTS`, `REGISTER_WINDOW_SECONDS`, `STORAGE_BACKEND`, `UPLOAD_DIR`,
`MAX_UPLOAD_BYTES`, `MAX_PDF_PAGES`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `ANTHROPIC_API_KEY`,
`ANTHROPIC_MODEL`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES`, `PROMPT_VERSION`, `SCORING_VERSION`.

**Backend (production adds/overrides, `backend/.env.production.example`):** `REFRESH_COOKIE_SAMESITE`,
`REFRESH_COOKIE_SECURE`, `S3_ENDPOINT_URL`, `S3_REGION`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`,
`S3_BUCKET_NAME` (plus optional `S3_CONNECT_TIMEOUT`, `S3_READ_TIMEOUT`, `S3_MAX_ATTEMPTS`).

**Frontend:** `VITE_API_BASE` only (empty in dev → Vite proxy; the Render origin in production).

Secrets (`JWT_SECRET`, `DATABASE_URL`, `REDIS_URL`, `OPENAI_API_KEY`, all `S3_*`) live only in the
host dashboards and local git-ignored `.env`; `render.yaml` marks them `sync:false`.

## 15. Known limitations

- No file upload attached to evidence yet (response carries a contract-stable `attachment: null`).
- No OCR — scanned PDFs return a clear unsupported-quality warning.
- No password reset (needs email delivery a portfolio demo lacks); no virus scanning on uploads.
- Single user, single company profile; no multi-tenancy/RBAC.
- Server-side signed exports are future work (current export is client-side over loaded data).
- Matcher residual: it cannot distinguish a *specific* certificate from *any* certificate in the
  same category (surfaced honestly by the eval, not hidden).
- Live requirement/risk precision/recall are understated by the eval's lexical matching.
- Free-tier: Render sleeps (~1 min cold start), API+worker restart together with no auto worker
  restart, Supabase pauses after ~1 week idle, Upstash free caps apply, OpenAI is not free without
  credits, container disk is ephemeral (uploads go to durable Supabase Storage), advisory-only.

## 16. Exact local run commands

One-time setup (from `backend/`, then run each; they return to the prompt):
```
py -3.12 -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
./make.ps1 up          # Postgres + Redis via Docker
./make.ps1 migrate     # alembic upgrade head
./make.ps1 seed        # fictional demo company
```
Then three long-running processes in three terminals:
```
cd backend && ./make.ps1 api        # FastAPI on http://127.0.0.1:8000
cd backend && ./make.ps1 worker     # Dramatiq worker
cd frontend && npm install && npm run dev   # Vite (prints its port, e.g. 5173)
```
Demo sign-in: `demo@fm-demo.ae` / `bidpilot-demo-passphrase-1`. Reset demo: `./make.ps1 demo-reset`.
(Bash equivalents: `make up`, `make migrate`, etc.)

## 17. Exact verification commands

Backend (from `backend/`):
```
./make.ps1 check          # ruff format --check + ruff check + mypy app + unit/API tests
./make.ps1 test           # unit + API tests (no external services)
./make.ps1 test-integration   # needs Postgres + Redis (./make.ps1 up first)
./make.ps1 eval           # gold-set evaluation, mocked, zero cost
./make.ps1 eval-live      # gold-set evaluation, real OpenAI, cost-capped $1.00
```
Frontend (from `frontend/`):
```
npm run typecheck
npm run lint
npm run build
npx playwright test       # needs the stack running + `npx playwright install chromium` once
```

## 18. Recommended next actions

1. **Deploy the free stack** following `deploy/DEPLOYMENT.md` (create Supabase, Upstash, Render,
   Vercel; set the named secrets; run `seed_demo.py` once). Verify the live smoke path end to end.
2. **Add evidence file attachments** (S3 keys already flow through the storage adapter) — the
   contract already reserves `attachment: null`.
3. **Improve the matcher's specific-vs-any-certificate weakness** (the eval already quantifies it;
   consider matching expected-evidence tokens against evidence titles more strictly, or an
   LLM-assisted capability check gated behind determinism).
4. **Server-side signed/streamed exports** (PDF/CSV) through authenticated endpoints.
5. **Sweep expired refresh sessions on a schedule** (currently revoked on use only).
6. **Optional: model-written narrative** over the validated structured summary (kept out so far to
   avoid a hallucination surface).
