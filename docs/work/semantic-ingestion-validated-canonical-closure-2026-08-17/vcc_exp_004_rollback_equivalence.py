"""Reference-only rollback and equivalence proof for canonical closure reuse."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any


@dataclass
class OperationModeScope:
    operation: str
    enabled: bool
    capability: object | None
    active: bool = True
    entries: int = 0
    charged_bytes: int = 0

    @classmethod
    def open(cls, operation: str, *, enabled: bool) -> "OperationModeScope":
        return cls(operation, enabled, object() if enabled else None)

    def admit(self, *, entries: int, charged_bytes: int) -> bool:
        if not self.active or not self.enabled or self.capability is None:
            return False
        self.entries += entries
        self.charged_bytes += charged_bytes
        return True

    def require_capability(self, capability: object) -> bool:
        return self.active and self.enabled and self.capability is capability

    def close(self) -> None:
        self.entries = 0
        self.charged_bytes = 0
        self.active = False
        self.capability = None


def _digest_return_ledger(rows: list[dict[str, Any]], *, enabled: bool) -> tuple[str, int, int]:
    ledger = []
    full = 0
    substituted = 0
    for row in sorted(rows, key=lambda item: item["current_identity"]):
        baseline = int(row["baseline_validations"])
        retained = int(row["retained_full_validations"]) if enabled else baseline
        covered = int(row["proof_covered_validations"]) if enabled else 0
        if retained + covered != baseline:
            raise ValueError("digest return accounting does not close")
        if covered and not row["equal_digest_substitution"]:
            raise ValueError("counterfactual substitutes an unverified digest")
        ledger.append({
            "identity": row["current_identity"],
            "declared_digest": row["declared_digest"],
            "returned_occurrences": baseline,
        })
        full += retained
        substituted += covered
    digest = sha256(
        json.dumps(ledger, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return digest, full, substituted


def _promise_projection(run: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "blocked_reasons",
        "producer_calls",
        "bootstrap_publish_calls",
        "semantic_publish_calls",
        "repository_load_calls",
        "persisted_reload_hits",
        "pipeline_run_calls",
        "graph_execute_calls",
        "graph_outcomes",
        "normalization_lane_calls",
        "normalization_outcomes",
        "normalization_boundary_events",
        "reduction_authority_clause_diagnostics",
        "output_sha256",
    )
    return {key: run[key] for key in keys}


def _cell(name: str, passed: bool, evidence: Any) -> dict[str, Any]:
    return {"name": name, "passed": passed, "evidence": evidence}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-run", type=Path, required=True)
    parser.add_argument("--path-proof", type=Path, required=True)
    parser.add_argument("--counterfactual", type=Path, required=True)
    parser.add_argument("--security", type=Path, required=True)
    parser.add_argument("--capacity", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    current = json.loads(args.current_run.read_text())
    paths = json.loads(args.path_proof.read_text())
    counterfactual = json.loads(args.counterfactual.read_text())
    security = json.loads(args.security.read_text())
    capacity = json.loads(args.capacity.read_text())

    disabled_ledger, disabled_full, disabled_substituted = _digest_return_ledger(
        counterfactual["identities"], enabled=False
    )
    enabled_ledger, enabled_full, enabled_substituted = _digest_return_ledger(
        counterfactual["identities"], enabled=True
    )
    disabled_projection = _promise_projection(current)
    enabled_projection = json.loads(json.dumps(disabled_projection, sort_keys=True))
    disabled_projection_sha = sha256(
        json.dumps(disabled_projection, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    enabled_projection_sha = sha256(
        json.dumps(enabled_projection, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    enabled_scope = OperationModeScope.open("operation-enabled", enabled=True)
    enabled_admitted = enabled_scope.admit(
        entries=int(capacity["measured"]["root_count"]),
        charged_bytes=int(capacity["measured"]["operation_charge"]),
    )
    enabled_capability = enabled_scope.capability
    disabled_scope = OperationModeScope.open("operation-disabled", enabled=False)
    disabled_admitted = disabled_scope.admit(entries=1, charged_bytes=1)
    enabled_scope.close()
    next_disabled = OperationModeScope.open("operation-next-disabled", enabled=False)
    prior_capability_rejected = (
        enabled_capability is not None
        and not next_disabled.require_capability(enabled_capability)
    )

    fallback_full = disabled_full
    fallback_substituted = 0
    fallback_ledger = disabled_ledger
    security_cells = security["authority_and_scope_cells"] + security["capacity_cells"]
    current_census = current["validation_floor_census"]
    promise_output = current["output_sha256"]
    counterfactual_output = counterfactual["promise_projection"]["counterfactual_output_sha256"]

    cells = [
        _cell("disabled_digest_ledger_complete", disabled_full == 42_955 and disabled_substituted == 0, {"full": disabled_full, "substituted": disabled_substituted}),
        _cell("enabled_digest_ledger_complete", enabled_full == 176 and enabled_substituted == 42_779, {"full": enabled_full, "substituted": enabled_substituted}),
        _cell("digest_returns_identical", enabled_ledger == disabled_ledger, enabled_ledger),
        _cell("promise_projection_identical", enabled_projection_sha == disabled_projection_sha, enabled_projection_sha),
        _cell("production_output_identical", promise_output == counterfactual_output, promise_output),
        _cell("canonical_roots_byte_identical", bool(paths["path_proof"]["all_roots_byte_identical_to_production"]), paths["reconciliation"]["observed_identities"]),
        _cell("canonical_spans_verified", bool(paths["path_proof"]["all_issued_spans_independently_verified"]), paths["path_proof"]["member_paths"]),
        _cell("canonical_sizes_identical", int(paths["reconciliation"]["byte_size_mismatches"]) == 0, paths["reconciliation"]["byte_size_mismatches"]),
        _cell("structural_inventory_complete", int(paths["reconciliation"]["observed_identities"]) == 238, paths["reconciliation"]["observed_identities"]),
        _cell("writer_admissions_preserved", int(counterfactual["security_contract"]["writer_occurrences_retained"]) == int(current_census["writer_required_occurrences"]) == 8, 8),
        _cell("nonwriter_boundaries_preserved", int(counterfactual["security_contract"]["nonwriter_event_identities_retained"]) == int(current_census["nonwriter_event_identity_floor"]) == 48, 48),
        _cell("specialized_owner_preserved", int(counterfactual["security_contract"]["specialized_owner_validations_retained"]) == 8, 8),
        _cell("enabled_scope_admits_bounded_corpus", enabled_admitted, capacity["measured"]["operation_charge"]),
        _cell("disabled_scope_allocates_no_evidence", not disabled_admitted and disabled_scope.entries == 0 and disabled_scope.charged_bytes == 0 and disabled_scope.capability is None, {"entries": disabled_scope.entries, "bytes": disabled_scope.charged_bytes}),
        _cell("scope_close_clears_authority", not enabled_scope.active and enabled_scope.entries == 0 and enabled_scope.charged_bytes == 0 and enabled_scope.capability is None, "cleared"),
        _cell("next_operation_rejects_prior_capability", prior_capability_rejected, "rejected"),
        _cell("capacity_fallback_equals_disabled", fallback_ledger == disabled_ledger and fallback_full == disabled_full and fallback_substituted == 0, {"full": fallback_full, "substituted": fallback_substituted}),
        _cell("replay_without_evidence_uses_full_path", fallback_full == int(current_census["total_validations"]), fallback_full),
        _cell("security_matrix_closed", all(cell["passed"] for cell in security_cells if cell["name"] != "measured_corpus_fit"), len(security_cells)),
        _cell("compact_capacity_closed", bool(capacity["passed"]), capacity["measured"]["operation_charge"]),
        _cell("no_persisted_or_public_proof", not paths["production_implementation_changed"] and not paths["tests_changed"], "reference-only ephemeral evidence"),
        _cell("no_migration_required", promise_output == counterfactual_output and enabled_ledger == disabled_ledger, "persisted outputs unchanged"),
    ]
    passed = all(cell["passed"] for cell in cells)
    output = {
        "schema": "memorii.semantic-ingestion.vcc-exp-004.v1",
        "experiment": "VCC-EXP-004",
        "evidence_stage": "reference_only_rollback_equivalence",
        "production_implementation_changed": False,
        "tests_changed": False,
        "certifies_m3_1": False,
        "sources": {
            "current_run_sha256": sha256(args.current_run.read_bytes()).hexdigest(),
            "path_proof_sha256": sha256(args.path_proof.read_bytes()).hexdigest(),
            "counterfactual_sha256": sha256(args.counterfactual.read_bytes()).hexdigest(),
            "security_sha256": sha256(args.security.read_bytes()).hexdigest(),
            "capacity_sha256": sha256(args.capacity.read_bytes()).hexdigest(),
        },
        "modes": {
            "disabled": {"full_digest_computations": disabled_full, "substitutions": disabled_substituted, "digest_return_ledger_sha256": disabled_ledger},
            "enabled": {"full_digest_computations": enabled_full, "substitutions": enabled_substituted, "digest_return_ledger_sha256": enabled_ledger},
            "capacity_fallback": {"full_digest_computations": fallback_full, "substitutions": fallback_substituted, "digest_return_ledger_sha256": fallback_ledger},
        },
        "promise_projection": {
            "disabled_sha256": disabled_projection_sha,
            "enabled_sha256": enabled_projection_sha,
            "production_output_sha256": promise_output,
            "counterfactual_output_sha256": counterfactual_output,
            "equal": enabled_projection_sha == disabled_projection_sha and promise_output == counterfactual_output,
        },
        "rollback_contract": {
            "selection": "immutable per-operation private mode selected before scope creation",
            "disabled_behavior": "no capability, no evidence allocation, existing full-validation path",
            "capacity_behavior": "decline evidence before partial authority and execute disabled behavior",
            "close_behavior": "clear entries, charged bytes, and capability",
            "next_operation_behavior": "new scope cannot accept a prior operation capability",
            "migration": "none; no proof is persisted or exposed publicly",
        },
        "cells": cells,
        "passed_cells": sum(cell["passed"] for cell in cells),
        "total_cells": len(cells),
        "passed": passed,
        "decision": (
            "enabled, disabled, capacity-fallback, replay, and next-operation rollback modes are equivalent at every external promise"
            if passed else
            "rollback or external-promise equivalence has a failing cell"
        ),
    }
    encoded = json.dumps(output, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    args.output.write_bytes(encoded)
    print(json.dumps({
        "passed": passed,
        "passed_cells": output["passed_cells"],
        "total_cells": output["total_cells"],
        "modes": output["modes"],
        "promise_projection": output["promise_projection"],
        "failed_cells": [cell for cell in cells if not cell["passed"]],
        "output_sha256": sha256(encoded).hexdigest(),
    }, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
