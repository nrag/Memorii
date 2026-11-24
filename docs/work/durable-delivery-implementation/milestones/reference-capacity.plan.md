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

Proposed. No product edits, tests or milestone approvals recorded.
