# BidPilot UAE — Build Progress

Phase-by-phase record of what is built, what was verified, and what remains. A phase is marked
complete only after its verification commands have actually been run and reported.

Roadmap: [docs/06_IMPLEMENTATION_ROADMAP.md](docs/06_IMPLEMENTATION_ROADMAP.md).
Decisions: [docs/08_ENGINEERING_DECISIONS.md](docs/08_ENGINEERING_DECISIONS.md).

| Phase | Scope | Status |
|---|---|---|
| 0 | Repository foundation, config, logging, error contract, health, migrations, CI | Complete |
| 1 | Authentication, refresh rotation, rate limiting, ownership enforcement | Complete |
| 2 | Company profile, evidence, and projects | Complete |
| 3 | Tender CRUD and PDF upload | Complete |
| 4 | Page-aware extraction | Not started |
| 5 | Background jobs and progress | Not started |
| 6 | Requirement extraction | Not started |
| 7 | Citation verification | Not started |
| 8 | Evidence matching and risks | Not started |
| 9 | Readiness scoring and report | Not started |
| 10 | Frontend | Not started |
| 11 | Evaluation and polish | Not started |
| 12 | Deployment | Not started |

---

## Phase 0 — Repository foundation

**Complete.** Modular-monolith skeleton with the four things every later phase depends on.

- Typed configuration that fails fast at startup: async-driver check on `DATABASE_URL`,
  placeholder-secret rejection outside development, bounded upload and LLM limits.
- RFC 7807 problem details as the single error contract. Tracebacks, database messages, and
  provider messages are logged, never serialized.
- Request-ID correlation via pure ASGI middleware, with denylist redaction in the log formatter.
- `/health/live` (checks nothing) and `/health/ready` (Postgres + Redis, 503 problem+json).
- Async SQLAlchemy 2 + asyncpg, Alembic with an intentionally empty `0001` baseline revision.
- `Makefile` plus a `make.ps1` PowerShell shim; Docker Compose; CI workflow; OpenAPI export.

### Verified

`make check` passed (ruff format, ruff check, mypy, unit tests). Migration ran forward and
back. `/health/live` and `/health/ready` returned 200 against real containers; with Redis
stopped, readiness returned **503 `application/problem+json`** naming redis, then recovered.

**86 tests** — 80 unit/API, 6 integration.

### Issues found during verification

1. **Port 5432 already allocated** by an unrelated project's container. Compose now publishes
   55432/56379 with container-internal ports unchanged, overridable via
   `POSTGRES_HOST_PORT`/`REDIS_HOST_PORT`.
2. **`/api/v1/health/ready` logged at INFO** — the noise-suppression list only matched the
   unprefixed alias. Now matched by suffix, covering both mount points.
3. **Duplicate access logging** — `uvicorn.access` overlapped the middleware's structured line.
   Uvicorn's is now raised to WARNING; one correlated access log remains.

---

## Phase 1 — Authentication and ownership

**Complete.** Committed as `1d1c484 feat(auth): implement secure authentication and ownership
foundation`.

- Argon2id password hashing, never trimmed, transparently re-hashed when cost parameters change.
- Short-lived JWT access tokens with a pinned algorithm and a checked `typ` claim.
- Opaque 384-bit refresh tokens stored only as SHA-256, delivered solely as an HttpOnly,
  path-scoped cookie whose `Secure`/`SameSite` attributes derive from `APP_ENV`.
- Refresh rotation with reuse detection: replaying a revoked token revokes the whole family.
- Uniform generic failures; an unknown email still spends a dummy Argon2 verification so
  response timing reveals nothing.
- Redis fixed-window throttling keyed on (account, hashed client IP), failing open.
- `OwnedRepository`: the owner ID is a required parameter of every read, list, and delete.
- Endpoints: `register`, `login`, `refresh`, `logout`, `logout-all`, `me`, `sessions`.
- Migration `0002` — `users`, `refresh_sessions`, with an email-lowercase check constraint.

### Verified

| Command | Result |
|---|---|
| `./make.ps1 check` | passed — ruff format, ruff check, mypy (29 files), 149 unit/API tests |
| `./make.ps1 test-integration` | 62 passed against real PostgreSQL + Redis |
| `alembic downgrade base` → `upgrade head` | clean round-trip, head `0002` |
| `./make.ps1 openapi` | 9 paths, 12 schemas |
| Live curl journey | register → me → refresh rotation → replay → family revocation |

**Final totals: 211 tests — 149 unit/API, 62 integration.**

### The refresh-token rollback bug

Found by live verification, not by the test suite.

**Symptom.** The server logged `refresh_token_reuse_detected sessions_revoked=1`, yet the
rotated token still returned **200** on the next refresh. Reuse detection appeared to work and
did nothing.

