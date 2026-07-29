"""The signed-in account's own organisation: read it, amend it.

Small on purpose. There is no create — an organisation is born with the account in
`AuthService.register`, because an account without one cannot appear on a listing card or an
applicant row — and no delete, because deleting the identity out from under published listings
and submitted bids is not an operation the portal offers.

Two rules justify a service rather than a repository call from the route:

* every read and write is scoped to the caller. `OrganisationRepository.get_for_owner` takes
  the user ID, so there is no lookup here that could be reached without one;
* `account_type` is immutable (`docs/09_PORTAL_SPEC.md` §2), and the non-nullable columns
  cannot be cleared by a `PATCH` that sends an explicit null.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.api.errors import NotFoundError, ValidationProblem
from app.core.logging import get_logger
from app.models.organisation import Organisation
from app.repositories.organisation_repository import OrganisationRepository
from app.schemas.organisation import OrganisationUpdate

logger = get_logger(__name__)

#: Set once and never by their owner: `account_type` is fixed at registration and cached on
#: this row precisely because it cannot change (`app/models/organisation.py`), `owner_user_id`
#: is the ownership boundary itself, and `is_verified` is an administrator's judgement.
#: `OrganisationUpdate` declares none of them and forbids extras, so today this guard cannot
#: fire — it exists so that adding one of these fields to the schema is a visible 422 rather
#: than a silently writable column.
IMMUTABLE_FIELDS = frozenset({"account_type", "owner_user_id", "is_verified"})

#: `NOT NULL` on `organisations`. `OrganisationUpdate` types them as optional so they may be
#: *omitted*, which makes an explicit `null` indistinguishable from "leave alone" at the schema
#: level. Rejecting it here turns what would be an IntegrityError at flush — a 500 — into a
#: precise 422 naming the field.
NON_NULLABLE_FIELDS = frozenset({"name", "description", "emirate", "country", "contact_email"})


class OrganisationService:
    def __init__(self, *, organisations: OrganisationRepository) -> None:
        self.organisations = organisations

    async def get_own(self, user_id: uuid.UUID) -> Organisation:
        """The caller's organisation.

        404 rather than an empty body: registration creates one, so its absence means either a
        pre-portal account or a bug, and both deserve to be visible.
        """
        organisation = await self.organisations.get_for_owner(user_id)
        if organisation is None:
            raise NotFoundError("No organisation exists for this account.")
        return organisation

    async def update_own(self, *, user_id: uuid.UUID, payload: OrganisationUpdate) -> Organisation:
        """Apply a partial update to the caller's own organisation.

        The row is fetched by owner, never by ID, so "update someone else's organisation" is
        not a request this service can express.
        """
        organisation = await self.get_own(user_id)
        # `exclude_unset` is what distinguishes "field absent" from "field explicitly null",
        # which is the whole point of PATCH — and the reason the null check below is needed.
        changes: dict[str, Any] = payload.model_dump(exclude_unset=True)

        self._reject_immutable(changes)
        self._reject_cleared_required(changes)
        self._normalise(changes, payload)

        for field, value in changes.items():
            setattr(organisation, field, value)

        await self.organisations.flush()
        logger.info(
            "organisation_updated",
            extra={"organisation_id": str(organisation.id), "fields_changed": len(changes)},
        )
        return organisation

    # --- Internals ---------------------------------------------------------------------

    def _reject_immutable(self, changes: dict[str, Any]) -> None:
        attempted = sorted(IMMUTABLE_FIELDS & changes.keys())
        if attempted:
            raise ValidationProblem(
                f"{', '.join(attempted)} cannot be changed after registration. "
                "An account's side of the marketplace is fixed, and verification is set by an "
                "administrator."
            )

    def _reject_cleared_required(self, changes: dict[str, Any]) -> None:
        cleared = sorted(
            field for field in NON_NULLABLE_FIELDS & changes.keys() if changes[field] is None
        )
        if cleared:
            raise ValidationProblem(
                f"{', '.join(cleared)} cannot be cleared. Omit the field to leave it unchanged."
            )

    def _normalise(self, changes: dict[str, Any], payload: OrganisationUpdate) -> None:
        """Convert the schema's rich types to what the columns actually store.

        `Emirate` is a vocabulary enum stored as its value (the column is a `String` with a
        CHECK constraint, not a database enum), and `HttpUrl`/`EmailStr` are objects that would
        be coerced to some repr on the way in. The email is lower-cased to match what
        `OrganisationRepository.create` writes, so a row does not change shape depending on
        whether it was last touched at registration or by an edit.
        """
        if changes.get("emirate") is not None and payload.emirate is not None:
            changes["emirate"] = payload.emirate.value
        if "website" in changes:
            changes["website"] = str(payload.website) if payload.website else None
        if changes.get("contact_email") is not None and payload.contact_email is not None:
            changes["contact_email"] = str(payload.contact_email).strip().lower()
