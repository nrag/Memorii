from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from memorii.core.memory_evolution.identity_lineage import (
    IdentityLineageError,
    derive_claim_reverse_reference_closure,
    derive_total_reverse_reference_closure,
    identity_lineage_audit_view,
    replay_identity_lineage,
)
from memorii.core.memory_evolution.projection_binding import (
    ProjectionHistoryReplayBinding,
)
from memorii.core.memory_evolution.projection_history import (
    projection_records_from_replay_state,
)
from memorii.core.memory_evolution.semantic_state import (
    CompiledIdentityLineageTransition,
    LineageEntityIdentity,
    LineageEvidenceReference,
    LineageReferenceDisposition,
    LineageReverseReference,
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
    FileSemanticEventRepository,
    ReplayCheckpointLifecycleState,
    ReplayCheckpointResumeAuthority,
    ReplayCheckpointSigningKey,
    ReplayCheckpointTrustPolicy,
    SemanticEventReplayError,
    SemanticEventSchemaRegistry,
    SemanticReplayState,
    build_semantic_memory_event_batch,
    create_replay_checkpoint,
    encode_semantic_memory_event_batch,
    replay_semantic_checkpoint_tail,
    replay_semantic_event_batches,
)
from pydantic import ValidationError
from semantic_terminal_test_support import NOW, accepted_terminal

REPOSITORY_ID = "identity-lineage"
ALICE_V1 = LineageEntityIdentity(
    entity_revision_id="entity-revision:alice:v1",
    logical_entity_id="entity:alice",
)
ALICE_V2 = LineageEntityIdentity(
    entity_revision_id="entity-revision:alice:v2",
    logical_entity_id="entity:alice",
)
ALICE_V3 = LineageEntityIdentity(
    entity_revision_id="entity-revision:alice:v3",
    logical_entity_id="entity:alice",
)


