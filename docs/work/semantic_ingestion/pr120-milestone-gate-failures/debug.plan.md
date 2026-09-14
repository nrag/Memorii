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
- GitHub run `34805514963` advanced to one Unit Test Shard 2 failure after 23 jobs passed. The Hermes reopen fixture coupled Atlas seeding to writer-admission absence; current production graph composition already installs that writer record, so the retrieval fixture was never created. Seeding writer authority idempotently and guarding the Atlas record by its own identity restores the intended persistent reopen proof (9 Hermes bridge tests pass under the CI source-revision environment).
- The superseded replacement run also exposed Linux sticky-ancestor handling in the separate revocation publisher. Applying the same private-descendant rule as the runtime path validator restores all eight revocation CLI cases without admitting a writable leaf or descendant.
- Accepted graph fixtures had not adopted the capability authorization checkpoint now required by the production group CAS. The scenario host now initializes a complete current status/checkpoint pair and derives its operation bindings through the production binding constructor; accepted and protected-unresolved public ingress both pass.
- The coordinator lifecycle fixture now uses an unresolved completed group for its generic success arm. Accepted effect persistence remains covered by production-shaped graph tests and no longer depends on an incomplete empty capability registry.
- A captured capability-monitor predecessor is a cutover-only manifest under the current contract. Its immutable terminal still reloads without writes through the atomic read API, while the public ingestion root now has an explicit regression proof that it fails closed before activation and invokes neither normalization nor graph execution.
- GitHub run `34808452965` reduced the remaining failures to one shared fixture defect: the production-root transaction matrices and the native group-result codec expected accepted graph effects without installing the capability status and authorization checkpoint now required by group CAS.
- One shared production-root fixture initializer now creates the writer epoch, installs the existing signed test monitoring authority, and initializes fresh active evidence. Production execution still fails closed when this authority is absent.
- The four focused conflict proofs pass across direct, factory, filesystem, and Hermes roots; the complete factory transaction-boundary shard passes all 29 scenarios; and exact Unit Test Shard 2 passes all 1,044 tests.
- Independent-process conflict first/reopen proofs pass for direct, factory, filesystem, and Hermes JSONL roots. Each first phase reaches three CAS attempts and two graph effects; each reopen reaches zero CAS attempts and reloads the same source-progress evidence without reinitializing capability authority.
- Replacement run `34811310162` passed 40 jobs and exposed one later batch element after the conflict repair: the deterministic `reused_committed` arm requested accepted materialization but still emitted an empty capability-binding set. It now uses the production selector over the same active fixture status/checkpoint.
- The focused `reused_committed` factory JSONL first/reopen pair passes with three initial graph effects and zero replay effects. The complete factory JSONL independent-process gate then passes all 29 scenarios.
- PR run `34813313355` passed 46 jobs, including every transaction-boundary job and both CodeQL jobs. Unit Shard 3 then exposed 18 accepted-effect recovery fixtures that lacked the production capability-status/checkpoint authority; GitHub cancelled the shard at its 15-minute job limit before pytest could print the assertions.
- The shared active-authority initializer now reaches the intended post-effect failure seams for every built-in recovery root. All 31 recovery cases pass, including persistent reopen and lease-reclaim variants, in 828.51 seconds locally.
- The observation-ledger gate reached 154 passes and two failures. Its unsigned-authority case had accidentally requested the fixture factory's signed default, and the public cohort boundary leaked a typed internal store error for a corrupt detached group record. The fixture now explicitly requests no verified authority, and detached-authority corruption is translated into the public non-disclosing cohort denial; both exact cases pass.
- Unit shard setup plus the corrected 13-minute recovery family cannot fit the former 15-minute whole-job limit. The gate retains the complete shard and raises only its execution ceiling to 45 minutes.
- Exact Shard 3 then exposed the same missing active-authority setup in the two accepted clarification-race fixtures. Installing the shared monitor/checkpoint fixture lets both the in-memory stale-plan race and fresh-process JSONL reopen reach their intended group CAS and pass in 242.30 seconds.
- The corrected full shard reached 874 passes and one expected skip in 1,601.17 seconds. Its only two failures were caused by the coordinator supplying an abbreviated local `MEMORII_SOURCE_REVISION`; rerunning those exact benchmark tests with the repository's full HEAD produced two passes. The GitHub workflow already supplies `${{ github.sha }}`. The shard ceiling is therefore 45 minutes, preserving every test while allowing package setup and runner variance around the measured 26-minute test body.

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
| PR 120 run `34805514963` | Superseded; exposed Shards 1, 2, and 4 fixture/path defects now corrected in focused tests |
| Revocation CLI Linux path family | passed, 8 tests |
| Coordinator lifecycle family | passed, 8 cases |
| Historical terminal reload/cutover family | passed, 3 tests |
| Scenario public ingress accepted and protected-unresolved reproducers | passed |
| Unit Test Shard 1 | passed, 723 tests |
| Unit Test Shard 4 | passed, 957 tests / 1 expected skip |
| Static Analysis | Ruff, Pyright, and identity hygiene passed |
| Package Smoke bootstrap tests | passed, 19 tests on Python 3.11 |
| Installed package preparation | passed for source `e9263d33`; 23 distributions / 6,036 files / 1,800 package files |
| Installed package rejection family | passed; all five mutations rejected before host execution |
| PR 120 run `34808452965` | 35 jobs passed; nine underlying failures plus one umbrella failure mapped to the missing active-capability fixture setup |
| Production-root conflict proof | passed across direct, factory, filesystem, and Hermes, 4 tests |
| Bootstrap Graph Transaction Boundary (memory, factory) | passed, all 29 scenarios |
| Independent JSONL conflict/reopen proof | passed for direct, factory, filesystem, and Hermes; persisted authority reloaded with zero replay CAS attempts |
| PR 120 run `34811310162` | 40 jobs passed; four JSONL matrix failures plus the umbrella failure mapped to the stale `reused_committed` binding fixture |
| Bootstrap Graph Transaction Boundary (jsonl, factory) | passed, all 29 scenarios |
| Unit Test Shard 2 after final fixture repair | passed, 1,044 tests |
| Final fixture static checks | Ruff and exact CI-form Pyright passed |
| PR 120 run `34813313355` | 46 jobs passed; Unit Shard 3 was cancelled at its 15-minute ceiling and Observation Ledger Activation reported two mapped failures |
| Post-effect recovery family | passed, all 31 cases in 828.51 seconds |
| Observation ledger reported failures | passed, two exact cases / nine unrelated cases deselected |
| Final observation/recovery static checks | Ruff and exact CI-form Pyright passed |
| Clarification accepted-race family | passed, memory and independent JSONL reopen, 2 tests |
| Unit Test Shard 3 corrected run | 874 passed / 1 expected skip; two local invocation identity errors pass with full HEAD |
| PR workflow static contract | passed, 18 tests with the explicit 45-minute complete-shard bound |

## Next Action

Commit and push the production/fixture/workflow repair, refresh the release-preparation candidate against that clean code commit, then verify every PR 120 check on the replacement revision.
