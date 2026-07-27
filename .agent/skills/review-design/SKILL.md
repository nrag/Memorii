FILE: `.agents/skills/review-design/SKILL.md`

---

name: review-design
description: Independently review a Memorii technical design for requirement completeness, internal consistency, architectural fit, feasibility, failure behavior, security, operability, and verifiability. Produce evidence-backed findings without editing the canonical design.
-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# Review A Memorii Design

Perform an independent, evidence-backed review of a technical design.

This workflow is read-only by default.

Do not edit the canonical design, governing specifications, production code, or
tests while conducting the review.

Produce a review report. Confirmed findings may later be addressed through a
separate `$build-design` workflow.

## Required Inputs

Read:

* root `AGENTS.md`
* `.agent/PLANS.md`
* the target design
* the active design-review WorkPlan, if one exists
* governing documents selected through the repository knowledge router
* relevant production code and tests
* referenced incidents, benchmarks, prototypes, or prior decisions

Do not assume the design is correct merely because it is marked complete or
approved.

Do not assume the implementation is correct merely because tests pass.

Do not use prior review findings until after completing an independent first
pass. This reduces anchoring on previous reviewers.

## Review Modes

Classify the review as one of:

* `full`
* `delta`
* `targeted`

### Full Review

Review the entire design and all material requirements.

Use this mode before design approval, implementation planning, or a major
architecture commitment.

### Delta Review

Review changes between two identified design revisions.

Also inspect enough surrounding context to determine whether the change creates
inconsistencies elsewhere in the design.

Do not limit the review to changed lines when the affected semantics extend
beyond them.

### Targeted Review

Review one explicitly identified concern, such as:

* persistence
* idempotency
* concurrency
* lifecycle semantics
* security
* retrieval
* migration
* rollback
* observability
* benchmark validity
* implementation feasibility

A targeted review must not make a whole-design approval claim.

## Review WorkPlan

For a full or long-running review, create or resume a WorkPlan whose work type
is `design-review`.

Store it under:

```
docs/work/<work-id>/design-review.plan.md
```

A small targeted review may produce only a review report unless repository or
user instructions require a WorkPlan.

The WorkPlan must identify:

* target design path
* frozen design revision
* review mode
* review scope
* governing sources
* excluded areas
* expected report location
* review budget
* exactly one next action

## Review Output

Write the review report to:

```
docs/reviews/<design-id>/<review-id>.md
```

Do not overwrite an earlier review report.

The report must identify the exact design baseline being reviewed.

## Phase 1: Freeze The Review Baseline

Record:

* design path
* design title
* design revision, commit, checksum, or timestamp
* review mode
* included scope
* excluded scope
* governing source documents
* relevant implementation revision
* known external decisions
* prior review reports, if any
* review date

Do not review a moving target.

If the design changes during review:

1. complete the current report against the recorded baseline, or
2. explicitly abandon the current review and restart against the new baseline

Do not silently mix evidence from multiple design revisions.

## Phase 2: Reconstruct The Intended Requirements

Before trusting the requirements listed by the design, independently reconstruct
the expected requirements from governing sources.

Inspect:

* canonical specifications
* related design documents
* implementation rules
* issue or problem statements
* relevant current behavior
* public and persisted contracts
* tests that encode existing expectations
* operational and certification requirements
* explicit user or stakeholder decisions

Create an independent requirements ledger:

| ID | Reconstructed requirement | Source | Design coverage | Acceptance criteria | Finding |
| -- | ------------------------- | ------ | --------------- | ------------------- | ------- |

Classify design coverage as:

* complete
* partial
* missing
* contradictory
* intentionally excluded
* unclear

Do not treat every existing test as a requirement.

Do not treat every existing implementation behavior as intentional.

When code, tests, and documents disagree, apply the source precedence in
`AGENTS.md` and record the disagreement.

## Phase 3: Analyze Repository Reality

Inspect the existing system sufficiently to determine whether the design is
grounded in the repository.

