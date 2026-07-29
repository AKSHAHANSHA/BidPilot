"""Request and response schemas for authentication.

Password policy lives here so it is enforced at the boundary, applies identically to every
entry point, and appears in the generated OpenAPI contract the frontend validates against.
Registration and password reset share the policy through `Password` and
`reject_whitespace_only_password` rather than restating it, so the two can never drift.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.constants import MAX_PASSWORD_LENGTH
from app.domain.enums import AccountType
from app.schemas.organisation import OrganisationCreate, OrganisationSummary

#: Domain used in schema examples and tests. `.test`, `.invalid`, and `.localhost` are
#: special-use names that `email-validator` refuses, so examples use a realistic domain.
EXAMPLE_DOMAIN = "fm-demo.ae"

#: Minimum length. Kept as a constant rather than read from settings because it is part of the
#: published schema; settings carry the same value for service-layer checks.
PASSWORD_MIN_LENGTH = 12

#: A reset token is `secrets.token_urlsafe` output. Bounded so a hostile caller cannot make
#: the server hash a megabyte of input looking for a match.
RESET_TOKEN_MIN_LENGTH = 16
RESET_TOKEN_MAX_LENGTH = 512

Password = Annotated[str, Field(min_length=PASSWORD_MIN_LENGTH, max_length=MAX_PASSWORD_LENGTH)]


def reject_whitespace_only_password(value: str) -> str:
    """A password of nothing but spaces satisfies the length bound and is still not a secret.

    Module-level so registration and password reset apply the identical rule; a second copy
    would eventually be relaxed in one place and not the other.
    """
    if not value.strip():
        raise ValueError("Password must contain non-whitespace characters")
    return value


class RegisterRequest(BaseModel):
    # Deliberately no model-wide `str_strip_whitespace`: it would silently trim the password
    # too, so " passphrase " would be stored as "passphrase" and a client that does not trim
    # could never sign in again. Text fields are stripped individually below.
    email: EmailStr = Field(examples=["coordinator@fm-demo.ae"])
    password: Password = Field(examples=["a-long-passphrase-1"])
    display_name: str = Field(min_length=1, max_length=120, examples=["Tender Coordinator"])
    account_type: AccountType = Field(
        description=(
            "Which side of the marketplace this account is on. Fixed at registration and never "
            "changed: an account's listings and applications would be meaningless if its side "
            "could flip underneath them."
        )
    )
    organisation: OrganisationCreate = Field(
        description=(
            "Required. The account and its organisation are created in one transaction, so a "
            "user can never exist without the identity every listing card and applicant row "
            "has to render."
        )
    )

    @field_validator("display_name")
    @classmethod
    def _strip_display_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Display name must contain non-whitespace characters")
        return stripped

    @field_validator("password")
    @classmethod
    def _reject_whitespace_only(cls, value: str) -> str:
        return reject_whitespace_only_password(value)

    @model_validator(mode="after")
    def _password_must_not_contain_email(self) -> RegisterRequest:
        # A password derived from the address is the first thing an attacker tries.
        local_part = str(self.email).split("@", 1)[0].lower()
        if len(local_part) >= 4 and local_part in self.password.lower():
            raise ValueError("Password must not contain the email address")
        return self


class LoginRequest(BaseModel):
    # Not `Password`: a login attempt with a short password must fail as a normal
    # authentication failure, not as a 422 that reveals the policy applied to real accounts.
    # The submitted password is passed through untouched for the same reason as above.
    email: EmailStr
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class PasswordResetRequest(BaseModel):
    """`POST /auth/password-reset/request`.

    Always answered with 202 whether or not the address is registered: a differing response
    would be an account-enumeration oracle.
    """

    email: EmailStr = Field(examples=["coordinator@fm-demo.ae"])


class PasswordResetConfirm(BaseModel):
    """`POST /auth/password-reset/confirm`. Single-use; consuming the token revokes every
    refresh session for that account."""

    token: Annotated[
        str,
        Field(
            min_length=RESET_TOKEN_MIN_LENGTH,
            max_length=RESET_TOKEN_MAX_LENGTH,
            description="The opaque token from the reset link.",
        ),
    ]
    #: The same policy registration applies — reused, not restated.
    new_password: Password = Field(examples=["a-long-passphrase-1"])

    @field_validator("new_password")
    @classmethod
    def _reject_whitespace_only(cls, value: str) -> str:
        return reject_whitespace_only_password(value)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    display_name: str
    is_active: bool
    account_type: AccountType
    #: Loaded from the `organisation` relationship, so callers must eager-load it. Optional
    #: only because accounts created before the portal layer have no organisation row.
    organisation: OrganisationSummary | None = None
    created_at: datetime


class TokenResponse(BaseModel):
    """Access token plus the authenticated user.

    The refresh token is absent by design: it is delivered only as an HttpOnly cookie, so
    JavaScript cannot read it and an XSS payload cannot exfiltrate a long-lived credential.
    """

    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - a scheme name, not a credential
    expires_in: int = Field(description="Access token lifetime in seconds.")
    user: UserRead


class LogoutResponse(BaseModel):
    revoked: bool = Field(description="Whether a live session was revoked by this call.")


class SessionRead(BaseModel):
    """A live refresh session, so a user can see where they are signed in."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    expires_at: datetime
    user_agent: str | None
