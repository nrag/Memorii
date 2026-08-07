from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[4]
_ARTIFACT = _ROOT / "docs/design/equal_version_replay_decision-v1.json"
_VALIDATOR = _ROOT / "docs/design/validate_equal_version_replay_decision.py"


def _validator_module():
    spec = importlib.util.spec_from_file_location("equal_version_replay_decision_validator", _VALIDATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _artifact() -> dict[str, object]:
    return json.loads(_ARTIFACT.read_text(encoding="utf-8"))


def _write(tmp_path: Path, value: object) -> Path:
    path = tmp_path / "decision.json"
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return path


def _validate(path: Path) -> None:
    _validator_module().validate(artifact_path=path, repository_root=_ROOT)


def _with_recomputed_digest(value: dict[str, object]) -> dict[str, object]:
    value["decision_digest"] = _validator_module()._decision_digest(value)
    return value


def test_pristine_equal_version_replay_decision_passes() -> None:
    _validate(_ARTIFACT)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"decision":"one","decision":"two"}',
        b'{"bound_documents":{"docs/design/event_model.md":"a","docs/design/event_model.md":"b"}}',
    ],
)
def test_duplicate_json_keys_reject_before_semantic_validation(tmp_path: Path, raw: bytes) -> None:
    artifact = tmp_path / "duplicate.json"
    artifact.write_bytes(raw)
    with pytest.raises(ValueError, match="duplicate key"):
        _validate(artifact)


@pytest.mark.parametrize(
    "field",
    [
        "approved_on",
        "approved_owner",
        "checkpoint_rule",
        "decision",
        "duplicate_rule",
        "format",
        "ordering_authority",
        "recovery_rule",
        "visibility_rule",
    ],
)
def test_each_normative_field_is_frozen(tmp_path: Path, field: str) -> None:
    value = _artifact()
    value[field] = "mutated"
    with pytest.raises(ValueError):
        _validate(_write(tmp_path, value))


def test_evidence_members_and_order_are_frozen(tmp_path: Path) -> None:
    value = _artifact()
    evidence = value["required_evidence_families"]
    assert isinstance(evidence, list)
    value["required_evidence_families"] = [*reversed(evidence)]
    with pytest.raises(ValueError):
        _validate(_write(tmp_path, value))
    value = _artifact()
    value["required_evidence_families"] = value["required_evidence_families"][:-1]  # type: ignore[index]
    with pytest.raises(ValueError):
        _validate(_write(tmp_path, value))


@pytest.mark.parametrize("mutation", ["path", "digest"])
def test_document_binding_path_and_digest_are_frozen(tmp_path: Path, mutation: str) -> None:
    value = _artifact()
    documents = copy.deepcopy(value["bound_documents"])
    assert isinstance(documents, dict)
    path, digest = next(iter(documents.items()))
    del documents[path]
    documents["docs/design/not-bound.md" if mutation == "path" else path] = digest if mutation == "path" else "0" * 64
    value["bound_documents"] = documents
    with pytest.raises(ValueError):
        _validate(_write(tmp_path, value))


def test_digest_key_and_value_and_schema_shape_are_frozen(tmp_path: Path) -> None:
    value = _artifact()
    value["decision_digest"] = "0" * 64
    with pytest.raises(ValueError):
        _validate(_write(tmp_path, value))
    value = _artifact()
    del value["approved_on"]
    with pytest.raises(ValueError):
        _validate(_write(tmp_path, value))
    value = _artifact()
    value["unexpected"] = True
    with pytest.raises(ValueError):
        _validate(_write(tmp_path, value))
    value = _artifact()
    value["approved_on"] = 20260802
    with pytest.raises(ValueError):
        _validate(_write(tmp_path, value))


@pytest.mark.parametrize(
    "field,wrong_value",
    [
        ("approved_on", 20260802),
        ("approved_owner", []),
        ("checkpoint_rule", {}),
        ("decision", False),
        ("duplicate_rule", 1),
        ("format", None),
        ("ordering_authority", []),
        ("recovery_rule", {}),
        ("visibility_rule", False),
        ("required_evidence_families", "arrival_order"),
        ("bound_documents", []),
    ],
)
def test_every_closed_value_family_rejects_wrong_types_before_digest_validation(
    tmp_path: Path, field: str, wrong_value: object
) -> None:
    value = _artifact()
    value[field] = wrong_value
    # A matching outer digest proves rejection comes from the closed field
    # contract rather than merely from a stale decision digest.
    _with_recomputed_digest(value)
    with pytest.raises(ValueError):
        _validate(_write(tmp_path, value))


@pytest.mark.parametrize("wrong_digest", [0, [], {}])
def test_nested_document_digest_and_decision_digest_reject_wrong_types(tmp_path: Path, wrong_digest: object) -> None:
    value = _artifact()
    documents = copy.deepcopy(value["bound_documents"])
    assert isinstance(documents, dict)
    path = next(iter(documents))
    documents[path] = wrong_digest
    value["bound_documents"] = documents
    _with_recomputed_digest(value)
    with pytest.raises(ValueError):
        _validate(_write(tmp_path, value))
    value = _artifact()
    value["decision_digest"] = wrong_digest
    with pytest.raises(ValueError):
        _validate(_write(tmp_path, value))
