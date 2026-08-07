# Semantic Ingestion Internal Closure Revision

- Work ID: semantic-ingestion-internal-closure-revision-2026-07-26
- Work type: design
- Status: blocked
- Coordinator: main Codex thread
- Created: 2026-07-26
- Last updated: 2026-07-26, final round-04 reconciliation
- Parent WorkPlan: `docs/work/semantic_ingestion/design-review-internal-closure-2026-07-26.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/design-review-internal-closure-2026-07-26.plan.md`
- Canonical inputs: coordinator-validated findings from the linked review
- Expected outputs: the smallest complete corrections to
  `docs/design/semantic_ingestion_architecture.md`

## Objective

Close every coordinator-confirmed internal P1/P2 semantic-ingestion design gap
while preserving correct requirements and all registered external-decision
boundaries.

## Completion Contract

Revision is complete only when every admitted finding has a determinate,
traceable correction; the design has a new recorded digest; acceptance and
verification are measurable; no correct invariant regresses; and a fresh
whole-design review uses new reviewer instances. A revision cannot be declared
complete merely because its targeted text changed.

## Scope

Included: only findings confirmed by the linked review and minimum consistency
edits required by their corrections.

Excluded: external-decision selection, implementation, tests, retrieval/query,
agent integration, P3 polish, compatibility paths, and unrelated cleanup.

Explicitly deferred: implementation planning and external-decision resolution.

## Constraints And Invariants

* One writer owns the canonical design.
* The writer reads governing requirements and repository evidence directly.
* No external value, topology, replay rule, threshold, or policy may be
  invented.
* Every corrected contract must be typed, fail closed, and independently
  verifiable.
* No live provider call or GitHub workflow is permitted.
* The shared budget is at most three revisions.

## Sources Of Truth

Use the precedence and source set in the linked review WorkPlan. Review
findings are advisory and cannot override higher-precedence requirements.

## Current State

Verified facts:

* Repository baseline:
  `44cd7773a75ac8545ddcf799c76dc94c0240f788`.
* Design baseline:
  `c80a83e3281e020cdcaf971f5ef3c95fa36ed96a26542b90f882dee7e7ed833e`.
* SIC-001 through SIC-005 are coordinator-confirmed in the linked round-01
  report.
* Revision 01 was frozen and reviewed against its exact digest.
* Round 02 confirms SIC-006 and SIC-007 as the complete revision-02 scope.

Interpretation: one writer may revise only the contracts and consistency
surfaces required to close SIC-001 through SIC-005.

## Assumptions And Open Questions

Verified facts: product priority and approval disposition are independent.

Working assumptions: confirmed internal gaps can be corrected without choosing
external decisions.

Unresolved questions: the exact validated finding inventory.

Decisions requiring external input: the three registered `SIA-ED-*`
decisions, which are excluded from this revision.

## Milestones Or Experiments

### Milestone 1: Freeze Revision Scope

Purpose: admit only coordinator-confirmed internal findings.

Bounded scope: linked round-01 report.

Expected artifacts: finding-to-requirement correction ledger.

Verification method: coordinator evidence validation.

Status: complete.

### Milestone 2: Revise And Verify

Purpose: apply the smallest complete correction with one writer.

Bounded scope: frozen admitted findings.

Expected artifacts: revised design, updated traceability, new digest, and fresh
whole-design review.

Verification method: static consistency checks plus three new reviewers.

Status: complete; final revision is frozen and under review.

## Progress Log

### 2026-07-26: WorkPlan creation

Action: linked a new design-revision operation to the independent internal
closure review.

Result: design edits remain prohibited until round-01 findings are reconciled.

Evidence produced: this WorkPlan.

Effect on current understanding: no historical finding is automatically
admitted.

Next action: wait for coordinator-validated round-01 findings.

### 2026-07-26: Revision 01 completed

Action: one writer revised only the canonical design for SIC-001 through
SIC-005. Coordinator checks returned incomplete duplicate identity,
carrier-field, and traceability details to that same writer before freeze.

Result: the design now has one stable delivery identity contract, separately
typed session authorization, explicit governance/message carriers across all
named boundaries, atomic cross-route message admission, one canonical execution
graph, and deterministic all-unit reverse traceability with an independent
checker.

Evidence produced: design SHA-256
`4cd6775a3d14daf4760a8476584d5964213dad40f1d67b0b905e37c69dd59fc5`,
13,651 lines, and clean `git diff --check`.

Effect on current understanding: revision 01 closes its frozen scope subject to
fresh whole-design review.

Next action: wait for round-02 review reconciliation.

### 2026-07-26: Revision 02 scope frozen

Action: reconciled round-02 reviewer findings and admitted only SIC-006 and
SIC-007.

