from __future__ import annotations

from typing import Any, cast

from jsonschema import Draft7Validator
from pydantic import BaseModel, ValidationError

from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.base import LLMProviderError, LLMStructuredClient
from memorii.core.llm_provider.models import LLMDecisionResult, LLMStructuredRequest, LLMStructuredResponse
from memorii.core.llm_provider.parser import parse_structured_response
from memorii.core.prompts.registry import RegisteredPromptContract
from memorii.core.prompts.render import PromptRenderer
from memorii.core.prompts.semantics import (
    PromptSemanticValidationError,
    assert_semantic_contract_configuration,
    validate_prompt_semantics,
)
from memorii.core.prompts.sensitivity import redact_sensitive_value


def _sanitize_metadata(metadata: dict[str, object] | None) -> dict[str, object]:
    redacted = redact_sensitive_value(metadata or {})
    if not isinstance(redacted, dict):
        raise TypeError("redacted metadata must remain a mapping")
    return redacted


class PromptLLMRunner:
    def __init__(
        self,
        *,
        client: LLMStructuredClient,
        config: LLMRuntimeConfig,
        renderer: PromptRenderer | None = None,
    ) -> None:
        self._client = client
        self._config = config
        self._renderer = renderer or PromptRenderer()

    def run(
        self,
        *,
        contract: RegisteredPromptContract,
        variables: dict[str, object],
        request_id: str,
        metadata: dict[str, object] | None = None,
        output_model: type[BaseModel] | None = None,
        semantic_model: type[BaseModel] | None = None,
    ) -> LLMDecisionResult:
        assert_semantic_contract_configuration(
            registration=contract.runtime_registration,
            semantic_model=semantic_model,
        )
        if semantic_model is not None and output_model is None:
            raise ValueError("semantic validation requires a transport output model")
        input_errors = sorted(
            Draft7Validator(contract.input_schema).iter_errors(cast(Any, variables)),
            key=lambda error: list(error.absolute_path),
        )
        if input_errors:
            details = "; ".join(error.message for error in input_errors[:3])
            raise ValueError(f"prompt input failed schema validation: {details}")
        rendered = self._renderer.render(contract=contract, variables=variables)
        request_metadata = _sanitize_metadata(metadata)
        request_metadata.update(
            {
                "prompt_ref": rendered.prompt_ref,
                "prompt_hash": rendered.prompt_hash,
                "provider": self._client.provider_name,
                "model": rendered.model_defaults.model,
            }
        )
        request = LLMStructuredRequest(
            request_id=request_id,
            prompt_ref=rendered.prompt_ref,
            prompt_hash=rendered.prompt_hash,
            system=rendered.system,
            user=rendered.user,
            output_schema=rendered.expected_output_schema,
            model_defaults=rendered.model_defaults,
            metadata=request_metadata,
        )
        try:
            raw_response = self._client.complete_structured(request, config=self._config)
        except LLMProviderError as exc:
            failed_response = LLMStructuredResponse(
                request_id=request_id,
                provider=self._client.provider_name,
                requested_model=rendered.model_defaults.model or self._config.model,
                effective_settings={
                    "temperature": rendered.model_defaults.temperature,
                    "max_output_tokens": rendered.model_defaults.max_tokens,
                    "timeout_seconds": rendered.model_defaults.timeout_seconds or self._config.timeout_seconds,
                },
                attempt_count=1 if self._config.max_retries == 0 else None,
                sdk_max_retries=self._config.max_retries,
                raw_text="",
                valid_json=False,
                schema_valid=False,
                error=f"Provider request failed: {type(exc).__name__}",
            )
            return LLMDecisionResult(
                request=request, response=failed_response, output=None, success=False, failure_mode="provider_error"
            )

        if raw_response.request_id != request_id:
            mismatch_response = raw_response.model_copy(
                update={
                    "request_id": request_id,
                    "valid_json": False,
                    "schema_valid": False,
                    "parsed_json": None,
                    "error": "Provider returned mismatched request identifier.",
                }
            )
            return LLMDecisionResult(
                request=request, response=mismatch_response, output=None, success=False, failure_mode="provider_error"
            )

        parsed_response = parse_structured_response(
            response=raw_response, output_schema=rendered.expected_output_schema
        )
        success = (
            parsed_response.valid_json and parsed_response.schema_valid and parsed_response.parsed_json is not None
        )
        parsed_output = parsed_response.parsed_json
        rejected_output: dict[str, object] | None = None
        validation_issues = []
        failure_mode: str | None = None
        if success and output_model is not None:
            try:
                transport_output = output_model.model_validate(parsed_output)
                parsed_output = transport_output.model_dump(mode="json")
            except ValidationError as exc:
                parsed_response = parsed_response.model_copy(
                    update={
                        "schema_valid": False,
                        "error": f"Transport output validation failed: {type(exc).__name__}",
                    }
                )
                success = False
                failure_mode = "schema_validation"
            else:
                try:
                    validate_prompt_semantics(
                        registration=contract.runtime_registration,
                        output=transport_output,
                        semantic_model=semantic_model,
                    )
                except PromptSemanticValidationError as exc:
                    redacted_output = redact_sensitive_value(parsed_output)
                    if not isinstance(redacted_output, dict):
                        raise TypeError(
                            "redacted structured output must remain a mapping"
                        ) from exc
                    rejected_output = redacted_output
                    validation_issues = list(exc.issues)
                    parsed_response = parsed_response.model_copy(
                        update={
                            "semantic_valid": False,
                            "error": f"Semantic output validation failed: {type(exc).__name__}",
                        }
                    )
                    success = False
                    failure_mode = "semantic_validation"
                else:
                    if semantic_model is not None:
                        parsed_response = parsed_response.model_copy(update={"semantic_valid": True})
        if not success and failure_mode is None:
            failure_mode = "invalid_json" if not parsed_response.valid_json else "schema_validation"
        return LLMDecisionResult(
            request=request,
            response=parsed_response,
            output=parsed_output if success else None,
            rejected_output=rejected_output,
            validation_issues=validation_issues,
            success=success,
            failure_mode=failure_mode,
        )
