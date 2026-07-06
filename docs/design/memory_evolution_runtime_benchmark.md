# Memory Evolution Runtime Benchmark

`memory_evolution_runtime_v1` validates Memorii's real opt-in memory evolution path against the latent-graph simulator.

```text
latent simulator surface observations
  -> ProviderMemoryService(memory_evolution_enabled=True)
  -> MemoryEvolutionService extraction, validation, lifecycle, graph projection
  -> runtime graph snapshot
  -> graph-to-oracle alignment
  -> role-aware programmatic judges and calibration reports
```

This suite is intentionally separate from `memory_evolution_sim_v1`:

- `memory_evolution_sim_v1` validates whether a reconstruction decision can solve the latent graph task from visible simulator cards.
- `memory_evolution_runtime_v1` validates whether the real runtime path can build enough graph state from raw provider observations for the same judges to pass.

## Safety And Oracle Boundaries

Dry-run `llm` and `hybrid` modes use a fake extractor that emits only graph items explicitly exposed by simulator surface observations. This validates plumbing, artifacts, alignment, judges, and calibration without provider calls.

Live `llm` and `hybrid` modes use the runtime memory extractor stack. The live model is the system under test. It is not the oracle and it is not a judge.

Oracle fields, expected ids, hidden graph items, and judge votes are not passed into runtime extraction. They are used only after runtime graph projection for alignment and scoring.

## Runtime Output Projection

The benchmark aligns runtime graph nodes and edges back to latent entities, claims, relations, evidence, and actions:

- entity alignment: canonical/alias name, entity type, and evidence overlap
- claim alignment: subject, predicate, normalized object, scope, and optional valid time
- relation alignment: endpoint ids, relation type, and directionality
- provenance alignment: runtime `OBSERVED_IN` sources mapped back to simulator event ids

Aligned graph state is converted into a `SimSystemOutput`-compatible checkpoint view so the existing role-aware judges can be reused without weakening the simulator contract.

## Artifacts

In addition to the normal benchmark report and calibration artifacts, the runtime suite writes:

- `runtime_graph_snapshot.json`
- `runtime_graph_items.jsonl`
- `runtime_graph_alignments.jsonl`
- `runtime_checkpoint_results.jsonl`
- `runtime_failures.jsonl`

These files are intended to support stage attribution: extraction, validation, evolution, graph projection, alignment, or retrieval-decision projection.

## Agent Integration Gate

Passing this suite is the gate before treating Memorii as a default memory substrate for Hermes/OpenClaw-style agents. Early live adversarial runs are expected to expose classified runtime failures. The first goal is auditable failure, then smoke stability, then adversarial robustness.

Production defaults are not changed by this suite. Runtime memory evolution remains opt-in.