Identify applicable:

* package and component ownership
* production composition roots
* public APIs
* persisted models
* event models
* transaction boundaries
* state transitions
* retrieval paths
* provider boundaries
* prompt contracts
* adapters and integrations
* command-line entry points
* configuration
* tests
* deployment and operational behavior

Determine whether the design:

* changes the correct canonical owner
* duplicates an existing abstraction
* bypasses an existing contract
* assumes a capability that does not exist
* relies on behavior contradicted by production code
* requires an unstated migration
* creates incompatible mixed-version behavior
* violates a universal Memorii invariant

Do not reject a design merely because implementation work will be substantial.

Do identify implementation difficulty that creates material feasibility,
migration, safety, or sequencing risk.

## Phase 4: Review The Design Across All Lanes

Evaluate every applicable review lane.

### 1. Problem And Scope

Check whether:

* the problem is concrete
* affected users or systems are identified
* current and desired behavior are distinguishable
* success is observable
* scope and non-goals are explicit
* the design solves the stated problem
* the design introduces unrelated scope

### 2. Requirements

Check whether:

* requirements have stable identifiers
* requirement sources are traceable
* acceptance criteria are measurable
* externally visible behavior is explicit
* persisted behavior is explicit
* security-sensitive behavior is explicit
* operational behavior is explicit
* negative and unsupported behavior is defined
* requirements do not contradict each other

### 3. Internal Consistency

Check whether:

* terminology is used consistently
* diagrams agree with prose
* examples agree with normative requirements
* schemas agree with described behavior
* state transitions are complete
* error behavior is consistent across sections
* assumptions are not later presented as guarantees
* non-goals do not contradict requirements

### 4. Architectural Fit

Check whether the design preserves:

* domain ownership
* typed public and persisted contracts
* candidate versus committed state
* structural graph versus belief overlay
* execution graph versus solver graph
* routing versus retrieval planning
* observation versus derived projection
* transport versus semantic validation
* production versus benchmark-oracle isolation
* core versus framework-specific integration boundaries

Check whether the design introduces:

* bypass paths
* duplicated sources of truth
* implicit global state
* hidden coupling
* circular dependencies
* unowned abstractions
* framework leakage into core contracts
* untyped dictionary-based public or persisted state

### 5. Data, State, And Lifecycle

Check whether the design defines applicable:

* identifiers
* ownership
* creation
* validation
* candidate state
* committed state
* visibility
* revision
* supersession
* deletion or retention
* provenance
* reconstruction
* serialization
* replay
* temporal validity
* lifecycle transitions

Check for states that can be entered but not exited.

Check for transitions that can occur without validation or evidence.

### 6. Transactions, Concurrency, And Recovery

Check whether the design addresses applicable:

* atomicity
* idempotency
* retry behavior
* duplicate delivery
* partial failure
* crash recovery
* stale work
* lease ownership
* fencing
* ordering
* concurrent mutation
* consistency
* process restart
* rollback
* terminal exhaustion

Require explicit behavior for failures between material steps.

Do not accept “retry” as sufficient without defining identity, ownership,
visibility, and side-effect behavior.

### 7. Security, Privacy, And Trust

Check whether the design defines applicable:

* trust boundaries
* authentication
* authorization
* caller identity
* tenant and scope isolation
* provenance
* evidence validation
* model-output validation
* sensitive-data handling
* persisted failure sanitization
* audit behavior
* unsafe input behavior
* privilege boundaries
* framework and adapter isolation

Check whether a model, adapter, benchmark, or integration can bypass canonical
validation or persistence contracts.

### 8. Failure Behavior

Check whether the design addresses:

* malformed input
* unsupported values
* insufficient evidence
* ambiguous identity
* provider failure
* schema failure
* semantic failure
* partial output
* timeout
* resource exhaustion
* unavailable dependency
* corrupt persisted state
* incompatible version
* interrupted operation