class _CheckpointSignatureAuthority:
    key_id = "identity-lineage-checkpoint"
    secret = b"identity-lineage-checkpoint-key"

    @property
    def public_key_fingerprint(self) -> str:
        return hashlib.sha256(self.secret).hexdigest()

    def sign_checkpoint_digest(self, checkpoint_digest: str) -> str:
        return hmac.new(
            self.secret,
            b"memorii.semantic-replay-checkpoint-signature.v1\0"
            + checkpoint_digest.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()

    def verify_checkpoint_signature(self, checkpoint_digest: str, signature: str) -> bool:
        return hmac.compare_digest(
            self.sign_checkpoint_digest(checkpoint_digest),
            signature,
        )


class _ProjectionVerifier:
    def __init__(self, bindings, graph_revision: str) -> None:
        self.bindings = bindings
        self.graph_revision = graph_revision

    def validate_checkpoint_bindings(self, bindings, *, graph_revision: str) -> None:
        if bindings != self.bindings or graph_revision != self.graph_revision:
            raise ValueError("projection binding mismatch")


def _evidence(label: str = "lineage") -> LineageEvidenceReference:
    return LineageEvidenceReference(
        source_id="source:identity",
        start=0,
        end=5,
        evidence_digest=sha256(label.encode()).hexdigest(),
    )


def _claim_state():
    terminal = accepted_terminal(
        operation_id="claim-terminal:alice",
        source_text="Alice works for Globex.",
        source_id="source:claim:alice",
        subject_logical_entity_id="entity:alice",
        subject_entity_revision_id="entity-revision:alice:v1",
        object_logical_entity_id="entity:globex",
        object_entity_revision_id="entity-revision:globex:v1",
    )
    registry = SemanticEventSchemaRegistry.create()
    genesis = SemanticReplayState.genesis(REPOSITORY_ID)
    batch = build_semantic_memory_event_batch(
        graph_delta=SemanticGraphDelta.create(terminal),
        prior_state=genesis,
        repository_id=REPOSITORY_ID,
        source_id="source:claim:alice",
        transaction_group_id="group:claim:alice",
        operation_fence_id="fence:claim:alice",
        writer_epoch=1,
        graph_revision_before="genesis",
        graph_revision_after="graph:1",
        timestamp=NOW,
        registry=registry,
    )
    state = replay_semantic_event_batches(
        repository_id=REPOSITORY_ID,
        batches=(batch,),
        registry=registry,
    )
    return terminal, registry, batch, state


def _dispositions(
    closure,
    *,
    successor: LineageEntityIdentity,
    operation: str,
):
    values = []
    for reference in closure:
        if reference.lifecycle == "historical":
            values.append(
                LineageReferenceDisposition.create(
                    reference_digest=reference.reference_digest,
                    record_kind=reference.record_kind,
                    record_id=reference.record_id,
                    reference_path=reference.reference_path,
                    predecessor=reference.predecessor,
                    disposition="preserve_historical",
                    successors=(),
                    source_evidence=(),
                    basis="operation_defined_history_preservation",
                )
            )
            continue
        basis = {
            "rekey": "operation_defined_rekey_redirect",
            "merge": "operation_defined_merge_redirect",
            "split": "source_assignment",
        }[operation]
        values.append(
            LineageReferenceDisposition.create(
                reference_digest=reference.reference_digest,
                record_kind=reference.record_kind,
                record_id=reference.record_id,
                reference_path=reference.reference_path,
                predecessor=reference.predecessor,
                disposition=("migrate_current" if operation == "split" else "redirect_current"),
                successors=(successor,),
                source_evidence=((_evidence("assignment"),) if operation == "split" else ()),
                basis=basis,
            )
        )
    return tuple(sorted(values, key=lambda item: item.reference_digest))


def _lineage_record(
    *,
    claim_terminal,
    state,
    operation_id: str = "operation:rekey",
    predecessor: LineageEntityIdentity = ALICE_V1,
    successor: LineageEntityIdentity = ALICE_V2,
):
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
    recorded_at = NOW + timedelta(minutes=1)
    closure = derive_total_reverse_reference_closure(
        materialized_records=state.materialized_records,
        predecessors=(predecessor,),
        recorded_before=recorded_at,
    )
    transition = CompiledIdentityLineageTransition.create(
        operation_id=operation_id,
        operation="rekey",
        predecessors=(predecessor,),
        successors=(successor,),
        graph_revision_before=state.graph_revision,
        recorded_at=recorded_at,
        lineage_snapshot_before_digest=replay_identity_lineage(state).snapshot_digest,
        source_evidence=(_evidence(),),
        reverse_reference_closure=closure,
        reference_dispositions=_dispositions(
            closure,
            successor=successor,
            operation="rekey",
        ),
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
        body
        | {
            "record_digest": contract_digest(
                b"memorii.semantic-ingestion.temporal-carrier.v1",
                body,
            )
        }
    )


def _append_lineage(record, *, registry, state, graph_revision_after: str = "graph:2"):
    delta_body = {
        "kind": "semantic_graph_delta",
        "operation_id": record.operation_id,
        "carriers": (record,),
        "terminal_binding_sets": (),
    }
    delta = SemanticGraphDelta(
        **delta_body,
        delta_digest=contract_digest(
            b"memorii.semantic-ingestion.graph-delta.v1",
            delta_body,
        ),
    )
    batch = build_semantic_memory_event_batch(
        graph_delta=delta,
        prior_state=state,
        repository_id=REPOSITORY_ID,
        source_id="source:identity",
        transaction_group_id="group:identity",
        operation_fence_id="fence:identity",
        writer_epoch=1,
        graph_revision_before=state.graph_revision,
        graph_revision_after=graph_revision_after,
        timestamp=NOW + timedelta(minutes=1),
        registry=registry,
    )
    replayed = replay_semantic_event_batches(
        repository_id=REPOSITORY_ID,
        batches=(batch,),
        registry=registry,
        initial_state=state,
    )
    return batch, replayed


def _record_with_transition(
    record: IdentityLineageRecord,
    transition: CompiledIdentityLineageTransition,
) -> IdentityLineageRecord:
    body = record.model_dump(mode="python", exclude={"record_digest"}) | {
        "statement_digest": transition.transition_digest,
        "transition": transition,
    }
    return IdentityLineageRecord.model_validate(
        body
        | {
            "record_digest": contract_digest(
                b"memorii.semantic-ingestion.temporal-carrier.v1", body
            )
        }
    )


def _batch_for_lineage(record, *, registry, state):
    delta_body = {
        "kind": "semantic_graph_delta",
        "operation_id": record.operation_id,
        "carriers": (record,),
        "terminal_binding_sets": (),
    }
    delta = SemanticGraphDelta(
        **delta_body,
        delta_digest=contract_digest(
            b"memorii.semantic-ingestion.graph-delta.v1", delta_body
        ),
    )
    return build_semantic_memory_event_batch(
        graph_delta=delta,
        prior_state=state,
        repository_id=REPOSITORY_ID,
        source_id="source:identity",
        transaction_group_id="group:identity:tampered",
        operation_fence_id="fence:identity:tampered",
        writer_epoch=1,
        graph_revision_before=state.graph_revision,
        graph_revision_after="graph:2",
        timestamp=NOW + timedelta(minutes=1),
        registry=registry,
    )


def test_rekey_preserves_assertion_revision_and_projection_identity_across_replay() -> None:
    terminal, registry, _, claim_state = _claim_state()
    record = _lineage_record(claim_terminal=terminal, state=claim_state)
    _, state = _append_lineage(record, registry=registry, state=claim_state)

    current = identity_lineage_audit_view(state)
    historical = identity_lineage_audit_view(
        state,
        system_time=NOW + timedelta(seconds=1),
    )
    resolved = current.resolved_claims[0].subject
    assert resolved.assertion_reference.entity_revision_id == ALICE_V1.entity_revision_id
    assert resolved.resolved_identity == ALICE_V2
    assert historical.resolved_claims[0].subject.resolved_identity == ALICE_V1

    temporal, trust, _, _, _ = projection_records_from_replay_state(state)
    claim_temporal = tuple(item for item in temporal if item.claim_slot_key is not None)
    claim_trust = tuple(item for item in trust if item.claim_slot_key is not None)
    temporal_slot = claim_temporal[0].claim_slot_key
    trust_assertion_key = claim_trust[0].evidence[0].assertion_key
    assert temporal_slot is not None
    assert trust_assertion_key is not None
    assert temporal_slot.subject_logical_entity_id == "entity:alice"
    assert trust_assertion_key.slot.subject_logical_entity_id == "entity:alice"


def test_rekey_exact_restart_is_stable_and_same_prefix_contention_fails_closed() -> None:
    terminal, registry, claim_batch, claim_state = _claim_state()
    record = _lineage_record(claim_terminal=terminal, state=claim_state)
    lineage_batch, state = _append_lineage(record, registry=registry, state=claim_state)

    restarted = replay_semantic_event_batches(
        repository_id=REPOSITORY_ID,
        batches=(claim_batch, lineage_batch),
        registry=registry,
    )
    assert identity_lineage_audit_view(restarted) == identity_lineage_audit_view(state)

    competing = record.transition.model_copy(
        update={
            "operation_id": "operation:rekey:competing",
            "successors": (
                LineageEntityIdentity(
                    entity_revision_id="entity-revision:alice:v3",
                    logical_entity_id="entity:alice",
                ),
            ),
        }
    )
    corrupted_record = record.model_copy(update={"transition": competing})
    corrupted_state = state.model_copy(
        update={
            "materialized_records": state.materialized_records
            + (state.materialized_records[-1].model_copy(update={"record": corrupted_record}),),
        }
    )
    with pytest.raises((IdentityLineageError, ValidationError)):
        replay_identity_lineage(corrupted_state)


def test_merge_and_split_contracts_reject_wrong_basis_and_default_fanout() -> None:
    bob = LineageEntityIdentity(
        entity_revision_id="entity-revision:bob:v1",
        logical_entity_id="entity:bob",
    )
    merged = LineageEntityIdentity(
        entity_revision_id="entity-revision:people:v1",
        logical_entity_id="entity:people",
    )
    CompiledIdentityLineageTransition.create(
        operation_id="operation:merge",
        operation="merge",
        predecessors=tuple(sorted((ALICE_V1, bob), key=lambda item: item.entity_revision_id)),
        successors=(merged,),
        graph_revision_before="graph:1",
        recorded_at=NOW,
        lineage_snapshot_before_digest="a" * 64,
        source_evidence=(_evidence("merge"),),
        reverse_reference_closure=(),
        reference_dispositions=(),
    )

    child_a = LineageEntityIdentity(
        entity_revision_id="entity-revision:alice-child-a:v1",
        logical_entity_id="entity:alice-child-a",
    )
    child_b = LineageEntityIdentity(
        entity_revision_id="entity-revision:alice-child-b:v1",
        logical_entity_id="entity:alice-child-b",
    )
    reference = derive_claim_reverse_reference_closure(
        claims=_claim_state()[3].materialized_records,
        predecessors=(ALICE_V1,),
        recorded_before=NOW + timedelta(minutes=1),
    )[1]
    with pytest.raises(ValidationError, match="shape"):
        LineageReferenceDisposition.create(
            reference_digest=reference.reference_digest,
            record_kind=reference.record_kind,
            record_id=reference.record_id,
            reference_path=reference.reference_path,
            predecessor=reference.predecessor,
            disposition="share_by_explicit_evidence",
            successors=tuple(sorted((child_a, child_b), key=lambda item: item.entity_revision_id)),
            source_evidence=(),
            basis="source_assignment",
        )


def test_event_builder_rejects_lineage_graph_revision_substitution() -> None:
    terminal, registry, _, claim_state = _claim_state()
    record = _lineage_record(claim_terminal=terminal, state=claim_state)
    transition_body = record.transition.model_dump(
        mode="python",
        exclude={"transition_digest"},
    )
    transition_body["graph_revision_before"] = "graph:foreign"
    bad_transition = CompiledIdentityLineageTransition.create(**transition_body)
    record_body = record.model_dump(mode="python", exclude={"record_digest"})
    record_body.update(
        {
            "transition": bad_transition,
            "statement_digest": bad_transition.transition_digest,
        }
    )
    bad_record = IdentityLineageRecord.model_validate(
        record_body
        | {
            "record_digest": contract_digest(
                b"memorii.semantic-ingestion.temporal-carrier.v1",
                record_body,
            )
        }
    )
    delta_body = {
        "kind": "semantic_graph_delta",
        "operation_id": bad_record.operation_id,
        "carriers": (bad_record,),
        "terminal_binding_sets": (),
    }
    delta = SemanticGraphDelta.model_construct(
        **delta_body,
        delta_digest=contract_digest(
            b"memorii.semantic-ingestion.graph-delta.v1",
            delta_body,
        ),
    )

    with pytest.raises(SemanticEventReplayError, match="identity_lineage_graph_revision_mismatch"):
        build_semantic_memory_event_batch(
            graph_delta=delta,
            prior_state=claim_state,
            repository_id=REPOSITORY_ID,
            source_id="source:identity",
            transaction_group_id="group:identity:bad",
            operation_fence_id="fence:identity:bad",
            writer_epoch=1,
            graph_revision_before=claim_state.graph_revision,
            graph_revision_after="graph:2",
            timestamp=datetime(2026, 3, 1, tzinfo=UTC),
            registry=registry,
        )


def test_lineage_jsonl_restart_exact_duplicate_and_corrupt_tail_are_fail_closed(
    tmp_path: Path,
) -> None:
    terminal, registry, claim_batch, claim_state = _claim_state()
    record = _lineage_record(claim_terminal=terminal, state=claim_state)
    lineage_batch, state = _append_lineage(record, registry=registry, state=claim_state)
    path = tmp_path / "identity-lineage-events.jsonl"
    repository = FileSemanticEventRepository(
        path,
        repository_id=REPOSITORY_ID,
        registry=registry,
    )

    repository.append_batch(claim_batch)
    repository.append_batch(lineage_batch)
    assert repository.append_batch(lineage_batch) == lineage_batch
    reopened = FileSemanticEventRepository(
        path,
        repository_id=REPOSITORY_ID,
        registry=registry,
    )
    assert identity_lineage_audit_view(reopened.replay_genesis()) == identity_lineage_audit_view(state)

    path.write_bytes(path.read_bytes() + b'{"canonical_hex":"00"}\n')
    with pytest.raises(SemanticEventReplayError):
        reopened.replay_genesis()


@pytest.mark.parametrize("mutation", ("missing", "extra", "substituted"))
def test_historical_lineage_closure_tamper_rejects_genesis_checkpoint_and_reopen(
    tmp_path: Path,
    mutation: str,
) -> None:
    terminal, registry, claim_batch, claim_state = _claim_state()
    record = _lineage_record(claim_terminal=terminal, state=claim_state)
    transition = record.transition
    closure = list(transition.reverse_reference_closure)
    dispositions = {
        item.reference_digest: item
        for item in transition.reference_dispositions
    }
    original = closure[0]
    original_disposition = dispositions[original.reference_digest]
    forged = LineageReverseReference.create(
        record_kind=original.record_kind,
        record_id=(
            "forged-record" if mutation == "extra" else original.record_id
        ),
        reference_path=original.reference_path,
        predecessor=original.predecessor,
        lifecycle=original.lifecycle,
        base_record_digest="f" * 64,
        referenced_value_digest=original.referenced_value_digest,
    )
    forged_disposition = LineageReferenceDisposition.create(
        reference_digest=forged.reference_digest,
        record_kind=forged.record_kind,
        record_id=forged.record_id,
        reference_path=forged.reference_path,
        predecessor=forged.predecessor,
        disposition=original_disposition.disposition,
        successors=original_disposition.successors,
        source_evidence=original_disposition.source_evidence,
        basis=original_disposition.basis,
    )
    if mutation == "missing":
        closure = closure[1:]
        dispositions.pop(original.reference_digest)
    elif mutation == "extra":
        closure.append(forged)
        dispositions[forged.reference_digest] = forged_disposition
    else:
        closure[0] = forged
        dispositions.pop(original.reference_digest)
        dispositions[forged.reference_digest] = forged_disposition
    transition_values = transition.model_dump(
        mode="python", exclude={"transition_digest"}
    ) | {
        "reverse_reference_closure": tuple(
            sorted(closure, key=lambda item: item.reference_digest)
        ),
        "reference_dispositions": tuple(
            sorted(dispositions.values(), key=lambda item: item.reference_digest)
        ),
    }
    tampered_transition = CompiledIdentityLineageTransition.create(
        **transition_values
    )
    tampered_record = _record_with_transition(record, tampered_transition)
    tampered_batch = _batch_for_lineage(
        tampered_record,
        registry=registry,
        state=claim_state,
    )

    with pytest.raises(
        SemanticEventReplayError,
        match="identity_lineage_reference_closure_mismatch",
    ):
        replay_semantic_event_batches(
            repository_id=REPOSITORY_ID,
            batches=(claim_batch, tampered_batch),
            registry=registry,
        )

    signature_authority = _CheckpointSignatureAuthority()
    key = ReplayCheckpointSigningKey.create(
        key_id=signature_authority.key_id,
        issuer_id="operator",
        public_key_fingerprint=signature_authority.public_key_fingerprint,
        valid_from=datetime(2025, 1, 1, tzinfo=UTC),
    )
    policy = ReplayCheckpointTrustPolicy.create(
        policy_revision=1,
        authorized_repository_id=REPOSITORY_ID,
        keys=(key,),
    )
    lifecycle = ReplayCheckpointLifecycleState.create(
        repository_id=REPOSITORY_ID,
        authority_revision=1,
        registry=registry,
        trust_policy=policy,
    )
    authority = ReplayCheckpointResumeAuthority(
        lifecycle=lifecycle,
        registry=registry,
        trust_policy=policy,
        signature_authority_provider=lambda _: signature_authority,
        signing_key_id=signature_authority.key_id,
    )
    checkpoint = create_replay_checkpoint(
        state=claim_state,
        watermark_batch=claim_batch,
        writer_epoch=1,
        authority=authority,
        created_at=NOW + timedelta(seconds=1),
    )
    with pytest.raises(
        SemanticEventReplayError,
        match="identity_lineage_reference_closure_mismatch",
    ):
        replay_semantic_checkpoint_tail(
            checkpoint,
            tail_batches=(tampered_batch,),
            authority=authority,
            projection_history_verifier=_ProjectionVerifier(
                (), claim_state.graph_revision
            ),
        )

    path = tmp_path / f"tampered-{mutation}.jsonl"
    path.write_bytes(
        b"".join(
            json.dumps(
                {"canonical_hex": encode_semantic_memory_event_batch(batch).hex()},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            + b"\n"
            for batch in (claim_batch, tampered_batch)
        )
    )
    reopened = FileSemanticEventRepository(
        path,
        repository_id=REPOSITORY_ID,
        registry=registry,
    )
    exposed = None
    with pytest.raises(
        SemanticEventReplayError,
        match="identity_lineage_reference_closure_mismatch",
    ):
        exposed = reopened.replay_genesis()
    assert exposed is None


def test_lineage_checkpoint_tail_is_byte_equivalent_to_genesis_prefix() -> None:
    terminal, registry, claim_batch, claim_state = _claim_state()
    record = _lineage_record(claim_terminal=terminal, state=claim_state)
    lineage_batch, state = _append_lineage(record, registry=registry, state=claim_state)
    signature_authority = _CheckpointSignatureAuthority()
    key = ReplayCheckpointSigningKey.create(
        key_id=signature_authority.key_id,
        issuer_id="operator",
        public_key_fingerprint=signature_authority.public_key_fingerprint,
        valid_from=datetime(2025, 1, 1, tzinfo=UTC),
    )
    policy = ReplayCheckpointTrustPolicy.create(
        policy_revision=1,
        authorized_repository_id=REPOSITORY_ID,
        keys=(key,),
    )
    lifecycle = ReplayCheckpointLifecycleState.create(
        repository_id=REPOSITORY_ID,
        authority_revision=1,
        registry=registry,
        trust_policy=policy,
    )
    authority = ReplayCheckpointResumeAuthority(
        lifecycle=lifecycle,
        registry=registry,
        trust_policy=policy,
        signature_authority_provider=lambda _: signature_authority,
        signing_key_id=signature_authority.key_id,
    )
    bindings = tuple(
        ProjectionHistoryReplayBinding.create(
            projection_kind=kind,
            repository_id=REPOSITORY_ID,
            history_prefix_digest=sha256(f"{kind}:history".encode()).hexdigest(),
            active_pointer_digest=sha256(f"{kind}:pointer".encode()).hexdigest(),
            generation_digest=sha256(f"{kind}:generation".encode()).hexdigest(),
        )
        for kind in ("temporal", "trust")
    )
    checkpoint = create_replay_checkpoint(
        state=claim_state,
        watermark_batch=claim_batch,
        writer_epoch=1,
        authority=authority,
        created_at=NOW + timedelta(seconds=1),
        projection_history_bindings=bindings,
    )

    resumed = replay_semantic_checkpoint_tail(
        checkpoint,
        tail_batches=(lineage_batch,),
        authority=authority,
        projection_history_verifier=_ProjectionVerifier(
            bindings,
            claim_state.graph_revision,
        ),
    )

    assert resumed == state
    assert identity_lineage_audit_view(resumed) == identity_lineage_audit_view(state)


def test_multi_lineage_checkpoint_tail_matches_genesis_replay() -> None:
    terminal, registry, claim_batch, claim_state = _claim_state()
    first_record = _lineage_record(claim_terminal=terminal, state=claim_state)
    first_batch, first_state = _append_lineage(
        first_record, registry=registry, state=claim_state
    )
    second_record = _lineage_record(
        claim_terminal=terminal,
        state=first_state,
        operation_id="operation:rekey:v2-v3",
        predecessor=ALICE_V2,
        successor=ALICE_V3,
    )
    second_batch, final_state = _append_lineage(
        second_record,
        registry=registry,
        state=first_state,
        graph_revision_after="graph:3",
    )
    signature_authority = _CheckpointSignatureAuthority()
    key = ReplayCheckpointSigningKey.create(
        key_id=signature_authority.key_id,
        issuer_id="operator",
        public_key_fingerprint=signature_authority.public_key_fingerprint,
        valid_from=datetime(2025, 1, 1, tzinfo=UTC),
    )
    policy = ReplayCheckpointTrustPolicy.create(
        policy_revision=1,
        authorized_repository_id=REPOSITORY_ID,
        keys=(key,),
    )
    lifecycle = ReplayCheckpointLifecycleState.create(
        repository_id=REPOSITORY_ID,
        authority_revision=1,
        registry=registry,
        trust_policy=policy,
    )
    authority = ReplayCheckpointResumeAuthority(
        lifecycle=lifecycle,
        registry=registry,
        trust_policy=policy,
        signature_authority_provider=lambda _: signature_authority,
        signing_key_id=signature_authority.key_id,
    )
    bindings = tuple(
        ProjectionHistoryReplayBinding.create(
            projection_kind=kind,
            repository_id=REPOSITORY_ID,
            history_prefix_digest=sha256(f"multi:{kind}:history".encode()).hexdigest(),
            active_pointer_digest=sha256(f"multi:{kind}:pointer".encode()).hexdigest(),
            generation_digest=sha256(f"multi:{kind}:generation".encode()).hexdigest(),
        )
        for kind in ("temporal", "trust")
    )
    checkpoint = create_replay_checkpoint(
        state=first_state,
        watermark_batch=first_batch,
        writer_epoch=1,
        authority=authority,
        created_at=NOW + timedelta(minutes=2),
        projection_history_bindings=bindings,
    )
    resumed = replay_semantic_checkpoint_tail(
        checkpoint,
        tail_batches=(second_batch,),
        authority=authority,
        projection_history_verifier=_ProjectionVerifier(
            bindings, first_state.graph_revision
        ),
    )
    from_genesis = replay_semantic_event_batches(
        repository_id=REPOSITORY_ID,
        batches=(claim_batch, first_batch, second_batch),
        registry=registry,
    )
    assert resumed == final_state == from_genesis
    assert replay_identity_lineage(resumed).snapshot_digest == (
        second_record.transition.lineage_snapshot_after_digest
    )
