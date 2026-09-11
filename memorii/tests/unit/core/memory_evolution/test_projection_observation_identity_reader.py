"""Reader-side ProjectionObservationIdentity re-derivation for observed projections.

The promoted projection-identity design requires protected registered readers
to derive the expected ``observation_id`` of an observed temporal/trust
projection record through the ``ProjectionObservationIdentity`` root of the
same selected publication and to reject a substituted identity before use,
while publications without the identity root keep reading historical records
through their original routes.
"""

from __future__ import annotations

import base64
import json
import re
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from memorii.core.memory_evolution.graph_observation_contracts import GraphObservationCohortSelector
from memorii.core.memory_evolution.graph_observation_paging import (
    AuthenticatedGraphObservationPagingRuntime,
    GraphObservationCohortInput,
    ObservationRetentionBudget,
    VerifiedGraphObservationAuthorization,
)
from memorii.core.memory_evolution.graph_observation_public_contracts import (
    AuthenticatedGraphObservationContext,
    GraphObservationAuthorizationDecision,
    GraphObservationPage,
    GraphObservationPagePolicySnapshot,
    GraphObservationRequest,
)
from memorii.core.memory_evolution.graph_observation_records import (
    ObservedTemporalClaimProjection,
    ObservedTrustClaimProjection,
)
from memorii.core.memory_evolution.graph_observation_snapshot_contracts import GraphObservationRecordKey
from memorii.core.memory_evolution.graph_observation_streams import TemporalClaimProjectionStreamRecord
from memorii.core.memory_evolution.ingestion_contracts import (
    CanonicalTypedValueProfileBinding,
    artifact_preimage,
)
from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.memory_evolution.observation_activation_runtime import (
    ObservationActivationRuntimeError,
    derive_projection_observation_identity,
    emit_registered_observation_artifact,
    projection_observation_identity_root_selected,
    validate_registered_artifact,
    verify_projection_observation_identity,
)
from memorii.core.memory_evolution.semantic_state import (
    ActiveTemporalProjectionPointer,
    ActiveTrustProjectionPointer,
    TemporalProjectionRecord,
    TrustProjectionRecord,
    projection_contract_digest,
)
from memorii.core.memory_evolution.typed_value_artifact_integrity import TrustedTypedValueArtifactVerificationKey
from memorii.core.memory_plane.service import MemoryPlaneService
from tests.fixtures.semantic_ingestion.observation_publication import observation_publication
from tests.unit.core.memory_evolution.test_graph_observation_public_contracts import _cohorts

_HEX64 = re.compile(r"^[0-9a-f]{64}$")

_IDENTITY_PUBLICATION_ROOTS = (
    "AuthenticatedGraphObservationContext", "GraphObservationAuthorizationDecision",
    "GraphObservationPagePolicySnapshot", "GraphObservationCohortPreimage",
    "ResolvedGraphObservationCohort", "GraphRecordObservationSnapshot",
    "GraphObservationPage", "GraphObservationCursorPayload",
    "ObservedTemporalClaimProjection", "ObservedTrustClaimProjection",
    "ProjectionObservationIdentity",
)
_HISTORICAL_PUBLICATION_ROOTS = tuple(
    root for root in _IDENTITY_PUBLICATION_ROOTS if root != "ProjectionObservationIdentity"
)


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _temporal_pointer(
    repository_id: str = "repository", generation: str = "generation",
) -> ActiveTemporalProjectionPointer:
    body = {
        "repository_id": repository_id, "policy_fingerprint": _digest("temporal-policy"),
        "generation_digest": _digest(generation), "publication_kind": "projection_commit",
        "publication_certificate_digest": _digest("certificate"), "writer_epoch": 1,
        "pointer_revision": 1, "published_at": datetime(2026, 9, 7, tzinfo=UTC),
        "publication_sequence": 1, "predecessor_pointer_digest": None,
    }
    return ActiveTemporalProjectionPointer.model_validate({
        **body, "pointer_digest": projection_contract_digest("temporal_pointer", body),
    })


def _temporal_projection(repository_id: str = "repository", source: str = "source") -> TemporalProjectionRecord:
    return TemporalProjectionRecord.create(
        projection_id="projection", repository_id=repository_id,
        source_record_kind="claim_assertion", source_record_id="claim",
        source_record_version=1, source_record_digest=_digest(source),
        temporal_policy_fingerprint=_digest("temporal-policy"), valid_interval=None,
        outcome="unknown", evidence=(),
    )


