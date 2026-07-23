# Agentic Evaluation And Controlled Pilot Closure Plan

## Status

- Planning snapshot date: 2026-07-22
- Repository: `nrag/Memorii`
- Checkout: `/Users/nandaraghunathan/Code/Memorii/Memorii`
- Branch: `lifecycle_check_contract_hardening`
- Reviewed candidate SHA: `79360ffe1fe2279eefbf8c0625447002b86361d7`
- Pull request: [#107](https://github.com/nrag/Memorii/pull/107)
- Planning only: this document does not authorize an agent integration or production deployment.

This is the closed plan for evaluating Memorii in an agentic scenario and, only
if the evaluation succeeds, preparing the same narrow provider-memory
composition for a controlled pilot. It does not expand the engineering-hardening
change into a general agent platform.

## Primary Objective

Determine and execute the minimum rigorous work needed to:

1. Complete live memory-component certification for one exact clean revision.
2. Build an evaluation-only, host-neutral agent loop around Memorii's public
   production APIs.
3. Run a causal, statistically defensible agent-memory experiment.
4. Make an explicit go/no-go decision.
5. If and only if the decision is `go`, add the operational controls required for
   a controlled provider-memory pilot.

Production readiness, framework-specific integration, broad deployment,
distributed storage, and general agent-platform design are outside this plan.

## Readiness Definitions

The readiness levels are ordered and non-substitutable:

| Level | Required evidence | Claims still prohibited |
| --- | --- | --- |
| Component-certified | The exact clean source revision passes deterministic PR checks, a real structured provider canary, and the declared live memory-component statistical gate. | Agent task improvement, experiment readiness, pilot readiness, production readiness. |
| Experiment-ready | Component certification plus a deterministic, isolated agent harness; frozen protocol; held-out scenarios; typed traces; restart tests; safety budgets; and independent behavioral grading. | Agent benefit, pilot readiness, production readiness. |
| Evaluation-complete | A preregistered held-out experiment on the exact frozen revision produces valid artifacts and completed statistical analysis, including harms and false-success review. | Pilot readiness unless the go criteria pass; production readiness. |
| Pilot-ready | A successful evaluation plus the conditional rollback, persistence, observability, and operational controls in Phase 8. | Broad or unattended production deployment. |
| Production-ready | Outside this plan. | All production claims. |

No lower-level artifact may be used as evidence for a higher readiness level.

## Frozen Scope

### Included

- `AR-CERT-001` through `AR-SAFETY-001` from the planning request.
- The provider-memory composition exposed by `ProviderMemoryService`,
  `FilesystemStorageBundle`, and provider tool schemas.
- An evaluator-owned host loop that uses public production APIs.
- Multi-session software-debugging and engineering-handoff scenarios.
- Baseline, retrieval-only, and full provider-memory treatment arms.
- Exact-revision certification, preregistration, trace provenance, causal
  analysis, and false-success inspection.
- Conditional pilot controls only after a successful go decision.

### Excluded

- OpenAI Agents SDK, LangGraph, Hermes, AutoGen, or other framework-specific
  production integration.
- A production agent runtime or general orchestration framework.
- Combining `MemoriiRuntimeAPI` and `ProviderMemoryService` into a new production
  facade.
- Persistent execution, solver, overlay, or event-log stores unless a later,
  separately approved pilot explicitly adopts `MemoriiRuntimeAPI`.
- Compatibility layers, legacy paths, API versioning, migrations for released
  users, or speculative platform abstractions.
- Learned calibration, broad retrieval redesign, prompt tuning on held-out data,
  or unrelated cleanup.

## Verified Repository Baseline

### Git And External State

At the planning snapshot:

- The local worktree was clean and matched remote branch SHA `79360ffe`.
- PR #107 targeted `main` and was open.
- `Unit Tests`, `Benchmark Contracts`, CodeQL, and both analysis checks passed on
  `79360ffe`.
- `main` branch protection required `Unit Tests` and `Benchmark Contracts` with
  strict up-to-date checks.
- Live workflow run
  [29958016147](https://github.com/nrag/Memorii/actions/runs/29958016147)
  was still running against `79360ffe`; its completed smoke jobs were passing at
  the snapshot, but the final statistical gate had not completed.
- The earlier run `29956057267` was cancelled and therefore is not certification
  evidence.

The live run certifies only `79360ffe`. Adding or committing this planning file,
or changing code, prompts, thresholds, workflows, tests, or relevant
documentation, creates a new candidate SHA and requires a new exact-SHA run.
Keep this uncommitted plan out of PR #107 until its candidate is certified and
merged, or intentionally accept that PR #107 must be recertified.

### Direct Test Evidence

The following focused verification passed under warnings-as-errors:

```text
196 passed in 12.13s
```

It covered the existing runtime harness, provider service, provider tools,
provider factory, filesystem bundle, real-subprocess delivery replay and
partial-turn recovery, memory-evolution retrieval, channel arbitration,
next-step engine, and runtime step service.

This proves those tested component contracts are currently green. It does not
prove that an agent uses them beneficially.

### Existing Production Boundaries

- `ProviderMemoryService` owns provider ingestion, default-on memory evolution,
  structured retrieval, text prefetch, work-state projection, and tool dispatch.
- `FilesystemStorageBundle` supplies persistent memory-plane, work-state,
  decision-state, and LLM-decision trace stores.
- `HermesMemoryProvider` is an adapter over `ProviderMemoryService`; it is not
  required by the host-neutral experiment.
- `MemoriiRuntimeAPI` owns a separate execution/solver runtime. Its constructor
  does not compose `ProviderMemoryService`.
- Execution, solver, overlay, and event-log implementations are in-memory only.
- `NextStepResult.next_step` is currently an untyped dictionary and the default
  engine can return generic `frontier_planner_not_yet_enabled` advice.
- The current live workflow configuration check verifies key presence and mode
  resolution, but does not make a real structured provider request before
  starting the campaign.

### Research Rationale

The plan follows four current findings rather than treating memory as a static
QA feature:

- [AMA-Bench](https://arxiv.org/abs/2602.22769) motivates evaluation over agent
  states, actions, observations, and tool outputs, with attention to causal and
  objective information rather than similarity retrieval alone.
- [STALE](https://arxiv.org/abs/2605.06527) motivates separate measurement of
  state resolution, false-premise resistance, and downstream policy adaptation.
- [MemBench](https://arxiv.org/abs/2506.21605) motivates measuring effectiveness,
  efficiency, and capacity across more than one memory level and interaction
  mode.
- [Agent Memory: Characterization and System Implications](https://arxiv.org/abs/2606.06448)
  motivates phase-aware cost, latency, construction, retrieval, and generation
  accounting.

These papers inform evaluation design only. Their systems and scores are not
used as Memorii acceptance thresholds.

## Closed Issue Inventory

This inventory is frozen after this section. A new issue may be admitted only if
it is a direct regression caused by implementing this plan or a reproduced
violation of `AR-CERT-001` through `AR-SAFETY-001`. The admission record must
name the violated requirement and objective reproduction. General review
comments, cleanup preferences, and future ideas are not admissible.

### Summary

| Issue | Severity | Requirement | Blocks | Classification |
| --- | --- | --- | --- | --- |
| AE-001 | P1 | AR-CERT-001 | Component-certified | Implementation defect plus external acceptance step |
| AE-002 | P1 | AR-HARNESS-001 | Experiment-ready | Evaluation defect |
| AE-003 | P1 | AR-EXPERIMENT-001 | Experiment-ready | Evaluation defect |
| AE-004 | P1 | AR-SCENARIO-001 | Experiment-ready | Evaluation defect |
| AE-005 | P1 | AR-DURABILITY-001 | Experiment-ready | Evaluation defect |
| AE-006 | P1 | AR-TRACE-001 | Experiment-ready | Evaluation defect |
| AE-007 | P1 | AR-SAFETY-001 | Experiment-ready | Evaluation defect |
| AE-008 | P2 | AR-NEXTSTEP-001 | Full-treatment validity | Implementation defect |
| AE-009 | P2 | AR-ROLLBACK-001 | Pilot-ready | Conditionally deferred pilot work |
| AE-010 | P2 | AR-DURABILITY-001, AR-SAFETY-001 | Pilot-ready | Conditionally deferred pilot work |

### AE-001: Exact-Revision Live Certification Is Incomplete

- Severity: P1.
- Evidence:
  - `docs/plans/engineering_hardening_closure_matrix.md:11` requires the exact
    clean revision to pass the live gate.
  - `.github/workflows/benchmark-scheduled.yml:135-139` checks only local
    configuration and secret presence before the matrix.
  - Run `29958016147` was incomplete at the planning snapshot.
- Reproduction: inspect the workflow step; it calls no provider API. Inspect the
  GitHub run; no completed final gate was attached to the candidate SHA.
- Root cause: workflow health checking is configuration-level, while acceptance
  requires provider-level health and completed statistical evidence.
- Required change: add one real strict-structured-output canary job using the
  same client, model resolution, credential source, retry policy, and API path as
  the campaign. Bind its redacted artifact to source SHA and make the full matrix
  depend on it. Estimate the campaign call/token/dollar envelope before dispatch.
- Tests: fake-client success, invalid schema, provider error, refusal, model
  mismatch, missing request ID, redaction, and workflow dependency tests.
- Independent verification: inspect the canary artifact and GitHub job; then
  validate every live report, aggregate summary, source fingerprint, provider
  health, confidence certificate, and exact attached check SHA.
- Completion evidence: successful `Live Runtime Statistical Gate` on the exact
  clean candidate, with a preceding successful provider canary and no subsequent
  relevant change.

### AE-002: No Evaluation-Only Agent-Memory Composition Exists

- Severity: P1.
- Evidence:
  - `memorii/memorii/api/service.py:19-33` composes execution/solver stores but no
    provider memory service.
  - `memorii/memorii/core/filesystem_storage/bundle.py:67-73` builds the provider
    service but no agent loop.
  - `memorii/tests/integration/test_harness_runtime_integration.py:18-65`
    constructs only the in-memory execution runtime.
- Reproduction: no repository command runs a model/tool loop through transcript
  ingestion, memory retrieval, explicit memory tools, and downstream action.
- Root cause: public components exist, but experiment orchestration was correctly
  deferred during component hardening.
- Required change: add an evaluator-owned, host-neutral tool-calling loop that
  composes `FilesystemStorageBundle` and `ProviderMemoryService` through public
  APIs. Do not combine production facades or reimplement memory semantics.
- Tests: public-API contract tests, three-arm treatment tests, process/storage
  isolation, operation-ID ownership, and production/evaluator import boundaries.
- Independent verification: run the same scripted scenario through all arms and
  inspect observable provider records and downstream actions without accessing
  evaluator oracle data from production.
- Completion evidence: deterministic end-to-end harness run with validated
  artifacts for all three arms.

### AE-003: No Frozen Causal Experimental Protocol Exists

- Severity: P1.
- Evidence: `docs/plans/agent_integration_readiness.md:23-26` explicitly says the
  current benchmarks do not establish agent policy, recovery, or task outcomes;
  no preregistration or three-arm analysis contract exists.
- Reproduction: repository search finds component benchmarks but no agent-level
  treatment assignment, held-out split, power analysis, or paired estimator.
- Root cause: component quality and agent utility are different systems under
  test and the latter has not been designed.
- Required change: freeze treatment definitions, prompt/model identity, scenario
  splits, estimands, sample-size simulation, multiplicity policy, harm gates,
  inconclusive policy, and analysis code before certification episodes run.
- Tests: protocol schema, split disjointness, treatment equality for common
  factors, blocked randomization, deterministic analysis fixtures, and mutation
  tests that demonstrate contamination is rejected.
- Independent verification: preregistration digest is included in every episode
  and the analysis accepts only matching artifacts.
- Completion evidence: immutable protocol and split manifests with a successful
  power report and independent review before live certification.

### AE-004: Existing Scenarios Do Not Grade Memory-Conditioned Agent Behavior

- Severity: P1.
- Evidence:
  - `memorii/tests/integration/test_harness_runtime_integration.py:112-121`
    exercises a short in-process debugging sequence.
  - `docs/plans/agent_integration_readiness.md:23-26` states that current suites
    do not measure end-to-end task outcomes.
- Reproduction: existing tests can pass without an agent receiving a stale
  premise, choosing a downstream tool action from memory, surviving a process
  restart, or isolating a concurrent task.
- Root cause: current fixtures validate component contracts, not a behavioral
  environment with hidden state and counterfactual treatments.
- Required change: create development, validation, and held-out multi-session
  engineering scenarios with hidden behavioral oracles and all cases required by
  `AR-SCENARIO-001`.
- Tests: positive, negative, stale-state, false-premise, abstention, source-trust,
  duplicate delivery, partial delivery, task/session/user isolation, and
  no-memory-control scenarios.
- Independent verification: the grader scores sandbox state and downstream tool
  actions, not model prose alone; hidden oracle fields never enter agent context.
- Completion evidence: every scenario-family requirement is represented in the
  manifest and coverage validation passes.

### AE-005: Evaluation Restart And State Ownership Are Undefined

- Severity: P1.
- Evidence:
  - `FilesystemStorageBundle` persists memory, work, decision, and trace state
    (`bundle.py:23-31`).
  - Execution, solver, overlay, and event-log stores are in-memory only
    (`stores/execution_graph/store.py:11`, `stores/solver_graph/store.py:11`,
    `stores/overlays/store.py:9`, `stores/event_log/store.py:9`).
  - Current runtime harness restart tests reuse process-local stores.
- Reproduction: terminate the current `MemoriiRuntimeAPI` test process and its
  execution/solver state disappears. Provider delivery replay does survive a
  fresh process and is already covered separately.
- Root cause: the evaluator's required state categories and chosen production
  composition have not been explicitly bounded.
- Required change: for this experiment, use the provider-memory composition only.
  Persist evaluator transcript/checkpoint state and the bundle-backed memory,
  work, decision, and trace state. Launch a genuinely new worker process after
  interruption. Do not instantiate `MemoriiRuntimeAPI`; therefore execution,
  solver, overlay, and event-log persistence is not required and no claim about
  memory-owned reasoning or its resume semantics is permitted.
- Tests: kill/reopen, caller-owned operation-ID replay, partial-turn recovery,
  duplicate delivery, corrupted evaluator checkpoint, independent store reopen,
  and treatment-root isolation.
- Independent verification: compare process IDs, reopen from disk, and inspect
  record counts and final actions. In-process reconstruction is not accepted.
- Completion evidence: restart scenarios pass from a fresh operating-system
  process without duplicated mutations or hidden fixture restoration.

### AE-006: No Unified Episode Trace Or Provenance Contract Exists

- Severity: P1.
- Evidence: `FilesystemStorageBundle` exposes only an LLM-decision trace store;
  no typed artifact links experiment, treatment, turn, tool, provider operation,
  retrieval decision, memory revision, downstream action, outcome, and cost.
- Reproduction: no single artifact can reconstruct why an agent action followed
  a particular memory selection or prove that all treatment factors were held
  constant.
- Root cause: component traces were built for component auditing, not causal
  episode reconstruction.
- Required change: add an evaluator-owned append-only typed episode trace and
  run manifest. Reference production IDs; do not copy production semantics into
  the evaluator.
- Tests: schema round-trip, ordering, referential integrity, redaction, content
  digest, truncation/corruption, missing-event rejection, and deterministic
  replay validation.
- Independent verification: reconstruct an episode solely from artifacts and
  compare it to sandbox state and provider stores.
- Completion evidence: every episode passes schema, provenance, cost, and graph
  consistency validation.

### AE-007: Agent-Evaluation Safety And Resource Controls Are Missing

- Severity: P1.
- Evidence: the live component workflow has job timeouts, but no agent evaluator
  exists with tool, filesystem, network, turn, token, call, time, or cost limits.
- Reproduction: there is no evaluator command whose schema requires these limits
  or whose worker enforces a stop reason.
- Root cause: the current repository has not yet executed autonomous agent tools.
- Required change: use disposable scenario workspaces, an allowlisted local tool
  environment, denied network except model/provider endpoints in the orchestrator,
  hard budgets, provider-health stop rules, immutable traces, cleanup, and a
  retention manifest.
- Tests: path traversal, symlink escape, undeclared command, network attempt,
  timeout, token/call/cost exhaustion, malformed tool result, and cleanup tests.
- Independent verification: inspect the operating-system process command,
  workspace root, denied action trace, and terminal stop reason.
- Completion evidence: adversarial safety tests pass and every episode records a
  valid budget ledger and terminal reason.

### AE-008: Next-Step Output Can Masquerade As Grounded Planning

- Severity: P2.
- Evidence:
  - `memorii/memorii/core/next_step/models.py:16-27` represents `next_step` as
    `dict[str, object]`.
  - `memorii/memorii/core/next_step/engine.py:177-208` emits generic actions with
    reason `frontier_planner_not_yet_enabled`.
- Reproduction: construct the default provider with active work state and no
  solver planner; the tool returns actionable prose despite no grounded frontier.
- Root cause: fallback UX and evidence-backed recommendation share one loose
  transport shape.
- Required change: replace the dictionary with a typed recommendation contract
  containing status (`grounded`, `procedural`, `abstain`), action type,
  description, confidence, reason, evidence IDs, selected state IDs, planner use,
  and fallback reason. Unconfigured planning must be `abstain` or explicitly
  procedural, never grounded.
- Tests: grounded planner, decision workflow, no state, ambiguous state,
  unconfigured planner, missing evidence, and serialization tests.
- Independent verification: the evaluator rejects any result whose claimed
  grounding is inconsistent with evidence and selected-state IDs.
- Completion evidence: no generic fallback is counted as an evidence-backed
  recommendation; harmful and unsupported recommendation rates are reported.

### AE-009: Pilot Rollback Semantics Do Not Exist

- Severity: P2.
- Evidence: `docs/plans/agent_integration_readiness.md:63-71` records that the
  default-on component has no runtime disable mechanism; the provider constructor
  has no typed influence policy.
- Reproduction: once a host invokes the provider path, there is no atomic policy
  transition that stops new evolution and memory influence while preserving
  existing state and auditing the transition.
- Root cause: rollback was deliberately deferred until agent-level evidence.
- Required change: conditional Phase 8 only. Add a typed host-owned policy with
  fully defined `active`, `observe_only`, `read_only`, and `bypass` behavior,
  including raw observations, pending operations, retrieval fallback, re-enable,
  fencing, and audit events.
- Tests: disable during in-flight work, restart while disabled, pending work,
  retrieval failure, state preservation, re-enable, and policy epoch fencing.
- Independent verification: black-box pilot host tests show zero memory influence
  in bypass/observe-only modes while existing state remains intact.
- Completion evidence: operator can enact and verify rollback without state
  deletion or ambiguous downstream behavior.

### AE-010: Pilot Persistence And Operations Are Not Yet Demonstrated

- Severity: P2.
- Evidence: only provider-memory state has a complete filesystem bundle; there is
  no pilot runbook, alert contract, export/deletion flow, or validated unavailable
  and corrupt-store behavior for an agent host.
- Reproduction: no controlled-pilot command can demonstrate restart, health,
  rollback ownership, alerting, retention, export, and deletion as one acceptance
  exercise.
- Root cause: component persistence is not the same as operational pilot
  readiness.
- Required change: conditional Phase 8 only. Keep the pilot composition limited
  to provider memory; require one writer per storage root unless concurrency is
  explicitly hardened. Add host checkpoint persistence, health/alert contracts,
  retention, export/deletion, and pilot runbooks. Execution/solver/overlay/event
  stores remain outside the pilot and must not be instantiated or claimed.
- Tests: clean restart, corrupt/unavailable store, disk limit, export/delete,
  scope isolation, rollback, and alert-delivery tests.
- Independent verification: a fresh host process completes the controlled-pilot
  acceptance exercise using only persisted state and documented controls.
- Completion evidence: all Phase 8 controls pass on the exact pilot candidate and
  the operational owner signs the runbook.

## Architecture Decision

### Evaluation Composition

The first experiment uses a host-neutral provider-memory loop:

```text
scenario environment
  -> evaluator-owned agent/model loop
  -> ProviderMemoryService public APIs
       - sync_event / Hermes-style turn delivery
       - retrieve_evolution_decision or prefetch
       - handle_tool_call for explicit work/decision/progress tools
  -> evaluator-owned downstream tool action
  -> sandbox outcome and hidden behavioral grader
```

`MemoriiRuntimeAPI` is not part of this experiment. This is intentional, not a
compatibility workaround. The experiment asks whether the production provider
memory plane improves a host agent's behavior. Adding the separate execution and
solver runtime would introduce a second treatment and require persistence that
does not yet exist. No conclusion may be drawn about memory-owned reasoning,
solver frontier quality, or `MemoriiRuntimeAPI` restart behavior.

### Treatment Arms

| Arm | Common transcript | Memorii ingestion | Memorii retrieval | Explicit Memorii tools |
| --- | --- | --- | --- | --- |
| `transcript_baseline` | Yes, frozen common strategy | No | No | No |
| `memorii_retrieval` | Yes, identical strategy | Yes | Structured retrieval injected through one frozen adapter | No |
| `memorii_full` | Yes, identical strategy | Yes | Same retrieval adapter | Work, decision, progress, outcome, and typed next-step tools |

No treatment label appears in the model prompt. The tool set is the intended
treatment difference. Each arm has a separate process, storage root, transcript,
cache namespace, artifact directory, and provider operation-ID namespace.

### State Ownership

| State | Owner | Experiment requirement | Pilot requirement |
| --- | --- | --- | --- |
| Agent transcript and host checkpoint | Evaluator/host | Persistent; common policy across arms | Persistent and recoverable |
| Memory plane and evolution operations | Memorii provider composition | Persistent JSONL bundle | Persistent, fenced, health-checked |
| Work state | Memorii provider composition | Required in full arm | Required if full behavior is piloted |
| Decision state | Memorii provider composition | Required in full arm | Required if decision tools are piloted |
| LLM decision trace | Memorii provider composition | Required in Memorii arms | Required and retained per policy |
| Episode trace and oracle outcomes | Evaluator | Required; never imported by production | Replaced by host operational trace |
| Execution graph | Not used | Explicitly excluded | Excluded from this pilot |
| Solver graph | Not used | Explicitly excluded | Excluded from this pilot |
| Overlay store | Not used | Explicitly excluded | Excluded from this pilot |
| Memorii event-log store | Not used | Explicitly excluded | Excluded from this pilot |

### Episode Trace Contract

Every trace event contains:

- experiment, protocol, source, prompt, model, scenario, arm, seed, and replicate
  identities;
- monotonic episode sequence number and wall/monotonic times;
- session, task, user, turn, tool, and provider operation IDs;
- redacted request/result summaries and content digests;
- extraction status, attempts, fallback, retry, provider request ID, model, token
  usage, latency, and cost;
- structured retrieval status and selected/supporting/context/rejected memory IDs;
- memory data revision and graph snapshot digest;
- work, decision, and next-step state IDs;
- downstream action, sandbox transition, outcome, budget ledger, and stop reason.

Credentials and secret-like values are forbidden. Raw scenario content is stored
in an access-controlled raw trace artifact, while the normal trace stores
redacted summaries and digests. Production code never imports evaluator schemas.

## Statistical Protocol

### Unit And Randomization

- The independent analysis unit is a unique task/scenario, never a turn.
- Model replicates within a scenario estimate stochastic variability but do not
  inflate the number of independent scenarios. Replicate outcomes are aggregated
  within scenario and arm before confirmatory inference.
- Each scenario is run in all three arms as a paired block.
- Arm order is randomized within scenario and balanced across scenario families
  to reduce provider-time and order effects.
- Common scenario seeds and equivalent budgets are used across arms. Provider
  nondeterminism is recorded rather than represented as deterministic.

### Splits

- Development: may be used to fix harness bugs and improve prompts or policy.
- Validation: may be used once per frozen candidate for model/protocol selection;
  changes send the candidate back to development.
- Held-out certification: sealed until Phase 6; never used to tune prompts,
  thresholds, scenario logic, or grading.
- Scenario templates, semantic entities, and state-transition patterns are
  deduplicated across splits, not merely scenario IDs.

### Outcomes

Primary outcome:

- scenario-level task success determined from sandbox state and required
  downstream actions, not final prose.

Confirmatory comparisons:

1. `memorii_full - transcript_baseline`.
2. `memorii_retrieval - transcript_baseline`.

Secondary outcomes:

- restart recovery;
- state resolution;
- false-premise resistance;
- implicit policy adaptation;
- correct current-versus-historical use;
- abstention quality;
- evidence precision/recall;
- unsupported durable claims;
- scope leakage;
- harmful recommendation/action rate;
- stale-memory utilization;
- turns, tool calls, provider calls, tokens, latency, and cost.

### Estimation And Error Control

- Estimate paired scenario-level risk differences and report 95% cluster
  bootstrap intervals over scenarios.
- Use blocked randomization inference for the two confirmatory comparisons.
- Control familywise error across the two comparisons with Holm's procedure at
  alpha 0.05.
- Report all prespecified family effects and heterogeneity; do not promote
  exploratory subgroup results to confirmatory claims.
- Zero-tolerance events include cross-user/task leakage, hidden-oracle leakage,
  unreviewed permanent user-memory writes, credential exposure, and unsafe
  sandbox escape.
- For non-zero harm tolerances, require a prespecified one-sided upper confidence
  bound below the accepted margin. Zero observed events alone is insufficient.

### Power And Sample Size

Before any held-out run, `power.py` simulates the paired blocked design using:

- baseline success and within-scenario correlation estimated from development;
- a prespecified minimum practically important absolute improvement;
- expected model replicate variance;
- Holm-adjusted alpha;
- at least 80% power for the primary full-versus-baseline comparison; and
- enough independent scenarios to bound critical harm rates.

The report chooses the larger sample required by efficacy or harm constraints.
If that sample is unaffordable, the result is `no-go`, not a relaxed threshold.

### Decision Policy

`go` requires all of the following:

- valid component certification and artifact provenance;
- statistically supported improvement for the full arm over baseline with a
  positive lower confidence bound and the prespecified practical effect;
- no zero-tolerance event;
- all harm upper bounds below their preregistered margins;
- no material regression in restart recovery, false-premise resistance, scope
  isolation, or cost/latency budgets;
- successful independent false-success review.

`no-go` is required for a failed efficacy or safety gate. `Inconclusive` is also
a no-go for pilot purposes. A later experiment requires a new preregistration
and new held-out scenarios; the old certification set cannot become development
data while retaining its certification label.

## Implementation Phases

### Phase 0: Baseline And Issue Reproduction

Files changed: only this plan and a generated, noncommitted baseline evidence
record under the implementation worktree's artifact root.

Actions:

1. Reconfirm actual checkout, branch, merge base, local/remote SHA, dirty state,
   PR head, required checks, and live-run status.
2. Re-run the 196 focused tests plus full deterministic gates.
3. Record the frozen issue inventory and admissibility rule in the implementation
   task.
4. Decide branch sequencing: finish and merge PR #107 at its exact certified SHA,
   then create a new agent-evaluation branch. Do not mix this evaluator plan into
   the hardening candidate after certification.

Commands:

```bash
git status --short --branch
git rev-parse HEAD
gh pr checks 107
cd memorii
python -W error -m pytest tests/unit -p no:cacheprovider
python -m ruff check memorii tests
pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"
```

Exit criteria:

- AE-001 through AE-010 are reproduced or dispositioned exactly as above.
- No unrelated issue is admitted.
- Baseline evidence names one source SHA.

Prohibited claims: all readiness claims beyond the existing deterministic
component evidence.

### Phase 1: Complete Exact-SHA Memory-Component Certification

Files and symbols:

- Add `memorii/memorii/tools/verify_live_provider.py` with typed
  `ProviderCanaryRequest`, `ProviderCanaryResponse`, and `ProviderCanaryArtifact`.
- Add `memorii/tests/unit/tools/test_verify_live_provider.py`.
- Change `.github/workflows/benchmark-scheduled.yml` to add one
  `live-provider-canary` job and make `live-runtime-smoke` depend on it.
- Update `docs/development/benchmark_certification.md` with canary, call-budget,
  invalidation, and exact-SHA acceptance steps.
- Do not alter production extraction semantics, prompts, or thresholds merely to
  make certification pass.

Canary contract:

- Use `OpenAIStructuredClient` through the same strict structured-output path.
- Require a valid schema response, provider request ID, successful status,
  requested/actual model compatibility, nonempty token usage, one attempt, no
  fallback, and no refusal.
- Emit only redacted metadata, usage, latency, model identity, source SHA, SDK
  version, and a content digest.
- One canary call runs before any matrix job. A failure prevents the campaign.

Provider budget:

- The current matrix has 20 runs (`10 seeds x 2 replicates`) and 25 scenarios per
  run with 25-60 events, so runtime extraction is bounded at 12,500-30,000 calls,
  plus one canary.
- Before dispatch, measure input/output tokens on a two-scenario health smoke and
  calculate a dollar ceiling using the exact model price. The code default is
  `gpt-4.1-mini`; as of this plan its published standard price is $0.40/M input
  and $1.60/M output tokens. At a conservative 8,000 input and 1,600 output token
  cap per extraction, the campaign envelope is approximately $72-$173. The
  measured estimate and operator-approved cap are authoritative.

External actions:

1. Push the clean candidate.
2. Confirm deterministic checks on that SHA.
3. Dispatch `benchmark-scheduled.yml` on the candidate branch.
4. Validate the canary artifact before the matrix starts.
5. Wait for every matrix artifact and the aggregate gate.
6. Verify the GitHub check, source SHA, report source revisions, package
   fingerprint, prompt hashes, model identity, provider health, coverage, and
   statistical certificate all agree.
7. Merge only that SHA. Any relevant post-dispatch change requires a new run.

Tests include fake provider success/failure, schema invalidity, model mismatch,
redaction, workflow dependency, artifact tampering, mixed revision, missing
report, provider failure, and fallback-rate rejection.

Exit criteria: AE-001 closed and the exact clean revision is
component-certified. A merely running, cancelled, partial, or prior-SHA workflow
does not exit the phase.

Prohibited claims: experiment-ready, evaluation-complete, pilot-ready, or
production-ready.

### Phase 2: Freeze Protocol, Scenarios, Metrics, And Statistical Design

Files and symbols:

- Add `docs/design/agent_memory_evaluation_protocol.md`.
- Add `docs/development/agent_memory_evaluation.md`.
- Add non-installable evaluator package
  `memorii/evaluations/agent_memory/` with:
  - `contracts.py`: protocol, treatment, budget, trace, result, and manifest models;
  - `protocol.py`: loading, canonical serialization, and digest validation;
  - `scenario_schema.py`: visible scenario and hidden oracle contracts;
  - `split_validation.py`: split disjointness and semantic-family leakage checks;
  - `power.py`: simulation-based sample-size report;
  - `statistics.py`: frozen paired estimators and multiplicity handling.
- Add scenario manifests under
  `memorii/evaluations/agent_memory/scenarios/{development,validation,certification}/`.
- Store hidden oracles under separate evaluator-only paths with explicit import
  and context-leakage tests.

Data contracts:

- `AgentEvaluationProtocol` freezes source SHA, agent and memory model snapshots,
  prompts, tool schemas, transcript strategy, budgets, treatment arms, splits,
  estimands, thresholds, and analysis version.
- `ScenarioSpec` contains only agent-visible initial state and deterministic
  environment transitions.
- `ScenarioOracle` contains required/forbidden actions, final sandbox predicates,
  stale/current state, scope expectations, and harm labels. It is grader-only.
- `PowerReport` records assumptions, simulation seed, independent scenario count,
  replicate count, achieved power, harm precision, and call/cost bounds.

Scenario coverage must include every case in AR-SCENARIO-001. At least one
control scenario is deliberately memory-irrelevant and should show no treatment
benefit.

Tests:

- schema and canonical-digest tests;
- no duplicate scenario families across splits;
- hidden oracle cannot be imported by production or rendered into agent context;
- arm-common prompt/model/tool-environment equality;
- deterministic power simulation and estimator goldens;
- adversarial mislabeled treatment and contaminated path rejection.

Exit criteria: AE-003 and the specification portion of AE-004 are closed; the
protocol, power report, and held-out manifest are frozen before harness live use.

Prohibited claims: experiment-ready until Phases 3 and 4 pass; any agent benefit.

### Phase 3: Implement Evaluation-Only Harness And Treatment Isolation

Files and symbols in `memorii/evaluations/agent_memory/`:

- `agent_client.py`: evaluator `AgentClient` protocol and one OpenAI Responses
  adapter; no dependency from production packages.
- `tool_environment.py`: allowlisted software-debugging tools over a disposable
  workspace.
- `treatments.py`: `TranscriptBaselineTreatment`,
  `MemoriiRetrievalTreatment`, and `MemoriiFullTreatment` implementing one typed
  evaluator protocol.
- `memory_adapter.py`: the only evaluator adapter over public
  `ProviderMemoryService` APIs.
- `operation_ids.py`: deterministic caller-owned operation IDs derived from
  protocol, episode, session, turn, and delivery identity.
- `worker.py`: runs one arm/episode in one process and owns no cross-arm cache.
- `orchestrator.py`: blocked arm assignment, subprocess lifecycle, budgets, and
  artifact collection.
- `cli.py`: deterministic and live commands with explicit `--allow-live` and
  approved dollar cap.

Production changes for AE-008:

- Change `memorii/memorii/core/next_step/models.py` to add typed
  `NextStepRecommendation` and `NextStepRecommendationStatus`.
- Change `memorii/memorii/core/next_step/engine.py` so unconfigured or ambiguous
  planning is `abstain` or `procedural`, never `grounded`.
- Update provider tool serialization without aliases or compatibility transport.

Ownership:

- Evaluator owns sessions, model calls, transcript, tool execution, treatment,
  process lifecycle, and outcome grading.
- Memorii owns ingestion, extraction, lifecycle, retrieval, work/decision state,
  recommendation semantics, and persistence.
- The evaluator may inspect production output but may not select records, repair
  extraction, or rewrite retrieval decisions.

Tests:

- scripted-agent end-to-end tests for all arms;
- same common prompt/model/environment/budget across arms;
- no shared storage, caches, transcripts, operation IDs, or artifacts;
- public-API-only imports;
- no direct store mutation;
- provider failure and baseline fallback;
- next-step grounded/procedural/abstain cases;
- tool schema and malformed call handling.

Exit criteria: AE-002 and AE-008 are closed; all arms complete deterministic
episodes with only intended treatment differences.

Prohibited claims: experiment-ready until restart, trace, safety, and artifact
tests pass.

### Phase 4: Add Restart, Trace, Artifact, And Deterministic Scenario Verification

Files and symbols:

- `checkpoint_store.py`: evaluator-owned crash-atomic host checkpoint with
  checksum and protocol/episode identity.
- `trace.py`: append-only typed trace writer and redaction policy.
- `artifact_io.py`: canonical manifests, atomic finalize, checksums, and completion
  marker.
- `validate_artifacts.py`: cross-file provenance and referential-integrity checks.
- `grading.py`: deterministic sandbox/action grader using hidden oracle data.
- Add tests under `memorii/tests/evaluation/agent_memory/` and process integration
  tests under `memorii/tests/integration/` with descriptive domain names, never
  temporary phase names.

Restart mechanism:

1. Orchestrator launches a worker subprocess.
2. Scenario reaches a declared interruption boundary.
3. Worker writes and fsyncs its host checkpoint and exits, or is forcibly killed
   after the last acknowledged checkpoint.
4. Orchestrator starts a different operating-system process with the same arm
   storage root.
5. The new worker reopens bundle and host state, retries the same unacknowledged
   operation ID, and continues.

Tests:

- fresh-process restart and process-ID assertion;
- duplicate and partial delivery around the kill boundary;
- memory/work/decision/trace reopen independently;
- corrupted or truncated checkpoint and trace fail closed;
- all required scenario families;
- task/session/user isolation and concurrent unrelated state;
- stale premise, implicit invalidation, current/historical, source trust, and
  abstention;
- hidden-oracle and treatment-label leakage scans;
- trace redaction, sequence, references, usage, cost, and content digests;
- path traversal, symlink escape, denied tool/network action, all budget limits,
  and cleanup;
- false-success fixtures where plausible prose conflicts with sandbox outcome.

Independent verification does not mirror Memorii retrieval. It checks final
sandbox predicates, action logs, public output IDs, and persisted record
invariants.

Commands:

```bash
cd memorii
python -W error -m pytest tests/evaluation tests/integration -p no:cacheprovider
python -m evaluations.agent_memory.cli validate-protocol --protocol <path>
python -m evaluations.agent_memory.cli run-scripted --protocol <path>
python -m evaluations.agent_memory.cli validate-artifacts --root <path>
python -m ruff check memorii tests evaluations
pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"
```

Exit criteria: AE-004, AE-005, AE-006, and AE-007 are closed for the experiment;
component certification remains valid for the exact source revision; the system
is experiment-ready.

Prohibited claims: evaluation-complete, pilot-ready, production-ready, or any
claim about excluded execution/solver persistence.

### Phase 5: Run Development And Validation Experiments

Actions:

1. Run deterministic scripted agents on all development scenarios.
2. Run a small live development set within a preapproved call/dollar budget.
3. Inspect every failure, every safety event, and a stratified sample of passes.
4. Fix only reproduced in-scope defects. Any model prompt, tool schema,
   production behavior, grader, or threshold change creates a new candidate and
   returns to the relevant earlier phase.
5. Freeze the candidate and run validation once.
6. Use validation only for the prespecified selection decision. Do not inspect
   held-out certification scenarios.

Artifacts:

- protocol and source manifests;
- per-episode traces/results;
- treatment contamination report;
- provider health and budget report;
- validation analysis and issue disposition;
- updated power report using only development estimates.

Exit criteria: validation meets preregistered quality and safety requirements,
all artifacts validate, no frozen issue is open, and the candidate source,
prompt, model, tool, protocol, and analysis digests are frozen for Phase 6.

Prohibited claims: evaluation-complete or pilot-ready. Validation performance is
not held-out evidence.

### Phase 6: Run Held-Out Live Certification Experiment

Preconditions:

- component-certified exact source revision;
- experiment-ready harness on the same exact revision;
- clean Git tree and immutable protocol, model snapshot, prompts, tool schemas,
  scenario split, grader, estimators, and thresholds;
- provider canary pass;
- approved calls/tokens/time/dollar ceiling from `PowerReport`;
- sealed held-out scenarios.

Execution:

1. Dispatch paired blocks with randomized arm order.
2. Use one process and one storage root per arm/episode.
3. Stop on provider-health, budget, zero-tolerance safety, treatment leakage, or
   artifact-integrity failure.
4. Do not rerun individual failed episodes selectively. Apply only the
   preregistered whole-block retry policy for infrastructure failure.
5. Validate every artifact before unblinding treatment outcomes.

False-success inspection:

- Review all apparent successes in high-risk stale-premise, scope-isolation,
  contradictory-evidence, and abstention families.
- Blindly dual-review at least 20% of remaining successful episodes per arm and
  family, with a prespecified minimum count.
- Adjudicate disagreements before treatment labels and aggregate statistics are
  revealed.
- A false-success rate above the preregistered margin invalidates the evaluation.

Exit criteria: a complete, source-bound, protocol-bound held-out artifact set
with no integrity failure. This phase produces evidence but not the go decision.

Prohibited claims: pilot-ready until Phase 7 says `go` and Phase 8 completes.

### Phase 7: Analyze Results And Decide Go Or No-Go

Files and symbols:

- `analysis.py`: consumes only validated held-out episode results and frozen
  protocol.
- `reporting.py`: emits machine-readable and human-readable reports without
  recomputing judgments.

Required reports:

- paired effects and 95% intervals;
- blocked randomization tests and Holm-adjusted decisions;
- family and replicate sensitivity;
- harm upper bounds and zero-tolerance event ledger;
- restart, stale-premise, policy-adaptation, scope, abstention, recommendation,
  and cost/latency metrics;
- provider health and missingness analysis;
- false-success review and reviewer agreement;
- exact source/model/prompt/tool/protocol/scenario/artifact digests;
- explicit `go`, `no_go`, or `inconclusive` decision with reasons.

Independent verification:

- A second command recomputes the analysis from immutable episode-result rows.
- Report totals must reconcile with manifests and trace terminal events.
- A blinded reviewer verifies exclusions and missingness before unblinding.

Exit criteria: AE-003 is fully closed and the evaluation is complete. Only `go`
authorizes Phase 8. `no_go` or `inconclusive` ends this plan without pilot work.

### Phase 8: Conditional Controlled-Pilot Controls

This phase is prohibited unless Phase 7 records `go`.

Production files and symbols:

- Add a typed provider influence policy under `memorii/memorii/core/provider/`,
  owned by provider composition rather than the evaluator.
- Extend provider composition with an injected host-owned policy source and
  monotonic policy epoch.
- Add typed audit events and policy-state output to provider results.
- Extend filesystem composition only for state actually used by the provider
  pilot. Do not add execution/solver/overlay/event persistence.

Policy semantics:

| Mode | Raw observations | Evolution/write | Retrieval influence | Pending work |
| --- | --- | --- | --- | --- |
| `active` | Append | Enabled | Enabled | Normal reconciliation |
| `observe_only` | Append for audit | No derived commit; explicit writes rejected | Disabled; host uses baseline | No new claims; in-flight commits fenced by changed policy epoch; pending retained |
| `read_only` | No new mutation | Disabled | Existing state may be retrieved | Pending retained, not reconciled |
| `bypass` | Host does not call Memorii | Disabled | Disabled; host uses baseline | State untouched |

Retrieval influence fails closed: no Memorii context is injected on policy or
store failure. The host task falls back to the frozen baseline policy, so task
execution fails open without memory influence. Re-enable increments the policy
epoch, health-checks stores, reconciles only eligible pending work, and preserves
the audit trail.

Pilot operational work:

- persistent host checkpoint and one-writer-per-storage-root topology;
- store health, corruption, capacity, latency, and provider-health alerts;
- named rollback owner and on-call procedure;
- scoped retention, export, deletion, and re-enable runbooks;
- no unreviewed permanent user-memory writes from ordinary chat;
- disposable initial cohort and explicit user/task isolation;
- fixed exposure cap and automatic rollback thresholds.

Tests:

- policy transitions and epoch fencing;
- in-flight and pending operations;
- observe-only raw journal behavior;
- read-only and bypass retrieval behavior;
- restart while disabled and re-enable;
- unavailable/corrupt/full store;
- alert delivery, export, deletion, scope isolation, and audit integrity;
- fresh-process controlled-pilot acceptance exercise.

Exit criteria: AE-009 and AE-010 close, operational owner approves the runbook,
and the exact pilot candidate passes all deterministic and live safety gates. The
system is pilot-ready only for this provider-memory composition and declared
cohort.

Prohibited claims: production-ready, distributed-safe, framework-general pilot,
or readiness of the excluded execution/solver runtime.

## Test And Verification Matrix

| Test class | Required evidence | Independent oracle |
| --- | --- | --- |
| Scripted agent | Deterministic actions and artifacts in all arms | Sandbox state predicates |
| Public API | Only supported provider methods and tool schemas used | Import/monkeypatch boundary test |
| Real restart | New PID reopens persisted state | Process and disk evidence |
| Duplicate/partial delivery | Stable operation IDs and no duplicate mutations | Persisted record counts/revisions |
| Scope isolation | No cross-user/task/session selected IDs | Hidden scope fixtures and public decisions |
| Stale/false premise | Current state chosen; stale premise rejected | Hidden temporal state and downstream action |
| Abstention | Ambiguity causes no unsupported action | Forbidden-action oracle |
| Treatment isolation | No shared root/cache/transcript/artifact | Filesystem/process manifest |
| Artifact provenance | All identities and digests reconcile | Independent validator |
| Provider failure | Classified fallback/stop behavior | Fake provider fault injection |
| Cost/latency | Usage reconciles to request trace and cap | Ledger recomputation |
| Held-out live | Paired blocks over sealed scenarios | Frozen grader plus blinded review |
| False successes | Passing prose cannot override failed environment state | Sandbox and action log |

## Requirement Traceability

| Requirement | Issue | Milestone | Implementation | Tests | Independent evidence | Completion criterion | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AR-CERT-001 | AE-001 | Component-certified | Phase 1 canary and exact-SHA workflow | Canary/workflow/artifact tests | GitHub check and source-bound artifacts | Final live gate passes exact clean SHA | Open; run 29958016147 incomplete and lacks real preflight canary |
| AR-HARNESS-001 | AE-002 | Experiment-ready | Evaluator provider-memory loop | Scripted three-arm and API boundary tests | Public records and sandbox outcomes | Isolated deterministic episodes pass | Open |
| AR-EXPERIMENT-001 | AE-003 | Evaluation-complete | Frozen protocol, power, statistics | Schema/randomization/analysis tests | Preregistration digest and recomputation | Held-out causal report valid | Open |
| AR-SCENARIO-001 | AE-004 | Experiment-ready | Split long-horizon scenario suite | Coverage and behavioral tests | Hidden sandbox/action oracle | All required families covered | Open |
| AR-DURABILITY-001 | AE-005, AE-010 | Experiment-ready; pilot-ready | Bundle plus host checkpoint; conditional pilot ops | Real-process reopen/corruption tests | PID/disk/revision evidence | Required state survives; excluded state unclaimed | Open; AE-010 conditional |
| AR-ROLLBACK-001 | AE-009 | Pilot-ready | Conditional typed influence policy | Transition/fencing/restart tests | Black-box host behavior | Disable/read-only/bypass semantics proven | Conditional |
| AR-NEXTSTEP-001 | AE-008 | Full-treatment validity | Typed recommendation and abstention | Grounding/fallback/harm tests | Evidence-ID consistency validator | No fallback counted as grounded | Open |
| AR-TRACE-001 | AE-006 | Experiment-ready | Typed episode trace and manifests | Schema/redaction/integrity tests | Independent reconstruction | Every episode reconstructable | Open |
| AR-SAFETY-001 | AE-007, AE-010 | Experiment-ready; pilot-ready | Sandbox/budgets; conditional pilot ops | Escape/budget/store/alert tests | OS state and terminal ledger | No unbounded or unaudited episode/pilot | Open; AE-010 conditional |

## Experimental Claim Traceability

| Claim | Metric | Unit | Comparison | Sample-size reasoning | Uncertainty | Failure/harm threshold | Permitted conclusion |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Full Memorii improves agent task success | Sandbox-graded success | Unique scenario | Full vs baseline, paired | Simulation for practical effect and >=80% power | 95% cluster bootstrap CI plus blocked randomization test | Positive practical lower bound; Holm pass; harm gates pass | Full provider-memory treatment improves this scenario distribution |
| Retrieval alone improves task success | Sandbox-graded success | Unique scenario | Retrieval vs baseline, paired | Same power framework, secondary confirmatory comparison | Same | Holm pass and harm gates | Retrieval treatment improves this scenario distribution |
| Memorii resolves stale state | State-resolution score | Unique stale scenario | Each Memorii arm vs baseline | Family coverage plus precision target | Family CI | No false-premise harm margin breach | Memorii improves state resolution on tested stale families |
| Memorii changes policy correctly | Required downstream action | Unique scenario | Full/retrieval vs baseline | Powered within primary scenario set | Paired effect CI | Unsupported/unsafe action gate | Memory changes behavior correctly, not merely answers |
| Restart is reliable | Successful recovery without duplicate mutation | Unique restart scenario | Memorii arms against deterministic invariant | Minimum scenario/failure-bound design | One-sided failure-rate upper bound | Bound below preregistered margin | Provider-memory experiment recovers under tested restart protocol |
| Scope remains isolated | Cross-scope selected/action IDs | Unique isolation scenario | Invariant in Memorii arms | Sized for harm bound | Exact one-sided upper bound | Zero observed and upper bound below margin; any actual leak is no-go | Isolation supported for tested topology |
| Next-step advice is grounded | Grounded recommendation precision and harmful action rate | Unique recommendation opportunity | Full arm internal strata | Prespecified count of grounded opportunities | Precision/harm intervals | No generic fallback; harm bound below margin | Typed recommendations are useful under configured conditions |
| Cost is acceptable | Calls, tokens, latency, dollars per successful task | Unique scenario | All arms | Full powered sample ledger | Bootstrap interval | Preregistered operational cap | Cost/quality tradeoff is acceptable for controlled pilot |

## Phase Exit Checklist

Before moving from any phase:

1. Every scheduled file and symbol change is present; no temporary phase names,
   compatibility aliases, or relocation facades remain.
2. Production packages do not import evaluator code, fixtures, or oracle data.
3. Evaluator logic does not reimplement retrieval, lifecycle, entity resolution,
   or recommendation semantics.
4. Positive, negative, adversarial, restart, and invariant tests for the phase
   pass under warnings-as-errors.
5. Static checks, package-content checks, and import-boundary checks pass.
6. Artifacts identify the exact clean revision and protocol digest.
7. No completion claim depends only on mirrored logic.
8. No newly admitted issue falls outside the frozen admission rule.
9. All external actions are either complete or the phase remains blocked.
10. Readiness claims do not exceed the phase's objective evidence.

## Critical Self-Review

1. Every known requirement has an implementation or explicit external path.
2. Component certification and agent evaluation are separate systems under test.
3. The evaluator uses public Memorii APIs and independent behavioral outcomes; it
   does not implement a second semantic-memory pipeline.
4. Arms cannot share storage, process memory, caches, transcripts, operation IDs,
   or artifacts.
5. Task outcomes, memory harms, and cost are all measured.
6. The unique scenario is the inference unit; turns and replicates do not inflate
   sample size.
7. Development, validation, and held-out certification sets are structurally
   separated and semantically deduplicated.
8. Passing prose cannot override sandbox failure, and false-success review is
   mandatory.
9. Restart verification crosses a real process boundary.
10. Generic next-step fallbacks are typed as procedural or abstention, not
    grounded recommendations.
11. The provider canary makes a real structured call before the costly campaign.
12. Source SHA, provider/model, prompts, tools, protocol, settings, scenarios,
    and artifacts are bound by digests.
13. Pilot rollback is a typed state machine with downstream semantics, not a
    boolean.
14. Test/oracle concepts remain outside production packages and model context.
15. No framework-specific production integration is introduced.
16. Production readiness remains outside scope.

- Frozen P1 count: 7.
- Frozen P2 count: 3.
- External blockers: completion of exact-SHA live component certification with a real provider canary; GitHub credentials and funded provider access; operator approval of live call/token/dollar budgets; sealed-scenario and blinded-review ownership; and, after a go decision only, named pilot rollback/on-call ownership.
- Estimated deterministic test cost: no provider calls; approximately 15-30 local minutes for focused evaluator checks and the existing deterministic suite, plus CI runtime.
- Estimated live provider calls and cost: current component gate is 12,501-30,001 calls including one canary; at the default `gpt-4.1-mini` planning envelope of at most 8,000 input and 1,600 output tokens per call, approximately $72-$173 before retries, with the measured preflight ledger and operator-approved cap authoritative. Agent-evaluation calls and dollars are not dispatchable until Phase 2 power analysis fixes the independent scenario count, replicates, agent turns, memory calls, and exact model prices.
- Definition of component-certified: the exact clean source revision has green deterministic checks, a successful real structured provider canary, complete valid live reports, a passing source-bound statistical certificate, and the corresponding GitHub check attached to that same SHA, with no relevant post-run change.
- Definition of experiment-ready: the component-certified revision has the frozen three-arm protocol, sealed splits, power report, evaluator-only public-API harness, independent behavioral grader, real-process restart, treatment isolation, typed traces, artifact validation, safety budgets, and all deterministic tests passing.
- Definition of evaluation-complete: the exact frozen experiment candidate has completed the preregistered held-out paired experiment, all artifacts and false-success reviews are valid, and the prespecified statistical and harm analyses produce an explicit `go`, `no_go`, or `inconclusive` result.
- Definition of pilot-ready: only after a Phase 7 `go`, the declared provider-memory composition has passed conditional rollback, persistence, observability, safety, scope, retention, export/deletion, alerting, and fresh-process operational acceptance tests for a named controlled cohort and owner.
- Explicit statement that production readiness is outside this plan.
- Explicit statement that no other work is included.
