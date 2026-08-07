# Semantic Ingestion Design Revision

- Work ID: semantic-ingestion-design-revision-2026-07-26
- Work type: design
- Status: active
- Coordinator: main Codex thread
- Created: 2026-07-26
- Last updated: 2026-07-26, after round-01 reconciliation
- Parent WorkPlan: `docs/work/semantic_ingestion/design-review-2026-07-26.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/design-review-2026-07-26.plan.md`
- Canonical inputs: validated findings from the current review round and the
  frozen `docs/design/semantic_ingestion_architecture.md` baseline
- Expected outputs: the smallest complete revision of
  `docs/design/semantic_ingestion_architecture.md`

## Objective

Resolve every validated finding whose approval disposition is
`blocks_approval` or `changes_required` while preserving correct existing
requirements, architecture decisions, and the ingestion-only scope.

## Completion Contract

Revision is complete only when:

* every validated pre-approval finding has a determinate design correction or
  is explicitly blocked by a named external decision
* every correction maps to stable requirements, measurable acceptance criteria,
  and verification
* no correction weakens an existing invariant or expands into retrieval,
  agents, production implementation, or unrelated cleanup
* the revised design has a new recorded SHA-256 baseline
* a fresh whole-design review uses new reviewer instances

## Scope

Included:

* corrections required by reconciled current-round findings
* local consistency and traceability updates required by those corrections
* removal of contradictory design statements made obsolete by a correction

Excluded:

* unvalidated reviewer preferences
* P3 follow-ups
* production and test implementation
* query and retrieval architecture
* agent integration
* speculative generalization

Explicitly deferred:

* any finding whose disposition is `follow_up`
* implementation WorkPlan creation

## Constraints And Invariants

* One writer owns the canonical design.
* The writer must inspect governing sources and repository evidence directly.
* Corrections must be the smallest complete changes that close validated
  findings.
* Existing satisfied requirements must not regress.
* No externally visible or persisted behavior may be invented.
* The revision budget is three rounds total, including the initial round.
* No live provider call or GitHub workflow is permitted.

## Sources Of Truth

Use the same source precedence as the linked review WorkPlan. The reconciled
review report defines which defects require correction but cannot override a
higher-precedence governing requirement.

## Current State

Verified facts:

* The initial design baseline SHA-256 is
  `3d7f1f045d32a8c13504fc501d8265c1c62f2ef1b5d3d76e4a061efece39d957`.
* DREV-001 through DREV-009 are validated in round 01.
* DREV-001 and DREV-002 require external governing decisions.
* DREV-003 through DREV-007 have determinate design corrections.
* DREV-008 permits strict numeric domains and policy-artifact binding, but its
  substantive initial values require product/ML acceptance approval.
* DREV-009 permits a resource/admission contract, but supported profiles depend
  on the DREV-001 ownership/deployment decision.
* The canonical design has not been modified during the initial review.

Interpretation:

* The design writer may close determinate contract gaps but must preserve
  explicit external blockers rather than inventing their answers.

## Assumptions And Open Questions

Verified facts:

* Product priority does not itself determine the review outcome.

Working assumptions:

* Most validated findings will have determinate corrections supported by
  existing requirements.

Unresolved questions:

* Which findings, if any, require external semantic decisions.

Decisions requiring external input:

* None known before round-01 reconciliation.

## Milestones Or Experiments

### Milestone 1: Reconcile Revision Scope

Purpose: freeze the exact set of validated pre-approval findings.

Bounded scope: round-01 findings only.

Expected artifacts: finding-to-requirement correction ledger.

Verification method: coordinator evidence validation.

Status: complete.

### Milestone 2: Revise Canonical Design

Purpose: implement the smallest complete design correction.

Bounded scope: frozen validated findings and necessary consistency edits.

Expected artifacts: revised canonical design and updated traceability.

Verification method: targeted static audit followed by a fresh whole-design
review.

Status: complete for revision 01. Fresh whole-design review is pending.

## Progress Log

### 2026-07-26: WorkPlan creation

Action: linked this revision WorkPlan to the independent review WorkPlan.

Result: revision scope and entry criteria are explicit.

Evidence produced: this WorkPlan.

Effect on current understanding: design edits cannot begin before findings are
independently produced and reconciled.

Next action: superseded by round-01 reconciliation.

### 2026-07-26: Revision scope frozen

Action: admitted DREV-003 through DREV-009 for bounded correction and retained
DREV-001/DREV-002 as explicit external blockers.

Result: the writer has a closed correction set and may not select ownership,
equal-version replay, local model artifacts, resource-profile values, or
statistical policy values without external authority.

Evidence produced: `docs/reviews/semantic_ingestion/review-round-01.md`.

Effect on current understanding: internal revision can improve implementation
readiness but cannot produce final approval.

Next action: one design writer updates the canonical design for DREV-003 through
DREV-009 without inventing blocked values.

### 2026-07-26: Revision 01 completed

Action: one writer added the authenticated ingress, governed snapshot, egress
governance, graph observation authorization/paging, policy-baseline, and local
resource/admission contracts. The coordinator returned undefined-field and
replay/pagination consistency defects to the same writer and verified their
correction.

Result: revised design SHA-256 is
`376a0d774bc951c5fd4190b165006f138c05f3145e9ad697d94b65f7760e3a17`.

Evidence produced: the canonical design delta and successful `git diff --check`.

Effect on current understanding: determinate round-01 findings have design
paths; external decisions remain visible.

Next action: wait for fresh round-02 whole-design review.

## Evidence Log

| Evidence | Location | Status |
| --- | --- | --- |
| Parent review plan | `docs/work/semantic_ingestion/design-review-2026-07-26.plan.md` | active |
| Round-01 report | `docs/reviews/semantic_ingestion/review-round-01.md` | complete |
| Revision baseline | `docs/design/semantic_ingestion_architecture.md` | frozen |

## Decision Log

| Decision | Rationale | Status |
| --- | --- | --- |
| Do not edit before reconciliation | Required independent initial review | active |
| Exclude P3 follow-ups from revision | P3 does not block approval | active |
| Use one canonical writer | Prevent conflicting semantics | active |

## Review Log

Round-01 revision scope is frozen to DREV-003 through DREV-009. DREV-001 and
DREV-002 remain external blockers.

## Risks And Stop Conditions

Risks:

* A narrow correction may leave contradictory text elsewhere in the large
  design.
* A reviewer recommendation may exceed governing requirements.
* A correction may accidentally weaken a previously satisfied invariant.

Mitigations:

* Search the whole design for every changed contract and term.
* Reconstruct traceability after revision.
* Run fresh whole-design reviewers rather than a diff-only review.

Stop conditions:

* Stop blocked if a validated finding requires an unresolved external semantic
  decision.
* Stop after the third review round if approval does not converge.

## Outcome And Retrospective

Final result: pending.

Evidence supporting the result: pending.

Remaining limitations: pending.

Follow-up work: pending.

Lessons for future operations: pending.
