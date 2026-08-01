"""M1 governed source admission and non-disclosing outcome access.

This module deliberately stops at source admission.  It does not allocate a
writer, acquire a lease, or publish a semantic generation; those are M2
responsibilities.
"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from memorii.core.memory_evolution.bootstrap_profile import (
    BOOTSTRAP_COORDINATE,
    BootstrapProfileOutcome,
    BootstrapUnavailableReason,
    GovernedSourceAdmissionFact,
    ProfileDisabled,
    ProfileInputOutcome,
    ProfileSelectedPipelinePending,
    ProfileUnavailable,
    normalized_input_digest,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContext,
    DeliveryIdentity,
    RequiredOutcomeScopeSet,
    encode_typed_value,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import MemoryPlaneRevisionConflictError, RecordAbsentPrecondition
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility


class SemanticIngestionOutcomeLookupRequest(BaseModel):
    """Purpose-bound authenticated lookup input; it contains no source payload."""

    delivery_identity: DeliveryIdentity

    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticIngestionOutcomeLookupResponse(BaseModel):
    """One deliberately non-disclosing result shape for all unavailable cases."""

    available: bool = False
    outcome: BootstrapProfileOutcome | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceAdmissionAccepted(BaseModel):
    source_id: str
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    delivery_identity: DeliveryIdentity
    required_outcome_scopes: RequiredOutcomeScopeSet
    admission_index_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


def required_scopes_for_record(record: CanonicalMemoryRecord, *, tenant_partition_id: str) -> RequiredOutcomeScopeSet:
    """Derive all represented scopes from the retained source, never caller claims."""

    scopes = {
        f"session:{record.session_id}" if record.session_id is not None else None,
        f"task:{record.task_id}" if record.task_id is not None else None,
        f"user:{record.user_id}" if record.user_id is not None else None,
    }
    return RequiredOutcomeScopeSet.create(
        tenant_partition_id=tenant_partition_id,
        scopes={scope for scope in scopes if scope is not None},
    )


class GovernedSourceAdmissionService:
    """Owns the small M1 admission index and its authorization-before-result rule."""

    def __init__(self, memory_plane: MemoryPlaneService) -> None:
        self._memory_plane = memory_plane

    def admit(
        self,
        *,
        source: CanonicalMemoryRecord,
        delivery_identity: DeliveryIdentity,
        ingress: AuthenticatedIngressContext,
        operation_id: str,
        outcome_kind: str = "selected_pipeline_pending",
        outcome_reason: str | None = None,
        normalized_input: bytes = b"",
        evidence_only: bool = False,
        matched_corpus_case_id: str | None = None,
        selection_digest: str | None = None,
        verification_digest: str | None = None,
    ) -> SourceAdmissionAccepted:
        _validate_governed_source(source)
        if delivery_identity.delivery_principal_binding_digest != ingress.delivery_principal_binding.binding_digest:
            raise ValueError("authenticated principal does not own delivery identity")
        required = (
            RequiredOutcomeScopeSet.create(
                tenant_partition_id=ingress.delivery_principal_binding.tenant_partition_id, scopes=()
            )
            if evidence_only
            else required_scopes_for_record(
                source, tenant_partition_id=ingress.delivery_principal_binding.tenant_partition_id
            )
        )
        if not set(required.scopes).issubset(ingress.current_authorized_scopes.scopes):
            raise ValueError("authenticated scope coverage is incomplete")
        source_digest = _source_digest(source)
        index = _index_record(delivery_identity=delivery_identity, required=required)
        selection_status = "disabled" if outcome_kind == "disabled" else (
            "selected" if selection_digest is not None else "unavailable"
        )
        verification_status = "verified" if verification_digest is not None else "unavailable"
        selection = _profile_evidence_record(
            index, "semantic_ingestion_profile_selection", {"status": selection_status}
        )
        verification = _profile_evidence_record(
            index, "semantic_ingestion_profile_verification", {"status": verification_status}
        )
        fact = GovernedSourceAdmissionFact(
            source_id=source.memory_id,
            source_digest=source_digest,
            delivery_principal_binding_digest=delivery_identity.delivery_principal_binding_digest,
            delivery_key_digest=delivery_identity.delivery_key_digest,
            required_scope_set_digest=required.required_scope_set_digest,
            admission_index_digest=_index_digest(index),
        )
        typed_outcome = _make_outcome(
            kind=outcome_kind,
            reason=outcome_reason,
            fact=fact,
            normalized_input=normalized_input,
            selection_digest=selection_digest or _index_digest(selection),
            verification_digest=verification_digest or _index_digest(verification),
            matched_corpus_case_id=matched_corpus_case_id,
        )
        outcome = _profile_evidence_record(
            index, "semantic_ingestion_profile_outcome", typed_outcome.model_dump(mode="json")
        )
        existing = self._memory_plane.get_record(index.memory_id)
        if existing is not None:
            return self._recover_exact_admission(
                source=source,
                source_digest=source_digest,
                index=index,
                existing=existing,
                delivery_identity=delivery_identity,
                required=required,
            )
        # A single memory-plane batch makes retained evidence and its protected
        # authorization index visible together.  It is intentionally not an M2
        # semantic generation or writer protocol.
        try:
            with self._memory_plane.unit_of_work() as unit_of_work:
                self._memory_plane.write_records((source, index, selection, verification, outcome))
                unit_of_work.commit(
                    preconditions=(
                        RecordAbsentPrecondition(memory_id=source.memory_id),
                        RecordAbsentPrecondition(memory_id=index.memory_id),
                        RecordAbsentPrecondition(memory_id=selection.memory_id),
                        RecordAbsentPrecondition(memory_id=verification.memory_id),
                        RecordAbsentPrecondition(memory_id=outcome.memory_id),
                    )
                )
        except MemoryPlaneRevisionConflictError:
            existing = self._memory_plane.get_record(index.memory_id)
            if existing is None:
                raise
            return self._recover_exact_admission(
                source=source,
                source_digest=source_digest,
                index=index,
                existing=existing,
                delivery_identity=delivery_identity,
                required=required,
            )
        return SourceAdmissionAccepted(
            source_id=source.memory_id,
            source_digest=source_digest,
            delivery_identity=delivery_identity,
            required_outcome_scopes=required,
            admission_index_digest=_index_digest(index),
        )

    def _recover_exact_admission(
        self,
        *,
        source: CanonicalMemoryRecord,
        source_digest: str,
        index: CanonicalMemoryRecord,
        existing: CanonicalMemoryRecord,
        delivery_identity: DeliveryIdentity,
        required: RequiredOutcomeScopeSet,
    ) -> SourceAdmissionAccepted:
        if existing.source_kind != "semantic_ingestion_admission_index" or existing.content != index.content:
            raise ValueError("delivery identity is already bound to a different admission")
        retained = self._memory_plane.get_record(source.memory_id)
        if retained is None or _immutable_source_identity(retained) != _immutable_source_identity(source):
            raise RuntimeError("admission index references missing or changed source evidence")
        return SourceAdmissionAccepted(
            source_id=source.memory_id,
            source_digest=source_digest,
            delivery_identity=delivery_identity,
            required_outcome_scopes=required,
            admission_index_digest=_index_digest(index),
        )

    def lookup(
        self,
        request: SemanticIngestionOutcomeLookupRequest,
        *,
        authenticated_ingress: AuthenticatedIngressContext,
    ) -> SemanticIngestionOutcomeLookupResponse:
        """Authorize from the protected index before touching any outcome store."""

        index_id = _index_id(request.delivery_identity.delivery_key_digest)
        index = self._memory_plane.get_record(index_id)
        if index is None or index.source_kind != "semantic_ingestion_admission_index":
            return SemanticIngestionOutcomeLookupResponse()
        content = index.content
        if (
            content.get("principal_binding_digest")
            != authenticated_ingress.delivery_principal_binding.binding_digest
            or content.get("delivery_key_digest") != request.delivery_identity.delivery_key_digest
            or content.get("tenant_partition_id")
            != authenticated_ingress.delivery_principal_binding.tenant_partition_id
        ):
            return SemanticIngestionOutcomeLookupResponse()
        required = tuple(content.get("required_scopes", ()))
        if not set(required).issubset(authenticated_ingress.current_authorized_scopes.scopes):
            return SemanticIngestionOutcomeLookupResponse()
        # Only after every non-disclosing authorization check may M1 read its
        # protected outcome evidence.
        outcome = self._memory_plane.get_record(f"{index_id}:outcome")
        if outcome is None or outcome.source_kind != "semantic_ingestion_profile_outcome":
            return SemanticIngestionOutcomeLookupResponse()
        try:
            decoded = TypeAdapter(BootstrapProfileOutcome).validate_python(outcome.content)
        except ValueError:
            return SemanticIngestionOutcomeLookupResponse()
        return SemanticIngestionOutcomeLookupResponse(available=True, outcome=decoded)


def _source_digest(source: CanonicalMemoryRecord) -> str:
    return sha256(encode_typed_value(_immutable_source_identity(source))).hexdigest()


def _immutable_source_identity(source: CanonicalMemoryRecord) -> dict[str, object]:
    """Exclude regenerated storage timestamps from delivery retry identity."""
    value = source.model_dump(mode="python")
    value.pop("timestamp", None)
    return value


def _index_digest(index: CanonicalMemoryRecord) -> str:
    return sha256(encode_typed_value(index.content)).hexdigest()


def _validate_governed_source(source: CanonicalMemoryRecord) -> None:
    if (
        source.domain != MemoryDomain.TRANSCRIPT
        or not source.is_raw_event
        or source.source_kind
        not in {"semantic_ingestion_source", "semantic_ingestion_metadata_poor_snapshot"}
        or source.visibility != MemoryRecordVisibility.INTERNAL_CONTROL
    ):
        raise ValueError("admission requires a governed immutable source record")


def _index_id(delivery_key_digest: str) -> str:
    return f"semantic_ingestion:admission:{delivery_key_digest}"


def _index_record(*, delivery_identity: DeliveryIdentity, required: RequiredOutcomeScopeSet) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_index_id(delivery_identity.delivery_key_digest),
        domain=MemoryDomain.TRANSCRIPT,
        text="",
        content={
            "principal_binding_digest": delivery_identity.delivery_principal_binding_digest,
            "delivery_key_digest": delivery_identity.delivery_key_digest,
            "tenant_partition_id": required.tenant_partition_id,
            "required_scopes": list(required.scopes),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_admission_index",
        timestamp=datetime.now(UTC),
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _profile_evidence_record(index: CanonicalMemoryRecord, kind: str, content: dict[str, object]) -> CanonicalMemoryRecord:
    return index.model_copy(update={
        "memory_id": f"{index.memory_id}:{kind.rsplit('_', 1)[-1]}",
        "source_kind": kind,
        "content": content,
    })


def _make_outcome(
    *,
    kind: str,
    reason: str | None,
    fact: GovernedSourceAdmissionFact,
    normalized_input: bytes,
    selection_digest: str,
    verification_digest: str,
    matched_corpus_case_id: str | None,
) -> ProfileSelectedPipelinePending | ProfileDisabled | ProfileUnavailable | ProfileInputOutcome:
    if kind == "selected_pipeline_pending":
        return ProfileSelectedPipelinePending(
            kind=kind,
            coordinate=BOOTSTRAP_COORDINATE,
            source_admission=fact,
            selection_digest=selection_digest,
            verification_digest=verification_digest,
        )
    if kind == "unavailable":
        return ProfileUnavailable(
            kind=kind,
            coordinate=BOOTSTRAP_COORDINATE,
            source_admission=fact,
            reason=BootstrapUnavailableReason(reason or "invalid_config"),
        )
    if kind == "disabled":
        return ProfileDisabled(
            kind=kind,
            coordinate=BOOTSTRAP_COORDINATE,
            source_admission=fact,
            disable_reason="operator_disabled",
        )
    if kind in {"unsupported_input", "abstained"} and reason is not None:
        return ProfileInputOutcome.model_validate(
            {
                "kind": kind,
                "coordinate": BOOTSTRAP_COORDINATE,
                "source_admission": fact,
                "reason": reason,
                "input_normalized_digest": normalized_input_digest(normalized_input),
                "matched_corpus_case_id": matched_corpus_case_id,
            }
        )
    raise ValueError("illegal M1 bootstrap outcome")
