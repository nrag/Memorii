# Operator Controls

- Parent WorkPlan: [implementation index](../implementation.plan.md)
- Work type: implementation milestone packet
- Delivery fidelity: Level 3, bounded slice only
- Status: active (sub-slice 1 landed: operator surface with fenced modes, status, scoped export 9fe1a6c6; backup/restore, forget/erasure, retention, doctor remain)
- Requirements: DUR-08,09,10,11,12,13; regression DUR-03,05,07,18
- Dependencies: all supported data/host roots enrolled; foundational control primitives already implemented
- Baseline revision: bad9eeefb43f7f42fb95d583b11859e2f2ca9eb8 (planning snapshot)
- Implementation base: ab9af959; sub-slice head 9fe1a6c6

## Observable Acceptance

Owner can inspect/explain, pause/resume/bypass, export, checkpoint, back up/verify/restore, plan/apply retention/forget and erase eligible isolated partitions without resurrecting revoked evidence.

## Owners, Contracts And Expected Files

Under memorii/memorii/: core/storage_administration/; filesystem policy/maintenance; participant owners; CLI; host status; encrypted backup and recovery-bundle/key-owner integrations.

All-writer enrollment and exclusive barrier; signed backup manifests/recovery bundle plus independent anchor; current security authority survives older-data restore; no prepared intent in backup; read_only forbids hidden expiry/background writes; exact deletion preview/epoch/owner confirmation; explicit erasure_incomplete and mixed-partition refusal.

Exact new symbols, payload/source-kind schemas, SQL catalogs, entrypoints and generated artifacts must match [identity ledger](../identity-and-changes.md) and approved design; expand the actual inventory before creating additional identifiers. [Bindings](../production_entrypoint_bindings.md) supplies current precursor -> proposed callsite/authority -> proof. Zero proposed callers cannot close this packet.

## Compatibility, Migration, Rollout And Rollback

Only explicit initialized/selected backend roots serve managed traffic. Preserve original domain APIs unless design declares the version boundary. No generic runtime grant, JSONL fallback, partial publication or speculative semantic truth. Relevant generation changes use exact old/new recovery and current control authority. Failed publication/validation leaves prior verified state; post-new-write downgrade requires tested compatibility or read_only forward repair. Release exposure stays limited until all allocated parent requirements close. Domain-specific obligations are in the contract above and [validation](../validation.md).

## Exact Validation Commands

Cwd memorii/. Interpreter is the CI-selected Python 3.11 or 3.12 environment from [gates](../gates.md), with editable `.[local,dev]` dependencies for local code tests. These **planned** new paths are not present/executed yet; create under linked approved test architecture, never add empty files just to make commands pass.

```bash
python -W error -m pytest tests/unit/core/test_storage_administration_contract.py -p no:cacheprovider
python -W error -m pytest tests/integration/test_installation_backup_restore.py -p no:cacheprovider
python -m ruff check memorii tests
python -m memorii.tools.identity_hygiene --root .. --allowlist ../.agents/identity_hygiene_allowlist.json
pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"
```

Run existing owner regressions mapped in validation.md, then every applicable live-workflow gate once on the coherent candidate (do not replace broad required coverage with these focused commands). Additional same-family tests/files are inventoried before writing. Subprocess/package/host/migration matrices remain in explicit slower tiers. Capture cwd, interpreter/dependency/SQLite versions, warnings, environment, command, exit code, logs, exact base/head and dirty-tree status. Required external/OS cases cannot be inferred from local success.

## Proof, Maturity And Completion

Acceptance requires the observable journey plus applicable positive/negative/boundary/retry/concurrency/crash/revocation/compatibility cases in validation.md. Failures must be asserted at real public roots, with no leaked data or partial durable state. Evidence target: implemented and locally verified for the bounded slice; CI-enforced only with actual run evidence, independently reproduced only for a separately authored reducer, operationally verified only for pinned real host/platform/restore journeys. Present maturity: specified only; historical design probes remain separate.

At candidate freeze update live diff, identities, generated authority descendants, root callsites/arguments/caller counts and gates; run spec/correctness/test reviewers once for the coherent milestone. Reconcile all findings before sole-writer remediation. Record exact revision and `remaining_validated_p1_p2: []` only after proof, never prefill it. Any required missing external proof keeps that acceptance open. Parent requirements remain partial until [coverage](../coverage.md) aggregates all allocated packets and release gates.

## Non-Goals

No selective physical row surgery, guaranteed media overwrite or remote hosting. Auxiliary files remain supported registered participants; SQLite backup alone is not installation backup. Mandatory capacity defaults and engineering measurements; no comparative agent benchmark.

## Progress, Review And Closure

Sub-slice 1 (2026-09-30, base ab9af959, commit 9fe1a6c6): memorii/core/storage_administration/operator.py — StorageAdministrationOperator (content-free status with revision heads from the last verified snapshot; acknowledged mode transitions active/read_only/bypass atomic in control state with journal entries — read_only fences data publication through the service gate, bypass returns to active only, stale control revision conflicts, quarantined refuses; scoped deterministic export under an OwnerCapability binding installation identity + owner principal with constant-time compare; destructive operations deliberately not one-call). Tests: tests/unit/core/test_storage_administration_operator.py (6). Remaining in this packet: backup/restore over participant snapshots; forget/erasure plans with epoch increments; retention plan/apply; doctor diagnostics; all-writer enrollment barrier; milestone review.

Sub-slice 2 (2026-10-01): backup/restore + forget/erasure + retention + doctor landed. BackupRestoreOperator (operator_backup.py): create runs only under the acknowledged exclusive barrier (read_only mode), snapshots control+partition through SQLite's online backup API (never live file copies), records revision vector/epoch, and writes an atomically-renamed complete marker; verify recomputes manifest + per-participant digests and refuses torn (missing marker) and tampered archives (size OR digest mismatch); restore plans from a verified archive with installation-identity binding and explicit data-loss acknowledgement for older control revisions, then applies into a staging root validating digests again — never deleting source or prior installation. GovernanceOperator (operator_governance.py): logical forget plans enumerate exact record ids and apply as durable suppression journals with the historical-bytes-retained disclosure; whole-partition erasure requires the acknowledged plan plus a second explicit consent, reports erasure_incomplete when offline copies are unaccounted, and leaves content-free receipts in independent control state; retention plans age-prune suppression journals only (active recovery untouched, recheck at apply); doctor is strictly read-only (control state, Tier verification, owner-only permissions on control/partition/keys) and reports findings without raising. Tests: 12 operator journeys green (barrier refusal, round trip incl. tamper, foreign/missing-marker refusals, forget-empty refusal + plan/apply + retention no-op, erasure acknowledgement + incomplete receipt, doctor read-only). Ruff/identity clean; new modules pyright-clean (service.py's 3 diagnostics are baseline). Remaining in packet: all-writer enrollment barrier, CLI surface, milestone review round.
