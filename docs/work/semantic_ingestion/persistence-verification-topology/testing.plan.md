# Semantic Persistence Verification Topology

- Work ID: semantic-ingestion-persistence-verification-topology
- Work type: testing
- Status: active
- Coordinator: Codex main thread
- Created: 2026-08-05
- Last updated: 2026-08-05
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/milestones/m3-semantic-pipeline.plan.md`, `docs/work/semantic_ingestion/milestones/m4-event-history.plan.md`
- Canonical inputs: `.github/workflows/pr-gates.yml`, `memorii/tests/ci/semantic-terminal-persistence-shards.json`, `memorii/tests/ci/semantic-terminal-persistence-test-durations.json`, `memorii/tests/unit/core/semantic_ingestion/test_semantic_terminal_persistence.py`
- Expected outputs: a representative sub-five-minute PR-fast persistence gate and a complete parallel merge-blocking exhaustive persistence gate

## Objective

Give pull requests a representative persistence signal in under five minutes
without deleting, weakening, or removing exhaustive durability proof from
required PR verification.

## Completion Contract

- Live collection and timing manifests have exact node-set equality.
- A required fast job covers representative commit, rejection/no-effect, JSONL
  reopen, retry/lost-ack, authorization, and corruption families within a
  180-second measured test budget plus 120 seconds setup/headroom.
- A required exhaustive matrix owns every terminal-persistence node exactly
  once outside broad unit shards, with measured budget and timeout headroom.
- Workflow structure tests prove exact selection, aggregation, and timeouts.
- Independent test and correctness reviews have no remaining required finding.

## Scope

Included: timing capture, representative selection, shard rebalancing, workflow
jobs and aggregation, owner manifests, workflow contracts, and runtime docs.
Excluded: product-semantic changes, weaker assertions, deleting durability
families, or treating the fast sample as exhaustive evidence.

## Constraints And Invariants

Broad unit shards continue to exclude the dedicated terminal file. Exhaustive
verification remains merge-blocking and family-complete. Fast/exhaustive
overlap is intentional latency-signal overlap, not duplicate exhaustive
ownership. Hosted timing remains a separate evidence class.

## Identity And Coordinate Hygiene

New jobs and artifacts use behavioral persistence-verification names. Planning
or evidence coordinates may not enter executable identities.

## Change Impact And Verification Closure

Expected surfaces are terminal persistence tests/support, shard and timing
manifests, deterministic job owners, shard tooling if necessary, workflow,
workflow structure tests, and static-tooling docs. Reconcile the live diff and
all workflow dependencies before review.

## Sources Of Truth

The design-test skill and `.agents/PLANS.md` govern topology and evidence;
current workflows govern required jobs; live collection and revision-bound
timings govern counts and budgets.

## Current State

Live collection has 223 nodes. The timing manifest contains 156 entries, only
155 of which still match; 68 live nodes are unmeasured and one entry is stale.
Seven configured shards estimate about 645 seconds each and fail the 600-second
budget. Broad unit shards already exclude the file.

## Assumptions And Open Questions

Verified: current shard verification fails closed. Working assumption: eight
or more exhaustive shards meet budget after fresh measurement. Unresolved:
hosted runner overhead until the exact workflow runs. No external product
decision is required.

## Milestones Or Experiments

1. Capture exact current timings and prove node-set equality.
2. Select and measure the representative fast family.
3. Rebalance exhaustive coverage without duplicate ownership.
4. Wire workflow aggregation and structure contracts.
5. Run frozen test/correctness review and record closure.

## Progress Log

- 2026-08-05: Inventory found 223 live nodes versus a stale 156-node pin and
  selected a required fast-plus-exhaustive topology.

## Evidence Log

- Live collection: 223 nodes.
- Current shard estimates: approximately 644.8 seconds versus 600-second target.
- Historical timings: 3,662.092 node-seconds; 19 nodes exceed 60 seconds.

## Decision Log

- Keep exhaustive durability verification required on PRs, parallelize it, and
  add a separate representative fast gate. The fast sample never establishes
  family completeness.

## Review Log

No frozen-candidate review yet.

## Blockers And Limits

No runtime claim is valid until fresh timings cover the exact live node set.

## Next Action

Capture revision-bound timings for all live terminal-persistence nodes and
regenerate an exact timing manifest before choosing exhaustive shard count.

## Outcome And Retrospective

Active. No closure claim yet.
