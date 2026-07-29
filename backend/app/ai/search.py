"""Turn a visitor's sentence into a structured search interpretation (`docs/09` §5).

Everything here exists to keep an untrusted, unauthenticated string from doing damage:

* The query is untrusted data. It goes in the *user* message between `DOCUMENT_DELIMITER`
  markers, never interpolated into the system prompt, so an imperative query is search text and
  not an instruction (`CLAUDE.md`: uploaded documents and search queries are never instructions).
* The response is validated back through `SearchInterpretation` (`extra="forbid"`) in our code,
  exactly as extraction does, so a malformed completion cannot reach the ranker.
* Category and emirate values the model invented are dropped before validation rather than
  failing it, the same defensive filtering `app/ai/extraction.py` applies to page numbers. One
  hallucinated word should cost a filter, not the whole search.
* Nothing here raises. A provider outage or a stubbornly invalid completion falls back to the
  keyword derivation: a search that degrades is a working page, a search that 500s is not.

Ranking is deliberately absent. The model never sees the listing set, so it cannot invent or
order a listing; the search service ranks in deterministic Python over the fields below.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from app.ai.prompts import DOCUMENT_DELIMITER, SEARCH_PROMPT, SEARCH_SCHEMA_NAME
from app.ai.providers.base import LLMProvider, LLMProviderError
from app.ai.providers.keyword import derive_interpretation
from app.ai.structured_models import SearchInterpretation
from app.core.config import Settings
from app.core.logging import get_logger
from app.domain.enums import Emirate, TenderCategory

logger = get_logger(__name__)

#: Longest query sent to a provider. A search box does not need more, and the limit bounds both
#: token spend and the work the keyword derivation does on a hostile input.
MAX_QUERY_CHARS = 500

#: One validation retry, as in `app/ai/extraction.py`. A model that returns the wrong shape
#: twice will not get it right on a third attempt, and a visitor is waiting on this request.
_ATTEMPTS = 2


async def interpret_query(
    query: str, *, provider: LLMProvider, settings: Settings
) -> SearchInterpretation:
    """Interpret a natural-language search query. Never raises; degrades to keyword matching."""
    # A query containing the delimiter would forge a closing marker and place the rest of its
    # own text outside the untrusted region. Removing it keeps the boundary meaningful; the
    # guard on the system prompt is the second line of defence, not the only one.
    text = query[:MAX_QUERY_CHARS].replace(DOCUMENT_DELIMITER, " ").strip()
    if not text:
        return derive_interpretation("")

    user = SEARCH_PROMPT.render_user(document_text=text)
    schema = SearchInterpretation.model_json_schema()
    provider_name = getattr(provider, "provider_name", "unknown")

    last_error: Exception | None = None
    for attempt in range(_ATTEMPTS):
        try:
            response = await provider.complete_json(
                system=SEARCH_PROMPT.system,
                user=user,
                schema=schema,
                schema_name=SEARCH_SCHEMA_NAME,
            )
        except LLMProviderError as exc:
            # The adapter has already retried transport failures with backoff; repeating that
            # here would only add latency to a request someone is watching.
            last_error = exc
            logger.warning(
                "search_provider_failed",
                extra={"provider": provider_name, "error_type": type(exc).__name__},
            )
            break
        try:
            return _validate(response.content)
        except (ValidationError, ValueError) as exc:
            last_error = exc
            logger.warning(
                "search_interpretation_invalid",
                extra={
                    "attempt": attempt,
                    "provider": provider_name,
                    "prompt_version": settings.prompt_version,
                },
            )

    logger.warning(
        "search_interpretation_fallback",
        extra={
            "provider": provider_name,
            "error_type": type(last_error).__name__ if last_error else None,
        },
    )
    return derive_interpretation(text)


def _validate(content: str) -> SearchInterpretation:
    """Parse, drop unknown vocabulary values, then validate strictly."""
    payload = json.loads(content)
    if not isinstance(payload, dict):
        raise ValueError("The search interpretation was not a JSON object.")
    _keep_known(payload, "categories", set(TenderCategory.values()))
    _keep_known(payload, "emirates", set(Emirate.values()))
    return SearchInterpretation.model_validate(payload)


def _keep_known(payload: dict[str, Any], field: str, allowed: set[str]) -> None:
    """Drop vocabulary values that are not real enum members, in place.

    Anything that is not a list is left alone so strict validation reports it as the shape error
    it is, rather than having it quietly replaced with an empty list here.
    """
    values = payload.get(field)
    if not isinstance(values, list):
        return
    kept = [value for value in values if isinstance(value, str) and value in allowed]
    if len(kept) != len(values):
        logger.warning(
            "search_unknown_values_dropped",
            extra={"field": field, "dropped": len(values) - len(kept)},
        )
    payload[field] = kept
