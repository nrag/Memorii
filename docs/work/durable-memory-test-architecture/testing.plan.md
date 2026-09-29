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

- None yet (first slice adds no workflow changes).

## Progress Log

- 2026-09-29: testing WorkPlan activated before storage-foundation test creation; placement decisions recorded above. Next action: record measured timing after the slice's focused tests run.
- 2026-09-29: sub-slice 1 measured. Parameterized contract suite: 16 → 20 collected (sqlite parameter added to the 4 store-factory tests), full contract file ~3.2 s locally (within unit-shard budget; shard/timing ownership re-verified at CI candidate). New focused files: tests/unit/core/test_sqlite_memory_plane_store.py (14 tests, ~1.2 s) in the unit tier; tests/integration/test_partition_storage_recovery.py (2 subprocess tests, ~5.3 s) in the integration tier outside fast shards. No existing test retired; jsonl/memory parameters retained. One transient [memory]-parameter flake observed in a pre-existing in-memory-store thread test (3/3 green on re-run) — tracked at candidate time.

## Next Action

Re-measure shard timing when the storage-foundation candidate freezes and record the gate-allocation decision (no new workflow expected before the init/publication sub-slice).
