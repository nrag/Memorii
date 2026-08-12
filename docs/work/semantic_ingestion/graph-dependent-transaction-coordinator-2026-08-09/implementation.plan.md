# Graph-Dependent Semantic Transaction Implementation

- Work ID: semantic-ingestion-graph-dependent-transaction-implementation-2026-08-10
- Work type: implementation
- Status: active
- Coordinator: Codex main thread
- Created: 2026-08-10
- Last updated: 2026-08-11
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/design.plan.md`; `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/testing.plan.md`; `docs/work/semantic_ingestion/source-normalization-authority-bundle-2026-08-10/design.plan.md`; `docs/work/semantic_ingestion/terminal-persistence-performance-2026-08-09/testing.plan.md`; `docs/work/semantic_ingestion/milestones/m3-semantic-pipeline.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md` SHA-256 `8cc2052243b440cdb5443702e63e0f4ad3f454225504de7026961433f949986e`; `docs/reviews/semantic-ingestion-graph-dependent-transaction-coordinator/final-approval-2026-08-10.md`; `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/production-entrypoint-bindings.json` SHA-256 `3cba90adbcf1e694465bef18ecddd8536070fa42b0e56c6a177ee13087bc53c5`
- Expected outputs: production-reachable graph-dependent Steps 5--8 coordinator, strict persistence and recovery, deterministic evidence, CI topology, and revision-bound independent closure review

## Objective

Implement the approved graph-dependent semantic transaction chain through the
ordinary provider composition roots. Accepted graph-bound outcomes must publish
and reload their source alignment, graph snapshot-derived planning closure,
complete attempt authorization, append-only lineage, graph/event effects, and
terminal result without fabricated or optional authority.

## Completion Contract

Complete only when GTC-R01 through GTC-R13 are reachable through direct,
factory, filesystem, and Hermes roots; the exact in-memory and filesystem
positive, adversarial, conflict, lost-acknowledgement, restart, replay, and
resource-bound families pass; the dedicated graph workflow topology and paired
terminal handoff validate; every changed authority chain and workflow-selected
local job is current; and frozen specification, correctness, and test reviews
record empty `remaining_validated_p1_p2`, `remaining_blocks_approval`, and
`remaining_changes_required` arrays.

## Scope

Included: the approved GTC-R01--R13 behavior, contracts, repositories,
coordinator orchestration, provider composition, terminal/replay binding,
feature-local tests, committed collection/timing topology, identity hygiene,
and current-state documentation.

Excluded: M4 conflict presentation and winner policy, terminal-persistence
performance optimization, new learned extraction behavior, external signing,
retrieval, ranking, and answer generation.

Deferred: hosted GitHub execution evidence until a reviewable pushed revision
exists. Local workflow-equivalent evidence remains required.

## Constraints And Invariants

- Preserve raw, semantic, execution, and solver state as separate domains.
- Preserve candidate versus committed state and append-only event/plan history.
- Validate current tenant, principal, scope, fence, and lease authority before
  every sensitive read, reservation, publication, CAS, or replay exposure.
- The pure compiler performs no repository lookup, allocation, persistence, or
  retry.
- A graph-bound success has a complete store-reloaded plan, authorization,
  attempt, lineage, result, and manifest chain; absence fails closed before
  graph effect and cannot use the legacy terminal fallback.
- Use one writer for overlapping production, test, workflow, and plan changes.

## Approved Baseline And Drift Disposition

The final design approval freezes the canonical architecture at SHA-256
`8cc2052243b440cdb5443702e63e0f4ad3f454225504de7026961433f949986e`, the
binding map at SHA-256
`3cba90adbcf1e694465bef18ecddd8536070fa42b0e56c6a177ee13087bc53c5`, and
Git HEAD `4691c0374b3b01617a6a50fd83d4e3ff8a61aa84`. Those hashes reproduce.
The current design WorkPlan hash is
`61a08a82949534d918ebe9a53af4234e172c713ae85dd0f414c5203f3a51d2a0`, while
the v9 delta identity records
`b28ddddfd24ed04e83c4aa9acb829b38f2a2a7feb6840ee2dbf6200330282674`.
The final approval report identifies the latter as the reviewed plan baseline,
and the current plan's post-review progress, evidence disposition, status, and
next-action entries are administrative closure only. This implementation uses
no semantic statement absent from the hash-matching architecture and approved
final report. Any later semantic conflict reopens design and blocks writing.

## Identity And Coordinate Hygiene

GTC-R01--GTC-R13 and M3.1 are planning/evidence coordinates. They may occur
only in this WorkPlan, review reports, and typed traceability metadata. New
modules, symbols, tests, fixtures, workflow jobs, artifacts, diagnostics, and
persisted values use behavioral or genuine protocol identities. The field-aware
identity gate and representative mutations are required before candidate freeze.

| Surface | Identity | Class | Disposition | Proof |
| --- | --- | --- | --- | --- |
| WorkPlan and review metadata | GTC-R01--GTC-R13, M3.1 | planning/evidence | retain only here | field-aware identity gate |
| Coordinator | `SemanticIngestionTransactionCoordinator` | behavioral | retain and extend canonical owner | production binding map |
| New repositories and artifacts | names derived from snapshot, planning, attempt, lineage, commit, replay behavior | behavioral/protocol | accept only after durability audit | identity ledger plus mutations |
| Dedicated workflow owner | `graph-dependent-semantic-ingestion` | behavioral | implement approved machine ID | workflow topology tests |

## Changed-Surface Ledger

The baseline tree is already dirty with active semantic-ingestion work. Those
paths remain parent or linked-operation owned unless this operation explicitly
edits them; overlapping edits are then recorded here and attributed by hunk.

| Path or pattern | Surface class | Scope owner | Authority chain | Required gates | Status |
| --- | --- | --- | --- | --- | --- |
| `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/implementation.plan.md` | implementation WorkPlan | this operation | plan -> evidence/review | WorkPlan audit | active |
| `memorii/memorii/core/memory_evolution/atomic_store.py` | product code | this operation | architecture -> native group CAS -> provider roots | focused/unit/integration/static | implemented and focused-verified |
| `memorii/memorii/core/semantic_ingestion/` | contracts/repositories/persistence | shared parent plus this operation by hunk | contracts -> codecs -> repository -> replay | focused/unit/integration/static | implemented and focused-verified |
| `memorii/memorii/core/provider/`, `memorii/memorii/core/filesystem_storage/bundle.py`, `memorii/memorii/integrations/hermes_provider.py` | composition | shared parent plus this operation by hunk | composition -> coordinator -> durable outcome | root mutation tests | implemented and four-root verified |
| `memorii/tests/unit/core/semantic_ingestion/`, `memorii/tests/integration/` | tests | this operation for graph selectors | requirement -> observable -> mutation | focused and workflow-selected | closure matrix implemented; final gates pending |
| `.github/workflows/pr-gates.yml`, `memorii/tests/ci/` | workflow/gate artifacts | this operation plus linked performance handoff | selectors -> manifest -> receipts -> aggregate | topology/self-tests | pending |

## Authority-Chain Ledger

| Chain | Canonical owner | Required downstream closure | Status |
| --- | --- | --- | --- |
| approved architecture -> typed contracts/codecs | semantic-ingestion contracts | exports, strict decode, vectors, identity gate | implemented and focused-verified |
| admitted source -> sealed alignment/groups | provider ingestion and source-normalization repository | same-generation reload, request digest, policy | implemented and restart-verified |
| alignment -> snapshot/reconciliation/compilation | built-in graph execution builder and coordinator | artifacts, plan publication/reload | implemented and four-root verified |
| plan -> authorization -> attempt -> lineage | graph planning and checkpoint repositories | authorized reread, progress, recovery | implemented and lost-ack verified |
| lineage -> CAS/event/result | native group commit and terminal persistence owners | exactly-once result, manifest, replay | implemented and memory/JSONL verified |
| test selectors -> collection manifest -> receipts -> aggregate | graph workflow topology | timing inventory and terminal residual handoff | pending |

## Production Entrypoint Bindings

The Spark preflight at Git HEAD `4691c037...` reproduced the ordinary root and
the zero-caller gaps. Exact search commands are recorded in the Evidence Log.

| Requirement | Trigger/root | Callsite and authority | Owner chain | Proof/caller count | Status |
| --- | --- | --- | --- | --- | --- |
| GTC-R01--R02 | `ProviderMemoryService.sync_event` -> `ProviderIngestionCoordinator.ingest` | admitted/prepared source, ingress, fence, lease, policy | normalize -> publish/reload -> native alignment/groups | one ordinary production caller; exact recovery reload proved | implemented |
| GTC-R03--R06 | provider ingestion after native normalization | ingress/scopes/fence/lease/snapshot | authority projection -> compile -> publish/reload plan | built-in caller shared by all four roots | implemented |
| GTC-R07--R11 | reloaded plan closure | current authority plus exact plan/artifacts | authorize -> attempt -> lineage -> native group CAS/result/replay | one coordinator caller; accepted effect and lost-ack proofs pass | implemented |
| GTC-R12--R13 | factory, filesystem bundle, and Hermes roots -> provider service | concrete non-injectable production graph bundle | root -> coordinator -> typed outcome | all four normal signatures reject the fixture builder and execute the built-in path | implemented |

Packet-2 graph-free derivation is locally implemented only. Its canonical
pipeline intermediate has no ordinary provider caller, so GTC-R01--R02 retain
their zero-caller `not implemented` binding status.

## Validation Matrix

| Behavior | Strongest proof | Defect/failure signal |
| --- | --- | --- |
| same-generation normalization closure and deterministic grouping | unit plus strict codec/mutation matrix | graph reader remains untouched on missing, extra, foreign, duplicate, or reordered authority |
| one snapshot and complete reconciliation/closure | coordinator unit/property matrix | second read, cross-token, missing extension/reservation, scope substitution rejects before CAS |
| pure compilation and fixed complete plan | unit, independent fixed vectors, repository round trip | hidden lookup, incomplete group union, artifact/certificate substitution rejects |
| authorization, attempt, and append-only lineage | unit plus restart/lost-ack matrix | provisional/empty/cross-plan authority and overwritten lineage reject |
| CAS, conflict, partial commit, recovery, replay | integration in-memory and filesystem | wrong effect count, changed committed authority, or visibility before validated replay |
| root reachability and no fallback | direct/factory/filesystem/Hermes mutation tests | missing coordinator yields typed non-commit and zero graph effect |
| limits, diagnostics, and no disclosure | N-1/N/N+1 and tenant A/B variants | silent truncation or target identifier disclosure fails |
| identity and workflow topology | field-aware mutations, collection/receipt/aggregate self-tests | planning identity accepted or skipped/failed producer yields green aggregate |

### Requirement-To-Evidence Allocation

Every row requires the ordinary `ProviderMemoryService.sync_event` trigger for
its accepted-path proof. Lower-level tests supplement that root proof; they do
not replace it. Direct, factory, filesystem, and Hermes roots each run an
accepted graph-bound case and caller-removal, omitted-authority, legacy-fallback,
and cross-tenant/no-disclosure mutations.

| Requirement | Named test owner | Production trigger and durable observable | Required mutations and failure signal | Required gate |
| --- | --- | --- | --- | --- |
| GTC-R01 | `test_graph_dependent_transaction_coordinator.py` and root integration | `sync_event` reloads one exact same-generation normalization closure | missing, extra, duplicate, foreign-generation, substituted, partial, reordered, or live-rebuilt member; zero graph read | graph-dependent semantic ingestion |
| GTC-R02 | `test_graph_dependent_transaction_coordinator.py` and root integration | `sync_event` reloads the complete deterministic operation/group bijection | omitted/duplicate operation, unstable order, graph-influenced grouping; zero graph read | graph-dependent semantic ingestion |
| GTC-R03 | `test_graph_dependent_transaction_coordinator.py` and root integration | one complete-source snapshot token/scopes/fence binds every downstream member | second/live read, cross-token, missing scope, stale fence/lease; typed noncommit and zero reservation/CAS | graph-dependent semantic ingestion |
| GTC-R04 | `test_graph_dependent_transaction_coordinator.py` and root integration | reloaded attempt contains complete typed reconciliation/reservation/closure and read-set extensions | missing extension/reservation/closure, token or tenant substitution; zero CAS and no target identifier | graph-dependent semantic ingestion |
| GTC-R05 | coordinator unit, independent compiler vectors, root integration | pure compiler output is published/reloaded with exact artifacts and certificates | hidden lookup/write/allocation, artifact/certificate/group substitution; no plan/attempt publication | graph-dependent semantic ingestion |
| GTC-R06 | `test_transaction_group_plan_repository.py`, coordinator unit, root integration | root-reached fixed complete plan is atomically published and authorized-reloaded | empty, partial, duplicate, reordered, cross-snapshot/tenant, opaque/null/sentinel plan; no planned progress | graph-dependent semantic ingestion |
| GTC-R07 | coordinator unit and root integration | complete reload-derived authorization bijection is embedded in one persisted/reloaded attempt before use | empty/provisional/post-mutated, missing/extra/wrong-group/repository/plan/snapshot/union-arm authority; no CAS/result | graph-dependent semantic ingestion |
| GTC-R08 | coordinator unit and memory/JSONL integration | append-only lineage retains committed authority and replaces only unfinished groups | overwrite, fork, broken predecessor, regroup committed group, wrong reused/replacement/final-no-authority arm | graph-dependent semantic ingestion |
| GTC-R09 | `test_graph_dependent_semantic_ingestion.py` memory/JSONL matrix | reloaded lineage entry authorizes exactly-once graph/event CAS | unrelated write accepted by read set; first related conflict suffix replan; second conflict, stale owner, retry exhaustion fail closed | graph-dependent semantic ingestion |
| GTC-R10 | terminal persistence unit plus root integration | each group and source result binds the final reloaded lineage/attempt/plan/authorization/artifacts/delta/event/manifest bijection | null/empty/sentinel/fabricated/incomplete binding, wrong no-authority proof; no success-shaped result | graph-dependent semantic ingestion plus paired terminal handoff |
| GTC-R11 | memory/JSONL restart and replay integration | reopen returns byte-identical result/effects from persisted authority only | crash after source closure, plan/artifacts, attempt, lineage, CAS/event/result; corruption/addition/omission/reorder/gap/cross-repository rejects before visibility | graph-dependent semantic ingestion |
| GTC-R12 | `test_semantic_provider_composition.py` plus root integration | direct/factory/filesystem/Hermes roots mandatorily traverse the complete coordinator chain | remove coordinator/caller/authority arg or enable legacy fallback; typed noncommit, zero graph read/reservation/CAS, no disclosure | graph-dependent semantic ingestion |
| GTC-R13 | coordinator unit, root integration, receipt topology tests | one persisted policy/counter chain binds attempts, lineage, results, manifests, replay, and bounded diagnostics | N-1/N/N+1 for every limit, fingerprint/counter/replay mismatch, silent truncation, raw source/target identifier disclosure | graph-dependent semantic ingestion |

### Lifecycle, Compatibility, And Topology Matrices

- Run every publication-boundary failure after source closure, plan/artifact /
  certificate closure, attempt, lineage, CAS/event, and result in both memory
  and JSONL stores. Reopen must return byte-identical authority/results or reject,
  never republish a same-purpose authority, and preserve exactly-once effects.
- Exercise unrelated write, first related conflict with suffix-only replan,
  second related conflict termination, stale-owner takeover, retry exhaustion,
  and all reused-predecessor, replacement-successor, and final-no-authority arms.
- Preserve typed pre-graph evidence-only, rejected, and unresolved outcomes with
  zero graph effect. Reject opaque, missing, null, empty, and sentinel legacy
  graph plans before disclosure. Permit only the explicitly registered legacy
  `retry_exhausted` terminal migration. Test rollback before and after the first
  committed group in memory and JSONL; rollback forbids new promotion and
  preserves/replays already committed history.
- Before graph tests are added, create the exclusive ordered selector manifest,
  derived collection count, three producer receipts, immutable 270-second
  ceiling, sole timing inventory, aggregate dependency, and same-revision
  residual terminal-topology handoff. Mutations remove a selector, create
  selector overlap, stale a receipt, skip/fail/cancel a producer, remove the
  aggregate dependency, or change a count; none may yield green aggregation.

### Frozen Graph Gate Topology Before Coding

The implementation owns exactly 26 non-parameterized collected nodes. The
committed manifest path is
`memorii/tests/ci/graph-dependent-semantic-ingestion.json`; its ordered
selectors and derived count are:

1. Eight nodes in
   `tests/unit/core/semantic_ingestion/test_graph_dependent_transaction_coordinator.py`:
   `test_provider_source_authority_reloads_complete_generation_before_graph_read`,
   `test_source_groups_are_complete_deterministic_and_graph_free`,
   `test_snapshot_reconciliation_uses_one_current_authority_binding`,
   `test_pure_compilation_publishes_complete_authorized_plan`,
   `test_attempt_is_complete_persisted_and_reloaded_before_lineage`,
   `test_append_only_lineage_preserves_committed_authority_during_replan`,
   `test_execution_policy_limits_and_counters_fail_closed`, and
   `test_cross_tenant_authority_rejects_without_disclosure_or_graph_calls`.
2. The four existing nodes in
   `tests/unit/core/semantic_ingestion/test_transaction_group_plan_repository.py`:
   `test_repository_reads_only_the_exact_atomic_plan_member`,
   `test_repository_rejects_wrong_repository_or_ambiguous_plan_id`,
   `test_repository_loads_the_plan_published_with_the_planned_checkpoint`, and
   `test_checkpoint_member_uses_the_typed_plan_payload_when_supplied`.
3. Four nodes in
   `tests/unit/core/semantic_ingestion/test_semantic_provider_composition.py`:
   `test_direct_root_requires_graph_coordinator_before_terminal_persistence`,
   `test_factory_root_requires_graph_coordinator_before_terminal_persistence`,
   `test_filesystem_root_requires_graph_coordinator_before_terminal_persistence`,
   and `test_hermes_root_requires_graph_coordinator_before_terminal_persistence`.
4. Four nodes in
   `tests/unit/core/semantic_ingestion/test_semantic_terminal_persistence.py`:
   `test_graph_bound_terminal_requires_reloaded_authority_bijection`,
   `test_graph_bound_terminal_rejects_legacy_plan_markers_before_effect`,
   `test_graph_bound_terminal_preserves_committed_history_during_rollback`, and
   `test_graph_bound_terminal_replay_rejects_substituted_closure_before_exposure`.
5. Six nodes in
   `tests/integration/test_graph_dependent_semantic_ingestion.py`:
   `test_memory_store_executes_graph_bound_source_exactly_once`,
   `test_filesystem_store_reopens_graph_bound_source_byte_identically`,
   `test_publication_boundary_failures_resume_without_republishing_authority`,
   `test_related_and_unrelated_graph_conflicts_follow_bounded_replan_policy`,
   `test_authority_arms_preserve_committed_and_noncommitting_history`, and
   `test_migration_and_rollback_preserve_only_authorized_history`.

The topology owner is a behavioral validator under
`memorii.tools.semantic_ingestion_graph_gate`. Its static and `--self-test`
commands run from `memorii/`:

```bash
python -m memorii.tools.semantic_ingestion_graph_gate --manifest tests/ci/graph-dependent-semantic-ingestion.json --unit-manifest tests/ci/unit-shards.json --terminal-manifest tests/ci/semantic-terminal-persistence-shards.json --workflow ../.github/workflows/pr-gates.yml
python -m memorii.tools.semantic_ingestion_graph_gate --manifest tests/ci/graph-dependent-semantic-ingestion.json --unit-manifest tests/ci/unit-shards.json --terminal-manifest tests/ci/semantic-terminal-persistence-shards.json --workflow ../.github/workflows/pr-gates.yml --self-test
python -W error -m pytest $(python -m memorii.tools.semantic_ingestion_graph_gate --manifest tests/ci/graph-dependent-semantic-ingestion.json --print-selectors) -p no:cacheprovider
```

The three producer job IDs are `graph-dependent-semantic-ingestion`,
`graph-dependent-semantic-ingestion-measurement-b`, and
`graph-dependent-semantic-ingestion-measurement-c`; the sole consumer is
`graph-dependent-semantic-ingestion-receipt-aggregate`. The consumer is the
only graph dependency added to `semantic-ingestion`. It validates A/B/C
receipts at the three approved artifact paths, publishes only
`memorii/tests/ci/graph-dependent-semantic-ingestion-timing-inventory.json`,
and cannot publish unless all producers succeeded at the current revision.
All 26 nodes are removed from `unit-shards.json`; the four terminal nodes are
also removed from `semantic-terminal-persistence-shards.json`. The linked
terminal performance WorkPlan must acknowledge and recalculate its residual
152-node historical count against the live collection in the same revision;
the live regenerated count, not 152, becomes authoritative if unrelated
pending test changes have already altered that baseline.

## Milestones

| Behavioral slice | Requirements | Observable result | Status |
| --- | --- | --- | --- |
| Source authority and graph preparation | GTC-R01--R04, part of R12--R13 | ordinary ingress publishes/reloads alignment/groups and obtains one authorized graph-derived reconciliation closure | complete |
| Planning authorization and lineage | GTC-R05--R08, part of R13 | pure compilation publishes/reloads a complete plan, then a complete attempt and initial append-only lineage | complete |
| Graph commit, terminal binding, and recovery | GTC-R09--R11, remainder of R12--R13 | direct and reopened stores produce exactly-once effects and byte-identical typed results or fail closed | complete |
| Verification topology and branch closure | all | exclusive graph selectors, receipts, aggregate, paired terminal handoff, broad gates, and independent review pass | active |

## Gate Ledger

| Job/gate | Exact local command | Required | Result |
| --- | --- | --- | --- |
| graph topology static/self-test | the two `memorii.tools.semantic_ingestion_graph_gate` commands frozen above | yes | not run |
| graph producer selection | the exact 26-node manifest command frozen above, with `-W error -p no:cacheprovider` | yes | not run |
| field-aware identity hygiene | `cd memorii && python -m memorii.tools.identity_hygiene --root .. --allowlist ../.agents/identity_hygiene_allowlist.json` | yes | not run |
| unit suite | `cd memorii && python -W error -m pytest tests/unit -p no:cacheprovider` | yes | not run |
| Ruff | `cd memorii && python -m ruff check memorii tests` | yes | not run |
| Pyright | `cd memorii && pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"` | yes | not run |
| workflow topology and selected graph jobs | derived from current `.github/workflows/pr-gates.yml` after topology implementation | yes | not run |

