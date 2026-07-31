from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from memorii.tools.semantic_ingestion_acceptance_watermark_store import (
    FileTraceabilityReleaseWatermarkStore,
    WatermarkAdvanced,
    WatermarkRejected,
)
from memorii.tools.semantic_ingestion_traceability_checker import (
    TraceabilityCoverageError,
    load_independent_registry_bytes,
    rebuild_structural_manifest_bytes,
)
from memorii.tools.semantic_ingestion_traceability_manifest import (
    StructuralManifestError,
    build_structural_manifest,
)
from memorii.tools.semantic_ingestion_traceability_registry import (
    RegistryValidationError,
    canonical_document,
    load_registry,
    load_registry_bytes,
)
from memorii.tools.semantic_ingestion_traceability_release import (
    TraceabilityGateAuthorized,
    TraceabilityGateRejected,
    TraceabilityGateUnavailable,
    VerifierHeldTrustMaterial,
    verify_active_release_pointer,
    verify_release_gate,
)


def _registry_path() -> Path:
    return Path(__file__).parents[4] / "docs" / "design" / "semantic_ingestion" / "traceability_registry" / "registry-v1.json"


def _signature(profile: str, key: str, payload: bytes) -> bytes:
    """A deterministic independent verifier, never a permissive test callback."""
    return sha256(b"memorii:test-verifier:v1\0" + profile.encode() + b"\0" + key.encode() + b"\0" + payload).digest()


def _verifier(profile: str, key: str, payload: bytes, signature: bytes) -> bool:
    return signature == _signature(profile, key, payload)


class _TestWatermarkStore:
    """Test-only protocol fake; production must receive a durable adapter."""

    def __init__(self, epoch: int = 0, sequence: int = 0, release_digest: str | None = None) -> None:
        self.epoch, self.sequence, self.release_digest = epoch, sequence, release_digest

    def provision(self, epoch: int, sequence: int, release_digest: str) -> WatermarkAdvanced | WatermarkRejected:
        if (self.epoch, self.sequence, self.release_digest) in {(0, 0, None), (epoch, sequence, release_digest)}:
            self.epoch, self.sequence, self.release_digest = epoch, sequence, release_digest
            return WatermarkAdvanced()
        return WatermarkRejected("watermark_already_provisioned")

    def compare_and_advance(self, epoch: int, sequence: int, release_digest: str) -> WatermarkAdvanced | WatermarkRejected:
        if (epoch, sequence) < (self.epoch, self.sequence):
            return WatermarkRejected("active_pointer_watermark_rewind")
        if (epoch, sequence) == (self.epoch, self.sequence) and self.release_digest not in {None, release_digest}:
            return WatermarkRejected("active_pointer_watermark_substitution")
        self.epoch, self.sequence, self.release_digest = epoch, sequence, release_digest
        return WatermarkAdvanced()


def _watermark() -> _TestWatermarkStore:
    return _TestWatermarkStore()


def _fixture_expected_roots(release: dict[str, object]) -> dict[str, str]:
    fields = ("design_document_digest", "structural_manifest_digest", "coverage_root_digest", "execution_root_digest", "report_schema_registry_digest", "runner_environment_profile_registry_digest", "trust_snapshot_digest")
    roots: dict[str, str] = {}
    for field in fields:
        value = release.get(field)
        if isinstance(value, str):
            roots[field] = value
    return roots


def _signed(body: dict[str, object], *, domain: bytes, digest_field: str, profile: str = "deterministic-v1", key: str = "bootstrap-key") -> bytes:
    digest = sha256(domain + b"\0" + canonical_document(body)).hexdigest()
    return canonical_document({**body, digest_field: digest, "signature": _signature(profile, key, digest.encode("ascii")).hex()})


def _release_history(entries: list[dict[str, object]], *, key: str = "bootstrap-key") -> bytes:
    body = {
        "history_id": "history",
        "issuance_purpose": "semantic_ingestion_traceability_release_history",
        "canonical_profile_id": "memorii-sia-canonical-json-v1",
        "signature_profile_id": "deterministic-v1",
        "issuer_key_or_certificate_digest": key,
        "entries": entries,
    }
    return _signed(body, domain=b"memorii:sia-traceability-release-history:v1", digest_field="release_history_digest", key=key)


def _history_entry(*, release: dict[str, object], sequence: int, predecessor: dict[str, object] | None = None, effective_at: str | None = None) -> dict[str, object]:
    body: dict[str, object] = {
        "entry_id": f"entry-{sequence}", "sequence": sequence,
        "predecessor_entry_digest": predecessor["entry_digest"] if predecessor else None,
        "release_id": release["release_id"], "release_digest": release["release_digest"],
        "release_epoch": release["epoch"], "release_sequence": release["sequence"],
        "prior_active_release_digest": predecessor["release_digest"] if predecessor else None,
        "prior_release_terminal_state": "superseded" if predecessor else None,
        "effective_at": release["issued_at"] if effective_at is None else effective_at,
    }
    return {**body, "entry_digest": sha256(b"memorii:sia-traceability-release-history-entry:v1\0" + canonical_document(body)).hexdigest()}


def _trusted_artifacts(*, mutated: str | None = None) -> tuple[dict[str, bytes], VerifierHeldTrustMaterial]:
    registry = load_registry(_registry_path())
    now = datetime(2026, 1, 2, tzinfo=UTC)
    bootstrap = _signed({"anchor_id": "bootstrap", "issuance_purpose": "semantic_ingestion_traceability_release_root", "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1", "public_key_or_root_certificate_digest": "bootstrap-key", "target_authority_id": "authority"}, domain=b"memorii:sia-traceability-bootstrap-anchor:v1", digest_field="anchor_digest")
    bootstrap_value = __import__("json").loads(bootstrap)
    recovery = _signed({"recovery_root_id": "recovery", "issuance_purpose": "semantic_ingestion_traceability_recovery_root", "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1", "public_key_or_root_certificate_digest": "recovery-key", "target_authority_id": "authority"}, domain=b"memorii:sia-traceability-recovery-root:v1", digest_field="recovery_root_digest", key="recovery-key")
    recovery_value = __import__("json").loads(recovery)
    policy = _signed({"issuance_purpose": "semantic_ingestion_traceability_recovery_policy", "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1", "policy_signer_key_or_certificate_digest": "bootstrap-key", "active_bootstrap_anchor_digest": bootstrap_value["anchor_digest"], "eligible_recovery_root_digests": [recovery_value["recovery_root_digest"]], "threshold": 1}, domain=b"memorii:sia-traceability-recovery-policy:v1", digest_field="recovery_policy_digest")
    record_body: dict[str, object] = {"issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle", "sequence": 1, "predecessor_record_digest": None, "effective_at": "2026-01-01T00:00:00Z", "recorded_at": "2026-01-01T00:00:01Z", "action": "activate", "target_id": "bootstrap", "target_digest": bootstrap_value["anchor_digest"], "replacement_target_id": None, "replacement_target_digest": None, "signer_bindings": [{"signer_id": "bootstrap", "signature_profile_id": "deterministic-v1", "key_digest": "bootstrap-key"}]}
    record_digest = sha256(b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(record_body)).hexdigest()
    record = {**record_body, "record_digest": record_digest, "signatures": [_signature("deterministic-v1", "bootstrap-key", record_digest.encode("ascii")).hex()]}
    root_body = {"authority_id": "authority", "records": [record]}
    root_digest = sha256(b"memorii:sia-traceability-trust-lifecycle-root:v1\0" + canonical_document(root_body)).hexdigest()
    lifecycle = canonical_document({**root_body, "lifecycle_root_digest": root_digest, "signature": _signature("deterministic-v1", "bootstrap-key", root_digest.encode("ascii")).hex()})
    roots = {
        "registry_source_identity": registry.source_identity,
        **{f"{name}_digest": digest for name, digest in registry.root_digests.items()},
        "design_document_digest": "d" * 64,
        "structural_manifest_digest": "1" * 64,
        "coverage_root_digest": "c" * 64,
        "execution_root_digest": "e" * 64,
        "report_schema_registry_digest": "a" * 64,
        "runner_environment_profile_registry_digest": "b" * 64,
        "trust_snapshot_digest": "f" * 64,
    }
    release_body: dict[str, object] = {"release_id": "one", "issuance_purpose": "semantic_ingestion_traceability_release", "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1", "issuer_key_or_certificate_digest": "bootstrap-key", "grammar_revision": registry.source["grammar_revision"], "issued_state": "active", "predecessor_release_id": None, "supersedes_release_id": None, "bootstrap_anchor_digest": bootstrap_value["anchor_digest"], "recovery_root_digest": recovery_value["recovery_root_digest"], "issued_at": "2026-01-01T00:00:02Z", "expires_at": (now + timedelta(days=1)).isoformat(), "epoch": 1, "sequence": 1, **roots}
    release = _signed(release_body, domain=b"memorii:sia-traceability-release:v1", digest_field="release_digest")
    pointer_body = {"issuance_purpose": "semantic_ingestion_traceability_active_release_pointer", "release_id": "one", "release_digest": __import__("json").loads(release)["release_digest"], "epoch": 1, "sequence": 1, "signature_profile_id": "deterministic-v1", "issuer_key_or_certificate_digest": "bootstrap-key"}
    pointer = _signed(pointer_body, domain=b"memorii:sia-traceability-active-release-pointer:v1", digest_field="active_pointer_digest")
    artifacts = {"bootstrap": bootstrap, "recovery": recovery, "lifecycle": lifecycle, "release": release, "pointer": pointer, "history": _release_history([_history_entry(release=json.loads(release), sequence=1)])}
    if mutated is not None:
        artifacts[mutated] = artifacts[mutated] + b" "
    return artifacts, VerifierHeldTrustMaterial(bootstrap, (recovery,), _verifier, policy)


def test_sia_t03_registry_loads_exact_frozen_source_and_dag() -> None:
    registry = load_registry(_registry_path())
    assert registry.source_identity == "6acb473684fdc80a5d89ab44f751ae1f39c9e01ea589a9f4b116f7b0dc116332"
    assert len(registry.source["heading_defaults"]) == 148


@pytest.mark.parametrize("mutation", [b" ", b"\n", b"\xef\xbb\xbf"])
def test_sia_t03_registry_rejects_noncanonical_raw_bytes(tmp_path: Path, mutation: bytes) -> None:
    target = tmp_path / "registry.json"
    target.write_bytes(_registry_path().read_bytes() + mutation)
    with pytest.raises(RegistryValidationError):
        load_registry(target)


def test_sia_t03_independent_approval_loader_consumes_raw_bytes() -> None:
    assert len(load_independent_registry_bytes(_registry_path().read_bytes())["heading_defaults"]) == 148
    with pytest.raises(TraceabilityCoverageError):
        load_independent_registry_bytes(_registry_path().read_bytes() + b" ")


def _parser_hostile_registry_bytes() -> tuple[tuple[str, bytes], ...]:
    return (
        ("deep_array", b"[" * 1100 + b"0" + b"]" * 1100 + b"\n"),
        ("deep_object", b'{"child":' * 1100 + b"0" + b"}" * 1100 + b"\n"),
        (
            "deep_schema",
            b'{"type":"array","items":' * 1100
            + b'{"type":"null"}'
            + b"}" * 1100
            + b"\n",
        ),
        ("oversized_integer", b'{"value":' + b"9" * 5000 + b"}\n"),
    )


@pytest.mark.parametrize(("case_id", "raw"), _parser_hostile_registry_bytes())
def test_sia_t03_both_registry_loaders_and_rebuild_normalize_parser_hostile_bytes(
    case_id: str, raw: bytes
) -> None:
    with pytest.raises(RegistryValidationError):
        load_registry_bytes(raw)
    with pytest.raises(TraceabilityCoverageError):
        load_independent_registry_bytes(raw)
    design = (
        Path(__file__).parents[4]
        / "docs"
        / "design"
        / "semantic_ingestion_architecture.md"
    ).read_bytes()
    with pytest.raises(TraceabilityCoverageError):
        rebuild_structural_manifest_bytes(
            design_bytes=design,
            registry=load_registry(_registry_path()),
            registry_bytes=raw,
        )


_ARRAY_ROOT_NAMES = (
    "anchor_bindings",
    "artifact_dag",
    "assertion_templates",
    "heading_defaults",
    "overrides",
    "report_schemas",
    "requirement_bindings",
    "runner_environment_profiles",
    "structural_rules",
    "test_evidence_groups",
)


@pytest.mark.parametrize("root", _ARRAY_ROOT_NAMES)
@pytest.mark.parametrize(
    ("replacement_id", "replacement"),
    (("object", {}), ("null", None), ("string", "not-an-array"), ("number", 1)),
)
def test_sia_t03_both_loaders_and_rebuild_reject_non_array_root_with_typed_error(
    tmp_path: Path, root: str, replacement_id: str, replacement: object
) -> None:
    source = json.loads(_registry_path().read_text())
    source[root] = replacement
    raw = canonical_document(source)
    target = tmp_path / f"{root}-{replacement_id}.json"
    target.write_bytes(raw)
    with pytest.raises(RegistryValidationError):
        load_registry(target)
    with pytest.raises(TraceabilityCoverageError):
        load_independent_registry_bytes(raw)
    design = (
        Path(__file__).parents[4]
        / "docs"
        / "design"
        / "semantic_ingestion_architecture.md"
    ).read_bytes()
    with pytest.raises(TraceabilityCoverageError):
        rebuild_structural_manifest_bytes(
            design_bytes=design,
            registry=load_registry(_registry_path()),
            registry_bytes=raw,
        )


def test_sia_t03_both_loaders_and_rebuild_accept_canonical_control_scalar_strings() -> None:
    source = json.loads(_registry_path().read_text())
    source["assertion_templates"][0]["acceptance"] = "line one\n\tline two"
    raw = canonical_document(source)
    assert b"line one\\u000a\\u0009line two" in raw
    assert (
        load_registry_bytes(raw).source["assertion_templates"][0]["acceptance"]
        == "line one\n\tline two"
    )
    assert (
        load_independent_registry_bytes(raw)["assertion_templates"][0]["acceptance"]
        == "line one\n\tline two"
    )
    design = (
        Path(__file__).parents[4]
        / "docs"
        / "design"
        / "semantic_ingestion_architecture.md"
    ).read_bytes()
    assert rebuild_structural_manifest_bytes(
        design_bytes=design,
        registry=load_registry(_registry_path()),
        registry_bytes=raw,
    )


def _registry_with_escaped_lone_surrogate() -> bytes:
    source = json.loads(_registry_path().read_text())
    source["assertion_templates"][0]["acceptance"] = "lone-surrogate-marker"
    raw = canonical_document(source)
    assert raw.count(b'"lone-surrogate-marker"') == 1
    return raw.replace(b'"lone-surrogate-marker"', b'"\\ud800"', 1)


def test_sia_t03_both_loaders_and_rebuild_reject_lone_surrogate_with_typed_error(
    tmp_path: Path,
) -> None:
    raw = _registry_with_escaped_lone_surrogate()
    target = tmp_path / "lone-surrogate.json"
    target.write_bytes(raw)
    with pytest.raises(RegistryValidationError):
        load_registry(target)
    with pytest.raises(TraceabilityCoverageError):
        load_independent_registry_bytes(raw)
    design = (
        Path(__file__).parents[4]
        / "docs"
        / "design"
        / "semantic_ingestion_architecture.md"
    ).read_bytes()
    with pytest.raises(TraceabilityCoverageError):
        rebuild_structural_manifest_bytes(
            design_bytes=design,
            registry=load_registry(_registry_path()),
            registry_bytes=raw,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda source: source["heading_defaults"].pop(),
        lambda source: source["heading_defaults"].append(source["heading_defaults"][0].copy()),
        lambda source: source["heading_defaults"][0].__setitem__("requirements", []),
        lambda source: source["heading_defaults"][0].__setitem__("requirements", ["SIA-R99"]),
        lambda source: source["heading_defaults"][0].__setitem__("requirements", ["SIA-R01", "SIA-R01"]),
        lambda source: source["heading_defaults"][next(i for i, item in enumerate(source["heading_defaults"]) if len(item["requirements"]) > 1)].__setitem__("requirements", ["SIA-R13", "SIA-R03"]),
    ],
    ids=("missing", "duplicate_heading", "empty", "unknown_requirement", "duplicate_requirement", "requirement_order"),
)
def test_sia_t03_both_registry_loaders_reject_closed_heading_mutations(tmp_path: Path, mutation: object) -> None:
    source = json.loads(_registry_path().read_text())
    assert callable(mutation)
    mutation(source)
    target = tmp_path / "registry.json"
    target.write_bytes(canonical_document(source))
    with pytest.raises(RegistryValidationError):
        load_registry(target)
    with pytest.raises(TraceabilityCoverageError):
        load_independent_registry_bytes(target.read_bytes())
    design = (
        Path(__file__).parents[4]
        / "docs"
        / "design"
        / "semantic_ingestion_architecture.md"
    ).read_bytes()
    with pytest.raises(TraceabilityCoverageError):
        rebuild_structural_manifest_bytes(
            design_bytes=design,
            registry=load_registry(_registry_path()),
            registry_bytes=target.read_bytes(),
        )


def test_sia_t03_independent_raw_root_rebuild_equals_generator_for_every_root() -> None:
    """Approval uses raw bytes; every nested specialized item participates."""
    registry = load_registry(_registry_path())
    design = (Path(__file__).parents[4] / "docs" / "design" / "semantic_ingestion_architecture.md").read_bytes()
    rebuilt = rebuild_structural_manifest_bytes(
        design_bytes=design, registry=registry, registry_bytes=_registry_path().read_bytes()
    )
    assert rebuilt == rebuild_structural_manifest_bytes(design_bytes=design, registry=registry)


def test_sia_t03_both_structural_parsers_reject_duplicate_section_heading() -> None:
    registry = load_registry(_registry_path())
    design = (Path(__file__).parents[4] / "docs" / "design" / "semantic_ingestion_architecture.md").read_bytes()
    duplicated = design.replace(b"## 1. ", b"## 1. \n### 1.1. Duplicate heading\n\n", 1)
    with pytest.raises(StructuralManifestError, match="duplicate"):
        build_structural_manifest(design_bytes=duplicated, registry=registry)
    with pytest.raises(TraceabilityCoverageError, match="duplicate"):
        rebuild_structural_manifest_bytes(design_bytes=duplicated, registry=registry, registry_bytes=_registry_path().read_bytes())


@pytest.mark.parametrize(
    "mutate",
    [
        lambda source: source["report_schemas"][0]["schema_document"].__setitem__("title", "substituted"),
        lambda source: source["runner_environment_profiles"][0]["network_policy"].__setitem__("enforcement", "allowed"),
        lambda source: source["test_evidence_groups"].reverse(),
    ],
)
def test_sia_t03_both_approval_loaders_reject_specialized_schema_profile_or_order_mutations(tmp_path: Path, mutate: object) -> None:
    source = json.loads(_registry_path().read_text())
    assert callable(mutate)
    mutate(source)
    target = tmp_path / "registry.json"
    target.write_bytes(canonical_document(source))
    with pytest.raises(RegistryValidationError):
        load_registry(target)
    with pytest.raises(TraceabilityCoverageError):
        load_independent_registry_bytes(target.read_bytes())


