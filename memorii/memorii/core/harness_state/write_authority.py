"""Control-owned finite authority for managed host runtime commands.

This is deliberately distinct from read grants and operation-origin proofs.
A bearer credential identifies a host credential, while this registry decides
which *finite* commands that credential may request.  Resolution happens
under the installation publication barrier, so a grant revoked while a worker
is waiting can never be accepted by a later target transaction.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.harness_state.credentials import IssuedCredential
from memorii.core.persistence.runtime_contracts import RuntimeCommandRequest
from memorii.core.storage_administration.operator import (
    OwnerCapability,
    require_owner_capability,
)
from memorii.core.storage_administration.service import (
    InstallationControlState,
    RuntimePublicationState,
    StorageAdministrationService,
)

RuntimeCommandKind = Literal[
    "start_task",
    "resume_task",
    "record_observation",
    "propose_state_change",
    "record_action_dispatch",
    "record_action_result",
    "checkpoint_task",
    "replan_task",
    "complete_task",
    "pause_task",
    "abort_task",
]


class HostCommandAuthorityError(RuntimeError):
    """Managed command authority was absent, stale, or outside its scope."""


class HostCommandGrant(BaseModel):
    """One finite command grant, persisted in installation control state."""

    grant_id: str = Field(min_length=1)
    credential_id: str = Field(min_length=1)
    principal: str = Field(min_length=1)
    client_namespace: str = Field(min_length=1, max_length=512)
    allowed_kinds: tuple[RuntimeCommandKind, ...] = Field(min_length=1)
    allowed_operation_ids: tuple[str, ...] = ()
    allowed_task_ids: tuple[str, ...] = ()
    epoch: int = Field(default=1, ge=1)
    expires_at: datetime
    installation_id: str = Field(min_length=1)
    data_generation_id: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def finite_scope_is_complete(self) -> HostCommandGrant:
        if len(set(self.allowed_kinds)) != len(self.allowed_kinds):
            raise ValueError("allowed_kinds must not contain duplicates")
        if len(set(self.allowed_operation_ids)) != len(self.allowed_operation_ids):
            raise ValueError("allowed_operation_ids must not contain duplicates")
        if len(set(self.allowed_task_ids)) != len(self.allowed_task_ids):
            raise ValueError("allowed_task_ids must not contain duplicates")
        if any(not item for item in self.allowed_operation_ids + self.allowed_task_ids):
            raise ValueError("grant coordinates must be nonempty")
        non_start_kinds = tuple(kind for kind in self.allowed_kinds if kind != "start_task")
        if non_start_kinds and not self.allowed_task_ids:
            raise ValueError("non-start commands require explicit task scope")
        if "start_task" in self.allowed_kinds and (
            non_start_kinds or self.allowed_task_ids
        ):
            raise ValueError("start_task authority must be granted separately")
        if self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
        return self


class HostCommandGrantRequest(BaseModel):
    """Owner-supplied finite scope used to issue one managed grant."""

    grant_id: str = Field(min_length=1)
    credential_id: str = Field(min_length=1)
    principal: str = Field(min_length=1)
    client_namespace: str = Field(min_length=1, max_length=512)
    allowed_kinds: tuple[RuntimeCommandKind, ...] = Field(min_length=1)
    allowed_operation_ids: tuple[str, ...] = ()
    allowed_task_ids: tuple[str, ...] = ()
    expires_at: datetime

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def finite_scope_is_complete(self) -> HostCommandGrantRequest:
        if len(set(self.allowed_kinds)) != len(self.allowed_kinds):
            raise ValueError("allowed_kinds must not contain duplicates")
        if len(set(self.allowed_operation_ids)) != len(self.allowed_operation_ids):
            raise ValueError("allowed_operation_ids must not contain duplicates")
        if len(set(self.allowed_task_ids)) != len(self.allowed_task_ids):
            raise ValueError("allowed_task_ids must not contain duplicates")
        if any(not item for item in self.allowed_operation_ids + self.allowed_task_ids):
            raise ValueError("grant coordinates must be nonempty")
        non_start_kinds = tuple(kind for kind in self.allowed_kinds if kind != "start_task")
        if non_start_kinds and not self.allowed_task_ids:
            raise ValueError("non-start commands require explicit task scope")
        if "start_task" in self.allowed_kinds and (
            non_start_kinds or self.allowed_task_ids
        ):
            raise ValueError("start_task authority must be granted separately")
        if self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
        return self


class ResolvedHostCommandAuthority(BaseModel):
    """In-process result after credential and finite-scope validation."""

    grant_id: str
    grant_epoch: int = Field(ge=1)
    credential_id: str
    principal: str
    client_namespace: str
    installation_id: str
    data_generation_id: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class _RegistryPayload(BaseModel):
    grants: tuple[HostCommandGrant, ...] = ()
    revoked: dict[str, int] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", frozen=True)


class ManagedHostCommandAuthority:
    """Installation-control registry for finite managed host command grants.

    Public resolution opens ``verified_operation_context`` itself.  Target
    owners that already hold that context must call
    :meth:`resolve_in_verified_context`; this avoids re-acquiring the
    non-reentrant publication fence while preserving the same linearization
    point as target commit.
    """

    def __init__(self, administration: StorageAdministrationService) -> None:
        self._administration = administration
        self._directory = administration.installation_root / "control" / "runtime-write-grants"
        self._directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self._directory, 0o700)
        self._path = self._directory / "grants.json"
        self._lock_path = self._directory / "grants.lock"

    def issue(
        self,
        request: HostCommandGrantRequest,
        *,
        capability: OwnerCapability,
    ) -> HostCommandGrant:
        """Owner-authorize a new finite grant for the current generation."""
        require_owner_capability(self._administration, capability)
        with self._administration.verified_operation_context() as (state, finalized):
            payload = self._read_payload()
            if any(item.grant_id == request.grant_id for item in payload.grants):
                raise HostCommandAuthorityError("conflict: grant id already exists")
            if any(
                item.client_namespace == request.client_namespace
                and item.installation_id == state.installation_id
                and item.data_generation_id == finalized.data_generation_id
                for item in payload.grants
            ):
                raise HostCommandAuthorityError(
                    "conflict: client namespace is already bound in this generation"
                )
            grant = HostCommandGrant(
                **request.model_dump(),
                installation_id=state.installation_id,
                data_generation_id=finalized.data_generation_id,
            )
            self._write_payload(
                payload.model_copy(update={"grants": (*payload.grants, grant)})
            )
            return grant

    def revoke(self, grant_id: str, *, capability: OwnerCapability) -> int:
        """Owner-authorize an append-only epoch advance for one grant."""
        if not grant_id:
            raise HostCommandAuthorityError("invalid_request: grant id must be nonempty")
        require_owner_capability(self._administration, capability)
        with self._administration.verified_operation_context():
            payload = self._read_payload()
            if not any(item.grant_id == grant_id for item in payload.grants):
                raise HostCommandAuthorityError("not_found: grant does not exist")
            next_epoch = int(payload.revoked.get(grant_id, 1)) + 1
            self._write_payload(
                payload.model_copy(
                    update={"revoked": {**payload.revoked, grant_id: next_epoch}}
                )
            )
            return next_epoch

    def resolve(
        self,
        *,
        credential: IssuedCredential,
        request: RuntimeCommandRequest,
        grant_id: str,
        grant_epoch: int,
        now: datetime | None = None,
    ) -> ResolvedHostCommandAuthority:
        """Resolve one host-selected grant under the installation barrier."""
        with self._administration.verified_operation_context() as (state, finalized):
            return self.resolve_in_verified_context(
                credential=credential,
                request=request,
                grant_id=grant_id,
                grant_epoch=grant_epoch,
                state=state,
                finalized=finalized,
                now=now,
            )

    def resolve_for_credential(
        self,
        *,
        credential: IssuedCredential,
        request: RuntimeCommandRequest,
        now: datetime | None = None,
    ) -> ResolvedHostCommandAuthority:
        """Resolve exactly one live grant without client-selected authority."""
        with self._administration.verified_operation_context() as (state, finalized):
            return self.resolve_for_credential_in_verified_context(
                credential=credential,
                request=request,
                state=state,
                finalized=finalized,
                now=now,
            )

    def resolve_for_credential_in_verified_context(
        self,
        *,
        credential: IssuedCredential,
        request: RuntimeCommandRequest,
        state: InstallationControlState,
        finalized: RuntimePublicationState,
        now: datetime | None = None,
    ) -> ResolvedHostCommandAuthority:
        """Server resolution under the caller's existing verified context."""
        payload = self._read_payload()
        moment = now or datetime.now(UTC)
        matches: list[HostCommandGrant] = []
        for grant in payload.grants:
            if grant.credential_id != credential.credential_id:
                continue
            if payload.revoked.get(grant.grant_id, grant.epoch) != grant.epoch:
                continue
            if moment >= grant.expires_at:
                continue
            if (
                grant.installation_id != state.installation_id
                or grant.data_generation_id != finalized.data_generation_id
                or request.kind not in grant.allowed_kinds
            ):
                continue
            if grant.allowed_operation_ids and request.operation_id not in grant.allowed_operation_ids:
                continue
            if request.kind != "start_task" and request.task_id not in grant.allowed_task_ids:
                continue
            matches.append(grant)
        if not matches:
            raise HostCommandAuthorityError("denied: no active grant authorizes command")
        if len(matches) != 1:
            raise HostCommandAuthorityError(
                "unsupported_configuration: credential has ambiguous command grants"
            )
        grant = matches[0]
        if grant.principal != credential.principal:
            raise HostCommandAuthorityError("denied: credential does not match grant")
        return self._resolved(grant)

    def resolve_persisted_binding_in_verified_context(
        self,
        *,
        credential_id: str,
        principal: str,
        grant_id: str,
        grant_epoch: int,
        request: RuntimeCommandRequest,
        state: InstallationControlState,
        finalized: RuntimePublicationState,
        now: datetime | None = None,
    ) -> ResolvedHostCommandAuthority:
        """Revalidate an already-authorized spool/receipt binding.

        This accepts no bearer and must only be used after the caller has
        verified its persisted origin/binding proof.  It is intentionally not
        a sidecar admission method: network request fields may not choose the
        credential, grant, or epoch.
        """
        return self.resolve_in_verified_context(
            credential=IssuedCredential(
                credential_id=credential_id, principal=principal
            ),
            request=request,
            grant_id=grant_id,
            grant_epoch=grant_epoch,
            state=state,
            finalized=finalized,
            now=now,
        )

    def resolve_persisted_namespace_in_verified_context(
        self,
        *,
        principal: str,
        client_namespace: str,
        request: RuntimeCommandRequest,
        state: InstallationControlState,
        finalized: RuntimePublicationState,
        now: datetime | None = None,
    ) -> ResolvedHostCommandAuthority:
        """Resolve replay authority from an immutable signed origin namespace.

        The caller verifies the origin proof first.  Namespace uniqueness is
        enforced at issuance across the generation, so this cannot choose
        between grants or be redirected by spool-provided grant coordinates.
        """
        matches = tuple(
            grant
            for grant in self._read_payload().grants
            if grant.principal == principal
            and grant.client_namespace == client_namespace
            and grant.installation_id == state.installation_id
            and grant.data_generation_id == finalized.data_generation_id
        )
        if not matches:
            raise HostCommandAuthorityError("denied: origin namespace has no grant")
        if len(matches) != 1:
            raise HostCommandAuthorityError(
                "unsupported_configuration: origin namespace is not unique"
            )
        grant = matches[0]
        return self.resolve_in_verified_context(
            credential=IssuedCredential(
                credential_id=grant.credential_id, principal=principal
            ),
            request=request,
            grant_id=grant.grant_id,
            grant_epoch=grant.epoch,
            state=state,
            finalized=finalized,
            now=now,
        )

    def resolve_in_verified_context(
        self,
        *,
        credential: IssuedCredential,
        request: RuntimeCommandRequest,
        grant_id: str,
        grant_epoch: int,
        state: InstallationControlState,
        finalized: RuntimePublicationState,
        now: datetime | None = None,
    ) -> ResolvedHostCommandAuthority:
        """Resolve while the caller holds ``verified_operation_context``.

        This intentionally does not acquire the publication fence.  It is the
        target-commit form: mode/generation/revocation checks and effect must
        share the caller's existing installation barrier.
        """
        grant = self._grant_for(grant_id)
        if grant.epoch != grant_epoch:
            raise HostCommandAuthorityError("denied: grant epoch does not match")
        current_epoch = self._read_payload().revoked.get(grant_id, grant.epoch)
        if current_epoch != grant_epoch:
            raise HostCommandAuthorityError("denied: grant is revoked or stale")
        moment = now or datetime.now(UTC)
        if moment >= grant.expires_at:
            raise HostCommandAuthorityError("denied: grant is expired")
        if grant.credential_id != credential.credential_id or grant.principal != credential.principal:
            raise HostCommandAuthorityError("denied: credential does not match grant")
        if grant.installation_id != state.installation_id:
            raise HostCommandAuthorityError("denied: grant belongs to another installation")
        if grant.data_generation_id != finalized.data_generation_id:
            raise HostCommandAuthorityError("needs_reconciliation: grant belongs to another generation")
        if request.kind not in grant.allowed_kinds:
            raise HostCommandAuthorityError("denied: command kind is outside grant scope")
        if grant.allowed_operation_ids and request.operation_id not in grant.allowed_operation_ids:
            raise HostCommandAuthorityError("denied: operation id is outside grant scope")
        if request.kind == "start_task":
            if grant.allowed_task_ids:
                raise HostCommandAuthorityError("denied: start task scope is invalid")
        elif request.task_id not in grant.allowed_task_ids:
            raise HostCommandAuthorityError("denied: task id is outside grant scope")
        return ResolvedHostCommandAuthority(
            grant_id=grant.grant_id,
            grant_epoch=grant_epoch,
            credential_id=credential.credential_id,
            principal=grant.principal,
            client_namespace=grant.client_namespace,
            installation_id=grant.installation_id,
            data_generation_id=grant.data_generation_id,
        )

    @staticmethod
    def _resolved(grant: HostCommandGrant) -> ResolvedHostCommandAuthority:
        return ResolvedHostCommandAuthority(
            grant_id=grant.grant_id,
            grant_epoch=grant.epoch,
            credential_id=grant.credential_id,
            principal=grant.principal,
            client_namespace=grant.client_namespace,
            installation_id=grant.installation_id,
            data_generation_id=grant.data_generation_id,
        )

    def _grant_for(self, grant_id: str) -> HostCommandGrant:
        for grant in self._read_payload().grants:
            if grant.grant_id == grant_id:
                return grant
        raise HostCommandAuthorityError("not_found: grant does not exist")

    def _read_payload(self) -> _RegistryPayload:
        with self._locked():
            if not self._path.exists():
                return _RegistryPayload()
            try:
                return _RegistryPayload.model_validate_json(
                    self._path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError) as exc:
                raise HostCommandAuthorityError(
                    "unsupported_configuration: host command grant registry is corrupt"
                ) from exc

    def _write_payload(self, payload: _RegistryPayload) -> None:
        with self._locked():
            temporary = self._directory / f".grants.{os.getpid()}.tmp"
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.write(descriptor, payload.model_dump_json().encode("utf-8"))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.replace(temporary, self._path)
            directory = os.open(self._directory, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)

    @contextmanager
    def _locked(self) -> Iterator[None]:
        from memorii.core.memory_plane.file_lock import locked_file

        with locked_file(self._lock_path, exclusive=True):
            yield


__all__ = [
    "HostCommandAuthorityError",
    "HostCommandGrant",
    "HostCommandGrantRequest",
    "ManagedHostCommandAuthority",
    "ResolvedHostCommandAuthority",
    "RuntimeCommandKind",
]
