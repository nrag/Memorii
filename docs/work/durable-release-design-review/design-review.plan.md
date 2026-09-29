# Durable Execution And Solver Runtime — Pre-Release Design And Implementation-Plan Review

- Work ID: durable-release-design-review
- Work type: investigation (design review per review-design skill)
- Delivery fidelity: Level 3 (review target fidelity; review bar per AGENTS.md Level 3 definitions and review-design skill)
- Status: complete
- Coordinator: main Codex thread
- Created: 2026-09-29
- Last updated: 2026-09-29 (review complete; outcome Changes required; report validated)
- Parent WorkPlan: None
- Related WorkPlans: [shared SQLite design](../shared-sqlite-design/design.plan.md) (complete), [durable memory implementation](../durable-memory-implementation/implementation.plan.md) (proposed; review target), [durable runtime design](../durable-runtime-design/design.plan.md) (complete historical)
- Canonical inputs: frozen targets and governing sources below
- Expected outputs: immutable review report `docs/reviews/durable-execution-and-solver-runtime/2026-09-29-final-approval.md`

## Objective

Perform the full design review (final-approval pass) of the durable execution/solver runtime design and the first review of its implementation WorkPlan, and record an approval outcome the owner can rely on before starting Level 3 first-release implementation.

## Completion Contract

Review is complete when: the frozen baseline is recorded; requirements are independently reconstructed from governing sources; repository reality is checked; all three independent reviewer roles (spec_auditor, correctness_reviewer, test_reviewer) complete passes on the same frozen baseline; every proposed finding is validated and classified per the canonical finding contract; a validated report exists at the expected output path and passes `.agents/skills/review-design/scripts/validate_review_report.py`; and one outcome (`Approved` / `Approved with follow-ups` / `Changes required` / `Blocked`) is recorded with required changes and follow-ups.

## Scope

Included: `docs/design/durable_execution_and_solver_runtime.md` at SHA-256 `22e29f90ab90fa9b67b489d8f293b4a9ecbe4e5bf1dad7c0d6d3f2a7697706ad`; `docs/work/durable-memory-implementation/implementation.plan.md` at SHA-256 `d30c0d585fc3767d63f21f236fbad5ff8d2ee2e38c5f849c7c62fce01ef8d943` plus its packets (coverage, validation, bindings, gates, identity-and-changes, planning-review, resume, eight milestone packets, workflow-inventory.json, baseline.json, authority-inventory.json); consistency of both against governing documents and current code at HEAD `bad9eeefb43f7f42fb95d583b11859e2f2ca9eb8`.

Excluded: editing the design or plan (read-only review); implementation; re-running CI; the separately user-deferred agent-benefit benchmark planning; live provider certification.

## Constraints And Invariants

AGENTS.md universal invariants; canonical finding classification (product priority P1/P2/P3/Not applicable; approval disposition blocks_approval/changes_required/follow_up; allowed combinations); evidence-maturity states not inflated; identity hygiene contract in `.agents/PLANS.md`.

## Sources Of Truth

Precedence per AGENTS.md: memorii_spec.md, memorii_storage_details.md, event_model.md, IMPLEMENTATION_RULES.md, scoped_memory_context.md, learned_ontology.md + addendum, then the design under review. Repository code/tests at HEAD `bad9eeef`.

## Current State

Baseline frozen 2026-09-29. Coordinator evidence gathering complete: (1) independent governing-requirement reconstruction (spec §17/§18/§19-23/§22.2, storage §2/§5/§6/§10, event model §3/§8/§9/§10/§15 + frozen equal-version decision, RULES, SMC, ONTO, ONTO-ADD) — held in review working notes and folded into the report; (2) repository-reality verification — every factual baseline claim in the design's "Verified Baseline And Problem" section CONFIRMED against code (four in-memory stores; root-node creation emits no reconstructible execution event; ID-only solver commit events; process-local directory; JSONL-only persistence; five production `JsonlMemoryPlaneStore(` callsites as inventoried; no SQLite/TS/SDK/storage-admin/harness-state/persistence-factory code exists; workflows match gates.md families). Prior design-review history: one full cohort approved candidate `22e29f90` (shared-sqlite-design/reviews.md); this review is the fresh final-approval full pass required before implementation, expanded to include the implementation plan.

## Milestones

1. Freeze baseline and gather evidence — complete.
2. Three independent reviewer passes on the frozen baseline — in progress.
3. Reconcile, classify, and write validated report with outcome — pending.

## Progress Log

