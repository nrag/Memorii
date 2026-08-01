# Runtime Memory Evolution Design

## Status

This document describes the runtime memory evolution implementation as it exists now. It is not a future-only architecture note.

Runtime memory evolution is part of the standard `ProviderMemoryService` composition. Provider ingestion durably records an evolution operation and projects eligible source observations without requiring an enablement flag.

`build_provider_memory_service_from_env(...)` is the production composition root. It
selects extraction and promotion providers from one environment snapshot, constructs
the dependency-injected service, and reconciles recoverable evolution operations.
Direct `ProviderMemoryService(...)` construction remains deterministic for explicit
embedding and tests; it does not read process configuration.

The production composition runs one recovery cycle at startup. Hosts with long-lived
shared stores should also schedule `reconcile_memory_evolution()` periodically; active
leased operations are skipped, while expired leases and retryable failures are reclaimed.
Durable operation records contain bounded failure categories and sanitized messages.
Full exception details remain operational logs and are not written into canonical memory.

## Purpose

Memorii's product goal is to act as a memory plane for agents. The runtime evolution layer is the part of that memory plane that turns raw observations into a typed, auditable graph of entities, claims, actions, evidence, lifecycle state, contradiction state, and retrieval views.

The hierarchy is:

```text
raw provider event / transcript record
  -> SourceObservation
  -> EvidenceSpan
  -> EntityMention / ExtractedClaim / ExtractedAction
  -> ValidationResult
  -> EntityLinkState / ClaimState / ContradictionSet
  -> MemoryGraphNode / MemoryGraphEdge
  -> graph retrieval views
  -> recall / next-step / agent-facing state
```

Raw observations remain the source of truth. Derived graph state is a projection over validated extracted state, not a replacement for the raw event log.

## Current Entry Points

Runtime evolution is part of the standard `ProviderMemoryService` composition.

Current provider entry points:

- `sync_event(..., operation_id=...)`
- `apply_memory_write(..., operation_id=...)`
- `prefetch(...)`
- `retrieve_evolution_decision(...)`
- `handle_tool_call(...)`
- `last_memory_evolution_result()`

`HermesMemoryProvider` delegates to `ProviderMemoryService` through:

- `prefetch`
- `sync_turn`
- `on_session_end`
- `on_pre_compress`
- `on_memory_write`
- `on_delegation`

Important current behavior:

- Mutating provider entry points require a stable caller-supplied operation ID. Replayed
  deliveries reuse their durable operation result instead of duplicating source events or
  projections.
- Provider transcript/source IDs are passed through the recoverable evolution coordinator to
  `MemoryEvolutionService.evolve_source_ids(...)` by default. Operations and projections are
  committed transactionally to the configured memory-plane store. They survive a process restart
  only when that store is persistent; the default standalone composition remains in-memory.
- The latest evolution result is available through `ProviderMemoryService.last_memory_evolution_result()`.
- Provider prefetch currently returns memory context plus work-state summaries. It does not yet default to graph-grounded current truth retrieval.

## Runtime Evolution Flow

`MemoryEvolutionService.evolve_records(...)` currently performs this sequence:

1. Convert raw `CanonicalMemoryRecord` transcript records into `SourceObservation`.
2. Classify modality and trigger mode.
3. Extract entities, claims, and actions from observations eligible for an
   extraction attempt. Deferred observations are still validated and retained
   as audit evidence, but their claims cannot become active truth.
4. Validate extracted claims.
5. Resolve entity mentions into entity links.
6. Apply accepted claims into claim lifecycle state.
7. Resolve single-value conflicts and contradiction sets.
8. Write derived entity links, claim states, action records, and contradiction sets into the memory plane.
9. Project the full runtime evolution state into graph nodes and edges.
10. Validate the graph snapshot.
11. Write graph node and edge records back to the memory plane.

The runtime flow is conservative by design. Observations classified as deferred, batch-only, or skipped are not immediately converted into active claims.

## Source Modality And Trigger Policy

The runtime has modality and trigger-policy primitives. The intended policy is:

- explicit memory writes, corrections, tool results, verified observations, and execution-state changes may trigger immediate extraction
- ordinary chat, pasted text, hypothetical text, questions, and noisy text should be deferred, batch-only, skipped, or evidence-only
- validators must reject active claims from ineligible modality/trigger combinations

Current implementation detail:

