# Durable Execution Design Remediation

- Work ID: durable-memory-remediation
- Work type: design
- Delivery fidelity: Level 3 (bounded remediation of the reviewed Level 3 design; no scope expansion)
- Status: complete
- Coordinator: main Codex thread (sole writer for the canonical design)
- Created: 2026-09-29
- Last updated: 2026-09-29 (complete; final design SHA 9f73f06ff2153439ed970f953b3679bdc4e9b60448248d2d5f5e64f947624a2d)
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
- 2026-09-29: Code facts confirmed (plane members `memory_records.jsonl`/`memory_records.lock`/`.protected/` at store.py:485-486/519; Consolidator triggers from_solver_resolution/from_validated_abstraction/from_user_finding; spec §23.1 twenty APIs, §12.2 outputs, §16.24 gates). Design edits applied for DREV-001..004 and DREV-007/009; attack matrix extended (task lifecycle, merge/consolidation, layout detection, verification tiers, sidecar transport); rollout order corrected; identity ledger row extended; label mapping enumerated. Plan edits applied: validation.md three new proof families (sidecar transport, consumer delivery, key lifecycle), coverage.md DUR-03/06/13 test mirrors and DUR-14 allocation clarification, additional-harnesses header aligned, four-category assumptions section added, design SHA repinned to `ef478a2e`, design-identity-inventory refreshed, plan-manifest re-verified (20/20 files, design_sha256 matches remediated design). Committed as `2efb234e`; delta review launched.
- 2026-09-29: Delta cohort returned (see Review Log): all DREV-001..009 closed; five reconciled observations (REM-001..005). One bounded revision batch applied per the reviewers' invariant-level resolutions: consolidation output set/neighborhood view/20.2 carrier table; four validation.md family rows + coverage mirrors; accumulator anchor rule; stale-read retry rule; plan index refreshed. Final design SHA `9f73f06ff2153439ed970f953b3679bdc4e9b60448248d2d5f5e64f947624a2d`; plan-manifest re-verified (20/20 files + design_sha256). WorkPlan complete per the completion contract: all findings closed or applied, delta review passed with no newly validated P1/P2 defect remaining (REM-001 corrected in the budgeted round), identity inventory extended, implementation plan repinned.

## Evidence Log

- Review report (immutable) with all finding evidence; remediation-time evidence: store.py:485-486/519 (plane members), consolidator.py:13-108 (triggers), memorii_spec.md:1443-1473 (§23.1), 512-543 (§12), 1070-1078 (§16.24); intermediate design SHA `ef478a2e…` (commit `2efb234e`); final design SHA `9f73f06f…`; plan-manifest verification outputs (20 files, no mismatches, both rounds); delta-cohort closure verdicts and REM reconciliations in the Review Log.

## Outcome And Retrospective

Final result: remediation complete. All six review required-changes plus companions closed and confirmed by a three-role delta review; the single validated P2 residual (REM-001) and four bounded observations corrected in one budgeted revision batch applying the reviewers' own resolutions. The design at `9f73f06f` is approval-ready from this operation's scope; the implementation plan pins it and its next action is storage-foundation readiness. Remaining limitations: design-level approval only — nothing implemented or measured; final whole-design review happens at implementation closure. Lesson: both review rounds' design defects clustered in closed-grammar completeness (enumerations that under-claimed or over-claimed their governing source) — future design edits in this repository should diff every enumerated closed set against its cited source before freezing.

## Decision Log

- 2026-09-29, DREV-004 verification mechanism: two-tier model selected. Tier A constant-time per released snapshot (finalized control tuple equality: generation identity, publication position, eligibility epoch, SQLite schema/data-version cookies); Tier B full catalog-manifest recomputation bound to verification acquisition (startup, first service of a foreign tuple, doctor/backup/restore/migration) with the publishing process's in-transaction manifest counting as its acquisition. Write path maintains per-catalog digests incrementally (per-row typed digests folded in primary-key order via a deterministic balanced accumulator, logarithmic per changed row). Alternatives rejected: per-read full rehash (incompatible with DUR-11 budgets at reference scale) and stored-digest-only comparison (detects no preserved-head row tampering). Consequence: the tamper guarantee is honestly bounded — preserved-head row mutation is detected at acquisition/explicit-verify/replay, not per snapshot; budgets re-derived with an explicit Tier B acquisition budget (<= 5 s at reference fixture).
- 2026-09-29, displaced-attempt disposition (DREV-009): displaced attempt moves to terminal `needs_reconciliation` with typed cause `superseded_by_fence` (chosen over a new `superseded` terminal state to avoid growing the closed stage enum for one cause); its spend reservation is not released to the retry budget; "active" defined as lease-valid and stage-nonterminal, uniqueness enforced accordingly.
- 2026-09-29, solver start/resume mapping (DREV-002): no separate v1 command kinds; a solver run starts via start/resume plus first proposal against its execution node, and solver resume is resume_task scoped to the solver view. Recorded as the deliberate v1 mapping in the design.
- 2026-09-29, consolidate_* mapping (DREV-002): consolidation remains trigger-driven (solver resolution, validated abstraction, user finding, plus task completion and pause), not a separate host command; CONSOLIDATION_RESULT is delivered via result envelope and the typed outbox payload. Full spec 23.1/20.2 mapping table recorded in the design's merge-and-consolidation contract.
- 2026-09-29, rollout-order conflict (DREV-008b): design line 426 was the inconsistent statement (host capture roots are registered writers, so all-writer enrollment completes only after host conformance); design amended to hosts-before-controls, matching the plan's dependency.

