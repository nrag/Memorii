# Hermes Level 2 PR Remediation

- Work ID: `hermes-level2-pr-remediation`
- Work type: debugging
- Delivery fidelity: Level 2 early real-world testing
- Status: active
- Coordinator: `/root`
- Created: 2026-09-24
- Last updated: 2026-09-24
- Parent WorkPlan: `docs/work/hermes-level2-pr/pr-review.plan.md`
- Related WorkPlans: `docs/work/hermes-level2-test-gate/testing.plan.md`; `docs/work/hermes-conversation-memory-trial/implementation.plan.md`
- Canonical inputs: final spec/correctness/test reviews at evidence head `cc4e5705643352eda996fc0703a51d051e0c34f0`; GitHub run `36075920094`; `docs/design/hermes_conversation_memory_trial.md`
- Expected outputs: corrected production lifecycle, setup path, Docker identity, installed-loader gate, candidate validation coverage, timing schema, and restored broad semantic tests

## Expected And Observed Behavior

The Level 2 candidate must use one installed first-party factory, pin its normal
Docker build to the reviewed Hermes RepoDigest, shut its background semantic
worker down with the provider, terminalize every received invalid candidate,
and keep all required semantic suites green.

At evidence head `cc4e5705`, independent review found that normal provider
shutdown leaves the completed-turn daemon alive, the Docker default remains a
mutable tag, README still recommends the retired development connector, the
installed `MemoryManager` behavioral test is opt-in, two invalid-output classes
are unit-only, and one measured test duration is outside the manifest `tests`
map. GitHub run `36075920094` also shows broad semantic failures because
`accepted_terminal()` calls `ProductionLocalSemanticAnalyzer.analyze()` and
receives `None` for the generic `works_for` fixture.

## Reproducers

- Initialize a real completed-turn runtime, call provider shutdown, and assert
  the runtime worker is no longer alive. Current behavior leaves it alive.
- Build `Dockerfile.memorii` without a build argument. Current default resolves
  `nousresearch/hermes-agent:v2026.9.21` rather than the approved digest.
- Load `memorii/tests/ci/unit-test-durations.json` through
  `memorii.tools.test_shards.load_durations()`. The equal-text node is absent.
- Run
  `PYTHONPATH=memorii <venv>/python -m pytest memorii/tests/unit/core/semantic_ingestion/test_identity_lineage.py::test_lineage_checkpoint_tail_is_byte_equivalent_to_genesis_prefix -q -p no:cacheprovider`.
  Current result is one assertion failure at
  `semantic_terminal_fixture.py:739` because analysis is `None`.

## Hypothesis Ledger

1. **Confirmed: lifecycle has no stop protocol.** The worker loop is
   unconditional and provider shutdown only drains and drops the binding, so a
   queue sentinel plus closed state and join are required.
2. **Confirmed: identity and documentation drift.** The Dockerfile and README
   preserve earlier Level 2 scaffolding after the first-party production path
   became canonical.
3. **Confirmed: timing shape error.** A new node was inserted at JSON top level
   instead of under `tests`; the loader ignores it because the manifest lacks a
   closed top-level schema check.
4. **Leading CI hypothesis: fixture authority mismatch.** The migrated generic
   terminal fixture uses the current production analyzer with a prepared source
   or predicate authority that no longer admits the generic `works_for`
   proposal. Inspect the exact rejection boundary before changing production
   semantics.
5. **Alternative CI hypothesis: test environment drift.** Python 3.11 or shard
   ordering changes analysis behavior. The same failure reproduces locally on
   Python 3.12, weakening this hypothesis.

## Scope And Constraints

Use Bootstrap V3 only. Preserve provider transport failure as retryable and
received invalid output as evidence-only. Do not restore V1/V2 APIs or the
development connector. Do not weaken source, predicate, provenance, lifecycle,
or transaction validation. Use the full approved Hermes RepoDigest as the
Docker default. The installed-loader proof must exercise real Hermes discovery,
initialization, sync, same-store reopen, protected prefetch, CLI inspection, and
an absent-authority denial with zero writes; only the Responses edge may be
faked.

