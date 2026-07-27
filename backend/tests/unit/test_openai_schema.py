"""The OpenAI strict-schema adaptation.

OpenAI structured-output strict mode requires every object to list all properties in `required`
and to set `additionalProperties: false`. Pydantic marks only no-default fields as required, so
`_strictify` fills the gap. These were real 400s hit on the first live run.
"""

from __future__ import annotations

from app.ai.providers.openai_provider import _strictify
from app.ai.structured_models import ExtractedMetadata, RequirementBatch


def test_all_optional_object_gets_every_key_required() -> None:
    # ExtractedMetadata is all-optional; Pydantic emits an empty `required`.
    strict = _strictify(ExtractedMetadata.model_json_schema())
    assert set(strict["required"]) == set(strict["properties"].keys())
    assert strict["additionalProperties"] is False


def test_nested_defs_are_strictified() -> None:
    strict = _strictify(RequirementBatch.model_json_schema())
    for definition in strict.get("$defs", {}).values():
        if definition.get("type") == "object" and "properties" in definition:
            assert set(definition["required"]) == set(definition["properties"].keys())
            assert definition["additionalProperties"] is False


def test_original_schema_is_not_mutated() -> None:
    original = ExtractedMetadata.model_json_schema()
    before = original.get("required", [])
    _strictify(original)
    assert original.get("required", []) == before  # deep-copied, not mutated in place
