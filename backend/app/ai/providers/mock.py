"""Scriptable mock provider for the test suite and the offline demo.

Tests queue responses (or exceptions) and assert on the prompts the pipeline sent. This keeps
the whole suite free of network calls and API keys — live provider behaviour is covered only by
manual, cost-controlled checks (`docs/07` §1).
"""

from __future__ import annotations

from collections import deque

from app.ai.providers.base import LLMProviderError, LLMResponse


class ScriptedResponse:
    """A queued reply: either JSON content or an exception to raise."""

    def __init__(
        self,
        content: str | None = None,
        *,
        error: Exception | None = None,
        input_tokens: int = 100,
        output_tokens: int = 200,
    ) -> None:
        self.content = content
        self.error = error
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class MockLLMProvider:
    """Returns queued responses in order and records the calls it received."""

    def __init__(
        self, responses: list[ScriptedResponse] | None = None, *, model: str = "mock-model"
    ) -> None:
        self._responses: deque[ScriptedResponse] = deque(responses or [])
        self.model = model
        self.provider_name = "mock"
        self.calls: list[dict[str, str]] = []

    def queue(self, *responses: ScriptedResponse) -> None:
        self._responses.extend(responses)

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, object],
        schema_name: str,
        temperature: float | None = None,
    ) -> LLMResponse:
        self.calls.append({"system": system, "user": user, "schema_name": schema_name})
        if not self._responses:
            raise AssertionError("MockLLMProvider received an unexpected call")
        scripted = self._responses.popleft()
        if scripted.error is not None:
            raise scripted.error
        assert scripted.content is not None  # noqa: S101
        return LLMResponse(
            content=scripted.content,
            input_tokens=scripted.input_tokens,
            output_tokens=scripted.output_tokens,
            provider="mock",
            model=self.model,
        )


class RoutedMockProvider:
    """Answers by schema name, so any number of runs get a consistent canned response.

    Used by API tests that trigger multiple analyses (new version, retry); the queue-based
    `MockLLMProvider` remains for tests that assert on an exact call sequence (retries, errors).
    """

    def __init__(self, content_by_schema: dict[str, str], *, model: str = "mock-model") -> None:
        self._content = content_by_schema
        self.model = model
        self.provider_name = "mock"
        self.calls: list[dict[str, str]] = []

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, object],
        schema_name: str,
        temperature: float | None = None,
    ) -> LLMResponse:
        self.calls.append({"schema_name": schema_name, "user": user})
        if schema_name not in self._content:
            raise AssertionError(f"RoutedMockProvider has no response for {schema_name!r}")
        return LLMResponse(
            content=self._content[schema_name],
            input_tokens=100,
            output_tokens=200,
            provider="mock",
            model=self.model,
        )


def raising(exc: Exception) -> ScriptedResponse:
    return ScriptedResponse(error=exc)


def transient_then(content: str) -> list[ScriptedResponse]:
    """A transient failure followed by success — for retry tests."""
    return [ScriptedResponse(error=LLMProviderError("transient")), ScriptedResponse(content)]
