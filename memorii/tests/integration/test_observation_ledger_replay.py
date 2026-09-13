"""Complete registered replay prefixes, independently of native store joins."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from memorii.core.memory_evolution.graph_effect_contracts import (
    CanonicalSourceTerminalOutcomeCore,
    CanonicalSourceTerminalOutcomeRecord,
    IngestionObservationDelta,
)
from memorii.core.memory_evolution.observation_activation_runtime import (
    emit_registered_observation_artifact,
    observation_successor_revision,
    registered_genesis_head_artifact,
    registered_semantic_payload,
    semantic_payload_digest,
)
from memorii.core.memory_evolution.observation_ledger_contracts import (
    ObservationGroupResultLocator,
    ObservationLedgerActivation,
    ObservationLedgerEntry,
    ObservationLedgerHead,
    ObservationSourceResultLocator,
)
from memorii.core.memory_evolution.observation_ledger_replay import (
    ObservationLedgerReplayError,
    replay_observation_ledger,
)
from memorii.core.memory_evolution.observation_persistence import build_source_finalization_observation_delta
from memorii.core.memory_evolution.observation_replay_contracts import ObservationReplayState
from memorii.core.memory_evolution.typed_value_artifact_integrity import TypedValueArtifactIntegrityError
from memorii.core.memory_evolution.typed_value_artifact_reader import ProtectedTypedValueArtifactReaderLimits
from memorii.core.memory_evolution.typed_value_body_validation import ProtectedTypedValueBodyLimits
from tests.unit.core.memory_evolution import test_typed_value_artifact_integrity as registry_fixture
from tests.unit.core.memory_evolution.test_observation_record_contracts import (
    _source_material,
    _source_terminal,
    _terminal_group_delta,
)


@pytest.fixture(scope="module")
def ledger(tmp_path_factory):
    schemas = set()
    def collect(schema):
        if schema in schemas:
            return
        schemas.add(schema)
        def visit(value):
            if isinstance(value, dict):
                if value.get("kind") == "model_ref":
                    collect(value["schema_id"])
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
        visit(json.loads((registry_fixture._ROOT / "schema" / schema / "1.json").read_text()))
    for schema in ("ObservationLedgerActivation", "ObservationLedgerHead", "ObservationLedgerEntry", "ObservationReplayState", "ObservationGroupSemanticPayload", "ObservationSourceSemanticPayload"):
        collect(schema)
    with pytest.MonkeyPatch.context() as patch:
        limits = registry_fixture._PUBLICATION_LIMITS
        patch.setattr(registry_fixture, "_PUBLICATION_LIMITS", replace(limits, decoder_source_limits=replace(limits.decoder_source_limits, maximum_files=len(schemas))))
        history = registry_fixture._publication(tmp_path_factory.mktemp("replay-publication"), tuple(sorted(schemas)))
    publication = history.publications[0]
    def emit(value):
        return emit_registered_observation_artifact(value, schema_id=type(value).__name__, history=history, publication=publication)
    activation_artifact = emit(ObservationLedgerActivation(
        schema_version=1, repository_id="repo", previous_writer_admission_digest="1" * 64,
        target_writer_epoch=1, writer_implementation_fingerprint="2" * 64,
        observation_schema_fingerprint="3" * 64, ledger_codec_fingerprint="4" * 64,
        legacy_terminal_inventory_digest="5" * 64, activation_digest="0" * 64,
    ))
    activation = activation_artifact.value
    genesis, genesis_raw = registered_genesis_head_artifact(activation, history=history, publication=publication)
    material = _source_material()
    group = _terminal_group_delta(material)
    group = IngestionObservationDelta.create(**{
        **group.model_dump(mode="python", exclude={"delta_digest"}),
        "observation_schema_fingerprint": activation.observation_schema_fingerprint,
    })
    def append(delta, head, locator, result_digest):
        payload = registered_semantic_payload(delta, history=history, publication=publication)
        commitment = semantic_payload_digest(payload, history=history, publication=publication)
        successor = observation_successor_revision(head, repository_id="repo", activation_digest=activation.activation_digest, payload_digest=commitment)
        assigned = type(delta).create(**{
            **delta.model_dump(mode="python", exclude={"delta_digest"}),
            "observation_revision_before": head.observation_revision,
            "observation_revision_after": successor,
        })
        entry = emit(ObservationLedgerEntry(
            schema_version=1, repository_id="repo", activation_digest=activation.activation_digest,
            sequence=head.sequence + 1, previous_entry_digest=head.last_entry_digest,
            semantic_payload_digest=commitment, delta=assigned, result_locator=locator,
            result_digest=result_digest, entry_digest="0" * 64,
        ))
        following = emit(ObservationLedgerHead(
            schema_version=1, repository_id="repo", activation_digest=activation.activation_digest,
            sequence=head.sequence + 1, observation_revision=successor,
            last_delta_id=assigned.observation_delta_id, last_delta_digest=assigned.delta_digest,
            last_entry_digest=entry.value.entry_digest, head_digest="0" * 64,
        ))
        return entry, following
    group_locator = ObservationGroupResultLocator(
        schema_version=1, kind="group_primary", immutable_record_id="group-result",
        source_id=group.source_id, source_digest=group.source_digest, source_operation_id="source-operation",
        operation_fence_id=group.operation_fence_id, transaction_group_id=group.transaction_group_id,
        operation_ids=group.operation_ids, request_ctv_digest="6" * 64,
    )
    group_entry, group_head = append(group, genesis, group_locator, "7" * 64)
    original = _source_terminal(material)
    core = CanonicalSourceTerminalOutcomeCore.create(**{
        **original.core.model_dump(mode="python", exclude={"core_digest"}),
        "group_result_digests": (group_entry.value.result_digest,),
    })
    outcome = CanonicalSourceTerminalOutcomeRecord.create(core=core, preparation_fingerprint=material.preparation_fingerprint)
    source = build_source_finalization_observation_delta(
        source_outcome=outcome, observation_delta_id="source-finalization",
        observation_revision_before="genesis", observation_revision_after="a" * 64,
        observation_schema_fingerprint=activation.observation_schema_fingerprint,
    )
    source_locator = ObservationSourceResultLocator(
        schema_version=1, kind="source_terminal", immutable_record_id="source-result",
        source_id=source.source_id, source_digest=source.source_digest, source_operation_id="source-operation",
        operation_fence_id=source.operation_fence_id, namespace_id="namespace", artifact_generation=1,
        member_id="source-result", publication_request_digest="8" * 64,
    )
    source_entry, source_head = append(source, group_head.value, source_locator, "9" * 64)
    arguments = dict(repository_id="repo", activation_digest=activation.activation_digest,
        activation_artifact=activation_artifact.raw, expected_head_artifact=source_head.raw,
        entry_artifacts=(group_entry.raw, source_entry.raw), history=history, publication=publication,
        limits=ProtectedTypedValueArtifactReaderLimits(2 * 1024 * 1024, 64_000, 32, ProtectedTypedValueBodyLimits(2 * 1024 * 1024, 64_000, 80)))
    return arguments, (group_entry, source_entry), (genesis_raw, group_head, source_head), emit, append


def test_complete_replay_requires_exact_head_and_all_immutable_joins(ledger):
    arguments, entries, heads, _, _ = ledger
    verified = []
    def join(entry):
        assert entry == entries[len(verified)].value
        verified.append(entry)
    replay = replay_observation_ledger(**arguments, verify_immutable_result=join)
    assert isinstance(replay.value, ObservationReplayState)
    assert replay.value.head == heads[-1].value
    assert len(replay.value.records) == 3
    assert len(verified) == 2
    def missing_join(entry):
        raise LookupError("immutable result missing")
    with pytest.raises(LookupError, match="immutable result missing"):
        replay_observation_ledger(**arguments, verify_immutable_result=missing_join)


@pytest.mark.parametrize("mutation", ["short", "extra", "reordered", "duplicate", "wrong-head", "wrong-activation"])
def test_replay_rejects_incomplete_or_substituted_authority(ledger, mutation):
    arguments, entries, heads, _, _ = ledger
    changed = dict(arguments)
    if mutation == "short":
        changed["entry_artifacts"] = (entries[0].raw,)
    elif mutation == "extra":
        changed["entry_artifacts"] = (*arguments["entry_artifacts"], entries[1].raw)
    elif mutation == "reordered":
        changed["entry_artifacts"] = tuple(reversed(arguments["entry_artifacts"]))
    elif mutation == "duplicate":
        changed["entry_artifacts"] = (entries[0].raw, entries[0].raw)
    elif mutation == "wrong-head":
        changed["expected_head_artifact"] = heads[1].raw
    else:
        changed["activation_digest"] = "a" * 64
    with pytest.raises(ObservationLedgerReplayError):
        replay_observation_ledger(**changed, verify_immutable_result=lambda entry: None)


def test_genesis_replay_does_not_manufacture_records_or_query_results(ledger):
    arguments, _, heads, _, _ = ledger
    def unexpected_join(entry):
        pytest.fail("genesis has no immutable result")
    replay = replay_observation_ledger(**{**arguments, "expected_head_artifact": heads[0], "entry_artifacts": ()}, verify_immutable_result=unexpected_join)
    assert replay.value.records == ()
    assert replay.value.entries == ()


def test_replay_rejects_validly_hashed_source_with_missing_group_membership(ledger):
    arguments, entries, heads, _, append = ledger
    source = entries[1].value.delta
    # The native model permits an operation-bearing source outcome in isolation;
    # complete replay additionally requires its preceding group receipt.
    genesis = ObservationLedgerHead(
        schema_version=1, repository_id="repo", activation_digest=arguments["activation_digest"], sequence=0,
        observation_revision="genesis", last_delta_id=None, last_delta_digest=None, last_entry_digest=None, head_digest="0" * 64,
    )
    entry, head = append(source, genesis, entries[1].value.result_locator, entries[1].value.result_digest)
    with pytest.raises(ObservationLedgerReplayError, match="finalization membership"):
        replay_observation_ledger(**{**arguments, "entry_artifacts": (entry.raw,), "expected_head_artifact": head.raw}, verify_immutable_result=lambda entry: None)


def test_zero_operation_source_replays_without_fabricated_group_and_cannot_finalize_twice(ledger):
    arguments, entries, _, _, append = ledger
    prior = entries[1].value.delta.source_outcome
    core = CanonicalSourceTerminalOutcomeCore.create(**{
        **prior.core.model_dump(mode="python", exclude={"core_digest"}),
        "operation_ids": (), "group_result_digests": (),
    })
    material = _source_material()
    outcome = CanonicalSourceTerminalOutcomeRecord.create(core=core, preparation_fingerprint=material.preparation_fingerprint)
    delta = build_source_finalization_observation_delta(
        source_outcome=outcome, observation_delta_id="empty-source-finalization",
        observation_revision_before="genesis", observation_revision_after="a" * 64,
        observation_schema_fingerprint=entries[1].value.delta.observation_schema_fingerprint,
    )
    genesis = ObservationLedgerHead(
        schema_version=1, repository_id="repo", activation_digest=arguments["activation_digest"], sequence=0,
        observation_revision="genesis", last_delta_id=None, last_delta_digest=None, last_entry_digest=None, head_digest="0" * 64,
    )
    entry, head = append(delta, genesis, entries[1].value.result_locator, "b" * 64)
    replay = replay_observation_ledger(**{**arguments, "entry_artifacts": (entry.raw,), "expected_head_artifact": head.raw}, verify_immutable_result=lambda entry: None)
    assert replay.value.records == (outcome,)
    duplicate, duplicate_head = append(delta, head.value, entry.value.result_locator, entry.value.result_digest)
    with pytest.raises(ObservationLedgerReplayError, match="entry chain"):
        replay_observation_ledger(**{**arguments, "entry_artifacts": (entry.raw, duplicate.raw), "expected_head_artifact": duplicate_head.raw}, verify_immutable_result=lambda entry: None)


@pytest.mark.parametrize("field", ["maximum_bytes", "maximum_nodes", "maximum_depth"])
def test_replay_honors_protected_resource_limits_before_result_lookup(ledger, field):
    arguments, _, _, _, _ = ledger
    limits = arguments["limits"]
    limited = replace(limits, body_limits=replace(limits.body_limits, **{field: 1}))
    def unexpected_join(entry):
        pytest.fail("invalid artifact must fail before result lookup")
    expected = ObservationLedgerReplayError if field == "maximum_nodes" else TypedValueArtifactIntegrityError
    with pytest.raises(expected):
        replay_observation_ledger(**{**arguments, "limits": limited}, verify_immutable_result=unexpected_join)


def test_replay_bounds_complete_prefix_before_decoding_entries(ledger):
    arguments, entries, _, _, _ = ledger
    limit = max(len(entry.raw) for entry in entries)
    def unexpected_join(entry):
        pytest.fail("oversized prefix must fail before result lookup")
    with pytest.raises(ObservationLedgerReplayError, match="prefix exceeds protected limits"):
        replay_observation_ledger(**{**arguments, "limits": replace(arguments["limits"], maximum_envelope_bytes=limit)}, verify_immutable_result=unexpected_join)
