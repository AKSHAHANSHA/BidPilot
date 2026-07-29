"""The certificate register screening checks an uploaded certificate against.

Stands in for what would, in a real deployment, be a lookup against the issuing body's public
register (IAS, ENAS, UKAS and so on). The point of the table is the *check*: a vendor can put
any number on a PDF, so a certificate is worth only as much as the register that confirms it.

Rows are reference data, not user data. Nothing here belongs to an account, nothing is created
through the API, and the whole table is world-readable within the application — it is the
public part of somebody else's register, reproduced locally so screening can run offline.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import CheckConstraint, Date, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.domain.enums import CertificateStatus
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class CertificateRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "certificate_registry"
    __table_args__ = (
        CheckConstraint(f"status IN ({CertificateStatus.sql_in_list()})", name="status"),
        CheckConstraint(
            "expires_on IS NULL OR issued_on IS NULL OR issued_on <= expires_on",
            name="issue_before_expiry",
        ),
        # Screening looks up exactly one thing: a normalised number. Everything else on this
        # table is for display once the row has been found.
        Index("ix_certificate_registry_standard", "standard"),
    )

    #: Normalised at write time — upper-cased, punctuation stripped — so a lookup never has to
    #: guess how the vendor's PDF happened to punctuate it. `app.domain.certificates` owns the
    #: normalisation and both sides must use it.
    certificate_number: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    #: The number exactly as the issuing body prints it, for display back to the user.
    display_number: Mapped[str] = mapped_column(String(80), nullable=False)

    standard: Mapped[str] = mapped_column(String(40), nullable=False)
    issued_to: Mapped[str] = mapped_column(String(255), nullable=False)
    issuing_body: Mapped[str] = mapped_column(String(160), nullable=False)
    scope: Mapped[str | None] = mapped_column(String(400), default=None)

    issued_on: Mapped[date | None] = mapped_column(Date, default=None)
    expires_on: Mapped[date | None] = mapped_column(Date, default=None)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=CertificateStatus.ACTIVE.value
    )

    def is_expired(self, *, today: date | None = None) -> bool:
        """Derived from the date rather than trusted from `status`.

        A register that is refreshed nightly will always contain rows whose stored status has
        not caught up with their expiry date. The date is the fact; the status is a summary.
        """
        if self.expires_on is None:
            return False
        return self.expires_on < (today or datetime.now(tz=UTC).date())

    @property
    def is_usable(self) -> bool:
        return self.status == CertificateStatus.ACTIVE.value and not self.is_expired()

    def __repr__(self) -> str:
        return f"<CertificateRecord {self.display_number} status={self.status}>"
