# Static Tooling Workflow

## C2 Layer 1 CTV v2 binding authority

```bash
python3.12 -I docs/design/semantic_ingestion/traceability_golden_vectors/check_ctv_binding_authority_v2.py \
  --design docs/design/semantic_ingestion_architecture.md \
  --registry docs/design/semantic_ingestion/traceability_registry/registry-v1.json \
  --authority docs/design/semantic_ingestion/traceability_golden_vectors/ctv-binding-authority-v2.json \
  --validator docs/design/semantic_ingestion/traceability_golden_vectors/validate_ctv_binding_authority_v2.py \
  --expected-design-sha256 e7de038a5cad8f8d95536d60d35621472a79588e100c2da8633a9dd1fcfb5e7a \
  --expected-registry-sha256 35396897f98833b3eeb9572b16d7eab38ea34741ca876a4a72048424de676ea3 \
  --expected-authority-sha256 0dff4f2c0c8a33b7a23ba067de07ae16e556d60b5f94192223b4c76a2246c056 \
  --expected-validator-sha256 826541e7864583bbe3c32e3f153c008f07a881f33d38861237dfac80d9f3657e \
  --expected-checker-sha256 e2c35870a99e587f34cbffc701f42587520ee015009cd51647367da56716c732
```

The gate requires architecture SHA-256
`e7de038a5cad8f8d95536d60d35621472a79588e100c2da8633a9dd1fcfb5e7a`,
authority SHA-256
`0dff4f2c0c8a33b7a23ba067de07ae16e556d60b5f94192223b4c76a2246c056`,
validator SHA-256
`826541e7864583bbe3c32e3f153c008f07a881f33d38861237dfac80d9f3657e`,
hermetic gate SHA-256
`e2c35870a99e587f34cbffc701f42587520ee015009cd51647367da56716c732`,
exactly 56 schemas, exactly 249 enum rows, and profile digest
`9dc8b3d01e3f78ed6a11c7668cbb576b09f48ddf107c5efe441bb8bad234fd7f`.
The checker self-hash is supplied by the reviewed command rather than embedded
inside the checker, avoiding an impossible self-referential file digest.

## Lifecycle-root genesis signer-provenance semantic evidence

```bash
python3.12 -I docs/design/semantic_ingestion/traceability_golden_vectors/check_lifecycle_root_signer_provenance_v1.py \
  --design docs/design/semantic_ingestion_architecture.md \
  --matrix docs/design/semantic_ingestion/traceability_golden_vectors/cgs_verification_attack_matrix-v1.json \
  --fixture docs/design/semantic_ingestion/traceability_golden_vectors/lifecycle-root-signer-provenance-witness-v1.json \
  --validator docs/design/semantic_ingestion/traceability_golden_vectors/validate_lifecycle_root_signer_provenance_v1.py \
  --expected-checker-sha256 c4168249dbf4845d90e9593819323dc331e22e3bdfa5a9df70b076ed10449f01 \
  --self-test
```

The current semantic gate pins design SHA-256
`e7de038a5cad8f8d95536d60d35621472a79588e100c2da8633a9dd1fcfb5e7a`,
matrix SHA-256
`a3375bd0d8d01cf7a7c9d7d16d90945d792d932eca7161097f6ee5ba44d3f604`,
witness SHA-256
`d3c1dce10624365647cbb00926f63b6deabe681e51a138bc3de88d7c60faef69`,
validator SHA-256
`46bbda1afb6ccbec5a49ea668752c19a7b1354b94515a33365191cee01745edb`,
and checker SHA-256
`c4168249dbf4845d90e9593819323dc331e22e3bdfa5a9df70b076ed10449f01`.
It must report exactly six accepted witnesses, 41 rejected witnesses, and two
identical isolated replicas. The totals include two canonical accepted roots,
four accepted inclusive-endpoint witnesses, four rejected outside-boundary
witnesses, 33 rejected root mutations, and four rejected malformed historical
coordinates. Its self-test also rejects boundary deletion, checker-identity
drift, and non-isolated invocation.

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

Historical-only (not a current gate): the following C2 recipe command verifies
its immutable historical design and registry bytes. It must not be run against
the current CGS design or used as current-contract evidence.

```bash
python docs/design/semantic_ingestion/traceability_golden_vectors/validate_recipe.py \
  --recipe docs/design/semantic_ingestion/traceability_golden_vectors/recipe-v1.json \
  --design docs/design/semantic_ingestion_architecture.md \
  --registry docs/design/semantic_ingestion/traceability_registry/registry-v1.json \
  --expected-recipe-sha256 9d5dbe525c22707d33878a7ce6788ba267816e5aff2f79500aa40286cbb2e1e8 \
  --expected-design-sha256 4020901b7b50d1a3ea2eee774af52234ef2b9f943176af506a9f15fc41f777b0 \
  --expected-registry-sha256 38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692 \
  --self-test
```

