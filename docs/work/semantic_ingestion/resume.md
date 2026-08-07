# Semantic Ingestion M4 Resume Packet

- Active WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Active milestone: `docs/work/semantic_ingestion/milestones/m3-semantic-pipeline.plan.md`
- Blocked linked operation: `docs/work/semantic_ingestion/conflict-authority-proof-failures-2026-08-04/debug.plan.md`
- Status: active; strict preparation/catalog/request contract cutover and adversarial closure proof in progress
- Coordinator: Codex main thread
- Last updated: 2026-08-05
- Git HEAD: `2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93`
- Tree state: dirty; preserve all existing changes and record a fresh identity before review
- Historical WorkPlan: `docs/work/semantic_ingestion/history/implementation-through-2026-08-04.md`
- Historical SHA-256: `eace351ffa26f42b707328e8a0a0a38206c8ba62d8f2603b90853116054a4a20`
- Coordination candidate identity: `docs/work/semantic_ingestion/history/implementation-split-review-identity.json`

## Authority

- `docs/design/memorii_spec.md`
- `docs/design/memorii_storage_details.md`
- `docs/design/event_model.md`
- `docs/design/conflict_attention.md`
- `docs/design/semantic_ingestion_architecture.md`
- `docs/design/equal_version_replay_decision-v1.json`
- Approved conflict-attention design SHA-256: `0b5a8a9246fb3d0d2cf18d0589d3b412778f0caa167bac331c3ae9a7b7ec1a68`
- Approved semantic-ingestion design SHA-256: `495e3c5cd95ca68eb2f3bca5c47870092c148d785fc57688127e9802ba93ddae`

## Current Objective

Finish the complete approved M3 contract and runtime realization, including
strict preparation identity, source-wide parent/child text coordinates,
proposal execution/persistence, Step-4/normalization joins, and the previously
identified plan-lineage gap. Then resume M4 clarification-winner replan and
provider/factory/cache/Hermes composition.

## Current Scope

The linked debugging operation owns:

- canonical clarification submission, claim, completion, and supersession in
  the memory plane
- both deterministic projection-versus-clarification winner orders
- the exact 12-case reproducer and focused sibling proof
- only production changes causally required by those failures

It excludes provider/factory/Hermes composition, derived cache/composite
listing, CI timing reconciliation, broad M4 gates, and whole-branch review.

## Completed Relevant Behavior

- The user approved fail-closed equal-version replay conflict handling.
- Semantic-conflict introduction authority is owned by the same semantic
  memory-plane conditional write as the contested projection.
- The file conflict ledger is a recoverable listing and clarification
  projection, not the canonical introduction owner.
- Core projection, temporal/trust, policy-cutover, decay, terminal, replay, and
  checkpoint paths carry the typed conflict-authority binding.
- Invalid authority is preflighted before lease or planned-checkpoint mutation.
- Replay fixture sequencing and canonical introduction digest causes were
  isolated and bounded corrections were applied.
- Clarification completion now has a typed pointer/work/attempt CAS input and a
  typed `superseded` result.
- The memory plane now has a strict immutable clarification-transition type and
  replay validation for predecessor status/revision/digest, contiguous
  coordinates, and audit-only supersession. The existing projection-history
  suite remains green.
- Clarification submission now atomically binds proposal, operation receipt,
  initial work, submitted transition, pointer history/current pointer, and
  ledger head. Claim and renewal use immutable predecessor-keyed successors
  with replay-derived ownership, fenced epochs/tokens, exact retry, and strict
  persisted-wire decoding.

## Confirmed Open Work

The remaining causal gap begins after claim/renew. Failure, lease reclaim, and
attempt exhaustion now have canonical successor closures. Work, attempt, and
result artifacts are independently addressable, and a canonical builder now
constructs the typed CAS from the exact live claimed image. If the natural
projection wins, clarification records `superseded` without semantic effect or
receipt. If clarification wins, the publisher reloads and replans rather than
committing a stale pointer.

No external decision is required. Do not reopen the approved transaction-owner
decision unless new evidence contradicts a governing source.

## Debug-Owned Surface And Commands

The linked debugging WorkPlan is the sole detailed owner of this in-flight
surface, its authority chain, gates, experiments, known failures, and evidence.
The parent index and M4 packet retain only its boundary, link, compact status,
and completion dependency.

