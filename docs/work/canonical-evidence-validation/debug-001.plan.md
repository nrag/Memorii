# Repair and reduce canonical-evidence validation runs

- Work ID: canonical-evidence-validation
- Work type: debugging
- Delivery fidelity: Level 2, bounded CI and test-fixture maintenance
- Status: blocked (recurring workflow paused; weekly replacement pending required CI)
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
helpers, current development documentation, and this debugging record. A
syntax-only solver conditional cleanup was tried as a required-CI unblocker,
then reverted because it invalidated frozen release-candidate source evidence.
The final correction contains no production source changes.
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

Verified at baseline: these files are excluded from ordinary unit shards and
had this schedule as their sole automated owner. The governing design requires their
invariants but does not require four-hour execution. Repository visibility is
public and runners are standard `ubuntu-latest`; current GitHub billing docs
state that public standard-runner compute is free. Account billing is unavailable,
so no claim is made that this workflow causes a metered charge.

Verified code evidence: the production fixture lacks verified capability
monitoring authority; the built-in graph path requires active capability status.
The scenario fixture supplies a different graph provider and does not explicitly
disable canonical evidence, although default enablement now applies to both.
Confirmed cause: stale fixture wiring, not an invalid production validator.

Verified locally: all five corrected tests pass in the lean environment, with
2 parity tests in 203.44 seconds and 3 admission tests in 279.49 seconds.
Nine directly affected sibling tests pass in 71.39 seconds. Both exact
collection guards, changed-file Ruff, identity hygiene, YAML and shell syntax
checks pass. The first hosted correction also passes both exact suites and
collection guards in a 6-minute 9-second job, including a cold lean install.
The 15-minute timeout therefore has measured hosted setup and execution headroom.

Independent final diff review is complete without blocking findings in the
canonical-evidence correction. PR #125 is open. Its corrected workflow passed
twice on GitHub, most recently in 5m52s. `Benchmark Contracts` passes, but
required repository-wide CI blocks merge. Full Ruff reproduces SIM102 on clean
baseline with Ruff 0.17.6. Unit shards report a missing `python3.12` executable
on Ubuntu 26.04 runners configured only with Python 3.11. This hosted failure
is observed, not excluded through a full clean-base shard reproduction.

The attempted solver syntax cleanup passed local Ruff, verifier tests, and
Pyright but violated a frozen release-candidate source hash in Package Smoke.
It is reverted exactly to the pinned baseline bytes; release evidence is not
silently regenerated. Broader CI environment/toolchain repair and any required
release-evidence recertification are outside this bounded fixture correction.

Immediate containment is applied: GitHub workflow `351716976` reports
`disabled_manually`, independently verified after the API operation on
2026-11-25 at 19:56 UTC. The former four-hour workflow therefore stays off.
Merge and re-enable only after required CI is repaired and green.

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
| `memorii/memorii/core/solver/verifier.py` | Frozen release-candidate source bytes | Temporary syntax cleanup reverted; SHA-256 exactly matches baseline and `candidate.json` | unchanged in final diff |
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
| Actual GitHub workflow, run `45685424785` | Runner/setup/expression behavior | passed: 2 parity tests in 113.61s, 3 admission tests in 165.69s; both count guards; job 6m09s including installation |
| Full `ruff check memorii tests` with Ruff 0.17.6 | Required Static Analysis blocker | exact baseline failure SIM102 at solver/verifier.py:52; attempted cleanup reverted to preserve frozen source proof |
| Solver verifier tests with warnings as errors | Temporary syntax-only cleanup | 4 passed in 0.61s before cleanup was reverted |
| `pyright --pythonpath <venv-python>` | Existing configured type-check scope | 0 errors, 0 warnings, 0 informations |
| Actual GitHub workflow, run `45687065023` | Final weekly workflow/fixture bytes | passed again in 5m52s on PR head `38c1ed9`, merge revision `a73537b`; subsequent cleanup changes only this record and restores unrelated solver bytes |
| GitHub workflow state | Immediate containment | independently read `disabled_manually` for workflow `351716976`; updated 2026-11-25T19:56:17Z |

