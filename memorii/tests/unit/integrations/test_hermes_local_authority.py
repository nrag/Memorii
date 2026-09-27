"""Focused contracts for the installed local Level 2 operator CLI."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import memorii.integrations.hermes_local_authority as local_authority
import pytest
from memorii.core.memory_evolution.atomic_store import StructuredSubmissionGrantRevokedError
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility
from memorii.integrations.hermes_local_authority import (
    LocalLevel2AuthorityError,
    authorize_local_level2,
    authorize_local_structured_tool,
    load_local_level2_authority,
    load_local_structured_tool_authority,
    local_level2_status,
    main,
)


def test_authorize_issues_an_installed_bundle_bound_sidecar(tmp_path: Path) -> None:
    result = authorize_local_level2(hermes_home=tmp_path)

    assert result.available is True
    assert result.profile == "memorii.project_assertions@1"
    assert (tmp_path / "memorii" / "installation-id").is_file()
    assert (tmp_path / "memorii" / "local-level2.json").is_file()


def test_cli_acknowledgement_issues_a_sidecar_from_verified_installed_material(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["authorize-local-level2", "--hermes-home", str(tmp_path), "--acknowledge-openai-egress"]) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["available"] is True
    assert result["profile"] == "memorii.project_assertions@1"
    assert (tmp_path / "memorii" / "local-level2.json").is_file()


def test_cli_requires_explicit_egress_acknowledgement(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as error:
        main(["authorize-local-level2", "--hermes-home", str(tmp_path)])

    assert error.value.code == 2
    assert not (tmp_path / "memorii").exists()


def test_structured_tool_artifact_is_closed_and_requires_the_verified_bootstrap_sidecar(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(LocalLevel2AuthorityError):
        authorize_local_structured_tool(hermes_home=tmp_path)

    authorize_local_level2(hermes_home=tmp_path)
    assert main([
        "authorize-local-structured-tool", "--hermes-home", str(tmp_path),
        "--acknowledge-local-memory",
    ]) == 0
    artifact = json.loads(capsys.readouterr().out)
    assert set(artifact) == local_authority._STRUCTURED_TOOL_FIELDS
    assert artifact["operator_acknowledgement"] == "local_structured_fact_no_egress"
    assert (tmp_path / "memorii" / "local-structured-tool.json").read_bytes().endswith(b"\n")
    assert load_local_structured_tool_authority(hermes_home=tmp_path) == artifact


def test_cli_revokes_factory_derived_grant_before_provisioning(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from memorii.core.memory_plane import JsonlMemoryPlaneStore, MemoryPlaneService
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    authorize_local_level2(hermes_home=tmp_path)
    binding = build_local_level2_runtime_binding(
        SimpleNamespace(
            storage_root=tmp_path / "memorii",
            hermes_home=tmp_path,
            session_id="session:one",
            user_id="raw:user:one",
            agent_identity="profile:primary",
            platform="cli",
            agent_context="primary",
            agent_workspace="hermes",
            parent_session_id=None,
        )
    )
    binding.completed_turn_runtime.close()
    authorize_local_structured_tool(hermes_home=tmp_path)

    assert main([
        "revoke-local-structured-grant", "--hermes-home", str(tmp_path),
        "--grant-kind", "fact",
    ]) == 0
    assert json.loads(capsys.readouterr().out) == {"grant_kind": "fact", "status": "revoked"}
    states = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(tmp_path / "memorii" / "memory-plane")
    ).list_records(source_kind="semantic_ingestion_structured_grant_state")
    assert len(states) == 1
    assert states[0].content["state"]["grant_kind"] == "fact"
    assert states[0].content["state"]["active"] is False
    with pytest.raises(StructuredSubmissionGrantRevokedError, match="revoked"):
        build_local_level2_runtime_binding(
            SimpleNamespace(
                storage_root=tmp_path / "memorii",
                hermes_home=tmp_path,
                session_id="session:two",
                user_id="raw:user:one",
                agent_identity="profile:primary",
                platform="cli",
                agent_context="primary",
                agent_workspace="hermes",
                parent_session_id=None,
            )
        )


def test_structured_tool_artifact_rejects_unknown_field_and_sidecar_refresh(tmp_path: Path) -> None:
    issued = datetime(2026, 9, 26, tzinfo=UTC)
    authorize_local_level2(hermes_home=tmp_path, now=issued)
    authorize_local_structured_tool(hermes_home=tmp_path, now=issued)
    path = tmp_path / "memorii" / "local-structured-tool.json"
    artifact = json.loads(path.read_text(encoding="utf-8"))
    artifact["unexpected"] = True
    path.write_text(json.dumps(artifact, sort_keys=True, separators=(",", ":")) + "\n", encoding="ascii")
    with pytest.raises(LocalLevel2AuthorityError, match="fields are invalid"):
        load_local_structured_tool_authority(hermes_home=tmp_path)

    authorize_local_structured_tool(hermes_home=tmp_path, now=issued)
    authorize_local_level2(hermes_home=tmp_path, now=issued + timedelta(seconds=1))
    with pytest.raises(LocalLevel2AuthorityError, match="bootstrap binding"):
        load_local_structured_tool_authority(hermes_home=tmp_path)


def test_inspection_summary_distinguishes_sources_graph_ledger_and_recall(tmp_path: Path) -> None:
    records = (
        CanonicalMemoryRecord(
            memory_id="source:1", domain=MemoryDomain.TRANSCRIPT, text="source",
            status=CommitStatus.COMMITTED, source_kind="semantic_ingestion_source",
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        ),
        CanonicalMemoryRecord(
            memory_id="graph:1", domain=MemoryDomain.SEMANTIC, text="graph",
            content={"member": {"kind": "claim_assertion"}}, status=CommitStatus.COMMITTED,
            source_kind="semantic_ingestion_bootstrap_graph_v3_member",
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        ),
        CanonicalMemoryRecord(
            memory_id="ledger:1", domain=MemoryDomain.SEMANTIC, text="ledger",
            status=CommitStatus.COMMITTED,
            source_kind="semantic_ingestion_observation_ledger_entry",
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        ),
        CanonicalMemoryRecord(
            memory_id="recall:1", domain=MemoryDomain.SEMANTIC, text="Mars Venus 001",
            content={"runtime_context_projection_kind": "bootstrap_v3_claim_assertion"},
            status=CommitStatus.COMMITTED, source_kind="semantic_projection",
            visibility=MemoryRecordVisibility.RUNTIME_CONTEXT,
        ),
    )

    summary = local_authority._inspection_summary(
        storage_root=tmp_path / "memorii" / "memory-plane", write_revision=8, records=records
    )

    assert summary["captured_source_count"] == 1
    assert summary["graph_record_count"] == 1
    assert summary["graph_record_counts_by_kind"] == {"claim_assertion": 1}
    assert summary["observation_ledger_entry_count"] == 1
    assert summary["retrieval_visible_record_count"] == 1
    assert summary["runtime_context_projection_count"] == 1


def test_status_maps_sidecar_filesystem_error_to_unavailable(tmp_path: Path) -> None:
    authority_root = tmp_path / "memorii"
    authority_root.mkdir()
    (authority_root / "installation-id").write_text("0" * 64 + "\n", encoding="ascii")
    (authority_root / "local-level2.json").mkdir()

    status = local_level2_status(hermes_home=tmp_path)

    assert status.available is False
    assert status.reason == "local Level 2 authority storage is unavailable"


def test_load_preserves_filesystem_cause_for_callers(tmp_path: Path) -> None:
    authority_root = tmp_path / "memorii"
    authority_root.mkdir()
    (authority_root / "installation-id").write_text("0" * 64 + "\n", encoding="ascii")
    (authority_root / "local-level2.json").mkdir()

    with pytest.raises(LocalLevel2AuthorityError, match="storage is unavailable") as error:
        load_local_level2_authority(hermes_home=tmp_path)

    assert isinstance(error.value.__cause__, OSError)


def test_first_install_stages_before_atomic_no_replace_publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    installation_path = tmp_path / "memorii" / "installation-id"

    def fail_link(_: Path, __: Path) -> None:
        raise OSError("injected link failure")

    monkeypatch.setattr(local_authority.os, "link", fail_link)
    with pytest.raises(OSError, match="injected link failure"):
        local_authority._atomic_write(installation_path, b"0" * 64 + b"\n", exclusive=True)

    assert not installation_path.exists()
    assert list(installation_path.parent.iterdir()) == []


def test_authorize_maps_write_side_storage_error_to_unavailable_with_cause(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_digests = {field: "a" * 64 for field in local_authority._PROFILE_DIGEST_FIELDS}

    def write_denied(_: Path, __: bytes, *, exclusive: bool = False) -> None:
        raise PermissionError("injected write denial")

    monkeypatch.setattr(local_authority, "_registered_profile_digests", lambda: profile_digests)
    monkeypatch.setattr(local_authority, "_atomic_write", write_denied)

    with pytest.raises(LocalLevel2AuthorityError, match="storage is unavailable") as error:
        authorize_local_level2(hermes_home=tmp_path)

    assert isinstance(error.value.__cause__, PermissionError)
    assert not (tmp_path / "memorii" / "local-level2.json").exists()


def test_load_rejects_profile_drift_before_a_factory_can_use_the_sidecar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorize_local_level2(hermes_home=tmp_path)
    monkeypatch.setattr(local_authority, "_registered_profile_digests", lambda: {
        field: "b" * 64 for field in local_authority._PROFILE_DIGEST_FIELDS
    })

    with pytest.raises(LocalLevel2AuthorityError, match=r"authorization .* is invalid"):
        load_local_level2_authority(hermes_home=tmp_path)
