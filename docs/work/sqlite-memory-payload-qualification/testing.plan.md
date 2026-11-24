# Staged Raw Payload Capacity Recheck

- Work type: testing
- Delivery fidelity: Level 3 release target, with diagnostic evidence on a shared Linux guest
- Status: active
- Baseline: `d0aa290b` on `codex/durable-delivery-implementation`
- Product wheel: `410556bf`
- Parent: [durable delivery](../durable-delivery-implementation/implementation.plan.md)
- Related: [owner-staged implementation](../sqlite-memory-payload-implementation/implementation.plan.md)

## Scope And Completion

Check the same owner-upgraded v8 generation with and without an authenticated generation-local replay checkpoint. Publish one real execution root timestamp update at the checkpoint boundary and exactly 1,000 individual signed updates from the existing task roots for the full tail. Independently verify genesis parity, schema and generation identity, and unchanged memory, semantic, and ontology heads. Measure complete acquisition and attribute raw payload verification, manifest work, and history replay.

Invoke actual owner backup in read-only mode and measure the exclusive publication fence, its online SQLite control and partition copies, and residual fence work. Record the complete operation separately and verify each resulting signed archive. This operation completes when both measurements and their limits are recorded for the pinned installed wheel. Keep v7 as the default. Open release acceptance is owned by the parent plan.

| Contract | Canonical path and proof | Failure signal |
| --- | --- | --- |
| Owner-staged v8 | Exact audited v7 tuple, real backup, restore attestation, reviewed preview and staged upgrade | Source or selected tuple mismatch or operator refuses |
| Signed checkpoint and tail | Runtime publication owner and independently verified genesis over the same updated snapshot | Wrong generation, wrong schema, missing history, wrong tail shape or shifted memory authority |
| Complete acquisition | Three fresh processes per replay mode over one full staged fixture, with shipped owners timed around execution | Failed acquisition, wrong tuple, or a sample over the five-second release budget |
| Actual backup startup barrier | Three actual signed archives in the full trial, with backup's two calls to the production SQLite copy and the actual fence timer | An invalid archive, a wrong publication, or a pause over five seconds |

The full concentrated workload begins from the existing 1 GiB fixture and includes the upgrade hold and 1,001 checkpoint or tail mutations. The inherited 100,000-event fixture and v7 baselines remain unchanged. New wrapper code delegates to the production methods with no format or operational semantics changes. The already passing operator interruption, compatibility, authorization and tamper suites remain the proof for those classes. The small one-sample Linux run validates the harness before full timing. Its filesystem may share I/O with staging. The full run uses fresh processes but uncontrolled caches. Native Linux and macOS under approved runner conditions, both distributions, and the full acceptance series are still required.

## Progress

The staged smoke fixture converted through the installed owner workflow. An independent local checkpoint probe exercised the same public writer and replay verifier. The backup profiler's isolated smoke verified signed archives and the split between control copy, partition copy and residual fence time.

## Next Action

Complete the full Linux fixture and run the paired checkpoint acquisition series and backup fence profiles.
