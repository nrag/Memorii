"""Exact inventory tests for the compiled default-catalog acceptance corpus."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from memorii.core.semantic_ingestion.catalog_authority import contract_digest
from memorii.core.semantic_ingestion.default_catalog_corpus import (
    EXPECTED_DEFAULT_RELATION_IDS,
    EXPECTED_SEMANTIC_COVERAGE_CODES,
    DefaultCatalogAcceptanceCorpus,
    load_default_catalog_acceptance_corpus,
)
from scripts.generate_default_catalog_corpus import _entity_declarations, generate


def _body() -> dict[str, object]:
    return load_default_catalog_acceptance_corpus().model_dump(mode="json")


def test_packaged_default_catalog_corpus_has_exact_inventory_and_coverage() -> None:
    corpus = load_default_catalog_acceptance_corpus()

    assert len(corpus.rows) == 53
    assert len(corpus.entity_types) == 27
    assert frozenset(row.relation_id for row in corpus.rows) == EXPECTED_DEFAULT_RELATION_IDS
    assert frozenset(code for row in corpus.rows for code in row.coverage) == (
        EXPECTED_SEMANTIC_COVERAGE_CODES
    )
    assert corpus.user_context_coverage == ("H8",)
    assert sum(row.requires_private_denial for row in corpus.rows) == 25
    literals = {row.relation_id: row.value_policy_id for row in corpus.rows if row.value_policy_id}
    assert literals == {
        "event_time": "time_interval",
        "obligation_amount": "money_iso4217",
        "obligation_due_on": "local_date",
        "opportunity_stage": "opportunity_stage",
        "work_item_due_on": "local_date",
        "work_item_status": "work_item_status",
    }


def test_default_catalog_corpus_regenerates_byte_identically(tmp_path: Path) -> None:
    output = tmp_path / "corpus.json"
    generate(
        design_path=Path("docs/design/learned_ontology_base_catalog.md"),
        output_path=output,
    )

    packaged = Path(
        "memorii/memorii/core/semantic_ingestion/resources/"
        "default_catalog_acceptance_corpus.v1.json"
    )
    assert output.read_bytes() == packaged.read_bytes()


@pytest.mark.parametrize(
    ("old", "new", "type_id", "field", "expected"),
    (
        ("| `Household` | `Group` |", "| `Household` | `Organization` |", "Household", "parent_type_id", "Organization"),
        ("| `Role` | None | `role_assignment` |", "| `Role` | None | `introduced` |", "Role", "identity_policy_id", "introduced"),
        ("| `Animal` | None | `animal` | P |", "| `Animal` | None | `animal` | G |", "Animal", "scope", "G"),
    ),
)
def test_entity_declaration_compiler_observes_normative_table_drift(
    old: str, new: str, type_id: str, field: str, expected: str,
) -> None:
    design = Path("docs/design/learned_ontology_base_catalog.md").read_text()
    assert old in design
    declarations = {
        item["type_id"]: item for item in _entity_declarations(design.replace(old, new))
    }

    assert declarations[type_id][field] == expected


@pytest.mark.parametrize("mutation", ("missing", "duplicate", "orphan", "wrong_case"))
def test_default_catalog_corpus_rejects_inventory_and_fixture_mutations(
    mutation: str,
) -> None:
    body = _body()
    rows = list(body["rows"])
    if mutation == "missing":
        rows.pop()
    elif mutation == "duplicate":
        rows[-1] = rows[0]
    elif mutation == "orphan":
        rows[-1] = {**rows[-1], "coverage": ["ORPHAN"]}
    else:
        rows[-1] = {**rows[-1], "cases": rows[0]["cases"]}
    body["rows"] = rows

    with pytest.raises(ValueError):
        DefaultCatalogAcceptanceCorpus.model_validate(body)


def test_default_catalog_corpus_rejects_stale_digest_and_source_contract() -> None:
    body = _body()
    with pytest.raises(ValueError, match="digest"):
        DefaultCatalogAcceptanceCorpus.model_validate({**body, "corpus_digest": "0" * 64})
    with pytest.raises(ValueError, match="source contract"):
        DefaultCatalogAcceptanceCorpus.model_validate({
            **body, "source_contract_sha256": "0" * 64,
        })


def test_default_catalog_corpus_rejects_one_rows_shared_coverage_omission() -> None:
    body = _body()
    rows = list(body["rows"])
    index = next(
        index for index, row in enumerate(rows) if row["relation_id"] == "member_of"
    )
    rows[index] = {**rows[index], "coverage": []}
    unsigned = {**body, "rows": rows}
    unsigned.pop("corpus_digest")
    mutated = {
        **unsigned,
        "corpus_digest": contract_digest(
            b"memorii.learned-ontology.default-acceptance-corpus.v1", unsigned
        ),
    }

    with pytest.raises(ValueError, match="primary coverage"):
        DefaultCatalogAcceptanceCorpus.model_validate(mutated)


def test_default_catalog_corpus_rejects_unknown_typed_endpoint() -> None:
    body = _body()
    rows = list(body["rows"])
    rows[0] = {**rows[0], "subject_type_ids": ["MysteryType"]}
    unsigned = {**body, "rows": rows}
    unsigned.pop("corpus_digest")

    with pytest.raises(ValueError, match="unknown entity type"):
        DefaultCatalogAcceptanceCorpus.model_validate({
            **unsigned,
            "corpus_digest": contract_digest(
                b"memorii.learned-ontology.default-acceptance-corpus.v1", unsigned
            ),
        })


def test_packaged_default_catalog_corpus_is_canonical_json() -> None:
    corpus = load_default_catalog_acceptance_corpus()
    encoded = json.dumps(
        corpus.model_dump(mode="json"), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8") + b"\n"
    packaged = Path(
        "memorii/memorii/core/semantic_ingestion/resources/"
        "default_catalog_acceptance_corpus.v1.json"
    ).read_bytes()
    assert encoded == packaged