@pytest.mark.parametrize(
    "mutate",
    [
        lambda source: next(
            item for item in source["artifact_dag"] if item["depends_on"]
        )["depends_on"].append(
            next(item for item in source["artifact_dag"] if item["depends_on"])["depends_on"][0]
        ),
        lambda source: source["structural_rules"].append(
            {**source["structural_rules"][0]}
        ),
        lambda source: source["anchor_bindings"].append(
            {**source["anchor_bindings"][0]}
        ),
        lambda source: source["overrides"].append(
            {"invariant_id": "SIA-N-test-0", "added_requirements": ["SIA-R01"]}
        ),
    ],
    ids=("duplicate_dag_dependency", "duplicate_rule_id", "duplicate_anchor", "nonempty_v1_overrides"),
)
def test_sia_t03_both_registry_loaders_reject_closed_duplicate_policy_mutations(
    tmp_path: Path, mutate: object
) -> None:
    source = json.loads(_registry_path().read_text())
    assert callable(mutate)
    mutate(source)
    target = tmp_path / "registry.json"
    target.write_bytes(canonical_document(source))
    with pytest.raises(RegistryValidationError):
        load_registry(target)
    with pytest.raises(TraceabilityCoverageError):
        load_independent_registry_bytes(target.read_bytes())
    design = (
        Path(__file__).parents[4]
        / "docs"
        / "design"
        / "semantic_ingestion_architecture.md"
    ).read_bytes()
    with pytest.raises(TraceabilityCoverageError):
        rebuild_structural_manifest_bytes(
            design_bytes=design,
            registry=load_registry(_registry_path()),
            registry_bytes=target.read_bytes(),
        )


def _mutate_closed_registry_source(source: dict[str, object], mutation: str) -> None:
    roots = {
        "unknown_requirement_binding": "requirement_bindings",
        "unknown_assertion_template": "assertion_templates",
        "unknown_heading_default": "heading_defaults",
        "unknown_structural_rule": "structural_rules",
        "unknown_anchor": "anchor_bindings",
        "unknown_artifact_node": "artifact_dag",
        "unknown_test_group": "test_evidence_groups",
    }
    if mutation in roots:
        items = source[roots[mutation]]
        assert isinstance(items, list) and items and isinstance(items[0], dict)
        items[0]["unknown_v1_member"] = "forbidden"
        return
    bindings = source["requirement_bindings"]
    templates = source["assertion_templates"]
    groups = source["test_evidence_groups"]
    nodes = source["artifact_dag"]
    assert all(isinstance(items, list) for items in (bindings, templates, groups, nodes))
    if mutation == "assertion_version_mismatch":
        assert isinstance(bindings, list) and isinstance(bindings[0], dict)
        bindings[0]["assertion_version"] = 2
    elif mutation == "requirement_binding_order":
        assert isinstance(bindings, list)
        bindings[0], bindings[1] = bindings[1], bindings[0]
    elif mutation == "assertion_template_order":
        assert isinstance(templates, list) and isinstance(templates[0], dict)
        templates.append({**templates[0], "template_id": "aaa-structural-conformance"})
    elif mutation == "test_group_order":
        assert isinstance(groups, list)
        groups[0], groups[1] = groups[1], groups[0]
    elif mutation.startswith("dependency_"):
        assert isinstance(nodes, list)
        node = next(item for item in nodes if isinstance(item, dict) and item["depends_on"])
        shape: object
        if mutation == "dependency_string":
            shape = ""
        elif mutation == "dependency_null":
            shape = None
        elif mutation == "dependency_object":
            shape = {}
        elif mutation == "dependency_number":
            shape = 1
        else:
            shape = [node["depends_on"][0], 1]
        node["depends_on"] = shape
    elif mutation == "kahn_valid_reorder":
        assert isinstance(nodes, list)
        nodes[0], nodes[1] = nodes[1], nodes[0]
    elif mutation == "kahn_back_edge":
        assert isinstance(nodes, list) and isinstance(nodes[0], dict)
        nodes[0]["depends_on"] = ["recovery_trust_roots"]
    else:
        raise AssertionError(f"unknown mutation: {mutation}")


@pytest.mark.parametrize(
    "mutation",
    (
        "unknown_requirement_binding",
        "unknown_assertion_template",
        "unknown_heading_default",
        "unknown_structural_rule",
        "unknown_anchor",
        "unknown_artifact_node",
        "unknown_test_group",
        "assertion_version_mismatch",
        "requirement_binding_order",
        "assertion_template_order",
        "test_group_order",
        "dependency_string",
        "dependency_null",
        "dependency_object",
        "dependency_number",
        "dependency_mixed",
        "kahn_valid_reorder",
    ),
)
def test_sia_t03_both_registry_loaders_and_rebuild_reject_closed_v1_mutations(
    tmp_path: Path, mutation: str
) -> None:
    source = json.loads(_registry_path().read_text())
    _mutate_closed_registry_source(source, mutation)
    target = tmp_path / f"{mutation}.json"
    target.write_bytes(canonical_document(source))
    with pytest.raises(RegistryValidationError):
        load_registry(target)
    with pytest.raises(TraceabilityCoverageError):
        load_independent_registry_bytes(target.read_bytes())
    design = (
        Path(__file__).parents[4]
        / "docs"
        / "design"
        / "semantic_ingestion_architecture.md"
    ).read_bytes()
    with pytest.raises(TraceabilityCoverageError):
        rebuild_structural_manifest_bytes(
            design_bytes=design,
            registry=load_registry(_registry_path()),
            registry_bytes=target.read_bytes(),
        )


def test_sia_t03_both_loaders_and_rebuild_reject_kahn_back_edge_at_topological_check(
    tmp_path: Path,
) -> None:
    source = json.loads(_registry_path().read_text())
    _mutate_closed_registry_source(source, "kahn_back_edge")
    raw = canonical_document(source)
    target = tmp_path / "kahn-back-edge.json"
    target.write_bytes(raw)
    with pytest.raises(RegistryValidationError, match="deterministic Kahn"):
        load_registry(target)
    with pytest.raises(TraceabilityCoverageError, match="deterministic Kahn"):
        load_independent_registry_bytes(raw)
    design = (
        Path(__file__).parents[4]
        / "docs"
        / "design"
        / "semantic_ingestion_architecture.md"
    ).read_bytes()
    with pytest.raises(TraceabilityCoverageError, match="deterministic Kahn"):
        rebuild_structural_manifest_bytes(
            design_bytes=design,
            registry=load_registry(_registry_path()),
            registry_bytes=raw,
        )


_SPECIALIZED_V1_MUTATIONS = (
    "metadata_format_literal",
    "metadata_registry_id_type",
    "metadata_registry_id_literal",
    "metadata_grammar_revision_literal",
    "metadata_design_path_type",
    "metadata_design_path_literal",
    "report_unknown_outer",
    "report_unknown_root",
    "report_canonical_literal",
    "report_media_literal",
    "report_schema_id_list",
    "report_schema_id_number",
    "report_version_bool",
    "report_version_zero",
    "report_version_string",
    "report_version_two",
    "report_document_schema_literal",
    "report_document_additional_literal",
    "report_document_properties_type",
    "report_document_required_type",
    "report_document_required_item_type",
    "report_document_type_literal",
    "report_property_schema_list",
    "report_duplicate_required",
    "report_inconsistent_required",
    "report_incomplete_closed_required",
    "report_unsupported_keyword",
    "report_unsupported_type",
    "report_anyof_empty",
    "report_anyof_invalid_alternative",
    "report_const_extra_keyword",
    "report_incompatible_keyword",
    "report_items_type",
    "report_min_items_bool",
    "report_unique_items_type",
    "report_min_length_bool",
    "report_pattern_type",
    "report_pattern_uncompilable",
    "report_format_literal",
    "report_additional_properties_type",
    "profile_unknown_outer",
    "profile_canonical_literal",
    "profile_id_list",
    "profile_id_number",
    "profile_version_bool",
    "profile_version_zero",
    "profile_version_string",
    "profile_version_two",
    "interpreter_unknown_member",
    "interpreter_literal",
    "interpreter_invocation_type",
    "runner_literal",
    "runner_version_type",
    "plugin_allowed_type",
    "configuration_literal",
    "configuration_option_literal",
    "configuration_file_unknown",
    "configuration_file_digest_type",
    "pytest_ini_unknown",
    "pytest_ini_testpaths_literal",
    "pytest_ini_markers_type",
    "dependency_unknown",
    "project_metadata_literal",
    "project_metadata_digest_type",
    "lockfile_literal",
    "lockfile_required_type",
    "fingerprint_fields_type",
    "fingerprint_literal",
    "import_path_paths_type",
    "import_path_literal",
    "startup_literal",
    "environment_unknown",
    "fixed_variables_unknown",
    "fixed_variable_literal",
    "dynamic_variables_type",
    "locale_literal",
    "network_unknown",
    "network_literal",
)


def _rebind_specialized_group_digests(source: dict[str, object]) -> None:
    schemas = source["report_schemas"]
    profiles = source["runner_environment_profiles"]
    groups = source["test_evidence_groups"]
    assert (
        isinstance(schemas, list)
        and len(schemas) == 1
        and isinstance(schemas[0], dict)
    )
    assert (
        isinstance(profiles, list)
        and len(profiles) == 1
        and isinstance(profiles[0], dict)
    )
    assert isinstance(groups, list) and all(isinstance(group, dict) for group in groups)
    schema_digest = sha256(
        b"memorii:sia-report-schema:v1\0" + canonical_document(schemas[0])
    ).hexdigest()
    profile_digest = sha256(
        b"memorii:sia-runner-environment-profile:v1\0"
        + canonical_document(profiles[0])
    ).hexdigest()
    for group in groups:
        group["expected_report_schema_digest"] = schema_digest
        group["expected_runner_environment_profile_digest"] = profile_digest


def _mutate_specialized_v1_source(source: dict[str, object], mutation: str) -> None:
    schemas = source["report_schemas"]
    profiles = source["runner_environment_profiles"]
    assert (
        isinstance(schemas, list)
        and len(schemas) == 1
        and isinstance(schemas[0], dict)
    )
    assert (
        isinstance(profiles, list)
        and len(profiles) == 1
        and isinstance(profiles[0], dict)
    )
    schema = schemas[0]
    profile = profiles[0]
    document = schema["schema_document"]
    assert isinstance(document, dict)
    if mutation == "metadata_format_literal":
        source["format"] = "memorii.semantic-ingestion.traceability-source.v2"
    elif mutation == "metadata_registry_id_type":
        source["registry_id"] = ["semantic-ingestion-traceability-registry-v1"]
    elif mutation == "metadata_registry_id_literal":
        source["registry_id"] = "semantic-ingestion-traceability-registry-alternate"
    elif mutation == "metadata_grammar_revision_literal":
        source["grammar_revision"] = "sia-traceability-v2"
    elif mutation == "metadata_design_path_type":
        source["design_path"] = {"path": "docs/design/semantic_ingestion_architecture.md"}
    elif mutation == "metadata_design_path_literal":
        source["design_path"] = "docs/design/alternate.md"
    elif mutation == "report_unknown_outer":
        schema["unknown_v1_member"] = "forbidden"
    elif mutation == "report_unknown_root":
        document["unknown_v1_member"] = "forbidden"
    elif mutation == "report_canonical_literal":
        schema["canonical_profile_id"] = "other-profile"
    elif mutation == "report_media_literal":
        schema["media_type"] = "application/json"
    elif mutation == "report_schema_id_list":
        schema["schema_id"] = ["memorii.semantic_ingestion.pytest_report"]
    elif mutation == "report_schema_id_number":
        schema["schema_id"] = 1
    elif mutation == "report_version_bool":
        schema["schema_version"] = True
    elif mutation == "report_version_zero":
        schema["schema_version"] = 0
    elif mutation == "report_version_string":
        schema["schema_version"] = "1"
    elif mutation == "report_version_two":
        schema["schema_version"] = 2
    elif mutation == "report_document_schema_literal":
        document["$schema"] = "https://json-schema.org/draft/2019-09/schema"
    elif mutation == "report_document_additional_literal":
        document["additionalProperties"] = True
    elif mutation == "report_document_properties_type":
        document["properties"] = []
    elif mutation == "report_document_required_type":
        document["required"] = {}
    elif mutation == "report_document_required_item_type":
        document["required"][0] = 1
    elif mutation == "report_document_type_literal":
        document["type"] = "array"
    elif mutation == "report_property_schema_list":
        document["properties"]["argv"] = []
    elif mutation == "report_duplicate_required":
        document["required"].append(document["required"][0])
    elif mutation == "report_inconsistent_required":
        document["required"].append("not_a_property")
    elif mutation == "report_incomplete_closed_required":
        document["required"].pop()
    elif mutation == "report_unsupported_keyword":
        document["properties"]["argv"]["maxItems"] = 10
    elif mutation == "report_unsupported_type":
        document["properties"]["argv"]["type"] = "number"
    elif mutation == "report_anyof_empty":
        document["properties"]["stdout_artifact_digest"]["anyOf"] = []
    elif mutation == "report_anyof_invalid_alternative":
        document["properties"]["stdout_artifact_digest"]["anyOf"][0] = []
    elif mutation == "report_const_extra_keyword":
        document["properties"]["schema_id"]["minLength"] = 1
    elif mutation == "report_incompatible_keyword":
        document["properties"]["runner_id"]["minItems"] = 1
    elif mutation == "report_items_type":
        document["properties"]["argv"]["items"] = []
    elif mutation == "report_min_items_bool":
        document["properties"]["argv"]["minItems"] = True
    elif mutation == "report_unique_items_type":
        document["properties"]["selected_test_ids"]["uniqueItems"] = "true"
    elif mutation == "report_min_length_bool":
        document["properties"]["runner_id"]["minLength"] = True
    elif mutation == "report_pattern_type":
        document["properties"]["design_document_digest"]["pattern"] = 1
    elif mutation == "report_pattern_uncompilable":
        document["properties"]["design_document_digest"]["pattern"] = "["
    elif mutation == "report_format_literal":
        document["properties"]["started_at"]["format"] = "email"
    elif mutation == "report_additional_properties_type":
        document["properties"]["tests"]["items"]["additionalProperties"] = "false"
    elif mutation == "profile_unknown_outer":
        profile["unknown_v1_member"] = "forbidden"
    elif mutation == "profile_canonical_literal":
        profile["canonical_profile_id"] = "other-profile"
    elif mutation == "profile_id_list":
        profile["profile_id"] = ["memorii.semantic_ingestion.runner_environment"]
    elif mutation == "profile_id_number":
        profile["profile_id"] = 1
    elif mutation == "profile_version_bool":
        profile["profile_version"] = True
    elif mutation == "profile_version_zero":
        profile["profile_version"] = 0
    elif mutation == "profile_version_string":
        profile["profile_version"] = "1"
    elif mutation == "profile_version_two":
        profile["profile_version"] = 2
    elif mutation == "interpreter_unknown_member":
        profile["interpreter_policy"]["unknown_v1_member"] = "forbidden"
    elif mutation == "interpreter_literal":
        profile["interpreter_policy"]["implementation"] = "PyPy"
    elif mutation == "interpreter_invocation_type":
        profile["interpreter_policy"]["invocation"] = "python -m pytest"
    elif mutation == "runner_literal":
        profile["runner_policy"]["distribution"] = "other"
    elif mutation == "runner_version_type":
        profile["runner_policy"]["minimum_version"] = 8
    elif mutation == "plugin_allowed_type":
        profile["plugin_policy"]["allowed_third_party_plugins"] = {}
    elif mutation == "configuration_literal":
        profile["configuration_policy"]["config_discovery"] = "ambient"
    elif mutation == "configuration_option_literal":
        profile["configuration_policy"]["command_options"] = ["-x"]
    elif mutation == "configuration_file_unknown":
        profile["configuration_policy"]["files"][0]["unknown_v1_member"] = "forbidden"
    elif mutation == "configuration_file_digest_type":
        profile["configuration_policy"]["files"][0]["sha256"] = 1
    elif mutation == "pytest_ini_unknown":
        profile["configuration_policy"]["pytest_ini_options"][
            "unknown_v1_member"
        ] = "forbidden"
    elif mutation == "pytest_ini_testpaths_literal":
        profile["configuration_policy"]["pytest_ini_options"]["testpaths"] = ["other"]
    elif mutation == "pytest_ini_markers_type":
        profile["configuration_policy"]["pytest_ini_options"]["markers"] = [1]
    elif mutation == "dependency_unknown":
        profile["dependency_policy"]["unknown_v1_member"] = "forbidden"
    elif mutation == "project_metadata_literal":
        profile["dependency_policy"]["project_metadata"]["path"] = "other.toml"
    elif mutation == "project_metadata_digest_type":
        profile["dependency_policy"]["project_metadata"]["sha256"] = 1
    elif mutation == "lockfile_literal":
        profile["dependency_policy"]["lockfile"]["state"] = "present"
    elif mutation == "lockfile_required_type":
        profile["dependency_policy"]["lockfile"]["state_must_be_observed"] = 1
    elif mutation == "fingerprint_fields_type":
        profile["dependency_policy"]["installed_distribution_fingerprint"][
            "fields"
        ] = "normalized_name"
    elif mutation == "fingerprint_literal":
        profile["dependency_policy"]["installed_distribution_fingerprint"][
            "ordering"
        ] = "source"
    elif mutation == "import_path_paths_type":
        profile["import_path_policy"]["normalized_paths"] = "<implementation-root>"
    elif mutation == "import_path_literal":
        profile["import_path_policy"]["outside_root"] = "allow"
    elif mutation == "startup_literal":
        profile["startup_customization_policy"]["sitecustomize"] = "present"
    elif mutation == "environment_unknown":
        profile["environment_policy"]["unknown_v1_member"] = "forbidden"
    elif mutation == "fixed_variables_unknown":
        profile["environment_policy"]["fixed_variables"][
            "UNKNOWN"
        ] = "forbidden"
    elif mutation == "fixed_variable_literal":
        profile["environment_policy"]["fixed_variables"]["TZ"] = "local"
    elif mutation == "dynamic_variables_type":
        profile["environment_policy"]["dynamic_artifact_coordinate_variables"] = [
            1
        ]
    elif mutation == "locale_literal":
        profile["locale_timezone_policy"]["timezone"] = "local"
    elif mutation == "network_unknown":
        profile["network_policy"]["unknown_v1_member"] = "forbidden"
    elif mutation == "network_literal":
        profile["network_policy"]["enforcement"] = "allowed"
    else:
        raise AssertionError(f"unknown specialized mutation: {mutation}")
    _rebind_specialized_group_digests(source)


@pytest.mark.parametrize("mutation", _SPECIALIZED_V1_MUTATIONS)
def test_sia_t03_both_loaders_and_rebuild_reject_rebound_specialized_v1_mutations(
    tmp_path: Path, mutation: str
) -> None:
    source = json.loads(_registry_path().read_text())
    _mutate_specialized_v1_source(source, mutation)
    raw = canonical_document(source)
    target = tmp_path / f"{mutation}.json"
    target.write_bytes(raw)
    with pytest.raises(RegistryValidationError):
        load_registry(target)
    with pytest.raises(TraceabilityCoverageError):
        load_independent_registry_bytes(raw)
    design = (
        Path(__file__).parents[4]
        / "docs"
        / "design"
        / "semantic_ingestion_architecture.md"
    ).read_bytes()
    with pytest.raises(TraceabilityCoverageError):
        rebuild_structural_manifest_bytes(
            design_bytes=design,
            registry=load_registry(_registry_path()),
            registry_bytes=raw,
        )


def test_sia_t03_both_loaders_and_rebuild_accept_supported_schema_dialect_variant() -> None:
    source = json.loads(_registry_path().read_text())
    schema = source["report_schemas"][0]["schema_document"]
    schema["properties"]["argv"]["uniqueItems"] = False
    _rebind_specialized_group_digests(source)
    raw = canonical_document(source)
    assert load_registry_bytes(raw).source["report_schemas"][0] == source["report_schemas"][0]
    assert load_independent_registry_bytes(raw)["report_schemas"][0] == source["report_schemas"][0]
    design = (
        Path(__file__).parents[4]
        / "docs"
        / "design"
        / "semantic_ingestion_architecture.md"
    ).read_bytes()
    assert rebuild_structural_manifest_bytes(
        design_bytes=design,
        registry=load_registry(_registry_path()),
        registry_bytes=raw,
    )


