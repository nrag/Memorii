"""Finite managed runtime-command authority stays control-owned."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from memorii.core.harness_state.credentials import IssuedCredential
from memorii.core.harness_state.write_authority import (
    HostCommandAuthorityError,
    HostCommandGrantRequest,
    ManagedHostCommandAuthority,
)
from memorii.core.persistence.managed_delivery import (
    DeliveryAuthorityBinding,
    MemoryPlaneCandidateScope,
    ProtectedSkillCandidateScope,
)
from memorii.core.persistence.runtime_contracts import RuntimeCommandRequest
from memorii.core.persistence.writeback_decisions import WritebackDecisionRequest, WritebackHostBinding
from memorii.core.storage_administration.operator import mint_owner_capability
from memorii.core.storage_administration.service import StorageAdministrationService
from tests.support.operator_files import write_owner_file


def _setup(tmp_path: Path) -> tuple[StorageAdministrationService, ManagedHostCommandAuthority, IssuedCredential]:
    administration = StorageAdministrationService(tmp_path / "installation")
    administration.initialize()
    return (
        administration,
        ManagedHostCommandAuthority(administration),
        IssuedCredential(principal="principal:a", credential_id="credential:a"),
    )


def _request(*, task_id: str = "task:a", operation_id: str = "operation:a") -> RuntimeCommandRequest:
    return RuntimeCommandRequest(
        kind="record_observation",
        operation_id=operation_id,
        task_id=task_id,
        expected_revision=0,
        source_digest="a" * 64,
    )


def _grant_request(credential: IssuedCredential) -> HostCommandGrantRequest:
    return HostCommandGrantRequest(
        grant_id="grant:a",
        credential_id=credential.credential_id,
        principal=credential.principal,
        client_namespace="host:openclaw:installation:a",
        allowed_kinds=("record_observation",),
        allowed_operation_ids=("operation:a",),
        allowed_task_ids=("task:a",),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )


def test_owner_issues_and_resolves_only_the_exact_finite_scope(tmp_path: Path) -> None:
    administration, authority, credential = _setup(tmp_path)
    grant = authority.issue(
        _grant_request(credential), capability=mint_owner_capability(administration, "owner:a")
    )

    resolved = authority.resolve(
        credential=credential,
        request=_request(),
        grant_id=grant.grant_id,
        grant_epoch=grant.epoch,
    )
    assert resolved.client_namespace == "host:openclaw:installation:a"
    assert resolved.credential_id == credential.credential_id

    with pytest.raises(HostCommandAuthorityError, match="operation id"):
        authority.resolve(
            credential=credential,
            request=_request(operation_id="operation:other"),
            grant_id=grant.grant_id,
            grant_epoch=grant.epoch,
        )
    with pytest.raises(HostCommandAuthorityError, match="task id"):
        authority.resolve(
            credential=credential,
            request=_request(task_id="task:other"),
            grant_id=grant.grant_id,
            grant_epoch=grant.epoch,
        )


def test_credential_identity_expiry_and_revocation_fail_closed(tmp_path: Path) -> None:
    administration, authority, credential = _setup(tmp_path)
    grant = authority.issue(
        _grant_request(credential), capability=mint_owner_capability(administration, "owner:a")
    )
    with pytest.raises(HostCommandAuthorityError, match="credential"):
        authority.resolve(
            credential=IssuedCredential(principal="principal:a", credential_id="credential:other"),
            request=_request(),
            grant_id=grant.grant_id,
            grant_epoch=grant.epoch,
        )
    with pytest.raises(HostCommandAuthorityError, match="expired"):
        authority.resolve(
            credential=credential,
            request=_request(),
            grant_id=grant.grant_id,
            grant_epoch=grant.epoch,
            now=datetime.now(UTC) + timedelta(minutes=10),
        )
    assert authority.revoke(
        grant.grant_id, capability=mint_owner_capability(administration, "owner:a")
    ) == 2
    with pytest.raises(HostCommandAuthorityError, match="revoked or stale"):
        authority.resolve(
            credential=credential,
            request=_request(),
            grant_id=grant.grant_id,
            grant_epoch=grant.epoch,
        )


def test_server_resolves_from_credential_without_client_grant_coordinates(tmp_path: Path) -> None:
    administration, authority, credential = _setup(tmp_path)
    authority.issue(
        _grant_request(credential), capability=mint_owner_capability(administration, "owner:a")
    )
    resolved = authority.resolve_for_credential(credential=credential, request=_request())
    assert resolved.grant_id == "grant:a"

    with pytest.raises(HostCommandAuthorityError, match="namespace"):
        authority.issue(
            _grant_request(credential).model_copy(update={"grant_id": "grant:b"}),
            capability=mint_owner_capability(administration, "owner:a"),
        )


def test_operation_restriction_is_optional_but_task_scope_is_not(tmp_path: Path) -> None:
    administration, authority, credential = _setup(tmp_path)
    grant = authority.issue(
        _grant_request(credential).model_copy(update={"allowed_operation_ids": ()}),
        capability=mint_owner_capability(administration, "owner:a"),
    )
    resolved = authority.resolve_for_credential(
        credential=credential, request=_request(operation_id="operation:another")
    )
    assert resolved.grant_id == grant.grant_id


def test_replay_binding_revalidates_persisted_authority_under_target_barrier(tmp_path: Path) -> None:
    administration, authority, credential = _setup(tmp_path)
    grant = authority.issue(
        _grant_request(credential), capability=mint_owner_capability(administration, "owner:a")
    )
    with administration.verified_operation_context() as (state, finalized):
        resolved = authority.resolve_persisted_binding_in_verified_context(
            credential_id=credential.credential_id,
            principal=credential.principal,
            grant_id=grant.grant_id,
            grant_epoch=grant.epoch,
            request=_request(),
            state=state,
            finalized=finalized,
        )
    assert resolved.client_namespace == "host:openclaw:installation:a"


def test_replay_can_resolve_only_the_signed_origin_namespace(tmp_path: Path) -> None:
    administration, authority, credential = _setup(tmp_path)
    authority.issue(
        _grant_request(credential), capability=mint_owner_capability(administration, "owner:a")
    )
    with administration.verified_operation_context() as (state, finalized):
        resolved = authority.resolve_persisted_namespace_in_verified_context(
            principal=credential.principal,
            client_namespace="host:openclaw:installation:a",
            request=_request(),
            state=state,
            finalized=finalized,
        )
    assert resolved.credential_id == credential.credential_id


def test_operator_cli_issues_and_revokes_owner_authorized_grant(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from memorii.tools.runtime_operator import main

    administration, authority, credential = _setup(tmp_path)
    capability = mint_owner_capability(administration, "owner:a")
    root = str(administration.installation_root)
    common = [
        "--installation-root",
        root,
        "--owner-principal",
        capability.owner_principal,
        "--capability-file", write_owner_file(tmp_path / "owner.capability", capability.capability_digest),
    ]
    assert main(
        [
            *common,
            "runtime-grant",
            "issue",
            "--grant-id",
            "grant:a",
            "--credential-id",
            credential.credential_id,
            "--principal",
            credential.principal,
            "--client-namespace",
            "host:openclaw:installation:a",
            "--kind",
            "record_observation",
            "--task-id",
            "task:a",
            "--expires-at",
            (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        ]
    ) == 0
    assert '"grant_id":"grant:a"' in capsys.readouterr().out
    assert main([*common, "runtime-grant", "revoke", "--grant-id", "grant:a"]) == 0
    assert '"epoch": 2' in capsys.readouterr().out
    with pytest.raises(HostCommandAuthorityError, match="revoked or stale"):
        authority.resolve(
            credential=credential,
            request=_request(),
            grant_id="grant:a",
            grant_epoch=1,
        )


def test_target_can_resolve_under_existing_verified_context_without_relocking(tmp_path: Path) -> None:
    administration, authority, credential = _setup(tmp_path)
    grant = authority.issue(
        _grant_request(credential), capability=mint_owner_capability(administration, "owner:a")
    )
    with administration.verified_operation_context() as (state, finalized):
        resolved = authority.resolve_in_verified_context(
            credential=credential,
            request=_request(),
            grant_id=grant.grant_id,
            grant_epoch=grant.epoch,
            state=state,
            finalized=finalized,
        )
    assert resolved.grant_id == grant.grant_id


def test_non_start_grants_require_task_scope(tmp_path: Path) -> None:
    _administration, _authority, credential = _setup(tmp_path)
    with pytest.raises(ValueError, match="task scope"):
        HostCommandGrantRequest(
            grant_id="grant:a",
            credential_id=credential.credential_id,
            principal=credential.principal,
            client_namespace="host:a",
            allowed_kinds=("record_observation",),
            allowed_operation_ids=("operation:a",),
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )


def test_writeback_authority_is_exact_and_rechecked_for_target(tmp_path: Path) -> None:
    administration, authority, credential = _setup(tmp_path)
    capability = mint_owner_capability(administration, "owner:a")
    command_grant = _grant_request(credential)
    with administration.verified_operation_context() as (state, finalized):
        scope = MemoryPlaneCandidateScope(
            partition_id=finalized.repository_id, task_id="task:a", domain="semantic",
        )
        request = WritebackDecisionRequest(
            host_binding=WritebackHostBinding(
                installation_id=state.installation_id,
                client_namespace=command_grant.client_namespace,
                task_id=scope.task_id,
            ),
            task_id=scope.task_id,
            operation_id="operation:a",
            result_id="a" * 64,
            output_id="b" * 64,
            expected_offer_version=1,
            expected_payload_digest="c" * 64,
            decision="accept",
        )
    grant = authority.issue(
        HostCommandGrantRequest.model_validate({
            **command_grant.model_dump(),
            "allowed_kinds": (),
            "allowed_task_ids": (),
            "allowed_writeback_scopes": [scope],
        }),
        capability=capability,
    )
    with pytest.raises(HostCommandAuthorityError, match="command kind"):
        authority.resolve(
            credential=credential, request=_request(), grant_id=grant.grant_id, grant_epoch=grant.epoch,
        )
    with administration.verified_operation_context() as (state, finalized):
        resolved = authority.resolve_writeback_in_verified_context(
            credential=credential, request=request, state=state, finalized=finalized,
        )
        assert resolved.permits_writeback(scope)
        assert not resolved.permits_writeback(
            ProtectedSkillCandidateScope(partition_id=scope.partition_id, task_id=scope.task_id)
        )
        assert not resolved.permits_writeback(
            MemoryPlaneCandidateScope(partition_id=scope.partition_id, task_id=scope.task_id, domain="user")
        )
        assert not resolved.permits_work_projection(scope.task_id)
        assert authority.resolve_writeback_in_verified_context(
            credential=credential, request=request.model_copy(update={"decision": "decline"}),
            state=state, finalized=finalized,
        ) == resolved
        for changed in (
            request.model_copy(update={"operation_id": "operation:other"}),
            request.model_copy(update={"task_id": "task:other"}),
            request.model_copy(update={
                "host_binding": request.host_binding.model_copy(update={"client_namespace": "namespace:other"}),
            }),
        ):
            with pytest.raises(HostCommandAuthorityError, match="denied:"):
                authority.resolve_writeback_in_verified_context(
                    credential=credential, request=changed, state=state, finalized=finalized,
                )
        binding = DeliveryAuthorityBinding(
            principal=resolved.principal,
            client_namespace=resolved.client_namespace,
            host_binding_id=resolved.client_namespace,
            credential_id=resolved.credential_id,
            installation_id=resolved.installation_id,
            grant_id=resolved.grant_id,
            grant_epoch=resolved.grant_epoch,
            scope=scope,
        )
        assert authority.resolve_persisted_writeback_in_verified_context(
            binding=binding, operation_id=request.operation_id, state=state, finalized=finalized,
        ) == resolved
        with pytest.raises(HostCommandAuthorityError, match="grant or target scope"):
            authority.resolve_persisted_writeback_in_verified_context(
                binding=binding.model_copy(update={"grant_epoch": binding.grant_epoch + 1}),
                operation_id=request.operation_id, state=state, finalized=finalized,
            )
    authority.revoke(grant.grant_id, capability=capability)
    with (
        administration.verified_operation_context() as (state, finalized),
        pytest.raises(HostCommandAuthorityError, match="no active grant"),
    ):
        authority.resolve_persisted_writeback_in_verified_context(
            binding=binding, operation_id=request.operation_id, state=state, finalized=finalized,
        )


def test_operator_cli_provisions_exact_writeback_scope(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture,
) -> None:
    from memorii.tools.runtime_operator import main

    administration, _authority, credential = _setup(tmp_path)
    capability = mint_owner_capability(administration, "owner:a")
    with administration.verified_operation_context() as (_state, finalized):
        scope = ProtectedSkillCandidateScope(partition_id=finalized.repository_id, task_id="task:a")
    command = [
        "--installation-root", str(administration.installation_root),
        "--owner-principal", capability.owner_principal,
        "--capability-file", write_owner_file(tmp_path / "owner.capability", capability.capability_digest),
        "runtime-grant", "issue",
        "--grant-id", "grant:writeback",
        "--credential-id", credential.credential_id,
        "--principal", credential.principal,
        "--client-namespace", "host:hermes:installation:a",
        "--expires-at", (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
    ]
    foreign_scope = scope.model_copy(update={"partition_id": "partition:other"})
    assert main([*command, "--writeback-scope", foreign_scope.model_dump_json()]) == 3
    assert "denied: runtime grant issuance failed" in caplog.text
    assert main([*command, "--writeback-scope", scope.model_dump_json()]) == 0
    issued = json.loads(capsys.readouterr().out)
    assert issued["allowed_kinds"] == []
    assert issued["allowed_writeback_scopes"] == [scope.model_dump(mode="json")]
