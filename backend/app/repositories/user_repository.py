"""User persistence.

`User` is not an `OwnedRepository`: a user is the owner, not an owned record. Lookup by email
exists solely for login and registration.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.domain.enums import AccountType
from app.models.user import User
from app.repositories.base import BaseRepository


def normalize_email(email: str) -> str:
    """Canonical stored form. Applied on both write and lookup, or the two disagree."""
    return email.strip().lower()


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.email == normalize_email(email))
        )
        return result.scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        result = await self.session.execute(
            select(User.id).where(User.email == normalize_email(email))
        )
        return result.scalar_one_or_none() is not None

    def create(
        self,
        *,
        email: str,
        password_hash: str,
        display_name: str,
        account_type: str = AccountType.VENDOR.value,
    ) -> User:
        user = User(
            email=normalize_email(email),
            password_hash=password_hash,
            display_name=display_name.strip(),
            is_active=True,
            account_type=account_type,
        )
        return self.add(user)
