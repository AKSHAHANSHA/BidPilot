"""Pydantic request and response schemas.

Schemas are the API boundary; ORM models are the persistence layer. They are kept separate so
that adding an internal column does not silently widen the public contract.
"""

from app.schemas.auth import (
    LoginRequest,
    LogoutResponse,
    RegisterRequest,
    SessionRead,
    TokenResponse,
    UserRead,
)
from app.schemas.common import Page
from app.schemas.company import (
    CompanyProfileCreate,
    CompanyProfileRead,
    CompanyProfileUpdate,
    CompletionRead,
)
from app.schemas.evidence import (
    EvidenceCreate,
    EvidenceExpiry,
    EvidenceRead,
    EvidenceUpdate,
)
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate

__all__ = [
    "CompanyProfileCreate",
    "CompanyProfileRead",
    "CompanyProfileUpdate",
    "CompletionRead",
    "EvidenceCreate",
    "EvidenceExpiry",
    "EvidenceRead",
    "EvidenceUpdate",
    "LoginRequest",
    "LogoutResponse",
    "Page",
    "ProjectCreate",
    "ProjectRead",
    "ProjectUpdate",
    "RegisterRequest",
    "SessionRead",
    "TokenResponse",
    "UserRead",
]
