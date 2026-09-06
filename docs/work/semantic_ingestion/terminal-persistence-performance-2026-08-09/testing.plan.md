# Terminal Persistence Performance And Topology

- Work ID: semantic_ingestion_terminal_persistence_performance_2026_08_09
- Work type: testing
- Status: active
- Coordinator: Codex main thread
- Created: 2026-08-09
- Last updated: 2026-08-09
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/milestones/m3-semantic-pipeline.plan.md`; `docs/work/semantic_ingestion/testing.plan.md`; `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/design.plan.md`
- Canonical inputs: `.github/workflows/pr-gates.yml`; `memorii/tests/ci/semantic-terminal-persistence-shards.json`; `memorii/tests/ci/semantic-terminal-persistence-test-durations.json`; `docs/development/static_tooling.md`; `docs/design/semantic_ingestion_architecture.md`
- Expected outputs: measured serialization remediation, current terminal-persistence collection and timing inventory, seven-shard plan, and a required-job topology with documented budget evidence

## Objective

Restore a measured, complete terminal-persistence topology without treating
runtime performance as evidence that the accepted semantic path is incorrect.
The resulting topology must collect every current terminal-persistence node,
assign it to exactly one dedicated shard, and preserve the 600-second
per-shard budget and timeout headroom.

## Completion Contract

Complete only when accepted and filesystem restart/race selectors have fresh
terminal results; controlled profiling identifies and addresses the owned
serialization hot path without weakening durable assertions; current collection
equals the timing inventory; the seven-shard plan is complete, disjoint, and
within budget; workflow arguments and aggregate ownership match the candidate;
and local/hosted evidence is recorded at one exact revision.
If graph-bound nodes transfer to the graph-dependent coordinator gate, the same
revision must also contain the paired graph collection/timing receipts and a
recalculated residual seven-shard collection, timing inventory, and budget;
neither WorkPlan may close on a one-sided topology claim.

## Scope

Included: accepted-path runtime (61.97 seconds), filesystem restart/race runtime
(108.27 seconds), terminal serialization cost, stale topology (224 collected
nodes versus 156 timed nodes), seven-shard recapture, budget reconciliation,
and PR-gate ownership.

Excluded: semantic product behavior, prepared-source authority, provider-root
composition, durable schema changes, assertion weakening, and unrelated unit
shards. Product defects return to the linked implementation or debugging plan.

## Constraints And Invariants

- M3 correctness may use completed long-tier focused evidence; neither runtime
  observation is a correctness blocker by itself.
- Preserve accepted, restart, corruption, recovery, lost-ack, and race
  assertions. No node may be dropped to meet budget.
- Keep the dedicated owner at seven exact-node shards unless a separately
  reviewed topology proves an equivalent or stronger owner.
- Keep `-W error`, cache disablement, current working directory, timeout, and
  aggregate dependencies identical to the live workflow unless this plan
  explicitly changes and verifies them.
- A node transferred to the graph-dependent manifest leaves this terminal
  collection and timing universe in the same revision. The graph plan is its
  sole correctness-gate owner; this WorkPlan retains every residual terminal
  node and its seven-shard performance ownership. The paired owner ledger,
  manifests, timing receipts, and budgets must prove exact-one ownership.

## Current State And Evidence Gaps

- The accepted selector took 61.97 seconds and the filesystem restart/race
  selector took 108.27 seconds. Both are performance observations; they do not
  invalidate M3 long-tier correctness evidence.
- Trace evidence identifies `SemanticTerminalSeal.validate_seal`,
  `contract_digest`, and `_normalized_typed_json` as the likely serialization
  hot path. That is a hypothesis until controlled profiling separates it from
  store and restart work.
- The dedicated owner collects 224 nodes but its checked-in timing inventory
  has 156. Median estimation yields an approximately 646.8-second seven-shard
  plan against the 600-second budget. This is incomplete topology evidence, not
  permission to use stale durations or omit nodes.
- Hosted PR results, refreshed timing files, collection pins, and aggregate
  proof are unavailable for the dirty current candidate.

## Test Portfolio And Failure Signals

| Family | Level and owner | Defect detected | Required evidence |
| --- | --- | --- | --- |
| accepted terminal path | long-tier focused selector | serialization regression or lost terminal effect | terminal result, profile, before/after duration |
| filesystem restart and race | long-tier focused selector | restart/reopen/race regression hidden by in-memory execution | terminal result, profile, restart artifact, duration |
| serialization hot path | deterministic profile experiment | repeated canonicalization/digest work dominates without semantic need | attributable timing and mutation-safe optimization proof |
| terminal collection | collection contract | missing, extra, or stale exact-node inventory | sorted node list and current count |
| duration inventory | timing capture and verifier | stale/missing/nonpositive duration | seven successful captures and inventory equality |
| PR topology | workflow structure contract | wrong argv, shard count, timeout, aggregate, or duplicate ownership | workflow contract and required-job execution |

## Planned Topology

`semantic-terminal-persistence` remains the sole exhaustive owner. It must
collect the full live selector, partition exact node IDs across seven disjoint
shards, and merge seven fresh timing outputs only when each capture succeeds.
Broad unit shards must not acquire these nodes. The aggregate must depend on
this dedicated owner rather than a hand-maintained count or median estimate.
For an acknowledged graph-node transfer, "full live selector" means the exact
residual terminal selector after those nodes are removed; the paired graph
manifest is the sole other allowed owner and must be pinned with this residual
manifest and their timing receipts at the same revision.

## Verification Matrix

| Step | Command or artifact | Passing signal |
| --- | --- | --- |
| collection | workflow-equivalent collection and shard verifier | selector, shard manifest, and timing inventory agree exactly |
| accepted baseline | exact accepted-path selector with profiling | terminal pass and saved elapsed-time attribution |
| restart/race baseline | exact filesystem selector with profiling | terminal pass and saved elapsed-time attribution |
| recapture | seven workflow-equivalent shard runs | every shard succeeds with positive, nonoverlapping durations |
| plan validation | shard verifier and workflow structure tests | seven-way plan is <= 600 seconds and aggregate owns it once |
| candidate gate | required PR workflow at candidate SHA | every required shard and aggregate succeeds |

## Delegation And Cost Ledger

| Task | Owner | Output | Status |
| --- | --- | --- | --- |
| causal profile | coordinator or read-only mapper | serialization/store/restart cost split | pending |
| collection and timing capture | one sole writer/runner | seven fresh timing artifacts | pending |
| topology/workflow update | one sole writer | manifest, timing, workflow, and contract changes | pending |
| independent closure review | test and correctness reviewers | classified topology findings | pending |

## Change Impact And Gate Ledger

| Surface | Owner | Required proof | Status |
| --- | --- | --- | --- |
| terminal persistence selectors | this testing WorkPlan | long-tier terminal results and collection equality | pending |
| duration inventory and shard manifest | this testing WorkPlan | seven fresh captures and exact-node verifier | pending |
| PR workflow and aggregate | this testing WorkPlan | structure contract and hosted required jobs | pending |
| M3 product correctness | implementation WorkPlan | focused long-tier semantic evidence | not blocked by performance topology |

## Progress Log

- 2026-08-09: Split performance and stale-topology work from M3 correctness.
  Recorded 61.97-second accepted and 108.27-second filesystem restart/race
  observations, the serialization hypothesis, and the 224-versus-156 inventory
  discrepancy. No test, workflow, timing, or product artifact changed.
- 2026-08-09: Linked scenario-writer debug follow-up. After the protected
  ambiguity classifier was corrected, the direct public ambiguity event no
  longer resolved accepted and instead reached `_persist_semantic_terminal`.
  The live runner/direct script then stalled inside replay-authority
  dependency reconstruction while decoding the persisted terminal contract:
  `provider/ingestion.py:_persist_semantic_terminal ->
  semantic_ingestion/persistence.py:persist ->
  atomic_store.py:_semantic_event_authority_updates ->
  atomic_store.py:_reconstruct_semantic_replay_authority ->
  semantic_ingestion/event_replay.py:_semantic_replay_dependency_digests ->
  semantic_ingestion/contracts.py:decode_semantic_contract ->
  memory_evolution/ingestion_contracts.py:decode_typed_value/_json`.
  Focused correctness proofs stayed green (`3` targeted tests in `12.68s`);
  this plan owns any further replay-authority decode profiling or optimization.
- 2026-08-09: Acknowledged the graph-dependent coordinator WorkPlan as a paired
  topology dependency. Any future transferred graph node moves exclusively to
  its manifest; before either WorkPlan closes, one revision must recalculate
  this plan's residual collection, seven timing shards, and budget and pin both
  manifests, timing receipts, and the owner ledger. No terminal test finding,
  timing result, workflow, or ownership transition has been claimed complete.

## Exact Next Action

Run one controlled profile of the accepted terminal selector, one controlled
profile of the filesystem restart/race selector, and one focused profile of
the protected-ambiguity replay-authority decode stack above. Capture terminal
pass/fail and attribute elapsed time between serialization, store, replay
decode, and restart work before proposing any optimization, shard/timing edit,
or paired graph-node transfer.

## Blockers And Limits

No external decision blocks planning. Candidate closure needs fresh terminal
results, controlled profiling, seven complete timing captures, and required
hosted workflow evidence. This WorkPlan must not claim M3 product correctness
or modify production semantics.
