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
