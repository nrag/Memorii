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

Sub-slice 1 (2026-09-29, base fe9e1913, commit c0b60e48): shared SQLite partition + memory-plane parity. memorii/stores/sqlite/partition.py (PartitionDataRepository: WAL, synchronous=FULL, foreign keys, busy timeout, advisory file lock around short transactions; closed schema: memory_batches, memory_record_versions, memory_current_records with first-insertion order, memory_revision_state), memorii/core/memory_plane/sqlite_store.py (full MemoryPlaneStore contract over the partition — canonical batch checksum codec reused unchanged, dual write/data revisions with the runtime-context visibility rule, precondition CAS, governed-policy gate, detached snapshots in first-insertion order, linearized reads, protected secrets 0o600, checkpoint signature authority, cached batch-chain validation failing closed on tamper/desync, append-only commits), the sqlite parameter in the parameterized store-contract suite (16→20 collected), tests/unit/core/test_sqlite_memory_plane_store.py (14) and tests/integration/test_partition_storage_recovery.py fresh-process journeys. Known observation: one transient [memory]-parameter flake in the pre-existing in-memory store thread test (3/3 green on re-run; watch at candidate).

Sub-slice 2 (2026-09-29, commit 20fdad3b): closed persistence contracts (genesis/batch position union with the domain-separated empty-chain commitment, materialization manifest with ordered unique catalogs, partition revision vector, signed publication tuple, intent phases, control state, trust registry, chained control journal) with Ed25519 domain-separated signatures via the owner-only LocalSigningKeyOwner (0o600 permission-checked keys); ControlDatabase (owner-only, atomic record+journal transactions, chain enforcement, signature validation failing closed on open); partition publication row, canonical per-catalog row-digest fold, manual-commit transactions; StorageAdministrationService implementing owner-authorized init on verified-empty roots (atomic state+trust+journal+intent, empty-generation publish, finalize, stable duplicate receipt, foreign-root/symlink refusal), the recoverable two-owner publication protocol (publication fence, intent durable before data commit, finalize; exact-old abort / exact-new finalize / third-state quarantine) and Tier A/B verification with preserved-head row-tamper quarantine. Tests: tests/unit/core/test_storage_administration_contract.py (15, incl. both crash-boundary cuts and tamper quarantine) plus a dead-publisher fresh-process recovery journey.

Sub-slice 3 (2026-09-29, commit ac396abd): memorii/core/persistence/factory.py — closed legacy layout detection (hyphen/underscore plane spellings plus direct plane directory), fail-closed managed open (uninitialized refuses creating nothing; recognized layout => migration_required never creating a database beside old memory; mixed layouts => unsupported_configuration; orphan partition => integrity), verified open serving PublishedMemoryPlaneStore, the repository-scoped view routing every domain-owner write through the signed publication protocol (a bare-store write journey exposed exactly the independent-append gap the design prohibits, then verified the gate). FilesystemStorageBundle.from_managed_root over the verified partition with protocol-typed memory-plane field and unchanged auxiliary owners; legacy from_root unchanged. tests/unit/core/test_persistent_partition_factory.py (7) and the real semantic-owner conditional-write subprocess journey (internal-control visibility: data revision 0, write revision 2, verified publication).

Packet status: all three sub-slices landed; 71 focused tests green; ruff/pyright/identity gates green locally (Python 3.14 venv — CI-parity runs recorded at candidate); the full-unit-suite gate and the three-role milestone review are the remaining closure steps for this packet. Ontology activation/recovery on the selected backend is allocated to the semantic-ontology packet per the coverage ledger; provider-factory env-path and Hermes ingress wiring belong to that packet as well. Production-caller status: the managed factory and bundle roots now have real composition callers (open_managed_partition, from_managed_root) exercised through published-write journeys; the remaining named roots (provider env path, Hermes factories) are semantic-ontology scope.
