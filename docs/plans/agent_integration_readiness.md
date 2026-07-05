# Agent Integration Readiness Plan

## Current Answer

Memorii is ready for a controlled agent-system pilot behind a feature flag.

Memorii is not yet ready to be the default always-on durable memory system for agents.

## Why A Pilot Is Reasonable

The codebase now has the main integration primitives:

- provider-facing hooks through `HermesMemoryProvider`
- `ProviderMemoryService` for sync, write, prefetch, and tool calls
- work-state detection and storage
- decision-state tools
- recall-state bundles
- next-step engine
- opt-in runtime memory evolution
- runtime graph projection and graph retrieval APIs
- benchmark suites for lifecycle, retrieval corruption, execution graph, hand-authored memory evolution, latent graph simulation, HotpotQA, and calibration reporting

The latest latent graph simulator work gives confidence that the benchmark contract is meaningful: live runs use live LLM output, hidden facts are present, role-aware channels are enforced, and programmatic judges are deterministic.

## Why Default Always-On Memory Is Premature

The strongest benchmark currently validates:

```text
surface observations -> benchmark reconstruction adapter -> judges
```

Agent integration needs to validate:

```text
agent events -> provider hooks -> MemoryEvolutionService
  -> runtime graph projection -> recall / next-step output
  -> agent behavior
```

That full runtime-backed loop is not yet the primary acceptance suite.

Runtime memory evolution is also disabled by default in `ProviderMemoryService`, which is the right default until runtime-backed validation is green.

## Integration Pilot Configuration

For a controlled pilot, use:

- `ProviderMemoryService(memory_evolution_enabled=True)`
- persistent memory plane storage
- work-state service enabled
- decision-state service enabled
- LLM/hybrid extractor only when live credentials and tracing are configured
- full trace capture for provider events, extraction runs, graph snapshots, and recall bundles

Pilot rules:

- keep raw transcript append-only
- keep semantic/user writes conservative
- expose graph/debug views for inspection
- do not let unsupported extracted claims silently become durable user truth
- keep calibration report-only
- allow rollback by disabling runtime evolution

## Pilot Agent Capabilities

Expose these capabilities to the agent harness:

- `prefetch(query, session_id, task_id, user_id)`
- `sync_turn(user_content, assistant_content, ...)`
- `on_memory_write(action, target, content, ...)`
- `on_delegation(task, result, ...)`
- `on_session_end(...)`
- `on_pre_compress(...)`

Expose provider tools:

- `memorii_get_state_summary`
- `memorii_get_next_step`
- `memorii_open_or_resume_work`
- `memorii_record_progress`
- `memorii_record_outcome`
- decision-state tools for options, criteria, evidence, recommendations, and finalization

## Required Gate Before Broad Integration

Implement `memory_evolution_runtime_v1` before making Memorii the default memory substrate.

The suite should:

1. Generate latent graph scenarios using the existing simulator.
2. Feed only surface observations through `HermesMemoryProvider` or `ProviderMemoryService`.
3. Enable runtime memory evolution.
4. Project runtime graph state.
5. Align runtime graph items to latent graph oracle items.
6. Score entity, claim, relation, provenance, lifecycle, conflict, scope, source trust, and hidden hallucination behavior.
7. Emit calibration and decision quality reports.

Acceptance target for pilot-to-default promotion:

- no hidden hallucinations
- no high-confidence wrong current truth
- no active claims from ineligible modality
- current vs historical truth works through runtime graph retrieval
- source-trust conflict resolves correctly
- task/global scope isolation works
- graph projection is replay/idempotency safe
- provider prefetch includes relevant memory plus structured state
- next-step tool returns evidence-backed continuation guidance

## Near-Term Work Order

1. Document current design and readiness state.
2. Implement `memory_evolution_runtime_v1`.
3. Run dry-run/runtime fixtures and live LLM extraction fixtures separately.
4. Add a small real agent harness pilot.
5. Inspect traces and calibration before changing defaults.
6. Only then consider enabling runtime evolution by default.

## Non-Goals For The First Pilot

Do not attempt to solve these in the first integration pass:

- full production scaling
- automatic confidence caps in runtime
- automatic abstention policy changes
- learned calibration
- broad reference-augmented retrieval
- permanent irreversible semantic writes from ordinary chat

## Readiness Summary

Ready now:

- controlled pilot
- opt-in runtime evolution
- benchmark-backed trace inspection
- provider tools for explicit state management

Not ready yet:

- default always-on memory evolution
- unguarded durable fact writes from ordinary chat
- broad production deployment
- claiming the runtime graph passes latent graph reconstruction until `memory_evolution_runtime_v1` exists
