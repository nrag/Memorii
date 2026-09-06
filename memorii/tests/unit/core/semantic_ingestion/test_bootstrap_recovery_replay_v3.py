"""Exact retained V3 replay reload proof for memory and JSONL backends."""

from __future__ import annotations

import pytest
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.semantic_ingestion.contracts import (
    ProviderEntityObject,
    ProviderFact,
    ProviderMention,
    ProviderSemanticProposal,
)
from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import (
    TEST_NOW,
    DeterministicTestHostBootstrapMaterialVerifier,
    _built_in_local_capability,
    _host_ingress,
    _v3_normalization_host_builder,
)


def _atlas_owner_proposal() -> ProviderSemanticProposal:
    """The complete V3 proposal used by graph-root success fixtures."""
    return ProviderSemanticProposal(
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
        facts=(ProviderFact(
            local_id="owner", predicate_id="owner_is",
            subject_entity_ref="atlas", object=ProviderEntityObject(entity_ref="bob"),
            assertion_quote="Atlas owner is Bob.", predicate_anchor_quote="owner",
            polarity="positive", commitment="asserted",
        ),),
        abstained=False,
    )

@pytest.mark.parametrize("durable", (False, True))
def test_reload_bootstrap_recovery_replay_v3_is_exact_and_rejects_foreign_key(
    tmp_path, durable: bool,
) -> None:
    builder, _calls = _v3_normalization_host_builder(proposal=_atlas_owner_proposal())
    plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(tmp_path / "plane") if durable else None
    )
    service = ProviderMemoryService(
        memory_plane=plane, now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=builder,
    )
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN, content="Atlas owner is Bob.",
        operation_id="replay-reload", task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    index = plane.list_records(
        source_kind="semantic_ingestion_bootstrap_v3_recovery_index"
    )[0]
    key = index.content["recovery_key_digest"]
    replay = service._semantic_atomic_store.reload_bootstrap_recovery_replay_v3(
        recovery_key_digest=key
    )
    assert replay is not None
    assert replay.recovery_key_digest == key
    assert replay.source_normalization_result.result_digest == index.content["result_digest"]
    assert service._semantic_atomic_store.reload_bootstrap_recovery_replay_v3(
        recovery_key_digest="0" * 64
    ) is None


@pytest.mark.parametrize("durable", (False, True))
def test_abstained_v3_proposal_remains_claimed_and_has_no_recovery_replay(
    tmp_path, durable: bool,
) -> None:
    """An abstained host proposal must not fabricate a graph recovery record."""
    builder, _calls = _v3_normalization_host_builder()
    plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(tmp_path / "plane") if durable else None
    )
    service = ProviderMemoryService(
        memory_plane=plane, now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=builder,
    )
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN, content="Atlas owner is Bob.",
        operation_id="replay-abstained", task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    index = plane.list_records(
        source_kind="semantic_ingestion_bootstrap_v3_recovery_index"
    )[0]
    assert index.content["state"] == "claimed"
    assert service._semantic_atomic_store.reload_bootstrap_recovery_replay_v3(
        recovery_key_digest=index.content["recovery_key_digest"]
    ) is None
