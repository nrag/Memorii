# AGENTS.md

## Purpose

This file is the operating guide for contributors and coding agents working on
Memorii.

It defines:

* repository-wide invariants
* sources of truth
* workflow routing
* knowledge routing
* rules that apply across all work types

Detailed product behavior belongs in the governing design documents. Detailed
workflows belong in repository Skills. Durable state for long-running work
belongs in WorkPlans.

Do not copy large specifications, implementation procedures, or debugging
playbooks into this file.

Memorii is a framework-neutral memory plane for agents. It is a typed,
multi-memory system with explicit routing, retrieval, persistence, execution
memory, solver/search memory, and conservative memory evolution.

It is not:

* a generic chat-history wrapper
* a single vector store
* a single graph for every kind of state
* a replacement for an agent harness

## Sources Of Truth

Before changing or evaluating a subsystem, read the documents that govern it.

Use this precedence when product or implementation requirements conflict:

1. `docs/design/memorii_spec.md`
2. `docs/design/memorii_storage_details.md`
3. `docs/design/event_model.md`
4. `docs/IMPLEMENTATION_RULES.md`
5. The relevant current document under `docs/design/`
6. `docs/plans/engineering_hardening_closure_matrix.md` for the current
   hardening acceptance contract
7. `docs/plans/agent_integration_readiness.md` for integration scope and
   readiness claims
8. This file
9. `docs/plans/initial.md`, which is historical context rather than a statement
   of current implementation status

`.agent/PLANS.md` is the process contract for long-running work. It defines how
WorkPlans are structured and completed. It is not a source of product behavior.

Repository Skills under `.agents/skills/` define how Codex conducts design,
implementation, and debugging operations. A Skill may not override a governing
design or architecture document.

Active WorkPlans under `docs/work/` record progress, assumptions, decisions,
experiments, and evidence. A WorkPlan may not silently amend a governing design.

Do not claim that planned behavior exists merely because it appears in a plan
or design. Confirm current behavior in production code, tests, and generated
artifacts.

Update current-state documentation when implementation changes make it stale.

## Workflow Routing

Classify long-running work before beginning.

| Work type                              | Use                 |
| -------------------------------------- | ------------------- |
| Build or substantially revise a design | `$build-design`     |
| Implement an approved design           | `$implement-design` |
| Investigate and fix a complex failure  | `$debug-problem`    |

A task is long-running when it:

* has multiple uncertain or dependent steps
* requires repeated experimentation or review
* may span multiple Codex turns
* must be resumable from repository artifacts
* affects several architectural or operational boundaries

Long-running work requires a WorkPlan conforming to `.agent/PLANS.md`.

Small, bounded changes do not require a WorkPlan unless the applicable design,
issue, or user instruction requires one. They must still follow the governing
documents and repository invariants.

Do not combine design, implementation, and debugging into one WorkPlan.

When work crosses operation boundaries:

1. complete or pause the current WorkPlan
2. create a new linked WorkPlan with the correct work type
3. identify the previous WorkPlan as its parent or related work
4. preserve the evidence and decisions from the earlier operation

Examples:

* A completed design WorkPlan may lead to a separate implementation WorkPlan.
* An implementation WorkPlan may expose a defect requiring a separate debugging
  WorkPlan.
* A debugging result may reveal a missing requirement requiring a new design
  WorkPlan.

Do not silently convert the type of an active WorkPlan after meaningful work
has begun.

## Long-Running Work Rules

The main Codex thread is the coordinator.

The coordinator owns:

* objective and scope
* active WorkPlan
* assumptions and decisions
* selection of milestones or experiments
* reconciliation of evidence
* validation of reviewer findings
* final completion or blocked judgment

Use parallel subagents primarily for read-heavy and independently verifiable
work, including:

* repository exploration
* requirement analysis
* design critique
* execution-path tracing
* log analysis
* hypothesis generation
* code review
* test-gap analysis

Use only one writer at a time for overlapping code or document artifacts.

The standard independent reviewers are:

* `spec_auditor`
* `correctness_reviewer`
* `test_reviewer`

Their responsibilities vary by workflow and are defined in the applicable
Skill.

Reviewer findings are advisory. The coordinator must inspect the evidence and
classify every finding as:

* confirmed
* duplicate
* unsupported
* already resolved
* accepted limitation
* design ambiguity
* blocked by missing evidence or information

Only confirmed findings enter a revision, remediation, or investigation loop.

### Finding Classification Contract

Every review finding must classify three independent dimensions:

