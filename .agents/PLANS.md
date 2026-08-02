# Long-Running WorkPlans

This document defines the structure, lifecycle, and completion rules for
long-running Codex operations in Memorii.

A WorkPlan is the durable, self-contained state of one operation.

Supported work types are:

* `design`
* `implementation`
* `testing`
* `debugging`
* `pr-review`
* `investigation`
* `migration`

This document fully defines design, implementation, testing, debugging, and PR
review.
Investigation and migration plans
must follow the common requirements and add an explicit completion contract
appropriate to their work.

## WorkPlan Storage

Store WorkPlans under:

```
docs/work/<work-id>/
```

Recommended filenames are:

* `design.plan.md`
* `implementation.plan.md`
* `testing.plan.md`
* `debug-001.plan.md`
* `pr-review.plan.md`
* `investigation-001.plan.md`
* `migration.plan.md`

Use separate linked WorkPlans for separate work types.

An active WorkPlan must not be silently converted from one work type to another.

## General Requirements

A WorkPlan must be self-contained.

Assume the reader has:

* the current repository
* applicable `AGENTS.md` instructions
* this file
* the WorkPlan
* artifacts explicitly referenced by the WorkPlan

Do not assume access to previous chats or unstated reasoning.

A WorkPlan is a living document. Update it whenever work changes the known
state, including after:

* completing a milestone
* running an experiment
* discovering evidence
* making or changing a decision
* validating or rejecting a review finding
* encountering a blocker
* changing scope
* changing the next action

Do not erase useful history.

Mark earlier hypotheses, decisions, or approaches as disproved, superseded,
abandoned, or no longer applicable.

## Status Values

Use one of these statuses:

* `proposed`
* `active`
* `blocked`
* `under-review`
* `complete`
* `abandoned`

A WorkPlan may be marked `complete` only when its work-type completion contract
is satisfied.

A WorkPlan marked `blocked` must identify the precise condition required to
resume.

## Required Header

Every WorkPlan begins with:

```markdown
# <Title>

- Work ID:
- Work type:
- Status:
- Coordinator:
- Created:
- Last updated:
- Parent WorkPlan:
- Related WorkPlans:
- Canonical inputs:
- Expected outputs:
```

Use `None` where a relationship does not exist.

## Required Common Sections

Every WorkPlan must contain the following sections.

### Objective

Describe the observable end state.

State what will be true when the operation succeeds.

### Completion Contract

State the exact evidence required for completion.

Do not use subjective completion conditions such as:

* looks correct
* seems complete
* no obvious issues
* reviewers are satisfied
* tests mostly pass

### Scope

Separate:

* included work
* excluded work
* explicitly deferred work

Do not expand scope silently.

### Constraints And Invariants

Record applicable:

* public behavior
* architecture invariants
* persisted semantics
* compatibility requirements
* security boundaries
* performance limits
* operational constraints
* external dependencies

Reference governing documents.

### Identity And Coordinate Hygiene

Classify every identifier introduced, retained, renamed, serialized, generated,
or exposed by the operation. Keep these identity classes separate:

| Identity class | Examples | Allowed use |
| -------------- | -------- | ----------- |
| planning/evidence coordinate | WorkPlan milestone or phase, requirement ID, issue or PR number, review round, experiment ID, temporary task label | WorkPlans, requirements ledgers, review reports, typed traceability fields, and explicit legacy or malformed-input vectors only |
| behavioral identity | module, file, class, function, test, fixture, helper, job, CLI command, log or error code, artifact member, owner, runtime discriminator | Name the durable domain behavior or owned contract |
| protocol identity | public wire/schema version, persisted format, event kind, externally consumed command | Name the durable protocol behavior and version, never the delivery sequence that created it |
| migration identity | an already shipped source/target format or migration generation | Use only when compatibility with real persisted or external state requires it |

Planning/evidence coordinates include names such as `M1`, `M3`, `phase-2`, `C2`,
`R22`, `SIA-R22`, issue numbers, dates, review rounds, and WorkPlan IDs. The
examples are illustrative, not a closed spelling list. A prefixed, abbreviated,
hyphenated, or reformatted planning/evidence coordinate remains in that class.

