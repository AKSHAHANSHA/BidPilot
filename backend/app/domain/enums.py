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


# ---------------------------------------------------------------------------
# Portal vocabularies
#
# The vocabularies below serve the two-sided marketplace: buying organisations
# publish listings, supplying vendors apply to them. They follow the same rule as
# everything above — the enum is the single source of truth and the migration's
# CHECK constraint is written from `sql_in_list()`.
# ---------------------------------------------------------------------------


class AccountType(VocabularyEnum):
    """Which side of the marketplace an account sits on.

    Chosen at registration and immutable afterwards: an account's listings and applications
    are meaningless if its side can flip underneath them. Changing sides means a new account.
    """

    #: A buying organisation. Publishes listings and reviews applicants.
    COMPANY = "company"
    #: A supplying organisation. Browses listings and applies to them.
    VENDOR = "vendor"


class TenderCategory(VocabularyEnum):
    """Procurement categories a listing can be filed under.

    Deliberately broad and flat rather than a nested taxonomy: a single-select category that a
    buyer picks correctly is worth more than a hierarchy they pick wrongly. Sector nuance lives
    in the free-text `industry` and the tag array, both of which are searchable.
    """

    CONSTRUCTION_CIVIL_WORKS = "construction_civil_works"
    ROADS_INFRASTRUCTURE = "roads_infrastructure"
    WATER_WASTEWATER = "water_wastewater"
    ELECTRICAL_POWER = "electrical_power"
    OIL_GAS_PETROCHEMICAL = "oil_gas_petrochemical"
    RENEWABLE_ENERGY = "renewable_energy"
    FACILITIES_MANAGEMENT = "facilities_management"
    CLEANING_WASTE_MANAGEMENT = "cleaning_waste_management"
    LANDSCAPING_IRRIGATION = "landscaping_irrigation"
    IT_SOFTWARE = "it_software"
    CYBERSECURITY = "cybersecurity"
    CLOUD_DATA_CENTRE = "cloud_data_centre"
    TELECOMMUNICATIONS = "telecommunications"
    AI_DATA_ANALYTICS = "ai_data_analytics"
    HEALTHCARE_MEDICAL = "healthcare_medical"
    EDUCATION_TRAINING = "education_training"
    TRANSPORT_LOGISTICS = "transport_logistics"
    FLEET_VEHICLES = "fleet_vehicles"
    SECURITY_SERVICES = "security_services"
    CATERING_HOSPITALITY = "catering_hospitality"
    PRINTING_MEDIA = "printing_media"
    MARKETING_EVENTS = "marketing_events"
    CONSULTING_ADVISORY = "consulting_advisory"
    LEGAL_SERVICES = "legal_services"
    FINANCIAL_AUDIT = "financial_audit"
    HR_RECRUITMENT = "hr_recruitment"
    FURNITURE_FITOUT = "furniture_fitout"
    LABORATORY_SCIENTIFIC = "laboratory_scientific"
    DEFENCE_AEROSPACE = "defence_aerospace"
    ENVIRONMENTAL_SERVICES = "environmental_services"


class ListingStatus(VocabularyEnum):
    """Lifecycle of a published tender listing.

    `CLOSED` and `AWARDED` are distinct because they answer different questions: closed means
    the window ended, awarded means a winner exists. A listing can be closed for weeks before
    an award is recorded, and the public list needs to say which is true.
    """

    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"
    AWARDED = "awarded"
    CANCELLED = "cancelled"


class ApplicationStatus(VocabularyEnum):
    """Lifecycle of a vendor's application to a listing.

    Maps directly onto the vendor dashboard's counters. `SUBMITTED` and `UNDER_REVIEW` are
    separate so "waiting for an answer" means the buyer has actually opened it, not merely
    that the vendor pressed send.
    """

    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    SHORTLISTED = "shortlisted"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"

    @classmethod
    def open_states(cls) -> tuple[str, ...]:
        """Applications still awaiting a buyer decision — the dashboard's "waiting" bucket."""
        return (cls.SUBMITTED.value, cls.UNDER_REVIEW.value, cls.SHORTLISTED.value)

    @classmethod
    def decided_states(cls) -> tuple[str, ...]:
        return (cls.APPROVED.value, cls.REJECTED.value)


