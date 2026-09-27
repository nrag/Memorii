"""Compile the normative default relation ledger into canonical corpus bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from memorii.core.semantic_ingestion.catalog_authority import contract_digest
from memorii.core.semantic_ingestion.default_catalog_corpus import DefaultCatalogAcceptanceCorpus
from memorii.core.semantic_ingestion.default_catalog_values import DEFAULT_CATALOG_VALUE_POLICIES

_LITERAL_POLICIES = {
    "work_item_due_on": ("LocalDate", "local_date"),
    "work_item_status": ("StatusText", "work_item_status"),
    "event_time": ("TimeInterval", "time_interval"),
    "obligation_due_on": ("LocalDate", "local_date"),
    "obligation_amount": ("Money", "money_iso4217"),
    "opportunity_stage": ("StatusText", "opportunity_stage"),
}

_SYMMETRIC_READ_RELATIONS = frozenset({"partner_of", "sibling_of"})


def _type_ids(value: str) -> tuple[str, ...]:
    normalized = value.replace(", or ", ", ").replace(" or ", ", ")
    return tuple(sorted(part.strip() for part in normalized.split(",") if part.strip()))


def _entity_declarations(markdown: str) -> tuple[dict[str, object], ...]:
    declarations: list[dict[str, object]] = []
    in_table = False
    for line in markdown.splitlines():
        if line.startswith("| Type IDs | Parent | Identity policy | Scope class |"):
            in_table = True
            continue
        if in_table and line.startswith("**Scope classes."):
            break
        if not in_table or not line.startswith("| `"):
            continue
        columns = [column.strip() for column in line.strip("|").split("|")]
        if len(columns) != 4:
            raise ValueError("default catalog entity row is invalid")
        type_ids = tuple(re.findall(r"`([^`]+)`", columns[0]))
        parent_matches = tuple(re.findall(r"`([^`]+)`", columns[1]))
        parent = None if columns[1] == "None" else parent_matches[0]
        identity_matches = tuple(re.findall(r"`([^`]+)`", columns[2]))
        if not type_ids or len(identity_matches) != 1:
            raise ValueError("default catalog entity row is invalid")
        identity_policy = identity_matches[0]
        scope_cell = columns[3]
        named_scopes = {
            name: scope for name, scope in re.findall(r"`([^`]+)`: ([GP])", scope_cell)
        }
        exception_types = set(
            re.findall(r"`([^`]+)`", scope_cell.split("except", 1)[1])
            if "except" in scope_cell else ()
        )
        for type_id in type_ids:
            default_scope = (
                "P" if type_id in exception_types
                else scope_cell if scope_cell in {"G", "P"} else "G"
            )
            scope = named_scopes.get(type_id, default_scope)
            declarations.append({
                "type_id": type_id, "parent_type_id": parent,
                "identity_policy_id": identity_policy, "scope": scope,
            })
    return tuple(sorted(declarations, key=lambda item: item["type_id"]))


def _ledger_rows(markdown: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    in_ledger = False
    for line in markdown.splitlines():
        if line == "## Relation ledger":
            in_ledger = True
            continue
        if in_ledger and line.startswith("There are 53"):
            break
        if not in_ledger or not line.startswith("| `"):
            continue
        columns = [column.strip() for column in line.strip("|").split("|")]
        if len(columns) != 7:
            raise ValueError("default catalog ledger row is invalid")
        relation_id = columns[0].strip("`")
        subject_contract, object_contract = (
            value.strip() for value in columns[1].split("->", 1)
        )
        literal_policy = _LITERAL_POLICIES.get(relation_id)
        lifecycle, read_form = (value.strip() for value in columns[4].split("/", 1))
        wording = relation_id.replace("_", " ")
        rows.append({
            "relation_id": relation_id,
            "endpoint_contract": columns[1],
            "subject_type_ids": _type_ids(subject_contract),
            "object_entity_type_ids": (
                () if literal_policy is not None else _type_ids(object_contract)
            ),
            "object_value_type": literal_policy[0] if literal_policy is not None else None,
            "value_policy_id": literal_policy[1] if literal_policy is not None else None,
            "value_policy_digest": (
                DEFAULT_CATALOG_VALUE_POLICIES[literal_policy[1]].policy_digest
                if literal_policy is not None else None
            ),
            "scope": columns[2],
            "evidence": columns[3],
            "lifecycle": lifecycle,
            "read_form": read_form,
            "read_derivation_policy": (
                "symmetric_view" if relation_id in _SYMMETRIC_READ_RELATIONS else "none"
            ),
            "meaning": columns[5],
            "coverage": tuple(sorted(columns[6].split(","))),
            "requires_private_denial": columns[2] == "P",
            "cases": (
                {"kind": "assertion", "source_text": f"Fixture subject explicitly {wording} fixture object.", "expected_predicate_id": relation_id, "expected_effect": "commit"},
                {"kind": "abstention", "source_text": f"Fixture subject and fixture object appear together, but no {wording} claim is made.", "expected_predicate_id": relation_id, "expected_effect": "zero_effect"},
                {"kind": "revision", "source_text": f"Correction: fixture subject no longer {wording} fixture object.", "expected_predicate_id": relation_id, "expected_effect": "revise"},
                {"kind": "current_read", "source_text": f"What currently {wording} for fixture subject?", "expected_predicate_id": relation_id, "expected_effect": "read_current"},
                {"kind": "historical_read", "source_text": f"What is the history of {wording} for fixture subject?", "expected_predicate_id": relation_id, "expected_effect": "read_history"},
            ),
        })
    return rows


def generate(*, design_path: Path, output_path: Path) -> None:
    design_bytes = design_path.read_bytes()
    body = {
        "schema_version": 1,
        "source_contract_sha256": hashlib.sha256(design_bytes).hexdigest(),
        "entity_types": _entity_declarations(design_bytes.decode("utf-8")),
        "rows": tuple(sorted(_ledger_rows(design_bytes.decode("utf-8")), key=lambda row: row["relation_id"])),
        "user_context_coverage": ("H8",),
    }
    corpus = DefaultCatalogAcceptanceCorpus(
        **body,
        corpus_digest=contract_digest(
            b"memorii.learned-ontology.default-acceptance-corpus.v1", body
        ),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            corpus.model_dump(mode="json"), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--design", type=Path,
        default=Path("docs/design/learned_ontology_base_catalog.md"),
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path(
            "memorii/memorii/core/semantic_ingestion/resources/"
            "default_catalog_acceptance_corpus.v1.json"
        ),
    )
    args = parser.parse_args()
    generate(design_path=args.design, output_path=args.output)


if __name__ == "__main__":
    main()
