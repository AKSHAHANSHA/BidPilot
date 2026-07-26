"""An uploaded tender document.

The database row is the source of truth; the file on disk is content-addressed by a
server-generated storage key. The original filename is stored for display only and never
participates in any path.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.enums import DocumentExtractionStatus
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.tender import Tender


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        # A document cannot be attached to another user's tender — database-guaranteed.
        ForeignKeyConstraint(
            ["tender_id", "owner_user_id"],
            ["tenders.id", "tenders.owner_user_id"],
            name="fk_documents_tender_owner",
            ondelete="CASCADE",
        ),
        # SHA-256 duplicate detection is scoped to the tender: the same PDF may legitimately
        # appear on two different tenders, but uploading it twice to one is a mistake.
        UniqueConstraint("tender_id", "sha256", name="uq_documents_tender_sha256"),
        CheckConstraint(
            f"extraction_status IN ({DocumentExtractionStatus.sql_in_list()})",
            name="extraction_status",
        ),
        CheckConstraint("size_bytes > 0", name="size_positive"),
        Index("ix_documents_tender_owner", "tender_id", "owner_user_id"),
        Index("ix_documents_owner", "owner_user_id"),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    tender_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    #: Display only. Truncated, never trusted as a path component.
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    #: Server-generated, e.g. "8f0c...a1.pdf".
    stored_filename: Mapped[str] = mapped_column(String(80), nullable=False)
    #: Full key within the storage backend: "{user_id}/{tender_id}/{stored_filename}".
    storage_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Populated by Phase 4's extraction; null until then.
    page_count: Mapped[int | None] = mapped_column(Integer, default=None)
    extraction_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DocumentExtractionStatus.PENDING.value
    )

    tender: Mapped[Tender] = relationship(back_populates="documents")

    def __repr__(self) -> str:
        return f"<Document id={self.id} status={self.extraction_status}>"