## Delegation And Cost Ledger

| Task | Role/tier | Ownership | Direct consumer | Status |
| --- | --- | --- | --- | --- |
| production entrypoint preflight | `code-mapper` / Spark | read-only | binding ledger and writer packet | complete; coordinator validated root order and zero-caller gaps |
| pre-coding validation matrix review | `test_reviewer` / Terra | read-only | validation matrix | complete after two targeted rechecks; no open pre-coding matrix finding |
| implementation slice | `worker` / Terra | sole writer | source-authority and graph-preparation milestone | ready to dispatch |
| frozen milestone reviews | spec/correctness/test reviewers / Terra | read-only | milestone closure | pending |

## Current State

Verified: the architecture and binding artifact reproduce their approved
hashes; existing contracts and a narrow snapshot coordinator exist; the
ordinary provider path has no complete graph-dependent chain; the workflow has
no dedicated graph job. The tree is dirty at Git HEAD `4691c037...`; initial
status SHA-256 is
`7b3eafd0355145a828a418cbeb5a0f3c55ddd5c20a538088b7f4bb111cdddd74`.

Interpretation: this is a multi-milestone implementation. The first writer
slice must end at a real provider caller and durable/reloadable graph-preparation
outcome; contract-only additions cannot close it.

## Assumptions And Open Questions

- Verified fact: the approved architecture resolves the public, persisted,
  authorization, retry, compatibility, and policy semantics.
- Working assumption: existing atomic generation primitives can host each new
  repository without a parallel transaction subsystem; the writer must prove
  this through the canonical store.
- Unresolved implementation question: exact existing owners reusable for the
  graph snapshot/reconciliation protocols; the preflight and writer inspect
  before adding abstractions.
- External decisions: none currently.

## Progress Log

- 2026-08-10: Created the separate implementation WorkPlan required by the
  approved design and initialized scope, identity, authority, binding,
  validation, gate, and delegation ledgers.
