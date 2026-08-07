# Semantic Ingestion Implementation Index

- Work ID: semantic_ingestion
- Work type: implementation
- Status: active
- Coordinator: Codex main thread
- Created: 2026-07-27
- Last updated: 2026-08-04
- Parent WorkPlan: None
- Related WorkPlans: `docs/work/semantic_ingestion/conflict-authority-proof-failures-2026-08-04/debug.plan.md`; `docs/work/semantic_ingestion/testing.plan.md`; milestone-linked design, testing, and debugging plans
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md`; `docs/design/event_model.md`; `docs/design/conflict_attention.md`; `docs/design/equal_version_replay_decision-v1.json`
- Expected outputs: production implementation, deterministic verification, current-state documentation, and immutable reports under `docs/reviews/semantic_ingestion/`
- Current resume packet: `docs/work/semantic_ingestion/resume.md`
- Preserved historical WorkPlan: `docs/work/semantic_ingestion/history/implementation-through-2026-08-04.md`
- Migration manifest: `docs/work/semantic_ingestion/history/implementation-split-manifest.json`
- Current coordination candidate identity: `docs/work/semantic_ingestion/history/implementation-split-review-identity.json`

## Objective

Implement every determinate semantic-ingestion requirement through canonical
production paths while keeping external activation fail closed until its
authority exists. Preserve exact replay, provenance, transaction, lifecycle,
authorization, compatibility, and evidence boundaries.

## Completion Contract

Complete only when every SIA-R01 through SIA-R23 obligation is verified or
explicitly excluded by the approved design; every milestone completion
contract is satisfied; active external gates remain honestly unavailable; the
complete changed surface passes its deterministic and hosted gates; and fresh
whole-branch specification, correctness, and test reviews leave no remaining
validated P1/P2, `blocks_approval`, or `changes_required` finding.

## Scope

Included: the determinate behavior, migrations, production composition,
verification, and current-state documentation defined by the frozen semantic-
ingestion design.

Excluded: retrieval interpretation/ranking/answer generation, invention of
externally owned topology or policy values, live certification without exact
revision-bound evidence, and unrelated redesign.

Deferred: only externally activated behavior whose required signed authority
does not yet exist. Its prescribed validators and fail-closed preapproval path
remain in scope.

## Constraints And Invariants

All root `AGENTS.md` invariants apply. In particular, preserve candidate versus
committed state, structural versus belief overlays, typed closed schemas,
single-writer transaction ownership, immutable history, independent evidence,
provider-envelope compatibility, and fail-closed unknown or unauthorized
state.

## Identity And Coordinate Hygiene

Milestone names are planning coordinates and may appear only in planning and
typed traceability evidence. Production, test, fixture, command, workflow, and
persisted identities remain behavioral or genuine protocol/migration names.

## Change Impact And Verification Closure

The active linked debugging WorkPlan is the sole detailed owner of its
in-flight changed-surface, authority-chain, gate, experiment, known-failure,
and evidence ledgers. M4 records only the debugging boundary, link, status,
completion dependency, and compact summary. This index owns only
cross-milestone dependencies, status, and final whole-branch closure. No
milestone may infer completion from another milestone's narrower evidence.

## Sources Of Truth

Use the precedence in root `AGENTS.md`. The approved design baseline is
`docs/design/semantic_ingestion_architecture.md`; the current conflict and
replay contracts additionally bind `docs/design/conflict_attention.md`,
`docs/design/event_model.md`, and the frozen replay decision artifact.

The preserved historical WorkPlan is the authority for all pre-split
decisions, evidence, review dispositions, hashes, and chronological records.
The index and milestone packets own current navigation and status.

## Current State

- Layer1: bounded independent compiler and hermetic gate complete.
- M0: historical proof/compatibility foundation remains mixed; completed
  compatibility and traceability slices are preserved, while the rejected C2
  authority is not approved for consumption.
- M1: complete.
- M2: complete.
- M3: explicitly reopened for the source/group plan-lineage contract that its
  approved scope required but production and closure evidence omitted.
- M4: dependency-blocked on that correction. Core conflict authority passes
  its exact reproducer; clarification-winner replan requires append-only plan
  lineage.
- M5: pending.

Current Git HEAD is `2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93` with a
dirty working tree. Record a fresh candidate identity before review.

## Assumptions And Open Questions

No new product-semantic assumption was introduced by the WorkPlan split. The
active debugging operation reports no external decision blocker. External
activation artifacts remain governed by their registered SIA-ED gates.

## Milestone Index

| Milestone | Requirements | Status | Detailed packet | Dependency |
| --- | --- | --- | --- | --- |
| Layer1 | SIA-R03, L1-008, L1-009 | complete | `docs/work/semantic_ingestion/milestones/layer1-independent-authority.plan.md` | frozen design and registry |
| M0 | SIA-R03, SIA-R13, SIA-R22 | blocked | `docs/work/semantic_ingestion/milestones/m0-proof-compatibility.plan.md` | Layer1 and external trust authority |
| M1 | SIA-R01, SIA-R04, SIA-R08, SIA-R12, SIA-R19, SIA-R22, SIA-R23 | complete | `docs/work/semantic_ingestion/milestones/m1-source-admission.plan.md` | M0 compatibility foundation |
| M2 | SIA-R10, SIA-R11, SIA-R20, SIA-R21 | complete | `docs/work/semantic_ingestion/milestones/m2-writer-atomicity.plan.md` | M1 admitted source |
| M3 | SIA-R02, SIA-R04 through SIA-R07, SIA-R09, SIA-R12 | active | `docs/work/semantic_ingestion/milestones/m3-semantic-pipeline.plan.md` | reopened correction for approved source/group plan lineage |
| M4 | SIA-R10, SIA-R18 | blocked | `docs/work/semantic_ingestion/milestones/m4-event-history.plan.md` | corrected M3 plan lineage and linked debug closure |
| M5 | SIA-R03, SIA-R08, SIA-R13 through SIA-R17, SIA-R19 | pending | `docs/work/semantic_ingestion/milestones/m5-deployment-acceptance.plan.md` | M4 and external activation authority |

## Requirement Coverage Ledger

Detailed implementation and evidence rows live in the milestone packets. The
preserved historical ledger remains available under the archive heading
`Requirement Coverage Ledger`. Overlapping requirements mean a later milestone
adds integration or operational maturity; it does not invalidate earlier
bounded completion.

## Progress Log

- 2026-08-04: Preserved the complete 7,052-line pre-split WorkPlan byte-for-byte
  and replaced its canonical path with this index.
- 2026-08-04: Created one detailed packet per existing milestone without
  changing product scope, status, or evidence claims.
- 2026-08-04: M4 product work remained paused during the migration.
- 2026-08-04: Confirmed split-governance findings: linked cross-type ledger
  ownership, resume command/state detail, and executable split fidelity proof
  were incomplete. Remediation assigns linked debug as detailed owner and adds
  the manifest-driven verifier; final approval remains pending.
- 2026-08-05: Reopened M3 after a design-to-production audit proved approved
  source dependency groups, transaction group plans, append-only plan lineage,
  and exact attempt/plan/authorization result binding were absent from both
  production and the closure matrix.

## Evidence Log

The executable split verifier and its manifest record archive metrics,
artifact hashes, requirement allocation, canonical-reference corpus, and active
obligation ownership. Fidelity requires the archived file to retain SHA-256
`eace351ffa26f42b707328e8a0a0a38206c8ba62d8f2603b90853116054a4a20`.
Run `.agents/scripts/verify_workplan_split.py` normally and with `--self-test`
after changing any indexed artifact, then refresh the manifest and its pin.

## Decision Log

All 14 pre-split decisions remain verbatim under the archive heading `Decision
Log`. No decision was amended by this migration. New decisions belong in the
active milestone packet and are summarized here only when they affect another
milestone.

- 2026-08-05: Classify missing source/group plan lineage as an M3
  implementation and evidence-scope gap, not a design gap. Preserve historical
  closure bytes, explicitly reopen M3, and require fresh evidence before
  restoring complete status. The user selected the complete approved contract.

## Review Log

All pre-split review rounds and dispositions remain verbatim under the archive
heading `Review Log` and the chronological milestone-specific sections. New
reviews write to the active milestone packet. Only cross-milestone or final
branch review results are summarized here.

- 2026-08-04: Three governance findings were confirmed and remediated by the
  indexed-plan ownership clarification, resume expansion, and executable
  fidelity verifier. This is not a final implementation or branch approval.

## Blockers And Limits

M4 cannot complete until the reopened M3 lineage correction and linked
semantic-conflict debugging operation close and pass frozen review. M5 claims
remain limited by externally owned authority and exact revision-bound evidence.
M0's rejected historical C2 baselines must not be consumed.

## Next Action

Remediate the eight confirmed frozen-review findings for the M3 strict
preparation/catalog/request/Step-4 contract slice and run bounded delta reviews
under `docs/work/semantic_ingestion/milestones/m3-semantic-pipeline.plan.md`.

## Outcome And Retrospective

Operation remains active. The plan split reduced routine context while retaining
all historical bytes and giving each milestone one explicit completion owner.

## Migration Crosswalk

| Preserved source section | Current owner |
| --- | --- |
| Header through M4 readiness/review material (historical lines 1-1499) | M4 packet plus archive |
| Objective through migration/rollout (historical lines 1500-1972) | this index; detailed historical text remains in archive |
| Milestones Or Experiments (historical lines 1973-2169) | seven milestone packets |
| Verification, progress, evidence, decisions, and reviews (historical lines 2170-6365) | archive; new evidence goes to active milestone |
| M0 current-pin closure (historical lines 6366-6561) | M0 and Layer1 packets plus archive |
| M3 closure and hosted-CI remediation (historical lines 6562-7015) | M3 packet plus archive |
| M4 core production slice (historical lines 7016-7052) | M4 packet plus archive |
