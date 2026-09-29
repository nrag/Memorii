# Durable Memory And Runtime Implementation

- Work ID: durable-memory-implementation
- Work type: implementation
- Delivery fidelity: Level 3 - first production rollout
- Status: active
- Coordinator: main Codex task; one implementation writer per overlapping slice
- Created: 2026-09-29
- Last updated: 2026-09-29 (implementation started; storage-foundation packet active; implementation base fe9e1913)
- Parent WorkPlan: [shared SQLite design](../shared-sqlite-design/design.plan.md), complete
- Related WorkPlans: [original runtime design](../durable-runtime-design/design.plan.md), [learned ontology](../learned-ontology/implementation.plan.md)
- Canonical inputs: [approved design](../../design/durable_execution_and_solver_runtime.md), AGENTS.md, .agents/PLANS.md, implement-design skill and governing sources pinned in [baseline](baseline.json)
- Expected outputs: working shared SQLite memory/runtime, migration, three harness bindings, operator controls, generated clients and revision-bound Level 3 evidence

## Objective

A user installs Memorii, persists semantic/ontology and task/solver state, safely restarts or migrates an existing installation, uses it from Hermes/OpenClaw/Pi, and can inspect, pause, export, back up, restore and forget data through supported controls. Domain authority stays separate despite shared physical storage.

This request creates the implementation WorkPlan only. Planning is delivered; implementation is not started. Proposed status is intentional, not a completion claim. [Resume packet](resume.md) selects [storage foundation](milestones/storage-foundation.plan.md) as the first implementation packet.

## Design Baseline And Sources Of Truth

Remediated design SHA-256: `9f73f06ff2153439ed970f953b3679bdc4e9b60448248d2d5f5e64f947624a2d` (closes review findings DREV-001..004 and companions DREV-007/009 via the [remediation WorkPlan](../durable-memory-remediation/design.plan.md); the reviewed baseline was `22e29f90ab90fa9b67b489d8f293b4a9ecbe4e5bf1dad7c0d6d3f2a7697706ad`, and the 2026-09-29 final-approval review report is [here](../../reviews/durable-execution-and-solver-runtime/2026-09-29-final-approval.md)). Design-cohort approval of the original scope is recorded in [design reviews](../shared-sqlite-design/reviews.md); plan-matrix findings DREV-005/006/008 are applied in this plan's validation/coverage/editorial packets. Delta review of the remediated design is recorded in the remediation WorkPlan; implementation starts only after it passes with no newly validated P1/P2 defect. No approved deviations. Pin this checksum before the first edit and reopen design if a material semantic choice differs.

