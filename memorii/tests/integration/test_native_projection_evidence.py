"""Registered native publication members preserve the checkpoint/event join."""

from datetime import timedelta

import pytest
from memorii.core.memory_evolution.observation_activation_runtime import validate_registered_artifact
from memorii.core.memory_evolution.projection_history import PreparedProjectionPublication, ProjectionPublication
from memorii.core.semantic_ingestion.bootstrap_graph_projection_publication import (
    prepare_native_projection_evidence,
    validate_native_projection_publication_evidence_coordinates,
)
from memorii.core.semantic_ingestion.event_replay import (
    SemanticEventSchemaRegistry,
    SemanticReplayState,
    build_semantic_memory_event_batch,
)
from tests.fixtures.semantic_ingestion.observation_publication import observation_publication
from tests.unit.core.semantic_ingestion.test_bootstrap_graph_projection_publication import _receipt_and_evidence


def test_native_projection_registered_members_and_stale_checkpoint(tmp_path, monkeypatch):
    roots = (
        "BootstrapGraphNativeProjectionPublicationReceiptV3",
        "BootstrapGraphNativeReplayAuthorityEvidenceV3",
        "BootstrapGraphNativeReplayCheckpointEvidenceV3",
    )
    history, limits = observation_publication(tmp_path / "registry", monkeypatch, roots)
    original, receipt_id, authority, checkpoint = _receipt_and_evidence(tmp_path, match_projection_revision=True)
    projection = PreparedProjectionPublication(
        publication=ProjectionPublication(
            temporal=original.temporal_publication, trust=original.trust_publication,
            replay_bindings=original.projection_history_replay_bindings,
        ), records=(), preconditions=(),
    )
    arguments = dict(
        source_operation_id=original.source_operation_id,
        transaction_group_id=original.transaction_group_id,
        request_ctv_digest=original.request_ctv_digest,
        graph_revision_before=original.graph_revision_before,
        graph_revision_after=original.graph_revision_after,
        canonical_graph_delta=original.canonical_graph_delta,
        canonical_event_batch=original.canonical_event_batch,
        prepared_projection=projection, aggregate=authority.aggregate,
        checkpoint=checkpoint.checkpoint_bundle, history=history,
        publication=history.publications[0], limits=limits,
    )
    receipt, records = prepare_native_projection_evidence(**arguments)
    assert records[0].memory_id == receipt_id
    decoded = tuple(validate_registered_artifact(
        record.content["artifact"].encode("utf-8"), schema_id=schema,
        history=history, limits=limits,
    ) for record, schema in zip(records, roots, strict=True))
    assert decoded[0] == receipt
    assert decoded[1].aggregate == authority.aggregate
    assert decoded[2].checkpoint_bundle == checkpoint.checkpoint_bundle
    validate_native_projection_publication_evidence_coordinates(
        receipt=receipt, receipt_id=receipt_id,
        authority_evidence=decoded[1], checkpoint_evidence=decoded[2],
    )
    batch = original.canonical_event_batch
    changed_batch = build_semantic_memory_event_batch(
        graph_delta=original.canonical_graph_delta,
        prior_state=SemanticReplayState.genesis(batch.repository_id),
        repository_id=batch.repository_id, source_id=batch.source_id,
        transaction_group_id=batch.transaction_group_id,
        operation_fence_id=batch.operation_fence_id, writer_epoch=batch.writer_epoch,
        graph_revision_before=original.graph_revision_before,
        graph_revision_after=original.graph_revision_after,
        timestamp=batch.events[0].timestamp + timedelta(seconds=1),
        registry=SemanticEventSchemaRegistry.create(),
    )
    with pytest.raises(ValueError, match="closure is substituted"):
        prepare_native_projection_evidence(**{**arguments, "canonical_event_batch": changed_batch})
