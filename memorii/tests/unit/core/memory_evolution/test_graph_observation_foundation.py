import base64
from datetime import UTC, datetime, timedelta

import memorii.core.memory_evolution.graph_observation_cursor as cursor_module
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from memorii.core.memory_evolution.graph_observation_authority import (
    GrantBackedGraphObservationAuthorizer,
    GraphObservationAccessGrant,
)
from memorii.core.memory_evolution.graph_observation_contracts import (
    AuthenticatedGraphObservationContext,
    GraphObservationAuthorizationDecision,
    GraphObservationAuthorizationDecisionPreimage,
    GraphObservationCohortSelector,
    GraphObservationPagePolicySnapshot,
    GraphObservationUnsignedCursorCoordinates,
)
from memorii.core.memory_evolution.graph_observation_cursor import (
    GraphObservationCursorCodec,
    GraphObservationCursorDecodeLimits,
    GraphObservationCursorError,
    GraphObservationCursorSigner,
    GraphObservationCursorVerificationKey,
    GraphObservationCursorVerifier,
)
from memorii.core.memory_evolution.ingestion_contracts import CanonicalTypedValueError, encode_typed_value
from memorii.core.memory_evolution.models import MemoryScope

NOW = datetime(2026, 9, 6, tzinfo=UTC)


def _context() -> AuthenticatedGraphObservationContext:
    return AuthenticatedGraphObservationContext.create(
        principal_subject_id="principal", tenant_partition_id="tenant",
        authorized_scope_set_digest="a" * 64, authentication_session_id="session",
    )


def _policy() -> GraphObservationPagePolicySnapshot:
    return GraphObservationPagePolicySnapshot.create(
        policy_revision="policy-1", minimum_total_page_size=1,
        maximum_total_page_size=4, snapshot_maximum_age=timedelta(minutes=5),
    )


def _selector() -> GraphObservationCohortSelector:
    return GraphObservationCohortSelector(
        seed_source_ids=("source-1",), seed_operation_ids=(),
        include_referenced_boundary_entities=True,
    )


def _coordinates() -> GraphObservationUnsignedCursorCoordinates:
    return GraphObservationUnsignedCursorCoordinates(
        schema_version=1, stream_position=0,
        preceding_record_kind=None, preceding_primary_key=None,
        preceding_record_digest=None, requested_total_page_size=2,
        page_policy_revision="policy-1", page_policy_digest=_policy().policy_digest,
        caller_context_digest=_context().context_digest,
        authorization_decision_digest="b" * 64,
        authorization_expires_at=NOW + timedelta(minutes=1),
        cohort_digest="c" * 64, snapshot_token="snapshot-1",
        graph_revision="graph-1", observation_revision="observation-1",
        view="current", valid_at=None, system_as_of=NOW,
    )


def _cursor_components(*, limits: GraphObservationCursorDecodeLimits | None = None) -> tuple[GraphObservationCursorCodec, bytes]:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )
    return GraphObservationCursorCodec(
        GraphObservationCursorSigner(private_key),
        GraphObservationCursorVerifier(
            GraphObservationCursorVerificationKey(public_key=public_key),
            limits or GraphObservationCursorDecodeLimits(
                maximum_wire_characters=4096, maximum_raw_bytes=2048,
                maximum_ctv_nodes=128, maximum_ctv_depth=16,
            ),
        ),
    ), public_key


def _codec(*, limits: GraphObservationCursorDecodeLimits | None = None) -> GraphObservationCursorCodec:
    return _cursor_components(limits=limits)[0]


def test_cursor_real_ed25519_rejects_tampering_and_noncanonical_wire() -> None:
    codec, public_key = _cursor_components()
    cursor = codec.issue(_coordinates())
    assert codec.decode(cursor).stream_position == 0
    verifier = GraphObservationCursorVerifier(
        GraphObservationCursorVerificationKey(public_key=public_key),
        GraphObservationCursorDecodeLimits(maximum_wire_characters=4096, maximum_raw_bytes=2048, maximum_ctv_nodes=128, maximum_ctv_depth=16),
    )
    assert verifier.decode(cursor).stream_position == 0
    wrong_public_key = Ed25519PrivateKey.generate().public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    wrong_verifier = GraphObservationCursorVerifier(
        GraphObservationCursorVerificationKey(public_key=wrong_public_key),
        GraphObservationCursorDecodeLimits(maximum_wire_characters=4096, maximum_raw_bytes=2048, maximum_ctv_nodes=128, maximum_ctv_depth=16),
    )
    with pytest.raises(GraphObservationCursorError):
        wrong_verifier.decode(cursor)

    wire, encoded = cursor.split(".")
    altered = encoded[:-1] + ("A" if encoded[-1] != "A" else "B")
    with pytest.raises(GraphObservationCursorError):
        codec.decode(f"{wire}.{altered}")
    with pytest.raises(GraphObservationCursorError):
        codec.decode("v1.not-a-ctv")
    payload = codec.decode(cursor)
    changed_payload = payload.model_copy(update={"graph_revision": "graph-2"})
    changed_wire = base64.urlsafe_b64encode(encode_typed_value(changed_payload.model_dump(mode="python"))).rstrip(b"=").decode("ascii")
    with pytest.raises(GraphObservationCursorError):
        verifier.decode(f"v1.{changed_wire}")


