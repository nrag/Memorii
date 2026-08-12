# Graph-Free Source Alignment Producer Design

- Work ID: semantic-ingestion-source-alignment-producer-2026-08-10
- Work type: design
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-08-10
- Last updated: 2026-08-10
- Parent WorkPlan: `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/design.plan.md`; `docs/work/semantic_ingestion/milestones/m3-semantic-pipeline.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md`; `docs/design/memorii_spec.md`; `docs/design/memorii_storage_details.md`; `docs/design/event_model.md`; `docs/IMPLEMENTATION_RULES.md`
- Expected outputs: implementation-ready producer contract and derivation algorithm for graph-free scope, temporal attachment, source-local identity, alignment, grouping, and atomic publication authority

## Objective

Close the design-to-code gap that prevents production from constructing
`SourceProposalAlignment` without fabricated authority. Define what the primary
and corroborating analyzers emit, how source-only scope and temporal consensus
are derived, how source-local identity becomes a total partition, and how those
artifacts enter the source-normalization generation before graph access or
terminalization.

## Completion Contract

Complete only when every producer input and output has a canonical owner,
strict typed shape, deterministic derivation or fail-closed outcome, policy and
digest authority, atomic publication member, replay/recovery rule, production
callsite, and family-complete positive/adversarial proof; a frozen candidate
must pass independent specification, correctness, and test review with no
remaining validated P1/P2, `blocks_approval`, or `changes_required` finding.

## Scope

Included: analyzer scope interpretations, analyzer temporal attachments,
source-local identity evidence-to-partition derivation, scope and temporal
consensus, operation alignment, deterministic source grouping, pipeline
intermediate API, atomic source-normalization membership, provider callsite,
strict replay, and failure/no-disclosure behavior.

Excluded: graph lookup, canonical graph identity, graph reconciliation,
planning compilation, attempts, lineage, CAS, M4, new learned calls, and
terminal-persistence performance.

## Constraints And Invariants

- All derivation is graph-free and source-only.
- Provider proposal bytes may align against evidence but cannot create or
  resolve scope, attachment, identity, or consensus authority.
- Primary and corroborating outputs remain distinct; equality is explicit and
  disagreement is non-promoting.
- Source-local identity is a total source mention partition with explicit
  unresolved clusters; it never imports canonical graph identity.
- Every retained artifact is typed, content-addressed, policy-bound, published
  in one source-normalization generation, and reloaded before alignment use.
- Missing or ambiguous evidence fails closed with zero graph effect; no
  terminal output is reverse-engineered into source authority.

## Problem And Current Evidence

`IndependentSourceAnalysis` carries parser consensus, raw
`SourceLocalIdentityEvidence`, and raw `SourceTemporalEvidenceSet`. It does not
carry `AnalyzerScopeInterpretation`, `AnalyzerTemporalAttachment`,
`SemanticScopeConsensus`, `TemporalAttachmentConsensus`, or
`SourceLocalIdentityResolution`. `SourceProposalAlignment` requires the latter
three authority families and exact operation-alignment joins. Before this
operation, the architecture defined their validators and high-level equality
constraints but did not bind a concrete production producer API or complete
derivation from the existing pipeline output. The canonical delta now freezes
that contract. Constructing them from `SemanticTerminalOutcome` remains
prohibited because it reverses publication order and fabricates authority.

## Requirements And Acceptance Criteria

| Requirement | Observable contract | Acceptance |
| --- | --- | --- |
| SAP-R01 Analyzer evidence | Each analyzer produces one typed scope interpretation and temporal attachment per proposal/operation/segment/route. | Complete coordinate bijection; omitted, duplicate, cross-source, cross-route, proposer-derived, or same-analyzer pairing rejects. |
| SAP-R02 Scope consensus | Equality of the two source-only interpretations yields stable scope only when every required check passes. | Exact stable/disagreement/ambiguous/unsupported state machine with no confidence/order tie-break. |
| SAP-R03 Temporal attachment consensus | Equality of two analyzer attachment sets yields stable candidates only when each candidate is independently resolved and policy-authorized. | Zero/multiple/conflicting/ungrounded candidates remain explicit and non-promoting. |
| SAP-R04 Source-local identity | All grounded mentions become one deterministic total partition from typed source evidence. | Exact mention coverage, canonical clusters, explicit unresolved cases, no graph identity or provider hint. |
| SAP-R05 Alignment and groups | Complete retained artifacts join one-to-one into operation alignments and deterministic graph-free dependency groups. | Exact row/group coverage and ordering; every incomplete join fails before graph access. |
| SAP-R06 Atomic authority | Request, result, manifest, policies, selections, retained artifacts, alignment, groups, and ingress/fence binding publish and reload in one generation. | Lost-ack byte idempotency; missing/extra/foreign/substituted/partial/reordered member rejects without live reconstruction. |
| SAP-R07 Production reachability | Provider ingestion invokes the producer after graph-free analysis and before terminal or graph-dependent work. | At least one ordinary root caller; absence yields typed noncommit and zero graph calls. |

