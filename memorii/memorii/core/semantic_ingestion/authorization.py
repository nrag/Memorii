"""Canonical same-store authorization authority for semantic ingestion execution and commit."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from hashlib import sha256
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.atomic_store import (
    AuthorizationReadSetPrecondition,
    PreplanningStoreError,
    SemanticAuthorizationAuthorityRecord,
    SemanticIngestionAtomicStore,
)
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.memory_evolution.writer_admission import SemanticWriterCommitBinding
from memorii.core.semantic_ingestion.contracts import SemanticAuthorizationReadSet


class SemanticAuthorizationAuthorityError(PreplanningStoreError):
    """A verified authority transition or authoritative read failed closed."""


class VerifiedSemanticAuthorizationTransition(BaseModel):
    authority_scope_id: str = Field(min_length=1)
    action: Literal["activate", "rotate", "revoke"]
    expected_revision: int = Field(ge=0)
    read_set: SemanticAuthorizationReadSet | None = None
    valid_until: datetime | None = None
    transition_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_transition(self) -> VerifiedSemanticAuthorizationTransition:
        if self.action == "revoke":
            if self.read_set is not None or self.valid_until is not None:
                raise ValueError("authorization revocation cannot carry active coordinates")
        elif self.read_set is None or self.valid_until is None or self.valid_until.utcoffset() is None:
            raise ValueError("authorization activation requires verified coordinates and expiry")
        body = self.model_dump(mode="python", exclude={"transition_digest"})
        if self.transition_digest != sha256(encode_typed_value(body)).hexdigest():
            raise ValueError("authorization transition digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> VerifiedSemanticAuthorizationTransition:
        digest_values = dict(values)
        digest_values.setdefault("read_set", None)
        digest_values.setdefault("valid_until", None)
        read_set = digest_values.get("read_set")
        if isinstance(read_set, SemanticAuthorizationReadSet):
            digest_values["read_set"] = read_set.model_dump(mode="python")
        return cls(
            **values,
            transition_digest=sha256(encode_typed_value(digest_values)).hexdigest(),
        )


class SemanticAuthorizationTransitionVerifier(Protocol):
    def verify(
        self, *, command_bytes: bytes, server_time: datetime,
    ) -> VerifiedSemanticAuthorizationTransition | None: ...


class SemanticAuthorizationAuthorityRepository:
    """Source-bound authority whose record is CASed with every semantic ingestion effect group."""

    def __init__(
        self,
        *,
        atomic_store: SemanticIngestionAtomicStore,
        writer_binding_provider: Callable[[], SemanticWriterCommitBinding],
        now_provider: Callable[[], datetime],
    ) -> None:
        self._store = atomic_store
        self._writer_binding_provider = writer_binding_provider
        self._now = now_provider

    @staticmethod
    def scope_id(*, source_id: str, source_digest: str) -> str:
        return f"source:{source_id}:{source_digest}"

    def apply_verified_transition(
        self, transition: VerifiedSemanticAuthorizationTransition,
    ) -> AuthorizationReadSetPrecondition:
        current = self._store.authorization_authority(transition.authority_scope_id)
        if transition.action == "activate":
            if transition.expected_revision != 0 or current is not None:
                raise SemanticAuthorizationAuthorityError("authorization activation CAS is stale")
            assert transition.read_set is not None and transition.valid_until is not None
            return self._store.install_authorization_authority(
                writer_binding=self._writer_binding_provider(),
                authority=self._record(
                    transition.authority_scope_id, 1, "active",
                    transition.read_set, transition.valid_until,
                ),
            )
        if current is None:
            raise SemanticAuthorizationAuthorityError("authorization transition requires active authority")
        authority, precondition = current
        if authority.authority_revision != transition.expected_revision:
            raise SemanticAuthorizationAuthorityError("authorization transition CAS is stale")
        if transition.action == "revoke":
            body = authority.model_dump(mode="python", exclude={"coordinates_digest"})
            body.update({"authority_revision": authority.authority_revision + 1, "state": "revoked"})
            replacement = SemanticAuthorizationAuthorityRecord(
                **body,
                coordinates_digest=sha256(encode_typed_value(body)).hexdigest(),
            )
        else:
            assert transition.read_set is not None and transition.valid_until is not None
            replacement = self._record(
                transition.authority_scope_id,
                authority.authority_revision + 1,
                "active",
                transition.read_set,
                transition.valid_until,
            )
        return self._store.replace_authorization_authority(
            writer_binding=self._writer_binding_provider(),
            expected=precondition,
            authority=replacement,
        )

    def observe_verified(
        self,
        *,
        authority_scope_id: str,
        read_set: SemanticAuthorizationReadSet,
        valid_until: datetime,
        server_now: datetime | None = None,
    ) -> AuthorizationReadSetPrecondition:
        current = self._store.authorization_authority(authority_scope_id)
        if current is None:
            return self.apply_verified_transition(VerifiedSemanticAuthorizationTransition.create(
                authority_scope_id=authority_scope_id,
                action="activate",
                expected_revision=0,
                read_set=read_set,
                valid_until=valid_until,
            ))
        authority, precondition = current
        if (
            authority.state != "active"
            or authority.valid_until <= (server_now or self._now())
            or not self._matches(authority, read_set)
        ):
            raise SemanticAuthorizationAuthorityError("same-store authorization authority is not current")
        return precondition

    def require_current(
        self, *, authority_scope_id: str, read_set: SemanticAuthorizationReadSet,
        server_now: datetime | None = None,
    ) -> AuthorizationReadSetPrecondition:
        current = self._store.authorization_authority(authority_scope_id)
        if current is None:
            raise SemanticAuthorizationAuthorityError("same-store authorization authority is unavailable")
        authority, precondition = current
        if (
            authority.state != "active"
            or authority.valid_until <= (server_now or self._now())
            or not self._matches(authority, read_set)
        ):
            raise SemanticAuthorizationAuthorityError("same-store authorization authority is stale")
        return precondition

    @staticmethod
    def _record(
        scope_id: str,
        revision: int,
        state: Literal["active", "revoked"],
        read_set: SemanticAuthorizationReadSet,
        valid_until: datetime,
    ) -> SemanticAuthorizationAuthorityRecord:
        record_id = f"semantic_ingestion:authorization:{sha256(scope_id.encode('utf-8')).hexdigest()}"
        body = {
            "authority_record_id": record_id,
            "authority_scope_id": scope_id,
            "authority_revision": revision,
            "state": state,
            "policy_bundle_digest": read_set.policy_bundle_digest,
            "policy_revision_digest": read_set.policy_revision_digest,
            "egress_policy_revision": read_set.egress_policy_revision,
            "egress_decision_digest": read_set.egress_decision_digest,
            "deployment_authorization_digest": read_set.deployment_authorization_digest,
            "deployment_active_epoch": read_set.deployment_active_epoch,
            "deployment_decision_digest": read_set.deployment_decision_digest,
            "valid_until": valid_until,
            "read_set_digest": read_set.read_set_digest,
        }
        return SemanticAuthorizationAuthorityRecord(
            **body,
            coordinates_digest=sha256(encode_typed_value(body)).hexdigest(),
        )

    @staticmethod
    def _matches(
        authority: SemanticAuthorizationAuthorityRecord,
        read_set: SemanticAuthorizationReadSet,
    ) -> bool:
        return (
            authority.policy_bundle_digest == read_set.policy_bundle_digest
            and authority.policy_revision_digest == read_set.policy_revision_digest
            and authority.egress_policy_revision == read_set.egress_policy_revision
            and authority.egress_decision_digest == read_set.egress_decision_digest
            and authority.deployment_authorization_digest == read_set.deployment_authorization_digest
            and authority.deployment_active_epoch == read_set.deployment_active_epoch
            and authority.deployment_decision_digest == read_set.deployment_decision_digest
            and authority.read_set_digest == read_set.read_set_digest
        )


class VerifiedSemanticAuthorizationControlPlane:
    """Adapter: external signature/lifecycle verification precedes same-store CAS."""

    def __init__(
        self,
        *,
        verifier: SemanticAuthorizationTransitionVerifier,
        repository: SemanticAuthorizationAuthorityRepository,
        now_provider: Callable[[], datetime],
    ) -> None:
        self._verifier = verifier
        self._repository = repository
        self._now = now_provider

    def apply(self, command_bytes: bytes) -> AuthorizationReadSetPrecondition:
        transition = self._verifier.verify(
            command_bytes=bytes(command_bytes), server_time=self._now()
        )
        if transition is None:
            raise SemanticAuthorizationAuthorityError("authorization transition verification failed")
        return self._repository.apply_verified_transition(transition)


__all__ = [
    "SemanticAuthorizationAuthorityError",
    "SemanticAuthorizationAuthorityRepository",
    "SemanticAuthorizationTransitionVerifier",
    "VerifiedSemanticAuthorizationTransition",
    "VerifiedSemanticAuthorizationControlPlane",
]