Result: revision 02 may define the global canonical typed-value profile and
complete structural/evidence traceability across authoritative Sections 1-5.
It may not choose any registered external decision or alter runtime semantics.

Evidence produced:
`docs/reviews/semantic_ingestion/internal-closure/review-round-02.md`.

Effect on current understanding: one P2 and one governance correction remain;
no internal P1 remains on revision 01.

Next action: assign the same sole writer to SIC-006 and SIC-007, then freeze
and independently review revision 02.

### 2026-07-26: Revision 02 completed

Action: the sole writer added the one global canonical typed-value profile and
closed authoritative structural and executable-evidence traceability for
SIC-006 and SIC-007. The coordinator verified all affected contracts and stale
forms before freeze.

Result: all admitted internal findings now have complete design corrections;
fresh whole-design approval remains mandatory.

Evidence produced: design SHA-256
`4c4d2a4708358838d77b5d8da375f65d5f86da9283bcbb9ff1e47ff39fb90709`,
14,018 lines, and clean `git diff --check`.

Effect on current understanding: revision 02 consumes the second of at most
three revisions and is ready for round-03 review.

Next action: wait for round-03 whole-design review reconciliation.

### 2026-07-26: Revision 03 scope frozen

Action: reconciled round-03 findings and admitted only SIC-008, SIC-009, and
SIC-010. Implementation-absence observations were rejected from design scope.

Result: the final revision may correct text coordinate spaces, segment language
routing, and all-scope outcome authorization. It may not alter retrieval/query,
choose an external decision, or add unrelated implementation work.

Evidence produced:
`docs/reviews/semantic_ingestion/internal-closure/review-round-03.md`.

Effect on current understanding: three P2 corrections remain and no P1 remains.

Next action: assign the same sole writer to SIC-008 through SIC-010, freeze
revision 03, and run the final fresh whole-design review.

### 2026-07-26: Revision 03 completed

Action: the sole writer implemented the typed text-artifact mapping,
per-segment language-route/resource, and complete required-scope authorization
contracts. The coordinator verified all downstream carriers, evidence,
persistence, replay, observation, outcome, and acceptance surfaces.

Result: all admitted internal findings are corrected in the design. The third
revision is frozen and no additional revision is available.

Evidence produced: design SHA-256
`4c8884214e73b580aa4f9ae0ee21cf62a4bc1b1e284121c6560dd063c1b29f19`,
14,497 lines, and clean `git diff --check`.

Effect on current understanding: only final independent approval and the three
registered external decisions remain.

Next action: wait for the final round-04 whole-design review.

### 2026-07-26: Final review did not converge

Action: reconciled the final fresh whole-design review against revision 03.

Result: SIC-011 remains: result-access prose invokes the all-scope authorizer
with the scalar-scope admission/recovery request type. No fourth revision is
permitted in this operation.

Evidence produced:
`docs/reviews/semantic_ingestion/internal-closure/review-round-04.md`.

Effect on current understanding: revision 03 closed SIC-008 through SIC-010,
but introduced one narrow P2 request-type contradiction.

Next action: stop and request a new bounded revision operation for SIC-011.

## Evidence Log

| Evidence | Location | Status |
| --- | --- | --- |
| Linked review plan | `docs/work/semantic_ingestion/design-review-internal-closure-2026-07-26.plan.md` | active |
| Round-01 report | `docs/reviews/semantic_ingestion/internal-closure/review-round-01.md` | complete |
| Revision-01 design digest | `4cd6775a3d14daf4760a8476584d5964213dad40f1d67b0b905e37c69dd59fc5` | complete |
| Round-02 report | `docs/reviews/semantic_ingestion/internal-closure/review-round-02.md` | complete |
| Revision-02 design digest | `4c4d2a4708358838d77b5d8da375f65d5f86da9283bcbb9ff1e47ff39fb90709` | complete |
| Round-03 report | `docs/reviews/semantic_ingestion/internal-closure/review-round-03.md` | complete |
| Revision-03 design digest | `4c8884214e73b580aa4f9ae0ee21cf62a4bc1b1e284121c6560dd063c1b29f19` | complete |
| Round-04 report | `docs/reviews/semantic_ingestion/internal-closure/review-round-04.md` | complete; one P2 unresolved |

## Decision Log

Revision 03 corrected only SIC-008 through SIC-010 and is frozen.

## Review Log

No revision review has occurred.

## Blockers And Limits

Current blocker: SIC-011 requires a new explicitly authorized revision
operation; no revision remains in this operation.

Iteration budget: shared maximum of three design revisions.

Rounds used: three of three; no further revision is permitted.

## Next Action

Stop. Do not revise again without explicit authorization for SIC-011.

## Outcome And Retrospective

Blocked after three revisions. SIC-011 and the three registered external
decisions remain; all other admitted internal findings are closed.