* `Product priority`: `P1`, `P2`, `P3`, or `Not applicable`
* `Approval disposition`: `blocks_approval`, `changes_required`, or `follow_up`
* `Finding type`: the affected concern, such as runtime behavior, architecture,
  verification, governance, external decision, security, operability, or
  compatibility

Use product priority only for product impact:

* `P1`: Mainstream scenarios are broken. The defect affects the ordinary,
  default, or dominant path, approximately the 90% use case, and is a shipping
  blocker.
* `P2`: Mainstream scenarios work, but important cases are broken,
  approximately the remaining 10%. Shipping with the defect is not advisable.
* `P3`: Fit, finish, clarity, diagnostics, ergonomics, maintainability, or
  polish. The product remains correct and high quality without the change, but
  fixing it improves the user or developer experience.
* `Not applicable`: The finding concerns review governance, conflicting source
  authority, missing external decisions, or another approval concern without a
  demonstrated product-behavior impact.

The 90% and 10% figures are decision heuristics, not statistical claims unless
measured evidence is available. Every P1 or P2 classification must name the
affected scenario and cite evidence for its prevalence or explain why it is
mainstream or important. Do not infer P1 merely because a finding concerns a
critical invariant, security, persistence, architecture, or an external
decision.

Use approval disposition only for review outcome:

* `blocks_approval`: Safe approval or implementation cannot proceed because a
  governing conflict, missing external decision, infeasible architecture, or
  unresolved core objective prevents a determinate correction.
* `changes_required`: The correction is determinate and must be made before
  approval.
* `follow_up`: The finding does not prevent approval and may be handled later.

Product priority and approval disposition are deliberately independent. A
governance finding may be `Not applicable` and still `blocks_approval`; an
important edge-case defect may be `P2` and `changes_required`. Reviewers must
not use `Blocking`, `High`, `Medium`, or `Low` as severity aliases.

Use only these combinations:

| Product priority | Allowed approval dispositions |
| ---------------- | ----------------------------- |
| `P1`             | `blocks_approval`, `changes_required` |
| `P2`             | `blocks_approval`, `changes_required` |
| `P3`             | `follow_up` |
| `Not applicable` | `blocks_approval`, `changes_required`, `follow_up` |

If a supposed P3 must be corrected before safe implementation or approval, it
is not P3. Re-evaluate its demonstrated product impact or classify it as `Not
applicable` when it is purely an approval or governance concern.

Every active WorkPlan must have exactly one stated next action.

Update the WorkPlan after every material:

* milestone
* experiment
* review round
* decision
* discovery
* blocker
* change in scope

A new agent must be able to resume the operation using only:

1. applicable `AGENTS.md` instructions
2. `.agent/PLANS.md`
3. the active WorkPlan
4. artifacts and evidence referenced by the WorkPlan

Do not depend on inaccessible chat history or unstated reasoning.

## Repository Knowledge Routing

Read the documents governing the affected subsystem before proposing,
implementing, debugging, or reviewing behavior.

| Area                                        | Required documents                                   |
| ------------------------------------------- | ---------------------------------------------------- |
| Core architecture and public behavior       | `docs/design/memorii_spec.md`                        |
| Storage, transactions, and persistence      | `docs/design/memorii_storage_details.md`             |
| Events and lifecycle                        | `docs/design/event_model.md`                         |
| Package ownership, types, and serialization | `docs/IMPLEMENTATION_RULES.md`                       |
| Runtime memory evolution                    | `docs/design/memory_evolution_runtime.md`            |
| Runtime benchmark design                    | `docs/design/memory_evolution_runtime_benchmark.md`  |
| Prompts and model output                    | `docs/design/prompt_contracts.md`                    |
| Temporal retrieval                          | `docs/design/semantic_temporal_retrieval.md`         |
| Simulator and oracle isolation              | `docs/design/latent_graph_simulator.md`              |
| Deterministic tooling and package checks    | `docs/development/static_tooling.md`                 |
| Live benchmark certification                | `docs/development/benchmark_certification.md`        |
| Engineering hardening                       | `docs/plans/engineering_hardening_closure_matrix.md` |
| Agent integration readiness                 | `docs/plans/agent_integration_readiness.md`          |

Read nearby tests and production call paths in addition to documents. Documents
can be stale, incomplete, or narrower than the current implementation.

When sources disagree:

1. apply the precedence defined above
2. record the conflict in the WorkPlan
3. do not silently select the most convenient interpretation
4. stop for an external decision when the conflict changes public or persisted
   semantics

