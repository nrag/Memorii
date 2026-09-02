"""Encode/revalidation multiplicity census for one enabled delivery.

Instruments one deterministic corpus delivery through the public sync_event
root (the same composition as the wall-clock harness) with pure counters:

- ``encode_semantic_contract_result`` calls split into total, unique
  ``(type, id)`` pairs, and unique types — the identity-memo ceiling;
- ``decode_semantic_contract`` calls split into total and unique
  ``(type, raw-bytes)`` pairs — the decode-memo ceiling;
- ``contract_digest`` calls from ``validate_content_digest`` (the accounting
  counter the wall-clock harness also records);
- wall-clock elapsed for context.

No behavior is changed; wrappers delegate to the originals.  Output is a
single JSON line on stdout.
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

ROOT = Path("/Users/nandaraghunathan/Code/Memorii/Memorii")
VECTORS = ROOT / "docs/design/semantic_ingestion/traceability_golden_vectors"
sys.path.insert(0, str(VECTORS))

import memorii.core.semantic_ingestion.contracts as semantic_contracts
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.memory_plane.service import MemoryPlaneService
from tests.unit.core.semantic_ingestion.test_bootstrap_graph_coordinator_v3 import (
    _delivery,
    _production_recovery_service,
)

DELIVERY_CONTENT = "Atlas owner is Alice."
DELIVERY_TIMESTAMP = datetime(2026, 7, 30, tzinfo=UTC)


def main() -> None:
    service = _production_recovery_service(plane=MemoryPlaneService())
    assert service._canonical_evidence_enabled is True

    encode_calls = 0
    encode_unique_pairs: set[tuple[str, int]] = set()
    encode_by_type: Counter[str] = Counter()
    encode_unique_by_type: Counter[str] = Counter()
    original_encode_result = semantic_contracts.encode_semantic_contract_result

    def counting_encode_result(value, *, canonical_staging=None):
        nonlocal encode_calls
        encode_calls += 1
        type_name = f"{type(value).__module__}.{type(value).__qualname__}"
        pair = (type_name, id(value))
        encode_by_type[type_name] += 1
        if pair not in encode_unique_pairs:
            encode_unique_pairs.add(pair)
            encode_unique_by_type[type_name] += 1
        return original_encode_result(value, canonical_staging=canonical_staging)

    semantic_contracts.encode_semantic_contract_result = counting_encode_result

    decode_calls = 0
    decode_unique_pairs: set[tuple[str, bytes]] = set()
    decode_by_type: Counter[str] = Counter()
    original_decode = semantic_contracts.decode_semantic_contract

    def counting_decode(raw, expected_type, *, max_nodes=None, max_depth=None):
        nonlocal decode_calls
        decode_calls += 1
        type_name = f"{expected_type.__module__}.{expected_type.__qualname__}"
        decode_by_type[type_name] += 1
        decode_unique_pairs.add((type_name, raw))
        return original_decode(raw, expected_type, max_nodes=max_nodes, max_depth=max_depth)

    semantic_contracts.decode_semantic_contract = counting_decode

    content_digest_calls = 0
    original_digest = semantic_contracts.contract_digest

    def counted(domain: bytes, value: object) -> str:
        nonlocal content_digest_calls
        frame = sys._getframe(1)
        if frame.f_code.co_name == "validate_content_digest":
            content_digest_calls += 1
        return original_digest(domain, value)

    semantic_contracts.contract_digest = counted

    started = time.perf_counter()
    try:
        result = _delivery(service, "encode-revalidation-census")
    finally:
        semantic_contracts.contract_digest = original_digest
        semantic_contracts.decode_semantic_contract = original_decode
        semantic_contracts.encode_semantic_contract_result = original_encode_result
    elapsed = time.perf_counter() - started

    records = sorted(service._memory_plane.list_records(), key=lambda record: record.memory_id)
    output = encode_typed_value(
        {
            "result": result.model_dump(mode="python"),
            "records": tuple(record.model_dump(mode="python") for record in records),
        }
    )
    print(
        json.dumps(
            {
                "elapsed_seconds": elapsed,
                "output_sha256": sha256(output).hexdigest(),
                "content_digest_calls": content_digest_calls,
                "encode_result_calls": encode_calls,
                "encode_unique_type_id_pairs": len(encode_unique_pairs),
                "encode_identity_memo_saved_calls": encode_calls - len(encode_unique_pairs),
                "encode_calls_by_type": dict(encode_by_type.most_common()),
                "encode_unique_by_type": dict(encode_unique_by_type.most_common()),
                "decode_calls": decode_calls,
                "decode_unique_type_bytes_pairs": len(decode_unique_pairs),
                "decode_memo_saved_calls": decode_calls - len(decode_unique_pairs),
                "decode_calls_by_type": dict(decode_by_type.most_common()),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
