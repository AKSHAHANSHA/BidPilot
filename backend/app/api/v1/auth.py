"""Authentication endpoints.

These handlers do three things only: translate HTTP into a service call, manage the refresh
cookie, and shape the response. Every policy decision — what counts as valid, what a failure
reveals, when a session is revoked — belongs to `AuthService`.
"""

from __future__ import annotations

from http import HTTPStatus

from fastapi import APIRouter, Request, Response, status

from app.api.dependencies import (
    AuthServiceDep,
    ClientContextDep,
    CurrentUser,
    SettingsDep,
)
from app.api.errors import ProblemDetail, RateLimitedError
from app.core.config import Settings
from app.core.rate_limit import RateLimiter
from app.core.security import hash_ip
from app.repositories.user_repository import normalize_email
from app.schemas.auth import (
    LoginRequest,
    LogoutResponse,
    RegisterRequest,
    SessionRead,
    TokenResponse,
    UserRead,
)
from app.services.auth_service import AuthResult, ClientContext

router = APIRouter(prefix="/auth", tags=["authentication"])

_AUTH_PROBLEM_RESPONSES: dict[int | str, dict[str, object]] = {
    HTTPStatus.UNAUTHORIZED: {"model": ProblemDetail},
    HTTPStatus.TOO_MANY_REQUESTS: {"model": ProblemDetail},
}


def _rate_limit_identity(email: str, client: ClientContext, settings: Settings) -> str:
    """Bucket key combining the target account and the caller's address.

    Keying on the email alone would let one attacker lock a victim out of their own account;
    keying on the address alone is defeated by rotating the target. The IP is hashed so the
    Redis keyspace holds no raw addresses.
    """
    ip_component = hash_ip(client.ip_address, secret=settings.jwt_secret) or "unknown"
    return f"{normalize_email(email)}|{ip_component[:16]}"


async def _enforce_rate_limit(limiter: RateLimiter, identity: str, action: str) -> None:
    decision = await limiter.hit(identity)
    if decision.exceeded:
        raise RateLimitedError(
            f"Too many {action} attempts. Try again in {decision.retry_after_seconds} seconds.",
            retry_after_seconds=decision.retry_after_seconds,
            extra={"action": action},
        )


def _set_refresh_cookie(response: Response, result: AuthResult, settings: Settings) -> None:
    """Deliver the refresh token as an HttpOnly cookie and nothing else.

    HttpOnly keeps it out of reach of JavaScript, and the narrow path means it is not attached
    to ordinary API calls — only to the auth routes that need it.
    """
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=result.refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path=settings.refresh_cookie_path,
        max_age=settings.refresh_token_days * 24 * 60 * 60,
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path=settings.refresh_cookie_path,
    )


def _token_response(result: AuthResult) -> TokenResponse:
    return TokenResponse(
        access_token=result.access.token,
        expires_in=result.access.expires_in_seconds,
        user=UserRead.model_validate(result.user),
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account and sign in",
    responses={
        HTTPStatus.CONFLICT: {"model": ProblemDetail},
        HTTPStatus.TOO_MANY_REQUESTS: {"model": ProblemDetail},
    },
)
async def register(
    payload: RegisterRequest,
    response: Response,
    auth: AuthServiceDep,
    client: ClientContextDep,
    settings: SettingsDep,
) -> TokenResponse:
    limiter = RateLimiter(
        limit=settings.register_max_attempts,
        window_seconds=settings.register_window_seconds,
        scope="register",
    )
    await _enforce_rate_limit(
        limiter, _rate_limit_identity(str(payload.email), client, settings), "registration"
    )

    result = await auth.register(
        email=str(payload.email),
        password=payload.password,
        display_name=payload.display_name,
        client=client,
        account_type=payload.account_type,
        location=payload.location,
        primary_category=payload.primary_category,
        bio=payload.bio,
    )
    _set_refresh_cookie(response, result, settings)
    return _token_response(result)


