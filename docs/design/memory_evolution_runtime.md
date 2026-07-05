# Runtime Memory Evolution Design

## Status

This document describes the runtime memory evolution implementation as it exists now. It is not a future-only architecture note.

Runtime memory evolution is implemented as an opt-in layer inside `ProviderMemoryService` and `MemoryEvolutionService`. It is not enabled by default for provider integrations yet.

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

Runtime evolution is reached through `ProviderMemoryService` when constructed with `memory_evolution_enabled=True`.

Current provider entry points:

- `sync_event(...)`
- `apply_memory_write(...)`
- `prefetch(...)`
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

- Runtime memory evolution is disabled by default.
- When enabled, provider transcript/source IDs are passed to `MemoryEvolutionService.evolve_source_ids(...)`.
- The latest evolution result is available through `ProviderMemoryService.last_memory_evolution_result()`.
- Provider prefetch currently returns memory context plus work-state summaries. It does not yet default to graph-grounded current truth retrieval.

## Runtime Evolution Flow

`MemoryEvolutionService.evolve_records(...)` currently performs this sequence:

1. Convert raw `CanonicalMemoryRecord` transcript records into `SourceObservation`.
2. Classify modality and trigger mode.
3. Extract entities, claims, and actions from immediate observations.
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

- `RuleMemoryExtractor`
- `LLMMemoryExtractor`
- `HybridMemoryExtractor`

`build_memory_extractor_from_env(...)` selects rule, LLM, or hybrid behavior from environment/runtime configuration.

Current limits:

- The rule extractor is intentionally simple and pattern based.
- The LLM extractor can produce entities, claims, and actions from `memory_extraction:v1`, but the runtime-backed benchmark is not yet the main acceptance gate.
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

For single-value predicates, a stronger or newer accepted claim can supersede older active claims. Older claims are retained with invalidated/superseded state rather than deleted.

Current conflict behavior:

- same-value claims reinforce an existing active claim
- different values for single-value predicates can supersede or invalidate based on source strength and confidence
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

## Runtime Graph Retrieval APIs

`MemoryEvolutionService` currently exposes:

- `retrieve_graph_snapshot()`
- `retrieve_current_truth_graph(subject_entity_id=None, predicate_id=None)`
- `retrieve_entity_subgraph(entity_id, include_historical=False, include_conflicts=False)`
- `retrieve_claim_lineage(claim_id)`
- `retrieve_conflict_graph()`

These are graph-level APIs. Provider prefetch does not yet automatically use these APIs as its default answer-selection mechanism.

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

The current implementation does not yet prove that real provider ingestion can reconstruct the same kind of latent graph that `memory_evolution_sim_v1` tests through its reconstruction adapter.

The missing acceptance suite is `memory_evolution_runtime_v1`:

```text
latent simulator surface observations
  -> ProviderMemoryService / HermesMemoryProvider
  -> MemoryEvolutionService
  -> runtime graph projection
  -> graph-to-oracle alignment
  -> programmatic judges and calibration reports
```

Until that suite is implemented and green, runtime evolution should remain opt-in for agent integrations.

## Readiness Position

Runtime evolution is ready for controlled integration pilots behind a feature flag.

It is not yet ready to be the default always-on durable agent memory path.
