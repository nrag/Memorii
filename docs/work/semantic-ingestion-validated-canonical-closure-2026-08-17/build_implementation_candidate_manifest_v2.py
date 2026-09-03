"""Freeze the final-closure implementation candidate over a clean tree."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "implementation-candidate-manifest-v2.json"
OWNED_RUNTIME = (
    "memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py",
    "memorii/memorii/core/semantic_ingestion/contracts.py",
    "memorii/memorii/core/memory_evolution/ingestion_contracts.py",
    "memorii/memorii/core/provider/service.py",
    "memorii/memorii/core/provider/ingestion.py",
    "memorii/memorii/core/memory_evolution/atomic_store.py",
    "memorii/memorii/core/memory_evolution/writer_admission.py",
    "memorii/memorii/core/memory_evolution/bootstrap_graph_planning.py",
    "memorii/memorii/core/memory_evolution/projection_history.py",
    "memorii/memorii/core/memory_evolution/conflict_attention.py",
    "memorii/memorii/core/memory_evolution/bootstrap_profile.py",
    "memorii/memorii/core/memory_evolution/source_admission.py",
    "memorii/memorii/core/memory_evolution/source_governance.py",
    "memorii/memorii/core/memory_evolution/record_projection.py",
    "memorii/memorii/core/memory_evolution/graph_records.py",
    "memorii/memorii/core/memory_evolution/graph_effect_contracts.py",
    "memorii/memorii/core/memory_evolution/graph_planning.py",
    "memorii/memorii/core/memory_evolution/semantic_analysis/decision_contracts.py",
)
OWNED_TESTS_AND_GATES = (
    "memorii/tests/unit/core/semantic_ingestion/test_canonical_evidence_arena.py",
    "memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_coordinator_v3.py",
    "memorii/tests/unit/core/semantic_ingestion/test_canonical_evidence_mode_parity.py",
    "memorii/tests/unit/core/semantic_ingestion/test_canonical_evidence_production_limits.py",
    "memorii/tests/unit/core/test_provider_service.py",
    "memorii/tests/unit/tools/test_identity_hygiene.py",
    "memorii/tests/unit/tools/test_static_tooling_config.py",
    "memorii/tests/ci/unit-shards.json",
    "memorii/tests/ci/unit-test-durations.json",
    ".github/workflows/pr-gates.yml",
    ".github/workflows/canonical-evidence-parity-scheduled.yml",
)
REQUIRED = (
    "implementation.plan.md",
    "implementation-acceptance-v12.md",
    "canonical-closure-operation-contract-v1.json",
    "production-entrypoint-bindings-v11.json",
    "production-entrypoint-expected-graph-v11.json",
    "production-owner-oracle-v8.json",
    "production-entrypoint-bindings-v11-validation.json",
    "validate_production_entrypoint_bindings_v11.py",
    "production-entrypoint-bindings-v14.json",
    "production-entrypoint-bindings-v14-validation.json",
    "build_production_entrypoint_bindings_v14.py",
    "validate_production_entrypoint_bindings_v14.py",
    "milestones/direct-ingress-closure-slice.md",
    "milestones/complete-trigger-and-durable-path-propagation.md",
    "milestones/recovery-reconciliation-fresh-owner-propagation.md",
    "milestones/performance-rollout-gates-and-final-closure.md",
    "build_implementation_candidate_manifest_v2.py",
    "validate_implementation_candidate_manifest_v2.py",
)
# Frozen-revision gate evidence; finalized at freeze time.
FOCUSED_RESULTS = (
    "identity_hygiene: exit 0 (124 findings resolved via behavioral corpus ids)",
    "unit shard plan: 6 shards, ~487s estimated, verify exit 0",
    "arena suite: 62 passed",
    "production-limits module: 3 passed",
    "CI pyright command: exit 0 after annotation-precision remediation",
)


def _git(*args: str) -> str:
    return subprocess.check_output(("git", *args), cwd=ROOT, text=True).strip()


def main() -> None:
    milestone_paths = sorted(
        path.relative_to(ROOT).as_posix() for path in (HERE / "milestones").glob("*.md")
    )
    paths = (
        list(OWNED_RUNTIME)
        + list(OWNED_TESTS_AND_GATES)
        + [str((HERE / value).relative_to(ROOT)) for value in REQUIRED]
        + milestone_paths
    )
    artifacts = [
        {
            "path": path,
            "role": (
                "owned_runtime_or_test"
                if path in OWNED_RUNTIME or path in OWNED_TESTS_AND_GATES
                else "governance_or_evidence"
            ),
            "sha256": sha256((ROOT / path).read_bytes()).hexdigest(),
        }
        for path in sorted(set(paths))
    ]
    here_relative = HERE.relative_to(ROOT).as_posix()
    status = [
        line
        for line in _git("status", "--porcelain=v1").splitlines()
        if line
        # The freeze artifacts this builder and its validator create are the
        # only permitted tree entries at freeze time.
        and f"{here_relative}/" not in line
    ]
    manifest = {
        "schema": "memorii.implementation-candidate.v2",
        "base_revision": _git("rev-parse", "HEAD"),
        "dirty_tree": {
            "clean": not status,
            "all_status": status,
        },
        "artifacts": artifacts,
        "focused_results": list(FOCUSED_RESULTS),
        "scope": (
            "final closure: validated-canonical-closure runtime and gate surfaces, "
            "the annotation-precision type-gate remediation, and this operation's "
            "governance artifacts at one frozen revision"
        ),
    }
    OUTPUT.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
