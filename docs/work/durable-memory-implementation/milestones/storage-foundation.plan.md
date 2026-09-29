# Storage Foundation

- Parent WorkPlan: [implementation index](../implementation.plan.md)
- Work type: implementation milestone packet
- Delivery fidelity: Level 3, bounded slice only
- Status: active (sub-slice 1: shared partition + SqliteMemoryPlaneStore parity; publication/init and factory wiring remain)
- Requirements: DUR-02,03,05,13,15,16
- Dependencies: Readiness, approved design and matrix review
- Baseline revision: bad9eeefb43f7f42fb95d583b11859e2f2ca9eb8 (planning snapshot)
- Implementation base: fe9e1913; current sub-slice head recorded per commit

## Observable Acceptance

Initialize a verified partition; submit a canonical memory batch through build_filesystem_provider; reopen it in another process with original records and both revisions. Exercise a semantic commit and ontology activation/recovery through unchanged domain owners on the selected backend.

Before code: confirm approved design SHA; select and record actual implementation base/head; refresh mapper bindings and actual codec/schema/generated inventories; capture existing sibling identities. Activate a separate linked testing WorkPlan via design-tests for substantial new suite/gate architecture; obtain test_reviewer matrix approval. Record production root grant/key/bootstrap availability. If semantics differ, reopen design. No plan-only gate is a production approval.

## Owners, Contracts And Expected Files

Under memorii/memorii/: core/persistence/contracts.py; stores/sqlite/partition.py; core/memory_plane/sqlite_store.py; core/filesystem_storage/bundle.py; core/provider/factory.py; core/storage_administration/; pyproject.toml.

PartitionDataRepository, SqliteMemoryPlaneStore, signed control/genesis and full partition publication tuple/manifest; existing MemoryPlaneStore methods/CAS/governed policy preserved. Domain views share a transaction coordinator, not authority. Basic grants, fence order, complete snapshot verification and atomic old/new crash recovery are mandatory now.

Exact new symbols, payload/source-kind schemas, SQL catalogs, entrypoints and generated artifacts must match [identity ledger](../identity-and-changes.md) and approved design; expand the actual inventory before creating additional identifiers. [Bindings](../production_entrypoint_bindings.md) supplies current precursor -> proposed callsite/authority -> proof. Zero proposed callers cannot close this packet.

## Compatibility, Migration, Rollout And Rollback

Only explicit initialized/selected backend roots serve managed traffic. Preserve original domain APIs unless design declares the version boundary. No generic runtime grant, JSONL fallback, partial publication or speculative semantic truth. Relevant generation changes use exact old/new recovery and current control authority. Failed publication/validation leaves prior verified state; post-new-write downgrade requires tested compatibility or read_only forward repair. Release exposure stays limited until all allocated parent requirements close. Domain-specific obligations are in the contract above and [validation](../validation.md).

## Exact Validation Commands

Cwd memorii/. Interpreter is the CI-selected Python 3.11 or 3.12 environment from [gates](../gates.md), with editable `.[local,dev]` dependencies for local code tests. These **planned** new paths are not present/executed yet; create under linked approved test architecture, never add empty files just to make commands pass.

```bash
python -W error -m pytest tests/unit/core/test_sqlite_memory_plane_store.py -p no:cacheprovider
python -W error -m pytest tests/integration/test_partition_storage_recovery.py -p no:cacheprovider
python -m ruff check memorii tests
python -m memorii.tools.identity_hygiene --root .. --allowlist ../.agents/identity_hygiene_allowlist.json
pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"
```

Run existing owner regressions mapped in validation.md, then every applicable live-workflow gate once on the coherent candidate (do not replace broad required coverage with these focused commands). Additional same-family tests/files are inventoried before writing. Subprocess/package/host/migration matrices remain in explicit slower tiers. Capture cwd, interpreter/dependency/SQLite versions, warnings, environment, command, exit code, logs, exact base/head and dirty-tree status. Required external/OS cases cannot be inferred from local success.

## Proof, Maturity And Completion

Acceptance requires the observable journey plus applicable positive/negative/boundary/retry/concurrency/crash/revocation/compatibility cases in validation.md. Failures must be asserted at real public roots, with no leaked data or partial durable state. Evidence target: implemented and locally verified for the bounded slice; CI-enforced only with actual run evidence, independently reproduced only for a separately authored reducer, operationally verified only for pinned real host/platform/restore journeys. Present maturity: specified only; historical design probes remain separate.

At candidate freeze update live diff, identities, generated authority descendants, root callsites/arguments/caller counts and gates; run spec/correctness/test reviewers once for the coherent milestone. Reconcile all findings before sole-writer remediation. Record exact revision and `remaining_validated_p1_p2: []` only after proof, never prefill it. Any required missing external proof keeps that acceptance open. Parent requirements remain partial until [coverage](../coverage.md) aggregates all allocated packets and release gates.

## Non-Goals

No indexed retrieval replacement, legacy import, durable runtime graph or remote/extra-host support. Reject existing JSONL as migration_required; no production claim outside this bounded installed root.

## Progress, Review And Closure

Sub-slice 1 (2026-09-29, base fe9e1913): shared SQLite partition + memory-plane parity implemented. Added memorii/stores/sqlite/partition.py (PartitionDataRepository: WAL, synchronous=FULL, foreign keys, busy timeout, advisory file lock around short BEGIN IMMEDIATE/DEFERRED transactions; closed schema v1: memory_batches, memory_record_versions, memory_current_records with first-insertion order, memory_revision_state), memorii/core/memory_plane/sqlite_store.py (SqliteMemoryPlaneStore: full MemoryPlaneStore contract over the partition — canonical batch checksum codec reused unchanged, dual write/data revisions with the runtime-context visibility rule, precondition CAS, governed-policy gate, detached snapshots in first-insertion order, linearized reads, protected secrets 0o600, checkpoint signature authority claim, batch-chain validation cached per revision state with fail-closed tamper/desync rejection, append-only batches), stores/sqlite/__init__.py, and the sqlite parameter in the parameterized store-contract suite. New focused tests: tests/unit/core/test_sqlite_memory_plane_store.py (14 tests: fresh-handle reopen, both revisions, record versions retained, cross-handle visibility, first-insertion order across updates, filter parity vs in-memory reference, precondition atomicity, tampered batch/checksum/revision-state fail-closed on read and write, unknown future schema rejection, owner-only secret permissions, append-without-rewrite, two store views on one partition) and tests/integration/test_partition_storage_recovery.py (2 fresh-process subprocess journeys incl. cross-process CAS denial). Codec note: canonical record/batch serialization reuses the existing _PersistedBatch codec unchanged; the full semantic/ontology codec/projector inventory stays gated before the semantic-ontology packet per design sequencing. Evidence: ruff clean, pyright 0 errors, identity hygiene pass, 57 affected tests pass (contract suite 16→20 collected, ~3 s); commands run from memorii/ with .venv python 3.14 (CI-parity runs at candidate time). Known observation: one transient [memory]-parameter concurrency-test flake in the pre-existing in-memory store (passed 3/3 on re-run; not touched by this slice; watch at candidate). Production caller count for new paths remains 0 — factory wiring (build path from FilesystemStorageBundle/provider factory) is the next sub-slice with init/signed publication; this packet is not closed and no milestone review has run.
