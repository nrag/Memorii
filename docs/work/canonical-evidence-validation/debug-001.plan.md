# Repair and reduce canonical-evidence validation runs

- Work ID: canonical-evidence-validation
- Work type: debugging
- Delivery fidelity: Level 2, bounded CI and test-fixture maintenance
- Status: under-review
- Coordinator: Codex
- Created: 2026-11-25
- Last updated: 2026-11-25
- Parent WorkPlan: None
- Related WorkPlans: `docs/work/semantic-ingestion-canonical-evidence-default-on-2026-08-27/implementation.plan.md`
- Canonical inputs: main commit `885c7db7ad8bba1aa0dd7d88c8f162d26c3bed0d`; workflow run `45635391628`
- Expected outputs: corrected fixtures and parity proof; economical scheduled workflow; current tooling guidance; before/after evidence

## Objective and completion contract

Stop repeated failing scheduled validation while retaining the five existing
canonical-evidence invariants. Establish the causal failure, reproduce it,
verify the correction with warnings treated as errors, and reduce redundant
setup and scheduling. Record local verification separately from GitHub execution.
Completion requires all five checks passing, actual opposite modes observed,
focused fixture regressions, workflow/configuration validation, independent
review, and the change applied to the default-branch schedule.

Level 2 is sufficient because the intended changes affect CI and test fixtures,
not public or persisted behavior. Full production certification, the complete
repository test corpus, and unrelated workflow optimization are deferred.

## Scope, constraints, and sources

Included: the named workflow, its five tests and directly shared construction
helpers, current development documentation, and this debugging record.
Excluded: runtime semantic changes, suppressing failures, removing assertions,
unrelated workflows, billing-account configuration, and new hosted infrastructure.

Preserve production authority checks, explicit feature rollback, writer isolation,
capacity limits, privacy assertions, warning policy, and exact test collection.
The user explicitly authorizes fixing/removing this workflow and choosing a
cheaper periodic mechanism; this supersedes the historical every-few-hours cadence.

Sources, in repository precedence order: root `AGENTS.md`,
`docs/design/semantic_ingestion_validated_canonical_closure.md`, the capability
activation contract in `docs/design/semantic_ingestion_architecture.md`,
`docs/development/static_tooling.md`, actual production call paths and tests,
and the observed GitHub logs. `.agents/PLANS.md` and `debug-problem` govern process.

## Incident and reproduction contract

The scheduled workflow runs two Ubuntu jobs every four hours. In the latest
100 repository runs, 91 are this workflow, all failures on the same main SHA,
from 2026-10-24 through 2026-11-25. The latest run installs successfully and
collects the expected two parity and three admission tests. Both parity tests
fail comparing `graph_transaction_authority_unavailable` with `source_only`.
Two admission tests fail because preplanning controls never become terminal.
The snapshot-privacy test passes. Earliest historical onset is not established.

Reproduce from `memorii/` on the clean baseline with Python 3.12:

```bash
python -W error -m pytest tests/unit/core/semantic_ingestion/test_canonical_evidence_mode_parity.py -p no:cacheprovider
python -W error -m pytest tests/unit/core/semantic_ingestion/test_canonical_evidence_production_limits.py -p no:cacheprovider
```

The tests use deterministic fixture dependencies and a fixed clock. Concurrency
is explicit in the admission tests. Use a clean environment without the local
ML extra to verify that Torch, spaCy, Stanza, and model downloads are unnecessary.

## Current state and open questions

Verified: these files are excluded from ordinary unit shards and have this
schedule as their sole automated owner. The governing design requires their
invariants but does not require four-hour execution. Repository visibility is
public and runners are standard `ubuntu-latest`; current GitHub billing docs
state that public standard-runner compute is free. Account billing is unavailable,
so no claim is made that this workflow causes a metered charge.

Verified code evidence: the production fixture lacks verified capability
monitoring authority; the built-in graph path requires active capability status.
The scenario fixture supplies a different graph provider and does not explicitly
disable canonical evidence, although default enablement now applies to both.
Working hypothesis: stale fixture wiring, not an invalid production validator.

Verified locally: all five corrected tests pass in the lean environment, with
2 parity tests in 203.44 seconds and 3 admission tests in 279.49 seconds.
Nine directly affected sibling tests pass in 71.39 seconds. Both exact
collection guards, changed-file Ruff, identity hygiene, YAML and shell syntax
checks pass. The measured suite total supports a 15-minute job timeout with
setup headroom; CI runner timing remains to be observed.

Open: independent final diff review and GitHub execution. The default branch is protected;
its required statuses are `Unit Tests` and `Benchmark Contracts`. No external
decision is currently needed for the proposed correction.

## Hypothesis ledger and experiments

