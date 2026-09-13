from __future__ import annotations

import json

from memorii.core.memory_evolution.typed_value_declarations import (
    ProtectedDeclarationParseLimits,
    parse_typed_value_declaration,
)
from memorii.tools.semantic_ingestion_observation_source_draft import _integrity_policy, build_draft


def test_draft_is_explicitly_untrusted_and_includes_profile3_observation_roots() -> None:
    draft = build_draft()

    assert draft["status"] == "UNTRUSTED_AUTHORING_DRAFT_NOT_FOR_COMPILATION_OR_PUBLICATION"
    assert "GraphRecordObservationSnapshot" in draft["source_ids"]
    assert "ObservedTemporalClaimProjection" in draft["source_ids"]
    assert "GraphObservationStreamRecord" not in draft["source_ids"]
    assert "ObservedClaimProjection" not in draft["source_ids"]


def test_snapshot_graph_record_uses_the_reviewed_closed_payload_override() -> None:
    draft = build_draft()
    schema = next(item["draft"]["schema"] for item in draft["schemas"] if item["schema_id"] == "SnapshotGraphRecord")
    payload = next(field for field in schema["fields"] if field["name"] == "payload")

    assert payload["type"]["kind"] == "union"
    assert payload["type"]["discriminator"] == "record_kind"
    assert len(payload["type"]["alternatives"]) == 12
    assert all(item["model"]["schema_id"] != "BaseModel" for item in payload["type"]["alternatives"])


def test_unsupported_policies_remain_auditable_instead_of_becoming_declarations() -> None:
    issues: list[dict[str, str]] = []
    policy, _ = _integrity_policy("DeliberatelyUnmappedDraftSchema", [], issues)

    assert policy == {"kind": "unresolved"}
    assert issues == [{
        "schema_id": "DeliberatelyUnmappedDraftSchema",
        "path": "digest-signature",
        "reason": "profile3_digest_or_signature_policy_not_yet_mapped",
    }]


def test_annotated_digest_bounds_and_native_discriminators_are_preserved() -> None:
    draft = build_draft()
    schemas = {item["schema_id"]: item["draft"]["schema"] for item in draft["schemas"]}
    record_digest = next(field for field in schemas["ObservedEntityRevision"]["fields"] if field["name"] == "record_digest")
    cursor_revision = next(field for field in schemas["GraphObservationCursorPayload"]["fields"] if field["name"] == "snapshot_write_revision")
    delta = next(field for field in schemas["ObservationLedgerEntry"]["fields"] if field["name"] == "delta")
    certificate = next(field for field in schemas["TemporalProjectionPublication"]["fields"] if field["name"] == "certificate")

    assert record_digest["type"]["lexical_rule"] == "sha256"
    assert cursor_revision["type"]["minimum"] == "0"
    assert delta["type"]["discriminator"] == "kind"
    assert certificate["type"]["discriminator"] == "publication_kind"


def test_explicit_integrity_table_marks_native_and_proposed_profile3_policies() -> None:
    draft = build_draft()
    schemas = {item["schema_id"]: item["draft"] for item in draft["schemas"]}

    assert schemas["BootstrapGraphNativeProjectionPublicationReceiptV3"]["digest_signature"]["policy"] == {
        "kind": "self_digest",
        "digest_field": "receipt_digest",
        "digest_domain": "memorii.bootstrap-graph.native-projection-publication-receipt.v3",
    }
    assert schemas["ObservationLedgerHead"]["digest_signature"]["policy"]["proposal_requires_review"] is True
    assert schemas["GraphObservationCursorPayload"]["digest_signature"]["policy"]["kind"] == "signature_only"
    modality = schemas["SegmentGovernanceBinding"]["enum"]["enums"][0]
    assert modality["qualified_id"] == "memorii.domain.SourceModality"
    assert modality["members"][0] == {"member_id": "ASSERTION", "wire_value": "assertion"}
    assert schemas["SourceRetentionTimeAttestation"]["digest_signature"]["policy"]["digest_field"] == "attestation_digest"
    assert schemas["SourceRetentionTimeAttestation"]["digest_signature"]["policy"]["proposal_requires_review"] is True


def test_native_defaults_are_required_source_fields_and_witness_is_absent_everywhere() -> None:
    draft = build_draft()
    schemas = {item["schema_id"]: item["draft"] for item in draft["schemas"]}
    selector_optional = schemas["GraphObservationCohortSelector"]["optional"]["fields"]
    request_optional = schemas["GraphObservationRequestCoordinates"]["optional"]["fields"]
    witnesses = ("SourceRetentionTimeWitness", "TransactionGroupCommitTimeWitness")

    assert {field["policy"] for field in selector_optional} == {"required"}
    assert next(field for field in request_optional if field["field_name"] == "valid_at")["policy"] == "required_nullable"
    assert all(witness not in draft["source_ids"] for witness in witnesses)
    assert all(witness not in {root["source_id"] for root in draft["roots"]} for witness in witnesses)
    assert all(witness not in schemas for witness in witnesses)

    def walk(value: object) -> tuple[object, ...]:
        if isinstance(value, dict):
            return tuple(item for pair in value.items() for item in walk(pair))
        if isinstance(value, (list, tuple)):
            return tuple(item for child in value for item in walk(child))
        return (value,)

    flattened = walk(draft["schemas"])
    assert all(witness not in flattened for witness in witnesses)


def test_all_five_raw_roles_parse_after_stripping_draft_review_metadata() -> None:
    draft = build_draft()

    def strip_review_metadata(value: object) -> object:
        if isinstance(value, dict):
            return {key: strip_review_metadata(item) for key, item in value.items() if key != "proposal_requires_review"}
        if isinstance(value, list):
            return [strip_review_metadata(item) for item in value]
        return value

    limits = ProtectedDeclarationParseLimits(maximum_bytes=100_000, maximum_nodes=10_000, maximum_depth=100)
    roles = ("schema", "enum", "optional", "numeric", "digest_signature")
    parsed = [
        parse_typed_value_declaration(
            json.dumps(strip_review_metadata(schema["draft"][role]), separators=(",", ":"), sort_keys=True).encode(),
            limits=limits,
        ).role
        for schema in draft["schemas"]
        for role in roles
    ]

    assert parsed == [item for _ in draft["schemas"] for item in ("schema", "enum", "optional", "numeric", "digest-signature")]
