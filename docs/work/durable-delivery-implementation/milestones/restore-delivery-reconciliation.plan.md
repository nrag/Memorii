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

The operator CLI now exposes `backup restore-stage` with the reviewed plan file and a raw, owner-only recovery key file. The command publishes only verified staging. The CLI test checks a readable key from other users is refused and that successful staging leaves the current signed tuple unchanged.

Staging now writes a purpose-signed attestation binding the reviewed plan, signed source tuple, live watermark, exact SQLite participant bytes and suppression evidence. The owner can run `backup restore-verify-stage` after restart to revalidate this evidence without a decryption key. Thirty-two operator tests passed. The approved generation selector, stale-handle fencing and older-generation activation remain open.

The signed physical generation selector now fences retained SQLite handles and checks the finalized tuple even for a default-file fallback. The owner CLI `backup restore-activate-current` selects verified exact-current staging under the installation barrier and old partition lock. A failure before pointer publication leaves the live tuple unchanged and permits exact retry. Reopening sees the same signed tuple in the selected file. The owner must reopen retained services after a physical cutover. An older backup still requires a separate generation-change intent, authenticated history ancestry, and a durable delivery hold.

`backup restore-preview-stage` compares attested staging with the current fenced publication. It reports exact-row parity and differences for command receipts, target receipts, queued deliveries and writeback decisions. It returns counts without exposing records. A target receipt comparison establishes catalog differences only. Reconciliation still requires the target owner to verify both receipt and effect under current authority, and older restores remain in inert staging.

The continuation adds owner selection of a reviewed older restore under a signed generation-change intent, plus exact-current staged upgrade from authenticated journal formats v4 and v5 to v6. Cutover writes a manifest-covered hold and converts digest-only queue entries without rewriting their original bytes. Interrupted selectors resolve to the verified old or new tuple, and an invalid selector quarantines. Generation and effective epoch bind managed paging tokens. Enabling delivery polling still requires owner reconciliation of held work. Nonempty runtime formats preceding a signed event journal cannot use this staged upgrade.
