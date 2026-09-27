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
| A grounded correction remains contested because projection derivation ignores its retained lifecycle transition. | Replay retains old and replacement claim assertions plus a temporal transition. `_typed_claim_projection_records` arbitrates every same-slot claim but does not apply the transition's exact corrected/retracted target IDs first. | The repaired installed run reaches the offline resolver and fails with `local Level 2 conflict resolution is unavailable`. General equal-rank independent claims must remain contested, but this correction already carries exact target authority. `TemporalTransitionRecord` alone lacks target IDs; verified native group request/reload effects retain them. | Reconstruct the complete retired-claim set from verified committed group primaries plus the pending typed group request, pass it into replay projection derivation, and prove only lifecycle-targeted claims become `retained_noncurrent`. Independent equal-rank claims must remain contested. | confirmed |
| The test's literal correction shape creates a false semantic conflict. | A malformed corrected/replacement literal could bypass lifecycle matching but still reach projection. | Provider validation and native planner accepted the operation far enough to build a group; exact target selection has not yet been inspected for this failed run. | Compare retained corrected target and transition claim IDs with the initial claim and replacement claim IDs. | open |

## Experiment Ledger

| Experiment | Prediction | Result |
| --- | --- | --- |
| Inspect failed snapshot admission/source/control joins | If the leading hypothesis is correct, original index fields validate but control lookup by its fence fails while a retained linked control exists. | Confirmed for all retained source admissions; two structured operation controls exist under distinct fence IDs linked to their captured sources. |
| Inspect projection grouping and catalog read form | If conflict creation is valid, the literal relation is single-cardinality and equal-rank replacement values become `contested_top`. | Confirmed: `work_item_due_on` uses current/single semantics; the entity sibling uses set semantics. Conflict authority is required. |
| Propagate pending operation authority through projection preparation | If both conflict-resolution passes receive the exact pending group fence and writer binding, a real retained admission/link/control chain will prepare; omitting the map or removing the link will deny. | Commit `f59261b0` passes the real-record regression in both positive and fail-closed forms; 21 focused projection/retained-operation checks pass. Independent review then found its committed-contender group-primary decoder incomplete, so the candidate is not accepted. |
| Run installed LocalDate lifecycle probe after authority repair | If the admission join was the only defect, correction commits; if lifecycle projection still treats replacement as an independent contradiction, the no-model runtime reaches its deliberately unavailable general resolver. | At `18e72183`, initialization and the initial LocalDate assertion/read pass. Correction fails after `281.99s` in `resolve_semantic_conflicts` with `local Level 2 conflict resolution is unavailable`. This confirms the transition overlay is absent from projection arbitration; the lease error is downstream. |
| Retire verified lifecycle targets before projection arbitration | If correction/retraction targets are removed from the current candidate set before trust and temporal selection, replacements can win while independent equal-rank claims remain contested and retired evidence stays historical. | Commits `e96ad054` and `e4a80771` implement the shared verified lifecycle reader, committed-plus-pending target reconstruction, pre-arbitration retirement, and deterministic publication refresh. The five affected unit files pass `129 passed in 187.15s`; the publication compiler passes `23 passed`; Ruff, compileall, and diff checks pass. |
| Run installed lifecycle and symmetric-read probe at `286897d5` | If lifecycle retirement is complete, correction and retraction commit, current/history/as-of reads select the lifecycle-valid value, and symmetric reads survive reopen. | After `1433.57s`, correction and retraction both commit; corrected current, retracted current, complete history states, and pre-correction as-of pass. Pre-retraction as-of incorrectly returns both the superseded original and replacement instead of only the replacement. Symmetric/reopen steps are not reached. The projection contest defect is resolved; historical effective-interval filtering remains defective. |

## production_entrypoint_bindings

The required Spark `code-mapper` preflight was attempted for frozen commit
`f59261b0` and failed before repository inspection because the configured
`gpt-5.3-codex-spark` model is unavailable for this ChatGPT account. The
coordinator produced this bounded replacement map from the exact searches
`rg -n "_prepare_native_projection_publication\\(" memorii/memorii`,
`rg -n "resolve_semantic_conflict_authority\\(" memorii/memorii`, and
`rg -n "submit_structured_fact\\(" memorii/memorii` so the operation can
continue without fabricating a successful delegate run.

