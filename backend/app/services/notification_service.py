"""In-app notifications: recipient-scoped reads, and the writers for every event in `docs/09` §9.

Two halves with different shapes, for a reason.

The reads are `async` and go through `NotificationRepository`, which puts the recipient in the
`WHERE` clause of every statement — including the writes that mark rows read.

The emitters are **synchronous** and only *stage* rows. A notification is a statement that
something happened, so it belongs to the same unit of work as the thing that happened: if the
submission rolls back, the buyer must not be left holding a message about an application that
does not exist. Making them `async def` would invite a caller to commit between the event and
its notification, which is exactly the split we are avoiding.

Emitters take identifiers and a title rather than ORM rows. Under async SQLAlchemy an unloaded
relationship raises when touched, so an emitter that reached for `application.listing.title`
would fail — occasionally, and only for callers who happened not to eager-load it. Scalars in
means an emitter cannot fail that way at all.

Wording rules, from `CLAUDE.md` and `docs/09` §10.6: plain human sentences, never raw document
text, and a message about an unmatched document says what was searched rather than asserting
that the vendor does not hold it.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from app.api.errors import NotFoundError
from app.core.logging import get_logger
from app.domain.enums import ApplicationStatus, NotificationType
from app.models.notification import Notification
from app.repositories.notification_repository import NotificationDraft, NotificationRepository
from app.schemas.notification import NotificationCounts

logger = get_logger(__name__)

#: `notifications.title` is `String(255)`. A listing title is itself up to 255 characters, so
#: every title built from one has to be shortened or the insert fails at commit — turning a
#: successful submission into a 500 because somebody named their tender verbosely.
MAX_TITLE_LENGTH = 255
#: How much of that budget a quoted listing title may spend, leaving room for the surrounding
#: sentence in every template below.
MAX_SUBJECT_LENGTH = 120

#: The sentence that must accompany any statement that a document was not found
#: (`CLAUDE.md`: "Not found" does not prove non-existence). Worded to suit both audiences: the
#: buyer reading an applicant's result and the vendor reading their own.
NOT_PROOF_OF_ABSENCE = (
    "This reflects what was supplied with the application, not proof that the documents "
    "do not exist."
)

#: The three outcomes a buyer may set (`docs/09` §3.3), each with the sentence the vendor reads.
#: A table rather than an `if` chain so the guard below can prove it is exhaustive.
_DECISION_WORDING: dict[ApplicationStatus, tuple[str, str]] = {
    ApplicationStatus.SHORTLISTED: (
        "shortlisted",
        'Your application to "{subject}" has been shortlisted. The buyer has not made a final '
        "decision yet.",
    ),
    ApplicationStatus.APPROVED: (
        "approved",
        'Your application to "{subject}" has been approved.',
    ),
    ApplicationStatus.REJECTED: (
        "not successful",
        'Your application to "{subject}" was not successful.',
    ),
}

if set(_DECISION_WORDING) != {
    ApplicationStatus.SHORTLISTED,
    ApplicationStatus.APPROVED,
    ApplicationStatus.REJECTED,
}:  # pragma: no cover - configuration guard
    raise RuntimeError(
        "_DECISION_WORDING must cover exactly the statuses a buyer may set. A decision with no "
        "wording would reach the vendor as an empty notification."
    )


@dataclass(frozen=True, slots=True)
class ApplicantRef:
    """One recipient of a listing-wide fan-out, and the application to link them back to.

    Deliberately not the `Application` row: the closing job iterates applicants, and a
    dataclass makes it obvious that the only two things a notification needs from each are an
    addressee and a deep-link target.
    """

    vendor_user_id: uuid.UUID
    application_id: uuid.UUID


def _shorten(value: str, limit: int) -> str:
    """Collapse whitespace and cut to `limit`, so a long title cannot overflow the column."""
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _title(text: str) -> str:
    # Belt and braces: every template below already fits, but a title that silently exceeded the
    # column would surface as an IntegrityError on an unrelated commit.
    return _shorten(text, MAX_TITLE_LENGTH)


def _score_sentence(score: int | None, *, subject: str, audience: str) -> str:
    """One sentence stating the outcome, or stating honestly that there is no number.

    `score is None` means the checklist held nothing to assess (`app/domain/screening.py`). It is
    never rendered as zero: "scored 0" reads as a damning result about a vendor who was asked
    for nothing.
    """
    if score is None:
        return (
            f'{audience} to "{subject}" has been screened. No score was produced, because the '
            "checklist for this listing had no requirements to assess."
        )
    return f'{audience} to "{subject}" has been screened and scored {score} out of 100.'


class NotificationService:
    def __init__(self, *, notifications: NotificationRepository) -> None:
        self.notifications = notifications

    # --- Reads ---------------------------------------------------------------------------

    async def list_notifications(
        self,
        *,
        user_id: uuid.UUID,
        unread_only: bool = False,
        limit: int,
        offset: int,
    ) -> tuple[list[Notification], int]:
        return await self.notifications.list_for_recipient(
            user_id, unread_only=unread_only, limit=limit, offset=offset
        )

    async def unread_count(self, *, user_id: uuid.UUID) -> int:
        return await self.notifications.unread_count(user_id)

    async def counts(self, *, user_id: uuid.UUID) -> NotificationCounts:
        """The header badge. Two counts rather than one, so the UI can say "3 of 40"."""
        return NotificationCounts(
            unread=await self.notifications.unread_count(user_id),
            total=await self.notifications.count_for_user(user_id),
        )

    async def mark_read(self, *, user_id: uuid.UUID, notification_id: uuid.UUID) -> None:
        """Idempotent: a second call on an already-read notification still succeeds.

        A 404 here means "not yours or not there" — the repository puts the recipient in the
        `WHERE` clause, so a stranger's notification is indistinguishable from a missing one.
        """
        if not await self.notifications.mark_read(notification_id, user_id):
            raise NotFoundError("Notification not found.")

    async def mark_all_read(self, *, user_id: uuid.UUID) -> int:
        """Clear the badge. Returns how many were still unread."""
        return await self.notifications.mark_all_read(user_id)

    # --- Emitters ------------------------------------------------------------------------
    #
    # Synchronous and staging-only. The caller's commit is what makes any of these real.

    def _emit(self, draft: NotificationDraft) -> Notification:
        notification = self.notifications.create(draft)
        logger.info(
            "notification_staged",
            extra={
                # The body is deliberately absent: it quotes a listing title and, for a
                # decision, the buyer's own words.
                "notification_type": draft.notification_type.value,
                "recipient_user_id": str(draft.recipient_user_id),
                "application_id": str(draft.application_id) if draft.application_id else None,
            },
        )
        return notification

    def application_received(
        self,
        *,
        owner_user_id: uuid.UUID,
        listing_id: uuid.UUID,
        listing_title: str,
        application_id: uuid.UUID,
    ) -> Notification:
        """A vendor submitted. Addressed to the listing's owner (`docs/09` §9).

        The applicant is not named: the buyer is one click from the applicant list, and putting
        a vendor's identity in a notification body means it survives in a place no ownership
        check ever looks at again.
        """
        subject = _shorten(listing_title, MAX_SUBJECT_LENGTH)
        return self._emit(
            NotificationDraft(
                recipient_user_id=owner_user_id,
                notification_type=NotificationType.APPLICATION_RECEIVED,
                title=_title(f'New application for "{subject}"'),
                body=(
                    f'A vendor has submitted an application to your listing "{subject}". '
                    "Document screening starts automatically; you will be notified when it "
                    "finishes."
                ),
                listing_id=listing_id,
                application_id=application_id,
            )
        )

    def screening_completed(
        self,
        *,
        owner_user_id: uuid.UUID,
        vendor_user_id: uuid.UUID,
        listing_id: uuid.UUID,
        listing_title: str,
        application_id: uuid.UUID,
        score: int | None,
        has_blocking_gap: bool,
    ) -> list[Notification]:
        """Both halves of the §9 row: the buyer (with the score) and the vendor.

        Written together because they describe one event. Emitting them from two call sites
        would eventually mean one of them is forgotten for one status transition.
        """
        subject = _shorten(listing_title, MAX_SUBJECT_LENGTH)
        gap_note = (
            f" One or more mandatory documents were not matched. {NOT_PROOF_OF_ABSENCE}"
            if has_blocking_gap
            else ""
        )

        buyer = self._emit(
            NotificationDraft(
                recipient_user_id=owner_user_id,
                notification_type=NotificationType.SCREENING_COMPLETED,
                title=_title(f'Screening complete for an applicant on "{subject}"'),
                body=_score_sentence(score, subject=subject, audience="An application") + gap_note,
                listing_id=listing_id,
                application_id=application_id,
                screening_score=score,
            )
        )
        vendor = self._emit(
            NotificationDraft(
                recipient_user_id=vendor_user_id,
                notification_type=NotificationType.SCREENING_COMPLETED,
                title=_title(f'Your application to "{subject}" has been screened'),
                body=_score_sentence(score, subject=subject, audience="Your application")
                + gap_note
                + " Open the screening result to see every requirement and what was searched "
                "for.",
                listing_id=listing_id,
                application_id=application_id,
                # The vendor is entitled to their own score; §9 only calls it out for the buyer
                # because it is the column their applicant list reads.
                screening_score=score,
            )
        )
        return [buyer, vendor]

    def screening_failed(
        self,
        *,
        vendor_user_id: uuid.UUID,
        listing_id: uuid.UUID,
        listing_title: str,
        application_id: uuid.UUID,
    ) -> Notification:
        """Screening could not finish. Only the vendor is told, and told plainly.

        The buyer is not notified: a failed run says nothing about the submission, and a message
        implying otherwise would prejudice an applicant for our fault.
        """
        subject = _shorten(listing_title, MAX_SUBJECT_LENGTH)
        return self._emit(
            NotificationDraft(
                recipient_user_id=vendor_user_id,
                notification_type=NotificationType.SCREENING_FAILED,
                title=_title(f'Screening could not be completed for "{subject}"'),
                body=(
                    f'Document screening for your application to "{subject}" did not finish, so '
                    "nothing about your documents has been judged. Submitting the application "
                    "again will start a fresh screening."
                ),
                listing_id=listing_id,
                application_id=application_id,
            )
        )

    def application_status_changed(
        self,
        *,
        vendor_user_id: uuid.UUID,
        listing_id: uuid.UUID,
        listing_title: str,
        application_id: uuid.UUID,
        status: ApplicationStatus,
        note: str | None = None,
    ) -> Notification:
        """The buyer decided. `note` is their own wording and is quoted verbatim."""
        wording = _DECISION_WORDING.get(status)
        if wording is None:
            raise ValueError(
                f"{status.value} is not a buyer decision; only "
                f"{', '.join(sorted(s.value for s in _DECISION_WORDING))} notify the vendor."
            )
        label, template = wording
        subject = _shorten(listing_title, MAX_SUBJECT_LENGTH)
        body = template.format(subject=subject)
        if note:
            body = f"{body} The buyer added: {note}"
        return self._emit(
            NotificationDraft(
                recipient_user_id=vendor_user_id,
                notification_type=NotificationType.APPLICATION_STATUS_CHANGED,
                title=_title(f'Your application to "{subject}" is {label}'),
                body=body,
                listing_id=listing_id,
                application_id=application_id,
            )
        )

    def listing_closed(
        self,
        *,
        listing_id: uuid.UUID,
        listing_title: str,
        applicants: Sequence[ApplicantRef],
    ) -> list[Notification]:
        """One message per applicant, staged as a single batch.

        `create_many` builds the whole set in one unit of work, so the closing job issues one
        flush for a listing with fifty bidders rather than fifty round trips. Callers pass only
        the applicants who actually applied — a draft was never sent, and a withdrawn
        application is no longer waiting on this listing.
        """
        if not applicants:
            return []
        subject = _shorten(listing_title, MAX_SUBJECT_LENGTH)
        title = _title(f'Applications have closed for "{subject}"')
        body = (
            f'The submission window for "{subject}" has closed. The buyer is reviewing the '
            "applications they received; you will be notified when yours is decided."
        )
        notifications = self.notifications.create_many(
            [
                NotificationDraft(
                    recipient_user_id=applicant.vendor_user_id,
                    notification_type=NotificationType.LISTING_CLOSED,
                    title=title,
                    body=body,
                    listing_id=listing_id,
                    application_id=applicant.application_id,
                )
                for applicant in applicants
            ]
        )
        logger.info(
            "notification_fanout_staged",
            extra={
                "notification_type": NotificationType.LISTING_CLOSED.value,
                "listing_id": str(listing_id),
                "recipients": len(notifications),
            },
        )
        return notifications
