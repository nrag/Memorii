"""Finite managed runtime-command authority stays control-owned."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from memorii.core.harness_state.credentials import IssuedCredential
from memorii.core.harness_state.write_authority import (
    HostCommandAuthorityError,
    HostCommandGrantRequest,
    ManagedHostCommandAuthority,
)
from memorii.core.persistence.runtime_contracts import RuntimeCommandRequest
from memorii.core.storage_administration.operator import mint_owner_capability
from memorii.core.storage_administration.service import StorageAdministrationService


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
        "--capability-digest",
        capability.capability_digest,
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
