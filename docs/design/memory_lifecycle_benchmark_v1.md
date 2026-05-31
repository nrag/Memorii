# Memory Lifecycle Benchmark v1

## Purpose

Promotion and belief v1 now test individual memory decisions well enough to freeze as a regression suite. The next benchmark should test whether memory evolves correctly over time.

Memory lifecycle behavior is higher value than adding more isolated promotion/belief traps because production failures usually come from sequence errors:

- a memory is created correctly but never reused
- a correction is stored but stale memory still wins retrieval
- a duplicate is promoted instead of merged
- a task-scoped preference leaks into durable user memory
- a contradiction is noticed but not resolved
- retrieval returns plausible but wrong historical context

The Memory Lifecycle Benchmark v1 evaluates those temporal behaviors end to end.

## Relationship To Existing Evals

Current frozen LLM decision baseline:

```text
rule   43/61
llm    61/61
hybrid 61/61
```

Those 61 promotion/belief cases are decision-point regression tests. They should be changed only when a real failure is discovered.

Memory Lifecycle v1 is a system benchmark. It does not replace promotion/belief v1. Instead, it checks that a sequence of decisions produces the correct memory-plane state and retrieval behavior.

Run it with:

```bash
PYTHONPATH=memorii python -m memorii.tools.run_eval --suite memory_lifecycle_v1 --storage-root .memorii
```

The default mode is `auto`: it resolves to `hybrid` when a real LLM provider and API key are configured, and to `rule` otherwise.
Explicit `hybrid` also falls back to rule mode when no LLM provider/key is configured. Explicit `llm` is strict and intended for benchmark/eval use.

Artifacts are written under `.memorii/benchmark_runs/memory_lifecycle_v1/<mode>/<run_id>/`.

LLM-backed lifecycle transition runs use the same entry point:

```bash
PYTHONPATH=memorii python -m memorii.tools.run_eval --suite memory_lifecycle_v1 --mode llm --allow-live --storage-root .memorii
PYTHONPATH=memorii python -m memorii.tools.run_eval --suite memory_lifecycle_v1 --mode hybrid --storage-root .memorii
```

Lifecycle artifacts include `lifecycle_traces.jsonl` and `llm_traces.jsonl`. Each lifecycle trace records the requested mode, effective mode, whether an LLM call happened, whether fallback was used, the fallback reason, the final output source, and whether the transition assertion passed.

## Benchmark Thesis

A good memory system must preserve the lifecycle invariant:

```text
observe -> stage -> promote/block -> retrieve -> merge/supersede/expire -> retrieve correct current memory
```

The benchmark should catch failures at each transition, not only at one decision point.

## Existing Benchmark Categories To Use

Memory Lifecycle v1 should build on the current benchmark schema instead of introducing a new top-level framework.

Map lifecycle scenario families onto existing categories:

```text
create and reuse                 -> learning_across_episodes
merge duplicate                  -> conflict_resolution or end_to_end
supersede corrected memory       -> conflict_resolution
stale memory demotion            -> long_horizon_degradation or conflict_resolution
scope preservation               -> end_to_end
retrieval after update           -> semantic_retrieval / episodic_retrieval
implicit reuse of learned memory -> implicit_recall
```

If implementation friction is high, add one new scenario category later:

```text
memory_lifecycle
```

Do not add it until at least two lifecycle scenarios are awkward to express with the current schema.

## V1 Scenario Families

Start with 10 handcrafted scenarios. Keep them small, readable, and deterministic.

### 1. Create And Reuse User Preference

Episode 1:

User explicitly says they prefer concise coding answers.

Expected:

- user memory is staged/promoted
- later query retrieves that preference
- response context includes the durable user preference

Failure modes caught:

- memory not written
- memory written to wrong plane
- preference not retrieved later

Suggested category:

```text
learning_across_episodes
```

### 2. Block Inferred User Preference

Episode 1:

User asks for concise output once or twice without an explicit memory request.

Episode 2:

Similar style request appears again but remains ambiguous.

Expected:

