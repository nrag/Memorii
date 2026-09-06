from __future__ import annotations

import argparse
import contextvars
import json
import os
import random
import statistics
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

ROOT = Path("/Users/nandaraghunathan/Code/Memorii/Memorii")
VBP_WORK = ROOT / "docs/work/semantic-ingestion-validation-boundary-performance-2026-08-17"
DEBUG_WORK = ROOT / "docs/work/semantic-ingestion-canonical-evidence-production-performance-2026-08-16"
sys.path.insert(0, str(VBP_WORK))

import vbp_exp_002_preparation_capability as base
from memorii.core.memory_evolution.semantic_analysis.source_contracts import PreparedSource

MODES = ("safe_reference", "persisted_reload", "rollback")
SAMPLES = 3
SEED = 20260817
CHILD_TIMEOUT_SECONDS = 120


class _CountingProducer:
    def __init__(self, producer: object) -> None:
        self._producer = producer
        self.calls = 0

    def __call__(self, request: object) -> PreparedSource:
        self.calls += 1
        return self._producer(request)


def _child(mode: str) -> None:
    observation, ingress, operation_id = base._scenario_material()
    service = base._service()
    ingestion = service._provider_ingestion
    runtime = ingestion._semantic_runtime
    preparation = runtime.text_preparation_service
    repository = runtime.prepared_source_repository
    atomic_store = ingestion._atomic_store

    issuer = base._ReferenceIssuer()
    original_validate = PreparedSource.model_validate
    validation_sites: list[tuple[str, bool]] = []

    @classmethod
    def reference_validate(
        cls: type[PreparedSource], value: object, *args: object, **kwargs: object
    ) -> PreparedSource:
        registered = id(value) in issuer._mappings
        validation_sites.append((sys._getframe(1).f_code.co_name, registered))
        consumed = issuer.consume(value)
        return consumed if consumed is not None else original_validate(value, *args, **kwargs)

    PreparedSource.model_validate = reference_validate
    counting = _CountingProducer(preparation._producer)
    proxy = base._TrustedProducerProxy(counting, issuer)
    preparation._producer = proxy

    semantic_context = contextvars.ContextVar("pbd_exp_004_semantic_context", default=False)
    original_run_semantic = type(ingestion)._run_semantic_ingestion
    original_prepare_publish = type(preparation).prepare_and_publish
    original_repository_load = type(repository).load
    original_bootstrap_publish = type(atomic_store).publish_bootstrap_prepared_source_if_absent
    original_semantic_publish = type(atomic_store).publish_prepared_source
    repository_load_calls = 0
    bootstrap_publish_calls = 0
    semantic_publish_calls = 0
    persisted_reload_hits = 0

    def observed_run_semantic(self: object, *args: object, **kwargs: object) -> object:
        token = semantic_context.set(self is ingestion)
        try:
            return original_run_semantic(self, *args, **kwargs)
        finally:
            semantic_context.reset(token)

    def observed_repository_load(self: object, *args: object, **kwargs: object) -> object:
        nonlocal repository_load_calls
        if self is repository:
            repository_load_calls += 1
        return original_repository_load(self, *args, **kwargs)

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

    def observed_prepare_publish(self: object, request: object) -> PreparedSource:
        nonlocal persisted_reload_hits
        if (
            self is preparation
            and mode == "persisted_reload"
            and semantic_context.get()
        ):
            loaded = repository.load(
                source_id=request.observation.source_id,
                source_digest=request.observation.source_digest,
            )
            if loaded is not None:
                persisted_reload_hits += 1
                verifier = type(preparation)(
                    producer=lambda _: loaded,
                    repository=repository,
                )
                return verifier.prepare(request)
        return original_prepare_publish(self, request)

    type(ingestion)._run_semantic_ingestion = observed_run_semantic
    type(preparation).prepare_and_publish = observed_prepare_publish
    type(repository).load = observed_repository_load
    type(atomic_store).publish_bootstrap_prepared_source_if_absent = observed_bootstrap_publish
    type(atomic_store).publish_prepared_source = observed_semantic_publish
    try:
        elapsed, output, content_calls = base._run(
            service, observation, ingress, operation_id
        )
    finally:
        type(atomic_store).publish_prepared_source = original_semantic_publish
        type(atomic_store).publish_bootstrap_prepared_source_if_absent = original_bootstrap_publish
        type(repository).load = original_repository_load
        type(preparation).prepare_and_publish = original_prepare_publish
        type(ingestion)._run_semantic_ingestion = original_run_semantic
        PreparedSource.model_validate = original_validate
        issuer.close()

    if bootstrap_publish_calls != 1:
        raise RuntimeError(f"bootstrap publication count changed: {bootstrap_publish_calls}")
    if mode == "persisted_reload":
        if counting.calls != 1 or semantic_publish_calls != 0 or persisted_reload_hits != 1:
            raise RuntimeError(
                "persisted reload did not replace exactly the second lifecycle: "
                f"producer={counting.calls}, semantic_publish={semantic_publish_calls}, "
                f"reload_hits={persisted_reload_hits}"
            )
        if repository_load_calls != 1:
            raise RuntimeError(
                f"persisted reload count changed on the pre-pipeline path: {repository_load_calls}"
            )
    elif counting.calls != 2 or semantic_publish_calls != 1 or persisted_reload_hits != 0:
        raise RuntimeError(
            "baseline or rollback lifecycle accounting changed: "
            f"producer={counting.calls}, semantic_publish={semantic_publish_calls}, "
            f"reload_hits={persisted_reload_hits}"
        )
    registered_sites = [site for site, registered in validation_sites if registered]
    if any(site != "prepare" for site in registered_sites):
        raise RuntimeError(f"private authority crossed a mandatory boundary: {registered_sites}")
    ordinary_sites = [site for site, registered in validation_sites if not registered]
    print(
        json.dumps(
            {
                "mode": mode,
                "elapsed_seconds": elapsed,
                "output_sha256": sha256(output).hexdigest(),
                "content_validation_calls": content_calls,
                "producer_calls": counting.calls,
                "bootstrap_publish_calls": bootstrap_publish_calls,
                "semantic_publish_calls": semantic_publish_calls,
                "repository_load_calls": repository_load_calls,
                "persisted_reload_hits": persisted_reload_hits,
                "registered_validation_sites": registered_sites,
                "ordinary_validation_sites": ordinary_sites,
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
            raise RuntimeError(f"PBD-EXP-004 child timed out: {ordinal=} {sample=} {mode=}") from error
        if completed.returncode != 0:
            raise RuntimeError(
                f"PBD-EXP-004 child failed: {ordinal=} {sample=} {mode=} "
                f"stderr={completed.stderr[-2500:]!r}"
            )
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        run = json.loads(lines[-1])
        run.update({"ordinal": ordinal, "sample": sample})
        runs.append(run)

    if len({str(run["output_sha256"]) for run in runs}) != 1:
        raise RuntimeError("duplicate-lifecycle cells emitted different output bytes")
    distributions = {
        mode: _distribution(
            [float(run["elapsed_seconds"]) for run in runs if run["mode"] == mode]
        )
        for mode in MODES
    }
    validation_counts = {
        mode: sorted(
            {int(run["content_validation_calls"]) for run in runs if run["mode"] == mode}
        )
        for mode in MODES
    }
    if any(len(counts) != 1 for counts in validation_counts.values()):
        raise RuntimeError(f"validation accounting was nondeterministic: {validation_counts}")
    if validation_counts["rollback"] != validation_counts["safe_reference"]:
        raise RuntimeError("rollback did not restore baseline validation accounting")
    baseline = distributions["safe_reference"]["median"]
    optimized = distributions["persisted_reload"]["median"]
    reduction = 1.0 - optimized / baseline
    result = {
        "schema": "memorii.semantic-ingestion.production-performance.duplicate-step2.v1",
        "experiment": "PBD-EXP-004",
        "decision": "DUPLICATE_STEP2_PRE_PIPELINE_CONFIRMED",
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
        "distributions_seconds": distributions,
        "validation_counts": validation_counts,
        "persisted_reload_median_reduction_fraction": reduction,
        "pipeline_reload_exercised": False,
        "counterfactual_boundary": (
            "Bootstrap preparation/publication, handoff, persisted reload validation, production "
            "TextPreparationService source/policy checks, and the handled pre-pipeline terminal "
            "path execute. Only the second producer invocation and duplicate publication attempt "
            "are replaced. This scenario does not reach SemanticIngestionPipeline.run."
        ),
        "runs": runs,
    }
    evidence = DEBUG_WORK / "evidence/pbd-exp-004-duplicate-step2-v1.json"
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