Never use a planning/evidence coordinate as, or inside, a behavioral or protocol
identity. In particular, it must not appear in production or test filenames,
module paths, Python or schema symbols, persisted discriminators, owner IDs,
fixture or helper IDs, generated member IDs, test node IDs, executable command
or evidence-group IDs, CI job or step names, runtime diagnostics, or user-facing
labels. Requirement IDs remain values in explicit traceability metadata; they
must not become executable names or general prose labels.

A numeric or version token is permitted only when it describes a genuine
behavioral quantity or stable protocol/migration version. For example, `BM25`
is an algorithm name and `.v1` may be a wire version; neither permission makes
`M2` or `R25` a valid planning-derived identity. Domain terms such as
`DeliveryCoordinate` remain valid when they describe durable product behavior
and pass the durability test; the word "delivery" is not itself prohibited.

Apply the durability test before accepting a name:

> If the WorkPlan, milestone ledger, requirement numbering, issue, and review
> history disappeared, would a new maintainer still choose this name from the
> behavior or protocol alone?

If not, choose a behavioral name. When a governing design prescribes a
planning-derived durable identity, record a design conflict and correct or
reopen the design before implementation. Do not preserve an unshipped bad name
through an alias. For a shipped public or persisted identity, use an explicit
migration or compatibility contract while making the current owner behavioral.

Every WorkPlan that creates, changes, or reviews identifiers must maintain this
ledger; otherwise record `Not applicable` with evidence:

| Surface | Proposed or existing identity | Class | Behavioral owner or protocol meaning | Retain, rename, migrate, or reject | Proof |
| ------- | ----------------------------- | ----- | ------------------------------------ | --------------------------------- | ----- |

Inventory the complete affected family, including production, tests, fixtures,
generators, golden files, registries, persisted bytes, docs, CI, timing data,
and generated artifacts. Search for predecessor and sibling spellings before
editing and again at closure.

Identity hygiene requires executable enforcement. Use or extend a field-aware
static check that inspects identifiers and the relevant structured fields in
Python, schemas, registries, fixtures, workflow files, and generated manifests.
The canonical owner is `memorii.tools.identity_hygiene`; its machine-readable
exception authority is `.agents/identity_hygiene_allowlist.json`. CI invokes
it from `memorii/` as
`python -m memorii.tools.identity_hygiene --root .. --allowlist ../.agents/identity_hygiene_allowlist.json`.
Do not use a blanket substring ban that rejects legitimate names such as
`BM25`. Keep exceptions exact, typed, minimal, and recorded in the ledger.
Every exception must point to machine-checked repository proof: the named
rejection test, canonical traceability registry, or retained compatibility
artifact that makes the occurrence necessary. A classification label or
rationale alone is not proof. A directory-wide or whole-file exception is
invalid. The check must run in the appropriate required gate. Mutation coverage
must prove that `M1`, `M2`, `M3`, `C2`, `R22`, and `SIA-R22` are rejected in
each newly covered behavioral or protocol surface. A fixed positive corpus
must prove that `BM25`, genuine wire or schema versions, and a real retained
compatibility or migration identity remain accepted in their valid fields.

### Sources Of Truth

List the exact specifications, code, tests, logs, incidents, measurements, or
other artifacts that define expected behavior.

State the precedence to apply if these sources disagree.

### Current State

Explain what is known at the time of the most recent update.

Separate verified facts from interpretation.

Before closure, reconcile this section with completed milestones, named
artifacts, and recorded evidence. A historical baseline must be labeled as
historical; it must not remain presented as current state after implementation.

### Assumptions And Open Questions

Maintain four categories:

* verified facts
* working assumptions
* unresolved questions
* decisions requiring external input

Do not present an assumption as a fact.

### Milestones Or Experiments

Design, implementation, and testing WorkPlans use milestones.

