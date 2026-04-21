# Memorii Benchmark Design Specification

## Status
Draft for implementation. This document is normative for the benchmark system and dataset design. If benchmark code and this document disagree, the benchmark code must be updated to match this document unless an explicit design change is approved.

---

## 1. Purpose

Memorii is not only a retrieval system. It is a memory plane for agents. The benchmark system must therefore evaluate both:

1. **Industry-parity memory behavior**
   - transcript retrieval
   - semantic retrieval
   - multi-hop / implicit retrieval
   - long-horizon memory use

2. **Memorii-specific memory-plane behavior**
   - routing correctness
   - blocked-write correctness
   - execution resume correctness
   - solver resume correctness
   - solver validation correctness
   - writeback correctness
   - semantic pollution avoidance
   - user-memory pollution avoidance
   - end-to-end memory-assisted task success

This document defines:
- benchmark architecture
- benchmark execution flow
- fixture and dataset schema
- external dataset adaptation rules
- scenario category definitions
- baseline definitions
- metrics and exact formulas
- reproducibility rules
- acceptance criteria
- review and reporting requirements

This document is written so a junior engineer can implement the system without inventing missing behavior.

---

## 2. Non-goals

The benchmark system does **not** attempt to:
- reproduce public leaderboard numbers exactly for external benchmarks
- evaluate general model intelligence independent of memory
- use live LLM judges for correctness scoring
- run online downloads during normal benchmark execution
- provide dashboards or production telemetry
- benchmark distributed systems behavior

---

## 3. Definitions

### 3.1 System Under Test (SUT)
The SUT is Memorii running in one of the supported benchmark modes:
- `memorii`
- `baseline_transcript_only`
- `baseline_flat_retrieval`
- `baseline_no_solver_graph`

### 3.2 Benchmark Scenario
A scenario is one fully specified evaluation unit. It includes:
- initial state
- one or more benchmark steps
- expected outputs
- expected final conditions
- applicable baselines
- scenario-level metadata

### 3.3 Component-level scenario
A benchmark scenario that intentionally tests one subsystem in isolation, such as:
- router only
- verifier only
- retrieval planner only

### 3.4 System-level scenario
A benchmark scenario that must execute through the runtime API or `RuntimeStepService`, not only isolated component calls.

### 3.5 External dataset adapter
A module that converts raw examples from a public benchmark dataset into Memorii benchmark fixtures.

---

## 4. Benchmark layers

### 4.1 Layer A — Industry parity
Purpose: show that Memorii is at least competitive on standard retrieval-style memory tasks.

Initial targets:
- HotpotQA-derived fixtures
- LongMemEval-derived fixtures
- later: LoCoMo-derived fixtures

Layer A asks:
- can Memorii retrieve the correct supporting memory?
- can it do multi-hop / implicit retrieval reasonably well?
- is it competitive with simple baselines?

### 4.2 Layer B — Memorii differentiation
Purpose: evaluate features missing from standard memory benchmarks.

This includes:
- routing correctness
- blocked-write correctness
- execution resume correctness
- solver resume correctness
- solver validation correctness
- writeback correctness
- semantic pollution rate
- user-memory pollution rate
- end-to-end task success

### 4.3 Layer C — Advanced memory behavior
Purpose: evaluate memory behavior over time and under structure.

This includes:
- learning across episodes
- long-horizon degradation
- conflict resolution
- implicit recall

---

## 5. Benchmark directory structure

The benchmark implementation must use the following structure unless explicitly revised:

```text
memorii/
  memorii/
    core/
      benchmark/
        __init__.py
        adapters/
          __init__.py
          hotpotqa.py
          longmemeval.py
        baselines.py
        fixtures.py
        harness.py
        metrics.py
        models.py
        reporting.py
        reproducibility.py
        scenarios.py
        validation.py
  tests/
    fixtures/
      benchmarks/
        __init__.py
        benchmark_minimal.py
        hotpotqa_sample.py
        longmemeval_sample.py
    unit/
      core/
        benchmark/
          test_adapters.py
          test_baselines.py
          test_benchmark_categories.py
          test_fixture_validation.py
          test_harness.py
          test_metrics.py
          test_reporting.py
          test_reproducibility.py
          test_scenarios.py
    integration/
      test_benchmark_system_level.py
  docs/
    design/
      benchmarking.md
```

