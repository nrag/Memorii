# Implementation Resume Packet

Parent: [implementation index](implementation.plan.md). Status proposed; plan creation complete, product implementation not started.

Read AGENTS.md and .agents/PLANS.md, then this packet, [storage foundation](milestones/storage-foundation.plan.md), [bindings](production_entrypoint_bindings.md), [validation](validation.md), [gates](gates.md), [identity/change ledger](identity-and-changes.md) and the approved canonical design referenced in the index. Do not reload prior design review history unless a named contract is disputed.

Design SHA: 22e29f90ab90fa9b67b489d8f293b4a9ecbe4e5bf1dad7c0d6d3f2a7697706ad. Implementation branch `codex/durable-memory-release` from main `e6880a46` (ontology work merged via PR #123; planning HEAD `bad9eeef` contained in main); artifacts committed at `ca845fc1`. The 2026-09-29 final-approval review returned Changes required — design findings DREV-001..004 and plan-matrix findings DREV-005/006 must be remediated ([report](../../reviews/durable-execution-and-solver-runtime/2026-09-29-final-approval.md)) before implementation starts. Preserve the uncommitted user edit to docs/design/hermes_conversation_memory_trial.md. CI/environment availability beyond the planning inventory is not yet established; capture current status before work.

The first slice is a real initialized partition -> selected provider -> canonical memory/semantic/ontology owner -> restart journey, not a detached backend library. Basic authorization, signed publication, dual revisions/CAS and common-crash behavior are prerequisites. Later packets add indexed readers, legacy migration, runtime graphs, hosts and all-owner operations. No comparative agent-benefit benchmark here.

Current maturity: specified only, with historical design diagnostics. Root mapping reports zero callers for every new design path. Test-matrix consultation is recorded in planning-review.md. Before substantial new suites/CI, activate a linked design-tests operation; before code, refresh actual owner/codec/generated/identity inventory and verify baseline. The index contains the one current next action.