| ID | Hypothesis | Evidence | Discriminating experiment | Status |
| --- | --- | --- | --- | --- |
| H1 | Dependency/setup failure | Setup and collection pass in GitHub | Inspect logs and reproduce with lean dependencies | disproved for reported failures |
| H2 | Stale fixture lacks required graph capability authority | Built-in authority rejects missing status; successful nearby fixtures install signed monitoring authority; clean baseline reproduces both terminal failures | Add the existing verified authority only to recovery fixture and retain terminal assertions | confirmed root cause |
| H3 | Actual enabled/disabled runtime divergence | Baseline tests use different graph compositions and both default enabled | Same valid production composition with explicit `False` passes all outcome, replay, projection, and observed-mode assertions | disproved for the tested path |

Experiment budget: four causal experiments and one targeted independent review.
Do not repeat expensive runs without a changed hypothesis or required verification.

## Fix strategy and decisions

Retain the five proofs; deleting their only owner would remove meaningful coverage.
Prefer one weekly job plus manual dispatch, one lean dependency installation,
concurrency cancellation, and a measured timeout. Keep cold-install drift coverage;
do not skip unchanged commits solely to avoid a small weekly validation.
Run the same workflow on pull requests that change its own definition,
dependency manifest, or directly consumed fixture/proof files. This catches
the demonstrated stale-fixture failure before merge while leaving unrelated
PRs unaffected. No new branch-protection requirement is introduced.
Use the existing signed monitoring fixture through the production constructor;
do not inject scenario graph authority into the production path or weaken checks.
Compare explicit modes through otherwise identical composition.

Rollback is a normal revert. No migration or public API change is intended.
Existing-machine cron was considered but adds maintenance and does not lower
the public repository's already-free standard runner compute cost.

## Changed surfaces, authority chain, and identity ledger

| Surface | Owner and authority | Verification | Status |
| --- | --- | --- | --- |
| `.github/workflows/canonical-evidence-parity-scheduled.yml` | CI cadence and exact five-test selection | YAML/shell validation, exact collection and local suite execution passed; GitHub execution pending | locally verified |
| `memorii/tests/unit/core/test_provider_service.py` and `memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_coordinator_v3.py` | Existing signed monitoring authority -> provider constructor -> active status -> built-in graph path | Clean-base failures reproduced; corrected five tests and nine sibling cases pass | locally verified |
| `memorii/tests/unit/core/semantic_ingestion/test_canonical_evidence_mode_parity.py` | Same production composition -> explicit mode -> public outcome/replay/durable projection | Enabled/disabled snapshot checks and retained outcome, idempotence, projection assertions pass | locally verified |
| `docs/development/static_tooling.md` and historical canonical-closure implementation plan | Current executable workflow and historical cadence supersession | Read against final YAML | verified |
| WorkPlan | Debugging evidence only | Reconcile actual diff and evidence | active |

Behavioral identities (canonical-evidence workflow, helpers, modes, test names)
are retained or named by behavior. Work ID, experiment IDs, run IDs, and dates
are traceability only. No persisted or public identities change. Run the existing
field-aware identity check; no allowlist changes are intended.

Production bindings are unchanged. The investigated chain is:
`_production_recovery_service` -> `_build_production_scoped_provider_service` ->
`ProviderMemoryService` -> capability monitoring -> built-in graph authority
`_active_capability_bindings` -> graph commit and terminal control. The read-only
correctness investigation maps this chain before fixture edits.

## Gate and evidence ledger

| Check | Scope | Result |
| --- | --- | --- |
| Two exact failed pytest commands above | Five reported tests | Clean base: parity 2 failed in 42.73s; admission 2 failed, 1 passed in 77.37s; same four GitHub signatures |
| Same commands after correction | Regression proof, warnings as errors | 2 passed in 203.44s; 3 passed in 279.49s |
| Direct fixture consumers and mode selection checks | Shared-helper effects | 9 passed in 71.39s; exact selected nodes below |
| Workflow configuration and shell syntax | Cadence, cost bounds, selection | YAML and `bash -n` passed; one job, Monday 07:23 UTC, 15-minute initial cap, read-only contents permission |
| Ruff changed Python files; identity hygiene | Repository conventions | passed, exit 0 |
| Actual GitHub workflow | Runner/setup/expression behavior | pending; do not claim from local success |

Known failures: the four GitHub assertions described above remain in scope.
No failure is excluded as unrelated without identical clean-base reproduction.

## Delegation and review log

- Cost researcher, read-only: official GitHub pricing and alternatives; complete.
- Spec auditor, read-only: coverage ownership, governing requirements, dependency
  footprint; evidence inspected by coordinator; no code changes.
- Correctness reviewer, read-only: fixture and authority execution-path mapping;
  evidence inspected by coordinator; no code changes.
- One bounded writer (Terra-class) made the six code/workflow/documentation
  edits; complete. Coordinator retains evidence and testing ownership. A clean
  detached baseline preserved reproduction independently of candidate edits.
- Final targeted review (independent Terra-class test reviewer) inspected the
  frozen diff and retained proof coverage. No `changes_required` or
  `blocks_approval` finding. Its bookkeeping observation about stale table rows
  is confirmed and resolved above. Hosted-runner timing and rollout remain
  pending evidence, not product defects.