These coordinates are planning metadata only and may not name production,
persisted, test, fixture, command, workflow, or diagnostic identities.

## Identity And Coordinate Hygiene

| Surface | Proposed identity | Class | Disposition | Proof |
| --- | --- | --- | --- | --- |
| WorkPlan requirements | SAP-R01--SAP-R07 | planning/evidence | retain only here and typed traceability | field-aware scan |
| Pipeline API | behavior-derived graph-free analysis/alignment name | behavioral | writer must freeze | durability audit |
| Producer/repository/contracts | behavior-derived scope, attachment, identity, normalization names | behavioral/protocol | writer must freeze | identity matrix |

## Production Entrypoint Binding

| Trigger/root | Callsite | Authority in | Owner chain | Durable outcome | Current proof |
| --- | --- | --- | --- | --- | --- |
| `ProviderMemoryService.sync_event` -> `ProviderIngestionCoordinator.ingest` | after source analysis, before terminal or graph work | prepared source, proposal, analysis bundle, language route, request-owned policies/selections, ingress/fence/lease | analyzer evidence -> consensus -> source identity -> alignment/groups -> atomic publish/reload | reloaded `SourceProposalAlignment` and groups or typed noncommit | zero current constructors/callers |

The implementation binding is intentionally a future production transition,
not a claim about current callers. `ProviderMemoryService.sync_event` has one
ordinary production caller today; `ProviderIngestionCoordinator.ingest` has the
existing service composition but zero `SourceProposalAlignment` constructors.
Implementation must update the parent binding map before claiming SAP-R06 or
SAP-R07 complete, prove a non-test caller reaches
`GraphFreeSourceNormalizationStage.normalize`, and record the exact mandatory
arguments through the factory, filesystem, and Hermes roots. Optional pipeline
injection, fixture-only analyzers, or a legacy terminal path are insufficient.

| Future requirement binding | Required non-test caller proof | Required authority/outcome |
| --- | --- | --- |
| SAP-R01--SAP-R05 | `sync_event -> ingest -> GraphFreeSourceNormalizationStage.normalize` with the parameterized real-trigger matrix | admitted source, complete source-wide analyzer bundle, role-complete temporal and identity inputs; reloaded generation or `source_alignment_authority_unavailable` before graph/terminal work |
| SAP-R06 | same chain through `SourceNormalizationAtomicWriteRequest` and atomic reload | fence, lease, writer, exact request/member closure; byte-identical lost-ack result or stale-generation noncommit |
| SAP-R07 | direct, factory, filesystem, and Hermes construction roots each reach the same mandatory chain | no optional dependency/fallback; one ordinary root proof plus four-root mutation proof |

## Frozen Producer Contract

The canonical delta in `docs/design/semantic_ingestion_architecture.md`,
"Graph-free interpretation producer", selects a distinct
`GraphFreeInterpretationBundle`, rather than extending
`IndependentSourceAnalysis`. The exact cardinality is decisive: analysis is
one per proposal candidate, while the pre-alignment subject set expands every
member of the five normalized proposal-operation arrays and can contain several
operations for that candidate. The bundle is source/request scoped and owns the
complete primary/corroborating scope and temporal rows keyed by each subject.

Existing raw `SourceLocalIdentityEvidence` is insufficient. It can carry a
cluster label but lacks the complete mention universe and source-proof closure
needed to prove the required total partition. The delta requires explicit
`SourceLocalIdentityPartitionEvidence` and rejects any `canonical_entity_id`,
graph lookup, provider hint, terminal outcome, or current-policy reconstruction.
The existing raw temporal evidence is sufficient only as input to the existing
typed `TemporalResolution`; the analyzer must still emit both exact attachment
sets. It cannot manufacture attachment candidates from its raw evidence.