Notes:
- `validation.py` is required. It must validate scenario fixture shape and category-specific invariants.
- `adapters/` is required for external dataset conversion.
- external dataset samples used in tests must be local and checked into the repo or generated deterministically.

---

## 6. Benchmark execution model

### 6.1 Execution overview
For each benchmark run:

1. load benchmark fixtures
2. validate fixtures
3. normalize fixture ordering
4. construct deterministic run ID
5. for each fixture:
   1. determine applicable systems / baselines
   2. execute the fixture in each applicable system mode
   3. collect scenario observation
   4. compute scenario metrics
6. aggregate metrics by system
7. aggregate metrics by category
8. compute baseline deltas
9. emit machine-readable report
10. emit optional markdown report

### 6.2 System-level vs component-level enforcement
Every scenario must declare:
- `execution_level = "component_level" | "system_level"`

Rules:
- `end_to_end`, `learning_across_episodes`, and any task-flow benchmark that claims system behavior **must** be `system_level`
- `routing_correctness`, `solver_validation`, and some planner benchmarks may be `component_level`
- report output must preserve the execution level

### 6.3 Entry points
For system-level scenarios, the benchmark executor must use either:
- the public runtime API, or
- `RuntimeStepService`

Direct component calls are not allowed for system-level scenarios.

---

## 7. Canonical benchmark schema

The benchmark system must support a canonical top-level fixture schema.

```python
class BenchmarkScenarioFixture(BaseModel):
    scenario_id: str
    title: str
    description: str
    category: BenchmarkScenarioType
    execution_level: BenchmarkExecutionLevel
    source: BenchmarkSourceMetadata

    initial_state: BenchmarkInitialState
    steps: list[BenchmarkStep]
    expected: BenchmarkExpectedOutcome

    baseline_applicability: dict[BenchmarkSystem, BaselineApplicability] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
```

### 7.1 Why canonical schema is required
A single top-level schema is required so that:
- fixture authors do not guess where to put information
- dataset adapters can target one format
- validation can be generic
- scenario execution can evolve without changing every fixture format

Scenario-type-specific helper models are allowed internally, but the canonical fixture persisted in fixtures must follow the top-level schema.

---

## 8. Source metadata

```python
class BenchmarkSourceMetadata(BaseModel):
    source_type: Literal["handcrafted", "external_dataset", "synthetic"]
    dataset_name: str | None = None
    dataset_split: str | None = None
    dataset_example_id: str | None = None
    adapter_name: str | None = None
    seed: int | None = None
```

Rules:
- handcrafted fixtures must set `source_type="handcrafted"`
- adapted HotpotQA fixtures must set:
  - `source_type="external_dataset"`
  - `dataset_name="hotpotqa"`
  - `dataset_split` and `dataset_example_id`
  - `adapter_name`

---

## 9. Initial state schema

```python
class BenchmarkInitialState(BaseModel):
    transcript_entries: list[TranscriptEntry] = Field(default_factory=list)
    memory_objects: list[BenchmarkMemoryObject] = Field(default_factory=list)
    execution_nodes: list[BenchmarkExecutionNode] = Field(default_factory=list)
    execution_edges: list[BenchmarkExecutionEdge] = Field(default_factory=list)
    solver_nodes: list[BenchmarkSolverNode] = Field(default_factory=list)
    solver_edges: list[BenchmarkSolverEdge] = Field(default_factory=list)
    solver_overlays: list[BenchmarkSolverOverlay] = Field(default_factory=list)
```