- 2026-08-10: Reproduced approved architecture and binding-map hashes. Recorded
  the post-approval design-plan hash drift and constrained the implementation
  baseline to the hash-matching architecture plus final approval report.
- 2026-08-10: Started the required Spark production-entrypoint preflight and
  pre-coding test-matrix review. The test reviewer correctly blocked review of
  an unfrozen current design-plan hash; no semantic or test-matrix finding was
  asserted. Coordinator classified this as a governance evidence action and
  recorded the narrower immutable baseline above.
- 2026-08-10: Reconciled the Spark preflight. The production chain is factory /
  filesystem / Hermes -> `ProviderMemoryService` ->
  `ProviderIngestionCoordinator` -> four terminal persistence callsites. The
  existing transaction coordinator has one identity-lineage caller but none
  from provider ingestion. Source alignment, source grouping, graph attempt,
  group authorization, source plan lineage, and production plan publication
  each have zero provider callers; optional plan persistence is the live bypass.
- 2026-08-10: Reconciled five pre-coding verification findings. Added the
  mechanical GTC-R01--R13 trigger/observable/mutation/gate allocation, four-root
  accepted and attack matrix, finite memory/JSONL publication-failure matrix,
  conflict and authority-arm matrix, compatibility/rollback fixtures, and
  exclusive graph receipt/topology mutations. These are bounded evidence and
  conformance actions, not new product semantics.
- 2026-08-10: Closed the remaining CI-topology planning delta with the exact
  26-node selector universe, three producer IDs, sole receipt consumer,
  manifest and inventory paths, ownership transfers, aggregate edge, and
  executable static/self-test/pytest commands. Node names are behavioral and
  contain no planning or requirement coordinates.
- 2026-08-10: The test reviewer closed the pre-coding matrix after the second
  targeted recheck. The tests, manifest, validator, and workflow remain pending
  implementation evidence, not an unresolved test-design choice.
- 2026-08-10: Source-authority/graph-preparation writer resumed after
  coordinator review. The approved design assigns the concrete repository and
  adapter choices to implementation; the absent production owners are the
  intended first-vertical implementation gap, not a semantic blocker. The
  writer is adding those owners without deriving authority from a terminal
  outcome.
- 2026-08-10: Packet-1 contract writer completed the source-alignment schema
  replacement preflight. The canonical delta requires every retired v1 and
  singular-temporal direct consumer to be removed, while the assigned surface
  owns only the declarations and atomic base. Live consumers outside that
  surface still import and construct the retired contracts. Marked the parent
  requirement allocation partial and paused before creating an invalid
  compatibility bridge; coordinator split/expansion is required.
- 2026-08-10: Coordinator expanded packet-1 ownership through the direct
  consumer boundary. The first strict migration now carries schema version 2
  through source-local identity, operation alignment, dependency groups,
  parser/scope/temporal consensus leaves, and a role-keyed temporal set; the
  legacy singular temporal field and unversioned payload are rejected. Focused
  contract, group-plan, and repository tests pass. The exhaustive producer
  request/result/manifest and atomic 15-category closure remain partial.
- 2026-08-10: Packet-2 replaces the stale source-alignment input boundary with
  role-keyed source scope/temporal observations and route-bound pre-partition
  identity evidence. It derives exact two-analyzer consensus, role-complete
  temporal closure, conservative identity components, operation joins,
  coverage, and singleton groups without graph or terminal input. Focused
  codec migration and derivation tests pass. Publication/reload and provider
  composition remain outside this packet.

## Evidence Log

- Git HEAD and merge base: `4691c0374b3b01617a6a50fd83d4e3ff8a61aa84`.
- Initial dirty-tree status digest: `7b3eafd0355145a828a418cbeb5a0f3c55ddd5c20a538088b7f4bb111cdddd74`.
- Approved design report: `docs/reviews/semantic-ingestion-graph-dependent-transaction-coordinator/final-approval-2026-08-10.md`.
- Existing canonical coordinator: `memorii/memorii/core/memory_evolution/transaction_coordinator.py`.
- Existing optional plan persistence: `memorii/memorii/core/semantic_ingestion/persistence.py`.
- Preflight search anchors: `rg -n "build_provider_memory_service_from_env|build_provider_memory_service|HermesMemoryProvider" memorii/memorii`; `rg -n "def sync_event|def apply_memory_write|ingest\\(" memorii/memorii/core/provider`; `rg -n "persist\\(|authorization_verifier=|recover_terminal_artifact|recover_execution_plan|checkpoint_recovery_authority_binding" memorii/memorii/core/{provider/ingestion.py,semantic_ingestion/persistence.py}`; and `rg -n "SemanticIngestionTransactionCoordinator|_coordinator.execute\\(|SourceProposalAlignment|GraphDependentValidationAttempt|TransactionSemanticGroupPlan" memorii/memorii/core`.
- 2026-08-10 writer preflight: `rg -n 'class GraphSemanticSnapshotBundle|class ReconciliationResult|class ReferenceClosureSnapshot|class GraphDependentExecutionPolicy|class GraphDependentCoordinatorRequest|class GraphDependentCoordinatorResult' memorii/memorii docs/design/semantic_ingestion_architecture.md docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/design.plan.md` found all named graph-bound coordinator shapes only in the architecture/design documents except an unrelated identity-lineage coordinator instantiation. `rg -n 'SourceProposalAlignment\\.create|SourceDependencyGroup\\.create' memorii/memorii --glob '*.py'` found no production constructor. This is the implementation gap being closed by this slice; `ProviderIngestionCoordinator` must not treat its legacy terminal persistence path as graph-bound authority.
- 2026-08-10 packet-1 boundary preflight: the approved architecture section
  3.4.2d--f requires stable schema-version-2 names only and rejects a v1/V2
  bridge. `rg -n "AtomicGenerationMember\\(|SourceProposalAlignment|SourceDependencyGroup|SemanticScopeConsensus|TemporalAttachmentConsensus" memorii/memorii --glob '*.py'` identifies active uses outside the assigned writer surface, including `semantic_ingestion/pipeline.py`, `semantic_ingestion/persistence.py`, and `semantic_ingestion/transaction_group_plan_repository.py`. No source or test edits were made, and no test command was run, because a declarations-only edit would deliberately leave active callers on rejected shapes.

## Decision Log

- 2026-08-10: Use the hash-matching canonical architecture and final approval
  report as the frozen semantic baseline. Treat later design-WorkPlan closure
  text as administrative only. Consequence: any missing semantic detail blocks
  implementation rather than being inferred from the drifted plan.
- 2026-08-10: Implement as four behavioral vertical slices. Each production
  slice must end in an ordinary composition-root caller and durable outcome.

## Review Log

- Pre-coding test review: one `Not applicable` / `blocks_approval` /
  governance-verification finding for design-plan candidate hash drift.
  Coordinator disposition: confirmed evidence mismatch, not a product or
  semantic defect; remediation eligibility `evidence_action`. The immutable
  semantic baseline and drift constraint are now explicit. A fresh matrix
  review is required against this WorkPlan before coding.
- Refreshed pre-coding test review: five `Not applicable` /
  `changes_required` / verification, authorization, lifecycle, compatibility,
  and CI-topology findings. Coordinator disposition: confirmed bounded
  `evidence_action` and `contract_conformance_action`; no product-semantic
  remediation. The Requirement-To-Evidence and lifecycle/topology matrices now
  address every requested delta. Targeted recheck is pending.
- First targeted recheck: four findings closed; CI topology remained
  `Not applicable` / `changes_required`. Coordinator disposition: confirmed
  `contract_conformance_action`. The frozen 26-node graph topology now supplies
  the missing exact path-to-gate contract; second targeted recheck pending.
- Second targeted recheck: remaining CI-topology finding closed. No
  pre-coding `blocks_approval` or `changes_required` finding remains.

## Known-Failure Ledger

None established for this operation. Historical parent and linked testing
failures are not exclusions until reproduced at the merge base with the same
causal signature.

## Blockers And Limits

- Current blocker: implementation packet 1 combines the schema-v2 replacement
  with every active consumer of the retired schema, but its assigned writer
  surface excludes those consumers. The approved architecture requires that
  no v1/singular-temporal type, codec registration, or direct consumer remain
  active; the live v1 types are imported and constructed by `pipeline.py`,
  `persistence.py`, `transaction_group_plan_repository.py`, and the existing
  graph/terminal test owners. Replacing only `contracts.py` and
  `atomic_store.py` would leave those production consumers either importing
  retired names or constructing rejected payloads, violating the strict
  no-bridge requirement before a production caller exists. This is an
  ownership-boundary blocker, not a semantic ambiguity. Split the replacement
  at the non-overlapping consumer boundary, or authorize this packet to own
  the listed consumers and their focused migration tests.
- Resolved boundary: packet ownership now includes the direct consumer and
  fixture migration boundary. Remaining work is implementation, not a scope
  blocker.
- 2026-08-10 source-normalization publication boundary: added
  `AtomicStoreSourceNormalizationRepository` and its typed
  `SourceNormalizationStage` handoff. It accepts only the sealed specialized
  atomic request, writes through the atomic checkpoint owner, and returns only
  the exact same-generation reloaded result. The checkpoint allowlist now
  recognizes the closed source-normalization member family. Focused repository
  and request-closure tests passed (12), along with Ruff, `py_compile`, and
  `git diff --check`.
- Current blocker: the approved request requires a prepared source, proposal
  run, linguistic analysis bundle, predicate-event inventory, temporal
  resolution, policy bundles, publication coordinate, and graph-free
  interpretation bundle. The live pipeline only yields source analyses and an
  existing terminal-shaped result; it has no producer for those sealed request
  inputs. Wiring the provider now would require synthetic authority or terminal
  reconstruction, both prohibited by the approved design.
- 2026-08-10 normalization-stage packet: added the explicit typed
  `GraphFreeSourceNormalizationInputs`/`GraphFreeSourceNormalizationStage`
  boundary. It verifies the source/run/analysis/temporal/coordinate/fence/
  lease joins, derives graph-free alignment, creates the sealed request,
  manifest, result, and exact ordered atomic member closure, then delegates
  only to the reloading atomic publisher. It has no provider, graph, terminal,
  or configuration lookup.
- 2026-08-10 correction selection remediation: `ConsensusPolicySelection`
  and its bundle are strict schema-version-2 contracts with the complete
  `(kind, operation, proposal, segment, route, temporal_role)` coordinate and
  V2 digests. Parser/scope selections require a null role; temporal selections
  require one exact role. The normalization stage derives and proves the exact
  ordered parser/scope/temporal selection closure from every graph-free
  subject, including both `replacement` and `transition` for a correction.
  Focused evidence: 65 selected tests passed; Ruff, `py_compile`, and
  `git diff --check` passed. The vectors cover two-role correction acceptance
  and missing, duplicate, swapped, and unknown-role closures rejecting before
  alignment/publication.
- 2026-08-10 provider-root wiring: `ProviderIngestionCoordinator` now invokes
  a typed `GraphFreeSourceNormalizationRuntime` after prepared-source
  validation and before `SemanticIngestionPipeline.run` or terminal
  persistence. The runtime binds the pure stage to a host-owned
  `GraphFreeSourceNormalizationInputsProvider`; its absence, a substituted
  prepared source, or a rejected sealed closure returns the typed
  `source_alignment_authority_unavailable` source-only outcome and bypasses
  terminal persistence (including reconciliation). The local built-in runtime
  intentionally has no such producer yet: it fails closed rather than
  reconstructing request inputs. Focused provider-root tests prove the absent
  authority has no terminal control and an injected authority is invoked before
  the existing terminal path. Ruff and `py_compile` pass. The stage/repository
  packet separately proves atomic publication and same-generation reload; an
  integrated success cannot be claimed until a real complete-input producer is
  composed.
- Review cadence: one full reviewer cohort per coherent milestone, targeted
  delta review after bounded remediation, and one fresh whole-branch cohort.
- Hosted CI cannot establish evidence until a pushed reviewable revision exists.

## Historical Next Action (Superseded 2026-08-10)

Complete the certified local Duckling runtime and adapter, then bind all four
selected lane manifests into the route/profile release before composing the
complete graph-free input producer. Until that closure is present, production
must continue to return the typed `source_alignment_authority_unavailable`
non-commit for this route.

