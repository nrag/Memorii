# Semantic Ingestion Design Review Restart

- Work ID: semantic-ingestion-design-review-2026-07-26-restart
- Work type: design-review
- Status: blocked
- Coordinator: main Codex thread
- Created: 2026-07-26
- Last updated: 2026-07-26, final post-revision review reconciliation
- Parent WorkPlan: `docs/work/semantic_ingestion/design-review-2026-07-26.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/design-revision-2026-07-26-restart.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md`,
  `AGENTS.md`, `.agent/PLANS.md`, `.agent/skills/review-design/SKILL.md`
- Expected outputs: `docs/reviews/semantic_ingestion/review-round-01.md`
  through `review-round-04.md`; round 04 is the mandatory post-third-revision
  review and unresolved-findings report

## Objective

Conduct a fresh, independent, whole-design review from the repository state the
user intentionally committed, and determine whether the semantic-ingestion
architecture is implementation-ready without expanding beyond ingestion.

## Completion Contract

This review is complete only when either:

1. a fresh whole-design round has no validated `blocks_approval` or
   `changes_required` finding, every material requirement is traceable, every
   acceptance criterion is measurable, every material requirement has an
   independent verification strategy, and implementation requires no invented
   material semantics; or
2. three review/revision rounds are exhausted and the final report identifies
   each unresolved finding and the exact external decision, evidence, or
   architectural change required.

Every round requires fresh `spec_auditor`, `correctness_reviewer`, and
`test_reviewer` instances. The coordinator validates every finding against
direct repository evidence.

## Scope

Included:

* the complete semantic-ingestion architecture
* governing ingestion requirements and universal repository invariants
* production ownership and integration feasibility relevant to ingestion
* security, failure, persistence, replay, recovery, operability, and validation
* requirement traceability and measurable acceptance

Excluded:

* production or test implementation
* query and retrieval redesign
* agent integration
* unrelated cleanup
* requirement weakening for approval

Explicitly deferred:

* implementation planning after design approval
* live, paid, or GitHub validation

## Constraints And Invariants

* The initial round is read-only with respect to the design.
* Reviewers receive no prior reports or revision summaries before completing
  their independent pass.
* Product priority and approval disposition use the taxonomy in `AGENTS.md`.
* Only one writer may edit the canonical design between review rounds.
* A changed design or repository revision invalidates the active baseline and
  requires an explicit restart.
* No unrelated working-tree change may be modified or reverted.
* The total budget is three design revisions. Every revision must be followed
  by a fresh whole-design review; the initial read-only review does not consume
  a revision.

## Sources Of Truth

Apply the precedence in `AGENTS.md`. At minimum:

* `docs/design/memorii_spec.md`
* `docs/design/memorii_storage_details.md`
* `docs/design/event_model.md`
* `docs/IMPLEMENTATION_RULES.md`
* `docs/design/memory_evolution_runtime.md`
* `docs/design/prompt_contracts.md`
* `docs/design/latent_graph_simulator.md`
* `docs/plans/engineering_hardening_closure_matrix.md`
* relevant production code and tests

## Current State

Verified facts:

* Branch: `live-benchmark-repair`.
* Repository revision: `44cd7773a75ac8545ddcf799c76dc94c0240f788`.
* Frozen design SHA-256:
  `376a0d774bc951c5fd4190b165006f138c05f3145e9ad697d94b65f7760e3a17`.
* Frozen design size: 12,400 lines.
* The working tree contains pre-existing user changes.
* The user confirmed that the repository revision changed intentionally.
* The review interrupted by that revision change is not approval evidence.

Interpretation:

* The current content hash and repository revision jointly identify round 01.

## Assumptions And Open Questions

Verified facts:

* P1/P2/P3 describe product impact; approval disposition is separate.

Working assumptions:

* Determinate gaps can be corrected without changing governing requirements.

Unresolved questions:

* Whether governing-source conflicts or deployment choices require external
  decisions.

Decisions requiring external input:

* None admitted until independently reproduced and coordinator-validated.

## Milestones Or Experiments

