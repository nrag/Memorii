from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "production-entrypoint-bindings-v2.json"
OUTPUT = HERE / "production-entrypoint-bindings-v3.json"


VALIDATION = {
    "VCC-R01": ("memorii/memorii/core/semantic_ingestion/contracts.py", "def decode_semantic_contract("),
    "VCC-R02": ("memorii/memorii/core/semantic_ingestion/contracts.py", "def decode_semantic_contract("),
    "VCC-R03": ("memorii/memorii/core/semantic_ingestion/authorization.py", "def apply_verified_transition("),
    "VCC-R04": ("memorii/memorii/core/memory_evolution/ingestion_contracts.py", "def decode_typed_value("),
    "VCC-R05": ("memorii/memorii/core/semantic_ingestion/bootstrap_graph_host.py", "def execute("),
    "VCC-R06": ("memorii/memorii/core/semantic_ingestion/source_normalization_execution.py", "def normalize_after_recovery_claim("),
    "VCC-R07": ("memorii/memorii/core/semantic_ingestion/persistence.py", "def persist("),
    "VCC-R08": ("memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py", "def admit_success("),
    "VCC-R09": ("memorii/memorii/core/semantic_ingestion/persistence.py", "def persist("),
    "VCC-R10": ("memorii/memorii/core/semantic_ingestion/production_authority.py", "def verified_production_authority_inputs("),
    "VCC-R11": ("memorii/memorii/core/provider/service.py", "def sync_event("),
    "VCC-R12": ("memorii/memorii/core/provider/service.py", "def sync_event("),
}

DURABLE = {
    "VCC-R03": ("memorii/memorii/core/semantic_ingestion/authorization.py", "def apply_verified_transition(", "writer_local_transition"),
    "VCC-R06": ("memorii/memorii/core/memory_evolution/atomic_store.py", "def bootstrap_writer_handoff(", "writer_handoff"),
    "VCC-R08": ("memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py", "def close(", "no_durable_write"),
}

FALLBACK = {
    "VCC-R01": ("memorii/memorii/core/provider/ingestion.py", "source_only"),
    "VCC-R02": ("memorii/memorii/core/semantic_ingestion/contracts.py", "SemanticContractCodecError"),
    "VCC-R03": ("memorii/memorii/core/provider/ingestion.py", "_admit_with_writer_retry"),
    "VCC-R04": ("memorii/memorii/core/memory_evolution/ingestion_contracts.py", "CanonicalTypedValueError"),
    "VCC-R05": ("memorii/memorii/core/provider/ingestion.py", "source_only"),
    "VCC-R06": ("memorii/memorii/core/provider/ingestion.py", "authority_unavailable"),
    "VCC-R07": ("memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py", "require_active_nonce"),
    "VCC-R08": ("memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py", "capacity_fallbacks"),
    "VCC-R09": ("memorii/memorii/core/semantic_ingestion/persistence.py", "retry"),
    "VCC-R10": ("memorii/memorii/core/provider/service.py", "verified_production_host_authority"),
    "VCC-R11": ("memorii/memorii/core/provider/service.py", "sync_event"),
    "VCC-R12": ("memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py", "capacity_fallbacks"),
}


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    rows = []
    for old in source["requirements"]:
        requirement = old["id"]
        owner_chain = old["owner_chain"]
        call_edges = [
            {
                "from_owner": owner_chain[index],
                "to_owner": owner_chain[index + 1],
                "status": "planned",
                "proof_id": f"{requirement}-EDGE-{index + 1:02d}",
            }
            for index in range(len(owner_chain) - 1)
        ]
        validation_path, validation_symbol = VALIDATION[requirement]
        durable_path, durable_symbol, durable_mode = DURABLE.get(
            requirement,
            ("memorii/memorii/core/semantic_ingestion/persistence.py", "def persist(", "unchanged_persistence"),
        )
        fallback_path, fallback_token = FALLBACK[requirement]
        parameters = list(old["authority_arguments"])
        rows.append(
            {
                "id": requirement,
                "status": "planned",
                "production_trigger": old["trigger"],
                "current_production_anchor": {
                    "from_path": "memorii/memorii/core/semantic_ingestion/production_capture.py",
                    "from_symbol": "def capture_cell(",
                    "edge_token": "service.sync_event(",
                    "to_path": "memorii/memorii/core/provider/service.py",
                    "to_symbol": "def sync_event(",
                    "caller_query_pattern": "\\.sync_event\\(",
                    "caller_query_roots": ["memorii/memorii/core", "memorii/memorii/integrations"],
                    "excluded_path_parts": ["benchmark", "test", "tests", "tools"],
                    "captured_non_test_callers": 5,
                },
                "target_callsite": {
                    "owner": old["composition_root"],
                    "constructor": "ProviderMemoryService.__init__",
                    "status": "planned",
                    "parameters": parameters,
                },
                "authority_bindings": [
                    {"parameter": parameter, "status": "planned", "proof_id": f"{requirement}-AUTH-{index + 1:02d}"}
                    for index, parameter in enumerate(parameters)
                ],
                "ordered_owner_chain": owner_chain,
                "call_edges": call_edges,
                "validation_boundary": {"path": validation_path, "symbol": validation_symbol, "status": "existing"},
                "durable_outcome": {"path": durable_path, "symbol": durable_symbol, "status": "existing", "mode": durable_mode},
                "fallback_branch": {"path": fallback_path, "token": fallback_token, "status": "existing"},
                "planned_proof_ids": [
                    f"{requirement}-ENABLED-EQUIVALENCE",
                    f"{requirement}-NEGATIVE-HANDOFF",
                    f"{requirement}-FALLBACK",
                ],
            }
        )
    output = {
        "schema": "memorii.production-entrypoint-bindings.v3",
        "candidate_manifest": "candidate-manifest-v3.json",
        "revision_scope": "validated-canonical-closure-design",
        "requirements": rows,
        "mutation_contract": [
            "wrong_authority_parameter",
            "disconnected_owner_edge",
            "wrong_row_caller_count",
            "missing_durable_writer",
            "missing_fallback_and_proof",
        ],
    }
    OUTPUT.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
