# Restore The Built-In Native Graph Authority

- Work ID: `native-graph-authority-debug` (planning coordinate only)
- Work type: debugging
- Delivery fidelity: Level 2 for the runnable normal-root happy path and common failure behavior; later Level 3 breadth remains in the parent implementation WorkPlan
- Status: complete at Level 2 for the fixture defect; parent Level 3 implementation remains open
- Coordinator: `/root`
- Created: 2026-09-25
- Last updated: 2026-09-25
- Parent WorkPlan: `docs/work/learned-ontology/implementation.plan.md` (blocked on this operation)
- Related WorkPlans: None
- Canonical inputs: `docs/design/memorii_spec.md`, `docs/design/memorii_storage_details.md`, `docs/design/event_model.md`, `docs/IMPLEMENTATION_RULES.md`, `docs/design/semantic_ingestion_architecture.md`, baseline `5716ba1143a124f98df4c9701f1420a4ee71b0f2`
- Expected outputs: cause, narrow repair, normal-root and structured no-key path regression evidence, independent closure review

## Objective

Restore the existing built-in native graph route so a valid accepted claim reaches its group commit and runtime projection from a normal provider root. This unblocks the approved learned-ontology structured fact and protected-read proof.

## Completion Contract

Identify the causal authority failure with discriminating evidence, repair its canonical owner, and pass the existing direct/factory/filesystem/Hermes normal-root family plus one accepted claim/projection case under the declared interpreter. Cover unavailable/revoked capability status without weakening fail-closed behavior. Reconcile the affected authority chain and required gates; obtain independent correctness and test review and a revision-bound closure record with `remaining_validated_p1_p2: []`. Then restore the parent implementation WorkPlan to active.

## Scope

Included: built-in graph capability-status composition and its exact normal roots, focused regression tests, required generated or workflow artifacts affected by the fix. Excluded: ontology catalog expansion, public structured commit enablement, legacy reader, model quality and release certification. Deferred to parent: Level 3 platform, packaging, migration and whole-branch approval.

## Constraints And Invariants

Preserve provider transport, domain semantics, candidate/committed state, native V3 transaction authority and current capability-status grant checks. Do not fabricate an active capability, bypass a missing status, or change a public or persisted contract just to make the test green. Apply governing-document precedence and source-owner validation. Preserve unrelated dirty implementation and approved design files.

## Identity And Coordinate Hygiene

No new runtime identity is authorized at diagnosis. Inventory any identity changed by the repair across code, tests, generated artifacts and gates; planning ID in this document cannot enter a behavioral or persisted name. Run the field-aware identity gate if such an identity changes.

## Change Impact And Verification Closure

Current linked debugging diff: this plan only. Parent implementation owns its paused dirty code; do not silently assign those files to this operation. Expected repair owner is `core/semantic_ingestion/bootstrap_graph_builtin.py` or its canonical capability-status composition, with production service/factory and focused test surfaces determined by experiment. Gate ledger: existing `test_bootstrap_graph_root_composition.py` normal-root family; affected static/type, feature shard and aggregate jobs to be selected from current `.github/workflows/pr-gates.yml` after the fix. Known failure: direct-root test below, same signature on clean baseline and dirty implementation tree. No closure evidence yet.

## Production Entrypoint Bindings

`ProviderMemoryService.sync_event` and its factory/filesystem/Hermes wrappers compose the built-in graph host bundle; `bootstrap_graph_builtin._active_capability_bindings` requires an active stored capability status before accepted native graph execution. The current direct root has one real production caller chain but returns `graph_transaction_authority_unavailable` before native group CAS. Exact authority arguments and caller counts will be recorded after the causal experiment.

## Sources Of Truth

Governing documents in the header precede current subsystem design, code and tests. Actual code and clean-baseline repro establish current behavior; a passing test name alone does not establish a successful runtime path.

## Current State

The root cause was a test fixture omission: the accepted normal-root fixture provided no retained capability status, so the production native V3 guard correctly returned `graph_transaction_authority_unavailable` before group CAS. The same failure occurred at the clean baseline. The final test fixture now passes a signed verified monitoring authority through each public constructor, asserts active status and the installed live-authority guard, and calls Hermes through `HermesMemoryProvider.sync_event`. The missing-status test asserts zero graph primary/effects/event batches and unchanged replay. Four normal roots passed at the final test bytes; both reviewers found no remaining Level 2 change. Parent implementation resumes at B1-D.

## Assumptions And Open Questions

