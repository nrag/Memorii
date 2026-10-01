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


def _counting_verifier(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Wrap the uncached verifier; the counter proves cache hits and misses."""
    import memorii.core.memory_evolution.observation_activation_runtime as runtime_module

    calls: list[int] = []
    real = runtime_module.verify_protected_typed_value_artifact_integrity

    def counting(*args: object, **kwargs: object) -> object:
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(runtime_module, "verify_protected_typed_value_artifact_integrity", counting)
    return calls


@pytest.fixture(autouse=True)
def _clear_proof_cache():
    from memorii.core.memory_evolution.observation_activation_runtime import _PROOF_CACHE

    _PROOF_CACHE.clear()
    yield
    _PROOF_CACHE.clear()


def test_repeated_validation_serves_one_verified_proof(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from memorii.core.memory_evolution.observation_activation_runtime import validate_registered_artifact

    calls = _counting_verifier(monkeypatch)
    history = _publication(tmp_path, schemas=("ObservationLedgerActivation",))
    emitted = emit_registered_observation_artifact(
        _activation(), schema_id="ObservationLedgerActivation", history=history,
        publication=history.publications[0],
    )
    first = validate_registered_artifact(
        emitted.raw, schema_id="ObservationLedgerActivation", history=history,
    )
    second = validate_registered_artifact(
        emitted.raw, schema_id="ObservationLedgerActivation", history=history,
    )
    third = validate_registered_artifact(
        emitted.raw, schema_id="ObservationLedgerActivation", history=history,
    )
    # Exactly one full verification (emission's); the three validations share it.
    assert sum(calls) == 1
    assert first == second == third


def test_cached_path_still_rejects_mutated_bytes_and_wrong_schema(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memorii.core.memory_evolution.observation_activation_runtime import validate_registered_artifact

    history = _publication(tmp_path, schemas=("ObservationLedgerActivation",))
    emitted = emit_registered_observation_artifact(
        _activation(), schema_id="ObservationLedgerActivation", history=history,
        publication=history.publications[0],
    )
    assert validate_registered_artifact(
        emitted.raw, schema_id="ObservationLedgerActivation", history=history,
    ) is not None
    calls = _counting_verifier(monkeypatch)
    tampered = emitted.raw[:-1] + bytes([emitted.raw[-1] ^ 1])
    with pytest.raises(Exception) as cached_reject:
        validate_registered_artifact(tampered, schema_id="ObservationLedgerActivation", history=history)
    with pytest.raises(ObservationActivationRuntimeError):
        validate_registered_artifact(
            emitted.raw, schema_id="ObservationLedgerHead", history=history,
        )
    assert sum(calls) >= 1
    assert cached_reject.value is not None


def test_history_change_misses_the_cache_and_reverifies(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memorii.core.memory_evolution.observation_activation_runtime import validate_registered_artifact

    calls = _counting_verifier(monkeypatch)
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first_history = _publication(tmp_path / "a", schemas=("ObservationLedgerActivation",))
    other_history = _publication(
        tmp_path / "b", schemas=("ObservationLedgerActivation", "ObservationLedgerHead"),
    )
    emitted = emit_registered_observation_artifact(
        _activation(), schema_id="ObservationLedgerActivation", history=first_history,
        publication=first_history.publications[0],
    )
    in_first = validate_registered_artifact(
        emitted.raw, schema_id="ObservationLedgerActivation", history=first_history,
    )
    in_other = validate_registered_artifact(
        emitted.raw, schema_id="ObservationLedgerActivation", history=other_history,
    )
    again_first = validate_registered_artifact(
        emitted.raw, schema_id="ObservationLedgerActivation", history=first_history,
    )
    # One verification for emission, one fresh verification for the different
    # publication chain (a miss by design); the repeat under the first chain
    # shares the emission proof. The compatible chain yields the same value.
    assert sum(calls) == 2
    assert in_first == in_other == again_first


def test_proof_cache_is_bounded(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from memorii.core.memory_evolution import observation_activation_runtime as runtime

    history = _publication(tmp_path, schemas=("ObservationLedgerActivation",))
    proofs = [object() for _ in range(2)]
    monkeypatch.setattr(
        runtime, "verify_protected_typed_value_artifact_integrity",
        lambda *args, **kwargs: proofs[0],
    )
    for index in range(runtime._PROOF_CACHE_ENTRIES + 25):
        runtime._verify_registered_artifact_proofed(
            f"raw-{index}".encode(), history=history, limits=runtime._LIMITS,
            verification_key=None,
        )
    assert len(runtime._PROOF_CACHE) == runtime._PROOF_CACHE_ENTRIES
    assert not any(key[0] == b"raw-0" for key in runtime._PROOF_CACHE)
    assert any(key[0] == f"raw-{runtime._PROOF_CACHE_ENTRIES + 24}".encode() for key in runtime._PROOF_CACHE)