### Milestone 1: Independent Round 01

Purpose: reconstruct requirements and evaluate the complete frozen design.

Bounded scope: read-only review by all three required reviewers.

Expected artifacts: reconciled `review-round-01.md`.

Verification method: reviewer completion plus coordinator evidence validation.

Status: complete. All three reviewers completed. Coordinator validation froze
three P1, four P2, and three `Not applicable` pre-approval findings in
`review-round-01.md`.

### Milestone 2: Fresh Revised-Baseline Review

Purpose: evaluate the complete corrected design with new reviewers.

Bounded scope: up to two further full rounds.

Expected artifacts: `review-round-02.md` and, only if required,
`review-round-03.md`.

Verification method: new repository/design freeze and fresh reviewer instances.

Status: complete but not approved.

Revision 01 produced design SHA-256
`22fa2e5688d5cae027a843b29e7cd4a5fca2c90acb9e3e5a470a29ea4146818a`
at 12,633 lines. All three allowed revisions and their mandatory fresh reviews
are complete. The final baseline is
`c80a83e3281e020cdcaf971f5ef3c95fa36ed96a26542b90f882dee7e7ed833e`
at 13,046 lines. Round 04 records the unresolved internal findings and external
decisions.

## Progress Log

### 2026-07-26: Restarted baseline freeze

Action: confirmed the repository commit with the user and recorded the current
repository revision, design digest, size, scope, and review budget.

Result: round 01 has a stable, explicit baseline.

Evidence produced: this WorkPlan and the hashes in Current State.

Effect on current understanding: the interrupted review is historical evidence
only and cannot determine approval.

Next action: launch the three independent read-only reviewers concurrently.

### 2026-07-26: Round-01 reconciliation

Action: completed all three independent passes and validated every proposed
finding against governing documents, the frozen design, and repository code.

Result: confirmed DREV-001 through DREV-010. DREV-001-DREV-003 and
DREV-005-DREV-007 plus DREV-010 have determinate corrections; DREV-004,
DREV-008, and DREV-009 require external authority.

Evidence produced: `docs/reviews/semantic_ingestion/review-round-01.md`.

Effect on current understanding: the design is blocked but has a bounded local
revision scope.

Next action: activate the linked design-revision WorkPlan and assign one design
writer to the seven determinate findings.

### 2026-07-26: Revision-01 freeze

Action: the sole design writer corrected the seven determinate round-01
findings and preserved all three external blockers.

Result: a revised immutable baseline is available for round 02.

Evidence produced: design SHA-256
`22fa2e5688d5cae027a843b29e7cd4a5fca2c90acb9e3e5a470a29ea4146818a`,
12,633 lines, and clean `git diff --check`.

Effect on current understanding: approval now requires a fresh complete review,
not a delta-only check.

Next action: launch three fresh round-02 reviewers against the revised hash.

### 2026-07-26: Round-02 reconciliation

Action: completed all three fresh whole-design reviews and coordinator
validation.

Result: foundational types, ingress resolver, local reservation, egress CAS,
and baseline traceability are closed. The operation fence is missing from
terminal result variants; production/acceptance isolation regressed; external
decision identifiers are ambiguous. Three external blockers remain.

Evidence produced: `docs/reviews/semantic_ingestion/review-round-02.md`.

Effect on current understanding: one bounded final revision is required before
the third and final review round.

Next action: resume the sole writer for DREV-R2-001 through DREV-R2-003 only.

### 2026-07-26: Revision-02 freeze

Action: the same sole writer closed the three determinate round-02 findings and
preserved the external decisions as stable registered dependencies.

Result: the final design baseline is ready for the third whole-design review.

Evidence produced: design SHA-256
`1662665b471b6c821773101eae4a627df2034729eab384bff532496d35b1cacf`,
12,798 lines, and clean `git diff --check`.

Effect on current understanding: the remaining question is whether only the
three explicit external blockers remain.

Next action: launch the final three fresh reviewers.

### 2026-07-26: Revision-03 freeze and final review

