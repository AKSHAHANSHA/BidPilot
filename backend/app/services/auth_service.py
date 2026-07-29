"""Authentication orchestration: registration, login, refresh rotation, logout, and reset.

All authentication policy lives here. Routes translate HTTP to calls and set the cookie;
they make no decisions. That separation is what lets the security-critical behaviour —
generic failures, rotation, reuse detection — be tested without HTTP.

Registration creates the account *and* its organisation in one unit of work
(`docs/09_PORTAL_SPEC.md` §3.2). Password reset is the second flow with an enumeration
surface, and it is handled the same way sign-in is: identical outcome whether or not the
address exists, with the reason recorded only in the log.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import NoReturn

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import set_committed_value

from app.api.errors import AuthenticationError, ConflictError
from app.core.config import ConfigurationError, Settings
from app.core.logging import get_logger
from app.core.mail import MailDeliveryError, Mailer
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
from app.repositories.organisation_repository import OrganisationRepository
from app.repositories.password_reset_repository import PasswordResetTokenRepository
from app.repositories.refresh_session_repository import RefreshSessionRepository
from app.repositories.user_repository import UserRepository, normalize_email
from app.schemas.organisation import OrganisationCreate

logger = get_logger(__name__)

#: The only message a failed sign-in ever produces. Distinguishing "no such account" from
#: "wrong password" hands an attacker a working email-enumeration oracle.
INVALID_CREDENTIALS_DETAIL = "Invalid email or password."

#: Refresh failures are equally uninformative to the client. The reason is logged.
INVALID_SESSION_DETAIL = "Your session is no longer valid. Sign in again."

#: Unknown, spent, and expired reset tokens are one answer, for the same reason. It names the
#: recovery action because, unlike a failed sign-in, there is always something useful to do.
INVALID_RESET_LINK_DETAIL = "This password reset link is no longer valid. Request a new one."

#: 32 random bytes (256 bits). Shorter than a refresh token because the lifetime is an hour
#: rather than a week, and far past the point where guessing is a strategy.
PASSWORD_RESET_TOKEN_BYTES = 32

RESET_MAIL_SUBJECT = "Reset your {app_name} password"

#: Plain text, and deliberately dull. It states what was requested, what to do, when the link
#: dies, and that ignoring it is safe — the last line matters because most recipients of an
#: unexpected reset mail did not request it.
RESET_MAIL_BODY = """Hello {display_name},

Someone asked to reset the password for your {app_name} account.

Open this link to choose a new one:

{link}

The link works once and expires at {expires_at} UTC.

If this was not you, no action is needed. Your password has not changed, and nobody can
change it without this message.

