"""Tender and document endpoints (`docs/04_API_AND_DATA_MODEL.md` §3)."""

from __future__ import annotations

import uuid
from datetime import datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Path, Query, UploadFile, status

from app.api.dependencies import CurrentUser, TenderServiceDep
from app.api.errors import ProblemDetail
from app.domain.enums import TenderStatus
from app.models.document import Document
from app.models.tender import Tender
from app.repositories.tender_repository import TenderFilters
from app.schemas.common import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, Page
from app.schemas.tender import DocumentRead, TenderCreate, TenderRead, TenderUpdate

router = APIRouter(tags=["tenders"])

_OWNED: dict[int | str, dict[str, object]] = {
    HTTPStatus.UNAUTHORIZED: {"model": ProblemDetail},
    HTTPStatus.NOT_FOUND: {"model": ProblemDetail},
}

TenderId = Annotated[uuid.UUID, Path(description="Tender identifier.")]
DocumentId = Annotated[uuid.UUID, Path(description="Document identifier.")]
Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)]
Offset = Annotated[int, Query(ge=0)]


def _tender_read(tender: Tender, *, document_count: int = 0) -> TenderRead:
    read = TenderRead.model_validate(tender)
    read.document_count = document_count
    return read


def _document_read(document: Document) -> DocumentRead:
    return DocumentRead.model_validate(document)


@router.post(
    "/tenders",
    response_model=TenderRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a tender project",
    responses={HTTPStatus.UNAUTHORIZED: {"model": ProblemDetail}},
)
async def create_tender(
    payload: TenderCreate, current_user: CurrentUser, service: TenderServiceDep
) -> TenderRead:
    tender = await service.create_tender(user_id=current_user.id, payload=payload)
    return _tender_read(tender)


@router.get(
    "/tenders",
    response_model=Page[TenderRead],
    summary="List tenders",
    responses={HTTPStatus.UNAUTHORIZED: {"model": ProblemDetail}},
)
async def list_tenders(
    current_user: CurrentUser,
    service: TenderServiceDep,
    tender_status: Annotated[TenderStatus | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    deadline_before: Annotated[datetime | None, Query()] = None,
    deadline_after: Annotated[datetime | None, Query()] = None,
    limit: Limit = DEFAULT_PAGE_LIMIT,
    offset: Offset = 0,
) -> Page[TenderRead]:
    items, total = await service.list_tenders(
        user_id=current_user.id,
        filters=TenderFilters(
            status=tender_status,
            search=search,
            deadline_before=deadline_before,
            deadline_after=deadline_after,
        ),
        limit=limit,
        offset=offset,
    )
    return Page[TenderRead].build(
        [_tender_read(t) for t in items], total=total, limit=limit, offset=offset
    )


@router.get(
    "/tenders/{tender_id}",
    response_model=TenderRead,
    summary="Get a tender",
    responses=_OWNED,
)
async def get_tender(
    tender_id: TenderId, current_user: CurrentUser, service: TenderServiceDep
) -> TenderRead:
    tender = await service.get_tender(user_id=current_user.id, tender_id=tender_id)
    documents = await service.list_documents(user_id=current_user.id, tender_id=tender_id)
    return _tender_read(tender, document_count=len(documents))


@router.patch(
    "/tenders/{tender_id}",
    response_model=TenderRead,
    summary="Update a tender",
    responses=_OWNED,
)
async def update_tender(
    tender_id: TenderId,
    payload: TenderUpdate,
    current_user: CurrentUser,
    service: TenderServiceDep,
) -> TenderRead:
    tender = await service.update_tender(
        user_id=current_user.id, tender_id=tender_id, payload=payload
    )
    return _tender_read(tender)


@router.delete(
    "/tenders/{tender_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a tender",
    description="Irreversible. Removes the tender, its documents, and their stored files.",
    responses=_OWNED,
)
async def delete_tender(
    tender_id: TenderId, current_user: CurrentUser, service: TenderServiceDep
) -> None:
    await service.delete_tender(user_id=current_user.id, tender_id=tender_id)


# --- Documents --------------------------------------------------------------------------


@router.post(
    "/tenders/{tender_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a tender PDF",
    description=(
        "Multipart upload. The file must be a PDF by content (magic bytes), not just by name; "
        "size is bounded; an identical file (SHA-256) on the same tender returns 409. Storage "
        "paths are generated server-side — the client filename is display-only."
    ),
    responses={
        **_OWNED,
        HTTPStatus.CONFLICT: {"model": ProblemDetail},
        HTTPStatus.REQUEST_ENTITY_TOO_LARGE: {"model": ProblemDetail},
        HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ProblemDetail},
    },
)
async def upload_document(
    tender_id: TenderId,
    file: UploadFile,
    current_user: CurrentUser,
    service: TenderServiceDep,
) -> DocumentRead:
    content = await file.read()
    document = await service.upload_document(
        user_id=current_user.id,
        tender_id=tender_id,
        content=content,
        original_filename=file.filename,
    )
    return _document_read(document)


@router.get(
    "/tenders/{tender_id}/documents",
    response_model=list[DocumentRead],
    summary="List a tender's documents",
    responses=_OWNED,
)
async def list_documents(
    tender_id: TenderId, current_user: CurrentUser, service: TenderServiceDep
) -> list[DocumentRead]:
    documents = await service.list_documents(user_id=current_user.id, tender_id=tender_id)
    return [_document_read(d) for d in documents]


@router.get(
    "/documents/{document_id}",
    response_model=DocumentRead,
    summary="Get a document record",
    responses=_OWNED,
)
async def get_document(
    document_id: DocumentId, current_user: CurrentUser, service: TenderServiceDep
) -> DocumentRead:
    document = await service.get_document(user_id=current_user.id, document_id=document_id)
    return _document_read(document)


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document",
    responses=_OWNED,
)
async def delete_document(
    document_id: DocumentId, current_user: CurrentUser, service: TenderServiceDep
) -> None:
    await service.delete_document(user_id=current_user.id, document_id=document_id)
