from __future__ import annotations

import pytest
from memorii.core.semantic_ingestion import catalog_inspection
from memorii.core.semantic_ingestion.catalog_authority import CatalogAuthorityError
from memorii.core.semantic_ingestion.catalog_capture_pin import SeedCatalogBundleLocator, VerifiedCatalogBundle
from memorii.core.semantic_ingestion.catalog_inspection import (
    CatalogRelationInspectionRequest,
    CatalogRelationInspectionResponse,
    StructuredRecallDiagnosisRequest,
    StructuredRecallDiagnosisResponse,
    normalize_relation_name,
    project_catalog_relations,
)
from memorii.core.semantic_ingestion.default_catalog_package import load_packaged_default_catalog_release
from pydantic import ValidationError


def _selected_packaged_bundles() -> tuple[VerifiedCatalogBundle, VerifiedCatalogBundle]:
    seed = SeedCatalogBundleLocator().locate()
    release = load_packaged_default_catalog_release()
    return (
        VerifiedCatalogBundle(
            catalog=seed.catalog, version=seed.version, runtime_bundle_digest=seed.runtime_bundle_digest,
        ),
        VerifiedCatalogBundle(
            catalog=seed.catalog, version=release.child_version, runtime_bundle_digest=release.runtime_bundle_digest,
        ),
    )


def test_verified_catalog_projection_preserves_both_type_namespaces() -> None:
    seed, default = _selected_packaged_bundles()
    for bundle, count in ((seed, 3), (default, 56)):
        rows = project_catalog_relations(bundle)
        ids = tuple(row.predicate_id for row in rows)
        assert len(rows) == count and ids == tuple(sorted(set(ids)))
        owner = next(row for row in rows if row.predicate_id == "project_owner").model_dump(mode="json")
        assert owner["subject_type_ids"] == ["ProjectId"]
        assert owner["object_endpoint"] == {"kind": "entity", "type_ids": ["PersonName"]}
        assert owner["read_form"] == "current"
    rows_by_id = {row.predicate_id: row.model_dump(mode="json") for row in project_catalog_relations(default)}
    assert rows_by_id["project_owned_by"]["object_endpoint"] == {
        "kind": "entity", "type_ids": ["Group", "Organization", "Person"],
    }
    assert rows_by_id["project_owned_by"]["read_form"] == "set"
    assert rows_by_id["decision_supersedes"]["read_form"] == "history"
    assert rows_by_id["partner_of"]["read_direction"] == "symmetric_view"
    assert rows_by_id["obligation_due_on"]["object_endpoint"] == {"kind": "literal", "value_type": "LocalDate"}
    assert rows_by_id["obligation_due_on"]["lookup_aliases"] == ["bill due date"]
    assert normalize_relation_name(" _ Bill-DUE__date- ") == "bill due date"


def test_catalog_projection_rejects_a_missing_unrelated_declaration(monkeypatch) -> None:
    _, default = _selected_packaged_bundles()
    corpus = catalog_inspection.load_default_catalog_acceptance_corpus()
    monkeypatch.setattr(
        catalog_inspection, "load_default_catalog_acceptance_corpus",
        lambda: corpus.model_copy(update={"rows": tuple(row for row in corpus.rows if row.relation_id != "partner_of")}),
    )
    with pytest.raises(CatalogAuthorityError, match="incomplete"):
        project_catalog_relations(default)


def test_lookup_and_diagnosis_have_closed_inputs_and_status_only_failures() -> None:
    for invalid_lookup in (
        {"kind": "predicate_id", "predicate_id": "Project_owner"},
        {"kind": "predicate_id", "predicate_id": "project_owner", "name": "project owner"},
        {"kind": "name", "name": " "},
        {"kind": "name", "name": "a" * 129},
        {"kind": "name", "name": None},
        {"kind": "name", "name": "bill?"},
    ):
        with pytest.raises(ValidationError):
            CatalogRelationInspectionRequest.model_validate(invalid_lookup)
    # User-supplied names are data, even when they resemble plan coordinates.
    lookup_text = "".join(("M", "1"))
    assert CatalogRelationInspectionRequest.model_validate({"kind": "name", "name": lookup_text}).root.kind == "name"

    exact = {"kind": "exact", "predicate_id": "project_owner", "subject_entity_id": "subject"}
    assert StructuredRecallDiagnosisRequest.model_validate(exact).root.kind == "exact"
    for invalid_query in (
        {**exact, "expected_catalog_version_digest": None},
        {**exact, "expected_catalog_version_digest": "A" * 64},
        {**exact, "subject_entity_id": "*"},
        {**exact, "subject_entity_id": "subject "},
        {**exact, "subject_entity_id": "\x00subject"},
        {"kind": "unresolved", "reference": "relation", "subject_entity_id": "subject"},
    ):
        with pytest.raises(ValidationError):
            StructuredRecallDiagnosisRequest.model_validate(invalid_query)
    assert CatalogRelationInspectionResponse.model_validate({"status": "denied"}).model_dump(mode="json") == {
        "status": "denied",
    }
    assert StructuredRecallDiagnosisResponse.model_validate({"status": "catalog_changed"}).model_dump(mode="json") == {
        "status": "catalog_changed",
    }
    with pytest.raises(ValidationError):
        StructuredRecallDiagnosisResponse.model_validate({"status": "catalog_changed", "items": []})
    with pytest.raises(ValidationError):
        CatalogRelationInspectionResponse.model_validate({"status": "ambiguous", "relations": []})