Debugging WorkPlans use experiments and may also use milestones.

Every milestone must include:

* purpose
* bounded scope
* expected artifacts
* verification method
* status

Every experiment must include:

* hypothesis being tested
* discriminating observation
* procedure
* expected outcomes
* actual result
* conclusion
* evidence location

### Progress Log

Use timestamped entries.

Each entry records:

* action
* result
* evidence produced
* effect on current understanding
* next action

### Evidence Log

Record concrete evidence such as:

* file paths
* symbols
* line ranges
* test names
* test output
* commands and exit status
* logs and traces
* benchmark measurements
* reproduction steps
* prototype results
* review findings
* generated artifacts

An agent summary is not evidence by itself.

For every milestone or final closure, append one revision-bound record:

```yaml
reviewed_revision:
tested_revision:
tree_state:
workflow_identities: []
ci_event:
ci_executed_sha:
ci_executed_ref:
remaining_validated_p1_p2: []
remaining_blocks_approval: []
remaining_changes_required: []
local_ci_parity:
acceptance_gate_inventory: []
github_run_urls: []
pr_head_sha:
pr_base_sha:
merge_base_sha:
required_checks_green:
```

Use `not_applicable` only with a reason. A closure record is invalid when code,
tests, fixtures, generated artifacts, dependencies, or workflows change after
the recorded review or verification.

Every milestone and final closure requires
`remaining_validated_p1_p2: []`. Testing and debugging work may route a newly
discovered product defect to a linked WorkPlan, but the current milestone is
not complete until that defect is resolved, explicitly removed from scope by
an authorized decision, or makes the operation blocked.

### Decision Log

For each material decision, record:

* decision
* date
* alternatives considered
* evidence and rationale
* consequences
* owner, when external approval is required

### Review Log

For every review round, record:

* reviewers used
* review scope
* findings
* coordinator disposition
* evidence supporting the disposition
* product-impact evidence and remediation eligibility
* resulting actions

Use these finding dispositions:

* confirmed
* duplicate
* unsupported
* already resolved
* accepted limitation
* design ambiguity
* blocked by missing evidence or information

### Blockers And Limits

Record:

* current blockers
* iteration or experiment budget
* rounds already used
* resource or environment limits
* conditions required to resume

### Next Action

While a WorkPlan is active, identify exactly one next action.

The next action must be bounded and executable.

Avoid statements such as:

* continue implementation
* keep debugging
* review more
* finish the design

### Outcome And Retrospective

When work is complete, abandoned, or permanently blocked, summarize:

* final result
* evidence supporting the result
* remaining limitations
* follow-up work
* lessons for future operations

## Coordinator And Reviewer Protocol

The main thread is the coordinator.

The coordinator must:

1. maintain the WorkPlan
2. select bounded milestones or discriminating experiments
3. validate subagent claims against direct evidence
4. reconcile conflicting reviewer findings
5. decide whether the completion contract has been satisfied

Use one writer at a time for overlapping artifacts.

Read-only exploration and independent review may run in parallel.

The standard reviewers are:

* `spec_auditor`
* `correctness_reviewer`
* `test_reviewer`

Every reviewer and coordinator must use the canonical product-priority,
approval-disposition, and finding-type contract in `AGENTS.md`. Product
priority does not determine approval outcome by itself.

Review findings do not automatically become requirements.

The coordinator must validate each finding before changing the plan or
implementation.

### Product-Impact Remediation Gate

Product-semantic remediation is reserved for validated `P1` or `P2` product
defects. Before a finding can consume a product-remediation round, the
coordinator must record:

* the supported production scenario that is broken
* direct evidence of wrong or absent behavior through the canonical path
* why the scenario is mainstream (`P1`) or important (`P2`)
* the governing requirement violated
* the smallest in-scope correction and behavioral failure signal

Do not infer `P1` or `P2` from:

* `blocks_approval` or `changes_required`
* the importance of an invariant, subsystem, or trust boundary
* a missing or weak test by itself
* a malformed, unsupported, or hypothetical input that cannot reach a
  supported trust boundary
