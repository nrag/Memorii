# Semantic Ingestion Design Review

- Work ID: semantic-ingestion-design-review-2026-07-26
- Work type: design
- Status: active
- Coordinator: main Codex thread
- Created: 2026-07-26
- Last updated: 2026-07-26, after round-01 reconciliation
- Parent WorkPlan: None
- Related WorkPlans: `docs/work/semantic_ingestion/design-revision-2026-07-26.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md`,
  `AGENTS.md`, `.agent/PLANS.md`, `.agent/skills/review-design/SKILL.md`
- Expected outputs: `docs/reviews/semantic_ingestion/review-round-01.md`
  through at most `review-round-03.md`

## Objective

Independently review the complete semantic-ingestion architecture and determine
whether it is implementation-ready under the repository design-completion
contract. Every confirmed finding must use the canonical product-priority,
approval-disposition, and finding-type taxonomy.

## Completion Contract

This review is complete only when one of these conditions holds:

1. A fresh whole-design review records `Approved` or `Approved with follow-ups`,
   no confirmed finding has `blocks_approval` or `changes_required`, every
   material requirement is traceable, acceptance criteria are measurable,
   every material requirement has a verification strategy, and implementation
   requires no invented material semantics.
2. Three review/revision rounds have been exhausted and the final report records
   every unresolved finding plus the exact external decision, evidence, or
   architectural change required.

All three independent reviewers must complete every full review round. The
coordinator must validate rather than automatically accept their findings.

## Scope

Included:

* the complete semantic-ingestion architecture
* governing ingestion requirements and repository invariants
* architecture feasibility and ownership boundaries
* failure, security, recovery, compatibility, and operational behavior
* requirement traceability, measurable acceptance, and verification design
* historical ingestion failure patterns only as evidence after independent
  reviewer passes complete

Excluded:

* production or test implementation
* query and retrieval redesign
* agent integration
* unrelated documentation cleanup
* weakening requirements to obtain approval

Explicitly deferred:

* implementation planning after design approval
* live or paid validation

## Constraints And Invariants

* The initial review is read-only with respect to the canonical design.
* `spec_auditor`, `correctness_reviewer`, and `test_reviewer` run concurrently
  and independently.
* Reviewers do not receive prior review findings before their independent pass.
* Product priority and approval disposition remain separate.
* Only one design writer may edit the canonical design.
* Each revised baseline receives a new content hash and a fresh reviewer set.
* No unrelated working-tree change may be reverted or modified.
* At most three revision rounds may be performed.

## Sources Of Truth

Apply the precedence in `AGENTS.md`. Required sources include:

* `docs/design/memorii_spec.md`
* `docs/design/memorii_storage_details.md`
* `docs/design/event_model.md`
* `docs/IMPLEMENTATION_RULES.md`
* `docs/design/memory_evolution_runtime.md`
* `docs/design/prompt_contracts.md`
* `docs/design/latent_graph_simulator.md`
* `docs/plans/engineering_hardening_closure_matrix.md`
* relevant production contracts and tests

The target design is the design under review, not a higher-precedence governing
source.

## Current State

Verified facts:

* Branch: `live-benchmark-repair`.
* Repository revision: `f76850fc45f09d21a40b5a7302d173ce642ec9d6`.
* The working tree contains substantial pre-existing changes.
* Round-01 design baseline SHA-256:
  `3d7f1f045d32a8c13504fc501d8265c1c62f2ef1b5d3d76e4a061efece39d957`.
* Round-02 revised design baseline SHA-256:
  `376a0d774bc951c5fd4190b165006f138c05f3145e9ad697d94b65f7760e3a17`.
* The design has 11,812 lines at the frozen baseline.
* Older review artifacts exist and are excluded from reviewer input until each
  independent pass is complete.

Interpretation:

* Content hashing is the reliable design-baseline identity for this review
  because the branch is not clean.

## Assumptions And Open Questions

Verified facts:

* The repository taxonomy defines P1, P2, P3, and `Not applicable`.
* Approval is governed by `blocks_approval`, `changes_required`, and
  `follow_up`, not by legacy severity aliases.

Working assumptions:

* Current governing documents are sufficient to resolve determinate design
  corrections.

Unresolved questions:

* Whether any design ambiguity requires an external product or architecture
  decision.