### 9.1 Transcript entry
```python
class TranscriptEntry(BaseModel):
    entry_id: str
    role: Literal["user", "assistant", "tool"]
    content: str
    timestamp: int
    task_id: str | None = None
    execution_node_id: str | None = None
    solver_run_id: str | None = None
```

### 9.2 Benchmark memory object
```python
class BenchmarkMemoryObject(BaseModel):
    memory_id: str
    memory_type: Literal["transcript", "semantic", "episodic", "user", "execution", "solver"]
    text: str
    content: dict[str, Any] = Field(default_factory=dict)

    task_id: str | None = None
    execution_node_id: str | None = None
    solver_run_id: str | None = None
    agent_id: str | None = None

    status: Literal["candidate", "committed"] = "committed"

    created_at: int
    valid_from: int | None = None
    valid_to: int | None = None
    validity_status: Literal["active", "expired", "invalidated", "candidate"] = "active"
```

### 9.3 Execution node
```python
class BenchmarkExecutionNode(BaseModel):
    node_id: str
    node_type: str
    status: Literal["pending", "ready", "running", "blocked", "completed", "failed"]
    title: str
    description: str
```

### 9.4 Execution edge
```python
class BenchmarkExecutionEdge(BaseModel):
    edge_id: str
    src: str
    dst: str
    edge_type: str
```

### 9.5 Solver node
```python
class BenchmarkSolverNode(BaseModel):
    node_id: str
    node_type: str
    content: dict[str, Any]
    status: Literal[
        "unknown",
        "active",
        "supported",
        "refuted",
        "insufficient_evidence",
        "needs_test",
        "multiple_plausible_options",
    ]
    source_refs: list[str] = Field(default_factory=list)
```

### 9.6 Solver edge
```python
class BenchmarkSolverEdge(BaseModel):
    edge_id: str
    src: str
    dst: str
    edge_type: str
    status: Literal["candidate", "committed"]
```

### 9.7 Solver overlay
```python
class BenchmarkSolverOverlay(BaseModel):
    version_id: str
    solver_run_id: str
    node_id: str
    belief: float
    status: str
    is_frontier: bool = False
    reopenable: bool = False
    unexplained: bool = False
```

---

## 10. Benchmark step schema

```python
class BenchmarkStep(BaseModel):
    step_id: str
    observation: BenchmarkObservationInput
    expected_step: BenchmarkExpectedStep
```

### 10.1 Observation input
```python
class BenchmarkObservationInput(BaseModel):
    event_id: str
    event_class: str
    task_id: str
    execution_node_id: str | None = None
    solver_run_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    model_output: dict[str, Any] | None = None
```

### 10.2 Expected step
```python
class BenchmarkExpectedStep(BaseModel):
    expected_routed_domains: list[str] = Field(default_factory=list)
    expected_blocked_domains: list[str] = Field(default_factory=list)
    expected_retrieved_ids: list[str] = Field(default_factory=list)
    expected_solver_decision: str | None = None
    expected_follow_up_required: bool | None = None
    expected_writeback_domains: list[str] = Field(default_factory=list)
```

---

## 11. Expected outcome schema

```python
class BenchmarkExpectedOutcome(BaseModel):
    success: bool

    expected_retrieved_ids: list[str] = Field(default_factory=list)
    expected_excluded_ids: list[str] = Field(default_factory=list)

    expected_execution_status_by_node: dict[str, str] = Field(default_factory=dict)
    expected_solver_frontier: list[str] = Field(default_factory=list)
    expected_unresolved_questions: list[str] = Field(default_factory=list)
    expected_reopenable_branches: list[str] = Field(default_factory=list)

    expected_writeback_domains: list[str] = Field(default_factory=list)
    expected_writeback_ids: list[str] = Field(default_factory=list)
```

---

## 12. Category definitions and required invariants

### 12.1 Transcript retrieval
Purpose:
- verify verbatim transcript retrieval under scope constraints

Required invariants:
- at least one transcript item in initial state
- expected retrieved IDs must point to transcript items only
- scenario may be component-level

### 12.2 Semantic retrieval
Purpose:
- verify retrieval of validated semantic facts

