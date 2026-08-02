"""Source-bound, deny-by-default remote egress authority for semantic ingestion.

This module deliberately owns policy lifecycle separately from transport.  A
provider can ask for a decision, but cannot install, activate, or revive one.
Hosts supply signature and lifecycle verification; there is no package-local
trust root or permissive fallback.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.memory_plane.file_lock import locked_file


def _digest(domain: bytes, value: object) -> str:
    return sha256(domain + b"\0" + encode_typed_value(_canonical(value))).hexdigest()


def _canonical(value: object) -> object:
    if isinstance(value, BaseModel):
        return _canonical(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_canonical(item) for item in value)
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


class EgressPolicyError(ValueError):
    """A policy command or use did not satisfy the closed authority contract."""


class EgressPolicySignatureVerifier(Protocol):
    def verify(self, *, signer_id: str, payload: bytes, signature: bytes) -> bool: ...


class EgressPolicyLifecycleVerifier(Protocol):
    def is_eligible(self, *, signer_id: str, at: datetime) -> bool: ...


class ProviderEgressBinding(BaseModel):
    tenant_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    classification: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    region: str = Field(min_length=1)
    retention_mode: str = Field(min_length=1)
    training_use: bool

    model_config = ConfigDict(
        extra="forbid", frozen=True, ser_json_bytes="base64", val_json_bytes="base64"
    )


class ProviderEgressDecision(BaseModel):
    binding: ProviderEgressBinding
    policy_id: str = Field(min_length=1)
    policy_revision: int = Field(ge=1)
    policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    expires_at: datetime

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_digest(self) -> ProviderEgressDecision:
        body = self.model_dump(mode="python", exclude={"decision_digest"})
        if self.decision_digest != _digest(b"memorii.semantic-ingestion.egress-decision.v1", body):
            raise ValueError("provider egress decision digest mismatch")
        return self

    @classmethod
    def create(
        cls, *, binding: ProviderEgressBinding, policy_id: str, policy_revision: int,
        policy_fingerprint: str, expires_at: datetime,
    ) -> ProviderEgressDecision:
        body = {
            "binding": binding, "policy_id": policy_id, "policy_revision": policy_revision,
            "policy_fingerprint": policy_fingerprint, "expires_at": expires_at,
        }
        return cls(**body, decision_digest=_digest(b"memorii.semantic-ingestion.egress-decision.v1", body))


class SignedEgressPolicyCommand(BaseModel):
    command_id: str = Field(min_length=1)
    action: Literal["install", "activate", "rotate", "revoke", "rollback"]
    policy_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=0)
    issued_at: datetime
    signer_id: str = Field(min_length=1)
    decision: ProviderEgressDecision | None = None
    rollback_to_revision: int | None = Field(default=None, ge=1)
    signature: bytes = Field(min_length=1)

    model_config = ConfigDict(
        extra="forbid", frozen=True, ser_json_bytes="base64", val_json_bytes="base64"
    )

    @model_validator(mode="after")
    def validate_shape(self) -> SignedEgressPolicyCommand:
        if self.action in {"install", "activate", "rotate"} and self.decision is None:
            raise ValueError("policy installation or activation requires a decision")
        if self.action in {"revoke", "rollback"} and self.decision is not None:
            raise ValueError("revoke and rollback cannot carry a decision")
        if self.action == "rollback" and self.rollback_to_revision is None:
            raise ValueError("rollback requires a target revision")
        if self.action != "rollback" and self.rollback_to_revision is not None:
            raise ValueError("only rollback may name a target revision")
        if self.decision is not None and self.decision.policy_id != self.policy_id:
            raise ValueError("policy command and decision IDs differ")
        return self

    def signed_payload(self) -> bytes:
        return encode_typed_value(_canonical(self.model_dump(mode="python", exclude={"signature"})))


class EgressPolicyControlRepository(Protocol):
    def apply(self, command: SignedEgressPolicyCommand, *, control_plane_principal: str) -> None: ...


class EgressPolicyProvider(Protocol):
    def current(self, *, binding: ProviderEgressBinding, at: datetime) -> ProviderEgressDecision | None: ...


class InMemoryEgressPolicyRepository(EgressPolicyControlRepository, EgressPolicyProvider):
    """Thread-safe CAS lifecycle repository intended only for tests/local processes."""

    def __init__(self, *, signature_verifier: EgressPolicySignatureVerifier,
                 lifecycle_verifier: EgressPolicyLifecycleVerifier) -> None:
        self._signature_verifier = signature_verifier
        self._lifecycle_verifier = lifecycle_verifier
        self._history: dict[str, dict[int, ProviderEgressDecision]] = {}
        self._active: dict[str, int] = {}
        self._revoked: set[tuple[str, int]] = set()
        self._commands: dict[str, str] = {}
        self._lock = RLock()

    def apply(self, command: SignedEgressPolicyCommand, *, control_plane_principal: str) -> None:
        with self._lock:
            self._apply_locked(command, control_plane_principal=control_plane_principal)

    def _apply_locked(
        self, command: SignedEgressPolicyCommand, *, control_plane_principal: str
    ) -> None:
        if not control_plane_principal:
            raise EgressPolicyError("egress control plane principal is required")
        command_digest = sha256(command.signed_payload() + command.signature).hexdigest()
        previous = self._commands.get(command.command_id)
        if previous is not None:
            if previous != command_digest:
                raise EgressPolicyError("egress command ID was reused with different bytes")
            return
        if not self._lifecycle_verifier.is_eligible(signer_id=command.signer_id, at=command.issued_at):
            raise EgressPolicyError("egress command signer is lifecycle-ineligible")
        if not self._signature_verifier.verify(
            signer_id=command.signer_id, payload=command.signed_payload(), signature=command.signature
        ):
            raise EgressPolicyError("egress command signature is invalid")
        active_revision = self._active.get(command.policy_id, 0)
        if active_revision != command.expected_revision:
            raise EgressPolicyError("egress policy command CAS is stale")
        history = self._history.setdefault(command.policy_id, {})
        if command.action in {"install", "activate", "rotate"}:
            assert command.decision is not None
            revision = command.decision.policy_revision
            if revision in history and history[revision] != command.decision:
                raise EgressPolicyError("egress policy revision bytes conflict")
            if command.action == "install" and active_revision != 0:
                raise EgressPolicyError("install requires an inactive policy")
            if command.action in {"activate", "rotate"} and revision <= active_revision:
                raise EgressPolicyError("activation must advance policy revision")
            history[revision] = command.decision
            self._active[command.policy_id] = revision
        elif command.action == "revoke":
            if active_revision == 0:
                raise EgressPolicyError("cannot revoke an inactive policy")
            self._revoked.add((command.policy_id, active_revision))
            del self._active[command.policy_id]
        else:
            assert command.rollback_to_revision is not None
            target = history.get(command.rollback_to_revision)
            if target is None or (command.policy_id, command.rollback_to_revision) in self._revoked:
                raise EgressPolicyError("rollback target is unavailable")
            # Rollback is forward-only: reinstall the target bytes at a new revision.
            new_revision = active_revision + 1
            replacement = ProviderEgressDecision.create(
                binding=target.binding, policy_id=target.policy_id, policy_revision=new_revision,
                policy_fingerprint=target.policy_fingerprint, expires_at=target.expires_at,
            )
            history[new_revision] = replacement
            self._active[command.policy_id] = new_revision
        self._commands[command.command_id] = command_digest

    def current(self, *, binding: ProviderEgressBinding, at: datetime) -> ProviderEgressDecision | None:
        # Read-only transport interface: any outage/corruption is represented as None.
        with self._lock:
            for policy_id, revision in tuple(self._active.items()):
                decision = self._history.get(policy_id, {}).get(revision)
                if decision is None or (policy_id, revision) in self._revoked or decision.expires_at <= at:
                    continue
                if decision.binding == binding:
                    return decision
        return None


class _PersistedEgressCommand(BaseModel):
    principal: str = Field(min_length=1)
    command: SignedEgressPolicyCommand
    record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_record(self) -> _PersistedEgressCommand:
        body = {"principal": self.principal, "command": self.command}
        if self.record_digest != _digest(b"memorii.semantic-ingestion.egress-command-record.v1", body):
            raise ValueError("persisted egress command digest mismatch")
        return self

    @classmethod
    def create(
        cls, *, principal: str, command: SignedEgressPolicyCommand
    ) -> _PersistedEgressCommand:
        body = {"principal": principal, "command": command}
        return cls(
            **body,
            record_digest=_digest(b"memorii.semantic-ingestion.egress-command-record.v1", body),
        )


class JsonlEgressPolicyRepository(EgressPolicyControlRepository, EgressPolicyProvider):
    """Process-safe durable egress authority with locked replay and CAS mutation."""

    def __init__(
        self,
        path: str | Path,
        *,
        signature_verifier: EgressPolicySignatureVerifier,
        lifecycle_verifier: EgressPolicyLifecycleVerifier,
    ) -> None:
        self._base_path = Path(path)
        self._records_path = self._base_path / "egress_policy_commands.jsonl"
        self._lock_path = self._base_path / "egress_policy_commands.lock"
        self._signature_verifier = signature_verifier
        self._lifecycle_verifier = lifecycle_verifier
        self._base_path.mkdir(parents=True, exist_ok=True)

    def apply(self, command: SignedEgressPolicyCommand, *, control_plane_principal: str) -> None:
        with locked_file(self._lock_path, exclusive=True):
            records = self._read_unlocked()
            repository = self._replay(records)
            existing = next(
                (record for record in records if record.command.command_id == command.command_id),
                None,
            )
            repository.apply(command, control_plane_principal=control_plane_principal)
            if existing is not None:
                return
            self._replace_unlocked(
                [
                    *records,
                    _PersistedEgressCommand.create(
                        principal=control_plane_principal, command=command
                    ),
                ]
            )

    def current(self, *, binding: ProviderEgressBinding, at: datetime) -> ProviderEgressDecision | None:
        with locked_file(self._lock_path, exclusive=False):
            return self._replay(self._read_unlocked()).current(binding=binding, at=at)

    def _replay(
        self, records: list[_PersistedEgressCommand]
    ) -> InMemoryEgressPolicyRepository:
        repository = InMemoryEgressPolicyRepository(
            signature_verifier=self._signature_verifier,
            lifecycle_verifier=self._lifecycle_verifier,
        )
        for record in records:
            repository.apply(record.command, control_plane_principal=record.principal)
        return repository

    def _read_unlocked(self) -> list[_PersistedEgressCommand]:
        if not self._records_path.exists():
            return []
        content = self._records_path.read_text(encoding="utf-8")
        if content and not content.endswith("\n"):
            raise EgressPolicyError("egress policy log ends with an incomplete record")
        records: list[_PersistedEgressCommand] = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                records.append(_PersistedEgressCommand.model_validate_json(line))
            except ValueError as exc:
                raise EgressPolicyError(
                    f"invalid egress policy record at line {line_number}: {exc}"
                ) from exc
        return records

    def _replace_unlocked(self, records: list[_PersistedEgressCommand]) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self._base_path, prefix=".egress-policy.", suffix=".tmp"
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                for record in records:
                    handle.write(record.model_dump_json())
                    handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self._records_path)
            directory = os.open(self._base_path, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise


def verify_current_egress(
    provider: EgressPolicyProvider | None, *, binding: ProviderEgressBinding, at: datetime,
) -> ProviderEgressDecision | None:
    """Deny on a missing, failed, stale, or mismatched control-plane read."""
    if provider is None:
        return None
    try:
        decision = provider.current(binding=binding, at=at)
    except (OSError, RuntimeError, ValueError):
        return None
    if decision is None or decision.binding != binding or decision.expires_at <= at:
        return None
    # Revalidate content-addressed bytes because model_copy bypasses validators.
    try:
        return ProviderEgressDecision.model_validate(decision.model_dump(mode="python"))
    except ValueError:
        return None
