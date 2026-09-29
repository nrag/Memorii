# Semantic And Ontology Parity

- Parent WorkPlan: [implementation index](../implementation.plan.md)
- Work type: implementation milestone packet
- Delivery fidelity: Level 3, bounded slice only
- Status: active (sub-slice 1: managed selection + provider/Hermes/inspection ingress; indexed MemoryPlaneQuery reads, capture cells and wrapper branches remain)
- Requirements: DUR-05,07,15,16,17
- Dependencies: storage-foundation
- Baseline revision: bad9eeefb43f7f42fb95d583b11859e2f2ca9eb8 (planning snapshot)
- Implementation base: a8b8ed50; sub-slice head recorded per commit

## Observable Acceptance

Current filesystem/provider/Hermes source, structured fact, ontology and protected read paths use one selected partition; indexed results equal authorized scans while catalog history remains immutable.

## Owners, Contracts And Expected Files

Under memorii/memorii/: core/memory_evolution/atomic_store.py; core/memory_plane/service.py; core/semantic_ingestion/learned_relation.py; catalog_authority.py; catalog_capture_pin.py; core/provider/service.py; integrations/hermes_factory.py; hermes_local_authority.py; core/semantic_ingestion/production_capture.py.

Generate closed codec/projector inventory from installed owners; indexed canonical latest records and derived graph/catalog views; MemoryPlaneQuery/Page with authority-bound cursors; update all direct main/delegation/diagnostic constructors and complete detached-cohort read owners. Preserve original two revision counters, visibility, history, selection CAS, replay receipts and package authority.

Exact new symbols, payload/source-kind schemas, SQL catalogs, entrypoints and generated artifacts must match [identity ledger](../identity-and-changes.md) and approved design; expand the actual inventory before creating additional identifiers. [Bindings](../production_entrypoint_bindings.md) supplies current precursor -> proposed callsite/authority -> proof. Zero proposed callers cannot close this packet.

## Compatibility, Migration, Rollout And Rollback

Only explicit initialized/selected backend roots serve managed traffic. Preserve original domain APIs unless design declares the version boundary. No generic runtime grant, JSONL fallback, partial publication or speculative semantic truth. Relevant generation changes use exact old/new recovery and current control authority. Failed publication/validation leaves prior verified state; post-new-write downgrade requires tested compatibility or read_only forward repair. Release exposure stays limited until all allocated parent requirements close. Domain-specific obligations are in the contract above and [validation](../validation.md).

## Exact Validation Commands

Cwd memorii/. Interpreter is the CI-selected Python 3.11 or 3.12 environment from [gates](../gates.md), with editable `.[local,dev]` dependencies for local code tests. These **planned** new paths are not present/executed yet; create under linked approved test architecture, never add empty files just to make commands pass.

```bash
python -W error -m pytest tests/unit/core/test_memory_plane_query_parity.py -p no:cacheprovider
python -W error -m pytest tests/integration/test_shared_sqlite_provider_paths.py -p no:cacheprovider
python -m ruff check memorii tests
python -m memorii.tools.identity_hygiene --root .. --allowlist ../.agents/identity_hygiene_allowlist.json
pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"
```

Run existing owner regressions mapped in validation.md, then every applicable live-workflow gate once on the coherent candidate (do not replace broad required coverage with these focused commands). Additional same-family tests/files are inventoried before writing. Subprocess/package/host/migration matrices remain in explicit slower tiers. Capture cwd, interpreter/dependency/SQLite versions, warnings, environment, command, exit code, logs, exact base/head and dirty-tree status. Required external/OS cases cannot be inferred from local success.

## Proof, Maturity And Completion

Acceptance requires the observable journey plus applicable positive/negative/boundary/retry/concurrency/crash/revocation/compatibility cases in validation.md. Failures must be asserted at real public roots, with no leaked data or partial durable state. Evidence target: implemented and locally verified for the bounded slice; CI-enforced only with actual run evidence, independently reproduced only for a separately authored reducer, operationally verified only for pinned real host/platform/restore journeys. Present maturity: specified only; historical design probes remain separate.

At candidate freeze update live diff, identities, generated authority descendants, root callsites/arguments/caller counts and gates; run spec/correctness/test reviewers once for the coherent milestone. Reconcile all findings before sole-writer remediation. Record exact revision and `remaining_validated_p1_p2: []` only after proof, never prefill it. Any required missing external proof keeps that acceptance open. Parent requirements remain partial until [coverage](../coverage.md) aggregates all allocated packets and release gates.

## Non-Goals

No ontology grammar/model changes or reinterpretation of legacy catalog-less records; no graph page substituted for a required complete observation cohort.

## Progress, Review And Closure

