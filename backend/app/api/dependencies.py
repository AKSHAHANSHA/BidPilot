"""Shared FastAPI dependencies.

Route handlers stay thin by depending on these annotated aliases instead of wiring
infrastructure themselves. `CurrentUser` is the single gate for authenticated access: a route
that declares it cannot be reached anonymously, and every repository it then uses requires
that user's ID.

`CurrentCompany` and `CurrentVendor` narrow that gate to one side of the marketplace
(`docs/09_PORTAL_SPEC.md` §2). They answer **403, never 404**, which is the opposite of the
ownership rule a few lines below: a vendor calling a company endpoint is not being told about
somebody else's record, only that their own account is on the wrong side — a fact they already
know and cannot change.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.ai.providers.base import LLMProvider
from app.ai.providers.factory import build_llm_provider
from app.api.errors import AuthenticationError, PermissionDeniedError
from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.logging import get_logger, user_id_var
from app.core.mail import Mailer, build_mailer
from app.core.security import TokenError, decode_access_token
from app.documents.ocr import OcrEngine, build_ocr_engine
from app.domain.enums import AccountType
from app.models.user import User
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.application_repository import (
    ApplicationRepository,
    ApplicationScreeningRepository,
)
from app.repositories.company_repository import (
    CompanyEvidenceRepository,
    CompanyProfileRepository,
    CompanyProjectRepository,
)
from app.repositories.listing_repository import TenderListingRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.organisation_repository import OrganisationRepository
from app.repositories.password_reset_repository import PasswordResetTokenRepository
from app.repositories.refresh_session_repository import RefreshSessionRepository
from app.repositories.requirement_repository import RequirementRepository
from app.repositories.risk_repository import RiskRepository
from app.repositories.tender_repository import DocumentRepository, TenderRepository
from app.repositories.user_repository import UserRepository
from app.services.analysis_service import AnalysisService
from app.services.application_service import ApplicationService
from app.services.auth_service import AuthService, ClientContext
from app.services.company_service import CompanyService
from app.services.listing_service import ListingService
from app.services.notification_service import NotificationService
from app.services.organisation_service import OrganisationService
from app.services.readiness_service import ReadinessService
from app.services.requirement_service import RequirementService
from app.services.risk_service import RiskService
from app.services.screening_service import ScreeningService
from app.services.search_service import SearchService
from app.services.tender_service import TenderService
from app.storage.base import StorageBackend
from app.storage.local import LocalStorage
from app.storage.s3 import S3Storage
from app.workers.queue import DramatiqJobQueue, EagerJobQueue, JobQueue

logger = get_logger(__name__)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

#: `auto_error=False` so a missing header raises our own problem+json rather than FastAPI's
#: default 403 body, which would not match the error contract.
bearer_scheme = HTTPBearer(auto_error=False, description="Access token from /auth/login")

BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]

#: Every authentication failure returns this. The specific cause is logged.
NOT_AUTHENTICATED_DETAIL = "Authentication is required to access this resource."


def get_client_context(request: Request) -> ClientContext:
    """Capture the caller's user agent and address for the session record.

    `request.client.host` is the direct peer. Behind a proxy that is the proxy's address; a
    deployment that needs the real client IP must configure trusted-proxy handling rather than
    have this function trust a spoofable `X-Forwarded-For`.
    """
    return ClientContext(
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )


ClientContextDep = Annotated[ClientContext, Depends(get_client_context)]


def get_mailer(settings: SettingsDep) -> Mailer:
    # Log transport in development, SMTP when a relay is configured. Cheap to build and it
    # holds no connection, so there is nothing to pool or shut down.
    return build_mailer(settings)


MailerDep = Annotated[Mailer, Depends(get_mailer)]


def get_auth_service(session: SessionDep, settings: SettingsDep, mailer: MailerDep) -> AuthService:
    return AuthService(
        users=UserRepository(session),
        sessions=RefreshSessionRepository(session),
        organisations=OrganisationRepository(session),
        tokens=PasswordResetTokenRepository(session),
        mailer=mailer,
        settings=settings,
    )


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def get_llm_provider(settings: SettingsDep) -> LLMProvider:
    """The single provider selection point (`docs/09_PORTAL_SPEC.md` §5).

    Search reports `degraded` from the provider's own identity, so constructing a provider
    anywhere else would make that flag lie: the response would claim a model answered because
    somebody had reached past this function for one.
    """
    return build_llm_provider(settings)


LLMProviderDep = Annotated[LLMProvider, Depends(get_llm_provider)]


def get_ocr_engine(settings: SettingsDep) -> OcrEngine:
    # `NullOcrEngine` unless OCR is enabled *and* the binary is on PATH; the factory logs which
    # and why, because a silent downgrade looks exactly like "every page was unreadable".
    return build_ocr_engine(settings)


OcrEngineDep = Annotated[OcrEngine, Depends(get_ocr_engine)]


def get_organisation_service(session: SessionDep) -> OrganisationService:
    return OrganisationService(organisations=OrganisationRepository(session))


OrganisationServiceDep = Annotated[OrganisationService, Depends(get_organisation_service)]


def get_company_service(session: SessionDep, settings: SettingsDep) -> CompanyService:
    return CompanyService(
        profiles=CompanyProfileRepository(session),
        evidence=CompanyEvidenceRepository(session),
        projects=CompanyProjectRepository(session),
        settings=settings,
    )


CompanyServiceDep = Annotated[CompanyService, Depends(get_company_service)]


def get_storage(settings: SettingsDep) -> StorageBackend:
    # Local filesystem in development; S3-compatible object storage when deployed.
    if settings.storage_backend == "s3":
        return S3Storage(settings.require_s3())
    return LocalStorage(settings.upload_dir)


StorageDep = Annotated[StorageBackend, Depends(get_storage)]


def get_tender_service(
    session: SessionDep, settings: SettingsDep, storage: StorageDep
) -> TenderService:
    return TenderService(
        tenders=TenderRepository(session),
        documents=DocumentRepository(session),
        storage=storage,
        settings=settings,
    )


TenderServiceDep = Annotated[TenderService, Depends(get_tender_service)]


def get_job_queue(session: SessionDep, settings: SettingsDep) -> JobQueue:
    """Choose where an enqueued pipeline actually runs.

    `JOB_EXECUTION=worker` (the default) sends the job to Redis and returns immediately.
    `inline` runs it on this request's session before the response is written, which is the only
    option on a host that cannot run a second process — Vercel's Python runtime, for one
    (`deploy/VERCEL.md`).

    The inline trade-off is real and deliberately not hidden: the submitting request blocks for
    the entire pipeline — S3 reads, PDF extraction, and any model call — and is killed if the
    platform's function timeout expires first, leaving the row in whatever state the pipeline
    last committed. `POST /applications/{id}/submit` therefore returns a *finished* screening
    there rather than a pending one, and a slow submission is a slow HTTP response.

    A provider is built here rather than left to the pipelines because `EagerJobQueue` forwards
    it to the analysis pipeline, whose AI stages have no fallback of their own; screening would
    have built the same one internally. Tests still override this dependency wholesale, so they
    keep injecting their own mock.
    """
    if settings.job_execution == "inline":
        return EagerJobQueue(session, build_llm_provider(settings))
    return DramatiqJobQueue()


JobQueueDep = Annotated[JobQueue, Depends(get_job_queue)]


def get_analysis_service(
    session: SessionDep, settings: SettingsDep, job_queue: JobQueueDep
) -> AnalysisService:
    return AnalysisService(
        analyses=AnalysisRepository(session),
        tenders=TenderRepository(session),
        documents=DocumentRepository(session),
        job_queue=job_queue,
        settings=settings,
    )


AnalysisServiceDep = Annotated[AnalysisService, Depends(get_analysis_service)]


def get_requirement_service(session: SessionDep) -> RequirementService:
    return RequirementService(
        requirements=RequirementRepository(session),
        analyses=AnalysisRepository(session),
    )


RequirementServiceDep = Annotated[RequirementService, Depends(get_requirement_service)]


def get_risk_service(session: SessionDep) -> RiskService:
    return RiskService(
        risks=RiskRepository(session),
        analyses=AnalysisRepository(session),
    )


RiskServiceDep = Annotated[RiskService, Depends(get_risk_service)]


def get_readiness_service(session: SessionDep) -> ReadinessService:
    return ReadinessService(session=session, analyses=AnalysisRepository(session))


ReadinessServiceDep = Annotated[ReadinessService, Depends(get_readiness_service)]


# --- Portal services ------------------------------------------------------------------------


def get_listing_service(session: SessionDep, settings: SettingsDep) -> ListingService:
    return ListingService(
        listings=TenderListingRepository(session),
        organisations=OrganisationRepository(session),
        applications=ApplicationRepository(session),
        settings=settings,
    )


ListingServiceDep = Annotated[ListingService, Depends(get_listing_service)]


def get_notification_service(session: SessionDep) -> NotificationService:
    return NotificationService(notifications=NotificationRepository(session))


#: One instance per request. FastAPI caches a dependency's result for the request, so the
#: application service, the screening service, and the notifications router all stage into the
#: same unit of work — which is what makes "a rolled-back submit leaves nobody notified" true.
NotificationServiceDep = Annotated[NotificationService, Depends(get_notification_service)]


def get_application_service(
    session: SessionDep,
    settings: SettingsDep,
    storage: StorageDep,
    # `JobQueue` satisfies the service's narrower `ScreeningQueue` protocol structurally, so a
    # test that swaps in an eager queue through `get_job_queue` gets eager screening too.
    job_queue: JobQueueDep,
    notifications: NotificationServiceDep,
) -> ApplicationService:
    return ApplicationService(
        applications=ApplicationRepository(session),
        screenings=ApplicationScreeningRepository(session),
        listings=TenderListingRepository(session),
        organisations=OrganisationRepository(session),
        notifications=notifications,
        storage=storage,
        job_queue=job_queue,
        settings=settings,
    )


ApplicationServiceDep = Annotated[ApplicationService, Depends(get_application_service)]


def get_screening_service(
    session: SessionDep, notifications: NotificationServiceDep
) -> ScreeningService:
    return ScreeningService(
        applications=ApplicationRepository(session),
        screenings=ApplicationScreeningRepository(session),
        notifications=notifications,
    )


ScreeningServiceDep = Annotated[ScreeningService, Depends(get_screening_service)]


def get_search_service(
    session: SessionDep, settings: SettingsDep, provider: LLMProviderDep
) -> SearchService:
    return SearchService(
        listings=TenderListingRepository(session),
        provider=provider,
        settings=settings,
    )


SearchServiceDep = Annotated[SearchService, Depends(get_search_service)]


async def get_current_user(
    credentials: BearerCredentials,
    session: SessionDep,
    settings: SettingsDep,
) -> User:
    """Resolve the authenticated user from the bearer access token.

    The user is loaded from the database on every request rather than trusted from the token's
    claims, so deactivating or deleting an account takes effect immediately instead of when
    the access token happens to expire.
    """
    if credentials is None or not credentials.credentials:
        raise AuthenticationError(NOT_AUTHENTICATED_DETAIL)

    try:
        claims = decode_access_token(credentials.credentials, secret=settings.jwt_secret)
    except TokenError as exc:
        logger.info("access_token_rejected", extra={"reason": str(exc)})
        raise AuthenticationError(NOT_AUTHENTICATED_DETAIL) from exc

    user = await UserRepository(session).get_by_id(claims.user_id)
    if user is None or not user.is_active:
        logger.warning("access_token_subject_unavailable", extra={"user_id": str(claims.user_id)})
        raise AuthenticationError(NOT_AUTHENTICATED_DETAIL)

    # `UserRead` serialises `User.organisation`, and the relationship is lazy on the model, so
    # `GET /auth/me` would raise `MissingGreenlet` mid-serialisation — a 500 on a request that
    # had already succeeded. Loaded here rather than in each handler because every route that
    # renders the current user goes through this dependency. `set_committed_value` binds the
    # row without marking the user dirty, which is what `AuthService` does on its own paths.
    set_committed_value(
        user, "organisation", await OrganisationRepository(session).get_for_owner(user.id)
    )

    # Bind the user to the logging context so every later line in this request is attributable.
    user_id_var.set(str(user.id))
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


# --- Marketplace side guards ----------------------------------------------------------------
#
# `docs/09_PORTAL_SPEC.md` §2: 403, never 404. Ownership failures use 404 so the API does not
# confirm that another user's record exists; that reasoning does not apply here, because the
# caller is being told a fact about their own account and nothing about the resource.

COMPANY_ONLY_DETAIL = (
    "This action belongs to buying organisations. This account is registered as a vendor, and "
    "an account's side of the marketplace is fixed at registration."
)

VENDOR_ONLY_DETAIL = (
    "This action belongs to supplying organisations. This account is registered as a company, "
    "and an account's side of the marketplace is fixed at registration."
)


def require_company(current_user: CurrentUser) -> User:
    """The caller must be a buying organisation."""
    if current_user.account_type != AccountType.COMPANY.value:
        logger.info(
            "account_type_rejected",
            extra={"required": AccountType.COMPANY.value, "actual": current_user.account_type},
        )
        raise PermissionDeniedError(COMPANY_ONLY_DETAIL)
    return current_user


def require_vendor(current_user: CurrentUser) -> User:
    """The caller must be a supplying organisation."""
    if current_user.account_type != AccountType.VENDOR.value:
        logger.info(
            "account_type_rejected",
            extra={"required": AccountType.VENDOR.value, "actual": current_user.account_type},
        )
        raise PermissionDeniedError(VENDOR_ONLY_DETAIL)
    return current_user


CurrentCompany = Annotated[User, Depends(require_company)]
CurrentVendor = Annotated[User, Depends(require_vendor)]
