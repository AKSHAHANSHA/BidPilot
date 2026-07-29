# BidPilot UAE — Vercel deployment (single project, reduced backend)

This puts the whole app — React frontend **and** FastAPI backend — on **one** Vercel project at
one origin. It is the fastest way to get a clickable public demo.

It is deliberately a **reduced** deployment. Vercel's Python runtime gives you one short-lived
serverless function per request and nothing else: no second process, no system packages, no
disk. Three things follow, and none of them are hidden:

| | Normal deployment (`deploy/DEPLOYMENT.md`) | This one |
|---|---|---|
| Background jobs | Dramatiq worker over Redis | **Run inline, inside the request** (`JOB_EXECUTION=inline`) |
| Scanned pages | Tesseract OCR | **Off** (`OCR_ENABLED=false`) — pages with no text layer are reported unreadable, never assumed blank |
| Uploads | S3 bucket | **S3 bucket, mandatory** — the function's filesystem is read-only and thrown away |

PyMuPDF's native text extraction is a pure Python wheel with no system dependency, so **text
PDFs are still read page by page**, citations still carry page numbers, and the certificate
register check works in full. Only *scanned* pages are lost.

> **Not production.** This is a portfolio demo on free tiers: cold starts, no backups, no
> uptime guarantee, and a request timeout that can cut a long screening in half. Do not put
> real, confidential, or regulated tender data in it. The seeded data is fictional.

---

## Architecture

```mermaid
flowchart LR
    User([Reviewer]) -->|HTTPS| VP[Vercel project — one origin]
    subgraph VP
      Static[Static build<br/>frontend/dist]
      Fn[Python function<br/>api/index.py → FastAPI]
    end
    Static -.->|"same-origin /api/v1/*"| Fn
    Fn -->|SQL over TLS| PG[(Neon<br/>PostgreSQL)]
    Fn -->|private S3 API| S[(Object storage<br/>private bucket)]
    Fn -->|optional| RE[(Upstash Redis<br/>rate limits + /health/ready)]
    Fn -->|optional, structured JSON| LLM[OpenAI API]
```

The frontend and the API share an origin, which is the one genuine advantage of this shape: the
refresh cookie is **same-site**, so there is no cross-site cookie to get wrong and no CORS
preflight on every call. The frontend's `VITE_API_BASE` is left **unset** on purpose — the
client falls back to relative `/api/v1/...` URLs.

### How a request is routed

`vercel.json` at the repository root:

- `/api/*` and `/health/*` → rewritten to the Python function, which receives the **original**
  path, so FastAPI still sees `/api/v1/auth/login`.
- everything else → served from the static build if the file exists, otherwise rewritten to
  `/index.html` (the SPA fallback that makes `/vendor/applications` reload correctly).

The backend package lives in `backend/`, which is not where Vercel installs Python code from.
Two lines make it importable:

- `api/index.py` prepends `<repo>/backend` to `sys.path` before importing `app.main`, and
- `vercel.json` sets `functions["api/index.py"].includeFiles = "backend/app/**"`, because the
  runtime bundles only files it can trace, and it cannot trace an import that depends on a
  `sys.path` edit made at runtime.

`requirements.txt` at the repository root is what the Python runtime installs. It mirrors
`backend/pyproject.toml`'s runtime dependencies; the header in that file explains the three
deliberate differences.

---

## Before you start

