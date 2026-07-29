"""Authentication endpoints.

These handlers do three things only: translate HTTP into a service call, manage the refresh
cookie, and shape the response. Every policy decision — what counts as valid, what a failure
reveals, when a session is revoked — belongs to `AuthService`.
"""

from __future__ import annotations

from http import HTTPStatus

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field

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
    PasswordResetConfirm,
    PasswordResetRequest,
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

#: The single answer `/password-reset/request` ever gives. Fixed text, because a body that
#: differed for a registered address would be the account-enumeration oracle the endpoint's
#: whole design exists to avoid (`docs/09_PORTAL_SPEC.md` §3.2).
RESET_ACCEPTED_DETAIL = (
    "If that address has an account, a reset link is on its way. The link expires shortly, "
    "and requesting a new one invalidates the old."
)


class PasswordResetAccepted(BaseModel):
    """Acknowledgement for `POST /auth/password-reset/request`.

    Declared here rather than in `app/schemas/auth.py` because it carries no data: it exists so
    the 202 has a documented body instead of an untyped null, and its only field is a constant.
    """

    detail: str = Field(
        default=RESET_ACCEPTED_DETAIL,
        description="Fixed text. Identical whether or not the address is registered.",
    )


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
    description=(
        "The account and its organisation are created in one transaction, so a user can never "
        "exist without the identity every listing card and applicant row has to render. "
        "`account_type` fixes which side of the marketplace this account is on and is never "
        "changed afterwards; the organisation inherits it rather than restating it."
    ),
    responses={
        HTTPStatus.CONFLICT: {"model": ProblemDetail},
        HTTPStatus.TOO_MANY_REQUESTS: {"model": ProblemDetail},
        HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ProblemDetail},
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
        account_type=payload.account_type,
        organisation=payload.organisation,
        client=client,
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
    "/password-reset/request",
    response_model=PasswordResetAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a password reset link",
    description=(
        "Always 202 with the same body, whether or not the address has an account: a response "
        "that differed would let anyone test which addresses are registered. Rate limited per "
        "address and caller. Issuing a link invalidates any earlier unused one."
    ),
    responses={HTTPStatus.TOO_MANY_REQUESTS: {"model": ProblemDetail}},
)
async def request_password_reset(
    payload: PasswordResetRequest,
    auth: AuthServiceDep,
    client: ClientContextDep,
    settings: SettingsDep,
) -> PasswordResetAccepted:
    limiter = RateLimiter(
        limit=settings.password_reset_max_attempts,
        window_seconds=settings.password_reset_window_seconds,
        scope="password-reset",
    )
    # The bucket key is the same shape as sign-in's, so throttling reveals nothing new: it is
    # keyed on the submitted address and the caller's hashed address, both of which the caller
    # already supplied.
    await _enforce_rate_limit(
        limiter, _rate_limit_identity(str(payload.email), client, settings), "password reset"
    )

    # Returns nothing, on purpose: there is no result here that could differ for a registered
    # address, and therefore nothing a future edit to this handler could leak.
    await auth.request_password_reset(email=str(payload.email), client=client)
    return PasswordResetAccepted()


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Set a new password with a reset token",
    description=(
        "Single use. Unknown, already spent, expired, and belonging to a disabled account all "
        "return the same 401, so a caller holding a guessed token learns nothing about which "
        "part of the guess was wrong. Success revokes every refresh session for the account — "
        "resetting a password is exactly when a user wants sessions they do not control "
        "dropped — so this does not sign anyone in and the refresh cookie is cleared."
    ),
    responses={HTTPStatus.UNAUTHORIZED: {"model": ProblemDetail}},
)
async def confirm_password_reset(
    payload: PasswordResetConfirm,
    response: Response,
    auth: AuthServiceDep,
    settings: SettingsDep,
) -> None:
    await auth.reset_password(token=payload.token, new_password=payload.new_password)
    # Every session for this account has just been revoked, so the cookie in this browser is
    # already dead; clearing it means the next call is a clean sign-in rather than a 401.
    _clear_refresh_cookie(response, settings)


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
    description=(
        "Includes `account_type` — which side of the marketplace this account is on, fixed at "
        "registration — and a summary of its organisation. The summary carries no contact "
        "block: it is the same shape a listing card shows to the public."
    ),
    responses=_AUTH_PROBLEM_RESPONSES,
)
async def me(current_user: CurrentUser) -> UserRead:
    # `organisation` is loaded by the `CurrentUser` dependency; serialising it from a lazy
    # relationship would fail mid-response under async SQLAlchemy.
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
