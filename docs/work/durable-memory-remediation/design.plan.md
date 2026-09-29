# Durable Execution Design Remediation

- Work ID: durable-memory-remediation
- Work type: design
- Delivery fidelity: Level 3 (bounded remediation of the reviewed Level 3 design; no scope expansion)
- Status: active
- Coordinator: main Codex thread (sole writer for the canonical design)
- Created: 2026-09-29
- Last updated: 2026-09-29
- Parent WorkPlan: [release design review](../durable-release-design-review/design-review.plan.md) (complete; owns the findings)
- Related WorkPlans: [shared SQLite design](../shared-sqlite-design/design.plan.md) (complete), [durable memory implementation](../durable-memory-implementation/implementation.plan.md) (proposed; plan-side corrections included here)
- Canonical inputs: [design under remediation](../../design/durable_execution_and_solver_runtime.md) at SHA-256 `22e29f90ab90fa9b67b489d8f293b4a9ecbe4e5bf1dad7c0d6d3f2a7697706ad`; [review report](../../reviews/durable-execution-and-solver-runtime/2026-09-29-final-approval.md); governing sources per AGENTS.md precedence
- Expected outputs: remediated design (new SHA), corrected validation/coverage/plan packets, delta review record, updated implementation-plan baseline

## Objective

Close review findings DREV-001..004 (P2 design) and companion edits DREV-007/009 in the canonical design, and apply plan-side corrections DREV-005/006/008 to the implementation WorkPlan, so the design is approval-ready and the implementation plan's proof matrix is complete. No new product scope; no changes outside the findings' boundaries.

## Completion Contract

Every DREV-001..006 required change is implemented in the design/plan text; the four P2 corrections state invariant-level mechanisms (not examples); new durable identities are behavioral and added to the design's identity inventory; the frozen remediated design passes a three-role delta review (spec/correctness/test) over the complete affected semantic boundaries with no newly validated P1/P2 defect and no unresolved changes_required finding; the implementation plan pins the new design SHA; plan-manifest hashes verify; all changes are committed on `codex/durable-memory-release`.

## Scope

Included: design edits for DREV-001 (task-lifecycle command kinds + label mappings), DREV-002 (solver proposal union enumeration; merge/consolidation durable contract; §23.1/§20.2 mapping-or-exclusion table), DREV-003 (closed legacy layout inventory, per-root input-root rule, mixed/ambiguous-root behavior), DREV-004 (snapshot verification structure and cost model; re-derived budgets; honest tamper-detection boundaries), DREV-007 (HostBinding run-coordinate mapping), DREV-009 (displaced-attempt terminal transition and active-attempt definition); attack-matrix/identity-inventory extensions these require. Plan edits: validation.md families (sidecar transport security; consumer delivery; checkpoint key lifecycle), coverage.md mirrors, DREV-008 editorial pass (DUR-14 allocation, rollout-order note, four-category assumptions section), baseline SHA repin.

Excluded: any behavior not named by the findings; reopening approved architecture (partition model, publication protocol, mode fencing); implementation; CI changes; the deferred agent-benefit benchmark.

## Constraints And Invariants

All universal Memorii invariants; closed schemas fail closed; candidate/committed distinction preserved; no beliefs on structural nodes; backtracking is revision not deletion; migration preserves original bytes/authority; identity hygiene (no planning/evidence coordinate in durable names; new kind/enum values are behavioral). Remediation must not weaken any previously approved contract (convergence: nonmaterial-bounded unless a finding requires otherwise).

## Identity And Coordinate Hygiene

