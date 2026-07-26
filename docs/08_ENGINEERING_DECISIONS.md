# BidPilot UAE — Engineering Decisions

A record of choices the specification left open, with the reasoning. Written to be defended
in a technical interview. Each entry states the decision, why, and what was rejected.

---

## D1 — Dramatiq for background jobs

**Decision:** Dramatiq with the Redis broker, behind a small `JobQueue` protocol.

Celery and Dramatiq both work. Dramatiq needs no result backend, no beat scheduler, and far
less configuration for the one thing this project needs: enqueue an analysis, run it in a
worker, record progress in PostgreSQL. For a single developer, less configuration is a
correctness advantage.

The protocol matters more than the library. Tests use an eager adapter that runs the task
inline, so no test needs a broker, and swapping to Celery later would touch one module.

**Rejected:** Celery (configuration weight), RQ (weaker middleware story), and
FastAPI `BackgroundTasks` — the latter dies with the web process, which would lose an
in-flight analysis on deploy.

## D2 — One async database driver, everywhere

**Decision:** SQLAlchemy 2 async engine with `asyncpg` for both the API and the worker.
Worker actors are thin synchronous wrappers around `asyncio.run(...)`.

`.env.example` already pins `postgresql+asyncpg://`. Adding a second sync driver for the
worker would mean two engines, two session factories, and two places to configure pooling,
in exchange for slightly more idiomatic worker code. Not worth it.

A validator rejects a non-asyncpg `DATABASE_URL` at startup, because a sync URL otherwise
fails deep inside SQLAlchemy with a message that does not name the real problem.

## D3 — Argon2id password hashing

**Decision:** `argon2-cffi` with library defaults.

The requirements permit Argon2 or bcrypt. Argon2id is the current OWASP recommendation and
avoids bcrypt's 72-byte input truncation, which silently ignores the tail of a long
passphrase.

Stored hashes are re-checked against the current cost parameters on every successful login and
transparently upgraded while the plaintext is in hand, so raising the parameters later does not
leave old accounts on weak settings.

## D4 — Ruff for lint and format, mypy for types

One tool for both linting and formatting removes an entire class of "the formatter and the
linter disagree" problems. SQLAlchemy 2 ships native typing, so mypy needs no plugin beyond
Pydantic's.

## D5 — Standard-library logging, no structlog

**Decision:** `logging` with a custom JSON formatter, a `ContextVar` filter for
`request_id`/`user_id`, and denylist-based redaction in the formatter.

Architecture §8 requires structured logs with correlation and an explicit exclusion list
(passwords, tokens, keys, full document text, complete prompts). That is roughly eighty
lines of standard library code, and it keeps third-party library logs in the same format
without adapters.

Redaction is enforced in the formatter rather than left to convention: any log extra whose
key matches a sensitive marker (`password`, `token`, `api_key`, `page_text`, …) is replaced
with `[redacted]` before serialization. Over a long build, a convention that depends on
remembering it will eventually be forgotten.

## D6 — Pure ASGI request middleware, not `BaseHTTPMiddleware`

Starlette's `ServerErrorMiddleware` sits *outside* the user middleware stack. With
`BaseHTTPMiddleware`, an unhandled exception would bypass our layer entirely and produce a
500 with no `X-Request-ID` header and no access log line — exactly the response you most
need to trace. The pure ASGI middleware catches `Exception` itself, so every response,
including a contained 500, is correlated and logged identically.

CORS is deliberately mounted *outside* it, so browser clients can read the body of an error
response.

## D7 — Ownership failures return 404, not 403

Requesting another user's tender returns `RESOURCE_NOT_FOUND`. A 403 would confirm that the
record exists, which is an information leak. The repository layer therefore takes the
authenticated user ID as a parameter (`get_tender_for_user(tender_id, user_id)`) rather than
fetching by ID and checking ownership afterwards in a different layer.

## D8 — Liveness and readiness are separate, and liveness checks nothing

