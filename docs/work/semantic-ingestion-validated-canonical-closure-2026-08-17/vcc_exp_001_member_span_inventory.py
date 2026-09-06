"""Reference-only feasibility check for exact canonical member spans."""

from __future__ import annotations

import argparse
import json
from dataclasses import fields, is_dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.semantic_ingestion.contracts import (
    SemanticContractCodecError,
    canonical_contract_value,
    encode_semantic_contract,
)
from tests.fixtures.semantic_ingestion.source_normalization_fixture_builder import (
    build_bootstrap_declared_prepared_source,
    build_bootstrap_v3_fixture_authority,
)
from tests.unit.core.semantic_ingestion.clean_room_request_test_support import (
    build_clean_room_semantic_proposal_request,
)

PROFILE = "semantic-ingestion-canonical-profile-v1"
CODEC = "semantic-contract-envelope-v1"


class JsonSpanScanner:
    """Parse UTF-8 JSON and retain every value's exact half-open byte span."""

    def __init__(self, raw: bytes) -> None:
        self.raw = raw
        self.spans: list[tuple[tuple[object, ...], int, int]] = []

    def scan(self) -> list[tuple[tuple[object, ...], int, int]]:
        end = self._value(0, ())
        if end != len(self.raw):
            raise ValueError("trailing canonical JSON bytes")
        return self.spans

    def _value(self, start: int, path: tuple[object, ...]) -> int:
        if start >= len(self.raw):
            raise ValueError("truncated canonical JSON")
        marker = self.raw[start]
        if marker == ord('"'):
            end = self._string(start)
        elif marker == ord('{'):
            end = self._object(start, path)
        elif marker == ord('['):
            end = self._array(start, path)
        else:
            end = start
            while end < len(self.raw) and self.raw[end] not in b",]}":
                end += 1
            json.loads(self.raw[start:end])
        self.spans.append((path, start, end))
        return end

    def _string(self, start: int) -> int:
        index = start + 1
        while index < len(self.raw):
            if self.raw[index] == ord('\\'):
                index += 2
                continue
            if self.raw[index] == ord('"'):
                return index + 1
            index += 1
        raise ValueError("unterminated JSON string")

    def _array(self, start: int, path: tuple[object, ...]) -> int:
        index = start + 1
        item = 0
        if index < len(self.raw) and self.raw[index] == ord(']'):
            return index + 1
        while True:
            index = self._value(index, path + (item,))
            item += 1
            if self.raw[index] == ord(']'):
                return index + 1
            if self.raw[index] != ord(','):
                raise ValueError("invalid JSON array separator")
            index += 1

    def _object(self, start: int, path: tuple[object, ...]) -> int:
        index = start + 1
        if index < len(self.raw) and self.raw[index] == ord('}'):
            return index + 1
        while True:
            key_end = self._string(index)
            key = json.loads(self.raw[index:key_end])
            index = key_end
            if self.raw[index] != ord(':'):
                raise ValueError("invalid JSON object separator")
            index = self._value(index + 1, path + (key,))
            if self.raw[index] == ord('}'):
                return index + 1
            if self.raw[index] != ord(','):
                raise ValueError("invalid JSON object member separator")
            index += 1