## Progress and evidence

- 2026-11-25: inspected run `https://github.com/nrag/Memorii/actions/runs/45635391628`
  and job logs `139279342433`, `139279343259`; isolated four assertion failures.
- 2026-11-25: cloned clean baseline. Lean dependency installation initially
  failed because the local environment lacks ICU development headers; resolving
  this local prerequisite before drawing test conclusions.
- 2026-11-25: supplied local Debian ICU headers and selected the available GCC
  compiler; clean Python 3.12.14 environment installed `.[dev]` successfully.
  Torch, spaCy, and Stanza are absent. No project dependency contract changed.
- 2026-11-25: exact baseline commands reproduced all four reported failures,
  eliminating a GitHub-only runner/dependency explanation. Logs are local
  diagnostic files; the durable reproduction is the recorded base SHA and commands.
- 2026-11-25: froze the six-file candidate content digest
  `17fe7e518dc9ccad1420a402cf1b72b46c52519aee9d3ace6d88c4da2a8f493a` for initial
  regression measurement. No production code changed.
- 2026-11-25: corrected suites passed all five tests with warning errors enabled.
  Production admission execution overlapped the small sibling check, so its
  timing is a local measurement, not a dedicated-runner benchmark. Nine sibling
  cases, exact collection guards, Ruff, identity hygiene, YAML, and shell checks
  passed. No assertion was weakened or test deselected.
- 2026-11-25: direct pause is unavailable through the GitHub connector. The
  local browser connection is unavailable and cloud GitHub is signed out.
  No schedule was paused or remote run triggered; proceed through the PR path.

## Blockers and limits

Local ICU build prerequisite is resolved. No GitHub reruns have been triggered.
Billing attribution cannot be established through repository tools alone.

## Next action

Publish the reviewed correction as a pull request and observe its GitHub checks.

## Outcome

Local root cause and regression proof are complete. GitHub rollout is pending.

## Candidate review record

```yaml
base_revision: 885c7db7ad8bba1aa0dd7d88c8f162d26c3bed0d
reviewed_revision: base plus the six-file correction
tested_revision: base plus the six-file correction
tested_tree_digest: 17fe7e518dc9ccad1420a402cf1b72b46c52519aee9d3ace6d88c4da2a8f493a
tree_state: tracked correction plus this evidence record; local diagnostic verification
changed_surface_inventory_complete: true
scope_delta_resolved: true
authority_chains_complete: true
required_local_jobs: [mode-parity, production-admission, affected-fixture-consumers, collection-guards, ruff, identity-hygiene, workflow-syntax]
passed_local_jobs: [mode-parity, production-admission, affected-fixture-consumers, collection-guards, ruff, identity-hygiene, workflow-syntax]
known_local_failures: []
failure_exclusions: []
workflow_identities: [.github/workflows/canonical-evidence-parity-scheduled.yml]
ci_event: pending pull_request
ci_executed_sha: pending
ci_executed_ref: pending
remaining_validated_p1_p2: []
remaining_blocks_approval: []
remaining_changes_required: []
local_ci_parity: exact test commands and lean installation passed; hosted actions unverified
acceptance_gate_inventory: [Canonical-Evidence Validation, Unit Tests, Benchmark Contracts]
github_run_urls: [https://github.com/nrag/Memorii/actions/runs/45635391628]
pr_head_sha: pending
pr_base_sha: 885c7db7ad8bba1aa0dd7d88c8f162d26c3bed0d
merge_base_sha: 885c7db7ad8bba1aa0dd7d88c8f162d26c3bed0d
required_checks_green: pending
```

This is a local candidate record, not a claim of GitHub enforcement or rollout.

## Exact sibling verification

Run from `memorii/` with Python 3.12 and `.[dev]`:

```bash
python -W error -m pytest \
  tests/unit/core/test_provider_service.py::test_default_provider_composition_is_source_admission_only \
  tests/unit/core/test_provider_service.py::test_sync_event_default_path_keeps_canonical_arena_disabled \
  tests/unit/core/test_provider_service.py::test_apply_memory_write_default_path_keeps_canonical_arena_disabled \
  tests/unit/core/test_provider_service.py::test_sync_event_production_profile_path_enables_canonical_evidence_arena \
  tests/unit/core/test_provider_service.py::test_apply_memory_write_production_profile_path_enables_canonical_evidence_arena \
  tests/unit/core/semantic_ingestion/test_bootstrap_graph_coordinator_v3.py::test_every_trigger_family_stages_seals_and_leases_prepared_bytes \
  -p no:cacheprovider
ruff check tests/unit/core/test_provider_service.py tests/unit/core/semantic_ingestion/test_bootstrap_graph_coordinator_v3.py tests/unit/core/semantic_ingestion/test_canonical_evidence_mode_parity.py
python -m memorii.tools.identity_hygiene --root .. --allowlist ../.agents/identity_hygiene_allowlist.json
```
