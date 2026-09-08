"""Read a captured baseline terminal through the current canonical store."""

from __future__ import annotations

import gzip
import json
from importlib.metadata import version
from pathlib import Path

import pytest
from memorii.core.memory_evolution import bootstrap_profile
from memorii.core.memory_evolution.atomic_store import PreplanningStoreError, SemanticIngestionAtomicStore
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore, _PersistedBatch
from memorii.core.provider.models import ProviderOperation
from memorii.core.semantic_ingestion.bootstrap_graph_host import BootstrapGraphHostBundleBuilder
from memorii.core.semantic_ingestion.contracts import (
    BootstrapGraphTerminalPublicationRequestV3,
    BootstrapGraphTerminalReloadV3,
    ProviderEntityObject,
    ProviderFact,
    ProviderMention,
    ProviderSemanticProposal,
    decode_semantic_contract,
)
from tests.fixtures.semantic_ingestion.bootstrap_graph_v3_fixture import (
    DeterministicBootstrapGraphAuthorityProviderV3,
)
from tests.unit.core.semantic_ingestion.bootstrap_graph_production_roots_support import (
    provider_service,
)
from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import (
    TEST_NOW,
    DeterministicTestHostBootstrapMaterialVerifier,
    _built_in_local_capability,
    _host_ingress,
    _v3_normalization_host_builder,
)

_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[3]
    / "fixtures/semantic_ingestion/historical_terminal"
)


def _fixture_bytes(filename: str) -> bytes:
    return gzip.decompress((_FIXTURE_ROOT / f"{filename}.gz").read_bytes())


def _rehydrated_historical_plane(tmp_path: Path) -> MemoryPlaneService:
    records = tuple(
        CanonicalMemoryRecord.model_validate(item)
        for item in json.loads(_fixture_bytes("memory-records.json").decode())
    )
    backend = JsonlMemoryPlaneStore(tmp_path / "historical-terminal")
    backend._replace_batches([
        _PersistedBatch.create(revision=1, data_revision=0, records=records),
    ])
    return MemoryPlaneService(record_store=backend)


def test_historical_terminal_reloads_from_captured_records_without_write(
    tmp_path: Path,
) -> None:
    request = decode_semantic_contract(
        _fixture_bytes("publication-request.ctv"),
        BootstrapGraphTerminalPublicationRequestV3,
    )
    expected = decode_semantic_contract(
        _fixture_bytes("terminal-reload.ctv"), BootstrapGraphTerminalReloadV3,
    )
    # Restore the immutable current-record snapshot through the backend's
    # batch rehydration path, rather than attempting an unauthorized write.
    plane = _rehydrated_historical_plane(tmp_path)
    writers = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest(),
    )
    atomic = SemanticIngestionAtomicStore(plane, writers)
    before = plane.read_snapshot()

    reload = atomic.reload_bootstrap_graph_terminal_by_request_v3(
        request=request.coordinator_request,
    )

    assert reload == expected
    assert reload is not None
    assert reload.terminal_member_schema_version == 1
    assert reload.source_finalization_observation_delta is None
    assert plane.read_snapshot() == before


@pytest.mark.parametrize("unique_distribution", [True, False])
def test_public_root_recovers_captured_v1_terminal_without_executor_or_audit_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, unique_distribution: bool,
) -> None:
    # Reconstruct the captured package inventory, retaining real version and
    # component-byte verification. Duplicate metadata exercises its rejection.
    assert version("memorii") == "0.1.0"
    monkeypatch.setattr(bootstrap_profile, "packages_distributions", lambda: {
        "memorii": ["memorii"] if unique_distribution else ["memorii", "memorii"],
    })
    plane = _rehydrated_historical_plane(tmp_path)
    proposal = ProviderSemanticProposal(
        mentions=(
            ProviderMention(
                local_id="atlas", mention_quote="Atlas",
                mention_context_quote="Atlas owner is Bob.",
            ),
            ProviderMention(
                local_id="bob", mention_quote="Bob",
                mention_context_quote="Atlas owner is Bob.",
            ),
        ),
        facts=(
            ProviderFact(
                local_id="owner", predicate_id="owner_is",
                subject_entity_ref="atlas", object=ProviderEntityObject(entity_ref="bob"),
                assertion_quote="Atlas owner is Bob.", predicate_anchor_quote="owner",
                polarity="positive", commitment="asserted",
            ),
        ),
        abstained=False,
    )
    normalization, lane_calls = _v3_normalization_host_builder(proposal=proposal)
    graph_calls: list[str] = []
    service = provider_service(
        memory_plane=plane,
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=normalization,
        bootstrap_graph_host_bundle_builder=BootstrapGraphHostBundleBuilder(
            authority_provider=DeterministicBootstrapGraphAuthorityProviderV3(
                successful_calls=graph_calls,
            ),
        ),
    )
    before = plane.read_snapshot()
    expected_verification = next(
        record.content["verification_digest"] for record in plane.list_records()
        if record.memory_id.endswith(":outcome") and "verification_digest" in record.content
    )
    assert service._bootstrap_profile is not None
    if not unique_distribution:
        assert service._bootstrap_profile.verification_digest != expected_verification
        with pytest.raises(PreplanningStoreError, match="admission evidence is partial or mismatched"):
            service.sync_event(
                operation=ProviderOperation.CHAT_USER_TURN,
                content="Atlas owner is Bob.", operation_id="graph-root-direct",
                task_id="task:one", user_id="user:alice",
                authenticated_host_ingress=_host_ingress(),
            )
        assert sum(lane_calls.values()) == 0
        assert graph_calls == []
        return
    assert service._bootstrap_profile.verification_digest == expected_verification

    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.", operation_id="graph-root-direct",
        task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )

    assert result.blocked_reasons["semantic_ingestion"] == "source_only"
    assert sum(lane_calls.values()) == 0
    assert graph_calls == []
    assert plane.read_snapshot() == before
    terminal = next(
        BootstrapGraphTerminalReloadV3.model_validate(record.content["reload"], strict=False)
        for record in plane.list_records(
            source_kind="semantic_ingestion_bootstrap_graph_v3_terminal_locator"
        )
        if record.content.get("semantic_ingestion_kind")
        == "bootstrap_graph_v3_terminal_locator"
    )
    assert terminal.terminal_member_schema_version == 1
    assert terminal.source_finalization_observation_delta is None
