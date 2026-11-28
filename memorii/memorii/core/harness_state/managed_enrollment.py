"""Owner provisioning and exact read authority for enrolled native hosts."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from memorii.core.harness_state.credentials import IssuedCredential, SidecarCredentialStore
from memorii.core.harness_state.service import RuntimeReadGrant
from memorii.core.harness_state.write_authority import (
    HostCommandAuthorityError,
    HostCommandGrantRequest,
    ManagedHostCommandAuthority,
    NativeSourceScope,
)
from memorii.core.memory_plane.file_lock import locked_file
from memorii.core.persistence.contracts import InstallationControlState, RuntimePublicationState
from memorii.core.persistence.runtime_api import (
    CommandAuthorityPurpose,
    ManagedRuntimeCommandService,
    ResolvedRuntimeCommandAuthority,
    managed_start_task_id,
)
from memorii.core.persistence.runtime_contracts import (
    OperationOriginCoordinate,
    RuntimeCommandRequest,
    canonical_runtime_digest,
)
from memorii.core.persistence.runtime_repository import RuntimeStateRepository
from memorii.core.storage_administration.operator import OwnerCapability, require_owner_capability
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.stores.sqlite.private_storage import (
    ensure_private_directory,
    finish_private_handoff,
    read_private_file,
    require_private_directory,
    write_private_file,
)

_HOST_CREDENTIAL = re.compile(r"native-host-([0-9a-f]{64})\.[0-9a-f]{32}\Z")


class HostEnrollmentError(RuntimeError):
    """A content-free refusal from the owner provisioning boundary."""


class _ClosedEnrollmentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HostEnrollmentRequest(_ClosedEnrollmentModel):
    """One explicit owner operation and its finite native scope."""

    operation_id: str = Field(min_length=1, max_length=512)
    principal: str = Field(min_length=1, max_length=512)
    source: NativeSourceScope
    expires_at: AwareDatetime
    task_id: str | None = Field(default=None, min_length=1, max_length=512)
    goal: str | None = Field(default=None, min_length=1, max_length=16_384)
    replaces_grant_id: str | None = Field(default=None, min_length=1, max_length=512)

    @model_validator(mode="after")
    def select_task(self) -> HostEnrollmentRequest:
        if (self.task_id is None) == (self.goal is None):
            raise ValueError("select an existing task or provide a new task goal")
        if self.replaces_grant_id is not None and self.task_id is None:
            raise ValueError("credential rotation requires the existing exact task")
        return self


class HostEnrollmentReceipt(_ClosedEnrollmentModel):
    operation_id: str
    task_id: str
    credential_id: str
    read_grant_id: str
    command_grant_id: str
    client_namespace: str


class _EnrollmentRecord(_ClosedEnrollmentModel):
    protocol_version: Literal[1] = 1
    installation_id: str
    repository_id: str
    generation_id: str
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    principal: str
    source: NativeSourceScope
    task_id: str | None = None
    task_receipt_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    expires_at: AwareDatetime
    credential_id: str | None = None
    read_epoch: int = Field(default=1, ge=1)
    handoff_ready: bool = False

    def command_scope(self) -> HostCommandGrantRequest:
        if self.task_id is None or self.credential_id is None:
            raise HostEnrollmentError("integrity_error: enrollment coordinates are incomplete")
        return HostCommandGrantRequest(
            grant_id=self.credential_id,
            credential_id=self.credential_id,
            principal=self.principal,
            client_namespace=self.credential_id,
            allowed_kinds=("resume_task", "record_observation"),
            allowed_task_ids=(self.task_id,),
            native_source=self.source,
            expires_at=self.expires_at,
        )


class ManagedHostEnrollment:
    """Persist owner intent. Existing command-grant publication activates it."""

    def __init__(self, administration: StorageAdministrationService) -> None:
        self._administration = administration
        control = administration.installation_root / "control"
        self.credentials = SidecarCredentialStore(control / "runtime-credentials")
        self._grants = ManagedHostCommandAuthority(administration)
        self._root = control / "native-host-enrollments"
        ensure_private_directory(self._root)

    def enroll(
        self, request: HostEnrollmentRequest, *, capability: OwnerCapability, credential_file: Path,
    ) -> HostEnrollmentReceipt:
        from memorii.core.harness_state.native_sources import enroll_native_source

        require_owner_capability(self._administration, capability)
        require_private_directory(credential_file.parent)
        key = canonical_runtime_digest({"operation": request.operation_id})
        path = self._root / f"{key}.json"
        request_digest = canonical_runtime_digest({
            "request": request.model_dump(mode="json"),
            "handoff": str(credential_file.absolute()),
        })
        with locked_file(self._root / "enrollments.lock", exclusive=True, private=True):
            record = self._read_record(path)
            with self._administration.verified_operation_context() as (state, finalized):
                if state.mode != "active" or datetime.now(UTC) >= request.expires_at:
                    raise HostEnrollmentError("denied: enrollment requires a current expiry and active installation")
                if record is None:
                    record = _EnrollmentRecord(
                        installation_id=state.installation_id,
                        repository_id=finalized.repository_id,
                        generation_id=finalized.data_generation_id,
                        request_digest=request_digest,
                        principal=request.principal,
                        source=request.source,
                        expires_at=request.expires_at,
                    )
                    self._write_record(path, record)
                elif record.request_digest != request_digest:
                    raise HostEnrollmentError("conflict: operation id already binds another enrollment")
                elif not self._in_generation(record, finalized):
                    raise HostEnrollmentError("needs_reconciliation: enrollment belongs to another generation")

            if record.task_id is None:
                task_id, receipt_digest = self._task_for(request, key=key, capability=capability, record=record)
                record = record.model_copy(update={"task_id": task_id, "task_receipt_digest": receipt_digest})
                self._write_record(path, record)
            if record.credential_id is not None:
                issued = self._grants.inspect_grant(record.credential_id, capability=capability)
                if issued is not None:
                    grant, epoch = issued
                    if epoch != grant.epoch or not record.handoff_ready:
                        raise HostEnrollmentError("denied: enrollment is revoked or incomplete")
                    if record.command_scope().model_dump() != grant.model_dump(include=set(HostCommandGrantRequest.model_fields)):
                        raise HostEnrollmentError("integrity_error: enrollment grant does not match")
                    return self._receipt(request.operation_id, record)

            record = self._handoff(credential_file, key=key, path=path, record=record)
            if request.replaces_grant_id is not None:
                self._retire_previous(request.replaces_grant_id, record, capability=capability)
            # All prerequisites have durably landed before any host command
            # can resolve its grant. A retry inspects that same commit.
            enroll_native_source(
                self._administration, record.command_scope(), capability=capability,
                expected_generation_id=record.generation_id,
            )
            return self._receipt(request.operation_id, record)

    def resolve_read(
        self, *, credential: IssuedCredential, task_id: str,
        state: InstallationControlState, finalized: RuntimePublicationState,
        source: NativeSourceScope | None = None,
    ) -> RuntimeReadGrant:
        """Resolve a credential and exact task under an already verified fence."""
        match = _HOST_CREDENTIAL.fullmatch(credential.credential_id)
        record = self._read_record(self._root / f"{match.group(1)}.json") if match else None
        if (
            record is None or not record.handoff_ready or record.credential_id != credential.credential_id
            or record.principal != credential.principal or record.task_id != task_id
            or not self._in_generation(record, finalized)
            or (source is not None and record.source != source)
        ):
            raise HostEnrollmentError("denied: enrolled read authority is unavailable")
        try:
            grant = self._grants.resolve_in_verified_context(
                credential=credential, grant_id=credential.credential_id, grant_epoch=1,
                request=RuntimeCommandRequest(
                    kind="resume_task", task_id=task_id, operation_id="native-read-authority", expected_revision=0,
                ),
                state=state, finalized=finalized,
            )
        except HostCommandAuthorityError as exc:
            raise HostEnrollmentError("denied: enrolled read authority is unavailable") from exc
        if grant.native_source != record.source or grant.client_namespace != credential.credential_id:
            raise HostEnrollmentError("denied: enrolled read authority is unavailable")
        result = RuntimeReadGrant(
            grant_id=f"read:{credential.credential_id}", principal=record.principal,
            allowed_task_ids=(task_id,), epoch=record.read_epoch, expires_at=record.expires_at,
        )
        if not result.authorizes(task_id):
            raise HostEnrollmentError("denied: enrolled read authority is unavailable")
        return result

    def _task_for(
        self, request: HostEnrollmentRequest, *, key: str, capability: OwnerCapability, record: _EnrollmentRecord,
    ) -> tuple[str, str | None]:
        task_id = request.task_id
        receipt_digest = None
        if task_id is None:
            command = RuntimeCommandRequest(kind="start_task", operation_id=f"native-task:{key}", goal=request.goal)

            def authorize(
                incoming: RuntimeCommandRequest, purpose: CommandAuthorityPurpose,
                origin: OperationOriginCoordinate | None,
                state: InstallationControlState, finalized: RuntimePublicationState,
            ) -> ResolvedRuntimeCommandAuthority | None:
                if incoming != command or purpose == "historical_release" or not self._in_generation(record, finalized):
                    return None
                require_owner_capability(self._administration, capability)
                return ResolvedRuntimeCommandAuthority(request.principal, "operator:native-task")

            service = ManagedRuntimeCommandService(self._administration, authorize=authorize)
            proof = service.prepare(command)
            receipt = service.dispatch(command, operation_origin=proof)
            if receipt.status != "committed" or receipt.operation_origin != proof.coordinate:
                raise HostEnrollmentError("integrity_error: signed task receipt does not match provisioning")
            task_id = managed_start_task_id(proof.coordinate)
            receipt_digest = canonical_runtime_digest(receipt.model_dump(mode="json"))
        with self._administration.verified_operation_context() as (_, finalized):
            if not self._in_generation(record, finalized):
                raise HostEnrollmentError("needs_reconciliation: enrollment generation changed")
            task = RuntimeStateRepository(self._administration.partition()).get_task(task_id)
            if task is None or task.principal != request.principal:
                raise HostEnrollmentError("denied: exact enrollment task is unavailable")
        return task_id, receipt_digest

    def _handoff(
        self, destination: Path, *, key: str, path: Path, record: _EnrollmentRecord,
    ) -> _EnrollmentRecord:
        finish_private_handoff(destination)
        try:
            previous = read_private_file(destination, limit=256).decode("ascii")
        except FileNotFoundError:
            previous = None
        if previous is None:
            if record.credential_id is not None:
                self.credentials.retire(record.credential_id)
            record = record.model_copy(update={
                "credential_id": f"native-host-{key}.{uuid.uuid4().hex}", "handoff_ready": False,
            })
            self._write_record(path, record)
            _, secret = self.credentials.issue(record.principal, credential_id=record.credential_id)
            write_private_file(destination, secret.encode("ascii"), exclusive=True)
        else:
            credential = self.credentials.credential_for(previous)
            if (
                credential is None or credential.credential_id != record.credential_id
                or credential.principal != record.principal
            ):
                raise HostEnrollmentError("conflict: host credential destination already exists")
        ready = record.model_copy(update={"handoff_ready": True})
        self._write_record(path, ready)
        return ready

    def _retire_previous(
        self, grant_id: str, record: _EnrollmentRecord, *, capability: OwnerCapability,
    ) -> None:
        previous = self._grants.inspect_grant(grant_id, capability=capability)
        if previous is None:
            raise HostEnrollmentError("denied: the prior enrollment does not exist")
        grant, epoch = previous
        if (
            _HOST_CREDENTIAL.fullmatch(grant.credential_id) is None
            or grant.principal != record.principal or grant.allowed_task_ids != (record.task_id,)
            or grant.native_source != record.source or grant.data_generation_id != record.generation_id
        ):
            raise HostEnrollmentError("denied: the prior enrollment does not match the replacement scope")
        if epoch == grant.epoch:
            self._grants.revoke(grant_id, capability=capability)
        self.credentials.retire(grant.credential_id)

    @staticmethod
    def _in_generation(record: _EnrollmentRecord, finalized: RuntimePublicationState) -> bool:
        return (
            record.installation_id == finalized.installation_id and record.repository_id == finalized.repository_id
            and record.generation_id == finalized.data_generation_id
        )

    @staticmethod
    def _receipt(operation_id: str, record: _EnrollmentRecord) -> HostEnrollmentReceipt:
        scope = record.command_scope()
        return HostEnrollmentReceipt(
            operation_id=operation_id, task_id=scope.allowed_task_ids[0], credential_id=scope.credential_id,
            read_grant_id=f"read:{scope.credential_id}", command_grant_id=scope.grant_id,
            client_namespace=scope.client_namespace,
        )

    @staticmethod
    def _write_record(path: Path, record: _EnrollmentRecord) -> None:
        write_private_file(path, record.model_dump_json().encode())

    @staticmethod
    def _read_record(path: Path) -> _EnrollmentRecord | None:
        try:
            return _EnrollmentRecord.model_validate_json(read_private_file(path, limit=1 << 20))
        except FileNotFoundError:
            return None
        except ValueError as exc:
            raise HostEnrollmentError("integrity_error: native enrollment record is invalid") from exc
