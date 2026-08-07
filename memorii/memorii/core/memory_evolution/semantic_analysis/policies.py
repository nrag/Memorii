"""Closed, content-addressed language construction policies."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value

Commitment = Literal["asserted", "believed", "reported", "quoted", "questioned", "instructed", "hypothetical"]


class _CanonicalMap(dict[str, object]):
    """Map-shaped but hashable CTV member for frozensets of policy models."""

    def __hash__(self) -> int:
        return hash(encode_typed_value(dict(self)))


def _digest(domain: bytes, body: object) -> str:
    return sha256(domain + b"\0" + encode_typed_value(_canonical(body))).hexdigest()


def _canonical(value: object) -> object:
    if isinstance(value, BaseModel):
        return _CanonicalMap({name: _canonical(getattr(value, name)) for name in type(value).model_fields})
    if isinstance(value, tuple):
        return tuple(_canonical(item) for item in value)
    if isinstance(value, frozenset):
        return frozenset(_canonical(item) for item in value)
    if isinstance(value, dict):
        return _CanonicalMap({key: _canonical(item) for key, item in value.items()})
    return value


class _ContentAddressedPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    _digest_domain: ClassVar[bytes]
    _digest_field: ClassVar[str]

    @model_validator(mode="after")
    def validate_content_digest(self):
        body = {name: getattr(self, name) for name in type(self).model_fields if name != self._digest_field}
        if getattr(self, self._digest_field) != _digest(self._digest_domain, body):
            raise ValueError("semantic analysis policy digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object):  # type: ignore[no-untyped-def]
        return cls(**values, **{cls._digest_field: _digest(cls._digest_domain, values)})


class ConstructionFamily(_ContentAddressedPolicy):
    family_id: str = Field(min_length=1)
    family_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.construction-family.v1"
    _digest_field = "family_digest"


class UdPathStep(BaseModel):
    direction: Literal["up", "down"]
    dependency_label: str = Field(min_length=1)
    ordinal: int | None = Field(ge=0)
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class UdPathPattern(_ContentAddressedPolicy):
    anchor: Literal["predicate_head", "role_head", "clause_head"]
    steps: tuple[UdPathStep, ...]
    pattern_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.ud-path-pattern.v1"
    _digest_field = "pattern_digest"

    @model_validator(mode="after")
    def validate_steps(self):
        ordinals = tuple(step.ordinal for step in self.steps if step.ordinal is not None)
        if len(ordinals) != len(set(ordinals)):
            raise ValueError("UD path step ordinals must be unique")
        return self


class QuotationBoundaryPolicy(_ContentAddressedPolicy):
    mode: Literal["outside_quoted_content", "inside_quoted_content", "allow_nested_quotation"]
    policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.quotation-boundary-policy.v1"
    _digest_field = "policy_digest"


def _canonical_patterns(values: tuple[UdPathPattern, ...], label: str) -> None:
    keys = tuple(value.pattern_digest for value in values)
    if keys != tuple(sorted(keys)) or len(set(keys)) != len(keys):
        raise ValueError(f"{label} must be canonical and unique")


class SemanticScopePolicy(_ContentAddressedPolicy):
    language: str = Field(min_length=1)
    construction_family: ConstructionFamily
    predicate_family: str = Field(min_length=1)
    allowed_predicate_ancestor_paths: tuple[UdPathPattern, ...]
    negation_bearer_patterns: tuple[UdPathPattern, ...]
    embedding_head_lemmas: Mapping[str, Commitment]
    reporting_head_lemmas: frozenset[str]
    question_mood_features: frozenset[str]
    quotation_boundary_policy: QuotationBoundaryPolicy
    temporal_attachment_patterns: tuple[UdPathPattern, ...]
    forbidden_clause_crossings: frozenset[str]
    policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.semantic-scope-policy.v1"
    _digest_field = "policy_fingerprint"

    @model_validator(mode="after")
    def validate_policy(self):
        for values, label in (
            (self.allowed_predicate_ancestor_paths, "allowed predicate paths"),
            (self.negation_bearer_patterns, "negation patterns"),
            (self.temporal_attachment_patterns, "temporal attachment patterns"),
        ):
            _canonical_patterns(values, label)
        if any(not lemma for lemma in self.embedding_head_lemmas):
            raise ValueError("embedding head lemmas must have nonempty keys")
        for values in (self.reporting_head_lemmas, self.question_mood_features, self.forbidden_clause_crossings):
            if any(not value for value in values):
                raise ValueError("semantic scope set members must be nonempty")
        return self


class UdRoleSchema(_ContentAddressedPolicy):
    role_id: str = Field(min_length=1)
    anchor_form: Literal["verbal", "nominal"]
    allowed_dependency_paths: tuple[UdPathPattern, ...]
    required_function_word_lemmas: frozenset[str]
    forbidden_clause_crossings: frozenset[str]
    coordination_support: Literal["allowed", "forbidden"]
    voice_normalization: Literal["active_only", "active_passive_equivalent"]
    canonical_graph_role: str = Field(min_length=1)
    required_polarity_evidence: Literal["not_required", "must_support_positive", "must_support_negative"]
    required_commitment_evidence: frozenset[Commitment]
    schema_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.ud-role-schema.v1"
    _digest_field = "schema_digest"

    @model_validator(mode="after")
    def validate_schema(self):
        _canonical_patterns(self.allowed_dependency_paths, "allowed dependency paths")
        if any(not value for value in self.required_function_word_lemmas | self.forbidden_clause_crossings):
            raise ValueError("role schema set members must be nonempty")
        return self


class PredicateSemanticPolicy(_ContentAddressedPolicy):
    predicate_id: str = Field(min_length=1)
    language: str = Field(min_length=1)
    predicate_lemmas: frozenset[str]
    nominal_lemmas: frozenset[str]
    role_schemas: tuple[UdRoleSchema, ...]
    verbalizer_id: str | None
    supported_commitments: frozenset[Commitment]
    supported_constructions: frozenset[ConstructionFamily]
    policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.predicate-semantic-policy.v1"
    _digest_field = "policy_fingerprint"

    @model_validator(mode="before")
    @classmethod
    def restore_construction_set(cls, value: object):
        if isinstance(value, dict) and isinstance(value.get("supported_constructions"), frozenset):
            return {
                **value,
                "supported_constructions": frozenset(
                    item if isinstance(item, ConstructionFamily) else ConstructionFamily.model_validate(dict(item))
                    for item in value["supported_constructions"]
                ),
            }
        return value

    @model_validator(mode="after")
    def validate_policy(self):
        if not self.predicate_lemmas or any(not value for value in self.predicate_lemmas | self.nominal_lemmas):
            raise ValueError("predicate lemmas must be nonempty")
        keys = tuple((value.role_id, value.schema_digest) for value in self.role_schemas)
        if not keys or keys != tuple(sorted(keys)) or len({value.role_id for value in self.role_schemas}) != len(keys):
            raise ValueError("role schemas must be canonical and role-id unique")
        families = tuple(sorted((value.family_id, value.family_digest) for value in self.supported_constructions))
        if not families or len({value.family_id for value in self.supported_constructions}) != len(families):
            raise ValueError("supported constructions must be nonempty and family-id unique")
        return self

    @model_serializer(mode="plain")
    def serialize_policy(self) -> dict[str, object]:
        return {
            "predicate_id": self.predicate_id,
            "language": self.language,
            "predicate_lemmas": self.predicate_lemmas,
            "nominal_lemmas": self.nominal_lemmas,
            "role_schemas": self.role_schemas,
            "verbalizer_id": self.verbalizer_id,
            "supported_commitments": self.supported_commitments,
            "supported_constructions": frozenset(
                _CanonicalMap({name: getattr(value, name) for name in type(value).model_fields})
                for value in self.supported_constructions
            ),
            "policy_fingerprint": self.policy_fingerprint,
        }