- `SourceModalityClassifier` and `ExtractionTriggerPolicy` decide modality and trigger mode.
- `MemoryEvolutionValidator` rejects claims whose evidence comes from question, hypothetical, instruction, noise, quoted/pasted, deferred, batch-only, or skipped observations.

## Extraction Providers

Runtime extraction is provider-backed through `MemoryExtractor`.

Implemented extractors:

- `EnglishRuleMemoryExtractor`
- `LLMMemoryExtractor`
- `HybridMemoryExtractor`

`build_memory_extractor_from_env(...)` selects rule, LLM, or hybrid behavior from environment/runtime configuration.

Current limits:

- The English rule extractor is intentionally simple, pattern based, and
  fail-closed for unsupported languages.
- The LLM extractor can produce entities, claims, and actions from
  `memory_extraction:v1`; the runtime-backed benchmark is the memory-component
  acceptance gate, not an agent-system acceptance gate.
- Hybrid falls back to rule extraction when the LLM extraction run reports errors.

## Validation

Current claim validators include:

- predicate registry validation
- modality eligibility
- object presence
- subject support
- predicate support
- temporal support
- evidence span quote support

Quote existence is necessary but not sufficient. Predicate support and modality eligibility are separate validators.

Current known limitation:

- Some semantic distinctions still depend on extraction quality and relatively simple predicate support checks. The benchmark simulator catches many of these as model reconstruction failures, but runtime-backed validation is still needed.

## Claim Lifecycle

`ClaimState` is the active runtime state for extracted claims.

The lifecycle supports:

- active
- candidate
- superseded
- invalidated
- expired
- archived

For single-value predicates, validation and modality eligibility run before arbitration.
Accepted claims use an explicit precedence tuple: effective time first, predicate-specific
source authority second, and stable claim ID only as the final deterministic tie-break.
Model confidence is diagnostic and never selects categorical durable truth. Older claims
are retained with invalidated/superseded state rather than deleted.

Current conflict behavior:

- same-value claims reinforce an existing active claim
- different values for single-value predicates supersede or invalidate according to the explicit precedence tuple
- contradiction sets are written for incompatible single-value claims

## Runtime Graph Projection

The runtime graph is a deterministic projection over source observations, entity links, claim states, actions, contradiction sets, and transitions.

Implemented graph model types include:

- source observation nodes
- entity nodes
- claim nodes
- action nodes
- literal nodes
- scope nodes
- task nodes
- contradiction set nodes
- reference entity/claim nodes

Implemented graph edge types include:

- observed_in
- mentions
- has_subject
- has_object
- has_literal_object
- has_scope
- supports
- contradicts
- supersedes
- reinforces
- conflicts_with
- alias_of
- same_as
- merged_into
- split_from
- rekeyed_from
- depends_on
- blocks
- member_of_contradiction_set
- typed_as
- reference_supports

Graph records are written as `CanonicalMemoryRecord` objects with `memory_evolution_kind` set to `graph_node` or `graph_edge`.

Graph records are retained rather than physically deleted. Stale state is represented through lifecycle state and validity status.

Entity splits require grounded identity evidence rather than same-name text
alone. A split is eligible only when an extracted mention and an existing link
share an explicit normalized alias, have distinct known entity types, and the
new mention carries evidence. The child link persists its lineage parent, and
graph projection emits exactly one `split_from` edge from that persisted state.
The benchmark may align the native child and parent IDs to oracle labels after
projection, but it does not create or duplicate lineage edges.

## Runtime Graph Retrieval APIs

`MemoryEvolutionService` currently exposes:

- `retrieve_graph_snapshot()`
- `retrieve_current_truth_graph(subject_entity_id=None, predicate_id=None)`
- `retrieve_entity_subgraph(entity_id, include_historical=False, include_conflicts=False)`
- `retrieve_claim_lineage(claim_id)`
- `retrieve_conflict_graph()`

These are graph-level APIs. Current-truth and entity-subgraph retrieval accept
an evaluation time or temporal frame and apply validity intervals consistently
with claim retrieval. A point-in-time current view may return a claim that is
now superseded if it was valid at the requested time; it does not promote that
claim to present-day truth.

## Reference Knowledge

Reference knowledge exists as a separate read-only seed provider.

Current built-in references include examples such as Paris, France, Azure, Python, and UTC.

Rules:

- Reference knowledge may help entity typing.
- Reference knowledge must not create user/project claim states by itself.
- Reference facts should not appear as user truth unless a future caller explicitly requests a reference-augmented view.