- no durable user memory auto-promotion
- optional review candidate is allowed
- retrieval should not treat the inferred preference as committed

Failure modes caught:

- user-memory pollution
- repeated behavior over-promoted

Suggested category:

```text
end_to_end
```

### 3. Merge Near Duplicate Preference

Initial state:

Committed memory: "User prefers concise direct answers."

New event:

"Remember that I strongly prefer brief, direct responses."

Expected:

- do not create a second standalone user memory
- create merge/supersession candidate
- retrieval returns one consolidated preference

Failure modes caught:

- duplicate durable memories
- retrieval confusion from near duplicates

Suggested category:

```text
conflict_resolution
```

### 4. Supersede Corrected Preference

Initial state:

Committed memory: "User prefers detailed answers by default."

New event:

"Actually, for coding work, prefer concise answers."

Expected:

- old memory is superseded or scoped
- new memory is active for coding contexts
- old memory is not returned as the current preference for coding

Failure modes caught:

- stale preference outranks correction
- contradiction stored without lifecycle linkage

Suggested category:

```text
conflict_resolution
```

### 5. Preserve Task-Scoped Preference

Event:

"For this PR, be very verbose in review comments."

Later unrelated coding session:

Query asks for preferred answer style.

Expected:

- PR-scoped preference is not durable global user memory
- retrieval does not apply it outside the PR context

Failure modes caught:

- task-local memory leaks globally
- retrieval scope ignored

Suggested category:

```text
end_to_end
```

### 6. Promote Repeated Project Fact With Review

Episodes:

Release freeze happens every Friday in multiple recent sprints.

Expected:

- project fact can be promoted
- requires review or temporal scope annotation
- retrieval uses it for current sprint planning

Failure modes caught:

- repeated current project facts rejected because they are time-bound
- missing temporal metadata

Suggested category:

```text
learning_across_episodes
```

### 7. Supersede Stale Project Fact

Initial state:

"Beta rollout requires manual QA sign-off."

Correction:

"Manual QA gate was replaced by automated checks."

Expected:

- old project fact is inactive/superseded
- new project fact is active
- retrieval for rollout checklist returns automated gate, not manual QA

Failure modes caught:

- stale fact retrieval
- missing supersession edge

Suggested category:

```text
conflict_resolution
```

### 8. Avoid Wrong Entity Carryover

Initial state:

ACME requires SOC2 review.

Distractor:

Apex appears in pasted docs near the ACME ticket.

Later query:

"What does Apex require before rollout?"

Expected:

- ACME memory is not applied to Apex
- retrieval either abstains or asks for Apex-specific evidence

Failure modes caught:

- wrong entity linking
- plausible but corrupt retrieval

Suggested category:

```text
semantic_retrieval or implicit_recall
```

### 9. Retrieval After Expiration

Initial state:

Time-bound memory: "Release freeze applies this sprint."

Later context:

Sprint has ended.

Expected:

- expired memory is not retrieved as active
- if retrieved, it is clearly marked stale/historical

Failure modes caught:

- temporal validity ignored
- stale memories treated as active

Suggested category:

```text
long_horizon_degradation
```

### 10. End-To-End Lifecycle With Noise

Sequence:

1. user gives explicit project preference
2. several noisy tool logs and temporary debug states occur
3. user corrects the preference
4. later query asks for current preference

Expected:

- noise is not promoted
- original preference is linked to correction
- retrieval returns the corrected current memory

Failure modes caught:

- semantic pollution
- missing correction handling
- retrieval over noisy repeated observations

Suggested category:

```text
end_to_end
```

## Minimal Fixture Shape

Use the existing `BenchmarkScenarioFixture` where possible.

For lifecycle scenarios, fixture metadata should include:

```json
{
  "lifecycle_family": "supersede_corrected_preference",
  "expected_active_memory_ids": ["mem:user:concise-coding"],
  "expected_inactive_memory_ids": ["mem:user:detailed-default"],
  "expected_absent_memory_texts": ["prefer detailed answers by default"],
  "expected_retrieval_ids": ["mem:user:concise-coding"],
  "expected_excluded_retrieval_ids": ["mem:user:detailed-default"]
}
```