def _trust_projection_and_pointer(
    repository_id: str = "trust-repository", generation: str = "trust-generation",
) -> tuple[TrustProjectionRecord, ActiveTrustProjectionPointer]:
    projection = TrustProjectionRecord.create(
        projection_id="trust-projection", repository_id=repository_id,
        source_record_kind="claim_assertion", source_record_id="claim",
        source_record_version=1, source_record_digest=_digest("trust-source"),
        trust_policy_fingerprint=_digest("trust-policy"),
        arbitration_as_of=datetime(2026, 9, 7, tzinfo=UTC),
        outcome="unknown", evidence=(),
    )
    body = {
        "repository_id": repository_id, "policy_fingerprint": _digest("trust-policy"),
        "generation_digest": _digest(generation), "publication_kind": "projection_commit",
        "publication_certificate_digest": _digest("trust-certificate"), "writer_epoch": 1,
        "pointer_revision": 1, "published_at": datetime(2026, 9, 7, tzinfo=UTC),
        "publication_sequence": 1, "predecessor_pointer_digest": None,
    }
    pointer = ActiveTrustProjectionPointer.model_validate({
        **body, "pointer_digest": projection_contract_digest("trust_pointer", body),
    })
    return projection, pointer


def _temporal_observation(
    observation_id: str, *, repository_id: str = "repository", generation: str = "generation",
    source: str = "source",
) -> ObservedTemporalClaimProjection:
    pointer = _temporal_pointer(repository_id, generation)
    return ObservedTemporalClaimProjection(
        observation_id=observation_id, projection=_temporal_projection(repository_id, source),
        generation_digest=pointer.generation_digest, publication_pointer=pointer,
        successor_publication_pointer=None, boundary=False,
        record_digest="0" * 64,
    )


def _derived_temporal_identity(
    history, publication, limits, *, repository_id: str = "repository",
    generation: str = "generation", source: str = "source",
) -> tuple[str, ObservedTemporalClaimProjection]:
    pointer = _temporal_pointer(repository_id, generation)
    projection = _temporal_projection(repository_id, source)
    identity = derive_projection_observation_identity(
        "temporal", projection.repository_id, pointer.generation_digest,
        projection.projection_digest, history=history, publication=publication, limits=limits,
    )
    return identity, _temporal_observation(
        identity, repository_id=repository_id, generation=generation, source=source,
    )


def test_derived_identity_round_trips_and_binds_every_preimage_field(tmp_path, monkeypatch):
    history, limits = observation_publication(tmp_path, monkeypatch, ("ProjectionObservationIdentity",))
    publication = history.publications[0]
    assert projection_observation_identity_root_selected(history, publication)

    derived = derive_projection_observation_identity(
        "temporal", "repository", _digest("generation"), _digest("projection"),
        history=history, publication=publication, limits=limits,
    )
    assert _HEX64.fullmatch(derived)
    assert derive_projection_observation_identity(
        "temporal", "repository", _digest("generation"), _digest("projection"),
        history=history, publication=publication, limits=limits,
    ) == derived
    # Changing kind, repository, generation or native projection changes the identity.
    assert derive_projection_observation_identity(
        "trust", "repository", _digest("generation"), _digest("projection"),
        history=history, publication=publication, limits=limits,
    ) != derived
    assert derive_projection_observation_identity(
        "temporal", "other-repository", _digest("generation"), _digest("projection"),
        history=history, publication=publication, limits=limits,
    ) != derived
    assert derive_projection_observation_identity(
        "temporal", "repository", _digest("other-generation"), _digest("projection"),
        history=history, publication=publication, limits=limits,
    ) != derived
    assert derive_projection_observation_identity(
        "temporal", "repository", _digest("generation"), _digest("other-projection"),
        history=history, publication=publication, limits=limits,
    ) != derived
    # Nonconforming preimage fields deny before any digest.
    with pytest.raises(ObservationActivationRuntimeError, match="preimage is invalid"):
        derive_projection_observation_identity(
            "spatial", "repository", _digest("generation"), _digest("projection"),  # type: ignore[arg-type]
            history=history, publication=publication, limits=limits,
        )
    with pytest.raises(ObservationActivationRuntimeError, match="preimage is invalid"):
        derive_projection_observation_identity(
            "temporal", "", _digest("generation"), _digest("projection"),
            history=history, publication=publication, limits=limits,
        )
    with pytest.raises(ObservationActivationRuntimeError, match="preimage is invalid"):
        derive_projection_observation_identity(
            "temporal", "repository", "not-a-digest", _digest("projection"),
            history=history, publication=publication, limits=limits,
        )


