# BidPilot UAE — Free Student Deployment Guide

A completely free deployment for a student portfolio demo. **Nothing here provisions paid
infrastructure** — you create the free accounts and click deploy. This document is configuration
and instructions only.

> **Production-readiness disclaimer.** BidPilot is a portfolio project, not a production service.
> This architecture targets free tiers with cold starts, an ephemeral container, a single combined
> API+worker process, and no backups, autoscaling, or uptime guarantees. Do not use it with real,
> confidential, or regulated tender data. The demo data is entirely fictional.

---

## Architecture (all free)

```mermaid
flowchart LR
    User([Reviewer]) -->|HTTPS| V[Vercel Hobby<br/>React SPA]
    V -->|"cross-site API calls (CORS, cookies)"| R[Render Free Web Service]
    subgraph R[Render Free Web Service — one container]
      API[FastAPI + Uvicorn]
      W[Dramatiq worker]
    end
    API -->|SQL over TLS| PG[(Supabase<br/>PostgreSQL)]
    API -->|enqueue| RE[(Upstash<br/>Redis, TLS)]
    W -->|dequeue| RE
    W -->|read/write| PG
    API -->|private S3 API| S[(Supabase Storage<br/>private bucket)]
    W -->|structured JSON| LLM[OpenAI API]
```

- **Frontend** — Vercel Hobby, static Vite build. Calls the backend cross-site at `VITE_API_BASE`.
- **Backend** — one Render **Free** Web Service. `scripts/start.sh` runs migrations, launches the
  Dramatiq **worker in the background**, then serves the API in the foreground. No separate paid
  Background Worker.
- **PostgreSQL** — Supabase Free.
- **Redis** — Upstash Free (TLS `rediss://`). Not Render Key Value.
- **Object storage** — Supabase Storage **private** bucket via its S3-compatible API. Files are
  served only through authenticated backend endpoints; no public or pre-signed URLs.
- **OpenAI** — your existing key; used only by the worker.

---

## 1. Supabase — PostgreSQL

1. Create a project (choose a region near your Render region).
2. **Connection string** — Project Settings → Database. Supabase offers two:
   - **Pooled** (Supavisor/pgBouncer, port `6543`) — use for the **application runtime**
     (`DATABASE_URL`). Best for the free service's small connection budget.
   - **Direct** (port `5432`) — Alembic migrations run once per deploy via `start.sh`; the pooled
     string works for them too, but if you ever run migrations manually and hit a transaction-pooling
     limitation, use the direct string for that run.
3. Rewrite the scheme for the async driver and keep TLS:
   `postgres://…` → `postgresql+asyncpg://…` and append `?ssl=require`.
   Example: `postgresql+asyncpg://postgres.abcd:PASSWORD@aws-0-eu-west-1.pooler.supabase.com:6543/postgres?ssl=require`
4. Save it as the `DATABASE_URL` secret in Render. Never commit it.

## 2. Supabase — Storage (private bucket, S3 API)

1. Storage → **New bucket**, name it e.g. `bidpilot-tenders`, and keep **Public = off**.
2. Project Settings → Storage → **S3 Connection**: note the **endpoint URL** and **region**.
3. Create **S3 access keys** (access key ID + secret). These are **server-side secrets only** — they
   never go to Vercel or the frontend.
4. Set the Render secrets: `S3_ENDPOINT_URL`, `S3_REGION`, `S3_ACCESS_KEY_ID`,
   `S3_SECRET_ACCESS_KEY`, `S3_BUCKET_NAME` (the bucket name from step 1). Keep `STORAGE_BACKEND=s3`.

The adapter uses path-style addressing and SigV4, keeps the bucket private, adds bounded retries and
timeouts, and reads bytes back through authenticated endpoints only.

## 3. Upstash — Redis

1. Create a Redis database (region near Render). Enable TLS.
2. Copy the **`rediss://`** URL and save it as the `REDIS_URL` secret. Do **not** use Render Key Value.

Dramatiq's Redis broker and the `/health/ready` Redis probe both accept the TLS `rediss://` URL as-is
(config validates the scheme).

## 4. Render — one free Web Service

**Blueprint:** Render → *New → Blueprint* on this repo. It reads [`render.yaml`](../render.yaml) and
creates a single **Free** web service named `bidpilot` with:

- **Root directory:** `backend`
- **Build:** `pip install -e .`
- **Start:** `bash scripts/start.sh`
- **Health check:** `/health/ready`

Then set the `sync:false` secrets in the dashboard: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`,
`OPENAI_API_KEY`, `FRONTEND_ORIGIN`, and all five `S3_*` values. `APP_ENV`, `STORAGE_BACKEND=s3`,
`OPENAI_MODEL=gpt-5-mini`, and the cookie settings are baked into `render.yaml`.

### Exact start command

`scripts/start.sh` runs:

```bash
python -m alembic upgrade head
python -m dramatiq app.workers.main --processes 1 --threads 4 &
exec python -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --proxy-headers \
  --forwarded-allow-ips="*"