def test_cursor_coordinates_classify_policy_revision_expiry_and_request_mismatch() -> None:
    codec = _codec()
    payload = codec.decode(codec.issue(_coordinates()))
    assert GraphObservationCursorCodec.continuation_failure(
        payload=payload, now=NOW, caller_context_digest=_context().context_digest,
        authorization_decision_digest="b" * 64, page_policy_revision="policy-2",
        page_policy_digest=_policy().policy_digest, graph_revision="graph-1",
        observation_revision="observation-1", requested_total_page_size=2,
        view="current", valid_at=None, system_as_of=NOW,
    ) == "stale_cursor"
    assert GraphObservationCursorCodec.continuation_failure(
        payload=payload, now=NOW + timedelta(minutes=2), caller_context_digest=_context().context_digest,
        authorization_decision_digest="b" * 64, page_policy_revision="policy-1",
        page_policy_digest=_policy().policy_digest, graph_revision="graph-1",
        observation_revision="observation-1", requested_total_page_size=2,
        view="current", valid_at=None, system_as_of=NOW,
    ) == "revoked_access"
    assert GraphObservationCursorCodec.continuation_failure(
        payload=payload, now=NOW, caller_context_digest=_context().context_digest,
        authorization_decision_digest="b" * 64, page_policy_revision="policy-1",
        page_policy_digest=_policy().policy_digest, graph_revision="graph-1",
        observation_revision="observation-1", requested_total_page_size=3,
        view="current", valid_at=None, system_as_of=NOW,
    ) == "invalid_cursor"


def test_authorizer_uses_protected_grant_and_current_policy_before_any_read() -> None:
    context = _context()
    grant = GraphObservationAccessGrant(
        principal_subject_id="principal", tenant_partition_id="tenant", context_digest=context.context_digest,
        authorized_scopes=(MemoryScope(user_id="user", session_id="session"),), issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=1),
    )
    calls: list[str] = []

    class Policy:
        def current_policy(self, **_: object) -> GraphObservationPagePolicySnapshot | None:
            calls.append("policy")
            return _policy()

    authorizer = GrantBackedGraphObservationAuthorizer(
        grant_provider=lambda digest: grant if digest == context.context_digest else None,
        policy_provider=Policy(), correlation_token_factory=lambda: "correlation",
    )
    decision = authorizer.authorize(
        context=context, purpose="graph_observation", scope_constraint=MemoryScope(user_id="user", session_id="session"),
        selector=_selector(), server_time=NOW,
    )
    assert decision.kind == "authorized"
    assert calls == ["policy"]

    denied = authorizer.authorize(
        context=context, purpose="graph_observation", scope_constraint=MemoryScope(user_id="other"),
        selector=_selector(), server_time=NOW,
    )
    assert denied.kind == "failure"
    assert denied.reason == "denied"
    assert calls == ["policy"]


def test_closed_contracts_reject_forged_digest_selector_and_cursor_predecessor() -> None:
    with pytest.raises(ValueError, match="context digest"):
        AuthenticatedGraphObservationContext(
            principal_subject_id="principal", tenant_partition_id="tenant", authorized_scope_set_digest="a" * 64,
            authentication_session_id="session", context_digest="b" * 64,
        )
    with pytest.raises(ValueError, match="ordered"):
        GraphObservationCohortSelector(
            seed_source_ids=("z", "a"), seed_operation_ids=(), include_referenced_boundary_entities=True,
        )
    body = _coordinates().model_copy(update={"stream_position": 1})
    with pytest.raises(ValueError, match="predecessor"):
        _codec().issue(body)


