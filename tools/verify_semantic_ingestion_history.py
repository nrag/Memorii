"""Verify that incorporated semantic-ingestion history preserved the main tree."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parent.parent
RECORD_PATH = Path(__file__).with_name("semantic_ingestion_history_reconciliation.json")
_COMMIT_LENGTH = 40
_TREE_LENGTH = 40
_PERMITTED_EQUIVALENCE_ROWS = [
    {
        "status": "M",
        "path": "docs/work/hermes-conversation-memory-trial/candidate-manifest.json",
    },
    {
        "status": "M",
        "path": "docs/work/hermes-conversation-memory-trial/implementation.plan.md",
    },
    {
        "status": "M",
        "path": "docs/work/hermes-conversation-memory-trial/milestones/startup-admission.plan.md",
    },
]


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


def _revision(repository: Path, revision: str) -> str:
    _require(isinstance(revision, str) and revision, "target revision must be text")
    return _git(repository, "rev-parse", f"{revision}^{{commit}}")


def _tree(repository: Path, revision: str) -> str:
    tree = _git(repository, "rev-parse", f"{revision}^{{tree}}")
    _require(len(tree) == _TREE_LENGTH and all(character in "0123456789abcdef" for character in tree), "invalid Git tree identity")
    return tree


def _is_ancestor(repository: Path, ancestor: str, descendant: str) -> bool:
    completed = subprocess.run(
        ("git", "-C", str(repository), "merge-base", "--is-ancestor", ancestor, descendant),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode not in {0, 1}:
        raise VerificationError(
            "git merge-base --is-ancestor failed: " + completed.stderr.strip()
        )
    return completed.returncode == 0


def _load_record(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="ascii"))
    _require(isinstance(value, dict), "record must be an object")
    expected = {
        "schema_version",
        "kind",
        "reconciliation_merge_commit",
        "expected_ordered_parents",
        "expected_tree",
        "review_anchor_commit",
        "source_transplant_commit",
        "incorporated_history_head",
        "equivalence",
    }
    _require(set(value) == expected, "record has unknown or missing fields")
    _require(value["schema_version"] == 2, "unsupported record schema")
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


def verify_record(
    repository: Path, record: dict[str, object], target_revision: str = "HEAD"
) -> dict[str, object]:
    merge = _commit(repository, record["reconciliation_merge_commit"])
    parents = record["expected_ordered_parents"]
    _require(isinstance(parents, list) and len(parents) == 2, "record must name exactly two ordered parents")
    expected_parents = [_commit(repository, parent) for parent in parents]
    history_head = _commit(repository, record["incorporated_history_head"])
    _require(expected_parents[1] == history_head, "incorporated history must be second merge parent")
    actual_parents = _git(repository, "show", "-s", "--format=%P", merge).split()
    _require(actual_parents == expected_parents, "merge parents differ from recorded order")
    expected_tree = record["expected_tree"]
    _require(isinstance(expected_tree, str), "expected tree must be text")
    _require(_tree(repository, merge) == expected_tree, "merge tree differs from recorded tree")
    _require(_tree(repository, expected_parents[0]) == expected_tree, "merge tree differs from first-parent tree")

    source_transplant = _commit(repository, record["source_transplant_commit"])
    _require(
        _is_ancestor(repository, source_transplant, expected_parents[0]),
        "source transplant is not ancestor of first merge parent",
    )
    target = _revision(repository, target_revision)
    _require(
        _is_ancestor(repository, merge, target),
        "reconciliation merge is not ancestor of review target",
    )
    _require(
        all(_is_ancestor(repository, parent, target) for parent in expected_parents),
        "merge parent is not ancestor of review target",
    )
    review_anchor = _commit(repository, record["review_anchor_commit"])
    _require(
        _is_ancestor(repository, review_anchor, target),
        "review anchor is not ancestor of review target",
    )

    equivalence = record["equivalence"]
    _require(isinstance(equivalence, dict) and set(equivalence) == {"left_commit", "right_commit", "expected_name_status"}, "invalid equivalence record")
    left = _commit(repository, equivalence["left_commit"])
    right = _commit(repository, equivalence["right_commit"])
    _require(left == source_transplant, "equivalence left side differs from transplant")
    _require(right == history_head, "equivalence right side differs from incorporated history")
    expected_rows = equivalence["expected_name_status"]
    _require(isinstance(expected_rows, list) and expected_rows, "equivalence rows must be nonempty")
    _require(all(isinstance(row, dict) and set(row) == {"status", "path"} for row in expected_rows), "invalid equivalence row")
    _require(expected_rows == _PERMITTED_EQUIVALENCE_ROWS, "equivalence rows differ from permitted evidence paths")
    _require(_name_status(repository, left, right) == _PERMITTED_EQUIVALENCE_ROWS, "transplant and incorporated history differ outside recorded evidence files")
    return {
        "merge": merge,
        "parents": actual_parents,
        "review_target": target,
        "tree": expected_tree,
        "equivalence_rows": len(expected_rows),
    }


def _expect_rejection(
    repository: Path,
    record: dict[str, object],
    label: str,
    expected_message: str,
    target_revision: str = "HEAD",
) -> None:
    try:
        verify_record(repository, record, target_revision)
    except VerificationError as error:
        _require(expected_message in str(error), f"self-test rejected {label} at wrong boundary: {error}")
        return
    raise VerificationError(f"self-test accepted {label} substitution")


def self_test(repository: Path, record: dict[str, object]) -> None:
    mutated_parent = copy.deepcopy(record)
    mutated_parent["reconciliation_merge_commit"] = record["review_anchor_commit"]
    _expect_rejection(repository, mutated_parent, "parent", "merge parents differ from recorded order")

    mutated_tree = copy.deepcopy(record)
    mutated_tree["expected_tree"] = _tree(repository, record["incorporated_history_head"])
    _expect_rejection(repository, mutated_tree, "tree", "merge tree differs from recorded tree")

    mutated_equivalence = copy.deepcopy(record)
    mutated_equivalence["equivalence"]["expected_name_status"] = [
        {"status": "M", "path": "docs/work/hermes-conversation-memory-trial/unrecorded.json"}
    ]
    _expect_rejection(
        repository,
        mutated_equivalence,
        "equivalence",
        "equivalence rows differ from permitted evidence paths",
    )

    mutated_transplant = copy.deepcopy(record)
    mutated_transplant["source_transplant_commit"] = record["incorporated_history_head"]
    _expect_rejection(
        repository,
        mutated_transplant,
        "source transplant ancestry",
        "source transplant is not ancestor of first merge parent",
    )

    _expect_rejection(
        repository,
        copy.deepcopy(record),
        "review target reachability",
        "reconciliation merge is not ancestor of review target",
        record["expected_ordered_parents"][0],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--record", type=Path, default=RECORD_PATH)
    parser.add_argument("--target", default="HEAD")
    parser.add_argument("--self-test", action="store_true")
    arguments = parser.parse_args()
    try:
        record = _load_record(arguments.record)
        result = verify_record(arguments.repo.resolve(), record, arguments.target)
        if arguments.self_test:
            self_test(arguments.repo.resolve(), record)
            result["self_test"] = "passed"
    except (OSError, TypeError, json.JSONDecodeError, VerificationError) as error:
        parser.exit(1, f"semantic-ingestion history verification failed: {error}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
