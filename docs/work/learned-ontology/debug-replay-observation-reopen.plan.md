# Replay Observation Reopen Debugging

- Work ID: `replay-observation-reopen`
- Work type: debugging
- Delivery fidelity: Level 2, early real-world manual testing
- Status: complete
- Coordinator: `/root`
- Created: 2026-09-27
- Last updated: 2026-09-27
- Parent WorkPlan: `implementation.plan.md`
- Related WorkPlan: `milestones/learning-activation-replay.plan.md`
- Canonical inputs: root `AGENTS.md`, `.agents/PLANS.md`, `.agents/skills/debug-problem/SKILL.md`, `docs/design/learned_ontology.md`, `docs/design/event_model.md`, and the active M5 packet
- Expected output: an invariant-level correction for retained-before-activation observation-ledger reopen, focused regression proof, and targeted independent closure review.

## Objective

Allow a retained source that later replays under an activated agent-local catalog to survive JSONL reopen without weakening observation-ledger inventory verification. Resume M5 only after the replay operation, its observation activation, and the recovered ledger agree on one complete immutable inventory.

## Expected And Observed Behavior

Expected: activation replays the retained `mentors(Person, Person)` source through `ProviderMemoryService.submit_structured_fact`, commits one fact, shuts down, and reopens with the same durable replay/status/read result.

Observed: the live replay commits after selected-authority refresh, but startup raises `PreplanningStoreError` from `_reload_observation_ledger_activation` because the recovered activation successor or inventory is partial or mismatched. The trigger is a source retained before learned-catalog activation and replayed after selection. Classification: implementation defect in a Level-2 persistence/recovery path.

## Identity And Authority Chain

retained source -> preplanning observation ledger -> catalog activation -> replay operation -> selected agent-local pin -> ordinary structured writer -> observation activation/reload -> JSONL recovery. Public and persisted identity recipes must remain unchanged unless the root cause proves an existing recipe inconsistent with the governing event model.

## Hypothesis Ledger

| Hypothesis | Mechanism | Evidence | Discriminating experiment | Status |
| --- | --- | --- | --- | --- |
| Replay appends an observation activation using a stale pre-selection inventory. | A replay's grants, control, and terminal can use separately fetched writer bindings. A transition between those calls can leave the control in the predecessor inventory. | `submit_structured_fact` allocated the operation without a writer binding, then independently fetched one for grants and a second for the control. The inventory verifier classifies controls exclusively by their persisted binding. | Snapshot one binding before allocation and carry it through all replay writes. | confirmed |
| Reload selects the wrong activation generation for a source that has both preactivation and replay operations. | The loader may join by source/capture identity without selecting the exact activation referenced by the replayed operation. | Reload uses the control's fence binding and verifies an exact terminal locator; no source-only activation join was found. | Exercise the existing malformed locator and terminal-control variants through ledger reload. | disproved |
| The learned replay path violates an existing writer invariant before persistence. | A new replay request may bypass the ordinary ledger refresh step even though the later semantic writer succeeds. | Replay enters `submit_structured_fact` and the ordinary structured writer; the failure boundary is the unfrozen binding between allocation and publication. | Exercise a retained-before-selection replay through the installed JSONL root. | confirmed |

## Experiment Ledger

| Experiment | Prediction | Result |
| --- | --- | --- |
| Freeze the smallest retained-before-activation JSONL reproducer and inspect activation inventory records | A replayed control will identify whether its writer binding is activation-lineage or predecessor-lineage. | Added `test_learned_replay_of_a_preselection_capture_reopens_jsonl`; it captures `Atlas mentors Ada.`, activates the candidate with that exact retained source as evidence, then proves one claim/receipt and an equivalent direct protected read before and after JSONL reopen. The corrected path passed: `1 passed in 386.12s` (2026-09-27). |
| Compare writer-binding ownership across one replay operation | A single binding fixed at allocation will be used for grant, control, and terminal writes. | `ProviderMemoryService.submit_structured_fact` now snapshots the current binding before retained-operation allocation and passes it through the grant publisher and `ProviderIngestionCoordinator.execute_retained_structured_proposal`; the coordinator no longer fetches a second binding. |

## Completion Contract