## Review Log

- 2026-09-29 delta cohort (spec_auditor, correctness_reviewer, test_reviewer; independent concurrent passes) on frozen candidate `ef478a2e` (commit `2efb234e`). Closure verdicts, unanimous across roles: DREV-001 closed; DREV-002 closed in substance; DREV-003 closed (verified against all five constructor sites and the store member set); DREV-004 closed (two-tier model verified sound: Tier A genuinely constant-time, accumulator correct under update/delete, budgets re-derived, honest boundary); DREV-005/006 closed (families with exact signals and correct levels); DREV-007/008/009 closed. No new architectural contradiction; identity governance clean (nine new values behavioral, ledgered in both inventories); no evidence inflation.
- New observations, coordinator-reconciled and renumbered REM-001..005:
  - REM-001 (from spec_auditor; confirmed P2 / changes_required / eligible_p1_p2): consolidation output enumeration mis-stated the closed set (dropped spec 12.2 archive packages and the user-memory candidate produced by the user-finding trigger the design itself names); `get_local_neighborhood` had no expressible carrier in RuntimeStateRequest; CANDIDATE_EDGE_ATTACHMENTS had no named carrier. Product impact: consolidation result schema at every completion/pause would be invented mid-build. Disposition: corrected in the budgeted revision batch — output set restated (six kinds incl. archive package reference; one delivery per output kind), neighborhood view added to RuntimeStateRequest (bounded node-ID tuple, depth 1|2, explicit truncation), and an explicit 20.2 carrier table naming all ten outputs including candidate edges in the solver view and paged retrieval.
  - REM-002 (spec_auditor changes_required vs test_reviewer follow_up; reconciled to Not applicable / changes_required / evidence_action for consistency with the original DREV-006 disposition of the identical invariant): the four design attack-matrix rows added by the remediation (task lifecycle, merge/consolidation, layout detection, verification tiers) were not selectable proof families in validation.md. Disposition: corrected — four validation.md rows added with failure signals, coverage.md DUR-01/02/17/18 test columns mirrored.
  - REM-003 (correctness P3 / follow_up / record_only; folded into the batch as a determinate one-sentence correction inside the DREV-004 boundary): incremental accumulator not anchored to the signed tuple; a persisted-accumulator-without-anchor implementation could launder accumulator-consistent tampering through a legitimate publication. Disposition: anchor rule added (pre-update root equals expected-old signed manifest digest in-transaction, or protected in-memory accumulator rebuilt at acquisition).
  - REM-004 (correctness P3 / follow_up / record_only; folded in): Tier A "any mismatch quarantines" lacked a benign-race carve-out for a snapshot pinned just before a concurrent publication finalizes (spurious integrity_error). Disposition: stale-finalized-read retry rule added; quarantine reserved for incoherent tuple/component mismatch.
  - REM-005 (spec_auditor + test_reviewer P3 / follow_up / record_only; fixed): implementation.plan.md verified-facts bullet and Next Action stale after the remediation commit. Disposition: corrected with a new progress entry and the storage-foundation next action.
- Coordinator verification: each batch correction was checked against its finding's recommended invariant-level resolution (corrections apply the reviewers' recommendations; no new semantic choices). Re-running a third cohort on the corrected text would be non-discriminating under the convergence rule; final whole-design review remains the implementation plan's closure obligation.

## Blockers And Limits

None. Budget used: one consolidated edit batch + one delta cohort + one bounded revision round (within plan).

## Next Action

None (WorkPlan complete). The implementation plan owns the next action: storage-foundation readiness against design SHA `9f73f06f`.