Unknown and insufficient-evidence outcomes must remain valid where applicable.

The design must fail closed where guessing would mutate truth, broaden scope, or
cross a trust boundary.

### 9. Operations And Evolution

Check whether the design defines applicable:

* deployment sequence
* feature flags
* migration
* backfill
* rollback
* mixed-version behavior
* compatibility
* observability
* metrics
* logs
* alerts
* operational ownership
* resource limits
* performance expectations
* capacity assumptions
* recovery procedures

Check whether operators can distinguish:

* success
* partial success
* abstention
* retryable failure
* terminal failure
* stale work
* corrupt state

### 10. Verification And Testability

Check whether every material requirement can be verified.

Look for:

* requirements without verification methods
* acceptance criteria that depend on subjective judgment
* failure behavior with no deterministic test strategy
* concurrency claims with no contention or fencing tests
* migration claims with no mixed-version tests
* rollback claims with no rollback evidence
* benchmark claims with no revision-bound artifact policy
* mocks that would bypass the behavior being validated
* properties requiring live evidence but described as unit-test guarantees

Keep these evidence classes distinct:

* deterministic unit and contract tests
* integration and process-level tests
* fake-oracle evaluation
* live runtime evaluation
* agent-level evaluation
* operational evidence

### 11. Implementation Readiness

Determine whether an implementation team can proceed without relying on hidden
conversation context.

Check whether the design identifies:

* affected components
* canonical owners
* contract changes
* persistence changes
* sequencing
* compatibility
* migration
* rollout
* rollback
* verification
* unresolved decisions
* explicitly deferred work

A design is not implementation-ready when a material semantic choice would have
to be invented by the implementer.

### 12. Complexity And Alternatives

Check whether:

* complexity is proportional to the problem
* simpler serious alternatives were considered
* new abstractions have clear ownership
* the design creates unnecessary generality
* the design assumes future use cases without evidence
* the selected approach has an explicit rationale
* rejected alternatives were rejected for substantive reasons

Do not report a style preference as a design defect.

## Phase 5: Run Independent Reviewers

Run these reviewers concurrently:

* `spec_auditor`
* `correctness_reviewer`
* `test_reviewer`

Give every reviewer:

* the frozen design baseline
* review mode and scope
* governing sources
* relevant code and test paths
* the required finding format
* the canonical finding-classification contract from `AGENTS.md`

Do not give one reviewer another reviewer's findings before its independent pass
is complete.

Tell every reviewer explicitly that product priority, approval disposition, and
finding type are independent. Reviewers must not use `Blocking`, `High`,
`Medium`, or `Low` as severity labels or infer P1 from an approval blocker.

### Spec Auditor Mandate

Ask `spec_auditor` to focus on:

* reconstructed requirements
* missing requirements
* contradictions
* undefined terms
* hidden assumptions
* scope leakage
* incomplete acceptance criteria
* inconsistencies among prose, schemas, diagrams, and examples

### Correctness Reviewer Mandate

Ask `correctness_reviewer` to focus on:

* architecture
* feasibility
* state and lifecycle correctness
* transactions
* concurrency
* recovery
* security
* trust boundaries
* migration
* compatibility
* integration risks
* failure behavior

### Test Reviewer Mandate

Ask `test_reviewer` to focus on:

* measurable acceptance criteria
* requirement-to-evidence coverage
* negative and boundary behavior
* failure and retry cases
* concurrency testing
* migration and rollback testing
* benchmark validity
* observability
* whether proposed tests would prove the actual claims

Wait for all reviewers.

## Required Finding Format

Every proposed finding must include:

* Finding ID
* Title
* Product priority
* Approval disposition
* Confidence
* Finding type
* Affected scenario and prevalence evidence
* Design location
* Governing source or requirement
* Expected behavior
* Design behavior
* Evidence
* Impact
* Recommended resolution
* Verification needed

