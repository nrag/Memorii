"""Atomic, evidence-only M2 admission-to-preplanning persistence."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.memory_evolution.admission import (
    PreparedSourceAdmission,
    SourceAdmissionAccepted,
    source_admission_source_digest,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    OperationFenceBinding,
    SemanticWriterCommitBinding,
    encode_typed_value,
)
from memorii.core.memory_evolution.writer_admission import SemanticWriterAdmissionStore
from memorii.core.memory_plane.models import CanonicalMemoryRecord, MemoryRecordFence
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    MemoryPlanePrecondition,
    MemoryPlaneRevisionConflictError,
    RecordAbsentPrecondition,
    RecordDigestPrecondition,
    RecordFencePrecondition,
    record_digest,
)
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility, TemporalValidityStatus


class PreplanningStoreError(ValueError):
    pass


class PreplanningLease(BaseModel):
    owner_id: str = Field(min_length=1)
    execution_token: str = Field(min_length=1)
    ownership_epoch: int = Field(ge=1)
    acquired_at: datetime
    expires_at: datetime
    renewal_interval: timedelta

    model_config = ConfigDict(extra="forbid", frozen=True)


class PreplanningOperationControl(BaseModel):
    operation_fence: OperationFenceBinding
    writer_binding: SemanticWriterCommitBinding
    state: Literal["preplanning", "planned", "terminal", "lease_recovery_exhausted"] = "preplanning"
    lease: PreplanningLease | None = None
    lease_recovery_count: int = Field(default=0, ge=0)
    max_lease_recoveries: int = Field(default=1, ge=0)
    graph_record_ids: tuple[str, ...] = ()
    event_ids: tuple[str, ...] = ()
    terminal_group_ids: tuple[str, ...] = ()
    group_result_digests: tuple[str, ...] = ()
    graph_revision: str = "genesis"
    observation_revision: str = "genesis"
    effective_read_set_digest: str = "0" * 64
    generation: int = Field(default=1, ge=1)
    state_revision: int = Field(default=0, ge=0)
    attempt_count: int = Field(default=0, ge=0)
    last_request_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


class PreplanningPublication(BaseModel):
    operation: PreplanningOperationControl
    introduction_bytes: bytes
    artifact_index_bytes: bytes
    artifact_closure_bytes: bytes

    model_config = ConfigDict(extra="forbid", frozen=True)


class AtomicGenerationMember(BaseModel):
    member_id: str = Field(min_length=1)
    kind: Literal[
        "progress", "retry_outcome", "group_result", "observation_delta", "graph_delta",
        "event_batch", "terminal_operation", "source_summary", "source_result", "lifecycle",
        "replay_artifact", "artifact_index", "artifact_closure",
        "plan", "planning_artifact", "independence_certificate", "planning_authorization",
    ]
    canonical_payload: bytes
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


class OperationLeaseBinding(BaseModel):
    operation_id: str
    operation_fence_binding: OperationFenceBinding
    delivery_principal_binding_digest: str
    delivery_key_digest: str
    allocation_namespace_id: str
    writer_namespace: Literal["semantic_ingestion"]
    admitted_writer_epoch: int = Field(ge=0)
    writer_admission_digest: str
    writer_implementation_fingerprint: str
    state_revision: int = Field(ge=1)
    owner_id: str
    execution_token: str
    ownership_epoch: int = Field(ge=1)
    lease_expires_at: datetime
    binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


class AtomicGenerationRequest(BaseModel):
    operation_fence_binding: OperationFenceBinding
    operation_lease_binding: OperationLeaseBinding
    writer_commit_binding: SemanticWriterCommitBinding
    expected_operation_generation: int = Field(ge=1)
    expected_artifact_generation: int = Field(ge=1)
    members: tuple[AtomicGenerationMember, ...]
    required_artifact_digests: tuple[str, ...]
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceCheckpointAtomicWriteRequest(AtomicGenerationRequest):
    kind: Literal["checkpoint"] = "checkpoint"
    progress_state: Literal["preplanning", "planned"]


class CommittedGroupAtomicWriteRequest(AtomicGenerationRequest):
    kind: Literal["committed"] = "committed"
    expected_graph_revision: str = Field(min_length=1)
    expected_observation_revision: str = Field(min_length=1)
    expected_effective_read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    graph_revision_after: str = Field(min_length=1)
    observation_revision_after: str = Field(min_length=1)


class NonCommittingGroupAtomicWriteRequest(AtomicGenerationRequest):
    kind: Literal["non_committing"] = "non_committing"
    expected_observation_revision: str = Field(min_length=1)
    observation_revision_after: str = Field(min_length=1)


TerminalGroupAtomicWriteRequest = Annotated[
    CommittedGroupAtomicWriteRequest | NonCommittingGroupAtomicWriteRequest,
    Field(discriminator="kind"),
]


class SourceFinalizationAtomicWriteRequest(AtomicGenerationRequest):
    kind: Literal["finalization"] = "finalization"
    source_summary_kind: Literal["pre_graph", "graph_bound"]
    expected_group_result_digests: tuple[str, ...]


class SemanticIngestionAtomicStore:
    """The only M2 owner permitted to publish preplanning control evidence."""

    def __init__(
        self,
        memory_plane: MemoryPlaneService,
        writer_admission: SemanticWriterAdmissionStore,
        *,
        max_lease_recoveries: int = 1,
        now_provider=lambda: datetime.now(UTC),
    ) -> None:
        if max_lease_recoveries < 0:
            raise ValueError("max lease recoveries must be non-negative")
        self._memory_plane = memory_plane
        self._writers = writer_admission
        self._write_capability = self._writers._register_atomic_owner()
        self._max_lease_recoveries = max_lease_recoveries
        self._now = now_provider

    def publish_preplanning(
        self,
        *,
        admission: SourceAdmissionAccepted,
        writer_binding: SemanticWriterCommitBinding,
    ) -> PreplanningPublication:
        raise PreplanningStoreError("new preplanning publication requires atomic source admission")

    def _publish_preplanning(
        self,
        *,
        admission: SourceAdmissionAccepted,
        writer_binding: SemanticWriterCommitBinding,
    ) -> PreplanningPublication:
        operation_fence = admission.operation_fence_binding
        self._validate_handoff(admission, operation_fence)
        writer_record = self._writers.require_current(writer_binding)
        authorization = self._writers._authorize_atomic(
            writer_binding,
            capability=self._write_capability,
        )
        control_id = _control_id(operation_fence.operation_id)
        existing = self._memory_plane.get_record(control_id)
        if existing is not None:
            return self._recover_publication(existing, admission, operation_fence, writer_binding)
        control = PreplanningOperationControl(
            operation_fence=operation_fence,
            writer_binding=writer_binding,
            max_lease_recoveries=self._max_lease_recoveries,
        )
        publication = _publication(control)
        records = _publication_records(publication, self._now())
        try:
            self._memory_plane.conditionally_write_records(
                records,
                preconditions=tuple(RecordAbsentPrecondition(memory_id=record.memory_id) for record in records)
                + (
                    RecordDigestPrecondition(
                        memory_id=writer_record.memory_id, expected_digest=record_digest(writer_record)
                    ),
                ),
                authorization=authorization,
            )
        except MemoryPlaneRevisionConflictError as exc:
            existing = self._memory_plane.get_record(control_id)
            if existing is None:
                raise exc
            return self._recover_publication(existing, admission, operation_fence, writer_binding)
        return publication

    def admit_source(
        self, *, prepared: PreparedSourceAdmission, writer_binding: SemanticWriterCommitBinding
    ) -> PreplanningPublication:
        """Atomically publish retained admission evidence and its pending operation."""
        admission = prepared.accepted
        fence = admission.operation_fence_binding
        if any(self._memory_plane.get_record(record.memory_id) is not None for record in prepared.records):
            if any(
                not _same_admission_record(self._memory_plane.get_record(record.memory_id), record)
                for record in prepared.records
            ):
                raise PreplanningStoreError("atomic admission evidence is partial or mismatched")
            return self._publish_preplanning(admission=admission, writer_binding=writer_binding)
        writer_record = self._writers.require_current(writer_binding)
        authorization = self._writers._authorize_atomic(writer_binding, capability=self._write_capability)
        control = PreplanningOperationControl(
            operation_fence=fence, writer_binding=writer_binding,
            max_lease_recoveries=self._max_lease_recoveries,
        )
        publication = _publication(control)
        generation_records = _publication_records(publication, self._now())
        all_records = (*prepared.records, *generation_records)
        try:
            self._memory_plane.conditionally_write_records(
                all_records,
                preconditions=(
                    *(RecordAbsentPrecondition(memory_id=record.memory_id) for record in all_records),
                    RecordDigestPrecondition(memory_id=writer_record.memory_id, expected_digest=record_digest(writer_record)),
                ),
                authorization=authorization,
            )
        except MemoryPlaneRevisionConflictError as exc:
            if any(
                not _same_admission_record(self._memory_plane.get_record(record.memory_id), record)
                for record in prepared.records
            ):
                raise PreplanningStoreError("atomic admission conflict is not an exact committed retry") from exc
            existing = self._memory_plane.get_record(_control_id(fence.operation_id))
            if existing is None:
                raise PreplanningStoreError("atomic admission conflict has no complete operation generation") from exc
            return self._recover_publication(existing, admission, fence, writer_binding)
        return publication

    def acquire_lease(
        self,
        *,
        operation_id: str,
        writer_binding: SemanticWriterCommitBinding,
        execution_token: str,
        owner_id: str | None = None,
        duration: timedelta,
    ) -> PreplanningOperationControl:
        if duration <= timedelta(0):
            raise PreplanningStoreError("lease duration must be positive")
        writer_record = self._writers.require_current(writer_binding)
        record = self._required_control_record(operation_id)
        control = _control_from_record(record)
        if control.writer_binding != writer_binding:
            raise PreplanningStoreError("writer binding does not own operation")
        if control.state not in {"preplanning", "planned"}:
            raise PreplanningStoreError("operation is terminal")
        now = self._now()
        lease = control.lease
        if lease is not None and lease.expires_at > now:
            if lease.execution_token == execution_token and (
                owner_id is None or lease.owner_id == owner_id
            ):
                return control
            raise PreplanningStoreError("operation lease is held by another owner")
        recovery = control.lease_recovery_count + int(lease is not None and lease.expires_at <= now)
        if recovery > control.max_lease_recoveries:
            exhausted = control.model_copy(update={"state": "lease_recovery_exhausted", "lease": None})
            self._replace_control(
                record,
                exhausted,
                writer_record,
                writer_binding=writer_binding,
                expected_lease=lease,
            )
            return exhausted
        next_control = control.model_copy(
            update={
                "lease": PreplanningLease(
                    owner_id=owner_id or execution_token,
                    execution_token=execution_token,
                    ownership_epoch=(lease.ownership_epoch + 1 if lease is not None else 1),
                    acquired_at=now,
                    expires_at=now + duration,
                    renewal_interval=duration / 2,
                ),
                "lease_recovery_count": recovery,
                "state_revision": control.state_revision + 1,
                "attempt_count": control.attempt_count + 1,
            }
        )
        self._replace_control(
            record,
            next_control,
            writer_record,
            writer_binding=writer_binding,
            expected_lease=lease,
            require_active_lease=False,
        )
        return next_control

    def renew_lease(
        self,
        *,
        operation_id: str,
        writer_binding: SemanticWriterCommitBinding,
        lease: PreplanningLease,
        duration: timedelta,
    ) -> PreplanningOperationControl:
        if duration <= timedelta(0):
            raise PreplanningStoreError("lease duration must be positive")
        writer_record = self._writers.require_current(writer_binding)
        record = self._required_control_record(operation_id)
        control = _control_from_record(record)
        if control.writer_binding != writer_binding or control.lease != lease or lease.expires_at <= self._now():
            raise PreplanningStoreError("stale or mismatched operation lease")
        next_control = control.model_copy(
            update={
                "lease": lease.model_copy(update={"expires_at": self._now() + duration, "renewal_interval": duration / 2}),
                "state_revision": control.state_revision + 1,
            }
        )
        self._replace_control(
            record,
            next_control,
            writer_record,
            writer_binding=writer_binding,
            expected_lease=lease,
            require_active_lease=True,
        )
        return next_control

    def lease_binding(self, control: PreplanningOperationControl) -> OperationLeaseBinding:
        lease = control.lease
        if lease is None:
            raise PreplanningStoreError("operation has no active lease")
        fence = control.operation_fence
        values = {
            "operation_id": fence.operation_id,
            "operation_fence_binding": fence,
            "delivery_principal_binding_digest": fence.delivery_principal_binding_digest,
            "delivery_key_digest": fence.delivery_key_digest,
            "allocation_namespace_id": fence.allocation_namespace_id,
            "writer_namespace": "semantic_ingestion",
            "admitted_writer_epoch": control.writer_binding.expected_writer_epoch,
            "writer_admission_digest": control.writer_binding.admission_digest,
            "writer_implementation_fingerprint": control.writer_binding.writer_implementation_fingerprint,
            "state_revision": control.state_revision,
            "owner_id": lease.owner_id,
            "execution_token": lease.execution_token,
            "ownership_epoch": lease.ownership_epoch,
            "lease_expires_at": lease.expires_at,
        }
        digest_values = dict(values)
        digest_values["operation_fence_binding"] = fence.model_dump(mode="python")
        return OperationLeaseBinding(**values, binding_digest=sha256(encode_typed_value(digest_values)).hexdigest())

    def get_operation(self, operation_id: str) -> PreplanningOperationControl:
        return _control_from_record(self._required_control_record(operation_id))

    def checkpoint_source_progress(self, request: SourceCheckpointAtomicWriteRequest) -> tuple[AtomicGenerationMember, ...]:
        control = _control_from_record(self._required_control_record(request.operation_fence_binding.operation_id))
        recovered = self._recover_exact_generation(control, request.request_digest)
        if recovered is not None:
            return recovered
        counts = _member_kind_counts(request.members)
        if counts.get("progress") != 1:
            raise PreplanningStoreError("checkpoint requires exactly one progress record")
        if request.progress_state == "preplanning" and counts.get("retry_outcome", 0):
            raise PreplanningStoreError("preplanning checkpoint cannot contain retry outcomes")
        planned_closure = {
            "plan", "planning_artifact", "independence_certificate", "planning_authorization",
            "artifact_index", "artifact_closure",
        }
        if (
            request.progress_state == "planned"
            and control.state == "preplanning"
            and any(counts.get(kind) != 1 for kind in planned_closure)
        ):
            raise PreplanningStoreError("planned checkpoint closure is incomplete")
        allowed = {
            "progress", "retry_outcome", "replay_artifact", "artifact_index", "artifact_closure",
            "plan", "planning_artifact", "independence_certificate", "planning_authorization",
        }
        return self._publish_generation(request, next_state=request.progress_state, allowed_kinds=allowed)

    def persist_terminal_group(self, request: TerminalGroupAtomicWriteRequest) -> tuple[AtomicGenerationMember, ...]:
        control = _control_from_record(self._required_control_record(request.operation_fence_binding.operation_id))
        recovered = self._recover_exact_generation(control, request.request_digest)
        if recovered is not None:
            return recovered
        if control.state != "planned":
            raise PreplanningStoreError("terminal group requires planned source progress")
        if request.kind == "committed" and request.writer_commit_binding.runtime_mode == "evidence_only":
            raise PreplanningStoreError("evidence-only writer cannot publish graph or event effects")
        if request.expected_observation_revision != control.observation_revision:
            raise PreplanningStoreError("observation revision precondition is stale")
        if request.kind == "committed":
            if (
                request.expected_graph_revision != control.graph_revision
                or request.expected_effective_read_set_digest != control.effective_read_set_digest
            ):
                raise PreplanningStoreError("graph/read-set precondition is stale")
            required = {"group_result", "observation_delta", "graph_delta", "event_batch"}
            allowed = required | {"replay_artifact", "artifact_index", "artifact_closure"}
        else:
            required = {"group_result", "observation_delta"}
            allowed = required | {"replay_artifact", "artifact_index", "artifact_closure"}
        counts = _member_kind_counts(request.members)
        if any(counts.get(kind) != 1 for kind in required):
            raise PreplanningStoreError("terminal group generation is incomplete")
        group_results = tuple(member for member in request.members if member.kind == "group_result")
        if len(group_results) != 1:
            raise PreplanningStoreError("terminal group requires exactly one group result")
        return self._publish_generation(
            request, next_state="planned", allowed_kinds=allowed,
            terminal_group_result_digest=group_results[0].payload_digest,
            graph_revision_after=request.graph_revision_after if request.kind == "committed" else None,
            observation_revision_after=request.observation_revision_after,
        )

    def finalize_source(self, request: SourceFinalizationAtomicWriteRequest) -> tuple[AtomicGenerationMember, ...]:
        control = _control_from_record(self._required_control_record(request.operation_fence_binding.operation_id))
        recovered = self._recover_exact_generation(control, request.request_digest)
        if recovered is not None:
            return recovered
        required = {"terminal_operation", "source_summary", "source_result", "observation_delta", "lifecycle"}
        if any(_member_kind_counts(request.members).get(kind) != 1 for kind in required):
            raise PreplanningStoreError("source finalization generation is incomplete")
        if request.expected_group_result_digests != control.group_result_digests:
            raise PreplanningStoreError("source finalization group-result closure is mismatched")
        if request.source_summary_kind == "graph_bound" and not control.group_result_digests:
            raise PreplanningStoreError("graph-bound source has no terminal group results")
        if request.source_summary_kind == "pre_graph" and control.group_result_digests:
            raise PreplanningStoreError("pre-graph source cannot contain terminal group results")
        return self._publish_generation(
            request, next_state="terminal",
            allowed_kinds=required | {"replay_artifact", "artifact_index", "artifact_closure"},
            clear_lease=True,
        )

    def _publish_generation(
        self,
        request: AtomicGenerationRequest,
        *,
        next_state: Literal["preplanning", "planned", "terminal"],
        allowed_kinds: set[str],
        terminal_group_result_digest: str | None = None,
        graph_revision_after: str | None = None,
        observation_revision_after: str | None = None,
        clear_lease: bool = False,
    ) -> tuple[AtomicGenerationMember, ...]:
        writer_record = self._writers.require_current(request.writer_commit_binding)
        control_record = self._required_control_record(request.operation_fence_binding.operation_id)
        control = _control_from_record(control_record)
        if control.operation_fence != request.operation_fence_binding or control.writer_binding != request.writer_commit_binding:
            raise PreplanningStoreError("generation does not bind the admitted operation")
        if control.last_request_digest == request.request_digest:
            return self._read_generation_members(control.operation_fence.operation_id, control.generation)
        if control.state in {"terminal", "lease_recovery_exhausted"}:
            raise PreplanningStoreError("operation is terminal")
        if control.generation != request.expected_operation_generation or request.expected_artifact_generation != control.generation:
            raise PreplanningStoreError("generation precondition is stale")
        if self.lease_binding(control) != request.operation_lease_binding or request.operation_lease_binding.lease_expires_at <= self._now():
            raise PreplanningStoreError("generation lease is stale or expired")
        if next_state == "preplanning" and control.state == "planned":
            raise PreplanningStoreError("planned progress cannot regress")
        ids = tuple(member.member_id for member in request.members)
        if (
            len(ids) != len(set(ids))
            or ids != tuple(sorted(ids))
            or "manifest" in ids
        ):
            raise PreplanningStoreError("generation members must have unique canonical order")
        if any(member.kind not in allowed_kinds for member in request.members):
            raise PreplanningStoreError("generation contains a forbidden member kind")
        if any(sha256(member.canonical_payload).hexdigest() != member.payload_digest for member in request.members):
            raise PreplanningStoreError("generation member digest is invalid")
        available_artifacts = {
            member.payload_digest for member in request.members if member.kind == "replay_artifact"
        }
        for prior_generation in range(2, control.generation + 1):
            for member in self._read_generation_members(control.operation_fence.operation_id, prior_generation):
                if member.kind == "replay_artifact":
                    available_artifacts.add(member.payload_digest)
        if not set(request.required_artifact_digests).issubset(available_artifacts):
            raise PreplanningStoreError("required replay artifact closure is incomplete")
        if request.request_digest != generation_request_digest(request):
            raise PreplanningStoreError("generation request digest is invalid")
        generation = control.generation + 1
        group_result_digests = control.group_result_digests
        if terminal_group_result_digest is not None:
            if terminal_group_result_digest in group_result_digests:
                raise PreplanningStoreError("terminal group result is already recorded")
            group_result_digests = (*group_result_digests, terminal_group_result_digest)
        next_control = control.model_copy(update={
            "state": next_state, "generation": generation, "last_request_digest": request.request_digest,
            "group_result_digests": group_result_digests,
            "graph_revision": graph_revision_after or control.graph_revision,
            "observation_revision": observation_revision_after or control.observation_revision,
            "lease": None if clear_lease else control.lease,
        })
        member_records = tuple(
            _generation_member_record(control.operation_fence.operation_id, generation, member, self._now())
            for member in request.members
        )
        manifest_record = _generation_manifest_record(
            control.operation_fence.operation_id, generation, request, self._now()
        )
        authorization = self._writers._authorize_atomic(
            request.writer_commit_binding,
            capability=self._write_capability,
            lease_expires_at=request.operation_lease_binding.lease_expires_at,
            server_now=self._now,
        )
        record_ids = [record.memory_id for record in (
            _control_record(next_control, control_record.timestamp), *member_records, manifest_record
        )]
        if len(record_ids) != len(set(record_ids)):
            raise PreplanningStoreError("generation record identities collide")
        self._memory_plane.conditionally_write_records(
            (_control_record(next_control, control_record.timestamp), *member_records, manifest_record),
            preconditions=(
                RecordDigestPrecondition(memory_id=control_record.memory_id, expected_digest=record_digest(control_record)),
                RecordDigestPrecondition(memory_id=writer_record.memory_id, expected_digest=record_digest(writer_record)),
                RecordFencePrecondition(
                    memory_id=control_record.memory_id,
                    expected_fence=MemoryRecordFence(
                        execution_token=request.operation_lease_binding.execution_token,
                        ownership_epoch=request.operation_lease_binding.ownership_epoch,
                    ),
                ),
                *(RecordAbsentPrecondition(memory_id=record.memory_id) for record in (*member_records, manifest_record)),
            ),
            authorization=authorization,
        )
        return request.members

    def _read_generation_members(self, operation_id: str, generation: int) -> tuple[AtomicGenerationMember, ...]:
        manifest = self._memory_plane.get_record(
            f"semantic_ingestion:generation:{operation_id}:{generation}:manifest"
        )
        if manifest is None:
            raise PreplanningStoreError("committed generation manifest is absent")
        try:
            members = tuple(AtomicGenerationMember.model_validate(item) for item in manifest.content["members"])
        except (KeyError, ValueError, TypeError) as exc:
            raise PreplanningStoreError("committed generation manifest is corrupt") from exc
        for member in members:
            record = self._memory_plane.get_record(
                f"semantic_ingestion:generation:{operation_id}:{generation}:{member.member_id}"
            )
            if record is None or record.content.get("member") != member.model_dump(mode="json"):
                raise PreplanningStoreError("committed generation is incomplete")
        return members

    def _recover_exact_generation(
        self, control: PreplanningOperationControl, request_digest: str
    ) -> tuple[AtomicGenerationMember, ...] | None:
        if control.last_request_digest != request_digest:
            return None
        return self._read_generation_members(control.operation_fence.operation_id, control.generation)

    def _replace_control(
        self,
        prior: CanonicalMemoryRecord,
        control: PreplanningOperationControl,
        writer_record: CanonicalMemoryRecord,
        *,
        writer_binding: SemanticWriterCommitBinding,
        expected_lease: PreplanningLease | None,
        require_active_lease: bool = False,
    ) -> None:
        updated = _control_record(control, prior.timestamp)
        preconditions: list[MemoryPlanePrecondition] = [
            RecordDigestPrecondition(memory_id=prior.memory_id, expected_digest=record_digest(prior)),
            RecordDigestPrecondition(memory_id=writer_record.memory_id, expected_digest=record_digest(writer_record)),
        ]
        if expected_lease is not None:
            preconditions.append(
                RecordFencePrecondition(
                    memory_id=prior.memory_id,
                    expected_fence=MemoryRecordFence(
                        execution_token=expected_lease.execution_token, ownership_epoch=expected_lease.ownership_epoch
                    ),
                )
            )
        self._memory_plane.conditionally_write_records(
            (updated,),
            preconditions=tuple(preconditions),
            authorization=self._writers._authorize_atomic(
                writer_binding,
                capability=self._write_capability,
                lease_expires_at=(
                    expected_lease.expires_at if expected_lease is not None and require_active_lease else None
                ),
                server_now=self._now if expected_lease is not None and require_active_lease else None,
            ),
        )

    def _validate_handoff(self, admission: SourceAdmissionAccepted, fence: OperationFenceBinding) -> None:
        if (
            admission.source_id != fence.source_id
            or admission.source_digest != fence.source_digest
            or admission.delivery_identity != fence.delivery_identity
        ):
            raise PreplanningStoreError("operation fence does not bind the admitted source")
        source = self._memory_plane.get_record(admission.source_id)
        index = self._memory_plane.get_record(
            f"semantic_ingestion:admission:{admission.delivery_identity.delivery_key_digest}"
        )
        if (
            source is None
            or index is None
            or source_admission_source_digest(source) != admission.source_digest
            or index.source_kind != "semantic_ingestion_admission_index"
            or sha256(encode_typed_value(index.content)).hexdigest() != admission.admission_index_digest
            or index.content.get("operation_fence_binding") != fence.model_dump(mode="json")
            or index.content.get("principal_binding_digest") != fence.delivery_principal_binding_digest
            or index.content.get("delivery_key_digest") != fence.delivery_key_digest
            or index.content.get("tenant_partition_id") != admission.required_outcome_scopes.tenant_partition_id
            or tuple(index.content.get("required_scopes", ())) != admission.required_outcome_scopes.scopes
            or index.content.get("required_scope_set_digest")
            != admission.required_outcome_scopes.required_scope_set_digest
        ):
            raise PreplanningStoreError("source handoff is not already M1-admitted")
        admitted_epoch = index.content.get("admitted_writer_epoch")
        admitted_digest = index.content.get("writer_admission_digest")
        if admitted_epoch is not None:
            current = self._writers.current()
            if admitted_epoch != current.writer_epoch or admitted_digest != current.admission_digest:
                raise PreplanningStoreError("source admission belongs to a stale writer epoch")

    def _recover_publication(
        self,
        existing: CanonicalMemoryRecord,
        admission: SourceAdmissionAccepted,
        fence: OperationFenceBinding,
        binding: SemanticWriterCommitBinding,
    ) -> PreplanningPublication:
        control = _control_from_record(existing)
        if control.operation_fence != fence or control.writer_binding != binding:
            raise PreplanningStoreError("operation is already bound differently")
        publication = _publication(
            control,
            self._read_artifact_bytes(fence.operation_id, "introduction"),
            self._read_artifact_bytes(fence.operation_id, "index"),
            self._read_artifact_bytes(fence.operation_id, "closure"),
        )
        if publication != _publication(control):
            raise PreplanningStoreError("preplanning artifact index or closure is inconsistent")
        return publication

    def _read_artifact_bytes(self, operation_id: str, kind: str) -> bytes:
        record = self._memory_plane.get_record(_artifact_id(operation_id, kind))
        encoded = None if record is None else record.content.get("canonical_bytes_base64")
        if not isinstance(encoded, str):
            raise PreplanningStoreError("preplanning artifact closure is incomplete")
        if record is None:
            raise PreplanningStoreError("preplanning artifact closure is incomplete")
        try:
            canonical_bytes = base64.b64decode(encoded, validate=True)
        except ValueError as exc:
            raise PreplanningStoreError("preplanning artifact closure is corrupt") from exc
        if (
            base64.b64encode(canonical_bytes).decode("ascii") != encoded
            or record.content.get("digest") != sha256(canonical_bytes).hexdigest()
        ):
            raise PreplanningStoreError("preplanning artifact closure is corrupt")
        return canonical_bytes

    def _required_control_record(self, operation_id: str) -> CanonicalMemoryRecord:
        record = self._memory_plane.get_record(_control_id(operation_id))
        if record is None:
            raise PreplanningStoreError("preplanning operation is absent")
        return record


def _control_id(operation_id: str) -> str:
    return f"semantic_ingestion:operation:{operation_id}"


def _artifact_id(operation_id: str, kind: str) -> str:
    return f"semantic_ingestion:artifact:{operation_id}:{kind}"


def _generation_member_record(
    operation_id: str, generation: int, member: AtomicGenerationMember, timestamp: datetime
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=f"semantic_ingestion:generation:{operation_id}:{generation}:{member.member_id}",
        domain=MemoryDomain.EXECUTION,
        text="",
        content={"semantic_ingestion_kind": "generation_member", "member": member.model_dump(mode="json")},
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_generation_member",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _generation_manifest_record(
    operation_id: str, generation: int, request: AtomicGenerationRequest, timestamp: datetime
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=f"semantic_ingestion:generation:{operation_id}:{generation}:manifest",
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "generation_manifest",
            "generation": generation,
            "request_digest": request.request_digest,
            "members": tuple(member.model_dump(mode="json") for member in request.members),
            "required_artifact_digests": request.required_artifact_digests,
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_generation_manifest",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def generation_request_digest(request: AtomicGenerationRequest) -> str:
    return sha256(
        encode_typed_value(request.model_dump(mode="python", exclude={"request_digest"}))
    ).hexdigest()


def _member_kind_counts(members: tuple[AtomicGenerationMember, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for member in members:
        counts[member.kind] = counts.get(member.kind, 0) + 1
    return counts


def _publication(
    control: PreplanningOperationControl,
    introduction: bytes | None = None,
    index: bytes | None = None,
    closure: bytes | None = None,
) -> PreplanningPublication:
    introduction = introduction or encode_typed_value(
        {
            "kind": "operation_introduction",
            "operation_fence": control.operation_fence.model_dump(mode="python"),
            "graph_record_ids": (),
            "event_ids": (),
            "terminal_group_ids": (),
        }
    )
    index = index or encode_typed_value(
        {"kind": "artifact_index", "members": (("introduction", sha256(introduction).hexdigest()),)}
    )
    closure = closure or encode_typed_value(
        {
            "kind": "artifact_closure",
            "members": (("introduction", sha256(introduction).hexdigest()), ("index", sha256(index).hexdigest())),
            "graph_record_ids": (),
            "event_ids": (),
            "terminal_group_ids": (),
        }
    )
    return PreplanningPublication(
        operation=control, introduction_bytes=introduction, artifact_index_bytes=index, artifact_closure_bytes=closure
    )


def _publication_records(publication: PreplanningPublication, timestamp: datetime) -> tuple[CanonicalMemoryRecord, ...]:
    operation_id = publication.operation.operation_fence.operation_id
    return (
        _control_record(publication.operation, timestamp),
        *(
            _artifact_record(operation_id, kind, value, timestamp)
            for kind, value in (
                ("introduction", publication.introduction_bytes),
                ("index", publication.artifact_index_bytes),
                ("closure", publication.artifact_closure_bytes),
            )
        ),
    )


def _control_record(control: PreplanningOperationControl, timestamp: datetime) -> CanonicalMemoryRecord:
    fence = (
        None
        if control.lease is None
        else MemoryRecordFence(
            execution_token=control.lease.execution_token, ownership_epoch=control.lease.ownership_epoch
        )
    )
    return CanonicalMemoryRecord(
        memory_id=_control_id(control.operation_fence.operation_id),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "preplanning_operation_control",
            "control": control.model_dump(mode="json"),
        },
        status=CommitStatus.COMMITTED,
        validity_status=TemporalValidityStatus.ACTIVE,
        source_kind="semantic_ingestion_preplanning_control",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        mutation_fence=fence,
    )


def _artifact_record(
    operation_id: str, kind: str, canonical_bytes: bytes, timestamp: datetime
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_artifact_id(operation_id, kind),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": f"preplanning_{kind}",
            "canonical_bytes_base64": base64.b64encode(canonical_bytes).decode("ascii"),
            "digest": sha256(canonical_bytes).hexdigest(),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_preplanning_artifact",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _control_from_record(record: CanonicalMemoryRecord) -> PreplanningOperationControl:
    if (
        record.source_kind != "semantic_ingestion_preplanning_control"
        or record.content.get("semantic_ingestion_kind") != "preplanning_operation_control"
    ):
        raise PreplanningStoreError("preplanning control record is corrupt")
    try:
        return PreplanningOperationControl.model_validate(record.content.get("control"))
    except ValueError as exc:
        raise PreplanningStoreError("preplanning control record is corrupt") from exc


def _same_admission_record(
    existing: CanonicalMemoryRecord | None,
    proposed: CanonicalMemoryRecord,
) -> bool:
    """Compare deterministic admission identity while ignoring retry wall-clock time."""
    if existing is None:
        return False
    return existing.model_copy(update={"timestamp": proposed.timestamp}) == proposed
