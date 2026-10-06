# First Release Assessment

- Work ID: first-release-assessment
- Work type: investigation
- Delivery fidelity: Level 3 assessment, not production certification
- Status: complete
- Coordinator: main Codex task
- Created: 2026-09-29
- Last updated: 2026-09-29
- Parent WorkPlan: None
- Related WorkPlans: ../hermes-level2-pr/pr-review.plan.md; ../learned-ontology/implementation-readiness.md
- Canonical inputs: AGENTS.md; .agents/PLANS.md; docs/design/memorii_spec.md; docs/design/memorii_storage_details.md; docs/design/event_model.md; docs/IMPLEMENTATION_RULES.md; current production code, tests, workflows, and official harness documentation
- Expected outputs: assessment.md with prioritized gaps, integration recommendations, evidence limits, and release exit criteria

## Objective

Determine what must be completed for a useful first production release and how OpenClaw and Pi should integrate without coupling core memory behavior to a harness. The user corrected the initial OpenAI wording during investigation.

## Completion Contract

Answer all four user questions; inspect current implementation and recent evidence; distinguish demonstrated defects, explicit deferrals, missing evidence, and product recommendations; reconcile independent investigations; cite sources; record a concrete release sequence. This is an assessment, not a full branch audit or certification run.

## Scope

Included: integration feasibility, Level 3 hardening, critical product gaps, onboarding, and evaluation. Excluded: product edits, new normative designs, live paid evaluations, deployment, PR approval. Proposed integrations require separate design/implementation work.

## Constraints And Invariants

Preserve framework-neutral core, typed contracts, authenticated scope, candidate/commit separation, append-only observations, and independently validated model output. Do not treat historical plans as current code proof.

## Baseline And Changed Surfaces

Inspected HEAD: bad9eeefb43f7f42fb95d583b11859e2f2ca9eb8. Pre-existing user modification: docs/design/hermes_conversation_memory_trial.md; read as working design context, preserve unchanged. This investigation owns only this directory's documentation. No runtime or protocol identifiers introduced; identity ledger not applicable beyond planning/evidence coordinates.

## Method And Budget

One focused local investigation plus two independent read-only investigations, followed by one reconciliation pass. Inspect primary upstream documentation for OpenClaw and Pi. Initial OpenAI research was superseded by the user's correction. No broad test rerun: inspection cannot certify this dirty tree. Record unavailable exact-release evidence explicitly.

## Progress And Evidence

- Repository has a working first-party Hermes path; older integration plans contain superseded missing-factory statements. Current README labels early real-world testing and explicitly disclaims agent-level task improvement.
- Official OpenAI SDK documentation supports custom storage and tools/MCP. Pi current extension documentation supports external storage, lifecycle integration, and MCP; verify precise event semantics before recommendations.
- Two initial specialized explorer attempts failed because their model is unavailable. Replaced with two default read-only agents: release_gaps and usefulness.

## Verification And Findings Ledger

Completed in assessment.md. Confirmed current local authority binding, generic authenticated adapter, Level 3 release deferrals, in-memory execution/solver stores and soft-limit-only maintenance. Rejected stale blanket missing-factory/no-rollback claims; reclassified missing matrices and measurements as evidence gaps rather than product outages. OpenClaw manifest, memory-core code, typed prompt hooks and plugin permissions were opened and read after the user correction. Runtime tests, hosted CI state, live quality, and release certification were not performed. All four requested questions are answered with explicit release exit criteria and limits. Only documentation in this directory changed; the user-owned design remains untouched.

## Next Action

None; assessment complete. Recommended successor: manually validate the five Level 2 ontology journeys and select the first-release support boundary before activating a linked Level 3 implementation WorkPlan.