Sub-slice 1 — managed selection and ingress (2026-09-29, base a8b8ed50): memorii/core/persistence/factory.py gains select_persistent_memory_plane — managed roots (initialized control) serve the verified published partition; legacy roots (a recognized pre-cutover plane, no control) serve their legacy JSONL plane until governed migration; managed+legacy coexistence, orphan partitions and empty roots are refused (allow_legacy_bootstrap=False default enforces no ephemeral store; True preserves the pre-cutover bootstrap behavior of legacy composition roots only). Wired: core/filesystem_storage/bundle.py::build_filesystem_provider selects managed from_managed_root vs legacy from_root; integrations/hermes_factory.py main memory-plane construction and the delegated authority_is_current recheck use the selection (the recheck now reads the current selected partition); integrations/hermes_local_authority.py::inspect_local_memory resolves the selected backend read-only (managed installations verified through open_managed_partition; missing state never initializes). Tests: tests/integration/test_shared_sqlite_provider_paths.py (packet-named): managed provider journey with verification and no JSONL, legacy provider unchanged, empty-root refusal, coexistence refusal, managed inspection with restart-safety and never-initialize, and a fresh-process provider composition round-trip. Evidence: 6 integration journeys green; 236 neighboring regression anchors green (scoped-context production binding, semantic provider composition, bundle, factory); ruff/pyright/identity gates green.

Sub-slice 2 — typed query contracts (2026-09-29): memorii/core/memory_plane/query.py defines the closed MemoryPlaneQuery (record_lookup and filtered_records kinds; finite domain/status/source-kind filters; page size default 100 max 500; extra=forbid) and MemoryPlanePage with an opaque HMAC-authenticated cursor (QueryCursorCodec, key from the installation protected-secret owner under purpose memory-plane-query-cursor) binding the query digest, both revision counters, the offset and a five-minute expiry — forged cursors, cursors from another query, and cursors crossing a publication revision boundary are rejected. SqliteMemoryPlaneStore.query_records serves bounded pages in first-insertion order via typed SQL selection (partition read path gained multi-value filters with limit/offset). tests/unit/core/test_memory_plane_query_parity.py (13 tests): every filter combination's paged walk equals the authorized list_records scan in identity and order, complete-set pagination, lookup semantics with filter eligibility, cursor forgery/stale-query/revision-change/expiry rejection, page-size bounds, and the visibility-rule note (revisions govern visibility, not query eligibility). Bounded deferral recorded: entity-neighborhood, evidence-link and catalog-history query variants and bounded time filters arrive with the derived semantic_* tables sub-slice (they select derived state that does not exist yet). Evidence: 13 parity tests plus the full store battery (80 tests across four files) green; ruff/pyright/identity gates green.

Sub-slice 3 — real semantic owner journeys (2026-09-29, commit fd0e0ff2): tests/integration/test_shared_sqlite_semantic_owners.py drives the unchanged governed source admission, writer-admission binding and atomic preplanning publication over the selected published partition — idempotent publication, three artifacts, signed ordinal advancing, verification green, no legacy plane, and full owner state surviving an independent fresh-process reopen. Evidence: 2 journeys plus the provider-path and partition-recovery batteries green; gates green.

Sub-slice 4 (in progress) — derived semantic tables reconnaissance: the typed graph (EntityRevision/ClaimAssertion) is NOT stored as records; it is projected by SemanticIngestionAtomicStore.graph_state_snapshot() via _semantic_replay_state_from(memory_plane) — canonical event records in the plane are the authority. Graph plan members are stored as records with source_kind semantic_ingestion_bootstrap_graph_v3_member, content {semantic_ingestion_kind, member: BootstrapGraphPlanAtomicMemberV3}; the member kind surface is a closed 12-value Literal with codec map BOOTSTRAP_GRAPH_V3_ATOMIC_MEMBER_CODECS and decoder decode_bootstrap_graph_atomic_member_payload_v3 (fail-closed envelope: schema, codec_key, payload; retired reductions rejected). The group effect chain is: member kind transaction_group_result decodes to BootstrapNativeGroupCommitTerminalConstructionV3 (contracts.py:13216, "store-owned reload bytes are the sole authority for the group effect") whose group_commit_reload: BootstrapGraphGroupCommitReloadV3 (contracts.py:13119) carries persisted_result: BootstrapGraphGroupCommitResultV3 — the graph effect carrier feeding the typed entity/claim state; verify its delta shape next. Derived-table plan: index rows carry canonical record id/digest + typed identity columns; the projector consumes the same replay projection authority (never a second decoder); maintenance in the publication transaction; rebuild-from-records must equal maintained state; the graph_state_snapshot public contract is the projection boundary. Next: confirm BootstrapGraphGroupCommitResultV3's delta fields (entity/claim/relationship revisions + validity intervals), then implement partition derived-table schema + projector + rebuild-equality + neighborhood/evidence/time query variants with parity against graph_state_snapshot scans.

Packet not closed; remaining: derived semantic/ontology typed tables and their query variants (in progress), provider read-path routing through the query surface, capture cells, wrapper branches, codec/projector inventory, and the milestone review cohort.

Additional concrete wrapper owners: integrations/authenticated_source.py::build_authenticated_source_runtime and integrations/hermes_provider.py::HermesMemoryProvider. Cover service-injection, memory-plane and storage-root branches with verified managed selection, outer callbacks, restart receipts and missing/wrong selector/control denial. Explicit diagnostic injections remain nonmanaged; no implicit fallback.
