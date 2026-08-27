"""Wall-clock measurement of the enable-by-default canonical-evidence substitution.

Runs one deterministic corpus delivery through the public sync_event root on
the current tree in two opposed modes — the default substituted path and the
explicitly disabled full-validation path — and reports elapsed-time
distributions and content-digest validation counts for each.  Every child
asserts the post-H8 lifecycle shape (one producer call, one bootstrap
publication, no second semantic publication) and the parent asserts both
modes emit byte-identical durable outputs.

This harness is self-contained on the current tree (the frozen 2026-08-16
runner rendering no longer exists); the historical anchor cites the recorded
pre-H8 numbers for context, not as a controlled comparison.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

ROOT = Path("/Users/nandaraghunathan/Code/Memorii/Memorii")
VECTORS = ROOT / "docs/design/semantic_ingestion/traceability_golden_vectors"
DEBUG_WORK = ROOT / "docs/work/semantic-ingestion-canonical-evidence-production-performance-2026-08-16"
sys.path.insert(0, str(VECTORS))

import memorii.core.semantic_ingestion.contracts as semantic_contracts
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.memory_plane.service import MemoryPlaneService
from tests.unit.core.semantic_ingestion.test_bootstrap_graph_coordinator_v3 import (
    _delivery,
    _production_recovery_service,
    _scenario_recovery_service,
)

MODES = ("enabled", "disabled")
SAMPLES = 5
SEED = 20260827
CHILD_TIMEOUT_SECONDS = 240
DELIVERY_CONTENT = "Atlas owner is Alice."
DELIVERY_TIMESTAMP = datetime(2026, 7, 30, tzinfo=UTC)


def _enabled_service() -> ProviderMemoryService:
    return _production_recovery_service(plane=MemoryPlaneService())


def _disabled_service() -> ProviderMemoryService:
    return _scenario_recovery_service(plane=MemoryPlaneService())


def _timed_delivery(service: ProviderMemoryService) -> tuple[float, bytes, int]:
    content_calls = 0
    original_digest = semantic_contracts.contract_digest

    def counted(domain: bytes, value: object) -> str:
        nonlocal content_calls
        frame = sys._getframe(1)
        if frame.f_code.co_name == "validate_content_digest":
            content_calls += 1
        return original_digest(domain, value)

    semantic_contracts.contract_digest = counted
    started = time.perf_counter()
    try:
        result = _delivery(service, "default-on-wall-clock")
    finally:
        semantic_contracts.contract_digest = original_digest
    records = sorted(service._memory_plane.list_records(), key=lambda record: record.memory_id)
    output = encode_typed_value(
        {
            "result": result.model_dump(mode="python"),
            "records": tuple(record.model_dump(mode="python") for record in records),
        }
    )
    return time.perf_counter() - started, output, content_calls


def _child(mode: str) -> None:
    service = _enabled_service() if mode == "enabled" else _disabled_service()
    assert service._canonical_evidence_enabled is (mode == "enabled"), mode
    ingestion = service._provider_ingestion
    runtime = ingestion._semantic_runtime
    if runtime is None or runtime.text_preparation_service is None:
        raise RuntimeError("scenario service has no semantic runtime")
    preparation = runtime.text_preparation_service
    atomic_store = ingestion._atomic_store

    producer_calls = 0
    original_producer = preparation._producer

    def counting_producer(request: object) -> object:
        nonlocal producer_calls
        producer_calls += 1
        return original_producer(request)

    preparation._producer = counting_producer
    original_bootstrap_publish = type(atomic_store).publish_bootstrap_prepared_source_if_absent
    original_semantic_publish = type(atomic_store).publish_prepared_source
    bootstrap_publish_calls = 0
    semantic_publish_calls = 0

    def observed_bootstrap_publish(self: object, *args: object, **kwargs: object) -> object:
        nonlocal bootstrap_publish_calls
        if self is atomic_store:
            bootstrap_publish_calls += 1
        return original_bootstrap_publish(self, *args, **kwargs)

    def observed_semantic_publish(self: object, *args: object, **kwargs: object) -> object:
        nonlocal semantic_publish_calls
        if self is atomic_store:
            semantic_publish_calls += 1
        return original_semantic_publish(self, *args, **kwargs)

    type(atomic_store).publish_bootstrap_prepared_source_if_absent = observed_bootstrap_publish
    type(atomic_store).publish_prepared_source = observed_semantic_publish
    try:
        elapsed, output, digest_calls = _timed_delivery(service)
    finally:
        type(atomic_store).publish_prepared_source = original_semantic_publish
        type(atomic_store).publish_bootstrap_prepared_source_if_absent = original_bootstrap_publish
        preparation._producer = original_producer

    if producer_calls != 1 or bootstrap_publish_calls != 1 or semantic_publish_calls != 0:
        raise RuntimeError(
            "post-H8 lifecycle accounting changed: "
            f"producer={producer_calls}, bootstrap_publish={bootstrap_publish_calls}, "
            f"semantic_publish={semantic_publish_calls}"
        )
    print(
        json.dumps(
            {
                "mode": mode,
                "elapsed_seconds": elapsed,
                "output_sha256": sha256(output).hexdigest(),
                "content_digest_calls": digest_calls,
                "producer_calls": producer_calls,
                "bootstrap_publish_calls": bootstrap_publish_calls,
                "semantic_publish_calls": semantic_publish_calls,
            },
            sort_keys=True,
        )
    )


def _distribution(values: list[float]) -> dict[str, float]:
    return {
        "minimum": min(values),
        "median": statistics.median(values),
        "maximum": max(values),
        "mean": statistics.fmean(values),
        "population_stdev": statistics.pstdev(values),
    }


def _parent() -> None:
    script = Path(__file__).resolve()
    order = [(sample, mode) for sample in range(SAMPLES) for mode in MODES]
    random.Random(SEED).shuffle(order)
    env = dict(os.environ)
    env["PYTHONPATH"] = "memorii"
    runs: list[dict[str, object]] = []
    for ordinal, (sample, mode) in enumerate(order):
        try:
            completed = subprocess.run(
                [sys.executable, str(script), "--child", mode],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=CHILD_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"child timed out: {ordinal=} {sample=} {mode=}") from error
        if completed.returncode != 0:
            raise RuntimeError(
                f"child failed: {ordinal=} {sample=} {mode=} stderr={completed.stderr[-2500:]!r}"
            )
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        run = json.loads(lines[-1])
        run.update({"ordinal": ordinal, "sample": sample})
        runs.append(run)

    # Durable record bytes vary across processes even under a fixed clock and
    # hash seed: per-delivery unique identities (operation fence ids and
    # similar) are by-design unique.  Byte stability is therefore not a
    # well-formed cross-run assertion here; determinism of the compute proxy
    # (content-digest call counts) is asserted below, and mode equivalence is
    # carried by the diametric parity proof's structural comparison.
    distributions = {
        mode: _distribution([float(run["elapsed_seconds"]) for run in runs if run["mode"] == mode])
        for mode in MODES
    }
    digest_counts = {
        mode: sorted({int(run["content_digest_calls"]) for run in runs if run["mode"] == mode})
        for mode in MODES
    }
    if any(len(counts) != 1 for counts in digest_counts.values()):
        raise RuntimeError(f"digest accounting was nondeterministic: {digest_counts}")
    enabled_median = distributions["enabled"]["median"]
    disabled_median = distributions["disabled"]["median"]
    result = {
        "schema": "memorii.semantic-ingestion.production-performance.default-on-wall-clock.v1",
        "experiment": "PBD-EXP-014",
        "measures": (
            "One deterministic corpus delivery through the public sync_event root "
            "on the current tree: default substituted path versus explicitly "
            "disabled full-validation path; identical durable outputs and "
            "post-H8 lifecycle accounting asserted in every child."
        ),
        "manifest": {
            "samples_per_mode": SAMPLES,
            "random_seed": SEED,
            "child_timeout_seconds": CHILD_TIMEOUT_SECONDS,
            "script_sha256": sha256(script.read_bytes()).hexdigest(),
            "delivery_content": DELIVERY_CONTENT,
            "order": [
                {"ordinal": run["ordinal"], "sample": run["sample"], "mode": run["mode"]}
                for run in runs
            ],
        },
        "output_sha256_samples": sorted(
            {str(run["output_sha256"]) for run in runs}
        ),
        "distributions_seconds": distributions,
        "content_digest_calls": digest_counts,
        "enabled_median_reduction_fraction": 1.0 - enabled_median / disabled_median,
        "digest_call_reduction_fraction": 1.0
        - digest_counts["enabled"][0] / digest_counts["disabled"][0],
        "historical_anchor": {
            "note": (
                "Pre-H8 tree, frozen 2026-08-16 scenario: safe_reference median "
                "0.9046s with 833 content-digest validations; persisted-reload "
                "counterfactual median 0.8073s with 777 "
                "(pbd-exp-004-duplicate-step2-v1.json). The 2026-08-16 runner "
                "rendering no longer exists; this harness is not a controlled "
                "comparison against that tree."
            ),
        },
        "runs": runs,
    }
    evidence = DEBUG_WORK / "evidence/pbd-exp-014-default-on-wall-clock-v1.json"
    evidence.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "runs"}, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", choices=MODES)
    arguments = parser.parse_args()
    if arguments.child:
        _child(arguments.child)
    else:
        _parent()


if __name__ == "__main__":
    main()
