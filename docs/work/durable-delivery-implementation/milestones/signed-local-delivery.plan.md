# Signed Local Delivery

- Parent: [durable delivery implementation](../implementation.plan.md)
- Status: proposed
- Requirements: DUR-02/03/05/07/08/13
- Dependencies: Host result and decision. Restore safeguards required before rollout.
- Closure identity: unset, record actual base, code head, dirty state and artifact/run digests before claim

## Observable Acceptance

Installed enrolled worker advances both target kinds and persisted authorized host receipts. No duplicate logical effect after lost acknowledgement.

## Owners And Contract Changes

core/persistence/runtime_api.py and runtime_repository.py, stores/sqlite/partition.py, StorageAdministrationService, memory_plane/sqlite_store.py, WorkStateService, provider-owned candidate and recall roots.

Replace raw callback path for managed composition. Use signed claim/lease/fence and narrow target owner ports. Under one coordinator transaction check current grant/source/mode/generation/lease and commit exact effect, receipt and terminal status. Work projections stay separate from native events and prefer highest eligible revision. Episodic, semantic and user staging uses governed in-transaction memory batch. Skill catalog has no MemoryDomain coercion. Apply design retry schedule and due-entry bounds. Use owner-authorized upgrade for existing digest-only records, preserving bytes and requiring reconciliation.

## Verification

Count actual target receipts and effects for both kinds and all candidate destinations, confirm candidate-only writes. Test both revoke/pause race orders, stale worker, concurrent claims, wait budget, unknown target, old digest-only rows, precommit and postcommit crash cuts, lost acknowledgement and restart. Prove duplicate lookup does not republish a target effect.

Existing regression anchors from memorii/ in the applicable pinned CI environment:

```bash
python -W error -m pytest tests/unit/core/test_runtime_command_dispatch.py tests/unit/core/test_runtime_state_repository.py tests/unit/core/test_storage_administration_operator.py tests/integration/test_runtime_process_recovery.py -p no:cacheprovider
```

New path proof commands and exact test names must be registered through the [validation ledger](../validation.md) before implementation. Include the affected workflow job and artifact evidence. Review against the exact commit. Evidence maturity is design specified at this baseline. This packet is complete only with local and applicable enforced proof and reviewed closure. It satisfies only its bounded portion of the parent requirements.

## Scope Boundary

Use the approved design and existing semantic owners. Keep unsupported roots visibly unavailable. Record compatibility and rollout deltas at the actual candidate. Parent owns release authorization and aggregate gate outcome.

## Progress And Review

494508d3 records an authorization-bound work projection at managed pause and exercises the registered target through a transactional claim, effect, receipt, terminal queue state and idempotent retry in a real managed installation. The provider staging validator checks exact acceptance selectors and current source closure and produces inert candidate records. Candidate publication, protected skill storage, managed projection read composition, legacy conversion and installed polling remain open. Polling stays behind the activation gate.

Independent review reproduced lease reuse after owner pause and resume. Claim and recovery now check the control revision and eligibility epoch. Task suppression is rechecked during claim and publication, and terminal receipt retry requires the exact completed claim.
