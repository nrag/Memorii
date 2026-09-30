# Legacy Migration

- Parent WorkPlan: [implementation index](../implementation.plan.md)
- Work type: implementation milestone packet
- Delivery fidelity: Level 3, bounded slice only
- Status: active (sub-slices 1-3 landed incl. review remediation 183e47a5; CLI surface, external key/catalog authority verification and pre-cutover rollback plan remain)
- Requirements: DUR-10,12,13,18; regression DUR-15,16,17
- Dependencies: semantic-ontology
- Baseline revision: bad9eeefb43f7f42fb95d583b11859e2f2ca9eb8 (planning snapshot)
- Implementation base: c906e849; current head 183e47a5

## Observable Acceptance

A seeded existing JSONL installation adopts independent control authority, migrates without changing canonical data, and restarts through each managed root on SQLite.

## Owners, Contracts And Expected Files

Under memorii/memorii/: core/storage_administration/ migration owner; core/memory_plane/store.py import reader; selected factories; CLI and backend selector; key/catalog authority adapters.

MemoryPlaneMigrationPlan, LegacyStorageSelector, migration_only lifecycle, adoption receipt and generation-change intent; validate checksums/all versions/source closure/keys/codecs before exact selector cutover. Original files immutable, no dual writes. Before-new-write rollback explicit; after accepted writes stale JSONL rollback denied.

Exact new symbols, payload/source-kind schemas, SQL catalogs, entrypoints and generated artifacts must match [identity ledger](../identity-and-changes.md) and approved design; expand the actual inventory before creating additional identifiers. [Bindings](../production_entrypoint_bindings.md) supplies current precursor -> proposed callsite/authority -> proof. Zero proposed callers cannot close this packet.

## Compatibility, Migration, Rollout And Rollback

Only explicit initialized/selected backend roots serve managed traffic. Preserve original domain APIs unless design declares the version boundary. No generic runtime grant, JSONL fallback, partial publication or speculative semantic truth. Relevant generation changes use exact old/new recovery and current control authority. Failed publication/validation leaves prior verified state; post-new-write downgrade requires tested compatibility or read_only forward repair. Release exposure stays limited until all allocated parent requirements close. Domain-specific obligations are in the contract above and [validation](../validation.md).

## Exact Validation Commands

Cwd memorii/. Interpreter is the CI-selected Python 3.11 or 3.12 environment from [gates](../gates.md), with editable `.[local,dev]` dependencies for local code tests. These **planned** new paths are not present/executed yet; create under linked approved test architecture, never add empty files just to make commands pass.

```bash
python -W error -m pytest tests/unit/core/test_memory_plane_migration_contract.py -p no:cacheprovider
python -W error -m pytest tests/integration/test_memory_plane_migration_recovery.py -p no:cacheprovider
python -m ruff check memorii tests
python -m memorii.tools.identity_hygiene --root .. --allowlist ../.agents/identity_hygiene_allowlist.json
pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"
```

Run existing owner regressions mapped in validation.md, then every applicable live-workflow gate once on the coherent candidate (do not replace broad required coverage with these focused commands). Additional same-family tests/files are inventoried before writing. Subprocess/package/host/migration matrices remain in explicit slower tiers. Capture cwd, interpreter/dependency/SQLite versions, warnings, environment, command, exit code, logs, exact base/head and dirty-tree status. Required external/OS cases cannot be inferred from local success.

## Proof, Maturity And Completion

Acceptance requires the observable journey plus applicable positive/negative/boundary/retry/concurrency/crash/revocation/compatibility cases in validation.md. Failures must be asserted at real public roots, with no leaked data or partial durable state. Evidence target: implemented and locally verified for the bounded slice; CI-enforced only with actual run evidence, independently reproduced only for a separately authored reducer, operationally verified only for pinned real host/platform/restore journeys. Present maturity: specified only; historical design probes remain separate.

