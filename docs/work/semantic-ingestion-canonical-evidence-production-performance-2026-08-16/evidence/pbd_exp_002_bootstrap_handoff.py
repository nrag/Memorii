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

ROOT = Path("/Users/nandaraghunathan/Code/Memorii/Memorii")
VBP_WORK = ROOT / "docs/work/semantic-ingestion-validation-boundary-performance-2026-08-17"
DEBUG_WORK = ROOT / "docs/work/semantic-ingestion-canonical-evidence-production-performance-2026-08-16"
sys.path.insert(0, str(VBP_WORK))

import vbp_exp_002_preparation_capability as base
import memorii.core.provider.ingestion as provider_ingestion_module
from memorii.core.memory_evolution.semantic_analysis.source_contracts import PreparedSource
from memorii.core.semantic_ingestion import contracts

MODES = ("safe_reference", "captured_handoff_encode")
SAMPLES = 3
SEED = 20260817
CHILD_TIMEOUT_SECONDS = 120
PARENT = "bootstrap_handoff_parent"


class _NestedTimer:
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

    def contains(self, category: str) -> bool:
        return any(frame[0] == category for frame in self._stack())

    def current(self) -> str | None:
        stack = self._stack()
        return str(stack[-1][0]) if stack else None

    def measure(self, category: str, action: object) -> object:
        stack = self._stack()
        frame: list[object] = [category, time.perf_counter(), 0.0]
        stack.append(frame)
        try:
            return action()
        finally:
            elapsed = time.perf_counter() - float(frame[1])
            stack.pop()
            self._totals[category] += elapsed - float(frame[2])
            self._calls[category] += 1
            if stack:
                stack[-1][2] = float(stack[-1][2]) + elapsed

    def patch(
        self,
        owner: object,
        name: str,
        category: str,
        *,
        only_within_parent: bool = False,
    ) -> None:
        original = getattr(owner, name)
        timer = self

        def measured(*args: object, **kwargs: object) -> object:
            if only_within_parent and not timer.contains(PARENT):
                return original(*args, **kwargs)
            return timer.measure(category, lambda: original(*args, **kwargs))

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
    preparation = ingestion._semantic_runtime.text_preparation_service
    atomic_store = ingestion._atomic_store
    writer_admission = ingestion._writer_admission
    timer = _NestedTimer()
    issuer = base._ReferenceIssuer()
    original_validate = PreparedSource.model_validate
    original_contract_encode = contracts.encode_semantic_contract
    original_provider_encode = provider_ingestion_module.encode_semantic_contract
    captured_wire: bytes | None = None
    capture_calls = 0
    reuse_calls = 0

    if mode == "captured_handoff_encode":
        def capture_publication_wire(value: object) -> bytes:
            nonlocal captured_wire, capture_calls
            wire = original_contract_encode(value)
            if isinstance(value, PreparedSource) and sys._getframe(1).f_code.co_name == "publish_bootstrap_prepared_source_if_absent":
                captured_wire = wire
                capture_calls += 1
            return wire

        def reuse_handoff_wire(value: object) -> bytes:
            nonlocal reuse_calls
            if (
                isinstance(value, PreparedSource)
                and captured_wire is not None
                and timer.contains(PARENT)
            ):
                reuse_calls += 1
                return captured_wire
            return original_provider_encode(value)

        contracts.encode_semantic_contract = capture_publication_wire
        provider_ingestion_module.encode_semantic_contract = reuse_handoff_wire

    @classmethod
    def reference_validate(
        cls: type[PreparedSource], value: object, *args: object, **kwargs: object
    ) -> PreparedSource:
        def validate() -> PreparedSource:
            consumed = issuer.consume(value)
            return consumed if consumed is not None else original_validate(value, *args, **kwargs)

        if timer.current() == PARENT:
            return timer.measure("published_value_validation", validate)
        return validate()

    PreparedSource.model_validate = reference_validate
    proxy = base._TrustedProducerProxy(preparation._producer, issuer)
    preparation._producer = proxy

    timer.patch(type(ingestion), "_bootstrap_prepare_and_handoff", PARENT)
    timer.patch(
        type(ingestion),
        "_load_admitted_observation",
        "observation_reload",
        only_within_parent=True,
    )
    timer.patch(
        type(atomic_store),
        "assert_current_bootstrap_release",
        "release_assertions",
        only_within_parent=True,
    )
    timer.patch(type(preparation), "prepare", "preparation", only_within_parent=True)
    timer.patch(
        type(atomic_store),
        "publish_bootstrap_prepared_source_if_absent",
        "bootstrap_publication",
        only_within_parent=True,
    )
    timer.patch(
        provider_ingestion_module,
        "encode_semantic_contract",
        "handoff_canonical_encode",
        only_within_parent=True,
    )
    timer.patch(
        type(writer_admission),
        "current",
        "writer_admission_read",
        only_within_parent=True,
    )
    timer.patch(
        type(atomic_store),
        "bootstrap_writer_handoff",
        "atomic_writer_handoff",
        only_within_parent=True,
    )
    try:
        elapsed, output, content_calls = base._run(
            service, observation, ingress, operation_id
        )
    finally:
        timer.restore()
        PreparedSource.model_validate = original_validate
        contracts.encode_semantic_contract = original_contract_encode
        provider_ingestion_module.encode_semantic_contract = original_provider_encode
        issuer.close()
    if mode == "captured_handoff_encode" and (capture_calls != 1 or reuse_calls != 1):
        raise RuntimeError(
            f"captured counterfactual did not execute exactly once: {capture_calls=} {reuse_calls=}"
        )
    exclusive, calls = timer.result()
    parent_total = exclusive.get(PARENT, 0.0) + sum(
        seconds for category, seconds in exclusive.items() if category != PARENT
    )
    print(
        json.dumps(
            {
                "mode": mode,
                "elapsed_seconds": elapsed,
                "output_sha256": sha256(output).hexdigest(),
                "content_validation_calls": content_calls,
                "bootstrap_handoff_seconds": parent_total,
                "exclusive_seconds": exclusive,
                "instrumented_calls": calls,
                "capture_calls": capture_calls,
                "reuse_calls": reuse_calls,
            },
            sort_keys=True,
        )
    )


