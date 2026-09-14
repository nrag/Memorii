from __future__ import annotations

from hashlib import sha256

import pytest
from memorii.core.memory_evolution.observation_activation_runtime import (
    ObservationActivationRuntimeError,
    emit_registered_observation_artifact,
    observation_successor_revision,
)
from memorii.core.memory_evolution.observation_ledger_contracts import (
    ObservationLedgerActivation,
    ObservationLedgerHead,
)
from pydantic import ValidationError
from tests.unit.core.memory_evolution.test_typed_value_artifact_integrity import _publication


def _activation() -> ObservationLedgerActivation:
    return ObservationLedgerActivation(
        schema_version=1, repository_id="repo", previous_writer_admission_digest="1" * 64,
        target_writer_epoch=1, writer_implementation_fingerprint="2" * 64,
        observation_schema_fingerprint="3" * 64, ledger_codec_fingerprint="4" * 64,
        legacy_terminal_inventory_digest="5" * 64, activation_digest="0" * 64,
    )


def test_emission_uses_selected_real_publication_and_self_digest(tmp_path) -> None:
    history = _publication(tmp_path, schemas=("ObservationLedgerActivation",))
    emitted = emit_registered_observation_artifact(
        _activation(), schema_id="ObservationLedgerActivation", history=history,
        publication=history.publications[0],
    )
    assert emitted.value.activation_digest != "0" * 64
    assert emitted.canonical_value_digest == sha256(emitted.canonical_value_bytes).hexdigest()


def test_successor_uses_exact_lp5_bytes() -> None:
    head = ObservationLedgerHead(
        schema_version=1, repository_id="repo", activation_digest="a" * 64, sequence=0,
        observation_revision="genesis", last_delta_id=None, last_delta_digest=None,
        last_entry_digest=None, head_digest="b" * 64,
    )
    expected = sha256(b"".join(
        len(part).to_bytes(8, "big") + part for part in (
            b"memorii.observation-ledger.revision.v1", b"repo", b"a" * 64,
            b"genesis", b"c" * 64,
        )
    )).hexdigest()
    assert observation_successor_revision(
        head, repository_id="repo", activation_digest="a" * 64, payload_digest="c" * 64,
    ) == expected


def test_emitter_rejects_model_and_digest_substitution(tmp_path) -> None:
    history = _publication(tmp_path, schemas=("ObservationLedgerActivation",))
    with pytest.raises(ObservationActivationRuntimeError):
        emit_registered_observation_artifact(
            _activation(), schema_id="ObservationLedgerHead", history=history,
            publication=history.publications[0],
        )
    head = ObservationLedgerHead(
        schema_version=1, repository_id="repo", activation_digest="a" * 64, sequence=0,
        observation_revision="genesis", last_delta_id=None, last_delta_digest=None,
        last_entry_digest=None, head_digest="b" * 64,
    )
    with pytest.raises(ObservationActivationRuntimeError):
        observation_successor_revision(
            head, repository_id="repo", activation_digest="a" * 64, payload_digest="C" * 64,
        )


