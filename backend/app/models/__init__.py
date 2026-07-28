"""ORM models.

Importing this package registers every table on `Base.metadata`. `migrations/env.py` imports it
so Alembic autogenerate sees the full schema; forgetting a model here would silently produce a
migration that drops its table.
"""

from app.models.analysis import Analysis
from app.models.application import Application
from app.models.company_evidence import CompanyEvidence
from app.models.company_profile import CompanyProfile
from app.models.company_project import CompanyProject
from app.models.document import Document
from app.models.document_page import DocumentPage
from app.models.evidence_match import RequirementEvidenceMatch
from app.models.market_project import MarketProject
from app.models.notification import Notification
from app.models.readiness import ReadinessAssessment
from app.models.refresh_session import RefreshSession
from app.models.requirement import Requirement, RequirementCitation
from app.models.risk import RiskCitation, RiskFinding
from app.models.tender import Tender
from app.models.tender_metadata import TenderMetadata
from app.models.user import User
from app.models.vendor_profile import VendorProfile

__all__ = [
    "Analysis",
    "Application",
    "CompanyEvidence",
    "CompanyProfile",
    "CompanyProject",
    "Document",
    "DocumentPage",
    "MarketProject",
    "Notification",
    "ReadinessAssessment",
    "RefreshSession",
    "Requirement",
    "RequirementCitation",
    "RequirementEvidenceMatch",
    "RiskCitation",
    "RiskFinding",
    "Tender",
    "TenderMetadata",
    "User",
    "VendorProfile",
]
