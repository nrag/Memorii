# Durable Memory Test Architecture

- Work ID: durable-memory-test-architecture
- Work type: testing
- Delivery fidelity: Level 3 (bounded to test architecture for durable-memory implementation slices; CI gate allocation grows per milestone)
- Status: active (focused placement now; broader CI allocation at each coherent milestone candidate)
- Coordinator: main Codex task
- Created: 2026-09-29
- Last updated: 2026-09-29
- Parent WorkPlan: [durable memory implementation](../durable-memory-implementation/implementation.plan.md)
- Related WorkPlans: [validation matrix](../durable-memory-implementation/validation.md) owns family definitions
- Canonical inputs: implementation plan validation/coverage packets; remediated design SHA 9f73f06ff2153439ed970f953b3679bdc4e9b60448248d2d5f5e64f947624a2d
- Expected outputs: test placement decisions, suite/gate ownership records, timing baselines as slices land

## Objective

Own test-suite placement, naming, and CI allocation for the durable-memory implementation so implementation slices add proof without weakening existing coverage or bloating fast gates.

## Completion Contract

Every new durable-memory test family lands in the correct tier with a measured runtime, behavioral names, and a recorded placement decision; existing coverage is retained; gate changes are recorded with failure signals; the parent implementation plan's coverage ledger reflects actual test ownership at each milestone candidate.

## Test Portfolio

| Requirement or contract | Behavior and canonical path | Test owner and level | Failure signal | Status |
| --- | --- | --- | --- | --- |
| MemoryPlaneStore protocol parity (DUR-16) | existing parameterized contract suite in memorii/tests/unit/core/test_memory_plane_store_contract.py gains the sqlite backend parameter | unit, parameterized (memory/jsonl/sqlite) | any existing contract assertion fails for sqlite | parameter added in storage-foundation slice |
| SQLite-specific durability/reopen (DUR-15,16) | fresh handle and fresh process read prior writes with identical revisions/records | unit (new handle) + integration subprocess (new process) | revision/record/order mismatch or corruption error | new: tests/unit/core/test_sqlite_memory_plane_store.py, tests/integration/test_partition_storage_recovery.py |
| Partition crash cuts, init/publication (DUR-02,13,15) | subprocess kill at commit cuts; init/genesis/duplicate/hostile roots | integration, slower tier (subprocess) | old-or-new invariant violation, quarantine failure | later storage-foundation sub-slices; paths inventoried here before creation |

## Equivalence And Failure Matrix

Families and signals are owned by [validation](../durable-memory-implementation/validation.md); this plan owns placement only. Current slice covers: store-contract equivalence across backends (parameterized), fresh-handle/fresh-process reopen, checksum/revision-chain corruption rejection, cross-handle visibility of a second writer, precondition/CAS siblings via the parameterized suite.

## Suite Topology And Runtime Budget

- Parameterized contract suite stays in the unit tier; the sqlite parameter must not push the suite out of its shard budget — measure before/after and record both counts.
- Subprocess/fresh-process tests go to tests/integration (existing integration tier, not fast unit shards).
- No CI workflow changes in the first slice; timing inventory and shard ownership are re-measured at the first coherent candidate and gate additions are recorded then.

## Test Asset Inventory

- New fixtures: none beyond behavioral record builders mirroring the existing `_record` helper style; no test authority enters production packages.

## Retention And Retirement Ledger

- No existing test retired; the jsonl/memory parameters are retained unchanged.

## Gate Change Log

- 2026-09-30 (LANDED): pr-gates.yml gained two enforced integration jobs — durable-storage-integration (partition recovery, provider paths, semantic owners, migration recovery; 20-min timeout) and durable-runtime-integration (runtime process recovery, resume checkpoint, sidecar/CLI; 15-min timeout) — both wired into the unit-tests aggregate needs/env/test. All seven durable-memory integration files now have CI homes. Remaining: shard timing-manifest refresh at the next regeneration.

## Progress Log

- 2026-09-29: testing WorkPlan activated before storage-foundation test creation; placement decisions recorded above. Next action: record measured timing after the slice's focused tests run.
- 2026-09-29: sub-slice 1 measured. Parameterized contract suite: 16 → 20 collected (sqlite parameter added to the 4 store-factory tests), full contract file ~3.2 s locally (within unit-shard budget; shard/timing ownership re-verified at CI candidate). New focused files: tests/unit/core/test_sqlite_memory_plane_store.py (14 tests, ~1.2 s) in the unit tier; tests/integration/test_partition_storage_recovery.py (2 subprocess tests, ~5.3 s) in the integration tier outside fast shards. No existing test retired; jsonl/memory parameters retained. One transient [memory]-parameter flake observed in a pre-existing in-memory-store thread test (3/3 green on re-run) — tracked at candidate time.
- 2026-09-29: sub-slices 2-3 measured. tests/unit/core/test_storage_administration_contract.py: 23 tests ~2.4 s. tests/unit/core/test_persistent_partition_factory.py: 8 nodes ~11 s wall (per-test < 0.1 s; import overhead). write-snapshot suite gained the sqlite parameter (11 tests × 3 = 33, ~1.7 s) closing the CAS-sibling parity action. Integration file grew to six journeys (~13 s): fresh-process reopen, cross-process CAS, dead-publisher recovery, semantic-owner conditional writes, concurrent publishers on the fence, SIGKILL mid-transaction. Remediation batch added init-crash-cut retries, third-state quarantine, tamper-refusals and per-catalog tamper cases. Full battery across seven files: 114 passed ~24 s. White-box protocol staging drives real production internals only; no test-only production hooks (verified by test_reviewer).

## Next Action

Land the CI integration-tier home for tests/integration/test_partition_storage_recovery.py (gate change recorded above) before storage-foundation packet closure.

- 2026-09-29 (semantic-ontology candidate): measured the slice's suites (13 parity ~1.4 s; 9 provider-path ~30 s; 6 semantic-owner ~8 s; coordinator file 638.8 s with the parity-bearing [completed] node at 87.3 s — heavyweight, stays in its existing shard placement). Environment record correction: local interpreter is Python 3.14.7 (the gates.md note saying 3.12.14 is stale); CI-pinned 3.11/3.12 re-runs remain a queued closure item for both packets.

- 2026-09-30 (deadlock reclassification): the recorded "wholesale tests/unit/integrations + tests/unit/tools deadlock" is NOT a deadlock and NOT caused by this branch. Reproduced single-test at the clean merge base e6880a46: test_hermes_local_authority.py::test_installed_preference_uses_existing_canonical_typed_topic passes in 231 s there, 190 s at HEAD — a pre-existing pathological cost in the canonical typed-value codec (_json pure-Python encoder: 41.5M calls, 222 s cumulative; _json_string 33.5M calls; quadratic set normalization re-encoding child subtrees per level). The parked memorii-hermes-semantic-worker thread is an idle queue worker, not a deadlock participant. A bounded lru_cache on _json_string was prototyped and measured: 190 s -> 6 s with byte-identical output — but landing it requires the semantic-ingestion observation-registry publication refresh (decoder-source-manifest 181 entries + publication-manifest digests, the 184-file signed evidence chain), which is that subsystem's own governed release operation. Reverted on this branch; the measured fix + refresh path is recorded here for the semantic-ingestion owner.
