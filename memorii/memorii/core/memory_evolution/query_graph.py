"""Typed semantic graph constraints for production memory retrieval."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class GraphConstraintOperator(StrEnum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IN = "in"
    NOT_IN = "not_in"


class ResolvedEntityReference(BaseModel):
    """One server-catalog entity selected without residual ambiguity."""

    reference_kind: Literal["resolved"] = "resolved"
    entity_id: str = Field(min_length=1)
    mention: str | None = None
    expected_entity_types: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @field_validator("entity_id")
    @classmethod
    def validate_entity_id(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("entity IDs must not contain surrounding whitespace")
        return value


class AmbiguousEntityReference(BaseModel):
    """An unresolved mention with multiple plausible server-catalog entities."""

    reference_kind: Literal["ambiguous"] = "ambiguous"
    candidate_entity_ids: list[str] = Field(min_length=2)
    mention: str | None = None
    expected_entity_types: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @field_validator("candidate_entity_ids")
    @classmethod
    def validate_candidates(cls, values: list[str]) -> list[str]:
        candidates = list(dict.fromkeys(values))
        if len(candidates) < 2 or any(not value.strip() or value != value.strip() for value in candidates):
            raise ValueError("ambiguous references require at least two distinct non-empty candidates")
        return candidates


class UnresolvedEntityReference(BaseModel):
    """A mention or wildcard that has not been bound to a catalog entity."""

    reference_kind: Literal["unresolved"] = "unresolved"
    mention: str | None = None
    expected_entity_types: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ExplicitEntitySet(BaseModel):
    """An intentional set-valued query operand, distinct from ambiguity."""

    reference_kind: Literal["entity_set"] = "entity_set"
    entity_ids: list[str] = Field(min_length=1)
    mention: str | None = None
    expected_entity_types: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @field_validator("entity_ids")
    @classmethod
    def validate_entity_ids(cls, values: list[str]) -> list[str]:
        entity_ids = list(dict.fromkeys(values))
        if not entity_ids or any(not value.strip() or value != value.strip() for value in entity_ids):
            raise ValueError("entity sets require non-empty distinct IDs")
        return entity_ids


EntityReference = Annotated[
    ResolvedEntityReference | AmbiguousEntityReference | UnresolvedEntityReference | ExplicitEntitySet,
    Field(discriminator="reference_kind"),
]


class ObjectConstraint(BaseModel):
    """Entity-valued or literal-valued object constraint in a query pattern."""

    entity: EntityReference | None = None
    literal_value: str | None = None
    normalized_literal: str | None = None
    value_type: Literal["entity", "text", "boolean", "number", "date", "unknown"] = "unknown"
    operator: GraphConstraintOperator = GraphConstraintOperator.EQUALS

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_value(self) -> ObjectConstraint:
        if (self.entity is None) == (self.literal_value is None):
            raise ValueError("object constraint requires exactly one entity or literal value")
        if self.normalized_literal is not None and self.literal_value is None:
            raise ValueError("normalized_literal requires literal_value")
        if self.entity is not None:
            if isinstance(self.entity, ExplicitEntitySet):
                if self.operator not in {GraphConstraintOperator.IN, GraphConstraintOperator.NOT_IN}:
                    raise ValueError("explicit entity sets require an IN or NOT_IN operator")
            elif self.operator in {GraphConstraintOperator.IN, GraphConstraintOperator.NOT_IN}:
                raise ValueError("IN and NOT_IN require an explicit entity set")
        elif self.operator in {GraphConstraintOperator.IN, GraphConstraintOperator.NOT_IN}:
            raise ValueError("literal set operators require a typed literal-set representation")
        return self


class GraphPatternConstraint(BaseModel):
    """A supported single-hop outgoing graph pattern extracted from a query."""

    subject: EntityReference = Field(default_factory=UnresolvedEntityReference)
    predicate_id: str | None = None
    object: ObjectConstraint | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_pattern(self) -> GraphPatternConstraint:
        if self.object is not None and self.predicate_id is None:
            raise ValueError("object constraints require a predicate_id")
        if isinstance(self.subject, ExplicitEntitySet):
            raise ValueError("set-valued subjects are not supported")
        return self


class GraphCompilationFailureCode(StrEnum):
    AMBIGUOUS_SUBJECT = "ambiguous_subject"
    AMBIGUOUS_OBJECT = "ambiguous_object"
    UNRESOLVED_OBJECT = "unresolved_object"


class ExecutableObjectConstraint(BaseModel):
    operator: GraphConstraintOperator
    entity_ids: list[str] = Field(default_factory=list)
    literal_value: str | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_executable_value(self) -> ExecutableObjectConstraint:
        if bool(self.entity_ids) == (self.literal_value is not None):
            raise ValueError("executable object constraints require exactly one entity or literal operand")
        if len(self.entity_ids) != len(set(self.entity_ids)):
            raise ValueError("executable object entity IDs must be unique")
        if self.operator in {GraphConstraintOperator.IN, GraphConstraintOperator.NOT_IN}:
            if not self.entity_ids:
                raise ValueError("executable set operators require entity IDs")
        elif len(self.entity_ids) > 1:
            raise ValueError("non-set executable operators accept one entity ID")
        return self


class ExecutableGraphPattern(BaseModel):
    source_pattern: GraphPatternConstraint
    subject_entity_id: str | None = None
    predicate_id: str | None = None
    object_constraint: ExecutableObjectConstraint | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_executable_pattern(self) -> ExecutableGraphPattern:
        if self.object_constraint is not None and self.predicate_id is None:
            raise ValueError("executable object constraints require a predicate")
        return self


class ExecutableGraphQuery(BaseModel):
    patterns: list[ExecutableGraphPattern] = Field(min_length=1, max_length=3)

    model_config = ConfigDict(extra="forbid")


class GraphCompilationFailure(BaseModel):
    code: GraphCompilationFailureCode
    pattern: GraphPatternConstraint
    rationale: str

    model_config = ConfigDict(extra="forbid")


class GraphPatternResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    NO_MATCH = "no_match"
    UNSUPPORTED = "unsupported"


class GraphResolutionMethod(StrEnum):
    STRUCTURED_CONSTRAINT = "structured_constraint"
    LEXICAL_PARTICIPANT_FALLBACK = "lexical_participant_fallback"
    SUBJECT_FRAME_FALLBACK = "subject_frame_fallback"


class GraphPatternFailureReason(StrEnum):
    OBJECT_CONSTRAINT_NO_MATCH = "object_constraint_no_match"
    SUBJECT_CONSTRAINT_NO_MATCH = "subject_constraint_no_match"
    PREDICATE_UNRESOLVED = "predicate_unresolved"
    MULTIPLE_SUBJECTS_MATCH = "multiple_subjects_match"
    QUERY_SUBJECT_UNRESOLVED = "query_subject_unresolved"
    CONJUNCTION_NO_COMMON_SUBJECT = "conjunction_no_common_subject"
    AMBIGUOUS_ENTITY_REFERENCE = "ambiguous_entity_reference"
    UNRESOLVED_OBJECT_REFERENCE = "unresolved_object_reference"
    OPEN_WORLD_COMPARISON_UNKNOWN = "open_world_comparison_unknown"


class GraphPatternResolution(BaseModel):
    """Evidence-backed production resolution of a semantic graph pattern."""

    status: GraphPatternResolutionStatus
    resolution_method: GraphResolutionMethod
    pattern: GraphPatternConstraint
    conjunctive_patterns: list[GraphPatternConstraint] = Field(default_factory=list)
    subject_entity_id: str | None = None
    matched_claim_ids: list[str] = Field(default_factory=list)
    supporting_source_ids: list[str] = Field(default_factory=list)
    candidate_subject_entity_ids: list[str] = Field(default_factory=list)
    ambiguity_reasons: list[str] = Field(default_factory=list)
    failure_reasons: list[GraphPatternFailureReason] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
