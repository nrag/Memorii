# SQLite Backup And Acquisition Capacity Remediation

- Work type: implementation
- Delivery fidelity: Level 3 release target with installed Linux diagnostics
- Status: active
- Baseline: `c3afc196` on `codex/durable-delivery-implementation`
- Parent: [durable delivery](../durable-delivery-implementation/implementation.plan.md)
- Evidence: [checkpoint and backup recheck](../sqlite-memory-payload-qualification/testing.plan.md)

## Scope

Pin both WAL participants under the existing verified publication fence. Bind the pinned control state and journal tip to the selected signed partition. Copy from the same handles after releasing the fence. Verify the copied pair using the existing backup checks before publishing the encrypted archive. Keep authority and destructive storage changes fenced. Preserve v7 defaults, existing backup manifests, archive readers, signed roots, checkpoints and release checks.

Optimize full v8 acquisition while preserving exact BLOB hashing, typed catalog digests, reference and index closure, and runtime checkpoint and tail verification. Run the repaired installed wheel on the retained synthetic 1 GiB concentrated fixture with the generation-local v8 checkpoint and 1,000 signed tail events.

| Milestone | Proof owed |
| --- | --- |
| Backup fence and failure paths | A coherent old pair survives a permitted signed advance outside the fence. A failed pin or copy cleans up and emits no archive. Scope changes cannot release an archive under stale authority. Whole-partition erasure excludes outstanding plaintext backup leases. |
| Acquisition verification | Signed v7/v8 roots and replay parity remain exact. Corrupt bodies, indexes and reference state still reject. Measure complete acquisition and component timings on the installed candidate. |
| Full installed diagnostic | Record all attempted samples and verified backup archives against the same signed checkpointed fixture. Report both five-second budgets using three fresh-process samples. Native qualification still belongs to the release plan. |

The backup writer owns production backup and necessary owner erasure coordination. A separate test writer owns focused backup integration regressions. The acquisition writer owns repository verification internals. The coordinator owns baseline profiling, release timing, integration and evidence.

## Next Action

Implement and verify the short backup fences and exact acquisition optimizations, then freeze the candidate for installed measurement.
