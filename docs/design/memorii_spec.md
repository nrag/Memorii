# Memorii Specification v0.1

## 1. Document purpose

This document specifies **Memorii**, a framework-neutral memory plane for agent systems.

Memorii is not a single memory store. It is a coordinated memory architecture plus runtime contracts that let an agent harness:

1. classify information into the right memory domain,
2. store one event in one or more domains when needed,
3. retrieve the right memory for the current step,
4. persist work across runs,
5. attach task-local solver memories to execution tasks,
6. support state-space search without corrupting long-term memory,
7. remain compatible with common agent harnesses.

This specification stays close to the design discussed earlier. It does not assume undocumented capabilities beyond what has already been defined.

---

## 2. Core problem statement

Current agent systems usually treat memory as one or more of:

- raw transcript history,
- retrieval over text chunks,
- vector memory,
- user preference memory,
- long-term summaries.

This is insufficient for agentic execution because two different concerns are often mixed together:

1. **Execution of work**
   - what tasks exist,
   - what dependencies exist,
   - what status each task is in,
   - what artifacts, tests, and invariants define completion.

2. **Search within a task**
   - hypotheses,
   - observations,
   - tests/actions,
   - branch revision,
   - uncertainty,
   - backtracking.

Memorii separates these concerns.

---

## 3. High-level architecture

Memorii consists of:

1. **Memory Plane**
   - multiple memory domains with clear ownership.

2. **Execution Graph**
   - persistent graph of assigned work.

3. **Solver Graphs**
   - task-local problem-solving memories attached to execution nodes.

4. **Capability Engines**
   - pluggable reasoning modules used to complete execution nodes.

5. **Memory Router**
   - decides where new information should be written.

6. **Retrieval Planner**
   - decides which memory domains to query for the current step.

7. **Memory Directory**
   - index of tasks, graphs, stores, and references.

8. **Consolidator**
   - converts transient task-local state into episodic, semantic, skill, or archival outputs.

9. **Framework Adapters**
   - integrate Memorii with external agent harnesses.

---

## 4. Goals

### 4.1 Functional goals

Memorii must:

1. provide distinct memory domains for different kinds of information,
2. support one-to-many routing of a single event,
3. support many-to-one retrieval composition,
4. persist execution state beyond a single run,
5. persist task-local solver state when unresolved,
6. support resuming work later,
7. support state-space search for local subproblems,
8. support task decomposition and dependency tracking,
9. support framework-neutral integration,
10. protect long-term memory from speculative or hallucinated content.

### 4.2 Safety and robustness goals

Memorii must protect against:

1. model guesses being stored as facts,
2. speculative branch state overwriting durable memory,
3. lack of explicit unknown/insufficient-evidence states,
4. repeated actions caused by missing local search memory,
5. mode collapse to a single explanation,
6. prompt-framing bias,
7. graph explosion from trivial node creation,
8. irreversible branch poisoning,
9. inability to resume after process failure,
10. framework coupling.

---

## 5. Non-goals

Memorii will not:

1. replace the host agent harness planner,
2. assume one database backend,
3. force one orchestration pattern,
4. store all reasoning permanently,
5. treat all tasks as state-space search,
6. trust model outputs without validation.

---

## 6. Memory domains

Memorii defines six required first-class memory domains.

### 6.1 Raw Transcript Memory

#### Purpose
Store the raw interaction and evidence trail.

#### Stores
- user messages,
- agent messages,
- tool calls,
- tool results,
- environment snapshots,
- timestamps,
- source references.

#### Ownership
Source of truth for raw conversation and tool/event chronology.

#### Write policy
- append-only or near append-only,
- always store raw inbound and outbound interaction events,
- do not synthesize in place.

#### Read policy
Used for:
- reconstruction,
- audit,
- grounding,
- provenance.

---

### 6.2 Semantic Memory

#### Purpose
Store stable, reusable, generalizable domain knowledge.

#### Stores
- validated domain facts,
- definitions,
- procedures,
- stable abstractions,
- reusable general rules.

#### Ownership
Source of truth for validated general knowledge.

#### Write policy
Only write when all are true:
1. information is generalizable,
2. information is not task-local speculation,
3. information has passed validation and commit checks.

#### Read policy
Used for:
- priors,
- domain guidance,
- grounding hypothesis generation,
- validating decisions.

---

### 6.3 Episodic Memory

#### Purpose
Store synthesized prior cases and analogies.

#### Stores
- case summaries,
- timelines,
- lessons learned,
- prior outcomes,
- reusable analogies,
- prior successful and failed approaches.

#### Ownership
Source of truth for prior case-level memories.

#### Write policy
Write only synthesized summaries, not full raw transcript or speculative branches by default.

#### Read policy
Used for:
- analogy retrieval,
- avoiding repeated mistakes,
- suggesting branches,
- informing decomposition or debugging.

---

### 6.4 User Preference / User Context Memory

#### Purpose
Store durable user-specific facts, preferences, and constraints.

#### Stores
- communication preferences,
- stable risk tolerance,
- durable constraints,
- recurring goals,
- relevant personal context.