At candidate freeze update live diff, identities, generated authority descendants, root callsites/arguments/caller counts and gates; run spec/correctness/test reviewers once for the coherent milestone. Reconcile all findings before sole-writer remediation. Record exact revision and `remaining_validated_p1_p2: []` only after proof, never prefill it. Any required missing external proof keeps that acceptance open. Parent requirements remain partial until [coverage](../coverage.md) aggregates all allocated packets and release gates.

## Non-Goals

No loss-tolerant salvage, inferred catalog IDs, reextraction/model calls, cross-partition repartitioning or silent old-binary fallback.

## Progress, Review And Closure

Sub-slices 1-2 (2026-09-29, base c906e849, commit fc565bbb): memorii/core/storage_administration/migration.py — build_migration_plan (closed read-only MemoryPlaneMigrationPlan: byte fingerprint/size, both revisions, validated chain, batch/record counts, participant inventory, free-space requirement, self-verifying digest; unknown plane members refuse; never writes); typed LegacyStorageSelector binding the exact legacy input into one expected-old discriminator; migrate_legacy_installation performing owner-authorized adoption (first atomic control transaction: selector + plan digest + migration-only read-only lifecycle), import (validated copy of every batch with original bytes/revisions/checksums into the fresh SQLite generation) and cutover (generation-change intent with the legacy selector digest as expected-old; finalize activates operational mode). InstallationControlState gained adopted_legacy_records_digest (closed optional field, pre-release format) so post-cutover roots serve managed traffic with legacy files preserved while unrelated coexistence still refuses. Tests: tests/unit/core/test_memory_plane_migration_contract.py (6: read-only + digest-bound plan, participant inventory, unknown-member and missing-plane refusal, corrupt-chain fail-closed, selector digest stability) and tests/integration/test_memory_plane_migration_recovery.py (4: byte-preserving migration with revision/record/order parity + managed selection after, changed-input refusal, fresh-process restart, idempotent repeat). Evidence: 36 affected tests green across migration/provider/administration suites; ruff/pyright/identity gates green.

Remaining in this packet: adoption crash-cut matrix (intent-only, imported-without-cutover, third-state) with migration_only gating of ordinary data APIs; explicit pre-new-write rollback through the owner plan and post-write stale-rollback denial; migration-only denies normal backup/data APIs; CLI surface (migrate plan/apply) and external key/catalog/legacy-reader authority verification; then the milestone review cohort.


## Milestone review round 1 + remediation (2026-09-29)

Combined-lens cohort on candidate 3bcf81cf: happy path judged real and well-tested; four P2s reproduced (adoption-crash dead-end quarantining, mid-import PK collisions bricking re-migration, conflicting adoption silently serving the previous migration, closed-layout inventory gaps for the direct/inspection layouts) plus mode-enforcement, capacity/locking, .protected preservation and test-family findings. Remediation commit 183e47a5 restructured the owner into staged phases with migration-binding marker intents (exact-legacy-state recovery), full-rebuild import, conflicting-adoption refusal, read-only window enforcement at the publication gate, plane-lock import hold with capacity preflight, in-place .protected adoption, the pointer-set constant fix and staged crash-cut/conflict/read-only journeys. Remaining recorded follow-ups for this packet: direct-plane and installed-inspection layout journeys (the digest check and _LEGACY_LAYOUTS extension), the post-cutover adopted-input-modified refusal reason, per-selection hashing cost/TOCTOU on the adoption digest, CLI staging (migrate plan/apply), external key/catalog/legacy-reader authority verification, explicit pre-new-write rollback, adoption receipt object, parity families needing richer fixtures (semantic reconstruction, ontology state, protected reads, export), migration-only denial of backup/background, and the design's parity list once fixtures exist. Identity additions (LegacyStorageSelector, MemoryPlaneMigrationPlan, LegacyMigrationError, adopted_legacy_records_digest, stage names) ledgered in identity-and-changes.md at remediation.
