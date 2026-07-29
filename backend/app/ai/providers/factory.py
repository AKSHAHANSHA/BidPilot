"""The one place a provider is chosen.

Selection used to be implicit — whoever constructed `OpenAIProvider` decided — which meant an
unconfigured environment failed differently in the API, the worker, and the tests. Here "no key"
has exactly one meaning: the keyword provider, named as such in the log line that records the
choice, so a degraded search is visible in the logs rather than inferred later.

Mirrors `get_storage` in `app/api/dependencies.py`: one function, one branch on settings, no
registry or plugin indirection for two implementations.
"""

from __future__ import annotations

from app.ai.providers.base import LLMProvider
from app.ai.providers.keyword import KeywordProvider
from app.ai.providers.openai_provider import OpenAIProvider
from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def build_llm_provider(settings: Settings) -> LLMProvider:
    """Return OpenAI when a key and a model are configured, otherwise the keyword provider.

    Both are required: a key without a model (or the reverse) is a half-finished configuration,
    and constructing the client anyway would turn it into an authentication error at the worst
    possible moment. Falling back is safe because the keyword provider refuses every schema it
    cannot honestly answer — document analysis still fails loudly, only search degrades.
    """
    if settings.openai_api_key and settings.openai_model:
        logger.info(
            "llm_provider_selected",
            extra={"provider": "openai", "llm_model": settings.openai_model},
        )
        return OpenAIProvider(settings)

    logger.warning(
        "llm_provider_selected",
        extra={
            "provider": KeywordProvider.provider_name,
            "reason": "openai_api_key_and_model_not_configured",
        },
    )
    return KeywordProvider()