**Cause.** `get_session` rolls back when a handler raises. `AuthService.refresh` revoked the
session family and *then* raised `AuthenticationError` to reject the request — so the rollback
discarded the revocation. A known-stolen refresh token would have kept working indefinitely
while every replay was detected and logged.

**Why the tests missed it.** The integration `get_session` override committed on success but had
no rollback-on-exception. Writes made before the raise survived inside the test session, so the
double diverged from production in exactly the way that hid the defect.

**Fix.**
1. `BaseRepository.commit_security_action()` — commits before the error response unwinds the
   request. The single documented exception to "repositories never commit".
2. `AuthService._fail_refresh_durably()` persists the revocation, then raises. Applied to all
   three failure paths: reuse, expiry, and unavailable user.
3. The test override now mirrors `app.core.database.get_session` exactly, rollback included.
4. `test_reuse_detection_survives_the_failed_request` asserts persisted database state rather
   than the response.

**Re-verified live:** replay → 401, rotated token → 401 with `sessions_revoked=0` on the second
detection, confirming the family was already dead.

Recorded as D19 in `docs/08_ENGINEERING_DECISIONS.md`.

### Second issue found

Model-wide `str_strip_whitespace` was silently trimming passwords, so `" passphrase "` would be
stored as `"passphrase"` and a client that trims differently could never sign in. Passwords now
pass through byte-for-byte; text fields are stripped individually. Recorded as D21.

### Scope note

The roadmap's Phase 1 exit test is "User A cannot access User B's **tender**", but tenders arrive
in Phase 3. The ownership mechanism is complete and the invariant is proven on the entities that
exist — cross-user session isolation at both API and repository level, including that mixing two
users' credentials grants no escalation. Phase 3 re-asserts it on tenders.

### Remaining limitations after Phase 1

- **No password reset.** Needs email delivery a portfolio demo does not have; a forgotten
  password requires database access.
- **Proxy-unaware client IP.** `request.client.host` is the direct peer, so behind a proxy the
  recorded IP is the proxy's. A real deployment needs trusted-proxy handling rather than
  trusting a spoofable `X-Forwarded-For`.
- **No scheduled session sweep.** Expired refresh sessions are revoked on use but not swept.
- **Email enumeration on registration.** Duplicate registration returns 409, which confirms an
  address is registered. Deliberate trade-off, recorded as D20.
- **Rate limiting fails open.** A Redis outage disables throttling rather than logins (D23).
- Not built by design: OCR, S3 storage, Anthropic adapter, pgvector, PDF export.

---

## Phase 2 — Company profile and evidence

**Complete.** The company knowledge base that tender requirements will be evaluated against from
Phase 8. Nothing here calls an LLM; it is structured data plus deterministic derivation.

### Verified

| Command | Result |
|---|---|
| `./make.ps1 check` | passed — ruff format, ruff check, mypy (43 files), **191 unit/API tests** |
| `./make.ps1 test-integration` | **143 passed** against real PostgreSQL + Redis |
| `alembic downgrade base` → `upgrade head` | clean round-trip, head `0003` |
| `alembic check` | "No new upgrade operations detected" — model and migration agree |
| `python scripts/seed_demo.py` | 12 evidence items, 2 projects, completion 100%, expiry spread `{active: 3, expiring_soon: 1, no_expiry: 6, unverified: 2}` |
| `./make.ps1 openapi` | 14 paths |
| Live smoke test | login → profile → filters → pagination → projects → cross-user isolation → mutation |

**Final totals: 334 tests — 191 unit/API, 143 integration.**

Live cross-user checks against real PostgreSQL: an intruder's `GET`/`PATCH`/`DELETE` on the demo
user's evidence all returned **404**, their evidence list returned **0**, and an attempt to create
evidence naming the demo user's `company_profile_id` in the body was refused — the body value is
ignored entirely, so it failed on the intruder having no profile of their own.

### The `MissingGreenlet` PATCH bug

Found by the integration suite; every `PATCH` route returned **500** instead of 200.

**Cause.** `updated_at` uses a server-side `onupdate`, so SQLAlchemy leaves it expired after an
UPDATE and reloads it lazily. The response serializers are synchronous, and an implicit SELECT
from a sync call stack cannot drive async IO.

**Why a service-level test would have missed it.** Calling `update_project` directly passed
cleanly, because nothing then read `updated_at`. Only a real `PATCH` over HTTP — which serializes
the row afterwards — reproduced it.

**Fix.** `__mapper_args__ = {"eager_defaults": True}` on `TimestampMixin`, so PostgreSQL returns
the new timestamp via `RETURNING` in the same statement that wrote it. Recorded as D32.

A second, smaller find during development: the `expiring_soon` SQL predicate initially also
matched already-expired rows, contradicting the documented precedence. Caught by the
SQL/Python agreement test before it reached a commit.

### Scope

- **One company profile per user**, enforced by a database unique constraint on
  `owner_user_id`, not only in application code. Structured columns for everything that
  materially supports future matching; `text[]` only for genuinely list-shaped fields.