* an evidence-maturity, documentation, governance, or process gap without a
  demonstrated product-behavior defect

Use one of these remediation-eligibility values in the Review Log:

| Value | Meaning |
| ----- | ------- |
| `eligible_p1_p2` | A validated P1/P2 product defect enters bounded remediation |
| `evidence_action` | Required proof is missing; gather the predefined evidence without changing product semantics |
| `contract_conformance_action` | A determinate architecture, identity, governance, or repository-contract violation must be corrected, without inventing product priority |
| `record_only` | P3, unsupported, duplicate, or nonblocking governance observation |
| `external_blocker` | A missing authority or semantic decision prevents determinate work; stop instead of iterating |

Approval disposition remains independent. A non-P1/P2 finding may require an
explicit evidence action, a bounded contract-conformance correction, or may
stop approval. `contract_conformance_action` is valid only when the governing
repository contract makes the correction determinate; it must not be used to
invent or choose product semantics. Identity leakage prohibited by the common
identity contract is `Not applicable`, `changes_required`, finding type
`identity-governance`, and `contract_conformance_action` unless direct product
impact supports P1/P2. Required evidence and conformance actions are bounded by
the existing validation matrix or completion contract; reviewers may not
expand them round by round.

When a review produces no newly validated P1/P2 defect, do not open another
product-remediation round. Close the milestone if its predefined completion
evidence is satisfied, record nonblocking follow-ups, or stop once with the
exact external blocker.

## Evidence Standards

Evidence should be proportional to the claim.

Examples:

| Claim                        | Minimum evidence                                              |
| ---------------------------- | ------------------------------------------------------------- |
| A requirement is implemented | Production path plus relevant tests                           |
| A defect is reproduced       | Repeatable procedure and observed failure                     |
| A root cause is confirmed    | Causal evidence and a discriminating experiment               |
| A fix works                  | Before/after proof and regression checks                      |
| A design is feasible         | Existing-system analysis, prototype, or bounded experiment    |
| A benchmark is certified     | Revision-bound artifact satisfying the certification contract |
| A document matches reality   | Inspection of current code, tests, and generated artifacts    |

Passing tests are necessary when applicable but do not alone prove that all
requirements are implemented.

Absence of reviewer findings is not proof of correctness.

Local command equivalence and CI enforcement are separate evidence classes.
Local equivalence requires the repository commands selected by current
workflow definitions with matching cwd, declared environment, warning mode,
matrix or shard inputs, and deterministic artifacts. GitHub-only actions,
artifact transport, runner setup, network steps, and expression evaluation are
not local commands and must not be claimed as locally reproduced.

Head-bound local verification requires a clean detached worktree, including no
untracked files. Results from a dirty tree or different runtime are diagnostic
only. CI enforcement requires the actual GitHub workflow to pass. Record the
event, run URL, executed SHA/ref, PR head/base/merge-base relationship, and
workflow identity. A `pull_request` merge SHA, PR head SHA, and `merge_group`
SHA are distinct identities and must never be substituted for one another.

## Work Type: Design

A design WorkPlan produces or substantially revises a canonical design
specification.

Writing a document is not sufficient evidence of completion.

### Required Design Sections

In addition to the common sections, include the following.

#### Problem Definition

Describe:

* user or system problem
* affected actors
* current behavior
* desired outcome
* why the problem matters

#### Requirements Ledger

Assign stable identifiers to requirements.

Use:

| ID | Requirement | Source | Priority | Acceptance criteria | Status |
| -- | ----------- | ------ | -------- | ------------------- | ------ |

Every externally visible, persisted, operational, or security-sensitive
behavior must have an explicit requirement or be explicitly excluded.
Requirement IDs are traceability values only. Derive all proposed public,
persisted, code, test, fixture, artifact, and CI names from behavior and record
them in the common identity ledger before design approval.

#### Non-Goals

State what the design deliberately does not solve.

#### Existing-System Analysis

Document relevant:

