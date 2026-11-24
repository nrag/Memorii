"""Closed, verified representations for durable consolidation results."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from hashlib import sha256
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value, length_prefixed

_RESULT_DOMAIN = b"memorii.consolidation-result.v1"
_OUTPUT_DOMAIN = b"memorii.consolidation-output.v1"
_DELIVERY_DOMAIN = b"memorii.runtime-delivery.v1"
_MAX_BATCH_BYTES = 10 * 1024 * 1024
MAX_CONSOLIDATION_SOURCE_REFERENCES = 64

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Revision = Annotated[int, Field(ge=0, strict=True)]
CandidateKind = Literal["episodic_summary", "skill_candidate", "semantic_candidate", "user_candidate"]
DeliveryKind = Literal["work_projection", "writeback_candidate"]

_OUTPUT_ORDER = (
    "episodic_summary",
    "skill_candidate",
    "semantic_candidate",
    "user_candidate",
    "unresolved_follow_up_summary",
    "archive_package",
)


def _bounded_text(value: str) -> str:
    if not value.strip() or len(value.encode("utf-8")) > 4 * 1024:
        raise ValueError("text must be nonblank and at most 4 KiB UTF-8")
    return value


BoundedText = Annotated[str, AfterValidator(_bounded_text)]


class _FrozenRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


class ConsolidationSourceReference(_FrozenRecord):
    source_id: BoundedText
    source_digest: Digest


def _unique_sources(
    entries: tuple[ConsolidationSourceReference, ...],
) -> tuple[ConsolidationSourceReference, ...]:
    if len({entry.source_id for entry in entries}) != len(entries):
        raise ValueError("source coordinates must be unique")
    return entries


SourceReferences = Annotated[
    tuple[ConsolidationSourceReference, ...],
    Field(max_length=MAX_CONSOLIDATION_SOURCE_REFERENCES),
    AfterValidator(_unique_sources),
]


class _Candidate(_FrozenRecord):
    source_refs: SourceReferences = ()
    solver_run_id: BoundedText | None = None
    execution_node_id: BoundedText | None = None
    # Durable candidates are derived data. Source admission and promotion are
    # separate owners; neither caller-supplied status nor native provenance fits here.
    provenance: Literal["derived"] = "derived"


class EpisodicSummary(_Candidate):
    kind: Literal["episodic_summary"] = "episodic_summary"
    summary: BoundedText


class SkillCandidate(_Candidate):
    kind: Literal["skill_candidate"] = "skill_candidate"
    title: BoundedText
    summary: BoundedText
    steps: tuple[BoundedText, ...] = Field(min_length=1, max_length=32)


class SemanticCandidate(_Candidate):
    kind: Literal["semantic_candidate"] = "semantic_candidate"
    abstraction: BoundedText


class UserCandidate(_Candidate):
    kind: Literal["user_candidate"] = "user_candidate"
    preference: BoundedText
    valid_from: AwareDatetime | None = None
    valid_to: AwareDatetime | None = None

    @model_validator(mode="after")
    def _validate_window(self) -> Self:
        if self.valid_from is not None and self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("validity window cannot end before it starts")
        return self


class FollowUpItem(_FrozenRecord):
    node_id: BoundedText
    reason: BoundedText
    source_refs: SourceReferences = ()


class UnresolvedFollowUpSummary(_FrozenRecord):
    kind: Literal["unresolved_follow_up_summary"] = "unresolved_follow_up_summary"
    items: tuple[FollowUpItem, ...] = Field(default=(), max_length=32)
    truncated: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def _validate_sources(self) -> Self:
        if sum(len(item.source_refs) for item in self.items) > 64:
            raise ValueError("a follow-up summary may contain at most 64 source references")
        return self


class ArchivePackageRef(_FrozenRecord):
    installation_id: BoundedText
    partition_id: BoundedText
    task_id: BoundedText
    origin_revision: Revision
    checkpoint_id: BoundedText
    checkpoint_digest: Digest
    manifest_id: BoundedText
    manifest_digest: Digest


class ArchivePackage(_FrozenRecord):
    kind: Literal["archive_package"] = "archive_package"
    reference: ArchivePackageRef


ConsolidationPayload = Annotated[
    EpisodicSummary | SkillCandidate | SemanticCandidate | UserCandidate | UnresolvedFollowUpSummary | ArchivePackage,
    Field(discriminator="kind"),
]


class ConsolidationOmission(_FrozenRecord):
    kind: CandidateKind
    reason: Literal["insufficient_evidence", "policy_denied"]


class ConsolidationOrigin(_FrozenRecord):
    installation_id: BoundedText
    partition_id: BoundedText
    operation_generation: BoundedText
    task_id: BoundedText
    client_namespace: BoundedText
    operation_id: BoundedText
    request_digest: Digest

    def coordinate(self) -> tuple[str, ...]:
        return (
            self.installation_id,
            self.partition_id,
            self.operation_generation,
            self.task_id,
            self.client_namespace,
            self.operation_id,
            self.request_digest,
        )


class ConsolidationOutput(_FrozenRecord):
    output_id: Digest
    ordinal: Revision
    payload_digest: Digest
    payload: ConsolidationPayload


def _identity(domain: bytes, coordinate: tuple[object, ...]) -> str:
    return sha256(length_prefixed(domain, encode_typed_value(coordinate))).hexdigest()


def runtime_delivery_id(
    partition_id: str,
    target_kind: DeliveryKind,
    coordinate: str | ConsolidationOrigin,
) -> str:
    """Derive an ID from an output or the full origin of a work projection."""
    value: str | tuple[str, ...]
    if target_kind == "work_projection":
        if not isinstance(coordinate, ConsolidationOrigin) or coordinate.partition_id != partition_id:
            raise ValueError("work projection requires its origin in the target partition")
        value = coordinate.coordinate()
    elif target_kind == "writeback_candidate":
        if (
            not isinstance(coordinate, str)
            or len(coordinate) != 64
            or any(c not in "0123456789abcdef" for c in coordinate)
        ):
            raise ValueError("candidate delivery requires its consolidation output ID")
        value = coordinate
    else:
        raise ValueError("unknown runtime delivery target")
    return _identity(_DELIVERY_DOMAIN, (partition_id, target_kind, value))


def _payload_digest(
    origin: ConsolidationOrigin, revision: int, payload: ConsolidationPayload,
) -> str:
    match payload:
        case EpisodicSummary():
            scope = ("memory_plane_candidate", "episodic")
        case SemanticCandidate():
            scope = ("memory_plane_candidate", "semantic")
        case UserCandidate():
            scope = ("memory_plane_candidate", "user")
        case SkillCandidate():
            scope = ("protected_skill_candidate",)
        case _:
            scope = None
    return sha256(encode_typed_value((
        origin.installation_id,
        origin.partition_id,
        origin.task_id,
        revision,
        scope,
        payload.model_dump(mode="python"),
    ))).hexdigest()


class ConsolidationResult(_FrozenRecord):
    result_id: Digest
    origin: ConsolidationOrigin
    origin_revision: Revision
    outputs: tuple[ConsolidationOutput, ...] = Field(max_length=32)
    omissions: tuple[ConsolidationOmission, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def _validate_seal(self) -> Self:
        if self.result_id != _identity(_RESULT_DOMAIN, self.origin.coordinate()):
            raise ValueError("consolidation result identity does not match origin")
        ordinals: Counter[str] = Counter()
        previous = -1
        for output in self.outputs:
            kind = output.payload.kind
            order = _OUTPUT_ORDER.index(kind)
            if order < previous or output.ordinal != ordinals[kind]:
                raise ValueError("consolidation outputs must follow producer order and per-kind ordinals")
            previous = order
            ordinals[kind] += 1
            if output.output_id != _identity(_OUTPUT_DOMAIN, (self.result_id, kind, output.ordinal)):
                raise ValueError("consolidation output identity does not match its result and ordinal")
            if output.payload_digest != _payload_digest(self.origin, self.origin_revision, output.payload):
                raise ValueError("consolidation output payload digest mismatch")
            if isinstance(output.payload, ArchivePackage):
                ref = output.payload.reference
                if (
                    ref.installation_id,
                    ref.partition_id,
                    ref.task_id,
                    ref.origin_revision,
                ) != (
                    self.origin.installation_id,
                    self.origin.partition_id,
                    self.origin.task_id,
                    self.origin_revision,
                ):
                    raise ValueError("archive reference does not match its consolidation origin")
        if len(self.canonical_bytes()) > _MAX_BATCH_BYTES:
            raise ValueError("consolidation result exceeds the 10 MiB batch bound")
        return self

    def canonical_bytes(self) -> bytes:
        return encode_typed_value(self.model_dump(mode="python"))


def build_consolidation_result(
    origin: ConsolidationOrigin,
    *,
    origin_revision: int,
    outputs: Sequence[ConsolidationPayload],
    omissions: Sequence[ConsolidationOmission] = (),
) -> ConsolidationResult:
    """Seal already validated producer outputs before the origin publication."""
    if len(outputs) > 32:
        raise ValueError("consolidation may produce at most 32 outputs")
    result_id = _identity(_RESULT_DOMAIN, origin.coordinate())
    ordinals: Counter[str] = Counter()
    sealed: list[ConsolidationOutput] = []
    for payload in sorted(outputs, key=lambda output: _OUTPUT_ORDER.index(output.kind)):
        kind = payload.kind
        ordinal = ordinals[kind]
        sealed.append(ConsolidationOutput(
            output_id=_identity(_OUTPUT_DOMAIN, (result_id, kind, ordinal)),
            ordinal=ordinal,
            payload_digest=_payload_digest(origin, origin_revision, payload),
            payload=payload,
        ))
        ordinals[kind] += 1
    return ConsolidationResult(
        result_id=result_id,
        origin=origin,
        origin_revision=origin_revision,
        outputs=tuple(sealed),
        omissions=tuple(omissions),
    )
