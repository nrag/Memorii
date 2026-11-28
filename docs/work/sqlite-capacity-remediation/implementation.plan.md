# SQLite Backup And Acquisition Capacity Remediation

- Work type: implementation
- Delivery fidelity: Level 3 release target with installed Linux diagnostics
- Status: complete for implementation, failure testing and the requested installed diagnostics. Acquisition qualification remains open.
- Baseline: `c3afc196` on `codex/durable-delivery-implementation`
- Parent: [durable delivery](../durable-delivery-implementation/implementation.plan.md)
- Evidence: [checkpoint and backup recheck](../sqlite-memory-payload-qualification/testing.plan.md)

## Scope

Pin both WAL participants under the existing verified publication fence. Bind the pinned control state and journal tip to the selected signed partition. Copy from the same handles after releasing the fence. Verify the copied pair using the existing backup checks before publishing the encrypted archive. Keep authority and destructive storage changes fenced. Preserve v7 defaults, existing backup manifests, archive readers, signed roots, checkpoints and release checks.

Optimize full v8 acquisition while preserving exact BLOB hashing, typed catalog digests, reference and index closure, and runtime checkpoint and tail verification. Run the repaired installed wheel on the retained synthetic 1 GiB concentrated fixture with the generation-local v8 checkpoint and 1,000 signed tail events.

| Milestone | Proof owed |
| --- | --- |
| Backup fence and failure paths | A coherent old pair survives a permitted signed advance outside the fence. A failed pin or copy cleans up and emits no archive. Scope changes cannot release an archive under stale authority. Whole-partition erasure excludes outstanding plaintext backup leases. |
| Acquisition verification | Signed v7/v8 roots and replay parity remain exact. Corrupt bodies, indexes and reference state still reject. Measure complete acquisition and component timings on the installed candidate. |
| Full installed diagnostic | Record all attempted samples and verified backup archives against the same signed checkpointed fixture. Report both five-second budgets using three fresh-process samples. Native qualification still belongs to the release plan. |

The backup writer owns production backup and necessary owner erasure coordination. A separate test writer owns focused backup integration regressions. The acquisition writer owns repository verification internals. The coordinator owns baseline profiling, release timing, integration and evidence.

## Candidate

The restarted guest's baseline acquisitions on the retained checkpointed tuple were 11.592, 7.096, and 6.086 seconds, with uncontrolled caches. Profiling observed 478,870 manifest rows and separated raw BLOB reads and hashing from compact catalog framing and tree construction. Commit `241d3f13` uses same-transaction SQLite reads and two bounded SHA workers, with bounded chunk streaming outside the worker size range. It reduces Python allocations and hash calls in the compact manifest and keeps the original checkpoint member serialization and exact replay comparisons. Independent tests verify original digest framing and both queued and large streamed BLOB corruption paths. The provisional raw-only overlay took 4.517 seconds median and 4.614 seconds maximum for three fresh-process samples.

Commit `c9e6ab50` pins checked WAL views under the first publication fence and copies with a deadline from those handles. A second short fence excludes stale authority before archive publication. Whole-partition erasure serializes through the backup lifetime lock and owns any interrupted plaintext scratch. Regression coverage includes concurrent same-generation publication on v7 and v8, missing and mismatched pins, both copy failures, deadline expiry, a real generation switch, forget, and live and orphaned plaintext during erasure. The full timing driver checks that both SQLite copies execute outside either measured hold.

The first installed combined candidate measured 4.944 seconds median acquisition and 5.069 seconds maximum. Commit `e54f8ec0` then removed the SQLite row-wrapper and additional per-node allocation overhead. Its Linux test run exposed erasure racing with a closing SQLite connection removing a sidecar. Commit `5af58275` accepts only an already-missing entry during tree deletion and keeps all other errors visible. Its installed Linux wheel passed all 104 selected warning-as-error tests, including the deterministic sidecar-removal regression.

## Installed Full-Scale Results

Exact candidate `5af58275` installed wheel SHA-256 `15cefaf62102a7b5343c6cdca2aae8548a97fa7d01680f44ca3736cf0259c2ca`. The three-sample runs used Linux arm64, Python 3.12.16, and SQLite 3.40.1 in the same shared Colima environment as the preceding trial. Each operation used a fresh process on the same unchanged signed v8 generation, with the signed checkpoint and 1,000-event tail. The backup timer starts from a verified tuple, as in the prior test. Cache state was uncontrolled.

| Operation | Median | Maximum |
| --- | ---: | ---: |
| Complete acquisition | 5.017 s | 6.377 s |
| Materialization manifest rebuild | 3.465 s | 4.529 s |
| Raw payload verification within manifest | 1.831 s | 2.791 s |
| Checkpoint and tail replay | 1.529 s | 1.827 s |
| Backup pause across both exclusive holds | 2.836 ms | 3.187 ms |
| SQLite partition copy outside the fence | 6.845 s | 7.544 s |
| Complete backup creation | 24.726 s | 26.379 s |

Each backup produced a separately verified signed archive. The installed driver asserted neither SQLite copy could run inside either fence. Compared with the preceding 6.757-second backup pause, the fence is now comfortably inside the diagnostic budget. Complete acquisition improved from the preceding 6.664-second median, while two of the three candidate samples exceeded five seconds. Raw payload verification ranged from 1.285 to 2.791 seconds, the largest measured moving component. The complete backup operation still includes copying, encryption, and staged verification outside the fence.

The one additional fresh-process acquisition after restarting the isolated guest took 8.576 seconds, including 4.349 seconds of raw payload verification. The guest page cache was reset, while the host cache was uncontrolled. This is a supplemental diagnostic, with no sample excluded from the main run.

The [full results](linux-full-results.jsonl), [restart sample](linux-after-restart.jsonl), and [comparison runs](linux-comparison-results.jsonl) preserve the sample and wheel identities. The source fixture remains on its isolated guest volume, and the guest was stopped after measurement.

## Release Follow-Up

Keep v7 as the default. The [parent release plan](../durable-delivery-implementation/implementation.plan.md) owns acquisition follow-up and qualification on native Linux and macOS before any default activation.