def test_source_payload_preserves_native_delta_and_commits_complete_binding(tmp_path, monkeypatch):
    import json
    from dataclasses import replace

    from memorii.core.memory_evolution.observation_activation_runtime import (
        registered_semantic_payload,
        semantic_payload_digest,
    )
    from memorii.core.memory_evolution.observation_persistence import build_source_finalization_observation_delta
    from tests.unit.core.memory_evolution.test_observation_record_contracts import _source_material, _source_terminal
    from tests.unit.core.memory_evolution.test_typed_value_artifact_integrity import _ROOT

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
        visit(json.loads((_ROOT / "schema" / schema / "1.json").read_text()))
    for schema in ("ObservationSourceSemanticPayload", "SourceFinalizationObservationDelta"):
        collect(schema)
    from tests.unit.core.memory_evolution import test_typed_value_artifact_integrity as fixture
    limits = fixture._PUBLICATION_LIMITS
    monkeypatch.setattr(fixture, "_PUBLICATION_LIMITS", replace(limits, decoder_source_limits=replace(limits.decoder_source_limits, maximum_files=len(schemas))))
    history = _publication(tmp_path, schemas=tuple(sorted(schemas)))
    publication = history.publications[0]
    delta = build_source_finalization_observation_delta(
        source_outcome=_source_terminal(_source_material()),
        observation_delta_id="source-finalization", observation_revision_before="genesis",
        observation_revision_after="a" * 64, observation_schema_fingerprint="b" * 64,
    )
    ordinary = emit_registered_observation_artifact(delta, schema_id="SourceFinalizationObservationDelta", history=history, publication=publication)
    assert ordinary.value == delta
    payload = registered_semantic_payload(delta, history=history, publication=publication)
    binding = payload.binding
    parts = [b"memorii.observation-ledger.semantic-payload.v1", binding.profile_id.encode(),
             str(binding.profile_version).encode(), binding.profile_digest.encode(),
             binding.schema_id.encode(), str(binding.schema_version).encode(),
             binding.binding_digest.encode(), payload.canonical_value_bytes]
    expected = sha256(b"".join(len(part).to_bytes(8, "big") + part for part in parts)).hexdigest()
    assert semantic_payload_digest(payload, history=history, publication=publication) == expected
    reassigned = build_source_finalization_observation_delta(
        source_outcome=delta.source_outcome, observation_delta_id=delta.observation_delta_id,
        observation_revision_before="d" * 64, observation_revision_after="e" * 64,
        observation_schema_fingerprint=delta.observation_schema_fingerprint,
    )
    assert semantic_payload_digest(registered_semantic_payload(reassigned, history=history, publication=publication), history=history, publication=publication) == expected
    changed = build_source_finalization_observation_delta(
        source_outcome=delta.source_outcome, observation_delta_id=delta.observation_delta_id,
        observation_revision_before="genesis", observation_revision_after="a" * 64,
        observation_schema_fingerprint="c" * 64,
    )
    assert semantic_payload_digest(registered_semantic_payload(changed, history=history, publication=publication), history=history, publication=publication) != expected

    for field in ("profile_id", "profile_version", "profile_digest", "schema_id", "schema_version", "binding_digest"):
        old = getattr(binding, field)
        changed = old + 1 if isinstance(old, int) else "changed"
        with pytest.raises((ObservationActivationRuntimeError, ValueError)):
            semantic_payload_digest(replace(payload, binding=replace(binding, **{field: changed})), history=history, publication=publication)
    with pytest.raises(ObservationActivationRuntimeError):
        semantic_payload_digest(replace(payload, canonical_value_bytes=payload.canonical_value_bytes + b" "), history=history, publication=publication)
    with pytest.raises(ObservationActivationRuntimeError):
        emit_registered_observation_artifact(delta, schema_id="ObservationSourceSemanticPayload", history=history, publication=publication)


@pytest.mark.parametrize("predecessor", ["predecessor", "révision:α"])
def test_successor_preserves_identifier_utf8_and_binds_protected_coordinates(predecessor):
    head = ObservationLedgerHead(schema_version=1, repository_id="repo", activation_digest="a" * 64,
        sequence=1, observation_revision=predecessor, last_delta_id="delta", last_delta_digest="b" * 64,
        last_entry_digest="c" * 64, head_digest="d" * 64)
    parts = [b"memorii.observation-ledger.revision.v1", b"repo", b"a" * 64, predecessor.encode("utf-8"), b"e" * 64]
    expected = sha256(b"".join(len(part).to_bytes(8, "big") + part for part in parts)).hexdigest()
    assert observation_successor_revision(head, repository_id="repo", activation_digest="a" * 64, payload_digest="e" * 64) == expected
    with pytest.raises(ObservationActivationRuntimeError):
        observation_successor_revision(head, repository_id="other", activation_digest="a" * 64, payload_digest="e" * 64)
    with pytest.raises(ObservationActivationRuntimeError):
        observation_successor_revision(head, repository_id="repo", activation_digest="b" * 64, payload_digest="e" * 64)
    with pytest.raises(ValidationError, match="string_unicode"):
        observation_successor_revision(head.model_copy(update={"observation_revision": chr(0xD800)}), repository_id="repo", activation_digest="a" * 64, payload_digest="e" * 64)


def test_emission_rejects_a_publication_outside_protected_history(tmp_path):
    first = tmp_path / "selected"
    other = tmp_path / "other"
    first.mkdir()
    other.mkdir()
    history = _publication(first, schemas=("ObservationLedgerActivation",))
    other_publication = _publication(other, schemas=("ObservationLedgerHead",)).publications[0]
    with pytest.raises(ObservationActivationRuntimeError):
        emit_registered_observation_artifact(_activation(), schema_id="ObservationLedgerActivation", history=history, publication=other_publication)
