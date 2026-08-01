from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.llm_validation import LLMValidationIssue
from memorii.core.prompts.models import PromptModelDefaults


class LLMStructuredRequest(BaseModel):
    request_id: str
    prompt_ref: str
    prompt_hash: str
    system: str
    user: str
    output_schema: dict[str, object]
    model_defaults: PromptModelDefaults
    metadata: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class LLMStructuredResponse(BaseModel):
    request_id: str
    provider: str
    requested_model: str | None = None
    actual_model: str | None = None
    provider_request_id: str | None = None
    response_status: str | None = None
    finish_reason: str | None = None
    sdk_version: str | None = None
    effective_settings: dict[str, object] = Field(default_factory=dict)
    attempt_count: int | None = Field(default=None, ge=1)
    sdk_max_retries: int = Field(default=0, ge=0)
    raw_text: str
    parsed_json: dict[str, object] | None = None
    valid_json: bool
    schema_valid: bool
    semantic_valid: bool | None = None
    refusal: str | None = None
    error: str | None = None
    usage: dict[str, object] = Field(default_factory=dict)
    latency_ms: int | None = None

    model_config = ConfigDict(extra="forbid")


class LLMDecisionResult(BaseModel):
    request: LLMStructuredRequest
    response: LLMStructuredResponse
    output: dict[str, object] | None
    rejected_output: dict[str, object] | None = None
    validation_issues: list[LLMValidationIssue] = Field(default_factory=list)
    success: bool
    failure_mode: str | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_semantic_rejection_evidence(self) -> LLMDecisionResult:
        if self.success and (self.rejected_output is not None or self.validation_issues):
            raise ValueError("successful decisions cannot carry rejected-output evidence")
        if self.failure_mode == "semantic_validation":
            if self.output is not None:
                raise ValueError("semantic rejection cannot expose accepted output")
            if self.rejected_output is None or not self.validation_issues:
                raise ValueError("semantic rejection requires rejected output and validation issues")
        return self
