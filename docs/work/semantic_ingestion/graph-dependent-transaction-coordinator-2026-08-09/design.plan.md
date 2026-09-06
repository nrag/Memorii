# Graph-Dependent Transaction Coordinator Design

- Work ID: semantic-ingestion-graph-dependent-transaction-coordinator-2026-08-09
- Work type: design
- Status: under-review (reopened for bootstrap V3 boundary amendment)
- Coordinator: Codex main thread
- Created: 2026-08-09
- Last updated: 2026-08-11
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/milestones/m3-semantic-pipeline.plan.md`; `docs/work/semantic_ingestion/operation-alignment-schema/design.plan.md`; `docs/work/semantic_ingestion/conflict-authority-proof-failures-2026-08-04/debug.plan.md`; `docs/work/semantic_ingestion/source-normalization-authority-bundle-2026-08-10/design.plan.md`
- Canonical design: `docs/design/semantic_ingestion_architecture.md`
- Current resume packet: `docs/work/semantic_ingestion/resume.md`
- Expected outputs: one implementation-ready graph-dependent coordinator design delta or an evidence-backed finding that the existing architecture is already sufficient; a production-entrypoint binding plan; a requirement/evidence/attack matrix; and bounded implementation milestones for the missing production Steps 5--8 chain

## Objective

Make the approved graph-dependent semantic-ingestion path implementable from a
real provider composition root without fabricated authority or hidden design
choices. The design must connect the already approved graph-free source
alignment to one snapshot-bound group plan, append-only attempt and plan
lineage, graph CAS/retry, and exact group/source terminal persistence.

This operation exists because M3 previously approved typed contracts and
bounded tests without proving that a production caller could construct and use
the complete authority chain. M3.1 closes that design-to-runtime reachability
gap before M4 resumes.

## Completion Contract

Complete only when:

- every requirement below has a stable behavioral owner, measurable acceptance
  criteria, and a production-entrypoint binding plan;
- a Spark code map proves the proposed owner chain is reachable from the real
  provider composition root and identifies every current zero-caller gap;
- all required inputs are derivable from persisted or transactionally acquired
  authority, with no fixture-only, digest-only, live-lookup, or sentinel value;
- transaction, CAS, retry, replay, restart, lost-acknowledgement, partial
  commit, and authorization-preservation semantics are explicit;
- the design partitions implementation into bounded vertical milestones, each
  ending in a real production caller and durable outcome rather than a schema-
  only slice;
- the requirement-to-evidence and attack matrices cover every in-scope
  requirement, including both in-memory and filesystem persistence;
- identity hygiene keeps the planning coordinate `M3.1` out of production,
  persisted, test, fixture, command, workflow, and artifact identities;
- a frozen candidate passes independent specification, correctness, and test
  review with no unresolved validated P1/P2, `blocks_approval`, or
  `changes_required` finding; and
- an implementation WorkPlan can be created without hidden conversation
  context or a new product-semantic decision.

## Problem And Impact

The current accepted provider path can produce a `SemanticTerminalOutcome`,
and the repository can store and reload a supplied
`TransactionSemanticGroupPlan`. Production does not construct the sealed
`SourceProposalAlignment`, graph snapshot/read-set extensions, reconciliation
and closure, planning artifacts, compiler output, validation attempt,
`GroupPlanningAuthorization`, or append-only plan lineage needed to supply that
plan truthfully. Provider persistence therefore omits the typed plan and may
use the legacy opaque marker.

This is a correctness and approval gap, not merely missing test evidence. A
terminal cannot claim graph-plan authorization when no production owner ever
created, persisted, reloaded, and revalidated the authorization chain. M4's
clarification-winner replan also cannot preserve a committed group's original
authorization while replacing only a stale group's plan until this chain
exists.

## Scope

Included:

- production publication and reload of the approved graph-free source
  normalization result, retained evidence manifest, and
  `SourceProposalAlignment`;
- source dependency groups and complete operation coverage;
- acquisition of one fenced `GraphSemanticSnapshotBundle` and typed read-set
  extensions for the complete admitted source;
- graph-dependent normalization, entity/reference reconciliation, reservation
  closure, and transaction-group expansion;
- typed planning compilation requests, independently loadable planning
  artifacts and certificates, the pure group compiler, and exact
  `TransactionSemanticGroupPlan` construction;
- persistence-before-use of `GraphDependentValidationAttempt`, exact
  `GroupPlanningAuthorization`, and append-only
  `SourceTransactionPlanLineage`;
- graph CAS, retry, regrouping restrictions, partial-commit preservation,
  restart, recovery, and lost-acknowledgement behavior;
- exact transaction-group and source-result binding to the store-reloaded
  attempt, plan, authorization, lineage entry, graph revisions, delta, event
  batch, and execution manifest;
- provider composition, atomic-store repository boundaries, and both in-memory
  and filesystem proof; and
- the implementation milestone split and evidence needed to call each slice
  complete.

Excluded:

- M4 conflict-attention presentation, user clarification policy, winner
  selection, and conflict-listing behavior;
- terminal-persistence performance optimization, timing inventory, shard
  balancing, and PR-gate duration work;
- new semantic extraction grammar, bootstrap release authority, learned-model
  behavior, retrieval, ranking, and answer generation;
- externally signed production activation; and
- redesign of the approved minimal eight-field `OperationAlignment` receipt.

M4 may consume the completed replan boundary later, but no M4 behavior is part
of this design operation.

## Governing Sources And Precedence

Apply the repository precedence in `AGENTS.md`:

1. `docs/design/memorii_spec.md`
2. `docs/design/memorii_storage_details.md`
3. `docs/design/event_model.md`
4. `docs/IMPLEMENTATION_RULES.md`
5. `docs/design/semantic_ingestion_architecture.md`
6. the approved minimal receipt decision in
   `docs/work/semantic_ingestion/operation-alignment-schema/design.plan.md`
7. production code and tests as feasibility/current-state evidence only

The active M3 packet and this WorkPlan may record scope and evidence but may not
silently amend product semantics.

## Requirements And Acceptance Criteria

| Requirement | Observable contract | Acceptance criteria |
| --- | --- | --- |
| GTC-R01 Source-normalization authority | One atomic pre-planning generation publishes the exact request, result, evidence manifest, policy bundles, aligned and terminal-unaligned consensus artifacts, and sealed `SourceProposalAlignment`. | Production ingress creates and reloads one complete same-generation closure; missing, extra, duplicate, foreign-generation, substituted, partial, or live-reconstructed members reject before graph use. |
| GTC-R02 Complete source grouping | Every aligned operation belongs to exactly one graph-free `SourceDependencyGroup`; coverage, group order, and static dependencies are deterministic. | The operation/group bijection and canonical order are proven for independent, correction, retraction, action, identity, coupled, and unresolved inputs; no graph lookup influences source grouping. |
| GTC-R03 Snapshot authority | One coordinator acquires one `GraphSemanticSnapshotBundle` for the complete admitted source and all required scopes before graph-relative work. | The bundle, base read set, identity/type evidence, policy snapshots, graph revision, and lease/fence bind every downstream artifact; second/live lookups and cross-token substitution reject. |
| GTC-R04 Graph-dependent reconciliation | The coordinator derives graph proposal alignment, identity reservations, capability execution bindings, reconciliation, reference closure, and read-set extensions only from the sealed source alignment and snapshot. | Every artifact is typed, content-addressed, loadable, attempt-bound, and complete; reservation intents remain attached through CAS; unsupported or ambiguous inputs terminate without a success-shaped plan. |
| GTC-R05 Planning artifact authority | A pure compiler consumes exact typed group compilation requests and produces independently loadable planning artifacts, certificates, and proposed deltas without persistence side effects. | Recompilation is deterministic; request/artifact/certificate substitution, cross-group reuse, hidden repository lookup, and digest-only authorization reject. |
| GTC-R06 Fixed transaction group plan | One snapshot-bound fixed-point expansion creates a complete `TransactionSemanticGroupPlan` with exact claim slots, operation membership, dependencies, order, and artifact references. | The plan is atomically published and reloaded through the canonical repository; empty, partial, duplicate, reordered, cross-snapshot, or legacy opaque plans cannot enter planned progress. |
| GTC-R07 Attempt-before-use authorization | The coordinator persists a `GraphDependentValidationAttempt` before using its artifacts and derives one exact `GroupPlanningAuthorization` per planned group by reloading the plan and supporting artifacts. | No compilation, CAS, or terminal result can cite an unpersisted attempt, missing/extra authorization, wrong group, wrong repository, stale snapshot, or superseded attempt. |
| GTC-R08 Append-only plan lineage | One `SourceTransactionPlanLineage` records the initial plan and every replan as append-only entries, preserving terminal committed-group authority. | Attempt IDs are monotone; each replacement names its predecessor; committed group membership and authorization never change; only unfinished/retryable groups receive replacement authority. |
| GTC-R09 CAS, retry, and partial commit | Group execution revalidates exact read/write authority immediately before graph CAS and handles unrelated change, related conflict, retryable failure, lost acknowledgement, and stale-owner takeover deterministically. | Exactly-once graph/event effects hold; unrelated writes may proceed only under the approved read-set rule; related conflict replans the affected suffix; exhausted or invalid retries fail closed without partial exposure. |
| GTC-R10 Terminal and source-result binding | Each group result and final source result binds the exact store-reloaded lineage entry, attempt, plan, authorization, compilation, delta/event batch where applicable, and execution manifest. | Group-result digests are a complete ordered bijection with final lineage entries; pre-graph and graph-bound summaries cannot be coerced through null/empty values; legacy opaque plan markers cannot authorize graph-bound success. |
| GTC-R11 Recovery and replay | Restart and replay reconstruct authority from persisted typed bytes, not current objects or configuration. | In-memory and filesystem lost-ack/reopen tests return byte-identical results; corruption, omission, addition, reordering, generation gaps, and cross-repository substitution reject before visibility. |
| GTC-R12 Production reachability | The complete chain is composed by the ordinary provider root and cannot be bypassed by an optional default or legacy terminal fallback. | The production binding ledger records at least one real caller for every owner; accepted graph-bound outcomes traverse the complete chain, while missing authority yields a typed non-committing outcome before graph effects. |
| GTC-R13 Observability and bounded resources | Attempts, replans, blockers, and terminal causes are visible without leaking raw source or mutable authority; retries and expansion are bounded. | Stable reason codes and trace stages identify the first causal blocker; limits for groups, attempts, artifacts, read-set extensions, and retained lineage are explicit; limit exhaustion is terminal or policy-defined retryable, never silent truncation. |

`GTC-R01` through `GTC-R13` are planning-only traceability coordinates. They
must never appear as production names or persisted values.

## Authority And Ownership Model

The intended owner chain is:

```text
ProviderMemoryService / ProviderIngestionCoordinator
  -> source-normalization coordinator and atomic publication
  -> SourceProposalAlignment + SourceDependencyGroups
  -> graph snapshot/read-set repository
  -> graph-dependent reconciliation and closure
  -> pure group compiler + planning-artifact repository
  -> TransactionSemanticGroupPlan repository
  -> persisted GraphDependentValidationAttempt
  -> reload-derived GroupPlanningAuthorization
  -> append-only SourceTransactionPlanLineage
  -> group graph CAS + event publication
  -> group result + graph-bound source result + execution manifest
