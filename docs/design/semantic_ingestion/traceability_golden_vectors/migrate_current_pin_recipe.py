"""Mechanically reduce the historical scenario-first closure candidate to closed primitive roots.

The historical body authority is migration provenance only.  This tool emits a
leaf-by-leaf ownership ledger alongside the reduced values so a later
elaborator never needs to guess whether a value was supplied or derived.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOTS = (
    "authority_use",
    "checked_fixture_outputs",
    "fixed_signers",
    "format",
    "nested_substitution_cases",
    "primitive_authority",
    "primitive_fixtures",
    "vector_cases",
)
BODY_CLASSIFICATION_KEY = "body_leaf_classification"
DERIVATION_PROGRAM_KEY = "derivation_program"

# These are field identities from the frozen scenario-first closure schemas, not a token matcher.
# A value below one of these fields is elaborated from the other primitive
# roots.  Every other value is retained verbatim as primitive authority.
DERIVED_FIELDS_BY_SCHEMA = {
    "NormativeExecutionEvidenceRecordBody.v1": {"canonical_profile_binding", "design_document_digest", "implementation_tree_digest", "loaded_report_schema_digest", "loaded_runner_environment_profile_digest", "result_artifact_digest", "runner_environment_observation_artifact_digest", "runner_environment_observation_binding_digest", "runner_environment_observation_digest", "runner_report_artifact_digest", "runner_report_binding_digest", "signer_coordinate", "structural_manifest_digest", "test_or_evidence_artifact_digest", "trust_snapshot_digest"},
    "NormativeTraceabilityStructuralManifestBody.v1": {"anchor_binding_registry_digest", "artifact_dag_digest", "assertion_registry_digest", "canonical_profile_binding", "design_document_digest", "explicit_anchor_bindings", "override_registry_digest", "report_schema_registry_digest", "requirement_binding_registry_digest", "runner_environment_profile_registry_digest", "runner_environment_profiles", "section_default_registry_digest", "structural_mapping_rule_registry_digest", "test_evidence_group_registry_digest"},
    "SemanticIngestionTraceabilityReleaseBody.v1": {"anchor_binding_registry_digest", "artifact_dag_digest", "assertion_registry_digest", "bootstrap_anchor_digest", "bootstrap_anchor_history_digest", "canonical_profile_binding", "coverage_root_digest", "design_document_digest", "execution_root_digest", "golden_vector_manifest_digest", "override_registry_digest", "recovery_policy_history_digest", "recovery_root_history_digest", "recovery_trust_policy_digest", "recovery_trust_root_digests", "report_schema_registry_digest", "requirement_binding_registry_digest", "runner_environment_profile_registry_digest", "section_default_registry_digest", "signer_coordinate", "structural_manifest_digest", "structural_mapping_rule_registry_digest", "test_evidence_group_registry_digest", "trust_lifecycle_root_digest", "trust_snapshot_digest"},
    "TraceabilityActiveReleasePointerBody.v1": {"canonical_profile_binding", "generation_manifest_digest", "predecessor_active_pointer_digest", "predecessor_pointer_history_digest", "release_digest", "release_history_digest", "signer_coordinate"},
    "TraceabilityActiveReleasePointerHistoryBody.v1": {"canonical_profile_binding", "signer_coordinate"},
    "TraceabilityApprovalGenerationManifestBody.v1": {"canonical_profile_binding", "design_document_digest"},
    "TraceabilityApprovalGoldenVectorManifestBody.v1": {"canonical_profile_binding", "design_document_digest"},
    "TraceabilityBootstrapAnchorHistoryBody.v1": {"canonical_profile_binding"},
    "TraceabilityBootstrapTrustAnchorBody.v1": {"authorized_signature_purposes", "canonical_profile_binding", "lifecycle_root_coordinate", "predecessor_anchor_digest", "public_key_or_root_certificate_digest", "signature_profile_id"},
    "TraceabilityCoverageApprovalRecordBody.v1": {"applicable_structural_rule_digests", "canonical_profile_binding", "design_document_digest", "signer_coordinate", "structural_manifest_digest", "trust_snapshot_digest"},
    "TraceabilityCoverageEvidenceRootBody.v1": {"structural_manifest_digest"},
    "TraceabilityCurrentPointerFenceBody.v1": {"canonical_profile_binding", "current_pointer_index_digest", "predecessor_fence_digest"},
    "TraceabilityCurrentPointerIndexBody.v1": {"active_pointer_digest", "canonical_profile_binding", "pointer_history_digest", "predecessor_index_digest"},
    "TraceabilityExecutionEvidenceRootBody.v1": {"structural_manifest_digest"},
    "TraceabilityGenerationReaderLeaseBody.v1": {"active_pointer_digest", "canonical_profile_binding", "generation_manifest_digest", "pointer_history_digest", "reader_authorization_request_digest", "signer_coordinate", "time_witness_digest"},
    "TraceabilityGoldenTypedInputFixtureBody.v1": {"target_body_binding"},
    "TraceabilityMonotonicTimeWitnessBody.v1": {"canonical_profile_binding", "predecessor_time_witness_digest", "signer_coordinate"},
    "TraceabilityReaderAuthorizationRequestBody.v1": {"expected_active_pointer_digest", "expected_pointer_history_digest", "requested_generation_manifest_digest", "time_witness_digest"},
    "TraceabilityRecoveryPolicyHistoryBody.v1": {"canonical_profile_binding"},
    "TraceabilityRecoveryRootHistoryBody.v1": {"canonical_profile_binding"},
    "TraceabilityRecoveryTrustPolicyBody.v1": {"bootstrap_anchor_digest", "canonical_profile_binding", "eligible_recovery_root_digests", "minimum_distinct_signatures", "predecessor_policy_digest", "signer_coordinate", "signer_separation_rule_digest"},
    "TraceabilityRecoveryTrustRootBody.v1": {"authorized_signature_purposes", "canonical_profile_binding", "lifecycle_root_coordinate", "predecessor_recovery_root_digest", "public_key_or_root_certificate_digest", "signature_profile_id"},
    "TraceabilityReleaseHistoryBody.v1": {"canonical_profile_binding", "signer_coordinate"},
    "TraceabilityReleaseTrustSnapshotBody.v1": {"bootstrap_anchor_digest", "canonical_profile_binding", "recovery_policy_digest", "trust_lifecycle_root_digest"},
    "TraceabilityRetentionWatermarkBody.v1": {"canonical_profile_binding", "expected_current_pointer_history_digest", "expected_predecessor_watermark_digest", "pointer_history_digest", "predecessor_watermark_digest", "signer_coordinate", "time_witness_digest"},
    "TraceabilityRunnerEnvironmentObservationBody.v1": {"canonical_profile_binding", "configuration_digest", "dependency_digest", "environment_digest", "import_path_digest", "interpreter_digest", "loaded_runner_environment_profile_digest", "network_enforcement_observation_digest", "runner_distribution_digest", "runner_environment_profile_id", "runner_environment_profile_version"},
    "TraceabilityRunnerReportBody.v1": {"canonical_profile_binding", "loaded_report_schema_digest", "report_bytes_digest", "result_artifact_digest", "runner_environment_observation_artifact_digest", "stderr_artifact_digest", "stdout_artifact_digest"},
    "TraceabilityTrustLifecycleRecordBody.v1": {"canonical_profile_binding", "predecessor_record_digest", "recovery_policy_digest", "replacement_target_digest", "signer_bindings", "target_digest"},
    "TraceabilityTrustLifecycleRootBody.v1": {"bootstrap_anchor_history_digest", "canonical_profile_binding", "recovery_policy_history_digest", "recovery_root_history_digest"},
}

# Nested CTV models are reused by several bodies.  Their classification is
# still closed: these are the exact field identities observed in the frozen
# scenario-first closure schema inventory, not a substring or suffix rule.  The exceptions below
# are the primitive signer/policy facts explicitly retained by the current-pin
# authority correction.
DERIVED_FIELD_NAMES = frozenset({
    "active_pointer_digest", "anchor_binding_registry_digest", "anchor_digest", "applicable_structural_rule_digests", "approval_digest", "artifact_coordinate", "artifact_dag_digest", "artifact_digest", "assertion_registry_digest", "binding", "binding_digest", "body_binding", "bootstrap_anchor_digest", "bootstrap_anchor_history_digest", "canonical_payload_digest", "canonical_profile_binding", "canonical_profile_id", "canonical_value_digest", "configuration_digest", "content_digest", "coverage_root_digest", "current_pointer_index_digest", "default_digest", "dependency_digest", "depends_on_coordinates", "design_document_digest", "dynamic_artifact_coordinate_variables", "eligible_recovery_root_digests", "enforcement_observation_digest", "entry_digest", "environment_digest", "evidence_digest", "execution_root_digest", "expected_active_pointer_digest", "expected_artifact_coordinate", "expected_artifact_digest", "expected_body_digest", "expected_current_pointer_history_digest", "expected_envelope_bytes", "expected_pointer_history_digest", "expected_predecessor_watermark_digest", "expected_report_schema_digest", "expected_runner_environment_profile_digest", "expected_signature_preimage_bytes", "expected_signatures", "explicit_anchor_bindings", "generation_manifest_digest", "golden_vector_manifest_digest", "implementation_tree_digest", "import_path_digest", "interpreter_digest", "key_or_certificate_digest", "lifecycle_record_digest", "lifecycle_root_coordinate", "loaded_report_schema_digest", "loaded_runner_environment_profile_digest", "mapping_digest", "network_enforcement_observation_digest", "override_digest", "override_registry_digest", "pointer_history_digest", "predecessor_active_pointer_digest", "predecessor_anchor_digest", "predecessor_entry_digest", "predecessor_fence_digest", "predecessor_index_digest", "predecessor_pointer_history_digest", "predecessor_policy_digest", "predecessor_record_digest", "predecessor_recovery_root_digest", "predecessor_time_witness_digest", "predecessor_watermark_digest", "prior_active_release_digest", "prior_lifecycle_record_digest", "prior_lifecycle_root_digest", "profile_digest", "profile_id", "profile_version", "public_key_or_root_certificate_digest", "reader_authorization_request_digest", "record_digest", "recovery_policy_digest", "recovery_policy_history_digest", "recovery_root_digest", "recovery_root_history_digest", "recovery_trust_policy_digest", "recovery_trust_root_digests", "release_digest", "release_history_digest", "replacement_target_digest", "report_binding", "report_bytes_digest", "report_schema_registry_digest", "requested_generation_manifest_digest", "requirement_binding_registry_digest", "result_artifact_digest", "reviewer_evidence_digest", "rule_digest", "runner_distribution_digest", "runner_environment_observation_artifact_digest", "runner_environment_observation_binding_digest", "runner_environment_observation_digest", "runner_environment_profile_id", "runner_environment_profile_registry_digest", "runner_environment_profile_version", "runner_environment_profiles", "runner_report_artifact_digest", "runner_report_binding_digest", "section_default_registry_digest", "signature", "signatures", "signer_coordinate", "signer_coordinates", "signer_key_or_certificate_digest", "signer_separation_rule_digest", "source_artifact_digest", "stderr_artifact_digest", "stdout_artifact_digest", "structural_manifest_digest", "structural_mapping_rule_registry_digest", "target_body_binding", "target_digest", "terminal_record_digest", "test_evidence_group_registry_digest", "test_or_evidence_artifact_digest", "time_witness_digest", "trust_lifecycle_root_digest", "trust_snapshot_digest", "typed_input_fixture_digest",
})
PRIMITIVE_FIELD_NAMES = frozenset({
    "authorized_signature_purposes", "minimum_distinct_signatures",
    "signature_profile_id", "signature_purpose", "signer_bindings",
})

# The program is deliberately declarative.  Both elaborators must implement
# these formula domains independently; the recipe records neither a derived
# value nor an implementation-specific expression tree.
DERIVATION_PROGRAM = {
    "v2_profile_or_binding": {
        "depends_on": ["ctv_binding_authority_v2", "design", "registry"],
        "formula": "published_v2_profile_or_schema_binding_preimage",
    },
    "canonical_body_or_identity_digest": {
        "depends_on": ["expanded_body", "schema_binding", "dependency_artifacts"],
        "formula": "domain_separated_sha256_of_canonical_body_or_dependency_identity",
    },
    "artifact_coordinate_or_envelope": {
        "depends_on": ["body_digest", "schema_binding", "dependency_artifacts"],
        "formula": "declared_outer_envelope_and_coordinate_construction",
    },
    "signature_preimage_or_signature": {
        "depends_on": ["body_digest", "schema_binding", "fixed_signer", "signer_eligibility"],
        "formula": "declared_preimage_then_rfc8032_pureed25519",
    },
    "structural_or_generation_root": {
        "depends_on": ["dependency_artifacts", "primitive_generation_state", "structural_stream"],
        "formula": "ordered_member_or_root_reconstruction",
    },
}
PROFILE_OR_BINDING_FIELDS = frozenset({
    "binding", "binding_digest", "body_binding", "canonical_profile_binding",
    "canonical_profile_id", "profile_digest", "profile_id", "profile_version",
    "report_binding", "target_body_binding",
})
SIGNATURE_FIELDS = frozenset({"signature", "signatures", "expected_signature_preimage_bytes", "expected_signatures"})
COORDINATE_OR_ENVELOPE_FIELDS = frozenset({
    "artifact_coordinate", "depends_on_coordinates", "dynamic_artifact_coordinate_variables",
    "expected_artifact_coordinate", "expected_envelope_bytes", "lifecycle_root_coordinate",
    "signer_coordinate", "signer_coordinates",
})
ROOT_FIELDS = frozenset({
    "artifact_dag_digest", "coverage_root_digest", "execution_root_digest",
    "generation_manifest_digest", "structural_manifest_digest", "trust_lifecycle_root_digest",
    "trust_snapshot_digest",
})


def _body_field_names(value: Any) -> set[str]:
    if not isinstance(value, dict) or value.get("$type") != "map":
        raise ValueError("authority body must be a CTV map")
    return {entry[0] for entry in value["entries"]}


def _is_derived(schema_id: str, field_name: str) -> bool:
    """Classify a field using the explicit migration table.

    The common rules are intentionally exact suffixes, rather than broad
    substring matching: e.g. ``profile_name`` remains primitive while the
    schema-owned ``canonical_profile_binding`` is derived.
    """
    if schema_id not in DERIVED_FIELDS_BY_SCHEMA:
        raise ValueError(f"unclassified scenario-first closure schema: {schema_id}")
    if field_name in PRIMITIVE_FIELD_NAMES:
        return False
    return field_name in DERIVED_FIELDS_BY_SCHEMA[schema_id] or field_name in DERIVED_FIELD_NAMES


def _derivation_rule(path: tuple[str, ...]) -> str:
    fields = [segment.removeprefix("field:") for segment in path if segment.startswith("field:")]
    # A derived model owns all of its descendant leaves.  Inspect ancestors
    # first so e.g. ``canonical_profile_binding.schema_id`` keeps the profile
    # formula instead of pretending the nested scalar has an independent one.
    for field_name in fields:
        if field_name in PROFILE_OR_BINDING_FIELDS:
            return "v2_profile_or_binding"
        if field_name in SIGNATURE_FIELDS:
            return "signature_preimage_or_signature"
        if field_name in COORDINATE_OR_ENVELOPE_FIELDS:
            return "artifact_coordinate_or_envelope"
        if field_name in ROOT_FIELDS:
            return "structural_or_generation_root"
    if any(field_name in DERIVED_FIELD_NAMES for field_name in fields):
        return "canonical_body_or_identity_digest"
    raise ValueError(f"unclassified derived scenario-first closure path: {path!r}")


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii") + b"\n"


def flatten(value: Any, schema_id: str, *, root_field: str | None = None) -> Any:
    """Retain explicit inputs using the schema-owned field classification."""
    if isinstance(value, list):
        return [flatten(item, schema_id, root_field=root_field) for item in value]
    if not isinstance(value, dict):
        return value
    if value.get("$type") == "map":
        entries = []
        for key, item in value["entries"]:
            if _is_derived(schema_id, key):
                continue
            entries.append([key, flatten(item, schema_id, root_field=key)])
        return {"$type": "map", "entries": entries}
    if "$type" in value:
        return {key: flatten(item, schema_id, root_field=root_field) for key, item in value.items()}
    return {key: flatten(item, schema_id, root_field=root_field) for key, item in value.items()}


def _leaf_paths(value: Any, path: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    if isinstance(value, dict) and value.get("$type") == "map":
        return [
            leaf
            for key, item in value["entries"]
            for leaf in _leaf_paths(item, (*path, f"field:{key}"))
        ]
    if isinstance(value, dict):
        return [leaf for key, item in value.items() for leaf in _leaf_paths(item, (*path, f"key:{key}"))]
    if isinstance(value, list):
        return [leaf for index, item in enumerate(value) for leaf in _leaf_paths(item, (*path, f"index:{index}"))]
    return [path]


def _has_path(value: Any, path: tuple[str, ...]) -> bool:
    current = value
    for segment in path:
        kind, token = segment.split(":", 1)
        if kind == "field":
            if not isinstance(current, dict) or current.get("$type") != "map":
                return False
            matches = [item for key, item in current["entries"] if key == token]
            if len(matches) != 1:
                return False
            current = matches[0]
        elif kind == "key":
            if not isinstance(current, dict) or token not in current:
                return False
            current = current[token]
        else:
            index = int(token)
            if not isinstance(current, list) or index >= len(current):
                return False
            current = current[index]
    return True


def migrate(source: bytes) -> bytes:
    old = json.loads(source)
    result = {key: old[key] for key in ROOTS if key in old}
    result["format"] = "memorii-sia-c2-normative-fixture-recipe-v1"
    # Old checked output was a generated oracle. It is deliberately absent from
    # current input authority and is regenerated by each clean-room elaborator.
    result["checked_fixture_outputs"] = []
    authority = result["primitive_authority"]
    bodies = authority.pop("authority_bodies")
    primitive_bodies = {}
    classifications = {}
    for fixture_id, body in sorted(bodies.items()):
        schema_id = body["inner_schema_id"]
        full_value = body["value"]
        primitive_value = flatten(full_value, schema_id)
        primitive_bodies[fixture_id] = {
            "inner_schema_id": body["inner_schema_id"],
            "inner_schema_version": body["inner_schema_version"],
            "value": primitive_value,
        }
        classifications[fixture_id] = []
        for path in _leaf_paths(full_value):
            source = "primitive" if _has_path(primitive_value, path) else "deterministic_derivation"
            entry: dict[str, Any] = {"path": list(path), "source": source}
            if source == "deterministic_derivation":
                rule_id = _derivation_rule(path)
                entry["derivation_rule_id"] = rule_id
                entry["depends_on"] = DERIVATION_PROGRAM[rule_id]["depends_on"]
            classifications[fixture_id].append(entry)
    authority["primitive_body_inputs"] = primitive_bodies
    authority[BODY_CLASSIFICATION_KEY] = classifications
    authority[DERIVATION_PROGRAM_KEY] = DERIVATION_PROGRAM
    if tuple(sorted(result)) != ROOTS:
        raise ValueError("historical source does not contain the closed scenario-first closure inputs")
    return canonical(result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_bytes(migrate(args.source.read_bytes()))


if __name__ == "__main__":
    main()