### Certified Parser Adapter Update (2026-08-10)

- The local analyzer optional dependency closure now pins `numpy>=1.26,<2`,
  `torch==2.2.2`, `stanza==1.14.0`, `spacy==3.8.14`, and the immutable
  `en-core-web-hf-trf` release URL with its wheel SHA-256. Package data ships
  the reviewed Stanza and spaCy model-file inventories and distribution hashes.
- `linguistic_adapters.py` verifies every declared local asset before import,
  disables Stanza download behavior, lazily imports both runtimes, and emits
  only `LinguisticAnalysis` contracts with exact source coordinates. Manifest,
  language, coordinate, asset, and resource failures return no analysis.
- Stanza `1.14.0` under Torch `2.2.2` cannot load its reviewed serialized
  model through `weights_only=True`. The adapter therefore applies a locked,
  construction-local `torch.load` wrapper only after complete asset
  verification. It accepts only exact manifest-listed paths beneath the asset
  root, rehashes the target immediately, forces `weights_only=False`, rejects
  file-like/outside/changed targets, and restores the original loader in a
  `finally` block. Full unpickle is justified solely by this closed verified
  model-byte boundary; any unlisted global/model remains unavailable.
- Focused adapter checks pass (9 tests), including fake independent lane
  normalization, real local model asset verification, tamper/path/file-like
  rejection, loader restoration, concurrent construction serialization, and
  bounded-input classification. A real Stanza smoke run completed with one
  normalized `complete` analysis containing two tokens and two dependency arcs.
- The failed `en_core_web_hftrf` release is replaced by the official
  `en_core_web_trf==3.8.0` wheel, SHA-256
  `272a31e9d8530d1e075351d30a462d7e80e31da23574f1b274e200f3fff35bf5`,
  together with `spacy-curated-transformers==0.3.1`,
  `curated-transformers==0.1.1`, and `curated-tokenizers==0.0.9`. Its reviewed
  local inventory verifies and direct smoke parsing reports `nsubj`, `ROOT`,
  `dobj`, and `punct` for `Alice owns Atlas.`. The observed peak RSS is about
  2.63 GB, so the production composition owner must reserve at least that
  ceiling before attempting this lane and otherwise retain a typed
  resource-unavailable outcome. The adapter enforces a 4096-character input
  limit and reports `resource_limit_exceeded`, `resource_exhausted`, or
  `analysis_timeout` as a non-authoritative local failure reason while
  returning no analysis. No smaller-model fallback is permitted.

### Built-in Producer Blocker (2026-08-10)

The approved bootstrap route cannot currently construct
`GraphFreeSourceNormalizationInputs` without fabricating authority. The
ordinary `GraphFreeSourceNormalizationInvocation` carries only the prepared
source, source authority/interval evidence, policy bundle, authorization
read-set provider, operation identifier, and fence. Its required result also
needs: (1) a complete `SemanticProposalRun` and its V2
`PreAlignmentSemanticOperationSubjectSet` expansion; (2) a
`LinguisticAnalysisBundle`, `PredicateEventInventory`, and
`TemporalResolution`; (3) complete raw primary/corroborating
`AnalyzerScopeObservation` and `AnalyzerTemporalAttachmentObservation` rows
and a total `SourceLocalIdentityPartitionEvidence` mention universe; (4)
complete consensus selections and paired language/construction authorities;
and (5) a publication coordinate, lease, writer-commit binding, progress,
generation expectations, temporal/trust/capability snapshots, and
graph-dependent execution policy.

No production constructor for that closure exists. The built-in
`ProductionLocalSemanticAnalyzer` currently emits legacy `SemanticCandidate`
and `IndependentSourceAnalysis` values only. Its
`GraphFreeAnalyzerOutput` contains role/status strings, not the V2 raw
interpretation, attachment, identity, proposal-run, policy, or publication
authorities. `build_authorized_local_semantic_runtime` only composes an
explicitly injected `GraphFreeSourceNormalizationInputsProvider`; it cannot
derive the missing authorities. Canonical architecture Section 3.4.2 forbids
reconstructing those inputs from terminal output, graph/provider hints,
canonical identity, capability selection, or live policy/time lookup. The
architecture additionally states that the local analyzer must add the explicit
bundle outputs before source normalization is callable. Therefore a built-in
success path now would violate the approved design; the safe maximum is the
existing fail-closed runtime boundary.

Required resumption input: an approved bounded implementation design that
assigns canonical producers for the complete V2 proposal, analyzer,
policy/snapshot, and publication-authority closure, or host-provided certified
instances of all listed typed values. Once supplied, compose that producer
through factory/filesystem/Hermes roots and add the specified positive
publication/reload tests.

#### External certified-artifact coordinates required for resumption

The missing dependency is not satisfied by installing Python packages. The
architecture requires the following selected and certified coordinate closure:

| Lane | Required selected/certified authority | Current repository state |
| --- | --- | --- |
| Primary syntax | Stanza `1.14.0`, the exact local language model/package files, processor configuration, adapter version, license record, content hashes, and one `AnalyzerManifest` whose digest equals the selected route's `stanza_analyzer_manifest_digest` | Neither dependency nor adapter/module, model asset, manifest, hash inventory, or resource binding is present. |
| Corroborating syntax | A separately configured pinned spaCy `en_core_web_trf`-class local pipeline, exact package/model files, processor configuration, adapter version, license record, content hashes, and one distinct `AnalyzerManifest` whose digest equals the selected route's `spacy_analyzer_manifest_digest` | Neither dependency nor adapter/module, model asset, manifest, hash inventory, or resource binding is present. |
| Predicate detection | The language-owned lexical/morphological manifest and implementation whose digest equals each selected route's `predicate_event_manifest_digest` | No implementation or certified manifest is present. |
| Temporal resolution | A pinned local Duckling sidecar or embedded binary, checksum/license/runtime configuration, resolver adapter, and manifest whose digest equals each selected route's `temporal_resolver_manifest_digest` | No sidecar/binary, adapter/module, manifest, or resource binding is present. |
| Route/profile release | `SegmentLanguageResourceBinding` values carrying the four exact lane manifest digests, plus regenerated/externally verified bootstrap profile/release/anchor material that binds them | Current bootstrap profile binds preparation and the legacy local analyzer only; it does not contain these four certified lane coordinates. |

The expected artifact/dependency categories are therefore: two Python runtime
libraries, at least two local model/pipeline asset sets, one local temporal
runtime or binary, adapter modules, content-addressed analyzer/predicate/
temporal manifests, route resource-binding bytes, bootstrap profile/release/
trust-anchor regeneration, license/provenance records, and deterministic
offline conformance corpus outputs. Exact package distribution versions and
file hashes for the spaCy model and Duckling runtime are intentionally absent
from the architecture; choosing them here would be a new external semantic
decision rather than implementation.

Smallest user decision needed: approve provisioning one audited, offline,
checksummed English artifact bundle that names the exact spaCy model release
and Duckling distribution/binary (including licenses and content hashes), then
authorize the linked implementation of the required adapters, manifests, and
bootstrap-release binding. Until that bundle exists, this work remains
correctly fail-closed; an ambient download, unpinned package, or regex stand-in
cannot satisfy the required independent-analyzer contract.

## Outcome And Retrospective

Active; provider-root reachability now fails closed through a typed authority
boundary, but the milestone remains incomplete pending the real complete-input
producer and its integrated publication/reload evidence.

### Duckling Sidecar And Adapter Update (2026-08-10)

- The reviewed local sidecar recipe is now owned at
  `memorii/containers/duckling/`: immutable Debian Bookworm builder/runtime
  digests, Duckling commit
  `59a13ff87b1aa8be6b93d387244f8636b26185c5`, Stack `3.9.3` tar digest,
  required GMP/PCRE/zlib dependencies, MIT notice, and a no-network runtime
  requirement are explicit. The recipe intentionally records no fabricated
  OCI result digest; `build-local.sh` emits the locally produced digest for
  release attestation.
- `DucklingTemporalResolver` is a loopback-only, manifest-coordinate-bound
  adapter under the canonical semantic-analysis temporal owner. It accepts one
  sealed selected segment plus explicit locale/timezone and authenticated
  reference evidence, converts Duckling UTF-8 byte offsets into exact scalar
  source spans, and emits one typed `TemporalResolution` only for strict
  unambiguous instant responses. Bad coordinates, non-loopback endpoints,
  malformed/offset-splitting output, unsupported values, timezone mismatch,
  reference-less relative text, and transport errors return no authority; it
  has no network or parser fallback.
- Focused fake-sidecar tests prove byte-offset conversion, ambiguity and
  unsupported-value rejection, endpoint/coordinate admission, and unbuilt
  image-digest status (`6 passed`), with Ruff, `py_compile`, and diff checks
  passing. The optional live smoke remains unavailable until the local image
  digest is attested and the sidecar is launched with network disabled.

## Design-Pause Update (2026-08-10)

The user approved the explicit trusted-host source-normalization authority
boundary. The linked design operation at
`docs/work/semantic_ingestion/source-normalization-authority-bundle-2026-08-10/design.plan.md`
is now the sole detailed owner of the packet contract, attack matrix, and
approval evidence. This implementation WorkPlan is blocked pending that design
candidate's required independent review. It must not add a producer, packet,
proposal-run path, or composition binding until the linked design is approved.

The design's reviewed remediation additionally freezes the mandatory handoff
runtime signature, preparation-bound publication coordinate, ephemeral
complete-lane reservation, revision-bound entrypoint map, and identity-gate
repair. These remain design-owned prerequisites until its remediated candidate
is approved.

## Next Action

Resume this WorkPlan only after the linked authority-bundle design completes;
then create the required production-entrypoint map and implement its approved
provider-owned authority producer without fabricating any input.

### V3 Recovery Owner Progress (2026-08-10)

- The provider coordinator now probes the persisted bootstrap V3 recovery key
  before calling the transient authority provider. `found` reloads retained
  bytes, while only `claimed` reaches the execution owner.
- The execution owner accepts the explicit claim, renews it before proposal,
  reservation consumption, every external lane, and publication, and attaches
  the latest claim to the V3 stage request. An aborted renewal produces a
  typed non-commit with no subsequent external effect.
- The host bundle exposes the atomic claim repository and trusted dual clock;
  the evidence owner receives the renewal gate and checks it immediately
  before Stanza, spaCy, predicate, and temporal lane effects.
- Focused V3 recovery repository tests passed (`6 passed`), as did `ruff`,
  `py_compile`, and diff hygiene. The old normal-vector tests intentionally
  still target the removed V2 owner signature and require their planned V3
  replacement.
- Remaining implementation prerequisite: no canonical bootstrap analysis
  route binding/projection was present for declared bootstrap routes. The
  initial strict binding/set contracts were added, but the full proposal and
  analyzer contract migration is not complete; normal bootstrap promotion
  therefore remains blocked rather than fabricating generic route authority.

### V3 Graph-Dependent Boundary Pause (2026-08-11)

- The ordinary selected bootstrap path now publishes and reloads only
  `BootstrapSourceNormalizationResultV3`. Its sealed alignment is
  `BootstrapSourceProposalAlignmentV3`, with
  `BootstrapSourceDependencyGroupV3` members and scalar bootstrap-analysis
  provenance. The V3 contract deliberately has no generic-route or V2
  reconstruction boundary.
- The approved graph-dependent coordinator request, snapshot/planning
  contracts, and current `SemanticIngestionTransactionCoordinator` all accept
  the V2 `SourceProposalAlignment` and `SourceDependencyGroup` family. No
  native V3 graph-dependent request, validation-attempt, transaction-plan,
  planning-authorization, or lineage contract exists. The corresponding
  constructors have zero production callers.
- Converting the V3 alignment into V2, inventing a graph input from terminal
  output, or retaining the legacy terminal persistence path would violate the
  V3 authority boundary and could create a committing path without the
  required graph-bound authority. This operation therefore makes no production
  wiring change at this boundary.
- Blocker: a linked design amendment must define the native V3 graph-dependent
  authority/request/attempt/plan/lineage closure and its exact host-injected
  graph snapshot, reconciliation, reservation, compiler, and terminal handoff
  providers. After approval, resume with one mandatory provider-root caller
  and update the production-entrypoint binding map from zero to the observed
  caller count.

