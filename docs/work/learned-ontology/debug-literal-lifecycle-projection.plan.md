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
| Apply transaction-time lifecycle filtering to both read backends | If any `system_as_of` query reconstructs the effective active image while unbounded history remains an audit view, the pre-retraction snapshot returns only the replacement in native projection and persisted claim-state paths. | Commit `cce43a6a` applies the same cutoff rule to both paths. Focused coverage proves original-only before correction, replacement-only after correction and before retraction, and superseded-plus-active unbounded history. `6 passed`; Ruff, compileall, and diff checks pass. |
| Rerun installed shared-mechanics probe at `9d2398df` | If the as-of fix closes the remaining lifecycle defect, both cutoffs pass and execution reaches symmetric reverse reads. | After `2329.86s`, assertion, correction, retraction, current/history, both transaction-time cutoffs, and transcript sync all pass. The first symmetric relation commits, but its reverse protected current read returns `unavailable`; sibling and reopen are not reached. Retained store is pytest run `1201`. |
| Trace and isolate symmetric reverse reads | If stored authority and projection data are valid, replay of run `1201` and clean one-row installed probes should distinguish durable read logic from the historical live runtime result. | Run `1201` contains 584 records and two verified lifecycle transitions; catalog and endpoint verification pass and direct production snapshot read returns the reverse partner item. Commit `51cdf138` binds fallback endpoint validation to the caller instead of a tautological claim-self check. Focused reader suite passes 7/7. Clean no-key installed one-row probes pass `sibling_of` in `184.48s` and `partner_of` in `181.64s`, each with exact reverse output and zero read-side record growth. The prior live `unavailable` is not reproduced. |
| Rerun combined installed probe at `af1abbb6` | If isolated symmetric success composes with the lifecycle sequence, both symmetric writes and reads complete before reopen. | After `3027.13s`, the literal lifecycle and first symmetric reverse read pass. A later symmetric submission returns `unavailable`: terminal persistence rejects an expired governed writer lease, graph retry rejects its stale lease, and terminal fallback finds a different execution lease. Isolated rows remain green, so the defect is long-sequence lease continuity rather than ontology or reverse-read semantics. Retained store is pytest run `1205`. |
| Reclaim an expired graph lease from verified retained replay | If the live graph attempt exhausts its individual recovery lease, exactly one reclaim with the same owner and configured duration can rebuild execution from retained checkpoints without accepting stale authority or changing TTL. | Commit `71432230` initializes replay explicitly, reclaims only an expired `bootstrap-v3-recovery` lease, retries graph execution once with the returned lease/writer binding, and preserves replay and revoked-grant propagation. The deterministic test raises the observed stale-lease error and proves one reclaim plus durable retry; five reachable graph/retained composition cases pass in `151.74s`; Ruff, compileall and diff checks pass. Six full-file failures were reproduced outside the changed branches and remain unrelated existing branch failures. |
| Rerun the combined installed probe at `6b8b2888` | If exception-only recovery matches the installed path, the later symmetric write reclaims the expired lease and completes. | After `2974.89s`, every lifecycle, as-of and earlier symmetric step passes, but the later write again returns `unavailable`. Terminal publication raises `SemanticWriterAdmissionError` for an expired writer lease; `_finalize_attempt` converts that failure into a persisted `BootstrapGraphDurableRetryProgressV3(reason="storage_retry")`, so the provider's exception/`None`-only reclaim branch does not run. Generic terminal fallback then finds the recovery operation owned by the graph execution. The recovery trigger must interpret the exact durable retry result instead of only exceptions. |
| Renew the retained graph lease before epoch-zero construction | If graph execution receives the full configured recovery window before it creates epoch zero, the long local normalization sequence cannot consume part of the graph's lease budget; post-effect durable retry semantics remain unchanged. | Commit `4bd44010` renews every active, owned `bootstrap-v3-recovery` lease once with its configured duration immediately before the first graph request. Foreign, expired and terminal controls fail closed. The prior exception-only expired-lease reclaim remains bounded to one attempt, and returned durable retry progress is never re-entered. Three focused tests cover near-expiry and fresh renewal, foreign/expired denial, exception-triggered reclaim, live-lease no-reclaim, revoked-grant propagation, and the ordinary provider root passing the renewed binding into the native graph request; `3 passed, 60 deselected in 10.72s`, with Ruff, compileall and whitespace checks clean. |
| Rerun the combined installed probe at `e5f042fd` | If a full configured 15-minute graph window is sufficient, the preflight renewal completes both symmetric writes and reopen. | After `2990.58s`, literal assertion/correction/retraction, current/history/as-of views, transcript sync and `partner_of` all complete. The `sibling_of` operation receives its preflight lease at `14:15:00.633471Z`, expires at `14:30:00.633471Z`, and terminal publication fails just after expiry with the same writer-admission error. The retained operation is the fifth structured fact and the only nonterminal control. This proves the graph stage itself exceeds 15 minutes on the accumulated Level-2 local store; preflight authority is correct but the configured window is too short. |
| Give the local Level-2 graph stage a measured 30-minute window | If the failure is only the measured execution-budget mismatch, doubling the local Bootstrap V3 recovery lease while preserving its half-window renewal rule lets the fifth accumulated graph complete without changing captured-turn, retry or epoch contracts. | Commit `f3b37295` configures the current local Level-2 Bootstrap V3 runtime with a 30-minute recovery-operation lease and a 15-minute renewal interval. Preflight and exception-only reclaim continue deriving duration from the lease. The authority suite passes `5 in 14.38s`; the three lease/provider-root selectors pass `3 in 11.01s`; Ruff, compileall and whitespace checks pass. |
| Rerun the combined installed probe at `d1d0fae3` | If the measured lease window closes the last write failure, both symmetric facts commit and their immediate reverse reads proceed to reopen. | After `2386.61s`, the fourth structured operation, `partner_of`, commits without any lease or terminal fallback error. Its immediate reverse read returns `unavailable` at line 1278; `sibling_of` has not started. Retained store is pytest run `1214`. Reopening that exact 85 MB/584-record JSONL store under a fresh captured turn returns both reverse and forward `partner_of` views correctly, proving persisted data and the reader are valid. Turn 4 was captured at `14:40:32.245804Z`; the long write holds its acquired turn handle past the 15-minute captured-turn TTL, so the next read call is denied before reaching the reader. |

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
reads, but exposed an as-of interval bug. Commit `cce43a6a` repairs both read
backends, and the installed rerun proves the entire literal lifecycle plus both
cutoffs. Commit `51cdf138` closes the reverse endpoint binding and isolated
installed probes prove both symmetric predicates. The combined reopen rerun
then exposes governed writer/graph lease expiry during the later sequential
symmetric write. Commit `71432230` adds bounded expired-lease reclaim from
verified replay, but the combined rerun at `6b8b2888` proves the actual
coordinator path persists a `storage_retry` result rather than returning
`None` or propagating the lease exception. Commit `4bd44010` avoids that path
by renewing the owned recovery lease before epoch zero and graph execution;
it does not reinterpret or rerun a sealed durable retry. The rerun then proves
that the accumulated `sibling_of` graph stage itself exceeds that 15-minute
window. The combined reopen proof and targeted independent review remain
outstanding, so no milestone or requirement count changes yet.

## Completion Contract

At Level 2, the smallest retained-source conflict-scope reproducer must fail
before and pass after the correction. It must cover the normal admission path,
the linked retained-source path, and missing/substituted link denial. The
affected projection checks and frozen installed LocalDate correction must pass.
Targeted independent correctness and test review must find no remaining
Level-2 P1/P2 in this boundary. Hostile-store permutations remain Level 3.

## One Next Action

Align the local captured-turn TTL with the measured 30-minute graph operation
window, prove that a tool call acquired before expiry may finish and a second
call remains available inside the aligned window, and keep exact-expiry denial.
Then rerun the frozen combined installed probe.
