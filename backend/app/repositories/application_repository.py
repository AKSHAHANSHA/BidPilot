"""Application and screening persistence.

An application is reachable from *both* sides of the marketplace, and the two paths are not
symmetric. The vendor owns the row, so their reads go through `OwnedRepository` on
`vendor_user_id`. The buyer owns nothing here — their claim is on the *listing* — so every
buyer-facing read joins `tender_listings` and filters on `owner_user_id` there. That join is
the ownership boundary for the whole company side of the portal: without it, an application ID
from one buyer's listing would fetch another buyer's applicant.

Buyer-facing reads also exclude drafts. A draft is a bid the vendor has not sent yet, and it is
no more the buyer's business than an unpublished listing is a visitor's.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, nulls_last, or_, select
from sqlalchemy.orm import selectinload

from app.domain.enums import ApplicationStatus
from app.models.application import Application
from app.models.listing import TenderListing
from app.models.screening import ApplicationScreening
from app.repositories.base import BaseRepository, OwnedRepository


@dataclass(frozen=True, slots=True)
class VendorApplicationStats:
    """Raw aggregates behind `GET /applications/stats` (`docs/09` §6).

    Deliberately only the sums and counts SQL can produce. The derived ratios — `win_rate`,
    `margin_percentage` — stay in the service because both are undefined on a zero denominator
    and the spec says they must be null there, which is a presentation decision, not a query.
    """

    total: int
    #: Keyed by `ApplicationStatus` value; every member is present, zero included.
    counts_by_status: dict[str, int]
    #: `ApplicationStatus.open_states()` rolled up — the dashboard's "waiting" tile.
    waiting: int
    #: Sum of `bid_amount` over approved applications.
    total_bid_value: Decimal
    #: Sum of `bid_amount - estimated_cost` over approved applications that carry both figures.
    total_margin: Decimal
    #: Approved applications missing a figure the money tiles need. Surfaced so a partly-filled
    #: dashboard reads as partial rather than as a smaller business.
    incomplete_financials: int


class ApplicationRepository(OwnedRepository[Application]):
    model = Application
    owner_field = "vendor_user_id"

    @staticmethod
    def _vendor_detail_options() -> tuple[Any, ...]:
        """Everything the vendor's application detail page renders, in four extra queries."""
        return (
            selectinload(Application.documents),
            selectinload(Application.screening).selectinload(ApplicationScreening.findings),
            selectinload(Application.listing).selectinload(TenderListing.organisation),
        )

    @staticmethod
    def _applicant_options() -> tuple[Any, ...]:
        """Everything a buyer's applicant row shows. `estimated_cost` is never serialised into
        a buyer-facing schema (`docs/09` §10.8); that is the schema layer's job, not a reason to
        skip loading the row."""
        return (
            selectinload(Application.vendor_organisation),
            selectinload(Application.screening).selectinload(ApplicationScreening.findings),
        )

    @staticmethod
    def _submitted_only() -> Any:
        """Buyer visibility rule: a draft is not an applicant."""
        return Application.status != ApplicationStatus.DRAFT.value

    # ------------------------------------------------------------------
    # Vendor side
    # ------------------------------------------------------------------

    async def get_for_vendor(
        self, application_id: uuid.UUID, vendor_user_id: uuid.UUID
    ) -> Application | None:
        result = await self.session.execute(
            select(Application)
            .where(Application.id == application_id, self.owned_by(vendor_user_id))
            .options(*self._vendor_detail_options())
        )
        return result.scalar_one_or_none()

    async def list_for_vendor(
        self,
        vendor_user_id: uuid.UUID,
        *,
        status: ApplicationStatus | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[Application], int]:
        base = select(Application).where(self.owned_by(vendor_user_id))
        if status is not None:
            base = base.where(Application.status == status.value)

        total = int(
            (
                await self.session.execute(select(func.count()).select_from(base.subquery()))
            ).scalar_one()
        )
        rows = await self.session.execute(
            base.options(
                selectinload(Application.listing).selectinload(TenderListing.organisation),
                selectinload(Application.screening),
            )
            .order_by(Application.created_at.desc(), Application.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars().unique().all()), total

    async def get_by_listing_and_vendor(
        self, listing_id: uuid.UUID, vendor_user_id: uuid.UUID
    ) -> Application | None:
        """Backs the one-application-per-vendor-per-listing rule.

        The database already guarantees it with a unique constraint; this exists so the service
        can answer 409 with a useful message and a link to the existing application instead of
        turning an IntegrityError into a 500.
        """
        result = await self.session.execute(
            select(Application).where(
                Application.listing_id == listing_id, self.owned_by(vendor_user_id)
            )
        )
        return result.scalar_one_or_none()

    async def count_documents(self, application_id: uuid.UUID, vendor_user_id: uuid.UUID) -> int:
        """Used against `settings.max_application_documents` before accepting an upload."""
        result = await self.session.execute(
            select(func.count())
            .select_from(Application)
            .join(Application.documents)
            .where(Application.id == application_id, self.owned_by(vendor_user_id))
        )
        return int(result.scalar_one())

    async def vendor_stats(self, vendor_user_id: uuid.UUID) -> VendorApplicationStats:
        """Every dashboard number in one query.

        `FILTER` rather than seven round trips or a `GROUP BY` the service has to reassemble.
        The money aggregates lean on SQL's own NULL handling: `SUM` skips NULL inputs, and
        `bid_amount - estimated_cost` is NULL whenever either side is missing, which is exactly
        the §6 rule that an application missing a figure is excluded from that figure — with no
        Python filtering that could drift away from the count below it.
        """
        approved = Application.status == ApplicationStatus.APPROVED.value

        status_columns = [
            func.count().filter(Application.status == status.value).label(f"status_{status.value}")
            for status in ApplicationStatus
        ]

        row = (
            (
                await self.session.execute(
                    select(
                        func.count().label("total"),
                        *status_columns,
                        func.count()
                        .filter(
                            Application.status.in_(list(ApplicationStatus.open_states())),
                        )
                        .label("waiting"),
                        func.coalesce(func.sum(Application.bid_amount).filter(approved), 0).label(
                            "total_bid_value"
                        ),
                        func.coalesce(
                            func.sum(Application.bid_amount - Application.estimated_cost).filter(
                                approved
                            ),
                            0,
                        ).label("total_margin"),
                        func.count()
                        .filter(
                            and_(
                                approved,
                                or_(
                                    Application.bid_amount.is_(None),
                                    Application.estimated_cost.is_(None),
                                ),
                            )
                        )
                        .label("incomplete_financials"),
                    )
                    .select_from(Application)
                    .where(self.owned_by(vendor_user_id))
                )
            )
            .mappings()
            .one()
        )

        return VendorApplicationStats(
            total=int(row["total"]),
            counts_by_status={
                status.value: int(row[f"status_{status.value}"]) for status in ApplicationStatus
            },
            waiting=int(row["waiting"]),
            total_bid_value=Decimal(row["total_bid_value"]),
            total_margin=Decimal(row["total_margin"]),
            incomplete_financials=int(row["incomplete_financials"]),
        )

    # ------------------------------------------------------------------
    # Buyer side — reached through the listing, never by application ID alone
    # ------------------------------------------------------------------

    async def get_for_listing_owner(
        self, application_id: uuid.UUID, owner_user_id: uuid.UUID
    ) -> Application | None:
        """One applicant on a listing the caller owns.

        The join is the authorisation. An application ID belonging to somebody else's listing
        produces no row, and the API turns that into 404 rather than 403 — a buyer should not be
        able to probe which application IDs exist elsewhere in the marketplace.
        """
        result = await self.session.execute(
            select(Application)
            .join(TenderListing, TenderListing.id == Application.listing_id)
            .where(
                Application.id == application_id,
                TenderListing.owner_user_id == owner_user_id,
                self._submitted_only(),
            )
            .options(*self._applicant_options())
        )
        return result.scalar_one_or_none()

    async def list_for_listing(
        self,
        listing_id: uuid.UUID,
        owner_user_id: uuid.UUID,
        *,
        status: ApplicationStatus | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[Application], int]:
        """Applicants on one of the caller's listings, best screening score first.

        `NULLS LAST` puts unscored submissions — pending, processing, or failed screening —
        below every scored one instead of letting Postgres' default sort them to the top of a
        descending order, which would show the buyer an empty score as if it were the best.
        """
        base = (
            select(Application)
            .join(TenderListing, TenderListing.id == Application.listing_id)
            .where(
                Application.listing_id == listing_id,
                TenderListing.owner_user_id == owner_user_id,
                self._submitted_only(),
            )
        )
        if status is not None:
            base = base.where(Application.status == status.value)

        total = int(
            (
                await self.session.execute(select(func.count()).select_from(base.subquery()))
            ).scalar_one()
        )

        # The outer join exists only to order by a column on the child row; screening is unique
        # per application, so it cannot multiply rows.
        rows = await self.session.execute(
            base.outerjoin(
                ApplicationScreening, ApplicationScreening.application_id == Application.id
            )
            .options(*self._applicant_options())
            .order_by(
                nulls_last(ApplicationScreening.overall_score.desc()),
                nulls_last(Application.submitted_at.desc()),
                Application.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars().unique().all()), total


class ApplicationScreeningRepository(BaseRepository[ApplicationScreening]):
    """Screening reads for the pipeline.

    Not an `OwnedRepository`: `application_screenings` carries no user column, because a
    screening belongs to an application and is reachable from both the vendor who submitted it
    and the buyer who owns the listing. Both of those paths go through
    `ApplicationRepository`, which enforces the respective ownership and eager-loads the
    screening — so nothing here is an authorised entry point.

    These methods exist for the worker (`docs/09` §4), which runs from a screening ID with no
    request user at all. A route must not call them without first resolving the application
    through an ownership-checked read.
    """

    model = ApplicationScreening

    async def get_by_id(self, screening_id: uuid.UUID) -> ApplicationScreening | None:
        """The job's single load: findings, the submitted files, and the checklist to score
        them against. Fetching these lazily inside the pipeline would raise under asyncio."""
        result = await self.session.execute(
            select(ApplicationScreening)
            .where(ApplicationScreening.id == screening_id)
            .options(
                selectinload(ApplicationScreening.findings),
                selectinload(ApplicationScreening.application).selectinload(Application.documents),
                selectinload(ApplicationScreening.application)
                .selectinload(Application.listing)
                .selectinload(TenderListing.document_requirements),
            )
        )
        return result.scalar_one_or_none()

    async def get_for_application(self, application_id: uuid.UUID) -> ApplicationScreening | None:
        result = await self.session.execute(
            select(ApplicationScreening)
            .where(ApplicationScreening.application_id == application_id)
            .options(selectinload(ApplicationScreening.findings))
        )
        return result.scalar_one_or_none()
