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
- Canonical inputs: PR `https://github.com/nrag/Memorii/pull/123`, active Actions run `36458247040`, pushed head `a2a3c0ed`
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
- Pushed static/authority repair commit `f1137c59`. Its PR run reduced the remaining failures to runtime recovery, stale generated package/candidate bytes, catalog selection, Hermes prefetch, and outdated test expectations; whole Pyright and the architecture gates remained green.
- Confirmed lost-ack root cause: startup recovery renewed a live bootstrap lease and changed the execution identity before the graph transaction used the retained authority. Recovery now preserves a still-current lease identity and only reclaims after verified expiry. The exact independent JSONL `source_progress_related_conflict-direct` node passes (`1 passed in 137.32s`).
- Confirmed graph-race fixture root cause: the CAS probe required an `authorization` keyword and rejected the newly reachable ordinary coverage-observation write before either worker reached graph CAS. The fixture now accepts absent optional authorization while forwarding supplied authority unchanged.
- Confirmed catalog root causes: the reports-to manifest/root was stale after package-byte changes; it was regenerated. Catalog lookup eagerly verified an unrelated legacy release and the selected authority repository ignored the writer's configured package locator. Lookup is lazy and selected-authority verification now uses the same verified locator as the semantic writer. The catalog module passes (`28 passed`) and the captured reports-to child scenario passes (`1 passed in 65.81s`).
- Confirmed Hermes prefetch root cause: ordinary scoped memory rows were suppressed when no optional structured-fact read grant existed. Prefetch now provisions an empty structured-authority tuple for ordinary rows while structured claim reads still require their grant. The exact rejected-candidate/later-valid-turn product case and focused ordinary-prefetch regression pass.
- Confirmed lifecycle coexistence defect: the native lifecycle reader treated every valid noncommitting graph primary as corrupt because it required a schema-2 committed result before determining whether the primary could contain an accepted lifecycle effect. It now verifies the closed request/reload/result joins for every primary, ignores verified noncommitting results, and continues to require schema 2 for committed lifecycle authority.
- Confirmed scenario identity defect: multiple normalized proposals could retain proposal-specific partition rows for the same stable mention digest, then feed duplicate mention digests into a source-local identity cluster. Clustering now deduplicates only by stable mention digest while retaining the full partition evidence. The exact public scenario runner passes (`1 passed in 147.70s`).
- Final local gate evidence at the dirty candidate: whole Pyright reports `0 errors, 0 warnings, 0 informations`; whole Ruff and `git diff --check` pass; bootstrap source admission passes (`28 passed`); package-smoke bootstrap/release-tool tests pass (`19 passed`); catalog pin and coverage observer tests pass (`17 passed`); the corruption/recovery race passes (`1 passed in 195.70s`).
- Refreshed the 1,909-member observation-ledger release-preparation candidate after the final source and publication-evidence changes. Every member digest and the sidecar verify locally; candidate SHA-256 is `d0071aea5662f13650333ca18a60ee619d93306a5118ef1cc7357dfe78cef69b`.
- PR run `36457503282` exposed one Package Smoke failure after the wheel installed successfully: the installed publication verified to the current digest, but `independent-positive-parity.json` still pinned the predecessor publication digest after `project_assertions.py` changed in `f1137c59`. Reproduced the publication with both compilers, refreshed the independent output/parity and vector manifests, and passed all 58 registry vectors with 181 entries and 1,269 roles. The refreshed pin now equals the packaged publication digest `9164dff33af04f68472a447f8158fd1476ddbfab501a1500f81d432ff4c0c453` and registry digest `722acb5858a6eaed37ac55a92d7efadb369ab8c906b1070ba1d9e54ec3a86f08`.
- Pushed refreshed publication evidence as `a2a3c0ed`; Package Smoke and Static Analysis pass on replacement run `36458247040`. The superseded queued run `36457503282` was cancelled so the current revision could acquire the workflow concurrency slot.
- Unit Test Shard 4 on run `36458247040` found two stale assertions in `test_semantic_provider_composition.py`: its rotated-catalog fake omitted the selected-bundle resolver required by the exercised interface, and its second failed activation compared against the snapshot before the intentionally persisted reference-integrity ledger. The fake now supplies the complete bundle surface and the no-write assertion uses the post-bootstrap snapshot. Both exact failed tests pass locally (`2 passed in 35.61s`).
- Hermes Installed Image Lifecycle on run `36458247040` reached the reopened valid-memory recall but exceeded Hermes MemoryManager's eight-second provider timeout. A stage-timed local reproduction measured the reopened prefetch at `29.240s`; profiling localized the cost to repeated native-group primary decoding and registered-artifact re-emission inside `verify_legacy_bootstrap_v3_runtime_projection`.
- The verifier now decodes each native primary once per legacy-projection verification, carries that verified request/reload pair into the native-entry verifier, and validates the persisted artifact's embedded publication binding after the same protected integrity/materialization path instead of emitting the large artifact again. The immutable-primary codec retains its exact byte-closure check while reusing the strict decoder's canonical-byte proof inside the bounded operation-local verification scope. Reopened recall is `6.131s`, down from `29.240s` and below the Hermes eight-second boundary.
- Focused post-fix evidence: whole-package Pyright reports `0 errors, 0 warnings, 0 informations`; Ruff and `git diff --check` pass; the two Shard 4 nodes pass (`2 passed in 36.19s`); corrupt immutable-primary denial plus the intact sibling path pass (`2 passed in 159.42s`); and the exact Docker installed-image lifecycle passes (`1 passed in 520.16s`).

## Verification Matrix

Run the exact failed workflow command for each confirmed family first, followed by its aggregate dependency. At minimum: whole-package Pyright; architecture benchmark module; wheel/package smoke; unit-shard verification plus affected nodes; semantic projection exact collection and test command; each affected graph-transaction matrix root; Hermes installed-image and Level-2 product commands; semantic-ingestion and benchmark aggregates. After pushing, verify the actual PR event, executed SHA/ref and every required check URL.

## Next Action

Commit and push the verified corrections without the user-owned Hermes design edit, then monitor every PR check on the replacement revision.