def test_sia_t03_both_loaders_and_rebuild_reject_rebound_pattern_compile_overflow(
    tmp_path: Path,
) -> None:
    source = json.loads(_registry_path().read_text())
    schema = source["report_schemas"][0]["schema_document"]
    schema["properties"]["argv"]["items"]["pattern"] = "a{999999999999999999999999999999}"
    _rebind_specialized_group_digests(source)
    raw = canonical_document(source)
    target = tmp_path / "pattern-compile-overflow.json"
    target.write_bytes(raw)
    with pytest.raises(RegistryValidationError, match="pattern is not compilable"):
        load_registry(target)
    with pytest.raises(TraceabilityCoverageError, match="pattern is not compilable"):
        load_independent_registry_bytes(raw)
    design = (
        Path(__file__).parents[4]
        / "docs"
        / "design"
        / "semantic_ingestion_architecture.md"
    ).read_bytes()
    with pytest.raises(TraceabilityCoverageError, match="pattern is not compilable"):
        rebuild_structural_manifest_bytes(
            design_bytes=design,
            registry=load_registry(_registry_path()),
            registry_bytes=raw,
        )


def test_sia_t03_release_gate_is_typed_unavailable_without_independent_material() -> None:
    result = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=None, recovery_artifact=None, lifecycle_artifact=None, release_artifact=None)
    assert isinstance(result, TraceabilityGateUnavailable)


def test_sia_t03_release_gate_is_unavailable_without_expected_root_authority() -> None:
    artifacts, material = _trusted_artifacts()
    result = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=artifacts["release"], release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"], verifier_material=material, watermark_store=_watermark(), now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(result, TraceabilityGateUnavailable)


