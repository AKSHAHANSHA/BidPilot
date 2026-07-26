"""ORM models.

Importing this package registers every table on `Base.metadata`. `migrations/env.py` imports it
so Alembic autogenerate sees the full schema; forgetting a model here would silently produce a
migration that drops its table.
"""

from app.models.analysis import Analysis
from app.models.company_evidence import CompanyEvidence
from app.models.company_profile import CompanyProfile
from app.models.company_project import CompanyProject
from app.models.document import Document
from app.models.document_page import DocumentPage
from app.models.refresh_session import RefreshSession
from app.models.tender import Tender
from app.models.user import User

__all__ = [
    "Analysis",
    "CompanyEvidence",
    "CompanyProfile",
    "CompanyProject",
    "Document",
    "DocumentPage",
    "RefreshSession",
    "Tender",
    "User",
]
