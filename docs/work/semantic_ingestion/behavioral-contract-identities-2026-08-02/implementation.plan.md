# Implement Semantic Ingestion Behavioral Contract Identities

- Work ID: semantic-ingestion-behavioral-contract-identities-implementation-2026-08-02
- Work type: implementation
- Status: active
- Coordinator: Codex main thread
- Created: 2026-08-02
- Last updated: 2026-08-02
- Parent WorkPlan: docs/work/semantic_ingestion/behavioral-contract-identities-2026-08-02/design.plan.md
- Related WorkPlans: docs/work/semantic_ingestion/implementation.plan.md; docs/work/semantic_ingestion/behavioral-test-taxonomy-2026-08-02/testing.plan.md
- Canonical inputs: docs/design/semantic_ingestion_architecture.md Section 5.9.8; current semantic-ingestion production composition
- Expected outputs: behaviorally named production API and persisted contracts; regenerated authority; deterministic verification and independent closure

## Objective

Implement the approved hard cutover so current production code and persisted
semantic-ingestion bytes contain no delivery milestone, phase, review, task, or
executable requirement identity, while stable traceability metadata remains
intact.

## Completion Contract

Complete only when every approved production mapping is implemented with no
aliases; old bytes fail closed; production/static scans are clean; derived
authority and frozen bytes are regenerated through canonical owners; focused,
exact semantic, acceptance, generation, scenario, unit-shard, Ruff, Pyright,
and diff gates pass as applicable; and final independent reviews have empty
required-finding arrays.

## Scope

Included: semantic-ingestion public/private symbols, digest domains, envelope,
codec, discriminators, lease/member/plan IDs, M2 admission/fingerprint values,
provider/benchmark diagnostics, canonical requirement-universe helper, and
authority regeneration necessitated by the design bytes.

Excluded until the linked testing operation: test-node/fixture/helper/CI-label
renames, R01-R23 executable registry bindings, static naming guard, public-wire
test generator/vector, and scenario coordinate migration implementation. M4 is
out of scope.

## Constraints And Invariants

No compatibility aliases or upcasters. Old unshipped bytes reject before
effects. Atomicity, authorization, fencing, retry, lost-ack, trust resolution,
and provider result behavior remain unchanged. Preserve unrelated staged and
working-tree edits.

## Sources Of Truth

Root governing documents and the approved parent design, with production code
as implementation evidence.

## Current State

HEAD is `7b5313a0d4953510258acec4818f4b595ce6278f`. The tree has nine entries,
including the approved design, prior CI compatibility fix, and behavioral test
file renames. Production still uses the old identities.

## Assumptions And Open Questions

The feature is unshipped and hard cutover is approved. No external decision is
required.

## Milestones Or Experiments

1. Rename production symbols and all runtime/persisted identities. In progress.
2. Add old-byte rejection and production identity scans. Pending.
3. Regenerate design-bound authority required before testing handoff. Pending.
4. Coordinator integrity check and linked testing handoff. Pending.
5. Final deterministic verification and independent review after testing
   operation returns. Pending.

## Progress Log

- 2026-08-02: Approved design handed off with clean three-role closure. Next
  action: implement the complete production mapping with one writer.

## Evidence Log

Design SHA-256 at handoff:
`c065b7a7e3a71d6c9be5be7dbe0c5a99175f0fdf99b34c7217bcadb07195ae25`.

## Decision Log

No aliases; behavioral `.v1` is the first shipped identity. Requirement IDs
remain typed traceability metadata.

## Review Log

Implementation review has not started.

## Blockers And Limits

No blocker. Authority regeneration may expose further source pins; those are
handled through canonical generators rather than manual hash edits.

## Next Action

Implement the complete production symbol and persisted-identity mapping.
