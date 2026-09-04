# Semantic Ingestion M3.1 Resume Packet

- Active parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Active implementation WorkPlan: `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/implementation.plan.md`
- Active milestone: M3.1 graph-dependent semantic transaction closure
- Frozen candidate: `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/implementation-candidate-identity-v81.json`
- Candidate predecessor: `implementation-candidate-identity-v80.json`
- Status: complete — final closure recorded 2026-09-04 at HEAD `bd1ebf0`; see the Final Closure Record in the active implementation plan
- Coordinator: Codex main thread
- Last updated: 2026-09-04
- Git base: `4691c0374b3b01617a6a50fd83d4e3ff8a61aa84`
- Tree state: dirty shared worktree; preserve all unrelated changes

## Authority

- `docs/design/memorii_spec.md`
- `docs/design/memorii_storage_details.md`
- `docs/design/event_model.md`
- `docs/IMPLEMENTATION_RULES.md`
- `docs/design/semantic_ingestion_architecture.md`
- `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/production-entrypoint-bindings.json`

The approved semantic baseline remains `design-candidate-identity-v76.json`.
The active implementation candidate changes runtime, persistence, composition,
tests, and current-state evidence only; it does not reopen semantic design.

## Current Objective

Close M3.1 end-to-end through the ordinary direct, factory, filesystem, and
Hermes provider roots.  Accepted native operations must atomically materialize
canonical graph, event, observation, replay, and reference-integrity state.
Post-effect recovery must return the exact persisted group and terminal state
without a duplicate effect, including lease reclaim and independent JSONL
reopen.  Fixture authority injection must remain outside normal production
root signatures and calls.

## Current Scope And State

- The native normalization, authority projection, plan, authorization,
  attempt, lineage, group-commit, terminal, and recovery chain has one ordinary
  production caller.
- Accepted native group commit now persists canonical graph/event/observation,
  replay-state, and reference-integrity records in the same CAS as the typed
  group result.
- Built-in recovery performs found-first predecessor authority reload before a
  new snapshot or authority publication; lease reclaim preserves exact request
  and group identity.
- Direct, factory, filesystem, and Hermes normal signatures do not accept
  `bootstrap_graph_host_bundle_builder`.  Production executes the concrete
  `BootstrapGraphHostBundle`; scenario authority injection is confined to
  `ProviderMemoryService._from_scenario_test_host` and the distinct scenario
  bundle with scenario trust-domain verification.
- Default no-injection lease-reclaim and terminal acknowledgement-loss matrices
  pass across all four roots in memory and independent JSONL.
- The v78 correctness and test remediation reviews found no remaining P1/P2 or
  required evidence gap.  The v78 specification review stopped solely because
  this resume packet and the parent index still described the superseded
  August 9 pause; v79 corrected the active index/resume and v80 also aligns the
  active implementation packet's exact next action.

## Evidence

- Accepted effect visibility and exact repeat: `1 passed in 137.26s`.
- Native atomic store focused suite: `3 passed in 4.40s`.
- Production signature and four-root default composition proof:
  `5 passed in 23.75s`.
- Private scenario terminal regression: `1 passed in 166.93s`.
- Scenario/production trust isolation: `1 passed in 13.75s`.
- Lease reclaim: all four roots passed in memory and independent JSONL.
- Terminal acknowledgement loss: all four roots passed in memory and
  independent JSONL with exact terminal identities and one group primary.
- Selector manifest tests: `11 passed in 5.45s`; the exact manifest validator
  passed.
- Scoped Ruff, bytecode compilation, JSON parsing, and diff hygiene pass.

## Remaining Review State

- `remaining_validated_p1_p2`: `[]`
- `remaining_changes_required`: `[]`
- `remaining_blocks_approval`: `[]` after the approved v80 specification delta.
- Hosted GitHub execution evidence remains unavailable until a reviewable
  revision is pushed; local workflow-equivalent evidence is the current proof.

## Exact Next Action

M3.1 is complete.  The v81 final branch-gate disposition was recorded
2026-09-04 at HEAD `bd1ebf0`: 8/11 pinned artifacts match byte-for-byte, the
three drifted artifacts (selector path re-point from the L1a split,
unrelated workflow jobs, and the repaired design renumbering cascade) were
dispositioned as non-semantic, and the targeted delta gates passed
(selector 11, static tooling 18, identity hygiene 150).  The next operation
is the M4 completion plan at
`docs/work/semantic_ingestion/m4-closure-2026-09-04/implementation.plan.md`,
which resumes the linked debug at clarification-winner replan and proceeds to
the provider/factory/cache/Hermes conflict-attention composition slice.

## Historical Navigation

Pre-split M0--M3 history and the superseded August 9 pause are preserved under
`docs/work/semantic_ingestion/history/` and the linked milestone/debug/design
WorkPlans.  They are historical evidence, not the active resume state.