-- {from_name}
"""


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
        organisations: OrganisationRepository,
        tokens: PasswordResetTokenRepository,
        mailer: Mailer,
        settings: Settings,
    ) -> None:
        self.users = users
        self.sessions = sessions
        self.organisations = organisations
        self.tokens = tokens
        self.mailer = mailer
        self.settings = settings

    # --- Registration ------------------------------------------------------------------

    async def register(
        self,
        *,
        email: str,
        password: str,
        display_name: str,
        account_type: AccountType,
        organisation: OrganisationCreate,
        client: ClientContext,
    ) -> AuthResult:
        """Create an account and its organisation, then sign the new user in.

        The organisation is required and is created here rather than as a later step: every
        listing card and applicant row renders the organisation, not the user, so an account
        without one is an account that cannot appear anywhere in the portal. Both rows belong
        to the request's single unit of work — `get_session` commits once — so a failure
        halfway cannot leave a user stranded without an identity.

        `account_type` is written to both rows. The copy on the organisation is deliberate
        denormalisation (see `app/models/organisation.py`) and is safe only because the value
        is immutable, which is why nothing else in this service ever assigns it.

        Duplicate registration returns 409. This does confirm that an address is registered —
        a deliberate, documented trade-off (see `docs/08_ENGINEERING_DECISIONS.md`): the
        alternative, a fake success, makes the demo confusing and is defeated anyway by the
        login form.
        """
        normalized = normalize_email(email)
        if await self.users.email_exists(normalized):
            raise ConflictError("An account with this email address already exists.")

        user = self.users.create(
            email=normalized,
            password_hash=hash_password(password),
            display_name=display_name,
        )
        # `UserRepository.create` predates account types. Assigning the column here keeps
        # registration the one place that decides which side of the marketplace an account is
        # on, instead of spreading that decision across two modules.
        user.account_type = account_type.value
        try:
            await self.users.flush()
        except IntegrityError as exc:
            # Two simultaneous registrations for the same address: the unique index is the
            # real arbiter, and it just rejected this one.
            raise ConflictError("An account with this email address already exists.") from exc

        record = self.organisations.create(
            owner_user_id=user.id,
            # Copied from the account, never read from the request body: the client states its
            # side once, so the two cannot disagree.
            account_type=account_type,
            name=organisation.name,
            description=organisation.description,
            emirate=organisation.emirate,
            contact_email=str(organisation.contact_email),
            industry=organisation.industry,
            registration_number=organisation.registration_number,
            city=organisation.city,
            address_line=organisation.address_line,
            country=organisation.country,
            contact_phone=organisation.contact_phone,
            website=str(organisation.website) if organisation.website else None,
            year_established=organisation.year_established,
            employee_count=organisation.employee_count,
        )
        await self.organisations.flush()

        logger.info(
            "user_registered",
            extra={
                "user_id": str(user.id),
                "account_type": account_type.value,
                "organisation_id": str(record.id),
            },
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

    # --- Password reset ----------------------------------------------------------------

    async def request_password_reset(self, *, email: str, client: ClientContext) -> None:
        """Issue a reset link, or do nothing at all — the caller cannot tell which.

        The route answers 202 either way (`docs/09_PORTAL_SPEC.md` §3.2). This method returns
        nothing for the same reason: there is no result a handler could accidentally leak into
        a response that differs for a registered address.

        One residual side channel, stated rather than hidden: the real path writes two rows and
        hands a message to the transport, so over SMTP a registered address takes measurably
        longer. The per-email+IP rate limit on the route bounds how usefully that can be
        sampled; closing it completely would mean moving delivery onto the job queue, which is
        not worth a queue dependency for one message.
        """
        user = await self.users.get_by_email(email)
        if user is None or not user.is_active:
            # A deactivated account is treated as absent here on purpose — reset is not a way
            # to find out that an account exists but has been switched off. The address is not
            # logged: it is precisely what a probe is trying to confirm.
            logger.info("password_reset_requested", extra={"outcome": "no_active_account"})
            return

        now = datetime.now(tz=UTC)
        # Supersede any live link before minting a new one. Two working links for one account
        # means an attacker who triggered an earlier reset still holds a usable one after the
        # owner completes theirs.
        superseded = await self.tokens.invalidate_for_user(user.id, now=now)

        raw_token = secrets.token_urlsafe(PASSWORD_RESET_TOKEN_BYTES)
        expires_at = now + timedelta(minutes=self.settings.password_reset_ttl_minutes)
        self.tokens.create(
            user_id=user.id,
            # The same SHA-256 helper refresh tokens use. Its name says "refresh" but the
            # reasoning is identical — server-generated randomness needs an indexed lookup, not
            # a password hash — and a second copy of one line would only be a second thing to
            # keep in step. Only the digest is stored; the raw token leaves in the mail.
            token_hash=hash_refresh_token(raw_token),
            expires_at=expires_at,
            requested_ip_hash=hash_ip(client.ip_address, secret=self.settings.jwt_secret),
        )
        await self.tokens.flush()

        await self._send_password_reset(user, raw_token=raw_token, expires_at=expires_at)
        logger.info(
            "password_reset_requested",
            extra={
                "outcome": "issued",
                "user_id": str(user.id),
                "superseded": superseded,
                "ttl_minutes": self.settings.password_reset_ttl_minutes,
            },
        )

    async def reset_password(self, *, token: str, new_password: str) -> None:
        """Consume a reset token and set the new password.

        Unknown, already spent, expired, and belonging-to-a-disabled-account all produce the
        identical error, for the reason a failed sign-in does: the reply must not tell someone
        holding a guessed token which part of the guess was wrong.

        Lookup is by digest — the raw token is never compared against anything, and never
        stored — so there is no secret for a comparison to leak timing about.

        Success revokes every refresh session for the account. Resetting a password is exactly
        the moment a user wants sessions they do not control dropped, and they may well be
        resetting *because* of one.
        """
        record = await self.tokens.get_by_token_hash(hash_refresh_token(token))
        if record is None:
            logger.info("password_reset_failed", extra={"reason": "unknown_token"})
            raise AuthenticationError(INVALID_RESET_LINK_DETAIL)

        now = datetime.now(tz=UTC)
        if not record.is_usable(now=now):
            logger.info(
                "password_reset_failed",
                extra={
                    "reason": "already_used" if record.is_used else "expired",
                    "user_id": str(record.user_id),
                },
            )
            raise AuthenticationError(INVALID_RESET_LINK_DETAIL)

        user = await self.users.get_by_id(record.user_id)
        if user is None or not user.is_active:
            logger.warning(
                "password_reset_failed",
                extra={"reason": "user_unavailable", "user_id": str(record.user_id)},
            )
            raise AuthenticationError(INVALID_RESET_LINK_DETAIL)

        user.password_hash = hash_password(new_password)
        await self.tokens.mark_used(record, now=now)
        # Any *other* outstanding link dies with this one. The account has just been recovered;
        # a second link still in someone's inbox would undo that.
        await self.tokens.invalidate_for_user(user.id, now=now)
        revoked = await self.sessions.revoke_all_for_user(user.id, now=now)

        logger.info(
            "password_reset_completed",
            extra={"user_id": str(user.id), "sessions_revoked": revoked},
        )

    # --- Internals ---------------------------------------------------------------------

    async def _send_password_reset(
        self, user: User, *, raw_token: str, expires_at: datetime
    ) -> None:
        """Render and deliver the reset mail. Never propagates a delivery failure.

        A dead relay and a malformed URL template are the same thing from the requester's
        point of view — the link did not arrive — and both must stay invisible in the
        response: an endpoint that 500s only for registered addresses is the enumeration
        oracle this flow exists to avoid. The token is left to expire unused and the failure
        is an ERROR in the log, which is where an operator would look for it anyway.
        """
        try:
            link = self._reset_link(raw_token)
            await self.mailer.send(
                to=user.email,
                subject=RESET_MAIL_SUBJECT.format(app_name=self.settings.app_name),
                text_body=RESET_MAIL_BODY.format(
                    display_name=user.display_name,
                    app_name=self.settings.app_name,
                    link=link,
                    expires_at=expires_at.strftime("%Y-%m-%d %H:%M"),
                    from_name=self.settings.mail_from_name,
                ),
            )
        except (MailDeliveryError, ConfigurationError):
            logger.error("password_reset_mail_failed", extra={"user_id": str(user.id)})
            return

        extra = {"user_id": str(user.id)}
        if self.settings.is_development:
            # Development only. A reset link is a bearer credential; however convenient it
            # would be to have in a deployed environment's log, that is a password reset
            # anyone with log access can complete.
            extra["reset_link"] = link
        logger.info("password_reset_mail_sent", extra=extra)

    def _reset_link(self, raw_token: str) -> str:
        """Render the frontend URL the user actually clicks.

        `frontend_origin` may hold a comma-separated allowlist because it also feeds CORS, so
        the first entry is taken as canonical; its trailing slash is dropped because the
        template supplies its own separator.
        """
        origins = self.settings.cors_origins
        origin = (origins[0] if origins else self.settings.frontend_origin).rstrip("/")
        try:
            return self.settings.password_reset_url_template.format(
                frontend_origin=origin, token=raw_token
            )
        except (KeyError, IndexError) as exc:
            raise ConfigurationError(
                "PASSWORD_RESET_URL_TEMPLATE may only use the {frontend_origin} and {token} "
                "placeholders"
            ) from exc

    async def _attach_organisation(self, user: User) -> None:
        """Populate `User.organisation` with an explicit query.

        `UserRead` serializes the relationship, and the model does not load it eagerly, so
        without this the serializer triggers a lazy load from synchronous code and raises
        `MissingGreenlet` — a 500 on a request that had already succeeded. Registration goes
        through the same path as sign-in rather than binding the row it just created, so there
        is one behaviour to reason about instead of two.

        `set_committed_value` writes the loaded value without marking the user dirty; assigning
        the relationship normally would emit an UPDATE and, for a one-to-one, a load of the
        value being replaced.
        """
        set_committed_value(user, "organisation", await self.organisations.get_for_owner(user.id))

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

        # Every path that produces an `AuthResult` also serializes the user, so the
        # organisation is loaded here — one funnel, rather than three call sites that each
        # have to remember.
        await self._attach_organisation(user)

        return AuthResult(
            user=user,
            access=access,
            refresh_token=raw_refresh,
            refresh_expires_at=refresh_expires_at,
        )
