"""Notifications for the signed-in account (`docs/09_PORTAL_SPEC.md` §3.5).

Read-only plus two acknowledgements. Rows are written by the services that cause them — a
submission, a screening result, a decision, a closure — never by a client, so there is no
create or delete route and no write schema.

The recipient is in the `WHERE` clause of every query, not checked afterwards, which is why
marking somebody else's notification read is indistinguishable from marking a missing one: both
are 404, and neither confirms that the notification exists.
"""

from __future__ import annotations

import uuid
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.api.dependencies import CurrentUser, NotificationServiceDep
from app.api.errors import ProblemDetail
from app.schemas.common import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, Page
from app.schemas.notification import NotificationCounts, NotificationRead

router = APIRouter(prefix="/notifications", tags=["notifications"])

_AUTHENTICATED: dict[int | str, dict[str, object]] = {
    HTTPStatus.UNAUTHORIZED: {"model": ProblemDetail},
}

NotificationId = Annotated[uuid.UUID, Path(description="Notification identifier.")]
Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT, description="Rows per page.")]
Offset = Annotated[int, Query(ge=0, description="Rows to skip.")]


@router.get(
    "",
    response_model=Page[NotificationRead],
    summary="List your notifications",
    description="Newest first. Set `unread_only` to show only what is still waiting.",
    responses=_AUTHENTICATED,
)
async def list_notifications(
    current_user: CurrentUser,
    service: NotificationServiceDep,
    unread_only: Annotated[bool, Query(description="Return only unread notifications.")] = False,
    limit: Limit = DEFAULT_PAGE_LIMIT,
    offset: Offset = 0,
) -> Page[NotificationRead]:
    items, total = await service.list_notifications(
        user_id=current_user.id, unread_only=unread_only, limit=limit, offset=offset
    )
    return Page[NotificationRead].build(
        [NotificationRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/counts",
    response_model=NotificationCounts,
    summary="Unread and total counts for the header badge",
    description=(
        "Two numbers rather than one so the badge can say '3 of 40' without pulling a page of "
        "rows it is not going to render."
    ),
    responses=_AUTHENTICATED,
)
async def get_notification_counts(
    current_user: CurrentUser, service: NotificationServiceDep
) -> NotificationCounts:
    return await service.counts(user_id=current_user.id)


@router.post(
    "/read-all",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark every notification read",
    description="Idempotent. Only notifications belonging to the signed-in account are touched.",
    responses=_AUTHENTICATED,
)
async def mark_all_read(current_user: CurrentUser, service: NotificationServiceDep) -> None:
    await service.mark_all_read(user_id=current_user.id)


@router.post(
    "/{notification_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark one notification read",
    description=(
        "Idempotent: a second call succeeds and keeps the original read timestamp. A "
        "notification belonging to another account answers 404, exactly as a missing one does."
    ),
    responses={**_AUTHENTICATED, HTTPStatus.NOT_FOUND: {"model": ProblemDetail}},
)
async def mark_notification_read(
    notification_id: NotificationId,
    current_user: CurrentUser,
    service: NotificationServiceDep,
) -> None:
    await service.mark_read(user_id=current_user.id, notification_id=notification_id)