* architecture
* production execution paths
* public interfaces
* persisted models
* integration boundaries
* operational constraints
* tests
* prior decisions

#### Alternatives Considered

For every serious alternative, record:

* approach
* advantages
* disadvantages
* risks
* supporting evidence
* reason accepted or rejected

#### Feasibility Evidence

Use prototypes, repository exploration, dependency analysis, measurements, or
small experiments for material unknowns.

Do not leave a major implementation risk hidden behind an assumption.

#### Failure And Operational Analysis

Address applicable:

* invalid inputs
* partial failure
* retries
* idempotency
* concurrency
* consistency
* authorization
* privacy
* security
* observability
* deployment
* migration
* rollback
* compatibility
* resource exhaustion
* recovery after interruption

#### Verification Strategy

For each requirement, describe how it will eventually be verified through:

* deterministic tests
* integration tests
* end-to-end tests
* benchmarks
* static checks
* inspection
* operational evidence

### Design Reviewer Responsibilities

During design work:

* `spec_auditor` checks requirement completeness, contradictions, undefined
  terms, hidden assumptions, and scope gaps
* `correctness_reviewer` checks technical feasibility, architecture,
  integration boundaries, security, failure handling, and operational risks
* `test_reviewer` checks whether acceptance criteria are measurable and the
  proposed behavior can be verified

### Design Completion Contract

A design is complete only when:

* the problem, users, scope, and non-goals are explicit
* every requirement has a stable ID
* every requirement has measurable acceptance criteria
* affected existing-system paths and contracts are documented
* major architectural choices and alternatives are recorded
* material feasibility risks have evidence or are explicitly unresolved
* failure, security, operational, migration, rollback, and compatibility
  concerns are addressed where applicable
* the verification strategy covers every in-scope requirement
* the identity ledger covers every affected durable surface, proposed names are
  behavioral or genuine protocol/migration identities, and the verification
  strategy includes field-aware enforcement
* no validated `P1` or `P2` design defect remains
* no unresolved external authority or semantic decision prevents approval
* predefined verification evidence is complete, or unavailable evidence is
  recorded without inflating it into a product defect
* assumptions and remaining limitations are visible
* the specification is sufficient to create an implementation WorkPlan without
  relying on hidden conversational context

## Work Type: Implementation

An implementation WorkPlan implements a specific canonical design baseline.

The implementation must not silently reinterpret the design.

### Required Implementation Sections

In addition to the common sections, include the following.

#### Design Baseline

Record:

* canonical design path
* design revision, commit, or checksum
* in-scope requirement IDs
* approved deviations
* unresolved design questions

#### Requirement Coverage Ledger

Use:

| Requirement | Implementation | Tests | Other evidence | Status |
| ----------- | -------------- | ----- | -------------- | ------ |

Valid statuses are:

* not started
* in progress
* implemented
* verified
* blocked
* excluded by design

Do not mark a requirement verified based only on a worker summary.

#### Change Map

List expected changes to:

* domain schemas
* persistence
* transactions
* orchestration
* retrieval
* prompts
* provider boundaries
* adapters
* integrations
* command-line entry points
* configuration
* artifacts
* tests
* documentation
* deployment

Mark non-applicable areas explicitly when their absence could otherwise hide a
gap.

For every changed area, include filenames, symbols, serialized identifiers,
tests, fixtures, generated artifacts, and CI labels in the common identity
ledger. A milestone boundary may organize work but may not name its outputs.

#### Migration, Rollout, And Rollback

Describe applicable:

* compatibility strategy
* persisted-data migration
* feature flags
* staged rollout
* rollback
* mixed-version behavior
* operational monitoring

#### Verification Commands

Record exact commands for applicable:

* formatting
* linting
* type checking
* builds
* unit tests
* integration tests
* end-to-end tests
* migration tests
* package checks
* benchmarks
* live certification

Record commands that could not be run and explain why.

### Implementation Reviewer Responsibilities

During implementation:

* `spec_auditor` compares the full current implementation with every in-scope
  design requirement