That historical gate is design-only and deterministic. It must validate the complete
candidate bytes, all frozen identities, the full 56-schema recursive type and
enum closure, all 66 mutation descriptors, deep authority equality, and the
full negative corpus. A changed design, recipe, or registry must update the
three reviewed identities in this command in the same design revision. The
gate must remain fail closed while an incomplete-authority sentinel is present;
removing such a sentinel requires a fresh three-role design review.

Run the current CGS ledger, matrix, and known-answer gate from repository root:

```bash
python3.12 docs/design/semantic_ingestion/traceability_golden_vectors/cgs_structural_manifest_prototype.py \
  docs/design/semantic_ingestion_architecture.md \
  docs/design/semantic_ingestion/traceability_registry/registry-v1.json \
  docs/design/semantic_ingestion/traceability_golden_vectors/structural_manifest_derivation_ledger-v1.json \
  docs/design/semantic_ingestion/traceability_golden_vectors/cgs-structural-manifest-prototype-v1.json --verify
python3.12 -m json.tool docs/design/semantic_ingestion/traceability_golden_vectors/structural_manifest_derivation_ledger-v1.json
python3.12 -m json.tool docs/design/semantic_ingestion/traceability_golden_vectors/cgs_verification_attack_matrix-v1.json
python3.12 docs/design/semantic_ingestion/traceability_golden_vectors/check_cgs_structural_contract_v1.py \
  --design docs/design/semantic_ingestion_architecture.md \
  --registry docs/design/semantic_ingestion/traceability_registry/registry-v1.json \
  --ledger docs/design/semantic_ingestion/traceability_golden_vectors/structural_manifest_derivation_ledger-v1.json \
  --matrix docs/design/semantic_ingestion/traceability_golden_vectors/cgs_verification_attack_matrix-v1.json \
  --prototype docs/design/semantic_ingestion/traceability_golden_vectors/cgs_structural_manifest_prototype.py \
  --vector docs/design/semantic_ingestion/traceability_golden_vectors/cgs-structural-manifest-prototype-v1.json --self-test
```

The current gate requires ledger raw SHA-256
`085921e6c4e995f0d6259c9f6f6eabeec3f1455bba344105ef0e16d24eb81671`, matrix
raw SHA-256 `a3375bd0d8d01cf7a7c9d7d16d90945d792d932eca7161097f6ee5ba44d3f604`,
prototype SHA-256
`b655f474e4918d64447251e40b9a3af53daca0efd2e2cb6baa76890243bae5ed`,
prototype-vector SHA-256
`7af8aa57cf1b81f243883077fdde27064a638e95bf366cfd1cfd16979340c3ab`,
and CGS checker SHA-256
`212d016465e26b42c101521ecaacc8cd4c475949d19d29aa92ecce93fbaac278`.

Build an installable wheel and verify package-owned prompt contracts:

```bash
python -m pip wheel . --no-deps --wheel-dir /tmp/memorii-wheel
python -m pip install --no-deps --target /tmp/memorii-wheel-site /tmp/memorii-wheel/*.whl
cd /tmp
PYTHONPATH=/tmp/memorii-wheel-site python -c "from memorii.core.memory_evolution.extraction_contracts import MemoryExtractionOutput; from memorii.core.prompts.runtime_manifest import PromptOwner; from memorii.core.prompts.registry import PromptRegistry; PromptRegistry().load('memory_extraction:v1', owner=PromptOwner.LLM_MEMORY_EXTRACTOR, output_model=MemoryExtractionOutput)"
PYTHONPATH=/tmp/memorii-wheel-site python -c "from importlib.util import find_spec; removed=('memorii.core.promotion.models', 'memorii.core.promotion.legacy_models', 'memorii.core.promotion.lifecycle_models', 'memorii.core.prompts.manifest', 'memorii.core.prompts.schema_compatibility'); assert all(find_spec(module) is None for module in removed)"
PYTHONPATH=/tmp/memorii-wheel-site python -m memorii.tools.run_eval --suite memory_evolution_sim_v1 --mode llm --dry-run --storage-root /tmp/memorii-wheel-benchmark --sim-profile long_horizon --sim-scenario-count 1 --sim-min-events 5 --sim-max-events 10 --sim-noise-rate 0.35 --seed 7
PYTHONPATH=/tmp/memorii-wheel-site python -m memorii.tools.validate_benchmark_artifacts --root /tmp/memorii-wheel-benchmark/benchmark_runs --suite memory_evolution_sim_v1
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
live gate. Manual dispatch runs the live matrix for a designated candidate; scheduled
execution is independently opt-in through the repository variable
`MEMORII_RUN_LIVE_GATES=true`. The gate runs ten generator seeds with 25 scenarios per
seed and two inference replicates. It requires `execution_source=live_llm`,
provider calls, one seed-invariant run configuration fingerprint, one source
revision, and one clean source-tree digest. Dirty or mixed source states cannot
produce a certification.

Repository rules require the deterministic `Unit Tests` and `Benchmark Contracts`
checks for normal pull requests. `Live Runtime Statistical Gate` is deliberately not
a permanent required check because it is a manually dispatched, three-hour candidate
acceptance run. A designated merge candidate is merge-ready only after that manual gate
passes on the exact unchanged PR head SHA.

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
