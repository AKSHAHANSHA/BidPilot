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


class AnalysisStatus(VocabularyEnum):
    """Coarse lifecycle of an analysis job. `current_stage` carries the fine-grained detail."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AnalysisStage(VocabularyEnum):
    """Fine-grained pipeline position (`docs/02_BACKEND_ARCHITECTURE.md` §6).

    The full progression is fixed now so the persisted vocabulary is stable; phases 6-9 fill in
    the handlers for the stages between quality assessment and report generation. A stage the
    pipeline has not reached yet is simply never written — no fake progress.
    """

    QUEUED = "queued"
    VALIDATING = "validating"
    EXTRACTING_TEXT = "extracting_text"
    ASSESSING_QUALITY = "assessing_quality"
    EXTRACTING_METADATA = "extracting_metadata"
    EXTRACTING_REQUIREMENTS = "extracting_requirements"
    VERIFYING_CITATIONS = "verifying_citations"
    MATCHING_EVIDENCE = "matching_evidence"
    ANALYSING_RISKS = "analysing_risks"
    SCORING = "scoring"
    GENERATING_REPORT = "generating_report"
    COMPLETED = "completed"


class RequirementCategory(VocabularyEnum):
    """Requirement taxonomy (`docs/01_PRODUCT_REQUIREMENTS.md` §5)."""

    LEGAL_REGISTRATION = "legal_registration"
    CERTIFICATION = "certification"
    TECHNICAL_CAPABILITY = "technical_capability"
    EXPERIENCE = "experience"
    STAFFING = "staffing"
    FINANCIAL = "financial"
    INSURANCE = "insurance"
    BID_BOND_GUARANTEE = "bid_bond_guarantee"
    SUBMISSION_INSTRUCTION = "submission_instruction"
    DEADLINE = "deadline"
    COMMERCIAL = "commercial"
    CONTRACTUAL = "contractual"
    HEALTH_SAFETY_ENVIRONMENT = "health_safety_environment"
    DATA_CYBERSECURITY = "data_cybersecurity"
    OTHER = "other"


class RequirementObligation(VocabularyEnum):
    MANDATORY = "mandatory"
    OPTIONAL = "optional"
    UNCERTAIN = "uncertain"


class ComplianceStatus(VocabularyEnum):
    """Machine or human compliance verdict (`docs/01` §5)."""

    UNREVIEWED = "unreviewed"
    MET = "met"
    PARTIALLY_MET = "partially_met"
    NOT_MET = "not_met"
    NEEDS_CLARIFICATION = "needs_clarification"
    NOT_APPLICABLE = "not_applicable"


class CitationMatchMethod(VocabularyEnum):
    """How a citation quote was verified against its source page (Phase 7)."""

    EXACT = "exact"
    NORMALIZED = "normalized"
    FUZZY = "fuzzy"
    UNVERIFIED = "unverified"
    REJECTED = "rejected"


class RiskType(VocabularyEnum):
    """Risk-clause taxonomy (`docs/01` §5)."""

    LIQUIDATED_DAMAGES = "liquidated_damages"
    INDEMNITY_LIABILITY = "indemnity_liability"
    TERMINATION = "termination"
    PAYMENT_TERMS = "payment_terms"
    PERFORMANCE_GUARANTEE = "performance_guarantee"
    BID_BOND = "bid_bond"
    INSURANCE = "insurance"
    DATA_PRIVACY = "data_privacy"
    INTELLECTUAL_PROPERTY = "intellectual_property"
    UNCLEAR_SCOPE = "unclear_scope"
    AGGRESSIVE_DEADLINE = "aggressive_deadline"
    OTHER = "other"


class RiskSeverity(VocabularyEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DecisionLabel(VocabularyEnum):
    """Overall bid recommendation (`docs/03` §13). Hard blockers can override the numeric band."""

    STRONG_BID = "strong_bid"
    CONDITIONAL_BID = "conditional_bid"
    WEAK_BID = "weak_bid"
    DO_NOT_BID = "do_not_bid"
    INSUFFICIENT_INFORMATION = "insufficient_information"


class MatchStatus(VocabularyEnum):
    """Evidence-match verdict. Absence is `needs_clarification`/`not_met`, never proof of a gap
    (`docs/03` §9)."""

    MET = "met"
    PARTIALLY_MET = "partially_met"
    NOT_MET = "not_met"
    NEEDS_CLARIFICATION = "needs_clarification"
    NOT_APPLICABLE = "not_applicable"


class AnalysisErrorCode(VocabularyEnum):
    """Safe, machine-readable failure reason. Developer detail lives in logs only."""

    FAILED_VALIDATION = "failed_validation"
    FAILED_EXTRACTION = "failed_extraction"
    FAILED_AI = "failed_ai"
    FAILED_INTERNAL = "failed_internal"


class RevenueRange(VocabularyEnum):
    """Coarse bands. A band is easier for a user to disclose than an exact figure, and precise
    enough for the contract-size sanity checks in later phases."""

    UNDER_1M = "under_1m_aed"
    FROM_1M_TO_5M = "1m_to_5m_aed"
    FROM_5M_TO_20M = "5m_to_20m_aed"
    FROM_20M_TO_50M = "20m_to_50m_aed"
    OVER_50M = "over_50m_aed"