```

The implementation design must assign one canonical module/service to every
arrow and define exact typed arguments, durable boundaries, authorization,
failure outcome, and replay load. A repository is not an owner of derivation;
a contract definition is not evidence of reachability; and a fixture builder
is never production authority.

## Production Entrypoint Bindings

This ledger records the design target and current gap. The revision-bound Spark
mapping artifact will replace provisional caller counts before candidate
freeze.

| Requirement | Canonical trigger and composition root | Exact callsite and arguments/authority | Owner chain: validation -> write/read -> outcome | Proof and caller count | Status or explicit blocker |
| --- | --- | --- | --- | --- | --- |
| GTC-R01--R02 | ordinary provider event through `ProviderMemoryService` and `ProviderIngestionCoordinator` | admitted source, prepared source, proposal/analysis, operation fence, immutable policy bundles | normalize -> atomic pre-planning publication -> typed reload -> alignment/groups | The binding map records zero production `SourceProposalAlignment` constructors | not implemented |
| GTC-R03--R04 | accepted complete source alignment | alignment reference, required scopes, lease/fence, snapshot token, graph revision, policy snapshots | snapshot acquire -> reservation/reconciliation/closure -> attempt inputs | Current provider terminal path has no graph snapshot/reconciliation owner | not implemented |
| GTC-R05--R06 | complete graph-dependent group inputs | compilation requests, artifacts/certificates, snapshot-bound group closure | pure compile -> artifact publication/reload -> fixed plan publication/reload | The binding map records zero production transaction-plan repository references | not implemented |
| GTC-R07--R09 | plan/attempt/lineage checkpoint sequence and group execution | reloaded plan/artifact/certificate closure, complete persisted/reloaded group-authority bijection, lineage entry, expected revision/read set, writer/lease fences | publish/reload plan, artifacts, certificates -> derive complete group-authority bijection -> persist/reload complete attempt -> append/reload lineage -> pre-CAS reload -> CAS/retry -> event batch | The binding map records zero production attempt/authority/lineage constructors; existing persistence accepts an optional plan | not implemented |
| GTC-R10--R11 | terminal group completion, restart, replay, source finalization | final lineage entry, attempt/plan/authorization, compilation, graph revisions, manifest | reload/validate -> group result -> source result -> replay | Existing legacy terminal outcome does not prove the graph-bound chain | not implemented |
| GTC-R12--R13 | ordinary provider ingress, with Hermes as one adapter | paired coordinator repositories, policy, store, writer/lease/current authority | `ProviderMemoryService.sync_event` -> `ProviderIngestionCoordinator.ingest`/reconcile -> semantic pipeline -> `SemanticTerminalPersistenceService.persist` | Direct coordinator validation found four production persistence callsites, all omitting `transaction_group_plan`; graph-dependent contracts have zero production constructors/consumers outside the optional repository path | not implemented |

The revision-bound baseline map is
`docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/production-entrypoint-bindings.json`.
It records reproducible direct queries, their current counts, the required
caller-count transition, composition roots, authority arguments, and the
legacy-fallback classification. It is a static design/binding artifact, not a
runtime event ledger. Its zero counts establish the implementation gap; they
must become nonzero only through the ordinary production composition roots.

## Remediated Coordinator Contract

The architecture's new graph-dependent coordinator implementation profile is
the canonical design delta for this WorkPlan. It selects
`memory_evolution/transaction_coordinator.py::SemanticIngestionTransactionCoordinator`
as the sole Steps 5--8 owner, with `ProviderIngestionCoordinator` as mandatory
caller and `ProviderMemoryService` as facade. Factory, filesystem, and Hermes
must compose the same dependencies. Absence produces a typed non-committing
outcome before a graph read or legacy committing terminal fallback.

The delta corrects the attempt order: the complete plan/artifact/certificate
closure is published and reloaded first, then its exact authorization bijection
is derived, embedded in the complete attempt, atomically published and
reloaded, and only then appended to lineage and used for pre-CAS reload/CAS.
Recovery after a lost acknowledgement reads the durable generation/result
before retrying; a same-generation member is never authorized by a result that
it is about to create. This is a narrow correction of ambiguous prose, not a
change to the typed attempt contract.

The delta also selects a single immutable `GraphDependentExecutionPolicy` V1,
strict unreleased compatibility/rollback state machine, and continuous
tenant/principal/scope authority through ingress, snapshot, reservations,
planning, attempt, CAS, result, and replay. Full fields, digest preimage,
limits, status/reason, fixture oracles, no-disclosure behavior, and the policy
registry boundary are normative in the architecture subsection.

## Requirement Evidence And Gate Ledger

Implementation must add the named tests before claiming the respective
requirement complete. `existing` means the listed file is a foundation only;
none currently proves the full graph-bound route. Existing job names are read
from `.github/workflows/pr-gates.yml`; this design proposes the dedicated
`Graph-Dependent Semantic Ingestion` workflow job and no runtime JSON ledger.

| Requirement | Proposed test owner/file | Root and durable observable | Mutation/failure signal | Existing/new | Required PR job / aggregate |
| --- | --- | --- | --- | --- | --- |
| GTC-R01 | `tests/unit/core/semantic_ingestion/test_graph_dependent_transaction_coordinator.py` | provider ingress -> reloaded same-generation alignment closure | missing/extra/foreign/reordered member; no graph read | new | `graph-dependent-semantic-ingestion` (`Graph-Dependent Semantic Ingestion`) / `Semantic Ingestion` |
| GTC-R02 | `tests/unit/core/semantic_ingestion/test_graph_dependent_transaction_coordinator.py` | reloaded complete operation-to-group bijection | duplicate, omitted, graph-influenced grouping | new | `graph-dependent-semantic-ingestion` (`Graph-Dependent Semantic Ingestion`) / `Semantic Ingestion` |
| GTC-R03 | `tests/unit/core/semantic_ingestion/test_graph_dependent_transaction_coordinator.py` | one authorized snapshot and sealed extension union | token/scope/fence/second-read substitution; no CAS | new | `graph-dependent-semantic-ingestion` (`Graph-Dependent Semantic Ingestion`) / `Semantic Ingestion` |
| GTC-R04 | `tests/unit/core/semantic_ingestion/test_graph_dependent_transaction_coordinator.py` | typed reconciliation/reservation/closure artifacts in reloaded attempt | omitted extension/reservation/closure or tenant mismatch | new | `graph-dependent-semantic-ingestion` (`Graph-Dependent Semantic Ingestion`) / `Semantic Ingestion` |
| GTC-R05 | `tests/unit/core/semantic_ingestion/test_graph_dependent_transaction_coordinator.py` | pure compiler artifacts/certificates reload from planned generation | hidden repository lookup, substituted artifact/certificate | new; compiler vectors remain existing supplemental evidence | `graph-dependent-semantic-ingestion` (`Graph-Dependent Semantic Ingestion`) / `Semantic Ingestion` |
| GTC-R06 | `tests/unit/core/semantic_ingestion/test_transaction_group_plan_repository.py` | fixed-point plan publication then authorized typed repository reload | incomplete/duplicate/reordered/cross-snapshot/cross-tenant plan | existing file, new cases | `graph-dependent-semantic-ingestion` (`Graph-Dependent Semantic Ingestion`) / `Semantic Ingestion` |
| GTC-R07 | `tests/unit/core/semantic_ingestion/test_graph_dependent_transaction_coordinator.py` | complete typed group-authority bijection embedded in persisted/reloaded attempt | empty/post-persist/cross-group/cross-plan/wrong-union-arm; final-no-authority proof/null/CAS mutation | new | `graph-dependent-semantic-ingestion` (`Graph-Dependent Semantic Ingestion`) / `Semantic Ingestion` |
| GTC-R08 | `tests/unit/core/semantic_ingestion/test_graph_dependent_transaction_coordinator.py` | append-only lineage retains committed-group authority across replan | overwrite, regroup committed group, broken predecessor | new | `graph-dependent-semantic-ingestion` (`Graph-Dependent Semantic Ingestion`) / `Semantic Ingestion` |
| GTC-R09 | `tests/integration/test_graph_dependent_semantic_ingestion.py` | root-to-CAS group result and exactly-once graph/event outcome | related/unrelated conflict, stale lease, lost acknowledgement | new | `graph-dependent-semantic-ingestion` (`Graph-Dependent Semantic Ingestion`) / `Semantic Ingestion` |
| GTC-R10 | `tests/unit/core/semantic_ingestion/test_semantic_terminal_persistence.py` | terminal/source result references reloaded attempt/plan/authority/lineage and final-before-planning proof | null/empty/sentinel plan, fabricated authority, proof mismatch, or incomplete result bijection | existing file, new selectors | `graph-dependent-semantic-ingestion` (`Graph-Dependent Semantic Ingestion`) / `Semantic Ingestion` |
| GTC-R11 | `tests/integration/test_graph_dependent_semantic_ingestion.py` | memory and JSONL restart replay produce identical result or reject before visibility | crash at every publication boundary, no-authority arm/proof/CAS mutation, corruption, cross-repository input | new | `graph-dependent-semantic-ingestion` (`Graph-Dependent Semantic Ingestion`) / `Semantic Ingestion` |
| GTC-R12 | `tests/unit/core/semantic_ingestion/test_semantic_provider_composition.py` | direct/factory/filesystem/Hermes roots reach coordinator with mandatory authority | owner removal/optional default/legacy fallback; zero graph effect | existing file, new selectors | `graph-dependent-semantic-ingestion` (`Graph-Dependent Semantic Ingestion`) / `Semantic Ingestion` |
| GTC-R13 | `tests/unit/core/semantic_ingestion/test_graph_dependent_transaction_coordinator.py` | attempt/progress/replay binds one policy digest and exact observed limits | N-1/N/N+1, truncation, digest substitution, replay mismatch | new | `graph-dependent-semantic-ingestion` (`Graph-Dependent Semantic Ingestion`) / `Semantic Ingestion` |

The attack matrix is complete only when each row also runs the same-tenant
positive and cross-tenant/omitted/forged non-disclosing variants at direct,
factory, filesystem, and Hermes roots. The negative durable observable is zero
target-tenant read/reservation/CAS calls and no target identifier in the result.
Restart and concurrent A/B variants belong to the GTC-R09/R11 integration
families; optional-plan and legacy-marker variants belong to GTC-R10/R12.

## Graph-Dependent CI Gate Contract

Implementation must add the dedicated required PR job with machine ID
`graph-dependent-semantic-ingestion` and display name
`Graph-Dependent Semantic Ingestion`. Its receipt aggregator, rather than an
individual measurement producer, is added to the `needs` list of the existing
`Semantic Ingestion` aggregate. Each producer runs on Python 3.11 with a timeout
of at most five minutes and collects exactly these graph-dependent proof roots:

- `tests/unit/core/semantic_ingestion/test_graph_dependent_transaction_coordinator.py`
- `tests/unit/core/semantic_ingestion/test_transaction_group_plan_repository.py`
- selected graph-bound cases from
  `tests/unit/core/semantic_ingestion/test_semantic_provider_composition.py`
- selected graph-bound cases from
  `tests/unit/core/semantic_ingestion/test_semantic_terminal_persistence.py`
- `tests/integration/test_graph_dependent_semantic_ingestion.py`

The graph jobs own the committed collection manifest at
`memorii/tests/ci/graph-dependent-semantic-ingestion.json`, containing the
ordered test paths/selectors and a derived total collection count. The sole
post-run inventory is
`memorii/tests/ci/graph-dependent-semantic-ingestion-timing-inventory.json`;
it is not an input to the four-receipt `Unit Timing Inventory` merge. The exact
lifecycle is ordered: (1) before each run, every producer validates only the
committed collection manifest, selectors, count, and exclusive ownership
topology; (2) it runs that selection with `-W error -p no:cacheprovider`; (3) on
success it uploads one distinct current-revision receipt; (4) only the
aggregator downloads and validates all three current receipts, then publishes
the sole inventory. A producer never reads a prior receipt or any timing
inventory, and a prior inventory cannot satisfy a new run.

Ownership is exclusive. The implementation change that adds the graph manifest
must remove every selected graph node from `memorii/tests/ci/unit-shards.json`
and its generic unit collection universe. It must also remove the selected
graph-bound terminal-persistence node IDs from the terminal-persistence
collection manifest/count while retaining all non-graph-bound terminal tests in
their existing seven-shard performance owner. The new coordinator, plan
repository, provider-composition, and integration nodes belong only to the
graph manifest. A topology validator consumes all three collection manifests,
all timing manifests/receipts, and the `Semantic Ingestion` aggregate needs;
it rejects overlap, omission, zero selection, an unowned receipt, a timing node
outside its collection universe, or a graph job absent from the aggregate. A
new or removed test requires one intentional manifest/count/timing update in
the same change. Workflow mutations that remove a manifest node, any required
current-revision timing receipt, disjointness exemption, or aggregate dependency must make validation
fail. This preserves the five-minute correctness BVT while leaving the separate
performance WorkPlan and its long shards intact.

The graph evidence topology has three parallel pytest producer jobs:
`graph-dependent-semantic-ingestion` (display `Graph-Dependent Semantic
Ingestion`), `graph-dependent-semantic-ingestion-measurement-b`, and
`graph-dependent-semantic-ingestion-measurement-c`. Each has exactly a
five-minute timeout and runs the same closed graph manifest once. The required
non-pytest consumer job is
`graph-dependent-semantic-ingestion-receipt-aggregate`; it needs all three
producers, validates their receipts, emits the graph timing inventory, and is
the sole graph dependency of the `Semantic Ingestion` aggregate. It cannot run
before all producers reach a terminal result and cannot read or publish receipts
until all three results are `success`.

The producer receipt locations are exactly
`artifacts/graph-dependent-semantic-ingestion/receipt-a.json`,
`artifacts/graph-dependent-semantic-ingestion/receipt-b.json`, and
`artifacts/graph-dependent-semantic-ingestion/receipt-c.json`, uploaded under
the matching producer job ID and candidate revision. Each contains that
producer's `GraphDependentTimingMeasurementReceipt.v1`; names, paths, producer
ID, revision, selector, and environment are exact receipt identities. After its
three-result success check, only the aggregator downloads those three paths in
the fixed A/B/C order, validates the current revision-bound receipts, and
publishes `memorii/tests/ci/graph-dependent-semantic-ingestion-timing-inventory.json`.

The receipt aggregator declares `if: always()` so it can diagnose every
producer terminal result. Its first step captures all three exact
`needs.<producer>.result` values and explicitly requires each to equal
`success` before it reads, validates, or publishes any receipt/inventory; a
`failure`, `skipped`, or `cancelled` producer produces no graph inventory and a
failing aggregator result. `Semantic Ingestion` retains the aggregator in its
`needs`, exports exactly
`GRAPH_RECEIPT_AGGREGATE_RESULT: ${{ needs.graph-dependent-semantic-ingestion-receipt-aggregate.result }}`
to its assertion step, and executes the exact shell predicate
`test "$GRAPH_RECEIPT_AGGREGATE_RESULT" = success`. Thus `if: always()` cannot
turn incomplete graph evidence into a green semantic aggregate.

Each producer is an exact key in the existing
`dedicated_pytest_jobs` ledger and has only the existing fields:
`timeout_minutes: 5`, immutable `runtime_budget_seconds: 270`, immutable
`timeout_headroom_seconds: 30`, and `timing_exemption_reason`. The ceiling is
declared policy, not an observed value: every receipt elapsed time must be less
than or equal to `270`, so the declared ceiling is at least the observed maximum
and at most `270`; `300 - 270 = 30` is the required headroom. The reason says
only that the graph jobs are excluded from the generic Unit Timing Inventory
merge because their required receipt aggregator owns the separate graph timing
inventory. It is not an exemption from measurement, receipt validation, or the
declared ceiling.

Each `GraphDependentTimingMeasurementReceipt.v1` is a canonical immutable
artifact with fields in declaration order: producer job ID, candidate revision,
collection-manifest digest, canonical selector digest and count, environment
fingerprint (runner image, OS, Python, pytest, dependency-lock, and command
digest), elapsed milliseconds, started/finished UTC instants, and receipt
digest. Producer IDs are ordered exactly base, `-measurement-b`,
`-measurement-c`; the aggregate consumes exactly that ordered set. Receipts are
attached to the candidate revision and retained with its pinned CI evidence
until approval or supersession; they are never reused across revisions.

The static topology and aggregate validators consume the current owner ledger,
workflow, graph/unit/terminal collection manifests, graph/unit/terminal timing
manifests/receipts, and all three graph measurement receipts. They reject a
missing, duplicate, foreign-revision, future-schema, future-issued,
selector/count/environment mismatch, nonpositive, over-ceiling, reordered, or
unretained receipt; a missing producer/consumer edge; a missing or extra machine
ID; display-name/ID mismatch; any unknown owner field; timeout/headroom/budget
mismatch; blank/misused exemption; absent aggregate timing inventory; aggregate
omission; overlap/orphan; or receipt/collection mismatch. Mutating every receipt
field, producer result, ledger field, ID/display mapping, exemption semantics,
producer-to-consumer edge, aggregate edge, or transferred node must fail before
the consumer can publish its inventory or the aggregate can claim the gate.
The static mutation suite additionally fails when the aggregate edge is retained
but that environment export or exact assertion is removed, when the aggregator
`if: always()` or its three-result success check is removed, or when any producer
is forced to fail, skip, or cancel. It also forbids a producer read of an old
receipt or any inventory, an old inventory satisfying a current run, and an
aggregator publication before all three exact current-revision receipts have
been downloaded and validated.

The same implementation change is blocked on an acknowledged handoff update to
`docs/work/semantic_ingestion/terminal-persistence-performance-2026-08-09/testing.plan.md`:
that WorkPlan must recalculate and validate its residual terminal collection,
timing universe, seven-shard timing inventory, and measured budget after graph
nodes move. Neither this graph gate nor the terminal-persistence performance
operation may close until the paired manifests, timing receipts, owner ledger,
and residual seven-shard budget agree in one revision. The paired implementation
review must pin the graph collection manifest, residual terminal collection
manifest, both timing inventories/receipts, owner ledger, and the two WorkPlan
content digests at the same candidate revision; a stale or one-sided pin rejects
the topology transition.

## Revision Identity Ledger

| Identity | Classification | Rationale |
| --- | --- | --- |
| `SemanticIngestionTransactionCoordinator` | existing behavioral production owner | selected by the architecture module table; not a planning coordinate |
| `GraphDependentExecutionPolicy` | new behavioral persisted policy type | names replayable execution limits, not a milestone or requirement |
| `production-entrypoint-bindings.json` | new design evidence artifact | stores static production-map queries and counts; it is not runtime authority |
| `test_graph_dependent_transaction_coordinator.py` | proposed behavioral test identity | exercises the selected coordinator path; it is not a requirement label |
| `graph-dependent-semantic-ingestion` producers / `graph-dependent-semantic-ingestion-receipt-aggregate` / `Graph-Dependent Semantic Ingestion` / `Semantic Ingestion` | proposed measurement IDs / required consumer / display name / existing aggregate | exact current-ledger producer keys, receipt handoff, separate human display, and aggregate dependency required by this delta |

No production, persisted, fixture, test, command, workflow, or artifact name in
this delta contains a requirement, review, or milestone coordinate.

## Design Milestones

### D1: Baseline And Contract Closure

- Reconcile the normative requirement ledger with existing typed contracts and
  the production mapping artifact.
- Decide whether the canonical architecture needs a delta or only a compact
  implementation profile that selects already-defined contracts.
- Close any undefined owner, input, digest, state transition, or failure
  outcome before algorithm design.
- Acceptance: no required value depends on fixture data, live mutable lookup,
  hidden conversation context, or an unspecified repository.

### D2: Source-To-Graph Boundary

- Freeze atomic source-normalization publication/reload ownership.
- Freeze source dependency group completeness and the snapshot acquisition
  interface, required scopes, leases/fences, and read-set extension ownership.
- Freeze graph-dependent reconciliation, reservation, and reference-closure
  inputs/outputs.
- Acceptance: a single source can move from admitted/prepared authority to a
  complete graph-dependent attempt input without a graph write or fabricated
  identity.

### D3: Planning And Authorization Boundary

- Freeze pure compiler APIs, artifact/certificate repositories, fixed-point
  group expansion, plan construction/publication, attempt persistence, and
  reload-derived per-group authorization.
- Define deterministic limits, canonical ordering, independence rules, and all
  substitution failures.
- Acceptance: one independently reloadable plan and authorization set can be
  reconstructed from persisted authority alone before any group effect.

### D4: Execution, Lineage, And Recovery Boundary

- Freeze graph CAS/retry ownership, append-only lineage transitions,
  committed-group preservation, partial completion, group/source results,
  manifests, restart, lost acknowledgement, and replay.
- Specify the exact replan matrix needed by later clarification-winner
  behavior without designing that M4 trigger.
- Acceptance: every terminal group has exactly one retained
  attempt/plan/authorization tuple, and retry cannot rewrite committed history.

### D5: Verification And Implementation Slicing

- Build the complete requirement-to-evidence and attack matrices.
- Produce bounded implementation milestones whose acceptance includes real
  production callers and durable effects.
- Freeze candidate identity, run independent reviews, reconcile findings, and
  publish the approved design baseline.
- Acceptance: the implementation plan has no schema-only completion point and
  no milestone can claim completion with a zero-caller binding.

## Serious Alternatives

1. **Integrate the complete approved chain into the existing provider
   coordinator.** This is the baseline because it preserves one public ingress,
   one source operation fence, and the existing atomic store. It requires
   splitting the current legacy terminal pipeline into graph-free and
   graph-bound owners rather than wrapping its final result.
2. **Introduce a separate graph-bound orchestration service behind the provider
   coordinator.** This may improve cohesion if the coordinator would otherwise
   become monolithic. It is acceptable only if the service consumes and emits
   the exact approved typed authority and remains mandatory for graph-bound
   success; an optional plugin or sidecar fallback is rejected.
3. **Derive a plan from the legacy `SemanticTerminalOutcome`.** Rejected. The
   outcome lacks sealed alignment, snapshot, reconciliation, artifacts,
   certificates, attempt, and authorization inputs. Filling them after the fact
   fabricates authority.
4. **Keep the plan optional and defer graph authorization.** Rejected for M3.1
   graph-bound success. It may remain only for explicitly pre-graph,
   non-committing outcomes; it cannot authorize a committed semantic effect.
5. **Persist one mutable current plan instead of append-only lineage.**
   Rejected because restart, partial commit, replan, audit, and M4's later
   clarification-winner behavior require the original committed-group
   authorization to remain recoverable.

## Verification And Attack Matrix

| Family | Required proof |
| --- | --- |
| Production reachability | Provider, factory, filesystem, and Hermes roots compose the same mandatory graph-bound chain; missing owner/authority is typed non-committing and writes no graph effect. Static mapper proves nonzero production callers and no legacy success bypass. |
| Source normalization | Exact same-generation request/result/manifest/bundles/artifact closure; missing, extra, duplicate, reordered, cross-generation, cross-source, cross-route, and digest-only substitution reject. |
| Grouping | Every operation exactly once; independent, coupled, correction/retraction, action/identity, unresolved, empty, duplicate, and cross-source matrices. |
| Snapshot and reconciliation | Revision, token, policy, type evidence, identity reservation, scope, lease/fence, and read-set extension mutated independently; no second lookup or detached reservation intent. |
| Compilation and planning | Independent reference compiler or exact vectors; request, artifact, certificate, group membership, order, claim slot, dependency, snapshot, and repository substitutions; deterministic fixed point and bounded non-convergence. |
| Attempt and authorization | Attempt persisted before use; exact per-group authorization bijection; missing, duplicate, extra, stale, superseded, cross-attempt, cross-group, and cross-repository cases. |
| CAS and concurrency | Unrelated write, related conflict, stale revision, writer epoch, lease fence, operation state, reservation collision, two concurrent coordinators, exact retry, and retry exhaustion. |
| Partial commit and replan | Every final variant remains immutable; preserve its original authority and membership, replace only retryable unfinished groups; reject regrouping, result omission, union-arm substitution, or post-final mutation. |
| Terminal binding | Committed and non-committing group variants, pre-graph versus graph-bound source result, complete lineage/result bijection, exact delta/event-batch mapping, no empty/sentinel success. |
| Restart and replay | In-memory plus filesystem reopen and lost acknowledgement at every publication boundary; byte-identical retry; corruption, gap, omission, addition, reorder, rollback, and cross-repository substitution fail before visibility. |
| Observability and limits | Stable causal blocker, bounded attempts/groups/artifacts/read-set extensions/lineage, privacy-safe traces, explicit exhaustion outcome. |
| Identity hygiene | Field-aware scan rejects `M3.1`, `GTC-R*`, review IDs, and evidence coordinates on every durable surface while allowing genuine behavioral numerals and protocol versions. |

## Evidence Maturity Baseline

| Surface | Current maturity | Design target |
| --- | --- | --- |
| Typed Step 5--8 contracts | implemented in substantial part | specified and derivable as one closed owner chain |
| Minimal `OperationAlignment` receipt | approved design and implemented contract tests | consumed by production source alignment |
| Transaction group plan repository | implemented and locally focused-tested | mandatory production read/publication boundary |
| Source alignment producer/publication | strong contract tests, no complete production coordinator | production-entrypoint-bound and deterministically testable |
| Snapshot/reconciliation/compiler owners | specified contracts, no production chain | derivable interfaces and bounded algorithms |
| Attempt/authorization/lineage | typed declarations and isolated tests | append-only production persistence and replay |
| Group/source terminal binding | legacy terminal path exists | exact graph-bound typed result path |
| End-to-end/restart evidence | absent for complete chain | deterministic in-memory and filesystem families |

No row may be promoted because an adjacent row passed.

## Migration, Rollout, And Rollback

Memorii is unreleased, so there is no requirement to preserve an unsafe legacy
graph-bound wire. The design should prefer one strict current contract and a
deterministic fixture/artifact regeneration over dual-write or permissive
fallbacks. Existing pre-graph evidence-only/rejected/unresolved outcomes remain
valid when they satisfy their explicit variant.

Rollout is fail closed: graph-bound success becomes available only when the
complete owner chain is composed. A process built without any mandatory owner
must not silently fall back to the legacy committing terminal. Rollback may
disable graph-bound promotion and retain pre-graph evidence, but may not emit a
success-shaped opaque plan or discard persisted lineage.

## Resource And Performance Constraints

This design defines semantic bounds, not the separate performance remediation:

- maximum operations and source groups per source;
- maximum fixed-point expansion rounds;
- maximum graph-dependent attempts per group and source;
- maximum read-set extensions, reservations, artifacts, certificates, and
  lineage entries;
- bounded persisted payload size and decode depth; and
- no repeated learned or paid stage after acknowledged durable publication.

`GraphDependentExecutionPolicy` V1 fixes operations/groups/fixed-point/snapshot
records/snapshot partitions/related conflicts/attempts/read-set extensions/
reservations/lineage/decode depth to `256/64/16/4096/256/1/2/1024/512/256/64`.
`ReplayArtifactSchemaRegistry` is the sole authority for replay artifact count,
bundle bytes, and per-artifact bytes; policy copies its two bundle maxima
exactly and validation rejects any inequality or fingerprint mismatch. Test
runtime optimization remains out of scope.

## Assumptions And Open Questions

Verified facts:

- the approved architecture specifies the complete Step 5--8 semantic chain;
- the minimal `OperationAlignment` schema is already approved;
- an atomic-store-backed transaction group plan repository exists;
- the ordinary provider path does not currently supply a real typed plan; and
- M4 needs only the completed append-only replan boundary, not a redesign of
  M3.1 semantics.

Working assumptions to validate:

- existing typed contracts are sufficient or need only narrow owner/interface
  corrections rather than a new semantic model;
- the current atomic generation/checkpoint protocol can publish normalization,
  plan, attempt, lineage, group result, and finalization without a parallel
  transaction system; and
- graph snapshot and event publication can share existing memory-plane fencing
  while preserving their separate typed responsibilities.

Open design questions:

- No product-semantic question remains in this bounded design delta. The
  selected coordinator owner, required protocol boundaries, recovery sequence,
  policy values, compatibility table, and tenant authority chain are explicit.
- Implementation must determine concrete repository implementations and test
  adapters against these protocols; that is an implementation detail, not a
  license to select different semantic behavior.

Escalate only if a governing source contradicts a selected persisted or public
contract. No such contradiction was found in this remediation.

## Delegation And Cost Ledger

| Task | Role/tier | Mode | Direct consumer | Status |
| --- | --- | --- | --- | --- |
| Production trigger, callsite, owner, and caller-count map | `code-mapper` / Spark | read-only, artifact-only | production-entrypoint ledger and D1 | complete; paths corrected by coordinator validation |
| Normative Step 5--8 requirements and alternatives map | `explorer` / Spark | read-only, artifact-only | requirements ledger and D1--D4 | complete and reconciled |
| Existing tests/evidence and missing proof map | `explorer` / Spark | read-only, artifact-only | attack matrix and D5 | complete and reconciled |
| Canonical design/WorkPlan edits | one Terra-class worker or coordinator | sole writer | frozen design candidate | complete; this remediation batch is recorded above |
| Specification, correctness, and test review | three Terra reviewers | read-only, concurrent | final design approval | second full review complete; DREV-007--010 remediated, new candidate review pending coordinator validation |

The three mapping tasks are intentionally non-overlapping. Their outputs are
reused by all reviewers; no reviewer should repeat undirected repository
mapping.

## Progress Log

- 2026-08-09: User selected the bounded Step 5--8 design path before M4
  resumes.
- 2026-08-09: Created this linked design operation rather than silently
  converting the active M3 implementation packet into design work.
- 2026-08-09: Established the initial thirteen-requirement ledger, five design
  milestones, production-binding skeleton, alternatives, and attack families.
- 2026-08-09: Launched three cheap, non-overlapping read-only maps for
  production reachability, normative requirements, and verification evidence.
- 2026-08-09: Reconciled the normative and evidence maps. Existing evidence is
  strong for source-group/lineage schemas, the transaction-plan repository,
  and generic atomic persistence, but contract-only for the complete
  graph-dependent attempt flow and absent for production orchestration,
  graph-specific replan, and attempt/plan/authorization terminal binding.
- 2026-08-09: Confirmed the eight-field `OperationAlignment` contract is an
  approved baseline, not an open M3.1 design decision. Historical wording in
  the M3 packet records its earlier sequencing gap and does not reopen it.
- 2026-08-09: The Spark production map correctly identified the external shape
  but cited stale or nonexistent module names for the coordinator and
  persistence owners. Coordinator validation corrected the binding to
  `core/provider/ingestion.py` and `core/semantic_ingestion/persistence.py`.
  Direct search proves four production `persist(...)` callsites, all without
  `transaction_group_plan`, and zero production constructors or consumers for
  the complete alignment/attempt/authorization/lineage chain. The delegate
  output remains advisory; these validated paths are canonical.
- 2026-08-09: Remediated DREV-001 through DREV-006 in the canonical
  architecture and this plan. The architecture now selects the existing
  transaction coordinator as the mandatory Steps 5--8 owner, corrects the
  plan/authorization/attempt order, freezes recovery, policy limits,
  migration/rollback, and continuous tenant authority. This plan records the
  per-requirement executable evidence/gate ledger and the revision-bound static
  production-entrypoint binding map. The design remains active and unapproved
  pending candidate freeze and independent delta review.
- 2026-08-09: Reconciled the remediation's internal conformance pass: the
  policy has an exact fifteen-field preimage, copies replay bundle limits only
  from `ReplayArtifactSchemaRegistry`, and names strict persisted/internal
  coordinator contract shapes and digest domains. The binding ledger and
  resource section now use the selected lifecycle and V1 authority without
  deferred caller-count or later-budget wording.
- 2026-08-09: Remediated DREV-007 through DREV-010 from the second frozen full
  review. The architecture now has a closed four-image planning state machine,
  one durable policy reference/counter closure, authorized plan reads, and an
  executable dedicated CI-gate contract. The plan remains active and
  unapproved pending coordinator validation and a new candidate freeze.
- 2026-08-09: Remediated DREV-011 through DREV-013 from the third frozen full
  review. Replans now retain an authorized predecessor/committed-result closure,
  plan reads validate typed current authority before lookup, and the proposed
  CI gate has an exclusive collection/timing universe. The design remains
  active and unapproved pending coordinator validation and the next candidate
  freeze.
- 2026-08-09: Remediated DREV-014 through DREV-016 from the fourth frozen full
  review. Successor plans are complete effective partitions, both related-
  conflict variants are durable and bounded, and the graph gate now has a named
  measured-budget owner plus a required terminal-topology handoff. The design
  remains active and unapproved pending coordinator validation and a fourth
  candidate freeze.
- 2026-08-09: Remediated DREV-017 through DREV-019 from the fifth frozen full
  review. Successor attempts now carry a discriminated predecessor-reuse versus
  successor-replacement authority union, replan closure retains every typed
  final result, and the paired terminal topology handoff has an acknowledged
  same-revision residual-recalculation and pin contract. The design remains
  active and unapproved pending coordinator validation and a fifth candidate
  freeze.
- 2026-08-09: Remediated DREV-020 and DREV-021 from the sixth frozen full
  review. A third no-authority final non-committing successor arm preserves
  terminal-before-planning history without compilation or CAS, and the graph
  gate now targets the enforced machine-ID owner schema with separate display,
  receipt, budget, headroom, and timing-exemption semantics. The design remains
  active and unapproved pending coordinator validation and a sixth candidate
  freeze.
- 2026-08-09: Remediated DREV-022 through DREV-024 from the seventh frozen full
  review. The no-authority exception now relies on one typed replay-loadable
  terminal-before-planning proof with an append-only reverse join, and the graph
  gate uses three parallel revision-bound receipt producers plus a required
  aggregate consumer against an immutable 270-second ceiling. The design remains
  active and unapproved pending coordinator validation and a seventh candidate
  freeze.
- 2026-08-10: Remediated DREV-025 and DREV-026 from the eighth frozen full
  review. The proof now verifies one canonical pre-compilation lifecycle cutoff
  against loaded attempt/manifest state before arm admission, and the graph
  receipt aggregate explicitly propagates failed, skipped, and cancelled producer
  results into the required semantic aggregate. The design remains active and
  unapproved pending coordinator validation and an eighth candidate freeze.
- 2026-08-10: Remediated DREV-027 from the focused CI-ordering delta review.
  Graph producers now prevalidate only committed collection/ownership topology,
  upload three distinct current-revision receipts after success, and leave all
  receipt reads and sole inventory publication to the aggregator. The design
  remains active and unapproved pending focused delta validation and a new
  candidate freeze.
- 2026-08-10: Final approval recorded at
  `docs/reviews/semantic-ingestion-graph-dependent-transaction-coordinator/final-approval-2026-08-10.md`.
  The v8 full candidate `design-candidate-identity-v8.json` and v9 delta
  candidate `design-candidate-identity-v9.json` reproduced the approved design;
  DREV-001 through DREV-027 are closed. This design WorkPlan is complete and
  approved for a separate bounded M3.1 implementation operation.

## Evidence Log

- `docs/design/semantic_ingestion_architecture.md` defines source alignment and
  grouping near its Step 5 contracts, planning artifacts and group plans near
  the Step 7 contracts, the coordinator sequence near the Step 8 orchestration
  contract, and append-only lineage/result/restart invariants in the execution
  and persistence sections.
- `docs/work/semantic_ingestion/milestones/m3-semantic-pipeline.plan.md`
  records the audited absence of the complete production chain and rejects
  fabrication from the legacy terminal outcome.
- Direct revision-bound search finds no production construction of
  `SourceProposalAlignment`; `SemanticTerminalPersistenceService.persist`
  accepts `transaction_group_plan` optionally; the four provider persistence
  callsites at `core/provider/ingestion.py` omit it. The only production use of
  `TransactionSemanticGroupPlan` is typed repository/persistence support, not
  a producer or coordinator consumer.
- Existing focused evidence owners include
  `test_source_group_plan_contracts.py`, `test_plan_lineage_contracts.py`,
  `test_transaction_group_plan_repository.py`,
  `test_identity_lineage_prerequisites.py`,
  `test_semantic_generation_transactions.py`, and
  `test_semantic_terminal_persistence.py`. They establish contract and generic
  persistence foundations but not the complete Steps 5--8 production chain.
- `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/production-entrypoint-bindings.json`
  validates as JSON and records the direct baseline: one existing transaction
  coordinator class and service composition, four legacy persistence calls, and
  zero production constructors/references for source alignment, attempt,
  authorization, lineage, or the transaction-plan repository.
- The second frozen review is
  `docs/reviews/semantic-ingestion-graph-dependent-transaction-coordinator/full-review-remediation-1-2026-08-09.md`.
  Its DREV-007--010 corrections are owned by the architecture state machine,
  policy/read contract, and the dedicated-gate ledger above; no production or
  workflow artifact was edited in this design slice.

## Known-Failure Ledger

No command failure is currently attributed to this design operation. Existing
terminal-persistence duration and shard failures remain owned by
`docs/work/semantic_ingestion/terminal-persistence-performance-2026-08-09/testing.plan.md`.
Existing M4 conflict/debug failures remain owned by their linked debugging
WorkPlan.

2026-08-09 bounded identity-hygiene check attempted:
`PYTHONPATH=memorii .venv/bin/python -m memorii.tools.identity_hygiene --root . --allowlist .agents/identity_hygiene_allowlist.json`.
It stopped before scanning this delta because the existing global allowlist
contains a legacy-rejection exception without its required exact rejecting-test
proof. This is not attributed to the graph-dependent design artifacts and is
not remediated here. Targeted diff inspection confirms the architecture delta
adds no milestone, requirement, or review coordinate to a durable identity;
the plan's review coordinates are progress metadata only.

## Review Log

Final approval is immutable at
`docs/reviews/semantic-ingestion-graph-dependent-transaction-coordinator/final-approval-2026-08-10.md`.
The approved candidate identities are
`docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/design-candidate-identity-v8.json`
(full: architecture `8cc2052243b440cdb5443702e63e0f4ad3f454225504de7026961433f949986e`,
plan `5b1ca47f66b775b3885abb4d08ef043764f469f73a403877a4f1c2f84a2e874b`,
map `3cba90adbcf1e694465bef18ecddd8536070fa42b0e56c6a177ee13087bc53c5`,
terminal plan `cd031d4e89ee2c1936cb7193baeddaed76a7b0a67de9f1497f0165d01319bce9`)
and `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/design-candidate-identity-v9.json`
(delta plan `b28ddddfd24ed04e83c4aa9acb829b38f2a2a7feb6840ee2dbf6200330282674`;
same architecture, map, and terminal-plan hashes). All DREV-001--027 findings
are closed by the approved design:

| Finding | Disposition | Design evidence |
| --- | --- | --- |
| DREV-001 | closed | selected owner/protocol/composition profile and binding map |
| DREV-002 | closed | generation-by-generation plan -> authorization -> attempt -> lineage -> CAS sequence |
| DREV-003 | closed | immutable V1 execution policy, exact limits/outcomes, replay binding |
| DREV-004 | closed | per-requirement test/gate ledger and reproducible production map |
| DREV-005 | closed | strict unreleased migration/rollback table and fixture oracles |
| DREV-006 | closed | continuous tenant/principal/scope contract and root attack matrix |
| DREV-007 | closed | four durable progress variants, member closures, transitions, and recovery |
| DREV-008 | closed | loadable policy reference and counters in every replay-authoritative carrier |
| DREV-009 | closed | strict authorized plan-read request/result and internal-only legacy decoder |
| DREV-010 | closed | dedicated required job, manifest/count protocol, timing owner, and aggregate dependency |
| DREV-011 | closed | preserving partial-commit replan transition and durable predecessor closure |
| DREV-012 | closed | typed current ingress/scope authority validated before authorized plan lookup |
| DREV-013 | closed | exclusive graph collection, timing receipt/merge universe, and topology validator |
| DREV-014 | closed | complete successor effective-plan algebra with reused and replacement authority |
| DREV-015 | closed | discriminated pre-commit and partial-commit related-conflict replan closures |
| DREV-016 | closed | named job-owner budget/headroom contract and terminal-topology handoff |
| DREV-017 | closed | discriminated reused-predecessor/replacement-successor attempt authority union and complete bijection |
| DREV-018 | closed | typed committed/non-committing final-result closure, partition, and replay joins |
| DREV-019 | closed | paired terminal-plan dependency, transferred-node ownership, same-revision residual recalculation, and candidate pin |
| DREV-020 | closed | strict reused-final non-committing no-authority arm, terminal-before-planning proof, and no compilation/CAS closure |
| DREV-021 | closed | enforced graph job machine ID, current owner-ledger fields, three-run budget, headroom, receipt, and mutation rules |
| DREV-022 | closed | strict typed loadable terminal-before-planning proof, registry/repository publication, decode, and acyclic digest derivation |
| DREV-023 | closed | arm-specific append-only reverse join preserving immutable null-authority predecessor bytes |
| DREV-024 | closed | parallel three-receipt producer/consumer topology, immutable 270-second ceiling, retention, and fail-closed receipt validation |
| DREV-025 | closed | manifest-backed canonical pre-compilation cutoff, allowed terminal outcomes, empty authority/effect closure, and validator order |
| DREV-026 | closed | always-running receipt diagnostics, explicit producer success checks, and semantic-aggregate result export/assertion |
| DREV-027 | closed | ordered producer-output/aggregator-consumer receipt lifecycle with stale-output and early-publication mutations |

Closed means the final approval report accepted the complete design disposition.
It does not claim production implementation, test/CI evidence, parent M3
completion, or M4 approval.

## Bootstrap V3 Graph Transaction Amendment

The prior approved request/plan chain remains authoritative only for the
generic-route V1 family. The normal public bootstrap path now persists only
`BootstrapSourceNormalizationRequestV3`,
`BootstrapSourceNormalizationResultV3`,
`BootstrapSourceProposalAlignmentV3`, and
`BootstrapSourceDependencyGroupV3`; reconstructing their V2 counterparts would
discard native proposal-member, provenance, predicate, temporal, and dependency
identity. This reopened design therefore adds the normative V3 boundary in
architecture section 4.8.1 and does not authorize production code changes.

| Requirement | Observable contract | Acceptance evidence |
| --- | --- | --- |
| GTC-R14 Native V3 ingress | Coordinator accepts the complete typed `BootstrapRecoveryReplayRecordV3` and extracts the exact V3 request/result/alignment/group closure from it. | Replay/atomic/Found/claim/result/provenance and nested bytes/digests/groups biject; scalar, separately supplied, V1/V2/generic/mixed substitution rejects before graph read. |
| GTC-R15 Trusted graph authority | Host provider issues one source/result-bound snapshot authority and an acyclic append-only control-epoch chain links request core to current same-writer lease authority before final request digest. | Exact transition preimage contains core and typed replay/graph authority/current context only; strict decode rejects final request digest; core/head successor lookup, predecessor/transition/monotonicity joins, and distinct zero-effect `writer_changed`/`writer_unavailable` mutations prove no cycle, takeover, caller override, or stale epoch. |
| GTC-R16 V3 attempt and plan | Compiler returns plan/manifest inputs, one complete typed `BootstrapGraphPreExecutionGroupEvidenceV3` per group, and strict attempt inputs whose evidence-digest projection plus all other immutable graph-derived fields exclude authorizations/authority. Plan checkpoint persists complete evidence before post-reload authorization and attempt assembly. | Exact input/context/evidence preimages, group bijections and joins, checkpoint order/generations, no compiler authorization, no post-reload mutation, and no pre-authorization attempt. Omitted/duplicate/reordered/cross-group/empty/default/digest-only/post-CAS/ambient evidence and every field/digest mutation fail before CAS. |
| GTC-R17 Append-only V3 lineage | Initial and successor entries retain exact replay, attempt, group, plan member, authorization, predecessor final-result reference, and control authority with canonical final/unfinished/replanned partitions. | Partial commit and related-conflict schedules preserve committed/final bytes and replace only unfinished affected suffix entries. |
| GTC-R18 Atomic publication and recovery | Checkpoint output is acyclic: immutable reload core/core digest excludes receipt/final digest; receipt binds predecessor, request/write, core digest, publication generations, and successor; wrapper digest is last. Only receipt successor threads. | Exact two-pass order and found-retry byte identity. Core receipt injection, receipt final-digest cycle, request/write/core/predecessor/successor mutation, wrapper reorder, stale/skip/reuse, and generation mutation reject. |
| GTC-R19 Terminal publication | Pre-execution identities form a canonical final-group closure keyed by producing attempt/plan/lineage/group. Reused results preserve predecessor identity bytes; replacements use successor identity. Final manifest embeds the complete typed closure plus equal recomputed closure digest and source-wide authority invariants without forcing producer equality; the terminal registry remains nine kinds. | Partial-commit/related-conflict retained/replaced vectors; swap, collapse-to-final-attempt, predecessor-byte mutation, replacement-old-identity, closure order/projection, digest-only/omitted closure, altered retained identity with stale digest, unresolved identity, forced-equality, and found/absent reconstruction mutations reject. |
| GTC-R20 Composition and lifecycle | Four normal roots require compiler, authorizer, group executor, and terminal preparer plus generation-capable repository; evidence-only has none. Expanded host authority owns immutable execution-graph/route/governance/message/capability carriers. Coordinator seals and reloads `BootstrapGraphFinalStageEvidenceV3` after results (or exact terminal-before-planning proof state). Terminal preparation receives final compilation/closure/attempt/plan/lineage/groups/evidence and alone constructs the manifest construction; coordinator never supplies a prebuilt construction. | Four-root removal/cross-wire/evidence-only injection; host/evidence/coordinator field-source omission, duplication, substitution; normal/partial-replan/terminal-before-planning; evidence checkpoint lost ack, search, final-compilation/plan mismatch, prebuilt/ambient/default/digest-only construction; generation threading, revocation, migration/rollback/restart/non-disclosure pass. |
| GTC-R21 Public-root verification topology | One committed typed selector manifest maps the closed 352-tuple requirement/scenario/root/backend universe, including GTC-R09 unrelated conflict and GTC-R19 terminal locator, to exact public trigger, injection boundary, durable state, calls/effects, and non-disclosure oracle; typed exclusions require architecture-proven non-applicability. | Executed projection union verified exclusions equals required tuples exactly and disjointly; validator rejects missing/orphan/duplicate/helper-only/overlap/count/edge/unjustified-exclusion/one-requirement mutations; revocation, unrelated-conflict, and locator oracles remain exact. |

The exact owner chain is `ProviderMemoryService.sync_event` -> admitted
`ProviderIngestionCoordinator` -> reload V3 normalization found generation ->
`BootstrapGraphDependentAuthorityProviderV3.acquire` ->
`BootstrapGraphDependentCoordinatorV3.coordinate` -> atomic plan/attempt/
lineage/group-result repositories -> `BootstrapGraphTerminalPersistencePortV3`.
Absence at any owner returns the closed V3 noncommit and performs zero legacy
terminal persistence.

The implementation sequence is fixed: validate V3 closure; acquire one graph
authority; seal read set; reconcile and close references; bounded fixed-point
group expansion; pure compilation; publish/reload plan; derive authorization
bijection; publish/reload attempt; append/reload lineage; revalidate immediately
before each group CAS; recover durable group result before retry; append final
lineage; construct/persist/reload terminal handoff. Related conflict replaces
only the unfinished affected suffix once. No normalized proposal, lane,
alignment, or committed group is reconstructed or rerun.

The attack matrix is family-complete across nested V3 closure, graph authority,
group coverage/order, snapshots/read sets/extensions, policy/capability,
lease/fence/writer, compile purity, plan/authorization/attempt acyclicity,
lineage/retry/partial commit, atomic generation order, terminal handoff,
cross-tenant disclosure, migration/rollback, four-root composition, and memory/
independent-process JSONL lost acknowledgement. Each family removes,
duplicates, reorders, substitutes, cross-links, and supplies the adjacent V2 or
digest-only form. The future exclusive selector is
`memorii/tests/ci/bootstrap-graph-transaction-boundary.json`; collection,
timing, three revision-bound receipts, and aggregate are design-only until
implemented and CI-enforced.

Evidence maturity for GTC-R14--R20 is `specified` and `derivable`; production
coordinator, atomic repositories, terminal port, public-root reachability, test,
CI, and operational evidence remain unimplemented. The prior V1 approval does
not advance these V3 rows.

## Exact Next Action

Run targeted specification, correctness, and test review against frozen v76.
Verify the one native reload-derived terminal-result wrapper, its exact
attempt/lineage/member/authorization/pre-execution/epoch joins, withdrawal of
CAS-shaped execution/construction/carrier/receipt contracts from native V3, and
the complete reload-derived final-evidence, retry, manifest, source-result,
terminal, found-reload, four-root, memory, and independent-JSONL proof plan.

## V3 Amendment Progress

- 2026-08-11: Reopened the approved generic graph-dependent design after the
  normal public path completed a native bootstrap V3 normalization closure that
  cannot lawfully feed the V1 coordinator request. Architecture section 4.8.1
  now defines the complete native request/authority/attempt/authorization/plan/
  lineage/atomic/terminal family, exact joins and digest ordering, coordinator
  retry algorithm, atomic generation closures, four-root composition,
  migration/rollback, and family-complete attack matrix. The binding artifact
  records the exact future production owner chain and explicitly reports this
  amendment as specified/derivable but not implemented.
- 2026-08-11: Design-only V3 amendment candidate frozen. `git diff --check` and
  binding JSON parsing pass. Dirty-tree status-list digest is
  `d36afb1bdbefd3e55387371e638e0709d8c0d36d10e82027b8323785c63c7850`;
  architecture and binding SHA-256 values are respectively
  `01b9a727a51e48402054e7d2808c0fb4dd0ce43cf662b3ffd0380957217814ba`
  and `7b586c2ee24e2e782dd66d559337a0cb7a3910ea2748b48076939bf547eeab85`.
  Review scope is GTC-R14--R20 and the V3 amendment only; existing generic V1
  approval, production implementation, workflows, and unrelated dirty-tree
  changes are excluded. No production or test implementation is claimed.
- 2026-08-11: Targeted review confirmed four transaction-boundary gaps. The
  correction replaces scalar normalization identities with the complete typed
  replay record and threads its digest through all durable graph carriers; adds
  canonical replan partitions and reused-committed/reused-final/replacement
  authority arms; requires current ingress/scope/fence/lease on plan and
  terminal repository calls before any read/write; and separates pre-graph
  zero-effect noncommit from durable retry or terminal finalization after an
  attempt, lineage, or possible effect. This remains design-only and is
  unfrozen until the revised candidate identities are recorded.
- 2026-08-11: Replay/replan/current-authority/finalization remediation frozen
  for full targeted specification, correctness, and test review. `git diff
  --check`, binding JSON parsing, and stale-symbol scans pass. Dirty-tree
  status-list digest is
  `d36afb1bdbefd3e55387371e638e0709d8c0d36d10e82027b8323785c63c7850`;
  architecture and binding SHA-256 values are respectively
  `4e519cdd235905cd6677a2e959e4c78f9ffbf3ae35b98be1d7bb73f94162a644`
  and `1847e8dd5e4eba92cf3c98785c3008a7cb3ad6ead5f9d0ae8509faa5d4a8cbf6`.
  The candidate remains design-only; no production, test, CI, or operational
  evidence is claimed.
- 2026-08-11: V11 targeted review found the attempt closure still allowed an
  initial/successor hybrid, omitted unchanged unfinished-group reuse, and
  returned an unverified terminal handoff. The correction makes attempt
  authority a strict initial/successor union, adds `reused_unfinished` with
  byte-preserving no-compile/no-reauthorize semantics and complete partition
  bijections, and requires both success and finalized failure to carry a
  current-authority-bound `BootstrapGraphTerminalReloadV3` whose reload digest
  is covered by the response. Candidate is unfrozen pending new identities.
- 2026-08-11: Strict attempt/reuse/terminal-reload correction frozen for
  targeted specification, correctness, and test review. `git diff --check`,
  binding JSON parse, and stale-shape scan pass. Dirty-tree status-list digest
  is `d36afb1bdbefd3e55387371e638e0709d8c0d36d10e82027b8323785c63c7850`;
  architecture and binding SHA-256 values are respectively
  `912b5e3084a8bbf88d76f9e8b01e310cb891d70e14d04c60ca720361e807c91a`
  and `cb14608ba54cb8c132fb2128af7f11891f65333de5deac167b7596aa3935a2d1`.
  This is design-only and claims no production or test implementation.
- 2026-08-11: DREV-031 confirmed immutable request lease/writer equality could
  not authorize a long-running or reclaimed graph transaction. The correction
  adds append-only `BootstrapGraphControlEpochV3` with acyclic request-core
  binding, strict predecessor/epoch/transition rules, found-first atomic
  renewal/reclaim, and current ingress/scope/fence validation. Every new plan,
  attempt, authorization, lineage, retry, CAS, terminal handoff/reload/result
  binds the latest epoch; reused history retains its historical epoch while new
  effects require current head. Plan/terminal ports accept the typed epoch, not
  raw request lease equality. Candidate is unfrozen pending revised identities.
- 2026-08-11: Append-only graph control-epoch correction frozen for targeted
  specification, correctness, and test review. `git diff --check`, binding JSON
  parsing, and epoch-carrier scans pass. Dirty-tree status-list digest is
  `d36afb1bdbefd3e55387371e638e0709d8c0d36d10e82027b8323785c63c7850`;
  architecture and binding SHA-256 values are respectively
  `29fbaac9eba56dc17f38a06fd9e3545921d91712628ddb0b09445a64b467bc53`
  and `5cd4a3bc955a3e42648451415cdc8a3eb168b812a8547e1da3b5aadac3c2de26`.
  No production or test implementation is claimed.
- 2026-08-11: V13 review found epoch-zero still accepted final request identity,
  creating a construction cycle, and allowed cross-writer reclaim inside an
  active attempt. The correction makes epoch-zero transition authority the
  request core plus complete typed replay/graph authority/current context,
  persists/finds epoch zero before final request digest, and keys successors by
  core+head. Active chains now require byte-identical writer binding and allow
  only lease renewal or same-writer lease reclaim. A different writer requires
  global proof that the old operation terminalized/drained and starts a new
  operation/core/epoch-zero chain; it never resumes the active attempt.
  Candidate is unfrozen pending new identities.
- 2026-08-11: Acyclic epoch-zero and same-writer lease-reclaim correction
  frozen for targeted specification, correctness, and test review. `git diff
  --check`, binding JSON parse, and stale writer/cycle scans pass. Dirty-tree
  status-list digest is
  `d36afb1bdbefd3e55387371e638e0709d8c0d36d10e82027b8323785c63c7850`;
  architecture and binding SHA-256 values are respectively
  `2680e5f562f4952ce6e6803054454bfe6cfbf6ffb869bb2f71a6d17a093b670c`
  and `4166adeb887615ec30a4a48db0cb580f78ce6a108bc1c42ca0cf6d08b769e023`.
  No production or test implementation is claimed.
- 2026-08-11: Literal V14 audit confirms the definitive transition request uses
  `request_core_digest`, not final request identity. The transition digest
  preimage and validator are now explicit and strict decoding rejects a final
  request digest anywhere in the epoch protocol. `writer_changed` is a closed
  reason distinct from `writer_unavailable`; attack rows prove both are
  non-disclosing and cause zero read, append, graph, CAS, or terminal effect.
  Candidate is unfrozen pending new identities.
- 2026-08-11: Literal core-only transition and writer-reason correction frozen
  for targeted review. `git diff --check`, binding JSON parse, definitive-schema
  inspection, and closed-reason scans pass. Dirty-tree status-list digest is
  `d36afb1bdbefd3e55387371e638e0709d8c0d36d10e82027b8323785c63c7850`;
  architecture and binding SHA-256 values are respectively
  `6e9414a99ab7363afdb56a1752d70608ca28bde03e336231373f8da062ae0e03`
  and `5b9b8f7459cdc95be00550993811882f6dbc466a8aa37fa0634dd53600ea9fad`.
  No production or test implementation is claimed.
- 2026-08-11: Test review found the pre-CAS revocation proof and future gate
  topology underspecified. GTC-R21 and architecture now require public
  `sync_event` execution through direct/factory/filesystem/Hermes and memory/
  independent-process JSONL, revoking current scope at the final boundary
  before each actual group CAS. Each fresh run records one rejected CAS call,
  zero CAS linearization/graph/event effect, durable retry or finalized state,
  non-disclosure, and reopen rejection of old authority. A committed typed
  manifest covers initial/successor attempts, all four arms, epoch lifecycle,
  conflicts/partial commit/finalization, lost ack/reopen, migration/rollback,
  and dependency omission/removal, with exact topology and aggregate mutation
  rejection. Candidate is unfrozen pending revised identities.
- 2026-08-11: Public-root revocation and machine-checkable topology correction
  frozen for targeted test review. `git diff --check`, binding JSON parsing,
  and selector/revocation inventory scans pass. Dirty-tree status-list digest
  is `d36afb1bdbefd3e55387371e638e0709d8c0d36d10e82027b8323785c63c7850`;
  architecture and binding SHA-256 values are respectively
  `39a745ef717d7b213545bec35c92429b301b65a1dd736744e9a13ee1fc926361`
  and `b47c317eb494a8975fda731187555abc93ccd395f2a1007bf0ed55b80f4e3db5`.
  This is a future test/CI contract only; no implementation or CI evidence is
  claimed.
- 2026-08-11: Final test-topology review found no closed required-tuple universe
  and allowed exclusions without a typed authority. The correction defines 42
  exact requirement/scenario pairs across four roots and two backends (336
  tuples), requires executed projection plus verified exclusions to be an exact
  disjoint cover, and adds strict exclusion fields/digests whose sole rationale
  is architecture-proven semantic non-applicability. Convenience, missing
  implementation, cost, and fixture gaps cannot exclude a tuple. Validator
  mutations cover duplicate/missing/extra/mismatched/unproved exclusions,
  overlap/union inequality, and mapping every row to one requirement. Candidate
  is unfrozen pending revised identities.
- 2026-08-11: Closed coverage/exclusion topology correction frozen for final
  targeted test review. `git diff --check`, binding JSON parse, and executable
  assertion of 42 pairs x 4 roots x 2 backends = 336 tuples pass. Dirty-tree
  status-list digest is
  `d36afb1bdbefd3e55387371e638e0709d8c0d36d10e82027b8323785c63c7850`;
  architecture and binding SHA-256 values are respectively
  `869fc3f3aae7a552496487ce1d95d0291b384bce01efe291f66c4feac93941d1`
  and `c442dee0c8e6aa09659ed404e25ad46696c8298e728eebd54e8476036543aae6`.
  No test, CI, or production implementation is claimed.
- 2026-08-11: Literal topology audit found the governing GTC-R09 unrelated-
  conflict positive path missing from the closed universe. The table now has 43
  requirement/scenario pairs and 344 root/backend tuples. Its oracle injects a
  foreign write outside the sealed key/partition set and requires exactly one
  authorized CAS plus one expected graph/event effect, with no successor
  attempt, reconciliation, recompilation, or replan. Removing or weakening the
  pair fails validation. Candidate is unfrozen pending revised identities.
- 2026-08-11: GTC-R09 unrelated-conflict topology correction frozen. `git diff
  --check`, binding JSON parse, and executable assertion of 43 pairs x 4 roots
  x 2 backends = 344 tuples pass. Dirty-tree status-list digest is
  `d36afb1bdbefd3e55387371e638e0709d8c0d36d10e82027b8323785c63c7850`;
  architecture and binding SHA-256 values are respectively
  `e80af9612b6ad8d07ba122d1bd977b21f1bd202d03206ea8b6626dce95bb9fcc`
  and `cc131531ff73fe7093095ab34144c169deb27a2d66b866d1a14b6952bb5bfedf`.
  No test, CI, or production implementation is claimed.
- 2026-08-11: Terminal-port implementation mapping found the V3 handoff lacked
  an exact atomic checkpoint locator and would require ambient store search.
  The correction adds `BootstrapGraphPlanAtomicWriteIdentityV3` containing the
  sealed write/request/replay identity, expected/publication generations,
  canonical member manifest ID/digest and required vector, source/operation,
  fence, and control epoch. Terminal persistence validates current caller
  authority, performs exact-locator found-first lost-ack reload, and only when
  absent validates latest epoch/current generations and publishes atomically.
  Legacy locator-less and mixed forms reject. Candidate is unfrozen pending
  revised identities.
- 2026-08-11: Typed terminal checkpoint locator correction frozen for targeted
  specification and correctness review. `git diff --check`, binding JSON parse,
  and executable assertion of 44 pairs x 4 roots x 2 backends = 352 tuples
  pass. Dirty-tree status-list digest is
  `2cf1191b786c5f4ee671e3cf32c01eebbda852abe53c530a7f3d0340fd033de4`;
  architecture and binding SHA-256 values are respectively
  `40f04a6bf5856b911f6d2a9011050dea1550105dc6329a1c30d30ea0772b4b92`
  and `8a76288d21ca37a41271312cf7d662c57f1bcbbed682039200e3f5fdaa70dce7`.
  No production or test implementation is claimed.
- 2026-08-11: Review found the v19 terminal locator cyclic because a handoff
  embedded in the terminal write attempted to carry that final write's own
  digest, generations, and manifest. The correction replaces the prewrite
  locator with `BootstrapGraphTerminalPublicationIntentV3`, derived only from
  durable preterminal inputs and ordered construction intents. The handoff
  binds that intent. Only after CAS construction does the store derive
  `BootstrapGraphPlanAtomicWriteIdentityV3` and atomically index the intent's
  locator to the realized sealed write/generation/manifest; found-first reload
  validates exact realization and returns the final identity. Candidate is
  unfrozen pending revised checks and identities; the 352-tuple coverage
  universe is unchanged.
- 2026-08-11: Acyclic terminal publication-intent correction frozen for
  targeted specification and correctness review. `git diff --check`, binding
  JSON parse, and executable assertion of 44 pairs x 4 roots x 2 backends =
  352 tuples pass. Dirty-tree status-list digest is
  `9865f6c2db395e9a3b4a173dd9f48726d7f9ba173efe9f9ba6284a50aa53a9aa`;
  architecture and binding SHA-256 values are respectively
  `fe896ed1573799fbd5ade29f748ef22ca5c6718f3ca84c2625e4bbb98f79716e`
  and `a839f8573995da9a8858a7e33f78bc0bd45b07920e0cf18b4107eddf94423a1c`.
  No production or test implementation is claimed.
- 2026-08-11: Correctness-review identity audit recomputed the exact current
  `git status --short` byte stream twice and obtained
  `9865f6c2db395e9a3b4a173dd9f48726d7f9ba173efe9f9ba6284a50aa53a9aa`
  both times. The reported `2cf119...` value is not the current shared-tree
  identity. Architecture and binding bytes remain unchanged; only this review
  evidence and the candidate identity are refreshed.
- 2026-08-11: Correctness review confirmed DREV-020, DREV-021, and DREV-035.
  The design now closes all nine terminal member-intent recipes and exact
  realization checks, introduces a pre-intent handoff core so the handoff
  descriptor cannot self-reference, and splits terminal authorization into
  prelookup non-disclosing caller authentication, completed-lease found
  recovery, and live-authority absent publication. Memory and independent JSONL
  schedules cover post-CAS lease expiry/release, revoked/foreign zero index
  read, absent historical lease rejection, and all core/intent/descriptor/
  index/identity mutations. Candidate is unfrozen pending revised identities.
- 2026-08-11: DREV-020/DREV-021/DREV-035 remediation frozen for targeted
  specification and correctness review. `git diff --check`, binding JSON parse,
  the 44 x 4 x 2 = 352 coverage assertion, and two exact identity passes
  succeed. Dirty-tree status-list digest is
  `9865f6c2db395e9a3b4a173dd9f48726d7f9ba173efe9f9ba6284a50aa53a9aa`;
  architecture and binding SHA-256 values are respectively
  `e8b087a5707da32d2fdf62080ddc4e69da14263a6db33fb33fce4fa79de509e5`
  and `206cbf2f8eab64378e62a8fdf5c89e859d99d8b28e6164cbc72481d01c7b8c86`.
  No production or test implementation is claimed.
- 2026-08-11: DREV-036 binding-ledger audit replaced the retired
  `graph_free_normalization.normalize` owner/query with the actual production
  edge `host_bundle.execution_owner.normalize_after_recovery_claim` in
  `provider/ingestion.py`, owned by `SourceNormalizationExecutionOwner` with
  its exact invocation/handoff/recovery-claim/authority signature. The current
  edge count is one, the retired query count is zero, and the owner declaration
  count is one. Architecture semantics are unchanged. Candidate is unfrozen
  only to refresh binding and review identities.
- 2026-08-11: DREV-036 binding-ledger correction frozen. JSON parsing,
  `git diff --check`, two exact identity passes, and production-edge counts
  `current=1`, `retired=0`, `owner=1` pass. Dirty-tree status-list digest is
  `9865f6c2db395e9a3b4a173dd9f48726d7f9ba173efe9f9ba6284a50aa53a9aa`;
  unchanged architecture and corrected binding SHA-256 values are respectively
  `e8b087a5707da32d2fdf62080ddc4e69da14263a6db33fb33fce4fa79de509e5`
  and `b84e6d9c7755ffda44960aafb669352d9d084ee563281c217655db266a26016d`.
  No production or test implementation is claimed.
- 2026-08-11: Terminal-writer implementation mapping found that the handoff-only
  API could not reconstruct the nine canonical members from digests. The design
  now makes sealed `BootstrapGraphTerminalPublicationRequestV3` the sole port
  input and carries every typed prepublication carrier, canonical tuple/result
  input, expected generation, and current authority needed for deterministic
  realization. Found recovery validates supplied carriers against indexed
  bytes; absent publication constructs only from them. Repository search,
  opaque member bytes, and materializer callbacks are forbidden. Candidate is
  unfrozen pending revised identities and targeted review.
- 2026-08-11: Typed terminal publication-request correction frozen for targeted
  specification, correctness, and test review. `git diff --check`, JSON parse,
  352 coverage assertion, and two exact status passes succeed. Dirty-tree
  status-list digest is
  `9865f6c2db395e9a3b4a173dd9f48726d7f9ba173efe9f9ba6284a50aa53a9aa`;
  architecture and binding SHA-256 values are respectively
  `fbbe28c2c100876f732b43e2922aa94dc6077164ed02aff194449a7541cfc32e`
  and `d91d9906773dc969640bc5cfad55ef80cc9a2d97758c709cb66fb791089980c4`.
  No production or test implementation is claimed.
- 2026-08-11: v23 review found two remaining digest-only shortcuts and one
  evidence overclaim. The request now carries complete typed
  `BootstrapSourcePlanLineageV3` history and ordered
  `BootstrapGraphGroupResultConstructionV3` values with exact outcome, CAS,
  effect payload, and three-receipt preimages. Latest lineage and group results
  are derived and checked against the final plan; the canonical source input
  consumes the same constructions. The binding ledger now marks locator found
  support as unreachable partial read-side scaffolding, v23 publication as
  unimplemented, and production callers as zero. Candidate is unfrozen pending
  revised identities and targeted review.
- 2026-08-11: Complete-lineage and typed group-result-construction remediation
  frozen for targeted specification, correctness, and test review. Diff check,
  JSON parse, 352 coverage assertion, stale-shortcut search, and two exact
  status passes succeed. Dirty-tree status-list digest is
  `9865f6c2db395e9a3b4a173dd9f48726d7f9ba173efe9f9ba6284a50aa53a9aa`;
  architecture and binding SHA-256 values are respectively
  `033b24ed8b474aefd210e70a11f21c1c49b9afe7601013e0cf63f9500b49b9d5`
  and `3bed920001f2208482eebd48ce74689b77b9b547ec659fa01f65dd44aa04ac75`.
  The public terminal path remains unimplemented with zero callers; no
  production or test implementation is claimed.
- 2026-08-11: DREV-038 found detached effect digests inside otherwise typed
  group-result constructions. They are replaced by a closed discriminated V3
  union carrying canonical typed observation delta, graph delta, event batch,
  or explicit not-applicable evidence. CAS outcome, receipts, construction, and
  canonical source input retain the same carriers and derive every digest.
  Group/coordinate/status/order joins and retained-old-digest/cross-group/
  not-applicable mutations cover both found and absent branches. Complete
  lineage and the truthful zero-caller ledger are preserved. Candidate is
  unfrozen pending revised identities and targeted review.
- 2026-08-11: DREV-038 typed effect-carrier remediation frozen for targeted
  specification, correctness, and test review. Diff check, JSON parse, 352
  coverage assertion, detached-effect-field search, and two exact status passes
  succeed. Dirty-tree status-list digest is
  `9865f6c2db395e9a3b4a173dd9f48726d7f9ba173efe9f9ba6284a50aa53a9aa`;
  architecture and binding SHA-256 values are respectively
  `1ba3724f16ba16d6ba70e3e51f8a82e6379f1fc8d89baa1ae023996358d8675a`
  and `28b04ca168d6a2cabc5bf2553a7abdcbcb43c60958d756a2a0bbbf9d17ba93d1`.
  No production or test implementation is claimed.
- 2026-08-11: DREV-039 found that individually valid typed effects still
  needed an arm-specific equality algebra. The design now closes committed,
  noncommitting, and failed observation/graph/event arms across plan, CAS
  request/outcome, carrier payload, receipt, and observed/publication revision.
  Event and observation graph references equal the graph carrier delta;
  observation terminal status equals the disposition mapping. Found and absent
  attacks include same-group valid swaps and graph-link/publication-revision/
  observation-reference mutations. Acyclic construction and truthful zero-
  caller ledger remain unchanged. Candidate is unfrozen pending identities.
- 2026-08-11: DREV-039 arm-specific CAS effect equality correction frozen for
  targeted review. Diff check, JSON parse, 352 coverage assertion, and two
  exact status passes succeed. Dirty-tree status-list digest is
  `9865f6c2db395e9a3b4a173dd9f48726d7f9ba173efe9f9ba6284a50aa53a9aa`;
  architecture and binding SHA-256 values are respectively
  `d9bb4a35f98115b8dd54359aed3a5b16d7c0032db5712fe2a59bcf2ce0b27429`
  and `c54694a0ee9eef7aa2c7560803dd88bf95550903c7c52dcbe99e1004c58c4500`.
  No production or test implementation is claimed.
- 2026-08-11: Terminal-writer mapping found the canonical-source input still
  lacked the typed record and governance/message/delivery carriers needed to
  construct `CanonicalSourceTerminalOutcomeRecord`. The record is now a
  mandatory nested typed input. Source-result and record digests plus source,
  preparation, operations, groups, status, scopes, governance, messages,
  delivery identity, and fence are derived and joined to replay/request/effect
  constructions on both found and absent branches. Ambient reconstruction and
  defaults are forbidden. Candidate is unfrozen pending identities/review.
- 2026-08-11: Typed canonical source terminal-outcome correction frozen for
  targeted specification, correctness, and test review. Diff check, JSON parse,
  352 coverage assertion, and two exact status passes succeed. Current dirty-
  tree status-list digest is
  `f16b169bdf8ed3c6eba28af38b7a9cc1156ef3f0447a885bb846dce7ff42b270`;
  architecture and binding SHA-256 values are respectively
  `7bad832813b9dadd55a8d720fa51bf830d893b7f2885268cefa620ad77c0e471`
  and `d295a7cdc47dd73f573d77f899f985413c990b19635741361aa8784cdb4f3dde`.
  No production or test implementation is claimed.
- 2026-08-11: DREV-040 identified a cycle because `outcome_id` depended on the
  later source-result digest. The design now separates a strict canonical
  outcome core, derives its digest first, derives outcome ID from stable source/
  preparation/operation/fence/core coordinates, then derives source-result and
  record digests in order. Completed-record core fields must equal the core
  byte-for-byte. Found/absent attacks cover every core field, ID preimage, digest
  exclusion/order, retained-old digest, and the retired cyclic form. Candidate
  is unfrozen pending identities and targeted review.
- 2026-08-11: DREV-040 canonical source outcome construction order frozen for
  targeted review. Diff check, JSON parse, 352 coverage assertion, retired-cycle
  search, and two exact status passes succeed. Dirty-tree status-list digest is
  `f16b169bdf8ed3c6eba28af38b7a9cc1156ef3f0447a885bb846dce7ff42b270`;
  architecture and binding SHA-256 values are respectively
  `4d1a684ba4d9510679c146b1c31669986b69f3ec12aa0e3836f88cfebbaf14ef`
  and `6ee76fda18d48a3cda50d62ccf0e0095c11ad034706ec6e652881ed4badbe789`.
  No production or test implementation is claimed.
- 2026-08-11: Coordinator implementation mapping found no native V3 planner,
  authorizer, or group-CAS producer boundary; existing generic graph planning
  consumes forbidden predecessor contracts. The design now requires three thin
  host-injected V3 ports: pure compiler returning plan/manifest inputs,
  authorizer consuming only the atomically reloaded plan, and group executor
  performing an internal authority/revocation check immediately before CAS and
  returning typed outcome/effects/receipts. All normal roots require the trio;
  evidence-only has none. Closed unavailable outcomes preserve the pregraph/
  post-attempt failure cut, and no V1/V2 bridge is permitted. Candidate is
  unfrozen pending identities/review.
- 2026-08-11: Native V3 compiler/authorizer/group-executor boundary frozen for
  targeted specification, correctness, and test review. Diff check, JSON parse,
  352 coverage assertion, forbidden-bridge search, and two exact status passes
  succeed. Current dirty-tree status-list digest is
  `34b0a628dfec50d85451d325af82f20d6742ce3676b0dca5af2f8b50f86c58f6`;
  architecture and binding SHA-256 values are respectively
  `ce73144e8628ce75c87ddeefd8f7970424634840e3f2412315d1ad8366e8ca21`
  and `d6e6ba6efdc14241ecfec02c466e724008ff1bf4d112904eaaf496f68446d905`.
  The ports remain design-only with zero production callers; no production or
  test implementation is claimed.
- 2026-08-11: DREV-041 found the executor result and terminal construction could
  independently supply overlapping CAS outcome/effect values. The executor
  result is now closed over its nested CAS request, outcome, carriers, receipts,
  group/attempt/epoch, and result digest. Group-result construction embeds that
  exact result as its sole execution projection and joins it to plan,
  authorization, latest lineage, fence, disposition, and terminal aggregation.
  Found/absent attacks cover every wrapper field, duplicate projection, and
  same-group schema-valid result substitution. Candidate is unfrozen pending
  identities/review.
- 2026-08-11: DREV-041 closed group-execution-result correction frozen for
  targeted review. Diff check, JSON parse, 352 coverage assertion, duplicate-
  projection search, and two exact status passes succeed. Dirty-tree status-
  list digest is
  `34b0a628dfec50d85451d325af82f20d6742ce3676b0dca5af2f8b50f86c58f6`;
  architecture and binding SHA-256 values are respectively
  `c0591fc30933921160c99d3d06feef0b81f3c1b08ad4cc974c02f17b7c9c9541`
  and `09366feb8e117b1de3b9d259767b8e7a77f19f4c69475a11eae81880da867c48`.
  No production or test implementation is claimed.
- 2026-08-11: Attempt-assembler mapping found compiler output omitted the
  immutable graph-derived fields needed to construct
  `BootstrapGraphDependentAttemptV3`, while checkpoint language did not make
  the post-reload authorization sequence explicit. Compiler output now includes
  strict `BootstrapGraphAttemptConstructionInputsV3` but no authorization or
  attempt authority. The plan checkpoint persists those inputs; authorizer
  consumes the reload; coordinator combines exact reloaded inputs with strict
  initial/successor authority and only then publishes the attempt checkpoint.
  Field/preimage/join/order/generation mutations are closed. Candidate is
  unfrozen pending identities/review.
- 2026-08-11: Typed attempt-construction input and checkpoint-order correction
  frozen for targeted specification, correctness, and test review. Diff check,
  JSON parse, 352 coverage assertion, checkpoint inventory search, and two exact
  status passes succeed. Current dirty-tree status-list digest is
  `fdd67de363d9d1ccf0719bacb3ddc07d0807a5a10daea318cbeacc65058b2c13`;
  architecture and binding SHA-256 values are respectively
  `1a8b6182c612295727a1b95423955defad799ddb12f4679932fa1ae9c53b7dc9`
  and `8b6051216a55f1b16f13529c36bc816c9cd1946c812d7d1224b0f2d29cac0e57`.
  No production or test implementation is claimed.
- 2026-08-11: Coordinator assembly mapping found no authoritative source for
  checkpoint predecessor generations or the complete terminal publication
  closure. The repository now loads a typed current-generation snapshot and
  returns a checkpoint receipt whose successor is the only next predecessor;
  caller generation scalars are forbidden. A fourth injected V3 producer,
  terminal preparation, combines coordinator-derived final state with separate
  host delivery/governance/message/scope authority to produce the exact sealed
  publication request without opaque bytes or ambient search. Compiler output
  remains `PlanCompilation`, not a checkpoint. Candidate is unfrozen pending
  identities/review.
- 2026-08-11: Typed generation-threading and terminal-preparation correction
  frozen for targeted specification, correctness, and test review. Diff check,
  JSON parse, 352 coverage assertion, caller-generation-field search, and two
  exact status passes succeed. Current dirty-tree status-list digest is
  `15fc5acedd81ab62b5ad055c76b8c48d196a0bd817bfe47c863d46bef203485c`;
  architecture and binding SHA-256 values are respectively
  `79c0009dbcc4dd194cde6f39b0417d7e9e34cd7747666672c7bf3c47e312a9aa`
  and `1a2fc07240325c6c53cdda1ec53ea0ac06e78a8f7155e014206001b2e461edc1`.
  No production or test implementation is claimed.
- 2026-08-11: DREV-042 found a cycle because the checkpoint receipt named the
  reload digest while the reload embedded the receipt. The result is now built
  in two passes: immutable reload core/core digest, then receipt and successor,
  then final wrapper digest. Receipt binds request/write and core digest but
  never the final reload digest. Only receipt successor threads forward, and
  found recovery returns byte-identical core/receipt/wrapper bytes. Candidate is
  unfrozen pending identities/review.
- 2026-08-11: DREV-042 acyclic checkpoint-result correction frozen for targeted
  review. Diff check, JSON parse, 352 coverage assertion, receipt/reload-cycle
  search, and two exact status passes succeed. Dirty-tree status-list digest is
  `15fc5acedd81ab62b5ad055c76b8c48d196a0bd817bfe47c863d46bef203485c`;
  architecture and binding SHA-256 values are respectively
  `7f4d468e71fc54d8a511e3049063c2e28f3f1dc67e4d11e0fca961131e0eea14`
  and `e0f6ff2d3bf6c49b65b45f8da20eb0500301cf2df2b586118c92fab10fd49ff5`.
  No production or test implementation is claimed.
- 2026-08-11: Terminal-preparation implementation mapping found compiler
  manifest-group coordinates insufficient to construct the existing full
  `IngestionExecutionManifest`. The coordinator now seals a strict
  `BootstrapGraphExecutionManifestConstructionV3` containing every required
  route, governance, message, capability, source/group outcome, validation-
  attempt, blocker, and proof input from already supplied typed authority and
  coordinator state. Terminal preparation receives this construction and
  deterministically derives the manifest with exact byte projection/digest
  equality. No ambient authority was added. Candidate is unfrozen pending
  identities/review.
- 2026-08-11: Complete typed execution-manifest construction correction frozen
  for targeted review. Diff check, JSON parse, 352 coverage assertion, terminal-
  preparation/current-generation signature search, and two exact status passes
  succeed. Current dirty-tree status-list digest is
  `1b75f3a810e43ff85f51342c6e53403eb28d090b30d082df7e2f912873686ee7`;
  architecture and binding SHA-256 values are respectively
  `e3852db7ed7e3c5e533e466fa88bd3e82dbd0690451176684a05886a9924a894`
  and `dbe6725133f87ab82023c70b24519b1a2677b3b97438ae7ad4e1db862bf92f8c`.
  No production or test implementation is claimed.
- 2026-08-11: DREV-043 found a fixed point because operation terminal
  observations needed an execution-manifest digest before the final manifest
  could include those outcomes. The design now seals an acyclic pre-execution
  manifest core/identity after attempt and initial lineage but before CAS.
  Existing operation-record `execution_manifest_digest` carries that identity.
  CAS/effects/results join it. The post-group `IngestionExecutionManifest`
  explicitly binds the pre-identity and then adds final lineage/outcomes/results.
  Found/absent substitutions across either stage reject. Candidate is unfrozen
  pending identities/review.
- 2026-08-11: DREV-043 two-stage execution-manifest identity correction frozen
  for targeted review. Diff check, JSON parse, 352 coverage assertion, manifest-
  identity field mapping search, and two exact status passes succeed. Dirty-tree
  status-list digest is
  `1b75f3a810e43ff85f51342c6e53403eb28d090b30d082df7e2f912873686ee7`;
  architecture and binding SHA-256 values are respectively
  `fcdf9134105ba996cee84990dab17621e146cda31386c4863109f024b04586fb`
  and `5dcaee11759469a0e58f1a58f53703d88ac4d56abcb617bbb40cf76cdb67905c`.
  No production or test implementation is claimed.
- 2026-08-11: DREV-044 found that one final pre-execution identity could not
  represent partial commit followed by related-conflict replacement. Identity
  is now per group and keyed by the producing attempt, plan, and lineage entry.
  The final manifest carries a canonical ordered closure selected from each
  final group result: reused predecessor results retain exact old identity
  bytes, while replacements use successor identities. Source-wide authority
  remains equal, but producer attempt/plan/lineage deliberately may differ.
  Found/absent retained/replaced and swap/collapse/predecessor mutations are
  explicit. Candidate is unfrozen pending identities/review.
- 2026-08-11: DREV-044 per-group producing-identity closure frozen for targeted
  review. Diff check, JSON parse, 352 coverage assertion, singular-identity
  search, and two exact status passes succeed. Dirty-tree status-list digest is
  `1b75f3a810e43ff85f51342c6e53403eb28d090b30d082df7e2f912873686ee7`;
  architecture and binding SHA-256 values are respectively
  `1bc8c93481ff498f74381374220766503badd717b8005c05ad1be6b210e50837`
  and `b09032d3eb977152a482714b7b29ca01c0d3064e966cae4782a2ca24835805fb`.
  No production or test implementation is claimed.
- 2026-08-11: DREV-045 found that the final execution manifest retained only
  the closure digest, so its existing atomic member could not independently
  resolve or validate per-group producing identities. `IngestionExecutionManifest`
  now embeds the complete typed ordered closure alongside an exactly equal
  recomputed closure digest; both participate in the manifest preimage.
  Terminal preparation, the existing manifest member intent, and both found and
  absent persistence paths reconstruct and validate the nested closure without
  adding a tenth member. Digest-only, omitted, altered-retained-with-old-digest,
  and unresolved-identity mutations reject. Candidate is unfrozen pending the
  refreshed identity and targeted review.
- 2026-08-11: DREV-045 self-contained execution-manifest closure correction
  frozen for targeted review. Diff check, binding JSON parse, nested-closure and
  nine-kind assertions, mutation inventory search, and two exact identity
  passes succeed. Dirty-tree status-list digest is
  `1b75f3a810e43ff85f51342c6e53403eb28d090b30d082df7e2f912873686ee7`;
  architecture and binding SHA-256 values are respectively
  `d04c3c6bb8de46ca395a50a1b491877972cbcdcfae1b30094d317a192ef80c7d`
  and `481f76817b73382dc1bfc45f58d09d43bb643255b8238b3bd24fa5f3574a0987`.
  No production or test implementation is claimed.
- 2026-08-11: Implementation mapping after v37 found no typed producer for
  `BootstrapGraphExecutionManifestConstructionV3`: compilation correctly occurs
  before results and terminal preparation incorrectly required the coordinator
  to supply the completed construction. The boundary now assigns every field
  exactly once. Expanded terminal host authority supplies immutable execution-
  graph, route, governance, message, capability, scope, and fence carriers;
  terminal preparation receives final compilation, pre-identity closure,
  attempt/plan, complete lineage, and group constructions, derives all runtime
  projections, then seals construction after results. Prebuilt, ambient,
  defaulted, duplicate-source, and digest-only construction are forbidden.
  Candidate is unfrozen pending refreshed identity and targeted review.
- 2026-08-11: Post-result manifest-construction ownership correction frozen for
  targeted review. Diff check, binding JSON parse, exact terminal signature,
  closed field-source assertions, stale prebuilt-construction search, and two
  identity passes succeed. Dirty-tree status-list digest is
  `1b75f3a810e43ff85f51342c6e53403eb28d090b30d082df7e2f912873686ee7`;
  architecture and binding SHA-256 values are respectively
  `6fd97e1fc134acbf1c6f1a9718c99c78e7b23b0bf68f32b976857d0a5d9e002d`
  and `5dbccf3539e2c7c51ea58bd110a4dbd9cf0b0c91132307e4bfb6f167c22ce4b4`.
  No production or test implementation is claimed.
- 2026-08-11: DREV-046 found that v38 named source outcomes, validation
  attempts, blockers, and terminal-before-planning proofs as projections but
  supplied no sealed typed carrier or durable reload owner. The coordinator now
  constructs strict `BootstrapGraphFinalStageEvidenceV3` from exact final typed
  records, persists/reloads it through a dedicated checkpoint, and threads only
  the receipt successor. Terminal preparation accepts the byte-identical
  evidence and validates request/attempt/plan/lineage/group/epoch joins. Normal,
  partial-replan, and terminal-before-planning shapes are closed; omission,
  duplicate, search, ambient, and digest-only reconstruction reject. Candidate
  is unfrozen pending refreshed identity and targeted review.
- 2026-08-11: DREV-046 sealed final-stage-evidence correction frozen for
  targeted review. Diff check, binding JSON parse, schema/signature/checkpoint,
  four-field closure, nine-terminal-kind preservation, and two exact identity
  passes succeed. Dirty-tree status-list digest is
  `1b75f3a810e43ff85f51342c6e53403eb28d090b30d082df7e2f912873686ee7`;
  architecture and binding SHA-256 values are respectively
  `519178dfb0304ec76cfea95b67369db3b1b6e6f5c4a246df1b8fd4020b05b6c1`
  and `f9e44cba19e1d17809cdced0973e9f922cf24c223d4e82c2763b81079eda1c7a`.
  No production or test implementation is claimed.
- 2026-08-11: The v39 implementation-readiness audit found that pre-execution
  manifest cores required validation attempts, blockers, and terminal-before-
  planning proofs before the first CAS, while only post-CAS final-stage evidence
  carried those complete tuples. `BootstrapGraphPlanCompilationV3` now contains
  one strict complete `BootstrapGraphPreExecutionGroupEvidenceV3` per plan group;
  attempt inputs bind its canonical digest projection and the plan checkpoint
  persists/reloads the complete evidence. The coordinator copies only the
  matched reloaded typed evidence into each pre-identity. Empty/default/ambient,
  digest-only, cross-group, and post-CAS evidence substitution reject before
  identity seal or CAS. Candidate is unfrozen pending refreshed identity and
  targeted review.
- 2026-08-11: Pre-CAS group-evidence ownership correction frozen for targeted
  review. Diff check, binding JSON parse, compiler/attempt/checkpoint schema,
  complete evidence-field and pre/post-CAS separation assertions, and two exact
  identity passes succeed. Dirty-tree status-list digest is
  `1b75f3a810e43ff85f51342c6e53403eb28d090b30d082df7e2f912873686ee7`;
  architecture and binding SHA-256 values are respectively
  `a66e3f965b9f1b4c615ae2904665e79c62f8b8e85a4a6847b189c0df357e1988`
  and `d9d21cf85af96884060f06f2b7b0cd8f67f4f6df417af548c0058ffc74aa4b91`.
  No production or test implementation is claimed.
- 2026-08-11: M3.1 remediation found that ordinary V3 roots still depend on a
  fixture-shaped in-memory authority provider, while the recovery record lacks
  graph snapshot/read-set, full policy/capability, and prepared-source terminal
  authority.  The architecture now requires one persisted, store-reloaded
  same-generation `BootstrapGraphTransactionAuthorityProjectionV3` before the
  epoch and plan checkpoints.  Its sources are the atomic graph snapshot/read
  set, reloaded `SourceNormalizationDerivationAuthority` policy/capability
  authority, and atomically published/reloaded `PreparedSource`; terminal host
  authority is a closed projection of those values plus sealed compilation.
  Static fixture providers remain test seams only and cannot supply ordinary
  roots.  Missing or incompatible authority is a zero-effect pre-graph
  noncommit; replay, migration, rollback, and the four-root attack family are
  explicit.  This is design-only; no production or test implementation is
  claimed.
- 2026-08-11: The v41 review confirmed three linked authority-boundary gaps.
  Policy and capability authority now form one strict canonical-byte member of
  the atomic normalization generation and the graph builder can load it only
  through typed replay; caller-supplied derivation authority is removed.  The
  pre-epoch projection now has its own recovery/projection-keyed generation,
  core, receipt, and reload family, with epoch zero as the only exact bridge to
  request/epoch-bound checkpoint generations.  A complete replacement
  `BootstrapGraphHostBundleV3` is mandatory in direct, factory, filesystem, and
  Hermes roots; fresh and recovery order is closed, recovery authority reload
  precedes terminal locator lookup, and the fixture-shaped provider is test-
  only.  The binding map preserves the concurrently completed request/recovery
  terminal-index validation while recording zero current production callers
  for the new authority repository.  Fresh/found ambient authority mutation,
  generation-family confusion, bridge, bundle omission, and lookup-order
  attacks are explicit.  No production or test implementation is claimed.
- 2026-08-11: The v42 specification review confirmed one narrow generation-
  bridge gap: epoch zero named only the successor generation digest and did not
  carry the typed store-reloaded pre-epoch receipt that authorizes that digest.
  The transition request and persisted epoch now carry the exact
  `BootstrapGraphAuthorityPublicationReceiptV3`; both preimages bind the typed
  receipt followed by its successor-generation digest.  Before epoch-zero CAS,
  the repository validates receipt, recovery/projection/write/core/store/
  generation closure and exact replay, ingress, scopes, fence, initial lease,
  and writer equality.  Omitted, substituted, cross-generation, stale, digest-
  only, and post-epoch receipt attacks reject before epoch append.  The binding
  CTV and call order now place projection publish/reload and receipt validation
  before epoch zero.  Correctness/test observations that the new repository has
  zero production callers and ordinary roots still use the old path are
  expected implementation obligations at specified/derivable maturity, not
  semantic design defects.  No production or test implementation is claimed.
- 2026-08-11: The v43 targeted review confirmed the typed pre-epoch receipt
  semantic finding closed.  Review could not issue a revision-bound disposition
  solely because concurrent post-effect recovery and CI binding updates made
  the candidate's dirty-tree status identity stale.  Those binding updates are
  preserved unchanged and introduce no new semantic finding in this design
  slice.  With concurrent writes stopped, v43 semantics are re-frozen as v44
  against the stable architecture, binding map, WorkPlan, and status identity.
  No production, test, CI, or operational maturity is claimed by this re-freeze.
- 2026-08-11: The v45 feasibility audit found that the earlier compiler,
  authorizer, and executor protocols had no production implementation and that
  fixture code fabricated reconciliation, reference-closure, plan-artifact,
  proposed-effect, reservation, and receipt digests. The architecture now
  specifies three built-in local adapters over the existing transaction
  coordinator, graph-planning/identity, admission/reservation, persistence, and
  atomic-store owners. The unreleased V3 shape is narrowed to a complete native
  sealed snapshot/read-set/ledger plus typed planning-state/frozen-artifact
  fold; reservation authority is an explicit none/use union; event and effect
  receipts arise only after the store CAS. Direct, factory, filesystem, and
  Hermes roots must construct this closed bundle and cannot inject fixture
  producers. Migration, rollback, absence behavior, field-source tests, and
  the four-root/backend attack matrix are specified. Candidate is unfrozen
  pending identity checks and independent review; no production code changed.
- 2026-08-11: The native local-adapter correction is frozen as candidate v45
  for targeted specification, correctness, and test review. Diff whitespace,
  binding JSON, native contract/adapter/absence anchors, and two exact identity
  passes are required. Evidence remains design-only: no production adapter,
  ordinary-root activation, deterministic test, CI, or operational maturity is
  claimed.
- 2026-08-11: Targeted v45 review rejected the candidate on two confirmed
  feasibility gaps. The design named pure identity planning without defining a
  canonical non-publishing API over the outer sealed snapshot/group/current
  planning state, and it projected an effect receipt after a persistence call
  that did not atomically issue the required V3 result/receipt closure. v46 adds
  `IdentityOperationPlanner.plan_nonpublishing` with an exact pure state-fold
  result and a store-owned `BootstrapGraphGroupCommitRepositoryV3` whose single
  CAS persists request index, semantic effects, result core, atomic receipt,
  successor generation, and reload. Executor, durable retry, final evidence,
  manifest, source result, and terminal now thread the exact typed reload. An
  exhaustive table removes or replaces every legacy/synthetic plan, attempt,
  manifest, CAS, result, retry, and terminal effect field with strict mixed-
  shape rejection. Attacks/tests cover every row and pre/post-CAS failure cut.
  Candidate is unfrozen pending stable identity; no production code changed.
- 2026-08-11: v46 non-publishing planner and atomic group-commit ownership is
  frozen for targeted review. Diff whitespace, binding/candidate JSON,
  planner/store API anchors, all supersession rows, and two exact artifact and
  status identity passes are required. Evidence remains specified/derivable;
  no implementation, test, CI, root activation, or operational claim is made.
- 2026-08-11: v46 review confirmed two remaining specification gaps. The pure
  planner did not receive operation/candidate or define base/sequence/applied-
  delta continuity, and downstream same-named V3 schemas still normatively
  exposed old outcome/effect/receipt fields. v47 defines one state-aware pure
  helper and exact missing-input/discontinuity failures, including multi-op
  same-group and continuing cross-group folds. It replaces execution result,
  group construction, attempt inputs, manifest group input, final evidence,
  durable retry, source-result input, and terminal request with reload-only
  schemas; fixes CTV domains, member kinds, primary/reverse indexes, cardinality,
  and reload validation; and withdraws all old codecs/kinds without aliases.
  Terminal publication is unrepresentable without the complete reload
  bijection. The test design now requires a machine-checked row for every
  carrier/mutation/cut/index across four roots and memory/independent JSONL,
  including default built-ins, convergence/conflict/auth, old/mixed rejection,
  and rollback replay/new-operation denial. Candidate is unfrozen pending
  stable identity; no production or test code changed.
- 2026-08-11: Correctness DREV-048 confirmed that v46/v47's singular semantic
  group result could not represent a multi-operation transaction group. The
  store request now contains an ordered per-operation input bijection to the
  plan member; the result core contains one ordered typed semantic result per
  operation; and the receipt carries the exact result-digest projection. The
  complete nested vector remains inside the reload through retry, final
  evidence, manifest, source, and terminal. Explicit non-empty no-op groups
  produce one noncommitting result and observation per operation with no graph
  or event digest. Missing, duplicate, reordered, cross-operation, extra, and
  singular substitutions reject. Selector rows cover committing, mixed, no-op,
  and malformed multi-operation groups. No production/test code changed.
- 2026-08-11: v47 state-aware planning and reload-only downstream schema
  correction is frozen for targeted review. Diff whitespace, binding/candidate
  JSON, planner continuity, downstream schema/cardinality, codec/member/index
  withdrawal, selector-matrix anchors, and two exact identity passes are
  required. Evidence remains specified/derivable only.
- 2026-08-11: v47 review confirmed that reload/index identity remained keyed by
  a singular member operation despite multi-operation group semantics. v48
  keys request, reload, primary index, and repository methods by source control,
  transaction group, complete canonical operation vector, and request CTV;
  per-operation indexes are explicit fanout to the same whole-group reload.
  Two-operation lost-ack/reopen/retry/terminal and convergence/conflict attacks
  are exact. The active binding map now uses only GroupCommitRequest-to-
  GroupCommitReload, with old execution vocabulary purged and a denylist
  validator/mutation family specified. Correctness also closed the failure
  partition: every pre-CAS failure has zero reload/observation/revision and
  durable retry only after attempt/lineage; a reload may be committed or
  noncommitting, never failed, with exact per-operation result and group revision
  algebra. Candidate is unfrozen pending stable identity. Missing implementation
  evidence and zero callers remain expected and truthful; no code changed.
- 2026-08-11: v48 group-keyed identity, exclusive binding vocabulary, and
  closed group-failure partition are frozen for targeted review. Diff/JSON,
  denied-token absence, group/index/fanout/failure anchors, and two exact
  artifact/status identity passes are required. Maturity remains design-only.
- 2026-08-11: Surgical v49 binding audit found one stale active sentence inside
  the v47 evidence entry that still described a scalar operation-keyed primary
  index. It now states the v48 group primary and complete-operation-vector
  fanout rule. The v48 mutation contract explicitly rejects restoration of the
  stale scalar form anywhere in active bindings. Architecture semantics and
  production/test code are unchanged. v49 is frozen for targeted binding review.
- 2026-08-11: Implementation readiness review found that even the group-keyed
  commit request lacked typed semantic inputs from which the store could create
  the terminal, artifact closure, group result, graph/event/observation records,
  and exact receipt without ambient lookup. v50 adds one complete typed semantic
  compilation/terminal/artifact-closure reduction and store-materialization
  input per operation. The store derives all persistence effects and coordinates
  inside its one linearization. v50 also replaces the old parallel-vector plan
  member with one complete snapshot/read-set/ledger/state-bound group schema and
  ordered operation-plan records, with exact planning fold, reservation union,
  preimages, cardinality, and limits. Coordinator, plan checkpoint, attempt,
  evidence, authorization, group request, manifest, retry, final, source, and
  terminal consumers are explicitly mapped; no removed field has a consumer.
  Four-root public-constructor and mutation tests are specified. Candidate is
  unfrozen pending stable identity; no production/test code changed.
- 2026-08-11: v50 typed store materialization and complete plan-member closure
  are frozen for targeted review. Diff/JSON, schema/preimage/limit/consumer-map
  anchors, and two exact artifact/status identity passes are required. Evidence
  remains specified/derivable; implementation and tests are not claimed.
- 2026-08-11: v50 review required one exhaustive active supersession block so
  implementers do not reconcile older same-named sketches or inherited fields.
  v51 defines the complete PlanCompilation carrying typed reductions, exact plan
  checkpoint member kinds/order and byte payloads, current group planning
  authorization with typed reservation union, and one full GroupCommitRequest
  CTV. Reduction-to-operation-plan-to-authorization-to-materialization joins are
  ordinal and complete. Every obsolete field/domain/kind/discriminator is a
  strict pre-lookup decode failure. Mutations cover missing/extra/reordered/
  cross-group reductions and members, byte-identical checkpoint recovery,
  reservation bijection, and four-root no-ambient constructors. Candidate is
  unfrozen pending stable identity; no production/test code changed.
- 2026-08-11: v51 exhaustive active planning-to-commit supersession is frozen
  for targeted review. Diff/JSON, schema/member/order/preimage/join/obsolete-
  decode anchors, and two exact artifact/status identity passes are required.
- 2026-08-11: Surgical v52 retires the residual
  `BootstrapGraphPlanAuthorizationSetV3` aggregate. The authorizer now returns a
  canonical ordered tuple of individual group authorizations matching the
  reloaded plan group-member vector. The coordinator publishes one atomic
  authorization member per group in that order; ordinary checkpoint reload
  returns exact bytes; initial/successor attempts and group commit consume only
  the matching individual authorization. The old aggregate schema/domain/kind/
  digest is strict obsolete decode failure. Missing/extra/reordered/cross-plan/
  stale/substituted and reservation mutations reject before CAS. v52 is frozen
  for targeted review; no production/test code changed.
- 2026-08-11: Implementation readiness review found that the graph compiler's
  request/dependency inputs could not lawfully derive v50 semantic compilation
  and terminal reductions. v53 adds one normalization-owned, same-generation,
  atomically persisted/reloaded semantic-reduction authority containing complete
  typed proposal, observations, candidates, independent analysis, arbitration,
  policy, authorization read set, identity-decision triple, and dependency-group
  identity per operation. Graph authority projection, pre-epoch receipt,
  coordinator request/core, plan compilation, attempt inputs, and plan checkpoint
  bind the exact reload. The built-in compiler consumes only those bytes plus
  the sealed graph snapshot/current planning state; earlier pipeline stages,
  ambient lookup, caller authority, defaults, and fabrication are forbidden.
  Roots, CTVs, order, limits, absence, migration, rollback, and mutation/reopen/
  replan proofs are explicit. Candidate is unfrozen pending stable identity; no
  production/test code changed.
- 2026-08-11: v53 persisted semantic-reduction authority is frozen for targeted
  review. Diff/JSON, owner/schema/CTV/order/root/migration/test anchors, and two
  exact artifact/status identity passes are required. Evidence remains design-only.
- 2026-08-11: Surgical v54 exhaustively supersedes the normalization V3 outer
  atomic request. It adds the typed semantic-reduction authority request, full
  member registry/order, and a singleton semantic-authority member immediately
  before graph-normalization authority. The pre-publication request binds known
  expected/publication generations plus fence/writer, avoiding a final-write
  digest cycle. SourceNormalizationExecutionOwner's complete input and the store
  decode/authenticate/CTV/order/join/CAS/reload algorithm are exact. Omitted,
  duplicate, reordered, substituted, foreign-generation, digest-only, and valid-
  member-wrong-position forms reject.
- 2026-08-11: Correctness DREV-050 also corrected identity staging in v54.
  Normalization persists only graph-free identity operation/candidate/analysis/
  evidence/policy/capability/fence input. Initial and replacement planning derive
  a fresh accepted/trusted/verified triple after each sealed snapshot/read set;
  lawful reuse retains predecessor bytes and performs no planner call. Snapshot-
  bound/partial triples in normalization and stale replacement triples reject.
  v54 is frozen for targeted review; no production/test code changed.
- 2026-08-11: Surgical v55 consolidates duplicate normalization grammar. Earlier
  outer request, atomic member, semantic authority member, and recovery replay
  declarations are renamed `Historical*Grammar` and have no runtime authority.
  v54/v55 now contain exactly one active declaration for each current type, and
  recovery replay targets only the complete v54 outer request with exact found
  reverse joins. Legacy bytes are offline read-only inspection artifacts; they
  cannot be converted, inferred, returned by production replay, promoted to
  graph V3, or used for new writes. Static exactly-one-declaration and runtime
  legacy/relabel/nesting/rollback rejection tests are specified. v55 is frozen
  for targeted review; no production/test code changed.
- 2026-08-11: v55 review confirmed a type-owner mismatch: bootstrap normalization
  does not produce the generic proposal/observation/candidate/analysis/arbitration
  inputs named by v53. v56 withdraws that grammar and defines the semantic
  authority solely from retained `BootstrapProposalRunPayloadV3`, exact four-lane
  results, `BootstrapGraphFreeInterpretationBundleV3`, and
  `BootstrapSourceProposalAlignmentV3`. Each operation input carries the exact
  proposal member, subject, consensus/alignment, identity partition/resolution,
  dependency, coverage, and optional native graph-free identity carrier. The
  native reducer maps those bytes plus the sealed snapshot directly to native
  compilation, terminal, and closure without generic reconstruction/compiler or
  ambient lookup. Joins, preimages, limits, persistence, migration, all five
  operation kinds, and mutation/recovery tests are explicit. v56 is frozen for
  targeted review; no production/test code changed.
- 2026-08-11: v57 removes a prepublication replay fixed point by replacing the
  semantic authority's replay digest with recovery key and acyclic normalization
  request-core identity. The store adds atomic-write/publication generations and
  computed replay digest only in the post-CAS authority reload. It also replaces
  the last generic graph-free identity arm with a native carrier built from the
  retained identity member, subject, provenance, partition evidence, source-
  local resolution, alignment, dependency group, and fence. Finally, each native
  operation receives an explicit coverage binding joining operation/event/
  disposition/proposal/member/provenance/alignment for covered and unresolved
  rows. Preimages, reverse joins, ambiguity rules, old-shape rejection, lost-ack,
  identity staging, and coverage mutations are explicit. v57 is frozen for
  targeted review; no production/test code changed.
- 2026-08-11: v58 resolves DREV-052/053 by making
  `BootstrapNormalizationRequestCoreV3` an exhaustive ordered typed object
  constructed before either authority and embedded byte-identically in the
  semantic-authority and outer requests. Its preimage explicitly excludes all
  authority/member-dependent, atomic-write, found, replay, and wrapper state;
  store recovery reloads and authenticates exact core bytes first. Coverage is
  now a canonical nonempty vector under one stable operation-execution identity.
  The vector models two-events/one-operation, one-event/multiple-operations,
  unresolved, and mixed coverage without multiplying downstream operation IDs.
  DREV-051 remains a truthful zero-caller/default-composition implementation
  obligation, and the mandatory construction order is unchanged. v58 is frozen
  for targeted review; no production/test code changed.
- 2026-08-11: v59 closes the implementation-discovered native reduction gap.
  `BootstrapGraphOperationReductionV3` now contains only exact native
  compilation, terminal, artifact-closure, and effect-materialization records,
  bound to the sealed snapshot/read set and stable operation execution identity.
  Its accepted union is exhaustive across fact, correction, retraction,
  action-state, and identity, with deterministic carrier and record-intent
  mappings; unresolved, rejected, and evidence-only are a closed zero-intent
  partition. The store remains sole owner of deltas, versions, events,
  observations, revisions, commit time, CAS receipt, and reload. Generic
  compilation/terminal/closure fields, codecs, consumers, and mixed shapes are
  explicitly obsolete. v59 is frozen for targeted review; no production/test
  code changed.
- 2026-08-11: v60 resolves DREV-054/055 with a mechanically checkable five-arm
  validation table. Each arm now has exact carrier shape, ordered record-intent
  kind blocks, input-derived cardinality, field sources, and observation
  disposition/reasons. Correction alone may contain one nonrecursive nested
  replacement fact; its complete fact intent vector is spliced once under the
  same operation identity and never becomes a second result. One pure validator
  is required before either store. The V3 supersession matrix now exhaustively
  names plan member, registry/codec, encoder/decoder, store, persistence/reload,
  replay/recovery, converter, retry/final/terminal surfaces and their native
  replacement or rejection. Supersession is explicitly Bootstrap V3-only;
  generic contracts remain valid for governed non-V3 flows. v60 is frozen for
  targeted review; no production/test code changed.
- 2026-08-11: v60's supersession table is additionally closed against the
  complete literal `BootstrapGraphPlanAtomicMemberV3.kind` vocabulary and its
  terminal-member subset. It names the sole reduction payload owner, literal
  qualified codec keys, encoder/decoder, store materialization, persistence,
  found reload, replay/recovery, and each member's exact native projection or
  rejection. This is a design-only contract correction: current generic V3
  code remains implementation debt, while separately governed non-V3 generic
  contracts remain valid and unchanged.
- 2026-08-11: v61 resolves the v60 delta findings by fixing the nested
  correction equality path to
  `correction.replacement_effect.fact == correction.correction.replacement_fact`
  and making all inherited outer identities/provenance explicit. The V3
  supersession contract now has one row for every one of the 21 literal atomic
  member kinds and identifies its literal codec key, encoder, decoder,
  persisted member, found reload, recovery consumer, native projection or
  prohibition, and pre-decode fail-closed behavior. The row-validator/mutation
  corpus includes all 21 rows and the terminal subset. v61 is frozen for
  targeted review; no production/test code changed.
- 2026-08-11: v62 retires every stale 19-item graph atomic-member order and
  every claim that normalization authority reload, operation-plan vectors,
  operation-reduction vectors, or attempt-construction inputs are graph member
  kinds. Graph checkpoint order and references now derive only from the 21
  literal `BootstrapGraphPlanAtomicMemberV3.kind` registry; nested projections
  are explicitly non-kinds and the nine-member terminal subset is unchanged.
  The required static architecture/binding validator rejects omissions,
  additions, aliases, array pseudo-kinds, stale orders, and cross-artifact
  disagreement. v62 is frozen for targeted review; no production/test code
  changed.
- 2026-08-11: v63 explicitly withdraws the remaining V51 prose and binding
  claims that described operation-plan, operation-reduction, and
  attempt-construction-input members as a fixed/current checkpoint order.
  Those claims are historical only; the v62 21-kind registry and closure table
  are the sole active order authority. The static validator now mutates a
  restoration of the former V51 phrasing/order and requires rejection. v63 is
  frozen for targeted review; no production/test code changed.
- 2026-08-11: v64 closes the implementation-discovered owner gap between v58
  retained authority and v59/v60 native effects. It defines the complete
  `BootstrapGraphTargetMaterializationPlannerV3` request/result family and the
  sole built-in production owner. The planner deterministically resolves graph
  targets, creates dual planning/durable record payloads and preconditions,
  terminal binding sets, exact citation/provenance projections, the planning
  state fold, and fresh identity materialization for all five arms from only
  retained native input plus the sealed snapshot/read set. The reducer now only
  validates/projects this explicit plan into effects and intents; generic
  `compile_accepted_carriers`, ambient lookup, and partial plans are forbidden.
  Host-bundle composition and all four roots require the built-in planner, with
  recovery validating persisted plan bytes rather than replanning. v64 is
  frozen for targeted review; no production/test code changed.
- 2026-08-11: v65 combines the v64 reviews into a fully V3-native pre-CAS
  closure. Target authority is now an exact snapshot-or-pending union with
  pending-state precedence, including removal/transition preconditions. Planner
  records contain only planning payloads; the store creates durable payloads and
  references inside CAS. Native temporal bindings and the exact ordered
  duplicate-free planning-record union close target/effect/evidence/identity
  bijections. A pure V3 identity-admission port derives fresh accepted/trusted/
  verified inputs and calls `plan_nonpublishing` once for initial/replacement,
  while reuse and absence are zero-call. Reducer plan and unavailable arms are
  request/operation-bound; unavailable maps exactly to a zero-effect native
  terminal/closure. v65 is frozen for targeted review; no production/test code
  changed.
- 2026-08-11: Surgical v66 closes the identity-admission mode/nullability
  contradiction. Initial alone requires no predecessor. Replacement and reuse
  require an exact predecessor; replacement rejects before planning unless both
  current snapshot and read-set authorities differ from the predecessor result,
  then derives a fresh triple and plans once. Reuse returns predecessor
  materialization byte-identically with zero derivation/planner calls. Mode,
  nullability, predecessor substitution, and stale snapshot/read-set mutations
  are explicit. v66 is frozen for targeted review; no production/test code
  changed.
- 2026-08-11: Surgical v67 adds transaction-group identity to the native
  identity-admission request and closes every predecessor join. Replacement and
  reuse require predecessor result group equality, graph-free input digest
  equality, and request operation-execution identity on all materialization
  records. Reuse has one canonical state rule: current planning state must equal
  predecessor `planning_state_after` byte-for-byte; later, earlier, or rebuilt
  states reject. Cross-group, state, input, and record substitution tests are
  explicit. v67 is frozen for targeted review; no production/test code changed.
- 2026-08-11: v68 closes the implementation feasibility gap between retained
  mention/selector evidence and native planning records. It adds a sealed target-
  resolution authority with exact mention-cluster and selector-to-snapshot/
  pending mappings, proof-gated deterministic entity creation, and closed
  missing/ambiguous behavior. A five-arm planning-seed union now supplies every
  canonical planning payload field and stable ID from typed retained input,
  target authority, consensus/evidence, registry policy, or planned commit
  coordinate. Correction/retraction require existing selector targets;
  correction alone constructs one exact replacement fact seed. The sole
  production projector/module, algorithms, CTVs, store boundary, mutations, and
  four-root golden vectors are explicit, with no generic compiler or ambient
  lookup. v68 is frozen for targeted review; no production/test code changed.
- 2026-08-11: v69 corrects the identity-authority boundary exposed by review.
  A typed, authenticated source-wide canonical identity binding/allocation
  authority now maps every referenced cluster exactly once to an existing
  scoped target with proof or one stable new allocation. It is persisted and
  reloaded before operation planning and binds snapshot/read set, planning
  state, required scope, authorized scope, allocation namespace, recovery, and
  generation. Entity seeds carry the complete ordered mention vector, cluster,
  decision/proof digests, and complete alias/type proof closure; exactly one
  seed exists per newly authorized cluster, and later operations reuse its
  pending target. Existing and absent decisions create zero identities. Root
  composition and stale/cross-scope/cluster/proof/multi-mention/recovery tests
  are explicit. v69 is frozen for targeted review; no production/test code
  changed.
- 2026-08-11: v70 combines the v69 review findings into a closed identity
  decision and first-use algebra. It explicitly retires v68's per-operation
  allocation ID rule; referenced clusters now biject with existing/new/absent
  decisions sharing one canonical proof preimage. New decisions bind allocation
  policy and complete identity reservation, collision read extension, expected-
  absent writes, reservation-use and CAS checks. Source-plan order selects one
  seed producer; only it may use new-first-use authority, while later operations
  depend on and reuse its pending record even under reversed runtime order.
  Identity admission embeds the exact authority reload and reverse-joins all
  predecessor/successor/reference/materialization records. v70 is frozen for
  targeted review; no production/test code changed.
- 2026-08-11: v71 closes target-arm wire semantics and persists first-use order.
  Snapshot, pending, new-first-use, and absent arms now have exact CTV domains,
  preimages, discriminators, cardinalities, and cross-arm rejection. A typed
  dependency vector persists producer/consumer execution, group, and plan-member
  identities per cluster proof. Immutable authority base planning state is
  separated from each operation's prefix proof: producer uses base, consumers
  prove the exact prefix containing byte-identical producer records. The complete
  typed authority reload is threaded through identity admission/materialization,
  compilation/reduction, checkpoint, and replay/terminal closure; digest-only or
  searched reconstruction rejects. The 21-kind atomic registry is unchanged;
  these are nested group-compilation artifacts. v71 is frozen for targeted
  review; no production/test code changed.
- 2026-08-11: v72 breaks the first-use/compilation cycle with a persisted pre-
  compilation source-operation membership vector derived only from normalized
  group and operation order. Dependencies and prefix proofs use memberships;
  compiled plan members reverse-bind them afterward. Each cluster dependency
  bijects producer plus all later consumers to all cluster references. Prefix
  proofs contain the full preceding membership vector, including intervening
  operations, with exact state fold and producer entity/alias/type record subset.
  Pending/new-first-use arms embed the complete prefix proof, never a digest-only
  duplicate. Terminal decodes/authenticates the complete authority, source/
  recovery/generation/base/membership/dependency/prefix closure before any index
  access. v72 is frozen for targeted review; implementation absence remains a
  later evidence obligation and no production/test code changed.
- 2026-08-11: Surgical v73 makes first-use dependency occurrence-aware while
  preserving membership-level producer selection and prefix folding. Every
  retained cluster reference now has one canonical membership/cluster/source-
  coordinate occurrence. Producer occurrences cover all references in the
  earliest membership; consumer entries cover every occurrence in later
  memberships; their union bijects all references. New-first-use and pending
  arms bind the exact coordinate. Same-cluster subject/object, repeated action
  participants, and correction nested replacement references remain distinct
  while sharing one allocation and seed. v73 is frozen for targeted review; no
  production/test code changed.
- 2026-08-11: Surgical v74 defines the sole seed-producing occurrence as the
  lexicographically first unique source-coordinate digest in the producer
  membership. The selected coordinate is carried in the new decision, new-
  first-use authority, and entity seed at exact CTV ordinals and is recomputed
  throughout reload/recovery/terminal validation. Nonselected producer
  occurrences bind the same allocation/target but emit no seed; later occurrences
  remain pending. Swap, substitution, duplicate/tie, extra-seed, and recovery
  mutations are explicit. v74 is frozen for targeted review; no production/test
  code changed.
- 2026-08-11: v75 confirms that v74 retained native input was not construction-
  complete. It adds one same-generation persisted/reloaded typed planning-
  construction authority containing governance/admission, predicate/action
  policy, temporal evidence/decision, codec, source authority, and identity
  authority-record/verifier bytes. A literal constructor table maps every live
  Planning payload, snapshot/mutation/ledger field and identity accepted,
  artifact, trusted, and verified field to an exact nested V3 path; missing,
  duplicate, substituted, partial, digest-only, defaulted, ambient, clock, or
  generic-compiler data rejects. The built-in projector is the sole production
  owner and all four roots/two backends retain design-only implementation and
  evidence obligations. v75 is frozen for targeted review; no production/test
  code changed.
- 2026-08-11: Surgical v76 resolves the demonstrated accepted-fact terminal
  blocker. The native group-commit reload is now wrapped once with its exact
  request/attempt/lineage/member/authorization/pre-execution/epoch joins as the
  persisted `transaction_group_result`; no CAS-shaped execution result,
  construction, carrier, or per-effect receipt survives on a native V3
  downstream surface. Final evidence, retry, manifest, canonical source result,
  terminal publication, and found reload carry its exact ordered nested reload
  digest projection and resolve it through the persisted wrapper, while
  disposition and terminal status are derived solely from the nested
  store reload. The twenty-one member-kind registry is unchanged. v76 is
  frozen for targeted review; no production/test code changed.