`/health/live` returns 200 whenever the process can serve a request. `/health/ready` checks
PostgreSQL and Redis and returns 503 problem+json naming the unavailable dependency.

If liveness checked the database, a brief outage would make the platform kill and restart
healthy processes, turning a short dependency blip into a longer outage. Readiness is the
signal that should remove an instance from rotation.

Driver exception text can contain hosts and credentials, so the failing dependency is named
in the response but its exception is only logged.

## D9 — `code` is the API's stable error identifier

Problem documents carry both `title`/`detail` (human text, may be reworded freely) and
`code` (machine-readable, treated as contract). The frontend switches on `code`, so error
copy can be improved without breaking clients.

Validation errors omit Pydantic's `input` and `ctx` fields: echoing the rejected value would
return a submitted password or API key in the response body.

## D10 — An empty baseline migration

Phase 0 defines no tables, but the roadmap's exit test requires that a migration runs.
Revision `0001` is intentionally empty: it creates `alembic_version` on a fresh database and
gives Phase 1's first schema revision a parent. Faking a schema to make a checklist item go
green would violate the "no fake progress" rule in `CLAUDE.md`.

## D11 — `Makefile` plus a PowerShell shim

The documentation mandates a `Makefile`, and CI is Linux, so the `Makefile` is canonical.
GNU make is not installed on the development machine, so `backend/make.ps1` exposes the same
target names (`./make.ps1 check`). Targets belonging to unbuilt phases print which phase
implements them and exit non-zero, rather than appearing to succeed.

## D12 — `make check` excludes integration tests

`check` runs format check, lint, mypy, and the unit/API suite — everything that needs no
external service. Integration tests run explicitly via `make test-integration` and in their
own CI job with service containers. A quality gate that cannot run without Docker gets
skipped, and a skipped gate protects nothing.

## D13 — A separate `bidpilot_test` database

Integration tests drop and rebuild the schema. Pointing them at the development database
would destroy seeded demo data, so `docker-compose.yml` provisions `bidpilot_test` on first
initialization and the test suite pins `DATABASE_URL` to it in `tests/conftest.py`, ahead of
any `.env` file.

## D15 — Non-default host ports for the compose stack

**Decision:** Compose publishes PostgreSQL on 55432 and Redis on 56379. Container-internal
ports stay standard (5432 / 6379), so the api and worker services are unaffected.

A developer machine frequently already runs a PostgreSQL for another project, and
`docker compose up` then fails with "port is already allocated" — which is exactly the error
this project hit on first run. Shifting only the *published* ports removes a class of setup
failure at no architectural cost. Both are overridable via `POSTGRES_HOST_PORT` and
`REDIS_HOST_PORT`, and CI maps its service containers to the same published ports so one set
of URLs works everywhere.

## D16 — One access log, owned by the middleware

`RequestContextMiddleware` emits a single structured access line per request with request ID,
status, and latency, so `uvicorn.access` is raised to WARNING. Two access logs per request
with different formats and no shared correlation ID is worse than one good one.

Health-check paths are logged at DEBUG, matched by suffix so both the unprefixed and the
`/api/v1` mount points are covered. Continuous platform polling would otherwise bury real
traffic at INFO.

## D18 — Two token kinds, deliberately different

**Access token:** a signed JWT, 15 minutes, verified without a database round trip.
**Refresh token:** an opaque 384-bit random string, 7 days, stored only as a SHA-256 hash and
checked against the database on every use.

The asymmetry follows from lifetime. A short-lived token can be stateless because the damage
window is small. A long-lived token must be revocable, and revocation has to be authoritative
— a JWT refresh token invites stateless validation and silently breaks logout.

SHA-256 rather than Argon2 for the refresh hash: the token is server-generated randomness, so
there is no guessable password to slow down, and lookup must be one indexed query rather than
a scan that verifies every stored hash in turn.

The `typ` claim is checked on decode, and `algorithms` is pinned to the one algorithm we issue
— accepting the algorithm named in an untrusted token's own header is the classic JWT
vulnerability.

