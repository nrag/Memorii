from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from memorii.core.memory_evolution.graph_ingestion_time_contracts import (
    SourceRetentionTimeAttestation,
    TransactionGroupCommitTimeAttestation,
)
from memorii.core.memory_evolution.graph_observation_contracts import GraphObservationCohortSelector
from memorii.core.memory_evolution.graph_observation_public_contracts import (
    GraphObservationAuthorizationDecision,
    GraphObservationPage,
    GraphObservationPagePolicySnapshot,
    GraphObservationRequestCoordinates,
    GraphRecordObservationSnapshot,
    IngestionTimeAttestationPage,
    IngestionTimeAttestationRequestCoordinates,
    IngestionTimeObservationSnapshot,
)
from memorii.core.memory_evolution.graph_observation_snapshot_contracts import (
    GraphObservationCohortPreimage,
    ResolvedGraphObservationCohort,
)
from memorii.core.memory_evolution.models import MemoryScope
from pydantic import ValidationError


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _cohorts() -> tuple[GraphObservationCohortPreimage, ResolvedGraphObservationCohort]:
    body = {
        "seed_source_ids": ("source",), "seed_operation_ids": (), "source_ids": ("source",),
        "operation_ids": (), "operation_fence_ids": (), "include_referenced_boundary_entities": True,
        "authorized_scope_identity": "scope", "authorization_policy_revision": "policy",
        "authorization_decision_digest": _digest("decision"),
        "graph_revision_delta_ids": (), "graph_revision_delta_digests": (),
        "ingestion_observation_delta_ids": (), "ingestion_observation_delta_digests": (),
        "reference_schema_manifest_fingerprint": _digest("reference-schema"),
        "reference_ledger_high_watermark": "watermark", "reference_ledger_digest": _digest("ledger"),
        "reference_audit_certificate_digest": _digest("audit"), "complete": True,
        "graph_revision": "graph", "observation_revision": "observation",
        "memory_plane_write_revision": 2,
        "temporal_projection_generation_digest": None, "temporal_projection_pointer_digest": None,
        "trust_projection_generation_digest": None, "trust_projection_pointer_digest": None,
        "observation_schema_fingerprint": _digest("observation-schema"),
        "changed_record_keys": (), "boundary_record_keys": (),
    }
    return (
        GraphObservationCohortPreimage.model_validate(body),
        ResolvedGraphObservationCohort.model_validate({**body, "cohort_digest": _digest("cohort")}),
    )


def _decision() -> GraphObservationAuthorizationDecision:
    return GraphObservationAuthorizationDecision(
        kind="authorized", authorized_scope_identity="scope", policy_revision="policy",
        page_policy_revision="page-policy", page_policy_digest=_digest("page-policy"),
        expires_at=datetime(2026, 9, 7, tzinfo=UTC), decision_digest=_digest("decision"),
    )


