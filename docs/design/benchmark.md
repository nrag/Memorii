

## 1. Scope

**Spec intent:** benchmark architecture, dataset schema, fixtures, execution flow, metrics, baselines, evaluation, acceptance criteria.

**Implementation:** mostly present.

What exists:

* benchmark harness and runner logic in `core/benchmark/harness.py` 
* dataset/fixture models in `core/benchmark/models.py` 
* metric computation in `core/benchmark/metrics.py` 
* baselines in `core/benchmark/baselines.py` 
* reproducibility helpers in `core/benchmark/reproducibility.py` 
* reporting in `core/benchmark/reporting.py` 
* deterministic fixture set in `tests/fixtures/benchmarks/benchmark_minimal.py` 

**Assessment:** **aligned at a high level**.

---

## 2. System Under Test (SUT)

**Spec intent:** all benchmarks should run through the actual system entrypoint, which we defined as `RuntimeStepService.step(...)`.

**Implementation:** **not aligned**.

In `ScenarioExecutor`, most benchmark categories do **not** run through `RuntimeStepService.step(...)`. Instead they call internal components directly:

* `RetrievalPlanner`
* `MemoryRouter`
* `ResumeService`
* `SolverDecisionVerifier`

and they simulate behavior in custom scenario methods. 

Examples:

* retrieval scenarios call `_retrieve(...)` with planner + manual ranking, not runtime 
* routing scenarios call `self._router.route_event(...)` directly 
* resume scenarios call `ResumeService(...)` directly 
* solver validation scenarios call `self._verifier.verify(...)` directly 

**Assessment:** **major drift**.

### Why this matters

This means the benchmark harness is partially benchmarking:

* the real system
* and partially benchmarking **synthetic benchmark logic**

So benchmark results are less trustworthy than they look.

---

## 3. Benchmark architecture

**Spec intent:** clear benchmark module layout and a canonical runner.

**Implementation:** mostly aligned, but directory differs from the doc.

Actual benchmark module layout is:

```text
memorii/memorii/core/benchmark/
  __init__.py
  baselines.py
  fixtures.py
  harness.py
  metrics.py
  models.py
  reporting.py
  reproducibility.py
  scenarios.py
```

This is confirmed by merged Phase 7 and 7.1 PRs and file structure.

**Assessment:** **aligned in substance**, **doc directory structure needs updating**.

---

## 4. Dataset / fixture schema

**Spec intent:** one canonical `BenchmarkFixture` with:

* `initial_state`
* `steps`
* `expected`

and strongly typed component objects.

**Implementation:** **not aligned**.

Instead of one canonical fixture model, the repo uses a **scenario-type-specific fixture union**:

* `RetrievalFixture`
* `RoutingFixture`
* `ExecutionResumeFixture`
* `SolverResumeFixture`
* `SolverValidationFixture`
* `EndToEndFixture`
* `LearningAcrossEpisodesFixture`
* `LongHorizonDegradationFixture`
* `ConflictResolutionFixture`
* `ImplicitRecallFixture`

all wrapped in `BenchmarkScenarioFixture`. 

This is workable, but it means:

* there is no single canonical “initial state / steps / expected” schema
* junior devs must infer execution semantics from scenario type
* fixture authors can’t use one universal pattern

**Assessment:** **major drift**.

### Recommendation

Either:

* keep this union design and update the design doc to match it, or
* refactor toward the stricter canonical fixture schema

Given current code maturity, I would **update the doc first**, then decide whether refactor is worth it.

---

## 5. Execution flow

**Spec intent:** for each fixture:

1. initialize system state
2. run steps
3. compare final state
4. compute metrics

**Implementation:** **partial alignment**.

What exists:

* `BenchmarkHarness.run(...)` loads fixtures, applies seed, executes each scenario for each system, computes metrics, aggregates results, and computes baseline deltas. 

But execution is per-scenario-type, not via a generic state machine. `ScenarioExecutor.run(...)` dispatches into many special-case methods. 

**Assessment:** **partially aligned**, but the execution model is not yet the generic fixture-driven flow from the spec.

---