Implementation branch: `codex/durable-memory-release`, created from main `e6880a46` (merge PR #123, which contains planning HEAD `bad9eeefb43f7f42fb95d583b11859e2f2ca9eb8`); the release-prep artifacts are committed at `ca845fc1`. The former `codex/learned-ontology-implementation` branch is merged and deleted; no pre-existing diff remains unattributed on this branch. Implementation base for the storage-foundation slice: `fe9e1913` (tree clean except the preserved user edit to `docs/design/hermes_conversation_memory_trial.md`).

Source precedence follows AGENTS.md. Core spec/storage/event model and implementation rules govern the additive design. Learned ontology, scoped context, semantic ingestion and event registries retain their original authority; no migration may silently reinterpret them. Input and workflow hashes are recorded separately; installable schemas/registry/package member inventories are enumerated at storage readiness before changing them.

## Scope And Constraints

All DUR-01 through DUR-18 are in scope. Includes one SQLite application-data partition with separate memory-plane/runtime owners; immutable history and typed indexes; independent control/trust state; legacy adoption and migration; safe action/attempt recovery; bounded host state; embedded/HTTP/SDK/spool roots; installed Hermes/OpenClaw/Pi; contract examples for the other design-required frameworks; operator controls; Linux/macOS release evidence. Auxiliary work/decision/trace/conflict/integrity owners remain registered participants unless separately approved for migration.

Excludes new memory/planning algorithms, unrestricted semantic writeback, remote multi-tenant service, distributed transactions, Windows/network-filesystem certification, new GUI and comparative agent-benefit/publication benchmark planning. Existing exact-release component certification is still governed by benchmark_certification.md; its retained requirement is distinct from the user-deferred comparative campaign. No model/key/network work in plan creation.

Preserve raw/derived and candidate/committed distinctions; backend-neutral APIs; semantic/ontology writer authority; dual memory revisions; original IDs/digests/catalog ownership; explicit no-fallback managed roots; fail-closed grant/revocation and unknown formats; host-owned tools; immutable event history.

## Completion Contract

Every requirement has implementation, appropriate tests, actual nonzero production caller/path proof and exact-revision evidence; all declared supported roots and failure families work. Local deterministic gates and required GitHub/platform/host/external gates are recorded separately and pass at the reviewed revision. All generated authority chains, migration/rollback and runbooks agree. Final full branch review by spec/correctness/test roles has no unresolved required finding and records `remaining_validated_p1_p2: []`. A plan, toy probe, test-only implementation or one milestone cannot close this parent. Full details live in [coverage](coverage.md), [validation](validation.md), [bindings](production_entrypoint_bindings.md), [gates](gates.md) and [identity/change ledger](identity-and-changes.md).

## Milestones And Dependencies

| Order / packet | Usable outcome | Depends on | Status |
| --- | --- | --- | --- |
| 1. [Storage foundation](milestones/storage-foundation.plan.md) | Owner initializes partition; canonical memory persists and reopens with verified publication | readiness + test-matrix review | proposed |
| 2. [Semantic and ontology parity](milestones/semantic-ontology.plan.md) | Real provider/Hermes semantic and ontology paths use SQLite and indexed protected reads | storage foundation | proposed |
| 3. [Legacy migration](milestones/legacy-migration.plan.md) | Existing JSONL installation adopts control authority and safely cuts over | semantic and ontology parity | proposed |
| 4. [Runtime recovery](milestones/runtime-recovery.plan.md) | Complete task/solver/action state survives independent-process restart | storage foundation; parity regression baseline | proposed |
| 5. [Harness state exchange](milestones/harness-state.plan.md) | Hermes consumes bounded durable state through real API/sidecar/SDK/spool roots | runtime recovery + legacy migration | proposed |
| 6. [Additional harnesses](milestones/additional-harnesses.plan.md) | Pinned OpenClaw and Pi integrations complete the same task journey | harness state exchange | proposed |
| 7. [Operator controls](milestones/operator-controls.plan.md) | All registered owners honor pause, backup/restore, forget/retention and diagnostics | prior data/host roots enrolled | proposed |
| 8. [Release conformance](milestones/release-conformance.plan.md) | Exact installed artifacts, supported platforms, migration/rollback and release evidence pass | every bounded milestone | proposed |

Order prioritizes usable journeys, common-failure safety, then exhaustive release hardening. Foundational grants, fencing, crash consistency and integrity are mandatory in the first relevant slice; they are not deferred to release conformance. Read-only mapping/test preparation can run alongside the sole writer. Runtime work may be mapped during migration, but overlapping storage/schema edits stay serial.

## Requirement Allocation And Evidence Maturity

[Coverage ledger](coverage.md) reconstructs obligations from narrative contracts, not just requirement labels. Every requirement is currently **not started**; design is specified, with only the bounded design probes locally verified. No production implementation/independent reproduction/CI/operational claim is made. A milestone closure marks parent requirements partial until all allocated milestones and final gates are complete.

## Migration, Rollout, Rollback And Observability

New installs initialize owner-pinned control/genesis. Existing roots enter owner-authorized migration-only legacy adoption, preserve original bytes/authority and import into a new verified generation; exact selector cutover follows parity. No dual writer or fallback to old JSONL. Pre-new-write rollback uses explicit verified owner plan; accepted new writes forbid stale downgrade. Unsupported formats deny startup. Release readouts distinguish paused/unavailable, graph committed, pending projection/writeback, migration-only and reconciliation-required. Capacity and performance targets are design acceptance budgets, not promises already measured.

## Dirty Tree, Change Impact And Authority Chain

Preserve `docs/design/hermes_conversation_memory_trial.md` (uncommitted user change; do not commit or revert it). The design, this WorkPlan, the prior design/assessment packets and the release review are tracked on this branch at `ca845fc1`. Before implementation, record a fresh status/diff and reconcile any unrelated changes. [Identity/change ledger](identity-and-changes.md) owns planned files, authority descendants, gate impact and future live-diff updates.

## Validation, Toolchain And Known Gaps

[Workflow inventory](workflow-inventory.json) records exact current job definitions, matrices, working directories, environment expressions, commands, dependencies and artifact uploads. CI uses Python 3.11 for ordinary PR work and 3.12 for canonical authorities/parity. Local planning runtime is 3.12.14/SQLite 3.53.4; this is not CI parity. Planned Linux/macOS and actual-host gates do not exist merely because they are listed. No current gates run in this plan-only turn; prior design checks remain historical diagnostics. Known failures: none demonstrated by planning; unrun gates are unknown, not green. No quarantines or exemptions authorized.

Large new test suites and CI changes require a linked testing WorkPlan via design-tests before creation; this plan allocates behaviors and commands but does not perform that test-architecture operation. The first packet requires test_reviewer acceptance of the validation matrix before high-risk code. Narrow feature-local tests remain here. Reopen design on unresolved semantic ambiguity; do not silently choose compatibility behavior in a worker.

## Assumptions And Open Questions

- Verified facts: remediated design (delta-review batch applied) pinned by SHA in the baseline section; original review findings DREV-001..006 closed and the remediation delta-review dispositions recorded in the [remediation WorkPlan](../durable-memory-remediation/design.plan.md); all 18 requirements allocated in [coverage](coverage.md); current workflow inventory hashes verified against live workflow files; branch/base recorded in the baseline section.
- Working assumptions: CI Python 3.11/3.12 environments and existing gates remain available as inventoried; Node/npm and a TypeScript toolchain will be installable at SDK readiness; OpenClaw and Pi native APIs will be pinnable at the additional-harnesses milestone; Linux/macOS runners will be obtainable for the release matrix. Each is an execution prerequisite to confirm, not evidence.
- Unresolved questions: exact Node/npm/compiler versions and lockfile identity (pinned at SDK readiness per gates); exact OpenClaw/Pi native versions (pinned at milestone 6; absence blocks that host); final measured capacity envelope (design budgets are acceptance targets, revised only with evidence).
- Decisions requiring external input: release-asset signing setup (owner key configuration) remains an external prerequisite for exact-release evidence; runtime partition/checkpoint signing keys are provisioned by the installation key owner and are a separate authority. No other external decision currently blocks starting storage-foundation readiness.

## Delegation And Review Protocol

Planning: default read-only mapper reused because prior Spark code-mapper attempts were unavailable for this account; bounded root preflight in bindings. Coordinator owns all plan files. Terra-class test_reviewer consults validation/readiness before coding. Implementation: exactly one Terra worker per coherent slice; Spark read-only mapping/triage when available, otherwise documented bounded fallback. At each Level3 coherent milestone freeze candidate + updated bindings/live diff/gates, then concurrent spec/correctness/test review. Reconcile findings once; targeted deltas for bounded fixes, full review only after material contract change or final closure. Two consolidated remediation rounds per milestone; unresolved semantic decisions reopen design, unavailable environments/credentials become explicit evidence blockers rather than fabricated success. No repetitive broad runs after documentation-only edits.

## Progress And Planning Outcome

2026-09-29: planning requested; approved design checksum verified, repository/dirty-tree/toolchain baseline captured, live workflows inventoried, milestone and validation packets drafted. Mapper preflight completed; test-matrix consultation approved after two bounded planning corrections (public wrapper coverage and TypeScript gates), recorded in planning-review.md. Links, all18 requirements, eight milestone packets, baseline design SHA and live-workflow snapshot identities checked. Implementation remains proposed and unstarted.

2026-09-29: ontology branch merged to main (PR #123) and deleted; this WorkPlan, the design and review artifacts moved to `codex/durable-memory-release` from main `e6880a46` (commit `ca845fc1`). Final-approval design review returned Changes required (DREV-001..006); remediation now precedes implementation. Design SHA unchanged.

2026-09-29: remediation applied via the linked build-design WorkPlan (design findings DREV-001..004 + companions DREV-007/009; plan findings DREV-005/006/008 including validation/coverage family additions and this plan's assumptions section); design repinned. Delta review of the remediated candidate returned all DREV-001..009 closed plus a bounded revision batch (consolidation output set/neighborhood/edge-attachment carriers; validation-matrix mirrors for the four new design families; accumulator anchoring and stale-read carve-out; index staleness), applied and recorded in the remediation WorkPlan.

## Review Log

- 2026-09-29 storage-foundation milestone cohort (spec_auditor, correctness_reviewer, test_reviewer; independent concurrent passes) on frozen candidate 7c68b87d (code ac396adb). Coordinator reconciliation: five confirmed P2 design-of-implementation defects, all validated with repro and corrected in one batch (commit d867eca8) — managed-bundle bare-store bypass (spec-001/correctness-005), wedged init crash recovery (spec-002/correctness-004), manifest fold covering one of three catalogs (correctness-001, an indentation defect), missing publication anchor with tamper/rollback laundering (correctness-002), torn verification window plus unfenced init resolve (correctness-003). Conformance actions applied: identity ledger extended for sub-slices 2-3 (spec-003), control-database owner-only enforcement, interior-symlink rejection. Evidence actions applied: third-state quarantine, CAS sibling parameterization, concurrent-publisher contention, SIGKILL old-state proof, init crash-cut retries, per-catalog tamper tests. Recorded deferrals: incremental manifest accumulator (until DUR-11 capacity gate), publication-tuple/trust-registry field subset (until schema/policy registries), per-read Tier A (serving slices). Packet evidence inaccuracies corrected in the packet. Post-remediation: 114 affected tests green; ruff/pyright/identity gates green. Open before packet closure: per-shard CI-parity runs, CI integration-tier home for the partition-recovery file, one targeted delta review on d867eca8. No finding was blocks_approval; no external decision is missing.

## Next Action

Semantic-ontology sub-slice 2: implement MemoryPlaneQuery/MemoryPlanePage as closed typed reader contracts over the verified partition snapshot with authority-bound cursors, route the provider read paths (read_structured_facts, current_semantic_entity_matches, retrieve_context candidate selection, observe_graph detached cohorts) through them, and land tests/unit/core/test_memory_plane_query_parity.py proving indexed results equal authorized scans. Storage-foundation closure items remain queued in its packet (CI integration-tier home, per-shard CI-parity runs, delta review).