Required invariants:
- at least one semantic memory object
- excluded IDs may include speculative or expired items
- scenario may be component-level

### 12.3 Episodic retrieval
Purpose:
- verify retrieval of relevant prior-case abstractions

Required invariants:
- at least one episodic memory object
- expected retrieved IDs must point to episodic items
- scenario may be component-level

### 12.4 Routing correctness
Purpose:
- verify event fanout and blocked writes

Required invariants:
- exactly one benchmark step
- `expected_routed_domains` and `expected_blocked_domains` must be explicitly set
- scenario may be component-level

### 12.5 Execution resume
Purpose:
- verify execution graph persistence and restoration

Required invariants:
- initial execution graph state must be provided
- expected execution status by node must be provided
- scenario may be component-level or system-level

### 12.6 Solver resume
Purpose:
- verify solver frontier / unresolved / reopenable restoration

Required invariants:
- initial solver nodes and overlays must be provided
- expected frontier must be provided
- scenario may be component-level or system-level

### 12.7 Solver validation
Purpose:
- verify downgrade / abstention / invalid-output rejection

Required invariants:
- exactly one step
- step must include `model_output`
- expected solver decision must be set
- scenario may be component-level

### 12.8 End-to-end
Purpose:
- verify routed event -> retrieval -> solver -> writeback through real runtime path

Required invariants:
- scenario must be `system_level`
- at least one step
- runtime must be exercised
- expected writeback domains should be set when applicable

### 12.9 Learning across episodes
Purpose:
- verify reuse of memory written or consolidated in prior episode(s)

Required invariants:
- scenario must be `system_level`
- at least two benchmark steps or two linked fixtures
- must include explicit reuse target
- must include expected writeback and expected reuse outcome

### 12.10 Long-horizon degradation
Purpose:
- verify retrieval under noise and distance

Required invariants:
- total number of candidate items >= 50
- proportion of relevant items <= 0.20
- delayed retrieval depends on items introduced earlier in the scenario
- must include explicit noise IDs
- may be component-level for pure retrieval studies, but system-level preferred

### 12.11 Conflict resolution
Purpose:
- verify stale/invalid vs valid/new memory handling

Required invariants:
- at least two conflicting memory candidates
- each candidate must include one of:
  - version number
  - timestamp
  - validity window
- fixture must specify expected winning candidate
- scenario may be component-level or system-level

### 12.12 Implicit recall
Purpose:
- verify retrieval when lexical overlap is low

Required invariants:
- each relevant item must include precomputed lexical overlap metadata
- overlap with query must be <= configured threshold
- expected domains must be provided
- scenario may be component-level for retrieval studies, system-level optional

---

## 13. Lexical overlap definition for implicit recall

The benchmark system must use a deterministic overlap definition.

### 13.1 Tokenization
- lowercase
- split on whitespace
- strip punctuation from token edges
- remove empty tokens

### 13.2 Jaccard overlap
```python
jaccard(query_tokens, memory_tokens) = |intersection| / |union|
```

### 13.3 Threshold
Default threshold for implicit recall fixtures:
- `max_query_memory_jaccard <= 0.20`

If a relevant item exceeds this threshold, fixture validation must fail unless the fixture explicitly sets an override with justification.

---

## 14. External dataset adaptation rules

### 14.1 General rule
External datasets may only be used after conversion into canonical Memorii benchmark fixtures.

### 14.2 Adapter responsibilities
An adapter must:
1. parse raw examples
2. select a deterministic subset
3. map raw fields into canonical fixture fields
4. preserve provenance metadata
5. emit validated benchmark fixtures

### 14.3 HotpotQA adaptation rules
Initial external dataset target: HotpotQA.

For HotpotQA-derived fixtures:
- `question` -> benchmark query / step context
- `context` paragraphs -> candidate semantic memory items and/or transcript-like corpus items
- `supporting_facts` -> expected relevant memory IDs
- `answer` -> expected answer string only if answer checking is enabled

