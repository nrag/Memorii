from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import TypedDict

import pytest
from memorii.core.provider.models import ProviderEvolutionOutcome

_FIXTURE_ROOT = Path(__file__).parents[3] / "fixtures" / "semantic_ingestion" / "provider_compatibility"


class Provenance(TypedDict):
    baseline_revision: str
    source_blob: str
    resolved_source_blob: str
    source_sha256: str
    capture_method: str
    model_path: str


class Corpus(TypedDict):
    provenance: Provenance
    json_schema: dict[str, object]
    valid_cases: dict[str, dict[str, object]]
    canonical_json_utf8: dict[str, str]
    invalid_cases: dict[str, dict[str, object]]
    enum_members: dict[str, list[str]]


def _mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise AssertionError(f"fixture {name} must be a string-keyed object")
    return value


def _string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise AssertionError(f"fixture {name} must be a string")
    return value


def _cases(value: object, name: str) -> dict[str, dict[str, object]]:
    return {key: _mapping(item, f"{name}.{key}") for key, item in _mapping(value, name).items()}


def _strings(value: object, name: str) -> dict[str, str]:
    return {key: _string(item, f"{name}.{key}") for key, item in _mapping(value, name).items()}


def _enum_members(value: object) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for key, item in _mapping(value, "enum_members").items():
        if not isinstance(item, list) or not all(isinstance(member, str) for member in item):
            raise AssertionError(f"fixture enum_members.{key} must be a list of strings")
        result[key] = item
    return result


def _corpus() -> Corpus:
    raw = _mapping(json.loads((_FIXTURE_ROOT / "provider_evolution_outcome.json").read_text(encoding="utf-8")), "root")
    provenance = _mapping(raw.get("provenance"), "provenance")
    return Corpus(
        provenance=Provenance(
            baseline_revision=_string(provenance.get("baseline_revision"), "provenance.baseline_revision"),
            source_blob=_string(provenance.get("source_blob"), "provenance.source_blob"),
            resolved_source_blob=_string(provenance.get("resolved_source_blob"), "provenance.resolved_source_blob"),
            source_sha256=_string(provenance.get("source_sha256"), "provenance.source_sha256"),
            capture_method=_string(provenance.get("capture_method"), "provenance.capture_method"),
            model_path=_string(provenance.get("model_path"), "provenance.model_path"),
        ),
        json_schema=_mapping(raw.get("json_schema"), "json_schema"),
        valid_cases=_cases(raw.get("valid_cases"), "valid_cases"),
        canonical_json_utf8=_strings(raw.get("canonical_json_utf8"), "canonical_json_utf8"),
        invalid_cases=_cases(raw.get("invalid_cases"), "invalid_cases"),
        enum_members=_enum_members(raw.get("enum_members")),
    )


def test_sia_t22_compat_fixture_provenance_and_baseline_bytes_are_immutable() -> None:
    corpus = _corpus()
    provenance = corpus["provenance"]
    assert provenance["baseline_revision"] == "f76850fc45f09d21a40b5a7302d173ce642ec9d6"
    assert provenance["source_blob"] == "307921e7648fcaf5e11244200a7fb3c1f402e817"
    assert provenance["resolved_source_blob"] == provenance["source_blob"]
    assert provenance["source_sha256"] == "38b80a29a991ebfb1076cccc437c2406d43da031982a6c8fe57f755e1e58dbbd"
    baseline_bytes = (_FIXTURE_ROOT / "ProviderEvolutionOutcome.baseline.py").read_bytes()
    assert sha256(baseline_bytes).hexdigest() == provenance["source_sha256"]


def test_sia_t22_compat_target_schema_equals_independently_captured_baseline() -> None:
    assert ProviderEvolutionOutcome.model_json_schema() == _corpus()["json_schema"]


def test_sia_t22_compat_target_serializes_exact_captured_canonical_bytes() -> None:
    corpus = _corpus()
    for name, payload in corpus["valid_cases"].items():
        actual = ProviderEvolutionOutcome.model_validate(payload).model_dump(mode="json", exclude_none=False)
        assert json.dumps(actual, ensure_ascii=False, separators=(",", ":")).encode("utf-8") == corpus[
            "canonical_json_utf8"
        ][name].encode("utf-8")


def test_sia_t22_compat_target_rejects_every_captured_invalid_baseline_case() -> None:
    for payload in _corpus()["invalid_cases"].values():
        with pytest.raises(ValueError):
            ProviderEvolutionOutcome.model_validate(payload)


def test_sia_t22_compat_captured_enum_members_are_preserved() -> None:
    schema = _corpus()["json_schema"]
    definitions = _mapping(schema.get("$defs"), "json_schema.$defs")
    for enum_name, expected_members in _corpus()["enum_members"].items():
        enum_schema = _mapping(definitions.get(enum_name), f"json_schema.$defs.{enum_name}")
        assert enum_schema["enum"] == expected_members
