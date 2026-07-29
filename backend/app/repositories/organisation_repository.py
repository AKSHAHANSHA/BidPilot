"""Organisation persistence.

An organisation is created once, during registration, and read constantly afterwards — it is
the name on every listing card and every applicant row. Two lookups therefore exist and they
are deliberately different: `get_for_owner` is the owner-scoped read used by `/auth/me` and by
anything that writes on the organisation's behalf, while `get_by_id` is the unscoped read a
public listing card needs, since a visitor has no user ID to scope by. `get_by_id` returns an
organisation and nothing that hangs off it, so it cannot become a path to another account's
listings.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.domain.enums import AccountType, Emirate
from app.models.organisation import Organisation
from app.repositories.base import OwnedRepository


class OrganisationRepository(OwnedRepository[Organisation]):
    model = Organisation
    owner_field = "owner_user_id"

    async def get_for_owner(self, user_id: uuid.UUID) -> Organisation | None:
        """The account's single organisation.

        `scalar_one_or_none` rather than `.first()`: one-per-account is a unique constraint, so
        a second row means the constraint failed and we want the error, not an arbitrary pick.
        """
        result = await self.session.execute(select(Organisation).where(self.owned_by(user_id)))
        return result.scalar_one_or_none()

    async def get_by_id(self, organisation_id: uuid.UUID) -> Organisation | None:
        """Unscoped read for public rendering. Never use this to authorise a write."""
        result = await self.session.execute(
            select(Organisation).where(Organisation.id == organisation_id)
        )
        return result.scalar_one_or_none()

    async def exists_for_owner(self, user_id: uuid.UUID) -> bool:
        result = await self.session.execute(select(Organisation.id).where(self.owned_by(user_id)))
        return result.scalar_one_or_none() is not None

    def create(
        self,
        *,
        owner_user_id: uuid.UUID,
        account_type: AccountType,
        name: str,
        description: str,
        emirate: Emirate,
        contact_email: str,
        industry: str | None = None,
        registration_number: str | None = None,
        city: str | None = None,
        address_line: str | None = None,
        country: str = "United Arab Emirates",
        contact_phone: str | None = None,
        website: str | None = None,
        year_established: int | None = None,
        employee_count: int | None = None,
    ) -> Organisation:
        """Build and stage the row. No commit — registration's unit of work owns that, so the
        user and the organisation land together or not at all."""
        organisation = Organisation(
            owner_user_id=owner_user_id,
            # Stored as the plain value: the column is a String with a CHECK constraint, not a
            # database enum, so the enum member itself would not round-trip.
            account_type=account_type.value,
            name=name.strip(),
            description=description.strip(),
            industry=industry,
            registration_number=registration_number,
            emirate=emirate.value,
            city=city,
            address_line=address_line,
            country=country,
            contact_email=contact_email.strip().lower(),
            contact_phone=contact_phone,
            website=website,
            year_established=year_established,
            employee_count=employee_count,
        )
        return self.add(organisation)
