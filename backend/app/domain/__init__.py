"""Domain rules: pure Python, no I/O, no framework imports.

Everything here is deterministic and directly unit-testable. Deriving expiry state, scoring
profile completion, and (from Phase 9) calculating readiness all live in this layer precisely
because they must be repeatable and explainable rather than convenient.
"""

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

__all__ = [
    "COMPLETION_VERSION",
    "CompletionResult",
    "Emirate",
    "EvidenceCategory",
    "ExpiryState",
    "ProjectStatus",
    "RevenueRange",
    "VerificationStatus",
    "calculate_completion",
    "days_until_expiry",
    "derive_expiry_state",
    "expiry_state_filter",
]
