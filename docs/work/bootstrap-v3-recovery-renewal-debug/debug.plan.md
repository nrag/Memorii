# Bootstrap V3 Recovery Renewal Admission

- Work ID: `bootstrap-v3-recovery-renewal-debug`
- Work type: debugging
- Delivery fidelity: Level 2 early real-world testing
- Status: complete
- Coordinator: `/root`
- Created: 2026-09-24
- Parent WorkPlan: `docs/work/hermes-conversation-memory-trial/implementation.plan.md`
- Related WorkPlan: `docs/work/hermes-level2-test-gate/testing.plan.md`

## Objective

Restore the current Bootstrap V3 provider path after a live recovery claim is
issued by admitting the claim and operation-control renewal as one atomic,
same-operation write.

## Expected And Observed Behavior

The current V3 normalization owner renews its live recovery claim before remote
proposal work. The renewal must atomically extend the operation lease and
replace the claim snapshot. The writer admission policy currently recognizes
the initial two-record claim write and a one-record claim mutation, but rejects
the required two-record renewal as `generation contains cross-operation
governed records`. The provider then reports
`source_alignment_authority_unavailable` before invoking any semantic lane.

## Reproducer

`test_direct_provider_root_publishes_and_reloads_bootstrap_v3_normalization`
deterministically fails on the first renewal. The retained recovery index stays
claimed, all five lane call counters remain zero, and the captured exception is
`SemanticWriterAdmissionError` at the renewal CAS.

## Hypotheses

1. Confirmed: the writer policy has no validator for the two-record renewal
   closure, so valid control plus claim renewal falls into generic generation
   validation.
2. Rejected: the restored fixture supplied a stale authority bundle. Fixing
   its missing analyzer resource bindings advances execution to the renewal
   CAS but leaves the same deterministic admission failure.

## Scope And Invariants

- Admit exactly one same-operation control record and one matching claimed V3
  recovery index.
- Require unchanged operation generation, fence, writer, recovery key, marker,
  predecessor closure, and claim nonce.
- Require the operation lease, claim snapshot, timestamps, and renewal count to
  advance consistently and within existing bounds.
- Preserve fail-closed behavior for foreign, substituted, cross-operation, and
  generation writes.

## Evidence Log

- 2026-09-24: fixture authority validation initially failed because its
  analyzer resource list omitted the current V3 route binding; after correcting
  the fixture, execution reached the production renewal CAS.
- 2026-09-24: the renewal CAS failed in
  `SemanticWriterAdmissionPolicy.validate` with `generation contains
  cross-operation governed records` before proposal transport invocation.
- 2026-09-24: wired the existing exact two-record renewal recognizer into the
  live writer policy. It preserves the claim nonce, fence, writer, operation
  generation, recovery key, marker, predecessor closure, and renewal interval;
  requires advancing monotonic time and state revision; and permits an equal
  wall-clock lease expiry without regression.
- 2026-09-24: direct provider reproducer passed (`1 passed in 53.79s`); focused
  live-claim and cross-operation substitution regressions passed (`2 passed in
  17.91s`); full Ruff and configured Pyright passed.

## Next Action

None. The corrected boundary returns to the parent PR review.