## Next Action (2026-08-11)

Await the linked native-V3 graph-dependent design amendment; do not bridge or
reconstruct V2 authority from the bootstrap V3 closure.

### Native V3 Contract Slice Progress (2026-08-11)

- The approved amendment is now available. The first contract slice adds the
  strict codec-registered native V3 replay record, graph snapshot/policy
  references, graph authority, control epoch and transition result family,
  coordinator request, initial graph attempt, group-plan member/plan,
  planning authorization, lineage/final-result references, and replan
  partition. These contracts reject generic V2 input and bind their nested V3
  replay/alignment authority before graph work.
- Remaining in this implementation milestone: successor four-arm authority,
  append-only lineage/progress, terminal result/handoff/reload, graph atomic
  member/write/reload repository ports, memory/JSONL persistence proof, and
  only then provider-root composition. The production binding remains zero
  callers until the complete family can be published and reloaded together.

### Native V3 Atomic Store Slice (2026-08-11)

- Added the dedicated V3 graph checkpoint grammar in
  `SemanticIngestionAtomicStore`: sealed member records, a generation manifest,
  idempotency index, control CAS, and byte-for-byte reload. It does not reuse
  the generic atomic-generation member grammar.
- Added append-only control-epoch transition/find persistence and thin V3
  atomic-store repository ports for plan, attempt, lineage, retry, and terminal
  checkpoint kinds. Every port receives current ingress, scope, fence, lease,
  writer, and epoch authority; no provider composition has been changed.
- Focused proof: dedicated V3 graph member tests cover payload tampering plus
  incomplete member rejection in both in-memory and JSONL stores; combined V3
  contract/repository checks passed (`16 passed`). `py_compile`, Ruff, and
  diff hygiene also passed for the changed owners.
- This is only a persistence slice. The ordinary provider-root binding remains
  zero production callers and therefore remains `partial`, not an M3.1
  completion claim. The next action is to add the coordinator/terminal callers
  and the memory/JSONL graph recovery matrix against these owners.
- Terminal-handoff locator gap: `BootstrapGraphTerminalPersistenceHandoffV3`
  contains no atomic write-request digest, publication generation, manifest
  identity, or canonical member locator. A `persist_and_reload(handoff, ...)`
  port cannot safely discover a terminal checkpoint from the handoff alone
  without scanning or inferring across tenant records. The implemented atomic
  repository can publish/reload a terminal checkpoint when given its sealed
  `BootstrapGraphPlanAtomicWriteRequestV3`; the handoff-only terminal port is
  intentionally deferred until the approved contract adds an exact locator.

### Terminal Locator Contract Slice (2026-08-11)

- The approved terminal core, nine-kind publication-intent registry, terminal
  control, post-publication write identity, and expanded terminal reload
  contracts are now strict codec records. The atomic-store terminal port
  authenticates current ingress/scope/fence before its exact locator lookup and
  can reload a found terminal using the terminal-control completed-lease proof;
  it never scans a generation or falls back to generic terminal persistence.
- The absent-publication CAS remains blocked by a contract-to-owner gap: the
  sealed handoff carries only prepublication digests. No current coordinator or
  repository owns the nine typed construction carriers, their stable member
  coordinates, canonical source-result input, or a sealed publication request.
  Constructing final bytes from digest text or scanning unrelated graph records
  would violate the approved design. The smallest correction is a dedicated
  typed terminal-publication request (or exact typed carrier repository) that
  supplies the complete prepublication member construction closure to the port.
- This slice remains partial with zero production callers. Its next action is
  the linked coordinator/publication-request design correction before adding
  the memory/JSONL lost-ack and absent-CAS matrix.

### Terminal Effect Foundation Pause (2026-08-11)

- The v26 terminal publication request requires strict typed graph-revision,
  canonical-source-outcome, observation-delta, and semantic-event carriers.
  Production currently has only unrelated legacy semantic delta types; the
  architecture's recursive graph-effect contract family has no canonical code
  owner yet. A separate non-overlapping writer now owns that foundation.
- This terminal-store slice is paused after the stable v22 exact-locator found
  recovery work. It must not introduce opaque payloads, duplicate event-batch
  models, or speculative graph-effect contracts. Resume only after the shared
  typed foundation lands, then implement the v26 absent-CAS and recovery proof.

### Terminal V28 Atomic Publication Slice (2026-08-11)

- `SemanticIngestionAtomicStore.persist_bootstrap_graph_terminal_v3` now takes
  only the sealed `BootstrapGraphTerminalPublicationRequestV3`, materializes
  the exact nine-kind terminal member closure, and writes the operation
  control, members, terminal manifest, terminal control, write identity, and
  exact locator index in one conditional write. The found path reads only the
  locator then validates every immutable join and member byte payload; it does
  not scan generations.
- The absent branch verifies ingress/scope/fence/lease/writer/epoch current
  authority before operation-control lookup. The found branch accepts only the
  original completed lease retained in control, so a later owner cannot replay
  a historical locator with a substituted lease.
- Focused existing dedicated V3 store tests passed in both in-memory and JSONL
  modes (`5 passed`); `py_compile` and Ruff passed. This is still a persistence
  owner slice with **zero production callers**: no provider-root/coordinator
  wiring was authorized, so it remains partial and is not an M3.1 completion.
- Remaining evidence gap for this slice: a fully strict sealed terminal
  request builder is not yet available in this WorkPlan's unit-test fixtures;
  the next owner must add the lost-ack/released-lease/effect-mutation matrix
  through the now-canonical sealed terminal port before claiming runtime
  readiness.

### V33 Generation Snapshot and Receipt Slice (2026-08-11)

- Replaced caller-supplied V3 generation scalars with the sealed
  `BootstrapGraphCurrentGenerationV3` predecessor snapshot. The store now
  derives the successor generation only after validating current control,
  and returns a reload core plus checkpoint receipt carrying the exact
  predecessor/successor chain. Terminal reloads carry the same receipt shape.
- Added the repository current-generation read boundary and updated the pure
  graph assembler checkpoint APIs to accept a predecessor snapshot. This is
  still unbound from the coordinator/provider root (zero production callers),
  so it is a contract/persistence slice rather than M3.1 completion.

### V40 Coordinator Closure Slice (2026-08-11)

- The native coordinator now derives the complete pre-execution manifest
  identity closure after lineage reload, binds each identity digest into its
  group CAS request, writes/reloads final-stage evidence after all group
  results, and supplies the final evidence receipt successor plus the exact
  V40 preparation inputs. It no longer reads a nonexistent compilation
  manifest-construction field.
- This sequencing owner remains unbound from provider roots; production caller
  count remains zero and runtime completion is not claimed.

### V40 Post-Effect Recovery Correction (2026-08-11)

- `BootstrapGraphDependentCoordinatorV3` now treats a failed group-result or
  final-evidence checkpoint acknowledgement after a completed group CAS as a
  post-effect condition: it retains the exact group construction, publishes and
  reloads `BootstrapGraphDurableRetryProgressV3`, and recovery returns that
  sealed retry rather than allowing the provider to erase lifecycle state as
  `graph_transaction_authority_unavailable`.
- A terminal-port acknowledgement failure is now found-first recovered through
  the canonical terminal request index. A committed terminal reload returns the
  same finalized coordinator result; only an absent terminal falls back to the
  durable retry closure.
- The production caller remains the shared `BootstrapGraphHostBundle.execute`
  path used by the direct, factory, filesystem, and Hermes provider roots. The
  binding ledger records that path and the post-effect authority threading.
- Focused proof is `test_bootstrap_graph_post_effect_recovery.py`: injected
  group-CAS-to-checkpoint and terminal-CAS-to-ack failures each preserve the
  exact reloaded retry/final state with no second executor CAS in both memory
  and reopened JSONL stores. This is a bounded recovery correction, not M3.1
  completion.

### Exact V3 Recovery Replay Reload (2026-08-11)

- Added `reload_bootstrap_recovery_replay_v3`: an exact recovery-key index and
  sealed-generation reload which revalidates canonical request/result bytes and
  constructs `BootstrapRecoveryReplayRecordV3`; it has no ambient scan or
  reconstruction fallback. Focused direct-provider proof covers in-memory and
  JSONL publication/reload plus foreign-key rejection.
- The fixture owner now exposes a strict exact-replay carrier whose current
  ingress/fence/lease/writer/epoch authority is supplied explicitly rather
  than discovered by scan.
- The graph fixture now has typed transition and coordinator-request builders
  which recompute request-core digests and fail closed on replay, authority, or
  epoch substitution.
- Historical next action (completed): add coordinator happy/retry fixtures through the typed builders.

### V30 Artifact Assembler Foundation (2026-08-11)

- Added `BootstrapGraphGroupExecutionResultV3` as the closed v30 execution
  boundary and changed group-result construction to embed that one result,
  preventing independent CAS/effect substitutions.
- Added the pure `BootstrapGraphArtifactAssemblerV3` owner for sealed group
  CAS/result/construction/retry artifacts, atomic checkpoint members, initial
  and authorized-lineage checkpoint requests, and terminal-publication request
  precondition joins. It performs no repository or coordinator work.
- Focused deterministic substitution proof passes (`3 passed`); scoped Ruff
  and diff hygiene pass. This is a partial construction slice: it has zero
  production callers and does not establish coordinator/root reachability.

### Graph-Effect Contract Foundation (2026-08-11)

- Added the cycle-safe leaf module
  `memorii.core.memory_evolution.graph_effect_contracts` with strict frozen,
  content-addressed `GraphRecordMutation`/`GraphRevisionDelta`,
  `CanonicalSourceTerminalOutcomeRecord`, and
  `IngestionObservationRecordMutation`/`IngestionObservationDelta` types.
  The module imports authority carriers but no terminal store, coordinator, or
  replay owner; it does not relocate the already canonical
  `SemanticMemoryEventBatch` from `event_replay` because no import cycle or
  duplicated public contract was needed.
- The local graph-effect codec is exported by the leaf module. Focused
  construction/mutation proof passes (`2 passed`), as do scoped Ruff,
  compilation, and diff hygiene. No terminal-store, coordinator, or
  composition caller changed; the production-entrypoint binding remains zero.
- Historical next action (completed): add the remaining architecture-defined event payload/batch and
  terminal-publication carriers to this same leaf family before the paused
  terminal-store owner resumes its v26 absent-CAS work.

### V26 Terminal Carrier Continuation (2026-08-11)

- Added strict V3 observation, graph, event, not-applicable, CAS-request,
  CAS-outcome, result-construction, and canonical-source-result carriers to
  the semantic-ingestion codec registry. Payloads remain concrete shared
  graph-effect/event-batch models; no opaque carrier dictionaries were added.
- The pre-existing `graph_effect_contracts` import path re-entered
  `reference_integrity` while `contracts` initialized. Its models now resolve
  their concrete collaborators through the explicit
  `rebuild_bootstrap_graph_effect_contracts()` boundary once the replay owner
  is loaded. Focused import/rebuild proof and the graph-effect contract tests
  pass (`3 passed`), along with scoped Ruff and diff hygiene.
- This is partial: terminal absent-CAS publication, locator/control/index
  construction, and repository/store found-or-publish wiring remain unimplemented.
  The production-entrypoint binding remains zero callers.

### V31 Coordinator Authority Pause (2026-08-11)

- The coordinator cannot safely implement the requested sequence beyond the
  pre-graph authority cut with the currently sealed contracts. The compiler
  contract identifies `BootstrapGraphPlanCompilationV3`, but does not carry the
  current operation/artifact predecessor generation required by the assembler's
  plan checkpoint. That generation is mutable store state and must be supplied
  by a current-authority reload/handoff; deriving it from a lease state revision
  would be an unapproved inference.
- The completed per-group executor result is
  `BootstrapGraphGroupExecutionResultV3`. After the group loop, the terminal
  port requires a sealed `BootstrapGraphTerminalPublicationRequestV3`, whose
  manifest, handoff core, publication intent, handoff, and completed canonical
  source outcome are not present in the compiler, authorizer, executor-result,
  or coordinator-request closure. A coordinator must not fabricate those
  terminal carriers or introduce an unreviewed preparation port.
- Safe correction landed: pre-graph noncommit now derives its required
  `reason_digest` under the coordinator reason domain rather than supplying a
  placeholder. Focused proof passes for the no-producer, zero-write transition
  mismatch cut. Runtime binding remains zero; this is not a coordinator
  implementation completion.
