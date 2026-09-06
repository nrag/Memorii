# Bootstrap Graph Authority Unavailable Debugging

- Work ID: bootstrap-graph-authority-unavailable-2026-08-11
- Work type: debugging
- Status: active
- Coordinator: Codex `/root`
- Created: 2026-08-11
- Last updated: 2026-08-12
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/implementation.plan.md`
- Canonical inputs: current worktree; approved V3/V40 contracts; `test_all_normal_roots_execute_graph_terminal_once`
- Expected outputs: corrected ordinary graph transaction path and revision-bound regression evidence

## Objective

Restore the ordinary accepted-fact bootstrap graph transaction through every public production composition root without weakening authority, persistence, or replay validation.

## Completion Contract

- The direct-root reproducer returns `source_only` and executes one graph effect.
- The same invariant passes for factory, filesystem, and Hermes roots.
- Independent JSONL lost-ack recovery returns the exact persisted terminal result without a second graph effect.
- The causal boundary and correction are independently reviewed.
- `remaining_validated_p1_p2: []` is recorded at the corrected revision.

## Expected And Observed Behavior

- Expected: `test_all_normal_roots_execute_graph_terminal_once[direct]` returns `source_only`, with one graph call and one call to each normalization lane.
- Observed: the exact selector deterministically returned `graph_transaction_authority_unavailable` after 137.67 seconds on Python 3.12.13.
- Impact: P1 implementation failure on the ordinary accepted-fact production path; the provider collapses a graph construction/coordinator failure to the public fail-closed outcome.

## Hypotheses

1. Confirmed: the graph execution family was only partially migrated to the native V3 contracts. The fixture compiler initially emitted retired plan-member fields; after that correction, production assembler/coordinator consumers still read retired aggregate-authorization and group-CAS fields.
2. Disproved: graph epoch and authority projection succeed. The trace reaches compilation, plan checkpoint, authorization, attempt/lineage, and group-execution request construction.

## Experiments

- Reproducer: `PYTHONPATH=memorii .venv/bin/python -m pytest -vv memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_production_roots.py::test_all_normal_roots_execute_graph_terminal_once[direct] -p no:cacheprovider`
- Result: failed with the expected public symptom; no graph call was observed by the assertion boundary.
- First surfaced failure: the fixture supplied retired `BootstrapTransactionGroupPlanMemberV3` fields. The strict native fixture migration and member-envelope decode correction now pass nine focused assembler/fixture tests.
- Second surfaced failure: production attempt assembly read retired `transaction_group_plan_digest`; current per-group authorization joins replaced it and focused tests remain green.
- Current surfaced failure: the direct path reaches group execution, where `group_cas_request` reads removed `proposed_delta_digest`. The active boundary is native `BootstrapGraphGroupCommitRequestV3` plus exact store reload; the withdrawn group-CAS adapter must be replaced rather than restored.
- Discriminating mapping experiment (2026-08-11): the native request/repository pair exists and is strict, but no native downstream construction exists. `BootstrapGraphGroupResultConstructionV3` still requires `BootstrapGraphGroupExecutionResultV3`, which embeds `BootstrapGraphGroupCasRequestV3`, `BootstrapGraphGroupCasOutcomeV3`, and CAS effect carriers/receipts. Final-stage evidence and terminal preparation both consume that legacy execution-result digest. Constructing an adapter would revive the withdrawn CAS truth and fabricate effects, so this is an incompatible current-contract boundary rather than a missing coordinator argument.
- Built-in composition correction (2026-08-12): `BuiltInLocalHostSemanticIngestionCapability` now installs `BuiltInBootstrapGraphAuthorityProviderV3` when no explicit graph-host builder is supplied.  The provider reloads only the persisted normalization reduction authority, projects the snapshot/read-set from `SemanticIngestionAtomicStore.graph_state_snapshot()`, emits unresolved native reductions when no target planner is available, and connects the native group-commit and terminal ports.  It does not import fixture code, reconstruct retired CAS carriers, or create accepted effects.
- Final causal correction (2026-08-12): the built-in provider initially passed
  the persisted `GraphDependentExecutionPolicy` where the graph snapshot
  authority requires `GraphDependentExecutionPolicyReferenceV3`, then its
  otherwise valid pre-epoch authority publication was rejected because writer
  admission had no validator for that two-record closure.  The provider now
  derives an immutable reference from the exact persisted policy bytes, and
  admission decodes/re-encodes the typed reload and validates both exact record
  IDs plus all reverse joins before accepting the control-free publication.
- Four-root no-injection ordinary-fact execution now passes and each root writes
  exactly one native group-commit primary: direct `177.73s`, factory `229.55s`,
  filesystem `230.93s`, Hermes `229.24s`.  Corrected independent JSONL
  post-commit checkpoint-ack recovery also passes (`187.96s`) without a second
  group commit.

## Scope And Constraints

- Fix only the demonstrated ordinary-path invariant and its root/fresh-process siblings.
- Do not reopen the design or add compatibility fallbacks unless the direct exception proves an approved semantic contradiction.
- Preserve strict fail-closed behavior for missing or substituted authority.
- Preserve unrelated dirty-worktree changes.

## Next Action

Freeze the corrected revision and request independent specification,
correctness, and test review of the causal boundary plus four-root and JSONL
evidence.  Classify every finding before any further edit.
