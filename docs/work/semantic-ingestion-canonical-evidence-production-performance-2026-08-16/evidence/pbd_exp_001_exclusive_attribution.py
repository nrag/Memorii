from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import subprocess
import sys
import threading
import time
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from typing import Callable

ROOT = Path("/Users/nandaraghunathan/Code/Memorii/Memorii")
VBP_WORK = ROOT / "docs/work/semantic-ingestion-validation-boundary-performance-2026-08-17"
DEBUG_WORK = ROOT / "docs/work/semantic-ingestion-canonical-evidence-production-performance-2026-08-16"
sys.path.insert(0, str(VBP_WORK))

import vbp_exp_002_preparation_capability as base
from memorii.core.memory_evolution.semantic_analysis.source_contracts import PreparedSource
from memorii.core.semantic_ingestion import contracts

MODES = ("legacy", "safe_reference")
SAMPLES = 3
SEED = 20260817
CHILD_TIMEOUT_SECONDS = 120


class _ExclusiveTimer:
    def __init__(self) -> None:
        self._local = threading.local()
        self._totals: dict[str, float] = defaultdict(float)
        self._calls: dict[str, int] = defaultdict(int)
        self._restores: list[tuple[object, str, object]] = []

    def _stack(self) -> list[list[object]]:
        stack = getattr(self._local, "stack", None)
        if stack is None:
            stack = []
            self._local.stack = stack
        return stack

    def patch(self, owner: object, name: str, category: str) -> None:
        original = getattr(owner, name)
        timer = self

        def measured(*args: object, **kwargs: object) -> object:
            stack = timer._stack()
            frame: list[object] = [category, time.perf_counter(), 0.0]
            stack.append(frame)
            try:
                return original(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - float(frame[1])
                child_elapsed = float(frame[2])
                stack.pop()
                timer._totals[category] += elapsed - child_elapsed
                timer._calls[category] += 1
                if stack:
                    stack[-1][2] = float(stack[-1][2]) + elapsed

        self._restores.append((owner, name, original))
        setattr(owner, name, measured)

    def restore(self) -> None:
        for owner, name, original in reversed(self._restores):
            setattr(owner, name, original)
        self._restores.clear()

    def result(self) -> tuple[dict[str, float], dict[str, int]]:
        return dict(self._totals), dict(self._calls)


def _child(mode: str) -> None:
    observation, ingress, operation_id = base._scenario_material()
    service = base._service()
    ingestion = service._provider_ingestion
    pipeline = ingestion._semantic_pipeline
    preparation = ingestion._semantic_runtime.text_preparation_service
    atomic_store = ingestion._atomic_store
    memory_plane = service._memory_plane

    original_validate = PreparedSource.model_validate
    issuer = base._ReferenceIssuer()

    @classmethod
    def reference_validate(
        cls: type[PreparedSource], value: object, *args: object, **kwargs: object
    ) -> PreparedSource:
        consumed = issuer.consume(value)
        return consumed if consumed is not None else original_validate(value, *args, **kwargs)

    PreparedSource.model_validate = reference_validate
    if mode == "safe_reference":
        proxy = base._TrustedProducerProxy(preparation._producer, issuer)
        preparation._producer = proxy

    timer = _ExclusiveTimer()
    timer.patch(type(service), "sync_event", "provider_orchestration")
    timer.patch(type(ingestion), "_bootstrap_prepare_and_handoff", "bootstrap_handoff")
    timer.patch(type(ingestion), "_run_semantic_ingestion", "semantic_coordinator")
    timer.patch(type(pipeline), "run", "semantic_pipeline")
    timer.patch(type(preparation), "prepare", "preparation")
    timer.patch(type(preparation), "prepare_and_publish", "preparation_publication")
    timer.patch(
        type(atomic_store),
        "publish_bootstrap_prepared_source_if_absent",
        "bootstrap_persistence",
    )
    timer.patch(type(atomic_store), "publish_prepared_source", "semantic_persistence")
    timer.patch(type(memory_plane), "conditionally_write_records", "memory_write")
    timer.patch(contracts._ContentAddressedContract, "validate_content_digest", "content_validation")
    try:
        elapsed, output, content_calls = base._run(
            service, observation, ingress, operation_id
        )
    finally:
        timer.restore()
        PreparedSource.model_validate = original_validate
        issuer.close()
    exclusive, calls = timer.result()
    attributed = sum(exclusive.values())
    print(
        json.dumps(
            {
                "mode": mode,
                "elapsed_seconds": elapsed,
                "output_sha256": sha256(output).hexdigest(),
                "content_validation_calls": content_calls,
                "exclusive_seconds": exclusive,
                "instrumented_calls": calls,
                "attributed_seconds": attributed,
                "attributed_over_elapsed": attributed / elapsed,
            },
            sort_keys=True,
        )
    )


def _median_by_category(runs: list[dict[str, object]], mode: str) -> dict[str, float]:
    selected = [run for run in runs if run["mode"] == mode]
    categories = sorted(
        {
            category
            for run in selected
            for category in dict(run["exclusive_seconds"])
        }
    )
    return {
        category: statistics.median(
            float(dict(run["exclusive_seconds"]).get(category, 0.0))
            for run in selected
        )
        for category in categories
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
            raise RuntimeError(
                f"exclusive-attribution child timed out: {ordinal=} {sample=} {mode=}"
            ) from error
        if completed.returncode != 0:
            raise RuntimeError(
                f"exclusive-attribution child failed: {ordinal=} {sample=} {mode=} "
                f"stderr={completed.stderr[-2000:]!r}"
            )
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        run = json.loads(lines[-1])
        run.update({"ordinal": ordinal, "sample": sample})
        runs.append(run)

    if len({str(run["output_sha256"]) for run in runs}) != 1:
        raise RuntimeError("attribution cells emitted different output bytes")
    for run in runs:
        expected = 833 if run["mode"] == "safe_reference" else 1021
        if run["content_validation_calls"] != expected:
            raise RuntimeError(f"content validation count changed: {run!r}")
        coverage = float(run["attributed_over_elapsed"])
        if coverage < 0.95 or coverage > 1.05:
            raise RuntimeError(f"exclusive attribution did not close measured time: {coverage}")

    medians = {mode: _median_by_category(runs, mode) for mode in MODES}
    categories = sorted(set(medians["legacy"]) | set(medians["safe_reference"]))
    deltas = {
        category: medians["legacy"].get(category, 0.0)
        - medians["safe_reference"].get(category, 0.0)
        for category in categories
    }
    leading_residual = max(
        medians["safe_reference"], key=medians["safe_reference"].get
    )
    result = {
        "schema": "memorii.semantic-ingestion.production-performance.exclusive-attribution.v1",
        "experiment": "PBD-EXP-001",
        "decision": "RESIDUAL_STAGE_LOCALIZED",
        "evidence_stage": "reference_only_diagnostic",
        "production_implementation_changed": False,
        "certifies_m3_1": False,
        "manifest": {
            "samples_per_mode": SAMPLES,
            "random_seed": SEED,
            "child_timeout_seconds": CHILD_TIMEOUT_SECONDS,
            "setup_excluded": True,
            "script_sha256": sha256(script.read_bytes()).hexdigest(),
            "order": [
                {"ordinal": run["ordinal"], "sample": run["sample"], "mode": run["mode"]}
                for run in runs
            ],
        },
        "output_sha256": str(runs[0]["output_sha256"]),
        "median_exclusive_seconds": medians,
        "legacy_minus_reference_seconds": deltas,
        "leading_safe_reference_residual_category": leading_residual,
        "next_discriminating_ablation": (
            "Instrument the leading residual category's immediate production-owned children, "
            "then replace exactly one pure deterministic child result with a captured equivalent "
            "inside a reference-only cell. Require identical output bytes and validation counts."
        ),
        "runs": runs,
    }
    evidence = DEBUG_WORK / "evidence/pbd-exp-001-exclusive-attribution-v1.json"
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