- Required design handoff: define (1) a typed current-generation checkpoint
  authority carrying exact operation/artifact predecessor generations and
  current ingress/scope/fence/lease/writer/epoch joins, and (2) a typed
  terminal-preparation authority carrying the exact execution manifest,
  terminal core, intent, handoff, canonical outcome core and completed record
  required to construct `BootstrapGraphTerminalPublicationRequestV3` after the
  per-group results are sealed.

### V33 Coordinator Resume Check (2026-08-11)

- The current-generation snapshot/receipt contracts and repository load port
  now exist. The terminal-preparation port, however, currently accepts an
  already sealed `BootstrapGraphTerminalPublicationRequestV3` and merely
  validates a separately supplied host authority before wrapping it in
  `BootstrapGraphTerminalPreparationV3`. It does not accept coordinator
  attempt/plan/lineage/group-result inputs or construct the publication
  request described by the binding ledger.
- `BootstrapGraphDependentCoordinatorRequestV3` likewise contains no
  `BootstrapGraphTerminalHostAuthorityV3`; the graph authority lacks the
  terminal segment-governance/message-admission carriers required by that
  host authority. The typed per-group execution result contains no terminal
  host authority or complete terminal construction closure.
- Therefore the full initial chain cannot call the current terminal-preparation
  port without either fabricating host authority, inventing a second port, or
  treating a prebuilt terminal request as executor output. Each would violate
  the frozen typed-boundary requirement. The exact missing contract or its
  canonical module location is required before this coordinator slice resumes.

### V37 Terminal Preparation Completion (2026-08-11)

- The terminal-preparation owner now derives the execution manifest, ordered
  group results, canonical outcome core and completed record, canonical input
  and result, handoff core, nine-kind member-intent closure, publication intent,
  handoff, and sealed terminal publication request from typed inputs only.
  Terminal-handoff member intent binds the acyclic handoff-core digest; the
  atomic materializer validates that same core digest rather than creating a
  handoff/intent cycle.
- Corrected the canonical outcome factory to derive its required core ->
  outcome-id -> source-result -> record sequence. Graph terminal result digests
  retain final-plan order; generic evidence-only outcomes with no graph group
  results remain valid. The canonical input now binds the nested execution
  result digests rather than incompatible result-construction wrapper digests.
- Focused contract and preparation authority-substitution tests pass (`6
  passed`), as do scoped Ruff, compilation, and diff hygiene. This remains a
  construction-only slice with no coordinator or ordinary provider-root caller.

### Coordinator Fixture Slice C (2026-08-11)

- Added the strict one-group fixture compiler and authorizer around the V40
  plan-compilation builder. The authorizer constructs the exact public
  `BootstrapGroupPlanningAuthorizationV3` and set from the retained plan,
  epoch bindings, and persisted checkpoint authority; an unavailable executor
  likewise returns a public closed V3 producer-unavailable carrier after
  validating current ingress/scope/epoch joins. The fixture also now projects a
  prepared source and operation fence into a typed terminal-host authority.
- Focused fixture proof passes (`3 passed`), with scoped Ruff, `py_compile`,
  and diff hygiene passing. This is only the compiler/authorization/retry
  fixture foundation, not coordinator persistence evidence: a strict
  `BootstrapGraphDependentCoordinatorRequestV3` still requires a persisted
  `BootstrapRecoveryReplayRecordV3`, and there is no strict fixture producer
  for that record in the current tree. Existing source-normalization fixture
  construction uses `model_construct`, which is prohibited for this slice, so
  it cannot be used to bridge the gap.
- Historical next action (completed): add or identify a public-constructor replay fixture from a
  sealed source-normalization result, then exercise the real epoch repository,
  plan repository, atomic store, and coordinator for durable retry before
  attempting the terminal-success closure.

### Coordinator Fixture Slice C Follow-up (2026-08-11)

- The direct-provider replay reload fixture was identified and used. It proves
  canonical `reload_bootstrap_recovery_replay_v3` works without a construction
  bridge, so the earlier replay-fixture absence note is superseded.
- The real coordinator retry setup now fails at the next authority boundary:
  direct-provider `sync_event` completes source normalization and leaves the
  shared preplanning control terminal with no lease. The graph control-epoch
  transition requires the same operation fence plus a live exact lease, and
  the atomic-store lease acquisition path correctly rejects terminal controls.
  The focused coordinator test records this exact `operation has no active
  lease` failure before any graph checkpoint write.
- Required decision/implementation boundary: expose an authenticated replay
  fixture before source-normalization terminalization, or define a distinct
  graph control/lease ownership sequence. Neither can be supplied by a
  post-terminal replay reload without fabricating current authority.

### Execution-Manifest Closure Remediation (2026-08-11)

- `BootstrapGraphDependentCoordinatorV3` now derives final source/segment and
  transaction-group stage outcomes solely from the retained request, epoch,
  host authority, final attempt, lineage, and group constructions. The
  terminal preparation recomputes the same projection and rejects substituted
  final-stage evidence before it creates `IngestionExecutionManifest`.
- Failed group execution records `graph_compilation` as failed, later group
  stages and source-summary persistence as explicitly blocked, and derives
  exact causal blockers. Committed and noncommitting results retain complete
  or evidence-only terminal stages respectively. Every stage artifact digest
  is epoch- and closure-bound; no ambient store read or prepared-source
  mutation is used.
- Focused static proof passes: `py_compile`, scoped Ruff, and `git diff
  --check`. The direct provider-backed coordinator success/repeat command was
  restarted after this remediation; its long-running terminal result remains
  to be captured before this repository-only chain can be promoted beyond
  local implementation evidence. The binding map records this as zero ordinary
  provider callers, so no enabled runtime behavior is claimed.

### Initial V40 Vertical Closure (2026-08-11)

- The strict direct-provider fixture now proves both initial coordinator
  outcomes over the real atomic repositories: host executor unavailability is
  persisted and reloaded as durable retry, while the successful path persists
  the complete nine-member terminal closure and returns the typed terminal
  reload.
- Terminal persistence now uses an explicit member-kind-to-digest mapping,
  registers the retained lineage/group-result codecs, admits only the complete
  terminal control/member/manifest/identity/locator closure, and decodes the
  stored strict JSON representation without weakening the in-memory model.
- Lost-ack replay is durable and effect-free. The terminal CAS writes an exact
  coordinator-request index in the same atomic batch; a repeat authenticates
  that index and returns the persisted terminal reload before epoch, planning,
  authorization, or group execution. The focused successful test asserts the
  executor call count remains one.
- Focused evidence: coordinator retry + success/lost-ack and strict fixture
  suite, `5 passed in 164.02s`; scoped `py_compile` and Ruff pass.
- This closes the repository-level initial-attempt vertical only. Production
  callers remain zero until the host graph authority/producer bundle is wired
  through the shared provider coordinator.

## Superseded Exact Next Action (2026-08-11)

Wire the mandatory V3 graph host bundle and coordinator invocation into the
shared normal provider path before generic terminal persistence, then prove
direct/factory/filesystem/Hermes reachability and fail-closed bundle omission.

### Production Composition Progress (2026-08-11)

- Added the host-owned `BootstrapGraphHostBundleBuilder` and
  `BootstrapGraphDependentAuthorityProviderV3` boundary. The built-in local
  runtime, direct service, environment factory, filesystem bundle, and Hermes
  adapter now carry the same graph bundle against the same atomic store.
- `ProviderIngestionCoordinator._run_semantic_ingestion` is now the production
  caller after exact V3 normalization replay and before generic pipeline or
  terminal persistence. It supplies the persisted replay, prepared source,
  current ingress/scopes/fence/lease/writer to the host provider and calls the
  returned `BootstrapGraphDependentCoordinatorV3` directly. A completed graph
  terminal skips the generic terminal writer; a partial or unavailable graph
  bundle fails closed with `graph_transaction_authority_unavailable`.
- Direct public-root execution reaches the complete terminal CAS (`1 passed in
  51.36s`). All four composition roots carry the identical graph host bundle
  (`4 passed in 35.13s`). Missing graph authority performs zero graph-member
  writes (`1 passed in 25.63s`).

## Superseded Exact Next Action (2026-08-11)

Superseded by the current action below. Exact graph-terminal recovery from a
source-normalization Found replay is implemented and the fresh independent
JSONL service proof returns the persisted terminal before normalization lanes
or graph execution.

### Per-Group Durability Progress (2026-08-11)

- The coordinator now persists and reloads each complete typed group-result
  construction before another group can execute. Every later group, retry, and
  final-evidence checkpoint consumes only the store-issued successor generation
  receipt, closing the prior stale-generation and orphan-effect window.
- The append-only lineage validator now accepts successor history only when
  every per-group predecessor digest names that group's immediately preceding
  entry; its latest projection is derived from the final entry per group.
- The focused successful terminal/lost-ack case passes after the additional
  group checkpoint (`1 passed in 42.67s`), and the durable-retry repeat remains
  accepted (`1 passed in 39.38s`). Scoped Ruff and diff hygiene pass.
- Durable retry checkpoints now retain the complete attempt, plan,
  authorization, lineage, completed group-result construction, and progress
  closure. An exact request-keyed index is written in the same atomic batch;
  recovery validates the index -> idempotency -> manifest -> member chain and
  returns the byte-identical progress before compiler, authorizer, or executor.
- Independent JSONL evidence passes: a fresh filesystem service returns the
  same durable retry with zero source-normalization lane calls and zero graph
  executor calls (`1 passed in 86.75s`). The generic terminal lease reader now
  recognizes the disjoint graph checkpoint manifest and does not attempt to
  decode it as a generic generation.
- Successor construction has begun at the pure boundary: the assembler now
  builds the canonical all-replacement first-conflict partition, strict
  predecessor-lineage references, successor attempt authority/attempt, and an
  append-only successor lineage whose per-group predecessor links are
  validated. Runtime conflict dispatch and the mixed four-arm partial-commit
  path remain the current action and are not yet claimed complete.
- The bounded first related-conflict path is now production-reachable. The
  coordinator checkpoints a replacement plan, authorizes only after reload,
  appends a strict successor attempt and linked lineage, executes the successor
  once, and persists the complete predecessor+successor lineage in the terminal
  generation. Direct public-root proof passes with one conflict, one successor
  effect, and zero additional calls on replay (`1 passed in 84.13s`); the
  focused repository path passes (`1 passed in 71.36s`).
- Mixed partial-commit recovery is now production-reachable. A two-group public
  root run persists the first completed group, replans and executes only the
  conflicted group, retains the predecessor result and pre-execution identity
  byte-for-byte, and returns the sealed terminal result on replay without
  duplicate effects (`1 passed in 97.83s`). Multi-group ordering validators now
  preserve canonical group order instead of sorting unrelated content digests.
- The explicit `reused_unfinished` arm now retains the predecessor plan,
  authorization, and pre-execution identity while appending a linked successor
  lineage entry for the new CAS attempt. A three-group public-root run proves
  final-result reuse, one replacement, one reused-unfinished execution, and
  zero duplicate effects on replay (`1 passed in 103.95s`).
- Bounded conflict exhaustion now persists and reloads a typed
  `BootstrapGraphFinalizedFailureV3`; resolved successors remain succeeded.
  Both focused result/replay cases pass (`1 passed in 43.08s` and `1 passed in
  42.49s`), and the complete retry/success/resolved-conflict/exhausted-conflict
  coordinator family passes together (`4 passed in 170.46s`). The bounded
  successor/finalization behavior is complete.
- Independent-handle JSONL replay now covers resolved conflict, exhausted
  conflict, and three-group partial commit. Each fresh service returns the
  exact first result with zero source-normalization lane calls and zero graph
  executor calls (`1 passed in 70.34s`, `1 passed in 62.71s`, and `1 passed in
  110.96s`).
- The ordinary terminal path executes through direct, factory, filesystem, and
  Hermes roots. Direct/factory/filesystem passed together and Hermes passed in
  its focused rerun (`1 passed in 38.41s`); a final aggregate root run remains
  part of closure evidence.
