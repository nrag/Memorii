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
import memorii.core.memory_evolution.atomic_store as atomic_store_module
from memorii.core.memory_evolution.semantic_analysis.source_contracts import PreparedSource
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.semantic_ingestion import contracts

MODES = ("safe_reference", "captured_prepared_wire")
PARENTS = {
    "publish_bootstrap_prepared_source_if_absent": "bootstrap_publication_parent",
    "bootstrap_writer_handoff": "atomic_handoff_parent",
    "publish_prepared_source": "semantic_persistence_parent",
}
SAMPLES = 3
SEED = 20260817
CHILD_TIMEOUT_SECONDS = 120


class _KernelTimer:
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

    def parent(self) -> str | None:
        for frame in reversed(self._stack()):
            category = str(frame[0])
            if category in PARENTS.values():
                return category
        return None

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

    def patch_parent(self, owner: object, name: str, category: str) -> None:
        self._patch(owner, name, lambda: category)

    def patch_child(self, owner: object, name: str, child: str) -> None:
        self._patch(
            owner,
            name,
            lambda: f"{self.parent()}:{child}" if self.parent() is not None else None,
        )

    def _patch(self, owner: object, name: str, category_provider: object) -> None:
        original = getattr(owner, name)
        timer = self

        def measured(*args: object, **kwargs: object) -> object:
            category = category_provider()
            if category is None:
                return original(*args, **kwargs)
            return timer.measure(str(category), lambda: original(*args, **kwargs))

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
    writers = atomic_store._writers
    memory_plane = service._memory_plane
    timer = _KernelTimer()
    issuer = base._ReferenceIssuer()
    original_validate = PreparedSource.model_validate
    original_contract_encode = contracts.encode_semantic_contract
    captured_wire: bytes | None = None
    capture_calls = 0
    reuse_calls = 0

    if mode == "captured_prepared_wire":
        def captured_encode(value: object) -> bytes:
            nonlocal captured_wire, capture_calls, reuse_calls
            parent = timer.parent()
            if isinstance(value, PreparedSource) and captured_wire is not None and parent in {
                "atomic_handoff_parent",
                "semantic_persistence_parent",
            }:
                reuse_calls += 1
                return captured_wire
            wire = original_contract_encode(value)
            if (
                isinstance(value, PreparedSource)
                and captured_wire is None
                and parent == "bootstrap_publication_parent"
            ):
                captured_wire = wire
                capture_calls += 1
            return wire

        contracts.encode_semantic_contract = captured_encode

    @classmethod
    def reference_validate(
        cls: type[PreparedSource], value: object, *args: object, **kwargs: object
    ) -> PreparedSource:
        def validate() -> PreparedSource:
            consumed = issuer.consume(value)
            return consumed if consumed is not None else original_validate(value, *args, **kwargs)

        parent = timer.parent()
        if parent is not None:
            return timer.measure(f"{parent}:typed_reconstruction", validate)
        return validate()

    PreparedSource.model_validate = reference_validate
    proxy = base._TrustedProducerProxy(preparation._producer, issuer)
    preparation._producer = proxy

    for method, parent in PARENTS.items():
        timer.patch_parent(type(atomic_store), method, parent)
    timer.patch_child(contracts, "encode_semantic_contract", "canonical_encoding")
    timer.patch_child(CanonicalMemoryRecord, "__init__", "record_construction")
    timer.patch_child(atomic_store_module, "record_digest", "record_digest")
    timer.patch_child(type(memory_plane), "get_record", "record_read")
    timer.patch_child(type(memory_plane), "conditionally_write_records", "conditional_write")
    for method in ("current", "commit_binding", "require_current", "_authorize_atomic"):
        timer.patch_child(type(writers), method, f"writer_{method}")
    for method in ("_bootstrap_assertion_is_valid", "_current_bootstrap_access_is_valid"):
        timer.patch_child(atomic_store, method, method.removeprefix("_"))
    timer.patch_child(atomic_store, "_load_prepared_source_record", "prepared_record_reload")

    try:
        elapsed, output, content_calls = base._run(
            service, observation, ingress, operation_id
        )
    finally:
        timer.restore()
        PreparedSource.model_validate = original_validate
        contracts.encode_semantic_contract = original_contract_encode
        issuer.close()
    if mode == "captured_prepared_wire" and (capture_calls != 1 or reuse_calls != 2):
        raise RuntimeError(
            f"prepared-wire counterfactual count mismatch: {capture_calls=} {reuse_calls=}"
        )
    exclusive, calls = timer.result()
    parent_totals = {}
    for parent in PARENTS.values():
        parent_totals[parent] = exclusive.get(parent, 0.0) + sum(
            seconds
            for category, seconds in exclusive.items()
            if category.startswith(parent + ":")
        )
    print(
        json.dumps(
            {
                "mode": mode,
                "elapsed_seconds": elapsed,
                "output_sha256": sha256(output).hexdigest(),
                "content_validation_calls": content_calls,
                "exclusive_seconds": exclusive,
                "instrumented_calls": calls,
                "parent_totals_seconds": parent_totals,
                "capture_calls": capture_calls,
                "reuse_calls": reuse_calls,
            },
            sort_keys=True,
        )
    )