* `correctness_reviewer` inspects for bugs, regressions, security problems,
  state inconsistency, concurrency failures, unsafe recovery, and integration
  gaps
* `test_reviewer` checks whether tests prove the required behavior, including
  negative, boundary, failure, retry, migration, and compatibility cases

### Implementation Completion Contract

Implementation is complete only when:

* every in-scope requirement has implementation evidence
* every in-scope requirement has appropriate verification evidence
* implementation, types, tests, prompts, artifacts, and current-state
  documentation agree
* invalid inputs and unsupported states fail explicitly and safely
* provenance, scope, replay, transaction, and lifecycle invariants remain intact
* deterministic reconstruction and serialization remain stable where required
* migration, rollout, rollback, compatibility, and observability requirements
  are satisfied where applicable
* all required deterministic checks pass
* required live or external certification is identified separately and bound
  to the exact reviewed revision
* no validated `P1` or `P2` implementation defect remains
* the revision-bound closure record states `remaining_validated_p1_p2: []`
* no required `blocks_approval` or `changes_required` finding remains
* no unresolved external authority or semantic decision prevents completion
* predefined verification evidence is complete, or unavailable evidence is
  recorded without inflating it into a product defect
* no accidental stubs, skipped tests, ignored errors, undocumented TODOs, or
  incomplete fallback paths remain
* no planning/evidence coordinate remains in a behavioral or protocol identity, all
  allowed traceability/migration occurrences are field-specific and ledgered,
  and the field-aware identity gate plus representative mutations pass
* a final review has inspected the entire branch against the design baseline,
  not only the most recent diff

## Work Type: PR Review

A PR-review WorkPlan evaluates a complete pull request as an approval unit. It
does not implement corrections. Use a linked implementation, testing, or
debugging WorkPlan for changes, then review the resulting head revision anew.

### Required PR-Review Sections

In addition to the common sections, include:

* PR identity: repository, number, base/head branches and SHAs, and merge base
* reconstructed requirement and scope ledger
* complete changed-file and generated-artifact inventory
* specialist review results and coordinator dispositions
* workflow identities and local parity evidence
* required-check, review-thread, approval, and mergeability state
* one approval decision: `approve`, `changes_required`, or `blocked`

### PR-Review Completion Contract

A PR review is complete only when:

* the complete base-to-head diff and governing requirements were inspected
* review evidence names the PR head and base while check evidence names the
  actual executed event, SHA, and ref
* the head/base/merge-base and any merge or merge-group result remain current
* `remaining_validated_p1_p2`, `remaining_blocks_approval`, and
  `remaining_changes_required` are all empty only for `approve`
* all actionable review threads are resolved or explicitly dispositioned
* for `approve`, every required check and aggregate is green on its actual
  current executed ref and every scope-required manual or external acceptance
  gate has revision-bound evidence
* for `changes_required` or `blocked`, failed, unavailable, or incomplete check
  and acceptance-gate state is recorded and dispositioned
* local evidence is labeled accurately and is not substituted for CI enforcement
* scope, generated artifacts, migration, compatibility, rollback, and release
  implications are reconciled
* the complete diff passes the identity-hygiene contract, including files,
  symbols, persisted/generated values, tests, fixtures, commands, and workflow
  labels, with only exact ledgered exceptions
* the final decision and any external blocker are explicit

Any change to code, tests, fixtures, generated artifacts, dependencies,
workflows, base revision, merge result, or merge-group composition invalidates
an `approve` decision and requires review of the new approval unit.

## Work Type: Testing

A testing WorkPlan designs and maintains proof topology for approved behavior.
It may add, reorganize, migrate, or retire tests, fixtures, helpers, and CI
gates. It must not invent product semantics or silently weaken coverage.

Use a linked design, implementation, or debugging WorkPlan when test work
reveals that product behavior must change.

### Required Testing Sections

In addition to the common sections, include the following.

#### Test Portfolio

Use:

| Requirement or contract | Behavior and canonical path | Test owner and level | Failure signal | Status |
| ----------------------- | --------------------------- | -------------------- | -------------- | ------ |