- 2026-09-29: Skill loaded; targets read; baseline frozen (design `22e29f90…`, plan `d30c0d58…`, HEAD `bad9eeef`, dirty tree = user's hermes trial edit + untracked design/work packets). Requirement reconstruction and repository-reality verification completed via read-only delegates; results recorded under Current State. Reviewers dispatched. Next action: reconcile reviewer findings.
- 2026-09-29: Three independent passes returned; coordinator validated every load-bearing claim directly; report written, validated, outcome recorded (Changes required). Review complete per the completion contract: frozen baseline, independent requirement reconstruction, repository reality check, three passes, reconciled classifications, validated immutable report, recorded outcome. Hand-off to build-design remediation is Phase 10 disposition, recorded under Next Action.

## Outcome And Retrospective

Final result: Changes required — 4 validated P2 design defects (closed-grammar task-lifecycle gap; merge/consolidate/proposal-union undefined; legacy layout inventory missing; verification cost model unspecified), 2 changes_required plan-matrix gaps (sidecar transport-security family; consumer + key-lifecycle families), 3 P3 follow-ups. Evidence: validated report at docs/reviews/durable-execution-and-solver-runtime/2026-09-29-final-approval.md. Remaining limitations: performance reasoning in DREV-004 is analytical pending the named capacity fixtures. Lessons: the design's factual discipline held under full code verification (zero baseline contradictions); the residual defects were all completeness gaps in closed grammars and inventories — the strongest remaining failure mode for this design style is omission, not contradiction.

## Evidence Log

- `shasum -a 256` of both targets (values above); `git log -1` HEAD; `git status --porcelain`.
- Repository verification: api/service.py:19-33 (four stores), core/execution/service.py:230-300, core/persistence/replay.py:29-63 (subset reducer), api/service.py:118-135 (root without execution event), core/solver/update_engine.py:444/459 (ID-only commit events), core/directory/indexes.py:15-22, bundle.py:46-79/148, provider/factory.py:53, hermes_factory.py:552/559/813-930, authenticated_source.py:145/168, hermes_provider.py:63/97/109, hermes_local_authority.py:236/242, production_capture.py:183/195, memory_plane/store.py:122-146/877-906 + service.py:209, provider/service.py:1068/1087/1661/1883/1919, pyproject.toml:40-41, three workflow files; five JsonlMemoryPlaneStore callsites; no sqlite3/SDK/new-module usage.
- Governing citations: spec §17 (1150-1212), §18 (1215-1256), §19-23 (1263-1473), §27-28; storage §2 (42-88), §5 (206-238), §6 (242-270), §10 (361-382); event model §3 (47-109), §8-9 (262-352), §10 (355-394), §15 (474-507), frozen equal_version_replay_decision-v1.json; RULES 3-39; SMC 56-67/93-106/208-215/413-439; ONTO 202-227/264-276; ONTO-ADD 15-47/79-87.

## Review Log

- 2026-09-29 full cohort (spec_auditor, correctness_reviewer, test_reviewer; independent concurrent passes on frozen design `22e29f90` + plan `d30c0d58` at HEAD `bad9eeef`). Raw proposals: 4 spec findings, 3 correctness findings, 2 test findings; zero identity-governance violations reported by any role.
- Coordinator reconciliation: all 9 proposals validated against direct evidence (including re-verification of the legacy-layout spellings, the DUR-14 allocation delta, and the design's grammar omissions by grep/code inspection). All confirmed; none rejected; two accuracy nits recorded as notes. Renumbered DREV-001..009 in the report.
- Dispositions: DREV-001..004 confirmed P2 / changes_required / eligible_p1_p2 (design). DREV-005/006 confirmed Not applicable / changes_required / evidence_action (plan validation matrix). DREV-007..009 confirmed P3 / follow_up / record_only. Product-impact evidence for each P2: task-lifecycle termination of every journey (DREV-001); consolidation on the current default runtime path plus spec-mandated merge/consolidate surface (DREV-002); every existing JSONL installation affected by layout-divergent detection (DREV-003); 100% of read/commit paths at reference scale (DREV-004).
- Outcome: **Changes required**. Report written and validated: `docs/reviews/durable-execution-and-solver-runtime/2026-09-29-final-approval.md` (validator: structure valid).

## Blockers And Limits

None. Budget used: one full cohort + one reconciliation, within plan.

## Next Action

Hand DREV-001..004 (plus optional DREV-007/009 companion edits) to a linked `$build-design` remediation of the design, apply DREV-005/006/008 as bounded implementation-plan corrections, then request a delta review against the new frozen design baseline referencing this report.