def test_reader_accepts_derived_identity_and_rejects_substitutions(tmp_path, monkeypatch):
    history, limits = observation_publication(
        tmp_path, monkeypatch,
        ("ProjectionObservationIdentity", "ObservedTemporalClaimProjection", "ObservedTrustClaimProjection"),
    )
    publication = history.publications[0]
    identity, record = _derived_temporal_identity(history, publication, limits)
    record = emit_registered_observation_artifact(
        record, schema_id="ObservedTemporalClaimProjection", history=history,
        publication=publication, limits=limits,
    ).value
    assert record.observation_id == identity

    # A substituted random identity is rejected by both wired acceptance points.
    forged = record.model_copy(update={"observation_id": "f" * 64})
    with pytest.raises(ObservationActivationRuntimeError, match="identity is substituted"):
        verify_projection_observation_identity(
            forged, history=history, publication=publication, limits=limits,
        )
    with pytest.raises(ObservationActivationRuntimeError, match="identity is substituted"):
        emit_registered_observation_artifact(
            forged, schema_id="ObservedTemporalClaimProjection", history=history,
            publication=publication, limits=limits,
        )

    # Swapped kind: a trust record carrying the temporal identity of the same
    # coordinates is rejected, and vice versa.
    trust_projection, trust_pointer = _trust_projection_and_pointer()
    temporal_identity_of_trust = derive_projection_observation_identity(
        "temporal", trust_projection.repository_id, trust_pointer.generation_digest,
        trust_projection.projection_digest, history=history, publication=publication, limits=limits,
    )
    swapped = ObservedTrustClaimProjection(
        observation_id=temporal_identity_of_trust, projection=trust_projection,
        generation_digest=trust_pointer.generation_digest, publication_pointer=trust_pointer,
        successor_publication_pointer=None, boundary=False, record_digest="0" * 64,
    )
    with pytest.raises(ObservationActivationRuntimeError, match="identity is substituted"):
        verify_projection_observation_identity(
            swapped, history=history, publication=publication, limits=limits,
        )

    # Wrong repository, generation or native projection digest rejects: each
    # record keeps the default identity while its own field differs.
    with pytest.raises(ObservationActivationRuntimeError, match="identity is substituted"):
        verify_projection_observation_identity(
            _temporal_observation(identity, repository_id="other-repository"),
            history=history, publication=publication, limits=limits,
        )
    with pytest.raises(ObservationActivationRuntimeError, match="identity is substituted"):
        verify_projection_observation_identity(
            _temporal_observation(identity, generation="other-generation"),
            history=history, publication=publication, limits=limits,
        )
    with pytest.raises(ObservationActivationRuntimeError, match="identity is substituted"):
        verify_projection_observation_identity(
            _temporal_observation(identity, source="other-source"),
            history=history, publication=publication, limits=limits,
        )
    with pytest.raises(ObservationActivationRuntimeError, match="record model is invalid"):
        verify_projection_observation_identity(  # type: ignore[arg-type]
            "not-a-record", history=history, publication=publication, limits=limits,
        )


def test_historical_publications_without_identity_root_keep_original_routes(tmp_path, monkeypatch):
    history, limits = observation_publication(tmp_path, monkeypatch, ("ObservedTemporalClaimProjection",))
    publication = history.publications[0]
    assert not projection_observation_identity_root_selected(history, publication)

    legacy = _temporal_observation("legacy-observation")
    emitted = emit_registered_observation_artifact(
        legacy, schema_id="ObservedTemporalClaimProjection", history=history,
        publication=publication, limits=limits,
    )
    assert emitted.value.observation_id == "legacy-observation"
    # The strict registered reader check itself still denies on an absent root.
    with pytest.raises(ObservationActivationRuntimeError, match="identity root is not selected"):
        verify_projection_observation_identity(
            legacy, history=history, publication=publication, limits=limits,
        )