@router.post(
    "/forgot-password",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a password reset link (stub)",
    description=(
        "Demo stub. Real email delivery is not wired up. Always returns 202 with a generic "
        "message, whether or not the address is registered, so an attacker cannot use this "
        "endpoint to enumerate accounts. The reset flow is future work."
    ),
)
async def forgot_password(payload: dict[str, str]) -> dict[str, str]:
    # Deliberately does no work. Kept as a real endpoint so the frontend link is not dead
    # and so the OpenAPI schema documents the intended surface. Logging a token here would
    # violate the rule against printing secrets to server logs — even a demo one.
    return {
        "message": (
            "If that email is registered, a password-reset link has been sent. "
            "Follow the instructions in the message to complete the reset."
        )
    }


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Sign in with email and password",
    description=(
        "Returns a short-lived access token and sets an HttpOnly refresh cookie. A failed "
        "attempt always returns the same message, whether or not the account exists."
    ),
    responses=_AUTH_PROBLEM_RESPONSES,
)
async def login(
    payload: LoginRequest,
    response: Response,
    auth: AuthServiceDep,
    client: ClientContextDep,
    settings: SettingsDep,
) -> TokenResponse:
    limiter = RateLimiter(
        limit=settings.login_max_attempts,
        window_seconds=settings.login_window_seconds,
        scope="login",
    )
    identity = _rate_limit_identity(str(payload.email), client, settings)
    await _enforce_rate_limit(limiter, identity, "sign-in")

    result = await auth.authenticate(
        email=str(payload.email), password=payload.password, client=client
    )
    # A successful sign-in clears the counter so a user who mistyped twice is not throttled.
    await limiter.reset(identity)
    _set_refresh_cookie(response, result, settings)
    return _token_response(result)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Exchange the refresh cookie for a new access token",
    description=(
        "Rotates the refresh token: the presented one is revoked and a new cookie is set. "
        "Presenting an already-revoked token revokes every session for that user."
    ),
    responses=_AUTH_PROBLEM_RESPONSES,
)
async def refresh(
    request: Request,
    response: Response,
    auth: AuthServiceDep,
    client: ClientContextDep,
    settings: SettingsDep,
) -> TokenResponse:
    raw_token = request.cookies.get(settings.refresh_cookie_name)
    result = await auth.refresh(raw_token=raw_token, client=client)
    _set_refresh_cookie(response, result, settings)
    return _token_response(result)


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Revoke the current session",
    description=(
        "Idempotent: clears the cookie and returns 200 whether or not the presented token "
        "was still live, so the endpoint cannot be used to probe token validity."
    ),
)
async def logout(
    request: Request,
    response: Response,
    auth: AuthServiceDep,
    settings: SettingsDep,
) -> LogoutResponse:
    raw_token = request.cookies.get(settings.refresh_cookie_name)
    revoked = await auth.logout(raw_token=raw_token)
    _clear_refresh_cookie(response, settings)
    return LogoutResponse(revoked=revoked)


@router.post(
    "/logout-all",
    response_model=LogoutResponse,
    summary="Revoke every session for the signed-in user",
    responses=_AUTH_PROBLEM_RESPONSES,
)
async def logout_all(
    response: Response,
    current_user: CurrentUser,
    auth: AuthServiceDep,
    settings: SettingsDep,
) -> LogoutResponse:
    revoked = await auth.logout_everywhere(current_user.id)
    _clear_refresh_cookie(response, settings)
    return LogoutResponse(revoked=revoked > 0)


@router.get(
    "/me",
    response_model=UserRead,
    summary="The signed-in user",
    responses=_AUTH_PROBLEM_RESPONSES,
)
async def me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)


@router.get(
    "/sessions",
    response_model=list[SessionRead],
    summary="Live sessions for the signed-in user",
    description=(
        "Where this account is currently signed in. Revoked and expired sessions are omitted."
    ),
    responses=_AUTH_PROBLEM_RESPONSES,
)
async def list_sessions(current_user: CurrentUser, auth: AuthServiceDep) -> list[SessionRead]:
    sessions = await auth.list_sessions(current_user.id)
    return [SessionRead.model_validate(session) for session in sessions]