Each test must map to a stable requirement, contract, invariant, or supported
failure family. Record whether prior proof is retained, replaced, migrated, or
retired. A green test bound to superseded behavior is stale evidence.

#### Equivalence And Failure Matrix

For each invariant, record applicable positive, negative, boundary, malformed,
retry, replay, concurrency, interruption, migration, rollback, compatibility,
authorization, and resource-limit classes. Mark non-applicable classes with the
design fact that excludes them.

Identify one canonical test owner per failure family. Layered tests are valid
when they observe distinct boundaries; tests that induce the same fault and
observe the same boundary must merge or justify distinct diagnostic value.

#### Suite Topology And Runtime Budget

For each tier, record its purpose, trigger, owner, representative cases, exact
command, measured baseline, budget, and timeout headroom. Use these tiers where
applicable:

* BVT or PR-fast: small deterministic representative sample
* PR-contract: fast public, schema, adapter, and compatibility boundaries
* acceptance: supported end-to-end composition
* slow-exhaustive: family-complete matrices, packaging, restart, migration,
  large artifacts, and subprocess coverage
* benchmark or live: performance or provider evidence, separately governed

Moving a test does not remove its proof obligation. Heavy coverage moved out of
a fast gate must remain enforced at a named cadence and promotion point.

#### Test Asset Inventory

List fixtures, generators, golden files, fakes, mocks, trust material, and
shared setup with:

* stable behavioral owner
* authority and provenance
* production-package isolation requirement
* consumers
* retirement condition

Names must describe durable behavior or protocol identity. Do not use internal
milestones, WorkPlan phases, requirement IDs, review rounds, dates, issue
numbers, or evidence coordinates unless they are values in exact typed
traceability fields or genuine persisted migration identities.

#### Retention And Retirement Ledger

Before deleting or replacing a suite, record every negative and positive family
as retained, migrated, duplicate, obsolete, or intentionally deferred, with its
replacement proof and rationale. Remove obsolete tests, fixtures, imports, CI
paths, and stale WorkPlan references together.

#### Gate Change Log

Record every required-check addition, removal, split, or move, including:

* unique failure signal
* why an existing job cannot own it
* before and after collected count and wall time
* cadence and merge or promotion consequence

Do not create a gate that reruns a broad suite merely to add one unique test.

### Testing Reviewer Responsibilities

During testing work:

* `spec_auditor` confirms the portfolio matches approved requirements without
  inventing semantics
* `correctness_reviewer` checks fixture fidelity, production paths, mocks,
  isolation, and whether tests can pass while behavior is absent
* `test_reviewer` checks equivalence coverage, distinct failure signals,
  retention decisions, suite placement, runtime budgets, and CI enforcement

### Testing Completion Contract

Testing work is complete only when:

* every in-scope requirement or contract has current, non-stale proof
* every retained test has a distinct behavioral or diagnostic failure signal
* high-risk proofs demonstrably fail under a representative counterfactual
* applicable failure and compatibility classes are covered
* mocks and fakes do not bypass the canonical production boundary
* test-only authority and fixtures are excluded from production packages
* obsolete tests, fixtures, helpers, imports, and gate references are removed
* files, symbols, fixtures, and jobs use stable behavioral names
* the field-aware identity gate covers every changed test, fixture, generator,
  registry, timing, and workflow surface and rejects representative delivery-
  coordinate mutations without rejecting legitimate behavioral numerals
* unit tests remain isolated and fast; expensive behavior is placed in an
  explicit slower tier
* BVT and PR-fast gates are measured, small, representative samples rather
  than the complete corpus
* exhaustive deterministic coverage remains enforced outside the fast sample
* before and after counts, wall times, commands, revision, and environment are
  recorded
* deterministic checks and required gate configuration validation pass
* independent final review has no unresolved `changes_required` test-governance
  finding and no validated P1/P2 product defect is mislabeled as a test issue

## Work Type: Debugging

