from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml
from memorii.tools.bootstrap_graph_transaction_selector import (
    BACKENDS,
    RECEIPT_DOMAIN,
    ROOTS,
    RUNTIME_BUDGET_SECONDS,
    build_manifest,
    contract_digest,
    shard_selectors,
    validate_manifest,
    validate_receipts,
)

MANIFEST_PATH = (
    Path(__file__).parents[3]
    / "tests"
    / "ci"
    / "bootstrap-graph-transaction-boundary.json"
)
WORKFLOW_PATH = Path(__file__).parents[4] / ".github" / "workflows" / "pr-gates.yml"
UNIT_SHARDS_PATH = Path(__file__).parents[3] / "tests" / "ci" / "unit-shards.json"
OWNERS_PATH = Path(__file__).parents[3] / "tests" / "ci" / "deterministic-job-owners.json"


def _committed_manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_committed_manifest_is_exact_generated_352_tuple_inventory() -> None:
    manifest = _committed_manifest()

    validate_manifest(manifest)

    assert manifest == build_manifest()
    assert manifest["inventory_count"] == 200


@pytest.mark.parametrize(
    "mutation",
    [
        lambda manifest: manifest["rows"].pop(),
        lambda manifest: manifest["rows"].append(copy.deepcopy(manifest["rows"][0])),
        lambda manifest: manifest["rows"][0]["requirement_ids"].clear(),
        lambda manifest: manifest["rows"][0].update(row_digest="0" * 64),
    ],
    ids=("missing-row", "duplicate-selector", "missing-requirement", "stale-digest"),
)
def test_manifest_mutations_fail_closed(mutation: object) -> None:
    manifest = _committed_manifest()
    mutation(manifest)  # type: ignore[operator]

    with pytest.raises(ValueError, match="stale or invalid"):
        validate_manifest(manifest)


def test_workflow_has_exact_dedicated_shards_and_aggregate_dependency() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    boundary = jobs["bootstrap-graph-transaction-boundary"]

    assert boundary["strategy"]["matrix"] == {
        "root": ["direct", "factory", "filesystem", "hermes"],
        "backend": ["memory", "jsonl_independent_process"],
    }
    assert boundary["timeout-minutes"] == 90
    run_commands = "\n".join(
        str(step.get("run", "")) for step in boundary["steps"]
    )
    assert "bootstrap-graph-transaction-boundary.json" in run_commands
    assert "--run-shard" in run_commands
    assert "--receipt" in run_commands

    aggregate_job = jobs["bootstrap-graph-transaction-boundary-aggregate"]
    assert aggregate_job["needs"] == ["bootstrap-graph-transaction-boundary"]
    aggregate_commands = "\n".join(
        str(step.get("run", "")) for step in aggregate_job["steps"]
    )
    assert "--validate-receipts" in aggregate_commands

    aggregate = jobs["semantic-ingestion"]
    assert "bootstrap-graph-transaction-boundary-aggregate" in aggregate["needs"]
    aggregate_step = aggregate["steps"][0]
    assert aggregate_step["env"]["BOOTSTRAP_GRAPH_RESULT"] == (
        "${{ needs.bootstrap-graph-transaction-boundary-aggregate.result }}"
    )
    assert 'test "$BOOTSTRAP_GRAPH_RESULT" = success' in aggregate_step["run"]


def _write_receipts(path: Path, *, elapsed: float = 1.0) -> None:
    manifest = _committed_manifest()
    for root in ROOTS:
        for backend in BACKENDS:
            body = {
                "schema_version": 1,
                "owner": "bootstrap-graph-transaction-boundary",
                "manifest_digest": manifest["manifest_digest"],
                "root": root,
                "backend": backend,
                "selectors": shard_selectors(manifest, root=root, backend=backend),
                "selector_count": 25,
                "elapsed_milliseconds": round(elapsed * 1000),
                "runtime_budget_seconds": RUNTIME_BUDGET_SECONDS,
            }
            (path / f"{root}-{backend}.json").write_text(
                json.dumps({**body, "receipt_digest": contract_digest(RECEIPT_DOMAIN, body)}),
                encoding="utf-8",
            )


def test_receipts_are_exact_exclusive_manifest_union(tmp_path: Path) -> None:
    _write_receipts(tmp_path)
    validate_receipts(_committed_manifest(), tmp_path)


@pytest.mark.parametrize("mutation", ["missing", "stale", "over_budget"])
def test_receipt_mutations_fail_closed(tmp_path: Path, mutation: str) -> None:
    _write_receipts(tmp_path)
    target = tmp_path / "direct-memory.json"
    if mutation == "missing":
        target.unlink()
    else:
        value = json.loads(target.read_text(encoding="utf-8"))
        if mutation == "stale":
            value["manifest_digest"] = "0" * 64
        else:
            value["elapsed_milliseconds"] = (RUNTIME_BUDGET_SECONDS + 1) * 1000
        target.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError):
        validate_receipts(_committed_manifest(), tmp_path)


def test_dedicated_owner_is_excluded_from_generic_unit_shards() -> None:
    shards = json.loads(UNIT_SHARDS_PATH.read_text(encoding="utf-8"))
    assert all(
        ignore in shards["pytest_args"]
        for ignore in (
            "--ignore=tests/unit/core/semantic_ingestion/test_bootstrap_graph_jsonl_race_reopen.py",
            "--ignore=tests/unit/core/semantic_ingestion/test_bootstrap_graph_scenario_replay.py",
            "--ignore=tests/unit/core/semantic_ingestion/test_bootstrap_graph_root_composition.py",
        )
    )
    owners = json.loads(OWNERS_PATH.read_text(encoding="utf-8"))["dedicated_pytest_jobs"]
    assert owners["bootstrap-graph-transaction-boundary"] == {
        "runtime_budget_seconds": 4200,
        "timeout_headroom_seconds": 1200,
        "timeout_minutes": 90,
        "timing_exemption_reason": "Exact public-root and independent-process JSONL graph transaction shards own 25 manifest selectors each.",
    }