- **Company evidence** CRUD across twelve categories (trade licence, certification, insurance,
  financial statement, previous project, client reference, staff CV, technical capability,
  equipment, policy, registration, other), with tags, verification status and notes, and
  nullable attachment columns so Phase 3's real upload needs no destructive migration.
- **Company projects** as a separate entity rather than an evidence subtype, so contract value,
  dates, and services delivered are first-class filterable columns.
- **Derived expiry state** — active, expiring soon, expired, no expiry, unverified — calculated
  from dates and verification state on read, never stored, with a configurable threshold
  defaulting to 60 days.
- **Deterministic profile completion** in a versioned pure-Python module with documented field
  weights, bounded to 0–100. Never calculated by the frontend or a model.
- Filtering by category, verification status, expiry state, search term, and tag; offset
  pagination.
- Ownership via the Phase 1 `OwnedRepository` pattern — no ad hoc owner checks in routes.
- Seed data for one fictional UAE facilities-management company, containing no real personal or
  confidential information.

### Excluded from Phase 2

PDF or document upload, object storage, tender entities, AI extraction, embeddings, pgvector,
semantic matching, Redis jobs, frontend, billing, team accounts, public profiles, automated
certification verification, and external UAE government integrations.

### Completion gate — all met

Migration upgrade and downgrade pass · profile, evidence, and project CRUD work · ownership
isolation proven at API, repository, and database levels · profile completion deterministic and
tested · expiry states correct and tested · seed data loads · lint, format, typing, and tests
pass · OpenAPI regenerated · live authenticated smoke test succeeded against real PostgreSQL ·
documentation updated.

### Remaining limitations after Phase 2

- **No file upload on evidence.** The response carries a contract-stable `attachment: null`, but
  no storage columns exist. Every option for adding them in Phase 3 is additive, so building
  them now would be speculation rather than migration safety.
- **Vocabulary changes need a migration.** Evidence category, emirate, verification status, and
  project status are database check constraints generated from the Python enums. Deliberate: a
  typo'd category would silently hide evidence from every filter and from future matching.
- **`profile_completion_percentage` can go stale in storage** after a weight change, until the
  next write. Reads always serve a fresh calculation, so no stale value is returned; a backfill
  command is future work.
- **No cross-entity completion inputs.** Evidence and project counts deliberately do not affect
  the score (D30), so a profile can read 100% with no evidence attached.
- **`search` uses `ILIKE`, not full-text search.** Correct and wildcard-escaped for a handful of
  rows per user; a tsvector column would be needed at real scale.
- Expiry state is derived per request. There is no scheduled job that notices a certificate
  expiring overnight — that belongs with Phase 5's worker.

---

## Phase 3 — Tender CRUD and secure PDF upload

**Complete.** Tenders with filtered/paginated CRUD; documents uploaded as multipart PDFs,
accepted by magic bytes rather than filename or Content-Type, size-bounded, SHA-256 hashed,
stored under server-generated keys `{user_id}/{tender_id}/{uuid}.pdf` behind a `StorageBackend`
protocol (local adapter with traversal defence). Per-tender duplicate detection via a
`(tender_id, sha256)` unique constraint; the same composite-FK ownership pattern as Phase 2
(migration `0004`). Compensation: file-then-flush with delete-on-failure; delete row-first with
best-effort file cleanup (D35, D36).

### Verified

| Command | Result |
|---|---|
| `./make.ps1 check` | passed — ruff, mypy (54 files), **205 unit/API tests** |
| `./make.ps1 test-integration` | **163 passed** against real PostgreSQL + filesystem |
| `alembic upgrade head` / `alembic check` | head `0004`, no drift; single-step downgrade removes only Phase 3 tables |
| `./make.ps1 openapi` | 18 paths |
| Live smoke test | login → create tender → upload with hostile `../../` filename (sanitized, stored under generated key) → duplicate 409 → fake PDF 422 → delete tender removed file from disk |

**Totals: 368 tests — 205 unit/API, 163 integration.** The roadmap's Phase 1 exit test — "User A
cannot access User B's tender" — now passes on real tenders, including uploads into a foreign
tender (404) and document listing across users.

One fix during the phase: a shared strip-validator turned a whitespace-only title into `None`,
producing a 500 instead of a 422; caught by the integration suite.

### Remaining limitations after Phase 3

- No document download endpoint — nothing needs it until the frontend's source viewer (Phase 10).
- No virus scanning (documented as future work since Phase 0).
- Orphaned files after a crash between commit and cleanup are logged, not swept automatically.

---

## Phase 4 — Page-aware extraction (next)

Not started. PyMuPDF extraction into `document_pages` with preserved page numbers, normalized
text alongside raw text, per-page quality scoring, empty/scanned detection with a clear
unsupported-quality outcome (no OCR — postponed by the roadmap), and the extracted-page API.
