# Pinned Verification Feasibility

- Work type: design
- Delivery fidelity: Level 2 experiment for the Level 3 capacity gate
- Baseline: `a5f2e623`, `codex/durable-delivery-implementation`
- Related: [reference capacity debugging](../reference-capacity-debugging/debugging.plan.md)
- Status: the single-overlap and sustained-publication experiments are complete. Named-generation manifest reuse is implemented. Production pinning design and release qualification remain open.

## Objective And Scope

Measure how long a prewarmed managed command waits when a separate service acquires a held-out exact qualification tuple. Compare the normal production acquisition with a test-only pinned acquisition on independent copies of both retained v8 fixtures. Preserve v7 default, schemas, production release authority, recovery, and release budgets.

## Contract And Feasibility

Pin a read-only SQLite WAL view under the publication fence and establish its snapshot by reading the exact signed publication row. Capture the operational control state, finalized tuple, journal tip, signer fingerprint and participant file identities. A separate, autocommit observer detects same-head SQLite commits with its own connection-local cookie. Take its identity and version before pinning. Under the release fence, reread the authority and live row, compare the same observer's cookie, and require exact equality before returning the snapshot. Underlying participant locks follow the existing publication-fence then partition order. Pinning and revalidation perform metadata checks. Existing exact raw, catalog and replay verification runs outside both advisory locks on the pinned view.

A stale attempt drops its WAL pins and retries within a three-attempt limit. An exact-current verification failure or exhausted attempts refuses release. The synthetic prototype returns a snapshot at acquisition only. Production adoption would require cache transfer on the receiving connection, normal managed command/read integration, existing recovery and quarantine policy, erasure coordination, bounded pin lifetime and WAL growth, and an explicit policy for repeated competing publications. Releasing an old tuple to avoid retries would violate the current contract.

Compare real managed writer wall time, exclusive fence wait/hold, acquisition wall time, stale work, and release outcome. Start the writer at the reader's full verification entry and wait there until the writer reaches its first exclusive-lock attempt in both arms. Let the pinned reader wait outside both locks before its first revalidation until the writer returns, so the experiment deterministically exercises one stale attempt. Account for that wait separately. Require a committed writer and a distinct new signed head. The prototype must discard its stale pin and acquire the writer's tuple. The production baseline may verify the previous head because it linearizes acquisition before the writer. These are controlled overlap diagnostics.

## Verification And Limits

The verifier uses the installed post-race-fix wheel from `73b4265a` and the existing manifest and replay implementation. Both arms use that same wheel SHA-256 `b83e6eddb44779cf2c85f1d7479df0e5cdac6d613a1c165510047ea17c2efe86`. The standalone driver verifies its installed inventory and compares the retained fixture's signed head to the original `8e570195` qualification report. The probe runs one managed writer from the unchanged qualification driver. Prewarm the writer on each fresh copy and create its ordinary command grant outside the timed interval. Use independent copies per arm and reverse arm order between the two distributions. Report individual observations. Both retained fixtures run on the native Mac.

The small signed-fixture tests cover equality with normal clean acquisition, preserved-head SQL mutation between verification and release, three consecutive competing signed publications, and cached signer disagreement. The independent reviewer confirmed the snapshot and observer separation. The final guard compares the cached verifier fingerprint with a fresh key owner and compares the same unpinned observer cookie across acquisition and revalidation. The preliminary harness rejected a run when it required the writer to return before the first scan completed. The final gate only requires arrival during verification and a committed distinct tuple before revalidation, and reports the additional coordination time.

## Snapshot-Only Writer Warmup

The writer called normal `acquire_verified_snapshot()` before timing. The named-generation partition guard can verify its tuple without supplying the cookie that seeds the write-side manifest accumulator. Each measured writer still made one full rebuild. Moving the reader's scan off the fence removed the writer's seconds of lock wait. The writer's own full scan wall time increased when the two scans overlapped and remained inside its publication fence. No consistent end-to-end writer gain is established by this condition.

| Exact fixture | Reader total baseline / pinned | Reader fence hold baseline / pinned | Writer lock wait baseline / pinned | Writer total baseline / pinned |
| --- | ---: | ---: | ---: | ---: |
| Balanced | 8.73 / 23.03 s | 8.73 s / 8.01 ms | 8.72 s / 0.185 ms | 15.59 / 14.06 s |
| Concentrated | 5.98 / 25.93 s | 5.98 s / 7.52 ms | 5.98 s / 0.166 ms | 11.13 / 16.78 s |

Each pinned trial discarded one stale scan and verified the writer's new signed head. The [signer-checked samples](snapshot-warmup.jsonl) used probe SHA-256 `eec98ec772196a1f1f5b3bfa45f25b777f1ab19a983d5ef7faa94aba6cb4ef10`. The [earlier comparison](snapshot-warmup-initial.jsonl) showed the same fence and retry pattern before the cached-signer guard was added and used probe SHA-256 `cba8e88d3d6e063cdd30445634b36e1f948a836a29faa77511eaa40650b7ac10`. These trials do not distinguish I/O pressure from CPU or other overlapping work.

## Verified Writer Manifest Warmup

