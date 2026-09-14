# PR 120 Milestone Gate Failures

- Work ID: semantic-ingestion-pr120-milestone-gates
- Work type: debugging
- Delivery fidelity: Level 2 early real-world testing
- Status: active
- Coordinator: `/root`
- Created: 2026-09-13
- Last updated: 2026-09-13
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/hermes-memory-provider-integration/implementation.plan.md`
- Canonical inputs: `.github/workflows/pr-gates.yml`, PR 120 run `34795511535`, semantic-ingestion and acceptance governing designs
- Expected outputs: green PR gate run, focused regression evidence, refreshed release-preparation evidence

## Objective

Make every required PR 120 check pass for the current semantic-ingestion and Hermes milestone without weakening runtime validation, authority boundaries, or gate coverage.

## Completion Contract

The exact failed job commands pass locally, generated release-preparation evidence is bound to the final candidate, applicable static checks pass, the correction is pushed, and every required PR 120 check reports success for that pushed revision.

## Scope And Fidelity

Fix production-shaped happy paths and common recovery/configuration failures exposed by the current PR gates. Preserve signed authority, capability-status, transaction, replay, and fixed-path validation. Production signing, hostile filesystem variants beyond the shared cause, and broader platform certification remain Level 3 work.

## Expected And Observed Behavior

Expected: Hermes discovery, acceptance authority, observation activation, graph projection, benchmark ownership, package smoke, and unit shards pass together.

Observed on run `34795511535`: Acceptance Authority Runtime, Package Smoke, Benchmark Contract Tests, Unit Test Shards 2 and 5, and Observation Ledger Activation failed. Local reproduction confirmed the dynamic-import ownership omission, missing preprovisioned revocation fixture, sticky-temporary-ancestor portability defect, stale graph fixture composition, and stale release-preparation candidate.

## Hypothesis Ledger

| Hypothesis | Evidence | Status |
| --- | --- | --- |
| Hermes dynamic loading lacks an explicit architecture owner | exact benchmark test reports `hermes_memory_provider.py: importlib.metadata` | confirmed |
| Acceptance runtime entry-point discovery is broken | installed metadata loads the class; construction fails because the configured reader root is absent | disproved |
| Linux `/tmp` is rejected before secure fixture descendants | CI fails at fixed-path admission; local fixture reaches missing reader root first | confirmed |
| Graph failures are independent assertions | a shared normalization-only fixture omits current graph authority/status composition | confirmed shared setup cause |
| Package implementation is broken | package proof stops before execution on changed frozen member hashes | disproved; evidence snapshot stale |

## Experiments And Results

- Focused architecture ownership test failed before the owner entry and passed after it.
- Acceptance fixture family failed before revocation-root provisioning and passed after provisioning plus trusted-sticky-ancestor handling.
- V3 JSONL recovery ended in `preplanning` before scenario graph composition and passed after installing the deterministic graph host.
- Accepted graph materialization then exposed the required capability-status read-set, so activation fixtures must install their existing signed monitoring authority rather than bypass that check.
- The real activated-ledger ingest, detached observation, and JSONL reopen proof passes with the production graph host (1 test, 1008.07 seconds locally).
- Benchmark contracts pass (302 tests), the complete acceptance unit family passes (156 tests), unit shard 5 passes (853 tests), and the graph-observation native projection family passes (29 tests).
- Exact shard 2 isolated two historical monitor restart regressions. Retained version-1 status now remains fenced for the normal monitor tick; both restart proofs pass after the correction.
- The independent structural comparator imported production observation models. Replacing those imports with checks over the already validated public object shape restored the serialized package boundary; its 21 focused tests pass.
- Unit shard 2 passes after the retained version-1 monitoring correction (998 tests).
- The six observation-gate failures from the interrupted aggregate run now pass in their focused families: the five-case retained-control tamper family, fresh-process public reopen, and the native graph audit.
- Exact CI static commands pass: Ruff reports no findings, Pyright reports zero errors, and the static-tooling contract family passes (18 tests).
- Python 3.11 package bootstrap smoke passes (19 tests), matching the CI interpreter.
- Refreshing the package candidate exposed seven stale decoder-source identities left by the earlier public-helper rename. Regenerating the canonical decoder/publication package changed no declarations, restored primary/independent compiler parity across 181 entries and 1,269 roles, and passed all 58 positive/rejection vectors.
- The final Python 3.11 installed-wheel proof passes for candidate source `25b1d22b`: 23 distributions, 6,036 installed files, 1,800 package files, valid preparation accepted, and all five configured mutation families rejected.
- Targeted correctness and test reviewers found no confirmed P1/P2 issue in the production repair slice at `3684a9e3`.

## Changed Surfaces

- `acceptance/host_runtime.py`: portable secure ancestry validation.
- `memorii/memorii/core/memory_evolution/deployment_authorization.py`: matching storage ancestry validation.
- `memorii/memorii/core/provider/service.py`: preserve fenced version-1 monitor state through startup initialization.
- `acceptance/structural_comparator.py`: remove production-package imports from independent comparison.
- Acceptance and semantic-ingestion fixtures: complete current authority composition.
- Benchmark/static tooling ledgers: exact new dynamic-import and job ownership.
- Release-preparation evidence: regenerate only after the code candidate is stable.

## Gate Ledger

| Gate | Current result |
| --- | --- |
| Benchmark dynamic-import ownership reproducer | passed after correction |
| Acceptance installed-runtime unit family | passed, 156 tests |
| Static workflow ownership/umbrella assertions | passed after correction |
| V3 JSONL recovery reproducer | passed after correction |
| Benchmark contract gate | passed, 302 tests |
| Unit Test Shard 5 | passed, 853 tests |
| Unit Test Shard 2 | passed, 998 tests |
| Activated provider ledger proof | passed against production graph path |
| Graph observation/activation gate | 114 aggregate tests passed before interruption; all six reported failures pass in focused reruns |
| Package smoke bootstrap tests | passed on Python 3.11, 19 tests |
| Registry publication parity and rejection vectors | passed, 181 entries / 1,269 roles / 58 vectors |
| Package smoke installed proof | passed for source `25b1d22b`; five mutation families rejected |
| PR 120 required checks | pending correction push |

## Next Action

Commit and push the refreshed candidate manifest, then verify every PR 120 check on the executed GitHub revision.
