# Literal Lifecycle Projection Debugging

- Work ID: `literal-lifecycle-projection`
- Work type: debugging
- Delivery fidelity: Level 2, early real-world manual testing
- Status: active
- Coordinator: `/root`
- Created: 2026-09-27
- Last updated: 2026-09-27
- Parent WorkPlan: `implementation.plan.md`
- Related WorkPlans: `milestones/default-catalog-and-home.plan.md`
- Canonical inputs: root `AGENTS.md`, `.agents/PLANS.md`, `.agents/skills/debug-problem/SKILL.md`, `docs/design/memory_evolution_runtime.md`, `docs/design/learned_ontology.md`, and the M3 milestone packet
- Expected outputs: a causal correction and focused regression for installed literal correction publication, followed by the frozen installed shared-mechanics rerun.

## Objective

Allow a retained-source LocalDate correction to publish its canonical semantic
projection through the existing conflict-authority boundary while preserving
the capture admission, retained-operation link, principal, tenant, scope, and
writer fences. Resume M3 only after the literal correction reproducer and its
ordinary retained-source siblings pass.

## Expected And Observed Behavior

Expected: the installed no-key `work_item_due_on` assertion commits, and a
grounded correction from `2026-10-03` to `2027-10-03` commits atomically before
protected lifecycle reads.

Observed on commit `902df81b`: the initial claim commits, but correction returns
`unavailable` after `250.34s`. Projection preparation calls semantic conflict
scope derivation and raises `projection_history_integrity_error` at the closed
source/index/operation join. The outer competing-lease error is downstream.
The retained failed snapshot is under pytest run `1167` and reproduces one of
one installed attempts.

Classification: implementation defect in an ordinary Level-2 literal
correction path. Entity correction remains a known working sibling at
`b3d8189d`.

## Identity And Authority Chain

The correction uses the existing captured source ID, a new retained structured
operation fence, its `semantic_ingestion_retained_source_operation` link, the
original capture admission index, and one preplanning control. No public or
persisted identifier recipe may change. The affected chain is capture source ->
original admission index -> retained-operation link -> current operation
control -> event evidence -> semantic conflict scope -> atomic projection.

## Hypothesis Ledger

| Hypothesis | Mechanism | Evidence | Discriminating experiment | Status |
| --- | --- | --- | --- | --- |
| Conflict scope assumes the original capture fence owns a preplanning control and ignores the retained-operation link. | `_derive_semantic_conflict_scope` looks up the admission index by contender source ID, then loads `operation:<original fence id>`; installed retained structured execution stores its control under a distinct linked fence. | All retained snapshot admission indexes have valid source/digest/scope fields, while operation controls exist under distinct structured fences joined by exact retained-source links. The pending group also carries its exact operation fence, and committed contenders can be joined through their immutable group-primary request. | Add a typed transaction-group-to-operation-fence input to conflict scope derivation; validate both direct and retained admission chains and deny missing or substituted links. | confirmed |
| Literal lifecycle incorrectly remains contested after correction, so conflict authority should never run. | Old and replacement literal values may both remain top candidates if transition application fails. | `work_item_due_on` is a single-cardinality current projection. Equal-rank old and replacement literal candidates therefore form the expected `contested_top`; entity relation siblings use set projection and do not exercise this authority path. | Compare the catalog read form and typed-claim grouping rules. | disproved |
| The test's literal correction shape creates a false semantic conflict. | A malformed corrected/replacement literal could bypass lifecycle matching but still reach projection. | Provider validation and native planner accepted the operation far enough to build a group; exact target selection has not yet been inspected for this failed run. | Compare retained corrected target and transition claim IDs with the initial claim and replacement claim IDs. | open |

## Experiment Ledger

| Experiment | Prediction | Result |
| --- | --- | --- |
| Inspect failed snapshot admission/source/control joins | If the leading hypothesis is correct, original index fields validate but control lookup by its fence fails while a retained linked control exists. | Confirmed for all retained source admissions; two structured operation controls exist under distinct fence IDs linked to their captured sources. |
| Inspect projection grouping and catalog read form | If conflict creation is valid, the literal relation is single-cardinality and equal-rank replacement values become `contested_top`. | Confirmed: `work_item_due_on` uses current/single semantics; the entity sibling uses set semantics. Conflict authority is required. |

## Completion Contract

At Level 2, the smallest retained-source conflict-scope reproducer must fail
before and pass after the correction. It must cover the normal admission path,
the linked retained-source path, and missing/substituted link denial. The
affected projection checks and frozen installed LocalDate correction must pass.
Targeted independent correctness and test review must find no remaining
Level-2 P1/P2 in this boundary. Hostile-store permutations remain Level 3.

## One Next Action

Implement the confirmed retained-operation admission join with focused direct,
retained, and denial regressions, then run the smallest projection test set.