HotpotQA-derived scenarios may initially populate:
- semantic retrieval
- implicit recall
- lightweight end-to-end scenarios

Do **not** attempt full leaderboard reproduction.

### 14.4 Subset selection
Subset selection must be deterministic by:
- dataset name
- split
- seed
- subset size

The selected example IDs must be stored in the fixture metadata or emitted alongside the benchmark run.

---

## 15. Baselines

The benchmark system must support these baselines.

### 15.1 Memorii
The full system under test.

### 15.2 Transcript-only baseline
Rules:
- use only transcript entries
- no semantic, episodic, user, execution, or solver memory retrieval
- no routing planner benefits beyond transcript handling

### 15.3 Flat retrieval baseline
Rules:
- retrieve from all available memory candidates without scoped planner filtering
- no namespace-aware planner logic

### 15.4 No-solver-graph baseline
Rules:
- execution memory available
- solver graph retrieval disabled
- solver-specific memory and frontier state not used

### 15.5 Baseline applicability
Every scenario must either:
- run against all baselines, or
- explicitly skip a baseline with a reason

Skipping without reason is invalid.

---

## 16. Observation schema

```python
class ScenarioObservation(BaseModel):
    scenario_id: str
    category: str
    execution_level: str
    system: str

    retrieved_ids: list[str] = Field(default_factory=list)
    relevant_ids: list[str] = Field(default_factory=list)
    excluded_ids: list[str] = Field(default_factory=list)

    expected_routed_domains: list[str] = Field(default_factory=list)
    observed_routed_domains: list[str] = Field(default_factory=list)
    expected_blocked_domains: list[str] = Field(default_factory=list)
    observed_blocked_domains: list[str] = Field(default_factory=list)

    retrieval_latency_ms: float = 0.0

    execution_resume_correct: bool | None = None
    solver_resume_correct: bool | None = None
    frontier_restore_correct: bool | None = None
    unresolved_restore_correct: bool | None = None

    downgraded: bool | None = None
    abstention_preserved: bool | None = None
    invalid_output_rejected: bool | None = None

    scenario_success: bool | None = None

    expected_writeback_domains: list[str] = Field(default_factory=list)
    observed_writeback_domains: list[str] = Field(default_factory=list)
    expected_writeback_ids: list[str] = Field(default_factory=list)
    observed_writeback_ids: list[str] = Field(default_factory=list)

    semantic_pollution: bool | None = None
    user_memory_pollution: bool | None = None

    cross_episode_reuse_correct: bool | None = None
    baseline_without_reuse_success: bool | None = None
    writeback_reuse_correct: bool | None = None
    performance_improvement_over_baseline: float | None = None

    early_recall: float | None = None
    delayed_recall: float | None = None
    early_latency_ms: float | None = None
    delayed_latency_ms: float | None = None
    noise_hit_count: int | None = None
    retrieval_recall_degradation: float | None = None
    retrieval_latency_growth: float | None = None
    resume_correctness_under_scale: bool | None = None
    noise_resilience: float | None = None

    conflict_detected: bool | None = None
    conflict_resolution_correct: bool | None = None
    stale_memory_rejected: bool | None = None
    contradictory_handling_correct: bool | None = None

    implicit_recall_success: bool | None = None
    retrieval_plan_relevance_accuracy: bool | None = None
    false_positive_retrieval_rate: float | None = None
```

---

## 17. Metric definitions

All metric computation must be deterministic.

### 17.1 Retrieval metrics

#### Recall@K
```python
recall_at_k = len(set(retrieved_ids) & set(relevant_ids)) / len(set(relevant_ids))
```
If `relevant_ids` is empty, metric is `None`.

#### Precision@K
```python
precision_at_k = len(set(retrieved_ids) & set(relevant_ids)) / len(retrieved_ids)
```
If `retrieved_ids` is empty, metric is `None`.

#### Retrieval latency
Use deterministic measured or simulated value in milliseconds.
For synthetic/component benchmarks, the method used must be documented and consistent.

