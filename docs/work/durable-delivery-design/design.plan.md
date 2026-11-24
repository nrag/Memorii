# Durable Delivery Design Remediation

- Work type: design
- Fidelity: Level 3 first production release
- Status: complete
- Coordinator: main task and sole canonical writer
- Created and updated: 2026-11-23
- Parent: [readiness regrade](../durable-memory-design-regrade/design-review.plan.md)
- Related: [implementation WorkPlan](../durable-memory-implementation/implementation.plan.md)
- Canonical: [durable memory design](../../design/durable_execution_and_solver_runtime.md)
- Baseline: HEAD 4c390de14d63fd1e13961e77bcca2f6b82f693f5, design SHA-256 63f90df2a4e822df430c32b209f03a671379189bc8e999e19d7f12ac5fbf94fe

## Objective And Scope

Resolve the five regrade findings in the design. Cover output production, host decisions, target atomicity, restore reconciliation and reproducible capacity. Exclude product code, remote target delivery, and deferred agent benchmark. Existing README and implementation notes predate this operation. Preserve them.

## Baseline Evidence And Decisions

The installed consumer dispatches with RuntimeCommandService. Its work projection row contains a command digest. The generic drain takes a callback inside an unsigned write transaction and has test callers only. Consolidator currently produces episodic, semantic and user WritebackCandidates. Existing skill and archive outputs require deliberate new owner adapters. The provider sync_event path authenticates native evidence, and WorkStateMemoryProjector stages provider-event candidates. Neither can admit typed runtime-derived candidates with the required receipt. MemoryPlaneService.conditionally_write_records and SqliteMemoryPlaneStore.apply_batch_in_transaction already support conditional governed batches. Signed runtime and memory-plane publication share a partition and control owner. GrantEpochRegistry alone cannot serialize grant revocation with a partition commit. These are direct source observations, not implementation evidence for the new design.

Choose same-partition target owners for v1, a host decision before memory staging, and a reconciliation hold after uncertain restore. Core spec §21.2 determines the host boundary. Spec §12.2 requires output availability and does not require all outputs to become asynchronous target writes. The accepted package and installation limits already exclude distributed operation. No external product decision has been identified.

## Completion And Sequence

1. Reconcile contracts and independent experimental feasibility, including alternatives.
2. Freeze design and run spec, correctness and test reviews. Reconcile one bounded batch if needed, then final full review.
3. Record proof maturity, checksum and remaining implementation work. Never infer runtime or release readiness from a design review.

## Next Action

Hand off the approved design to the existing implementation WorkPlan. Pin the revised SHA before enqueue/target implementation and refresh the affected production bindings and validation inventory.

## Outcome

The [canonical design](../../design/durable_execution_and_solver_runtime.md) is frozen at a51ec4e02a62b05a5b28dc2afed146263a56b125ac2bae8f9abbaf22cbb4f9f2. All five regrade findings have design resolutions, including the reviewer-discovered skill-domain and restored-intent siblings. The three reviewers approved the final design scope. [Evidence and reviewer dispositions](evidence.md) cover baseline source evidence, feasibility, alternatives and exact validation limits. Current code does not implement the new routes, catalogs, coordinator, worker or capacity generator. No product release approval follows. No owner decision was needed.
