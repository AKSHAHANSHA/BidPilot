"""Version 1 API router.

Feature routers are added here as their roadmap phases land: tenders and uploads (Phase 3),
documents (Phase 4), analyses and events (Phase 5), requirements, risks, readiness, and reports
(Phases 6-9), and the two-sided portal — public catalogue, organisations, listings,
applications, and notifications (`docs/09_PORTAL_SPEC.md`).

Inclusion order matters in one place only: `public` comes before `listings` so the
unauthenticated `/public/listings` paths are registered as their own subtree rather than
competing with the authenticated `/listings` ones. Within `applications`, the fixed
`/applications/stats` path is declared ahead of `/applications/{application_id}` for the same
kind of reason — see that module.
"""

from fastapi import APIRouter

from app.api.v1 import (
    analyses,
    applications,
    auth,
    company,
    health,
    listings,
    notifications,
    organisations,
    public,
    readiness,
    requirements,
    risks,
    tenders,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(public.router)
api_router.include_router(organisations.router)
api_router.include_router(company.router)
api_router.include_router(tenders.router)
api_router.include_router(listings.router)
api_router.include_router(applications.router)
api_router.include_router(notifications.router)
api_router.include_router(analyses.router)
api_router.include_router(requirements.router)
api_router.include_router(risks.router)
api_router.include_router(readiness.router)
