"""Explicit semantic validation for structurally valid prompt outputs."""

from __future__ import annotations

from pydantic import BaseModel, ValidationError

from memorii.core.llm_validation import (
    LLMValidationIssue,
    LLMValidationStage,
    validation_issues_from_pydantic,
)
from memorii.core.prompts.runtime_manifest import (
    PromptRuntimeRegistration,
    PromptSemanticContract,
)


class PromptSemanticValidationError(ValueError):
    """A schema-valid provider output violates its domain contract."""

    def __init__(self, message: str, *, issues: tuple[LLMValidationIssue, ...]) -> None:
        super().__init__(message)
        self.issues = issues


def qualified_model_name(model: type[BaseModel]) -> str:
    return f"{model.__module__}.{model.__qualname__}"


def assert_semantic_contract_configuration(
    *,
    registration: PromptRuntimeRegistration,
    semantic_model: type[BaseModel] | None,
) -> None:
    expected = registration.semantic_contract
    if expected == PromptSemanticContract.NONE:
        if semantic_model is not None:
            raise ValueError(f"Prompt {registration.prompt_ref} does not declare a semantic model")
        return
    if semantic_model is None:
        raise ValueError(f"Prompt {registration.prompt_ref} requires semantic model {expected.value}")
    actual = qualified_model_name(semantic_model)
    if actual != expected.value:
        raise ValueError(f"Prompt {registration.prompt_ref} requires semantic model {expected.value}, not {actual}")


def validate_prompt_semantics(
    *,
    registration: PromptRuntimeRegistration,
    output: BaseModel,
    semantic_model: type[BaseModel] | None,
) -> None:
    assert_semantic_contract_configuration(
        registration=registration,
        semantic_model=semantic_model,
    )
    if semantic_model is None:
        return
    try:
        semantic_model.model_validate(output.model_dump(mode="python"))
    except ValidationError as exc:
        raise PromptSemanticValidationError(
            f"Prompt {registration.prompt_ref} output violates {registration.semantic_contract.value}",
            issues=validation_issues_from_pydantic(
                exc,
                stage=LLMValidationStage.SEMANTIC,
            ),
        ) from exc
