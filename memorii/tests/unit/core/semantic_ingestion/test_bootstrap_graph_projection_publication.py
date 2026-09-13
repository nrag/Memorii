from hashlib import sha256

import pytest
from memorii.core.semantic_ingestion.bootstrap_graph_projection_publication import (
    BootstrapGraphNativeProjectionPublicationReceiptV3,
    BootstrapGraphNativeReplayAuthorityEvidenceV3,
    BootstrapGraphNativeReplayCheckpointEvidenceV3,
    native_projection_authority_evidence_id,
    native_projection_checkpoint_evidence_id,
    native_projection_publication_receipt_id,
    publication_identity_digest,
    validate_native_projection_publication_evidence_coordinates,
)
from memorii.core.semantic_ingestion.contracts import SemanticGraphDelta
from memorii.core.semantic_ingestion.event_replay import (
    SemanticEventSchemaRegistry,
    SemanticReplayAuthorityAggregate,
    SemanticReplayState,
    advance_semantic_replay_authority,
    build_semantic_memory_event_batch,
    create_replay_checkpoint,
    replay_semantic_event_batches,
)
from pydantic import BaseModel, ValidationError
from tests.fixtures.semantic_ingestion.event_replay_fixture import build_replay_checkpoint_fixture
from tests.fixtures.semantic_ingestion.semantic_terminal_fixture import NOW, accepted_terminal
from tests.unit.core.test_projection_history import _Clock, _repository, _request


def _native_delta_and_batch(*, repository_id: str = "projection-publication-repository"):
    terminal = accepted_terminal(operation_id="projection-publication:identity")
    graph_delta = SemanticGraphDelta.create(terminal)
    state = SemanticReplayState.genesis(repository_id)
    source = terminal.source_analyses[0]
    event_batch = build_semantic_memory_event_batch(
        graph_delta=graph_delta,
        prior_state=state,
        repository_id=state.repository_id,
        source_id=source.source_id,
        transaction_group_id="projection-publication-group",
        operation_fence_id="projection-publication-fence",
        writer_epoch=1,
        graph_revision_before=state.graph_revision,
        graph_revision_after="projection-publication-after",
        timestamp=NOW,
        registry=SemanticEventSchemaRegistry.create(),
    )
    return graph_delta, event_batch, state, source.source_id


def _receipt_and_evidence(tmp_path, *, match_projection_revision=False):
    publication = _repository(tmp_path / "projection-history", _Clock(NOW)).install(
        _request(1, outcome="pass")
    )
    graph_delta, _, prior_state, source_id = _native_delta_and_batch(repository_id="semantic_ingestion")
    registry = SemanticEventSchemaRegistry.create()
    event_batch = build_semantic_memory_event_batch(
        graph_delta=graph_delta,
        prior_state=prior_state,
        repository_id="semantic_ingestion",
        source_id=source_id,
        transaction_group_id="projection-publication-group",
        operation_fence_id="projection-publication-fence",
        writer_epoch=1,
        graph_revision_before=prior_state.graph_revision,
        graph_revision_after=(publication.temporal.generation.base_graph_revision if match_projection_revision else "projection-publication-after"),
        timestamp=NOW,
        registry=registry,
    )
    replay_state = replay_semantic_event_batches(
        repository_id="semantic_ingestion",
        batches=(event_batch,),
        registry=registry,
        initial_state=prior_state,
    )
    checkpoint_fixture = build_replay_checkpoint_fixture(
        repository_id="semantic_ingestion",
        registry=registry,
        graph_revision=replay_state.graph_revision,
        valid_from=NOW,
    )
    checkpoint_bundle = create_replay_checkpoint(
        state=replay_state,
        watermark_batch=event_batch,
        writer_epoch=1,
        authority=checkpoint_fixture.authority,
        created_at=NOW,
        projection_history_bindings=publication.replay_bindings,
    )
    aggregate = advance_semantic_replay_authority(
        SemanticReplayAuthorityAggregate.genesis("semantic_ingestion"),
        graph_state=replay_state,
        member_bindings=(),
        reconstructed_authority_digest=checkpoint_bundle.checkpoint.reconstructed_replay_authority_digest,
        latest_checkpoint=checkpoint_bundle,
        projection_history_bindings=publication.replay_bindings,
    )
    source_operation_id = "projection-publication:source-operation"
    request_digest = sha256(b"projection-publication-request").hexdigest()
    identity = publication_identity_digest(
        source_operation_id=source_operation_id,
        transaction_group_id=event_batch.transaction_group_id,
        request_ctv_digest=request_digest,
        canonical_graph_delta=graph_delta,
        canonical_event_batch=event_batch,
    )
    authority_digest = sha256(b"authority-evidence").hexdigest()
    checkpoint_digest = sha256(b"checkpoint-evidence").hexdigest()
    temporal_binding, trust_binding = publication.replay_bindings
    bindings = (temporal_binding, trust_binding)
    receipt = BootstrapGraphNativeProjectionPublicationReceiptV3(
        schema_version=1,
        source_operation_id=source_operation_id,
        transaction_group_id=event_batch.transaction_group_id,
        request_ctv_digest=request_digest,
        graph_revision_before=prior_state.graph_revision,
        graph_revision_after=replay_state.graph_revision,
        canonical_graph_delta=graph_delta,
        canonical_event_batch=event_batch,
        temporal_publication=publication.temporal,
        trust_publication=publication.trust,
        projection_history_replay_bindings=bindings,
        replay_authority_evidence_id=native_projection_authority_evidence_id(identity),
        replay_authority_evidence_digest=authority_digest,
        replay_checkpoint_evidence_id=native_projection_checkpoint_evidence_id(identity),
        replay_checkpoint_evidence_digest=checkpoint_digest,
        publication_identity_digest=identity,
        receipt_digest=sha256(b"receipt").hexdigest(),
    )
    receipt_id = native_projection_publication_receipt_id(identity)
    authority_evidence = BootstrapGraphNativeReplayAuthorityEvidenceV3(
        schema_version=1,
        source_operation_id=source_operation_id,
        transaction_group_id=event_batch.transaction_group_id,
        request_ctv_digest=request_digest,
        publication_identity_digest=identity,
        receipt_id=receipt_id,
        aggregate=aggregate,
        evidence_digest=authority_digest,
    )
    checkpoint_evidence = BootstrapGraphNativeReplayCheckpointEvidenceV3(
        schema_version=1,
        source_operation_id=source_operation_id,
        transaction_group_id=event_batch.transaction_group_id,
        request_ctv_digest=request_digest,
        publication_identity_digest=identity,
        receipt_id=receipt_id,
        checkpoint_bundle=checkpoint_bundle,
        evidence_digest=checkpoint_digest,
    )
    return receipt, receipt_id, authority_evidence, checkpoint_evidence


