# Graph Transaction Authority Rejection

- Work ID: semantic-ingestion-graph-transaction-authority-debug
- Work type: debugging
- Status: active
- Coordinator: root
- Created: 2026-09-13
- Last updated: 2026-09-13
- Parent WorkPlan: `../engineering-closure/implementation.plan.md`
- Related WorkPlans: `../engineering-closure/milestones/05-authenticated-observer-comparator.plan.md`, `../engineering-closure/milestones/06-host-composition-closure.plan.md`
- Canonical inputs: current branch, semantic-ingestion architecture, configured observation integration fixture
- Expected outputs: causal correction, regression proof, exact-revision independent closure review

## Objective

Restore the canonical graph transaction path required to seed a committed
cohort for authenticated public observation. Preserve writer, monitor,
preplanning, lease, registry and observation-ledger authority boundaries.

## Expected And Observed Behavior

The scenario graph authority and signed observation registry/activation target
compose successfully, and the writer is `verified_semantic`. A normal supported
source should reach the configured graph authority and commit an observation
delta. Instead `sync_event` returns
`graph_transaction_authority_unavailable` before the deterministic graph
authority provider is invoked. One preplanning control remains. Moving ledger
activation after the rejected attempt fails correctly because the retiring
writer is not drained.

The failure reproduced in the configured observer fixture under Python 3.12 on
2026-09-13. Three fixture combinations produced the same causal signature; no
draft test or product edit was retained.

## Hypotheses

1. Observation-ledger activation changes writer or lease coordinates that the
   pending V3 recovery control still expects, so the lease session is rejected
   before graph authority execution.
2. Mandatory capability-monitor/status authority is absent or bound to a
   different writer epoch in the scenario host, and preflight converts that
   mismatch to the generic graph-transaction authority result.
3. Registry/activation replacement changes a digest incorporated into the V3
   handoff or recovery replay, making the sealed replay fail before graph
   authority acquisition.

The generic public reason is not root-cause evidence. Experiments must inspect
the retained control/recovery state and the smallest internal failure boundary
without weakening the public non-disclosure contract.

## Changed Surfaces And Ownership

No product or test change is currently retained. One read-only debugger owns
the causal trace. After root-cause confirmation, exactly one Terra writer may
own the minimal production correction and focused regression test. The parent
implementation WorkPlan retains comparator and host-closure state.

## Verification Matrix

- Deterministic reproducer: configured scenario graph authority plus signed
  observation registry/activation target; provider must be invoked and one
  observation delta must exist.
- Failure siblings: ledger inactive/active, monitor authority absent/current,
  stale writer epoch, substituted registry/target.
- Preservation: rejected authority remains fail closed; undrained activation
  remains rejected; no hidden fixture bypass.
- Closure: focused warnings-as-errors tests, affected persistence/integration
  shard, Ruff, Pyright, identity gate, then exact-revision spec/correctness/test
  review.

## Next Action

Trace the rejection from `_run_semantic_ingestion` through recovery,
lease-session and graph-bundle execution boundaries, and run one discriminating
experiment that distinguishes writer/lease mismatch from monitor authority and
registry/replay mismatch.
