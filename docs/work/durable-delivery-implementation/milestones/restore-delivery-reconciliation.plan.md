# Restore Delivery Reconciliation

- Parent: [durable delivery implementation](../implementation.plan.md)
- Status: proposed
- Requirements: DUR-02/03/05/07/08/10/12
- Dependencies: Durable intent and output plus the signed local delivery implementation in the enrolled test root
- Closure identity: unset, record actual base, code head, dirty state and artifact/run digests before claim

## Observable Acceptance

An older restored partition holds uncertain deliveries and old commands. An owner can reconcile with verified evidence. Exact-current restore preserves eligible retries.

## Owners And Contract Changes

core/storage_administration/operator_backup.py, operator and control owners, tools/runtime_operator.py, runtime repository/worker, sidecar and spool.

Record manifest-backed DeliveryRestoreHold with source/current watermark and generation during staged restore. Keep policy explicit for proven retained effect/receipt, proven pre-restore absence, discarded acceptance and unknown outcome. Implement reviewed owner reconcile_delivery plan, fence stale workers and preserve old proof on retries under renewed credentials. Reject missing prior receipts and old spooled intents on mutation. Preserve old data and current security state.

## Verification

Use old/current restore and fresh-host case with and without later proof. Exercise target commit then lost ack plus restore, verified absent receipt, retained exact old receipt, stale origin with renewed binding, spool retry, genuinely prepared new intent, and CLI owner/grant refusal. Confirm no effect in read_only or under a hold.

Existing regression anchors from memorii/ in the applicable pinned CI environment:

```bash
python -W error -m pytest tests/unit/core/test_storage_administration_operator.py tests/integration/test_runtime_process_recovery.py tests/integration/test_memory_plane_migration_recovery.py -p no:cacheprovider
```

New path proof commands and exact test names must be registered through the [validation ledger](../validation.md) before implementation. Include the affected workflow job and artifact evidence. Review against the exact commit. Evidence maturity is design specified at this baseline. This packet is complete only with local and applicable enforced proof and reviewed closure. It satisfies only its bounded portion of the parent requirements.

## Scope Boundary

Use the approved design and existing semantic owners. Keep unsupported roots visibly unavailable. Record compatibility and rollout deltas at the actual candidate. Parent owns release authorization and aggregate gate outcome.

## Progress And Review

The authenticated origin path refuses cross-generation reuse. Independent review replayed an already accepted proof after an older empty backup booted into its old generation. To prevent that exposure, direct fresh boot now refuses every managed-capable partition, including an empty backup. The encrypted backup, planning and staging journey remains available. Legacy schema v1 direct boot still passes and cannot mint managed proofs. Signed staged-generation activation, durable hold evidence, owner reconciliation and legacy queue migration remain open.

Backup v2 binds both the verified signed publication and the signed control tip. Owner restore plans bind the exact archive and current control/data watermark. The operator verifies both decrypted SQLite databases and the replay chain and indexes before exposing the inert staging directory. The v1 archive decoder keeps its original digest interpretation. Tests cover same-control-revision data advance, archive substitution, decrypted chain loss and invalid captured pairs. For activation, replacing the live SQLite inode is unsafe because existing services retain database and WAL handles. An authenticated generation selector must invalidate or replace retained handles. Old signed history also needs explicit generation ancestry at cutover.