## Universal Memorii Invariants

Preserve these distinctions in every design, implementation, debugging, and
review operation:

* raw transcript, semantic, episodic, user-context, execution-plan, and
  solver/search memory are separate logical domains
* candidate state is distinct from committed state
* structural graph state is distinct from versioned belief and status overlays
* the persistent execution graph is distinct from task-local solver graphs
* memory routing is distinct from retrieval planning
* raw observations are distinct from derived memory-evolution projections
* provider transport validation is distinct from domain-semantic validation
* production retrieval is isolated from benchmark oracle data
* framework-neutral contracts are isolated from host-specific integrations

Do not:

* store dynamic beliefs directly on structural graph nodes
* let model output mutate committed truth without explicit validation
* write speculative content directly into semantic or user memory
* let adapters or integrations bypass validators or store contracts
* replace typed public or persisted schemas with untyped dictionary blobs
* delete event history to represent revision or backtracking
* collapse execution and solver graphs into one generic graph
* import simulator oracle state into production extraction or retrieval
* couple core logic to Hermes, OpenClaw, LangGraph, AutoGen, OpenAI Agents, or
  another particular harness

Unknown, ambiguous, insufficient-evidence, and needs-test outcomes are valid.

The system must fail closed rather than require a model to guess.

## Common Repository Rules

Application code lives under `memorii/memorii/`.

Follow the current repository layout and existing ownership boundaries. Do not
enforce a historical exact file tree.

Before adding a type, helper, service, registry, or abstraction:

1. search for an existing contract or implementation
2. identify the canonical owner
3. inspect relevant public, persisted, and integration boundaries

Prefer:

* cohesive modules with explicit owners
* typed public and persisted contracts
* stable identifiers
* deterministic reconstruction
* explicit validation stages
* thin adapters, integrations, and command-line entry points
* reusable business logic under `memorii.core`

Avoid:

* relocation facades
* circular imports
* monolithic services
* magic registries
* framework-heavy base classes
* raw nested dictionaries used to avoid modeling a contract
* casts used to conceal incompatible representations

All public or persisted schemas must remain explicit and fail closed for
unknown lifecycle or enum values.

Model-produced data must pass the applicable stages separately:

1. prompt output-schema validation
2. provider transport parsing
3. typed domain-semantic validation
4. provenance and evidence validation
5. lifecycle or candidate/commit policy
6. transactional persistence

Do not make a fluent model response committed solver or memory truth.

Preserve unrelated user changes in the working tree.

Do not opportunistically redesign adjacent systems.

If a choice would alter a core semantic contract and governing documents do not
resolve it, record the ambiguity and stop for a decision.

Otherwise, implement or propose the narrowest complete behavior consistent with
the architecture.

## Testing And Evidence Routing

Testing and certification procedures belong in:

* `docs/development/static_tooling.md`
* `docs/development/benchmark_certification.md`
* the applicable workflow Skill
* the active WorkPlan

Tests must be proportional to the changed or investigated contract and must
cover relevant failure modes, not only successful examples.

Do not weaken:

* warnings
* test selection
* schema validation
* benchmark family coverage
* sample-size requirements
* retry accounting
* statistical thresholds

Do not modify a contract merely to make a gate pass unless the contract change
is explicit, justified, reviewed, and reflected in governing documents.

Keep these evidence classes distinct:

* deterministic tests establish code-level invariants
* fake-oracle runs validate plumbing and evaluation mechanics
* live runtime evaluation measures provider behavior for an exact revision
* agent-system quality requires separate agent-level evidence

Never report fake-oracle execution as provider success.

A live result from another revision, a dirty tree, mixed run identities, or
post-run threshold or prompt tuning is not certification for the reviewed
revision.

## Completion And Stop Rules

Do not claim completion because:

* code was written
* a document was produced
* tests passed
* reviewers stopped producing findings
* an agent reported success

Complete work only when the applicable completion contract in
`.agent/PLANS.md` is satisfied by recorded evidence.

Stop as blocked when:

* a required decision belongs to the user or another external owner
* required data, credentials, access, or environment is unavailable
* continuing requires expanding the agreed scope
* all defensible approaches within the defined budget are exhausted
* the iteration limit has been reached without convergence

When stopping as blocked, record:

* what was attempted
* what was learned
* remaining uncertainty
* the exact blocker
* the smallest input or decision needed to continue

Do not perform endless speculative revision, debugging, or refactoring merely
to make reviewers stop reporting observations.
