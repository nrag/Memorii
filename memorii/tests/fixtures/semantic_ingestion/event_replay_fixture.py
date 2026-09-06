"""Reusable deterministic replay authority for semantic-ingestion tests."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime

from memorii.core.memory_evolution.identity_lineage import (
    derive_total_reverse_reference_closure,
    replay_identity_lineage,
)
from memorii.core.memory_evolution.projection_binding import (
    ProjectionHistoryReplayBinding,
)
from memorii.core.memory_evolution.semantic_state import (
    CompiledIdentityLineageTransition,
    LineageEntityIdentity,
    LineageEvidenceReference,
    LineageReferenceDisposition,
)
from memorii.core.semantic_ingestion.contracts import (
    AcceptedTemporalEvidence,
    IdentityLineageRecord,
    OperationTemporalAttachmentBinding,
    OperationTemporalDecisionBinding,
    SemanticGraphDelta,
    contract_digest,
)
from memorii.core.semantic_ingestion.event_replay import (
    ReplayCheckpointLifecycleState,
    ReplayCheckpointResumeAuthority,
    ReplayCheckpointSigningKey,
    ReplayCheckpointTrustPolicy,
    SemanticEventSchemaRegistry,
    SemanticReplayState,
    build_semantic_memory_event_batch,
    replay_semantic_event_batches,
)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class CheckpointKeyMaterial:
    """Opaque deterministic material used only by replay fixtures."""

    def __init__(self, *, key_id: str, secret: bytes) -> None:
        self.key_id = key_id
        self.secret = secret

    @property
    def public_key_fingerprint(self) -> str:
        return hashlib.sha256(self.secret).hexdigest()


class DeterministicCheckpointSignatureAuthority:
    """Fixture signer that satisfies the production checkpoint protocol."""

    def __init__(self, material: CheckpointKeyMaterial) -> None:
        self._material = material

    @property
    def key_id(self) -> str:
        return self._material.key_id

    @property
    def public_key_fingerprint(self) -> str:
        return self._material.public_key_fingerprint

    def sign_checkpoint_digest(self, checkpoint_digest: str) -> str:
        return hmac.new(
            self._material.secret,
            b"memorii.semantic-replay-checkpoint-signature.v1\0"
            + checkpoint_digest.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()

    def verify_checkpoint_signature(
        self, checkpoint_digest: str, signature: str
    ) -> bool:
        return hmac.compare_digest(
            self.sign_checkpoint_digest(checkpoint_digest), signature
        )


def projection_history_bindings(
    repository_id: str,
) -> tuple[ProjectionHistoryReplayBinding, ...]:
    return tuple(
        ProjectionHistoryReplayBinding.create(
            projection_kind=kind,
            repository_id=repository_id,
            history_prefix_digest=_digest(f"{kind}-history-prefix"),
            active_pointer_digest=_digest(f"{kind}-active-pointer"),
            generation_digest=_digest(f"{kind}-generation"),
        )
        for kind in ("temporal", "trust")
    )


class ExactProjectionHistoryVerifier:
    """Fixture verifier for the exact bindings captured by one checkpoint."""

    def __init__(
        self,
        *,
        bindings: tuple[ProjectionHistoryReplayBinding, ...],
        graph_revision: str,
    ) -> None:
        self._bindings = bindings
        self._graph_revision = graph_revision

    def validate_checkpoint_bindings(
        self,
        bindings: tuple[ProjectionHistoryReplayBinding, ...],
        *,
        graph_revision: str,
    ) -> None:
        if bindings != self._bindings or graph_revision != self._graph_revision:
            raise ValueError("projection checkpoint authority diverged")


@dataclass(frozen=True)
class ReplayCheckpointFixture:
    authority: ReplayCheckpointResumeAuthority
    projection_history_bindings: tuple[ProjectionHistoryReplayBinding, ...]
    projection_history_verifier: ExactProjectionHistoryVerifier


def lineage_evidence(label: str = "lineage") -> LineageEvidenceReference:
    """Create deterministic evidence for a fixture-owned lineage transition."""
    return LineageEvidenceReference(
        source_id="source:identity",
        start=0,
        end=5,
        evidence_digest=_digest(label),
    )


def build_identity_rekey_record(
    *,
    claim_terminal: object,
    state: SemanticReplayState,
    predecessor: LineageEntityIdentity,
    successor: LineageEntityIdentity,
    operation_id: str = "operation:rekey",
    recorded_at: datetime,
) -> IdentityLineageRecord:
    """Compile one valid rekey from replay state without test-module imports."""
    # The assertion itself stays immutable; only current resolution redirects.
    claim = claim_terminal.accepted_carriers[0]
    source_binding = claim.temporal_decision_binding
    attachment = OperationTemporalAttachmentBinding.create(
        operation_id=operation_id,
        temporal_role="transition",
        stable_attachment_consensus_digest=(
            source_binding.temporal_attachment.stable_attachment_consensus_digest
        ),
        candidate_ids=source_binding.temporal_attachment.candidate_ids,
        candidate_spans=source_binding.temporal_attachment.candidate_spans,
    )
    binding = OperationTemporalDecisionBinding.create(
        operation_id=operation_id,
        temporal_role="transition",
        scope_assessment_digest=source_binding.scope_assessment_digest,
        semantic_assessment_digest=source_binding.semantic_assessment_digest,
        temporal_attachment=attachment,
        reference_evidence=source_binding.reference_evidence,
        decision_closure=source_binding.decision_closure,
    )
    closure = derive_total_reverse_reference_closure(
        materialized_records=state.materialized_records,
        predecessors=(predecessor,),
        recorded_before=recorded_at,
    )
    dispositions = tuple(
        sorted(
            (
                LineageReferenceDisposition.create(
                    reference_digest=reference.reference_digest,
                    record_kind=reference.record_kind,
                    record_id=reference.record_id,
                    reference_path=reference.reference_path,
                    predecessor=reference.predecessor,
                    disposition=(
                        "preserve_historical"
                        if reference.lifecycle == "historical"
                        else "redirect_current"
                    ),
                    successors=(
                        () if reference.lifecycle == "historical" else (successor,)
                    ),
                    source_evidence=(),
                    basis=(
                        "operation_defined_history_preservation"
                        if reference.lifecycle == "historical"
                        else "operation_defined_rekey_redirect"
                    ),
                )
                for reference in closure
            ),
            key=lambda value: value.reference_digest,
        )
    )
    transition = CompiledIdentityLineageTransition.create(
        operation_id=operation_id,
        operation="rekey",
        predecessors=(predecessor,),
        successors=(successor,),
        graph_revision_before=state.graph_revision,
        recorded_at=recorded_at,
        lineage_snapshot_before_digest=replay_identity_lineage(state).snapshot_digest,
        source_evidence=(lineage_evidence(),),
        reverse_reference_closure=closure,
        reference_dispositions=dispositions,
    )
    temporal_evidence = AcceptedTemporalEvidence(
        reference_evidence=binding.reference_evidence,
        decision_closure=binding.decision_closure,
    )
    body = {
        "record_kind": "identity_lineage",
        "identity_lineage_id": f"identity-lineage:{operation_id}",
        "operation_id": operation_id,
        "valid_interval": temporal_evidence.valid_interval,
        "temporal_evidence": temporal_evidence,
        "temporal_decision_binding": binding,
        "record_version": 1,
        "codec_fingerprint": claim.codec_fingerprint,
        "statement_digest": transition.transition_digest,
        "transition": transition,
    }
    return IdentityLineageRecord.model_validate(
        body | {"record_digest": contract_digest(
            b"memorii.semantic-ingestion.temporal-carrier.v1", body
        )}
    )


def build_identity_lineage_delta(record: IdentityLineageRecord) -> SemanticGraphDelta:
    """Wrap one compiled lineage record in the canonical graph delta."""
    body = {
        "kind": "semantic_graph_delta",
        "operation_id": record.operation_id,
        "carriers": (record,),
        "terminal_binding_sets": (),
    }
    return SemanticGraphDelta(
        **body,
        delta_digest=contract_digest(
            b"memorii.semantic-ingestion.graph-delta.v1", body
        ),
    )


def append_identity_lineage_batch(
    *,
    record: IdentityLineageRecord,
    registry: SemanticEventSchemaRegistry,
    state: SemanticReplayState,
    repository_id: str,
    graph_revision_after: str,
    timestamp: datetime,
):
    """Build and replay one lineage batch for focused event-replay tests."""
    batch = build_semantic_memory_event_batch(
        graph_delta=build_identity_lineage_delta(record),
        prior_state=state,
        repository_id=repository_id,
        source_id="source:identity",
        transaction_group_id="group:identity",
        operation_fence_id="fence:identity",
        writer_epoch=1,
        graph_revision_before=state.graph_revision,
        graph_revision_after=graph_revision_after,
        timestamp=timestamp,
        registry=registry,
    )
    return batch, replay_semantic_event_batches(
        repository_id=repository_id,
        batches=(batch,),
        registry=registry,
        initial_state=state,
    )


def build_replay_checkpoint_fixture(
    *,
    repository_id: str,
    registry: SemanticEventSchemaRegistry,
    graph_revision: str,
    key_id: str = "checkpoint-key",
    secret: bytes = b"k" * 32,
    policy_revision: int = 1,
    authority_revision: int = 1,
    valid_from: datetime,
) -> ReplayCheckpointFixture:
    """Build the complete test-only authority needed to checkpoint and reopen."""
    material = CheckpointKeyMaterial(key_id=key_id, secret=secret)
    signature_authority = DeterministicCheckpointSignatureAuthority(material)
    key = ReplayCheckpointSigningKey.create(
        key_id=material.key_id,
        issuer_id="operator",
        public_key_fingerprint=material.public_key_fingerprint,
        valid_from=valid_from,
    )
    policy = ReplayCheckpointTrustPolicy.create(
        policy_revision=policy_revision,
        authorized_repository_id=repository_id,
        keys=(key,),
    )
    lifecycle = ReplayCheckpointLifecycleState.create(
        repository_id=repository_id,
        authority_revision=authority_revision,
        registry=registry,
        trust_policy=policy,
    )
    authority = ReplayCheckpointResumeAuthority(
        lifecycle=lifecycle,
        registry=registry,
        trust_policy=policy,
        signature_authority_provider=lambda _: signature_authority,
        signing_key_id=material.key_id,
    )
    bindings = projection_history_bindings(repository_id)
    return ReplayCheckpointFixture(
        authority=authority,
        projection_history_bindings=bindings,
        projection_history_verifier=ExactProjectionHistoryVerifier(
            bindings=bindings, graph_revision=graph_revision
        ),
    )
