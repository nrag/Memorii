# Bootstrap V3 JSONL Reopen Stall Debug

- Work ID: bootstrap-v3-jsonl-reopen-stall-2026-08-10
- Work type: debugging
- Status: active
- Coordinator: Codex main thread
- Created: 2026-08-10
- Last updated: 2026-08-10
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/bootstrap-v3-recovery-renewal-2026-08-10/debug.plan.md`
- Canonical inputs: `memorii/core/memory_plane/store.py`; `memorii/core/provider/ingestion.py`; `memorii/tests/unit/core/semantic_ingestion/test_bootstrap_v3_recovery_reopen.py`
- Expected outputs: root-cause record, bounded fix, and deterministic fresh-handle JSONL recovery proof.

## Objective

Explain and correct the fresh-service JSONL V3 recovery test stall without weakening file locking or recovery validation.

## Expected And Observed Behavior

Expected: a second provider service backed by a new `JsonlMemoryPlaneStore` handle reloads the retained V3 Found and terminal result without analysis or terminal writes. Observed: the focused test prints collection and test start but did not return a final result in the initial 60-second observation.

## Hypothesis Ledger

| ID | Hypothesis | Discriminating experiment | Status |
| --- | --- | --- | --- |
| H1 | The second handle blocks on an unreleased JSONL file lock. | Faulthandler trace during the focused test. | unconfirmed |
| H2 | Reopening replays a growing JSONL history indefinitely. | Time construction and first `list_records` independently. | unconfirmed |
| H3 | The test is slow due to deterministic bootstrap/profile setup, not stalled. | TTY boundary trace. | supported |

## Experiments And Evidence

- E1: the in-memory public-root V3 test completed in approximately 25.5
  seconds. The JSONL TTY boundary trace reached `service1` and remained in the
  first public `sync_event` until the execution environment's approximately
  30-second command window ended. It never reached construction of the second
  handle, so it does not demonstrate a JSONL lock or replay loop.
- E2: the attempted faulthandler command did not survive long enough in this
  environment to emit its scheduled 45-second dump. This is an environment
  observation, not proof that the process is deadlocked.
- E3: a 45-second faulthandler trace located the first sync in repeated
  `JsonlMemoryPlaneStore._read_batches_unlocked` parsing during atomic terminal
  persistence. The file lock was held normally; the causal issue was repeated
  full-log validation by the same unchanged handle.
- E4: added an existing-lock-protected per-handle cache keyed by
  `(device, inode, size, mtime_ns)`. It caches only a fully validated snapshot,
  refreshes after local replace, and invalidates when another handle replaces
  the file. The cache tests and the two-service V3 JSONL restart proof pass:
  `12 passed in 49.02s`.

## Next Action

Add the atomic recovery contention, expiry/reclaim, stale claim, and consumed
nonce schedules against both memory and JSONL stores.
