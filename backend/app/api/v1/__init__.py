"""Version 1 API router.

Feature routers are added here as their roadmap phases land: company (Phase 2), tenders and
uploads (Phase 3), documents (Phase 4), analyses and events (Phase 5), requirements, risks,
readiness, and reports (Phases 6-9).
"""

from fastapi import APIRouter

from app.api.v1 import auth, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
