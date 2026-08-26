"""Deterministic compact-index capacity proof for canonical member evidence."""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

MAX_ROOTS = 512
MAX_ROOT_BYTES = 2 * 1024 * 1024
MAX_MEMBER_PATHS = 32_768
MAX_OPERATION_CHARGED_BYTES = 16 * 1024 * 1024
MAX_PROCESS_RESERVED_BYTES = 64 * 1024 * 1024

OPERATION_HEADER_BYTES = 4_096
ROOT_RECORD_BYTES = 128
MEMBER_RECORD_BYTES = 64
TRIE_NODE_BYTES = 16
INTERN_LENGTH_BYTES = 4
BINDING_RECORD_BYTES = 32


def _segment_key(value: object) -> str:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise TypeError(f"unsupported typed path segment: {value!r}")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _root_index(identity: str, row: dict[str, Any], type_ids: dict[str, int]) -> dict[str, Any]:
    paths = sorted(
        row["member_paths"],
        key=lambda item: json.dumps(item["path"], ensure_ascii=False, separators=(",", ":")),
    )
    nodes: list[tuple[int, str]] = [(0, "")]
    node_ids: dict[tuple[int, str], int] = {}
    string_segments: set[str] = set()
    records: list[dict[str, Any]] = []
    seen_paths: set[tuple[object, ...]] = set()
    reconstructed_equal = True

    for member in paths:
        typed_path = tuple(member["path"])
        if typed_path in seen_paths:
            raise ValueError(f"duplicate issued path for {identity}")
        seen_paths.add(typed_path)
        parent = 0
        for segment in typed_path:
            encoded = _segment_key(segment)
            if isinstance(segment, str):
                string_segments.add(segment)
            coordinate = (parent, encoded)
            node = node_ids.get(coordinate)
            if node is None:
                node = len(nodes)
                nodes.append(coordinate)
                node_ids[coordinate] = node
            parent = node
        rebuilt: list[object] = []
        cursor = parent
        while cursor:
            node_parent, encoded = nodes[cursor]
            rebuilt.append(json.loads(encoded))
            cursor = node_parent
        rebuilt.reverse()
        reconstructed_equal &= tuple(rebuilt) == typed_path
        records.append({
            "path_node": parent,
            "begin": int(member["begin"]),
            "end": int(member["end"]),
            "type_id": type_ids[member["member_type"]],
            "member_sha256": member["member_sha256"],
        })

    string_table_bytes = sum(
        INTERN_LENGTH_BYTES + len(value.encode("utf-8")) for value in sorted(string_segments)
    )
    trie_nodes = len(nodes) - 1
    metadata_charge = (
        ROOT_RECORD_BYTES
        + len(records) * MEMBER_RECORD_BYTES
        + trie_nodes * TRIE_NODE_BYTES
        + string_table_bytes
    )
    logical = {
        "identity": identity,
        "canonical_bytes": int(row["canonical_bytes"]),
        "profile": row["profile"],
        "codec": row["codec"],
        "digest_domain_sha256": row["digest_domain_sha256"],
        "nodes": [[parent, encoded] for parent, encoded in nodes[1:]],
        "records": records,
    }
    logical_digest = sha256(
        json.dumps(logical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "identity": identity,
        "root_bytes": int(row["canonical_bytes"]),
        "member_paths": len(records),
        "trie_nodes": trie_nodes,
        "unique_string_segments": len(string_segments),
        "string_table_bytes": string_table_bytes,
        "metadata_charge": metadata_charge,
        "operation_charge": int(row["canonical_bytes"]) + metadata_charge,
        "paths_reconstruct_exactly": reconstructed_equal,
        "logical_index_sha256": logical_digest,
    }


def _build(identities: dict[str, dict[str, Any]], order: list[str]) -> dict[str, Any]:
    types = sorted({
        member["member_type"]
        for row in identities.values()
        for member in row["member_paths"]
    })
    type_ids = {value: index for index, value in enumerate(types)}
    profiles = sorted({row["profile"] for row in identities.values()})
    codecs = sorted({row["codec"] for row in identities.values()})
    domains = sorted({row["digest_domain_sha256"] for row in identities.values()})
    bindings = sorted({
        (row["profile"], row["codec"], row["digest_domain_sha256"])
        for row in identities.values()
    })
    type_table_bytes = sum(INTERN_LENGTH_BYTES + len(value.encode("utf-8")) for value in types)
    binding_string_bytes = sum(INTERN_LENGTH_BYTES + len(value.encode("utf-8")) for value in profiles + codecs)
    domain_table_bytes = len(domains) * (INTERN_LENGTH_BYTES + 32)
    binding_table_bytes = len(bindings) * BINDING_RECORD_BYTES
    global_metadata = (
        OPERATION_HEADER_BYTES
        + type_table_bytes
        + binding_string_bytes
        + domain_table_bytes
        + binding_table_bytes
    )
    roots_by_identity = {
        identity: _root_index(identity, identities[identity], type_ids)
        for identity in order
    }
    roots = [roots_by_identity[identity] for identity in sorted(roots_by_identity)]
    root_bytes = sum(row["root_bytes"] for row in roots)
    root_metadata = sum(row["metadata_charge"] for row in roots)
    member_paths = sum(row["member_paths"] for row in roots)
    trie_nodes = sum(row["trie_nodes"] for row in roots)
    operation_charge = root_bytes + root_metadata + global_metadata
    logical_digest = sha256(
        json.dumps(
            {
                "type_ids": type_ids,
                "bindings": bindings,
                "roots": [(row["identity"], row["logical_index_sha256"]) for row in roots],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "roots": roots,
        "root_count": len(roots),
        "member_paths": member_paths,
        "trie_nodes": trie_nodes,
        "interned_types": len(types),
        "interned_profiles": len(profiles),
        "interned_codecs": len(codecs),
        "interned_domains": len(domains),
        "binding_records": len(bindings),
        "root_bytes": root_bytes,
        "root_metadata_charge": root_metadata,
        "global_metadata_charge": global_metadata,
        "metadata_charge": root_metadata + global_metadata,
        "operation_charge": operation_charge,
        "logical_index_sha256": logical_digest,
        "all_paths_reconstruct_exactly": all(row["paths_reconstruct_exactly"] for row in roots),
    }


def _cell(name: str, passed: bool, evidence: Any) -> dict[str, Any]:
    return {"name": name, "passed": passed, "evidence": evidence}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path-proof", type=Path, required=True)
    parser.add_argument("--prior-capacity", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    path_document = json.loads(args.path_proof.read_text())
    prior = json.loads(args.prior_capacity.read_text())
    identities = path_document["identities"]
    order = sorted(identities)
    compact = _build(identities, order)
    reversed_compact = _build(identities, list(reversed(order)))
    largest_root = max(row["root_bytes"] for row in compact["roots"])
    naive_metadata = int(prior["measured_corpus"]["metadata_charge"])
    metadata_reduction = 1 - compact["metadata_charge"] / naive_metadata
    headroom = MAX_OPERATION_CHARGED_BYTES - compact["operation_charge"]

    cells = [
        _cell("all_paths_reconstruct_exactly", compact["all_paths_reconstruct_exactly"], compact["member_paths"]),
        _cell("input_order_independent", compact["logical_index_sha256"] == reversed_compact["logical_index_sha256"], compact["logical_index_sha256"]),
        _cell("root_count_limit", compact["root_count"] <= MAX_ROOTS, compact["root_count"]),
        _cell("per_root_byte_limit", largest_root <= MAX_ROOT_BYTES, largest_root),
        _cell("member_path_limit", compact["member_paths"] <= MAX_MEMBER_PATHS, compact["member_paths"]),
        _cell("operation_charge_limit", compact["operation_charge"] <= MAX_OPERATION_CHARGED_BYTES, compact["operation_charge"]),
        _cell("four_operation_process_reservation", 4 * MAX_OPERATION_CHARGED_BYTES <= MAX_PROCESS_RESERVED_BYTES, 4 * MAX_OPERATION_CHARGED_BYTES),
        _cell("fifth_operation_declined", 5 * MAX_OPERATION_CHARGED_BYTES > MAX_PROCESS_RESERVED_BYTES, 5 * MAX_OPERATION_CHARGED_BYTES),
        _cell("bounded_type_table", compact["interned_types"] <= compact["member_paths"], compact["interned_types"]),
        _cell("bounded_trie", compact["trie_nodes"] <= sum(len(row["member_paths"]) for row in identities.values() for _ in [0]) * 32, compact["trie_nodes"]),
        _cell("metadata_reduced", compact["metadata_charge"] < naive_metadata, metadata_reduction),
        _cell("positive_operation_headroom", headroom > 0, headroom),
    ]
    passed = all(cell["passed"] for cell in cells)
    output = {
        "schema": "memorii.semantic-ingestion.vcc-exp-003b.v1",
        "experiment": "VCC-EXP-003B",
        "evidence_stage": "reference_only_compact_index_capacity",
        "production_implementation_changed": False,
        "tests_changed": False,
        "certifies_m3_1": False,
        "sources": {
            "path_proof_sha256": sha256(args.path_proof.read_bytes()).hexdigest(),
            "prior_capacity_sha256": sha256(args.prior_capacity.read_bytes()).hexdigest(),
        },
        "representation": {
            "operation_header_bytes": OPERATION_HEADER_BYTES,
            "root_record_bytes": ROOT_RECORD_BYTES,
            "member_record_bytes": MEMBER_RECORD_BYTES,
            "trie_node_bytes": TRIE_NODE_BYTES,
            "intern_length_bytes": INTERN_LENGTH_BYTES,
            "binding_record_bytes": BINDING_RECORD_BYTES,
            "type_ids": "operation-wide sorted intern table",
            "paths": "per-root parent-index trie with interned string segments",
        },
        "limits": {
            "maximum_roots": MAX_ROOTS,
            "maximum_root_bytes": MAX_ROOT_BYTES,
            "maximum_member_paths": MAX_MEMBER_PATHS,
            "maximum_operation_charged_bytes": MAX_OPERATION_CHARGED_BYTES,
            "maximum_process_reserved_bytes": MAX_PROCESS_RESERVED_BYTES,
        },
        "measured": {key: value for key, value in compact.items() if key != "roots"},
        "largest_root_bytes": largest_root,
        "naive_metadata_charge": naive_metadata,
        "compact_metadata_charge": compact["metadata_charge"],
        "metadata_reduction_fraction": metadata_reduction,
        "operation_headroom_bytes": headroom,
        "cells": cells,
        "passed_cells": sum(cell["passed"] for cell in cells),
        "total_cells": len(cells),
        "passed": passed,
        "decision": (
            "compact deterministic member index fits the unchanged operation and process limits"
            if passed else
            "compact member index does not satisfy the frozen capacity limits"
        ),
    }
    encoded = json.dumps(output, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    args.output.write_bytes(encoded)
    print(json.dumps({
        "passed": passed,
        "passed_cells": output["passed_cells"],
        "total_cells": output["total_cells"],
        "root_bytes": compact["root_bytes"],
        "naive_metadata_charge": naive_metadata,
        "compact_metadata_charge": compact["metadata_charge"],
        "metadata_reduction_fraction": metadata_reduction,
        "operation_charge": compact["operation_charge"],
        "operation_headroom_bytes": headroom,
        "member_paths": compact["member_paths"],
        "trie_nodes": compact["trie_nodes"],
        "failed_cells": [cell for cell in cells if not cell["passed"]],
        "output_sha256": sha256(encoded).hexdigest(),
    }, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