def test_cursor_rejects_over_cap_and_raw_malformed_before_typed_decode() -> None:
    codec = _codec(limits=GraphObservationCursorDecodeLimits(
        maximum_wire_characters=64, maximum_raw_bytes=24, maximum_ctv_nodes=4, maximum_ctv_depth=2,
    ))
    with pytest.raises(GraphObservationCursorError):
        codec.decode("v1." + "a" * 65)
    with pytest.raises(GraphObservationCursorError):
        codec.decode("v1." + "e30")


def test_cursor_accepts_exact_limits_and_rejects_one_less_and_ctv_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    codec, public_key = _cursor_components()
    cursor = codec.issue(_coordinates())
    raw = base64.urlsafe_b64decode(cursor.split(".")[1] + "==")
    exact = GraphObservationCursorDecodeLimits(
        maximum_wire_characters=len(cursor), maximum_raw_bytes=len(raw), maximum_ctv_nodes=128, maximum_ctv_depth=16,
    )
    assert GraphObservationCursorVerifier(GraphObservationCursorVerificationKey(public_key=public_key), exact).decode(cursor).snapshot_token == "snapshot-1"
    with pytest.raises(GraphObservationCursorError):
        GraphObservationCursorVerifier(GraphObservationCursorVerificationKey(public_key=public_key), exact.model_copy(update={"maximum_wire_characters": len(cursor) - 1})).decode(cursor)
    with pytest.raises(GraphObservationCursorError):
        GraphObservationCursorVerifier(GraphObservationCursorVerificationKey(public_key=public_key), exact.model_copy(update={"maximum_raw_bytes": len(raw) - 1})).decode(cursor)
    with pytest.raises(GraphObservationCursorError):
        GraphObservationCursorVerifier(GraphObservationCursorVerificationKey(public_key=public_key), exact.model_copy(update={"maximum_ctv_nodes": 1})).decode(cursor)
    assert GraphObservationCursorVerifier(GraphObservationCursorVerificationKey(public_key=public_key), exact.model_copy(update={"maximum_ctv_depth": 1})).decode(cursor).snapshot_token == "snapshot-1"
    nested_raw = encode_typed_value((("nested",),))
    nested_cursor = "v1." + base64.urlsafe_b64encode(nested_raw).rstrip(b"=").decode("ascii")
    saw_depth_limit = False
    original_decode = cursor_module.decode_typed_value

    def instrumented_decode(raw: bytes, *, max_nodes: int | None = None, max_depth: int | None = None) -> object:
        nonlocal saw_depth_limit
        try:
            return original_decode(raw, max_nodes=max_nodes, max_depth=max_depth)
        except CanonicalTypedValueError as exc:
            if str(exc) == "canonical_typed_value_depth_limit":
                saw_depth_limit = True
            raise

    monkeypatch.setattr(cursor_module, "decode_typed_value", instrumented_decode)
    with pytest.raises(GraphObservationCursorError):
        GraphObservationCursorVerifier(GraphObservationCursorVerificationKey(public_key=public_key), exact.model_copy(update={"maximum_ctv_depth": 1})).decode(nested_cursor)
    assert saw_depth_limit


def test_decision_preimage_binds_context_purpose_scope_and_selector() -> None:
    context = _context()
    policy = _policy()
    preimage = GraphObservationAuthorizationDecisionPreimage(
        context=context, purpose="graph_observation", scope_constraint=MemoryScope(user_id="user"),
        selector=_selector(), authorized_scope=MemoryScope(user_id="user"), policy=policy,
        expires_at=NOW + timedelta(minutes=1),
    )
    decision = GraphObservationAuthorizationDecision.create(preimage=preimage)
    decision.validate_for_request(preimage)
    with pytest.raises(ValueError, match="does not bind"):
        decision.validate_for_request(preimage.model_copy(update={"purpose": "ingestion_time_attestation"}))
    with pytest.raises(ValueError, match="does not bind"):
        decision.validate_for_request(preimage.model_copy(update={"selector": GraphObservationCohortSelector(seed_source_ids=("source-2",), seed_operation_ids=(), include_referenced_boundary_entities=True)}))
    with pytest.raises(ValueError, match="does not bind"):
        decision.validate_for_request(preimage.model_copy(update={"context": AuthenticatedGraphObservationContext.create(principal_subject_id="other", tenant_partition_id="tenant", authorized_scope_set_digest="a" * 64, authentication_session_id="session")}))
    with pytest.raises(ValueError, match="does not bind"):
        decision.validate_for_request(preimage.model_copy(update={"scope_constraint": MemoryScope(user_id="user", session_id="session")}))
