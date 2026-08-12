"""Adversarial closure tests for the sealed local-evidence producer.

These tests intentionally exercise the public ``produce`` entry point.  The
stage accepts only its complete graph-free input carrier, so a lane cannot
silently become an optional fallback.
"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from types import SimpleNamespace

import pytest
from memorii.core.memory_evolution.ingestion_contracts import (
    DeliveryIdentity,
    DeliveryPrincipalBinding,
    OperationFenceBinding,
)
from memorii.core.semantic_ingestion.sealed_source_normalization_evidence_producer import (
    SealedSourceNormalizationEvidenceProducer,
)
from memorii.core.semantic_ingestion.source_normalization_execution import (
    ConsumedSourceNormalizationResourceReservation,
    SourceNormalizationNonCommit,
)
from memorii.core.semantic_ingestion.source_normalization_stage import (
    GraphFreeSourceNormalizationInvocation,
)
from tests.unit.core.semantic_ingestion.clean_room_request_test_support import (
    build_prepared_source_authority,
)


def _digest(value: str) -> str:
    return sha256(value.encode("ascii")).hexdigest()


class _Parser:
    def __init__(self, manifest: object, value: object | None) -> None:
        self.manifest = manifest
        self.value = value
        self.calls = 0

    def analyze(self, _request: object) -> object | None:
        self.calls += 1
        return self.value


class _Predicate:
    def __init__(self, manifest: object, value: object | None) -> None:
        self.manifest = manifest
        self.value = value
        self.calls = 0

    def detect(self, _request: object) -> object | None:
        self.calls += 1
        return self.value


class _Temporal:
    def __init__(self, manifest: object, value: object | None) -> None:
        self.manifest = manifest
        self.value = value
        self.calls = 0

    def resolve(self, _request: object, *, locale: str, timezone: str) -> object | None:
        assert (locale, timezone) == ("en_US", "UTC")
        self.calls += 1
        return self.value


class _UnavailableInterpreter:
    def __init__(self) -> None:
        self.calls = 0

    def produce(self, **_: object) -> None:
        self.calls += 1
        return None


def _fixture() -> tuple[object, object, object, object]:
    """Build the source and reservation with the canonical prepared contract."""
    text = "Alice starts project Atlas."
    source = build_prepared_source_authority(
        source_id="evidence-source", source_digest=_digest(text), source_text=text
    )
    principal = DeliveryPrincipalBinding.create(
        principal_subject_id="principal", tenant_partition_id="tenant", provider_identity="provider"
    )
    fence = OperationFenceBinding.create(
        operation_id="operation", source_id=source.source_id,
        source_digest=source.source_digest,
        delivery_identity=DeliveryIdentity.create(principal, "delivery"),
    )
    invocation = GraphFreeSourceNormalizationInvocation(
        operation_id="operation", source=source, source_authority_evidence=SimpleNamespace(),
        source_interval_evidence=None, policy_bundle=SimpleNamespace(),
        authorization_read_set_provider=object(), operation_fence_binding=fence,
    )
    binding = source.segment_language_routes.routes[0].resource_binding
    assert binding is not None
    authority = SimpleNamespace(derivation=SimpleNamespace(analyzer_resource_bindings=(binding,)))
    manifests = tuple(sorted((
        binding.stanza_analyzer_manifest_digest, binding.spacy_analyzer_manifest_digest,
        binding.predicate_event_manifest_digest, binding.temporal_resolver_manifest_digest,
    )))
    reservation = ConsumedSourceNormalizationResourceReservation(
        source_id=source.source_id, source_digest=source.source_digest,
        preparation_fingerprint=source.preparation_fingerprint, operation_id="operation",
        operation_fence_digest=fence.binding_digest, required_lane_manifest_digests=manifests,
        resource_envelope_digest=_digest("envelope"), reservation_nonce="nonce",
        issued_server_time=datetime(2026, 1, 1, tzinfo=UTC),
        expires_server_time=datetime(2026, 1, 2, tzinfo=UTC), issued_monotonic_tick=1,
        expires_monotonic_tick=2, consumed_server_time=datetime(2026, 1, 1, tzinfo=UTC),
        consumed_monotonic_tick=1, consumption_digest=_digest("consumed"),
    )
    run = SimpleNamespace(status="complete", source_id=source.source_id,
        source_digest=source.source_digest, preparation_fingerprint=source.preparation_fingerprint)
    return invocation, authority, reservation, run


def _producer(*, stanza: object | None = None, spacy: object | None = None,
              predicate: object | None = (), temporal: object | None = None):
    invocation, authority, reservation, run = _fixture()
    binding = invocation.source.segment_language_routes.routes[0].resource_binding
    assert binding is not None
    interpreter = _UnavailableInterpreter()
    producer = SealedSourceNormalizationEvidenceProducer(
        stanza=_Parser(SimpleNamespace(manifest_digest=binding.stanza_analyzer_manifest_digest), stanza),
        spacy=_Parser(SimpleNamespace(manifest_digest=binding.spacy_analyzer_manifest_digest), spacy),
        predicate_detector=_Predicate(SimpleNamespace(manifest_digest=binding.predicate_event_manifest_digest), predicate),
        duckling=_Temporal(SimpleNamespace(manifest_digest=binding.temporal_resolver_manifest_digest), temporal),
        interpretation_producer=interpreter, locale_by_language={"en": "en_US"}, timezone="UTC",
    )
    return producer, invocation, authority, reservation, run, interpreter


def test_missing_parser_lane_is_one_closed_evidence_noncommit() -> None:
    producer, invocation, authority, reservation, run, interpreter = _producer()
    result = producer.produce(
        invocation=invocation, proposal_run=run, authority=authority, resources=reservation
    )
    assert isinstance(result, SourceNormalizationNonCommit)
    assert (result.phase, result.reason) == ("evidence_sealed", "analysis_unavailable")
    assert interpreter.calls == 0


@pytest.mark.parametrize("mutation", ("missing_binding", "swapped_reservation", "unsorted_manifest"))
def test_resource_binding_and_reservation_mutations_fail_closed(mutation: str) -> None:
    producer, invocation, authority, reservation, run, _ = _producer()
    if mutation == "missing_binding":
        authority = SimpleNamespace(derivation=SimpleNamespace(analyzer_resource_bindings=()))
    elif mutation == "swapped_reservation":
        reservation = reservation.model_copy(update={"operation_id": "other"})
    else:
        reservation = reservation.model_copy(
            update={"required_lane_manifest_digests": tuple(reversed(reservation.required_lane_manifest_digests))}
        )
    result = producer.produce(invocation=invocation, proposal_run=run, authority=authority, resources=reservation)
    assert isinstance(result, SourceNormalizationNonCommit)
    assert (result.phase, result.reason) == ("evidence_sealed", "analysis_unavailable")
