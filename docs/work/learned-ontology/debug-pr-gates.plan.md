# Learned Ontology Pull Request Gate Debugging

- Work ID: `learned-ontology-pr-gate-debug` (planning coordinate only)
- Work type: debugging
- Delivery fidelity: Level 2 for product behavior and the exact required pull-request gates; Level-3 release certification remains outside this operation
- Status: active
- Coordinator: `/root`
- Created: 2026-09-28
- Last updated: 2026-09-28
- Parent WorkPlan: `docs/work/learned-ontology/implementation.plan.md` (Level-2 implementation complete; this operation repairs its failing PR gates)
- Related WorkPlans: `docs/work/learned-ontology/milestones/learning-activation-replay.plan.md`
- Canonical inputs: PR `https://github.com/nrag/Memorii/pull/123`, Actions run `36437600316`, head `3dd6be8d`
- Expected outputs: green scope-required PR gates on the corrected pushed revision, focused regressions for confirmed defects, and an exact revision-bound closure record

## Objective

Make every scope-required PR gate for the learned-ontology branch pass without weakening type checks, test selection, package contents, architecture boundaries, transaction invariants, or acceptance behavior. Preserve the unrelated user-owned modification to `docs/design/hermes_conversation_memory_trial.md` and exclude it from every commit.

## Expected And Observed Behavior

Expected: the branch installs as a wheel, passes Pyright/Ruff/identity checks, owns all collected tests in the required shard plans, preserves architecture import boundaries, and passes unit, Hermes, semantic-ingestion, projection, benchmark and graph-transaction jobs.

Observed on run `36437600316`: Static Analysis reports 110 Pyright errors. Benchmark Contract Tests report an unowned dynamic resource import and cross-module private imports. Package Smoke cannot load the default-catalog acceptance corpus from the built package. Semantic Projection History has a stale exact collection count. Unit shards report missing packaged corpus plus record-count, lease/retry, Hermes schema/context and scenario-ingress failures. Four independent-process graph-transaction jobs fail after a shared batch element does not reach group CAS. Aggregate jobs fail or skip downstream. This is a mixed implementation, packaging, test-governance and verification failure, not one presumed product defect.

## Changed Surface And Ownership

No fix is accepted yet. Candidate owners include package data configuration/resources, typed learned-catalog unions and adapter protocols, architecture ownership declarations, shard/count manifests, catalog-control-aware test assertions, lease/retry behavior, Hermes schema/context validation and graph transaction setup. Exactly one writer will own overlapping fixes after the causal families are confirmed.

## Hypotheses

1. New learned catalog variants entered existing broad unions without explicit narrowing, and private runtime placeholders remained typed as `object`; this explains the Pyright family while runtime behavior can still pass focused tests.
2. The new acceptance corpus exists in the source tree but is absent from package-data configuration; editable local tests pass while wheel and CI working-directory tests fail.
3. New resource loading and shared helper imports crossed architecture rules without declaring a canonical public owner; benchmark architecture tests therefore fail independently of product semantics.
4. Added tests changed exact collection and shard inventories; count gates fail even when the tests themselves are correct.
5. Fresh seed/catalog-control records and installed Preference/learning tools changed old exact-count/schema assumptions; some unit failures are stale assertions, while lease and graph-CAS failures may be real regressions and require separate discrimination.

## Experiments And Evidence

- GitHub check inventory captured with `gh pr checks 123 --repo nrag/Memorii` at head `3dd6be8d`.
- Downloaded Static Analysis, Benchmark Contract Tests, Package Smoke, Unit Shard 1, direct graph-transaction and Semantic Projection History logs from Actions run `36437600316`.
- Static log confirms the exact CI Pyright command and 110 diagnostics across learned catalog unions, proposal narrowing, provider recovery optionals, evaluation bundle protocols and Hermes factory/runtime types.
- Benchmark log confirms `test_dynamic_import_capabilities_have_explicit_owners` and `test_source_does_not_import_cross_module_private_symbols` failures.
- Unit log confirms the package-resource `FileNotFoundError` and several independent runtime/assertion families; no single assertion is yet treated as the root cause of all failures.
- Local remediation: the projection-history collection is now exactly 90 tests, and its workflow assertion and static workflow test are aligned. The focused architecture benchmark checks pass after catalog resource parsing became a public owner, dynamic package capabilities received explicit owners, and completed-turn consumers no longer import private symbols.
- Focused proof at the current dirty revision: `python -m pytest tests/unit/core/benchmark/test_memory_evolution_architecture.py::test_dynamic_import_capabilities_have_explicit_owners tests/unit/core/benchmark/test_memory_evolution_architecture.py::test_source_does_not_import_cross_module_private_symbols tests/unit/tools/test_static_tooling_config.py::test_projection_history_job_is_exact_and_disjoint_from_broad_unit_shards -p no:cacheprovider -q` passed (3 tests). The exact collection command reported `90 tests collected`.
- Whole-package Pyright now passes with `0 errors, 0 warnings, 0 informations` after explicit catalog-union, proposal, recovery, scoped-read and Hermes boundary narrowing. No type rule was weakened and no ignore or broad cast was added.
- The prompt schema now matches all 31 runtime `EntityType` values; project-assertions fingerprints and manifest were rederived after publishing their response models; default-catalog corpus tests resolve repository paths independently of the workflow working directory. The focused prompt/profile/corpus group passed (19 tests), and exact unit-owner collection passed.
- Refreshed `docs/work/semantic_ingestion/observation-ledger/release-preparation/candidate.json` only for admitted changed sources and updated `candidate.sha256` to `6f2383d31df88bcce16e79b6992ccc0a1bd0692fa1e4907617ba82a23bee6f7e`. The installed release-preparation proof remains pending this static-repair candidate.

## Verification Matrix

Run the exact failed workflow command for each confirmed family first, followed by its aggregate dependency. At minimum: whole-package Pyright; architecture benchmark module; wheel/package smoke; unit-shard verification plus affected nodes; semantic projection exact collection and test command; each affected graph-transaction matrix root; Hermes installed-image and Level-2 product commands; semantic-ingestion and benchmark aggregates. After pushing, verify the actual PR event, executed SHA/ref and every required check URL.

## Next Action

Commit and push the verified static/authority repair slice, then reproduce and repair the shared runtime failures beginning with terminal lease handoff and normal structured-claim commit/recall.