Decisions requiring external input:

* None known at baseline freeze.

## Milestones Or Experiments

### Milestone 1: Freeze And Review Round 01

Purpose: establish an independent whole-design verdict.

Bounded scope: read-only review of the frozen baseline by all three reviewers.

Expected artifacts: reconciled `review-round-01.md`.

Verification method: reviewer completion, direct evidence validation, and
baseline-hash confirmation.

Status: complete. All three reviewers completed; the coordinator validated nine
findings and wrote the reconciled report.

### Milestone 2: Review Revised Baseline

Purpose: assess the complete revised design without anchoring on the prior diff.

Bounded scope: at most two additional whole-design review rounds.

Expected artifacts: `review-round-02.md` and, only if needed,
`review-round-03.md`.

Verification method: new reviewer instances and new baseline hashes.

Status: in progress. Revision 01 is frozen for a fresh round-02 review.

## Progress Log

### 2026-07-26: Baseline freeze

Action: recorded branch, revision, tree state, design size, and design hash.

Result: initial design baseline is immutable for round 01.

Evidence produced: this WorkPlan and the SHA-256 in Current State.

Effect on current understanding: review can distinguish the exact design
content from unrelated dirty-tree changes.

Next action: superseded by round-01 reconciliation.

### 2026-07-26: Round-01 reconciliation

Action: completed three independent reviews, inspected every cited design and
governing-source location, reconciled duplicates, and revalidated higher-
precedence source conflicts after the independent passes.

Result: one P1, six P2, and two `Not applicable` findings are confirmed. Seven
have determinate design work; DREV-001 and DREV-002 require external decisions.

Evidence produced: `docs/reviews/semantic_ingestion/review-round-01.md`.

Effect on current understanding: the design can be improved internally but
cannot be approved until inference/writeback ownership and equal-version replay
semantics are decided.

Next action: revise the determinate contracts without choosing the externally
blocked semantics.

### 2026-07-26: Revision-01 baseline freeze

Action: reviewed the sole writer's design delta, returned concrete consistency
defects to the same writer, verified the corrections, and froze the revised
content hash.

Result: DREV-003 through DREV-009 have explicit contracts and verification
paths. DREV-001, DREV-002, substantive statistical values, and selected local
profiles/assets remain external.

Evidence produced: revised design SHA-256
`376a0d774bc951c5fd4190b165006f138c05f3145e9ad697d94b65f7760e3a17`.

Effect on current understanding: the design is ready for a fresh independent
whole-design review, not approval.

Next action: run new round-02 reviewer instances concurrently.

## Evidence Log

| Evidence | Location | Status |
| --- | --- | --- |
| Canonical design | `docs/design/semantic_ingestion_architecture.md` | frozen |
| Review workflow | `.agent/skills/review-design/SKILL.md` | read |
| WorkPlan contract | `.agent/PLANS.md` | read |
| Repository invariants | `AGENTS.md` | read |
| Round-01 report | `docs/reviews/semantic_ingestion/review-round-01.md` | complete |

## Decision Log

| Decision | Rationale | Status |
| --- | --- | --- |
| Use content hashes for each baseline | The branch contains unrelated pre-existing changes | active |
| Apply the new P1/P2/P3 taxonomy | It is the canonical repository contract | active |
| Keep prior findings hidden during independent passes | Prevent reviewer anchoring | active |

## Review Log

Round 01 completed with outcome `Blocked`. Confirmed findings are DREV-001
through DREV-009. The independent lanes and coordinator dispositions are
recorded in `review-round-01.md`.

## Risks And Stop Conditions

Risks:

* Reviewers may classify approval blockers as P1 without mainstream-impact
  evidence.
* The large design may contain internally duplicated or contradictory
  requirements.
* Prior reviews may bias reconciliation after the independent pass.

Mitigations:

* Reject incomplete classifications.
* Validate every finding against exact design and governing-source locations.
* Use prior reviews only after independent findings are frozen.

Stop conditions:

* Stop approved when the completion contract is satisfied.
* Stop blocked after three rounds if unresolved findings remain.
* Stop immediately if revision requires an external semantic decision.

## Outcome And Retrospective

Final result: pending.

Evidence supporting the result: pending.

Remaining limitations: pending.

Follow-up work: pending.

Lessons for future operations: pending.
