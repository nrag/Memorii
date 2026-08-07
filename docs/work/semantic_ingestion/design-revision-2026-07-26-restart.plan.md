# Semantic Ingestion Design Revision Restart

- Work ID: semantic-ingestion-design-revision-2026-07-26-restart
- Work type: design
- Status: blocked
- Coordinator: main Codex thread
- Created: 2026-07-26
- Last updated: 2026-07-26, revision-03 completion and final review
- Parent WorkPlan: `docs/work/semantic_ingestion/design-review-2026-07-26-restart.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/design-review-2026-07-26-restart.plan.md`
- Canonical inputs: coordinator-validated findings from the restarted review
- Expected outputs: the smallest complete correction to
  `docs/design/semantic_ingestion_architecture.md`

## Objective

Resolve every validated finding that prevents approval while preserving all
correct ingestion requirements and avoiding query/retrieval or agent scope.

## Completion Contract

Revision is complete only when every validated pre-approval finding has either
a determinate correction or a precisely named external blocker; corrections
are traceable to requirements, measurable acceptance, and verification; no
existing invariant regresses; the revised design has a new recorded digest;
and a fresh full review uses new reviewer instances.

## Scope

Included: only validated findings from the linked restarted review and the
minimum consistency edits required by their corrections.

Excluded: production implementation, tests, retrieval/query design, agent
integration, P3 follow-ups, speculative generalization, and unrelated cleanup.

Explicitly deferred: implementation planning after design approval.

## Constraints And Invariants

* Exactly one design writer edits the canonical document.
* The writer verifies governing requirements and repository evidence directly.
* No externally visible or persisted semantics may be invented.
* External blockers remain explicit and fail closed.
* No live provider call or GitHub workflow is permitted.

## Sources Of Truth

Use the precedence and source set in the linked review WorkPlan. Review findings
identify gaps but cannot override higher-precedence requirements.

## Current State

Verified facts:

* Repository baseline:
  `44cd7773a75ac8545ddcf799c76dc94c0240f788`.
* Design baseline:
  `376a0d774bc951c5fd4190b165006f138c05f3145e9ad697d94b65f7760e3a17`.
* DREV-001 through DREV-010 are coordinator-validated in the restarted
  round-01 report.
* DREV-001-DREV-003, DREV-005-DREV-007, and DREV-010 have determinate design
  corrections.
* DREV-004, DREV-008, and DREV-009 require external decisions or approved
  artifacts and must remain explicit blockers.
* The initial read-only review is complete; design revision may begin.

Interpretation: revision scope is frozen to the seven determinate findings.

## Assumptions And Open Questions

Verified facts: approval depends on approval disposition, not product priority
alone.

Working assumptions: confirmed determinate gaps can be corrected locally.

Unresolved questions: none until review reconciliation.

Decisions requiring external input: none admitted yet.

## Milestones Or Experiments

### Milestone 1: Freeze Revision Scope

Purpose: admit only validated pre-approval findings.

Bounded scope: restarted round-01 report.

Expected artifacts: finding-to-requirement correction ledger.

Verification method: coordinator direct-evidence validation.

Status: complete.

### Milestone 2: Revise Canonical Design

Purpose: apply the smallest complete correction with one writer.

Bounded scope: frozen validated findings.

Expected artifacts: revised design and updated traceability.

Verification method: static consistency audit and fresh full review.

Status: pending.
Revision 01 is complete; fresh round-02 review is active.
Revision 02 is active for DREV-R2-001 through DREV-R2-003 only.
Revision 02 is complete; final round-03 review is active.
Revision 03 is active for DREV-R3-001 and DREV-R3-002 only.
Revision 03 is complete. The mandatory post-revision whole-design review found
new internal gaps; the revision budget is exhausted.

## Progress Log

### 2026-07-26: WorkPlan creation

Action: linked a new revision operation to the restarted independent review.

Result: edits cannot begin before round-01 reconciliation.

Evidence produced: this WorkPlan.

Effect on current understanding: no prior interrupted-review finding is
automatically admitted.

Next action: wait for validated round-01 findings.

### 2026-07-26: Revision scope freeze

Action: admitted only coordinator-validated findings from the restarted
round-01 report.

Result: seven determinate corrections are assigned to one design writer; three
external blockers remain unchanged.

Evidence produced: `docs/reviews/semantic_ingestion/review-round-01.md`.

Effect on current understanding: the writer may revise foundational contracts,
ingress authority composition, operation fencing, approval lifecycle, local
admission concurrency, egress CAS, and assessment traceability only.

Next action: one design writer applies the smallest complete correction.

### 2026-07-26: Revision 01 completed

Action: the sole writer revised only the canonical design for the seven frozen
determinate findings.

Result: foundational types, ingress authority composition, operation fencing,
approval lifecycle, local reservation, egress CAS, and implementation baseline
contracts are now explicit. External replay, topology, and statistical-policy
decisions remain fail-closed.

