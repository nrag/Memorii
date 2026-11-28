# Staged Raw Payload Capacity Recheck

- Work type: testing
- Delivery fidelity: Level 3 release target, with diagnostic evidence on a shared Linux guest
- Status: complete for the requested diagnostics. Release timing gates remain open.
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

An additional feasibility check on SQLite 3.40.1 used a disposable copy of the checkpointed smoke fixture. A normal owner backup supplied its signed watermark. Inside the existing publication fence, explicit WAL read transactions pinned both participants and read the same selected signed tuple. After releasing the fence, a real runtime publication advanced the live tuple. Copying from the original handles and running the installed staged-backup verifier recovered the original tuple and verified control journal tip as one pair. The pin subphase took 0.53 ms in this smoke. That excludes service fence entry, authority checks, and backup copying. This establishes a mechanism for a future production design. The existing operator still holds the fence during copying, and this probe does not cover generation replacement, owner and suppression rechecks, interruption, WAL retention or the full workload.

## Full Linux Acquisition

The installed wheel matched SHA-256 `8e5a68b6ff26a837c72244f35979d1608adc4d7b59da1764138f7b857bd6f65b`. The Colima guest ran Linux arm64, Python 3.12.16 and SQLite 3.40.1 with six logical CPUs, 17.5 GiB RAM and ext4 on `/dev/vdb1`. Three samples per mode executed in fresh processes after staging work finished. The seed's audited v7 tuple was `a563e7a99d7c74caac32780dad2c4f19e5816e523fa2ff80c0b72e4f3cf1d8b1`.

| Replay mode | Complete median / max | Manifest median | Raw payload verification within manifest | Runtime replay median |
| --- | ---: | ---: | ---: | ---: |
| Genesis | 12.321 / 13.566 s | 4.937 s | 2.992 s | 7.546 s |
| Selected checkpoint plus 1,000 events | 6.664 / 7.593 s | 4.885 s | 3.019 s | 1.908 s |

The checkpoint was signed for the selected v8 generation and its replay was checked against independent genesis reconstruction before the timed samples. The memory write revision remained 4,097. The checkpoint improved complete acquisition by about 46%. Each checkpoint sample still missed five seconds, and payload verification accounts for about three seconds within the manifest rebuild. The component medians describe separate distributions and need not add up to the total median.

## Full Linux Backup

All three backups used the real owner operator and the same checkpointed v8 tuple. All three signed archives passed the actual archive verifier. The median pause was 6.757 seconds, with a maximum of 7.267 seconds. All three missed five seconds. Copying the 5.41 GiB partition consumed 6.724 seconds median and at least 99.4% of the fence in each sample. The median control copy was 20 ms and other fence work was 3 ms. The complete `create_backup` call took 23.420 seconds median, including work outside the fence. Cache state and guest I/O were uncontrolled. These measurements provide backup attribution for this fixture, with native release qualification still open.

The [full results](linux-full-results.jsonl) bind each sample to the wheel, runner, checkpoint and archive. The [supporting results](linux-supporting-results.jsonl) record the production staging and the paired pinned-WAL experiment. The checkpointed synthetic full fixture remains on the isolated guest volume at `/work/v8-release-checks/full`. Both diagnostic drivers passed Ruff and scoped Pyright.

## Release Follow-Up

Keep v7 as the default. Use the manifest and replay split to target full verified acquisition, and carry the paired snapshot evidence into a separate design for copying outside the publication fence. Both paths still need integrated failure tests and the approved native runner series before default v8 activation.