Action: the sole writer closed DREV-R3-001 and DREV-R3-002. The coordinator
froze SHA-256
`c80a83e3281e020cdcaf971f5ef3c95fa36ed96a26542b90f882dee7e7ed833e`
at 13,046 lines, launched three new whole-design reviewers, and validated every
finding.

Result: the final review confirmed DREV-R4-001 through DREV-R4-003 and rejected
implementation-absence findings. The three registered external decisions also
remain unresolved. The design is not approved and the revision budget is
exhausted.

Evidence produced: `docs/reviews/semantic_ingestion/review-round-04.md` and a
clean `git diff --check`.

Effect on current understanding: one P1 and two P2 internal design gaps remain;
no further architecture edit is allowed under this WorkPlan.

Next action: obtain explicit user authorization for a new bounded revision that
closes DREV-R4-001 through DREV-R4-003, and obtain the three external decision
artifacts named in the final report.

### 2026-07-26: Round-03 reconciliation

Action: completed three fresh reviewers and coordinator validation.

Result: confirmed two determinate P2 contract gaps: authenticated result lookup
and independent baseline-approval evidence. Rejected implementation-absence
observations as out of scope. Three external blockers remain.

Evidence produced: `docs/reviews/semantic_ingestion/review-round-03.md`.

Effect on current understanding: two of the allowed three design revisions have
been used. One final revision and its mandatory fresh review remain.

Next action: resume the sole writer for DREV-R3-001 and DREV-R3-002 only.

## Evidence Log

| Evidence | Location or value | Status |
| --- | --- | --- |
| Repository baseline | `44cd7773a75ac8545ddcf799c76dc94c0240f788` | frozen |
| Design baseline | `376a0d774bc951c5fd4190b165006f138c05f3145e9ad697d94b65f7760e3a17` | frozen |
| Round-01 report | `docs/reviews/semantic_ingestion/review-round-01.md` | complete |
| Round-02 design baseline | `22fa2e5688d5cae027a843b29e7cd4a5fca2c90acb9e3e5a470a29ea4146818a` | frozen |
| Round-02 report | `docs/reviews/semantic_ingestion/review-round-02.md` | complete |
| Round-03 design baseline | `1662665b471b6c821773101eae4a627df2034729eab384bff532496d35b1cacf` | frozen |
| Round-03 report | `docs/reviews/semantic_ingestion/review-round-03.md` | complete |
| Final design baseline | `c80a83e3281e020cdcaf971f5ef3c95fa36ed96a26542b90f882dee7e7ed833e` | frozen |
| Round-04 unresolved-findings report | `docs/reviews/semantic_ingestion/review-round-04.md` | complete |

## Decision Log

### 2026-07-26: Restart after intentional commit

Decision: abandon the interrupted review as approval evidence and begin a fresh
round at the confirmed commit.

Alternatives considered: continue the partially completed review across two
repository revisions.

Evidence and rationale: mixed baselines violate `$review-design`.

Consequences: all three round-01 reviewers must be fresh.

Owner: coordinator.

## Review Log

Round 01 used fresh `spec_auditor`, `correctness_reviewer`, and `test_reviewer`
instances. The coordinator confirmed DREV-001 through DREV-010, rejected test
absence as an extra design defect, and preserved three external blockers.

## Blockers And Limits

Current blockers: DREV-R4-001 through DREV-R4-003 and
SIA-ED-TOPOLOGY-001, SIA-ED-REPLAY-001, and SIA-ED-POLICY-001.

Iteration budget: three full review/revision rounds.

Revision rounds used: three of three. Review rounds completed: four, including
the mandatory fresh review after revision 03.

Environment limits: no live or paid validation is permitted or required.

## Next Action

Stop. No further edits are authorized under this WorkPlan. A new explicit user
authorization is required for DREV-R4-001 through DREV-R4-003; the named
external owners must supply the three registered decision artifacts.

## Outcome And Retrospective

Not converged. The final exact baseline remains unapproved with one P1 and two
P2 internal findings plus three external blockers. Scope remained limited to
semantic ingestion, and no production, retrieval, agent, live-provider, or
GitHub-workflow work was performed.
