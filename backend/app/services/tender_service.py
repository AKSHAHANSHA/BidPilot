"""Tender and document orchestration, including the storage/database compensation logic."""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy.exc import IntegrityError

from app.api.errors import ConflictError, NotFoundError
from app.core.config import Settings
from app.core.logging import get_logger
from app.documents.extraction import extract_pdf_pages
from app.documents.validation import validate_pdf_upload
from app.domain.enums import DocumentExtractionStatus
from app.models.document import Document
from app.models.document_page import DocumentPage
from app.models.tender import Tender
from app.repositories.tender_repository import (
    DocumentRepository,
    TenderFilters,
    TenderRepository,
)
from app.schemas.tender import TenderCreate, TenderUpdate
from app.storage.base import StorageBackend

logger = get_logger(__name__)


class TenderService:
    def __init__(
        self,
        *,
        tenders: TenderRepository,
        documents: DocumentRepository,
        storage: StorageBackend,
        settings: Settings,
    ) -> None:
        self.tenders = tenders
        self.documents = documents
        self.storage = storage
        self.settings = settings

    # --- Tender CRUD ---------------------------------------------------------------------

    async def create_tender(self, *, user_id: uuid.UUID, payload: TenderCreate) -> Tender:
        tender = Tender(owner_user_id=user_id, **payload.model_dump())
        self.tenders.add(tender)
        await self.tenders.flush()
        logger.info("tender_created", extra={"tender_id": str(tender.id)})
        return tender

    async def get_tender(self, *, user_id: uuid.UUID, tender_id: uuid.UUID) -> Tender:
        tender = await self.tenders.get_for_user(tender_id, user_id)
        if tender is None:
            raise NotFoundError("Tender not found.")
        return tender

    async def list_tenders(
        self, *, user_id: uuid.UUID, filters: TenderFilters, limit: int, offset: int
    ) -> tuple[list[Tender], int]:
        return await self.tenders.list_filtered(user_id, filters, limit=limit, offset=offset)

    async def update_tender(
        self, *, user_id: uuid.UUID, tender_id: uuid.UUID, payload: TenderUpdate
    ) -> Tender:
        tender = await self.get_tender(user_id=user_id, tender_id=tender_id)
        changes = payload.model_dump(exclude_unset=True)
        if "status" in changes and payload.status is not None:
            changes["status"] = payload.status.value
        for field, value in changes.items():
            setattr(tender, field, value)
        await self.tenders.flush()
        logger.info("tender_updated", extra={"tender_id": str(tender.id)})
        return tender

    async def delete_tender(self, *, user_id: uuid.UUID, tender_id: uuid.UUID) -> None:
        """Delete the tender row (cascading to documents) and then its files, best effort.

        Order matters: the database is the source of truth, so the row goes first. A file
        whose row is gone is an orphan that wastes disk; a row whose file is gone is a broken
        document. Orphans are logged for cleanup, never surfaced as request failures.
        """
        tender = await self.get_tender(user_id=user_id, tender_id=tender_id)
        keys = await self.documents.storage_keys_for_tender(tender_id, user_id)
        await self.tenders.delete(tender)
        await self.tenders.flush()
        for key in keys:
            if not await self.storage.delete(key):
                logger.warning("orphan_file_cleanup_missed", extra={"storage_key": key})
        logger.info(
            "tender_deleted", extra={"tender_id": str(tender_id), "files_removed": len(keys)}
        )

    # --- Documents -------------------------------------------------------------------------

    async def upload_document(
        self,
        *,
        user_id: uuid.UUID,
        tender_id: uuid.UUID,
        content: bytes,
        original_filename: str | None,
    ) -> Document:
        """Validate, store, and record an uploaded PDF.

        Compensation: the file is written to storage first, then the row is flushed. If the
        flush fails, the file is deleted before the error propagates, so a failed request
        leaves neither half behind. (A crash between commit and response could still orphan a
        file; the database stays authoritative and orphans are harmless.)
        """
        tender = await self.get_tender(user_id=user_id, tender_id=tender_id)

        validated = validate_pdf_upload(
            content=content,
            original_filename=original_filename,
            max_bytes=self.settings.max_upload_bytes,
        )

        duplicate = await self.documents.find_duplicate(tender.id, user_id, validated.sha256)
        if duplicate is not None:
            raise ConflictError(
                f"This file is already attached to the tender as "
                f"'{duplicate.original_filename}' (identical SHA-256).",
                extra={"existing_document_id": str(duplicate.id)},
            )

        # Parse and extract before anything is persisted: a corrupt, encrypted, or oversized
        # PDF is rejected outright, leaving no file and no row. PyMuPDF is CPU-bound sync
        # code, so it runs in a worker thread rather than on the event loop.
        extraction = await asyncio.to_thread(
            extract_pdf_pages, validated.content, max_pages=self.settings.max_pdf_pages
        )

        stored_filename = f"{uuid.uuid4().hex}.pdf"
        storage_key = f"{user_id}/{tender.id}/{stored_filename}"

        await self.storage.save(storage_key, validated.content)

        status = (
            DocumentExtractionStatus.EXTRACTED
            if extraction.is_text_extractable
            else DocumentExtractionStatus.UNSUPPORTED
        )
        document = Document(
            owner_user_id=user_id,
            tender_id=tender.id,
            original_filename=validated.safe_original_filename,
            stored_filename=stored_filename,
            storage_key=storage_key,
            mime_type="application/pdf",
            size_bytes=validated.size_bytes,
            sha256=validated.sha256,
            page_count=extraction.page_count,
            extraction_status=status.value,
        )
        self.documents.add(document)
        try:
            # Flush before building pages: `id` carries a column default, so it is only
            # populated once the INSERT runs. Reading it earlier yields None and every page
            # row would violate the foreign key.
            await self.documents.flush()

            # Pages are stored even for an unsupported document so the UI can show *why* it is
            # unsupported (every page empty) rather than a bare status.
            for page in extraction.pages:
                self.documents.session.add(
                    DocumentPage(
                        owner_user_id=user_id,
                        document_id=document.id,
                        page_number=page.page_number,
                        text=page.text,
                        normalized_text=page.normalized_text,
                        character_count=page.character_count,
                        quality_score=page.quality_score,
                        extraction_method=page.extraction_method,
                    )
                )
            await self.documents.flush()
        except IntegrityError as exc:
            await self.storage.delete(storage_key)
            # Only the SHA constraint means "duplicate"; anything else is a genuine fault and
            # must not be disguised as a friendly 409.
            if "uq_documents_tender_sha256" in str(exc.orig):
                raise ConflictError(
                    "This file is already attached to the tender (identical SHA-256)."
                ) from exc
            raise
        except Exception:
            await self.storage.delete(storage_key)
            raise

        logger.info(
            "document_uploaded",
            extra={
                "document_id": str(document.id),
                "tender_id": str(tender.id),
                "size_bytes": document.size_bytes,
            },
        )
        return document

    async def get_document(self, *, user_id: uuid.UUID, document_id: uuid.UUID) -> Document:
        document = await self.documents.get_for_user(document_id, user_id)
        if document is None:
            raise NotFoundError("Document not found.")
        return document

    async def list_documents(self, *, user_id: uuid.UUID, tender_id: uuid.UUID) -> list[Document]:
        # 404 for a foreign/absent tender before listing, so the response cannot distinguish
        # "no documents" from "not your tender".
        await self.get_tender(user_id=user_id, tender_id=tender_id)
        return await self.documents.list_for_tender(tender_id, user_id)

    async def list_pages(self, *, user_id: uuid.UUID, document_id: uuid.UUID) -> list[DocumentPage]:
        await self.get_document(user_id=user_id, document_id=document_id)
        return await self.documents.list_pages(document_id, user_id)

    async def get_page(
        self, *, user_id: uuid.UUID, document_id: uuid.UUID, page_number: int
    ) -> DocumentPage:
        await self.get_document(user_id=user_id, document_id=document_id)
        page = await self.documents.get_page(document_id, user_id, page_number)
        if page is None:
            raise NotFoundError(f"Page {page_number} does not exist on this document.")
        return page

    async def delete_document(self, *, user_id: uuid.UUID, document_id: uuid.UUID) -> None:
        document = await self.get_document(user_id=user_id, document_id=document_id)
        storage_key = document.storage_key
        await self.documents.delete(document)
        await self.documents.flush()
        if not await self.storage.delete(storage_key):
            logger.warning("orphan_file_cleanup_missed", extra={"storage_key": storage_key})
        logger.info("document_deleted", extra={"document_id": str(document_id)})