A proposed finding that omits any required classification field is incomplete
and must be returned to the reviewer before reconciliation. The coordinator
must not guess a missing product priority or derive it from approval
disposition.

Use finding IDs:

```
DREV-001
DREV-002
DREV-003
```

### Product Priority

Use:

#### P1

Mainstream scenarios are broken. The defect affects the ordinary, default, or
dominant path, approximately the 90% use case, and blocks shipping.

The finding must identify the mainstream scenario and provide repository,
product, usage, or governing-requirement evidence that it is mainstream.

#### P2

Mainstream scenarios work, but an important case is broken, approximately the
remaining 10%. Shipping with the defect is not advisable.

The finding must identify the important case and explain its material user or
operator impact.

#### P3

The issue concerns fit, finish, clarity, diagnostics, ergonomics,
maintainability, or polish. The product remains correct and high quality
without the change.

#### Not Applicable

Use when the finding concerns review governance, conflicting source authority,
a missing external decision, or another approval concern without demonstrated
product-behavior impact.

The 90% and 10% figures are decision heuristics, not statistical claims unless
the evidence supports a measured claim. Do not classify a finding as P1 solely
because it concerns a critical invariant, security, persistence, architecture,
or an external decision.

### Approval Disposition

Use:

* `blocks_approval`: Safe approval or implementation cannot proceed because a
  governing conflict, missing external decision, infeasible architecture, or
  unresolved core objective prevents a determinate correction.
* `changes_required`: The correction is determinate and must be made before
  approval.
* `follow_up`: The finding does not prevent approval and may be handled later.

Product priority does not mechanically determine approval disposition. A
finding may be `Not applicable` and `blocks_approval`, or `P2` and
`changes_required`. A confirmed P1 normally requires a pre-approval change, but
the report must still record both dimensions rather than collapsing them.

Use only these combinations:

| Product priority | Allowed approval dispositions |
| ---------------- | ----------------------------- |
| `P1`             | `blocks_approval`, `changes_required` |
| `P2`             | `blocks_approval`, `changes_required` |
| `P3`             | `follow_up` |
| `Not applicable` | `blocks_approval`, `changes_required`, `follow_up` |

If a proposed P3 must be corrected before safe implementation or approval,
reject the classification and re-evaluate its demonstrated product impact or
whether it is a `Not applicable` approval concern.

### Confidence

Use:

* high
* medium
* low

Low-confidence observations must not block approval without additional evidence.

## Phase 6: Reconcile Findings

The coordinator must validate every proposed finding.

For each finding:

1. inspect the cited design section
2. inspect the governing source
3. inspect relevant code or tests when applicable
4. challenge the claimed impact
5. challenge the claimed product priority and prevalence evidence
6. validate the approval disposition independently of product priority
7. check for duplication
8. check whether the issue is intentionally excluded
9. check whether the recommendation introduces larger problems

Classify each finding as:

* confirmed
* duplicate
* unsupported
* already addressed
* accepted limitation
* design ambiguity
* outside review scope
* blocked by missing evidence

Only confirmed findings appear in the main findings section.

Preserve rejected findings in an appendix with their dispositions when that
history would help future reviewers.

Do not convert a reviewer preference into a requirement.

## Phase 7: Build The Coverage And Risk Views

The final report must include a requirements coverage matrix:

| Requirement | Source | Design section | Acceptance criteria | Verification strategy | Status |
| ----------- | ------ | -------------- | ------------------- | --------------------- | ------ |

Use these statuses:

* covered
* partially covered
* missing
* contradictory
* excluded
* unclear

Also include a risk register:

| Risk | Trigger | Impact | Mitigation in design | Residual risk | Status |
| ---- | ------- | ------ | -------------------- | ------------- | ------ |

Include only material risks.

## Phase 8: Determine The Review Outcome

Use one of these outcomes:

### Approved

Use only when:

* no confirmed finding with `blocks_approval` or `changes_required` remains
* every in-scope requirement is traceable
* acceptance criteria are measurable
* material architectural and operational choices are explicit
* implementation does not require hidden semantic decisions
* verification covers every material requirement

