# Staged SQLite Payload Implementation

- Work type: implementation
- Delivery fidelity: Level 2 for the owner-controlled trial. Level 3 before default activation or release qualification.
- Status: active
- Baseline: `a798e27b` on `codex/durable-delivery-implementation`
- Parent: [durable delivery](../durable-delivery-implementation/implementation.plan.md)
- Accepted trial contract: [SQLite memory payload storage](../../design/sqlite_memory_payload_storage.md)
- Design evidence: [payload feasibility](../sqlite-memory-payload-design/design.plan.md)

## Objective And Boundaries

Convert a verified exact-current installation to a raw payload generation through the existing owner-authorized staging and review path. Keep v7 as the default for new installations. Measure released acquisition and the actual backup publication barrier before enabling the format elsewhere. Keep signed raw bytes, envelope order, revision semantics, history, and suppression behavior intact.

The owner CLI and backup operator bind an explicit raw format selection into the preview. The partition repository owns dispatch by physical format and the signed accumulator. The memory plane retains its typed batch checksum and revision checks. Provider source authority, archive evidence and forensic reads resolve through that repository. An older backup uses its preserved format. Production checks use the signed installed candidate and never use the scratch projection as evidence of an installed upgrade.

| Milestone | Proof owed |
| --- | --- |
| Staged raw format | Owner preference and exact preview digest; v7 defaults; signed raw acquisition on reopen; exact memory catalog conversion; correct write, empty batch, first read, scopes, and backup restore; reject unsupported framing and altered or stale state |
| Installed timing | Same frozen synthetic source on the pinned installed candidate; measure complete fresh-handle acquisition and exclusive backup pause through the actual backup operator; record archive and selected identities, whole-file bytes and remaining qualification |

Known baseline failures from the earlier trial are the standalone third-state intent quarantine assertion and managed partition factory assertion. Reproduce unexpected failures on the base before classifying them. The engineering qualification still requires both distributions on dedicated native Linux and macOS under the approved sample count and budgets.

## Next Action

Complete the staged raw format and verify the owner upgrade, reopen, memory write, and backup through the production entry points.