New identities introduced by this remediation (all behavioral, all registered in the design's identity inventory before use): request kind values `complete_task`, `pause_task`, `abort_task`; proposal discriminators `belief_update`, `status_update`, `node_reopen`, `node_merge`; attempt terminal cause `superseded_by_fence` (or explicit `superseded` terminal — final choice recorded below); HostBinding field `host_run_id`; legacy-layout entries as typed path-component records (no new public names). Requirement/review IDs remain traceability values only.

| Surface | Proposed or existing identity | Class | Behavioral owner or protocol meaning | Retain, rename, migrate, or reject | Proof |
| ------- | ----------------------------- | ----- | ------------------------------------ | --------------------------------- | ----- |
| RuntimeCommandRequest kinds | complete_task, pause_task, abort_task | protocol (v1 request union values) | task lifecycle transitions with typed evidence | add; generated union inventory + unknown-kind rejection | generated manifest parity; identity gate field reader |
| Solver proposal union | belief_update, status_update, node_reopen, node_merge | protocol (v1 proposal union values) | spec §23.1 mutation entries in closed form | add; closed discriminated union, unknown rejects | union inventory + rejection tests (validation.md families) |
| Operation attempt | cause superseded_by_fence (+ definition of active attempt) | behavioral lifecycle enum/semantic | fenced takeover disposition of displaced attempt | add; transition table row | lifecycle family in validation.md |
| HostBinding | host_run_id (bounded optional) | behavioral field | spec §20.3 framework_run_id mapping | add; closed schema | schema parity fixtures |
| Legacy layouts | typed path-component entries (memory-plane/memory_plane/direct) | migration facts, not new public names | detection and adoption fingerprint inputs | add to MemoryPlaneMigrationPlan schema | installed-root gate fixtures (validation.md) |

## Sources Of Truth

Precedence per AGENTS.md. Finding contracts: review report DREV-001..009 with their governing citations (spec §18.1/§20.1/§20.2/§20.3/§23.1/§12/§16.24; design lines as cited in the report; code evidence: hermes_factory.py:552/559, hermes_local_authority.py:236-242, bundle.py:71, production_capture.py:195, service.py consolidator composition).

## Current State

Remediation starting from design SHA `22e29f90` on branch `codex/durable-memory-release` (base `e6880a46`, artifacts at `7d94e660`). All finding evidence already validated by the review; no new research blockers expected.

## Assumptions And Open Questions

- Verified facts: as in the review report and its code citations.
- Working assumptions: consolidation semantics follow the existing Consolidator (resolution-triggered; effects are solver/execution updates + writeback candidates, never direct semantic writes) — to be confirmed against core/consolidation/consolidator.py before writing DREV-002 text.
- Unresolved questions: none currently; the DREV-004 verification mechanism choice (two-tier acquisition-bound verification) is a design decision to be recorded in the Decision Log, not an open question.
- Decisions requiring external input: none.

## Milestones Or Experiments

1. Fact confirmation (JSONL store members, Consolidator surface, spec §23.1/§12 lists) — verification method: direct code/doc inspection.
2. Design edits DREV-001..004 + companions; extend attack matrix and identity inventory — verification: self-check against each finding's "recommended invariant-level resolution".
3. Plan edits DREV-005/006/008; manifest refresh — verification: hash verification + mapping re-check (18 requirements, line-475 extension set complete).
4. Freeze + delta review (three roles) — verification: no newly validated P1/P2; findings closed.
5. Close: repin SHA in implementation plan/resume; commit.

## Progress Log

- 2026-09-29: WorkPlan created; baseline frozen (design `22e29f90`, branch head `7d94e660`). Next action: confirm code facts for DREV-002/003 edits.
- 2026-09-29: Code facts confirmed (plane members `memory_records.jsonl`/`memory_records.lock`/`.protected/` at store.py:485-486/519; Consolidator triggers from_solver_resolution/from_validated_abstraction/from_user_finding; spec §23.1 twenty APIs, §12.2 outputs, §16.24 gates). Design edits applied for DREV-001..004 and DREV-007/009; attack matrix extended (task lifecycle, merge/consolidation, layout detection, verification tiers, sidecar transport); rollout order corrected; identity ledger row extended; label mapping enumerated. Plan edits applied: validation.md three new proof families (sidecar transport, consumer delivery, key lifecycle), coverage.md DUR-03/06/13 test mirrors and DUR-14 allocation clarification, additional-harnesses header aligned, four-category assumptions section added, design SHA repinned to `ef478a2e`, design-identity-inventory refreshed, plan-manifest re-verified (20/20 files, design_sha256 matches). Next action: commit and run delta review.

## Evidence Log

- Review report (immutable) with all finding evidence; remediation-time evidence: store.py:485-486/519 (plane members), consolidator.py:13-108 (triggers), memorii_spec.md:1443-1473 (§23.1), 512-543 (§12), 1070-1078 (§16.24); new design SHA `ef478a2e765360d4e607ea5c8d756e42c92c19633e8956df3edafa7615e55907`; plan-manifest verification output (20 files, no mismatches).

## Decision Log

- 2026-09-29, DREV-004 verification mechanism: two-tier model selected. Tier A constant-time per released snapshot (finalized control tuple equality: generation identity, publication position, eligibility epoch, SQLite schema/data-version cookies); Tier B full catalog-manifest recomputation bound to verification acquisition (startup, first service of a foreign tuple, doctor/backup/restore/migration) with the publishing process's in-transaction manifest counting as its acquisition. Write path maintains per-catalog digests incrementally (per-row typed digests folded in primary-key order via a deterministic balanced accumulator, logarithmic per changed row). Alternatives rejected: per-read full rehash (incompatible with DUR-11 budgets at reference scale) and stored-digest-only comparison (detects no preserved-head row tampering). Consequence: the tamper guarantee is honestly bounded — preserved-head row mutation is detected at acquisition/explicit-verify/replay, not per snapshot; budgets re-derived with an explicit Tier B acquisition budget (<= 5 s at reference fixture).
- 2026-09-29, displaced-attempt disposition (DREV-009): displaced attempt moves to terminal `needs_reconciliation` with typed cause `superseded_by_fence` (chosen over a new `superseded` terminal state to avoid growing the closed stage enum for one cause); its spend reservation is not released to the retry budget; "active" defined as lease-valid and stage-nonterminal, uniqueness enforced accordingly.
- 2026-09-29, solver start/resume mapping (DREV-002): no separate v1 command kinds; a solver run starts via start/resume plus first proposal against its execution node, and solver resume is resume_task scoped to the solver view. Recorded as the deliberate v1 mapping in the design.
- 2026-09-29, consolidate_* mapping (DREV-002): consolidation remains trigger-driven (solver resolution, validated abstraction, user finding, plus task completion and pause), not a separate host command; CONSOLIDATION_RESULT is delivered via result envelope and the typed outbox payload. Full spec 23.1/20.2 mapping table recorded in the design's merge-and-consolidation contract.
- 2026-09-29, rollout-order conflict (DREV-008b): design line 426 was the inconsistent statement (host capture roots are registered writers, so all-writer enrollment completes only after host conformance); design amended to hosts-before-controls, matching the plan's dependency.

## Review Log

- Delta review pending: candidate frozen at design SHA `ef478a2e765360d4e607ea5c8d756e42c92c19633e8956df3edafa7615e55907`.

## Blockers And Limits

Budget: one consolidated edit batch + one delta review cohort + at most one bounded revision round. None blocked.

## Next Action

Commit the frozen candidate, then run the concurrent three-role delta review (spec_auditor, correctness_reviewer, test_reviewer) on design SHA `ef478a2e` covering the complete affected boundaries: command/proposal grammar and lifecycle mapping; merge/consolidation contract; migration detection; verification tiers/budgets; attempt state machine; HostBinding; and the plan-matrix additions.
