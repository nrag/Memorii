"""Durable V3 recovery proof through the ordinary provider composition root."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta

from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.semantic_ingestion.contracts import (
    BootstrapRecoveryClaimedV3,
    BootstrapRecoveryClaimV3,
    BootstrapRecoveryKeyV3,
    BootstrapRecoveryProbeV3,
    BootstrapRecoveryUnavailableV3,
    contract_digest,
)
from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import (
    TEST_NOW,
    DeterministicTestHostBootstrapMaterialVerifier,
    _built_in_local_capability,
    _host_ingress,
    _v3_normalization_host_builder,
)


def _service(*, storage, builder) -> ProviderMemoryService:
    return ProviderMemoryService(
        memory_plane=MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage)),
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=builder,
    )


def _sync(service: ProviderMemoryService):
    return service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="bootstrap-v3-jsonl-lost-ack",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )


class _NoBootstrapDerivationAuthority:
    """Leave a real issued claim pending without invoking a derived lane."""

    def build(self, *, invocation, handoff, recovery_claim):
        del invocation, handoff, recovery_claim
        return None


class _RecordingBootstrapDerivationAuthority:
    """Records the store-issued claim while delegating normal production work."""

    def __init__(self, delegate) -> None:
        self._delegate = delegate
        self.claims: list[BootstrapRecoveryClaimV3] = []

    def bind_publication_lease_lookup(self, lookup) -> None:
        self._delegate.bind_publication_lease_lookup(lookup)

    def build(self, *, invocation, handoff, recovery_claim):
        self.claims.append(recovery_claim)
        return self._delegate.build(
            invocation=invocation, handoff=handoff, recovery_claim=recovery_claim
        )


def _probe_from_service(service: ProviderMemoryService) -> BootstrapRecoveryProbeV3:
    marker = service._memory_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_handoff_marker"
    )[0].content["marker"]
    runtime = service._provider_ingestion._semantic_runtime
    assert runtime is not None and runtime.prepared_source_repository is not None
    prepared = runtime.prepared_source_repository.load(
        source_id=marker["source_id"], source_digest=marker["source_digest"]
    )
    assert prepared is not None
    key_body = {
        "source_id": prepared.source_id,
        "source_digest": prepared.source_digest,
        "preparation_fingerprint": prepared.preparation_fingerprint,
        "operation_id": marker["operation_fence_binding"]["operation_id"],
        "operation_fence_digest": marker["operation_fence_binding"]["binding_digest"],
        "bootstrap_profile_manifest_digest": marker["release_evidence_digest"],
        "handoff_request_digest": marker["handoff_request_digest"],
    }
    key = BootstrapRecoveryKeyV3(
        **key_body,
        recovery_key_digest=contract_digest(
            b"memorii.semantic-ingestion.bootstrap-recovery-key.v3", key_body
        ),
    )
    probe_body = {
        "recovery_key": key,
        "handoff_marker_digest": marker["marker_digest"],
        "expected_predecessor_operation_generation": marker[
            "expected_predecessor_operation_generation"
        ],
        "expected_predecessor_artifact_generation": marker[
            "expected_predecessor_artifact_generation"
        ],
        "expected_predecessor_control_digest": marker[
            "expected_predecessor_control_digest"
        ],
    }
    return BootstrapRecoveryProbeV3(
        **probe_body,
        probe_digest=contract_digest(
            b"memorii.semantic-ingestion.bootstrap-recovery-probe.v3", probe_body
        ),
    )


def _pending_claim_service(tmp_path) -> tuple[ProviderMemoryService, object]:
    builder, calls = _v3_normalization_host_builder()
    service = _service(
        storage=tmp_path / "pending-claim",
        builder=replace(builder, authority_provider=_NoBootstrapDerivationAuthority()),
    )
    result = _sync(service)
    assert result.blocked_reasons["semantic_ingestion"] == "source_alignment_authority_unavailable"
    assert calls == {"proposal": 0, "stanza": 0, "spacy": 0, "predicate": 0, "temporal": 0}
    runtime = service._provider_ingestion._semantic_runtime
    assert runtime is not None and runtime.source_normalization_host_bundle is not None
    return service, runtime.source_normalization_host_bundle.recovery_repository


def _pending_claim(service: ProviderMemoryService) -> BootstrapRecoveryClaimV3:
    content = service._memory_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_v3_recovery_index"
    )[0].content
    return BootstrapRecoveryClaimV3.model_validate_json(
        json.dumps({name: content[name] for name in BootstrapRecoveryClaimV3.model_fields})
    )


def test_jsonl_live_claim_denies_second_probe_and_stale_renewal(tmp_path) -> None:
    """A pending claimant fences a fresh JSONL handle until it expires."""
    first, repository = _pending_claim_service(tmp_path)
    claim = _pending_claim(first)
    probe = _probe_from_service(first)

    denied = repository.probe(probe=probe, server_time=TEST_NOW, monotonic_tick=1)
    assert isinstance(denied, BootstrapRecoveryUnavailableV3)
    assert denied.reason == "foreign_live_claim"

    renewed = repository.renew_or_abort(
        claim=claim, server_time=TEST_NOW, monotonic_tick=2
    )
    assert renewed.kind == "renewed"
    stale = repository.renew_or_abort(
        claim=claim, server_time=TEST_NOW, monotonic_tick=3
    )
    assert stale.kind == "aborted"
    assert stale.reason == "foreign"

    stale_probe_body = probe.model_dump(mode="python", exclude={"probe_digest"})
    stale_probe_body["handoff_marker_digest"] = "0" * 64
    stale_probe = BootstrapRecoveryProbeV3(
        **stale_probe_body,
        probe_digest=contract_digest(
            b"memorii.semantic-ingestion.bootstrap-recovery-probe.v3", stale_probe_body
        ),
    )
    stale_fence = repository.probe(
        probe=stale_probe, server_time=TEST_NOW, monotonic_tick=3
    )
    assert isinstance(stale_fence, BootstrapRecoveryUnavailableV3)
    assert stale_fence.reason == "stale_predecessor"


def test_jsonl_expired_claim_reclaims_ready_control_with_a_new_nonce(tmp_path) -> None:
    """Expiry reclaims the existing ready control; it never replays handoff."""
    service, repository = _pending_claim_service(tmp_path)
    first = _pending_claim(service)
    probe = _probe_from_service(service)

    exact_expiry = repository.probe(
        probe=probe,
        server_time=first.expires_server_time,
        monotonic_tick=first.expires_monotonic_tick,
    )
    assert isinstance(exact_expiry, BootstrapRecoveryClaimedV3)
    second = exact_expiry.claim
    assert second.claim_nonce != first.claim_nonce
    assert second.claim_digest != first.claim_digest
    assert second.renewal_count == 0
    assert second.control_snapshot == first.control_snapshot

    before_expiry = repository.probe(
        probe=probe,
        server_time=second.expires_server_time - timedelta(microseconds=1),
        monotonic_tick=second.expires_monotonic_tick - 1,
    )
    assert isinstance(before_expiry, BootstrapRecoveryUnavailableV3)
    assert before_expiry.reason == "foreign_live_claim"


def test_jsonl_crash_before_publish_cas_keeps_only_the_live_claim(tmp_path) -> None:
    """A stop after probe cannot fabricate a Found recovery outcome."""
    service, repository = _pending_claim_service(tmp_path)
    claim = _pending_claim(service)

    assert repository.reload_found(recovery_key_digest=claim.recovery_key_digest) is None
    state = service._memory_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_v3_recovery_index"
    )[0].content
    assert state["state"] == "claimed"
    assert state["claim_digest"] == claim.claim_digest


def test_jsonl_consumed_claim_cannot_renew_after_found(tmp_path) -> None:
    """The claim consumed by generation-three publication has no replay path."""
    builder, calls = _v3_normalization_host_builder()
    recording_authority = _RecordingBootstrapDerivationAuthority(builder.authority_provider)
    service = _service(
        storage=tmp_path / "consumed-claim",
        builder=replace(builder, authority_provider=recording_authority),
    )

    _sync(service)
    assert calls == {"proposal": 1, "stanza": 1, "spacy": 1, "predicate": 1, "temporal": 1}
    assert len(recording_authority.claims) == 1
    runtime = service._provider_ingestion._semantic_runtime
    assert runtime is not None and runtime.source_normalization_host_bundle is not None
    replay = runtime.source_normalization_host_bundle.recovery_repository.renew_or_abort(
        claim=recording_authority.claims[0], server_time=TEST_NOW, monotonic_tick=2
    )
    assert replay.kind == "aborted"
    assert replay.reason == "consumed"


def test_jsonl_fresh_provider_reopens_v3_found_without_reinvoking_any_lane(tmp_path) -> None:
    """A lost acknowledgement reuses byte-identical V3 and terminal closures."""
    first_builder, first_calls = _v3_normalization_host_builder()
    first = _service(storage=tmp_path / "plane", builder=first_builder)
    first_result = _sync(first)
    assert first_calls == {
        "proposal": 1,
        "stanza": 1,
        "spacy": 1,
        "predicate": 1,
        "temporal": 1,
    }
    recovery_records = first._memory_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_v3_recovery_index"
    )
    assert len(recovery_records) == 1
    found_bytes = encode_typed_value(recovery_records[0].content)
    control = first._memory_plane.list_records(
        source_kind="semantic_ingestion_preplanning_control"
    )[0].content["control"]

    # A new store handle and service instance simulate process loss after the
    # first commit but before its caller receives the acknowledgement.
    second_builder, second_calls = _v3_normalization_host_builder()
    second = _service(storage=tmp_path / "plane", builder=second_builder)
    second_result = _sync(second)

    assert second_calls == {
        "proposal": 0,
        "stanza": 0,
        "spacy": 0,
        "predicate": 0,
        "temporal": 0,
    }
    assert second_result.blocked_reasons == first_result.blocked_reasons
    reopened_recovery = second._memory_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_v3_recovery_index"
    )
    assert len(reopened_recovery) == 1
    assert encode_typed_value(reopened_recovery[0].content) == found_bytes
    first_members = tuple(
        record.model_dump(mode="python")
        for record in first._memory_plane.list_records(
            source_kind="semantic_ingestion_generation_member"
        )
    )
    second_members = tuple(
        record.model_dump(mode="python")
        for record in second._memory_plane.list_records(
            source_kind="semantic_ingestion_generation_member"
        )
    )
    assert second_members == first_members
    assert control["state"] == "terminal"