If these fields become common, promote them into a typed fixture model:

```python
class MemoryLifecycleFixture(BaseModel):
    lifecycle_family: MemoryLifecycleFamily
    initial_memories: list[RetrievalFixtureMemoryItem]
    events: list[ProviderOperation]
    final_query: str
    expected_active_memory_ids: list[str]
    expected_inactive_memory_ids: list[str]
    expected_retrieval_ids: list[str]
    expected_excluded_retrieval_ids: list[str]
    expected_promotion_actions: list[str]
```

Do this only after the first handcrafted scenarios prove the shape.

## Metrics

V1 should report simple deterministic metrics:

```text
lifecycle_success_rate
active_memory_accuracy
inactive_memory_accuracy
retrieval_currentness_accuracy
duplicate_avoidance_accuracy
scope_preservation_accuracy
pollution_avoidance_accuracy
```

Definitions:

- `active_memory_accuracy`: expected active memories are active/committed at final state
- `inactive_memory_accuracy`: superseded, expired, or blocked memories are not active
- `retrieval_currentness_accuracy`: final retrieval returns current memory and excludes stale/incorrect memory
- `duplicate_avoidance_accuracy`: near duplicate events do not create standalone duplicate committed memories
- `scope_preservation_accuracy`: task/session/trip-scoped memory is not retrieved globally
- `pollution_avoidance_accuracy`: noise, spam, temporary debug state, and wrong-entity facts are not committed as durable memory

`lifecycle_success_rate` should require all applicable checks to pass for a scenario.

## Baselines

Run these baselines where applicable:

```text
memorii
transcript_only_baseline
flat_retrieval_baseline
no_solver_graph_baseline
```

Expected baseline behavior:

- transcript-only may recover recent explicit facts but should fail merge/supersession/currentness cases
- flat retrieval should retrieve plausible stale/duplicate/wrong-entity distractors more often
- no-solver-graph baseline may pass simple memory reuse but fail execution/state-linked lifecycle cases

## Acceptance Criteria

Initial implementation is complete when:

- at least 10 lifecycle fixtures exist
- fixtures are deterministic and local
- all fixtures validate in benchmark preflight
- report includes lifecycle metrics
- Memorii beats flat retrieval on currentness, duplicate avoidance, and scope preservation
- failures include enough artifact detail to convert into promotion/belief golden candidates when appropriate

## Implementation Plan

### Phase 1: Handcrafted fixtures

Add 10 lifecycle fixtures under existing benchmark fixture/test structure.

Prefer using existing categories first:

- `learning_across_episodes`
- `conflict_resolution`
- `long_horizon_degradation`
- `implicit_recall`
- `end_to_end`

### Phase 2: Lifecycle result fields

Add observation fields only if needed by two or more scenarios.

Start with metadata-based expected fields before adding a new typed fixture model.

### Phase 3: Metrics

Add lifecycle metric helpers in `memorii.core.benchmark.metrics`.

Wire report output so lifecycle regressions are visible by scenario family.

### Phase 4: System-level harness

Move the most valuable scenarios from component-level simulation to provider/system execution.

The first system-level targets should be:

- create and reuse user preference
- supersede corrected preference
- stale project fact retrieval
- end-to-end lifecycle with noise

### Phase 5: Freeze v1

Once v1 is passing and discriminative, freeze it as the lifecycle regression baseline. Add new lifecycle scenarios only from real failures or intentionally approved new behavior.

## Non-Goals

V1 does not need:

- live LLM judging
- external dataset import
- large-scale synthetic generation
- HotpotQA-style open-domain reasoning
- production telemetry integration

## Recommended Next PR

Implement Phase 1 with a minimal fixture set and preflight validation. Keep the scope narrow:

- no new public API
- no LLM calls
- no external data
- no new benchmark category unless existing categories cannot express the scenarios cleanly

The point of the next PR is to make memory lifecycle failures observable, not to solve every lifecycle behavior immediately.
