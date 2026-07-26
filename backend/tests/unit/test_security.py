"""Security primitives: hashing, access-token signing, refresh-token handling."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.constants import ACCESS_TOKEN_TYPE, JWT_ALGORITHM
from app.core.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_ip,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    refresh_tokens_equal,
    spend_dummy_verification,
    verify_password,
)

SECRET = "unit-test-signing-key-0123456789abcdefgh"
OTHER_SECRET = "a-different-signing-key-0123456789abcdef"
PASSWORD = "a-long-demo-passphrase-1"


# --- Passwords ---------------------------------------------------------------------------


def test_hash_is_argon2id_and_not_the_password() -> None:
    digest = hash_password(PASSWORD)
    assert digest.startswith("$argon2id$")
    assert PASSWORD not in digest


def test_hash_is_salted_so_equal_passwords_differ() -> None:
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_verify_accepts_the_correct_password() -> None:
    assert verify_password(hash_password(PASSWORD), PASSWORD) is True


@pytest.mark.parametrize("wrong", ["", "wrong-password", PASSWORD + "x", PASSWORD.upper()])
def test_verify_rejects_wrong_passwords_without_raising(wrong: str) -> None:
    assert verify_password(hash_password(PASSWORD), wrong) is False


def test_verify_rejects_a_corrupt_stored_hash() -> None:
    # A truncated or hand-edited hash must fail closed, not raise into the request path.
    assert verify_password("not-a-real-hash", PASSWORD) is False


def test_long_password_is_supported() -> None:
    # Argon2 has no bcrypt-style 72-byte truncation, so a long passphrase is fully honoured.
    long_password = "correct horse battery staple " * 4
    digest = hash_password(long_password)
    assert verify_password(digest, long_password) is True
    assert verify_password(digest, long_password[:-1]) is False


def test_current_hash_does_not_need_rehash() -> None:
    assert needs_rehash(hash_password(PASSWORD)) is False


def test_unparseable_hash_is_treated_as_needing_rehash() -> None:
    assert needs_rehash("garbage") is True


def test_dummy_verification_is_callable_and_silent() -> None:
    # Used to equalize login timing for unknown accounts; it must never raise.
    spend_dummy_verification()


# --- Access tokens -----------------------------------------------------------------------


def test_round_trip_preserves_the_subject() -> None:
    user_id = uuid.uuid4()
    issued = create_access_token(user_id, secret=SECRET, expires_in=timedelta(minutes=15))
    claims = decode_access_token(issued.token, secret=SECRET)
    assert claims.user_id == user_id
    assert issued.expires_in_seconds == 900


def test_issued_token_carries_expiry_and_type() -> None:
    issued = create_access_token(uuid.uuid4(), secret=SECRET, expires_in=timedelta(minutes=5))
    payload = jwt.decode(issued.token, SECRET, algorithms=[JWT_ALGORITHM])
    assert payload["typ"] == ACCESS_TOKEN_TYPE
    assert payload["jti"]
    assert payload["exp"] > payload["iat"]


def test_each_token_has_a_unique_id() -> None:
    first = create_access_token(uuid.uuid4(), secret=SECRET, expires_in=timedelta(minutes=5))
    second = create_access_token(uuid.uuid4(), secret=SECRET, expires_in=timedelta(minutes=5))
    assert (
        decode_access_token(first.token, secret=SECRET).token_id
        != decode_access_token(second.token, secret=SECRET).token_id
    )


def test_expired_token_is_rejected() -> None:
    past = datetime.now(tz=UTC) - timedelta(hours=2)
    issued = create_access_token(
        uuid.uuid4(), secret=SECRET, expires_in=timedelta(minutes=15), now=past
    )
    with pytest.raises(TokenError):
        decode_access_token(issued.token, secret=SECRET)


def test_token_signed_with_another_secret_is_rejected() -> None:
    issued = create_access_token(uuid.uuid4(), secret=OTHER_SECRET, expires_in=timedelta(minutes=5))
    with pytest.raises(TokenError):
        decode_access_token(issued.token, secret=SECRET)


def test_tampered_payload_is_rejected() -> None:
    issued = create_access_token(uuid.uuid4(), secret=SECRET, expires_in=timedelta(minutes=5))
    header, payload, signature = issued.token.split(".")
    forged = f"{header}.{payload[:-2]}xy.{signature}"
    with pytest.raises(TokenError):
        decode_access_token(forged, secret=SECRET)


def test_unsigned_token_is_rejected() -> None:
    # The `alg: none` attack: a token that declares it needs no signature.
    forged = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "typ": ACCESS_TOKEN_TYPE,
            "iat": int(datetime.now(tz=UTC).timestamp()),
            "exp": int((datetime.now(tz=UTC) + timedelta(minutes=5)).timestamp()),
        },
        key="",
        algorithm="none",
    )
    with pytest.raises(TokenError):
        decode_access_token(forged, secret=SECRET)


def test_token_of_the_wrong_type_is_rejected() -> None:
    # A correctly signed token is still refused for API access unless it is an access token.
    forged = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "typ": "refresh",
            "iat": int(datetime.now(tz=UTC).timestamp()),
            "exp": int((datetime.now(tz=UTC) + timedelta(minutes=5)).timestamp()),
        },
        SECRET,
        algorithm=JWT_ALGORITHM,
    )
    with pytest.raises(TokenError, match="not an access token"):
        decode_access_token(forged, secret=SECRET)


def test_token_missing_required_claims_is_rejected() -> None:
    forged = jwt.encode({"sub": str(uuid.uuid4())}, SECRET, algorithm=JWT_ALGORITHM)
    with pytest.raises(TokenError):
        decode_access_token(forged, secret=SECRET)


def test_token_with_non_uuid_subject_is_rejected() -> None:
    forged = jwt.encode(
        {
            "sub": "administrator",
            "typ": ACCESS_TOKEN_TYPE,
            "iat": int(datetime.now(tz=UTC).timestamp()),
            "exp": int((datetime.now(tz=UTC) + timedelta(minutes=5)).timestamp()),
        },
        SECRET,
        algorithm=JWT_ALGORITHM,
    )
    with pytest.raises(TokenError, match="not a valid user id"):
        decode_access_token(forged, secret=SECRET)


@pytest.mark.parametrize("garbage", ["", "not.a.token", "a.b", "...."])
def test_malformed_token_strings_are_rejected(garbage: str) -> None:
    with pytest.raises(TokenError):
        decode_access_token(garbage, secret=SECRET)


# --- Refresh tokens ----------------------------------------------------------------------


def test_generated_refresh_tokens_are_unique_and_long() -> None:
    tokens = {generate_refresh_token() for _ in range(100)}
    assert len(tokens) == 100
    assert all(len(token) >= 60 for token in tokens)


def test_refresh_hash_is_deterministic_and_hides_the_token() -> None:
    token = generate_refresh_token()
    digest = hash_refresh_token(token)
    assert digest == hash_refresh_token(token)
    assert len(digest) == 64
    assert token not in digest


def test_different_refresh_tokens_hash_differently() -> None:
    assert hash_refresh_token(generate_refresh_token()) != hash_refresh_token(
        generate_refresh_token()
    )


def test_refresh_comparison_matches_only_the_original_token() -> None:
    token = generate_refresh_token()
    stored = hash_refresh_token(token)
    assert refresh_tokens_equal(stored, token) is True
    assert refresh_tokens_equal(stored, generate_refresh_token()) is False


# --- IP hashing --------------------------------------------------------------------------


def test_ip_hash_is_keyed_so_it_cannot_be_recomputed_without_the_secret() -> None:
    address = "203.0.113.7"
    assert hash_ip(address, secret=SECRET) != hash_ip(address, secret=OTHER_SECRET)


def test_ip_hash_is_stable_for_the_same_address() -> None:
    assert hash_ip("203.0.113.7", secret=SECRET) == hash_ip("203.0.113.7", secret=SECRET)


def test_ip_hash_never_contains_the_address() -> None:
    digest = hash_ip("203.0.113.7", secret=SECRET)
    assert digest is not None
    assert "203.0.113" not in digest


@pytest.mark.parametrize("missing", [None, ""])
def test_unknown_address_hashes_to_none(missing: str | None) -> None:
    assert hash_ip(missing, secret=SECRET) is None