- Control-epoch transition validation now distinguishes a different current
  writer (`writer_changed`) from loss of authority for the byte-identical
  writer (`writer_unavailable`), rejects non-initial epoch zero, and validates
  exact same-owner lease renewal versus expired-lease ownership-epoch reclaim.
  The coordinator still needs to consume successor epochs at its effect
  boundaries; the current request remains correctly bound to epoch zero.
- The real coordinator path now consumes same-writer lease renewal and expired
  lease reclaim epochs, and fails closed before compiler/authorizer/executor
  work for both a changed writer and unavailable current-writer authority.
  Focused changed/unavailable proof passes (`2 passed, 7 deselected in
  69.36s`); scoped Ruff, bytecode compilation, and diff hygiene pass.
- The complete production-root graph suite passes (`16 passed in 628.45s`),
  covering composition, execution, fail-closed omission, same-process replay,
  and independent filesystem reopen across the direct, factory, filesystem,
  and Hermes surfaces. The revision-bound binding ledger now reflects the
  actual shared non-test `BootstrapGraphHostBundle.execute` caller and the
  reachable coordinator/repository/terminal chain instead of stale zero-caller
  claims.
- Public pre-CAS race evidence now covers memory and filesystem-backed stores.
  Revoking the current scope at the executor's immediate-before-CAS boundary
  records one rejected attempt, zero graph effects, a durable retry, and zero
  repeated lane/effect calls (`2 passed, 16 deselected in 102.93s`). A foreign
  write outside the sealed read-set partition permits the one authorized CAS
  and terminal result without successor/replan work (`2 passed, 18 deselected
  in 90.96s`).
- Direct, factory, filesystem, and Hermes race rows now all pass for their
  ordinary backend (`4 passed, 20 deselected in 187.92s` for revocation and
  `4 passed, 20 deselected in 138.38s` for unrelated writes). Separate Python
  processes prove JSONL reopen for both scenarios with zero second-process
  lane or graph-executor calls (`1 passed, 25 deselected in 71.34s` and
  `1 passed, 25 deselected in 65.04s`). The latter exposed and fixed a real
  fresh-interpreter forward-reference defect: exact terminal reload now
  rebuilds its typed graph-effect and checkpoint-receipt namespace before
  decoding persisted bytes.

## Current Exact Next Action (2026-08-11, superseding all prior entries)

Implement the approved group-keyed store-owned commit/reload family and replace
the withdrawn V3 CAS/effect carriers through the coordinator and terminal
closure. The preliminary pure-planning owner is now present in
`memorii/memorii/core/memory_evolution/graph_planning.py` and
`memorii/memorii/core/memory_evolution/identity_lineage.py`: it accepts the
outer sealed snapshot and caller-owned planning prefix, produces one typed
non-publishing planning result, and does not call the legacy publish/retry
path. Focused Ruff, bytecode, import, and diff-hygiene checks passed; it has no
ordinary production caller yet, so the binding ledger remains unchanged and no
completion claim is made.

### V55 Normalization Grammar Progress (2026-08-11)

- Removed the temporary `SourceNormalizationAtomicWriteRequestV3` alias from
  the active source-normalization stage and atomic-store dispatch.  The sole
  active request spelling is now
  `BootstrapSourceNormalizationAtomicWriteRequestV3`.
- Replaced unchecked `model_construct` request assembly in the graph-free and
  bootstrap-V3 stage paths with canonical preimage mappings, typed encoding,
  derived request digests, and strict `model_validate` construction.
- Added a focused static regression that proves one active request declaration,
  no temporary alias export, no stage reference to the alias, and no unchecked
  stage construction.
- Focused evidence: `17 passed in 4.37s` for the grammar,
  source-normalization-stage, and atomic-contract suites; scoped Ruff passed
  for the changed stage and test.  This is a partial grammar cleanup only.  It
  does not yet introduce the v55 semantic-reduction authority member/reload or
  make any additional production binding reachable.

### V55 Semantic-Reduction Authority Boundary (2026-08-11)

- The active bootstrap producer is
  `BootstrapV3GraphFreeInterpreter.interpret` in
  `memorii/memorii/core/semantic_ingestion/bootstrap_v3_interpreter.py`.  Its
  complete retained output is the native
  `BootstrapGraphFreeInterpretationBundleV3` plus
  `BootstrapSourceProposalAlignmentV3`; the V3 stage consumes and persists
  only that proposal/lane/interpreter/alignment closure.
- The approved v55 semantic-reduction member instead names complete generic
  `MemoryExtractionProposal`, `SourceObservation`, `SemanticCandidate`,
  `IndependentSourceAnalysis`, `SemanticArbitrationDecision`,
  `SemanticArbitrationPolicyBundle`, and `SemanticAuthorizationReadSet`
  inputs.  No `SemanticArbitrationDecision` contract exists in the current
  repository, and the native interpreter has no production projection to the
  named generic proposal/candidate/analysis inputs.
- Constructing those generic artifacts from the retained bootstrap carriers
  would be a new legacy-shaped semantic pipeline, forbidden by the approved
  no-rerun/no-reconstruction boundary.  This slice is therefore blocked on a
  design remediation that defines the exact native bootstrap reduction input
  grammar or names one canonical pre-graph producer.  No semantic-reduction
  member, store reload, compiler, or production-binding maturity is claimed.

### V58 Native Normalization Core Progress (2026-08-11)

- The v58 native grammar now has a strict
  `BootstrapNormalizationRequestCoreV3`, constructed before either graph or
  semantic-reduction authority.  It carries the complete retained
  proposal/lane/interpretation/alignment/payload-limit/recovery-key preimage
  and rejects incomplete or reordered four-lane closure.
- The V3 normalization checkpoint persists that core byte-identically in a
  `BootstrapSemanticReductionAuthorityMemberV3` alongside the exact policy and
  capability-registry bytes.  The source-normalization repository validates
  the complete retained core/member relation at publication and reload.
- The atomic store now exposes a narrow recovery reload for that authority.  It
  decodes and re-encodes the exact core and member bytes from the found
  generation and rejects missing, substituted, noncanonical, or replay-foreign
  input before returning a typed reload.
- Focused local evidence: the strict grammar, source-normalization
  stage/repository, bootstrap graph atomic-store, and a real JSONL V3
  publication/recovery case passed (`22 passed in 22.12s`).  This is only the first v58
  persistence prerequisite; native reduction/compiler/authorizer/executor and
  mandatory composition remain incomplete.

## Current Exact Next Action (2026-08-11, v58)

Consume the exact reloadable native semantic-reduction authority in the native
compiler and authorizer, then replace the fixture-only graph host provider in
the direct, factory, filesystem, and Hermes composition roots.  Do not add a
fallback to the retired aggregate/CAS/effect path.

### V63 Atomic Member Codec Checkpoint (2026-08-11)

- `BootstrapGraphPlanAtomicMemberV3` now uses the single literal 21-kind V3
  vocabulary and each member is encoded in a qualified
  `bootstrap_graph_v3/<kind>/native` envelope.  Cross-kind, malformed, and
  retired generic reduction (`semantic_compilation`, `terminal_outcome`, or
  `artifact_closure`) payloads reject before a checkpoint is persisted or
  reloaded.
- `BootstrapGraphArtifactAssemblerV3` is the canonical checkpoint producer
  for that envelope.  `AtomicMemoryStore` validates every member before its
  checkpoint CAS and again before reload construction; a payload digest alone
  is no longer sufficient.
- Focused evidence:
  `PYTHONPATH=memorii .venv/bin/python -m pytest
  memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_atomic_member_native_codec.py
  memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_atomic_store.py
  -q -p no:cacheprovider` -> `5 passed in 5.53s`; scoped
  `git diff --check` passed.  This establishes only the native member dispatch
  barrier.  Native operation reduction/output, reducer, group commit
  materialization, and coordinator/root replacement remain incomplete.

## Current Exact Next Action (2026-08-11, v63)

Replace the active generic `BootstrapGraphOperationReductionV3` and its group
commit result inputs with the approved native five-arm reduction/output
contracts, then route the group commit store through its pure validation before
CAS.  The existing generic V3 fixtures must not become a compatibility path.

### V63 Native Reduction Contract Checkpoint (2026-08-11)

- The active `BootstrapGraphOperationReductionV3` grammar no longer contains
  `semantic_compilation`, `terminal_outcome`, or `artifact_closure`.  It now
  retains native compilation, terminal, closure, and materialization outputs,
  including the five closed fact/correction/retraction/action-state/identity
  effect arms and typed record-intent carrier.
- Group commit result construction now derives graph, event, and observation
  identities from native materialization only.  It no longer constructs the
  withdrawn `SemanticEffectGroupResult`, `SemanticGraphDelta`, or
  `SemanticObservationDelta` bridge objects in its V3 path.
- Focused evidence:
  `test_bootstrap_graph_atomic_member_native_codec.py` -> `3 passed in 5.02s`,
  `test_bootstrap_graph_atomic_store.py` -> `3 passed in 4.66s`, plus explicit
  contracts/atomic-store import and forward-reference rebuild and scoped
  bytecode compilation.  Existing old-coordinator fixture paths are expected
  to be incompatible until their separately assigned native reducer/compiler
  and coordinator replacement is complete; this checkpoint is not an M3.1
  completion claim.

### V63 Native Group Commit Repository Port (2026-08-11)

- Added `AtomicStoreBootstrapGraphGroupCommitRepositoryV3` as the sole typed
  adapter for `SemanticIngestionAtomicStore.commit_or_reload_bootstrap_graph_group_v3`.
  It validates the complete `BootstrapGraphGroupCommitRequestV3` before the
  store call and validates the returned `BootstrapGraphGroupCommitReloadV3` on
  both first commit and found reload. It has no digest-only or per-operation
  publication entry point.
- The production-entrypoint binding map records this canonical owner with zero
  ordinary callers. This is not a runtime reachability claim: the coordinator
  still uses the historical `BootstrapGraphGroupExecutorPortV3.execute_cas`
  protocol and does not yet construct a native group-commit request from a
  native reduction, reloaded authorization tuple, lineage, and pre-execution
  identity.
- Focused local proof from `memorii/`: `PYTHONPATH=memorii .venv/bin/python -m
  pytest tests/unit/core/semantic_ingestion/test_bootstrap_graph_atomic_store.py
  tests/unit/core/semantic_ingestion/test_bootstrap_graph_atomic_member_native_codec.py
  -q -p no:cacheprovider` -> `6 passed in 4.71s`; scoped Ruff and
  `git diff --check` pass.

## Historical Exact Next Action (2026-08-11, coordinator/root migration; completed by v76/v77)

The native coordinator now constructs `BootstrapGraphGroupCommitRequestV3`,
persists/reloads it through `AtomicStoreBootstrapGraphGroupCommitRepositoryV3`,
and carries the exact reload through the native terminal construction.  The
built-in local host now composes that path without a fixture builder: it reloads
the persisted normalization authority, publishes/reloads transaction authority,
uses the store snapshot/read set, and emits only unresolved native reductions
until a target planner is installed.  Direct, factory, filesystem, and Hermes
no-injection composition checks pass; the direct ordinary-fact selector proves
one persisted native group-commit record.  No fallback, generic replay
reconstruction, retired CAS bridge, or fabricated accepted effect was added.

## Current Exact Next Action (2026-08-12, v81 test-gate delta review)

Validate the frozen v81 identity, obtain targeted test and correctness review
of the measured 4200-second graph-shard budget and exact selector traceability
field rule, then record the final branch-gate disposition.  The runtime,
recovery, composition, terminal-ack, binding, and active-state reviews are
complete.  No additional design expansion is in scope; only a confirmed P1/P2
runtime defect or a determinate contract-conformance violation may reopen code.

### v77 independent review findings and remediation (2026-08-12)

- Confirmed P1: the native group commit previously wrote only typed result
  wrappers with derived graph/event/observation digests.  It did not persist the
  actual materialized planning records or canonical effect carriers.
