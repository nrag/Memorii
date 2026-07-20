# Agent Integration Readiness Plan

## Current Answer

Memorii is not yet ready for agent-system integration, including a controlled
pilot. Current work validates memory components and benchmark integrity only.

## Validated Component Surface

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

The latent graph simulator and runtime suite provide evidence about memory
reconstruction, extraction, lifecycle, graph projection, retrieval, and
reporting. They do not provide evidence about an agent's policy, tool-use
strategy, recovery behavior, or end-to-end task outcomes.

## Why Integration Is Deferred

The strongest benchmark currently validates:

```text
surface observations -> benchmark reconstruction adapter -> judges
```

Any future agent integration needs a separately approved evaluation of:

```text
agent events -> provider hooks -> MemoryEvolutionService
  -> runtime graph projection -> recall / next-step output
  -> agent behavior
```

The runtime-backed benchmark now validates the memory portion of this path on
generated observations. It does not include an agent as the system under test.

Runtime memory evolution is also disabled by default in `ProviderMemoryService`, which is the right default until runtime-backed validation is green.

## Future Integration Design Inputs

The following are design inputs for a future evaluation, not approved pilot
instructions:

- `ProviderMemoryService(memory_evolution_enabled=True)`
- persistent memory plane storage
- work-state service enabled
- decision-state service enabled
- LLM/hybrid extractor only when live credentials and tracing are configured
- full trace capture for provider events, extraction runs, graph snapshots, and recall bundles

Future evaluation safety requirements:

- keep raw transcript append-only
- keep semantic/user writes conservative
- expose graph/debug views for inspection
- do not let unsupported extracted claims silently become durable user truth
- keep calibration report-only
- allow rollback by disabling runtime evolution

## Candidate Agent Capabilities

A future harness may expose these capabilities after its protocol is reviewed:

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

## Required Memory-Component Gate

`memory_evolution_runtime_v1` is the memory-component acceptance suite. It
must remain green across declared live seeds, replicates, and scenario
families, but passing it is necessary rather than sufficient for agent
integration.

The suite should:

1. Generate latent graph scenarios using the existing simulator.
2. Feed only surface observations through `HermesMemoryProvider` or `ProviderMemoryService`.
3. Enable runtime memory evolution.
4. Project runtime graph state.
5. Align runtime graph items to latent graph oracle items.
6. Score entity, claim, relation, provenance, lifecycle, conflict, scope, source trust, and hidden hallucination behavior.
7. Emit calibration and decision quality reports.

Memory-component acceptance targets:

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
2. Keep benchmark-only oracle data isolated from production retrieval.
3. Run fake-oracle plumbing and live LLM gates as distinct evidence classes.
4. Stabilize multi-seed, multi-replicate, family-level statistical gates.
5. Inspect traces, calibration, provider health, and generator coverage.
6. Design an agent-system evaluation separately; do not integrate in this phase.

## Current Non-Goals

Do not attempt these during benchmark hardening:

- full production scaling
- automatic confidence caps in runtime
- automatic abstention policy changes
- learned calibration
- broad reference-augmented retrieval
- permanent irreversible semantic writes from ordinary chat

## Readiness Summary

Ready now:

- isolated opt-in runtime component validation
- benchmark-backed trace inspection
- provider tools for explicit state management

Not ready yet:

- controlled agent integration
- default always-on memory evolution
- unguarded durable fact writes from ordinary chat
- broad production deployment
- claims about agent-level quality or task improvement
