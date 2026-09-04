"""Typed composite conflict-listing contracts governed by conflict attention.

The provider composite repository freezes one authorized retained snapshot in
each child (semantic, integrity) and publishes a single composite listing
whose cursor uses the v2 grammar.  This module owns the closed typed
contracts, the v2 cursor codec, snapshot assembly, continuation validation,
and member routing.  It performs no repository I/O: the child snapshot APIs
and provider wiring compose these pure owners.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from secrets import token_hex
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from memorii.core.memory_evolution.conflict_attention_repository import (
        ConflictCursorKey,
        FileConflictAttentionRepository,
    )

from memorii.core.memory_evolution.conflict_attention import (
    _DIGEST,
    ConflictAccessContext,
    ConflictAttentionPage,
    ConflictListRequest,
    _identifier,
    _utc,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    decode_typed_value,
    encode_typed_value,
)

_COMPOSITE_MEMBER_KEY_DOMAIN = b"memorii.composite-conflict-member-key.v1\0"
_COMPOSITE_CHILD_BINDING_DOMAIN = b"memorii.composite-conflict-child-binding.v1\0"
_COMPOSITE_LISTING_MEMBER_DOMAIN = (
    b"memorii.composite-conflict-listing-member.v1\0"
)
_COMPOSITE_SNAPSHOT_DOMAIN = b"memorii.composite-conflict-listing-snapshot.v1\0"
COMPOSITE_CURSOR_DOMAIN = b"memorii.composite-conflict-listing-cursor.v2\0"
COMPOSITE_CURSOR_LIFETIME = timedelta(seconds=900)
COMPOSITE_CURSOR_PROTOCOL = "memorii.conflict-listing-cursor.v2"


class CompositeConflictListingError(ValueError):
    """Typed non-disclosing composite listing failure."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class CompositeChildKind(StrEnum):
    SEMANTIC = "semantic"
    INTEGRITY = "integrity"


class CompositeMemberRoute(StrEnum):
    SEMANTIC_REPOSITORY = "semantic_repository"
    OPERATOR_ACTION_REQUIRED = "operator_action_required"


def _digest(domain: bytes, value: object) -> str:
    return sha256(domain + encode_typed_value(_canonical(value))).hexdigest()