### 17.2 Routing metrics

#### Routing accuracy
```python
routing_accuracy = 1.0 if set(observed_routed_domains) == set(expected_routed_domains) else 0.0
```

#### Blocked write accuracy
```python
blocked_write_accuracy = 1.0 if set(observed_blocked_domains) == set(expected_blocked_domains) else 0.0
```

#### Multi-domain fanout correctness
```python
multi_domain_fanout_correctness = 1.0 if len(expected_routed_domains) > 1 and set(observed_routed_domains) == set(expected_routed_domains) else 0.0
```
If the scenario does not require fanout, metric may be `None`.

### 17.3 Resume metrics

#### Execution resume correctness
Binary metric based on final reconstructed execution state vs expected execution state.

#### Solver resume correctness
Binary metric based on final reconstructed solver state vs expected solver state.

#### Frontier restore correctness
Binary metric based on active frontier equality.

#### Unresolved restore correctness
Binary metric based on unresolved-question equality.

### 17.4 Solver validation metrics

#### Unsupported commitment downgrade rate
For scenarios where downgrade is expected:
```python
1.0 if downgraded == True else 0.0
```
Else `None`.

#### Abstention preservation rate
```python
1.0 if abstention_preserved == True else 0.0
```
Else `None`.

#### Invalid output rejection rate
```python
1.0 if invalid_output_rejected == True else 0.0
```
Else `None`.

### 17.5 Writeback metrics

#### Writeback candidate correctness
```python
1.0 if set(observed_writeback_domains) == set(expected_writeback_domains) and
         (not expected_writeback_ids or set(observed_writeback_ids) == set(expected_writeback_ids))
    else 0.0
```
Do not compute this as “some writeback exists”.

#### Semantic pollution rate
```python
1.0 if semantic_pollution == True else 0.0
```
Lower is better.

#### User-memory pollution rate
```python
1.0 if user_memory_pollution == True else 0.0
```
Lower is better.

### 17.6 Learning metrics

#### Cross-episode reuse accuracy
```python
1.0 if cross_episode_reuse_correct == True else 0.0
```

#### Performance improvement over baseline
Use the precomputed scalar field. Positive is better.

#### Writeback reuse correctness
```python
1.0 if writeback_reuse_correct == True else 0.0
```

### 17.7 Long-horizon metrics

#### Retrieval recall degradation
```python
max(0.0, early_recall - delayed_recall)
```
Lower is better.

#### Retrieval latency growth
```python
delayed_latency_ms - early_latency_ms
```
Lower is better.

#### Resume correctness under scale
Binary.

#### Noise resilience
```python
1.0 - (noise_hit_count / max(1, len(retrieved_ids)))
```
Higher is better.

### 17.8 Conflict metrics

#### Conflict detection rate
Binary.

#### Correct preference for newer or valid memory
Binary.

#### Stale memory rejection rate
Binary.

#### Contradictory memory handling correctness
Binary.

### 17.9 Implicit recall metrics

#### Implicit recall success rate
Binary.

#### Retrieval plan relevance accuracy
Binary based on whether planned domains include expected domains.

#### False positive retrieval rate
```python
len(set(retrieved_ids) - set(relevant_ids)) / max(1, len(retrieved_ids))
```
Lower is better.

### 17.10 End-to-end metric

#### Scenario success rate
```python
1.0 if scenario_success == True else 0.0
```

---

## 18. Aggregation rules

### 18.1 Aggregate by system
For each system, compute the arithmetic mean of each non-`None` metric across scenarios.

### 18.2 Aggregate by category
For each category and system, compute the arithmetic mean of each non-`None` metric across scenarios in that category.

### 18.3 Baseline delta
For each scenario and baseline:
```python
memorii_metric - baseline_metric
```
Only compute deltas where both values are non-`None`.

---

## 19. Validation rules

A benchmark validation module is required.

### 19.1 Global validation
Validation must fail if:
- duplicate `scenario_id`
- unsupported category
- unsupported execution level
- invalid baseline skip with no reason

