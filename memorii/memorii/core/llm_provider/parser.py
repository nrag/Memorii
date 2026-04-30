from __future__ import annotations

import json

from jsonschema import ValidationError, validate

from memorii.core.llm_provider.models import LLMStructuredResponse


def parse_structured_response(
    *,
    response: LLMStructuredResponse,
    output_schema: dict[str, object],
) -> LLMStructuredResponse:
    try:
        parsed = json.loads(response.raw_text)
    except json.JSONDecodeError:
        return response.model_copy(update={"valid_json": False, "schema_valid": False, "parsed_json": None, "error": "Response was not valid JSON."})

    if not isinstance(parsed, dict):
        return response.model_copy(update={"valid_json": False, "schema_valid": False, "parsed_json": None, "error": "Response JSON must be an object."})

    try:
        validate(instance=parsed, schema=output_schema)
    except ValidationError as exc:
        return response.model_copy(update={"valid_json": True, "schema_valid": False, "parsed_json": parsed, "error": f"Schema validation failed: {exc.message}"})

    return response.model_copy(update={"valid_json": True, "schema_valid": True, "parsed_json": parsed, "error": None})
