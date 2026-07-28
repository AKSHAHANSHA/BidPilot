"""Authentication orchestration: registration, login, refresh rotation, and logout.

All authentication policy lives here. Routes translate HTTP to calls and set the cookie;
they make no decisions. That separation is what lets the security-critical behaviour —
generic failures, rotation, reuse detection — be tested without HTTP.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import NoReturn

from sqlalchemy.exc import IntegrityError

from app.api.errors import AuthenticationError, ConflictError
from app.core.config import Settings
from app.core.logging import get_logger
from app.core.security import (
    IssuedAccessToken,
    create_access_token,
    generate_refresh_token,
    hash_ip,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    spend_dummy_verification,
    verify_password,
)
from app.domain.enums import AccountType
from app.models.refresh_session import RefreshSession
from app.models.user import User
from app.models.vendor_profile import VendorProfile
from app.repositories.refresh_session_repository import RefreshSessionRepository
from app.repositories.user_repository import UserRepository, normalize_email

logger = get_logger(__name__)

#: The only message a failed sign-in ever produces. Distinguishing "no such account" from
#: "wrong password" hands an attacker a working email-enumeration oracle.
INVALID_CREDENTIALS_DETAIL = "Invalid email or password."

#: Refresh failures are equally uninformative to the client. The reason is logged.
INVALID_SESSION_DETAIL = "Your session is no longer valid. Sign in again."


@dataclass(frozen=True, slots=True)
class ClientContext:
    """Where a request came from, for session records. Never used for authorization."""

    user_agent: str | None = None
    ip_address: str | None = None


@dataclass(frozen=True, slots=True)
class AuthResult:
    """Everything a route needs: the user, the access token, and the raw refresh token.

    The raw refresh token exists only in this object and in the `Set-Cookie` header. It is
    never persisted, logged, or returned in a response body.
    """

    user: User
    access: IssuedAccessToken
    refresh_token: str
    refresh_expires_at: datetime


class AuthService:
    def __init__(
        self,
        *,
        users: UserRepository,
        sessions: RefreshSessionRepository,
        settings: Settings,
    ) -> None:
        self.users = users
        self.sessions = sessions
        self.settings = settings

    # --- Registration ------------------------------------------------------------------

    async def register(
        self,
        *,
        email: str,
        password: str,
        display_name: str,
        client: ClientContext,
        account_type: str = AccountType.VENDOR.value,
        location: str | None = None,
        primary_category: str | None = None,
        bio: str | None = None,
    ) -> AuthResult:
        """Create an account and sign the new user in.

        Duplicate registration returns 409. This does confirm that an address is registered —
        a deliberate, documented trade-off (see `docs/08_ENGINEERING_DECISIONS.md`): the
        alternative, a fake success, makes the demo confusing and is defeated anyway by the
        login form.

        For vendor signups, a lightweight `VendorProfile` row is created in the same
        transaction using the supplied role-specific fields (marketplace layer). Company
        signups create no auxiliary rows here — companies fill in their existing rich
        `CompanyProfile` after sign-in.
        """
        normalized = normalize_email(email)
        if await self.users.email_exists(normalized):
            raise ConflictError("An account with this email address already exists.")

        user = self.users.create(
            email=normalized,
            password_hash=hash_password(password),
            display_name=display_name,
            account_type=account_type,
        )
        try:
            await self.users.flush()
        except IntegrityError as exc:
            # Two simultaneous registrations for the same address: the unique index is the
            # real arbiter, and it just rejected this one.
            raise ConflictError("An account with this email address already exists.") from exc

        if account_type == AccountType.VENDOR.value:
            self.users.session.add(
                VendorProfile(
                    owner_user_id=user.id,
                    display_name=display_name,
                    location=location,
                    primary_category=primary_category,
                    bio=bio,
                    contact_email=normalized,
                )
            )
            await self.users.flush()

        logger.info(
            "user_registered",
            extra={"user_id": str(user.id), "account_type": account_type},
        )
        return await self._issue_tokens(user, client)

    # --- Login -------------------------------------------------------------------------

    async def authenticate(self, *, email: str, password: str, client: ClientContext) -> AuthResult:
        """Verify credentials and start a session."""
        user = await self.users.get_by_email(email)

        if user is None:
            # Spend comparable CPU to a real verification so response time does not reveal
            # whether the address exists.
            spend_dummy_verification()
            logger.info("login_failed", extra={"reason": "unknown_email"})
            raise AuthenticationError(INVALID_CREDENTIALS_DETAIL)

        if not verify_password(user.password_hash, password):
            logger.info("login_failed", extra={"reason": "bad_password", "user_id": str(user.id)})
            raise AuthenticationError(INVALID_CREDENTIALS_DETAIL)

        if not user.is_active:
            # Same generic message: a deactivated account should not be identifiable either.
            logger.warning("login_failed", extra={"reason": "inactive", "user_id": str(user.id)})
            raise AuthenticationError(INVALID_CREDENTIALS_DETAIL)

        if needs_rehash(user.password_hash):
            # Transparently upgrade the stored hash now that we hold the plaintext.
            user.password_hash = hash_password(password)
            await self.users.flush()
            logger.info("password_hash_upgraded", extra={"user_id": str(user.id)})

        logger.info("login_succeeded", extra={"user_id": str(user.id)})
        return await self._issue_tokens(user, client)

    # --- Refresh -----------------------------------------------------------------------

    async def refresh(self, *, raw_token: str | None, client: ClientContext) -> AuthResult:
        """Rotate a refresh token.

        Every successful refresh revokes the presented token and issues a new one, so a
        captured token has a bounded useful life. Presenting an *already revoked* token means
        either a replay or a stolen cookie, and the response is to revoke every session for
        that user and force a fresh sign-in.
        """
        if not raw_token:
            raise AuthenticationError(INVALID_SESSION_DETAIL)

        token_hash = hash_refresh_token(raw_token)
        session_row = await self.sessions.get_by_token_hash(token_hash)

        if session_row is None:
            logger.info("refresh_failed", extra={"reason": "unknown_token"})
            raise AuthenticationError(INVALID_SESSION_DETAIL)

        now = datetime.now(tz=UTC)

        if session_row.is_revoked:
            revoked_count = await self.sessions.revoke_all_for_user(session_row.user_id, now=now)
            logger.warning(
                "refresh_token_reuse_detected",
                extra={
                    "user_id": str(session_row.user_id),
                    "sessions_revoked": revoked_count,
                },
            )
            await self._fail_refresh_durably()

        if session_row.is_expired(now=now):
            await self.sessions.revoke(session_row, now=now)
            logger.info("refresh_failed", extra={"reason": "expired"})
            await self._fail_refresh_durably()

        user = await self.users.get_by_id(session_row.user_id)
        if user is None or not user.is_active:
            await self.sessions.revoke(session_row, now=now)
            logger.warning(
                "refresh_failed",
                extra={"reason": "user_unavailable", "user_id": str(session_row.user_id)},
            )
            await self._fail_refresh_durably()

        await self.sessions.revoke(session_row, now=now)
        logger.info("refresh_rotated", extra={"user_id": str(user.id)})
        return await self._issue_tokens(user, client, now=now)

    # --- Logout ------------------------------------------------------------------------

    async def logout(self, *, raw_token: str | None) -> bool:
        """Revoke the presented session. Idempotent, and never reveals token validity.

        Returns whether a live session was actually revoked, purely for the response body;
        an unknown or already-revoked token is still a successful logout.
        """
        if not raw_token:
            return False

        session_row = await self.sessions.get_by_token_hash(hash_refresh_token(raw_token))
        if session_row is None or session_row.is_revoked:
            return False

        await self.sessions.revoke(session_row)
        logger.info("logout", extra={"user_id": str(session_row.user_id)})
        return True

    async def logout_everywhere(self, user_id: uuid.UUID) -> int:
        """Revoke every session for a user."""
        revoked = await self.sessions.revoke_all_for_user(user_id)
        logger.info("logout_all", extra={"user_id": str(user_id), "sessions_revoked": revoked})
        return revoked

    async def list_sessions(self, user_id: uuid.UUID) -> list[RefreshSession]:
        return await self.sessions.list_active_for_user(user_id)

    # --- Internals ---------------------------------------------------------------------

    async def _fail_refresh_durably(self) -> NoReturn:
        """Persist the revocation just decided, then reject the request.

        Order matters. `get_session` rolls back when a handler raises, so revoking a session
        and *then* raising would undo the revocation — a stolen token would keep working
        despite every attempt being detected and logged.
        """
        await self.sessions.commit_security_action()
        raise AuthenticationError(INVALID_SESSION_DETAIL)

    async def _issue_tokens(
        self, user: User, client: ClientContext, *, now: datetime | None = None
    ) -> AuthResult:
        issued_at = now or datetime.now(tz=UTC)
        access = create_access_token(
            user.id,
            secret=self.settings.jwt_secret,
            expires_in=timedelta(minutes=self.settings.access_token_minutes),
            now=issued_at,
        )
        raw_refresh = generate_refresh_token()
        refresh_expires_at = issued_at + timedelta(days=self.settings.refresh_token_days)

        self.sessions.create(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=refresh_expires_at,
            user_agent=client.user_agent,
            ip_hash=hash_ip(client.ip_address, secret=self.settings.jwt_secret),
        )
        await self.sessions.flush()

        return AuthResult(
            user=user,
            access=access,
            refresh_token=raw_refresh,
            refresh_expires_at=refresh_expires_at,
        )
