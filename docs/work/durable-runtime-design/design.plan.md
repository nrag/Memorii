<!-- Current frozen design SHA-256: ec927db8397e567b4087767b11572a5a5ab734bce55137fc4e8655c1d0ed97d2; prior hashes below are review history. -->

# Durable Runtime And Operator Experience Design

- Work ID: durable-runtime-design
- Work type: design
- Delivery fidelity: Level 3 first production release
- Status: complete
- Coordinator: main Codex task; sole canonical document writer
- Created: 2026-09-29
- Last updated: 2026-09-29
- Parent WorkPlan: ../first-release-assessment/investigation.plan.md (completed investigation)
- Related WorkPlans: ../learned-ontology/implementation.plan.md; ../learned-ontology/milestones/release-conformance.plan.md
- Canonical inputs: AGENTS.md, .agents/PLANS.md, build-design SKILL.md, memorii_spec.md, memorii_storage_details.md, event_model.md, IMPLEMENTATION_RULES.md, scoped_memory_context.md and inspected current code/tests
- Expected outputs: docs/design/durable_execution_and_solver_runtime.md; baseline/evidence/review records in this directory

## Objective And Problem

Design production durable execution/solver state, delivery of that state back to Hermes/OpenClaw/Pi, and usable operation/user controls. Verify the reported gap before specifying changes. User explicitly defers the agent-benefit benchmark plan until other release aspects are complete; retain deterministic recovery/performance acceptance here, not a comparative benchmark campaign.

## Completion Contract

Stable measurable requirements; explicit public/persisted/authority/transaction/harness/operational contracts; current production binding map; bounded feasibility proof for uncertain storage choice; alternatives and migration/rollback; failure/attack/test matrices; coherent independently reviewed frozen design with all three standard reviewers; final full review and no unresolved validated P1/P2 or required conformance finding. Product implementation and production certification remain separate.

## Scope And Constraints

Includes execution and solver structures, overlay/justification history, directory/task context, events/checkpoints, concurrent durable command admission, source references, safe resume, typed harness context/tools, local sidecar and embedded composition, pause/bypass, inspect/export, backup/restore, retention/forget semantics and deployment diagnostics. Excludes new reasoning algorithms, semantic ontology redesign, automatic external action execution, distributed storage, remote hosted service rollout, agent-benefit benchmark/publication plan. Preserve domain separation, conservative commit, canonical event semantics, and host-owned tools/models.

## Baseline And Changed Surface Ledger

HEAD bad9eeefb43f7f42fb95d583b11859e2f2ca9eb8. Pre-existing user design modification: docs/design/hermes_conversation_memory_trial.md. Prior assessment artifacts: docs/work/first-release-assessment/. Preserve both. This operation owns only docs/design/durable_execution_and_solver_runtime.md and docs/work/durable-runtime-design/. No governing hashed design, code, schema, generated package or workflow is modified.

## Sources And Current Facts

Source precedence follows AGENTS.md. memorii_spec sections 17-20 already require durable execution/solver state and host outputs. Storage details require checkpoints, scoped reads and local operation. Event model requires full-state typed registered batches and atomic replay indexes. Current api/service.py injects four stores; resume reads those stores; core/execution/service.py performs separate graph/overlay/event writes; core/persistence/replay.py handles nodes/edges only. Resume and integration tests use the same in-memory objects. The semantic-memory durable path is separate and must not be described as absent.

## Requirements And Identity Ledger

Canonical design owns the complete requirement/identity/production-binding and acceptance matrices; WorkPlan references rather than duplicates them. Requirement IDs are traceability only. New document and proposed module/type/tool names describe durable behavior. No new executable identity introduced during design. Future implementation must extend the existing field-aware identity gate and mutation corpus.

## Assumptions And Decisions

Verified: only supplied execution/solver/overlay/event backends are in-memory; current runtime mutations lack one unit of work. Working deployment assumption: local single-account installation, explicit task/agent grants, supported local filesystem, multiple harness clients via one authority owner. No new cloud vendor decision required. Proposed storage choice and erasure scope must be explicit in the canonical design; do not infer source permissions from IDs.

## Milestones And Budget

1. Verify baseline and owner map; run focused existing tests plus discriminating process/storage prototype. Status: complete; evidence.md.
2. Draft complete contract, alternatives, entrypoint bindings and acceptance matrix. Status: complete; canonical design.
3. Freeze design, run concurrent spec/correctness/test review, reconcile one coherent remediation batch; two planned conformance batches plus one bounded final bootstrap clarification. Status: complete; two consolidated conformance batches, reviews.md.
4. Fresh final whole-design three-role review, link evidence and close. Status: complete; final three-role approval recorded in reviews.md.

## Delegation And Cost

- persistence_map: default read-only agent, actual runtime/storage/replay map; Spark roles are known unavailable from prior assessment. Complete.
- harness_ops_map: default read-only agent, scoped provider/harness and operations map. Complete.
- Canonical writer: coordinator only. Standard Terra-class three-role review cohort completed first review; fresh full final review completed.

## Evidence And Gate Ledger

Design-only gates: cited baseline verification, focused diagnostic tests, standalone storage feasibility experiment, Markdown/link/checksum and diff checks, independent frozen design review. No product CI parity or operational certification claimed. Baseline tests and bounded probes passed; evidence.md distinguishes toy feasibility from product proof. Final full three-role design review passed for the frozen candidate. Failed discovery commands for nonexistent guessed paths were followed by rg inventory; they are not product failures.

## Progress

2026-09-29: user authorized design and inclusion of operations/user controls. Read build-design skill and governing documents. Verified same-store resume, separate writes, broad untyped legacy events and in-memory directory. Launched independent read-only maps. Production code unchanged.

2026-09-29: completed baseline probes and first full review. Reconciled six confirmed conformance families in one batch; no production code changes. Fresh final whole-design cohort active on the revised frozen SHA recorded in reviews.md.

2026-09-29: final cohort exposed a shared publication/control authority gap. Reconstructed the complete boundary in the second/final conformance batch; new frozen full review active. Publication feasibility remains specified, not production-proven.

## Next Action

No further design action; deliver the approved design. Any implementation starts a separate linked implementation WorkPlan.

## Outcome And Retrospective

Completed design-only objective: confirmed the precise runtime durability gap while preserving the separate provider-memory durability claim; specified durable execution/solver recovery, Hermes/OpenClaw/Pi state delivery and usable operator controls. All 14 requirements have measurable acceptance and production-binding plans. All three reviewers approved the final frozen artifact; no unresolved confirmed required finding or external decision remains. Source checks, eight existing diagnostic tests, bounded SQLite/reducer probes, links/identity inventory and final freeze checks are recorded in evidence.md. Existing production code and user Hermes design edit remain untouched.

Residual implementation obligations: production schemas/backend, signed publication and control bootstrap, all-writer enrollment, actual-host callbacks, capacity targets, installed platform tests and release evidence are specified but unimplemented/unverified. Toy experiments do not certify these mechanisms. Agent-benefit benchmark and publication planning remain deferred by user instruction. The review usefully exposed cross-file publication and fresh-install authority gaps; they were closed in the design rather than hidden as implementation choices.