class ScreeningStatus(VocabularyEnum):
    """Where a submission sits in the document-screening pipeline.

    Mirrors `AnalysisStatus` rather than reusing it: the two pipelines fail for different
    reasons and are polled by different dashboards, and a shared vocabulary would force one
    to carry states the other can never enter.
    """

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class RequiredDocumentType(VocabularyEnum):
    """The checklist a buyer builds a listing's document requirements from.

    A controlled list — not free text — because screening matches an uploaded file against
    these keys. A buyer inventing "Trade Licence (copy)" would produce a requirement no
    classifier can ever satisfy, and every vendor would score as missing it.
    """

    TRADE_LICENCE = "trade_licence"
    COMMERCIAL_REGISTRATION = "commercial_registration"
    VAT_TAX_CERTIFICATE = "vat_tax_certificate"
    ESTABLISHMENT_CARD = "establishment_card"
    AUTHORISED_SIGNATORY = "authorised_signatory"
    COMPANY_PROFILE = "company_profile"
    AUDITED_FINANCIALS = "audited_financials"
    BANK_REFERENCE_LETTER = "bank_reference_letter"
    BID_BOND = "bid_bond"
    PERFORMANCE_GUARANTEE = "performance_guarantee"
    INSURANCE_CERTIFICATE = "insurance_certificate"
    ISO_CERTIFICATION = "iso_certification"
    HSE_PLAN = "hse_plan"
    QUALITY_PLAN = "quality_plan"
    TECHNICAL_PROPOSAL = "technical_proposal"
    COMMERCIAL_PROPOSAL = "commercial_proposal"
    METHOD_STATEMENT = "method_statement"
    PROJECT_SCHEDULE = "project_schedule"
    STAFF_CVS = "staff_cvs"
    ORGANISATION_CHART = "organisation_chart"
    EQUIPMENT_LIST = "equipment_list"
    PAST_PROJECT_REFERENCES = "past_project_references"
    CLIENT_TESTIMONIAL = "client_testimonial"
    OTHER = "other"


class DocumentScreeningVerdict(VocabularyEnum):
    """Per-requirement outcome of screening a submission's documents.

    `UNREADABLE` is separate from `MISSING` on purpose: a scanned page that OCR could not read
    is a fixable upload problem, and telling a vendor "missing" when they did supply the file
    is both wrong and unactionable (`docs/03` §9 — absence is not proof of non-existence).

    `UNVERIFIED` is separate again. It means the document arrived and was read, but the
    credential it asserts could not be confirmed against the issuing registry — the number is
    not on file, or is recorded as withdrawn. Reporting that as `MISSING` would tell a vendor
    to upload a document they already uploaded; reporting it as `PRESENT` would let an
    unverifiable claim earn full credit.
    """

    PRESENT = "present"
    PRESENT_EXPIRED = "present_expired"
    PRESENT_UNREADABLE = "present_unreadable"
    PRESENT_UNVERIFIED = "present_unverified"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"


class CertificateStatus(VocabularyEnum):
    """State of a certificate in the issuing body's register.

    `SUSPENDED` and `WITHDRAWN` are both "not currently valid" but are kept apart because they
    say different things to a buyer: a suspended certificate may be reinstated, a withdrawn one
    will not be.
    """

    ACTIVE = "active"
    EXPIRED = "expired"
    SUSPENDED = "suspended"
    WITHDRAWN = "withdrawn"


class NotificationType(VocabularyEnum):
    """What a notification is telling its recipient about."""

    APPLICATION_RECEIVED = "application_received"
    SCREENING_COMPLETED = "screening_completed"
    SCREENING_FAILED = "screening_failed"
    APPLICATION_STATUS_CHANGED = "application_status_changed"
    DEADLINE_APPROACHING = "deadline_approaching"
    LISTING_CLOSED = "listing_closed"