| Requirement | Canonical trigger and composition root | Exact callsite and arguments/authority | Owner chain: validation -> write/read -> outcome | Proof and caller count | Status or explicit blocker |
| --- | --- | --- | --- | --- | --- |
| Retained LocalDate correction conflict publication | Installed `MemoriiHermesMemoryProvider.handle_tool_call("memorii_submit_fact", correction)` composed by `build_local_level2_runtime_binding` into `HermesCompletedTurnRuntime` and `ProviderMemoryService` | `HermesCompletedTurnRuntime.handle_tool_call` validates captured pin/default-catalog lifecycle grounding and calls `ProviderMemoryService.submit_structured_fact`; that owner allocates the retained operation and calls `execute_retained_structured_proposal`; `SemanticIngestionAtomicStore.commit_or_reload_bootstrap_graph_group_v3` calls `_prepare_native_projection_publication` with the pending group request, exact operation-fence binding, and writer binding | captured turn/pin and proposal validation -> retained source admission/link/control -> native group reduction -> verified committed and pending lifecycle targets -> projection conflict resolve and prepare -> same group CAS persists primary/reload, projections, replay authority and structured claim binding -> protected current/history/as-of read | `rg` finds one production structured-fact caller, one native group callsite at `atomic_store.py:16232`, and one generic terminal callsite at `atomic_store.py:17873`; 129 affected-family checks and 23 publication checks pass. Frozen installed probe `test_installed_default_catalog_literal_retraction_and_symmetric_reads_survive_reopen` is outstanding. | candidate implemented; installed proof outstanding. |
| Generic committed terminal conflict publication | `SemanticIngestionAtomicStore` committed terminal replay path | `atomic_store.py:17834` passes `{batch.transaction_group_id: request.operation_fence_binding}` and `request.writer_commit_binding` into the same `_prepare_native_projection_publication` owner | validated terminal group closure -> shared projection resolve/prepare -> replay aggregate/checkpoint CAS | One production caller; same shared owner and focused prepare proof. No separate default-catalog trigger reaches this path in the frozen installed scenario. | implemented supporting root; retained LocalDate closure depends on the native group root above. |

## Frozen Candidate And Review

- Candidate commit: `f59261b06fcd131b62a1bdabea958ee0d951cec4`.
- Dirty tree at review: only the preserved user-owned
  `docs/design/hermes_conversation_memory_trial.md` modification.
- Focused evidence: `21 passed, 31 deselected in 8.90s`; targeted Ruff and
  `git diff --check` passed.
- Test review first blocked on the missing entrypoint ledger above. Correctness
  review then confirmed a Level-2 P2: a committed contender's group primary
  was accepted without closed lifecycle/content and coherent reload proof.
- Level-3 corrupt/duplicate-primary matrices remain deferred. The ordinary
  malformed/missing reload denial is part of the current Level-2 correction.

Delta `b162a667` plus regenerated authority commit `18e72183` resolved the
committed-primary P2 and received targeted correctness/test approval for the
installed probe. The probe advanced past that join and exposed the confirmed
lifecycle-overlay defect above. No milestone or requirement count changes.

Candidate delta `e96ad054` plus generated publication `e4a80771` now retires
only exact correction/retraction targets from current arbitration while
preserving them as `retained_noncurrent`. Independent equal-rank claims remain
contested, and an all-retired slot has no selected or contested assertion.
Affected-family and publication checks pass. The installed probe at `286897d5`
proves correction and retraction publication plus current and complete-history
reads, but exposes an as-of interval bug before reaching symmetric/reopen
checks. Targeted independent review remains outstanding, so no milestone or
requirement count changes yet.

## Completion Contract

At Level 2, the smallest retained-source conflict-scope reproducer must fail
before and pass after the correction. It must cover the normal admission path,
the linked retained-source path, and missing/substituted link denial. The
affected projection checks and frozen installed LocalDate correction must pass.
Targeted independent correctness and test review must find no remaining
Level-2 P1/P2 in this boundary. Hostile-store permutations remain Level 3.

## One Next Action

Correct lifecycle history `system_as_of` filtering so a superseded assertion
ends when its correction is recorded and a replacement ends when retracted,
then run focused read regressions before restarting the installed probe.
