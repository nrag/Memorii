Current frozen candidate: 22e29f90ab90fa9b67b489d8f293b4a9ecbe4e5bf1dad7c0d6d3f2a7697706ad

# Shared SQLite Storage Design Extension

- Work type: design
- Status: complete
- Fidelity: Level 3 first production release
- Coordinator / sole writer: main task
- Parent: ../durable-runtime-design/design.plan.md (complete, prior approved scope)
- Canonical: ../../design/durable_execution_and_solver_runtime.md
- Baseline: bad9eeefb43f7f42fb95d583b11859e2f2ca9eb8; prior document archived here by SHA

## Objective / Scope

Extend the approved runtime design to one SQLite application-data database per isolation partition for semantic entity/relationship records, mutable ontology state and runtime state. Preserve domain contracts, canonical bytes, package authority and independent control authority. Define migration from existing durable JSONL, indexed reads and operational implications. No implementation or agent-benefit benchmark campaign.

## Completion Contract

Complete contract/requirement/identity/production binding and evidence matrices; material feasibility probe; migration/rollback and failure behavior; first and final whole-design three-role reviews; no unresolved confirmed required findings. Product runtime remains unimplemented.

## Sources / Baseline

AGENTS.md, .agents/PLANS.md, build-design skill, memorii_spec, memorii_storage_details, event_model, IMPLEMENTATION_RULES, learned_ontology and its installed-Hermes addendum; current MemoryPlaneStore, JsonlMemoryPlaneStore, MemoryPlaneUnitOfWork, filesystem bundle and semantic/catalog owners/tests. Existing provider memory is durable. JSONL replacement rewrites full history. Existing write revision and runtime-context data revision are distinct. Current canonical record content can contain legacy dictionaries; migration cannot reclassify unknown bytes as newly validated truth.

## Changed Surface / Authority

Only canonical design and this work directory are owned. Preserve existing user Hermes design edit and prior assessment/design records. No governing digest-bound semantic specs, generated schemas, packaged catalog resources, code, workflows or production data change. Existing runtime document approval remains historical only after expansion.

## Milestones / Budget

1. Map owners and establish discriminating migration/transaction feasibility. Complete; evidence.md.
2. Revise coherent design and inventories. Complete draft.
3. Frozen full independent review, at most two consolidated conformance rounds. Complete first review and one consolidated remediation; reviews.md.
4. Fresh final whole-design review and completion evidence. Complete; all three roles approved final candidate.

## Decisions / Constraints

Share engine and physical data transaction coordinator, not domain meaning. Separate protected control database. Keep immutable package catalogs as package resources. No permanent dual-write authority; JSONL migration is offline, validated and reversible before new writes. Main writer only; read-only mapper and spec/correctness/test roles.

## Evidence / Review

Evidence recorded in evidence.md; review dispositions in reviews.md. Planned production callers are specified, not represented as existing. Baseline existing tests and toy mechanism evidence do not certify production migration or SQLite backend.

## Next Action

No further design action; deliver the revised document. Implementation requires a separate linked implementation WorkPlan.

## Progress

Baseline owner mapping and tests/probe complete. Shared database changes preserve existing logical owner contracts. Coherent draft includes all 18 requirements, transaction/query/migration and corresponding identities/gates. Historical first-review candidate: dd852f746068a3fe3d960c9566df06fa163d00b13b80e5608bacdaf4a0d457d5

## Outcome And Retrospective

User-requested design extension complete. Shared SQLite physical storage now covers full memory-plane history, semantic graph indexes and mutable ontology state alongside runtime, preserving each domain owner, canonical identity, visibility and both revision counters. Package catalogs and independent control authority retain their owners. Offline JSONL migration includes owner-pinned legacy adoption, verified parity, exact old/new selector recovery and safe rollback limits. All current construction/reopen/diagnostic and protected-query precursors have explicit future bindings and gates. DUR-01 through DUR-18, identity inventory and release proof families are reconciled.

Validation: 27 memory-plane baseline tests + 14 ontology baseline tests passed; bounded real JSONL/toy SQLite migration probe passed; link/requirement/whitespace/frozen-identity checks passed; full final three-role design review approved. No production code or data changed. Earlier runtime approval was archived by content hash; this expanded approval supersedes it for the canonical design. Existing user Hermes design edits remain untouched. Benchmarks proving agent benefit remain deferred. Residual obligations are production implementation, installed-root parity/migration, measured capacity and Level3 release evidence, all explicitly specified but unproven.
