# Staged SQLite Payload Implementation

- Work type: implementation
- Delivery fidelity: Level 2 for the owner-controlled trial. Level 3 before default activation or release qualification.
- Status: complete for the staged trial and installed diagnostic. Release activation remains blocked on capacity.
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

## Staged Format Evidence

Product and timing runner are pinned at `410556bf`. The Linux arm64 image installed the matching wheel with SHA-256 `8e5a68b6ff26a837c72244f35979d1608adc4d7b59da1764138f7b857bd6f65b`. The runner verified the installed wheel inventory and the exact audited v7 input tuple before making staging changes. The installed warning-as-error selection passed 40 integration cases, including the nine new raw-upgrade cases. Scoped Ruff and Pyright passed. The selected cases cover opt-in, exact preview binding, raw append and reopen, older and exact-current raw restore, interrupted selector exchange, incompatible framing, and isolated payload or index corruption. Independent review additionally exercised native source admission and release of a source retained under v7 after conversion, and confirmed the indexes used for bounded current reads.

The 128-source smoke selected format 8 through the real owner handler and reopened it from a fresh process. The partition dropped from 474 MiB to 166 MiB. Complete acquisition took 0.243 seconds and the backup operator held its publication fence for 0.069 seconds. The v7 source backup held the fence for 0.221 seconds. Each was one diagnostic sample.

The full trial keeps the audited source, rollback generation, and verified restore stage separate. The guest filesystem reached 98% use during conversion with SQLite secure deletion enabled and an approximately 17 GiB working WAL. The disposable encrypted fixture archive was removed after restore attestation and before selection, freeing about 15 GiB without changing the signed source or staging bytes. The working WAL reached about 20 GiB before compaction. Provision staging workspace separately from the expected final file size.

On the audited 1 GiB concentrated workload, selection retained the v7 recovery file and reduced the complete active partition from 14.899 GiB to 5.265 GiB (64.7%). The activation call, including the second preview, format conversion, compaction and verification, took 400.3 seconds in this guest. That is a staging cost with the installation in `read_only`; the backup pause samples time only the exclusive publication fence around required snapshot capture.

## Full Linux Timing

The [concentrated fixture audit](../sqlite-memory-payload-design/linux-reference-fixture.json) binds 4,096 sources, 1 GiB of native source bytes, 200 tasks, 10,000 execution nodes, 50,000 solver nodes, and 100,000 signed runtime events. The experimental format was selected only in a disposable copy. The backup timer includes both participant snapshots and the live watermark check while holding the exclusive publication fence. Encryption and signed archive verification finish outside the fence. Every sample opens a fresh process over the selected installation; the operating-system cache is uncontrolled.

The source generation has a selected checkpoint with a 1,000-event tail. The exact-current upgrade adds a generation boundary. Its new publication starts without a selected checkpoint and all three fresh acquisitions therefore include genesis replay. Their median was 10.951 seconds, with a maximum of 11.115 seconds. The first point read's median was another 8.657 seconds with the original semantic batch checks. The acquisition result exceeds the five-second reference budget and characterizes the current installed cutover path. A matched checkpoint-and-tail comparison is still open.

The v8 backup pause was 5.624 seconds median and 5.652 seconds maximum across three signed archives, above the five-second budget. The one v7 source backup paused for 18.566 seconds. The upgrade made both the active file and backup pause smaller. These are installed diagnostics on a shared Colima guest and do not establish the platform qualification gate. The Linux operation samples are in the [full results](linux-staged-reference.jsonl) and [smoke results](linux-staged-smoke.jsonl). Each full v8 sample resolves the same finalized owner-upgrade tuple.

## Release Follow-Up

Keep v7 as the default. Evaluate a generation-local checkpoint for the staged v8 publication and profile the backup fence's snapshot copy. The [durable delivery plan](../durable-delivery-implementation/implementation.plan.md) owns capacity qualification and default activation.
