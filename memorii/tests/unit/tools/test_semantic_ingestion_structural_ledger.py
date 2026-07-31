"""Focused CGS-04/05/06/11 primitives tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta  # type: ignore[attr-defined]
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from memorii.core.memory_evolution.ingestion_contracts import (
    CanonicalTypedValueError,
    CanonicalTypedValueProfileBinding,
    artifact_preimage,
    canonical_encoded_artifact_binding,
    decode_artifact,
    decode_legacy_artifact_diagnostic,
    decode_typed_value,
    encode_typed_value,
    serialize_artifact,
    serialize_legacy_artifact_diagnostic,
)
from memorii.tools.semantic_ingestion_structural_ledger import (
    FROZEN_LEDGER_SHA256,
    StructuralLedgerError,
    digest_raw_bytes,
    digest_typed_value,
    load_checked_in_frozen_structural_manifest_ledger,
    load_frozen_structural_manifest_ledger,
)

ROOT = Path(__file__).parents[4]
LEDGER = (
    ROOT / "docs/design/semantic_ingestion/traceability_golden_vectors/structural_manifest_derivation_ledger-v1.json"
)

EXPECTED_FIELDS = (
    ("grammar_revision", None),
    ("design_document_digest", "raw_design"),
    ("registry_source_identity", "raw_registry"),
    ("derivation_ledger_schema_id", None),
    ("derivation_ledger_schema_version", None),
    ("derivation_ledger_digest", "ledger"),
    ("derivation_ledger_coordinate", None),
    ("artifact_dag", None),
    ("artifact_dag_digest", "artifact_dag_root"),
    ("canonical_profile_binding", None),
    ("requirement_binding_registry_digest", "requirement_binding_root"),
    ("section_defaults", None),
    ("section_default_registry_digest", "section_default_root"),
    ("structural_mapping_rules", None),
    ("structural_mapping_rule_registry_digest", "structural_mapping_rule_root"),
    ("assertion_registry_artifact", None),
    ("assertion_registry_digest", "outer_envelope"),
    ("test_evidence_groups", None),
    ("test_evidence_group_registry_digest", "test_evidence_group_root"),
    ("report_schemas", None),
    ("report_schema_registry_digest", "report_schema_root"),
    ("runner_environment_profiles", None),
    ("runner_environment_profile_registry_digest", "runner_environment_profile_root"),
    ("units", None),
    ("entries", None),
    ("overrides", None),
    ("override_registry_digest", "override_root"),
    ("explicit_anchor_bindings", None),
    ("anchor_binding_registry_digest", "anchor_binding_root"),
)


def _binding() -> CanonicalTypedValueProfileBinding:
    return CanonicalTypedValueProfileBinding(
        "semantic_ingestion_typed_value",
        2,
        "c425fa6823f42fdd0d83ff444699bfd4c2b5fc9468812ff2b60c158a04ad254f",
        "NormativeTraceabilityStructuralManifestBody.v1",
        1,
        "5146322f2275c67dbe3ee2a290de128713023b3e3c969f8a50df6f732fe4c8e4",
    )


def test_frozen_ledger_identity_and_complete_ordered_field_contract() -> None:
    raw = LEDGER.read_bytes()
    assert sha256(raw).hexdigest() == FROZEN_LEDGER_SHA256
    ledger = load_checked_in_frozen_structural_manifest_ledger()
    assert tuple((field.name, field.digest_domain) for field in ledger.fields) == EXPECTED_FIELDS
    assert tuple(field.ordinal for field in ledger.fields) == tuple(range(1, 30))
    assert ledger.coordinate.endswith(ledger.digest)


@pytest.mark.parametrize("mutation", [b" ", b"\n\n", b"x"])
def test_stale_or_mutated_ledger_pin_fails_before_elaboration(mutation: bytes) -> None:
    with pytest.raises(StructuralLedgerError, match="identity_mismatch"):
        load_frozen_structural_manifest_ledger(LEDGER.read_bytes() + mutation)


def test_ledger_domains_use_declared_raw_and_typed_preimages() -> None:
    ledger = load_checked_in_frozen_structural_manifest_ledger()
    raw = b"raw-value"
    assert digest_raw_bytes(ledger, "raw_design", raw) == sha256(ledger.domain("raw_design") + raw).hexdigest()
    encoded = encode_typed_value(("x", 7))
    assert (
        digest_typed_value(ledger, "artifact_dag_root", ("x", 7))
        == sha256(ledger.domain("artifact_dag_root") + len(encoded).to_bytes(8, "big") + encoded).hexdigest()
    )
    assert digest_raw_bytes(ledger, "ledger", raw) != digest_raw_bytes(ledger, "raw_design", raw)


def test_ctv_nested_known_answer_preserves_the_v2_wire_representation() -> None:
    value = {
        "nested": [None, True, 3, b"\x00\xff", ("x", timedelta(microseconds=-2))],
        "when": datetime(2026, 7, 31, 12, 34, 56, 789, tzinfo=UTC),
        "set": {"z", 4, ("a", False)},
    }

    assert encode_typed_value(value) == (
        b'{"$type":"map","entries":[["nested",{"$type":"list","items":'
        b'[null,true,{"$type":"integer","value":"3"},{"$type":"bytes",'
        b'"value":"AP8="},{"$type":"tuple","items":["x",{"$type":'
        b'"duration_microseconds","value":"-2"}]}]}],["set",{"$type":"set",'
        b'"items":["z",{"$type":"integer","value":"4"},{"$type":"tuple",'
        b'"items":["a",false]}]}],["when",{"$type":"datetime",'
        b'"value":"2026-07-31T12:34:56.000789Z"}]]}'
    )


def test_large_design_manifest_matches_the_independent_byte_rebuild() -> None:
    from memorii.tools.semantic_ingestion_traceability_checker import rebuild_structural_manifest_bytes
    from memorii.tools.semantic_ingestion_traceability_manifest import build_structural_manifest
    from memorii.tools.semantic_ingestion_traceability_registry import load_registry

    design_path = ROOT / "docs/design/semantic_ingestion_architecture.md"
    registry_path = ROOT / "docs/design/semantic_ingestion/traceability_registry/registry-v1.json"
    design = design_path.read_bytes()
    assert len(design) > 1_000_000
    registry = load_registry(registry_path)

    manifest = build_structural_manifest(design_bytes=design, registry=registry)
    independent = rebuild_structural_manifest_bytes(
        design_bytes=design,
        registry=registry,
        registry_bytes=registry_path.read_bytes(),
    )

    assert manifest.canonical_bytes == independent


def test_structural_body_shape_rejects_missing_extra_and_reordered_fields() -> None:
    ledger = load_checked_in_frozen_structural_manifest_ledger()
    body: dict[str, Any] = {name: None for name, _ in EXPECTED_FIELDS}
    body.update(
        {
            "grammar_revision": ledger.grammar_revision,
            "derivation_ledger_schema_id": ledger.schema_id,
            "derivation_ledger_schema_version": ledger.schema_version,
            "derivation_ledger_digest": ledger.digest,
            "derivation_ledger_coordinate": ledger.coordinate,
        }
    )
    ledger.validate_body_shape(body)
    for changed in (
        {key: value for key, value in list(body.items())[1:]},
        {**body, "unexpected": None},
        dict(reversed(tuple(body.items()))),
    ):
        with pytest.raises(StructuralLedgerError, match="field_order_or_shape"):
            ledger.validate_body_shape(changed)


def test_ctv_outer_envelope_is_double_encoded_and_legacy_cannot_enter_registered_reader() -> None:
    binding = _binding()
    raw = serialize_artifact({"body": "value"}, binding)
    # The transport is a CTV model: its bytes begin with the map tag rather
    # than the retired JSON/base64 wrapper, and the inner body remains bytes.
    assert raw.startswith(b'{"$type":"map"')
    artifact = decode_artifact(raw, expected_binding=binding)
    assert artifact.binding == binding
    assert artifact.canonical_value_digest != artifact.artifact_digest
    outer = canonical_encoded_artifact_binding()
    assert outer.schema_id == "CanonicalEncodedArtifact.v1"
    legacy = serialize_legacy_artifact_diagnostic({"body": "value"}, binding)
    with pytest.raises(CanonicalTypedValueError):
        decode_artifact(legacy, expected_binding=binding)
    assert decode_legacy_artifact_diagnostic(legacy, expected_binding=binding) == artifact


def _lp(*parts: bytes) -> bytes:
    return b"".join(len(part).to_bytes(8, "big") + part for part in parts)


def test_artifact_preimage_matches_independent_outer_envelope_known_answer() -> None:
    ledger = load_checked_in_frozen_structural_manifest_ledger()
    binding = _binding()
    body = encode_typed_value({"body": "value"})
    operands = (
        ledger.domain("outer_envelope"),
        binding.profile_id.encode(),
        str(binding.profile_version).encode(),
        binding.profile_digest.encode(),
        binding.schema_id.encode(),
        str(binding.schema_version).encode(),
        binding.binding_digest.encode(),
        body,
    )
    expected = _lp(*operands)
    assert artifact_preimage(binding, body) == expected
    assert sha256(body).hexdigest() != sha256(expected).hexdigest()
    for index, operand in enumerate(operands):
        changed = list(operands)
        changed[index] = operand + b"x"
        assert _lp(*changed) != expected

    # A self-consistent digest made with another domain is still not an
    # artifact under the registered outer-envelope contract.
    raw = serialize_artifact({"body": "value"}, binding)
    outer = decode_typed_value(raw)
    assert isinstance(outer, dict)
    wrong = list(operands)
    wrong[0] = ledger.domain("structural_body")
    outer["artifact_digest"] = sha256(_lp(*wrong)).hexdigest()
    with pytest.raises(CanonicalTypedValueError, match="digest_mismatch"):
        decode_artifact(encode_typed_value(outer), expected_binding=binding)

    wrong_binding = replace(binding, binding_digest="0" * 64)
    wrong_raw = serialize_artifact({"body": "value"}, wrong_binding)
    with pytest.raises(CanonicalTypedValueError, match="binding_mismatch"):
        decode_artifact(wrong_raw, expected_binding=binding)


def test_every_frozen_digest_domain_uses_its_declared_exact_bytes() -> None:
    ledger = load_checked_in_frozen_structural_manifest_ledger()
    raw = b"domain-fixture"
    typed = ("domain-fixture", 7)
    typed_bytes = encode_typed_value(typed)
    domain_ids = tuple(ledger.digest_domains)
    assert len(domain_ids) == 16
    for domain_id in domain_ids:
        domain = ledger.domain(domain_id)
        if domain_id in {"raw_design", "raw_registry"}:
            actual = digest_raw_bytes(ledger, domain_id, raw)
            expected = sha256(domain + raw).hexdigest()
        elif domain_id == "ledger":
            actual = digest_raw_bytes(ledger, domain_id, raw)
            expected = sha256(domain + len(raw).to_bytes(8, "big") + raw).hexdigest()
        elif domain_id == "outer_envelope":
            binding = _binding()
            preimage = artifact_preimage(binding, raw)
            expected = sha256(preimage).hexdigest()
            actual = expected
        else:
            actual = digest_typed_value(ledger, domain_id, typed)
            expected = sha256(domain + len(typed_bytes).to_bytes(8, "big") + typed_bytes).hexdigest()
        assert actual == expected
        alternate = next(candidate for candidate in domain_ids if candidate != domain_id)
        if domain_id in {"raw_design", "raw_registry"}:
            swapped = sha256(ledger.domain(alternate) + raw).hexdigest()
        elif domain_id == "ledger":
            swapped = sha256(ledger.domain(alternate) + len(raw).to_bytes(8, "big") + raw).hexdigest()
        elif domain_id == "outer_envelope":
            binding = _binding()
            swapped = sha256(
                _lp(
                    ledger.domain(alternate), binding.profile_id.encode(),
                    str(binding.profile_version).encode(), binding.profile_digest.encode(),
                    binding.schema_id.encode(), str(binding.schema_version).encode(),
                    binding.binding_digest.encode(), raw,
                )
            ).hexdigest()
        else:
            swapped = sha256(
                ledger.domain(alternate) + len(typed_bytes).to_bytes(8, "big") + typed_bytes
            ).hexdigest()
        assert swapped != actual

    with pytest.raises(StructuralLedgerError, match="domain_unknown"):
        ledger.domain("not_registered")
    with pytest.raises(StructuralLedgerError, match="operand_invalid"):
        digest_raw_bytes(ledger, "outer_envelope", raw)
    with pytest.raises(StructuralLedgerError, match="operand_invalid"):
        digest_typed_value(ledger, "raw_design", typed)
