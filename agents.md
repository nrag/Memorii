# AGENTS.md
## Project identity
Memorii is a framework-neutral memory plane for agents.
Memorii is **not**:
- a single vector memory store
- a generic chat history wrapper
- a replacement for an agent harness
- a single graph for everything
Memorii **is**:
- a typed multi-memory system
- a routing and retrieval layer across memory domains
- a persistent execution memory plus solver/search memory architecture
- a framework-neutral service with adapters for agent harnesses
Before making any changes, read:
1. `docs/memorii_spec.md`
2. `docs/implementation_rules.md`
3. `PLANS.md`
If these files disagree, use this priority:
1. `docs/memorii_spec.md`
2. `docs/implementation_rules.md`
3. `AGENTS.md`
4. `PLANS.md`
---
## Non-negotiable architecture rules
Do not redesign the system.
Do not collapse multiple memory domains into one generic store.
Do not remove:
- candidate vs committed state
- event-sourced history
- versioned belief/status overlays
- execution graph vs solver graph separation
- explicit memory routing
- retrieval planning
- consolidation and writeback gating
- framework-neutral adapters
Do not:
- store beliefs directly on structural graph nodes
- write speculative content into semantic or user memory
- let adapters bypass validators
- let model output directly mutate committed state
- replace explicit typed schemas with untyped dict blobs
- couple core logic to a specific framework like OpenClaw, Hermes, LangGraph, AutoGen, or OpenAI Agents
Unknown and insufficient evidence are valid states.
The system must never require the model to guess.
---
## Language and runtime
Primary language: Python 3.11+
Use:
- Python type hints everywhere
- `pydantic` models for schemas and API contracts
- `dataclasses` only for small internal immutable helpers when appropriate
- `pytest` for tests
- explicit interfaces / protocols for pluggable components
Avoid:
- hidden dynamic typing
- passing around raw nested dictionaries as core domain objects
- magic global registries
- framework-heavy base classes unless justified
- metaclass-heavy abstractions
- implicit serialization behavior
All core objects must be JSON serializable or have an explicit serialization adapter.
---
## Required memory domains
Memorii must support these first-class memory domains:
1. Raw Transcript Memory
2. Semantic Memory
3. Episodic Memory
4. User Preference / User Context Memory
5. Execution Plan Memory
6. Solver / State-Space Search Memory
These are separate logical domains even if some share physical storage backends.
Do not merge them conceptually.
---
## Core system model
The architecture has these major parts:
### 1. Memory Plane
The top-level memory operating model across domains.
### 2. Memory Router
Classifies events into memory objects and routes them to one or more memory domains.
### 3. Retrieval Planner
Selects which memory domains to query for a given step.
### 4. Memory Directory
Maps relationships across memories, tasks, execution nodes, solver runs, and references.
### 5. Consolidator
Compresses task-local or solver-local state into episodic, semantic, user, or skill writeback candidates.
### 6. Execution Graph
Persistent graph of work, dependencies, invariants, artifacts, tests, decisions, and statuses.
### 7. Solver Graph
Task-local reasoning/search graph attached to an execution node or subproblem when deeper reasoning is needed.
### 8. Event Log
Immutable event history for all structural and belief/status changes.
### 9. Belief / Status Overlay
Versioned task-local overlay storing dynamic reasoning state.
### 10. Adapter Layer
Framework-specific integrations built on canonical Memorii contracts.
---
## Core architectural distinctions
### Execution Graph
This is the graph of work to be done.
It tracks:
- missions
- work items
- components
- interfaces
- invariants
- tests
- artifacts
- milestones
- blockers
- dependencies
- decisions
- defects
- statuses
It is persistent and resumable across runs.
### Solver Graph
This is one capability used to solve a local subproblem.
It tracks:
- hypotheses
- observations
- actions
- assumptions
- constraints
- justifications
- belief/status state
- active frontier
- revisions
- reopen conditions
- unresolved questions
It is local to an execution node or subproblem.
### Memory Router
This decides where a new memory object belongs.
One event may write to multiple memory domains.
### Retrieval Planner
This chooses which memory domains are relevant for the current step.
Retrieval must be typed and intentional.
---
## Python package structure
Use this exact package layout unless explicitly instructed otherwise:
```text
memorii/
  memorii/
    __init__.py
    domain/
      __init__.py
      ids.py
      enums.py
      common.py
      memory_object.py
      transcript.py
      semantic.py
      episodic.py
      user_memory.py
      execution_graph/
        __init__.py
        nodes.py
        edges.py
        events.py
        state.py
      solver_graph/
        __init__.py
        nodes.py
        edges.py
        justifications.py
        overlays.py
        events.py
        decisions.py
      adapters/
        __init__.py
        contracts.py
        events.py
        memory_provider.py
        writebacks.py
    core/
      __init__.py
      router/
        __init__.py
        classifier.py
        routing_policy.py
        router.py
      retrieval/
        __init__.py
        intents.py
        planner.py
        query_plans.py
      consolidation/
        __init__.py
        consolidator.py
        policies.py
      directory/
        __init__.py
        directory.py
        indexes.py
      validation/
        __init__.py
        schemas.py
        candidate_commit.py
        provenance.py
        invariants.py
      execution/
        __init__.py
        service.py
        state_machine.py
      solver/
        __init__.py
        service.py
        update_engine.py
        verifier.py
        abstention.py
    stores/
      __init__.py
      base/
        __init__.py
        interfaces.py
      transcript/
        __init__.py
        store.py
      semantic/
        __init__.py
        store.py
      episodic/
        __init__.py
        store.py
      user/
        __init__.py
        store.py
      execution_graph/
        __init__.py
        store.py
      solver_graph/
        __init__.py
        store.py
      event_log/
        __init__.py
        store.py
      overlays/
        __init__.py
        store.py
    api/
      __init__.py
      models.py
      service.py
    sdk/
      __init__.py
      python_client.py
    utils/
      __init__.py
      time.py
      json.py
      hashing.py
  tests/
    unit/
    integration/
    conformance/
    replay/
    adapters/
  docs/
    memorii_spec.md
    implementation_rules.md
  PLANS.md
  AGENTS.md
  pyproject.toml
  README.md

All application code must live under the memorii/ package.

Do not create business logic in scripts.

⸻

Module responsibilities

memorii.domain

Contains canonical schemas and enums.
No IO logic.
No persistence logic.
No framework-specific code.

memorii.core

Contains routing, retrieval planning, validation, solver update logic, execution orchestration, and consolidation.

memorii.stores

Contains persistence-layer interfaces and implementations.

memorii.api

Contains framework-neutral service contracts.

memorii.sdk

Contains the Python SDK.

memorii.adapters

Contains only adapter contracts in core package.
Framework-specific adapters should live in separate packages or adapter modules later.

⸻

Strong typing rules

Use pydantic models for:

* public APIs
* persisted domain records
* memory objects
* graph nodes and edges
* event records
* writeback candidates
* adapter payloads

Use enums instead of free-form strings for:

* memory domains
* node types
* edge types
* statuses
* confidence classes
* decision classes
* writeback types
* retrieval intents

Use stable IDs for all major entities:

* task_id
* session_id
* thread_id
* execution_node_id
* solver_run_id
* observation_id
* action_id
* node_id
* edge_id
* event_id
* justification_id
* version_id

Do not rely on in-memory object identity.

Graph edges must refer to node IDs, not object pointers.

⸻

Serialization rules

Every persisted object must support:

* model_dump()
* model_validate()
* JSON serialization
* deterministic reconstruction

Never put non-serializable Python objects in domain models.

Keep storage records and domain records explicit.
If they differ, create separate schema models.

⸻

Persistence rules

Always persistent

* transcript memory
* semantic memory
* episodic memory
* user memory
* execution graph
* event log
* belief/status overlays

Conditionally persistent

* solver graph
* candidate solver state
* unresolved solver frontier
* suspended and reopenable branches

Persist solver state if:

* unresolved
* attached to an open execution node
* needed for future resume
* likely useful for recovery

Resume guarantees

Resuming a task must reconstruct:

* execution graph state
* current task status
* active and blocked work items
* current solver runs
* frontier state
* unresolved questions
* unexplained observations
* belief/status overlay
* reopenable branches

⸻

Candidate vs committed rules

Model-generated content is candidate first unless explicitly grounded and validated.

This applies to:

* hypotheses
* support/contradiction edges
* writebacks
* semantic abstractions
* user preference extraction
* branch conclusions

A candidate item may become committed only after:

1. schema validation
2. provenance validation
3. type-specific consistency checks
4. candidate/committed transition checks
5. evidence sufficiency checks if model-derived

Speculative content must never directly:

* falsify committed branches strongly
* write into semantic memory
* write into user memory
* become execution truth
* become final solver truth

⸻

Event sourcing rules

All structural and dynamic changes must be recorded as immutable events.

Examples:

* memory object created
* memory object routed
* node added
* edge added
* candidate committed
* belief updated
* status updated
* branch suspended
* branch reopened
* node merged
* solver resolved
* consolidation emitted

Do not delete history during normal operation.

Backtracking means revision through new events, not deletion.

⸻

Belief and status overlay rules

Dynamic reasoning state belongs in overlays, not structural nodes.

The overlay must store:

* belief
* status
* frontier priority
* active justifications
* inactive justifications
* last update timestamp

Structural graph nodes must remain stable and replayable.

⸻

Execution graph rules

Execution graph is the top-level work graph.

Required node classes include:

* mission
* work item
* component
* interface
* invariant
* test case
* test suite
* artifact
* decision
* risk
* question
* defect
* milestone

Required edge classes include:

* decomposes_into
* depends_on
* blocks
* implements
* verified_by
* produces
* consumes
* constrained_by
* resolves
* supersedes

Execution graph is the source of truth for:

* what work exists
* what depends on what
* what state work is in
* what invariants/tests define correctness

⸻

Solver graph rules

Solver graph is a task-local reasoning/search graph attached to an execution node or subproblem.

Required node classes include:

* goal
* hypothesis
* composite_hypothesis
* explanation_factor
* observation
* action
* assumption
* constraint
* scenario
* question
* synthesis
* semantic_ref
* episodic_ref
* user_ref
* environment_ref
* skill_ref

Required edge classes include:

* supports
* contradicts
* tested_by
* produces
* refines
* depends_on
* contributes_to
* synthesizes_from
* valid_under
* blocks
* resolves
* reopens
* equivalent_to
* references

The full solver graph is not globally required to be acyclic.
However, structural edges such as refines, derived_from, depends_on, and decomposes_into must remain acyclic where specified by the validator.

⸻

Abstention and uncertainty rules

Unknown must be representable in system state.

Solver outputs must support these decision classes:

* SUPPORTED
* REFUTED
* INSUFFICIENT_EVIDENCE
* NEEDS_TEST
* MULTIPLE_PLAUSIBLE_OPTIONS

For parameter-sensitive or branch-evaluation tasks, stronger classes may be used:

* PROVEN_WORKS
* PROVEN_FAILS
* UNTESTED_PLAUSIBLE
* INSUFFICIENT_INFORMATION
* NEEDS_EXPERIMENT

The model must not be prompted as an oracle.
It must be prompted as a branch evaluator using explicit evidence.

Any unsupported commitment must be downgraded to:

* candidate only
* insufficient evidence
* or needs test

⸻

Prompting and verification rules

Prompts for solver updates must:

* be evidence-bounded
* include explicit abstention options
* require structured output
* require cited evidence IDs
* require missing-evidence reporting when unresolved
* require next-best-test when unresolved

The runtime must not trust the model’s self-report of compliance.

Every model-derived solver decision must pass:

1. schema validation
2. structural validation
3. evidence coverage validation
4. entailment-style verification when applicable
5. optional consistency checks for high-risk steps

Do not directly commit solver state from a single fluent model answer.

⸻

Memory routing rules

Every inbound event must first become one or more typed memory objects.

The router must decide:

* memory domain(s)
* scope
* durability
* candidate vs committed state
* primary store
* secondary stores
* whether a writeback candidate should be created

One event may write to multiple memory domains.

Examples:

* a user message always goes to transcript memory
* a stable user preference may also create a user-memory candidate
* a failing test may update transcript memory, execution memory, and solver memory
* a resolved solver may produce episodic and skill writeback candidates

Do not hardcode memory routing into adapters.

⸻

Retrieval planning rules

Retrieval must be typed and intention-driven.

The retrieval planner must choose memory domains based on task step.

Examples:

* continuing work → execution graph + relevant artifacts + constraints
* debugging → solver graph + transcript evidence + episodic analogies + semantic facts
* user-personalized answer → user memory + semantic memory + transcript context
* resume after pause → execution graph + active solver runs + overlays + unresolved items

Do not do one generic retrieval against all memory stores by default.

⸻

Consolidation rules

Consolidation turns local or transient state into durable reusable memory.

Examples:

* solver run → episodic summary
* repeated successful pattern → skill candidate
* validated reusable abstraction → semantic candidate
* durable user preference revealed → user memory candidate

Consolidation must be explicit and policy-driven.

Do not:

* dump raw full solver graphs into long-term memory by default
* write speculative content into semantic memory
* write transient constraints into durable user memory

⸻

Adapter rules

Memorii core must remain framework-neutral.

Adapters are responsible only for translation between framework-native concepts and Memorii canonical contracts.

Adapters may:

* map framework lifecycle events to Memorii events
* map framework message formats to transcript memory objects
* map framework tool results to observations
* call Memorii retrieval APIs
* return writeback candidates to the host framework

Adapters may not:

* bypass validators
* write directly into stores
* change core semantics
* collapse candidate/committed behavior
* invent framework-specific core behavior

Framework support targets include:

* OpenClaw
* Hermes
* LangGraph
* AutoGen
* OpenAI Agents

Core package must not import framework internals.

⸻

Public contracts and interfaces

Use explicit protocols or abstract base classes for:

* transcript store
* semantic store
* episodic store
* user store
* execution graph store
* solver graph store
* event log store
* overlay store
* memory provider
* adapter interface
* retrieval planner
* consolidator
* verifier

Do not use duck typing without explicit contracts.

All interfaces must be small and testable.

⸻

Dependency policy

Preferred dependencies:

* pydantic
* pytest
* typing_extensions
* sqlalchemy if relational persistence is added
* fastapi only if/when API service is built
* lightweight graph utilities only if justified

Avoid:

* large hidden frameworks
* unnecessary orchestration frameworks inside core
* framework-specific SDK dependencies in core package
* complex dependency injection libraries unless truly necessary

Use the standard library when possible.

Every dependency must have a clear reason.

⸻

Database and backend policy

Do not hardwire the logical model to one physical backend.

The logical model must remain valid whether stores are implemented on:

* PostgreSQL
* document store
* graph store
* hybrid store

Persistence logic must sit behind explicit store interfaces.

The source of truth is the domain model, not the database schema.

⸻

Testing rules

Use pytest.

Every new subsystem must include tests.

Required test categories

Unit tests

For:

* schema validation
* enums and status transitions
* router classification
* retrieval planning
* candidate/committed rules
* event serialization

Integration tests

For:

* memory routing end to end
* execution graph persistence/resume
* solver graph persistence/resume
* event replay
* writeback generation
* adapter translation

Conformance tests

For:

* store interfaces
* adapter interfaces
* retrieval contracts
* candidate/committed invariants

Replay tests

For:

* event-sourced rebuild
* branch reopen behavior
* local recomputation after invalidation

Critical invariants to test

You must test:

* no duplicate committed IDs on idempotent replay
* candidate state cannot strongly falsify committed state
* beliefs are not stored on structural nodes
* resuming a task restores frontier and unresolved state
* one observation can support one branch and contradict another
* solver graph and execution graph remain distinct
* speculative semantic writeback is rejected
* user memory only accepts durable, policy-approved writes

⸻

Commands

Assume these commands unless the repo says otherwise:

Install:

pip install -e ".[dev]"

Run tests:

pytest

Run a subset:

pytest tests/unit
pytest tests/integration

Lint:

ruff check .

Format:

black .

Type check if configured:

mypy memorii

Do not add tools without updating repo docs.

⸻

Workflow for Codex

Before editing code:

1. Read docs/memorii_spec.md
2. Read docs/implementation_rules.md
3. Read PLANS.md
4. Restate the exact task being implemented
5. Identify impacted packages and tests

When implementing:

1. start with schemas and contracts
2. then validators and store interfaces
3. then business logic
4. then tests
5. then docs updates if required

Prefer small safe commits in this order:

* domain models
* interfaces
* storage contracts
* service logic
* adapters
* tests

When asked to implement a feature, do not opportunistically redesign nearby modules.

⸻

If the spec feels underspecified

Do not invent major architecture.

Instead:

1. implement the narrowest interpretation consistent with the spec
2. leave clear TODO markers only where the spec explicitly leaves room
3. document assumptions in code comments or implementation notes
4. keep extension points explicit and typed

If a choice affects core semantics, stop and surface the ambiguity instead of improvising.

⸻

Success criteria for any implementation step

A step is complete only if:

* code matches spec
* types are explicit
* validators are present where needed
* tests cover invariants
* no architecture shortcuts were introduced
* resume and provenance semantics are preserved if affected

⸻

Final reminder

Memorii is a memory operating model, not a single storage plugin.

The most important things to preserve are:

* typed memory domains
* execution graph vs solver graph separation
* candidate vs committed lifecycle
* event-sourced revision
* abstention-aware solver updates
* framework-neutral adapter model
* persistence and resume across runs
* explicit routing, retrieval, and consolidation

A few optional companion files will make this work even better:
- `docs/implementation_rules.md`
- `PLANS.md`
- `skills/execution-graph/SKILL.md`
- `skills/solver-graph/SKILL.md`
- `skills/adapters/SKILL.md`
My recommendation is to add this `AGENTS.md` first, then ask Codex to do only one narrow task:
> Read `AGENTS.md`, `docs/memorii_spec.md`, and `PLANS.md`. Implement only the Python package skeleton, core enums, IDs, and Pydantic schemas. Then stop.
That will keep the first Codex run under control.