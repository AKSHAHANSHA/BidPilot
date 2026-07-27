"""Domain rules: pure Python, no I/O, no framework imports.

Everything here is deterministic and directly unit-testable. Deriving expiry state, scoring
profile completion, and (from Phase 9) calculating readiness all live in this layer precisely
because they must be repeatable and explainable rather than convenient.
"""

from app.domain.citation import (
    FUZZY_THRESHOLD,
    VerificationResult,
    verify_quote,
)
from app.domain.completion import (
    COMPLETION_VERSION,
    CompletionResult,
    calculate_completion,
)
from app.domain.enums import (
    Emirate,
    EvidenceCategory,
    ExpiryState,
    ProjectStatus,
    RevenueRange,
    VerificationStatus,
)
from app.domain.expiry import days_until_expiry, derive_expiry_state, expiry_state_filter
from app.domain.scoring import (
    SCORING_VERSION,
    ReadinessResult,
    RequirementScore,
    RiskScore,
    ScoringInput,
    calculate_readiness,
    days_until,
)

__all__ = [
    "COMPLETION_VERSION",
    "FUZZY_THRESHOLD",
    "SCORING_VERSION",
    "CompletionResult",
    "Emirate",
    "EvidenceCategory",
    "ExpiryState",
    "ProjectStatus",
    "ReadinessResult",
    "RequirementScore",
    "RevenueRange",
    "RiskScore",
    "ScoringInput",
    "VerificationResult",
    "VerificationStatus",
    "calculate_completion",
    "calculate_readiness",
    "days_until",
    "days_until_expiry",
    "derive_expiry_state",
    "expiry_state_filter",
    "verify_quote",
]
