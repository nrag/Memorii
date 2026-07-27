---

name: build-design
description: Build or substantially revise a Memorii technical design through repository research, requirements analysis, feasibility work, independent review, and revision.
-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# Build A Memorii Design

Read:

* root `AGENTS.md`
* `.agent/PLANS.md`
* the active design WorkPlan, if one exists
* governing documents selected through the repository knowledge router
* relevant production code and tests

Create or resume a WorkPlan whose work type is `design`.

The main thread is the coordinator. Use exactly one writer for the canonical
design document.

## Phase 1: Establish The Problem

1. Identify the problem, actors, current behavior, desired outcome, and impact.
2. Identify the source of each claimed requirement.
3. Define included scope, excluded scope, and non-goals.
4. Identify the current or intended canonical design document.
5. Create stable requirement IDs.
6. Define measurable acceptance criteria for each requirement.
7. Record assumptions and unresolved product decisions.

Do not invent externally visible behavior to close an ambiguity.

## Phase 2: Analyze The Existing System

Spawn read-only exploration agents when useful to inspect:

* architecture
* relevant packages and owners
* production execution paths
* public and persisted contracts
* provider and integration boundaries
* current tests
* failure and recovery behavior
* existing related designs
* historical or current plans

Wait for the exploration agents and reconcile their results against the
repository.

Do not trust document claims without checking relevant code and tests.

## Phase 3: Develop And Evaluate Alternatives

For every material design choice:

1. describe at least one serious alternative
2. record advantages, disadvantages, and risks
3. identify affected invariants and boundaries
4. identify migration, compatibility, and rollback implications
5. select an approach based on explicit evidence and constraints

Do not add alternatives merely to create the appearance of analysis.

Use prototypes or bounded experiments for material feasibility questions.

Experiments must have a discriminating outcome. Record them in the WorkPlan.

## Phase 4: Draft The Design

The design must cover, where applicable:

* requirements and acceptance criteria
* architecture and component ownership
* typed public and persisted contracts
* data and event flow
* candidate and committed state
* transaction and visibility boundaries
* idempotency and replay
* concurrency and fencing
* failure and recovery
* provenance and evidence validation
* prompt and provider validation stages
* retrieval and temporal semantics
* oracle isolation
* authorization and security
* privacy
* observability
* deployment
* migration
* rollback
* compatibility
* resource and performance limits
* verification strategy
* non-goals and remaining limitations

Preserve the universal Memorii invariants in `AGENTS.md`.

## Phase 5: Independent Review

After a coherent draft exists, run these reviewers concurrently:

* `spec_auditor`
* `correctness_reviewer`
* `test_reviewer`

Tell each reviewer to inspect the design, governing documents, relevant code,
tests, and active WorkPlan directly.

Tell each reviewer to classify findings using the canonical contract in
`AGENTS.md`: product priority, approval disposition, and finding type. Reviewers
must not use `Blocking`, `High`, `Medium`, or `Low` as severity labels or infer
P1 from an approval blocker.

During design review:

* `spec_auditor` checks requirement completeness, contradictions, undefined
  terms, hidden assumptions, and scope gaps
* `correctness_reviewer` checks feasibility, architecture, security,
  integration, failure handling, and operational risks
* `test_reviewer` checks that acceptance criteria are measurable and the design
  can be verified

Wait for every reviewer.

The coordinator must classify each finding using the dispositions in
`.agent/PLANS.md`.

Revise only for confirmed findings.

Update the requirements ledger, decision log, review log, and next action.

## Phase 6: Final Design Review

When the design appears complete:

1. rebuild the requirements ledger from the design
2. compare it with the maintained ledger
3. resolve every discrepancy
4. inspect the design for undefined terms and hidden assumptions
5. confirm all externally visible or persisted behavior is explicit
6. confirm failure, migration, rollback, security, compatibility, and
   verification sections are complete where applicable
7. run a fresh whole-design review with the three reviewers

Complete the WorkPlan only when the design completion contract in
`.agent/PLANS.md` is satisfied.

Do not claim the design is risk-free. State that no unresolved validated design
gaps remain under the defined scope and review contract.

Stop as blocked when the WorkPlan stop conditions apply.