### 19.2 Category/subtype validation
Validation must fail if a scenario does not provide required fields for its category.

### 19.3 Long-horizon validation
Validation must fail if:
- total candidate count < 50
- relevant proportion > 0.20
- noise IDs are missing

### 19.4 Implicit-recall validation
Validation must fail if:
- lexical overlap metadata missing
- overlap threshold exceeded without explicit justification

### 19.5 Conflict validation
Validation must fail if:
- fewer than two conflict candidates
- no expected winning candidate
- candidates missing temporal or validity semantics

### 19.6 Minimum fixture counts
The preflight validator must warn or fail according to configured strictness if required benchmark categories do not have minimum coverage.

Initial minimums for a “research review ready” benchmark set:
- transcript retrieval: 3
- semantic retrieval: 3
- episodic retrieval: 3
- routing correctness: 3
- execution resume: 2
- solver resume: 2
- solver validation: 4
- end-to-end: 3
- learning across episodes: 3
- long-horizon degradation: 3
- conflict resolution: 3
- implicit recall: 3

---

## 20. Reporting requirements

The benchmark system must emit:

### 20.1 Machine-readable report
Fields must include:
- run ID
- generated timestamp
- run config
- scenario results
- aggregate by system
- aggregate by category
- baseline comparison

### 20.2 Markdown report
Must include:
- summary of aggregate metrics by system
- aggregate metrics by category
- per-scenario result rows
- baseline comparison section
- scenario execution level (`component_level` vs `system_level`)

---

## 21. Reproducibility requirements

The benchmark system must be reproducible.

### 21.1 Seeds
All subset selection and any pseudo-random ordering must be controlled by seed.

### 21.2 Stable run ID
Run ID must be derived from:
- run label
- seed
- normalized fixture identity list

### 21.3 No network dependency
Normal benchmark execution must not require network access.
External datasets must be pre-downloaded or adapted ahead of time.

### 21.4 Test reproducibility
Tests must use:
- local sample fixtures
- deterministic sample data
- no online fetches

---

## 22. Benchmark review requirements (Phase 8)

Benchmark review must produce a markdown report containing:
- result matrix by category and baseline
- top wins
- top failures
- root-cause analysis
- benchmark-validity concerns
- prioritized fix list

Root-cause categories must be chosen from:
- benchmark fixture issue
- benchmark metric issue
- retrieval planner issue
- retrieval execution / ranking issue
- router policy issue
- runtime issue
- solver / verifier issue
- consolidation / writeback issue
- performance issue
- acceptable tradeoff

---

## 23. Acceptance criteria

The benchmark system is implementation-complete only if:

1. fixtures validate deterministically
2. all required categories can run
3. all baselines run or skip explicitly with reason
4. aggregate metrics by system and by category are emitted
5. baseline deltas are emitted
6. at least one system-level end-to-end scenario executes through the real runtime path
7. long-horizon, conflict, and implicit-recall scenarios satisfy their stricter validation rules
8. writeback and routing metrics use explicit expectations, not overloaded retrieval fields
9. benchmark reports are reproducible given the same seed and fixture set

---

## 24. Implementation notes for the current repo

Given the current codebase, the following implementation strategy is recommended:

1. keep the existing benchmark package under `memorii.core.benchmark`
2. add `validation.py`
3. add `adapters/`
4. migrate current scenario-union fixtures toward the canonical top-level schema
5. preserve existing report format where practical, but extend it to include execution level and stricter metric semantics
6. make end-to-end scenarios use the real runtime path

---

## 25. Summary

This benchmark system must evaluate both:
- whether Memorii matches strong basic memory behavior on standard tasks
- whether Memorii’s unique memory-plane design improves routing, resume, solver correctness, and writeback safety

The implementation must be:
- deterministic
- self-contained
- rigorous enough to stand up to scrutiny from experienced ML researchers
- concrete enough that a junior engineer can implement it without inventing benchmark semantics
