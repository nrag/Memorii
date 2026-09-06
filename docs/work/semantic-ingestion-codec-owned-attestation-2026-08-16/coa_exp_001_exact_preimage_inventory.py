from __future__ import annotations

import inspect
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

import run_scenario_ingress as runner
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.provider.models import ProviderOperation
from memorii.core.semantic_ingestion import contracts
from memorii.core.semantic_ingestion.canonical_evidence_arena import CanonicalEvidenceArena
from tests.fixtures.semantic_ingestion.scenario_fixture_authority import (
    build_scenario_test_provider_service,
)


def main() -> None:
    world = json.loads((VECTORS / "scenario-first-v1.json").read_text(encoding="utf-8"))
    scenario = runner.validate(world)[0]
    observation = runner.render(scenario)[0]
    operation_id = runner._opaque_event_id(ordinal=0, source_bytes=observation.text.encode("utf-8"))
    service = build_scenario_test_provider_service(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: datetime(2026, 7, 30, tzinfo=UTC),
    )

    # Reserve every process slot so sync_event's arena deterministically executes
    # the complete legacy path without changing production behavior.
    reservations = [CanonicalEvidenceArena() for _ in range(64)]
    if not all(arena.snapshot().reservation_acquired for arena in reservations):
        raise RuntimeError("COA-EXP-001 could not reserve the complete process budget")

    original = contracts.contract_digest
    all_calls = 0
    exactness_failures: list[str] = []
    identities: Counter[tuple[str, str, tuple[str, ...], str, str, int]] = Counter()

    def observed_contract_digest(domain: bytes, value: object) -> str:
        nonlocal all_calls
        all_calls += 1
        legacy_digest = original(domain, value)
        caller = inspect.currentframe()
        caller = caller.f_back if caller is not None else None
        if caller is None or caller.f_code.co_name != "validate_content_digest":
            return legacy_digest
        contract = caller.f_locals.get("self")
        if not isinstance(contract, contracts._ContentAddressedContract):
            exactness_failures.append("validator caller did not own a content-addressed contract")
            return legacy_digest
        canonical_value = contracts.canonical_contract_value(value)
        canonical_bytes = encode_typed_value(canonical_value)
        independently_recomputed = sha256(domain + b"\0" + canonical_bytes).hexdigest()
        if independently_recomputed != legacy_digest:
            exactness_failures.append(f"digest mismatch for {type(contract).__qualname__}")
        excluded = tuple(sorted(type(contract)._digest_excluded_fields))
        identities[
            (
                f"{type(contract).__module__}.{type(contract).__qualname__}",
                domain.hex(),
                excluded,
                sha256(canonical_bytes).hexdigest(),
                legacy_digest,
                len(canonical_bytes),
            )
        ] += 1
        return legacy_digest

    contracts.contract_digest = observed_contract_digest
    started = time.perf_counter()
    try:
        service.sync_event(
            operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
            content=observation.text,
            operation_id=operation_id,
            session_id=runner._PUBLIC_SCOPE[1],
            task_id=runner._PUBLIC_SCOPE[2],
            user_id=runner._PUBLIC_SCOPE[0],
            language="en",
            speaker_id="scenario-speaker",
            timestamp=observation.timestamp,
            authenticated_host_ingress=runner._host_ingress(ordinal=0),
        )
    finally:
        contracts.contract_digest = original
        for arena in reservations:
            arena.close()
    elapsed = time.perf_counter() - started

    rows = sorted(
        (
            {
                "contract_type": key[0],
                "domain_hex": key[1],
                "excluded_fields": list(key[2]),
                "canonical_bytes_sha256": key[3],
                "digest": key[4],
                "canonical_byte_length": key[5],
                "occurrences": count,
            }
            for key, count in identities.items()
        ),
        key=lambda row: (-row["occurrences"], row["contract_type"], row["digest"]),
    )
    content_calls = sum(row["occurrences"] for row in rows)
    repeated = sum(row["occurrences"] - 1 for row in rows)
    digest_to_metadata: dict[str, set[tuple[object, ...]]] = {}
    for row in rows:
        digest_to_metadata.setdefault(row["digest"], set()).add(
            (
                row["contract_type"],
                row["domain_hex"],
                tuple(row["excluded_fields"]),
                row["canonical_bytes_sha256"],
                row["canonical_byte_length"],
            )
        )
    ambiguous_digests = sorted(digest for digest, values in digest_to_metadata.items() if len(values) != 1)
    result = {
        "schema": "memorii.semantic-ingestion.codec-attestation.exact-preimage-inventory.v1",
        "experiment": "COA-EXP-001",
        "evidence_stage": "reference_only_feasibility",
        "certifies_m3_1": False,
        "candidate_lock_sha256": "24da95523b9a050266034cd6f3b923d52a4d8cc97cf83d32d83c1285bb2d99c3",
        "legacy_fallback": "process_reservation_saturation",
        "elapsed_seconds": elapsed,
        "all_contract_digest_calls": all_calls,
        "content_addressed_calls": content_calls,
        "content_addressed_call_fraction": content_calls / all_calls,
        "unique_content_identities": len(rows),
        "redundant_content_calls": repeated,
        "maximum_repetition": max((row["occurrences"] for row in rows), default=0),
        "canonical_bytes_total_unique": sum(row["canonical_byte_length"] for row in rows),
        "canonical_bytes_max_entry": max((row["canonical_byte_length"] for row in rows), default=0),
        "exactness_failures": exactness_failures,
        "ambiguous_digest_identities": ambiguous_digests,
        "identities": rows,
    }
    if exactness_failures or ambiguous_digests or content_calls == 0:
        raise RuntimeError(json.dumps(result, sort_keys=True))
    output = Path(__file__).with_name("evidence") / "coa-exp-001-exact-preimage-inventory-v1.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "identities"}, sort_keys=True))


if __name__ == "__main__":
    main()