The canonical owner chain is:

```text
prepared source + proposal run + subject set + two analyzer outputs
 -> GraphFreeSourceNormalizationStage
 -> consensus / source-local partition / exact operation joins / singleton groups
 -> SourceNormalizationAtomicWriteRequest
 -> atomic generation reload
 -> ProviderIngestionCoordinator noncommit or sealed alignment/groups
```

No arrow reads graph state, invokes a learned judge, uses confidence/order as a
tie-break, reconstructs a terminal result, or derives missing authority from a
provider proposal. The frozen typed fields, CTV domains, member order, state
machines, grouping rule, and compatibility boundary are all in the canonical
architecture delta; that document is normative over this summary.

## Requirement To Evidence Matrix

| Requirement | Design proof to implement | Focused implementation evidence |
| --- | --- | --- |
| SAP-R01 | Bundle has a complete distinct primary/corroborating row for every pre-alignment subject. | N-1/N/N+1 subjects; source/proposal/segment/route/analyzer substitutions. |
| SAP-R02 | Strict existing equality validator is the only stable-scope promotion rule. | Mutation of each scope field; same analyzer, order/score/majority fallback rejection. |
| SAP-R03 | Exact role-state machine and temporal-resolution candidate join are mandatory. | missing/extra/duplicate/cross-role/ungrounded/candidate disagreement matrix. |
| SAP-R04 | Partition evidence has complete mention universe, closed proof kinds, deterministic union, and explicit unresolved clusters. | alias/apposition/authenticated/repetition/insufficient/conflicting/overlap/omission corpus. |
| SAP-R05 | Amended role-complete row inner join plus conservative singleton group bijection. | multi-operation proposal, correction-role, unaligned subject, extra/missing/group-kind/member mutations. |
| SAP-R06 | One ordinary atomic generation owns request, bundle, evidence, retained artifacts, alignment, groups, result, manifest, policies, and ingress authority. | memory/JSONL member allowlist, crash point, lost-ack, replay, reorder/substitution/foreign-generation tests. |
| SAP-R07 | Provider ingestion calls the stage before terminal/graph work and composes all ordinary roots. | direct/factory/filesystem/Hermes caller mutation and zero-graph/non-disclosure proof. |

## Test, Gate, And Production-Binding Map

| Requirement | Required test path and node | Required gate / local command |
| --- | --- | --- |
| SAP-R01 | `memorii/tests/unit/core/semantic_ingestion/test_graph_free_interpretation_bundle.py::test_source_wide_subject_and_analyzer_coordinate_bijection` | PR-fast: `cd memorii && python -W error -m pytest tests/unit/core/semantic_ingestion/test_graph_free_interpretation_bundle.py -p no:cacheprovider` |
| SAP-R02 | `memorii/tests/unit/core/semantic_ingestion/test_source_scope_consensus.py::test_scope_value_pair_status_table_is_closed` | PR-fast: `cd memorii && python -W error -m pytest tests/unit/core/semantic_ingestion/test_source_scope_consensus.py -p no:cacheprovider` |
| SAP-R03 | `memorii/tests/unit/core/semantic_ingestion/test_source_temporal_attachment_consensus.py::test_correction_requires_replacement_and_transition_roles` | PR-fast: `cd memorii && python -W error -m pytest tests/unit/core/semantic_ingestion/test_source_temporal_attachment_consensus.py -p no:cacheprovider` |
| SAP-R04 | `memorii/tests/unit/core/semantic_ingestion/test_source_local_identity_partition.py::test_unresolved_hyperedge_propagates_without_unasserted_merge` | PR-fast: `cd memorii && python -W error -m pytest tests/unit/core/semantic_ingestion/test_source_local_identity_partition.py -p no:cacheprovider` |
| SAP-R05 | `memorii/tests/unit/core/semantic_ingestion/test_source_alignment_producer.py::test_alignment_and_singleton_group_bijections` | PR-fast: `cd memorii && python -W error -m pytest tests/unit/core/semantic_ingestion/test_source_alignment_producer.py -p no:cacheprovider` |
| SAP-R06 | `memorii/tests/integration/test_source_normalization_publication.py::test_memory_and_jsonl_lost_ack_replay_and_failpoint_closure` | Dedicated measured `source-alignment-producer` gate: `cd memorii && python -W error -m pytest tests/integration/test_source_normalization_publication.py -p no:cacheprovider` |
| SAP-R07 | `memorii/tests/integration/test_source_alignment_provider_composition.py::test_provider_ingress_reaches_source_normalization_before_graph_or_terminal` | PR-fast root smoke: `cd memorii && python -W error -m pytest tests/integration/test_source_alignment_provider_composition.py::test_provider_ingress_reaches_source_normalization_before_graph_or_terminal -p no:cacheprovider`; dedicated gate repeats all roots. |