You need: a GitHub account with this repo pushed, a [Vercel](https://vercel.com) account
(Hobby is enough), a [Neon](https://neon.tech) account, and an S3-compatible bucket
(instructions below use [Supabase](https://supabase.com) Storage, free).

You will also run two commands from your own machine against the deployed database, so you need
the backend checked out locally with its virtualenv:

```bash
cd /path/to/BidPilot/backend
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env      # only if you do not already have one
```

Nothing below provisions a paid resource, and no command in this document contains a real
secret. Every value shown is a shape to copy, not a credential to use.

---

## 1. Neon — PostgreSQL

1. <https://console.neon.tech> → **New Project**. Pick a region near the Vercel region you will
   deploy to. Keep the default database name (`neondb`).
2. On the project dashboard, open **Connection Details**. Note **both** strings:
   - the **pooled** one, whose host contains `-pooler` — for the application,
   - the **direct** one, without `-pooler` — for migrations.
3. Rewrite each for this codebase. Neon hands you a `psycopg` URL; the backend is async-only and
   validates the driver at startup, so you must change three things:

   | Neon gives you | Change it to | Why |
   |---|---|---|
   | `postgresql://` | `postgresql+asyncpg://` | the whole persistence layer is asyncpg |
   | `?sslmode=require` | `?ssl=require` | asyncpg does not understand `sslmode` |
   | `&channel_binding=require` | *(delete it)* | asyncpg does not understand it either |

   For the **pooled** URL also append `&prepared_statement_cache_size=0`. Neon's pooler is
   PgBouncer in transaction mode, and asyncpg's prepared-statement cache is not safe across it.

   Application URL (`DATABASE_URL` in Vercel), shape only:

   ```text
   postgresql+asyncpg://neondb_owner:YOUR_PASSWORD@ep-example-name-12345678-pooler.eu-central-1.aws.neon.tech/neondb?ssl=require&prepared_statement_cache_size=0
   ```

   Migration URL (used only from your laptop, in step 6), shape only:

   ```text
   postgresql+asyncpg://neondb_owner:YOUR_PASSWORD@ep-example-name-12345678.eu-central-1.aws.neon.tech/neondb?ssl=require
   ```

4. Keep both somewhere safe. They are secrets: they are never committed and never sent to the
   browser.

## 2. Object storage — a private bucket

Uploads **must** go to object storage. A Vercel function's filesystem is read-only apart from
`/tmp`, and `/tmp` is discarded when the instance is recycled — with `STORAGE_BACKEND=local` a
PDF uploaded by one request would simply not exist for the next one, and startup would fail
outright trying to create the upload directory.

Using Supabase Storage (any S3-compatible service works — see the note at the end of this
section):

1. <https://supabase.com/dashboard> → **New project**.
2. **Storage → New bucket**, name it `bidpilot-tenders`, and leave **Public** switched **off**.
   The backend never generates public or pre-signed URLs; bytes are served only through
   authenticated API endpoints.
3. **Project Settings → Storage → S3 Connection**: copy the **endpoint URL** and the **region**.
   The endpoint has this shape:
   `https://abcdefghijklmno.supabase.co/storage/v1/s3`
4. On the same page, **create S3 access keys**. Copy the access key ID and the secret **now**;
   the secret is shown once.

These five values become `S3_ENDPOINT_URL`, `S3_REGION`, `S3_ACCESS_KEY_ID`,
`S3_SECRET_ACCESS_KEY`, `S3_BUCKET_NAME`. They are **server-side only** and must never be added
as `VITE_*` variables.

> Cloudflare R2 and AWS S3 work unchanged — the adapter uses SigV4 with path-style addressing.
> For R2 the endpoint is `https://<account-id>.r2.cloudflarestorage.com` and the region is
> `auto`.

## 3. Redis — optional, but do it

Skip this and the app still works: the login rate limiter **fails open** (it logs a warning and
allows the request rather than turning a cache outage into a login outage), and nothing else in
the request path needs Redis once `JOB_EXECUTION=inline` stops jobs being enqueued. The visible
cost of skipping it is that `GET /health/ready` returns **503** naming `redis` as unavailable,
forever.

1. <https://console.upstash.com> → **Create database**, region near your Vercel region, TLS on.
2. Copy the **`rediss://`** URL. That becomes `REDIS_URL`.

## 4. Generate the JWT secret

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the output. This is `JWT_SECRET`. With `APP_ENV=production` the app refuses to start on a
placeholder value, so do not reuse the one from `.env.example`.

## 5. Import the project into Vercel

1. <https://vercel.com/new> → import this Git repository.
2. **Root Directory: leave it at the repository root** (`./`). Do **not** point it at
   `frontend/` — the root is where `vercel.json`, `api/index.py`, and `requirements.txt` live,
   and pointing Vercel at `frontend/` gives you the static site with no backend.
3. Framework Preset: **Other**. Build and output settings come from `vercel.json`; leave the
   dashboard fields empty.
4. **Settings → Functions → Python Version: 3.12** (the codebase requires ≥ 3.12).
5. **Settings → Environment Variables** — add every row from the table below to the
   **Production** environment (and Preview too, if you want preview deploys to work).
6. Deploy once. It will succeed but the app will not work yet: the database has no tables.
   Note the URL Vercel gives you, e.g. `https://bidpilot-demo.vercel.app`.
7. Set `FRONTEND_ORIGIN` to exactly that URL (scheme, no trailing slash) and **redeploy**.

### Environment variables

Every one of these goes in **Vercel → Settings → Environment Variables**, not in the repo.

| Variable | Value (example shape) | Why |
|---|---|---|
| `APP_ENV` | `production` | Secure cookies, `/docs` disabled, placeholder secrets refused |
| `LOG_LEVEL` | `INFO` | |
| `JWT_SECRET` | *(48 random chars from step 4)* | Signs access tokens. **Required — the function will not start without it.** |
| `DATABASE_URL` | `postgresql+asyncpg://…-pooler…/neondb?ssl=require&prepared_statement_cache_size=0` | Neon **pooled** URL from step 1 |
| `JOB_EXECUTION` | `inline` | **The key setting.** No worker exists here, so screening runs inside the submit request |
| `STORAGE_BACKEND` | `s3` | The function has no writable disk |
| `S3_ENDPOINT_URL` | `https://abcdefghijklmno.supabase.co/storage/v1/s3` | step 2 |
| `S3_REGION` | `eu-central-1` | step 2 |
| `S3_ACCESS_KEY_ID` | *(from step 2)* | server-side only |
| `S3_SECRET_ACCESS_KEY` | *(from step 2)* | server-side only |
| `S3_BUCKET_NAME` | `bidpilot-tenders` | step 2 |
| `OCR_ENABLED` | `false` | Tesseract is not installed and cannot be. This is also the default; set it explicitly so nobody wonders |
| `MAX_UPLOAD_BYTES` | `4194304` | **Vercel rejects request bodies over ~4.5 MB at the edge.** Setting 4 MB makes the API refuse an oversized PDF with its own clear error instead of an opaque platform 413 |
| `FRONTEND_ORIGIN` | `https://bidpilot-demo.vercel.app` | Exact origin, no wildcard. Same origin as the API here, but CORS and the password-reset link template both read it |
| `REFRESH_COOKIE_SAMESITE` | `lax` | Frontend and API share an origin, so the cookie does **not** need `SameSite=None`. `lax` is tighter; without this it would derive to `none` |
| `REFRESH_COOKIE_SECURE` | `true` | |
| `REDIS_URL` | `rediss://default:…@example-12345.upstash.io:6379` | Optional (step 3). Omit and `/health/ready` reports 503 for `redis` |
| `OPENAI_API_KEY` | *(your key)* | Optional. Without it the deterministic keyword classifier runs and says so in the logs |
| `OPENAI_MODEL` | `gpt-5-mini` | Required **only** if `OPENAI_API_KEY` is set — one without the other is a half-configuration and is rejected at the point of use |

**Do not set `VITE_API_BASE`.** The frontend defaults to relative URLs, which is exactly right
when the API is on the same origin. Setting it to the Vercel URL would turn every call into a
needless cross-site request. No backend secret ever belongs in a `VITE_*` variable — those are
compiled into the JavaScript bundle and are public.

## 6. Run the migrations against Neon

Vercel cannot run them: there is no shell and no build step that touches the database. Run them
from your machine, using the **direct** (non-pooled) URL from step 1.

```bash
cd /path/to/BidPilot/backend
DATABASE_URL='postgresql+asyncpg://neondb_owner:YOUR_PASSWORD@ep-example-name-12345678.eu-central-1.aws.neon.tech/neondb?ssl=require' \
  .venv/bin/python -m alembic upgrade head
```

Expect the last line to name revision `0012`. Verify:

```bash
DATABASE_URL='postgresql+asyncpg://…direct…?ssl=require' .venv/bin/python -m alembic current
```

The command is idempotent — running it again after a schema change is the normal upgrade path.

## 7. Seed the demo

```bash
cd /path/to/BidPilot/backend
DATABASE_URL='postgresql+asyncpg://…direct…?ssl=require' \
  .venv/bin/python scripts/seed_portal.py
```

The script prints the demo email domain and the shared demo password when it finishes. Re-run it
any time to refresh; `--reset` deletes the demo accounts and everything they own.

**One caveat, and it matters.** `seed_portal.py` deliberately writes its generated PDF bundles
to the **local** filesystem regardless of `STORAGE_BACKEND`, so that seeding can never push demo
files into a real bucket. Seeded from your laptop against Neon, the database rows will therefore
reference objects your deployment cannot read: browsing seeded listings, applications, findings,
verdicts, and scores all works, but *downloading a seeded document* returns "not found".
Documents you upload yourself through the deployed UI go to the bucket and work completely.

If you want the seeded files too, copy them up afterwards. The local layout is
`<upload_dir>/<storage_key>`, so a plain recursive copy preserves the keys exactly:

```bash
cd /path/to/BidPilot/backend
aws s3 cp --recursive data/uploads/ s3://bidpilot-tenders/ \
  --endpoint-url https://abcdefghijklmno.supabase.co/storage/v1/s3
```

(with `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_DEFAULT_REGION` set to the same S3
values you gave Vercel).

## 8. Smoke test

1. Open your Vercel URL. The landing page and public tender search should render.
2. `curl https://bidpilot-demo.vercel.app/health/live` → `200`.
3. `curl https://bidpilot-demo.vercel.app/health/ready` → `200` with Redis configured;
   `503` naming `redis` without it. Either way, `database` must read `ok` — if it does not, the
   `DATABASE_URL` rewrite in step 1 is wrong.
4. Sign in with a seeded vendor account, open a listing, apply, attach a small text PDF, and
   submit.
5. The submit response should come back with the screening **already complete** — that is
   `JOB_EXECUTION=inline` working. In the worker deployment it would have come back pending.

---

## What does not work in this mode

Read this before you demo it to anyone.

- **No background worker.** Screening runs inside `POST /api/v1/applications/{id}/submit`. The
  request blocks for the whole pipeline — S3 reads, PDF text extraction, and any model call —
  and the browser waits. There is no progress to poll because the work is already done when the
  response arrives.
- **A function timeout kills the job.** `vercel.json` asks for `maxDuration: 60` (seconds), the
  Hobby ceiling. A submission that needs longer is cut off mid-pipeline; the screening row is
  left in whatever state the pipeline last committed, and the vendor can resubmit — the submit
  endpoint re-runs a failed screening rather than refusing it. Keep demo uploads small, and
  prefer running without an OpenAI key (the deterministic classifier is far faster) if you are
  showing this live.
- **The tender-analysis pipeline is the risky one.** It makes three separate model calls
  (metadata, requirements, risks) over a whole document. Inline, on a 60-second budget, a real
  tender PDF will often time out. The *portal* flow — publish a listing, apply, submit, screen —
  is the path this deployment is meant to show.
- **No OCR.** There is no Tesseract binary in Vercel's Python runtime and no way to add one.
  Pages with no text layer are counted and reported as unreadable. They are never treated as
  blank and never silently pass a requirement — but a scanned trade licence will not be read.
  Use text PDFs in the demo. `backend/sample_data/` has suitable ones.
- **Cold starts.** After a few minutes of no traffic the function is torn down. The next request
  pays for the Python import (FastAPI, SQLAlchemy, PyMuPDF, boto3) plus a fresh Neon connection
  — a couple of seconds. Neon's free tier also suspends an idle compute; the first query after
  that adds its own wake-up delay.
- **~4.5 MB upload ceiling.** Vercel's platform limit on a request body, not ours. Hence
  `MAX_UPLOAD_BYTES=4194304`, so the rejection is a clear API error rather than a platform 413.
- **Connection budget.** Each warm function instance holds its own SQLAlchemy pool (5 + 5). Under
  concurrency that multiplies. The Neon **pooled** endpoint is what keeps this within the free
  plan's connection limit — this is why step 1 insists on it.
- **Rate limiting is effectively off without Redis**, by design (it fails open). Do not treat
  this deployment as hardened against credential stuffing.
- **Seeded documents are not in the bucket** unless you did the copy in step 7.
- **No backups, no autoscaling, no uptime guarantee.**

If any of that is unacceptable, use `deploy/DEPLOYMENT.md` instead: a Render free web service
runs the real worker alongside the API, with OCR available and no request timeout on the
pipeline.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Function crashes on every request, log shows `ValidationError … jwt_secret` | `JWT_SECRET` not set in Vercel | Add it, redeploy. Configuration is validated at import, so *every* request fails, not just the auth ones |
| `DATABASE_URL must use the asyncpg driver` | scheme still `postgresql://` | Rewrite per step 1 |
| `invalid dsn: invalid connection option "sslmode"` | Neon's `?sslmode=require` left in place | Use `?ssl=require` |
| `prepared statement "__asyncpg_…" already exists` | pooled Neon URL without the cache disabled | Append `&prepared_statement_cache_size=0` |
| `ModuleNotFoundError: No module named 'app'` | `backend/app/**` not in the bundle | Check `functions["api/index.py"].includeFiles` in `vercel.json` survived your edits |
| 404 on `/api/v1/...`, HTML returned instead of JSON | the `/api/(.*)` rewrite is missing or ordered after the SPA fallback | Rewrites are evaluated in order; `/api/(.*)` and `/health/(.*)` must come **before** `/(.*)` |
| Deep links like `/vendor/applications` 404 on reload | SPA fallback missing | Keep the `/(.*)` → `/index.html` rewrite |
| Build fails with "no package.json" | Vercel looked at the repository root | Confirm `installCommand` and `buildCommand` in `vercel.json` are being used, and that Root Directory is `./` |
| Login succeeds then immediately logs out | refresh cookie rejected | `REFRESH_COOKIE_SECURE=true` and `REFRESH_COOKIE_SAMESITE=lax`, and `FRONTEND_ORIGIN` exactly matches the browser's origin |
| Submit returns 504 | the pipeline exceeded `maxDuration` | Smaller PDF, or unset `OPENAI_API_KEY` to use the deterministic classifier, or move to the Render deployment |
| Uploaded document downloads 404 | seeded rows point at files on your laptop | Expected — see step 7 |

## Rolling back and resetting

- **Code:** Vercel → *Deployments* → promote a previous deployment. One project, so frontend and
  backend roll back together — which is the other advantage of this shape.
- **Schema:** from your machine, against the **direct** URL:
  `.venv/bin/python -m alembic downgrade -1`. Prefer rolling the code back to a compatible
  revision unless a migration is specifically the problem.
- **Demo data:** `DATABASE_URL='…' .venv/bin/python scripts/seed_portal.py --reset`, then seed
  again. Objects already in the bucket are not removed; delete them from the storage dashboard
  if you want a clean slate.

## Cost

| Component | Tier | Monthly |
|---|---|---|
| Vercel Hobby (static + Python function) | free | $0 |
| Neon | free | $0 |
| Supabase Storage | free | $0 |
| Upstash Redis (optional) | free | $0 |
| OpenAI (optional) | pay-as-you-go | a few cents per analysis; **skip the key and the app still screens**, deterministically |