@pytest.mark.parametrize("invalid", ["", "A" * 64, "a" * 63, "g" * 64])
def test_sia_t03_release_gate_rejects_non_digest_external_root_authority(
    invalid: str,
) -> None:
    artifacts, material = _trusted_artifacts()
    expected_roots = _fixture_expected_roots(json.loads(artifacts["release"]))
    expected_roots["structural_manifest_digest"] = invalid
    result = verify_release_gate(
        registry=load_registry(_registry_path()),
        bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=artifacts["recovery"],
        lifecycle_artifact=artifacts["lifecycle"],
        release_artifact=artifacts["release"],
        release_history_artifact=artifacts["history"],
        active_pointer_artifact=artifacts["pointer"],
        verifier_material=material,
        watermark_store=_watermark(),
        expected_release_roots=expected_roots,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(result, TraceabilityGateUnavailable)
    assert result.reason == "expected_release_roots_unavailable"


def test_sia_t03_release_gate_is_unavailable_without_watermark_store() -> None:
    artifacts, material = _trusted_artifacts()
    expected_roots = _fixture_expected_roots(json.loads(artifacts["release"]))
    result = verify_release_gate(
        registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"],
        release_artifact=artifacts["release"], release_history_artifact=artifacts["history"],
        active_pointer_artifact=artifacts["pointer"], verifier_material=material,
        watermark_store=None, expected_release_roots=expected_roots,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(result, TraceabilityGateUnavailable)


def test_sia_t03_release_gate_accepts_complete_genesis_and_signed_pointer() -> None:
    artifacts, material = _trusted_artifacts()
    expected_roots = _fixture_expected_roots(json.loads(artifacts["release"]))
    result = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=artifacts["release"], release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"], verifier_material=material, watermark_store=_watermark(), expected_release_roots=expected_roots, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(result, TraceabilityGateAuthorized)


def test_sia_t03_recovery_root_cannot_sign_an_ordinary_release_or_pointer() -> None:
    artifacts, material = _trusted_artifacts()
    release = json.loads(artifacts["release"])
    expected_roots = _fixture_expected_roots(release)
    body = {key: value for key, value in release.items() if key not in {"release_digest", "signature"}}
    artifacts["release"] = _signed(
        {**body, "issuer_key_or_certificate_digest": "recovery-key"},
        domain=b"memorii:sia-traceability-release:v1", digest_field="release_digest", key="recovery-key",
    )
    pointer = json.loads(artifacts["pointer"])
    pointer_body = {key: value for key, value in pointer.items() if key not in {"active_pointer_digest", "signature"}}
    artifacts["pointer"] = _signed(
        {**pointer_body, "release_digest": json.loads(artifacts["release"])["release_digest"], "issuer_key_or_certificate_digest": "recovery-key"},
        domain=b"memorii:sia-traceability-active-release-pointer:v1", digest_field="active_pointer_digest", key="recovery-key",
    )
    artifacts["history"] = _release_history([_history_entry(release=json.loads(artifacts["release"]), sequence=1)])
    result = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=artifacts["release"], release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"], verifier_material=material, watermark_store=_watermark(), expected_release_roots=expected_roots, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(result, TraceabilityGateRejected)


def test_sia_t03_acceptance_owned_watermark_rejects_history_replay() -> None:
    artifacts, material = _trusted_artifacts()
    expected_roots = _fixture_expected_roots(json.loads(artifacts["release"]))
    result = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=artifacts["release"], release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"], verifier_material=material, watermark_store=_TestWatermarkStore(1, 2, "newer"), expected_release_roots=expected_roots, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(result, TraceabilityGateRejected)


def test_sia_t03_file_watermark_reopens_and_rejects_a_valid_old_pointer(tmp_path: Path) -> None:
    artifacts, material = _trusted_artifacts()
    genesis_bytes = artifacts["release"]
    genesis = json.loads(genesis_bytes)
    body = {key: value for key, value in genesis.items() if key not in {"release_digest", "signature"}}
    successor = json.loads(_signed({**body, "release_id": "two", "predecessor_release_id": "one", "supersedes_release_id": "one", "sequence": 2, "issued_at": "2026-01-01T00:00:03Z"}, domain=b"memorii:sia-traceability-release:v1", digest_field="release_digest"))
    pointer = json.loads(artifacts["pointer"])
    pointer_body = {key: value for key, value in pointer.items() if key not in {"active_pointer_digest", "signature"}}
    successor_pointer = _signed({**pointer_body, "release_id": "two", "release_digest": successor["release_digest"], "sequence": 2}, domain=b"memorii:sia-traceability-active-release-pointer:v1", digest_field="active_pointer_digest")
    genesis_entry = _history_entry(release=genesis, sequence=1)
    successor_history = _release_history([genesis_entry, _history_entry(release=successor, sequence=2, predecessor=genesis_entry)])
    path = tmp_path / "watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(store.provision(1, 1, genesis["release_digest"]), WatermarkAdvanced)
    expected_roots = _fixture_expected_roots(successor)
    result = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=canonical_document(successor), release_history_artifact=successor_history, historical_release_artifacts=(genesis_bytes,), active_pointer_artifact=successor_pointer, verifier_material=material, watermark_store=store, expected_release_roots=expected_roots, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(result, TraceabilityGateAuthorized)
    old_result = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=genesis_bytes, release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"], verifier_material=material, watermark_store=FileTraceabilityReleaseWatermarkStore(path), expected_release_roots=expected_roots, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(old_result, TraceabilityGateRejected)


def test_sia_t03_file_watermark_gate_is_idempotent_and_rejects_same_coordinate_substitution(tmp_path: Path) -> None:
    artifacts, material = _trusted_artifacts()
    path = tmp_path / "watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    expected_roots = _fixture_expected_roots(json.loads(artifacts["release"]))
    release_digest = json.loads(artifacts["release"])["release_digest"]
    assert isinstance(store.provision(1, 1, release_digest), WatermarkAdvanced)
    first = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=artifacts["release"], release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"], verifier_material=material, watermark_store=store, expected_release_roots=expected_roots, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(first, TraceabilityGateAuthorized)
    bytes_before = path.read_bytes()
    again = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=artifacts["release"], release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"], verifier_material=material, watermark_store=store, expected_release_roots=expected_roots, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(again, TraceabilityGateAuthorized)
    assert path.read_bytes() == bytes_before
    release = json.loads(artifacts["release"])
    body = {key: value for key, value in release.items() if key not in {"release_digest", "signature"}}
    substituted = json.loads(_signed({**body, "release_id": "substituted"}, domain=b"memorii:sia-traceability-release:v1", digest_field="release_digest"))
    pointer = json.loads(artifacts["pointer"])
    pointer_body = {key: value for key, value in pointer.items() if key not in {"active_pointer_digest", "signature"}}
    substituted_pointer = _signed({**pointer_body, "release_id": "substituted", "release_digest": substituted["release_digest"]}, domain=b"memorii:sia-traceability-active-release-pointer:v1", digest_field="active_pointer_digest")
    rejected = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=canonical_document(substituted), release_history_artifact=_release_history([_history_entry(release=substituted, sequence=1)]), active_pointer_artifact=substituted_pointer, verifier_material=material, watermark_store=store, expected_release_roots=expected_roots, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(rejected, TraceabilityGateRejected)
    assert path.read_bytes() == bytes_before


@pytest.mark.parametrize(
    ("successor_issued_at", "successor_effective_at"),
    [
        ("2026-01-01T00:00:02Z", "2026-01-01T00:00:03Z"),
        ("2026-01-01T00:00:03Z", "2026-01-01T00:00:02Z"),
        ("2026-01-01T00:00:03Z", "2026-01-01T00:00:01Z"),
        ("2026-01-01T00:00:04Z", "2026-01-01T00:00:03Z"),
        ("2026-01-01T00:00:03Z", "2026-01-03T00:00:00Z"),
    ],
    ids=("issued_equal_predecessor_transition", "effective_equal_predecessor_transition", "effective_before_predecessor_transition", "effective_before_issuance", "tail_not_yet_effective"),
)
def test_sia_t03_signed_successor_time_failures_reject_before_watermark_mutation(
    tmp_path: Path, successor_issued_at: str, successor_effective_at: str
) -> None:
    artifacts, material = _trusted_artifacts()
    genesis = json.loads(artifacts["release"])
    expected_roots = _fixture_expected_roots(genesis)
    successor_body = {key: value for key, value in genesis.items() if key not in {"release_digest", "signature"}}
    successor = json.loads(_signed(
        {**successor_body, "release_id": "two", "predecessor_release_id": "one", "supersedes_release_id": "one", "sequence": 2, "issued_at": successor_issued_at},
        domain=b"memorii:sia-traceability-release:v1", digest_field="release_digest",
    ))
    pointer = json.loads(artifacts["pointer"])
    pointer_body = {key: value for key, value in pointer.items() if key not in {"active_pointer_digest", "signature"}}
    successor_pointer = _signed(
        {**pointer_body, "release_id": "two", "release_digest": successor["release_digest"], "sequence": 2},
        domain=b"memorii:sia-traceability-active-release-pointer:v1", digest_field="active_pointer_digest",
    )
    genesis_entry = _history_entry(release=genesis, sequence=1)
    successor_history = _release_history([
        genesis_entry,
        _history_entry(release=successor, sequence=2, predecessor=genesis_entry, effective_at=successor_effective_at),
    ])
    path = tmp_path / "watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(store.provision(1, 1, genesis["release_digest"]), WatermarkAdvanced)
    before = path.read_bytes()
    result = verify_release_gate(
        registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"],
        release_artifact=canonical_document(successor), release_history_artifact=successor_history,
        historical_release_artifacts=(artifacts["release"],), active_pointer_artifact=successor_pointer,
        verifier_material=material, watermark_store=store, expected_release_roots=expected_roots,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(result, TraceabilityGateRejected)
    assert path.read_bytes() == before


def test_sia_t03_release_gate_requires_complete_history_and_signed_pointer() -> None:
    artifacts, material = _trusted_artifacts()
    result = verify_release_gate(
        registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"],
        release_artifact=artifacts["release"], verifier_material=material, now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(result, TraceabilityGateUnavailable)


@pytest.mark.parametrize(
    ("now", "authorized"),
    [
        (datetime(2025, 12, 31, tzinfo=UTC), False),
        (datetime(2026, 1, 3, tzinfo=UTC), True),
        (datetime(2026, 1, 3, 0, 0, 1, tzinfo=UTC), False),
    ],
)
def test_sia_t03_current_release_enforces_inclusive_issued_expiry_window(now: datetime, authorized: bool) -> None:
    artifacts, material = _trusted_artifacts()
    expected_roots = _fixture_expected_roots(json.loads(artifacts["release"]))
    result = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=artifacts["release"], release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"], verifier_material=material, watermark_store=_watermark(), expected_release_roots=expected_roots, now=now)
    assert isinstance(result, TraceabilityGateAuthorized) is authorized


@pytest.mark.parametrize("mutated", ["bootstrap", "recovery", "lifecycle", "release", "pointer"])
def test_sia_t03_release_gate_rejects_mutated_or_same_coordinate_substitution(mutated: str) -> None:
    artifacts, material = _trusted_artifacts(mutated=mutated)
    expected_roots = _fixture_expected_roots(json.loads(_trusted_artifacts()[0]["release"]))
    result = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=artifacts["release"], release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"], verifier_material=material, watermark_store=_watermark(), expected_release_roots=expected_roots, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(result, TraceabilityGateRejected)


@pytest.mark.parametrize("field", ["release", "pointer"])
def test_sia_t03_signed_boolean_coordinates_reject_before_watermark_mutation(field: str) -> None:
    artifacts, material = _trusted_artifacts()
    release = json.loads(artifacts["release"])
    expected_roots = _fixture_expected_roots(release)
    release_body = {key: value for key, value in release.items() if key not in {"release_digest", "signature"}}
    if field == "release":
        release_body["epoch"] = True
        artifacts["release"] = _signed(release_body, domain=b"memorii:sia-traceability-release:v1", digest_field="release_digest")
        release = json.loads(artifacts["release"])
        pointer = json.loads(artifacts["pointer"])
        pointer_body = {key: value for key, value in pointer.items() if key not in {"active_pointer_digest", "signature"}}
        artifacts["pointer"] = _signed({**pointer_body, "release_digest": release["release_digest"]}, domain=b"memorii:sia-traceability-active-release-pointer:v1", digest_field="active_pointer_digest")
    else:
        pointer = json.loads(artifacts["pointer"])
        pointer_body = {key: value for key, value in pointer.items() if key not in {"active_pointer_digest", "signature"}}
        artifacts["pointer"] = _signed({**pointer_body, "epoch": True}, domain=b"memorii:sia-traceability-active-release-pointer:v1", digest_field="active_pointer_digest")
    artifacts["history"] = _release_history([_history_entry(release=release, sequence=1)])
    store = _TestWatermarkStore()
    result = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=artifacts["release"], release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"], verifier_material=material, watermark_store=store, expected_release_roots=expected_roots, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(result, TraceabilityGateRejected)
    assert (store.epoch, store.sequence, store.release_digest) == (0, 0, None)


@pytest.mark.parametrize("primitive", ["recovery_threshold", "lifecycle_sequence"])
def test_sia_t03_signed_boolean_lifecycle_primitives_reject_before_file_watermark_mutation(
    tmp_path: Path, primitive: str
) -> None:
    artifacts, material = _trusted_artifacts()
    expected_roots = _fixture_expected_roots(json.loads(artifacts["release"]))
    if primitive == "recovery_threshold":
        assert material.recovery_policy_bytes is not None
        policy = json.loads(material.recovery_policy_bytes)
        body = {key: value for key, value in policy.items() if key not in {"recovery_policy_digest", "signature"}}
        policy = _signed(
            {**body, "threshold": True},
            domain=b"memorii:sia-traceability-recovery-policy:v1",
            digest_field="recovery_policy_digest",
        )
        material = VerifierHeldTrustMaterial(
            material.bootstrap_anchor_bytes, material.recovery_root_bytes, _verifier, policy
        )
    else:
        lifecycle = json.loads(artifacts["lifecycle"])
        record = lifecycle["records"][0]
        body = {key: value for key, value in record.items() if key not in {"record_digest", "signatures"}}
        body["sequence"] = True
        record_digest = sha256(
            b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(body)
        ).hexdigest()
        malformed_record = {
            **body,
            "record_digest": record_digest,
            "signatures": [_signature("deterministic-v1", "bootstrap-key", record_digest.encode("ascii")).hex()],
        }
        root_body = {"authority_id": "authority", "records": [malformed_record]}
        root_digest = sha256(
            b"memorii:sia-traceability-trust-lifecycle-root:v1\0" + canonical_document(root_body)
        ).hexdigest()
        artifacts["lifecycle"] = canonical_document(
            {
                **root_body,
                "lifecycle_root_digest": root_digest,
                "signature": _signature("deterministic-v1", "bootstrap-key", root_digest.encode("ascii")).hex(),
            }
        )
    path = tmp_path / "watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(store.provision(1, 1, "0" * 64), WatermarkAdvanced)
    record_before = path.read_bytes()
    seal = path.with_name(f"{path.name}.bootstrap-seal")
    seal_before = seal.read_bytes()
    result = verify_release_gate(
        registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"],
        release_artifact=artifacts["release"], release_history_artifact=artifacts["history"],
        active_pointer_artifact=artifacts["pointer"], verifier_material=material,
        watermark_store=store, expected_release_roots=expected_roots,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(result, TraceabilityGateRejected)
    assert path.read_bytes() == record_before
    assert seal.read_bytes() == seal_before


@pytest.mark.parametrize(
    "field",
    [
        "registry_source_identity",
        "design_document_digest",
        "structural_manifest_digest",
        "coverage_root_digest",
        "execution_root_digest",
        "report_schema_registry_digest",
        "runner_environment_profile_registry_digest",
        "trust_snapshot_digest",
        *[f"{name}_digest" for name in load_registry(_registry_path()).root_digests],
    ],
)
def test_sia_t03_rejects_resigned_current_release_with_wrong_required_root(
    tmp_path: Path, field: str
) -> None:
    artifacts, material = _trusted_artifacts()
    release = json.loads(artifacts["release"])
    expected_roots = _fixture_expected_roots(release)
    body = {key: value for key, value in release.items() if key not in {"release_digest", "signature"}}
    artifacts["release"] = _signed({**body, field: "0" * 64}, domain=b"memorii:sia-traceability-release:v1", digest_field="release_digest")
    release = json.loads(artifacts["release"])
    pointer = json.loads(artifacts["pointer"])
    pointer_body = {key: value for key, value in pointer.items() if key not in {"active_pointer_digest", "signature"}}
    artifacts["pointer"] = _signed({**pointer_body, "release_digest": release["release_digest"]}, domain=b"memorii:sia-traceability-active-release-pointer:v1", digest_field="active_pointer_digest")
    artifacts["history"] = _release_history([_history_entry(release=release, sequence=1)])
    path = tmp_path / "watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(store.provision(1, 1, release["release_digest"]), WatermarkAdvanced)
    record_before = path.read_bytes()
    seal = path.with_name(f"{path.name}.bootstrap-seal")
    seal_before = seal.read_bytes()
    result = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=artifacts["release"], release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"], verifier_material=material, watermark_store=store, expected_release_roots=expected_roots, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(result, TraceabilityGateRejected)
    assert path.read_bytes() == record_before
    assert seal.read_bytes() == seal_before


def test_sia_t03_active_pointer_requires_monotonic_successor_and_signed_current_pointer() -> None:
    artifacts, material = _trusted_artifacts()
    release = __import__("json").loads(artifacts["release"])
    required = {key: release[key] for key in release if key.endswith("_digest") or key == "registry_source_identity"}
    pointer = __import__("json").loads(artifacts["pointer"])
    assert verify_active_release_pointer(releases=(release,), active_pointer=pointer, required_roots=required, verifier=_verifier)["release_id"] == "one"
    pointer["sequence"] = 0
    with pytest.raises(ValueError, match="active_pointer"):
        verify_active_release_pointer(releases=(release,), active_pointer=pointer, required_roots=required, verifier=_verifier)
    assert material.recovery_policy_bytes is not None


def _activated_lifecycle(
    artifacts: dict[str, bytes], target_bytes: bytes, *, envelope_key: str
) -> bytes:
    lifecycle = json.loads(artifacts["lifecycle"])
    target = json.loads(target_bytes)
    target_id = target.get("anchor_id", target.get("recovery_root_id"))
    target_digest = target.get("anchor_digest", target.get("recovery_root_digest"))
    body = {
        "issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle",
        "sequence": 2,
        "predecessor_record_digest": lifecycle["records"][-1]["record_digest"],
        "effective_at": "2026-01-01T00:00:02Z",
        "recorded_at": "2026-01-01T00:00:03Z",
        "action": "activate",
        "target_id": target_id,
        "target_digest": target_digest,
        "replacement_target_id": None,
        "replacement_target_digest": None,
        "signer_bindings": [
            {
                "signer_id": "bootstrap",
                "signature_profile_id": "deterministic-v1",
                "key_digest": "bootstrap-key",
            }
        ],
    }
    digest = sha256(
        b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(body)
    ).hexdigest()
    record = {
        **body,
        "record_digest": digest,
        "signatures": [
            _signature("deterministic-v1", "bootstrap-key", digest.encode("ascii")).hex()
        ],
    }
    root_body = {"authority_id": "authority", "records": [*lifecycle["records"], record]}
    root_digest = sha256(
        b"memorii:sia-traceability-trust-lifecycle-root:v1\0"
        + canonical_document(root_body)
    ).hexdigest()
    return canonical_document(
        {
            **root_body,
            "lifecycle_root_digest": root_digest,
            "signature": _signature(
                "deterministic-v1", envelope_key, root_digest.encode("ascii")
            ).hex(),
        }
    )


@pytest.mark.parametrize("root_kind", ["recovery", "successor"])
def test_sia_t03_foreign_authority_provisioned_roots_reject_before_watermark(
    tmp_path: Path, root_kind: str
) -> None:
    artifacts, material = _trusted_artifacts()
    if root_kind == "recovery":
        recovery = json.loads(artifacts["recovery"])
        recovery_body = {
            key: value
            for key, value in recovery.items()
            if key not in {"recovery_root_digest", "signature"}
        }
        foreign_root = _signed(
            {**recovery_body, "target_authority_id": "foreign-authority"},
            domain=b"memorii:sia-traceability-recovery-root:v1",
            digest_field="recovery_root_digest",
            key="recovery-key",
        )
        policy = json.loads(material.recovery_policy_bytes)
        policy_body = {
            key: value
            for key, value in policy.items()
            if key not in {"recovery_policy_digest", "signature"}
        }
        policy_bytes = _signed(
            {
                **policy_body,
                "eligible_recovery_root_digests": [
                    json.loads(foreign_root)["recovery_root_digest"]
                ],
            },
            domain=b"memorii:sia-traceability-recovery-policy:v1",
            digest_field="recovery_policy_digest",
        )
        recovery_artifact = foreign_root
        lifecycle_artifact = artifacts["lifecycle"]
        material = VerifierHeldTrustMaterial(
            artifacts["bootstrap"], (foreign_root,), _verifier, policy_bytes
        )
    else:
        foreign_root = _signed(
            {
                "anchor_id": "foreign-successor",
                "issuance_purpose": "semantic_ingestion_traceability_release_root",
                "canonical_profile_id": "memorii-sia-canonical-json-v1",
                "signature_profile_id": "deterministic-v1",
                "public_key_or_root_certificate_digest": "foreign-successor-key",
                "target_authority_id": "foreign-authority",
                "effective_at": "2026-01-01T00:00:02Z",
            },
            domain=b"memorii:sia-traceability-bootstrap-anchor:v1",
            digest_field="anchor_digest",
            key="foreign-successor-key",
        )
        recovery_artifact = artifacts["recovery"]
        lifecycle_artifact = _activated_lifecycle(
            artifacts, foreign_root, envelope_key="foreign-successor-key"
        )
        material = VerifierHeldTrustMaterial(
            material.bootstrap_anchor_bytes,
            material.recovery_root_bytes,
            _verifier,
            material.recovery_policy_bytes,
            (foreign_root,),
        )
    path = tmp_path / "watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(store.provision(1, 1, "0" * 64), WatermarkAdvanced)
    before = path.read_bytes()
    seal = path.with_name(f"{path.name}.bootstrap-seal")
    seal_before = seal.read_bytes()
    result = verify_release_gate(
        registry=load_registry(_registry_path()),
        bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=recovery_artifact,
        lifecycle_artifact=lifecycle_artifact,
        release_artifact=artifacts["release"],
        release_history_artifact=artifacts["history"],
        active_pointer_artifact=artifacts["pointer"],
        verifier_material=material,
        watermark_store=store,
        expected_release_roots=_fixture_expected_roots(json.loads(artifacts["release"])),
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(result, TraceabilityGateRejected)
    assert result.reason == "provisioned_root_authority_invalid"
    assert path.read_bytes() == before
    assert seal.read_bytes() == seal_before


@pytest.mark.parametrize(("expires_at", "authorized"), [(None, True), ("2026-01-01T00:00:02Z", False)])
def test_sia_t03_non_genesis_activation_target_window_is_start_inclusive_expiry_exclusive(
    tmp_path: Path, expires_at: str | None, authorized: bool
) -> None:
    artifacts, material = _trusted_artifacts()
    target_body: dict[str, object] = {
        "anchor_id": "activation-target",
        "issuance_purpose": "semantic_ingestion_traceability_release_root",
        "canonical_profile_id": "memorii-sia-canonical-json-v1",
        "signature_profile_id": "deterministic-v1",
        "public_key_or_root_certificate_digest": "activation-key",
        "target_authority_id": "authority",
        "effective_at": "2026-01-01T00:00:02Z",
    }
    if expires_at is not None:
        target_body["expires_at"] = expires_at
    target = _signed(
        target_body,
        domain=b"memorii:sia-traceability-bootstrap-anchor:v1",
        digest_field="anchor_digest",
        key="activation-key",
    )
    artifacts["lifecycle"] = _activated_lifecycle(
        artifacts, target, envelope_key="activation-key"
    )
    material = VerifierHeldTrustMaterial(
        material.bootstrap_anchor_bytes,
        material.recovery_root_bytes,
        _verifier,
        material.recovery_policy_bytes,
        (target,),
    )
    path = tmp_path / "watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    release_digest = json.loads(artifacts["release"])["release_digest"]
    assert isinstance(store.provision(1, 1, release_digest), WatermarkAdvanced)
    before = path.read_bytes()
    seal = path.with_name(f"{path.name}.bootstrap-seal")
    seal_before = seal.read_bytes()
    result = verify_release_gate(
        registry=load_registry(_registry_path()),
        bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"],
        lifecycle_artifact=artifacts["lifecycle"], release_artifact=artifacts["release"],
        release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"],
        verifier_material=material, watermark_store=store,
        expected_release_roots=_fixture_expected_roots(json.loads(artifacts["release"])),
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    if authorized:
        # The lifecycle itself is valid at the inclusive start; the unchanged
        # release remains signed by the still-active bootstrap signer.
        assert isinstance(result, TraceabilityGateAuthorized)
    else:
        assert isinstance(result, TraceabilityGateRejected)
        assert result.reason == "lifecycle_activation_time_invalid"
        assert path.read_bytes() == before
        assert seal.read_bytes() == seal_before


def test_sia_t03_recovery_activation_remains_purpose_separated_from_ordinary_signers(
    tmp_path: Path,
) -> None:
    artifacts, material = _trusted_artifacts()
    expected = _fixture_expected_roots(json.loads(artifacts["release"]))
    bootstrap_signed = _activated_lifecycle(
        artifacts, artifacts["recovery"], envelope_key="bootstrap-key"
    )
    recovery_signed = _activated_lifecycle(
        artifacts, artifacts["recovery"], envelope_key="recovery-key"
    )
    path = tmp_path / "watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(store.provision(1, 1, "0" * 64), WatermarkAdvanced)
    before = path.read_bytes()
    seal = path.with_name(f"{path.name}.bootstrap-seal")
    seal_before = seal.read_bytes()
    wrong = verify_release_gate(
        registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=artifacts["recovery"], lifecycle_artifact=recovery_signed,
        release_artifact=artifacts["release"], release_history_artifact=artifacts["history"],
        active_pointer_artifact=artifacts["pointer"], verifier_material=material,
        watermark_store=store, expected_release_roots=expected,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(wrong, TraceabilityGateRejected)
    assert wrong.reason == "signature_invalid"
    assert path.read_bytes() == before
    assert seal.read_bytes() == seal_before
    right = verify_release_gate(
        registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=artifacts["recovery"], lifecycle_artifact=bootstrap_signed,
        release_artifact=artifacts["release"], release_history_artifact=artifacts["history"],
        active_pointer_artifact=artifacts["pointer"], verifier_material=material,
        watermark_store=_watermark(), expected_release_roots=expected,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(right, TraceabilityGateAuthorized)

    release = json.loads(artifacts["release"])
    release_body = {key: value for key, value in release.items() if key not in {"release_digest", "signature"}}
    recovery_release = _signed(
        {**release_body, "issuer_key_or_certificate_digest": "recovery-key"},
        domain=b"memorii:sia-traceability-release:v1", digest_field="release_digest",
        key="recovery-key",
    )
    current = json.loads(recovery_release)
    pointer = json.loads(artifacts["pointer"])
    pointer_body = {key: value for key, value in pointer.items() if key not in {"active_pointer_digest", "signature"}}
    recovery_pointer = _signed(
        {**pointer_body, "release_digest": current["release_digest"], "issuer_key_or_certificate_digest": "recovery-key"},
        domain=b"memorii:sia-traceability-active-release-pointer:v1",
        digest_field="active_pointer_digest", key="recovery-key",
    )
    ineligible = verify_release_gate(
        registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=artifacts["recovery"], lifecycle_artifact=bootstrap_signed,
        release_artifact=recovery_release,
        release_history_artifact=_release_history([_history_entry(release=current, sequence=1)], key="recovery-key"),
        active_pointer_artifact=recovery_pointer, verifier_material=material,
        watermark_store=_watermark(), expected_release_roots=expected,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(ineligible, TraceabilityGateRejected)
    assert ineligible.reason == "release_signer_not_lifecycle_eligible"


@pytest.mark.parametrize("action", ["revoke", "compromise"])
def test_sia_t03_activated_recovery_root_terminal_transitions_are_causal(
    action: str,
) -> None:
    artifacts, material = _trusted_artifacts()
    activated = json.loads(
        _activated_lifecycle(artifacts, artifacts["recovery"], envelope_key="bootstrap-key")
    )
    recovery = json.loads(artifacts["recovery"])
    body = {
        "issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle",
        "sequence": 3,
        "predecessor_record_digest": activated["records"][-1]["record_digest"],
        "effective_at": "2026-01-01T00:00:04Z",
        "recorded_at": "2026-01-01T00:00:05Z",
        "action": action,
        "target_id": recovery["recovery_root_id"],
        "target_digest": recovery["recovery_root_digest"],
        "replacement_target_id": None,
        "replacement_target_digest": None,
        "signer_bindings": [{"signer_id": "bootstrap", "signature_profile_id": "deterministic-v1", "key_digest": "bootstrap-key"}],
    }
    digest = sha256(
        b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(body)
    ).hexdigest()
    record = {**body, "record_digest": digest, "signatures": [_signature("deterministic-v1", "bootstrap-key", digest.encode("ascii")).hex()]}
    root_body = {"authority_id": "authority", "records": [*activated["records"], record]}
    root_digest = sha256(
        b"memorii:sia-traceability-trust-lifecycle-root:v1\0"
        + canonical_document(root_body)
    ).hexdigest()
    lifecycle = canonical_document(
        {**root_body, "lifecycle_root_digest": root_digest, "signature": _signature("deterministic-v1", "bootstrap-key", root_digest.encode("ascii")).hex()}
    )
    result = verify_release_gate(
        registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=artifacts["recovery"], lifecycle_artifact=lifecycle,
        release_artifact=artifacts["release"], release_history_artifact=artifacts["history"],
        active_pointer_artifact=artifacts["pointer"], verifier_material=material,
        watermark_store=_watermark(),
        expected_release_roots=_fixture_expected_roots(json.loads(artifacts["release"])),
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(result, TraceabilityGateAuthorized)


@pytest.mark.parametrize("action", ["revoke", "compromise"])
def test_sia_t03_recovery_terminal_envelope_uses_verified_record_signer(
    tmp_path: Path, action: str
) -> None:
    artifacts, material = _trusted_artifacts()
    activated = json.loads(
        _activated_lifecycle(artifacts, artifacts["recovery"], envelope_key="bootstrap-key")
    )
    recovery = json.loads(artifacts["recovery"])
    secondary_root = _signed(
        {
            "anchor_id": "secondary",
            "issuance_purpose": "semantic_ingestion_traceability_release_root",
            "canonical_profile_id": "memorii-sia-canonical-json-v1",
            "signature_profile_id": "deterministic-v1",
            "public_key_or_root_certificate_digest": "secondary-key",
            "target_authority_id": "authority",
            "effective_at": "2026-01-01T00:00:02Z",
        },
        domain=b"memorii:sia-traceability-bootstrap-anchor:v1",
        digest_field="anchor_digest",
        key="secondary-key",
    )
    secondary = json.loads(secondary_root)

    def record(body: dict[str, object], key: str) -> dict[str, object]:
        digest = sha256(
            b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(body)
        ).hexdigest()
        return {
            **body,
            "record_digest": digest,
            "signatures": [_signature("deterministic-v1", key, digest.encode("ascii")).hex()],
        }

    activate_secondary = record(
        {
            "issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle",
            "sequence": 3,
            "predecessor_record_digest": activated["records"][-1]["record_digest"],
            "effective_at": "2026-01-01T00:00:03Z",
            "recorded_at": "2026-01-01T00:00:04Z",
            "action": "activate",
            "target_id": secondary["anchor_id"],
            "target_digest": secondary["anchor_digest"],
            "replacement_target_id": None,
            "replacement_target_digest": None,
            "signer_bindings": [
                {"signer_id": "bootstrap", "signature_profile_id": "deterministic-v1", "key_digest": "bootstrap-key"}
            ],
        },
        "bootstrap-key",
    )
    terminal = record(
        {
            "issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle",
            "sequence": 4,
            "predecessor_record_digest": activate_secondary["record_digest"],
            "effective_at": "2026-01-01T00:00:05Z",
            "recorded_at": "2026-01-01T00:00:06Z",
            "action": action,
            "target_id": recovery["recovery_root_id"],
            "target_digest": recovery["recovery_root_digest"],
            "replacement_target_id": None,
            "replacement_target_digest": None,
            "signer_bindings": [
                {"signer_id": "bootstrap", "signature_profile_id": "deterministic-v1", "key_digest": "bootstrap-key"}
            ],
        },
        "bootstrap-key",
    )
    body = {
        "authority_id": "authority",
        "records": [*activated["records"], activate_secondary, terminal],
    }
    digest = sha256(
        b"memorii:sia-traceability-trust-lifecycle-root:v1\0" + canonical_document(body)
    ).hexdigest()

    def lifecycle(envelope_key: str) -> bytes:
        return canonical_document(
            {
                **body,
                "lifecycle_root_digest": digest,
                "signature": _signature(
                    "deterministic-v1", envelope_key, digest.encode("ascii")
                ).hex(),
            }
        )

    trust = VerifierHeldTrustMaterial(
        material.bootstrap_anchor_bytes,
        material.recovery_root_bytes,
        _verifier,
        material.recovery_policy_bytes,
        (secondary_root,),
    )
    release = json.loads(artifacts["release"])
    expected = _fixture_expected_roots(release)
    path = tmp_path / f"{action}-recovery-envelope-watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(store.provision(1, 1, "0" * 64), WatermarkAdvanced)
    before = path.read_bytes()
    seal = path.with_name(f"{path.name}.bootstrap-seal")
    seal_before = seal.read_bytes()
    stale = verify_release_gate(
        registry=load_registry(_registry_path()),
        bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=artifacts["recovery"],
        lifecycle_artifact=lifecycle("secondary-key"),
        release_artifact=artifacts["release"],
        release_history_artifact=artifacts["history"],
        active_pointer_artifact=artifacts["pointer"],
        verifier_material=trust,
        watermark_store=store,
        expected_release_roots=expected,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(stale, TraceabilityGateRejected)
    assert stale.reason == "signature_invalid"
    assert path.read_bytes() == before
    assert seal.read_bytes() == seal_before
    accepted = verify_release_gate(
        registry=load_registry(_registry_path()),
        bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=artifacts["recovery"],
        lifecycle_artifact=lifecycle("bootstrap-key"),
        release_artifact=artifacts["release"],
        release_history_artifact=artifacts["history"],
        active_pointer_artifact=artifacts["pointer"],
        verifier_material=trust,
        watermark_store=_watermark(),
        expected_release_roots=expected,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(accepted, TraceabilityGateAuthorized)


def test_sia_t03_release_gate_accepts_immutable_higher_sequence_successor_after_restart() -> None:
    artifacts, material = _trusted_artifacts()
    current_genesis = json.loads(artifacts["release"])
    expected_roots = _fixture_expected_roots(current_genesis)
    store = _watermark()
    historical_body = {key: value for key, value in current_genesis.items() if key not in {"release_digest", "signature"}}
    historical_body.update({"registry_source_identity": "66c3414e869d3cb8a010c376bcbd53e19f48124bb841c88a5836bcc5ea67bfd1", "heading_defaults_digest": "1" * 64, "structural_manifest_digest": "2" * 64})
    original_genesis_bytes = _signed(historical_body, domain=b"memorii:sia-traceability-release:v1", digest_field="release_digest")
    genesis = json.loads(original_genesis_bytes)
    successor_body = {key: value for key, value in current_genesis.items() if key not in {"release_digest", "signature"}}
    successor = json.loads(_signed({
        **successor_body,
        "release_id": "two",
        "predecessor_release_id": "one",
        "supersedes_release_id": "one",
        "sequence": 2,
        "issued_at": "2026-01-01T00:00:03Z",
    }, domain=b"memorii:sia-traceability-release:v1", digest_field="release_digest"))
    pointer = json.loads(artifacts["pointer"])
    pointer_body = {key: value for key, value in pointer.items() if key not in {"active_pointer_digest", "signature"}}
    artifacts["pointer"] = _signed({**pointer_body, "release_id": "two", "release_digest": successor["release_digest"], "sequence": 2}, domain=b"memorii:sia-traceability-active-release-pointer:v1", digest_field="active_pointer_digest")
    genesis_entry = _history_entry(release=genesis, sequence=1)
    successor_entry = _history_entry(release=successor, sequence=2, predecessor=genesis_entry)
    history = _release_history([genesis_entry, successor_entry])
    result = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=canonical_document(successor), release_history_artifact=history, historical_release_artifacts=(original_genesis_bytes,), active_pointer_artifact=artifacts["pointer"], verifier_material=material, watermark_store=store, expected_release_roots=expected_roots, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(result, TraceabilityGateAuthorized)
    assert original_genesis_bytes == canonical_document(genesis)
    restarted = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=canonical_document(successor), release_history_artifact=history, historical_release_artifacts=(original_genesis_bytes,), active_pointer_artifact=artifacts["pointer"], verifier_material=material, watermark_store=store, expected_release_roots=expected_roots, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(restarted, TraceabilityGateAuthorized)
    missing = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=canonical_document(successor), release_history_artifact=history, active_pointer_artifact=artifacts["pointer"], verifier_material=material, watermark_store=store, expected_release_roots=expected_roots, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(missing, TraceabilityGateRejected)
    duplicate = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=canonical_document(successor), release_history_artifact=history, historical_release_artifacts=(original_genesis_bytes, original_genesis_bytes), active_pointer_artifact=artifacts["pointer"], verifier_material=material, watermark_store=store, expected_release_roots=expected_roots, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(duplicate, TraceabilityGateRejected)
    altered_old = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=canonical_document(successor), release_history_artifact=history, historical_release_artifacts=(original_genesis_bytes + b" ",), active_pointer_artifact=artifacts["pointer"], verifier_material=material, watermark_store=store, expected_release_roots=expected_roots, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(altered_old, TraceabilityGateRejected)
    for malformed_history in (
        _release_history([successor_entry, genesis_entry]),
        _release_history([successor_entry]),
        _release_history([genesis_entry, _history_entry(release=successor, sequence=2, predecessor={**genesis_entry, "release_digest": "0" * 64})]),
    ):
        result = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=canonical_document(successor), release_history_artifact=malformed_history, historical_release_artifacts=(original_genesis_bytes,), active_pointer_artifact=artifacts["pointer"], verifier_material=material, watermark_store=store, expected_release_roots=expected_roots, now=datetime(2026, 1, 2, tzinfo=UTC))
        assert isinstance(result, TraceabilityGateRejected)
    old_pointer = _signed({**pointer_body, "release_id": genesis["release_id"], "release_digest": genesis["release_digest"], "sequence": 1}, domain=b"memorii:sia-traceability-active-release-pointer:v1", digest_field="active_pointer_digest")
    rewind = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=canonical_document(successor), release_history_artifact=history, historical_release_artifacts=(original_genesis_bytes,), active_pointer_artifact=old_pointer, verifier_material=material, watermark_store=store, expected_release_roots=expected_roots, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(rewind, TraceabilityGateRejected)
    old_as_current = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=original_genesis_bytes, release_history_artifact=history, historical_release_artifacts=(canonical_document(successor),), active_pointer_artifact=artifacts["pointer"], verifier_material=material, watermark_store=store, expected_release_roots=expected_roots, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(old_as_current, TraceabilityGateRejected)
    successor["supersedes_release_id"] = "unrelated"
    with pytest.raises(ValueError):
        verify_active_release_pointer(releases=(genesis, successor), active_pointer=json.loads(artifacts["pointer"]), required_roots={key: successor[key] for key in successor if key.endswith("_digest") or key == "registry_source_identity"}, verifier=_verifier)


def test_sia_t03_release_gate_accepts_rotated_lifecycle_signer(tmp_path: Path) -> None:
    artifacts, material = _trusted_artifacts()
    expected_roots = _fixture_expected_roots(json.loads(artifacts["release"]))
    rotated_root = _signed({"anchor_id": "bootstrap-rotated", "issuance_purpose": "semantic_ingestion_traceability_release_root", "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1", "public_key_or_root_certificate_digest": "rotated-key", "target_authority_id": "authority", "effective_at": "2026-01-01T00:00:02Z"}, domain=b"memorii:sia-traceability-bootstrap-anchor:v1", digest_field="anchor_digest", key="rotated-key")
    rotated_digest = json.loads(rotated_root)["anchor_digest"]
    lifecycle = json.loads(artifacts["lifecycle"])
    previous = lifecycle["records"][-1]
    body = {
        "issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle",
        "sequence": 2,
        "predecessor_record_digest": previous["record_digest"],
        "effective_at": "2026-01-01T00:00:02Z",
        "recorded_at": "2026-01-01T00:00:03Z",
        "action": "rotate",
        "target_id": "bootstrap",
        "target_digest": json.loads(artifacts["bootstrap"])["anchor_digest"],
        "replacement_target_id": "bootstrap-rotated",
        "replacement_target_digest": rotated_digest,
        "replacement_signature_profile_id": "deterministic-v1",
        "replacement_key_digest": "rotated-key",
        "signer_bindings": [{"signer_id": "bootstrap", "signature_profile_id": "deterministic-v1", "key_digest": "bootstrap-key"}],
    }
    digest = sha256(b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(body)).hexdigest()
    record = {**body, "record_digest": digest, "signatures": [_signature("deterministic-v1", "bootstrap-key", digest.encode("ascii")).hex()]}
    root_body = {"authority_id": "authority", "records": [*lifecycle["records"], record]}
    root_digest = sha256(b"memorii:sia-traceability-trust-lifecycle-root:v1\0" + canonical_document(root_body)).hexdigest()
    artifacts["lifecycle"] = canonical_document({**root_body, "lifecycle_root_digest": root_digest, "signature": _signature("deterministic-v1", "rotated-key", root_digest.encode("ascii")).hex()})
    release = json.loads(artifacts["release"])
    release_body = {key: value for key, value in release.items() if key not in {"release_digest", "signature"}}
    artifacts["release"] = _signed({**release_body, "issuer_key_or_certificate_digest": "rotated-key", "issued_at": "2026-01-01T00:00:04Z"}, domain=b"memorii:sia-traceability-release:v1", digest_field="release_digest", key="rotated-key")
    pointer = json.loads(artifacts["pointer"])
    pointer_body = {key: value for key, value in pointer.items() if key not in {"active_pointer_digest", "signature"}}
    artifacts["pointer"] = _signed({**pointer_body, "release_digest": json.loads(artifacts["release"])["release_digest"], "issuer_key_or_certificate_digest": "rotated-key"}, domain=b"memorii:sia-traceability-active-release-pointer:v1", digest_field="active_pointer_digest", key="rotated-key")
    artifacts["history"] = _release_history([_history_entry(release=json.loads(artifacts["release"]), sequence=1)], key="rotated-key")
    material = VerifierHeldTrustMaterial(material.bootstrap_anchor_bytes, material.recovery_root_bytes, _verifier, material.recovery_policy_bytes, (rotated_root,))
    valid_lifecycle = artifacts["lifecycle"]
    artifacts["lifecycle"] = canonical_document({**json.loads(valid_lifecycle), "signature": _signature("deterministic-v1", "bootstrap-key", root_digest.encode("ascii")).hex()})
    path = tmp_path / "watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(store.provision(1, 1, "0" * 64), WatermarkAdvanced)
    before = path.read_bytes()
    seal = path.with_name(f"{path.name}.bootstrap-seal")
    seal_before = seal.read_bytes()
    wrong = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=artifacts["release"], release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"], verifier_material=material, watermark_store=store, expected_release_roots=expected_roots, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(wrong, TraceabilityGateRejected)
    assert wrong.reason == "signature_invalid"
    assert path.read_bytes() == before
    assert seal.read_bytes() == seal_before
    artifacts["lifecycle"] = valid_lifecycle
    result = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=artifacts["release"], release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"], verifier_material=material, watermark_store=_watermark(), expected_release_roots=expected_roots, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(result, TraceabilityGateAuthorized)


def test_sia_t03_rotate_target_expiry_is_exclusive_before_watermark(tmp_path: Path) -> None:
    artifacts, material = _trusted_artifacts()
    expired_root = _signed(
        {
            "anchor_id": "expired-rotation",
            "issuance_purpose": "semantic_ingestion_traceability_release_root",
            "canonical_profile_id": "memorii-sia-canonical-json-v1",
            "signature_profile_id": "deterministic-v1",
            "public_key_or_root_certificate_digest": "expired-key",
            "target_authority_id": "authority",
            "effective_at": "2026-01-01T00:00:00Z",
            "expires_at": "2026-01-01T00:00:02Z",
        },
        domain=b"memorii:sia-traceability-bootstrap-anchor:v1",
        digest_field="anchor_digest",
        key="expired-key",
    )
    lifecycle = json.loads(artifacts["lifecycle"])
    body = {
        "issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle",
        "sequence": 2,
        "predecessor_record_digest": lifecycle["records"][-1]["record_digest"],
        "effective_at": "2026-01-01T00:00:02Z",
        "recorded_at": "2026-01-01T00:00:03Z",
        "action": "rotate",
        "target_id": "bootstrap",
        "target_digest": json.loads(artifacts["bootstrap"])["anchor_digest"],
        "replacement_target_id": "expired-rotation",
        "replacement_target_digest": json.loads(expired_root)["anchor_digest"],
        "replacement_signature_profile_id": "deterministic-v1",
        "replacement_key_digest": "expired-key",
        "signer_bindings": [{"signer_id": "bootstrap", "signature_profile_id": "deterministic-v1", "key_digest": "bootstrap-key"}],
    }
    digest = sha256(b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(body)).hexdigest()
    record = {**body, "record_digest": digest, "signatures": [_signature("deterministic-v1", "bootstrap-key", digest.encode("ascii")).hex()]}
    root_body = {"authority_id": "authority", "records": [*lifecycle["records"], record]}
    root_digest = sha256(b"memorii:sia-traceability-trust-lifecycle-root:v1\0" + canonical_document(root_body)).hexdigest()
    candidate = canonical_document({**root_body, "lifecycle_root_digest": root_digest, "signature": _signature("deterministic-v1", "expired-key", root_digest.encode("ascii")).hex()})
    material = VerifierHeldTrustMaterial(material.bootstrap_anchor_bytes, material.recovery_root_bytes, _verifier, material.recovery_policy_bytes, (expired_root,))
    path = tmp_path / "watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(store.provision(1, 1, "0" * 64), WatermarkAdvanced)
    before = path.read_bytes()
    seal = path.with_name(f"{path.name}.bootstrap-seal")
    seal_before = seal.read_bytes()
    result = verify_release_gate(
        registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=artifacts["recovery"], lifecycle_artifact=candidate,
        release_artifact=artifacts["release"], release_history_artifact=artifacts["history"],
        active_pointer_artifact=artifacts["pointer"], verifier_material=material,
        watermark_store=store, expected_release_roots=_fixture_expected_roots(json.loads(artifacts["release"])),
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(result, TraceabilityGateRejected)
    assert result.reason == "lifecycle_replacement_time_invalid"
    assert path.read_bytes() == before
    assert seal.read_bytes() == seal_before


def test_sia_t03_active_pointer_requires_re_signed_purpose_before_watermark() -> None:
    artifacts, material = _trusted_artifacts()
    release = json.loads(artifacts["release"])
    pointer = json.loads(artifacts["pointer"])
    body = {key: value for key, value in pointer.items() if key not in {"active_pointer_digest", "signature"}}
    artifacts["pointer"] = _signed(
        {**body, "issuance_purpose": "semantic_ingestion_traceability_release"},
        domain=b"memorii:sia-traceability-active-release-pointer:v1",
        digest_field="active_pointer_digest",
    )
    store = _watermark()
    result = verify_release_gate(
        registry=load_registry(_registry_path()),
        bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"],
        lifecycle_artifact=artifacts["lifecycle"], release_artifact=artifacts["release"],
        release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"],
        verifier_material=material, watermark_store=store,
        expected_release_roots=_fixture_expected_roots(release), now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(result, TraceabilityGateRejected)
    assert result.reason == "active_pointer_purpose_invalid"
    assert (store.epoch, store.sequence, store.release_digest) == (0, 0, None)


@pytest.mark.parametrize("artifact_name", ["release", "pointer", "lifecycle"])
def test_sia_t03_cross_purpose_signer_aliases_reject_before_watermark(
    tmp_path: Path, artifact_name: str
) -> None:
    artifacts, material = _trusted_artifacts()
    if artifact_name == "release":
        release = json.loads(artifacts["release"])
        release_body = {
            key: value
            for key, value in release.items()
            if key not in {"release_digest", "signature"}
        }
        artifacts["release"] = _signed(
            {
                **release_body,
                "public_key_or_root_certificate_digest": "bootstrap-key",
            },
            domain=b"memorii:sia-traceability-release:v1",
            digest_field="release_digest",
        )
        release = json.loads(artifacts["release"])
        artifacts["history"] = _release_history(
            [_history_entry(release=release, sequence=1)]
        )
        pointer = json.loads(artifacts["pointer"])
        pointer_body = {
            key: value
            for key, value in pointer.items()
            if key not in {"active_pointer_digest", "signature"}
        }
        artifacts["pointer"] = _signed(
            {**pointer_body, "release_digest": release["release_digest"]},
            domain=b"memorii:sia-traceability-active-release-pointer:v1",
            digest_field="active_pointer_digest",
        )
    elif artifact_name == "pointer":
        pointer = json.loads(artifacts["pointer"])
        pointer_body = {
            key: value
            for key, value in pointer.items()
            if key not in {"active_pointer_digest", "signature"}
        }
        artifacts["pointer"] = _signed(
            {
                **pointer_body,
                "public_key_or_root_certificate_digest": "bootstrap-key",
            },
            domain=b"memorii:sia-traceability-active-release-pointer:v1",
            digest_field="active_pointer_digest",
        )
    else:
        lifecycle = json.loads(artifacts["lifecycle"])
        root_body = {
            key: value
            for key, value in lifecycle.items()
            if key not in {"lifecycle_root_digest", "signature"}
        }
        root_body["issuer_key_or_certificate_digest"] = "bootstrap-key"
        root_digest = sha256(
            b"memorii:sia-traceability-trust-lifecycle-root:v1\0"
            + canonical_document(root_body)
        ).hexdigest()
        artifacts["lifecycle"] = canonical_document(
            {
                **root_body,
                "lifecycle_root_digest": root_digest,
                "signature": _signature(
                    "deterministic-v1",
                    "bootstrap-key",
                    root_digest.encode("ascii"),
                ).hex(),
            }
        )
    release = json.loads(artifacts["release"])
    path = tmp_path / f"{artifact_name}-alias-watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(store.provision(1, 1, "0" * 64), WatermarkAdvanced)
    record_before = path.read_bytes()
    seal = path.with_name(f"{path.name}.bootstrap-seal")
    seal_before = seal.read_bytes()
    files_before = {
        item.name: item.read_bytes() for item in tmp_path.iterdir() if item.is_file()
    }
    result = verify_release_gate(
        registry=load_registry(_registry_path()),
        bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=artifacts["recovery"],
        lifecycle_artifact=artifacts["lifecycle"],
        release_artifact=artifacts["release"],
        release_history_artifact=artifacts["history"],
        active_pointer_artifact=artifacts["pointer"],
        verifier_material=material,
        watermark_store=store,
        expected_release_roots=_fixture_expected_roots(release),
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(result, TraceabilityGateRejected)
    assert result.reason == "signature_key_field_ambiguous"
    assert path.read_bytes() == record_before
    assert seal.read_bytes() == seal_before
    assert {
        item.name: item.read_bytes() for item in tmp_path.iterdir() if item.is_file()
    } == files_before


def test_sia_t03_nonrecover_lifecycle_rejects_appended_valid_ineligible_signature() -> None:
    artifacts, material = _trusted_artifacts()
    lifecycle = json.loads(artifacts["lifecycle"])
    original = lifecycle["records"][0]
    body = {key: value for key, value in original.items() if key not in {"record_digest", "signatures"}}
    bindings = [*body["signer_bindings"], {"signer_id": "recovery", "signature_profile_id": "deterministic-v1", "key_digest": "recovery-key"}]
    body["signer_bindings"] = bindings
    digest = sha256(b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(body)).hexdigest()
    record = {
        **body,
        "record_digest": digest,
        "signatures": [
            _signature("deterministic-v1", "bootstrap-key", digest.encode("ascii")).hex(),
            _signature("deterministic-v1", "recovery-key", digest.encode("ascii")).hex(),
        ],
    }
    root_body = {"authority_id": "authority", "records": [record]}
    root_digest = sha256(b"memorii:sia-traceability-trust-lifecycle-root:v1\0" + canonical_document(root_body)).hexdigest()
    artifacts["lifecycle"] = canonical_document({**root_body, "lifecycle_root_digest": root_digest, "signature": _signature("deterministic-v1", "bootstrap-key", root_digest.encode("ascii")).hex()})
    result = verify_release_gate(
        registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"],
        release_artifact=artifacts["release"], release_history_artifact=artifacts["history"],
        active_pointer_artifact=artifacts["pointer"], verifier_material=material, watermark_store=_watermark(),
        expected_release_roots=_fixture_expected_roots(json.loads(artifacts["release"])), now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(result, TraceabilityGateRejected)
    assert result.reason == "lifecycle_signatures_invalid"


@pytest.mark.parametrize("action", ["revoke", "compromise"])
def test_sia_t03_current_release_signer_must_remain_lifecycle_eligible_before_watermark(
    tmp_path: Path, action: str
) -> None:
    artifacts, material = _trusted_artifacts()
    release = json.loads(artifacts["release"])
    expected_roots = _fixture_expected_roots(release)
    bootstrap = json.loads(artifacts["bootstrap"])
    secondary_root = _signed(
        {
            "anchor_id": "secondary",
            "issuance_purpose": "semantic_ingestion_traceability_release_root",
            "canonical_profile_id": "memorii-sia-canonical-json-v1",
            "signature_profile_id": "deterministic-v1",
            "public_key_or_root_certificate_digest": "secondary-key",
            "target_authority_id": "authority",
            "effective_at": "2026-01-01T00:00:02Z",
        },
        domain=b"memorii:sia-traceability-bootstrap-anchor:v1",
        digest_field="anchor_digest",
        key="secondary-key",
    )
    secondary = json.loads(secondary_root)

    def lifecycle_record(body: dict[str, object], *, key: str) -> dict[str, object]:
        digest = sha256(
            b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(body)
        ).hexdigest()
        return {
            **body,
            "record_digest": digest,
            "signatures": [_signature("deterministic-v1", key, digest.encode("ascii")).hex()],
        }

    existing = json.loads(artifacts["lifecycle"])["records"]
    activate_body: dict[str, object] = {
        "issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle",
        "sequence": 2,
        "predecessor_record_digest": existing[-1]["record_digest"],
        "effective_at": "2026-01-01T00:00:02Z",
        "recorded_at": "2026-01-01T00:00:03Z",
        "action": "activate",
        "target_id": "secondary",
        "target_digest": secondary["anchor_digest"],
        "replacement_target_id": None,
        "replacement_target_digest": None,
        "signer_bindings": [
            {"signer_id": "bootstrap", "signature_profile_id": "deterministic-v1", "key_digest": "bootstrap-key"}
        ],
    }
    activate = lifecycle_record(activate_body, key="bootstrap-key")
    terminal_body: dict[str, object] = {
        "issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle",
        "sequence": 3,
        "predecessor_record_digest": activate["record_digest"],
        "effective_at": "2026-01-01T00:00:04Z",
        "recorded_at": "2026-01-01T00:00:05Z",
        "action": action,
        "target_id": "bootstrap",
        "target_digest": bootstrap["anchor_digest"],
        "replacement_target_id": None,
        "replacement_target_digest": None,
        "signer_bindings": [
            {"signer_id": "secondary", "signature_profile_id": "deterministic-v1", "key_digest": "secondary-key"}
        ],
    }
    terminal = lifecycle_record(terminal_body, key="secondary-key")
    root_body = {"authority_id": "authority", "records": [*existing, activate, terminal]}
    root_digest = sha256(
        b"memorii:sia-traceability-trust-lifecycle-root:v1\0" + canonical_document(root_body)
    ).hexdigest()
    artifacts["lifecycle"] = canonical_document(
        {
            **root_body,
            "lifecycle_root_digest": root_digest,
            "signature": _signature("deterministic-v1", "bootstrap-key", root_digest.encode("ascii")).hex(),
        }
    )
    release_body = {key: value for key, value in release.items() if key not in {"release_digest", "signature"}}
    artifacts["release"] = _signed(
        {**release_body, "issued_at": "2026-01-01T00:00:03Z"},
        domain=b"memorii:sia-traceability-release:v1",
        digest_field="release_digest",
        key="bootstrap-key",
    )
    current = json.loads(artifacts["release"])
    pointer = json.loads(artifacts["pointer"])
    pointer_body = {key: value for key, value in pointer.items() if key not in {"active_pointer_digest", "signature"}}
    artifacts["pointer"] = _signed(
        {
            **pointer_body,
            "release_digest": current["release_digest"],
            "issuer_key_or_certificate_digest": "secondary-key",
        },
        domain=b"memorii:sia-traceability-active-release-pointer:v1",
        digest_field="active_pointer_digest",
        key="secondary-key",
    )
    artifacts["history"] = _release_history(
        [_history_entry(release=current, sequence=1)], key="secondary-key"
    )
    material = VerifierHeldTrustMaterial(
        material.bootstrap_anchor_bytes,
        material.recovery_root_bytes,
        _verifier,
        material.recovery_policy_bytes,
        (secondary_root,),
    )
    path = tmp_path / "watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(store.provision(1, 1, "0" * 64), WatermarkAdvanced)
    record_before = path.read_bytes()
    seal = path.with_name(f"{path.name}.bootstrap-seal")
    seal_before = seal.read_bytes()
    result = verify_release_gate(
        registry=load_registry(_registry_path()),
        bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=artifacts["recovery"],
        lifecycle_artifact=artifacts["lifecycle"],
        release_artifact=artifacts["release"],
        release_history_artifact=artifacts["history"],
        active_pointer_artifact=artifacts["pointer"],
        verifier_material=material,
        watermark_store=store,
        expected_release_roots=expected_roots,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(result, TraceabilityGateRejected)
    assert result.reason == "release_signer_not_lifecycle_eligible"
    assert path.read_bytes() == record_before
    assert seal.read_bytes() == seal_before


def _lifecycle_with_secondary_terminal(
    artifacts: dict[str, bytes],
    material: VerifierHeldTrustMaterial,
    *,
    action: str,
    shared_bootstrap_key: bool = False,
    secondary_key_override: str | None = None,
) -> tuple[dict[str, bytes], VerifierHeldTrustMaterial, dict[str, object]]:
    """Add a signed ordinary root, then terminate it without changing bootstrap."""
    secondary_key = secondary_key_override or ("bootstrap-key" if shared_bootstrap_key else "secondary-key")
    secondary_root = _signed(
        {
            "anchor_id": "secondary",
            "issuance_purpose": "semantic_ingestion_traceability_release_root",
            "canonical_profile_id": "memorii-sia-canonical-json-v1",
            "signature_profile_id": "deterministic-v1",
            "public_key_or_root_certificate_digest": secondary_key,
            "target_authority_id": "authority",
            "effective_at": "2026-01-01T00:00:02Z",
        },
        domain=b"memorii:sia-traceability-bootstrap-anchor:v1",
        digest_field="anchor_digest",
        key=secondary_key,
    )
    secondary = json.loads(secondary_root)
    existing = json.loads(artifacts["lifecycle"])["records"]

    def record(body: dict[str, object], key: str) -> dict[str, object]:
        digest = sha256(
            b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(body)
        ).hexdigest()
        return {
            **body,
            "record_digest": digest,
            "signatures": [_signature("deterministic-v1", key, digest.encode("ascii")).hex()],
        }

    activate = record(
        {
            "issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle",
            "sequence": 2,
            "predecessor_record_digest": existing[-1]["record_digest"],
            "effective_at": "2026-01-01T00:00:02Z",
            "recorded_at": "2026-01-01T00:00:03Z",
            "action": "activate",
            "target_id": "secondary",
            "target_digest": secondary["anchor_digest"],
            "replacement_target_id": None,
            "replacement_target_digest": None,
            "signer_bindings": [
                {
                    "signer_id": "bootstrap",
                    "signature_profile_id": "deterministic-v1",
                    "key_digest": "bootstrap-key",
                }
            ],
        },
        "bootstrap-key",
    )
    terminal = record(
        {
            "issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle",
            "sequence": 3,
            "predecessor_record_digest": activate["record_digest"],
            "effective_at": "2026-01-01T00:00:04Z",
            "recorded_at": "2026-01-01T00:00:05Z",
            "action": action,
            "target_id": "secondary",
            "target_digest": secondary["anchor_digest"],
            "replacement_target_id": None,
            "replacement_target_digest": None,
            "signer_bindings": [
                {
                    "signer_id": "bootstrap",
                    "signature_profile_id": "deterministic-v1",
                    "key_digest": "bootstrap-key",
                }
            ],
        },
        "bootstrap-key",
    )
    root_body = {"authority_id": "authority", "records": [*existing, activate, terminal]}
    root_digest = sha256(
        b"memorii:sia-traceability-trust-lifecycle-root:v1\0" + canonical_document(root_body)
    ).hexdigest()
    artifacts["lifecycle"] = canonical_document(
        {
            **root_body,
            "lifecycle_root_digest": root_digest,
            "signature": _signature("deterministic-v1", secondary_key, root_digest.encode("ascii")).hex(),
        }
    )
    return (
        artifacts,
        VerifierHeldTrustMaterial(
            material.bootstrap_anchor_bytes,
            material.recovery_root_bytes,
            _verifier,
            material.recovery_policy_bytes,
            (secondary_root,),
        ),
        secondary,
    )


@pytest.mark.parametrize("action", ["revoke", "compromise"])
def test_sia_t03_terminal_ordinary_coordinate_cannot_reactivate_but_fresh_coordinate_can(
    tmp_path: Path, action: str
) -> None:
    artifacts, material = _trusted_artifacts()
    artifacts, material, secondary = _lifecycle_with_secondary_terminal(
        artifacts, material, action=action
    )
    lifecycle = json.loads(artifacts["lifecycle"])

    def record(body: dict[str, object], key: str) -> dict[str, object]:
        digest = sha256(
            b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(body)
        ).hexdigest()
        return {
            **body,
            "record_digest": digest,
            "signatures": [_signature("deterministic-v1", key, digest.encode("ascii")).hex()],
        }

    reactivation = record(
        {
            "issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle",
            "sequence": 4,
            "predecessor_record_digest": lifecycle["records"][-1]["record_digest"],
            "effective_at": "2026-01-01T00:00:06Z",
            "recorded_at": "2026-01-01T00:00:07Z",
            "action": "activate",
            "target_id": secondary["anchor_id"],
            "target_digest": secondary["anchor_digest"],
            "replacement_target_id": None,
            "replacement_target_digest": None,
            "signer_bindings": [
                {"signer_id": "bootstrap", "signature_profile_id": "deterministic-v1", "key_digest": "bootstrap-key"}
            ],
        },
        "bootstrap-key",
    )
    rejected_body = {
        "authority_id": "authority",
        "records": [*lifecycle["records"], reactivation],
    }
    rejected_digest = sha256(
        b"memorii:sia-traceability-trust-lifecycle-root:v1\0"
        + canonical_document(rejected_body)
    ).hexdigest()
    artifacts["lifecycle"] = canonical_document(
        {
            **rejected_body,
            "lifecycle_root_digest": rejected_digest,
            "signature": _signature(
                "deterministic-v1", "secondary-key", rejected_digest.encode("ascii")
            ).hex(),
        }
    )
    release = json.loads(artifacts["release"])
    path = tmp_path / f"{action}-ordinary-reactivation-watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(store.provision(1, 1, "0" * 64), WatermarkAdvanced)
    before = path.read_bytes()
    seal = path.with_name(f"{path.name}.bootstrap-seal")
    seal_before = seal.read_bytes()
    rejected = verify_release_gate(
        registry=load_registry(_registry_path()),
        bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=artifacts["recovery"],
        lifecycle_artifact=artifacts["lifecycle"],
        release_artifact=artifacts["release"],
        release_history_artifact=artifacts["history"],
        active_pointer_artifact=artifacts["pointer"],
        verifier_material=material,
        watermark_store=store,
        expected_release_roots=_fixture_expected_roots(release),
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(rejected, TraceabilityGateRejected)
    assert rejected.reason == "lifecycle_activation_not_independently_provisioned"
    assert path.read_bytes() == before
    assert seal.read_bytes() == seal_before

    fresh_artifacts, fresh_material = _trusted_artifacts()
    fresh_root = _signed(
        {
            "anchor_id": "fresh-secondary",
            "issuance_purpose": "semantic_ingestion_traceability_release_root",
            "canonical_profile_id": "memorii-sia-canonical-json-v1",
            "signature_profile_id": "deterministic-v1",
            "public_key_or_root_certificate_digest": "fresh-secondary-key",
            "target_authority_id": "authority",
            "effective_at": "2026-01-01T00:00:02Z",
        },
        domain=b"memorii:sia-traceability-bootstrap-anchor:v1",
        digest_field="anchor_digest",
        key="fresh-secondary-key",
    )
    fresh = json.loads(fresh_root)
    genesis = json.loads(fresh_artifacts["lifecycle"])["records"]
    fresh_activation = record(
        {
            "issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle",
            "sequence": 2,
            "predecessor_record_digest": genesis[-1]["record_digest"],
            "effective_at": "2026-01-01T00:00:02Z",
            "recorded_at": "2026-01-01T00:00:03Z",
            "action": "activate",
            "target_id": fresh["anchor_id"],
            "target_digest": fresh["anchor_digest"],
            "replacement_target_id": None,
            "replacement_target_digest": None,
            "signer_bindings": [
                {"signer_id": "bootstrap", "signature_profile_id": "deterministic-v1", "key_digest": "bootstrap-key"}
            ],
        },
        "bootstrap-key",
    )
    fresh_body = {"authority_id": "authority", "records": [*genesis, fresh_activation]}
    fresh_digest = sha256(
        b"memorii:sia-traceability-trust-lifecycle-root:v1\0"
        + canonical_document(fresh_body)
    ).hexdigest()
    fresh_artifacts["lifecycle"] = canonical_document(
        {
            **fresh_body,
            "lifecycle_root_digest": fresh_digest,
            "signature": _signature(
                "deterministic-v1", "fresh-secondary-key", fresh_digest.encode("ascii")
            ).hex(),
        }
    )
    prior_release = json.loads(fresh_artifacts["release"])
    release_body = {
        key: value
        for key, value in prior_release.items()
        if key not in {"release_digest", "signature"}
    }
    fresh_artifacts["release"] = _signed(
        {
            **release_body,
            "issuer_key_or_certificate_digest": "fresh-secondary-key",
            "issued_at": "2026-01-01T00:00:04Z",
        },
        domain=b"memorii:sia-traceability-release:v1",
        digest_field="release_digest",
        key="fresh-secondary-key",
    )
    current = json.loads(fresh_artifacts["release"])
    pointer = json.loads(fresh_artifacts["pointer"])
    pointer_body = {
        key: value
        for key, value in pointer.items()
        if key not in {"active_pointer_digest", "signature"}
    }
    fresh_artifacts["pointer"] = _signed(
        {
            **pointer_body,
            "release_digest": current["release_digest"],
            "issuer_key_or_certificate_digest": "fresh-secondary-key",
        },
        domain=b"memorii:sia-traceability-active-release-pointer:v1",
        digest_field="active_pointer_digest",
        key="fresh-secondary-key",
    )
    fresh_artifacts["history"] = _release_history(
        [_history_entry(release=current, sequence=1)], key="fresh-secondary-key"
    )
    accepted = verify_release_gate(
        registry=load_registry(_registry_path()),
        bootstrap_artifact=fresh_artifacts["bootstrap"],
        recovery_artifact=fresh_artifacts["recovery"],
        lifecycle_artifact=fresh_artifacts["lifecycle"],
        release_artifact=fresh_artifacts["release"],
        release_history_artifact=fresh_artifacts["history"],
        active_pointer_artifact=fresh_artifacts["pointer"],
        verifier_material=VerifierHeldTrustMaterial(
            fresh_material.bootstrap_anchor_bytes,
            fresh_material.recovery_root_bytes,
            _verifier,
            fresh_material.recovery_policy_bytes,
            (fresh_root,),
        ),
        watermark_store=_watermark(),
        expected_release_roots=_fixture_expected_roots(current),
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(accepted, TraceabilityGateAuthorized)


@pytest.mark.parametrize("action", ["revoke", "compromise"])
def test_sia_t03_terminal_ordinary_root_cannot_be_reinstalled_as_rotation_replacement(
    tmp_path: Path, action: str
) -> None:
    artifacts, material = _trusted_artifacts()
    artifacts, material, secondary = _lifecycle_with_secondary_terminal(
        artifacts, material, action=action
    )
    lifecycle = json.loads(artifacts["lifecycle"])
    bootstrap = json.loads(artifacts["bootstrap"])
    rotate_body: dict[str, object] = {
        "issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle",
        "sequence": 4,
        "predecessor_record_digest": lifecycle["records"][-1]["record_digest"],
        "effective_at": "2026-01-01T00:00:06Z",
        "recorded_at": "2026-01-01T00:00:07Z",
        "action": "rotate",
        "target_id": "bootstrap",
        "target_digest": bootstrap["anchor_digest"],
        "replacement_target_id": secondary["anchor_id"],
        "replacement_target_digest": secondary["anchor_digest"],
        "replacement_signature_profile_id": "deterministic-v1",
        "replacement_key_digest": "secondary-key",
        "signer_bindings": [
            {"signer_id": "bootstrap", "signature_profile_id": "deterministic-v1", "key_digest": "bootstrap-key"}
        ],
    }
    rotate_digest = sha256(
        b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(rotate_body)
    ).hexdigest()
    rotate = {
        **rotate_body,
        "record_digest": rotate_digest,
        "signatures": [_signature("deterministic-v1", "bootstrap-key", rotate_digest.encode("ascii")).hex()],
    }
    root_body = {"authority_id": "authority", "records": [*lifecycle["records"], rotate]}
    root_digest = sha256(
        b"memorii:sia-traceability-trust-lifecycle-root:v1\0" + canonical_document(root_body)
    ).hexdigest()
    artifacts["lifecycle"] = canonical_document(
        {
            **root_body,
            "lifecycle_root_digest": root_digest,
            "signature": _signature("deterministic-v1", "secondary-key", root_digest.encode("ascii")).hex(),
        }
    )
    release = json.loads(artifacts["release"])
    release_body = {key: value for key, value in release.items() if key not in {"release_digest", "signature"}}
    artifacts["release"] = _signed(
        {**release_body, "issuer_key_or_certificate_digest": "secondary-key", "issued_at": "2026-01-01T00:00:08Z"},
        domain=b"memorii:sia-traceability-release:v1",
        digest_field="release_digest",
        key="secondary-key",
    )
    current = json.loads(artifacts["release"])
    pointer = json.loads(artifacts["pointer"])
    pointer_body = {key: value for key, value in pointer.items() if key not in {"active_pointer_digest", "signature"}}
    artifacts["pointer"] = _signed(
        {**pointer_body, "release_digest": current["release_digest"], "issuer_key_or_certificate_digest": "secondary-key"},
        domain=b"memorii:sia-traceability-active-release-pointer:v1",
        digest_field="active_pointer_digest",
        key="secondary-key",
    )
    artifacts["history"] = _release_history(
        [_history_entry(release=current, sequence=1)], key="secondary-key"
    )
    path = tmp_path / f"{action}-reinstall-watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(store.provision(1, 1, "0" * 64), WatermarkAdvanced)
    record_before = path.read_bytes()
    seal = path.with_name(f"{path.name}.bootstrap-seal")
    seal_before = seal.read_bytes()
    result = verify_release_gate(
        registry=load_registry(_registry_path()),
        bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=artifacts["recovery"],
        lifecycle_artifact=artifacts["lifecycle"],
        release_artifact=artifacts["release"],
        release_history_artifact=artifacts["history"],
        active_pointer_artifact=artifacts["pointer"],
        verifier_material=material,
        watermark_store=store,
        expected_release_roots=_fixture_expected_roots(current),
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(result, TraceabilityGateRejected)
    assert result.reason == "lifecycle_replacement_coordinate_reused"
    assert path.read_bytes() == record_before
    assert seal.read_bytes() == seal_before

    # Exercise the distinct threshold-recovery path too.  The fixture policy
    # has an exact threshold of one independently provisioned recovery root;
    # the recovery record is fully signed even though replay must reject the
    # previously terminal ordinary replacement before release verification.
    recovery_artifacts, recovery_material = _trusted_artifacts()
    recovery_artifacts, recovery_material, old_secondary = _lifecycle_with_secondary_terminal(
        recovery_artifacts, recovery_material, action=action
    )
    recovery_lifecycle = json.loads(recovery_artifacts["lifecycle"])
    recovery_root = json.loads(recovery_artifacts["recovery"])
    recovery_bootstrap = json.loads(recovery_artifacts["bootstrap"])

    def signed_record(body: dict[str, object], key: str) -> dict[str, object]:
        digest = sha256(
            b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(body)
        ).hexdigest()
        return {
            **body,
            "record_digest": digest,
            "signatures": [_signature("deterministic-v1", key, digest.encode("ascii")).hex()],
        }

    activate_recovery = signed_record(
        {
            "issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle",
            "sequence": 4,
            "predecessor_record_digest": recovery_lifecycle["records"][-1]["record_digest"],
            "effective_at": "2026-01-01T00:00:06Z",
            "recorded_at": "2026-01-01T00:00:07Z",
            "action": "activate",
            "target_id": recovery_root["recovery_root_id"],
            "target_digest": recovery_root["recovery_root_digest"],
            "replacement_target_id": None,
            "replacement_target_digest": None,
            "signer_bindings": [
                {"signer_id": "bootstrap", "signature_profile_id": "deterministic-v1", "key_digest": "bootstrap-key"}
            ],
        },
        "bootstrap-key",
    )
    recover_body: dict[str, object] = {
        "issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle",
        "sequence": 5,
        "predecessor_record_digest": activate_recovery["record_digest"],
        "effective_at": "2026-01-01T00:00:08Z",
        "recorded_at": "2026-01-01T00:00:09Z",
        "action": "recover",
        "target_id": recovery_bootstrap["anchor_id"],
        "target_digest": recovery_bootstrap["anchor_digest"],
        "replacement_target_id": old_secondary["anchor_id"],
        "replacement_target_digest": old_secondary["anchor_digest"],
        "replacement_signature_profile_id": "deterministic-v1",
        "replacement_key_digest": "secondary-key",
        "signer_bindings": [
            {
                "signer_id": "recovery",
                "signature_profile_id": "deterministic-v1",
                "key_digest": "recovery-key",
                "recovery_root_digest": recovery_root["recovery_root_digest"],
            }
        ],
    }
    recover = signed_record(recover_body, "recovery-key")
    recovery_root_body = {
        "authority_id": "authority",
        "records": [*recovery_lifecycle["records"], activate_recovery, recover],
    }
    recovery_lifecycle_digest = sha256(
        b"memorii:sia-traceability-trust-lifecycle-root:v1\0"
        + canonical_document(recovery_root_body)
    ).hexdigest()
    recovery_artifacts["lifecycle"] = canonical_document(
        {
            **recovery_root_body,
            "lifecycle_root_digest": recovery_lifecycle_digest,
            "signature": _signature("deterministic-v1", "secondary-key", recovery_lifecycle_digest.encode("ascii")).hex(),
        }
    )
    recovery_path = tmp_path / f"{action}-recover-reinstall-watermark.json"
    recovery_store = FileTraceabilityReleaseWatermarkStore(recovery_path)
    assert isinstance(recovery_store.provision(1, 1, "0" * 64), WatermarkAdvanced)
    recovery_before = recovery_path.read_bytes()
    recovery_seal = recovery_path.with_name(f"{recovery_path.name}.bootstrap-seal")
    recovery_seal_before = recovery_seal.read_bytes()
    recovery_release = json.loads(recovery_artifacts["release"])
    recovery_result = verify_release_gate(
        registry=load_registry(_registry_path()),
        bootstrap_artifact=recovery_artifacts["bootstrap"],
        recovery_artifact=recovery_artifacts["recovery"],
        lifecycle_artifact=recovery_artifacts["lifecycle"],
        release_artifact=recovery_artifacts["release"],
        release_history_artifact=recovery_artifacts["history"],
        active_pointer_artifact=recovery_artifacts["pointer"],
        verifier_material=recovery_material,
        watermark_store=recovery_store,
        expected_release_roots=_fixture_expected_roots(recovery_release),
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(recovery_result, TraceabilityGateRejected)
    assert recovery_result.reason == "lifecycle_replacement_coordinate_reused"
    assert recovery_path.read_bytes() == recovery_before
    assert recovery_seal.read_bytes() == recovery_seal_before


@pytest.mark.parametrize("action", ["revoke", "compromise"])
def test_sia_t03_flat_signer_alias_between_provisioned_roots_rejects_closed(
    tmp_path: Path, action: str
) -> None:
    artifacts, material = _trusted_artifacts()
    artifacts, material, _ = _lifecycle_with_secondary_terminal(
        artifacts, material, action=action, shared_bootstrap_key=True
    )
    release = json.loads(artifacts["release"])
    expected_roots = _fixture_expected_roots(release)
    path = tmp_path / "watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(store.provision(1, 1, "0" * 64), WatermarkAdvanced)
    record_before = path.read_bytes()
    seal = path.with_name(f"{path.name}.bootstrap-seal")
    seal_before = seal.read_bytes()
    result = verify_release_gate(
        registry=load_registry(_registry_path()),
        bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=artifacts["recovery"],
        lifecycle_artifact=artifacts["lifecycle"],
        release_artifact=artifacts["release"],
        release_history_artifact=artifacts["history"],
        active_pointer_artifact=artifacts["pointer"],
        verifier_material=material,
        watermark_store=store,
        expected_release_roots=expected_roots,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(result, TraceabilityGateRejected)
    assert result.reason == "ambiguous_lifecycle_signer_coordinate"
    assert path.read_bytes() == record_before
    assert seal.read_bytes() == seal_before


def test_sia_t03_recovery_root_sharing_bootstrap_signer_rejects_closed() -> None:
    artifacts, material = _trusted_artifacts()
    bootstrap = json.loads(artifacts["bootstrap"])
    shared_recovery = _signed(
        {
            "recovery_root_id": "recovery-shared",
            "issuance_purpose": "semantic_ingestion_traceability_recovery_root",
            "canonical_profile_id": "memorii-sia-canonical-json-v1",
            "signature_profile_id": "deterministic-v1",
            "public_key_or_root_certificate_digest": "bootstrap-key",
            "target_authority_id": "authority",
        },
        domain=b"memorii:sia-traceability-recovery-root:v1",
        digest_field="recovery_root_digest",
        key="bootstrap-key",
    )
    recovery = json.loads(shared_recovery)
    policy = _signed(
        {
            "issuance_purpose": "semantic_ingestion_traceability_recovery_policy",
            "canonical_profile_id": "memorii-sia-canonical-json-v1",
            "signature_profile_id": "deterministic-v1",
            "policy_signer_key_or_certificate_digest": "bootstrap-key",
            "active_bootstrap_anchor_digest": bootstrap["anchor_digest"],
            "eligible_recovery_root_digests": [recovery["recovery_root_digest"]],
            "threshold": 1,
        },
        domain=b"memorii:sia-traceability-recovery-policy:v1",
        digest_field="recovery_policy_digest",
    )
    result = verify_release_gate(
        registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=shared_recovery, lifecycle_artifact=artifacts["lifecycle"],
        release_artifact=artifacts["release"], release_history_artifact=artifacts["history"],
        active_pointer_artifact=artifacts["pointer"],
        verifier_material=VerifierHeldTrustMaterial(artifacts["bootstrap"], (shared_recovery,), _verifier, policy),
        watermark_store=_watermark(), expected_release_roots=_fixture_expected_roots(json.loads(artifacts["release"])),
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(result, TraceabilityGateRejected)
    assert result.reason == "ambiguous_lifecycle_signer_coordinate"


def test_sia_t03_flat_signer_alias_between_recovery_and_successor_rejects_closed() -> None:
    artifacts, material = _trusted_artifacts()
    artifacts, material, _ = _lifecycle_with_secondary_terminal(
        artifacts, material, action="revoke", secondary_key_override="recovery-key"
    )
    result = verify_release_gate(
        registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"],
        release_artifact=artifacts["release"], release_history_artifact=artifacts["history"],
        active_pointer_artifact=artifacts["pointer"], verifier_material=material,
        watermark_store=_watermark(), expected_release_roots=_fixture_expected_roots(json.loads(artifacts["release"])),
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(result, TraceabilityGateRejected)
    assert result.reason == "ambiguous_lifecycle_signer_coordinate"


@pytest.mark.parametrize("action", ["revoke", "compromise"])
def test_sia_t03_terminal_lifecycle_root_rejects_cryptographically_valid_alternate_signer(
    tmp_path: Path, action: str
) -> None:
    artifacts, material = _trusted_artifacts()
    artifacts, material, _ = _lifecycle_with_secondary_terminal(artifacts, material, action=action)
    lifecycle = json.loads(artifacts["lifecycle"])
    digest = lifecycle["lifecycle_root_digest"]
    artifacts["lifecycle"] = canonical_document(
        {**lifecycle, "signature": _signature("deterministic-v1", "bootstrap-key", digest.encode("ascii")).hex()}
    )
    path = tmp_path / "watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(store.provision(1, 1, "0" * 64), WatermarkAdvanced)
    record_before = path.read_bytes()
    seal = path.with_name(f"{path.name}.bootstrap-seal")
    seal_before = seal.read_bytes()
    result = verify_release_gate(
        registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"],
        release_artifact=artifacts["release"], release_history_artifact=artifacts["history"],
        active_pointer_artifact=artifacts["pointer"], verifier_material=material,
        watermark_store=store, expected_release_roots=_fixture_expected_roots(json.loads(artifacts["release"])),
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(result, TraceabilityGateRejected)
    assert result.reason == "signature_invalid"
    assert path.read_bytes() == record_before
    assert seal.read_bytes() == seal_before


def test_sia_t03_activation_lifecycle_root_rejects_cryptographically_valid_alternate_signer(
    tmp_path: Path,
) -> None:
    artifacts, material = _trusted_artifacts()
    lifecycle = json.loads(artifacts["lifecycle"])
    digest = lifecycle["lifecycle_root_digest"]
    artifacts["lifecycle"] = canonical_document(
        {**lifecycle, "signature": _signature("deterministic-v1", "recovery-key", digest.encode("ascii")).hex()}
    )
    path = tmp_path / "watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(store.provision(1, 1, "0" * 64), WatermarkAdvanced)
    before, seal = path.read_bytes(), path.with_name(f"{path.name}.bootstrap-seal")
    seal_before = seal.read_bytes()
    result = verify_release_gate(
        registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"],
        release_artifact=artifacts["release"], release_history_artifact=artifacts["history"],
        active_pointer_artifact=artifacts["pointer"], verifier_material=material,
        watermark_store=store, expected_release_roots=_fixture_expected_roots(json.loads(artifacts["release"])),
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(result, TraceabilityGateRejected)
    assert result.reason == "signature_invalid"
    assert path.read_bytes() == before
    assert seal.read_bytes() == seal_before


@pytest.mark.parametrize("action", ["revoke", "compromise"])
def test_sia_t03_current_pointer_signer_must_remain_lifecycle_eligible_before_watermark(
    tmp_path: Path, action: str
) -> None:
    artifacts, material = _trusted_artifacts()
    artifacts, material, _ = _lifecycle_with_secondary_terminal(
        artifacts, material, action=action
    )
    release = json.loads(artifacts["release"])
    expected_roots = _fixture_expected_roots(release)
    pointer = json.loads(artifacts["pointer"])
    pointer_body = {
        key: value for key, value in pointer.items() if key not in {"active_pointer_digest", "signature"}
    }
    artifacts["pointer"] = _signed(
        {
            **pointer_body,
            "issuer_key_or_certificate_digest": "secondary-key",
            "issued_at": "2026-01-01T00:00:03Z",
        },
        domain=b"memorii:sia-traceability-active-release-pointer:v1",
        digest_field="active_pointer_digest",
        key="secondary-key",
    )
    path = tmp_path / "watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(store.provision(1, 1, "0" * 64), WatermarkAdvanced)
    record_before = path.read_bytes()
    seal = path.with_name(f"{path.name}.bootstrap-seal")
    seal_before = seal.read_bytes()
    result = verify_release_gate(
        registry=load_registry(_registry_path()),
        bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=artifacts["recovery"],
        lifecycle_artifact=artifacts["lifecycle"],
        release_artifact=artifacts["release"],
        release_history_artifact=artifacts["history"],
        active_pointer_artifact=artifacts["pointer"],
        verifier_material=material,
        watermark_store=store,
        expected_release_roots=expected_roots,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(result, TraceabilityGateRejected)
    assert result.reason == "active_pointer_signer_not_lifecycle_eligible"
    assert path.read_bytes() == record_before
    assert seal.read_bytes() == seal_before


@pytest.mark.parametrize("action", ["revoke", "compromise"])
def test_sia_t03_current_history_signer_must_remain_lifecycle_eligible_before_watermark(
    tmp_path: Path, action: str
) -> None:
    artifacts, material = _trusted_artifacts()
    artifacts, material, _ = _lifecycle_with_secondary_terminal(
        artifacts, material, action=action
    )
    release = json.loads(artifacts["release"])
    expected_roots = _fixture_expected_roots(release)
    artifacts["history"] = _release_history(
        [_history_entry(release=release, sequence=1)], key="secondary-key"
    )
    path = tmp_path / "watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(store.provision(1, 1, "0" * 64), WatermarkAdvanced)
    record_before = path.read_bytes()
    seal = path.with_name(f"{path.name}.bootstrap-seal")
    seal_before = seal.read_bytes()
    result = verify_release_gate(
        registry=load_registry(_registry_path()),
        bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=artifacts["recovery"],
        lifecycle_artifact=artifacts["lifecycle"],
        release_artifact=artifacts["release"],
        release_history_artifact=artifacts["history"],
        active_pointer_artifact=artifacts["pointer"],
        verifier_material=material,
        watermark_store=store,
        expected_release_roots=expected_roots,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(result, TraceabilityGateRejected)
    assert result.reason == "release_history_signer_not_lifecycle_eligible"
    assert path.read_bytes() == record_before
    assert seal.read_bytes() == seal_before


def test_sia_t03_release_gate_requires_threshold_recovery_and_authorizes_recovered_signer(
    tmp_path: Path,
) -> None:
    artifacts, material = _trusted_artifacts()
    expected_roots = _fixture_expected_roots(json.loads(artifacts["release"]))
    bootstrap = json.loads(artifacts["bootstrap"])
    first_recovery = json.loads(artifacts["recovery"])
    second_recovery_bytes = _signed({
        "recovery_root_id": "recovery-two", "issuance_purpose": "semantic_ingestion_traceability_recovery_root",
        "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1",
        "public_key_or_root_certificate_digest": "recovery-two-key", "target_authority_id": "authority",
        "effective_at": "2026-01-01T00:00:02Z",
    }, domain=b"memorii:sia-traceability-recovery-root:v1", digest_field="recovery_root_digest", key="recovery-two-key")
    second_recovery = json.loads(second_recovery_bytes)
    recovered_root = _signed({"anchor_id": "bootstrap-recovered", "issuance_purpose": "semantic_ingestion_traceability_release_root", "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1", "public_key_or_root_certificate_digest": "recovered-key", "target_authority_id": "authority", "effective_at": "2026-01-01T00:00:02Z"}, domain=b"memorii:sia-traceability-bootstrap-anchor:v1", digest_field="anchor_digest", key="recovered-key")
    recovered_digest = json.loads(recovered_root)["anchor_digest"]
    policy = _signed({
        "issuance_purpose": "semantic_ingestion_traceability_recovery_policy", "canonical_profile_id": "memorii-sia-canonical-json-v1",
        "signature_profile_id": "deterministic-v1", "policy_signer_key_or_certificate_digest": "bootstrap-key",
        "active_bootstrap_anchor_digest": bootstrap["anchor_digest"],
        "eligible_recovery_root_digests": [first_recovery["recovery_root_digest"], second_recovery["recovery_root_digest"]], "threshold": 2,
    }, domain=b"memorii:sia-traceability-recovery-policy:v1", digest_field="recovery_policy_digest")
    lifecycle = json.loads(artifacts["lifecycle"])

    def activation_record(
        *, sequence: int, predecessor: str, effective_at: str, recorded_at: str,
        root_id: str, root_digest: str,
    ) -> dict[str, object]:
        activation_body = {
            "issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle",
            "sequence": sequence, "predecessor_record_digest": predecessor,
            "effective_at": effective_at, "recorded_at": recorded_at, "action": "activate",
            "target_id": root_id, "target_digest": root_digest,
            "replacement_target_id": None, "replacement_target_digest": None,
            "signer_bindings": [{"signer_id": "bootstrap", "signature_profile_id": "deterministic-v1", "key_digest": "bootstrap-key"}],
        }
        activation_digest = sha256(
            b"memorii:sia-traceability-lifecycle-record:v1\0"
            + canonical_document(activation_body)
        ).hexdigest()
        return {
            **activation_body, "record_digest": activation_digest,
            "signatures": [_signature("deterministic-v1", "bootstrap-key", activation_digest.encode("ascii")).hex()],
        }

    genesis_records = list(lifecycle["records"])
    first_activation = activation_record(
        sequence=2, predecessor=genesis_records[-1]["record_digest"],
        effective_at="2026-01-01T00:00:02Z", recorded_at="2026-01-01T00:00:03Z",
        root_id="recovery", root_digest=first_recovery["recovery_root_digest"],
    )
    second_activation = activation_record(
        sequence=3, predecessor=first_activation["record_digest"],
        effective_at="2026-01-01T00:00:03Z", recorded_at="2026-01-01T00:00:04Z",
        root_id="recovery-two", root_digest=second_recovery["recovery_root_digest"],
    )
    lifecycle["records"] = [*genesis_records, first_activation, second_activation]
    body = {
        "issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle", "sequence": 4,
        "predecessor_record_digest": lifecycle["records"][-1]["record_digest"], "effective_at": "2026-01-01T00:00:04Z",
        "recorded_at": "2026-01-01T00:00:05Z", "action": "recover", "target_id": "bootstrap",
        "target_digest": bootstrap["anchor_digest"], "replacement_target_id": "bootstrap-recovered",
        "replacement_target_digest": recovered_digest, "replacement_signature_profile_id": "deterministic-v1",
        "replacement_key_digest": "recovered-key", "signer_bindings": [
            {"signer_id": "recovery-one", "signature_profile_id": "deterministic-v1", "key_digest": "recovery-key", "recovery_root_digest": first_recovery["recovery_root_digest"]},
            {"signer_id": "recovery-two", "signature_profile_id": "deterministic-v1", "key_digest": "recovery-two-key", "recovery_root_digest": second_recovery["recovery_root_digest"]},
        ],
    }
    digest = sha256(b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(body)).hexdigest()
    record = {**body, "record_digest": digest, "signatures": [_signature("deterministic-v1", "recovery-key", digest.encode("ascii")).hex(), _signature("deterministic-v1", "recovery-two-key", digest.encode("ascii")).hex()]}
    root_body = {"authority_id": "authority", "records": [*lifecycle["records"], record]}
    root_digest = sha256(b"memorii:sia-traceability-trust-lifecycle-root:v1\0" + canonical_document(root_body)).hexdigest()
    artifacts["lifecycle"] = canonical_document({**root_body, "lifecycle_root_digest": root_digest, "signature": _signature("deterministic-v1", "bootstrap-key", root_digest.encode("ascii")).hex()})
    release = json.loads(artifacts["release"])
    release_body = {key: value for key, value in release.items() if key not in {"release_digest", "signature"}}
    artifacts["release"] = _signed({**release_body, "issuer_key_or_certificate_digest": "recovered-key", "issued_at": "2026-01-01T00:00:04Z"}, domain=b"memorii:sia-traceability-release:v1", digest_field="release_digest", key="recovered-key")
    pointer = json.loads(artifacts["pointer"])
    pointer_body = {key: value for key, value in pointer.items() if key not in {"active_pointer_digest", "signature"}}
    artifacts["pointer"] = _signed({**pointer_body, "release_digest": json.loads(artifacts["release"])["release_digest"], "issuer_key_or_certificate_digest": "recovered-key"}, domain=b"memorii:sia-traceability-active-release-pointer:v1", digest_field="active_pointer_digest", key="recovered-key")
    threshold_material = VerifierHeldTrustMaterial(artifacts["bootstrap"], (artifacts["recovery"], second_recovery_bytes), _verifier, policy, (recovered_root,))
    artifacts["history"] = _release_history([_history_entry(release=json.loads(artifacts["release"]), sequence=1)], key="recovered-key")

    def rejects_recovery_record(
        name: str, record_body: dict[str, object], signatures: list[str], expected: str,
        material: VerifierHeldTrustMaterial = threshold_material, extra_recoveries: tuple[bytes, ...] = (second_recovery_bytes,),
        prefix_records: list[dict[str, object]] | None = None,
    ) -> None:
        record_digest = sha256(
            b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(record_body)
        ).hexdigest()
        candidate_record = {
            **record_body, "record_digest": record_digest, "signatures": signatures,
        }
        candidate_root_body = {
            "authority_id": "authority",
            "records": [*(prefix_records or lifecycle["records"]), candidate_record],
        }
        candidate_root_digest = sha256(
            b"memorii:sia-traceability-trust-lifecycle-root:v1\0"
            + canonical_document(candidate_root_body)
        ).hexdigest()
        candidate_lifecycle = canonical_document(
            {
                **candidate_root_body,
                "lifecycle_root_digest": candidate_root_digest,
                "signature": _signature(
                    "deterministic-v1", "bootstrap-key", candidate_root_digest.encode("ascii")
                ).hex(),
            }
        )
        path = tmp_path / f"{name}-watermark.json"
        store = FileTraceabilityReleaseWatermarkStore(path)
        assert isinstance(store.provision(1, 1, "0" * 64), WatermarkAdvanced)
        record_before = path.read_bytes()
        seal = path.with_name(f"{path.name}.bootstrap-seal")
        seal_before = seal.read_bytes()
        outcome = verify_release_gate(
            registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"],
            recovery_artifact=artifacts["recovery"], recovery_artifacts=extra_recoveries,
            lifecycle_artifact=candidate_lifecycle, release_artifact=artifacts["release"],
            release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"],
            verifier_material=material, watermark_store=store, expected_release_roots=expected_roots,
            now=datetime(2026, 1, 2, tzinfo=UTC),
        )
        assert isinstance(outcome, TraceabilityGateRejected)
        assert outcome.reason == expected
        assert path.read_bytes() == record_before
        assert seal.read_bytes() == seal_before

    unactivated_body = {
        **body,
        "sequence": 2,
        "predecessor_record_digest": genesis_records[-1]["record_digest"],
        "effective_at": "2026-01-01T00:00:02Z",
        "recorded_at": "2026-01-01T00:00:03Z",
    }
    unactivated_digest = sha256(
        b"memorii:sia-traceability-lifecycle-record:v1\0"
        + canonical_document(unactivated_body)
    ).hexdigest()
    rejects_recovery_record(
        "unactivated-recovery-roots", unactivated_body,
        [_signature("deterministic-v1", "recovery-key", unactivated_digest.encode("ascii")).hex(), _signature("deterministic-v1", "recovery-two-key", unactivated_digest.encode("ascii")).hex()],
        "recovery_root_not_lifecycle_eligible", prefix_records=genesis_records,
    )
    rotate_recovery_target_body = {
        **body,
        "action": "rotate",
        "target_id": "recovery",
        "target_digest": first_recovery["recovery_root_digest"],
        "signer_bindings": [
            {
                "signer_id": "bootstrap",
                "signature_profile_id": "deterministic-v1",
                "key_digest": "bootstrap-key",
            }
        ],
    }
    rotate_recovery_target_digest = sha256(
        b"memorii:sia-traceability-lifecycle-record:v1\0"
        + canonical_document(rotate_recovery_target_body)
    ).hexdigest()
    rejects_recovery_record(
        "rotate-recovery-target",
        rotate_recovery_target_body,
        [
            _signature(
                "deterministic-v1",
                "bootstrap-key",
                rotate_recovery_target_digest.encode("ascii"),
            ).hex()
        ],
        "lifecycle_target_not_ordinary_authority",
    )
    recover_recovery_target_body = {
        **body,
        "target_id": "recovery",
        "target_digest": first_recovery["recovery_root_digest"],
    }
    recover_recovery_target_digest = sha256(
        b"memorii:sia-traceability-lifecycle-record:v1\0"
        + canonical_document(recover_recovery_target_body)
    ).hexdigest()
    rejects_recovery_record(
        "recover-recovery-target",
        recover_recovery_target_body,
        [
            _signature(
                "deterministic-v1",
                "recovery-key",
                recover_recovery_target_digest.encode("ascii"),
            ).hex(),
            _signature(
                "deterministic-v1",
                "recovery-two-key",
                recover_recovery_target_digest.encode("ascii"),
            ).hex(),
        ],
        "lifecycle_target_not_ordinary_authority",
    )
    duplicate_activation = activation_record(
        sequence=4, predecessor=lifecycle["records"][-1]["record_digest"],
        effective_at="2026-01-01T00:00:04Z", recorded_at="2026-01-01T00:00:05Z",
        root_id="recovery", root_digest=first_recovery["recovery_root_digest"],
    )
    rejects_recovery_record(
        "duplicate-recovery-activation",
        {key: value for key, value in duplicate_activation.items() if key not in {"record_digest", "signatures"}},
        duplicate_activation["signatures"],
        "lifecycle_activation_duplicate_or_stale",
    )
    for terminal_action in ("revoke", "compromise"):
        terminal_body = {
            "issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle",
            "sequence": 4, "predecessor_record_digest": lifecycle["records"][-1]["record_digest"],
            "effective_at": "2026-01-01T00:00:04Z", "recorded_at": "2026-01-01T00:00:05Z",
            "action": terminal_action, "target_id": "recovery",
            "target_digest": first_recovery["recovery_root_digest"],
            "replacement_target_id": None, "replacement_target_digest": None,
            "signer_bindings": [{"signer_id": "bootstrap", "signature_profile_id": "deterministic-v1", "key_digest": "bootstrap-key"}],
        }
        terminal_digest = sha256(
            b"memorii:sia-traceability-lifecycle-record:v1\0"
            + canonical_document(terminal_body)
        ).hexdigest()
        terminal_record = {
            **terminal_body, "record_digest": terminal_digest,
            "signatures": [_signature("deterministic-v1", "bootstrap-key", terminal_digest.encode("ascii")).hex()],
        }
        terminated_prefix = [*lifecycle["records"], terminal_record]
        later_recovery = {
            **body, "sequence": 5, "predecessor_record_digest": terminal_digest,
            "effective_at": "2026-01-01T00:00:05Z", "recorded_at": "2026-01-01T00:00:06Z",
        }
        later_digest = sha256(
            b"memorii:sia-traceability-lifecycle-record:v1\0"
            + canonical_document(later_recovery)
        ).hexdigest()
        rejects_recovery_record(
            f"{terminal_action}-then-recover", later_recovery,
            [_signature("deterministic-v1", "recovery-key", later_digest.encode("ascii")).hex(), _signature("deterministic-v1", "recovery-two-key", later_digest.encode("ascii")).hex()],
            "recovery_root_not_lifecycle_eligible", prefix_records=terminated_prefix,
        )
        reactivation = activation_record(
            sequence=5, predecessor=terminal_digest,
            effective_at="2026-01-01T00:00:05Z", recorded_at="2026-01-01T00:00:06Z",
            root_id="recovery", root_digest=first_recovery["recovery_root_digest"],
        )
        rejects_recovery_record(
            f"{terminal_action}-then-reactivate",
            {key: value for key, value in reactivation.items() if key not in {"record_digest", "signatures"}},
            reactivation["signatures"], "lifecycle_activation_duplicate_or_stale",
            prefix_records=terminated_prefix,
        )

    attacker_policy_body = {
        **{key: value for key, value in json.loads(policy).items() if key not in {"recovery_policy_digest", "signature"}},
        "public_key_or_root_certificate_digest": "attacker-key",
    }
    attacker_policy = _signed(
        attacker_policy_body, domain=b"memorii:sia-traceability-recovery-policy:v1",
        digest_field="recovery_policy_digest", key="attacker-key",
    )
    rejects_recovery_record(
        "ambiguous-policy-signer-field", body,
        [_signature("deterministic-v1", "recovery-key", digest.encode("ascii")).hex(), _signature("deterministic-v1", "recovery-two-key", digest.encode("ascii")).hex()],
        "signature_key_field_ambiguous",
        VerifierHeldTrustMaterial(artifacts["bootstrap"], (artifacts["recovery"], second_recovery_bytes), _verifier, attacker_policy, (recovered_root,)),
    )
    expiring_policy_body = {
        **{key: value for key, value in json.loads(policy).items() if key not in {"recovery_policy_digest", "signature"}},
        "expires_at": body["effective_at"],
    }
    expiring_policy = _signed(
        expiring_policy_body, domain=b"memorii:sia-traceability-recovery-policy:v1",
        digest_field="recovery_policy_digest",
    )
    rejects_recovery_record(
        "policy-expiry-equality", body,
        [_signature("deterministic-v1", "recovery-key", digest.encode("ascii")).hex(), _signature("deterministic-v1", "recovery-two-key", digest.encode("ascii")).hex()],
        "recovery_policy_not_lifecycle_eligible",
        VerifierHeldTrustMaterial(artifacts["bootstrap"], (artifacts["recovery"], second_recovery_bytes), _verifier, expiring_policy, (recovered_root,)),
    )

    reversed_policy_body = json.loads(policy)
    reversed_policy = _signed(
        {
            **{key: value for key, value in reversed_policy_body.items() if key not in {"recovery_policy_digest", "signature"}},
            "eligible_recovery_root_digests": [
                second_recovery["recovery_root_digest"], first_recovery["recovery_root_digest"],
            ],
        },
        domain=b"memorii:sia-traceability-recovery-policy:v1",
        digest_field="recovery_policy_digest",
    )
    rejects_recovery_record(
        "reversed-policy", body,
        [_signature("deterministic-v1", "recovery-key", digest.encode("ascii")).hex(), _signature("deterministic-v1", "recovery-two-key", digest.encode("ascii")).hex()],
        "recovery_signer_order_not_policy_order",
        VerifierHeldTrustMaterial(artifacts["bootstrap"], (artifacts["recovery"], second_recovery_bytes), _verifier, reversed_policy, (recovered_root,)),
    )
    duplicate_body = {
        **body,
        "signer_bindings": [
            body["signer_bindings"][0],
            {**body["signer_bindings"][1], "key_digest": "recovery-key", "recovery_root_digest": first_recovery["recovery_root_digest"]},
        ],
    }
    rejects_recovery_record(
        "duplicate-root", duplicate_body,
        [_signature("deterministic-v1", "recovery-key", sha256(b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(duplicate_body)).hexdigest().encode("ascii")).hex()] * 2,
        "recovery_root_duplicate_signature",
    )
    shortened_body = {**body, "signer_bindings": [body["signer_bindings"][0]]}
    shortened_digest = sha256(b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(shortened_body)).hexdigest()
    rejects_recovery_record(
        "threshold-minus-one", shortened_body,
        [_signature("deterministic-v1", "recovery-key", shortened_digest.encode("ascii")).hex()],
        "recovery_signature_threshold_invalid",
    )
    unordered_body = {
        **body,
        "signer_bindings": [
            {**body["signer_bindings"][0], "signer_id": "z-recovery"},
            {**body["signer_bindings"][1], "signer_id": "a-recovery"},
        ],
    }
    unordered_digest = sha256(b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(unordered_body)).hexdigest()
    rejects_recovery_record(
        "unordered-signer-ids", unordered_body,
        [_signature("deterministic-v1", "recovery-key", unordered_digest.encode("ascii")).hex(), _signature("deterministic-v1", "recovery-two-key", unordered_digest.encode("ascii")).hex()],
        "lifecycle_signer_order_invalid",
    )
    expired_recovery_bytes = _signed(
        {
            "recovery_root_id": "recovery-two", "issuance_purpose": "semantic_ingestion_traceability_recovery_root",
            "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1",
            "public_key_or_root_certificate_digest": "recovery-two-key", "target_authority_id": "authority",
            "effective_at": "2026-01-01T00:00:00Z", "expires_at": "2026-01-01T00:00:02Z",
        }, domain=b"memorii:sia-traceability-recovery-root:v1", digest_field="recovery_root_digest", key="recovery-two-key"
    )
    expired_recovery = json.loads(expired_recovery_bytes)
    expired_policy = _signed(
        {
            **{key: value for key, value in json.loads(policy).items() if key not in {"recovery_policy_digest", "signature"}},
            "eligible_recovery_root_digests": [first_recovery["recovery_root_digest"], expired_recovery["recovery_root_digest"]],
        }, domain=b"memorii:sia-traceability-recovery-policy:v1", digest_field="recovery_policy_digest"
    )
    expired_body = {
        **body,
        "signer_bindings": [
            body["signer_bindings"][0],
            {**body["signer_bindings"][1], "recovery_root_digest": expired_recovery["recovery_root_digest"]},
        ],
    }
    expired_activation = activation_record(
        sequence=2, predecessor=genesis_records[-1]["record_digest"],
        effective_at="2026-01-01T00:00:01Z", recorded_at="2026-01-01T00:00:01.500000Z",
        root_id="recovery-two", root_digest=expired_recovery["recovery_root_digest"],
    )
    first_after_expired = activation_record(
        sequence=3, predecessor=expired_activation["record_digest"],
        effective_at="2026-01-01T00:00:02Z", recorded_at="2026-01-01T00:00:03Z",
        root_id="recovery", root_digest=first_recovery["recovery_root_digest"],
    )
    expired_body["predecessor_record_digest"] = first_after_expired["record_digest"]
    expired_digest = sha256(b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(expired_body)).hexdigest()
    rejects_recovery_record(
        "recovery-expiry-boundary", expired_body,
        [_signature("deterministic-v1", "recovery-key", expired_digest.encode("ascii")).hex(), _signature("deterministic-v1", "recovery-two-key", expired_digest.encode("ascii")).hex()],
        "recovery_root_not_lifecycle_eligible",
        VerifierHeldTrustMaterial(artifacts["bootstrap"], (artifacts["recovery"], expired_recovery_bytes), _verifier, expired_policy, (recovered_root,)),
        (expired_recovery_bytes,),
        [*genesis_records, expired_activation, first_after_expired],
    )
    third_recovery_bytes = _signed(
        {"recovery_root_id": "recovery-three", "issuance_purpose": "semantic_ingestion_traceability_recovery_root", "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1", "public_key_or_root_certificate_digest": "recovery-three-key", "target_authority_id": "authority"},
        domain=b"memorii:sia-traceability-recovery-root:v1", digest_field="recovery_root_digest", key="recovery-three-key"
    )
    third_recovery = json.loads(third_recovery_bytes)
    three_policy = _signed(
        {**{key: value for key, value in json.loads(policy).items() if key not in {"recovery_policy_digest", "signature"}}, "eligible_recovery_root_digests": [first_recovery["recovery_root_digest"], second_recovery["recovery_root_digest"], third_recovery["recovery_root_digest"]]},
        domain=b"memorii:sia-traceability-recovery-policy:v1", digest_field="recovery_policy_digest"
    )
    third_activation = activation_record(
        sequence=4, predecessor=lifecycle["records"][-1]["record_digest"],
        effective_at="2026-01-01T00:00:04Z", recorded_at="2026-01-01T00:00:05Z",
        root_id="recovery-three", root_digest=third_recovery["recovery_root_digest"],
    )
    subset_prefix = [*lifecycle["records"], third_activation]
    subset_body = {
        **body, "sequence": 5, "predecessor_record_digest": third_activation["record_digest"],
        "effective_at": "2026-01-01T00:00:05Z", "recorded_at": "2026-01-01T00:00:06Z",
        "signer_bindings": [body["signer_bindings"][0], {**body["signer_bindings"][1], "signer_id": "recovery-three", "key_digest": "recovery-three-key", "recovery_root_digest": third_recovery["recovery_root_digest"]}],
    }
    subset_digest = sha256(b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(subset_body)).hexdigest()
    subset_record = {**subset_body, "record_digest": subset_digest, "signatures": [_signature("deterministic-v1", "recovery-key", subset_digest.encode("ascii")).hex(), _signature("deterministic-v1", "recovery-three-key", subset_digest.encode("ascii")).hex()]}
    subset_root_body = {"authority_id": "authority", "records": [*subset_prefix, subset_record]}
    subset_root_digest = sha256(b"memorii:sia-traceability-trust-lifecycle-root:v1\0" + canonical_document(subset_root_body)).hexdigest()
    three_material = VerifierHeldTrustMaterial(artifacts["bootstrap"], (artifacts["recovery"], second_recovery_bytes, third_recovery_bytes), _verifier, three_policy, (recovered_root,))
    subset = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], recovery_artifacts=(second_recovery_bytes, third_recovery_bytes), lifecycle_artifact=canonical_document({**subset_root_body, "lifecycle_root_digest": subset_root_digest, "signature": _signature("deterministic-v1", "bootstrap-key", subset_root_digest.encode("ascii")).hex()}), release_artifact=artifacts["release"], release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"], verifier_material=three_material, watermark_store=_watermark(), expected_release_roots=expected_roots, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(subset, TraceabilityGateRejected)
    assert subset.reason == "lifecycle_root_recover_signature_threshold_unsupported"
    reversed_subset_body = {**subset_body, "signer_bindings": [{**subset_body["signer_bindings"][1], "signer_id": "a-third"}, {**subset_body["signer_bindings"][0], "signer_id": "z-first"}]}
    reversed_subset_digest = sha256(b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(reversed_subset_body)).hexdigest()
    rejects_recovery_record("reversed-selected-subset", reversed_subset_body, [_signature("deterministic-v1", "recovery-three-key", reversed_subset_digest.encode("ascii")).hex(), _signature("deterministic-v1", "recovery-key", reversed_subset_digest.encode("ascii")).hex()], "recovery_signer_order_not_policy_order", three_material, (second_recovery_bytes, third_recovery_bytes), subset_prefix)
    result = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], recovery_artifacts=(second_recovery_bytes,), lifecycle_artifact=artifacts["lifecycle"], release_artifact=artifacts["release"], release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"], verifier_material=threshold_material, watermark_store=_watermark(), expected_release_roots=expected_roots, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(result, TraceabilityGateRejected)
    assert result.reason == "lifecycle_root_recover_signature_threshold_unsupported"
    final_root = _signed(
        {"anchor_id": "bootstrap-final", "issuance_purpose": "semantic_ingestion_traceability_release_root", "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1", "public_key_or_root_certificate_digest": "final-key", "target_authority_id": "authority", "effective_at": "2026-01-01T00:00:05Z"},
        domain=b"memorii:sia-traceability-bootstrap-anchor:v1",
        digest_field="anchor_digest", key="final-key",
    )
    final_digest = json.loads(final_root)["anchor_digest"]
    rotation_body = {
        "issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle",
        "sequence": 5, "predecessor_record_digest": record["record_digest"],
        "effective_at": "2026-01-01T00:00:05Z", "recorded_at": "2026-01-01T00:00:06Z",
        "action": "rotate", "target_id": "bootstrap-recovered",
        "target_digest": recovered_digest, "replacement_target_id": "bootstrap-final",
        "replacement_target_digest": final_digest,
        "replacement_signature_profile_id": "deterministic-v1",
        "replacement_key_digest": "final-key",
        "signer_bindings": [{"signer_id": "recovered", "signature_profile_id": "deterministic-v1", "key_digest": "recovered-key"}],
    }
    rotation_digest = sha256(
        b"memorii:sia-traceability-lifecycle-record:v1\0"
        + canonical_document(rotation_body)
    ).hexdigest()
    rotation = {
        **rotation_body, "record_digest": rotation_digest,
        "signatures": [_signature("deterministic-v1", "recovered-key", rotation_digest.encode("ascii")).hex()],
    }
    closed_root_body = {
        "authority_id": "authority", "records": [*lifecycle["records"], record, rotation],
    }
    closed_root_digest = sha256(
        b"memorii:sia-traceability-trust-lifecycle-root:v1\0"
        + canonical_document(closed_root_body)
    ).hexdigest()
    closed_lifecycle = canonical_document(
        {**closed_root_body, "lifecycle_root_digest": closed_root_digest, "signature": _signature("deterministic-v1", "final-key", closed_root_digest.encode("ascii")).hex()}
    )
    final_release = json.loads(
        _signed(
            {**release_body, "issuer_key_or_certificate_digest": "final-key", "issued_at": "2026-01-01T00:00:07Z"},
            domain=b"memorii:sia-traceability-release:v1",
            digest_field="release_digest", key="final-key",
        )
    )
    final_pointer = _signed(
        {**pointer_body, "release_digest": final_release["release_digest"], "issuer_key_or_certificate_digest": "final-key"},
        domain=b"memorii:sia-traceability-active-release-pointer:v1",
        digest_field="active_pointer_digest", key="final-key",
    )
    final_material = VerifierHeldTrustMaterial(
        artifacts["bootstrap"], (artifacts["recovery"], second_recovery_bytes), _verifier,
        policy, (recovered_root, final_root),
    )
    authorized = verify_release_gate(
        registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=artifacts["recovery"], recovery_artifacts=(second_recovery_bytes,),
        lifecycle_artifact=closed_lifecycle, release_artifact=canonical_document(final_release),
        release_history_artifact=_release_history([_history_entry(release=final_release, sequence=1)], key="final-key"),
        active_pointer_artifact=final_pointer, verifier_material=final_material,
        watermark_store=_watermark(), expected_release_roots=expected_roots,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(authorized, TraceabilityGateAuthorized)
    extra_body = {**body, "signer_bindings": [*body["signer_bindings"], body["signer_bindings"][0]]}
    extra_digest = sha256(
        b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(extra_body)
    ).hexdigest()
    extra_record = {
        **extra_body,
        "record_digest": extra_digest,
        "signatures": [
            _signature("deterministic-v1", "recovery-key", extra_digest.encode("ascii")).hex(),
            _signature("deterministic-v1", "recovery-two-key", extra_digest.encode("ascii")).hex(),
            _signature("deterministic-v1", "recovery-key", extra_digest.encode("ascii")).hex(),
        ],
    }
    extra_root_body = {"authority_id": "authority", "records": [*lifecycle["records"], extra_record]}
    extra_root_digest = sha256(
        b"memorii:sia-traceability-trust-lifecycle-root:v1\0" + canonical_document(extra_root_body)
    ).hexdigest()
    artifacts["lifecycle"] = canonical_document(
        {**extra_root_body, "lifecycle_root_digest": extra_root_digest, "signature": _signature("deterministic-v1", "bootstrap-key", extra_root_digest.encode("ascii")).hex()}
    )
    extra = verify_release_gate(
        registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=artifacts["recovery"], recovery_artifacts=(second_recovery_bytes,),
        lifecycle_artifact=artifacts["lifecycle"], release_artifact=artifacts["release"],
        release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"],
        verifier_material=threshold_material, watermark_store=_watermark(), expected_release_roots=expected_roots,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(extra, TraceabilityGateRejected)
    assert extra.reason == "recovery_signature_threshold_invalid"
    rejected = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=artifacts["release"], release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"], verifier_material=threshold_material, watermark_store=_watermark(), expected_release_roots=expected_roots, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(rejected, TraceabilityGateRejected)
