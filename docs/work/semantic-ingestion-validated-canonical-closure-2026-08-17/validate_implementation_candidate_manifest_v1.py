"""Validate the scoped implementation candidate and deterministic mutations."""

from __future__ import annotations
import copy
from hashlib import sha256
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "implementation-candidate-manifest-v1.json"


def _head() -> str:
    return subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=ROOT, text=True
    ).strip()


def validate(value: dict) -> list[str]:
    failures = []
    paths = [item.get("path") for item in value.get("artifacts", [])]
    if len(paths) != len(set(paths)):
        failures.append("duplicate_path")
    if value.get("base_revision") != _head():
        failures.append("wrong_head")
    if value.get("dirty_tree", {}).get("clean") is not False:
        failures.append("false_clean_tree")
    required = {
        "implementation.plan.md",
        "production-entrypoint-bindings-v11-validation.json",
        "milestones/sealed-authority-lifecycle-remediation.md",
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
    if "production-entrypoint-bindings-v11-validation.json" not in "\n".join(paths):
        failures.append("stale_v11_identity")
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
        "false_clean_tree": lambda x: x["dirty_tree"].__setitem__("clean", True),
        "stale_v11_identity": lambda x: x["artifacts"].__setitem__(
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