## 6. Baselines

**Spec intent:** three baselines:

* transcript-only
* flat retrieval
* no solver graph

**Implementation:** **aligned**.

These exist as `BenchmarkSystem` members and `BASELINE_SYSTEMS`.

The harness runs Memorii plus baselines and supports skip policy through `BaselineApplicability`.

**Assessment:** **aligned**.

---

## 7. Metrics

**Spec intent:** exact metrics for retrieval, routing, resume, solver validation, writeback, advanced behaviors, end-to-end.

**Implementation:** mostly present, but some definitions drift from the intended semantics.

### What is good

The implementation has a broad metrics surface:

* retrieval
* routing
* resume
* solver validation
* writeback
* learning
* long-horizon
* conflict
* implicit recall

This is reflected in `ScenarioMetrics` and `METRIC_FIELDS`.

### What drifts

Some metrics are computed in a way that is too approximate or overloaded:

#### Routing metrics

`routing_accuracy` and `blocked_write_accuracy` rely on:

* `relevant_ids`
* `excluded_ids`

which are overloaded to store expected domain names as strings in routing scenarios.

That is brittle. Routing expectations should have dedicated typed fields.

#### Writeback correctness

`writeback_candidate_correctness` is currently:

* `scenario_success and bool(observation.writeback_candidate_domains)`

not an actual comparison against expected writeback candidates. 

That is too weak.

#### Conflict metrics

Conflict handling is reduced to booleans derived from a simplified candidate selection path. 

**Assessment:** **partially aligned**, **metric semantics need tightening**.

---

## 8. Scenario definitions

**Spec intent:** strict scenario rules.

### 8.1 Long horizon

**Spec:** minimum 50 transcript entries, few relevant, lots of noise.

**Implementation:** **not aligned**.

The “long horizon” fixture in `benchmark_minimal.py` uses only a tiny corpus of a few entries. 

### 8.2 Conflict

**Spec:** explicit timestamps / validity windows or equivalent strong temporal model.

**Implementation:** **partially aligned**.

Current conflict fixtures use:

* `recency_rank`
* `validity_status`
* `preferred`

via `ConflictCandidate`.

This is simpler than the spec and not strong enough for research-grade temporal conflict handling.

### 8.3 Implicit recall

**Spec:** enforce low lexical overlap.

**Implementation:** **not aligned**.

Current implicit recall is based on:

* keyword overlap
* context token overlap

with no explicit Jaccard/lexical-overlap threshold enforcement.

### 8.4 Learning

**Spec:** structured cross-episode reuse.

**Implementation:** **partially aligned**.

This exists as a scenario category and fixture type, but it is still implemented as a specialized retrieval case with a few extra flags, not as a full episode-state benchmark.

**Assessment:** **major drift in scenario rigor**.

---

## 9. Dataset construction rules

**Spec intent:** stable ids, deterministic fixtures, explicit expectations, no LLM dependence.

**Implementation:** mostly aligned.

What exists:

* stable scenario IDs and fixture objects
* deterministic run IDs based on fixture IDs + seed 
* no live model calls in benchmark core

**Assessment:** **aligned**.

---

## 10. Reporting

**Spec intent:** machine-readable output first, optional markdown summary.

**Implementation:** aligned.

`reporting.py` provides:

* JSON export
* Markdown export
* baseline summary JSON view 

**Assessment:** **aligned**.

---

## 11. Acceptance criteria

**Spec intent:** explicit completeness thresholds:

* reproducibility
* minimum fixture counts
* baselines
* metrics
* explainable failures

**Implementation:** **not encoded**.

I do not see acceptance-criteria enforcement in the benchmark harness itself. The harness runs and reports, but does not validate that:

* every category has enough fixtures
* all baselines ran where required
* reproducibility threshold was met
* failure explanation completeness exists

**Assessment:** **drift**.

---

## 12. Non-goals

**Spec intent:** no dashboards, no distributed runs, no live eval dependence.

**Implementation:** aligned.

The implementation stays local, deterministic, and simple.
No dashboard / distributed benchmarking was added.

**Assessment:** **aligned**.