def _models(value: object, path: tuple[object, ...] = ()) -> list[tuple[tuple[object, ...], BaseModel]]:
    found: list[tuple[tuple[object, ...], BaseModel]] = []
    seen: set[int] = set()

    def visit(item: object, item_path: tuple[object, ...]) -> None:
        if isinstance(item, (str, bytes, int, bool, type(None))):
            return
        identity = id(item)
        if identity in seen:
            return
        seen.add(identity)
        if isinstance(item, BaseModel):
            found.append((item_path, item))
            for name in type(item).model_fields:
                visit(getattr(item, name), item_path + (name,))
            return
        if is_dataclass(item) and not isinstance(item, type):
            for field in fields(item):
                visit(getattr(item, field.name), item_path + (field.name,))
            return
        if isinstance(item, dict):
            for key, child in item.items():
                visit(child, item_path + (str(key),))
            return
        if isinstance(item, (tuple, list, set, frozenset)):
            for index, child in enumerate(item):
                visit(child, item_path + (index,))

    visit(value, path)
    return found


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    census_document = json.loads(args.census.read_text())
    census = census_document["census"]
    frozen = census["identities"]
    required_fields = {
        "family", "content_digest", "canonical_bytes", "classification",
        "contexts", "first_stack", "root_families",
    }
    inventory_metadata_complete = all(required_fields <= set(row) for row in frozen.values())

    text = "Alice starts project Atlas. " * 4
    source_digest = sha256(text.encode("utf-8")).hexdigest()
    request = build_clean_room_semantic_proposal_request(
        source_id="clean-room-source", source_digest=source_digest, source_text=text
    )
    prepared = build_bootstrap_declared_prepared_source(
        source_id="clean-room-source", source_digest=source_digest, source_text=text
    )
    authority = build_bootstrap_v3_fixture_authority(source=prepared)
    observed_models = _models((request, prepared, authority))

    supported: dict[str, tuple[BaseModel, bytes]] = {}
    for _path, model in observed_models:
        try:
            canonical = encode_semantic_contract(model)
        except SemanticContractCodecError:
            continue
        key = f"{type(model).__module__}.{type(model).__qualname__}:{sha256(canonical).hexdigest()}"
        supported[key] = (model, canonical)

    root_results: list[dict[str, object]] = []
    member_links = 0
    exact_member_links = 0
    ambiguous_member_links = 0
    absent_member_links = 0
    all_span_reencodes_equal = True
    all_roots_equal = True

    for key, (root, canonical) in sorted(supported.items()):
        spans = JsonSpanScanner(canonical).scan()
        span_rows = []
        for span_path, begin, end in spans:
            decoded = json.loads(canonical[begin:end])
            equal = _canonical_json(decoded) == canonical[begin:end]
            all_span_reencodes_equal &= equal
            span_rows.append((span_path, begin, end))
        all_roots_equal &= encode_semantic_contract(root) == canonical

        links = []
        for typed_path, member in _models(root):
            member_links += 1
            member_payload = encode_typed_value(canonical_contract_value(member))
            candidates = [
                {"canonical_path": list(path), "begin": begin, "end": end}
                for path, begin, end in span_rows
                if canonical[begin:end] == member_payload
            ]
            if len(candidates) == 1:
                exact_member_links += 1
                status = "exact_unambiguous"
            elif candidates:
                ambiguous_member_links += 1
                status = "exact_ambiguous"
            else:
                absent_member_links += 1
                status = "absent"
            links.append({
                "typed_path": list(typed_path),
                "member_type": f"{type(member).__module__}.{type(member).__qualname__}",
                "payload_sha256": sha256(member_payload).hexdigest(),
                "candidate_spans": candidates,
                "status": status,
            })
        root_results.append({
            "identity": key,
            "profile": PROFILE,
            "codec": CODEC,
            "domain": "memorii.semantic-ingestion.contract-envelope.v1",
            "canonical_bytes": len(canonical),
            "root_span_count": len(span_rows),
            "member_links": links,
        })

    observed_keys = set(supported)
    frozen_keys = set(frozen)
    matched = observed_keys & frozen_keys
    missing = frozen_keys - observed_keys
    extra = observed_keys - frozen_keys
    passed = (
        inventory_metadata_complete
        and len(frozen) == census["unique_content_identities"] == 238
        and not missing
        and not extra
        and all_roots_equal
        and all_span_reencodes_equal
        and absent_member_links == 0
        and ambiguous_member_links == 0
    )
    output = {
        "schema": "memorii.semantic-ingestion.vcc-exp-001.v1",
        "experiment": "VCC-EXP-001",
        "evidence_stage": "reference_only_feasibility",
        "production_implementation_changed": False,
        "tests_changed": False,
        "profile": PROFILE,
        "codec": CODEC,
        "frozen_inventory": {
            "identities": len(frozen),
            "metadata_complete": inventory_metadata_complete,
            "unique_content_identities_claim": census["unique_content_identities"],
            "classification_identity_counts": census["classification_identity_counts"],
        },
        "regeneration": {
            "supported_identities": len(observed_keys),
            "matched_frozen_identities": len(matched),
            "missing_frozen_identities": len(missing),
            "extra_identities": len(extra),
            "missing_by_family": _counts(frozen[key]["family"] for key in missing),
            "extra_by_family": _counts(key.rsplit(":", 1)[0] for key in extra),
        },
        "span_proof": {
            "roots": len(root_results),
            "all_root_reencodes_equal": all_roots_equal,
            "all_json_span_reencodes_equal": all_span_reencodes_equal,
            "member_links": member_links,
            "exact_unambiguous_member_links": exact_member_links,
            "exact_ambiguous_member_links": ambiguous_member_links,
            "absent_member_links": absent_member_links,
        },
        "owner_binding": {
            "source": "frozen census first_stack, contexts, boundary_events, and root_families",
            "all_frozen_identities_have_owner_stack": all(bool(row["first_stack"]) for row in frozen.values()),
            "all_frozen_identities_have_context": all(bool(row["contexts"]) for row in frozen.values()),
        },
        "passed": passed,
        "decision": (
            "member-span inventory is feasible for the complete frozen identity set"
            if passed else
            "thin fixture is insufficient for complete frozen-set proof or deterministic typed-to-canonical paths need refinement"
        ),
        "roots": root_results,
    }
    encoded = json.dumps(output, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    args.output.write_bytes(encoded)
    print(json.dumps({
        "passed": passed,
        "frozen": len(frozen),
        "matched": len(matched),
        "missing": len(missing),
        "extra": len(extra),
        **output["span_proof"],
        "output_sha256": sha256(encoded).hexdigest(),
    }, sort_keys=True))
    return 0 if passed else 2


def _counts(values: Any) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return dict(sorted(result.items()))


if __name__ == "__main__":
    raise SystemExit(main())
