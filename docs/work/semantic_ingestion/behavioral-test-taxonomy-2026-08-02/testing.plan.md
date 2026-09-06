# Semantic Ingestion Behavioral Test Taxonomy

- Work ID: semantic-ingestion-behavioral-test-taxonomy-2026-08-02
- Work type: testing
- Status: proposed
- Coordinator: Codex main thread
- Created: 2026-08-02
- Last updated: 2026-08-02
- Parent WorkPlan: docs/work/semantic_ingestion/behavioral-contract-identities-2026-08-02/design.plan.md
- Related WorkPlans: docs/work/semantic_ingestion/implementation.plan.md
- Canonical inputs: memorii/tests; .github/workflows; memorii/tests/ci; docs/development/static_tooling.md
- Expected outputs: stable behavioral test/fixture/helper/CI names; stronger static naming guard; unchanged behavioral coverage

## Objective

Remove implementation milestone, phase, review-round, task, and requirement IDs
from durable test taxonomy and CI display names while preserving requirement
IDs only where they are the typed data under test in traceability-specific
tools and malformed-input vectors.

## Completion Contract

Complete when the classified retention map is exhaustive; every improper name
is behaviorally renamed with all references; legitimate traceability-data
exceptions are explicit and narrow; collection counts, timing ownership, gate
placement, and failure signals are preserved; the static guard covers files,
symbols, helpers, fixtures, and CI names; applicable deterministic suites pass;
and independent correctness/test review has empty required-finding arrays.

## Scope

Included: test filenames, test symbols, helper/fixture names, operation and
admission fixture identities, golden member IDs regenerated from corrected
production contracts, CI step display names, static assertions, timing node
IDs changed by rename, and current test documentation.

Excluded: typed requirement IDs used by traceability registries/checkers as
data; explicit invalid/unknown requirement vectors; prompt-domain requirements;
historical WorkPlans; genuine protocol version labels.

## Constraints And Invariants

- No behavior or failure-family coverage is weakened.
- Frozen expected bytes are regenerated through production paths, not patched
  without provenance.
- The exact semantic-ingestion collection lock remains 266 unless tests are
  intentionally added or removed.
- The duration-balanced unit inventory remains complete after node-ID changes.
- CI job ownership and aggregate dependencies remain unchanged unless the
  design explicitly requires a behavioral job rename.

## Sources Of Truth

The parent design WorkPlan and approved design delta govern naming semantics.
Current tests, workflows, timing manifests, and `docs/development/static_tooling.md`
govern collection and CI placement.

## Current State

Three milestone-named semantic-ingestion unit/support files have been renamed;
54 focused tests pass and the 2,584-test shard plan remains complete. The static
guard currently inspects only test function declarations and explicitly allows
requirement-named semantic integration tests. CI has two M3-labelled display
steps. Broader M1/M2/M3 and requirement-ID fixture/name inventory is active.

## Assumptions And Open Questions

Verified: requirement IDs are legitimate data only within traceability contract
testing. Working assumption: tests proving product behavior need behavioral
names even when they also supply traceability evidence. No external decision is
currently required.

## Milestones Or Experiments

1. Classified name and coverage inventory. Status: complete.
2. Stable topology and static-guard design. Status: in progress.
3. Rename/reference implementation with regenerated evidence. Status: pending.
4. Collection, timing, CI, deterministic, and independent review closure.
   Status: pending.

## Progress Log

- 2026-08-02: Expanded from three M3-named files to repository-wide current
  semantic-ingestion taxonomy after user identified M1/M2 and R22 debt. Next
  action: complete the classified retention map.
- 2026-08-02: Classified 24 requirement-named integration nodes, R01-R23
  executable group/command/primary acceptance nodes, positive M2/M3 fixture
  values, two CI labels, frozen JSONL member identities, and scenario-C2
  authority names for behavioral replacement. Stable requirement/test IDs in
  traceability metadata and explicit malformed/legacy vectors are retained.

## Evidence Log

- Baseline focused renamed suites: `54 passed in 189.44s`.
- Baseline deterministic unit plan: 2,584 collected with shard counts
  `[12, 1026, 718, 828]`.
- Current semantic-ingestion exact collection lock: 266.

## Decision Log

- Requirement IDs remain only as explicit traceability data, never as the name
  of a general product-behavior test, fixture, helper, or CI step.

## Review Log

No coherent expanded-scope review yet. Three read-only classified audits are
active.

## Blockers And Limits

No current blocker. Production semantic changes remain owned by the parent
design and a future linked implementation WorkPlan.

## Next Action

Await completion of the production contract-identity cutover, then implement
the approved test taxonomy and evidence regeneration as a separate operation.