#### Ownership
Source of truth for durable user-specific guidance.

#### Write policy
Write conservatively. Do not write temporary context as durable preference.

#### Read policy
Used for:
- personalization,
- choosing explanation style,
- selecting action strategies,
- applying user-specific constraints.

---

### 6.5 Execution Plan Memory

#### Purpose
Store the persistent graph of assigned work.

#### Stores
- mission,
- work items,
- dependencies,
- milestones,
- artifacts,
- interfaces,
- invariants,
- tests,
- decisions,
- blockers,
- defects,
- statuses.

#### Ownership
Source of truth for what work exists and what state it is in.

#### Write policy
Persistent and structured. Used across runs.

#### Read policy
Used by the scheduler/orchestrator to decide what work to do next.

---

### 6.6 Solver / State-Space Search Memory

#### Purpose
Store task-local search state for one execution node or subproblem.

#### Stores
- hypotheses,
- observations,
- actions/tests,
- assumptions,
- justifications,
- branch states,
- frontier,
- revisions,
- reopen conditions,
- unresolved questions.

#### Ownership
Source of truth for active local problem-solving state.

#### Write policy
May persist across runs when unresolved. Should consolidate or archive when resolved.

#### Read policy
Used by solver capability engines during debugging, diagnosis, investigation, local design exploration, and similar search-heavy tasks.

---

## 7. Memory object model

All stores must operate on a common logical object model.

### 7.1 Base MemoryObject schema

```json
{
  "memory_id": "string",
  "memory_type": "enum(transcript|semantic|episodic|user|execution|solver)",
  "scope": "enum(global|user|task|execution_node|step)",
  "durability": "enum(ephemeral|session|task_persistent|long_term)",
  "status": "enum(candidate|committed|archived)",
  "content": {},
  "provenance": {
    "source_type": "enum(user|agent|tool|environment|system|derived)",
    "source_refs": ["string"],
    "created_at": "timestamp",
    "created_by": "string"
  },
  "routing": {
    "primary_store": "string",
    "secondary_stores": ["string"]
  }
}
```

### 7.2 Required semantics

- `memory_type` determines logical domain.
- `scope` determines how broadly the object applies.
- `durability` determines retention and resume behavior.
- `status` controls candidate vs committed vs archived lifecycle.
- `provenance` is mandatory for all committed objects.

---

## 8. Scope and durability rules

### 8.1 Scope values

- `global`: general knowledge usable across users and tasks.
- `user`: user-specific memory.
- `task`: applies to a whole task or mission.
- `execution_node`: applies to one execution graph node.
- `step`: applies only to a single runtime step.

### 8.2 Durability values

- `ephemeral`: may be discarded after immediate use.
- `session`: persists through one interactive session.
- `task_persistent`: persists until task completion or archival.
- `long_term`: persists across tasks.

### 8.3 Required defaults

- transcript objects: `task` or `step`, `session` or `task_persistent`
- semantic objects: `global`, `long_term`
- episodic objects: `task` or `execution_node`, `long_term`
- user objects: `user`, `long_term`
- execution objects: `task`, `task_persistent`
- solver objects: `execution_node`, `task_persistent` when unresolved

---

## 9. Memory router

The Memory Router is the harness component that determines where new information should be stored.

### 9.1 Responsibilities

For every event, the router must decide:
1. what logical memory object(s) to create,
2. which memory domain(s) receive them,
3. whether the object is candidate or committed,
4. whether the object should persist,
5. whether one event must be written to multiple stores.

### 9.2 Inputs

The router receives:
- event type,
- event payload,
- task context,
- current execution node,
- current solver context if any,
- model confidence/validation status if derived,
- write policy.

### 9.3 Outputs

The router outputs one or more MemoryObjects and their destinations.

### 9.4 Routing rules

#### 9.4.1 User message
Always write to transcript memory.

Additionally:
- if a stable preference is detected, create a **candidate** user-memory object,
- if the message creates a task constraint, write an execution-memory update or solver observation as appropriate.

#### 9.4.2 Tool result
Always write to transcript memory.

Additionally:
- if it changes task status, update execution plan memory,
- if it serves as evidence in a local search, write an observation into solver memory.

#### 9.4.3 Completed solver run
Write:
- solver graph resolution,
- execution node update,
- episodic summary candidate,
- optional skill or semantic candidates if validated.

#### 9.4.4 Validated general abstraction
Write to semantic memory only after validation.

### 9.5 One-to-many routing

The router must support writing one event to multiple memories.

Example: a failed integration test may produce:
- transcript record,
- execution test-node failure,
- solver observation,
- episodic candidate after resolution.

---

## 10. Retrieval planner

The Retrieval Planner determines which memory domains should be queried for the current step.

### 10.1 Responsibilities

For a given task step, the retrieval planner must choose:
- which memory domains to query,
- how much context to retrieve,
- whether retrieval should be local, cross-task, or long-term.

### 10.2 Inputs

- current task context,
- current execution node,
- current solver graph state if any,
- retrieval intent,
- active constraints.

### 10.3 Outputs