The PR-fast smoke proves only that one ordinary root reaches the canonical
stage with the required authority. The dedicated measured gate owns the full
memory/JSONL, failpoint, concurrent writer, lost-ack/replay, reopen, exact
member-order, and topology matrix. It must run the same revision in both
backends, publish its timing record, and fail if either backend is omitted.
Topology mutations remove the stage/caller/authority argument or enable a
legacy fallback; identity mutations substitute source, preparation, route,
proposal, operation, temporal role, analyzer role, policy, manifest member,
or fence. All must fail closed. The production binding proof is the mapping
query from `ProviderMemoryService.sync_event` through
`ProviderIngestionCoordinator.ingest` and the factory/filesystem/Hermes roots,
plus an execution observation showing the reloaded generation before any graph
or terminal invocation. Zero runtime callers are pending implementation
evidence, not a design defect.

### Frozen Workflow Topology

The source-alignment owner is a measured prerequisite of, and does not overlap,
the parent graph gate. Its selector manifest is
`memorii/tests/ci/source-alignment-producer.json`; its static mutation owner is
`memorii/memorii/tools/semantic_ingestion_source_alignment_gate.py` with
`memorii/tests/unit/tools/test_semantic_ingestion_source_alignment_gate.py`.
The manifest owns all SAP nodes, removes them from `unit-shards.json` and
`semantic-terminal-persistence-shards.json`, and rejects overlap with
`graph-dependent-semantic-ingestion.json` before collection.

The exact workflow job IDs are `source-alignment-producer`,
`source-alignment-producer-timing-inventory`, and
`source-alignment-producer-receipt-aggregate`. The aggregate consumes only the
first two jobs, their exact selector manifest, three measured receipt artifacts
`source-alignment-producer-receipt-a`, `source-alignment-producer-receipt-b`,
and `source-alignment-producer-receipt-c`, and the timing artifact
`source-alignment-producer-timing-inventory`. The parent
`graph-dependent-semantic-ingestion` job depends on the source aggregate but
does not collect, time, or receipt any source-alignment node. This is an
ownership transfer to the source-alignment gate, not a fourth parent-graph
producer.

The aggregate verifies same revision, complete distinct producer receipts,
exact selector hash, memory and JSONL backend coverage, expected node count,
and timing-inventory hash before exposing its aggregate receipt. The required
local commands, from `memorii/`, are:

```text
python -m memorii.tools.semantic_ingestion_source_alignment_gate --manifest tests/ci/source-alignment-producer.json --unit-manifest tests/ci/unit-shards.json --terminal-manifest tests/ci/semantic-terminal-persistence-shards.json --graph-manifest tests/ci/graph-dependent-semantic-ingestion.json --workflow ../.github/workflows/pr-gates.yml
python -m memorii.tools.semantic_ingestion_source_alignment_gate --manifest tests/ci/source-alignment-producer.json --unit-manifest tests/ci/unit-shards.json --terminal-manifest tests/ci/semantic-terminal-persistence-shards.json --graph-manifest tests/ci/graph-dependent-semantic-ingestion.json --workflow ../.github/workflows/pr-gates.yml --self-test
python -W error -m pytest $(python -m memorii.tools.semantic_ingestion_source_alignment_gate --manifest tests/ci/source-alignment-producer.json --print-selectors) -p no:cacheprovider
```

