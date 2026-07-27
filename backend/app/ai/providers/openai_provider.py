"""OpenAI structured-output adapter.

The runtime primary. Uses the Chat Completions structured-output mode (`response_format` with a
strict JSON schema) so the model returns schema-shaped JSON, then applies a bounded timeout and
retries only transient transport failures. Schema/parse handling is the caller's, in
`app/ai/extraction.py` (see `providers/base.py`).

The client is created lazily and the key is read from settings, never logged.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.ai.providers.base import LLMProviderError, LLMResponse, LLMTimeoutError
from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _strictify(schema: dict[str, Any]) -> dict[str, Any]:
    """Adapt a Pydantic JSON schema to OpenAI structured-output strict mode.

    OpenAI requires every object to list *all* its properties in `required` and to set
    `additionalProperties: false`; optionality is expressed by a nullable type, not by omission
    from `required`. Pydantic marks only fields without defaults as required, so this walks the
    schema (including `$defs`) and fills `required` with every property key.
    """
    import copy

    result = copy.deepcopy(schema)

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["required"] = list(node["properties"].keys())
                node["additionalProperties"] = False
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(result)
    return result


class OpenAIProvider:
    def __init__(self, settings: Settings) -> None:
        api_key, model = settings.require_openai()
        self._model = model
        self.model = model
        self.provider_name = "openai"
        self._timeout = settings.llm_timeout_seconds
        self._max_retries = settings.llm_max_retries
        # Imported lazily so the package is only needed when AI actually runs.
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key, timeout=self._timeout)

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        schema_name: str,
        temperature: float | None = None,
    ) -> LLMResponse:
        from typing import cast

        from openai import APITimeoutError, OpenAIError

        response_format: Any = {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "schema": _strictify(schema), "strict": True},
        }
        messages: Any = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        # Only send temperature when explicitly requested; several current models accept only
        # their default and 400 on any other value.
        extra: dict[str, Any] = {} if temperature is None else {"temperature": temperature}

        last_error: Exception | None = None
        # attempt 0 is the initial try; up to llm_max_retries further attempts.
        for attempt in range(self._max_retries + 1):
            try:
                completion = await self._client.chat.completions.create(
                    model=cast("Any", self._model),
                    response_format=response_format,
                    messages=messages,
                    **extra,
                )
                content = completion.choices[0].message.content or ""
                usage = completion.usage
                return LLMResponse(
                    content=content,
                    input_tokens=usage.prompt_tokens if usage else 0,
                    output_tokens=usage.completion_tokens if usage else 0,
                    provider="openai",
                    model=self._model,
                )
            except APITimeoutError:
                last_error = LLMTimeoutError("The AI provider timed out.")
                logger.warning("openai_timeout", extra={"attempt": attempt})
            except OpenAIError as exc:
                # Transport/rate-limit errors are retried; the message is logged, not surfaced.
                last_error = LLMProviderError("The AI provider returned an error.")
                logger.warning(
                    "openai_error", extra={"attempt": attempt, "error_type": type(exc).__name__}
                )
            if attempt < self._max_retries:
                await asyncio.sleep(min(2**attempt, 8))

        assert last_error is not None  # noqa: S101
        raise last_error
