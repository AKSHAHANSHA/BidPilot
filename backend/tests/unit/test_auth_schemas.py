"""Password and registration policy, enforced at the API boundary."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.constants import MAX_PASSWORD_LENGTH
from app.schemas.auth import PASSWORD_MIN_LENGTH, LoginRequest, RegisterRequest

VALID = {
    "email": "coordinator@fm-demo.ae",
    "password": "a-long-demo-passphrase-1",
    "display_name": "Tender Coordinator",
}


def register(**overrides: object) -> RegisterRequest:
    return RegisterRequest(**{**VALID, **overrides})  # type: ignore[arg-type]


def test_valid_registration_is_accepted() -> None:
    payload = register()
    assert str(payload.email) == "coordinator@fm-demo.ae"
    assert payload.display_name == "Tender Coordinator"


def test_short_password_is_rejected() -> None:
    with pytest.raises(ValidationError):
        register(password="x" * (PASSWORD_MIN_LENGTH - 1))


def test_password_at_the_minimum_is_accepted() -> None:
    assert register(password="q" * PASSWORD_MIN_LENGTH).password


def test_absurdly_long_password_is_rejected() -> None:
    # An unbounded field would let a caller burn server CPU on Argon2 hashing.
    with pytest.raises(ValidationError):
        register(password="x" * (MAX_PASSWORD_LENGTH + 1))


def test_whitespace_only_password_is_rejected() -> None:
    with pytest.raises(ValidationError, match="non-whitespace"):
        register(password=" " * (PASSWORD_MIN_LENGTH + 4))


def test_password_surrounding_whitespace_is_preserved() -> None:
    """Passwords are never trimmed.

    Silently stripping would store a different secret than the user typed, and a client that
    does not trim identically could then never sign in.
    """
    padded = "  a-long-demo-passphrase-1  "
    assert register(password=padded).password == padded


def test_display_name_is_trimmed() -> None:
    assert register(display_name="  Tender Coordinator  ").display_name == "Tender Coordinator"


def test_password_containing_the_email_local_part_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must not contain the email"):
        register(email="coordinator@fm-demo.ae", password="coordinator-1234567")


def test_short_local_part_is_not_treated_as_a_forbidden_substring() -> None:
    # "ali" is too short to be a meaningful guess and would otherwise reject sane passwords.
    assert register(email="ali@fm-demo.ae", password="alignment-strategy-9").password


@pytest.mark.parametrize("bad_email", ["not-an-email", "@fm-demo.ae", "a@", "a b@c.test", ""])
def test_malformed_email_is_rejected(bad_email: str) -> None:
    with pytest.raises(ValidationError):
        register(email=bad_email)


def test_blank_display_name_is_rejected() -> None:
    with pytest.raises(ValidationError, match="non-whitespace"):
        register(display_name="   ")


def test_overlong_display_name_is_rejected() -> None:
    with pytest.raises(ValidationError):
        register(display_name="n" * 121)


def test_login_does_not_apply_the_password_policy() -> None:
    """A short password at login is an authentication failure, not a validation error.

    Rejecting it with 422 would tell an attacker that the policy is applied to real accounts,
    and would return a different shape for an account whose password predates the policy.
    """
    assert LoginRequest(email="coordinator@fm-demo.ae", password="x").password == "x"


def test_login_still_rejects_an_empty_password() -> None:
    with pytest.raises(ValidationError):
        LoginRequest(email="coordinator@fm-demo.ae", password="")