Verified: both trees reproduce the same direct-root failure; the failing fixture had zero capability-status records. The verified monitor test helper creates active status through `CapabilityMonitor.initialize_active_from_verified_evidence`; direct/factory/filesystem/Hermes accepted tests then pass. Fingerprint mismatch and stale status were not the cause of this failure. The real local Level 2 builder separately has a typed-value decoder source digest mismatch against the current dirty implementation tree; its package authority must be reconciled in the parent implementation and is not waived as a release gate. No external decision has been identified.

## Experiments

1. Inspect exact current status, registered fingerprint and operation provenance at `_active_capability_bindings` on the failing direct root. H1 absent status predicted `None`; H2 fingerprint mismatch predicted a status under a different key; H3 invalid/stale status predicted a non-active or malformed record. Actual: zero capability-status records; H1 confirmed, H2/H3 not supported for this case. Evidence: worker trace and clean-baseline failure, then passing active fixture experiment. Status: complete.
2. Compare composition timing and status publication at direct, factory, filesystem and Hermes roots. Actual: the same accepted test setup omitted active status at each root; using the existing verified monitor fixture made all four pass. Status: complete.
3. After repair, execute the accepted native family and negative missing/stale-status cases. Actual: four accepted roots, one missing-status denial and one stale/demotion test passed under root `.venv` Python 3.12.14; no production authority changed. Status: complete pending independent review.

## Progress Log

- 2026-09-25: linked from paused implementation after real claim fixture failed before group CAS. Clean baseline worktree reproduced the exact direct-root assertion; this rules out an ontology-only regression but does not remove the authority-chain blocker. Next: inspect live status/fingerprint at the failing boundary.
- 2026-09-25: discriminating probe found zero capability-status records before accepted execution. A first test-only correction used `initialize_graph_fixture_capability_monitor`, and 4-root parameter, missing-status, and stale/demotion checks passed. Independent review found the positive proof bypassed verified constructor authority and Hermes forwarding, so that four-root result was diagnostic only.
- 2026-09-25: the sole writer replaced the helper with constructor-supplied signed authority, asserted active status/guard, sent the Hermes event through Hermes, and strengthened missing-status no-effect checks. Direct accepted plus missing-status passed 2 in 153.73 seconds; Hermes passed 1 in 135.78 seconds. Correctness and test reviewers confirmed their Level 2 findings resolved. The coordinator ran the final accepted direct/factory/filesystem/Hermes selection: 4 passed in 455.61 seconds, exit 0. Linked fixture repair closes; parent implementation resumes.

## Evidence Log

- Dirty tree: `test_bootstrap_graph_root_composition.py -k 'all_normal_roots_execute_builtin_native_graph_path_without_injection and direct'`, root `.venv` Python 3.12.14: expected `source_only`, actual `graph_transaction_authority_unavailable` (worker, 24.88 seconds).
- Clean baseline `5716ba1143a124f98df4c9701f1420a4ee71b0f2`: `PYTHONDONTWRITEBYTECODE=1 /Users/nandaraghunathan/Code/Memorii/Memorii/.venv/bin/python -W error -m pytest tests/unit/core/semantic_ingestion/test_bootstrap_graph_root_composition.py -k 'all_normal_roots_execute_builtin_native_graph_path_without_injection and direct' -p no:cacheprovider -q`, cwd clean worktree `/Users/nandaraghunathan/.codex/worktrees/ontology-baseline-debug/Memorii/memorii`, exit 1, 1 failed in 27.88 seconds, same assertion.
- Dirty implementation tree, root `.venv` Python 3.12.14: direct accepted plus missing-status tests 2 passed in 86.49 seconds; first four-parameter accepted family 4 passed in 367.86 seconds; stale/demotion status test 1 passed in 12.99 seconds. Exact selections: `test_bootstrap_graph_root_composition.py -k 'all_normal_roots_execute_builtin_native_graph_path_without_injection and direct or builtin_normal_root_without_capability_status_fails_closed_before_effects'`; same file `-k all_normal_roots_execute_builtin_native_graph_path_without_injection`; `test_capability_monitoring.py -k group_commit_status_read_set_is_exact_and_stale_after_demotion`, each with `.venv/bin/python -W error -m pytest -p no:cacheprovider -q` from repository root and `PYTHONPATH=memorii`. The positive family is invalid as four-root evidence because it bypassed constructor authority and Hermes forwarding; retain it only as a discriminating diagnostic. Focused Ruff, compileall and `git diff --check` passed. Exact CI parity and frozen revision evidence remain open.
- Final test bytes SHA-256 `dc2ab2f22e9f07b601a84611de804585ffc535219d75018861869498a1086852` at `memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_root_composition.py`; HEAD `5716ba1143a124f98df4c9701f1420a4ee71b0f2`, dirty parent implementation tree. Root `.venv` Python 3.12.14 / pytest 9.0.3. Final direct accepted plus missing-status 2 passed in 153.73 seconds; Hermes public path 1 passed in 135.78 seconds. Coordinator final family: `PYTHONPATH=memorii .venv/bin/python -W error -m pytest memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_root_composition.py -k all_normal_roots_execute_builtin_native_graph_path_without_injection -p no:cacheprovider -q`, cwd repository root, exit 0, 4 passed and 44 deselected in 455.61 seconds. Stale/demotion selection previously 1 passed in 12.99 seconds. Focused Ruff, compileall and `git diff --check` passed. CI and package authority parity remain parent Level 3 work.