def _tamper_body_field(raw: bytes, field: str, replacement: object) -> bytes:
    """Rewrite one body field while keeping every outer digest consistent."""
    envelope = json.loads(raw.decode("utf-8"))
    outer = dict(envelope["entries"])
    body_bytes = base64.b64decode(outer["canonical_value_bytes"]["value"])
    tree = json.loads(body_bytes.decode("utf-8"))
    tree["entries"] = [
        [key, replacement if key == field else value] for key, value in tree["entries"]
    ]
    tampered = json.dumps(tree, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    binding_entries = dict(outer["binding"]["entries"])
    binding = CanonicalTypedValueProfileBinding(
        binding_entries["profile_id"],
        int(binding_entries["profile_version"]["value"]),
        binding_entries["profile_digest"],
        binding_entries["schema_id"],
        int(binding_entries["schema_version"]["value"]),
        binding_entries["binding_digest"],
    )
    return json.dumps({
        "$type": "map",
        "entries": [
            ("artifact_digest", sha256(artifact_preimage(binding, tampered)).hexdigest()),
            ("binding", outer["binding"]),
            ("canonical_value_bytes", {"$type": "bytes", "value": base64.b64encode(tampered).decode("ascii")}),
            ("canonical_value_digest", sha256(tampered).hexdigest()),
        ],
    }, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def test_record_digest_binds_entire_observed_payload(tmp_path, monkeypatch):
    history, limits = observation_publication(
        tmp_path, monkeypatch, ("ProjectionObservationIdentity", "ObservedTemporalClaimProjection"),
    )
    publication = history.publications[0]
    identity, record = _derived_temporal_identity(history, publication, limits)
    artifact = emit_registered_observation_artifact(
        record, schema_id="ObservedTemporalClaimProjection", history=history,
        publication=publication, limits=limits,
    )
    assert artifact.value.observation_id == identity
    assert validate_registered_artifact(
        artifact.raw, schema_id="ObservedTemporalClaimProjection", history=history, limits=limits,
    ) == artifact.value
    # Tampering any observed field (here: boundary) with every outer digest
    # recomputed still fails because record_digest binds the whole payload.
    tampered = _tamper_body_field(artifact.raw, "boundary", True)
    with pytest.raises(ValueError, match="self_digest_mismatch"):
        validate_registered_artifact(
            tampered, schema_id="ObservedTemporalClaimProjection", history=history, limits=limits,
        )


def _paging_runtime(history, limits, *, stream_factory):
    publication = history.publications[0]
    now = datetime(2026, 9, 8, tzinfo=UTC)

    def emit(value):
        return emit_registered_observation_artifact(
            value, schema_id=type(value).__name__, history=history,
            publication=publication, limits=limits,
        ).value

    context = emit(AuthenticatedGraphObservationContext(
        principal_subject_id="principal", tenant_partition_id="tenant",
        authorized_scope_set_digest="a" * 64, authentication_session_id="session",
        context_digest="0" * 64,
    ))
    policy = emit(GraphObservationPagePolicySnapshot(
        policy_revision="page-policy", minimum_total_page_size=1, maximum_total_page_size=10,
        cursor_schema_version=1, snapshot_maximum_age=timedelta(minutes=5), policy_digest="0" * 64,
    ))
    decision = emit(GraphObservationAuthorizationDecision(
        kind="authorized", authorized_scope_identity="scope", policy_revision="policy",
        page_policy_revision=policy.policy_revision, page_policy_digest=policy.policy_digest,
        expires_at=now + timedelta(minutes=10), decision_digest="0" * 64,
    ))

    class Authority:
        def now(self):
            return now

        def resolve(self, **kwargs):
            return context

        def authorize(self, **kwargs):
            return VerifiedGraphObservationAuthorization(
                decision=decision, page_policy=policy, authorized_scope=MemoryScope(user_id="user"),
            )

        def graph_observation_input(self, *, snapshot, **kwargs):
            stream = stream_factory()
            preimage = _cohorts()[0].model_copy(update={
                "memory_plane_write_revision": snapshot.memory_plane_write_revision,
                "authorization_decision_digest": decision.decision_digest,
                "changed_record_keys": tuple(GraphObservationRecordKey(
                    record_kind=item.record_kind, primary_key=item.primary_key,
                ) for item in stream),
            })
            return GraphObservationCohortInput(preimage, stream)

    key = Ed25519PrivateKey.generate()
    runtime = AuthenticatedGraphObservationPagingRuntime(
        memory_plane=MemoryPlaneService(), context_resolver=Authority(),
        authorizer=Authority(), cohort_provider=Authority(), protected_clock=Authority(),
        registry_history=history, registry_publication=publication,
        cursor_signing_key=key,
        cursor_verification_key=TrustedTypedValueArtifactVerificationKey(key.public_key().public_bytes_raw()),
        reader_limits=limits, correlation_token_factory=lambda: "correlation",
        retention_budget=ObservationRetentionBudget(
            maximum_stream_records=10, maximum_snapshot_bytes=200_000,
            maximum_retained_snapshots=10, maximum_retained_bytes=1_000_000,
            maximum_tenant_snapshots=10, maximum_tenant_bytes=1_000_000,
        ),
    )
    request = GraphObservationRequest(
        scope_constraint=MemoryScope(user_id="user"),
        cohort_selector=GraphObservationCohortSelector(
            seed_source_ids=("source",), seed_operation_ids=(),
            include_referenced_boundary_entities=True,
        ), view="current", expected_graph_revision="graph", expected_observation_revision="observation",
        valid_at=None, system_as_of=now, total_page_size=1, cursor=None,
    )
    return runtime, request


def _projection_stream_record(payload: ObservedTemporalClaimProjection) -> TemporalClaimProjectionStreamRecord:
    return TemporalClaimProjectionStreamRecord(
        record_kind="temporal_claim_projection", primary_key=payload.observation_id,
        record_digest=payload.record_digest, payload=payload,
    )


def test_paging_reader_accepts_derived_identity_and_denies_substituted_identity(tmp_path, monkeypatch):
    history, limits = observation_publication(tmp_path, monkeypatch, _IDENTITY_PUBLICATION_ROOTS)
    identity, record = _derived_temporal_identity(history, history.publications[0], limits)
    accepted = emit_registered_observation_artifact(
        record, schema_id="ObservedTemporalClaimProjection", history=history,
        publication=history.publications[0], limits=limits,
    ).value
    assert accepted.observation_id == identity
    runtime, request = _paging_runtime(history, limits, stream_factory=lambda: (_projection_stream_record(accepted),))
    page = runtime.observe_graph(host_ingress="trusted", request=request)
    assert isinstance(page, GraphObservationPage)
    assert [item.primary_key for item in page.records] == [identity]

    # An internally consistent record authored with a hand-set identity under a
    # historical publication is denied by the reader whose selected publication
    # contains the identity root.
    historical_history, historical_limits = observation_publication(
        tmp_path / "historical", monkeypatch, ("ObservedTemporalClaimProjection",),
    )
    substituted = emit_registered_observation_artifact(
        _temporal_observation("f" * 64), schema_id="ObservedTemporalClaimProjection",
        history=historical_history, publication=historical_history.publications[0],
        limits=historical_limits,
    ).value
    assert substituted.observation_id == "f" * 64
    forged_runtime, forged_request = _paging_runtime(
        history, limits, stream_factory=lambda: (_projection_stream_record(substituted),),
    )
    denial = forged_runtime.observe_graph(host_ingress="trusted", request=forged_request)
    assert not isinstance(denial, GraphObservationPage) and denial.reason == "denied"


def test_paging_reader_without_identity_root_keeps_historical_records(tmp_path, monkeypatch):
    history, limits = observation_publication(tmp_path, monkeypatch, _HISTORICAL_PUBLICATION_ROOTS)
    assert not projection_observation_identity_root_selected(history, history.publications[0])
    legacy = emit_registered_observation_artifact(
        _temporal_observation("legacy-observation"), schema_id="ObservedTemporalClaimProjection",
        history=history, publication=history.publications[0], limits=limits,
    ).value
    runtime, request = _paging_runtime(history, limits, stream_factory=lambda: (_projection_stream_record(legacy),))
    page = runtime.observe_graph(host_ingress="trusted", request=request)
    assert isinstance(page, GraphObservationPage)
    assert [item.payload.observation_id for item in page.records] == ["legacy-observation"]