## Changed-Surface Ledger

Expected owners include the completed-turn runtime and bridge shutdown,
Dockerfile, README, Hermes product/bridge/Docker tests, shard timing loader and
schema tests, PR workflow, generic semantic terminal fixture, generated profile
fingerprints when required, and linked WorkPlans/evidence.

## Completion Contract

- Deterministic pre-fix reproducers are recorded and pass after the correction.
- Worker shutdown drains admitted work, exits, joins, and rejects later enqueue.
- Default Docker build uses the approved digest and the required installed-loader
  CI job exercises the real Hermes `MemoryManager` lifecycle.
- README documents only the first-party Level 2 CLI flow.
- Malformed JSON and duplicate candidates produce one evidence-only terminal
  each, no graph/projection, and do not block a later valid turn.
- Timing manifest schema is closed and every changed Hermes node loads with its
  measured duration.
- Exact failed CI commands and affected sibling suites pass.
- Ruff, Pyright, candidate manifest/preflight validators, independent delta
  review, and required GitHub checks pass at the final head.

## Root Cause And Evidence

- **Completed-turn lifecycle:** the daemon loop had no sentinel or closed
  state. `shutdown()` drained work and discarded the runtime, leaving the
  blocked `Queue.get()` worker alive. The runtime now closes admission, drains,
  sends a stop sentinel, joins, and rejects every later enqueue. Focused worker
  and bridge shutdown tests pass.
- **Generic terminal fixture:** `accepted_terminal()` built the retired
  `SegmentLanguageRoute` through `build_prepared_source_authority`, while the
  production analyzer correctly accepts only
  `BootstrapFreeformSegmentLanguageRoute`. The fixture now constructs the
  current freeform authority through
  `build_bootstrap_freeform_prepared_source`; the exact lineage reproducer
  passes (`1 passed in 10.27s`). No production validation was weakened.
- **Historical persisted fixture:** its captured declared-language route is
  pre-Bootstrap-V3 and cannot decode under the active union. The test now proves
  rejection leaves the rehydrated plane unchanged and retains the current
  writer-cutover denial assertion. It does not restore a legacy decoder.
- **Dynamic import ownership:** the architecture check compares each owned
  file's exact dynamic capability set. `bootstrap_profile.py` has only the
  observed entry-point loader capability (its resource import is static for
  this checker); `project_assertions_profile.py` has `importlib`,
  `importlib.metadata`, and `importlib.resources`. The owner table now records
  those exact sets and their package-verification purpose.
- **Timing manifest:** the loader accepted unknown top-level fields. It now
  closes the allowed timing-evidence schema and has a regression for a stray
  duration key; the equal-text duration remains inside `tests`.
- **Installed image proof:** the default Docker image is pinned to
  `nousresearch/hermes-agent@sha256:6bece0644e29a347e5ae17db43c36938c86f171c6f5e0cef18aa2075d331f3a3`.
  The required PR job runs the default build and the installed MemoryManager
  smoke: entry point discovery, initialization, completed turn, persistence,
  reopen/prefetch, CLI inspect, and absent-authority zero-write denial. Only
  the Responses transport is replaced by a deterministic fake.
- **Package-smoke proof identity:** GitHub run `36084066597` failed before the
  installed proof with `proof_candidate_member_changed` because its bounded
  release-preparation candidate still pinned pre-Level-2 package and workflow
  bytes. The candidate now pins all 1,820 current package files and the
  existing scoped proof inputs at product revision `a85d2980`; independent
  registry construction and the 58-vector manifest were regenerated against
  the current 181-entry publication.

## Evidence Log

- Pre-fix worker review reproducer: reviewer observed worker remains alive after
  `shutdown()` while blocked on `Queue.get()`.
- Pre-fix semantic fixture reproducer: `1 failed in 8.56s` locally with
  `ProductionLocalSemanticAnalyzer.analyze()` returning `None`.
