# Reference Capacity

- Parent: [durable delivery implementation](../implementation.plan.md)
- Status: proposed
- Requirements: DUR-11/14/17
- Dependencies: Generator work in parallel. Final measurement after signed delivery and restore integration.
- Closure identity: unset, record actual base, code head, dirty state and artifact/run digests before claim

## Observable Acceptance

Both approved distributions run using installed artifacts on pinned Linux and macOS runners and emit measured support evidence.

## Owners And Contract Changes

Existing test_measured_capacity_envelope.py regression, owner-approved engineering verification generator and runner, current durable/macOS CI workflows, release evidence packet.

Freeze the approved 200-task distributions, exact counts including sources and replay tail, deterministic digests, workload and dependency/environment identity. Generate and verify fixture through production owners outside timed windows. Use design sample counts, warm/cold and contended workload, quantiles and storage growth. Separate capture, warm read, startup acquisition, resume and snapshot pause.

## Verification

Two distributions on both supported OSes. Verify fixture counts and authority closure before timing. Keep the current smaller test as a regression. Retain measurements, retries/errors, artifact hashes and gate output. A missing runner is unverified evidence. Threshold failure requires remediation or an explicitly approved design change.

Existing regression anchors from memorii/ in the applicable pinned CI environment:

```bash
python -W error -m pytest tests/integration/test_measured_capacity_envelope.py -p no:cacheprovider
```

New path proof commands and exact test names must be registered through the [validation ledger](../validation.md) before implementation. Include the affected workflow job and artifact evidence. Review against the exact commit. Evidence maturity is design specified at this baseline. This packet is complete only with local and applicable enforced proof and reviewed closure. It satisfies only its bounded portion of the parent requirements.

## Scope Boundary

Use the approved design and existing semantic owners. Keep unsupported roots visibly unavailable. Record compatibility and rollout deltas at the actual candidate. Parent owns release authorization and aggregate gate outcome.

## Progress And Review

The reference input generator defines the two deterministic workload distributions and sample coordinates. Focused tests cover counts, repeatability and bounded source body generation. The existing smaller measured integration test stays a regression.

The engineering loader now prepares and audits diagnostic signed SQLite fixtures through the installed package's storage owners. It verifies the installed files against the candidate wheel before staging, then verifies graph and source closure and the signed pre-checkpoint event inventory after reopening. The isolated working-tree wheel smoke tested 2 retained sources and 19 signed runtime events. All 28 focused tests passed. Qualification mode explicitly refuses until the production native-source receipt bridge and validated checkpoint tail are available. No timed or reference-size run is claimed.

Manifest recomputation now streams rows while retaining the existing authenticated ordering and digest. This bounds Python-side catalog memory without altering stored signatures. A regression compares the streamed result to the prior materialized fold. The full fixture still requires authenticated checkpoint-tail replay, the incremental manifest needed for throughput and matched Linux/macOS measurements.

The reference fixture now uses installed native source admission, authenticated runtime observation receipts, and the selected signed checkpoint plus one-event tail batches. The measurement driver uses installed managed reads, source capture, status proposal commit, snapshot acquisition, embedded bounded resume, and backup barrier timing. A separate series measures contention and write growth. The qualification workflow requires an exact reviewed revision, the same built wheel on both platforms, hash-locked Python dependencies, and dedicated runner profiles. The small installed diagnostic establishes path and format behavior. Repository runner inventory was empty. Full-size measurements, the incremental publication manifest accumulator and release evidence remain open.

Partition format v7 uses a deterministic, hash-prioritized immutable tree for each authoritative catalog. Both signed write owners capture affected SQL keys in their transactions and anchor the prior in-memory root inside the SQLite write lock. A verified acquisition rebuilds the root from all authoritative columns and separately checks runtime history. Expected update cost is logarithmic per changed row. Formats v1–v6 retain their historical digests. Staged upgrade independently checks memory selectors before v7 signs them. The memory-plane write validator still materializes all current records independently of the manifest and requires profiling at meaningful source sizes.

Verified standalone source admission and initial Hermes capture now validate against the current writer record and exact transaction precondition rows. The existing semantic validator handles authority and record shape. The seal path uses the existing SQLite source-kind index to select semantic event batches, including full replay checks over that history. Other write shapes and custom policies continue to receive the full snapshot. A 48-source diagnostic observed zero whole-current-table reads, with exact signed observation receipts for all sources.

The 128- and 512-source Linux diagnostics cover acquisition, checkpoint resume and backup pause with verified fixtures. Database bytes grew by about 14.8 times the native source body bytes at both sizes. A separate 128-source probe attributed 97.7% of database pages to memory batches, current records and record versions. The [payload storage study](../../sqlite-memory-payload-design/design.plan.md) cut those catalog bytes by 66% with raw deduplication and preserved all three signed roots. On the full concentrated workload the sequential raw verifier checked the projected memory catalogs in 2.269 seconds median. Current v7 full acquisition was 18.674 seconds median. A separate instrumented sample attributed 20.188 of 23.511 seconds to the three memory catalogs, with approximately 3.323 seconds spent elsewhere. The integrated candidate still has to demonstrate the five-second acquisition gate and the full backup pause on both platforms.

The [owner-staged raw trial](../../sqlite-memory-payload-implementation/implementation.plan.md) exercised the actual signed upgrade and backup on the full concentrated Linux fixture. The active SQLite file dropped 64.7%. Complete acquisition measured 10.951 seconds median with genesis replay. Actual backup pause measured 5.624 seconds median. Both exceeded five seconds. The v7 default remains in place.

The [checkpoint and backup recheck](../../sqlite-memory-payload-qualification/testing.plan.md) measured 6.664 seconds median acquisition with a generation-local checkpoint and 1,000 signed tail events, compared with 12.321 seconds median genesis acquisition on the same v8 generation before sealing. The actual checkpointed backup pause was 6.757 seconds median. The production SQLite partition copy accounted for at least 99.4% of each fence. Both budgets still failed and native qualification remains open.

The [capacity remediation](../../sqlite-capacity-remediation/implementation.plan.md) moved SQLite copies outside the publication fence and preserved the authenticated pair through concurrent writes and failure testing. The final installed Linux diagnostic recorded 2.836 ms median total backup pause. Acquisition improved to 5.017 seconds median with 6.377 seconds maximum on the same checkpointed v8 tuple. Default activation and native qualification remain open.