def _medians(runs: list[dict[str, object]], mode: str) -> dict[str, float]:
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
            raise RuntimeError(f"PBD-EXP-002 child timed out: {ordinal=} {sample=} {mode=}") from error
        if completed.returncode != 0:
            raise RuntimeError(
                f"PBD-EXP-002 child failed: {ordinal=} {sample=} {mode=} "
                f"stderr={completed.stderr[-2000:]!r}"
            )
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        run = json.loads(lines[-1])
        run.update({"ordinal": ordinal, "sample": sample})
        runs.append(run)

    if len({str(run["output_sha256"]) for run in runs}) != 1:
        raise RuntimeError("bootstrap handoff cells emitted different output bytes")
    if any(run["content_validation_calls"] != 833 for run in runs):
        raise RuntimeError("bootstrap handoff counterfactual changed validation accounting")
    medians = {mode: _medians(runs, mode) for mode in MODES}
    baseline_total = statistics.median(
        float(run["bootstrap_handoff_seconds"])
        for run in runs
        if run["mode"] == "safe_reference"
    )
    counterfactual_total = statistics.median(
        float(run["bootstrap_handoff_seconds"])
        for run in runs
        if run["mode"] == "captured_handoff_encode"
    )
    reduction = 1.0 - counterfactual_total / baseline_total
    child_medians = {
        category: seconds
        for category, seconds in medians["safe_reference"].items()
        if category != PARENT
    }
    leading_child = max(child_medians, key=child_medians.get)
    result = {
        "schema": "memorii.semantic-ingestion.production-performance.bootstrap-handoff.v1",
        "experiment": "PBD-EXP-002",
        "decision": "BOOTSTRAP_HANDOFF_CHILDREN_AND_ENCODING_DISCRIMINATED",
        "evidence_stage": "reference_only_diagnostic",
        "production_implementation_changed": False,
        "certifies_m3_1": False,
        "manifest": {
            "samples_per_mode": SAMPLES,
            "random_seed": SEED,
            "child_timeout_seconds": CHILD_TIMEOUT_SECONDS,
            "script_sha256": sha256(script.read_bytes()).hexdigest(),
            "order": [
                {"ordinal": run["ordinal"], "sample": run["sample"], "mode": run["mode"]}
                for run in runs
            ],
        },
        "output_sha256": str(runs[0]["output_sha256"]),
        "median_exclusive_seconds": medians,
        "leading_safe_reference_child": leading_child,
        "baseline_bootstrap_handoff_median_seconds": baseline_total,
        "captured_encode_bootstrap_handoff_median_seconds": counterfactual_total,
        "captured_encode_handoff_reduction_fraction": reduction,
        "counterfactual_boundary": (
            "Non-implementable causal upper bound: exact bytes captured at bootstrap publication "
            "are reused only for the later handoff encode in the same reference process. No trust "
            "or production authority is inferred from this result."
        ),
        "runs": runs,
    }
    evidence = DEBUG_WORK / "evidence/pbd-exp-002-bootstrap-handoff-v1.json"
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