def test_joined_graph_snapshot_and_page_validate_profile_three_coordinates() -> None:
    preimage, cohort = _cohorts()
    request = GraphObservationRequestCoordinates(
        scope_constraint=MemoryScope(user_id="user"),
        cohort_selector=GraphObservationCohortSelector(
            seed_source_ids=("source",), seed_operation_ids=(),
            include_referenced_boundary_entities=True,
        ),
        view="current", expected_graph_revision="graph", expected_observation_revision="observation",
        valid_at=None, system_as_of=datetime(2026, 9, 7, tzinfo=UTC), total_page_size=1,
    )
    snapshot = GraphRecordObservationSnapshot(
        schema_version=1, snapshot_token="snapshot", created_at=datetime(2026, 9, 7, tzinfo=UTC),
        memory_plane_write_revision=2, authenticated_context_digest=_digest("context"),
        purpose="graph_observation", authorization_decision=_decision(), request=request,
        cohort_preimage=preimage, resolved_cohort=cohort, stream=(),
    )
    page = GraphObservationPage(
        kind="page", graph_revision="graph", observation_revision="observation",
        snapshot_token=snapshot.snapshot_token, memory_plane_write_revision=2, cohort=cohort,
        page_policy_revision="page-policy", page_policy_digest=_digest("page-policy"), view="current",
        valid_at=None, system_as_of=datetime(2026, 9, 7, tzinfo=UTC), total_page_size=1,
        stream_start_position=0, stream_end_position=0, records=(),
        observation_schema_fingerprint=cohort.observation_schema_fingerprint,
        next_cursor=None, page_digest=_digest("page"),
    )

    assert snapshot.resolved_cohort == page.cohort
    with pytest.raises(ValidationError, match="write revision"):
        GraphRecordObservationSnapshot.model_validate({
            **snapshot.model_dump(mode="python"), "memory_plane_write_revision": 3,
        })
    with pytest.raises(ValidationError, match="snapshot coordinates"):
        GraphRecordObservationSnapshot.model_validate({
            **snapshot.model_dump(mode="python"),
            "request": {
                **snapshot.request.model_dump(mode="python"),
                "cohort_selector": {
                    "seed_source_ids": (), "seed_operation_ids": ("operation",),
                    "include_referenced_boundary_entities": True,
                },
            },
        })
    with pytest.raises(ValidationError, match="positions"):
        GraphObservationPage.model_validate({
            **page.model_dump(mode="python"), "stream_end_position": 1,
        })
    with pytest.raises(ValidationError, match="cohort coordinates"):
        GraphObservationPage.model_validate({
            **page.model_dump(mode="python"), "next_cursor": "cursor",
        })


