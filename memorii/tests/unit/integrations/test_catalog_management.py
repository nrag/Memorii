"""Local standing catalog policy persistence and operator identity checks."""

import json

import pytest
from memorii.core.memory_plane import JsonlMemoryPlaneStore, MemoryPlaneService
from memorii.core.semantic_ingestion.catalog_authority import AgentLocalCatalogAuthorityScope
from memorii.core.semantic_ingestion.catalog_management import CatalogManagementRepository
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.integrations.hermes_local_authority import main


def test_policy_persists_and_retries(tmp_path):
    scope = AgentLocalCatalogAuthorityScope(principal_id="owner", agent_id="agent")

    def repository():
        return CatalogManagementRepository(
            MemoryPlaneService(record_store=JsonlMemoryPlaneStore(tmp_path)),
            partition_id="local:installation",
            scope=scope,
        )

    assert repository().status()["state"] == "disabled"
    assert repository().set_state("enabled")["generation"] == 1
    assert repository().set_state("enabled")["generation"] == 1
    assert repository().set_state("paused")["generation"] == 2
    assert repository().status() == {"state": "paused", "generation": 2, "origin": "local_operator"}


def test_concurrent_pause_refuses_stale_enable(tmp_path, monkeypatch):
    scope = AgentLocalCatalogAuthorityScope(principal_id="owner", agent_id="agent")
    store = JsonlMemoryPlaneStore(tmp_path)
    first_plane = MemoryPlaneService(record_store=store)
    first = CatalogManagementRepository(first_plane, partition_id="local:installation", scope=scope)
    second = CatalogManagementRepository(
        MemoryPlaneService(record_store=store), partition_id="local:installation", scope=scope,
    )
    write = first_plane.conditionally_write_records

    def pause_then_write(*args, **kwargs):
        assert second.set_state("paused")["generation"] == 1
        return write(*args, **kwargs)

    monkeypatch.setattr(first_plane, "conditionally_write_records", pause_then_write)
    with pytest.raises(ValueError, match="changed concurrently"):
        first.set_state("enabled")
    assert first.status()["state"] == "paused"


@pytest.mark.parametrize("managed", [False, True])
def test_local_operator_requires_exact_private_context(tmp_path, capsys, managed):
    root = tmp_path / "memorii"
    if managed:
        with StorageAdministrationService(root) as administration:
            administration.initialize()
    else:
        root.mkdir(mode=0o700)
        plane = root / "memory-plane"
        plane.mkdir()
        (plane / "memory_records.jsonl").touch()
    installation = "a" * 64
    (root / "installation-id").write_text(installation + "\n")
    (root / "installation-id").chmod(0o600)
    context = {
        "schema": "memorii.hermes.local-operator-context.v1",
        "installation_id": installation,
        "primary_agent_id": "memorii:hermes:agent:" + "b" * 64,
        "raw_user_consistency_digest": "c" * 64,
    }
    path = root / "local-operator-context.json"
    path.write_text(json.dumps(context))
    path.chmod(0o600)

    def invoke(command, *, expected_exit=0):
        assert main([command, "--hermes-home", str(tmp_path)]) == expected_exit
        return json.loads(capsys.readouterr().out)

    assert invoke("catalog-management-status")["state"] == "disabled"
    assert invoke("enable-local-catalog-management")["generation"] == 1
    assert invoke("catalog-management-status")["state"] == "enabled"
    assert invoke("pause-local-catalog-management")["generation"] == 2
    context["installation_id"] = "d" * 64
    path.write_text(json.dumps(context))
    assert invoke("enable-local-catalog-management", expected_exit=1)["available"] is False
