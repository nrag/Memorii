"""Generate the v11 sealed-authority production binding contract."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
LEDGER = HERE / "production-entrypoint-bindings-v11.json"
ORACLE = HERE / "production-owner-oracle-v8.json"
EXPECTED = HERE / "production-entrypoint-expected-graph-v11.json"
EDGES = (
    ("service_owner", "memorii/memorii/core/provider/service.py", "CanonicalEvidenceArena("),
    ("service_handoff", "memorii/memorii/core/provider/service.py", "canonical_evidence_arena=canonical_evidence_arena"),
    ("coordinator_stage", "memorii/memorii/core/provider/ingestion.py", "canonical_staging=canonical_evidence_arena"),
    ("coordinator_seal", "memorii/memorii/core/provider/ingestion.py", "bind_and_seal(CanonicalValidationScope("),
    ("coordinator_lookup", "memorii/memorii/core/provider/ingestion.py", "lookup_sealed("),
    ("coordinator_lease", "memorii/memorii/core/provider/ingestion.py", "canonical_evidence_lease=lease"),
    ("codec_explicit_stage", "memorii/memorii/core/semantic_ingestion/contracts.py", "def encode_semantic_contract_result("),
    ("codec_stage_parameter", "memorii/memorii/core/semantic_ingestion/contracts.py", "canonical_staging:"),
    ("arena_bind", "memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py", "def bind_and_seal("),
    ("arena_lookup", "memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py", "def lookup_sealed("),
    ("atomic_lease", "memorii/memorii/core/memory_evolution/atomic_store.py", "canonical_evidence_lease: CanonicalEvidenceLease | None"),
    ("atomic_tenant", "memorii/memorii/core/memory_evolution/atomic_store.py", "scope.tenant"),
    ("atomic_writer", "memorii/memorii/core/memory_evolution/atomic_store.py", "scope.writer != f\"{current.admission_digest}:{current.writer_epoch}\""),
)
FORBIDDEN = (("memorii/memorii/core/semantic_ingestion/contracts.py", "current_canonical_evidence_arena"), ("memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py", "ContextVar"), ("memorii/memorii/core/provider/ingestion.py", "arena_nonce"), ("memorii/memorii/core/provider/service.py", "arena_nonce"))
MUTATIONS = tuple([f"remove_{item[0]}" for item in EDGES] + [f"forbidden_{index}" for index in range(len(FORBIDDEN))] + [f"disconnect_{item[0]}" for item in EDGES] + ["scope_operation", "scope_generation"])

def main() -> None:
    paths = sorted({item[1] for item in EDGES} | {item[0] for item in FORBIDDEN})
    sources = {path: (ROOT / path).read_text(encoding="utf-8") for path in paths}
    contract = {"schema": "memorii.production-entrypoint-bindings.v11", "family": "prepared_source_sealed_authority", "edges": [list(item) for item in EDGES], "forbidden_ambient_tokens": [list(item) for item in FORBIDDEN], "expected_mutation_names": list(MUTATIONS), "source_hashes": {path: sha256(source.encode()).hexdigest() for path, source in sources.items()}}
    for target in (LEDGER, ORACLE, EXPECTED):
        target.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
