"""Closed contracts and package-bound declarations for catalog reads."""

from __future__ import annotations

import re
import unicodedata
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
)

from memorii.core.semantic_ingestion.catalog_authority import CatalogAuthorityError
from memorii.core.semantic_ingestion.catalog_capture_pin import (
    SeedCatalogBundleLocator,
    VerifiedCatalogBundle,
)
from memorii.core.semantic_ingestion.default_catalog_corpus import (
    load_default_catalog_acceptance_corpus,
)
from memorii.core.semantic_ingestion.default_catalog_package import load_packaged_default_catalog_release
from memorii.core.semantic_ingestion.structured_fact_read import StructuredFactReadItem

_PredicateId = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")]
_Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class _ClosedReadModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _PredicateLookup(_ClosedReadModel):
    kind: Literal["predicate_id"]
    predicate_id: _PredicateId


class _NameLookup(_ClosedReadModel):
    kind: Literal["name"]
    name: str

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9 _-]{1,128}", value) or not normalize_relation_name(value):
            raise ValueError("invalid catalog relation name")
        return value


class CatalogRelationInspectionRequest(
    RootModel[Annotated[_PredicateLookup | _NameLookup, Field(discriminator="kind")]]
):
    model_config = ConfigDict(frozen=True)


class _ExactRecall(_ClosedReadModel):
    kind: Literal["exact"]
    predicate_id: _PredicateId
    subject_entity_id: str
    expected_catalog_version_digest: _Digest | None = None

    @field_validator("expected_catalog_version_digest", mode="before")
    @classmethod
    def reject_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("catalog version expectation must be omitted or a digest")
        return value

    @model_serializer(mode="wrap")
    def serialize_exact(self, serialize: SerializerFunctionWrapHandler) -> dict[str, object]:
        serialized = serialize(self)
        if self.expected_catalog_version_digest is None:
            serialized.pop("expected_catalog_version_digest", None)
        return serialized

    @field_validator("subject_entity_id")
    @classmethod
    def valid_subject(cls, value: str) -> str:
        if (
            not 1 <= len(value.encode("utf-8")) <= 1024
            or value != value.strip()
            or value == "*"
            or any(unicodedata.category(character) == "Cc" for character in value)
        ):
            raise ValueError("invalid canonical subject ID")
        return value


class _UnresolvedRecall(_ClosedReadModel):
    kind: Literal["unresolved"]
    reference: Literal["subject", "relation", "both"]


class StructuredRecallDiagnosisRequest(
    RootModel[Annotated[_ExactRecall | _UnresolvedRecall, Field(discriminator="kind")]]
):
    model_config = ConfigDict(frozen=True)


class CatalogReadStatus(StrEnum):
    MATCHED = "matched"
    AMBIGUOUS = "ambiguous"
    NO_MATCH = "no_match"
    FOUND = "found"
    NO_READABLE_FACT = "no_readable_fact"
    UNSUPPORTED_PREDICATE = "unsupported_predicate"
    CATALOG_CHANGED = "catalog_changed"
    NEEDS_CLARIFICATION = "needs_clarification"
    INVALID_REQUEST = "invalid_request"
    DENIED = "denied"
    UNAVAILABLE = "unavailable"


class CatalogReadDirection(StrEnum):
    FORWARD_ONLY = "forward_only"
    SYMMETRIC_VIEW = "symmetric_view"


class CatalogReadForm(StrEnum):
    SET = "set"
    CURRENT = "current"
    HISTORY = "history"


class _EntityEndpoint(_ClosedReadModel):
    kind: Literal["entity"] = "entity"
    type_ids: tuple[str, ...] = Field(min_length=1)


class _LiteralEndpoint(_ClosedReadModel):
    kind: Literal["literal"] = "literal"
    value_type: Literal["LocalDate", "StatusText", "TimeInterval", "Money"]


class CatalogRelationDescriptor(_ClosedReadModel):
    predicate_id: _PredicateId
    label: str
    lookup_aliases: tuple[str, ...]
    definition: str
    subject_type_ids: tuple[str, ...] = Field(min_length=1)
    object_endpoint: Annotated[_EntityEndpoint | _LiteralEndpoint, Field(discriminator="kind")]
    read_direction: CatalogReadDirection
    read_form: CatalogReadForm

    @field_validator("definition")
    @classmethod
    def valid_definition(cls, value: str) -> str:
        if not value.strip() or len(value.encode("utf-8")) > 4096:
            raise ValueError("invalid catalog definition")
        return value


class _MatchedRelations(_ClosedReadModel):
    status: Literal[CatalogReadStatus.MATCHED]
    catalog_version_digest: _Digest
    relations: tuple[CatalogRelationDescriptor] = Field(min_length=1, max_length=1)


class _AmbiguousRelations(_ClosedReadModel):
    status: Literal[CatalogReadStatus.AMBIGUOUS]
    catalog_version_digest: _Digest
    relations: tuple[CatalogRelationDescriptor, ...] = Field(min_length=2)

    @field_validator("relations")
    @classmethod
    def ordered_unique(cls, value: tuple[CatalogRelationDescriptor, ...]) -> tuple[CatalogRelationDescriptor, ...]:
        ids = tuple(relation.predicate_id for relation in value)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("catalog matches must be unique and ordered")
        return value