def _median_map(
    runs: list[dict[str, object]], mode: str, field: str
) -> dict[str, float]:
    selected = [run for run in runs if run["mode"] == mode]
    keys = sorted({key for run in selected for key in dict(run[field])})
    return {
        key: statistics.median(float(dict(run[field]).get(key, 0.0)) for run in selected)
        for key in keys
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
            raise RuntimeError(f"PBD-EXP-003 child timed out: {ordinal=} {sample=} {mode=}") from error
        if completed.returncode != 0:
            raise RuntimeError(
                f"PBD-EXP-003 child failed: {ordinal=} {sample=} {mode=} "
                f"stderr={completed.stderr[-2500:]!r}"
            )
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        run = json.loads(lines[-1])
        run.update({"ordinal": ordinal, "sample": sample})
        runs.append(run)

    if len({str(run["output_sha256"]) for run in runs}) != 1:
        raise RuntimeError("persistence-composition cells emitted different output bytes")
    if any(run["content_validation_calls"] != 833 for run in runs):
        raise RuntimeError("prepared-wire counterfactual changed validation accounting")

    exclusive = {mode: _median_map(runs, mode, "exclusive_seconds") for mode in MODES}
    totals = {mode: _median_map(runs, mode, "parent_totals_seconds") for mode in MODES}
    baseline_combined = sum(totals["safe_reference"].values())
    counterfactual_combined = sum(totals["captured_prepared_wire"].values())
    reduction = 1.0 - counterfactual_combined / baseline_combined
    child_totals: dict[str, float] = defaultdict(float)
    for category, seconds in exclusive["safe_reference"].items():
        if ":" in category:
            child_totals[category.split(":", 1)[1]] += seconds
    leading_kernel = max(child_totals, key=child_totals.get)
    result = {
        "schema": "memorii.semantic-ingestion.production-performance.persistence-composition.v1",
        "experiment": "PBD-EXP-003",
        "decision": "PERSISTENCE_COMPOSITION_KERNEL_DISCRIMINATED",
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
        "median_parent_totals_seconds": totals,
        "median_exclusive_seconds": exclusive,
        "safe_reference_combined_parent_seconds": baseline_combined,
        "captured_wire_combined_parent_seconds": counterfactual_combined,
        "captured_wire_combined_reduction_fraction": reduction,
        "leading_shared_kernel": leading_kernel,
        "safe_reference_shared_kernel_seconds": dict(child_totals),
        "counterfactual_boundary": (
            "Every persistence boundary retains full typed validation. Exact PreparedSource wire "
            "bytes captured after bootstrap publication are reused only to estimate canonical "
            "serialization cost in later persistence owners; no production coherence authority is claimed."
        ),
        "runs": runs,
    }
    evidence = DEBUG_WORK / "evidence/pbd-exp-003-persistence-composition-v1.json"
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
