"""Password hashing, access-token signing, and refresh-token handling.

Pure functions over primitives — no database, no request context — so every rule here is
directly unit-testable. Policy decisions live in `docs/08_ENGINEERING_DECISIONS.md`.

Two token kinds, deliberately different:

* **Access token** — a short-lived signed JWT. Stateless, verified without a database round
  trip on every request.
* **Refresh token** — an opaque 384-bit random string. Long-lived, so revocation must be
  authoritative: only its SHA-256 hash is stored, and every use is checked against the
  database. A JWT refresh token would invite stateless validation and silently break logout.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.constants import (
    ACCESS_TOKEN_TYPE,
    JWT_ALGORITHM,
    REFRESH_TOKEN_BYTES,
)

_hasher = PasswordHasher()

#: Hash of a value nobody can supply, used to spend the same CPU time on a login attempt for
#: an unknown email as for a known one. Without it, response latency reveals which addresses
#: are registered.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(32))


class TokenError(Exception):
    """An access token is malformed, expired, mis-signed, or of the wrong type.

    Callers translate this into a single generic authentication failure; the specific reason
    is logged, never returned, so a probing client learns nothing.
    """


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    user_id: uuid.UUID
    token_id: str
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class IssuedAccessToken:
    token: str
    expires_at: datetime
    expires_in_seconds: int


# --- Passwords ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Hash a password with Argon2id using the library's current defaults."""
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Return whether the password matches. Never raises on a wrong password."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when a stored hash predates the current Argon2 cost parameters."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def spend_dummy_verification() -> None:
    """Burn one Argon2 verification.

    Called when no user matches the submitted email so that "unknown account" and "wrong
    password" take comparable time.
    """
    verify_password(_DUMMY_HASH, "not-the-password")


# --- Access tokens -----------------------------------------------------------------------


def create_access_token(
    user_id: uuid.UUID,
    *,
    secret: str,
    expires_in: timedelta,
    now: datetime | None = None,
) -> IssuedAccessToken:
    """Sign a short-lived access token.

    `now` is injectable so tests can produce an already-expired token without sleeping.
    """
    issued_at = now or datetime.now(tz=UTC)
    expires_at = issued_at + expires_in
    payload = {
        "sub": str(user_id),
        "jti": uuid.uuid4().hex,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "typ": ACCESS_TOKEN_TYPE,
    }
    token = jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)
    return IssuedAccessToken(
        token=token,
        expires_at=expires_at,
        expires_in_seconds=int(expires_in.total_seconds()),
    )


def decode_access_token(token: str, *, secret: str) -> AccessTokenClaims:
    """Verify and decode an access token, or raise :class:`TokenError`."""
    try:
        payload = jwt.decode(
            token,
            secret,
            # Only the algorithm we issue is accepted. Trusting the token's own `alg` header
            # allows the `alg: none` and RS256-to-HS256 confusion attacks.
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "iat", "sub", "typ"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(f"token rejected: {type(exc).__name__}") from exc

    if payload.get("typ") != ACCESS_TOKEN_TYPE:
        raise TokenError("token is not an access token")

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise TokenError("token subject is not a valid user id") from exc

    return AccessTokenClaims(
        user_id=user_id,
        token_id=str(payload.get("jti", "")),
        issued_at=datetime.fromtimestamp(payload["iat"], tz=UTC),
        expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
    )


# --- Refresh tokens ----------------------------------------------------------------------


def generate_refresh_token() -> str:
    """Return a fresh opaque refresh token. This is the only time the raw value exists."""
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_refresh_token(token: str) -> str:
    """Hash a refresh token for storage and lookup.

    SHA-256 rather than Argon2, deliberately: the token is 384 bits of server-generated
    randomness, so there is no guessable password to slow down, and lookup must be a single
    indexed query rather than a scan that verifies every stored hash in turn.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def refresh_tokens_equal(stored_hash: str, candidate_token: str) -> bool:
    """Constant-time comparison of a presented token against a stored hash."""
    return hmac.compare_digest(stored_hash, hash_refresh_token(candidate_token))


# --- Client fingerprints -----------------------------------------------------------------


def hash_ip(ip_address: str | None, *, secret: str) -> str | None:
    """Return a keyed hash of a client IP, or None when the address is unknown.

    Sessions record where they were created to make suspicious activity visible, but a raw
    IP is personal data. Keying with the application secret stops an attacker who reads the
    database from confirming a guessed address by hashing it themselves.
    """
    if not ip_address:
        return None
    digest = hmac.new(secret.encode("utf-8"), ip_address.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()