P3 findings with `follow_up` may remain.

### Approved With Follow-Ups

Use only when:

* no finding with `blocks_approval` or `changes_required` remains
* remaining `follow_up` findings do not affect safe implementation
* each follow-up has an owner or destination
* the design remains implementation-ready

### Changes Required

Use when:

* any confirmed `changes_required` finding remains
* requirement coverage is incomplete
* acceptance criteria are not sufficient
* implementation would require inventing material behavior
* migration, compatibility, security, or operational behavior is incomplete

### Blocked

Use when the review cannot be completed because:

* governing sources conflict
* a required external decision is missing
* necessary repository evidence is unavailable
* the design baseline cannot be identified
* the review scope is not sufficiently defined

A blocked review is not an approval or rejection of the design.

## Phase 9: Write The Review Report

Use this structure:

```markdown id="6fk5cw"
# Design Review: <Design Title>

## Review Metadata

- Review ID:
- Review mode:
- Review outcome:
- Design path:
- Design baseline:
- Implementation baseline:
- Review date:
- Reviewers:
- Included scope:
- Excluded scope:

## Executive Assessment

Summarize:

- what the design proposes
- whether it solves the stated problem
- whether it is implementation-ready
- the most important strengths
- the most important unresolved risks
- the review outcome

## Governing Sources

List the sources used and their precedence.

## Independently Reconstructed Requirements

Include the reconstructed requirements ledger.

## Confirmed Findings

### DREV-001: <Title>

- Product priority:
- Approval disposition:
- Confidence:
- Finding type:
- Affected scenario and prevalence evidence:
- Design location:
- Governing source:
- Expected behavior:
- Design behavior:
- Evidence:
- Impact:
- Recommended resolution:
- Verification needed:

## Requirements Coverage

Include the requirements coverage matrix.

## Architecture And Feasibility Assessment

Summarize:

- architectural fit
- affected ownership boundaries
- implementation feasibility
- sequencing risks
- material assumptions

## Failure, Security, And Operational Assessment

Summarize:

- failure behavior
- concurrency and recovery
- security and trust boundaries
- migration and compatibility
- deployment, rollback, and observability

## Verification Assessment

Summarize:

- testability
- missing verification strategies
- required deterministic checks
- required integration, live, or operational evidence

## Risk Register

Include the material risk register.

## Rejected Or Consolidated Findings

Record proposed findings that were:

- duplicates
- unsupported
- already addressed
- outside scope
- accepted limitations

Include the disposition rationale.

## Required Changes Before Approval

List only confirmed changes required for approval.

Every item must reference a finding ID.

## Non-Blocking Follow-Ups

List findings whose approval disposition is `follow_up`.

## Final Outcome

State one:

- Approved
- Approved with follow-ups
- Changes required
- Blocked

Explain the evidence supporting the outcome.

## Review Limitations

State what was not inspected or could not be verified.
```

## Phase 10: Close Or Hand Off

A design-review operation is complete when:

* the design baseline is frozen and recorded
* governing sources have been identified
* requirements have been independently reconstructed
* all applicable review lanes have been evaluated
* all three independent reviewers have completed their passes
* findings have been validated and reconciled
* requirement coverage and material risks are recorded
* the report has one explicit outcome
* review limitations are visible
* the report can be understood without hidden conversational context

Do not edit the canonical design as part of this Skill.

When the outcome is `Changes required`:

1. identify the confirmed findings that must be resolved
2. recommend creating or resuming a linked `$build-design` WorkPlan
3. use the review report as an input to that WorkPlan
4. require a new `$review-design` run against the revised design baseline

Do not mark an earlier review report approved after the design changes.

Every new design revision requires a new review baseline and report.

Do not claim that the design has no possible defects.

State only that no unresolved validated findings remain under the recorded
scope, sources, and review method.
