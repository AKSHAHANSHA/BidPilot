"""Provider-neutral LLM interface.

The provider returns raw JSON text plus token counts; validation against a strict Pydantic
model happens in `app/ai/extraction.py`, in our own code. That placement is deliberate: a
malformed response or an unknown enum is rejected by the same code path whether it came from
OpenAI, Anthropic, or a test mock, so the "invalid output does not corrupt analysis" guarantee
does not depend on any provider's cooperation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class LLMProviderError(Exception):
    """A provider call failed in a way the pipeline should treat as an AI failure."""


class LLMTimeoutError(LLMProviderError):
    """The provider did not respond within the configured timeout."""


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """One structured completion. `content` is the raw JSON text, not yet validated."""

    content: str
    input_tokens: int
    output_tokens: int
    provider: str
    model: str


class LLMProvider(Protocol):
    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        schema_name: str,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Return a JSON completion constrained to `schema`.

        Implementations must apply a bounded timeout and retry only transient transport
        failures; a schema/parse failure is the caller's to handle.
        """
        ...
