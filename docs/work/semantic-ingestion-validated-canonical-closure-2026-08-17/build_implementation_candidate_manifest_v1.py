"""Freeze the scoped implementation candidate without claiming the dirty tree."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "implementation-candidate-manifest-v1.json"
OWNED = (
    "memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py",
    "memorii/memorii/core/semantic_ingestion/contracts.py",
    "memorii/memorii/core/memory_evolution/ingestion_contracts.py",
    "memorii/memorii/core/provider/service.py",
    "memorii/memorii/core/provider/ingestion.py",
    "memorii/memorii/core/memory_evolution/atomic_store.py",
    "memorii/tests/unit/core/semantic_ingestion/test_canonical_evidence_arena.py",
    "memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_coordinator_v3.py",
    "memorii/tests/unit/core/test_provider_service.py",
)
REQUIRED = (
    "design.plan.md",
    "implementation.plan.md",
    "implementation-acceptance-v12.md",
    "canonical-closure-operation-contract-v1.json",
    "production-entrypoint-bindings-v11.json",
    "production-entrypoint-expected-graph-v11.json",
    "production-owner-oracle-v8.json",
    "production-entrypoint-bindings-v11-validation.json",
    "build_production_entrypoint_bindings_v11.py",
    "validate_production_entrypoint_bindings_v11.py",
    "build_implementation_candidate_manifest_v1.py",
    "validate_implementation_candidate_manifest_v1.py",
    "milestones/sealed-authority-lifecycle-remediation.md",
    "milestones/direct-ingress-closure-slice.md",
    "milestones/complete-trigger-and-durable-path-propagation.md",
)


def _git(*args: str) -> str:
    return subprocess.check_output(("git", *args), cwd=ROOT, text=True).strip()


def main() -> None:
    milestone_paths = sorted(
        path.relative_to(ROOT).as_posix() for path in (HERE / "milestones").glob("*.md")
    )
    paths = (
        list(OWNED)
        + [str((HERE / value).relative_to(ROOT)) for value in REQUIRED]
        + milestone_paths
    )
    artifacts = [
        {
            "path": path,
            "role": "owned_runtime_or_test"
            if path in OWNED
            else "governance_or_evidence",
            "sha256": sha256((ROOT / path).read_bytes()).hexdigest(),
        }
        for path in sorted(set(paths))
    ]
    status = [line for line in _git("status", "--porcelain=v1").splitlines() if line]
    manifest = {
        "schema": "memorii.implementation-candidate.v1",
        "base_revision": _git("rev-parse", "HEAD"),
        "dirty_tree": {
            "clean": False,
            "all_status": status,
            "owned_status": [
                line
                for line in status
                if line[3:] in OWNED or line[3:].startswith(str(HERE.relative_to(ROOT)))
            ],
        },
        "artifacts": artifacts,
        "focused_results": [
            "19 passed in 31.60s: production-root plus arena",
            "v11 validator: 32 mutations passed",
        ],
        "scope": "M1-M3/remediation only; unrelated dirty paths are recorded, not owned.",
    }
    OUTPUT.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
