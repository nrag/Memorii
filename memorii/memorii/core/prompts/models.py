from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PromptModelDefaults(BaseModel):
    provider: str = "openai"
    model: str | None = None
    temperature: float = 0.0
    max_tokens: int = 1000
    timeout_seconds: int | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, value: float) -> float:
        if value < 0.0 or value > 2.0:
            raise ValueError("temperature must be between 0.0 and 2.0")
        return value

    @field_validator("max_tokens")
    @classmethod
    def validate_max_tokens(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("max_tokens must be > 0")
        return value


class PromptRedactionPolicy(BaseModel):
    redact_input_fields: list[str] = Field(default_factory=list)
    redact_output_fields: list[str] = Field(default_factory=list)
    redact_metadata_fields: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class PromptContract(BaseModel):
    prompt_id: str
    version: str
    task: str
    description: str
    input_schema: dict[str, object]
    output_schema: dict[str, object]
    system_template: str
    user_template: str
    model_defaults: PromptModelDefaults
    redaction: PromptRedactionPolicy
    allowed_failure_modes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @field_validator("prompt_id", "version", "system_template", "user_template")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must be non-empty")
        return value


class RenderedPrompt(BaseModel):
    prompt_ref: str
    prompt_id: str
    version: str
    prompt_hash: str
    system: str
    user: str
    model_defaults: PromptModelDefaults
    expected_output_schema: dict[str, object]

    model_config = ConfigDict(extra="forbid")