- GitHub failures: Semantic Projection History and semantic-terminal shards 0,
  5, and 6 share the same fixture assertion signature.
- Candidate manifest/preflight at `cc4e5705` otherwise validate successfully.
- `test_hermes_completed_turn_runtime.py`, bridge shutdown tests, and shard
  loader tests: `31 passed in 18.90s` after the lifecycle and schema changes.
- Exact `test_identity_lineage.py::test_lineage_checkpoint_tail_is_byte_equivalent_to_genesis_prefix`:
  `1 passed in 10.27s` after current freeform fixture construction.
- Product invalid-candidate regression with unknown predicate, ungrounded
  quote, invalid literal, malformed JSON, duplicate candidates, and a later
  valid turn: `1 passed in 607.98s`; it observed five `evidence_only`
  terminals, one `fully_committed` terminal, and final recall visibility.
- Product installed-factory lifecycle regression: `1 passed in 344.88s`; it
  closes the real completed-turn worker, rejects a later callback, and proves
  that callback leaves `write_revision` unchanged.
- Installed default-image lifecycle through Hermes `MemoryManager`: `1 passed
  in 1867.18s`. The required workflow job enables the Docker test, pins a
  60-minute timeout, and is a required dependency of the semantic-ingestion
  aggregate.
- Provider shutdown was tightened so `close()` owns both drain and stop. A
  worker failure still stops and joins the daemon before the exception is
  propagated and provider state is cleared. The production close/post-close
  regression passed again (`1 passed in 397.02s`).
- Historical persisted reload, timing shard, and Docker-context tests:
  `23 passed, 1 skipped in 88.51s`; the skipped test needs a local Docker
  daemon and remains required in the PR workflow.
- Runtime worker, provider bridge, and benchmark architecture siblings:
  `88 passed in 1137.21s`. This includes the dynamic-import-owner check and
  the real worker close/post-close admission regression.
- Focused Ruff over every changed Python path: `All checks passed!`; `git diff
  --check` also passed.
- Full Ruff over `memorii` and `tests`: `All checks passed!`; full configured
  Pyright: `0 errors, 0 warnings, 0 informations`.
- Static tooling contract: `19 passed in 140.18s`.
- Unit shard verification after recording the 826.52-second equal-text test:
  4,508 tests across six file shards, maximum estimated shard 1,065.711
  seconds under the 1,200-second target.
- Package-smoke focused tests: `19 passed in 22.89s`; regenerated independent
  registry parity reports 181 entries and 1,269 roles with 58 vector cases and
  no failures. The installed real-wheel proof then passed with 21
  distributions, 5,705 installed files, 1,819 package files, valid signature
  acceptance, all signature/authority mutation rejections, and retained target
  resolution. The installed-payload rejection driver also passed all five
  mutations.
- Replacement GitHub run `36085078058` exposed a stale recovery regression:
  an abstained provider response now completes the source as `evidence_only`,
  so the durable recovery index is `found` and carries an exact replay of the
  abstained normalization. The test still expected the pre-terminal `claimed`
  state and no replay. The assertions and timing node now describe the current
  Bootstrap V3 contract; production behavior is unchanged.
- Corrected recovery module: `4 passed in 82.56s`. Exact unit shard 2 then
  exercised all 740 assigned tests: the corrected recovery cases passed and
  the only local failure was the unrelated benchmark source-revision lookup in
  this isolated sandbox (`739 passed`). That benchmark test passed separately
  with `MEMORII_SOURCE_REVISION=bb4b2c7a...` (`1 passed in 24.75s`), matching
  CI's explicit revision binding. Ruff passes for the changed test, and shard
  verification still collects 4,508 tests with a 1,065.711-second maximum
  estimate under the 1,200-second target.

## Review Findings

All final review findings at `cc4e5705` are confirmed and enter this remediation
loop. No reviewer finding is dismissed or deferred within Level 2.

## Next Action

Commit and push the frozen evidence for product revision `7ab912c5`, request
independent delta review, then require the replacement GitHub run to pass.
