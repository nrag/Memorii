"""Generate and validate the closed bootstrap graph transaction selector."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from memorii.core.semantic_ingestion.contracts import contract_digest

ROOTS = ("direct", "factory", "filesystem", "hermes")
BACKENDS = ("memory", "jsonl_independent_process")
REQUIRED_COVERAGE = {
    "GTC-R09": ("unrelated_conflict",),
    "GTC-R14": ("initial_attempt", "mixed_version", "reopen", "source_progress_initial"),
    "GTC-R15": ("epoch_zero", "lease_renewed", "lease_reclaimed", "writer_changed", "writer_unavailable", "pre_cas_scope_revoked", "source_progress_reclaimed_lease"),
    "GTC-R16": ("initial_attempt", "successor_attempt", "reused_committed", "reused_final", "reused_unfinished", "replacement", "related_conflict", "source_progress_related_conflict"),
    "GTC-R17": ("successor_attempt", "reused_committed", "reused_final", "reused_unfinished", "replacement", "partial_commit"),
    "GTC-R18": ("durable_retry", "partial_commit", "lost_ack", "reopen", "related_conflict", "source_progress_lost_ack"),
    "GTC-R19": ("success_finalization", "finalized_failure", "terminal_locator", "lost_ack", "reopen"),
    "GTC-R20": ("coordinator_removed", "authority_omitted", "writer_changed", "writer_unavailable", "mixed_version", "rollback"),
    "GTC-R21": ("pre_cas_scope_revoked", "initial_attempt", "successor_attempt", "lost_ack", "reopen"),
}

ROW_DOMAIN = b"memorii.semantic-ingestion.bootstrap-graph-transaction-selector-row.v1"
MANIFEST_DOMAIN = b"memorii.semantic-ingestion.bootstrap-graph-transaction-selector-manifest.v1"
TUPLE_DOMAIN = b"memorii.semantic-ingestion.bootstrap-graph-transaction-required-tuples.v1"
NON_DISCLOSURE_DOMAIN = b"memorii.semantic-ingestion.bootstrap-graph-transaction-non-disclosure.v1"
RECEIPT_DOMAIN = b"memorii.semantic-ingestion.bootstrap-graph-transaction-receipt.v1"
RUNTIME_BUDGET_SECONDS = 4200


def _requirements_by_scenario() -> dict[str, tuple[str, ...]]:
    values: dict[str, list[str]] = {}
    for requirement, scenarios in REQUIRED_COVERAGE.items():
        for scenario in scenarios:
            values.setdefault(scenario, []).append(requirement)
    return {scenario: tuple(sorted(requirements)) for scenario, requirements in values.items()}


def build_manifest() -> dict[str, object]:
    requirements = _requirements_by_scenario()
    rows: list[dict[str, object]] = []
    for scenario in sorted(requirements):
        for root in ROOTS:
            for backend in BACKENDS:
                test_name = (
                    "test_graph_scenario_replays_without_effects_in_memory"
                    if backend == "memory"
                    else "test_graph_race_reopens_in_an_independent_jsonl_process"
                )
                test_module = (
                    "test_bootstrap_graph_scenario_replay.py"
                    if backend == "memory"
                    else "test_bootstrap_graph_jsonl_race_reopen.py"
                )
                selector_id = f"{scenario}-{root}"
                selector = (
                    "tests/unit/core/semantic_ingestion/"
                    f"{test_module}::{test_name}[{selector_id}]"
                )
                body = {
                    "requirement_ids": list(requirements[scenario]),
                    "node_id": f"bootstrap-graph-{scenario}-{root}-{backend}",
                    "pytest_selector": selector,
                    "root": root,
                    "backend": backend,
                    "public_trigger": "ProviderMemoryService.sync_event",
                    "scenario": scenario,
                    "injected_boundary": f"bootstrap_graph_v3:{scenario}",
                    "non_disclosure_oracle_digest": contract_digest(
                        NON_DISCLOSURE_DOMAIN,
                        {"scenario": scenario, "forbidden": [
                            "tenant", "principal", "scope", "graph_key",
                            "record_existence", "backend_detail",
                        ]},
                    ),
                }
                rows.append({**body, "row_digest": contract_digest(ROW_DOMAIN, body)})
    rows.sort(key=lambda row: (
        row["scenario"], row["root"], row["backend"],
        row["injected_boundary"], row["node_id"],
    ))
    tuples = sorted(
        (requirement, scenario, root, backend)
        for requirement, scenarios in REQUIRED_COVERAGE.items()
        for scenario in scenarios for root in ROOTS for backend in BACKENDS
    )
    body = {
        "schema_version": 1,
        "owner": "bootstrap-graph-transaction-boundary",
        "rows": rows,
        "exclusions": [],
        "required_tuple_digest": contract_digest(TUPLE_DOMAIN, tuples),
        "inventory_count": len(rows),
        "exclusion_count": 0,
        "collection_digest": contract_digest(
            b"memorii.semantic-ingestion.bootstrap-graph-transaction-collection.v1",
            tuple(row["pytest_selector"] for row in rows),
        ),
    }
    return {**body, "manifest_digest": contract_digest(MANIFEST_DOMAIN, body)}


def validate_manifest(manifest: dict[str, object]) -> None:
    expected = build_manifest()
    if manifest != expected:
        raise ValueError("bootstrap graph transaction selector is stale or invalid")
    rows = manifest["rows"]
    if not isinstance(rows, list):
        raise ValueError("bootstrap graph selector rows are not a list")
    selectors = [row["pytest_selector"] for row in rows]
    keys = [(row["scenario"], row["root"], row["backend"]) for row in rows]
    if len(rows) != 232 or len(set(selectors)) != 232 or len(set(keys)) != 232:
        raise ValueError("bootstrap graph selector row collection is incomplete or duplicated")
    projected = {
        (requirement, row["scenario"], row["root"], row["backend"])
        for row in rows for requirement in row["requirement_ids"]
    }
    required = {
        (requirement, scenario, root, backend)
        for requirement, scenarios in REQUIRED_COVERAGE.items()
        for scenario in scenarios for root in ROOTS for backend in BACKENDS
    }
    if projected != required or len(required) != 384:
        raise ValueError("bootstrap graph selector does not cover the exact 384 tuples")


def shard_selectors(manifest: dict[str, object], *, root: str, backend: str) -> list[str]:
    if root not in ROOTS or backend not in BACKENDS:
        raise ValueError("unknown bootstrap graph selector shard")
    rows = manifest["rows"]
    if not isinstance(rows, list):
        raise ValueError("bootstrap graph selector rows are not a list")
    selectors = [
        str(row["pytest_selector"])
        for row in rows
        if row["root"] == root and row["backend"] == backend
    ]
    if len(selectors) != 29 or len(set(selectors)) != 29:
        raise ValueError("bootstrap graph selector shard is incomplete or duplicated")
    return selectors


def run_shard(
    manifest: dict[str, object], *, root: str, backend: str, receipt: Path,
) -> None:
    selectors = shard_selectors(manifest, root=root, backend=backend)
    started = time.monotonic()
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-W", "error", *selectors, "-p", "no:cacheprovider"],
        check=False,
    )
    elapsed = time.monotonic() - started
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)
    body = {
        "schema_version": 1,
        "owner": "bootstrap-graph-transaction-boundary",
        "manifest_digest": manifest["manifest_digest"],
        "root": root,
        "backend": backend,
        "selectors": selectors,
        "selector_count": len(selectors),
        "elapsed_milliseconds": round(elapsed * 1000),
        "runtime_budget_seconds": RUNTIME_BUDGET_SECONDS,
    }
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(
        json.dumps({**body, "receipt_digest": contract_digest(RECEIPT_DOMAIN, body)}, indent=2) + "\n",
        encoding="utf-8",
    )


def validate_receipts(manifest: dict[str, object], receipt_dir: Path) -> None:
    receipts = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(receipt_dir.glob("*.json"))]
    if len(receipts) != len(ROOTS) * len(BACKENDS):
        raise ValueError("bootstrap graph receipt collection is incomplete")
    observed: set[str] = set()
    shards: set[tuple[str, str]] = set()
    for receipt in receipts:
        digest = receipt.pop("receipt_digest", None)
        if digest != contract_digest(RECEIPT_DOMAIN, receipt):
            raise ValueError("bootstrap graph receipt digest is stale")
        shard = (str(receipt["root"]), str(receipt["backend"]))
        if shard in shards or receipt["manifest_digest"] != manifest["manifest_digest"]:
            raise ValueError("bootstrap graph receipt producer is duplicated or stale")
        shards.add(shard)
        expected = shard_selectors(manifest, root=shard[0], backend=shard[1])
        if receipt["selectors"] != expected or receipt["selector_count"] != 29:
            raise ValueError("bootstrap graph receipt selectors are substituted")
        if int(receipt["elapsed_milliseconds"]) > int(receipt["runtime_budget_seconds"]) * 1000:
            raise ValueError("bootstrap graph receipt exceeded its runtime budget")
        if observed.intersection(expected):
            raise ValueError("bootstrap graph selector has duplicate CI ownership")
        observed.update(expected)
    expected_all = {str(row["pytest_selector"]) for row in manifest["rows"]}
    if observed != expected_all:
        raise ValueError("bootstrap graph receipts do not cover the manifest")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--run-shard", action="store_true")
    parser.add_argument("--root", choices=ROOTS)
    parser.add_argument("--backend", choices=BACKENDS)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--validate-receipts", type=Path)
    args = parser.parse_args()
    if args.write:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(
            json.dumps(build_manifest(), indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    validate_manifest(manifest)
    if args.run_shard:
        if args.root is None or args.backend is None or args.receipt is None:
            parser.error("--run-shard requires --root, --backend, and --receipt")
        run_shard(manifest, root=args.root, backend=args.backend, receipt=args.receipt)
    if args.validate_receipts is not None:
        validate_receipts(manifest, args.validate_receipts)


if __name__ == "__main__":
    main()