def _canonical(value: object) -> object:
    if isinstance(value, BaseModel):
        return _canonical(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return tuple(_canonical(item) for item in value) if isinstance(value, tuple) else [
            _canonical(item) for item in value
        ]
    return value


def _canonical_identifiers(values: tuple[str, ...], *, label: str) -> tuple[str, ...]:
    if not values or values != tuple(sorted(set(values), key=lambda item: item.encode("utf-8"))):
        raise ValueError(f"{label} must be canonical")
    for value in values:
        _identifier(value)
    return values


class CompositeConflictMemberKey(BaseModel):
    child_kind: CompositeChildKind
    child_repository_id: str
    conflict_id: str
    conflict_revision: str
    conflict_record_digest: str
    member_key_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_member_key(self) -> CompositeConflictMemberKey:
        _identifier(self.child_repository_id)
        _identifier(self.conflict_id)
        for value in (self.conflict_revision, self.conflict_record_digest, self.member_key_digest):
            if _DIGEST.fullmatch(value) is None:
                raise ValueError("composite member key digests are invalid")
        body = self.model_dump(mode="python", exclude={"member_key_digest"})
        if self.member_key_digest != _digest(_COMPOSITE_MEMBER_KEY_DOMAIN, body):
            raise ValueError("composite member key digest mismatch")
        return self

    @classmethod
    def create(
        cls,
        *,
        child_kind: CompositeChildKind,
        child_repository_id: str,
        conflict_id: str,
        conflict_revision: str,
        conflict_record_digest: str,
    ) -> CompositeConflictMemberKey:
        body = {
            "child_kind": child_kind,
            "child_repository_id": child_repository_id,
            "conflict_id": conflict_id,
            "conflict_revision": conflict_revision,
            "conflict_record_digest": conflict_record_digest,
        }
        return cls.model_validate(
            body
            | {
                "member_key_digest": _digest(_COMPOSITE_MEMBER_KEY_DOMAIN, body),
            }
        )


class CompositeConflictChildSnapshotBinding(BaseModel):
    child_kind: CompositeChildKind
    child_repository_id: str
    child_snapshot_id: str
    child_snapshot_digest: str
    child_watermark: int = Field(ge=0)
    child_authority_set_digest: str
    ordered_member_key_digests: tuple[str, ...]
    binding_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_binding(self) -> CompositeConflictChildSnapshotBinding:
        _identifier(self.child_repository_id)
        _identifier(self.child_snapshot_id)
        for value in (
            self.child_snapshot_digest,
            self.child_authority_set_digest,
            self.binding_digest,
            *self.ordered_member_key_digests,
        ):
            if _DIGEST.fullmatch(value) is None:
                raise ValueError("composite child binding digests are invalid")
        body = self.model_dump(mode="python", exclude={"binding_digest"})
        if self.binding_digest != _digest(_COMPOSITE_CHILD_BINDING_DOMAIN, body):
            raise ValueError("composite child binding digest mismatch")
        return self

    @classmethod
    def create(
        cls,
        *,
        child_kind: CompositeChildKind,
        child_repository_id: str,
        child_snapshot_id: str,
        child_snapshot_digest: str,
        child_watermark: int,
        child_authority_set_digest: str,
        ordered_member_key_digests: tuple[str, ...],
    ) -> CompositeConflictChildSnapshotBinding:
        body = {
            "child_kind": child_kind,
            "child_repository_id": child_repository_id,
            "child_snapshot_id": child_snapshot_id,
            "child_snapshot_digest": child_snapshot_digest,
            "child_watermark": child_watermark,
            "child_authority_set_digest": child_authority_set_digest,
            "ordered_member_key_digests": ordered_member_key_digests,
        }
        return cls.model_validate(
            body | {"binding_digest": _digest(_COMPOSITE_CHILD_BINDING_DOMAIN, body)}
        )


class CompositeConflictListingMember(BaseModel):
    snapshot_ordinal: int = Field(ge=0)
    member_key: CompositeConflictMemberKey
    member_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_member(self) -> CompositeConflictListingMember:
        if _DIGEST.fullmatch(self.member_digest) is None:
            raise ValueError("composite listing member digest is invalid")
        body = self.model_dump(mode="python", exclude={"member_digest"})
        if self.member_digest != _digest(_COMPOSITE_LISTING_MEMBER_DOMAIN, body):
            raise ValueError("composite listing member digest mismatch")
        return self


class CompositeConflictListingSnapshot(BaseModel):
    snapshot_id: str
    tenant_id: str
    principal_id: str
    principal_binding_digest: str
    authorization_snapshot_digest: str
    authorized_scope_ids: tuple[str, ...]
    listing_scope_ids: tuple[str, ...]
    scope_digest: str
    child_bindings: tuple[CompositeConflictChildSnapshotBinding, ...]
    members: tuple[CompositeConflictListingMember, ...]
    created_at: datetime
    expires_at: datetime
    snapshot_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_snapshot(self) -> CompositeConflictListingSnapshot:
        for value in (self.snapshot_id, self.tenant_id, self.principal_id):
            _identifier(value)
        for value in (
            self.principal_binding_digest,
            self.authorization_snapshot_digest,
            self.scope_digest,
            self.snapshot_digest,
        ):
            if _DIGEST.fullmatch(value) is None:
                raise ValueError("composite snapshot digest is invalid")
        for label, scopes in (
            ("authorized", self.authorized_scope_ids),
            ("listing", self.listing_scope_ids),
        ):
            _canonical_identifiers(scopes, label=f"{label} scope ids")
        if not set(self.listing_scope_ids) <= set(self.authorized_scope_ids):
            raise ValueError("composite listing scopes exceed authorization")
        if len(self.child_bindings) != 2 or (
            self.child_bindings[0].child_kind,
            self.child_bindings[1].child_kind,
        ) != (CompositeChildKind.SEMANTIC, CompositeChildKind.INTEGRITY):
            raise ValueError("composite child bindings must be (semantic, integrity)")
        ordinals = tuple(member.snapshot_ordinal for member in self.members)
        if ordinals != tuple(range(len(self.members))):
            raise ValueError("composite snapshot ordinals must be contiguous from zero")
        keys = [member.member_key for member in self.members]
        if len({key.member_key_digest for key in keys}) != len(keys):
            raise CompositeConflictListingError(
                "semantic_conflict_replay_integrity_failure"
            )
        bare_ids = [key.conflict_id for key in keys]
        if len(set(bare_ids)) != len(bare_ids):
            raise CompositeConflictListingError(
                "semantic_conflict_replay_integrity_failure"
            )
        expected_order = (
            self.child_bindings[0].ordered_member_key_digests
            + self.child_bindings[1].ordered_member_key_digests
        )
        if tuple(key.member_key_digest for key in keys) != expected_order:
            raise ValueError("composite member order must follow child bindings")
        _utc(self.created_at, label="created_at")
        _utc(self.expires_at, label="expires_at")
        if self.expires_at <= self.created_at:
            raise ValueError("composite snapshot expiry must follow creation")
        body = self.model_dump(mode="python", exclude={"snapshot_digest"})
        if self.snapshot_digest != _digest(_COMPOSITE_SNAPSHOT_DOMAIN, body):
            raise ValueError("composite snapshot digest mismatch")
        return self


class CompositeConflictListingCursorClaims(BaseModel):
    protocol: Literal["memorii.conflict-listing-cursor.v2"] = (
        COMPOSITE_CURSOR_PROTOCOL
    )
    tenant_id: str
    principal_id: str
    principal_binding_digest: str
    authorization_snapshot_digest: str
    authorized_scope_ids: tuple[str, ...]
    listing_scope_ids: tuple[str, ...]
    scope_digest: str
    composite_snapshot_id: str
    composite_snapshot_digest: str
    semantic_child_binding_digest: str
    integrity_child_binding_digest: str
    last_snapshot_ordinal: int = Field(ge=0)
    last_member_key_digest: str
    key_id: str
    key_epoch: int = Field(ge=1)
    issued_at: datetime
    expires_at: datetime

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_claims(self) -> CompositeConflictListingCursorClaims:
        for value in (self.tenant_id, self.principal_id, self.composite_snapshot_id, self.key_id):
            _identifier(value)
        for value in (
            self.principal_binding_digest,
            self.authorization_snapshot_digest,
            self.scope_digest,
            self.composite_snapshot_digest,
            self.semantic_child_binding_digest,
            self.integrity_child_binding_digest,
            self.last_member_key_digest,
        ):
            if _DIGEST.fullmatch(value) is None:
                raise ValueError("composite cursor digest is invalid")
        for label, scopes in (
            ("authorized", self.authorized_scope_ids),
            ("listing", self.listing_scope_ids),
        ):
            _canonical_identifiers(scopes, label=f"{label} scope ids")
        if not set(self.listing_scope_ids) <= set(self.authorized_scope_ids):
            raise ValueError("composite cursor listing scopes exceed authorization")
        _utc(self.issued_at, label="issued_at")
        _utc(self.expires_at, label="expires_at")
        if self.expires_at != self.issued_at + COMPOSITE_CURSOR_LIFETIME:
            raise ValueError("composite cursor expiry must be exactly 900 seconds")
        return self


def composite_snapshot_digest(
    snapshot: CompositeConflictListingSnapshot,
) -> str:
    """Recompute the composite snapshot's own domain-separated digest."""

    body = snapshot.model_dump(mode="python", exclude={"snapshot_digest"})
    return _digest(_COMPOSITE_SNAPSHOT_DOMAIN, body)


def assemble_composite_snapshot(
    *,
    snapshot_id: str,
    access: ConflictAccessContext,
    semantic_binding: CompositeConflictChildSnapshotBinding,
    integrity_binding: CompositeConflictChildSnapshotBinding,
    ordered_semantic_keys: tuple[CompositeConflictMemberKey, ...],
    ordered_integrity_keys: tuple[CompositeConflictMemberKey, ...],
    created_at: datetime,
) -> CompositeConflictListingSnapshot:
    """Freeze both child bindings and every member key in one snapshot.

    Member order concatenates the semantic child's retained order followed by
    the integrity child's retained order with contiguous ordinals from zero.
    Duplicate member keys or the same bare conflict ID in both children fail
    as ``semantic_conflict_replay_integrity_failure``.
    """
    if semantic_binding.child_kind is not CompositeChildKind.SEMANTIC:
        raise ValueError("semantic binding must be the semantic child")
    if integrity_binding.child_kind is not CompositeChildKind.INTEGRITY:
        raise ValueError("integrity binding must be the integrity child")
    if tuple(key.member_key_digest for key in ordered_semantic_keys) != (
        semantic_binding.ordered_member_key_digests
    ):
        raise ValueError("semantic member keys must match the semantic binding")
    if tuple(key.member_key_digest for key in ordered_integrity_keys) != (
        integrity_binding.ordered_member_key_digests
    ):
        raise ValueError("integrity member keys must match the integrity binding")
    for key in (*ordered_semantic_keys, *ordered_integrity_keys):
        if key.child_kind not in (CompositeChildKind.SEMANTIC, CompositeChildKind.INTEGRITY):
            raise ValueError("member key child kind is unknown")
    members = []
    for ordinal, key in enumerate((*ordered_semantic_keys, *ordered_integrity_keys)):
        body = {"snapshot_ordinal": ordinal, "member_key": key.model_dump(mode="python")}
        members.append(
            CompositeConflictListingMember.model_validate(
                body
                | {"member_digest": _digest(_COMPOSITE_LISTING_MEMBER_DOMAIN, body)}
            )
        )
    body = {
        "snapshot_id": snapshot_id,
        "tenant_id": access.tenant_id,
        "principal_id": access.principal_id,
        "principal_binding_digest": access.principal_binding_digest,
        "authorization_snapshot_digest": access.authorization_snapshot_digest,
        "authorized_scope_ids": access.authorized_scope_ids,
        "listing_scope_ids": access.authorized_scope_ids,
        "scope_digest": access.scope_digest,
        "child_bindings": (
            semantic_binding.model_dump(mode="python"),
            integrity_binding.model_dump(mode="python"),
        ),
        "members": tuple(member.model_dump(mode="python") for member in members),
        "created_at": created_at,
        "expires_at": created_at + COMPOSITE_CURSOR_LIFETIME,
    }
    return CompositeConflictListingSnapshot.model_validate(
        body | {"snapshot_digest": _digest(_COMPOSITE_SNAPSHOT_DOMAIN, body)}
    )


def _key_may_sign(key: ConflictCursorKey, now: datetime) -> bool:
    return (
        not key.revoked
        and key.valid_from <= now
        and key.expires_at >= now + COMPOSITE_CURSOR_LIFETIME
    )


def _key_may_verify(
    key: ConflictCursorKey, *, issued_at: datetime, now: datetime
) -> bool:
    return (
        not key.revoked
        and key.valid_from <= issued_at
        and key.expires_at > now
    )


def encode_composite_cursor(
    claims_body: dict[str, object],
    *,
    key: ConflictCursorKey,
) -> str:
    """Encode one v2 composite cursor under the active signing key."""

    issued_at = claims_body.get("issued_at")
    if issued_at is None:
        issued_at = datetime.now(UTC)
    assert isinstance(issued_at, datetime)
    if not _key_may_sign(key, issued_at):
        raise CompositeConflictListingError("conflict_cursor_key_unavailable")
    claims = CompositeConflictListingCursorClaims.model_validate(
        claims_body
        | {
            "protocol": COMPOSITE_CURSOR_PROTOCOL,
            "key_id": key.key_id,
            "key_epoch": key.key_epoch,
            "issued_at": issued_at,
            "expires_at": issued_at + COMPOSITE_CURSOR_LIFETIME,
        }
    )
    raw = encode_typed_value(claims.model_dump(mode="json"))
    mac = hmac.new(key.secret, COMPOSITE_CURSOR_DOMAIN + raw, hashlib.sha256).digest()
    return f"v2.{_b64(raw)}.{_b64(mac)}"


def decode_composite_cursor(
    cursor: str,
    *,
    keys: dict[tuple[str, int], ConflictCursorKey],
    access: ConflictAccessContext,
    now: datetime,
) -> CompositeConflictListingCursorClaims:
    """Verify one v2 composite cursor before any conflict payload read."""

    try:
        version, encoded, signature = cursor.split(".")
        if version != "v2" or "=" in cursor:
            raise ValueError
        raw = _unb64(encoded)
        supplied = _unb64(signature)
        if _b64(raw) != encoded or _b64(supplied) != signature or len(supplied) != 32:
            raise ValueError
        value = decode_typed_value(raw)
        if encode_typed_value(value) != raw:
            raise ValueError
        claims = CompositeConflictListingCursorClaims.model_validate_json(
            json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        )
        key = keys[(claims.key_id, claims.key_epoch)]
        expected = hmac.new(
            key.secret, COMPOSITE_CURSOR_DOMAIN + raw, hashlib.sha256
        ).digest()
        if (
            not _key_may_verify(key, issued_at=claims.issued_at, now=now)
            or now >= claims.expires_at
            or not hmac.compare_digest(expected, supplied)
        ):
            raise ValueError
        retained_binding = (
            claims.tenant_id,
            claims.principal_id,
            claims.principal_binding_digest,
            claims.authorization_snapshot_digest,
            claims.authorized_scope_ids,
            claims.scope_digest,
        )
        current_binding = (
            access.tenant_id,
            access.principal_id,
            access.principal_binding_digest,
            access.authorization_snapshot_digest,
            access.authorized_scope_ids,
            access.scope_digest,
        )
        if retained_binding != current_binding or not set(
            claims.listing_scope_ids
        ) <= set(access.authorized_scope_ids):
            raise ValueError
        return claims
    except CompositeConflictListingError:
        raise
    except (binascii.Error, KeyError, TypeError, ValueError):
        raise CompositeConflictListingError(
            "invalid_conflict_cursor"
        ) from None


def validate_composite_continuation(
    *,
    claims: CompositeConflictListingCursorClaims,
    snapshot: CompositeConflictListingSnapshot,
    now: datetime,
) -> None:
    """Fail closed on a missing, expired, substituted, or changed snapshot."""

    if (
        claims.composite_snapshot_id != snapshot.snapshot_id
        or claims.composite_snapshot_digest != snapshot.snapshot_digest
        or claims.semantic_child_binding_digest
        != snapshot.child_bindings[0].binding_digest
        or claims.integrity_child_binding_digest
        != snapshot.child_bindings[1].binding_digest
        or claims.tenant_id != snapshot.tenant_id
        or claims.principal_id != snapshot.principal_id
        or claims.principal_binding_digest != snapshot.principal_binding_digest
        or claims.authorization_snapshot_digest
        != snapshot.authorization_snapshot_digest
        or claims.authorized_scope_ids != snapshot.authorized_scope_ids
        or claims.listing_scope_ids != snapshot.listing_scope_ids
        or claims.scope_digest != snapshot.scope_digest
        or now >= snapshot.expires_at
    ):
        raise CompositeConflictListingError("invalid_conflict_cursor")


def route_composite_member(
    member: CompositeConflictListingMember,
) -> CompositeMemberRoute:
    """Only a semantic member routes to the same-store repository."""

    if member.member_key.child_kind is CompositeChildKind.SEMANTIC:
        return CompositeMemberRoute.SEMANTIC_REPOSITORY
    return CompositeMemberRoute.OPERATOR_ACTION_REQUIRED


class CompositeConflictListingRepository:
    """Single-paged composite listing over the retained child snapshots.

    A fresh listing creates one retained child snapshot per audience side,
    freezes both bindings and every member key in one composite snapshot, and
    pages that immutable member sequence through v2 composite cursors.  The
    file ledger remains the durable child authority; this owner performs no
    introduction or transition writes.
    """

    def __init__(
        self,
        ledger: FileConflictAttentionRepository,
        *,
        now_provider: object = None,
    ) -> None:
        self._ledger = ledger
        self._now = now_provider or (lambda: datetime.now(UTC))

    def list_conflicts(
        self,
        access: ConflictAccessContext,
        request: ConflictListRequest,
    ) -> ConflictAttentionPage:
        from memorii.core.memory_evolution.conflict_attention_repository import (
            ConflictAttentionReadError,
        )

        if request.cursor is None:
            scopes = request.scope_ids or access.authorized_scope_ids
            (
                semantic_binding,
                integrity_binding,
                semantic_keys,
                integrity_keys,
                _items,
            ) = self._ledger.create_composite_child_bindings(access, scopes=scopes)
            snapshot = assemble_composite_snapshot(
                snapshot_id=token_hex(16),
                access=access,
                semantic_binding=semantic_binding,
                integrity_binding=integrity_binding,
                ordered_semantic_keys=semantic_keys,
                ordered_integrity_keys=integrity_keys,
                created_at=self._now(),
            )
            self._ledger.retain_composite_snapshot(snapshot)
            start = 0
        else:
            try:
                claims = decode_composite_cursor(
                    request.cursor,
                    keys=self._ledger.cursor_keys(),
                    access=access,
                    now=self._now(),
                )
            except CompositeConflictListingError as exc:
                raise ConflictAttentionReadError(exc.reason) from None
            if (
                request.scope_ids is not None
                and request.scope_ids != claims.listing_scope_ids
            ):
                raise ConflictAttentionReadError("invalid_cursor_scope")
            try:
                snapshot = self._ledger.load_composite_snapshot(
                    claims.composite_snapshot_id
                )
                validate_composite_continuation(
                    claims=claims, snapshot=snapshot, now=self._now()
                )
            except (CompositeConflictListingError, ConflictAttentionReadError):
                raise ConflictAttentionReadError("invalid_conflict_cursor") from None
            start = self._continuation_start(snapshot, claims)
        items = self._ledger.composite_snapshot_items(snapshot)
        selected = items[start : start + request.page_size]
        next_cursor = None
        if start + len(selected) < len(items):
            last = snapshot.members[start + len(selected) - 1]
            next_cursor = encode_composite_cursor(
                _cursor_claims(snapshot, last),
                key=self._ledger.cursor_signing_key(),
            )
        return ConflictAttentionPage(
            items=tuple(selected),
            total_pending=len(items),
            next_cursor=next_cursor,
        )

    @staticmethod
    def _continuation_start(
        snapshot: CompositeConflictListingSnapshot,
        claims: CompositeConflictListingCursorClaims,
    ) -> int:
        from memorii.core.memory_evolution.conflict_attention_repository import (
            ConflictAttentionReadError,
        )

        matches = [
            index
            for index, member in enumerate(snapshot.members)
            if member.snapshot_ordinal == claims.last_snapshot_ordinal
            and member.member_key.member_key_digest == claims.last_member_key_digest
        ]
        if len(matches) != 1:
            raise ConflictAttentionReadError("invalid_conflict_cursor")
        return matches[0] + 1


def _cursor_claims(
    snapshot: CompositeConflictListingSnapshot,
    last: CompositeConflictListingMember,
) -> dict[str, object]:
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
    }


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


__all__ = [
    "COMPOSITE_CURSOR_LIFETIME",
    "COMPOSITE_CURSOR_PROTOCOL",
    "CompositeChildKind",
    "CompositeConflictChildSnapshotBinding",
    "CompositeConflictListingCursorClaims",
    "CompositeConflictListingError",
    "CompositeConflictListingMember",
    "CompositeConflictListingRepository",
    "CompositeConflictListingSnapshot",
    "CompositeConflictMemberKey",
    "CompositeMemberRoute",
    "assemble_composite_snapshot",
    "composite_snapshot_digest",
    "decode_composite_cursor",
    "encode_composite_cursor",
    "route_composite_member",
    "validate_composite_continuation",
]
