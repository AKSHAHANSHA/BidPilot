"""Ownership enforcement is structural, not a habit.

`docs/04_API_AND_DATA_MODEL.md` §5 forbids fetching an owned row by ID and checking ownership
somewhere else afterwards. These tests assert that the repository base class makes that
impossible to express: every read, list, and delete requires the owner's ID, and the generated
SQL actually filters on it.
"""

from __future__ import annotations

import inspect
import uuid

import pytest
from sqlalchemy import select

from app.models.refresh_session import RefreshSession
from app.repositories.base import OwnedRepository
from app.repositories.refresh_session_repository import RefreshSessionRepository
from app.repositories.user_repository import UserRepository, normalize_email

OWNED_ACCESS_METHODS = ["get_for_user", "list_for_user", "count_for_user", "delete_for_user"]


@pytest.mark.parametrize("method_name", OWNED_ACCESS_METHODS)
def test_every_owned_accessor_requires_a_user_id(method_name: str) -> None:
    signature = inspect.signature(getattr(OwnedRepository, method_name))
    assert "user_id" in signature.parameters


def test_owned_repository_exposes_no_lookup_without_an_owner() -> None:
    """There must be no `get(id)`-style escape hatch on the owned base class."""
    public_methods = {
        name
        for name, member in inspect.getmembers(OwnedRepository, inspect.isfunction)
        if not name.startswith("_")
    }
    forbidden = {"get", "get_by_id", "list", "all", "delete_by_id"}
    assert public_methods & forbidden == set()


def test_ownership_predicate_targets_the_declared_owner_column() -> None:
    # RefreshSession's foreign key is `user_id`, not the default `owner_user_id`.
    assert RefreshSessionRepository.owner_field == "user_id"
    predicate = RefreshSessionRepository.owned_by(uuid.uuid4())
    assert "user_id" in str(predicate)


def test_generated_sql_filters_on_both_id_and_owner() -> None:
    entity_id = uuid.uuid4()
    user_id = uuid.uuid4()
    statement = select(RefreshSession).where(
        RefreshSession.id == entity_id,
        RefreshSessionRepository.owned_by(user_id),
    )
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
    # PostgreSQL UUID literals render without dashes.
    assert entity_id.hex in compiled
    assert user_id.hex in compiled
    assert "refresh_sessions.user_id" in compiled


def test_user_repository_is_not_owned() -> None:
    """A user is the owner, not an owned record; inheriting the owned base would be wrong."""
    assert not issubclass(UserRepository, OwnedRepository)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Coordinator@FM-Demo.AE", "coordinator@fm-demo.ae"),
        ("  spaced@example.test  ", "spaced@example.test"),
        ("already@lower.test", "already@lower.test"),
    ],
)
def test_email_normalization_is_applied_consistently(raw: str, expected: str) -> None:
    # Lookup and insert must agree, or a case-different address creates a second account.
    assert normalize_email(raw) == expected
