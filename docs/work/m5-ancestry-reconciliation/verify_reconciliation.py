"""Verify that the M5 ancestry repair preserved the reviewed main tree."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[3]
RECORD_PATH = Path(__file__).with_name("reconciliation-record.json")
_COMMIT_LENGTH = 40
_TREE_LENGTH = 40


class VerificationError(ValueError):
    """The recorded ancestry or equivalence fact does not match Git."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repository), *arguments),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise VerificationError(
            f"git {' '.join(arguments)} failed: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def _commit(repository: Path, revision: str) -> str:
    _require(isinstance(revision, str) and len(revision) == _COMMIT_LENGTH, "invalid commit identity")
    _require(all(character in "0123456789abcdef" for character in revision), "commit identity is not lowercase hex")
    resolved = _git(repository, "rev-parse", f"{revision}^{{commit}}")
    _require(resolved == revision, "commit identity does not resolve exactly")
    return resolved


def _tree(repository: Path, revision: str) -> str:
    tree = _git(repository, "rev-parse", f"{revision}^{{tree}}")
    _require(len(tree) == _TREE_LENGTH and all(character in "0123456789abcdef" for character in tree), "invalid Git tree identity")
    return tree


def _load_record(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="ascii"))
    _require(isinstance(value, dict), "record must be an object")
    expected = {
        "schema_version",
        "kind",
        "reconciliation_merge_commit",
        "expected_ordered_parents",
        "expected_tree",
        "source_transplant_commit",
        "m5_head",
        "equivalence",
    }
    _require(set(value) == expected, "record has unknown or missing fields")
    _require(value["schema_version"] == 1, "unsupported record schema")
    _require(value["kind"] == "git_ancestry_reconciliation", "wrong record kind")
    return value


def _name_status(repository: Path, left: str, right: str) -> list[dict[str, str]]:
    output = _git(repository, "diff", "--no-ext-diff", "--no-renames", "--name-status", left, right)
    if not output:
        return []
    rows: list[dict[str, str]] = []
    for line in output.splitlines():
        status, separator, path = line.partition("\t")
        _require(separator == "\t" and status in {"A", "D", "M"} and path, "unexpected Git name-status row")
        rows.append({"status": status, "path": path})
    return rows


def verify_record(repository: Path, record: dict[str, object]) -> dict[str, object]:
    merge = _commit(repository, record["reconciliation_merge_commit"])
    parents = record["expected_ordered_parents"]
    _require(isinstance(parents, list) and len(parents) == 2, "record must name exactly two ordered parents")
    expected_parents = [_commit(repository, parent) for parent in parents]
    _require(expected_parents[1] == _commit(repository, record["m5_head"]), "M5 head must be second merge parent")
    actual_parents = _git(repository, "show", "-s", "--format=%P", merge).split()
    _require(actual_parents == expected_parents, "merge parents differ from recorded order")
    expected_tree = record["expected_tree"]
    _require(isinstance(expected_tree, str), "expected tree must be text")
    _require(_tree(repository, merge) == expected_tree, "merge tree differs from recorded tree")
    _require(_tree(repository, expected_parents[0]) == expected_tree, "merge tree differs from first-parent tree")

    equivalence = record["equivalence"]
    _require(isinstance(equivalence, dict) and set(equivalence) == {"left_commit", "right_commit", "expected_name_status"}, "invalid equivalence record")
    left = _commit(repository, equivalence["left_commit"])
    right = _commit(repository, equivalence["right_commit"])
    _require(left == _commit(repository, record["source_transplant_commit"]), "equivalence left side differs from transplant")
    _require(right == _commit(repository, record["m5_head"]), "equivalence right side differs from M5 head")
    expected_rows = equivalence["expected_name_status"]
    _require(isinstance(expected_rows, list) and expected_rows, "equivalence rows must be nonempty")
    _require(all(isinstance(row, dict) and set(row) == {"status", "path"} for row in expected_rows), "invalid equivalence row")
    _require(_name_status(repository, left, right) == expected_rows, "transplant and M5 head differ outside recorded evidence files")
    return {"merge": merge, "parents": actual_parents, "tree": expected_tree, "equivalence_rows": len(expected_rows)}


def _expect_rejection(repository: Path, record: dict[str, object], label: str) -> None:
    try:
        verify_record(repository, record)
    except VerificationError:
        return
    raise VerificationError(f"self-test accepted {label} substitution")


def self_test(repository: Path, record: dict[str, object]) -> None:
    mutated_parent = copy.deepcopy(record)
    mutated_parent["expected_ordered_parents"][1] = mutated_parent["expected_ordered_parents"][0]
    _expect_rejection(repository, mutated_parent, "parent")

    mutated_tree = copy.deepcopy(record)
    mutated_tree["expected_tree"] = "0" * _TREE_LENGTH
    _expect_rejection(repository, mutated_tree, "tree")

    mutated_equivalence = copy.deepcopy(record)
    mutated_equivalence["equivalence"]["expected_name_status"] = []
    _expect_rejection(repository, mutated_equivalence, "equivalence")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--record", type=Path, default=RECORD_PATH)
    parser.add_argument("--self-test", action="store_true")
    arguments = parser.parse_args()
    try:
        record = _load_record(arguments.record)
        result = verify_record(arguments.repo.resolve(), record)
        if arguments.self_test:
            self_test(arguments.repo.resolve(), record)
            result["self_test"] = "passed"
    except (OSError, TypeError, json.JSONDecodeError, VerificationError) as error:
        parser.exit(1, f"ancestry reconciliation verification failed: {error}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