```

(The real script supervises both PIDs and forwards SIGTERM so shutdown is clean; a worker crash
does not take the API down.)

## 5. Vercel — frontend (Hobby)

1. *New Project* → import the repo → **root directory `frontend/`**. Vercel detects Vite and reads
   [`frontend/vercel.json`](../frontend/vercel.json) (build `npm run build`, output `dist`, SPA rewrite).
2. Add **one** environment variable:
   `VITE_API_BASE=https://<your-render-service>.onrender.com`
3. Deploy. Then set the Render `FRONTEND_ORIGIN` secret to the resulting Vercel URL and redeploy the
   backend so CORS and the cross-site refresh cookie line up.

**No backend secrets belong in Vercel.** The frontend only ever needs `VITE_API_BASE`. The database
URL, Redis URL, JWT secret, OpenAI key, and S3 credentials live exclusively in Render.

## 6. Smoke test

Open the Vercel URL, sign in with the demo credentials, upload `backend/sample_data/sample_tender.pdf`,
run an analysis, watch the stages complete, and open a citation. (Seed the demo first — from a Render
one-off shell: `python scripts/seed_demo.py`.)

---

## Environment variables

Full template: [`backend/.env.production.example`](../backend/.env.production.example).

| Variable | Where | Notes |
|---|---|---|
| `APP_ENV=production` | render.yaml | Secure cookies, no `/docs`, real-secret enforcement |
| `DATABASE_URL` | Render secret | Supabase pooled, `postgresql+asyncpg://…?ssl=require` |
| `REDIS_URL` | Render secret | Upstash `rediss://…` |
| `JWT_SECRET` | Render secret | 48+ random chars |
| `OPENAI_API_KEY` | Render secret | worker-only |
| `OPENAI_MODEL=gpt-5-mini` | render.yaml | |
| `FRONTEND_ORIGIN` | Render secret | exact Vercel origin, no wildcard |
| `STORAGE_BACKEND=s3` | render.yaml | |
| `S3_ENDPOINT_URL/REGION/ACCESS_KEY_ID/SECRET_ACCESS_KEY/BUCKET_NAME` | Render secrets | Supabase Storage; server-side only |
| `VITE_API_BASE` | Vercel | Render service URL; the only frontend var |

## Secret handling

- Secrets live only in Render (backend) and Vercel (`VITE_API_BASE` only). Never in the repo — `.env`
  is git-ignored; only `*.example` templates are committed.
- `render.yaml` marks every secret `sync:false`, so a Blueprint apply never bakes a value into git.
- S3 credentials and the DB/Redis URLs are **never** sent to the browser. Uploaded PDFs are returned
  only through authenticated endpoints, never via public bucket URLs.

## Health checks

- `GET /health/live` — process up, no dependency checks (liveness).
- `GET /api/v1/health/ready` — checks PostgreSQL and Redis; 503 `application/problem+json` naming the
  failed dependency. Render's configured health-check path.

## Migrations

`python -m alembic upgrade head` runs at the top of `start.sh` on every deploy/restart. Idempotent.

## Rollback

- **Code:** Render → *Deploys* → *Rollback*; Vercel → *Deployments* → promote a previous build. Roll
  both back together when the API contract changed.
- **Schema:** from a Render one-off shell, `python -m alembic downgrade -1`. Prefer a code rollback to
  a compatible revision unless a migration is the specific cause.

## Data reset

From a Render one-off shell:

```bash
python scripts/demo_reset.py   # clears the demo user's tenders/analyses and re-seeds the company
```

Uploaded objects persist in the Supabase bucket (durable, unlike local disk); `demo_reset` clears the
DB rows. To also purge stored files, delete them from the Supabase Storage UI.

## Cost estimate

| Component | Tier | Monthly |
|---|---|---|
| Vercel Hobby | free | $0 |
| Render Free Web Service (API + worker) | free | $0 |
| Supabase (PostgreSQL + Storage) | free | $0 |
| Upstash Redis | free | $0 |
| OpenAI | pay-as-you-go | ~$0.05–0.10 per analysis; **not free** once trial credits run out |

Effectively **$0/month** plus a few cents per analysis you run (only if you have OpenAI credit).

## Free-tier behaviour and limitations

- **Render sleeps after inactivity.** The first request after idle can take **roughly a minute** to
  cold-start (spinning up the container, migrations, worker, API).
- **The API and worker restart together** — they are one container. A restart briefly interrupts both.
- **A worker crash does not silently kill the API** (start.sh waits on the API; a dead worker is
  logged and analyses queue until the next deploy) — but there is no automatic worker restart on the
  free plan.
- **Supabase free projects pause after ~1 week of inactivity**; the first request after that may fail
  until the project resumes (open the Supabase dashboard to wake it).
- **Upstash free limits apply** (per-day command and storage caps).
- **OpenAI usage is not free** unless you still have credits.
- **Single combined process, no autoscaling, no backups, ephemeral container disk** (uploads go to
  Supabase Storage, which is durable; the container filesystem is not).
- Intended for a **student portfolio demo, not commercial production.**
