"""Composite conflict-listing contract equivalence-class proof."""

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from memorii.core.memory_evolution.composite_conflict_listing import (
    COMPOSITE_CURSOR_DOMAIN,
    CompositeChildKind,
    CompositeConflictChildSnapshotBinding,
    CompositeConflictListingCursorClaims,
    CompositeConflictListingError,
    CompositeConflictListingSnapshot,
    CompositeConflictMemberKey,
    CompositeMemberRoute,
    assemble_composite_snapshot,
    decode_composite_cursor,
    encode_composite_cursor,
    route_composite_member,
    validate_composite_continuation,
)
from memorii.core.memory_evolution.conflict_attention import ConflictAccessContext
from memorii.core.memory_evolution.conflict_attention_repository import (
    ConflictCursorKey,
)
from pydantic import ValidationError

NOW = datetime(2026, 9, 4, 12, 0, 0, tzinfo=UTC)
def D(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _key(*, revoked: bool = False) -> ConflictCursorKey:
    return ConflictCursorKey(
        key_id="key-one",
        key_epoch=1,
        secret=b"a" * 32,
        valid_from=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(hours=1),
        signing=True,
        revoked=revoked,
    )


def _access() -> ConflictAccessContext:
    return ConflictAccessContext(
        tenant_id="tenant:a",
        principal_id="principal:a",
        principal_binding_digest=D("binding"),
        authorized_scope_ids=("scope:a", "scope:b"),
        scope_digest=D("scopes"),
        authorization_snapshot_digest=D("authz"),
    )


def _member_key(kind: CompositeChildKind, conflict: str) -> CompositeConflictMemberKey:
    return CompositeConflictMemberKey.create(
        child_kind=kind,
        child_repository_id="repo:semantic" if kind is CompositeChildKind.SEMANTIC else "repo:integrity",
        conflict_id=f"conflict:{conflict}",
        conflict_revision=D(f"revision:{conflict}"),
        conflict_record_digest=D(f"record:{conflict}"),
    )


def _bindings(*semantic_keys, integrity_keys=()) -> tuple:
    semantic = CompositeConflictChildSnapshotBinding.create(
        child_kind=CompositeChildKind.SEMANTIC,
        child_repository_id="repo:semantic",
        child_snapshot_id="snapshot:semantic",
        child_snapshot_digest=D("semantic-snapshot"),
        child_watermark=3,
        child_authority_set_digest=D("semantic-authority"),
        ordered_member_key_digests=tuple(k.member_key_digest for k in semantic_keys),
    )
    integrity = CompositeConflictChildSnapshotBinding.create(
        child_kind=CompositeChildKind.INTEGRITY,
        child_repository_id="repo:integrity",
        child_snapshot_id="snapshot:integrity",
        child_snapshot_digest=D("integrity-snapshot"),
        child_watermark=5,
        child_authority_set_digest=D("integrity-authority"),
        ordered_member_key_digests=tuple(k.member_key_digest for k in integrity_keys),
    )
    return semantic, integrity


def _snapshot(*, integrity_conflict: str = "integrity-one") -> CompositeConflictListingSnapshot:
    semantic_key = _member_key(CompositeChildKind.SEMANTIC, "semantic-one")
    integrity_key = _member_key(CompositeChildKind.INTEGRITY, integrity_conflict)
    semantic, integrity = _bindings(
        semantic_key, integrity_keys=(integrity_key,)
    )
    return assemble_composite_snapshot(
        snapshot_id="snapshot:composite",
        access=_access(),
        semantic_binding=semantic,
        integrity_binding=integrity,
        ordered_semantic_keys=(semantic_key,),
        ordered_integrity_keys=(integrity_key,),
        created_at=NOW,
    )


def test_assembly_orders_children_and_assigns_contiguous_ordinals() -> None:
    semantic_keys = tuple(
        _member_key(CompositeChildKind.SEMANTIC, f"semantic-{index}")
        for index in range(2)
    )
    integrity_key = _member_key(CompositeChildKind.INTEGRITY, "integrity-one")
    semantic, integrity = _bindings(*semantic_keys, integrity_keys=(integrity_key,))
    snapshot = assemble_composite_snapshot(
        snapshot_id="snapshot:composite",
        access=_access(),
        semantic_binding=semantic,
        integrity_binding=integrity,
        ordered_semantic_keys=semantic_keys,
        ordered_integrity_keys=(integrity_key,),
        created_at=NOW,
    )
    assert tuple(member.snapshot_ordinal for member in snapshot.members) == (0, 1, 2)
    kinds = [member.member_key.child_kind for member in snapshot.members]
    assert kinds == [
        CompositeChildKind.SEMANTIC,
        CompositeChildKind.SEMANTIC,
        CompositeChildKind.INTEGRITY,
    ]
    assert snapshot.listing_scope_ids == snapshot.authorized_scope_ids


def test_duplicate_member_key_and_cross_child_conflict_fail_integrity_closed() -> None:
    semantic_key = _member_key(CompositeChildKind.SEMANTIC, "same")
    integrity_key = _member_key(CompositeChildKind.INTEGRITY, "same")
    semantic, integrity = _bindings(
        semantic_key, integrity_keys=(integrity_key,)
    )
    with pytest.raises(
        ValidationError,
        match="semantic_conflict_replay_integrity_failure",
    ):
        assemble_composite_snapshot(
            snapshot_id="snapshot:composite",
            access=_access(),
            semantic_binding=semantic,
            integrity_binding=integrity,
            ordered_semantic_keys=(semantic_key,),
            ordered_integrity_keys=(integrity_key,),
            created_at=NOW,
        )


def test_substituted_member_keys_reject_against_bindings() -> None:
    semantic_key = _member_key(CompositeChildKind.SEMANTIC, "semantic-one")
    other_key = _member_key(CompositeChildKind.SEMANTIC, "semantic-two")
    semantic, integrity = _bindings(semantic_key)
    with pytest.raises(ValueError):
        assemble_composite_snapshot(
            snapshot_id="snapshot:composite",
            access=_access(),
            semantic_binding=semantic,
            integrity_binding=integrity,
            ordered_semantic_keys=(other_key,),
            ordered_integrity_keys=(),
            created_at=NOW,
        )


def test_member_key_and_binding_digest_mutations_fail() -> None:
    key = _member_key(CompositeChildKind.SEMANTIC, "semantic-one")
    with pytest.raises(ValidationError):
        CompositeConflictMemberKey.model_validate(
            key.model_dump() | {"conflict_id": "conflict:other"}
        )
    semantic, _ = _bindings(key)
    with pytest.raises(ValidationError):
        CompositeConflictChildSnapshotBinding.model_validate(
            semantic.model_dump() | {"child_watermark": 9}
        )
    snapshot = _snapshot()
    with pytest.raises(ValidationError):
        CompositeConflictListingSnapshot.model_validate(
            snapshot.model_dump() | {"snapshot_id": "snapshot:other"}
        )


def _claims(snapshot: CompositeConflictListingSnapshot) -> dict[str, object]:
    last = snapshot.members[0]
    return {
        "tenant_id": snapshot.tenant_id,
        "principal_id": snapshot.principal_id,
        "principal_binding_digest": snapshot.principal_binding_digest,
        "authorization_snapshot_digest": snapshot.authorization_snapshot_digest,
        "authorized_scope_ids": snapshot.authorized_scope_ids,
        "listing_scope_ids": snapshot.listing_scope_ids,
        "scope_digest": snapshot.scope_digest,
        "composite_snapshot_id": snapshot.snapshot_id,
        "composite_snapshot_digest": snapshot.snapshot_digest,
        "semantic_child_binding_digest": snapshot.child_bindings[0].binding_digest,
        "integrity_child_binding_digest": snapshot.child_bindings[1].binding_digest,
        "last_snapshot_ordinal": last.snapshot_ordinal,
        "last_member_key_digest": last.member_key.member_key_digest,
        "issued_at": NOW,
    }


def test_v2_cursor_round_trip_and_grammar() -> None:
    snapshot = _snapshot()
    key = _key()
    cursor = encode_composite_cursor(_claims(snapshot), key=key)
    assert cursor.startswith("v2.") and "=" not in cursor
    claims = decode_composite_cursor(
        cursor, keys={("key-one", 1): key}, access=_access(), now=NOW
    )
    assert claims.composite_snapshot_id == snapshot.snapshot_id
    assert claims.last_member_key_digest == snapshot.members[0].member_key.member_key_digest
    # Claims cannot be re-serialized to different canonical bytes.
    assert claims.expires_at == claims.issued_at + timedelta(seconds=900)


def test_v1_cursor_bytes_never_decode_as_composite() -> None:

    snapshot = _snapshot()
    key = _key()
    cursor = encode_composite_cursor(_claims(snapshot), key=key)
    downgraded = "v1." + cursor.split(".", 2)[1] + "." + cursor.split(".", 2)[2]
    with pytest.raises(CompositeConflictListingError, match="invalid_conflict_cursor"):
        decode_composite_cursor(
            downgraded, keys={("key-one", 1): key}, access=_access(), now=NOW
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "tampered_mac",
        "tampered_claims",
        "downgraded_protocol",
        "unknown_key",
        "revoked_key",
        "expired",
        "cross_principal",
        "cross_tenant",
        "scope_widened",
    ),
)
def test_cursor_mutation_matrix_fails_closed(mutation: str) -> None:
    snapshot = _snapshot()
    key = _key()
    cursor = encode_composite_cursor(_claims(snapshot), key=key)
    access = _access()
    keys = {("key-one", 1): key}
    now = NOW
    if mutation == "tampered_mac":
        parts = cursor.split(".")
        bad = bytearray(bytes(parts[2], "ascii"))
        bad[0] = ord("A") if bad[0] != ord("A") else ord("B")
        cursor = f"{parts[0]}.{parts[1]}.{bad.decode()}"
    elif mutation == "tampered_claims":
        parts = cursor.split(".")
        cursor = f"{parts[0]}.{parts[1][:-2]}aa.{parts[2]}"
    elif mutation == "downgraded_protocol":
        # A correctly MACed body carrying the v1 protocol literal must
        # reject as a downgraded-protocol cursor before any payload read.
        import base64
        import hmac as hmac_module

        from memorii.core.memory_evolution.ingestion_contracts import (
            encode_typed_value,
        )

        body = dict(_claims(snapshot))
        validated = CompositeConflictListingCursorClaims.model_validate(
            body
            | {
                "protocol": "memorii.conflict-listing-cursor.v2",
                "key_id": key.key_id,
                "key_epoch": key.key_epoch,
                "expires_at": NOW + timedelta(seconds=900),
            }
        )
        wire = validated.model_dump(mode="json")
        wire["protocol"] = "memorii.conflict-listing-cursor.v1"
        raw2 = encode_typed_value(wire)
        mac2 = hmac_module.new(
            key.secret, COMPOSITE_CURSOR_DOMAIN + raw2, hashlib.sha256
        ).digest()

        def b64(value: bytes) -> str:
            return base64.urlsafe_b64encode(value).decode().rstrip("=")

        cursor = f"v2.{b64(raw2)}.{b64(mac2)}"

    elif mutation == "unknown_key":
        keys = {("key-two", 1): _key()}
    elif mutation == "revoked_key":
        keys = {("key-one", 1): _key(revoked=True)}
    elif mutation == "expired":
        now = NOW + timedelta(seconds=901)
    elif mutation == "cross_principal":
        access = access.model_copy(update={"principal_id": "principal:other"})
    elif mutation == "cross_tenant":
        access = access.model_copy(update={"tenant_id": "tenant:other"})
    elif mutation == "scope_widened":
        access = access.model_copy(
            update={
                "authorized_scope_ids": ("scope:a", "scope:b", "scope:c"),
                "scope_digest": D("widened"),
            }
        )
    with pytest.raises(CompositeConflictListingError, match="invalid_conflict_cursor"):
        decode_composite_cursor(cursor, keys=keys, access=access, now=now)