- Implemented first correction: accepted reductions are now materialized by the
  canonical planning payload materializer under store-owned commit coordinates;
  result, observation, graph-delta-record vector and event-batch carrier are
  written in the same CAS.  Writer admission requires the exact per-operation
  carrier set and joins every carrier digest to the typed operation result.
  Existing native atomic tests pass (`7 passed in 5.54s`), and the built-in
  direct-root ordinary path remains green (`1 passed in 171.81s`).  A strict
  accepted-reduction store fixture and replay-state proof are now complete.
  The accepted coordinator fixture materializes a canonical provenance record,
  writes the canonical semantic event batch, replay state, and advanced
  reference-integrity ledger in the same group CAS, and proves
  `graph_state_snapshot()` exposes that record at a non-genesis revision.  Its
  exact repeat returns the same terminal result without a second group commit
  (`1 passed in 137.26s`).  The governed-write validator requires the complete
  native carrier set plus the canonical event/replay/reference closure and
  rejects any missing or mismatched record.  The existing atomic-store suite
  remains green (`3 passed in 4.40s`).  This closes the confirmed digest-only
  P1 behavior; reclaimed-lease recovery remains open.
- Confirmed P2: built-in recovery recreates graph authority with a live lease,
  while request/group identities retain the predecessor lease.  Reclaim can
  miss a post-CAS pre-checkpoint group and duplicate it.  The existing recovery
  authority repository is not yet used by the built-in provider.
- Implemented P2 correction: built-in acquisition now performs an authorized
  found-first `reload_for_recovery` before taking a new snapshot or publishing
  authority.  The recovered predecessor authority reconstructs the original
  request/group identity, while the epoch repository alone advances to the
  reclaimed lease.  A post-group-CAS checkpoint failure followed by lease
  expiry/reclaim retains exactly one authority and one primary record in memory
  (`1 passed in 188.06s`) and after reopening a fresh JSONL-backed service
  (`1 passed in 201.49s`).  No second group commit occurs.  This closes the
  confirmed reclaimed-lease P2 defect.
- The complete reclaimed-lease matrix is now green for direct, factory,
  filesystem, and Hermes roots in memory and independent JSONL.  The remaining
  memory results completed at `1 passed in 192.70s`, `192.30s`, and `192.76s`
  for factory, filesystem, and Hermes respectively; the direct memory case had
  already passed in `188.06s`.  The JSONL root results are direct `201.49s`,
  factory `197.04s`, filesystem `200.60s`, and Hermes `199.24s`.
- Confirmed architecture action: normal roots still expose the test-oriented
  authority-provider builder seam.  This must be removed or confined to a
  lower-level test harness after concrete production recovery is complete.
- Confirmed verification action: default no-injection recovery must compare
  exact terminal/group identities in a fresh JSONL process; fixture-injected
  recovery is insufficient for parent completion.
- Implemented architecture action: normal direct, factory, filesystem, and
  Hermes signatures no longer accept `bootstrap_graph_host_bundle_builder`.
  The production `BootstrapGraphHostBundle` is concrete and has no
  `authority_provider`/`acquire` seam.  Scenario injection is confined to the
  private `_from_scenario_test_host` harness and its distinct scenario bundle.
  The four default roots plus the static signature/absence proof pass together
  (`5 passed in 23.75s`).
- The default no-injection independent-JSONL terminal acknowledgement-loss
  matrix passed for all roots: direct `210.64s`, factory `206.25s`, filesystem
  `210.78s`, and Hermes `210.30s`.  Each fresh service returns the exact
  persisted terminal identities and retains exactly one native group primary.
- The corresponding default no-injection memory matrix also passed: direct
  `206.59s`, factory `206.50s`, filesystem `206.26s`, and Hermes `208.05s`.
  Each repeat uses the same memory plane and returns the byte-identical terminal
  identity vector with no second group primary.

### Built-in production composition evidence (2026-08-12)

- The built-in provider now projects the persisted
  `GraphDependentExecutionPolicy` bytes into the required authenticated
  `GraphDependentExecutionPolicyReferenceV3`; it does not pass the mutable
  policy carrier across the graph authority boundary.
- Writer admission now accepts only the exact two-record pre-epoch authority
  closure after decoding and re-encoding the typed reload, checking the
  authority/index IDs, reverse joins, canonical payload, and absence of both
  records.  It does not add an ambient control-free write exemption.
- Real ordinary-fact execution without an injected graph builder passed through
  every normal root and persisted exactly one native group-commit primary:
  direct `1 passed in 177.73s`, factory `1 passed in 229.55s`, filesystem
  `1 passed in 230.93s`, and Hermes `1 passed in 229.24s`.
- The corrected independent JSONL post-group-commit checkpoint-ack recovery
  selector passed (`1 passed in 187.96s`) after comparing JSON-normalized
  durable record content; it proves no second group commit on reopen.  The
  independent-process lost-ack selector remains green at the current native
  boundary (`1 passed in 196.74s`).

### Native Reduction Input Projection Progress (2026-08-11)

- Added the V56/V58-native `BootstrapNativeOperationReductionInputV3`,
  `BootstrapOperationCoverageBindingV3`, and
  `BootstrapGraphFreeIdentityPlanningInputV3` contracts.  The source-normalization
  stage now projects operation input from the sealed normalization core only:
  normalized proposal/member/subject, four retained lane results, consensus,
  alignment, identity partition/resolution, complete dependency group, and
  coverage disposition.  The stable execution identity is derived under the
  approved operation-execution CTV domain and is not derived from snapshot,
  attempt, or generation state.
- `BootstrapSemanticReductionAuthorityMemberV3` now carries this native input
  tuple.  Its validator requires canonical dependency-group/operation order,
  unique operation coverage, and exact coverage of complete source-alignment
  groups.  This is persistence-contract progress only: reducer, native
  compiler, group executor, and ordinary-root composition remain unimplemented.
- Focused stage grammar and source-normalization tests passed (`9 passed in
  6.37s`). The historical coordinator fixture selection was rerun after the
  projection change; its terminal result was clean but did not exercise the
  missing native compiler/reducer path.

### Native Reducer Owner Checkpoint (2026-08-11)

- Added `BootstrapNativeSemanticReducerV3`, the pure canonical owner for a
  `BootstrapNativeOperationReductionInputV3` plus sealed snapshot/read set. It
  performs no repository lookup, allocation, retry, persistence, provider
  invocation, or generic semantic-compilation conversion. Until the native
  snapshot target/materialization planner is implemented, it emits only the
  explicit closed nonaccepting reduction (`coverage_unresolved` or
  `graph_target_missing`) with zero effects. This preserves fail-closed
  behavior; it is not an accepted-effect implementation claim.
- The next required contract break is recorded: current V3 operation-plan,
  native-compilation, authorization, attempt, and checkpoint projections still
  lack the required native operation-input/execution identity fields. They must
  be migrated together before the reducer can be wired into the coordinator;
  using the historical fixture compiler would create a prohibited hybrid V3
  generic path.

### Native Compilation Schema Migration Started (2026-08-11)

- `BootstrapNativeOperationCompilationV3` now retains the exact native
  operation input, and `BootstrapTransactionGroupOperationPlanV3` now carries
  its stable `operation_execution_id`. Both validators require the projected
  identity to agree, so a compiler cannot relabel an operation or replace its
  native input after source-normalization publication.
- This deliberately invalidates historical compiler fixtures until they build
  the complete V63-native plan. The remaining coordinated updates are required
  before a test or root may claim a V3 graph execution: authorizations must
  biject `(operation_id, operation_execution_id)`, the attempt/lineage and
  checkpoints must retain the same tuple, and the group-commit request must
  embed the unchanged native reductions.

### V65-V67 Native Planner Contract Checkpoint (2026-08-11)

- Added the closed V65/V67 planning contracts: request-bound target planning,
  snapshot-or-pending target authority, target bindings, planning records,
  native temporal/evidence/identity closures, plan/unavailable results, and
  the identity-admission request/response port.  The identity request enforces
  the v67 predecessor group, graph-free-input, operation-execution-record, and
  mode/nullability joins before any planner invocation.
- Added the pure pending-precedence helper in
  `memory_evolution.bootstrap_graph_planning`; it selects a same-key pending
  planning record over durable snapshot state and returns a discriminated
  authority, never an ambient target coordinate.  The built-in planner is
  deliberately fail-closed until all five arm materializers are implemented.
- `BootstrapNativeSemanticReducerV3` now accepts only the exact V65 planner
  request and plan-or-unavailable result.  It validates every repeated request
  authority field, projects the unavailable arm into a zero-effect native
  reduction, and projects a complete plan through all five native effect arms
  and record intents without legacy carrier compilation.  The native
  compiler/authorizer, group-commit coordinator wiring, and ordinary-root
  reachability remain unimplemented; no production-caller claim is made.
- Focused proof: scoped Ruff, bytecode compilation, and normalization/source
  stage grammar tests (`9 passed in 5.02s`).

### V68-V74 Authority Contract Checkpoint (2026-08-11)

- Added the v68-v74 typed authority grammar for pre-compilation source
  memberships, occurrence-aware first-use dependencies, exact prefix proofs,
  snapshot/pending/new-first-use target arms including the v74 selected producer
  coordinate, canonical identity decision/allocation/reload closure, and
  operation-specific target resolution.  These are explicit content-addressed
  contracts; no digest-only compatibility path was introduced.
- The existing source normalization tests remain green (`9 passed in 4.92s`).
  The runtime projector, materialization planner, identity admission producer,
  compiler, authorizer, coordinator, repository, and root composition have no
  implementation yet and remain unclaimed.  In particular, no pre-existing
  production canonical-identity projector or target-resolution implementation
  exists to wire: it must be implemented with source-wide scope/allocation
  authority rather than inferred from the retained source-local clusters.

### V74 Source-Wide Allocation Projector Checkpoint (2026-08-11)

- Added `BootstrapCanonicalIdentityBindingAllocationProjectorV3` in the
  production graph-planning owner.  It takes only persisted operation inputs
  and explicit recovery/snapshot/read-set/planning-state/scope/allocation
  inputs, derives the v72 membership vector and v73/v74 occurrence-aware first
  use dependency graph, creates deterministic new-or-absent canonical decisions,
  and emits exact collision reservation authority for lawful new identities.
  It performs no store lookup, ambient allocation, or generic compiler call.
- The projector has not yet been persisted/reloaded by a dedicated atomic-store
  authority repository, nor passed to target resolution or the coordinator.
  Therefore this is a pure-owner checkpoint only and does not establish a
  production caller or root reachability claim. Focused Ruff, bytecode
  compilation, diff check, and normalization tests remain green (`9 passed in
  5.24s`).

### V74 Native Planning-Seed Schema Migration (2026-08-11)

- Replaced the incomplete V3 materialization-plan shape with the five-arm
  `BootstrapNativeOperationPlanningSeedV3` discriminated union
  (fact/correction/retraction/action-state/identity).  The nested correction
  replacement-fact and the v74 selected producer-coordinate entity seed are
  now explicit, typed, and content-addressed.  Identity materialization also
  carries the complete canonical-identity authority reload rather than only a
  derived digest.
- The contract registry, forward-reference rebuild namespace, and public
  exports include the new V3-only seed models.  No generic V3 codec or legacy
  plan fallback was added.
- Evidence: `rebuild_bootstrap_graph_effect_contracts()` and scoped bytecode
  compilation succeeded; from `memorii/`, `../.venv/bin/python -m pytest -q
  tests/unit/core/semantic_ingestion/test_bootstrap_graph_atomic_store.py
  tests/unit/core/semantic_ingestion/test_bootstrap_graph_atomic_member_native_codec.py
  tests/unit/core/semantic_ingestion/test_source_normalization_stage.py -p
  no:cacheprovider` -> `13 passed in 6.05s`; `git diff --check` passed.
- This is a schema-only prerequisite.  The built-in materializer, native
  identity-admission port, compiler/authorizer, coordinator group-commit
  migration, and ordinary-root binding remain incomplete.  The binding map
  intentionally remains at zero callers for those owners.

### Native Group-Commit Admission Checkpoint (2026-08-11)

- Added the store-independent
  `validate_bootstrap_native_operation_reduction_v3` boundary and invoke it in
  `SemanticIngestionAtomicStore.commit_or_reload_bootstrap_graph_group_v3`
  before current-authority validation or CAS. The validation re-parses the
  exact reduction, requires the sealed snapshot/read-set pair to equal the
  attempt, and requires its retained operation-input execution identity to
  equal the reduction identity. Backend commit cannot repair a substituted
  native reduction.
- This is an admission barrier only. The coordinator has not yet been migrated
  to construct a `BootstrapGraphGroupCommitRequestV3` through the new repository
  port, so the binding ledger remains zero callers for that port.