The four original assertion failures are resolved locally and on GitHub.
The clean-base lint failure and hosted missing-interpreter failures still block
normal merge. No other failure is excluded without identical clean-base
reproduction. The release-proof failure caused by the attempted lint cleanup
is resolved by restoring the exact original file; no pinned evidence is changed.

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
- 2026-11-25: published PR `https://github.com/nrag/Memorii/pull/125`, first
  head `1c546b9dcf295f3589c9205b65e931652ed7bb63`, based on `885c7db`.
  The corrected workflow passed at actual pull-request merge revision
  `0572f614a08232077c5ef75e057fbf1ebbaadf07`, ref `refs/pull/125/merge`:
  `https://github.com/nrag/Memorii/actions/runs/45685424785`.
  Python 3.12.16 on Ubuntu completed the job in 369 seconds; lean installation
  took 61 seconds. Both warning-as-error suites and exact collection guards pass.
- 2026-11-25: PR Gates run `45685424588` failed its Static Analysis job
  `139456639726` on Ruff SIM102 in the unchanged solver verifier. The independent
  reviewer ran the exact command on clean baseline `885c7db` using the same
  Ruff 0.17.6 and reproduced the sole identical error. The coordinator confirmed
  the final nested conditional has no following branch, so combining it with
  `and` preserves all outcomes and the spec's unresolved-evidence validation.
  The sole writer applied that bounded cleanup. Full Ruff and four existing
  verifier tests pass; configured Pyright also passes. No rule is suppressed.
- 2026-11-25: the unchanged canonical-evidence correction passed again at
  `https://github.com/nrag/Memorii/actions/runs/45687065023`, executed revision
  `a73537bc909718c10cd41239760bec6fe3b82484`, in 352 seconds. Required PR Gates
  additionally reports missing `python3.12` in unit compiler tests. Package
  Smoke reports `proof_candidate_member_changed:memorii/memorii/core/solver/verifier.py`.
  A bounded diagnostic on a separate, unmerged branch retrieved the large logs;
  no full workflow was manually rerun. The solver cleanup is reverted exactly
  to SHA-256 `e29e93b4a6293e814e5f0123c7fcca5fec4a0b93a89b95522f0b52c53d081e55`.
- 2026-11-25: an isolated two-minute containment job called GitHub's disable API
  for only the named scheduled workflow. Its immediate state assertion failed
  after the mutation, but a separate public REST read confirmed the resulting
  state is `disabled_manually`, updated at 19:56:17 UTC. No other schedule or
  repository protection was changed. The temporary diagnostic workflow is
  removed from its branch after evidence collection.

## Blockers and limits

Local ICU build prerequisite is resolved. No manual full GitHub reruns have
been triggered. The final scope cleanup uses `[skip ci]` to avoid repeating
known-blocked repository-wide checks. It does not satisfy, waive, or bypass a
merge gate: the PR remains blocked. The scheduled workflow is disabled, and its
replacement bytes have already passed twice. Required CI repair must receive
fresh hosted verification before merge and re-enablement.
Billing attribution cannot be established through repository tools alone.

## Next action

Leave the recurring workflow paused and the reviewed weekly correction in
PR #125. Resolve the repository-wide Python/toolchain and frozen release-proof
maintenance requirements separately; then run required gates, merge normally,
and re-enable the weekly workflow. The PR description records the final head
and containment evidence after this committed snapshot.

## Outcome

Root cause and canonical-evidence regression proof are complete locally and on
GitHub. Recurring failing execution is stopped through verified disablement.
The economical weekly replacement is prepared and tested, but normal merge and
re-enablement are blocked by the repository-wide CI issues above.

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
ci_event: pull_request
ci_executed_sha: 0572f614a08232077c5ef75e057fbf1ebbaadf07
ci_executed_ref: refs/pull/125/merge
remaining_validated_p1_p2: []
remaining_blocks_approval: [required-repository-ci-not-green]
remaining_changes_required: []
local_ci_parity: exact canonical-evidence test commands, collection guards, and lean installation passed locally and twice on GitHub; final unrelated solver revert and evidence update intentionally do not rerun known-blocked full CI
acceptance_gate_inventory: [Canonical-Evidence Validation, Unit Tests, Benchmark Contracts]
github_run_urls: [https://github.com/nrag/Memorii/actions/runs/45635391628, https://github.com/nrag/Memorii/actions/runs/45685424785, https://github.com/nrag/Memorii/actions/runs/45685424588]
pr_head_sha: 1c546b9dcf295f3589c9205b65e931652ed7bb63
pr_base_sha: 885c7db7ad8bba1aa0dd7d88c8f162d26c3bed0d
merge_base_sha: 885c7db7ad8bba1aa0dd7d88c8f162d26c3bed0d
required_checks_green: false
```

This records the canonical-evidence correction's hosted proof and the reverted
lint experiment. The final cleanup SHA and required-check status are recorded
in PR #125; this snapshot claims verified containment, not weekly rollout.

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