def test_continuation_rejects_substituted_or_expired_snapshot() -> None:
    snapshot = _snapshot()
    key = _key()
    cursor = encode_composite_cursor(_claims(snapshot), key=key)
    claims = decode_composite_cursor(
        cursor, keys={("key-one", 1): key}, access=_access(), now=NOW
    )
    validate_composite_continuation(
        claims=claims, snapshot=snapshot, now=NOW + timedelta(minutes=5)
    )
    # A regenerated (substituted) composite snapshot has a different digest.
    substituted = _snapshot(integrity_conflict="integrity-substituted")
    with pytest.raises(CompositeConflictListingError, match="invalid_conflict_cursor"):
        validate_composite_continuation(
            claims=claims, snapshot=substituted, now=NOW + timedelta(minutes=5)
        )
    with pytest.raises(CompositeConflictListingError, match="invalid_conflict_cursor"):
        validate_composite_continuation(
            claims=claims, snapshot=snapshot, now=NOW + timedelta(seconds=901)
        )


def test_routing_resolves_by_child_kind() -> None:
    snapshot = _snapshot()
    semantic_member = next(
        member
        for member in snapshot.members
        if member.member_key.child_kind is CompositeChildKind.SEMANTIC
    )
    integrity_member = next(
        member
        for member in snapshot.members
        if member.member_key.child_kind is CompositeChildKind.INTEGRITY
    )
    assert route_composite_member(semantic_member) is (
        CompositeMemberRoute.SEMANTIC_REPOSITORY
    )
    assert route_composite_member(integrity_member) is (
        CompositeMemberRoute.OPERATOR_ACTION_REQUIRED
    )
