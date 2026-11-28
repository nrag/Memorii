# Reference Capacity Startup And Contention

- Work type: debugging
- Delivery fidelity: Level 3 release target, with focused causal evidence first
- Status: source race corrected and reviewed. Full-scale startup and fence latency remain release work.
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

The [earlier diagnostic fixture](fixture-layout.jsonl) and exact concentrated qualification fixture had identical raw payload totals (20,481 bodies and 5,165,982,966 bytes). The earlier artifact's production package sources match the qualification wheel. When rerun in this investigation on zero-residency copies, the earlier fixture took 8.35-9.22 s. The old 4.89 s measurement therefore cannot be explained by a change to the installed acquisition code or raw payload volume. The layout experiment isolates a contribution in the current environment. The remaining difference across measurement sessions is unresolved. See [earlier-fixture rerun](earlier-fixture-recheck.jsonl).

## Contention Findings

The installed-wheel probe used two separate service handles, a staged v8 fixture with two sources and 29 verified runtime events, and nine calls per series including warmup. Sequential commands took four publication fences per call and one full rebuild across nine calls. The contended command series had 18 fenced foreground rebuilds and 19 fenced background rebuilds. It accumulated 772 ms of foreground lock wait on this small fixture. Each signed external commit advances the publication identity and SQLite `data_version`. The other handle's cache no longer proves the current state, so current guarded callers verify the full state while holding the exclusive fence. This is a demonstrated amplification mechanism. The probe does not attribute every second in the native timing reports. See [fence and rebuild observations](managed-contention.jsonl).

Two captured failure traces start during managed source admission's writer binding and prepared-coordinate lookups. These acquire the shared partition lock and can enter after the other handle committed the data transaction and released its partition lock, while signed control publication is still pending. The generation guard correctly rejects an intermediate view. The live publisher exposed that view too early. A probe also observed the finalized-tuple mismatch variant under the same contention. See [source error traces](managed-source-race.jsonl).

## Source-Capture Fix And Proof

Both ordinary signed publishers now retain the already-held exclusive partition advisory lock through final control-tuple and terminal-intent writes. The SQLite write transaction still ends before control finalization, and the lock order remains publication fence, partition, then control. A concurrent guarded reader waits for the live publisher. A failure after the data commit still releases the lock during unwinding and leaves durable recovery authority intact. The persisted format and v7 installation default are unchanged.

The targeted source test uses the real managed capture path and two separate handles. It deterministically pauses at prepared, data-committed, and control-committed cuts for both publisher types. On the original code, four of six cases raised the observed pending-publication error. All six pass with the fix, including fresh reopen and exact source readback. The crash regression also checks interruption after control finalization and before terminal intent. The focused regression sweep passed 97 tests, then 11 generation and process-recovery tests after adding the last crash case. Ruff and the identity gate passed. A wider ad hoc type check reports the same three diagnostics in unchanged portions of the service on the clean base and the candidate.

The independent specification, correctness, and test reviewers confirmed the live-publication mechanism and fail-closed recovery contract. Correctness review separately injected the terminal-intent interruption in both publishers of a staged v8 fixture. Reopening first denied the read and then recovered the exact candidate. The candidate slice has `remaining_validated_p1_p2: []` for this race correction. Full-scale qualification still fails at the frozen prior revision. This fix addresses transient source failures from live publication and retains mandatory exact verification.

An isolated installation of `73b4265acdcd7efadc4283384797c84a6ae0fc1d` verified against wheel SHA-256 `b83e6eddb44779cf2c85f1d7479df0e5cdac6d613a1c165510047ea17c2efe86` and passed all 100 focused tests with warnings treated as errors. The [small installed contention rerun](managed-contention-after-fix.jsonl) recorded zero source errors. It still observed 18 fenced foreground and 19 fenced background rebuilds in the contended command series. This corroborates the separate correctness and lock-amplification mechanisms. No updated release performance claim is made from the small fixture.

## Next Action

Use the [pinned verification experiment](../pinned-verification/design.plan.md) to evaluate avoiding redundant manifest rebuilds and measuring bounded progress under sustained publication. Startup still needs a separate reduction in exact payload, catalog, and replay costs.
