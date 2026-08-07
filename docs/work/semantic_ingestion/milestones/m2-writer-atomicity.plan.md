# Writer, Lease, And Atomic Generation Milestone

- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Status: complete
- Requirements: SIA-R10, SIA-R11, SIA-R20, SIA-R21
- Historical authority: archive heading `M2 - Single writer, leases and atomic generations` and its validation matrix

## Objective

Ensure one current semantic writer and fence publishes complete source,
control, graph, event-input, observation, artifact, and terminal generations;
stale writers and partial failures must have zero visibility.

## Scope And Owners

Own the semantic atomic-store protocol, writer manifest/epoch, lease and
allocation coordination, filesystem generation adapter, finite writer
inventory, migration certificate, drain, cutover, and forward-only rollback.
Learned semantic acceptance and complete replay algebra remain later milestones.

## Completion Evidence

- Every governed writer entry point requires the current certified binding.
- Lease claim, renewal, stale fencing, bounded recovery, exhaustion, and stable
  allocation pass fake-clock and backend proof.
- In-memory and JSONL failpoints expose prior-or-complete generations only.
- Process-safe same/distinct delivery, reopen corruption, lost acknowledgement,
  idempotent retry, migration, cutover, and rollback families pass.
- Complete changed-surface static and independent reviews close.

## Recorded Result

Complete. The archive retains the exact validation matrix, commands, process
proof, review dispositions, and the boundary that M3 supplies learned payloads
while M4 supplies full event/replay semantics.