- Current files/symbols: clarification transition contracts; projection-history
  conflict replay; writer admission; atomic clarification transaction; the
  conflict repository/processor boundary; semantic adapter; and the real JSONL
  tests in `test_semantic_terminal_persistence.py`.
- Smallest existing race command: `PYTHONPATH=memorii .venv/bin/python -m pytest tests/unit/core/semantic_ingestion/test_semantic_terminal_persistence.py::test_projection_and_claimed_clarification_races_have_one_pointer_winner`.
- Required new proof: add and run deterministic barriers for both
  projection-wins and clarification-wins orders; prove one linearized outcome,
  stale-image rejection before effect/receipt, and idempotent retry.
- Required focused static commands: `.venv/bin/python -m py_compile memorii/memorii/core/memory_evolution/atomic_store.py` and `.venv/bin/ruff check memorii/memorii/core/memory_evolution/atomic_store.py memorii/tests/unit/core/semantic_ingestion/test_semantic_terminal_persistence.py`.
- Command status: the existing race is a false proof for the required semantic
  serialization; the new two-order proof is unimplemented and unrun. Earlier
  focused compile/Ruff and clarification-idempotency evidence is historical,
  not closure for this race.
- Evidence limitation: the tree is dirty and all evidence is local-only until a
  fresh candidate identity and hosted required gates are recorded.

## Exact Next Action

Remediate the eight confirmed frozen-review findings for the strict-v1
preparation/catalog/request/Step-4 contract slice at canonical design SHA-256
`495e3c5cd95ca68eb2f3bca5c47870092c148d785fc57688127e9802ba93ddae`:
request authority and canonical artifact closure; split-parent run sealing and
preparation joins; parent-aware Step-4 span closure; selected-route
certification; closed literal domains; direct codec matrices; and Unicode-
scalar topology proof. Run bounded delta reviews on the refrozen candidate.

The final candidate also carries a global post-Step-2 source-span invariant and
the exact prepared-source identity through request, attempt, proposal, analysis,
NLI, run, and normalization joins; these remain design-only pending review.

The opaque preparation policy coordinate is superseded by the persisted strict
`TextPreparationPolicy` bytes and full prepared-source content address; replay
cannot replace it with a live policy lookup or same-output configuration.

Completion evidence for this action:

- every prepared segment retains exact governance, admission, text-artifact,
  route, prompt, proposer, and request authorities
- blocked routes make no proposal request or call
- selected routes construct the full typed request/identity/final-attempt/run
  path and normalize only an exact persisted terminal response
- focused provider/pipeline tests, compile, and Ruff pass

The proposal-attempt and Step-4 contract/codec prerequisite is accepted at the
exact hashes and evidence recorded in the active M3 packet.

## Delegation Packet

- One Terra-class worker owns all overlapping production and test edits until
  the bounded acceptance criteria complete or a concrete blocker is recorded.
- Spark-class mapping or error triage may run concurrently only for distinct
  read-only questions with a direct consumer. Spark capacity is exhausted
  until 2026-08-09; until then use bounded low-reasoning Terra mapping only
  when the expected avoided coordinator work justifies it.
- Use `fork_turns: none`; this packet, the M4 milestone packet, and the linked
  debugging WorkPlan are the default context. Do not load the historical
  WorkPlan unless a named historical question requires it.
- The agent that starts a long test owns it through the terminal result.
- Do not launch the three Terra reviewers until the candidate freeze gate in
  `.agents/PLANS.md` is satisfied.

Coordination controls were validated before M4 resumed: all four modified
repository skills passed the skill validator; all seven installed agent TOML
definitions parsed; repository diff hygiene passed; and three artifact-only
Spark forward tests followed this packet without inherited-chat contamination.
Those tests independently confirmed the workflow contract, mapped the current
clarification owners, and selected the existing single-node race discriminator.

## Review And Completion Limits

After focused proof is green and the candidate is frozen, run the independent
specification, correctness, and test reviewers concurrently once. Use only the
affected reviewer roles for bounded remediation deltas. M4 is not complete
until the parent WorkPlan's full completion contract and final branch gates are
satisfied; this packet never establishes completion by itself.

## Historical Context

The full implementation WorkPlan preserves M0-M3 history, all decisions,
evidence, and review logs. Consult it only for a specific unresolved rationale
or when updating its canonical ledgers. Linked completed design and testing
plans remain authoritative for their own operation types.