## D19 — Refresh rotation with reuse detection

Every successful refresh revokes the presented token and issues a new one, so a captured
token has a bounded useful life. Presenting an **already revoked** token means a replay or a
stolen cookie, so the response is to revoke every session for that user and force a fresh
sign-in.

**The revocation is committed before the error is raised.** `get_session` rolls back when a
handler raises, so revoking and then raising in that order silently undoes the defence: a
known-stolen token keeps working while every attempt is detected and logged. This was a real
bug found during live verification, not a hypothetical — `BaseRepository.commit_security_action`
exists for exactly this case and is the single documented exception to "repositories never
commit".

The bug survived the first test run because the integration test's `get_session` override only
committed on success and did not roll back on error. The override now mirrors the production
dependency exactly, and `test_reuse_detection_survives_the_failed_request` asserts the
persisted state rather than the response.

## D20 — Uniform generic failures, with one documented exception

Login failure always returns the same 401 and the same message whether the account exists, the
password is wrong, or the account is deactivated. An unknown email also spends one dummy Argon2
verification so response time does not reveal which addresses are registered.

`/auth/logout` is idempotent and returns 200 for an unknown token, so it cannot be used to
probe token validity. A short password at `/auth/login` is a 401, not a 422: a validation error
would confirm that the policy is enforced and would differ in shape from a normal failure.

**The exception:** duplicate registration returns 409, which does confirm the address is
registered. The alternative — a fake success — makes the demo confusing, complicates the
frontend, and is defeated anyway by the login form. Accepted and recorded rather than hidden.

## D21 — Passwords are never trimmed

`RegisterRequest` has no model-wide `str_strip_whitespace`. Stripping would store a different
secret than the user typed, and any client that trims differently could then never sign in.
Text fields are stripped individually; the password is passed through byte-for-byte.

## D22 — Ownership is structural, not a convention

`OwnedRepository` makes the owner ID a required parameter of every read, list, and delete.
There is no method that fetches an owned row by ID alone, so a caller cannot forget the check
— the signature will not let them. A unit test asserts no `get(id)`-style escape hatch exists
on the base class, and an integration test asserts the generated SQL genuinely isolates users.

Ownership failures return **404, not 403**: a 403 confirms the record exists.

## D23 — Rate limiting fails open

A fixed-window counter in Redis, keyed on (account, hashed client IP). Keying on email alone
would let an attacker lock a victim out of their own account; keying on IP alone is defeated by
rotating the target.

If Redis is unreachable, requests are **allowed** and a warning is logged. Failing closed would
turn a cache outage into a total login outage, and PostgreSQL remains the authority on whether
credentials are valid either way. A successful sign-in clears the counter so a user who mistyped
twice is not throttled.

Client IPs are stored as keyed HMACs, never raw: session records make suspicious activity
visible without holding personal data, and keying stops someone who reads the database from
confirming a guessed address.

## D24 — Auth tests are integration tests

Authentication cannot be meaningfully tested without a database, and `docs/07` lists auth
refresh/revocation and ownership enforcement under integration tests. Rather than substitute
SQLite — whose dialect differences would make the tests lie — the suite runs against real
PostgreSQL with the schema migrated once and each test wrapped in a transaction that is rolled
back (`join_transaction_mode="create_savepoint"`, so application `commit()` calls behave
normally).

Pure policy — hashing, token signing, password rules, the ownership contract — stays in unit
tests so `make check` still gates every commit without Docker.

## D25 — Postponed deliberately

Not built yet, and each waits for the phase that needs it: OCR fallback, the S3 storage
adapter, the Anthropic provider adapter, pgvector and semantic evidence retrieval, PDF
export, and password reset.

Permanently out of scope per `docs/01_PRODUCT_REQUIREMENTS.md` §4: microservices,
Kubernetes, Kafka, enterprise SSO, billing, organization tenancy with RLS, GraphQL,
procurement-portal scraping, and autonomous bid agents.