Evidence produced: design SHA-256
`22fa2e5688d5cae027a843b29e7cd4a5fca2c90acb9e3e5a470a29ea4146818a`,
12,633 lines, and clean `git diff --check`.

Effect on current understanding: a fresh whole-design review must verify actual
closure and detect regressions.

Next action: round-02 independent review.

### 2026-07-26: Revision-02 scope freeze

Action: reconciled round-02 findings and admitted three determinate corrections.

Result: revision 02 is limited to terminal-result fence closure,
production-owned deployment authorization isolation, and a canonical external
decision register. The writer may not choose the topology, replay, or
statistical-policy decisions.

Evidence produced: `docs/reviews/semantic_ingestion/review-round-02.md`.

Effect on current understanding: this is the final revision allowed by the
three-round review budget.

Next action: resume the same sole design writer.

### 2026-07-26: Revision 02 completed

Action: the same sole writer completed terminal-result fence closure, restored
production/acceptance isolation, and added the canonical external-decision
register.

Result: no normative `DREV-*` dependency remains; production owns deployment
authorization verification; all four terminal result variants carry the
operation fence.

Evidence produced: design SHA-256
`1662665b471b6c821773101eae4a627df2034729eab384bff532496d35b1cacf`,
12,798 lines, static searches, and clean `git diff --check`.

Effect on current understanding: only a fresh full review can determine final
approval or external blocking.

Next action: linked final round-03 review.

### 2026-07-26: Revision-03 scope freeze

Action: validated round-03 findings and rejected implementation-only findings.

Result: the final revision is limited to authenticated semantic-result lookup
and independently signed baseline-approval evidence bound into deployment
authorization issuance. External decisions remain untouched.

Evidence produced: `docs/reviews/semantic_ingestion/review-round-03.md`.

Effect on current understanding: this is the third and final permitted design
revision.

Next action: resume the same sole design writer.

### 2026-07-26: Revision 03 completed and reviewed

Action: the same sole writer added authenticated semantic-result lookup and an
independently signed acceptance-owned baseline approval release bound into
production deployment authorization issuance. Three fresh reviewers then
reviewed the complete new baseline.

Result: revision 03 closed its frozen findings. Final coordinator validation
confirmed three different internal gaps: contradictory execution-DAG contracts,
incomplete message-governance carrier closure, and incomplete detailed-clause
traceability. No fourth revision is permitted.

Evidence produced: design SHA-256
`c80a83e3281e020cdcaf971f5ef3c95fa36ed96a26542b90f882dee7e7ed833e`,
13,046 lines, `docs/reviews/semantic_ingestion/review-round-04.md`, and clean
`git diff --check`.

Effect on current understanding: the completed corrections are sound, but the
design as a whole is not approved.

Next action: stop this WorkPlan. A new user-authorized bounded revision is
required to address DREV-R4-001 through DREV-R4-003.

## Evidence Log

| Evidence | Location | Status |
| --- | --- | --- |
| Linked review plan | `docs/work/semantic_ingestion/design-review-2026-07-26-restart.plan.md` | active |
| Round-01 report | `docs/reviews/semantic_ingestion/review-round-01.md` | complete |
| Revision-01 design digest | `22fa2e5688d5cae027a843b29e7cd4a5fca2c90acb9e3e5a470a29ea4146818a` | complete |
| Round-02 report | `docs/reviews/semantic_ingestion/review-round-02.md` | complete |
| Revision-02 design digest | `1662665b471b6c821773101eae4a627df2034729eab384bff532496d35b1cacf` | complete |
| Round-03 report | `docs/reviews/semantic_ingestion/review-round-03.md` | complete |
| Revision-03 design digest | `c80a83e3281e020cdcaf971f5ef3c95fa36ed96a26542b90f882dee7e7ed833e` | complete |
| Final review report | `docs/reviews/semantic_ingestion/review-round-04.md` | complete; changes required |

## Decision Log

The revision scope is DREV-001-DREV-003, DREV-005-DREV-007, and DREV-010.
DREV-004, DREV-008, and DREV-009 remain external blockers.

## Review Log

No revision review has occurred.

## Blockers And Limits

Current blockers: DREV-R4-001 through DREV-R4-003 remain after final review;
external blockers SIA-ED-TOPOLOGY-001, SIA-ED-REPLAY-001, and
SIA-ED-POLICY-001 remain for final approval.

Iteration budget: shared three-round budget with the linked review.

Rounds used: three of three.

## Next Action

Stop. A fourth revision is outside this WorkPlan. The exact next architectural
changes and external actions are recorded in
`docs/reviews/semantic_ingestion/review-round-04.md`.

## Outcome And Retrospective

Revision 03 completed its frozen corrections, but the workflow did not
converge. No requirements were weakened and no unrelated scope was added.
