# Static Tooling Workflow

This project uses Ruff and scoped Pyright checks as PR gates. Ruff runs across the repository in error mode; Pyright covers every runtime, integration, benchmark, calibration, prompt-contract, and benchmark-runner surface owned by the engineering-hardening work.

## Install

From `memorii/`:

```bash
python -m pip install -e '.[dev]'
```

The `dev` extra installs the local test runner, live LLM dependency, Ruff, and Pyright. Production and benchmark semantics do not depend on these tools.

## Commands

Run unit tests:

```bash
python -W error -m pytest tests/unit -p no:cacheprovider
```

Run the full lint check:

```bash
python -m ruff check memorii tests
```

Run scoped type checks:

```bash
pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"
```

Build an installable wheel and verify package-owned prompt contracts:

```bash
python -m pip wheel . --no-deps --wheel-dir /tmp/memorii-wheel
python -m pip install --no-deps --target /tmp/memorii-wheel-site /tmp/memorii-wheel/*.whl
cd /tmp
PYTHONPATH=/tmp/memorii-wheel-site python -c "from memorii.core.memory_evolution.extraction import MemoryExtractionOutput; from memorii.core.prompts.runtime_manifest import PromptOwner; from memorii.core.prompts.registry import PromptRegistry; PromptRegistry().load('memory_extraction:v1', owner=PromptOwner.LLM_MEMORY_EXTRACTOR, output_model=MemoryExtractionOutput)"
PYTHONPATH=/tmp/memorii-wheel-site python -c "from importlib.util import find_spec; removed=('memorii.core.promotion.models', 'memorii.core.promotion.legacy_models', 'memorii.core.promotion.lifecycle_models', 'memorii.core.prompts.manifest', 'memorii.core.prompts.schema_compatibility'); assert all(find_spec(module) is None for module in removed)"
```

Move or remove any ignored in-tree `build/` directory before a local wheel
build. Setuptools can otherwise retain Python modules that were deleted from
the source tree; the final assertion above detects that contamination.

The Pyright scope is intentionally limited to:

- `memorii/core/belief`
- `memorii/core/benchmark/artifact_rows`
- `memorii/core/benchmark/artifact_validation.py`
- `memorii/core/benchmark/reproducibility.py`
- `memorii/core/memory_evolution`
- `memorii/core/memory_plane`
- `memorii/core/provider`
- `memorii/core/promotion`
- `memorii/core/benchmark/memory_evolution_sim`
- `memorii/core/benchmark/memory_evolution_runtime`
- `memorii/core/benchmark/calibration`
- `memorii/core/llm_decision`
- `memorii/core/prompts`
- `memorii/integrations`
- `memorii/tools/benchmark_suites`

Pyright is error-mode for the scoped surfaces above. Full-repo type checking is intentionally deferred until the rest of the repository has an explicit baseline.

Pyright intentionally does not pin `venvPath` or `venv` in `pyproject.toml`; local developers and CI should pass the active Python interpreter with `--pythonpath` from the environment where project dependencies are installed.

## Policy

- Do not mass-format unrelated files.
- Do not broaden type scope just to make a local edit feel cleaner.
- Fix new violations in touched files.
- Treat all configured Ruff findings as PR-gate failures.
- Treat Python warnings as unit and benchmark-contract test failures.
- Do not add per-package wildcard-import quarantines; simulator/runtime modules should use explicit imports.
- If a tool finding requires a semantic change, add or update a behavior test before changing code.
- Static tooling must not change benchmark pass/fail semantics, artifact schemas, prompt contracts, or production defaults.

## Benchmark Smoke Checks

After changes that touch benchmark, prompt, artifact, or runtime memory-evolution code, also run:

```bash
python -m memorii.tools.run_eval --suite memory_evolution_sim_v1 --mode all --dry-run --storage-root .memorii --sim-profile adversarial --sim-scenario-count 10 --sim-noise-rate 0.35 --seed 7
python -m memorii.tools.run_eval --suite memory_evolution_runtime_v1 --mode all --dry-run --storage-root .memorii --sim-profile long_horizon --sim-scenario-count 10 --sim-noise-rate 0.35 --seed 7
```

Live gates remain explicit and should only be run when intentionally validating provider behavior.

## CI Gate Boundaries

Pull requests run the deterministic benchmark-contract job. It exercises the
typed artifact validator, temporal/retrieval contracts, prompt no-leakage
checks, installed-wheel prompt loading, and fake-oracle simulator/runtime artifacts. It does not spend
provider credits or treat fake-oracle output as live success.

The scheduled workflow runs the same fake-oracle plumbing checks and has a separate
manual live gate. The live gate is opt-in through the repository variable
`MEMORII_RUN_LIVE_GATES=true`; it runs ten generator seeds with 25 scenarios per
seed and two inference replicates. It requires `execution_source=live_llm`,
provider calls, one seed-invariant run configuration fingerprint, one source
revision, and one clean source-tree digest. Dirty or mixed source states cannot
produce a certification.

The observed aggregate and family endpoints use exact one-sided beta-binomial
seed-cluster bounds under the declared intraseed-correlation assumption. Their
confidence level is adjusted simultaneously across the aggregate plus every
declared family. Every family must appear in every replicate; unexpected
families, provider failures, fallbacks, critical failure buckets, mixed
configurations, and underpowered seed/family sets fail the gate. Inference
replicates are collapsed conservatively and never increase the authoritative
scenario count.

The gate design is separately power- and coverage-audited over predeclared
reliability, dependence, and data-generating-process grids. Wilson bounds are
used only for finite-Monte-Carlo uncertainty in that coverage audit, not as the
production scenario interval. These simulations describe the gate design and
do not alter an observed run's verdict.