A set of retrieval queries by memory domain.

### 10.4 Required retrieval intents

- `continue_execution`
- `debug_local_failure`
- `make_decision`
- `answer_user_query`
- `resume_task`
- `consolidate_task`

### 10.5 Retrieval policy examples

#### Continue execution
Query:
- execution plan memory,
- linked artifacts,
- relevant user constraints.

#### Debug local failure
Query:
- solver graph for this execution node,
- recent transcript evidence,
- episodic analogies,
- semantic troubleshooting facts.

#### Answer user query
Query:
- transcript,
- semantic memory,
- user memory,
- possibly episodic analogies.

---

## 11. Memory directory

The Memory Directory is the index of memory assets.

### 11.1 Responsibilities

Track mappings such as:
- task id -> execution graph id,
- execution node id -> attached solver graph ids,
- thread id -> transcript partition,
- user id -> user-memory profile,
- case id -> episodic entries,
- artifact id -> environment references.

### 11.2 Requirement

No retrieval or persistence flow may assume direct store knowledge without going through the directory or an equivalent registry abstraction.

---

## 12. Consolidator

The Consolidator converts transient task-local state into durable long-term memory outputs.

### 12.1 Inputs

- completed or paused solver graphs,
- completed tasks,
- execution graph snapshots,
- transcript slices,
- validation outcomes.

### 12.2 Outputs

- episodic summaries,
- skill candidates,
- semantic candidates,
- archive packages,
- unresolved follow-up summaries.

### 12.3 Rules

- do not write speculative hypotheses directly into semantic memory,
- do not write temporary branch beliefs into user memory,
- do not store full raw graphs in long-term memory by default,
- keep provenance links back to original task and graph ids.

---

## 13. Execution Graph

The Execution Graph is the top-level persistent representation of assigned work.

### 13.1 Definition

A persistent typed graph representing the decomposition of assigned work into executable units, their dependencies, constraints, artifacts, invariants, verification requirements, and lifecycle state.

### 13.2 Required node types

- `MISSION`
- `WORK_ITEM`
- `COMPONENT`
- `INTERFACE`
- `INVARIANT`
- `TEST_SUITE`
- `TEST_CASE`
- `ARTIFACT`
- `DECISION`
- `RISK`
- `QUESTION`
- `DEFECT`
- `MILESTONE`
- `CONSTRAINT`

### 13.3 Required edge types

- `DECOMPOSES_INTO`
- `DEPENDS_ON`
- `BLOCKS`
- `IMPLEMENTS`
- `VERIFIED_BY`
- `PRODUCES`
- `CONSUMES`
- `REQUIRES`
- `CONSTRAINED_BY`
- `SUPERSEDES`
- `RAISES`
- `RESOLVES`
- `AFFECTS`

### 13.4 Node status model

Each execution node must have a runtime status.

Required statuses:
- `NOT_STARTED`
- `READY`
- `RUNNING`
- `WAITING`
- `BLOCKED`
- `FAILED`
- `DONE`
- `ARCHIVED`

### 13.5 Required fields for execution nodes

