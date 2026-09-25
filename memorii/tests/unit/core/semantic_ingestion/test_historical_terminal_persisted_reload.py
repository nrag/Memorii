"""Read a captured baseline terminal through the current canonical store."""

from __future__ import annotations

import gzip
import json
from importlib.metadata import version
from pathlib import Path

import pytest
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionError,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore, _PersistedBatch
from memorii.core.provider.models import ProviderOperation
from memorii.core.semantic_ingestion.bootstrap_graph_host import BootstrapGraphHostBundleBuilder
from memorii.core.semantic_ingestion.contracts import (
    BootstrapGraphTerminalPublicationRequestV3,
    ProviderEntityObject,
    ProviderFact,
    ProviderMention,
    ProviderSemanticProposal,
    SemanticContractCodecError,
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


def test_pre_bootstrap_v3_terminal_fixture_is_rejected_without_write(
    tmp_path: Path,
) -> None:
    # The captured route uses the retired declared-language shape. Bootstrap V3
    # accepts only the current freeform authority and must leave storage intact.
    plane = _rehydrated_historical_plane(tmp_path)
    before = plane.read_snapshot()
    with pytest.raises(SemanticContractCodecError, match="validation failed"):
        decode_semantic_contract(
            _fixture_bytes("publication-request.ctv"),
            BootstrapGraphTerminalPublicationRequestV3,
        )
    assert plane.read_snapshot() == before


def test_public_root_requires_historical_writer_cutover_without_executor_or_write(
    tmp_path: Path,
) -> None:
    # Current Bootstrap V3 owns installed metadata verification internally.
    assert version("memorii") == "0.1.0"
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
    # The captured terminal predates the current Bootstrap V3 authority. It is
    # readable history, but its verification digest cannot authorize a writer.
    assert service._bootstrap_profile.verification_digest != expected_verification
    with pytest.raises(
        SemanticWriterAdmissionError, match="semantic writer manifest is mismatched"
    ):
        service.sync_event(
            operation=ProviderOperation.CHAT_USER_TURN,
            content="Atlas owner is Bob.", operation_id="graph-root-direct",
            task_id="task:one", user_id="user:alice",
            authenticated_host_ingress=_host_ingress(),
        )
    assert sum(lane_calls.values()) == 0
    assert graph_calls == []
    assert plane.read_snapshot() == before
