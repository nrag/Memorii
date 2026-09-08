"""New intent grammar preserves captured terminal encodings and binds receipts."""
from __future__ import annotations

import pytest
from memorii.core.memory_evolution.observation_ledger_contracts import SourceObservationIntent
from memorii.core.memory_evolution.observation_persistence import build_source_finalization_observation_delta
from memorii.core.semantic_ingestion.contracts import (
    BootstrapGraphTerminalMemberIntentV3,
    BootstrapGraphTerminalPersistenceHandoffV3,
    BootstrapGraphTerminalPublicationIntentV3,
    BootstrapGraphTerminalPublicationRequestV3,
    BootstrapGraphTerminalReloadV3,
    decode_semantic_contract,
    encode_semantic_contract,
    rebuild_bootstrap_graph_effect_contracts,
)
from tests.unit.core.semantic_ingestion.test_historical_terminal_persisted_reload import _fixture_bytes


def _fields(value, exclude):
    return {name: getattr(value, name) for name in value._canonical_contract_field_names() if name not in exclude}


def _request(version: int):
    rebuild_bootstrap_graph_effect_contracts()
    old = decode_semantic_contract(_fixture_bytes("publication-request.ctv"), BootstrapGraphTerminalPublicationRequestV3)
    source = old.canonical_source_result_input.completed_canonical_source_result
    intent = SourceObservationIntent(kind="source_finalization", source_outcome=source, observation_schema_fingerprint="a" * 64, intent_digest="b" * 64)
    delta = build_source_finalization_observation_delta(source_outcome=source, observation_delta_id="source-finalization", observation_revision_before="genesis", observation_revision_after="c" * 64, observation_schema_fingerprint="a" * 64)
    members = (*old.publication_intent.member_intents, BootstrapGraphTerminalMemberIntentV3.create(
        kind="source_observation_intent" if version == 3 else "bootstrap_graph_source_finalization_observation_delta",
        member_id="source-finalization-observation", construction_input_digest=intent.intent_digest if version == 3 else delta.delta_digest,
    ))
    publication = BootstrapGraphTerminalPublicationIntentV3.create(**{
        **old.publication_intent.model_dump(mode="python", exclude={"intent_digest", "locator_digest"}),
        "terminal_member_schema_version": version, "member_intents": members,
    })
    handoff = BootstrapGraphTerminalPersistenceHandoffV3.create(core=old.handoff.core, publication_intent=publication)
    values = _fields(old, {"publication_request_digest", "schema_version"})
    values.update(publication_intent=publication, handoff=handoff)
    values.update({"source_observation_intent": intent} if version == 3 else {"source_finalization_observation_delta": delta})
    return BootstrapGraphTerminalPublicationRequestV3.create(**values), delta


@pytest.mark.parametrize("version", [2, 3])
def test_versioned_terminal_request_roundtrips_and_omits_other_source_grammar(version):
    request, _ = _request(version)
    assert decode_semantic_contract(encode_semantic_contract(request), type(request)) == request
    body = request.model_dump(mode="python")
    absent = "source_finalization_observation_delta" if version == 3 else "source_observation_intent"
    assert absent not in body
    with pytest.raises(ValueError):
        BootstrapGraphTerminalPublicationRequestV3.model_validate({
            **body, "publication_request_digest": "0" * 64,
        })


def test_terminal_intent_rejects_preassigned_delta_and_missing_ledger_receipt():
    request, delta = _request(3)
    with pytest.raises(ValueError):
        BootstrapGraphTerminalPublicationRequestV3.create(**{
            **_fields(request, {"publication_request_digest", "schema_version"}),
            "source_finalization_observation_delta": delta,
        })
    old = decode_semantic_contract(_fixture_bytes("terminal-reload.ctv"), BootstrapGraphTerminalReloadV3)
    body = {**_fields(old, {"reload_digest", "schema_version"}), "terminal_member_schema_version": 3, "source_finalization_observation_delta": delta}
    with pytest.raises(ValueError):
        BootstrapGraphTerminalReloadV3.create(**body)
    receipt = BootstrapGraphTerminalReloadV3.create(**body, ledger_entry_id="ledger-entry", ledger_entry_digest="d" * 64)
    assert decode_semantic_contract(encode_semantic_contract(receipt), type(receipt)) == receipt
    for field in ("ledger_entry_id", "ledger_entry_digest"):
        with pytest.raises(ValueError):
            BootstrapGraphTerminalReloadV3.create(**{**_fields(receipt, {"reload_digest", "schema_version"}), field: None})
