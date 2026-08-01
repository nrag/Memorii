"""Typed, serializable validation evidence for structured LLM decisions."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class LLMValidationStage(StrEnum):
    JSON = "json"
    SCHEMA = "schema"
    SEMANTIC = "semantic"
    DOMAIN = "domain"


class LLMValidationIssue(BaseModel):
    stage: LLMValidationStage
    code: str = Field(min_length=1)
    location: tuple[str | int, ...] = ()
    message: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)


def validation_issues_from_pydantic(
    error: ValidationError,
    *,
    stage: LLMValidationStage,
) -> tuple[LLMValidationIssue, ...]:
    """Return stable issue metadata without retaining rejected input values."""

    return tuple(
        LLMValidationIssue(
            stage=stage,
            code=str(item["type"]),
            location=tuple(item["loc"]),
            message=str(item["msg"]),
        )
        for item in error.errors(include_url=False, include_context=False, include_input=False)
    )


def domain_validation_issue(
    message: str,
    *,
    code: str = "domain_validation",
    location: tuple[str | int, ...] = (),
) -> LLMValidationIssue:
    return LLMValidationIssue(
        stage=LLMValidationStage.DOMAIN,
        code=code,
        location=location,
        message=message,
    )