## Decision Log

- 2026-09-25: treat this as a linked debugging operation because it is a preexisting complex normal-root failure in an authority chain required by implementation. Do not fold speculative fixes into the ontology WorkPlan.
- 2026-09-25: correct only the accepted test fixture using the existing verified monitor helper. Production code correctly denies absent status, so changing its guard would weaken the safety contract. The explicit absent-status test preserves that negative behavior.

## Review Log

Independent `correctness_reviewer` and `test_reviewer` reviewed the coherent test-only delta. Confirmed `Not applicable / changes_required / verification and integration`: the first accepted fixture mutated a private monitor after construction, and the Hermes parameter bypassed its trigger. Confirmed `Not applicable / changes_required / verification`: missing-status test checked too few durable effects. The sole writer corrected all three. Targeted correctness review approved the constructor and Hermes paths; targeted test review found no remaining Level 2 changes. The originally proposed full concurrent stale-status CAS race is a Level 3 parent follow-up: existing real-root revocation/demotion and private stale-precondition checks cover this Level 2 fixture correction, and no product failure was demonstrated. `remaining_validated_p1_p2: []` for this bounded debugging operation.

## Blockers And Limits

No blocker remains for this Level 2 fixture repair. The parent still needs real structured claim/read, verified legacy read, installed no-key integration, package digest regeneration and Level 3 CI/release evidence. This operation used the planned three experiments and one bounded remediation round.

## Next Action

Return to parent milestone 1 and prove one real catalog-bound structured claim through the native writer and protected reader with no API key.

## Outcome And Retrospective

Complete at Level 2 for the test fixture defect. The production capability-status denial was correct; only the accepted test setup changed. This operation does not complete parent milestone 1 or certify a no-key fact.

```yaml
base_revision: 5716ba1143a124f98df4c9701f1420a4ee71b0f2
reviewed_revision: 5716ba1143a124f98df4c9701f1420a4ee71b0f2+dirty-test-dc2ab2f22e9f07b601a84611de804585ffc535219d75018861869498a1086852
tested_revision: 5716ba1143a124f98df4c9701f1420a4ee71b0f2+dirty-test-dc2ab2f22e9f07b601a84611de804585ffc535219d75018861869498a1086852
tested_tree_digest: dc2ab2f22e9f07b601a84611de804585ffc535219d75018861869498a1086852 # owned test-file bytes; parent dirty tree is not frozen
tree_state: dirty_parent_implementation_tree; one owned test-file delta in this linked operation
changed_surface_inventory_complete: true_for_linked_debug_delta
scope_delta_resolved: true
authority_chains_complete: true_for_linked_debug_delta
required_local_jobs: [normal_root_four_parameter_family, missing_status_no_effect, stale_status_demotion, focused_ruff_compile_diff]
passed_local_jobs: [normal_root_four_parameter_family, missing_status_no_effect, stale_status_demotion, focused_ruff_compile_diff]
known_local_failures: [clean_baseline_missing_status_fixture_reproduced_and_corrected]
failure_exclusions: []
workflow_identities: [parent_level3_pr_gates_deferred]
ci_event: not_applicable_level2_local_fixture_repair
ci_executed_sha: not_applicable_level2_local_fixture_repair
ci_executed_ref: not_applicable_level2_local_fixture_repair
remaining_validated_p1_p2: []
remaining_blocks_approval: []
remaining_changes_required: []
local_ci_parity: false_parent_level3_gates_open
acceptance_gate_inventory: [focused_normal_root_family, missing_status_no_effect, stale_status_demotion]
github_run_urls: []
pr_head_sha: not_applicable_no_pr
pr_base_sha: not_applicable_no_pr
merge_base_sha: not_applicable_no_pr
required_checks_green: not_applicable_level2_local_fixture_repair
```
