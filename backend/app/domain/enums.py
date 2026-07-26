"""Controlled vocabularies shared by models, schemas, and database check constraints.

These enums are the single source of truth. Migration check constraints are written from the
`values()` helpers so a constraint and its enum cannot silently drift apart.

Extending a vocabulary therefore needs a small migration. That is a deliberate trade-off: a
typo'd category would quietly hide a piece of evidence from every filter and from future
requirement matching, which is worse than one `ALTER TABLE`.
"""

from __future__ import annotations

from enum import StrEnum


class VocabularyEnum(StrEnum):
    """Base class providing the value list used to build check constraints."""

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(member.value for member in cls)

    @classmethod
    def sql_in_list(cls) -> str:
        """Render as a SQL literal list for a CHECK constraint."""
        return ", ".join(f"'{value}'" for value in cls.values())


class Emirate(VocabularyEnum):
    """The seven emirates. Fixed by geography, so a check constraint is safe here."""

    ABU_DHABI = "abu_dhabi"
    DUBAI = "dubai"
    SHARJAH = "sharjah"
    AJMAN = "ajman"
    UMM_AL_QUWAIN = "umm_al_quwain"
    RAS_AL_KHAIMAH = "ras_al_khaimah"
    FUJAIRAH = "fujairah"


class EvidenceCategory(VocabularyEnum):
    """What kind of claim a piece of evidence supports."""

    TRADE_LICENCE = "trade_licence"
    CERTIFICATION = "certification"
    INSURANCE = "insurance"
    FINANCIAL_STATEMENT = "financial_statement"
    PREVIOUS_PROJECT = "previous_project"
    CLIENT_REFERENCE = "client_reference"
    STAFF_CV = "staff_cv"
    TECHNICAL_CAPABILITY = "technical_capability"
    EQUIPMENT_ASSET = "equipment_asset"
    POLICY = "policy"
    REGISTRATION = "registration"
    OTHER = "other"


class VerificationStatus(VocabularyEnum):
    """Whether the user has confirmed this evidence themselves.

    Only `verified` evidence may be treated as approved when matching tender requirements
    (`docs/03_AI_PIPELINE_AND_SCORING.md` §8).
    """

    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    REJECTED = "rejected"


class ExpiryState(VocabularyEnum):
    """Derived, never stored — see `app.domain.expiry`."""

    ACTIVE = "active"
    EXPIRING_SOON = "expiring_soon"
    EXPIRED = "expired"
    NO_EXPIRY = "no_expiry"
    UNVERIFIED = "unverified"


class ProjectStatus(VocabularyEnum):
    COMPLETED = "completed"
    CURRENT = "current"


class TenderStatus(VocabularyEnum):
    """Lifecycle of the tender record itself.

    Deliberately small: analysis progress and the bid/no-bid decision are properties of an
    Analysis (Phase 5+), not of the tender. Mixing them here would duplicate state.
    """

    ACTIVE = "active"
    ARCHIVED = "archived"


class DocumentExtractionStatus(VocabularyEnum):
    """Where an uploaded document sits in the extraction pipeline (Phase 4 populates it)."""

    PENDING = "pending"
    EXTRACTED = "extracted"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


class RevenueRange(VocabularyEnum):
    """Coarse bands. A band is easier for a user to disclose than an exact figure, and precise
    enough for the contract-size sanity checks in later phases."""

    UNDER_1M = "under_1m_aed"
    FROM_1M_TO_5M = "1m_to_5m_aed"
    FROM_5M_TO_20M = "5m_to_20m_aed"
    FROM_20M_TO_50M = "20m_to_50m_aed"
    OVER_50M = "over_50m_aed"
