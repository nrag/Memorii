"""Validate the final-closure candidate and its deterministic mutations."""

from __future__ import annotations
import copy
from hashlib import sha256
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "implementation-candidate-manifest-v2.json"


def _head() -> str:
    return subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=ROOT, text=True
    ).strip()


def _status_is_clean() -> bool:
    here_relative = HERE.relative_to(ROOT).as_posix()
    status = subprocess.check_output(
        ("git", "status", "--porcelain=v1"), cwd=ROOT, text=True
    ).splitlines()
    return not [
        line
        for line in status
        if line and f"{here_relative}/" not in line
    ]


def validate(value: dict) -> list[str]:
    failures = []
    paths = [item.get("path") for item in value.get("artifacts", [])]
    if len(paths) != len(set(paths)):
        failures.append("duplicate_path")
    if value.get("base_revision") != _head():
        failures.append("wrong_head")
    if value.get("dirty_tree", {}).get("clean") is not True:
        failures.append("dirty_tree")
    if value.get("dirty_tree", {}).get("clean") is not _status_is_clean():
        failures.append("clean_tree_mismatch")
    required = {
        "implementation.plan.md",
        "production-entrypoint-bindings-v11-validation.json",
        "production-entrypoint-bindings-v14-validation.json",
        "implementation-acceptance-v12.md",
        "milestones/performance-rollout-gates-and-final-closure.md",
    }
    if not required.issubset(
        {
            Path(path).name
            if "/" not in path
            else path.removeprefix(str(HERE.relative_to(ROOT)) + "/")
            for path in paths
        }
    ):
        failures.append("missing_artifact")
    for item in value.get("artifacts", []):
        path = ROOT / item["path"]
        if not path.is_file() or sha256(path.read_bytes()).hexdigest() != item.get(
            "sha256"
        ):
            failures.append("hash_drift")
        if item.get("role") not in {"owned_runtime_or_test", "governance_or_evidence"}:
            failures.append("wrong_role")
    if not any(
        "production-entrypoint-bindings-v14-validation.json" in path for path in paths
    ):
        failures.append("stale_v14_identity")
    if "v2" not in str(value.get("schema", "")):
        failures.append("wrong_schema")
    return sorted(set(failures))


def main() -> None:
    value = json.loads(MANIFEST.read_text())
    failures = validate(value)
    mutations = {}
    for name, mutate in {
        "hash_drift": lambda x: x["artifacts"][0].__setitem__("sha256", "0" * 64),
        "missing_artifact": lambda x: x.__setitem__(
            "artifacts",
            [
                item
                for item in x["artifacts"]
                if not item["path"].endswith("implementation.plan.md")
            ],
        ),
        "extra_artifact": lambda x: x["artifacts"].append(
            {"path": "extra", "role": "governance_or_evidence", "sha256": "0"}
        ),
        "duplicate_path": lambda x: x["artifacts"].append(
            copy.deepcopy(x["artifacts"][0])
        ),
        "wrong_role": lambda x: x["artifacts"][0].__setitem__("role", "wrong"),
        "wrong_head": lambda x: x.__setitem__("base_revision", "0" * 40),
        "dirty_tree": lambda x: x["dirty_tree"].__setitem__("clean", False),
        "wrong_schema": lambda x: x.__setitem__("schema", "memorii.implementation-candidate.v1"),
        "stale_v14_identity": lambda x: x["artifacts"].__setitem__(
            -1, {"path": "stale", "role": "governance_or_evidence", "sha256": "0"}
        ),
    }.items():
        candidate = copy.deepcopy(value)
        mutate(candidate)
        mutations[name] = bool(validate(candidate))
    result = {
        "passed": not failures and all(mutations.values()),
        "failures": failures,
        "mutation_count": len(mutations),
        "mutation_results": mutations,
    }
    print(json.dumps(result, sort_keys=True))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
