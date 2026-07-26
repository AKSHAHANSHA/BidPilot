"""Repositories — the only layer that builds queries.

Every repository for a user-owned model extends `OwnedRepository`, whose methods require the
authenticated user ID. Services never write raw `select()` against an owned table.
"""

from app.repositories.base import BaseRepository, OwnedRepository
from app.repositories.company_repository import (
    CompanyEvidenceRepository,
    CompanyProfileRepository,
    CompanyProjectRepository,
    EvidenceFilters,
    ProjectFilters,
)
from app.repositories.refresh_session_repository import RefreshSessionRepository
from app.repositories.user_repository import UserRepository, normalize_email

__all__ = [
    "BaseRepository",
    "CompanyEvidenceRepository",
    "CompanyProfileRepository",
    "CompanyProjectRepository",
    "EvidenceFilters",
    "OwnedRepository",
    "ProjectFilters",
    "RefreshSessionRepository",
    "UserRepository",
    "normalize_email",
]