```json
{
  "id": "string",
  "type": "enum",
  "title": "string",
  "description": "string",
  "status": "enum",
  "acceptance_criteria": ["string"],
  "linked_artifacts": ["string"],
  "linked_constraints": ["string"],
  "owner": "string|null",
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

### 13.6 Invariants and tests

Each component or work item may link to:
- one or more `INVARIANT` nodes,
- one or more `TEST_CASE` or `TEST_SUITE` nodes.

This makes correctness explicit and provides hooks for later solver invocations.

---

## 14. Capability engines

Capability Engines are reusable problem-solving modules that operate on execution nodes.

### 14.1 Requirement

The harness must not treat all work as state-space search.

### 14.2 Required capability engines in v1 architecture

#### 14.2.1 Decomposition Engine
Purpose:
- break a mission or work item into child work items, components, interfaces, invariants, dependencies, and tests.

Outputs:
- execution graph mutations only.

#### 14.2.2 Dependency / Impact Analysis Engine
Purpose:
- identify dependencies, blockers, propagation, and likely blast radius.

Outputs:
- execution graph edges and risk annotations.

#### 14.2.3 Decision Engine
Purpose:
- compare alternatives under constraints and choose or defer a decision.

Outputs:
- decision nodes,
- rationale,
- reopen conditions.

#### 14.2.4 State-Space Search Engine
Purpose:
- solve local search-heavy subproblems such as debugging, diagnosis, and local design search.

Outputs:
- solver graph mutations,
- final resolution candidates,
- execution graph writebacks.

#### 14.2.5 Plan Repair Engine
Purpose:
- revise the execution graph when tasks fail, dependencies change, or environment facts change.

Outputs:
- execution node status changes,
- dependency changes,
- reopened or blocked work items.

### 14.3 Capability engine lifecycle

A capability engine:
1. is invoked for an execution node,
2. may create or resume a solver graph,
3. produces outputs and writebacks,
4. updates execution graph state,
5. may persist internal state for later resume.

---

## 15. Solver Graphs

A Solver Graph is a task-local graph instantiated by a capability engine to solve or analyze one execution node or one local subproblem.

### 15.1 Requirement

Solver graphs are separate from the execution graph.

### 15.2 Relationship to execution graph

Each solver graph must be attached to exactly one of:
- a `WORK_ITEM`,
- a `TEST_CASE`,
- a `DEFECT`,
- a `DECISION`,
- a `QUESTION`.

A single execution node may have zero or more solver graphs over time.

### 15.3 Solver graph categories

v1 requires at least:
- `STATE_SPACE_SEARCH`
- `DECISION_ANALYSIS`
- `DECOMPOSITION_SESSION`

This specification fully details `STATE_SPACE_SEARCH` below.

---

## 16. State-Space Search Memory Module

This section incorporates the earlier detailed specification and must not be omitted.

### 16.1 Purpose

Represent active local reasoning for debugging, diagnosis, investigation, local design search, or similar search-heavy work.

### 16.2 Core design principles

1. execution is iterative, memory is graph-structured,
2. the model proposes, the runtime validates and commits,
3. observations are grounded, hypotheses are provisional,
4. backtracking is revision, not deletion,
5. candidate and committed state are separate,
6. unknown/insufficient-evidence must be first-class states,
7. most updates are local.

### 16.3 Graph type

The solver graph is a typed property graph.

The overall solver graph is **not globally required to be acyclic**.

#### 16.3.1 Acyclicity rules

Must be acyclic for structural edge types:
- `REFINES`
- `DERIVED_FROM`
- `DEPENDS_ON`
- `DECOMPOSES_INTO`

May be cyclic for associative/revision edge types:
- `EQUIVALENT_TO`
- `SIMILAR_TO`
- `REOPENS`
- `RELATED_TO`

### 16.4 Required node types

- `GOAL`
- `HYPOTHESIS`
- `COMPOSITE_HYPOTHESIS`
- `EXPLANATION_FACTOR`
- `OBSERVATION`
- `ACTION`
- `ASSUMPTION`
- `CONSTRAINT`
- `SCENARIO`
- `QUESTION`
- `SEMANTIC_REF`
- `EPISODIC_REF`
- `USER_REF`
- `ENVIRONMENT_REF`
- `SKILL_REF`
- `SYNTHESIS`

### 16.5 Base node schema

```json
{
  "id": "string",
  "type": "enum",
  "content": {},
  "metadata": {
    "created_at": "timestamp",
    "created_by": "enum(model|tool|user|system)",
    "origin_perspective": "string|null",
    "candidate_state": "enum(candidate|committed)",
    "source_refs": ["string"],
    "tags": ["string"]
  }
}
```

### 16.6 Required edge types

- `HAS_GOAL`
- `SUPPORTS`
- `CONTRADICTS`
- `TESTED_BY`
- `PRODUCES`
- `REFINES`
- `DEPENDS_ON`
- `CONTRIBUTES_TO`
- `SYNTHESIZES_FROM`
- `VALID_UNDER`
- `BLOCKS`
- `RESOLVES`
- `DERIVED_FROM`
- `REFERENCES`
- `REOPENS`
- `EQUIVALENT_TO`

### 16.7 Base edge schema

```json
{
  "id": "string",
  "src": "node_id",
  "dst": "node_id",
  "type": "enum",
  "weight": "float|null",
  "metadata": {
    "created_at": "timestamp",
    "created_by": "enum(model|tool|user|system)",
    "origin_perspective": "string|null",
    "candidate_state": "enum(candidate|committed)",
    "confidence_class": "enum(observed|inferred|speculative|retracted)",
    "source_refs": ["string"],
    "assumption_refs": ["node_id"]
  }
}
```

### 16.8 Candidate vs committed separation

#### Candidate state
Represents:
- model proposals,
- speculative hypotheses,
- low-confidence edges,
- tentative branch suggestions.

Candidate state may not:
- strongly falsify committed branches,
- write to semantic memory,
- overwrite execution truth,
- trigger destructive actions.

#### Committed state
Represents:
- grounded observations,
- validated structural relations,
- accepted hypotheses,
- operationally trusted search state.

### 16.9 Belief overlay

Beliefs must not be stored directly in the structural graph.

#### 16.9.1 Belief overlay schema

```json
{
  "version_id": "string",
  "node_id": "string",
  "belief": "float",
  "status": "enum",
  "frontier_priority": "float|null",
  "active_justification_ids": ["string"],
  "inactive_justification_ids": ["string"],
  "last_updated_at": "timestamp"
}
```

### 16.10 Required node statuses

- `ACTIVE`
- `PROMISING`
- `WEAKENED`
- `DOMINATED`
- `SUSPENDED`
- `FALSIFIED_UNDER_ASSUMPTIONS`
- `REOPENABLE`
- `RESOLVED`
- `MERGED`
- `ARCHIVED`
- `INSUFFICIENT_EVIDENCE`
- `NEEDS_TEST`
- `MULTIPLE_PLAUSIBLE_OPTIONS`

The last three are required to represent abstention and unresolved branches explicitly.

### 16.11 Justifications

Belief changes must use justifications.

```json
{
  "id": "string",
  "conclusion_node_id": "string",
  "supporting_node_ids": ["string"],
  "contradicting_node_ids": ["string"],
  "assumption_node_ids": ["string"],
  "strength": "float",
  "active": "boolean",
  "created_at": "timestamp"
}
```

### 16.12 Perspective-aware proposal generation

The proposal engine must support multiple perspectives.

Required configurable perspectives:
- `domain_expert`
- `safety`
- `practical`
- `outside_view`

Every proposal must record originating perspective.

### 16.13 Controller framework

Use one general learned controller framework, not separate hand-coded domain controllers.

#### 16.13.1 Generic controller actions
- `PROPOSE_HYPOTHESES`
- `PROPOSE_ACTIONS`
- `ATTACH_EDGES`
- `UPDATE_BELIEFS`
- `EXPAND_NODE`
- `SUSPEND_NODE`
- `REOPEN_NODE`
- `SYNTHESIZE_NODES`
- `MERGE_NODES`
- `ASK_QUESTION`
- `TERMINATE_WITH_RESOLUTION`

### 16.14 Observation handling

Every real result must be materialized as an `OBSERVATION` node.

Tool- or user-grounded observations are committed with `confidence_class=observed`.
Model-inferred summaries remain candidate until grounded.

### 16.15 Step execution algorithm

Each search cycle must execute in this order:

1. select frontier focus,
2. generate proposals,
3. validate proposals,
4. execute selected action if applicable,
5. materialize resulting observation,
6. attach local edges,
7. update justifications and beliefs,
8. decide whether to create a new node,
9. update frontier,
10. emit event log entries.

### 16.16 Node creation rules

#### Always create
- `OBSERVATION` for every real result,
- `ACTION` for every nontrivial action/test.

#### Create a new `HYPOTHESIS` only if at least one is true
1. novel explanatory content,
2. action distinction,
3. structural distinction,
4. reuse value.

#### Create `REFINED_HYPOTHESIS` only if all are true
1. materially narrows parent,
2. changes next action/test,
3. parent is too broad operationally.

#### Create `COMPOSITE_HYPOTHESIS` only if all are true
1. at least two factors or hypotheses jointly explain evidence,
2. combined explanation has materially better coverage,
3. combined explanation changes action plan or explanation materially.

#### Never create nodes for
- trivial paraphrases,
- confidence-only restatements,
- wording variants with no action impact,
- duplicate content.

### 16.17 Edge creation rules

- edge proposal must be local,
- do not force edges to all nearby nodes,
- speculative edges may not strongly falsify branches.

### 16.18 Belief update algorithm

Belief updates must be incremental and local.

Trigger on:
- new observation,
- node commit,
- edge commit,
- justification invalidation,
- reopen,
- assumption invalidation.

Affected neighborhood includes:
- directly linked nodes,
- dependent nodes,
- composite hypotheses,
- nodes whose justifications mention changed nodes.

The runtime may use deterministic heuristic score propagation in v1.

### 16.19 Hard falsification rule

A node may move to `FALSIFIED_UNDER_ASSUMPTIONS` only if all are true:
1. active contradiction path exists,
2. contradiction includes at least one grounded observation,
3. assumptions are explicit,
4. no stronger unresolved support path overrides it.

Otherwise mark `WEAKENED` or `SUSPENDED`.

### 16.20 Residual unexplained evidence

Every observation must have coverage status:
- `well_explained`
- `weakly_explained`
- `unexplained`
- `conflicted`

If unexplained/conflicted observations exceed threshold, the controller must allocate budget to:
- new hypotheses,
- reopen old branches,
- outside-view proposals.

### 16.21 Multi-cause explanation model

Support multi-cause explanations with:
- `EXPLANATION_FACTOR`
- `HYPOTHESIS`
- `COMPOSITE_HYPOTHESIS`

Do not enumerate all combinations.
Create composite hypotheses sparsely and only when evidence or residual coverage justifies them.

### 16.22 Constructive synthesis

Constructive synthesis creates a new node that combines useful elements of multiple non-equivalent branches.

Use edge type:
- `SYNTHESIZES_FROM`

This is separate from deduplication.

### 16.23 Backtracking and undo

Backtracking must be revision, not deletion.

Use immutable event log plus compensating events.

Undo means:
- append compensating events,
- deactivate justifications,
- recompute affected neighborhood,
- restore eligible nodes to frontier.

### 16.24 Duplication and merge handling

Merge semantic duplicates only if:
1. content similarity above threshold,
2. action implications substantially the same,
3. no conflicting evidence structure,
4. consistency validation passes.

### 16.25 Protections against wrong model proposals

Required protections:
- proposal-only model role,
- diversity requirement,
- edge strength gating,
- candidate layer,
- exploration budget for dissenting branches,
- explicit unknown-cause mass or equivalent residual policy.

### 16.26 Prompt augmentation and abstention requirements

The solver prompt must not force binary answers when evidence is insufficient.

Allowed decision labels must include:
- `SUPPORTED`
- `REFUTED`
- `INSUFFICIENT_EVIDENCE`
- `NEEDS_TEST`
- `MULTIPLE_PLAUSIBLE_OPTIONS`

Required prompt rules:
1. use only provided evidence and allowed deterministic transformations,
2. do not guess,
3. prefer `INSUFFICIENT_EVIDENCE` or `NEEDS_TEST` over unsupported commitment,
4. `SUPPORTED` and `REFUTED` require evidence ids,
5. unresolved results must list missing evidence and best next test.

Required output contract:

```json
{
  "decision": "SUPPORTED|REFUTED|INSUFFICIENT_EVIDENCE|NEEDS_TEST|MULTIPLE_PLAUSIBLE_OPTIONS",
  "evidence_ids": ["string"],
  "missing_evidence": ["string"],
  "next_best_test": "string|null",
  "rationale_short": "string",
  "confidence_band": "low|medium|high"
}
```

### 16.27 Verification of model compliance

Do not trust self-reported compliance.

Every solver output must pass:
1. schema validation,
2. evidence-id presence validation,
3. evidence coverage checks,
4. entailment-style validation where applicable,
5. optional cross-sample consistency checks for high-stakes cases.

If validation fails:
- keep output as candidate only,
- or downgrade to `INSUFFICIENT_EVIDENCE`,
- or request regeneration.

Only validated outputs may mutate committed solver state or durable memories.

### 16.28 Parameter-search special policy

For exact parameter-set questions, the solver must use stricter labels:
- `PROVEN_WORKS`
- `PROVEN_FAILS`
- `UNTESTED_PLAUSIBLE`
- `INSUFFICIENT_INFORMATION`
- `NEEDS_EXPERIMENT`

`PROVEN_WORKS` and `PROVEN_FAILS` may only be returned when backed by direct evidence or deterministic rules.

---

## 17. Persistence and resume

Memorii must support persistence beyond one agent run.

### 17.1 Persistence requirements

#### 17.1.1 Execution graph durability
Every task must have durable:
- structural execution graph,
- node statuses,
- linked artifacts,
- dependency edges,
- version history.

#### 17.1.2 Solver graph durability
Every unresolved solver graph must have durable:
- structural graph,
- belief overlay,
- event log,
- frontier state,
- unresolved questions,
- active candidate state.

### 17.2 Resume requirements

On resume, the runtime must be able to restore:
- task context,
- execution graph,
- current execution-node status,
- attached solver graphs,
- latest solver belief overlay,
- frontier,
- unexplained observations,
- reopenable branches.

### 17.3 Run independence

A persisted graph must not be tied to one process or one runtime instance.
Any compatible host adapter must be able to load by id and continue.

### 17.4 Checkpointing

Support:
- explicit checkpoints,
- periodic checkpoints,
- crash-safe recovery.

### 17.5 Retention states

Every persisted graph or memory partition should support:
- `HOT`
- `WARM`
- `COLD`
- `ARCHIVED`

### 17.6 Staleness handling

On resume after elapsed time, the runtime must:
1. reload graph state,
2. refresh environment references where needed,
3. revalidate stale assumptions,
4. continue from restored frontier.

---

## 18. Event log

Memorii uses immutable event sourcing for revision and audit.

### 18.1 Required event types

- `TASK_STARTED`
- `TASK_RESUMED`
- `TASK_PAUSED`
- `TASK_COMPLETED`
- `TASK_ABORTED`
- `NODE_ADDED`
- `EDGE_ADDED`
- `NODE_COMMITTED`
- `EDGE_COMMITTED`
- `BELIEF_UPDATED`
- `STATUS_UPDATED`
- `NODE_REOPENED`
- `NODE_MERGED`
- `JUSTIFICATION_INVALIDATED`
- `SOLVER_STARTED`
- `SOLVER_RESOLVED`
- `OBSERVATION_RECEIVED`
- `ACTION_SELECTED`
- `ACTION_COMPLETED`

### 18.2 Event requirements

Each event must have:
- stable id,
- timestamp,
- task id,
- optional execution node id,
- optional solver graph id,
- actor id or source,
- payload,
- dedupe key.

### 18.3 Idempotency

Repeated events from host retries must not create duplicate committed state.

---

## 19. Framework-neutral integration model

Memorii must be framework-agnostic.

### 19.1 Integration boundary

Host harness owns:
- session lifecycle,
- user interaction,
- tool execution,
- model invocation,
- harness-native state.

Memorii owns:
- memory domain classification,
- execution graph state,
- solver graph state,
- routing,
- retrieval planning,
- consolidation,
- memory writeback candidates.

### 19.2 Supported integration modes

- `advisory`: host keeps own planner, Memorii advises,
- `memory-owned reasoning`: host uses Memorii for execution and solver memory,
- `hybrid`: host planner stays primary, Memorii handles memory, resume, and solver attachments.

Hybrid is required for initial compatibility.

---

## 20. Canonical adapter contracts

### 20.1 Host-to-Memorii events

Every adapter must be able to send:
- `TASK_STARTED`
- `TASK_RESUMED`
- `USER_MESSAGE_RECEIVED`
- `MODEL_PROPOSAL_GENERATED`
- `ACTION_SELECTED`
- `ACTION_COMPLETED`
- `TOOL_RESULT_RECEIVED`
- `OBSERVATION_RECEIVED`
- `TASK_PAUSED`
- `TASK_COMPLETED`
- `TASK_ABORTED`

### 20.2 Memorii-to-host outputs

Memorii must be able to return:
- `FRONTIER_RECOMMENDATION`
- `CANDIDATE_HYPOTHESES`
- `CANDIDATE_ACTIONS`
- `CANDIDATE_EDGE_ATTACHMENTS`
- `BELIEF_UPDATE_SUMMARY`
- `REVISION_REQUEST`
- `REOPEN_SUGGESTION`
- `RESIDUAL_UNEXPLAINED_SUMMARY`
- `CONSOLIDATION_RESULT`
- `WRITEBACK_CANDIDATES`

### 20.3 Canonical task payloads

#### TaskContext

```json
{
  "task_id": "string",
  "session_id": "string",
  "thread_id": "string|null",
  "goal": "string",
  "framework_name": "string",
  "framework_run_id": "string",
  "metadata": {}
}
```

#### ModelProposalPayload

```json
{
  "task_id": "string",
  "step_id": "string",
  "perspective": "string|null",
  "proposal_type": "enum(hypothesis|action|edge|refinement|composite|synthesis)",
  "content": {},
  "source_message_ids": ["string"],
  "source_node_ids": ["string"]
}
```

#### ActionExecutionPayload

```json
{
  "task_id": "string",
  "step_id": "string",
  "action_id": "string",
  "action_type": "string",
  "input_ref": "string|null",
  "status": "enum(started|completed|failed)",
  "result_ref": "string|null",
  "metadata": {}
}
```

#### ObservationPayload

```json
{
  "task_id": "string",
  "step_id": "string",
  "observation_id": "string",
  "source_type": "enum(user|tool|model|environment|retrieval|system)",
  "summary": "string",
  "raw_ref": "string|null",
  "timestamp": "timestamp|null",
  "metadata": {}
}
```

---

## 21. Memory provider interface

To stay compatible with different frameworks, Memorii must consume other memory sources through a provider interface.

### 21.1 Required read methods

- `get_semantic_refs(task_context, query)`
- `get_episodic_refs(task_context, query)`
- `get_user_refs(task_context, query)`
- `get_skill_refs(task_context, query)`
- `get_environment_refs(task_context, query)`

### 21.2 Required writeback categories

Memorii must emit writeback candidates in normalized form:
- `episodic_writebacks[]`
- `user_writebacks[]`
- `skill_writebacks[]`
- `semantic_writebacks[]`

The host adapter decides whether to persist them.

---

## 22. Framework adapter requirements

Memorii must ship first-party adapters or clearly documented adapter contracts for common frameworks.

### 22.1 Adapter responsibilities

Each adapter must:
1. map harness-native ids to Memorii ids,
2. translate tool and model events into canonical payloads,
3. route transcript and tool results into Memorii,
4. expose Memorii retrievals or recommendations back to the harness,
5. preserve idempotency,
6. not bypass Memorii validation rules.

### 22.2 Adapters to support

At minimum define adapter contracts for:
- OpenClaw,
- Hermes,
- LangGraph,
- AutoGen,
- OpenAI Agents.

### 22.3 Adapter prohibition

Adapters must not:
- mutate graph storage directly,
- bypass candidate/committed rules,
- write directly into belief overlays,
- skip provenance.

---

## 23. APIs

### 23.1 Core APIs

- `create_task_graph(goal_spec)`
- `resume_task_graph(task_id)`
- `add_memory_object(memory_object)`
- `route_event(event, context)`
- `retrieve_context(intent, context)`
- `add_candidate_node(node_spec)`
- `commit_node(node_id)`
- `add_candidate_edge(edge_spec)`
- `commit_edge(edge_id)`
- `add_observation(observation_spec)`
- `update_belief(node_id, new_value, justification_ids)`
- `update_status(node_id, new_status, reason)`
- `reopen_node(node_id, reason_refs)`
- `merge_nodes(source_id, target_id, reason)`
- `get_local_neighborhood(node_ids, depth)`
- `get_frontier(task_id, solver_id)`
- `start_solver(execution_node_id, solver_type)`
- `resume_solver(solver_id)`
- `consolidate_task_graph(task_id)`
- `consolidate_solver_graph(solver_id)`

### 23.2 Lifecycle hooks

- `on_task_started(task_context)`
- `on_message_received(task_id, message_payload)`
- `on_model_proposals(task_id, proposals[])`
- `on_action_selected(task_id, action_payload)`
- `on_action_result(task_id, observation_payload)`
- `on_task_completed(task_id, completion_payload)`

---

## 24. Runtime loops

### 24.1 Execution loop

1. load or create task graph,
2. retrieve current execution state,
3. choose next ready execution node,
4. determine whether direct execution or capability engine invocation is needed,
5. run chosen engine or action,
6. route outputs into memory plane,
7. update execution graph state,
8. checkpoint.

### 24.2 Solver loop

1. load solver graph and local context,
2. retrieve typed memory based on solver intent,
3. choose frontier node,
4. generate candidate updates with perspective-aware prompting,
5. validate structured output,
6. execute test/action or attach candidate state,
7. commit grounded observations,
8. update beliefs locally,
9. update frontier and statuses,
10. checkpoint.

---

## 25. Failure modes and protections

### 25.1 Wrong model proposal
Protection:
- candidate vs committed separation,
- validation before commit,
- diversity requirement,
- residual unexplained evidence tracking.

### 25.2 LLM refuses to say unknown
Protection:
- explicit abstention states,
- structured solver output contract,
- prompt rules preferring insufficient evidence over guessing,
- verifier pipeline.

### 25.3 Model claims unsupported certainty
Protection:
- evidence-bound outputs,
- evidence-id validation,
- entailment verification,
- candidate-only downgrade on failure.

### 25.4 Premature branch death
Protection:
- hard falsification gating,
- weakened/suspended states,
- reopen support.

### 25.5 Prompt framing bias
Protection:
- perspective-aware proposal generation,
- disagreement-aware handling,
- graph-level resolution instead of single-role final answer.

### 25.6 Graph explosion
Protection:
- strict node creation rules,
- local edge creation,
- duplicate detection,
- consolidation and archival.

### 25.7 Mixing task execution with solver state
Protection:
- separate execution graph and solver graph data models,
- explicit attachments instead of one giant graph.

### 25.8 Long-term memory pollution
Protection:
- ownership boundaries,
- writeback candidates instead of direct durable writes,
- semantic and user-memory high write bars.

### 25.9 Duplicate events from adapters
Protection:
- idempotent event ids,
- dedupe keys,
- append-only event processing.

### 25.10 Stale resume state
Protection:
- checkpoint timestamps,
- staleness handling on resume,
- assumption revalidation,
- environment ref refresh.

---

## 26. Storage and packaging

### 26.1 Storage requirements

The logical architecture must not assume one backend.

Required logical stores:
- transcript store,
- semantic store,
- episodic store,
- user store,
- execution graph store,
- solver graph store,
- event log store,
- directory/index store.

### 26.2 Packaging modes

Memorii must support:
- sidecar service mode,
- embedded library mode,
- event-bus consumer mode.

### 26.3 SDK requirements

Provide:
- Python SDK,
- TypeScript SDK,
- HTTP or gRPC API.

---

## 27. Acceptance criteria

### 27.1 Memory-plane criteria

- one event can be routed to multiple memory domains,
- retrieval planner can query memory domains selectively,
- memory directory resolves task-to-graph relationships.

### 27.2 Execution criteria

- execution graph can represent missions, work items, dependencies, invariants, tests, and blockers,
- task state persists across runs,
- task can resume after reload.

### 27.3 Solver criteria

- solver graph can represent at least three competing hypotheses,
- one observation can support one hypothesis and contradict another,
- refined hypotheses and composite hypotheses are supported,
- backtracking does not delete history,
- unresolved branches can remain explicit.

### 27.4 Abstention criteria

- solver can emit `INSUFFICIENT_EVIDENCE` or `NEEDS_TEST`,
- schema validator rejects malformed outputs,
- evidence validator rejects unsupported commits,
- unsupported solver output does not mutate committed durable state.

### 27.5 Persistence criteria

- execution graph persists,
- unresolved solver graph persists,
- checkpoint reload restores frontier and unresolved state,
- stale assumptions can be revalidated.

### 27.6 Adapter criteria

- core can operate without importing host framework packages,
- duplicate adapter events do not create duplicate committed state,
- at least two adapters can be built without modifying core logic.

---

## 28. Implementation guidance for junior developers

1. Do not store beliefs on structural nodes. Use overlays.
2. Do not delete nodes during backtracking. Use events and status changes.
3. Do not write model guesses directly into semantic or user memory.
4. Do not merge execution graph and solver graph into one generic graph.
5. Do not allow speculative edges to falsify committed branches.
6. Do not trust LLM self-reports of compliance.
7. Do not skip provenance on committed state.
8. Do not store all raw solver history in long-term memory by default.
9. Do not assume a single framework runtime model.
10. Do not assume one answer is required; unresolved is a valid state.

---

## 29. Summary

Memorii is a framework-neutral memory plane for agents with:

- typed memory domains,
- a router,
- a retrieval planner,
- a memory directory,
- a consolidator,
- a persistent execution graph,
- attached solver graphs,
- a detailed state-space search memory module,
- persistence and resume,
- abstention-aware prompting and verification,
- and adapter contracts for common harnesses.

The central architectural principle is:

- **Execution Graph** tracks what work exists and how it progresses.
- **Solver Graphs** track local reasoning needed to complete a particular execution node.
- **The Memory Plane** decides what to store, where to store it, how to retrieve it, and when to consolidate it.