class _EmptyInspection(_ClosedReadModel):
    status: Literal[
        CatalogReadStatus.NO_MATCH,
        CatalogReadStatus.INVALID_REQUEST,
        CatalogReadStatus.DENIED,
        CatalogReadStatus.UNAVAILABLE,
    ]


class CatalogRelationInspectionResponse(
    RootModel[Annotated[_MatchedRelations | _AmbiguousRelations | _EmptyInspection, Field(discriminator="status")]]
):
    model_config = ConfigDict(frozen=True)

    @property
    def status(self) -> CatalogReadStatus:
        return self.root.status

    @property
    def relations(self) -> tuple[CatalogRelationDescriptor, ...]:
        return () if isinstance(self.root, _EmptyInspection) else self.root.relations

    @property
    def catalog_version_digest(self) -> str | None:
        return None if isinstance(self.root, _EmptyInspection) else self.root.catalog_version_digest


class _FoundRecall(_ClosedReadModel):
    status: Literal[CatalogReadStatus.FOUND]
    items: tuple[StructuredFactReadItem, ...] = Field(min_length=1)


class _EmptyRecall(_ClosedReadModel):
    status: Literal[
        CatalogReadStatus.NO_READABLE_FACT,
        CatalogReadStatus.UNSUPPORTED_PREDICATE,
        CatalogReadStatus.CATALOG_CHANGED,
        CatalogReadStatus.NEEDS_CLARIFICATION,
        CatalogReadStatus.INVALID_REQUEST,
        CatalogReadStatus.DENIED,
        CatalogReadStatus.UNAVAILABLE,
    ]


class StructuredRecallDiagnosisResponse(
    RootModel[Annotated[_FoundRecall | _EmptyRecall, Field(discriminator="status")]]
):
    model_config = ConfigDict(frozen=True)

    @property
    def status(self) -> CatalogReadStatus:
        return self.root.status

    @property
    def items(self) -> tuple[StructuredFactReadItem, ...]:
        return () if isinstance(self.root, _EmptyRecall) else self.root.items


def normalize_relation_name(value: str) -> str:
    return re.sub(r"[ _-]+", " ", value.lower()).strip()


_DEFAULT_ALIASES = {
    "project_owned_by": ("project owner",),
    "obligation_due_on": ("bill due date",),
    "work_item_due_on": ("work item due date",),
}


def project_catalog_relations(bundle: VerifiedCatalogBundle) -> tuple[CatalogRelationDescriptor, ...]:
    """Project the complete declaration set for the exact verified packaged tuple."""
    seed = SeedCatalogBundleLocator().locate()
    seed_selected = bundle.version == seed.version and bundle.runtime_bundle_digest == seed.runtime_bundle_digest
    seed_subject = ("ProjectId",)
    relations = [
        CatalogRelationDescriptor(
            predicate_id=predicate,
            label=predicate.replace("_", " "),
            lookup_aliases=(),
            definition=definition,
            subject_type_ids=seed_subject,
            object_endpoint=endpoint,
            read_direction=CatalogReadDirection.FORWARD_ONLY,
            read_form=CatalogReadForm.CURRENT,
        )
        for predicate, definition, endpoint in (
            ("project_owner", "One current person named as the project's owner.", _EntityEndpoint(type_ids=("PersonName",))),
            ("project_deadline", "One current calendar deadline for the project.", _LiteralEndpoint(value_type="LocalDate")),
            ("project_status", "One current reported status for the project.", _LiteralEndpoint(value_type="StatusText")),
        )
    ]
    if not seed_selected:
        default = load_packaged_default_catalog_release()
        if bundle.version != default.child_version or bundle.runtime_bundle_digest != default.runtime_bundle_digest:
            raise CatalogAuthorityError("catalog declaration projection is unavailable")
        corpus = load_default_catalog_acceptance_corpus()
        for row in corpus.rows:
            relations.append(CatalogRelationDescriptor(
                predicate_id=row.relation_id,
                label=row.relation_id.replace("_", " "),
                lookup_aliases=_DEFAULT_ALIASES.get(row.relation_id, ()),
                definition=row.meaning,
                subject_type_ids=row.subject_type_ids,
                object_endpoint=(
                    _LiteralEndpoint(value_type=row.object_value_type)
                    if row.object_value_type is not None
                    else _EntityEndpoint(type_ids=row.object_entity_type_ids)
                ),
                read_direction=(
                    CatalogReadDirection.SYMMETRIC_VIEW
                    if row.read_derivation_policy == "symmetric_view"
                    else CatalogReadDirection.FORWARD_ONLY
                ),
                read_form=CatalogReadForm(row.read_form),
            ))
    ordered = tuple(sorted(relations, key=lambda relation: relation.predicate_id))
    ids = tuple(relation.predicate_id for relation in ordered)
    if ids != tuple(sorted(set(ids))) or ids != getattr(bundle.version, "predicate_ids", ()):
        raise CatalogAuthorityError("catalog declaration projection is incomplete")
    return ordered
