# Reference Capacity Startup And Contention

- Work type: debugging
- Delivery fidelity: Level 3 release target, with focused causal evidence first
- Status: active
- Baseline: `f414e8fc` on `codex/durable-delivery-implementation`
- Related: [native qualification](../reference-capacity-qualification/testing.plan.md)

## Objective And Completion Contract

Explain the full startup budget miss and the publication lock waits and recovery errors seen under contention. Bind diagnostic evidence to the qualification wheel, signed fixture, and exact runtime paths. Demonstrate the trigger and propagation for any corrected behavior with a deterministic before-and-after test. Preserve v7 default, owner-staged v8, exact digest checks, transaction and recovery authority, and all qualification thresholds.

## Scope And Observations

Startup exceeded five seconds in all four qualification cells. Linux concentrated and macOS balanced reported five combined pending-publication recovery errors while capturing sources with one background writer. Use the retained native Mac v8 fixtures and the installed `8e570195` wheel for startup. Use isolated copies for timing and a small, controlled fixture for the contention reproducer. Dedicated Linux hardware was deprovisioned after the original reports. This investigation does not certify a new release candidate.

## Hypotheses And Experiments

| Hypothesis | Discriminating evidence | Status |
| --- | --- | --- |
| The exact qualification fixture spends most startup time on raw BLOB verification | Measure nested raw verification, complete manifest rebuild, and replay in fresh installed processes | Supported as the largest component |
| SQLite layout contributes to the startup miss | Compact an isolated copy and require the same signed tuple. Compare fresh processes with zero main-file page residency. | Supported. Compaction alone still misses the gate. |
| Cross-handle publication invalidates cached manifests and forces full verification while the exclusive fence is held | Trace fence wait and hold time, verification counts and publication revisions through real managed owners | Confirmed in the isolated probe |
| A managed read with only the partition lock reaches the generation guard while a live publisher has a signed intent | Pause both signed publishers at durable boundaries and compare to guarded reads from source capture | Confirmed at both post-data cuts |

## Constraints And Delegation

Run a bounded set of startup profiles and deterministic contention comparisons. The coordinator owns installed profiling, evidence reconciliation and publication. One writer owns any confirmed source-capture fix. A separate reader traces lock hold and wait causes. Do not weaken fail-closed behavior, run native diagnostics in parallel on the same SSD, or promote diagnostic timings to qualification.

## Startup Profile

The installed wheel matched the qualification artifact inventory and SHA-256 `db4fc4db38c6ace39dbbfdc27bbf5ae6621f04386bf587214abc1d33d48cda8e`. The retained fixtures passed acquisition with their original signed tuple digests. Two fresh subprocess and copy pairs per distribution reproduced startup in 9.06-9.91 s. Raw verification accounted for 4.47-4.67 s within a 7.13-7.96 s manifest build. The remaining manifest work took about 2.51-3.29 s and verified checkpoint replay took 1.78-1.97 s. See [qualification-procedure samples](qualification-copy.jsonl).

The [layout probe](profile_retained_acquisition.py) alternated original and compacted copies of the same balanced fixture. It reused `checkpoint_capacity.py` and `native_cold_acquisition.py` from their sibling WorkPlans. Install the frozen wheel, put the standalone qualification driver and those sibling directories on `PYTHONPATH`, and supply the retained installation, qualification measurement JSON, exact wheel, and scratch directory. All four copies started with zero resident main-database pages and verified the same signed tuple. Compaction reduced acquisition from 9.51-11.78 s to 8.18-8.27 s with a file size change under 0.2%. The largest raw cost was the residual ordered body read and digest pass. Darwin advice took 0.82-0.87 s in each trial. Layout contributes and compaction alone cannot reach five seconds. See [cold layout samples](layout-comparison.jsonl).

## Contention Findings

The installed-wheel probe used two separate service handles, a staged v8 fixture with two sources and 29 verified runtime events, and nine calls per series including warmup. Sequential commands took four publication fences per call and one full rebuild across nine calls. The contended command series had 18 fenced foreground rebuilds and 19 fenced background rebuilds. It accumulated 772 ms of foreground lock wait on this small fixture. Each signed external commit advances the publication identity and SQLite `data_version`. The other handle's cache no longer proves the current state, so current guarded callers verify the full state while holding the exclusive fence. This is a demonstrated amplification mechanism. The probe does not attribute every second in the native timing reports. See [fence and rebuild observations](managed-contention.jsonl).

Two captured failure traces start during managed source admission's writer binding and prepared-coordinate lookups. These acquire the shared partition lock and can enter after the other handle committed the data transaction and released its partition lock, while signed control publication is still pending. The generation guard correctly rejects an intermediate view. The live publisher exposed that view too early. A probe also observed the finalized-tuple mismatch variant under the same contention. See [source error traces](managed-source-race.jsonl).

## Next Action

Verify the publication-lock correction across both ordinary writers and the affected live and crash cuts, then publish the regression evidence.