def test_publication_identity_uses_exact_lp_components() -> None:
    graph_delta, event_batch, _, _ = _native_delta_and_batch()
    source_operation_id = "projection-publication:source-operation"
    transaction_group_id = event_batch.transaction_group_id
    request_digest = sha256(b"projection-publication-request").hexdigest()

    identity = publication_identity_digest(
        source_operation_id=source_operation_id,
        transaction_group_id=transaction_group_id,
        request_ctv_digest=request_digest,
        canonical_graph_delta=graph_delta,
        canonical_event_batch=event_batch,
    )
    parts = (
        b"memorii.bootstrap-graph.native-projection-publication-identity.v3",
        source_operation_id.encode("utf-8"),
        transaction_group_id.encode("utf-8"),
        request_digest.encode("ascii"),
        graph_delta.delta_digest.encode("ascii"),
        event_batch.source_event_batch_digest.encode("ascii"),
    )
    expected = sha256(b"".join(len(part).to_bytes(8, "big") + part for part in parts)).hexdigest()

    assert identity == expected
    prefix = f"semantic_ingestion:bootstrap-graph-v3:native-projection-publication:{identity}"
    assert native_projection_publication_receipt_id(identity) == f"{prefix}:receipt"
    assert native_projection_authority_evidence_id(identity) == f"{prefix}:aggregate"
    assert native_projection_checkpoint_evidence_id(identity) == f"{prefix}:checkpoint"


def test_publication_models_have_only_the_approved_fields() -> None:
    assert tuple(BootstrapGraphNativeProjectionPublicationReceiptV3.model_fields) == (
        "schema_version",
        "source_operation_id",
        "transaction_group_id",
        "request_ctv_digest",
        "graph_revision_before",
        "graph_revision_after",
        "canonical_graph_delta",
        "canonical_event_batch",
        "temporal_publication",
        "trust_publication",
        "projection_history_replay_bindings",
        "replay_authority_evidence_id",
        "replay_authority_evidence_digest",
        "replay_checkpoint_evidence_id",
        "replay_checkpoint_evidence_digest",
        "publication_identity_digest",
        "receipt_digest",
    )
    expected_evidence_fields = (
        "schema_version",
        "source_operation_id",
        "transaction_group_id",
        "request_ctv_digest",
        "publication_identity_digest",
        "receipt_id",
    )
    assert tuple(BootstrapGraphNativeReplayAuthorityEvidenceV3.model_fields) == (
        *expected_evidence_fields,
        "aggregate",
        "evidence_digest",
    )
    assert tuple(BootstrapGraphNativeReplayCheckpointEvidenceV3.model_fields) == (
        *expected_evidence_fields,
        "checkpoint_bundle",
        "evidence_digest",
    )


@pytest.mark.parametrize(
    "model",
    (
        BootstrapGraphNativeProjectionPublicationReceiptV3,
        BootstrapGraphNativeReplayAuthorityEvidenceV3,
        BootstrapGraphNativeReplayCheckpointEvidenceV3,
    ),
)
def test_profile_three_models_reject_boolean_schema_version(model: type[BaseModel]) -> None:
    with pytest.raises(ValidationError, match="schema version"):
        model.model_validate({"schema_version": True})


def test_receipt_and_evidence_join_real_native_values(tmp_path) -> None:
    receipt, receipt_id, authority_evidence, checkpoint_evidence = _receipt_and_evidence(tmp_path)

    validate_native_projection_publication_evidence_coordinates(
        receipt=receipt,
        receipt_id=receipt_id,
        authority_evidence=authority_evidence,
        checkpoint_evidence=checkpoint_evidence,
    )


def test_receipt_and_evidence_reject_coordinated_substituted_receipt_id(tmp_path) -> None:
    receipt, _, authority_evidence, checkpoint_evidence = _receipt_and_evidence(tmp_path)
    substituted_receipt_id = "receipt:substituted"

    with pytest.raises(ValueError, match="coordinates are substituted"):
        validate_native_projection_publication_evidence_coordinates(
            receipt=receipt,
            receipt_id=substituted_receipt_id,
            authority_evidence=authority_evidence.model_copy(update={"receipt_id": substituted_receipt_id}),
            checkpoint_evidence=checkpoint_evidence.model_copy(update={"receipt_id": substituted_receipt_id}),
        )