The deterministic reproducer must fail before and pass after the correction. A normal post-activation source and the retained-before-activation replay must both reopen. Duplicate replay must remain idempotent; malformed or genuinely partial activation inventory must still fail closed. Focused affected-family checks, Ruff, compile, diff checks, and targeted correctness/test review must report `remaining_validated_p1_p2: []`.

## Current Changed Surface

- `memorii/memorii/core/provider/service.py`: freeze the current writer binding at retained-operation allocation and pass it through replay publication.
- `memorii/memorii/core/provider/ingestion.py`: use the supplied binding for captured replay control and normal retained operation publication.
- `memorii/tests/unit/integrations/test_hermes_memory_provider_bridge.py`: retained-before-selection replay and JSONL reopen reproducer.
- `memorii/tests/unit/core/semantic_ingestion/test_semantic_provider_composition.py`: direct retained-operation helper captures its binding at allocation and passes it unchanged through grant and terminal execution.

## Evidence And Limits

- `ruff check` and `compileall` pass for the changed surfaces; `git diff --check` passes.
- The retained-before-selection replay JSONL reproducer, including pre- and post-reopen direct protected reads, passes after the binding correction: `1 passed in 386.12s`.
- The independent normal post-selection installed mentors journey also passes after the service/ingestion correction: `1 passed in 492.64s`.
- The first strengthened replay attempt used the provider tool outside an active captured-turn context after restart and returned `unavailable`. This was a harness-boundary error: that tool endpoint requires an active turn. The proof now uses the public Hermes protected reader root directly before and after restart; the equality assertion remains in place.
- Scoped Pyright reports ten pre-existing errors in the two provider modules, including unresolved `pydantic`, and no error caused by the binding parameter.
- The full JSONL reproducer requires several minutes because registered-artifact revalidation dominates the native terminal path.
- `test_exhausted_activated_control_rejects_terminal_attachment` passes for both locator and terminal-control variants: `2 passed in 10.65s`. It reopens through `activate_observation_ledger()` and exercises the same `_activation_inventory_digest` active-control classification before rejecting malformed attachments. A replay-specific malformed fixture would duplicate that strict branch.
- Direct retained V3 helper proof passes: `2 passed, 71 deselected in 143.64s`.

## Root Cause And Correction

The trigger was a replay of a source captured before catalog selection. `submit_structured_fact` allocated its retained operation without writer authority, published grant records after one current-binding lookup, then delegated to a second current-binding lookup before persisting the replay control and terminal. The observation-ledger reload accepts active controls only when the persisted binding belongs to the activated lineage, so a transition between those reads could retain the replay control in the predecessor inventory.

The correction snapshots one writer binding immediately before allocation and passes that exact value through grant publication, replay control publication, and terminal construction. It leaves activation and inventory digests and malformed-record denial unchanged. A later writer transition now fails the write fence instead of persisting a mixed-generation operation.

## Before/After Evidence

- Before: allocation, grants, and control/terminal used independent current-binding reads; JSONL reopen reported an activation successor or inventory mismatch.
- After: retained `Atlas mentors Ada.` replay activates, preserves exactly one claim/receipt, and reopens through the installed JSONL root with the same protected read (`1 passed in 386.12s`).
- Normal control: the installed post-selection mentors journey remains green (`1 passed in 492.64s`).
- Sibling: malformed terminal locator and terminal-control attachments remain fail-closed (`2 passed in 10.65s`).

## Reopened Read Finding

The persisted claim and receipt were present. The unavailable result came from invoking the provider tool after restart without an active captured-turn handle, which is correctly denied by that tool boundary. `HermesCompletedTurnRuntime.read_structured_facts` is the public protected reader root that authorizes a session without requiring an active tool turn; the regression now uses it on both sides of reopen.

## Independent Closure Review

Frozen revision `4954e2e4` received targeted correctness and test approval. The correctness reviewer confirmed the allocation-time writer binding reaches grant, control, and terminal publication while concurrent writer change fails closed. The test reviewer confirmed the retained-preselection journey proves exactly one claim and one replay receipt plus equivalent protected reads before and after JSONL reopen, the normal post-selection journey remains green, and malformed locator/control attachments remain denied. Both report `remaining_validated_p1_p2: []`.

## One Next Action

Resume parent M5 at rollback, revoked/deleted replay outcomes, and final milestone cohort review.
