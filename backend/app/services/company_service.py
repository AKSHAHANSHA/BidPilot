"""Company knowledge-base orchestration.

Holds the rules that need more than one field or more than one row to judge:

* one profile per user, with the database's unique constraint as the real arbiter;
* partial updates whose validity depends on persisted state (a `PATCH` that supplies only a new
  `end_date` has to be checked against the stored `status`);
* profile completion recalculated on every write and served fresh on every read.

Routes call these methods and shape responses. They make no decisions.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.api.errors import ConflictError, NotFoundError, ValidationProblem
from app.core.config import Settings
from app.core.logging import get_logger
from app.domain.completion import CompletionResult, calculate_completion
from app.domain.enums import ExpiryState, ProjectStatus
from app.domain.expiry import days_until_expiry, derive_expiry_state
from app.models.company_evidence import CompanyEvidence
from app.models.company_profile import CompanyProfile
from app.models.company_project import CompanyProject
from app.repositories.company_repository import (
    CompanyEvidenceRepository,
    CompanyProfileRepository,
    CompanyProjectRepository,
    EvidenceFilters,
    ProjectFilters,
)
from app.schemas.company import CompanyProfileCreate, CompanyProfileUpdate
from app.schemas.evidence import EvidenceCreate, EvidenceUpdate
from app.schemas.project import ProjectCreate, ProjectUpdate

logger = get_logger(__name__)

PROFILE_REQUIRED_DETAIL = "Create a company profile before adding evidence or projects."


@dataclass(frozen=True, slots=True)
class ExpiryView:
    state: ExpiryState
    days_until_expiry: int | None
    threshold_days: int


class CompanyService:
    def __init__(
        self,
        *,
        profiles: CompanyProfileRepository,
        evidence: CompanyEvidenceRepository,
        projects: CompanyProjectRepository,
        settings: Settings,
    ) -> None:
        self.profiles = profiles
        self.evidence = evidence
        self.projects = projects
        self.settings = settings

    # --- Helpers -----------------------------------------------------------------------

    def _today(self) -> date:
        return datetime.now(tz=UTC).date()

    @property
    def _threshold(self) -> int:
        return self.settings.evidence_expiring_soon_days

    def completion_for(self, profile: CompanyProfile) -> CompletionResult:
        """Freshly calculated score. Reads never serve the persisted value directly, so an
        algorithm change cannot surface a stale number."""
        return calculate_completion(profile)

    def expiry_for(self, evidence: CompanyEvidence) -> ExpiryView:
        today = self._today()
        return ExpiryView(
            state=derive_expiry_state(
                expiry_date=evidence.expiry_date,
                verification_status=evidence.verification_status,
                today=today,
                threshold_days=self._threshold,
            ),
            days_until_expiry=days_until_expiry(expiry_date=evidence.expiry_date, today=today),
            threshold_days=self._threshold,
        )

    def duration_months_for(self, project: CompanyProject) -> int | None:
        """Whole months delivered. None while the project is still running."""
        if project.end_date is None:
            return None
        months = (project.end_date.year - project.start_date.year) * 12 + (
            project.end_date.month - project.start_date.month
        )
        if project.end_date.day < project.start_date.day:
            months -= 1
        return max(months, 0)

    # --- Profile -----------------------------------------------------------------------

    async def create_profile(
        self, *, user_id: uuid.UUID, payload: CompanyProfileCreate
    ) -> CompanyProfile:
        if await self.profiles.exists_for_owner(user_id):
            raise ConflictError(
                "A company profile already exists for this account. "
                "Update it instead of creating a second one."
            )

        values = payload.model_dump()
        values["website"] = str(values["website"]) if values.get("website") else None
        values["emirate"] = payload.emirate.value
        values["annual_revenue_range"] = (
            payload.annual_revenue_range.value if payload.annual_revenue_range else None
        )
        values["contact_email"] = str(payload.contact_email)

        profile = CompanyProfile(owner_user_id=user_id, **values)
        self._refresh_completion(profile)
        self.profiles.add(profile)

        try:
            await self.profiles.flush()
        except IntegrityError as exc:
            # Two concurrent POSTs: the unique constraint on owner_user_id is the real arbiter,
            # and it just rejected this one. The database message is never surfaced.
            raise ConflictError("A company profile already exists for this account.") from exc

        logger.info(
            "company_profile_created",
            extra={
                "profile_id": str(profile.id),
                "completion": profile.profile_completion_percentage,
            },
        )
        return profile

    async def get_profile(self, user_id: uuid.UUID) -> CompanyProfile:
        profile = await self.profiles.get_for_owner(user_id)
        if profile is None:
            raise NotFoundError("No company profile exists for this account yet.")
        return profile

    async def require_profile(self, user_id: uuid.UUID) -> CompanyProfile:
        """The profile that evidence and projects must hang from."""
        profile = await self.profiles.get_for_owner(user_id)
        if profile is None:
            raise ValidationProblem(PROFILE_REQUIRED_DETAIL)
        return profile

    async def update_profile(
        self, *, user_id: uuid.UUID, payload: CompanyProfileUpdate
    ) -> CompanyProfile:
        profile = await self.get_profile(user_id)
        # `model_fields_set` distinguishes "field absent" from "field explicitly set to null",
        # which is the whole point of PATCH.
        changes = payload.model_dump(exclude_unset=True)

        if "website" in changes:
            changes["website"] = str(changes["website"]) if changes["website"] else None
        if "emirate" in changes and changes["emirate"] is not None:
            changes["emirate"] = payload.emirate.value if payload.emirate else None
        if "annual_revenue_range" in changes:
            changes["annual_revenue_range"] = (
                payload.annual_revenue_range.value if payload.annual_revenue_range else None
            )
        if "contact_email" in changes and changes["contact_email"] is not None:
            changes["contact_email"] = str(changes["contact_email"])

        self._validate_profile_changes(profile, changes)

        for field, value in changes.items():
            setattr(profile, field, value)

        self._refresh_completion(profile)
        await self.profiles.flush()
        logger.info(
            "company_profile_updated",
            extra={
                "profile_id": str(profile.id),
                "fields_changed": len(changes),
                "completion": profile.profile_completion_percentage,
            },
        )
        return profile

    def _validate_profile_changes(self, profile: CompanyProfile, changes: dict[str, Any]) -> None:
        """Checks that need the persisted row, because only one side may have been supplied."""
        minimum = changes.get("preferred_contract_value_min", profile.preferred_contract_value_min)
        maximum = changes.get("preferred_contract_value_max", profile.preferred_contract_value_max)
        if isinstance(minimum, Decimal) and isinstance(maximum, Decimal) and minimum > maximum:
            raise ValidationProblem(
                "Minimum preferred contract value cannot exceed the maximum preferred value."
            )

        year = changes.get("year_established", profile.year_established)
        experience = changes.get("years_of_experience", profile.years_of_experience)
        age = datetime.now(tz=UTC).year - int(year)
        if int(experience) > age + 1:
            raise ValidationProblem(
                f"Years of experience ({experience}) exceeds the company's age since {year}."
            )

    def _refresh_completion(self, profile: CompanyProfile) -> None:
        result = calculate_completion(profile)
        profile.profile_completion_percentage = result.score
        profile.completion_version = result.version

    async def delete_profile(self, user_id: uuid.UUID) -> None:
        """Delete the profile and, by cascade, all of its evidence and projects."""
        profile = await self.get_profile(user_id)
        await self.profiles.delete(profile)
        await self.profiles.flush()
        logger.info("company_profile_deleted", extra={"profile_id": str(profile.id)})

    # --- Evidence ----------------------------------------------------------------------

    async def create_evidence(
        self, *, user_id: uuid.UUID, payload: EvidenceCreate
    ) -> CompanyEvidence:
        profile = await self.require_profile(user_id)
        evidence = CompanyEvidence(
            owner_user_id=user_id,
            # Taken from the caller's own profile, never from the request body: that is what
            # makes "attach to another user's profile" unrepresentable rather than merely
            # rejected.
            company_profile_id=profile.id,
            title=payload.title,
            category=payload.category.value,
            issuing_organisation=payload.issuing_organisation,
            reference_number=payload.reference_number,
            description=payload.description,
            issue_date=payload.issue_date,
            expiry_date=payload.expiry_date,
            verification_status=payload.verification_status.value,
            verification_notes=payload.verification_notes,
            tags=list(payload.tags),
        )
        self.evidence.add(evidence)
        await self.evidence.flush()
        logger.info(
            "company_evidence_created",
            extra={"evidence_id": str(evidence.id), "category": evidence.category},
        )
        return evidence

    async def get_evidence(self, *, user_id: uuid.UUID, evidence_id: uuid.UUID) -> CompanyEvidence:
        evidence = await self.evidence.get_for_user(evidence_id, user_id)
        if evidence is None:
            # 404 whether the row is absent or owned by someone else — a 403 would confirm it
            # exists.
            raise NotFoundError("Evidence not found.")
        return evidence

    async def list_evidence(
        self,
        *,
        user_id: uuid.UUID,
        filters: EvidenceFilters,
        limit: int,
        offset: int,
    ) -> tuple[list[CompanyEvidence], int]:
        return await self.evidence.list_filtered(
            user_id,
            filters,
            today=self._today(),
            threshold_days=self._threshold,
            limit=limit,
            offset=offset,
        )

    async def update_evidence(
        self, *, user_id: uuid.UUID, evidence_id: uuid.UUID, payload: EvidenceUpdate
    ) -> CompanyEvidence:
        evidence = await self.get_evidence(user_id=user_id, evidence_id=evidence_id)
        changes = payload.model_dump(exclude_unset=True)

        if "category" in changes and payload.category is not None:
            changes["category"] = payload.category.value
        if "verification_status" in changes and payload.verification_status is not None:
            changes["verification_status"] = payload.verification_status.value

        issue = changes.get("issue_date", evidence.issue_date)
        expiry = changes.get("expiry_date", evidence.expiry_date)
        if issue is not None and expiry is not None and expiry < issue:
            raise ValidationProblem("Expiry date cannot be earlier than the issue date.")

        for field, value in changes.items():
            setattr(evidence, field, value)

        await self.evidence.flush()
        logger.info("company_evidence_updated", extra={"evidence_id": str(evidence.id)})
        return evidence

    async def delete_evidence(self, *, user_id: uuid.UUID, evidence_id: uuid.UUID) -> None:
        deleted = await self.evidence.delete_for_user(evidence_id, user_id)
        if not deleted:
            raise NotFoundError("Evidence not found.")
        logger.info("company_evidence_deleted", extra={"evidence_id": str(evidence_id)})

    # --- Projects ----------------------------------------------------------------------

    async def create_project(self, *, user_id: uuid.UUID, payload: ProjectCreate) -> CompanyProject:
        profile = await self.require_profile(user_id)
        project = CompanyProject(
            owner_user_id=user_id,
            company_profile_id=profile.id,
            client_name=payload.client_name,
            project_title=payload.project_title,
            industry=payload.industry,
            description=payload.description,
            contract_value=payload.contract_value,
            currency=payload.currency,
            start_date=payload.start_date,
            end_date=payload.end_date,
            status=payload.status.value,
            location=payload.location,
            services_delivered=list(payload.services_delivered),
            outcome=payload.outcome,
            client_reference_available=payload.client_reference_available,
            is_confidential=payload.is_confidential,
        )
        self.projects.add(project)
        await self.projects.flush()
        logger.info(
            "company_project_created",
            extra={"project_id": str(project.id), "status": project.status},
        )
        return project

    async def get_project(self, *, user_id: uuid.UUID, project_id: uuid.UUID) -> CompanyProject:
        project = await self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        return project

    async def list_projects(
        self,
        *,
        user_id: uuid.UUID,
        filters: ProjectFilters,
        limit: int,
        offset: int,
    ) -> tuple[list[CompanyProject], int]:
        return await self.projects.list_filtered(user_id, filters, limit=limit, offset=offset)

    async def update_project(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, payload: ProjectUpdate
    ) -> CompanyProject:
        project = await self.get_project(user_id=user_id, project_id=project_id)
        changes = payload.model_dump(exclude_unset=True)

        if "status" in changes and payload.status is not None:
            changes["status"] = payload.status.value

        start = changes.get("start_date", project.start_date)
        end = changes.get("end_date", project.end_date)
        status = changes.get("status", project.status)

        if end is not None and end < start:
            raise ValidationProblem("Project end date cannot be earlier than the start date.")

        # The combined state has to be judged against persisted values: a PATCH that only flips
        # status to "completed" must be rejected if no end date exists, and one that only sets an
        # end date must be rejected while the project is still current.
        if status == ProjectStatus.CURRENT.value and end is not None:
            raise ValidationProblem(
                "A current project cannot have an end date. Set status to 'completed' as well."
            )
        if status == ProjectStatus.COMPLETED.value and end is None:
            raise ValidationProblem("A completed project requires an end date.")

        for field, value in changes.items():
            setattr(project, field, value)

        await self.projects.flush()
        logger.info("company_project_updated", extra={"project_id": str(project.id)})
        return project

    async def delete_project(self, *, user_id: uuid.UUID, project_id: uuid.UUID) -> None:
        deleted = await self.projects.delete_for_user(project_id, user_id)
        if not deleted:
            raise NotFoundError("Project not found.")
        logger.info("company_project_deleted", extra={"project_id": str(project_id)})