The actual `sync_event`-through-`ingest` topology cases are parameterized in
`memorii/tests/integration/test_source_alignment_provider_composition.py` as
`test_sync_event_source_alignment_topology[analyzer]`, `[scope]`, `[temporal]`,
`[identity]`, and `[alignment]` for SAP-R01 through SAP-R05; `[publication]`
is the SAP-R06 measured publication case. Each case
asserts (1) the exact required source-analysis/interpretation input was
supplied, (2) removal or substitution returns the named typed noncommit reason
`source_alignment_authority_unavailable`, (3) graph and terminal call counters
remain zero, and (4) success reloads the exact source-normalization generation
before the next stage. Separate nodes are
`test_sync_event_rejects_source_alignment_topology_mutation` and
`test_source_alignment_all_roots_are_mandatory[direct]`, `[factory]`,
`[filesystem]`, `[hermes]`; they remove a composition edge/authority argument
and prove no optional fallback. SAP-R06 owns the memory/JSONL/failpoint/replay
nodes in the measured gate; SAP-R07 owns the four-root nodes and the PR-fast
smoke. This replaces the earlier generic topology statement.

The `[analyzer]` case executes the N-1/N/N+1 subject cardinality vectors and
missing, duplicate, same-role, cross-coordinate, and proposer-populated
observation mutations. Every vector returns
`source_alignment_authority_unavailable`, has zero graph/terminal counters, and
has no reloaded source-normalization generation. `[publication]` instead proves
the reloaded exact generation after the SAP-R06 atomic write and its
memory/JSONL lost-ack/replay closure.

The measured selector additionally owns these distinct exact nodes:

| Concern | Required node(s) |
| --- | --- |
| atomic concurrency | `test_source_normalization_same_request_concurrency[memory]`, `[jsonl]`, `test_source_normalization_different_request_concurrency[memory]`, `[jsonl]` |
| cardinality | `test_source_alignment_subject_cardinality[n_minus_one]`, `[exact]`, `[n_plus_one]`; matching `mention`, `assertion`, `artifact`, and `group` parameter families |
| strict replacement | `test_source_alignment_v2_rejects_old_v1_and_mixed_generation`; `test_source_alignment_v2_rollback_removes_unpublished_writer` |
| V2 vectors | `test_source_alignment_v2_ctv_decode_reopen_vectors` and `test_correction_temporal_two_role_closure_rejects_singular_payload` |
| type graph / handoff | `test_source_alignment_type_graph_import_and_compile_closure`; `test_reopened_v2_generation_reaches_graph_coordinator_and_nli_without_retired_shape` |
| atomic closure | `test_source_normalization_atomic_request_ctv_vector`; `test_source_normalization_atomic_request_rejects_member_closure_mutations` |
| atomic declaration | `test_source_normalization_atomic_write_has_one_active_declaration`; `test_source_alignment_gate_self_test_rejects_removed_atomic_declaration_selector` |
| root security | `test_source_alignment_all_roots_deny_without_disclosure[direct]`, `[factory]`, `[filesystem]`, `[hermes]` |
| identity hygiene | `test_source_alignment_identity_hygiene_mutations` |

V10 verification binding: the exact implementation node is
`memorii/tests/unit/tools/test_semantic_ingestion_source_alignment_gate.py::test_source_normalization_atomic_write_has_one_active_declaration`.
Its exact selector-manifest entry in
`memorii/tests/ci/source-alignment-producer.json` is
`tests/unit/tools/test_semantic_ingestion_source_alignment_gate.py::test_source_normalization_atomic_write_has_one_active_declaration`.
The measured job is `source-alignment-producer`; from `memorii/` it executes:

```text
python -W error -m pytest tests/unit/tools/test_semantic_ingestion_source_alignment_gate.py::test_source_normalization_atomic_write_has_one_active_declaration -p no:cacheprovider
```

The required gate self-test is
`test_source_alignment_gate_self_test_rejects_removed_atomic_declaration_selector`.
It removes that exact selector from a temporary manifest and runs
`python -m memorii.tools.semantic_ingestion_source_alignment_gate --manifest <mutated-manifest> --unit-manifest tests/ci/unit-shards.json --terminal-manifest tests/ci/semantic-terminal-persistence-shards.json --graph-manifest tests/ci/graph-dependent-semantic-ingestion.json --workflow ../.github/workflows/pr-gates.yml --self-test`; the command must fail with the missing atomic-declaration-selector diagnostic. The ordinary assertion proves one active declaration and codec and rejects old direct fields before publication/recovery.

