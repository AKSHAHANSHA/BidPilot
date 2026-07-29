"""ORM models.

Importing this package registers every table on `Base.metadata`. `migrations/env.py` imports it
so Alembic autogenerate sees the full schema; forgetting a model here would silently produce a
migration that drops its table.
"""

from app.models.analysis import Analysis
from app.models.application import Application, ApplicationDocument
from app.models.certificate import CertificateRecord
from app.models.company_evidence import CompanyEvidence
from app.models.company_profile import CompanyProfile
from app.models.company_project import CompanyProject
from app.models.document import Document
from app.models.document_page import DocumentPage
from app.models.evidence_match import RequirementEvidenceMatch
from app.models.listing import ListingDocumentRequirement, TenderListing
from app.models.notification import Notification
from app.models.organisation import Organisation
from app.models.password_reset import PasswordResetToken
from app.models.readiness import ReadinessAssessment
from app.models.refresh_session import RefreshSession
from app.models.requirement import Requirement, RequirementCitation
from app.models.risk import RiskCitation, RiskFinding
from app.models.screening import ApplicationScreening, ScreeningFinding
from app.models.tender import Tender
from app.models.tender_metadata import TenderMetadata
from app.models.user import User

__all__ = [
    "Analysis",
    "Application",
    "ApplicationDocument",
    "ApplicationScreening",
    "CertificateRecord",
    "CompanyEvidence",
    "CompanyProfile",
    "CompanyProject",
    "Document",
    "DocumentPage",
    "ListingDocumentRequirement",
    "Notification",
    "Organisation",
    "PasswordResetToken",
    "ReadinessAssessment",
    "RefreshSession",
    "Requirement",
    "RequirementCitation",
    "RequirementEvidenceMatch",
    "RiskCitation",
    "RiskFinding",
    "ScreeningFinding",
    "Tender",
    "TenderListing",
    "TenderMetadata",
    "User",
]