Before timing, both arms populated the writer's manifest accumulator through the existing write-side exact verification and confirmed the signed fixture head was unchanged. Neither writer rebuilt its manifest during the timed command. The writer returned while the pinned reader was still in its first scan, about 6.25 s before scan completion for balanced and 6.20 s for concentrated. Each pinned reader discarded one stale scan and verified the new head.

| Exact fixture | Reader total baseline / pinned | Reader fence hold baseline / pinned | Writer lock wait baseline / pinned | Writer total baseline / pinned |
| --- | ---: | ---: | ---: | ---: |
| Balanced | 6.27 / 14.03 s | 6.27 s / 9.53 ms | 6.27 s / 0.200 ms | 6.29 s / 63.6 ms |
| Concentrated | 6.13 / 14.17 s | 6.13 s / 11.12 ms | 6.13 s / 0.170 ms | 6.15 s / 52.4 ms |

The [manifest-warmed samples](primed-writer-overlap.jsonl) used probe SHA-256 `d7b5209330101073c501c6ff8ed2e43bb33f84c5ada989354cc483c029c3a14d`. All four probe tests passed with warnings treated as errors against the installed wheel. This is one controlled pair per distribution with a deliberately primed writer, so the result establishes that the reader no longer blocks that writer through a full verification. Measuring steady-state progress, retries under sustained publication, WAL growth, and cold-start improvement requires production integration and further runs. The Level 3 qualification remains open.

## Manifest Reuse And Sustained Publication

- `MANIFEST-REUSE`: ordinary acquisition of a named generation retains the manifest forest only after the existing exact materialization and replay verifier confirms the signed state and the same managed connection's verification cookie. The following write reuses the base only with a matching cookie and manifest digest. A same-head external data change must force exact verification and refuse write custody.
- `SUSTAINED-PROGRESS`: compare ordinary and pinned reader acquisition against the same verified manifest reuse candidate. Use both retained fixture heads and offer 40 real managed commands to a single writer, one every 500 ms starting when the reader enters its first exact scan. Measure queue delay, command completion, fence custody, scan count, bounded reader retries and WAL bytes sampled at command completion. A denied reader must consume at most three attempts and acquire the final signed tuple in a separately timed quiet retry.

The candidate reuses the existing connection-local cache on the guarded named-generation path. The previously verified publication digest is still scoped by the same SQLite cookie. There are no new durable identifiers, format changes, cache transfer, or new production pinning path. The named-generation guard now keeps the exact accumulator on handles that acquire without writing. This increases their retained memory and calls for process-level memory measurement before Level 3 approval.

The [sustained-publication measurements](sustained-publication.jsonl) used the same installed candidate wheel for both arms, SHA-256 `97ca205ebd9623cb8489f899093a3701e8f82a0c7ddfeb44a5c36ff70f851550`, and probe SHA-256 `ae36a355e2d36c0fad3914fb571298e00035709a042ff01c2b32c82614294236`. Both workload distributions started on their exact retained signed qualification heads on the native Mac. Writer setup used ordinary acquisition and verified its existing cache without a separate priming scan. In every arm all 40 distinct managed writes succeeded, advanced the signed ordinal by 40, and required zero writer manifest rebuilds. Pinned revalidation ran without the artificial wait for the writer used in the single-overlap experiment.

| Fixture | Reader | First write from offer | Writes finished before reader returned | Reader outcome and elapsed | Largest sampled WAL |
| --- | --- | ---: | ---: | --- | ---: |
| Balanced | Ordinary | 5.21 s | 0 | Verified in 5.19 s | 4,190,072 bytes |
| Balanced | Pinned | 43.6 ms | 28 | Three stale scans, exhausted in 13.95 s | 4,882,232 bytes |
| Concentrated | Ordinary | 4.67 s | 0 | Verified in 4.65 s | 4,140,632 bytes |
| Concentrated | Pinned | 39.6 ms | 29 | Three stale scans, exhausted in 14.44 s | 5,084,112 bytes |

The largest individual writer fence wait fell from 5.19 s to 0.218 ms on balanced and from 4.65 s to 0.223 ms on concentrated. The two pinned readers released no snapshot when their attempts exhausted. After the writer finished, new acquisitions verified the final signed head in 4.60 s and 5.05 s, respectively. These are one paired observation per distribution under a finite write burst. WAL samples are taken at command completion. The experiment does not establish a WAL growth limit, process memory cost, tail latency, or a cold-start qualification result.

The release-path regression in [generation selection](../../../memorii/tests/integration/test_partition_generation_selection.py) fails on the installed baseline because the following publication rebuilds a verified manifest. It passes on the candidate and shows that an external same-head edit still blocks publication without changing signed authority or creating a pending intent. The candidate wheel passed 57 of 58 focused tests with warnings treated as errors, including all four pin tests. The failing `test_third_state_intent_quarantines_and_blocks_publication` raises the same integrity error during recovery on both the baseline and candidate wheels. Ruff and whitespace checks passed.

## Next Action

Test a single optimistic attempt with a fallback to existing fenced acquisition after a stale pin, and measure the resulting reader completion and writer pause under the same sustained load.