## Relationship To Work State And Next Step

Runtime memory evolution is one layer of the larger agent-memory system.

Currently implemented neighboring layers include:

- work-state detection and storage
- decision-state storage and tools
- recall-state bundles
- next-step engine
- solver frontier planner integration when solver stores are configured

Current limit:

- The next-step engine can use solver frontier state when configured, but often falls back to work-state summaries.
- Graph-derived current truth is not yet fully integrated into next-step selection.

## Query-Temporal Retrieval Boundary

Production retrieval keeps two decisions separate:

1. `QueryTemporalFrame` describes what time, scope, entity, and purpose the
   query asks about.
2. `ClaimLifecycleState` and validity intervals determine which claim states
   are eligible for that frame.

`MemoryQueryRequest` can carry a structured `QueryAnalysis` from an upstream
query analyzer. Its entity and predicate constraints are applied by the
production retriever, not by benchmark alignment code. English fallback
parsing is intentionally conservative; non-English or ambiguous queries must
provide a structured frame or the retriever abstains.

The production query boundary also owns a configurable `LexicalQueryAnalyzer`,
an explicit `EnglishLexicalQueryAnalyzer` fallback, and an evidence-backed
`TemporalAnchorCatalog`. Named periods such as "release week" resolve only when
a caller has registered an anchor with an interval and source evidence. The
runtime never assigns dates from the phrase alone. Colliding anchors produce an
explicit abstention rather than an identifier tie-break.

Provider adapters may pass `query_language` and structured `QueryAnalysis`
through `prefetch`; the runtime benchmark passes each checkpoint language to
the same production request path. Simulator oracle labels never populate the
production frame.

The retriever returns a `ProductionRetrievalDecision` containing native record
ids, selected/supporting/context/rejected channels, temporal resolution, and
an explicit abstention status. Benchmarks may map those native ids to oracle
labels after the decision, but cannot use oracle labels to change selection.

## Execution-State Boundary

Action events are immutable history. `MemoryEvolutionService.derive_work_state`
reduces them into a `WorkStateSnapshot`, and execution retrieval resolves a
`ContinuationDecision` using scope, target entities, lifecycle status, and
progress. Ambiguous peer branches abstain instead of being chosen by a stable
identifier. Runtime benchmark execution checkpoints consume this production
decision and require selected/supporting action evidence; the benchmark does
not reconstruct the active branch independently.

## Artifact And Report Boundary

Runtime graph snapshots and normalized graph items are validated through
typed benchmark row models before they are written. The report separates
final-snapshot completeness from cumulative observation diagnostics, and
separates checkpoint-scored verdicts from broader graph-alignment audits.
Partial or ambiguous audit rows are therefore visible without being silently
counted as checkpoint failures. Dry-run extraction is labeled `fake_oracle`
and its provider-health status is `not_applicable`; it never contributes to
live provider success counts.

## What This Implementation Proves

The current runtime implementation proves that Memorii can:

- keep raw observations immutable
- conservatively classify observations before extraction
- extract typed entities/claims/actions
- validate claims before lifecycle writes
- preserve superseded/conflicting history
- project runtime state into graph nodes and edges
- retrieve current, historical, entity, lineage, and conflict subgraphs

## What It Does Not Yet Prove

The runtime-backed acceptance suite is `memory_evolution_runtime_v1`:

```text
latent simulator surface observations
  -> ProviderMemoryService / HermesMemoryProvider
  -> MemoryEvolutionService
  -> runtime graph projection
  -> graph-to-oracle alignment
  -> programmatic judges and calibration reports
```

The suite validates runtime graph construction and decision projection on
surface-only observations. Its deterministic dry-run gates are green for the
adversarial and long-horizon profiles. Live provider runs remain a separate
system-under-test gate and do not change production defaults.

Checkpoint provenance is scoped to the extraction attempts that produced that
checkpoint. Scenario-level provider counters remain aggregate diagnostics, and
mixed live/rule output is reported as `mixed` rather than attributed to one
provider.

## Readiness Position

Runtime evolution is not yet ready for agent integration. Pull-request gates
validate deterministic contracts, schema integrity, no-leakage, and
fake-oracle plumbing; scheduled live gates validate the component across seeds,
replicates, and scenario families using provider-observable metadata and
hierarchical confidence bounds. Neither gate measures agent policy interaction
or end-to-end task outcomes. An agent-system evaluation must be designed and
approved separately before any integration or default enablement work begins.
