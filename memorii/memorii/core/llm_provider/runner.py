from __future__ import annotations

from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.base import LLMStructuredClient
from memorii.core.llm_provider.models import LLMDecisionResult, LLMStructuredRequest, LLMStructuredResponse
from memorii.core.llm_provider.parser import parse_structured_response
from memorii.core.prompts.models import PromptContract
from memorii.core.prompts.render import PromptRenderer

_SECRET_METADATA_KEYS = {"api_key", "apikey", "token", "password", "secret", "authorization", "cookie"}


def _sanitize_metadata(metadata: dict[str, object] | None) -> dict[str, object]:
    cleaned: dict[str, object] = {}
    for key, value in (metadata or {}).items():
        if key.lower() in _SECRET_METADATA_KEYS:
            cleaned[key] = "[REDACTED]"
        else:
            cleaned[key] = value
    return cleaned


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
        contract: PromptContract,
        variables: dict[str, object],
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
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
        except Exception as exc:
            failed_response = LLMStructuredResponse(
                request_id=request_id,
                provider=self._client.provider_name,
                raw_text="",
                valid_json=False,
                schema_valid=False,
                error=f"Provider request failed: {type(exc).__name__}",
            )
            return LLMDecisionResult(request=request, response=failed_response, output=None, success=False, failure_mode="provider_error")

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
            return LLMDecisionResult(request=request, response=mismatch_response, output=None, success=False, failure_mode="provider_error")

        parsed_response = parse_structured_response(response=raw_response, output_schema=rendered.expected_output_schema)
        success = parsed_response.valid_json and parsed_response.schema_valid and parsed_response.parsed_json is not None
        failure_mode = None if success else ("invalid_json" if not parsed_response.valid_json else "schema_validation")
        return LLMDecisionResult(
            request=request,
            response=parsed_response,
            output=parsed_response.parsed_json if success else None,
            success=success,
            failure_mode=failure_mode,
        )
