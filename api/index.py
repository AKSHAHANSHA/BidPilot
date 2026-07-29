"""Vercel serverless entry point for the BidPilot backend.

Vercel's Python runtime serves whatever ASGI application a file under `api/` exports as `app`,
so this module exports the *real* application built by `app.main.create_app`. Forking the
factory here would let the deployed API drift from the one everyone else runs and tests; the
differences that Vercel does require are expressed as environment variables instead
(`JOB_EXECUTION=inline`, `OCR_ENABLED=false`, `STORAGE_BACKEND=s3` — see `deploy/VERCEL.md`).

**Import path.** The backend package lives in `backend/`, not at the repository root, and Vercel
installs from the root `requirements.txt` rather than from `backend/pyproject.toml`, so `app` is
never placed in site-packages. `backend/` is prepended to `sys.path` here, and `vercel.json`
carries `includeFiles: "backend/app/**"` so the source is actually inside the function bundle —
the runtime cannot trace an import it only learns about through `sys.path`. `scripts/` in the
backend does the same thing for the same reason.

**Cold starts.** The module body runs once per cold instance, and `create_app()` reads and
validates configuration eagerly, so a missing `JWT_SECRET` or a malformed `DATABASE_URL` fails
the whole function with a precise message instead of surfacing on some later request.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Imported below the path setup, which is the whole point of this file and which E402 cannot
# see. `backend/scripts/seed_portal.py` defers its imports the same way.
from app.main import create_app  # noqa: E402

#: The name Vercel's Python runtime looks for when deciding this file is an ASGI application.
app = create_app()