A debugging WorkPlan investigates a specific observed failure and, when
supported by evidence, produces and verifies a fix.

The initial objective is to reduce uncertainty, not immediately edit production
code.

Do not begin with a speculative production fix unless the WorkPlan explains why
reproduction or further isolation is not possible.

### Required Debugging Sections

In addition to the common sections, include the following.

#### Incident Or Symptom

Record:

* observed behavior
* expected behavior
* impact
* frequency
* first known occurrence
* affected environments
* affected versions
* known working environments or versions
* available logs, traces, artifacts, and reports

#### Reproduction Contract

Define:

* reproduction steps
* required environment
* required data or fixtures
* expected signal
* actual signal
* reproducibility rate
* sources of nondeterminism

If reproduction is not possible, record the evidence and limitation explicitly.

#### Timeline

Record relevant:

* deployments
* commits
* configuration changes
* dependency changes
* data changes
* incidents
* prior mitigations
* observations

#### Hypothesis Ledger

Use:

| ID | Hypothesis | Supporting evidence | Contradicting evidence | Experiment | Result | Status |
| -- | ---------- | ------------------- | ---------------------- | ---------- | ------ | ------ |

Valid statuses are:

* proposed
* testing
* supported
* disproved
* superseded
* confirmed root cause

Do not delete disproved hypotheses.

#### Experiment Log

For each experiment, record:

* hypothesis tested
* competing hypotheses distinguished
* procedure
* expected discriminating result
* actual result
* conclusion
* evidence location

Prefer experiments that distinguish among multiple hypotheses.

Avoid experiments that merely collect more undirected data.

#### Root-Cause Statement

A confirmed root-cause statement must explain the causal chain from the defect
or condition to the observed symptom.

Correlation alone is not a root cause.

The statement must identify:

* triggering condition
* defective assumption, state, or behavior
* propagation path
* reason the existing controls or tests did not prevent detection
* observed symptom
* whether a planning/evidence coordinate escaped into a durable identity and which
  missing inventory, review, or static control allowed it

#### Fix Strategy

Describe:

* smallest safe correction
* alternatives considered
* expected side effects
* compatibility risks
* migration implications
* rollback approach

#### Regression Proof

Where feasible, demonstrate:

1. a test or reproducer fails before the fix
2. the same test or reproducer passes after the fix
3. surrounding deterministic checks still pass

When a before-fix run cannot be performed, explain why and provide the strongest
available equivalent evidence.

### Debugging Reviewer Responsibilities

During debugging:

* `spec_auditor` establishes expected behavior and identifies whether the
  incident contradicts the specification or reveals a missing requirement
* `correctness_reviewer` traces causal execution paths, proposes competing
  hypotheses, and challenges the claimed root cause
* `test_reviewer` builds or critiques the reproducer and checks that the
  regression test detects the actual defect rather than a proxy

### Debugging Completion Contract

Debugging is complete only when:

* expected and observed behavior are unambiguous
* the symptom is reproduced, or inability to reproduce is explained with
  evidence
* the root cause is supported by causal evidence
* serious competing hypotheses are disproved or made materially less likely
* the fix addresses the causal mechanism rather than merely hiding the symptom
* a regression test or equivalent verification detects the defect
* before-and-after behavior is demonstrated when feasible
* relevant regression checks pass
* any identity introduced or renamed by the fix is behavioral, the affected
  identity family is inventoried, and the field-aware identity gate passes
* operational, migration, compatibility, and rollback implications are
  addressed where applicable
* remaining uncertainty and follow-up are documented
* no confirmed debugging finding with `blocks_approval` or
  `changes_required` remains

## Non-Convergence

Each WorkPlan must define an iteration or experiment budget.

When the budget is exhausted without satisfying the completion contract:

1. stop speculative work
2. mark the WorkPlan `blocked`
3. summarize attempts and evidence
4. identify what remains unknown
5. identify the smallest additional input, environment, decision, or experiment
   required to continue

Partial completion with explicit uncertainty is preferable to a false claim of
completion.
