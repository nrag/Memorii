from __future__ import annotations

import argparse
import json
import os
import platform
import random
import statistics
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

ROOT = Path("/Users/nandaraghunathan/Code/Memorii/Memorii")
WORK = ROOT / "docs/work/semantic-ingestion-validation-boundary-performance-2026-08-17"
sys.path.insert(0, str(WORK))

import vbp_exp_002_preparation_capability as base
from memorii.core.memory_evolution.semantic_analysis.source_contracts import PreparedSource
from memorii.core.semantic_ingestion.canonical_evidence_arena import CanonicalEvidenceArena

MODES = (
    "legacy",
    "enabled",
    "unavailable",
    "saturated_legacy",
    "saturated_enabled",
    "rollback",
)
SAMPLES = 5
SEED = 20260817
CHILD_TIMEOUT_SECONDS = 120
CANDIDATE_LOCK = "24da95523b9a050266034cd6f3b923d52a4d8cc97cf83d32d83c1285bb2d99c3"


def _child(mode: str) -> None:
    observation, ingress, operation_id = base._scenario_material()
    original_validate = PreparedSource.model_validate
    issuer = base._ReferenceIssuer()

    @classmethod
    def reference_validate(
        cls: type[PreparedSource], value: object, *args: object, **kwargs: object
    ) -> PreparedSource:
        consumed = issuer.consume(value)
        return consumed if consumed is not None else original_validate(value, *args, **kwargs)

    reservations = (
        [CanonicalEvidenceArena() for _ in range(64)]
        if mode in {"saturated_legacy", "saturated_enabled"}
        else []
    )
    if mode != "rollback":
        PreparedSource.model_validate = reference_validate
    try:
        service = base._service()
        preparation = base._preparation(service)
        if mode in {"enabled", "unavailable", "saturated_enabled"}:
            proxy = base._TrustedProducerProxy(preparation._producer, issuer)
            preparation._producer = proxy
            if mode == "unavailable":
                issuer.close()
        elapsed, output, content_calls = base._run(
            service, observation, ingress, operation_id
        )
    finally:
        PreparedSource.model_validate = original_validate
        issuer.close()
        for arena in reservations:
            arena.close()
    print(
        json.dumps(
            {
                "mode": mode,
                "elapsed_seconds": elapsed,
                "content_validation_calls": content_calls,
                "output_sha256": sha256(output).hexdigest(),
            },
            sort_keys=True,
        )
    )


def _distribution(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "minimum": ordered[0],
        "median": statistics.median(ordered),
        "maximum": ordered[-1],
        "mean": statistics.fmean(ordered),
        "population_stdev": statistics.pstdev(ordered),
    }


def _parent() -> None:
    script = Path(__file__).resolve()
    order = [(sample, mode) for sample in range(SAMPLES) for mode in MODES]
    random.Random(SEED).shuffle(order)
    env = dict(os.environ)
    env["PYTHONPATH"] = "memorii"
    runs: list[dict[str, object]] = []
    for ordinal, (sample, mode) in enumerate(order):
        command = [sys.executable, str(script), "--child", mode]
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=CHILD_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(
                f"isolated child timed out: ordinal={ordinal}, sample={sample}, mode={mode}"
            ) from error
        if completed.returncode != 0:
            raise RuntimeError(
                "isolated child failed: "
                f"ordinal={ordinal}, sample={sample}, mode={mode}, "
                f"stderr={completed.stderr[-2000:]!r}"
            )
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        if not lines:
            raise RuntimeError(f"isolated child emitted no result: {mode}")
        result = json.loads(lines[-1])
        result.update({"ordinal": ordinal, "sample": sample})
        runs.append(result)

    output_digests = {str(run["output_sha256"]) for run in runs}
    if len(output_digests) != 1:
        raise RuntimeError("performance cells emitted different output bytes")
    expected_calls = {
        "legacy": 1021,
        "enabled": 833,
        "unavailable": 1021,
        "saturated_legacy": 1303,
        "saturated_enabled": 1303,
        "rollback": 1021,
    }
    for run in runs:
        mode = str(run["mode"])
        if run["content_validation_calls"] != expected_calls[mode]:
            raise RuntimeError(
                f"validation accounting changed for {mode}: "
                f"{run['content_validation_calls']} != {expected_calls[mode]}"
            )

    distributions = {
        mode: _distribution(
            [
                float(run["elapsed_seconds"])
                for run in runs
                if run["mode"] == mode
            ]
        )
        for mode in MODES
    }
    legacy_median = distributions["legacy"]["median"]
    enabled_median = distributions["enabled"]["median"]
    reduction = 1.0 - enabled_median / legacy_median
    validation_call_reduction = 1.0 - 833 / 1021
    all_candidate_call_reduction = 453 / 1021
    decision = (
        "FROZEN_TARGET_CREDIBLE"
        if reduction >= 0.75
        else "FROZEN_TARGET_NOT_CREDIBLE_FROM_VALIDATION_BOUNDARY_DESIGN"
    )

    result = {
        "schema": "memorii.semantic-ingestion.validation-boundary.performance-discrimination.v1",
        "experiment": "VBP-EXP-004",
        "decision": decision,
        "evidence_stage": "reference_only_repeated_isolated_diagnostic",
        "production_implementation_changed": False,
        "certifies_m3_1": False,
        "candidate_lock": CANDIDATE_LOCK,
        "manifest": {
            "samples_per_mode": SAMPLES,
            "random_seed": SEED,
            "child_timeout_seconds": CHILD_TIMEOUT_SECONDS,
            "child_processes": len(runs),
            "setup_excluded_from_elapsed": True,
            "python": sys.version,
            "platform": platform.platform(),
            "script_sha256": sha256(script.read_bytes()).hexdigest(),
            "order": [
                {"ordinal": run["ordinal"], "sample": run["sample"], "mode": run["mode"]}
                for run in runs
            ],
        },
        "output_sha256": next(iter(output_digests)),
        "expected_content_validation_calls": expected_calls,
        "distributions_seconds": distributions,
        "enabled_median_reduction_fraction": reduction,
        "selected_edge_validation_call_reduction_fraction": validation_call_reduction,
        "all_classified_candidate_calls_over_legacy_fraction": all_candidate_call_reduction,
        "target_reduction_fraction": 0.75,
        "interpretation": (
            "The selected edge is behaviorally safe and measurably beneficial, but its repeated "
            "same-mode median reduction does not approach the frozen target. Even eliminating all "
            "453 classified candidate calls would remove only 44.37% of the 1,021 normal legacy "
            "content-validation calls; call fraction is not a latency bound, but the current evidence "
            "does not establish that those candidates own 75% of production-shaped elapsed time."
        ),
        "runs": runs,
    }
    evidence = WORK / "evidence/vbp-exp-004-performance-discrimination-v1.json"
    evidence.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "runs"}, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", choices=MODES)
    arguments = parser.parse_args()
    if arguments.child is not None:
        _child(arguments.child)
    else:
        _parent()


if __name__ == "__main__":
    main()