Same-request concurrency must return one byte-identical reloaded generation to
all winners; different-request concurrency permits only one current-generation
winner and the loser receives stale-generation noncommit. Each cardinality
family exercises N-1/N/N+1 independently; no family is inferred from the
subject case. The strict replacement nodes decode/reopen every V2 type from a
fixed CTV vector, mutate every field, and reject old V1, singular-temporal, and
mixed-format payloads. The correction vector proves both temporal roles through
manifest, selection, set, alignment, write, and reopen.

The type-graph node is
`memorii/tests/unit/core/semantic_ingestion/test_source_alignment_type_graph.py::test_source_alignment_type_graph_import_and_compile_closure`.
The persisted handoff/reopen node is
`memorii/tests/integration/test_source_alignment_graph_handoff.py::test_reopened_v2_generation_reaches_graph_coordinator_and_nli_without_retired_shape`.
Both belong to the measured selector; the latter is the exclusive proof that a
reloaded atomic generation reaches graph coordination and NLI with only stable
schema-version-2 names and rejects every retired nested member.

The four-root security node parameterizes missing and invalid ingress, fence,
and policy authority plus a cross-tenant substitution. It asserts the typed
non-disclosing result, zero graph/terminal calls, no generation lookup before
authorization, and spies/log capture containing no source text, mention text,
tenant, or foreign identifier. The identity-hygiene node mutates planning
coordinates in every new Python symbol, test/fixture/manifest/workflow/receipt/
timing surface and proves rejection while a positive corpus accepts `BM25`,
valid V2 protocol literals, and the retained migration-free names. It invokes
the canonical command from `memorii/` in both the PR-fast static gate and the
measured aggregate:

```text
python -m memorii.tools.identity_hygiene --root .. --allowlist ../.agents/identity_hygiene_allowlist.json
```

## Attack, Compatibility, And Operational Matrix

| Family | Invariant / fail-closed outcome |
| --- | --- |
| analyzer authority | Missing, duplicated, same-role, cross-coordinate, or proposer-populated rows produce a non-committing outcome; no alignment row. |
| consensus | Only complete exact two-analyzer equality is stable; all other statuses remain retained terminal-unaligned evidence. |
| identity | Every grounded mention appears once in one cluster; canonical graph identity and unsupported proof forms reject. |
| atomicity/replay | One attested generation is reloaded byte-for-byte; changed request digest loses generation CAS and never recomputes. |
| composition | Absent stage/dependency returns typed noncommit before graph read, persistence, or sensitive identifier lookup. |
| rollback/limits | Strict unreleased v1 rollback removes writers/codecs as a unit; subject, mention, assertion, artifact, and group counts must be bounded by the request policy and breach returns typed noncommit. |
| observability | Log only operation fence, generation, digest, stage/status, and bounded reason codes; never raw source text, mention text, or cross-tenant identifiers. |

## Evidence And Attack Matrix

- Stable fact, correction, retraction, identity, and action cases.
- Primary/corroborating disagreement in every scope field and attachment member.
- Missing, duplicate, same-analyzer, cross-source, cross-segment, cross-route,
  cross-proposal, policy, selection, digest, and order substitutions.
- Source-local identity singleton, alias, apposition, authenticated ID,
  repetition, insufficient, conflicting, overlap, omission, and duplicate cases.
- Complete singleton operation/group bijection for fact, correction, retraction,
  identity, action, and unresolved inputs; cross-operation grouping rejects.
- Memory and JSONL publication failure before/during/after every member;
  lost-ack retry and reopen use byte-identical persisted authority only.
- Direct/factory/filesystem/Hermes roots; missing producer returns typed
  noncommit before graph read and never leaks another tenant identifier.

## Serious Alternatives

1. Extend `IndependentSourceAnalysis` to retain both analyzer scope and temporal
   interpretations plus source-local evidence, then derive consensus in one
   source-normalization producer. Preferred if per-analysis cardinality is exact.
2. Add a distinct graph-free interpretation bundle beside analysis. Preferred
   if extending analysis would conflate candidate and source cardinalities.
3. Reconstruct from terminal outcome. Rejected because terminal projection is
   later and narrower than the retained authority.
4. Derive from provider proposal or graph state. Rejected by source-authority
   and graph-free invariants.

## Evidence Maturity

