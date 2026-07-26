"""One extracted PDF page — the provenance unit every citation refers to."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.document import Document


class DocumentPage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "document_pages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "owner_user_id"],
            ["documents.id", "documents.owner_user_id"],
            name="fk_document_pages_document_owner",
            ondelete="CASCADE",
        ),
        # One row per page; citation verification looks pages up by (document, number).
        UniqueConstraint("document_id", "page_number", name="uq_document_pages_number"),
        CheckConstraint("page_number >= 1", name="page_number_positive"),
        CheckConstraint("quality_score >= 0 AND quality_score <= 1", name="quality_range"),
        Index("ix_document_pages_document_owner", "document_id", "owner_user_id"),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    #: 1-based, exactly as a reader would cite it.
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Raw extracted text, preserved for the source viewer.
    text: Mapped[str] = mapped_column(Text, nullable=False)
    #: Whitespace/quote-normalized form used for search and citation matching (Phase 7).
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(16), nullable=False)

    document: Mapped[Document] = relationship(back_populates="pages")

    def __repr__(self) -> str:
        return f"<DocumentPage document_id={self.document_id} page={self.page_number}>"