def test_ingestion_time_page_and_profile_three_policy_reject_invalid_coordinates() -> None:
    _, cohort = _cohorts()
    attestation = SourceRetentionTimeAttestation(
        kind="source_retention", attestation_id="attestation", source_id="source",
        operation_fence_id="fence", retained_at=datetime(2026, 9, 7, tzinfo=UTC),
        graph_revision="graph", clock_identity="clock", source_record_digest=_digest("record"),
        attestation_digest=_digest("attestation"),
    )
    group_attestation = TransactionGroupCommitTimeAttestation(
        kind="transaction_group_commit", attestation_id="group-attestation", source_id="source",
        operation_fence_id="fence", transaction_group_id="group", operation_ids=("operation",),
        transaction_started_at=datetime(2026, 9, 7, tzinfo=UTC),
        transaction_committed_at=datetime(2026, 9, 7, tzinfo=UTC), graph_revision_before="before",
        graph_revision_after="graph", applied_graph_delta_digest=_digest("delta"), clock_identity="clock",
        committed_batch_digest=_digest("batch"), attestation_digest=_digest("group-attestation"),
    )
    page = IngestionTimeAttestationPage(
        kind="page", graph_revision="graph", observation_revision="observation", snapshot_token="snapshot",
        memory_plane_write_revision=2, cohort=cohort, page_policy_revision="page-policy",
        page_policy_digest=_digest("page-policy"), total_page_size=1, stream_start_position=0,
        stream_end_position=1, attestations=(attestation,), next_cursor=None, page_digest=_digest("page"),
    )

    assert page.attestations == (attestation,)
    request = IngestionTimeAttestationRequestCoordinates(
        scope_constraint=MemoryScope(user_id="user"),
        cohort_selector=GraphObservationCohortSelector(
            seed_source_ids=("source",), seed_operation_ids=(),
            include_referenced_boundary_entities=True,
        ),
        expected_graph_revision="graph", expected_observation_revision="observation",
        total_page_size=1,
    )
    preimage, _ = _cohorts()
    snapshot = IngestionTimeObservationSnapshot(
        schema_version=1, snapshot_token="snapshot", created_at=datetime(2026, 9, 7, tzinfo=UTC),
        memory_plane_write_revision=2, authenticated_context_digest=_digest("context"),
        purpose="ingestion_time_attestation", authorization_decision=_decision(), request=request,
        cohort_preimage=preimage, resolved_cohort=cohort, stream=(attestation,),
    )

    assert snapshot.stream == (attestation,)
    raw_witnesses = (
        {
            "kind": "source_retention", "witness_id": "source-witness", "attestation_digest": _digest("attestation"),
            "source_id": "source", "operation_fence_id": "fence", "retained_at": datetime(2026, 9, 7, tzinfo=UTC),
            "graph_revision": "graph", "clock_identity": "clock", "issued_at": datetime(2026, 9, 7, tzinfo=UTC),
            "signing_key_id": "key", "signing_authority_snapshot_digest": _digest("authority"),
            "trust_policy_digest": _digest("trust"), "witness_digest": _digest("source-witness"), "signature": "a" * 128,
        },
        {
            "kind": "transaction_group_commit", "witness_id": "group-witness", "attestation_digest": _digest("group-attestation"),
            "source_id": "source", "operation_fence_id": "fence", "transaction_group_id": "group", "operation_ids": ("operation",),
            "transaction_started_at": datetime(2026, 9, 7, tzinfo=UTC), "transaction_committed_at": datetime(2026, 9, 7, tzinfo=UTC),
            "graph_revision_before": "before", "graph_revision_after": "graph", "applied_graph_delta_digest": _digest("delta"),
            "clock_identity": "clock", "committed_batch_digest": _digest("batch"), "issued_at": datetime(2026, 9, 7, tzinfo=UTC),
            "signing_key_id": "key", "signing_authority_snapshot_digest": _digest("authority"),
            "trust_policy_digest": _digest("trust"), "witness_digest": _digest("group-witness"), "signature": "a" * 128,
        },
    )
    for candidate, raw_witness in zip((attestation, group_attestation), raw_witnesses, strict=True):
        candidate_snapshot = IngestionTimeObservationSnapshot.model_validate({
            **snapshot.model_dump(mode="python"), "stream": (candidate.model_dump(mode="python"),),
        })
        candidate_page = IngestionTimeAttestationPage.model_validate({
            **page.model_dump(mode="python"), "stream_end_position": 1,
            "attestations": (candidate.model_dump(mode="python"),),
        })

        assert candidate_snapshot.model_dump(mode="python")["stream"] == (candidate.model_dump(mode="python"),)
        assert candidate_page.model_dump(mode="python")["attestations"] == (candidate.model_dump(mode="python"),)
        with pytest.raises(ValidationError):
            IngestionTimeObservationSnapshot.model_validate({
                **snapshot.model_dump(mode="python"), "stream": (raw_witness,),
            })
        with pytest.raises(ValidationError):
            IngestionTimeAttestationPage.model_validate({
                **page.model_dump(mode="python"), "stream_end_position": 1, "attestations": (raw_witness,),
            })
        for extra_name, extra_value in (
            ("witness_id", "unexpected-witness"),
            ("signing_key_id", "unexpected-key"),
            ("trust_policy_digest", _digest("unexpected-trust")),
            ("fixture_coordinate", "acceptance-fixture"),
        ):
            extra_attestation = {**candidate.model_dump(mode="python"), extra_name: extra_value}
            with pytest.raises(ValidationError):
                IngestionTimeObservationSnapshot.model_validate({
                    **snapshot.model_dump(mode="python"), "stream": (extra_attestation,),
                })
            with pytest.raises(ValidationError):
                IngestionTimeAttestationPage.model_validate({
                    **page.model_dump(mode="python"), "stream_end_position": 1, "attestations": (extra_attestation,),
                })
    with pytest.raises(ValidationError, match="snapshot stream"):
        IngestionTimeObservationSnapshot.model_validate({
            **snapshot.model_dump(mode="python"), "stream": (attestation, attestation),
        })
    with pytest.raises(ValidationError, match="integer literal"):
        GraphObservationPagePolicySnapshot.model_validate({
            "policy_revision": "policy", "minimum_total_page_size": 1,
            "maximum_total_page_size": 1, "cursor_schema_version": True,
            "snapshot_maximum_age": timedelta(minutes=1), "policy_digest": _digest("policy"),
        })
    with pytest.raises(ValidationError, match="cohort coordinates"):
        IngestionTimeAttestationPage.model_validate({
            **page.model_dump(mode="python"), "graph_revision": "other",
        })