Contract validators are implemented and producer inputs/algorithm are
specified by the canonical delta. Production reachability is designed but not
implemented or locally verified; no implementation evidence is claimed.

## Changed-Surface And Authority-Chain Ledger

| Surface | Class | Authority chain | Status |
| --- | --- | --- | --- |
| this WorkPlan | design | gap -> requirements -> candidate/review | active |
| `docs/design/semantic_ingestion_architecture.md` | normative design | analyzer inputs -> consensus -> alignment -> generation -> provider | candidate written |
| parent implementation WorkPlan | cross-operation boundary | frozen producer delta -> graph-dependent implementation resume condition | updated link pending review |

## Delegation And Cost Ledger

| Task | Role/tier | Ownership | Status |
| --- | --- | --- | --- |
| analyzer/pipeline and contract map | code mapper / Spark | read-only | completed by writer evidence review |
| canonical design delta and WorkPlan | worker / Terra | sole writer | completed candidate |
| frozen final review | spec/correctness/test reviewers / Terra | read-only | next action |

## Progress Log

- 2026-08-10: Implementation readiness exposed the missing producer boundary.
  Paused implementation rather than inventing source authority.
- 2026-08-10: Created this linked design operation with seven requirements,
  authority boundary, alternatives, and attack families.
- 2026-08-10: Mapped contracts and the production analyzer/pipeline. The
  analyzer emits parser consensus plus raw identity/temporal evidence; it emits
  none of the operation-scoped scope/attachment rows or total partition needed
  by alignment. The no-constructor baseline is confirmed.
- 2026-08-10: Wrote the canonical graph-free producer delta. It selects the
  distinct interpretation bundle, makes the missing identity-proof input
  explicit, freezes conservative grouping and atomic publication, and leaves
  all graph/terminal work excluded.
- 2026-08-10: Static consistency check passed: `git diff --check` over the
  three owned artifacts returned zero diagnostics; production-constructor and
  analyzer-output searches confirmed the stated zero/missing baseline. This is
  a feasibility check of current ownership and not implementation evidence.
- 2026-08-10: Reconciled the frozen review remediation. The candidate now has
  value-bearing scope rows, source-wide coordinate wrappers, role-keyed
  temporal closure, pre-partition mention evidence, and a conservative
  component-wide ambiguity rule. The test/gate/binding map distinguishes the
  PR-fast root smoke from the measured persistence/replay gate.
- 2026-08-10: Reconciled v2 residuals with explicit replacement schemas,
  total scope status table, role-complete temporal receipt, pre-partition
  identity contracts, and an exclusive measured-gate topology prerequisite.

## Evidence Log

- `memorii/memorii/core/semantic_ingestion/contracts.py` defines the existing
  analysis and required consensus/alignment contracts.
- `docs/design/semantic_ingestion_architecture.md` now supplies the strict
  source-only producer API, derivation, generation, and caller contract.
- `memorii/memorii/core/semantic_ingestion/local_analyzer.py` shows the current
  analyzer returns only parser consensus and empty raw identity evidence.
- `memorii/memorii/core/semantic_ingestion/pipeline.py` and
  `memorii/memorii/core/provider/ingestion.py` show no source-normalization
  stage or production alignment constructor.
- Focused feasibility searches: `rg -n 'SourceProposalAlignment(\\.create)?\\('
  memorii/memorii/core/provider memorii/memorii/core/filesystem_storage
  memorii/memorii/integrations` has zero production matches; `rg -n
  'IndependentSourceAnalysis|AnalyzerScopeInterpretation|AnalyzerTemporalAttachment'
  memorii/memorii/core/semantic_ingestion/{local_analyzer.py,pipeline.py}`
  confirms the listed missing producer rows.

## Decision Log

- 2026-08-10: Treat missing producer inputs as a design gap, not permission for
  an implementation fallback.
- 2026-08-10: Select a distinct operation-scoped interpretation bundle rather
  than extending candidate-scoped `IndependentSourceAnalysis`; cardinality and
  ownership are non-isomorphic.
- 2026-08-10: Freeze singleton source groups. No existing typed source-only
  authority can justify a cross-operation dependency edge.

## Review Log

No design review yet. The candidate is ready for the required frozen reviewer
cohort; implementation remains blocked until that review is reconciled.

