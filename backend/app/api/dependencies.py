"""Shared FastAPI dependencies.

Route handlers stay thin by depending on these annotated aliases instead of wiring
infrastructure themselves. `CurrentUser` is the single gate for authenticated access: a route
that declares it cannot be reached anonymously, and every repository it then uses requires
that user's ID.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AuthenticationError
from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.logging import get_logger, user_id_var
from app.core.security import TokenError, decode_access_token
from app.models.user import User
from app.repositories.company_repository import (
    CompanyEvidenceRepository,
    CompanyProfileRepository,
    CompanyProjectRepository,
)
from app.repositories.refresh_session_repository import RefreshSessionRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService, ClientContext
from app.services.company_service import CompanyService

logger = get_logger(__name__)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

#: `auto_error=False` so a missing header raises our own problem+json rather than FastAPI's
#: default 403 body, which would not match the error contract.
bearer_scheme = HTTPBearer(auto_error=False, description="Access token from /auth/login")

BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]

#: Every authentication failure returns this. The specific cause is logged.
NOT_AUTHENTICATED_DETAIL = "Authentication is required to access this resource."


def get_client_context(request: Request) -> ClientContext:
    """Capture the caller's user agent and address for the session record.

    `request.client.host` is the direct peer. Behind a proxy that is the proxy's address; a
    deployment that needs the real client IP must configure trusted-proxy handling rather than
    have this function trust a spoofable `X-Forwarded-For`.
    """
    return ClientContext(
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )


ClientContextDep = Annotated[ClientContext, Depends(get_client_context)]


def get_auth_service(session: SessionDep, settings: SettingsDep) -> AuthService:
    return AuthService(
        users=UserRepository(session),
        sessions=RefreshSessionRepository(session),
        settings=settings,
    )


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def get_company_service(session: SessionDep, settings: SettingsDep) -> CompanyService:
    return CompanyService(
        profiles=CompanyProfileRepository(session),
        evidence=CompanyEvidenceRepository(session),
        projects=CompanyProjectRepository(session),
        settings=settings,
    )


CompanyServiceDep = Annotated[CompanyService, Depends(get_company_service)]


async def get_current_user(
    credentials: BearerCredentials,
    session: SessionDep,
    settings: SettingsDep,
) -> User:
    """Resolve the authenticated user from the bearer access token.

    The user is loaded from the database on every request rather than trusted from the token's
    claims, so deactivating or deleting an account takes effect immediately instead of when
    the access token happens to expire.
    """
    if credentials is None or not credentials.credentials:
        raise AuthenticationError(NOT_AUTHENTICATED_DETAIL)

    try:
        claims = decode_access_token(credentials.credentials, secret=settings.jwt_secret)
    except TokenError as exc:
        logger.info("access_token_rejected", extra={"reason": str(exc)})
        raise AuthenticationError(NOT_AUTHENTICATED_DETAIL) from exc

    user = await UserRepository(session).get_by_id(claims.user_id)
    if user is None or not user.is_active:
        logger.warning("access_token_subject_unavailable", extra={"user_id": str(claims.user_id)})
        raise AuthenticationError(NOT_AUTHENTICATED_DETAIL)

    # Bind the user to the logging context so every later line in this request is attributable.
    user_id_var.set(str(user.id))
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