Reconciliation for the current candidate: DREV-001 through DREV-004 are
confirmed `Not applicable` / `changes_required` contract-conformance findings
and are remediated by the canonical delta above (scope values, source-wide
coordinates, temporal roles, and pre-partition identity evidence). DREV-005,
the production-entrypoint absence, is `Not applicable` / `follow_up` /
implementation evidence: it is deferred until the required production caller
exists and is not a design defect. The identity ambiguity observation is
confirmed `Not applicable` / `changes_required`; the conservative connected
component rule resolves it without external input. A fresh frozen delta review
is still required.

V2 residual reconciliation: DREV-006 through DREV-009 are confirmed `Not
applicable` / `changes_required` contract-conformance findings. The strict
replacement schemas close scope values/statuses, role-bearing temporal joins,
pre-partition identity authority, and workflow topology. No new product P1/P2
finding is asserted. DREV-005 remains deferred implementation proof.

Final conformance reconciliation: DREV-010 and DREV-011 are confirmed `Not
applicable` / `changes_required` contract-conformance findings and are resolved
by assertion-level mixed-route rejection and the corrected real-trigger matrix.
The candidate remains `under-review` and ready for the frozen delta cohort; no
runtime or test evidence is claimed.

Whole-review reconciliation: DREV-012 through DREV-016 are confirmed `Not
applicable` / `changes_required` contract-conformance findings. The
authoritative V2 family supersedes all prior producer shapes; deterministic
cluster-ID derivation, exhaustive V2 vector/reopen proof, measured concurrency
and cardinality nodes, four-root no-disclosure, and field-aware identity hygiene
are now frozen. The candidate remains `under-review` and ready for the final
frozen cohort; implementation evidence remains deferred.

DREV-017 is confirmed `Not applicable` / `changes_required` /
contract-conformance. The stable-name schema-version-2 closure replaces the
temporary V2 labels, adds value-bearing `SemanticScopeConsensus` and complete
`ConsensusPolicySelectionBundle`, and binds every persistence/graph/NLI/import
edge to one rejected-retired-shape rule. The named type-graph and persisted
handoff vectors are required implementation evidence. The candidate remains
`under-review` and ready for frozen review; no runtime reachability is claimed.

DREV-018 is confirmed `Not applicable` / `changes_required` /
contract-conformance. The exhaustive stable-name schema-version-2 declaration
now enumerates every nested field, CTV preimage/domain, discriminator, member
order, and outer graph/NLI/trace/store consumer. The type-graph and persisted
handoff vectors must instantiate/decode every declared type and reject every
retired form. The candidate remains `under-review` and ready for frozen review;
no runtime or test execution claim is made.

DREV-019 is confirmed `Not applicable` / `changes_required` /
contract-conformance. The nested parser/group/coverage/capability closure and
the concrete flattened atomic storage subtype now carry stable schema-version-2
contracts, exactly fifteen ordered member categories with variable consensus
runs, and one nonduplicated request digest
preimage. Fixed atomic vectors cover every omission, old/extra/duplicate member,
and request-digest mutation. The candidate remains `under-review` and ready for
frozen review; no implementation evidence is claimed.

DREV-020 and DREV-021 are confirmed `Not applicable` / `changes_required` /
contract-conformance. The atomic closure now distinguishes its fifteen ordered
categories from variable parser/scope/temporal runs, including one-operation,
N-operation, and correction-role vectors. The 4.8 protocol references the sole
3.4.2f stable subtype; a static/type-graph assertion proves one active
declaration and strict decode rejects the retired direct-field shape before
publication/recovery. The candidate remains `under-review` and ready for frozen
review; no implementation evidence is claimed.

DREV-022 is confirmed `Not applicable` / `changes_required` / verification.
The atomic-declaration assertion now has its exact path, selector manifest
entry, measured job, local command, and selector-removal gate self-test. The
candidate remains `under-review` and ready for frozen review; no runtime or test
execution claim is made.

## Blockers And Limits

No external semantic decision blocker remains. Implementation evidence is
pending; the current production analyzer lacks the approved output contract.

## Next Action

Resume the linked implementation WorkPlan using frozen candidate v11.

## Outcome And Retrospective

Approved at `design-candidate-identity-v11.json`. Final specification,
correctness, and test-readiness reviews recorded empty remaining finding,
decision, `blocks_approval`, and `changes_required` sets. Runtime implementation
and evidence remain pending.
