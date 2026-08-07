# Replay Conflict And Attention Design

- Work ID: semantic_ingestion_conflict_attention_replay_design
- Work type: design
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-08-02
- Last updated: 2026-08-02
- Parent WorkPlan: None
- Related WorkPlans: `docs/work/semantic_ingestion/implementation.plan.md`
- Canonical inputs: `docs/design/event_model.md`; `docs/design/semantic_ingestion_architecture.md`; user decisions recorded on 2026-08-02
- Expected outputs: `docs/design/conflict_attention.md`; corrected equal-version replay semantics in `docs/design/event_model.md`; reviewed implementation-ready baseline

## Objective

Freeze one deterministic replay-conflict algebra and one pull-based conflict-
attention contract. Implementation can then reject corrupt equal-version
history without selecting a winner, expose user-decidable semantic conflicts
through ordinary agent pulls, and keep integrity repair outside ordinary agent
authority.

## Completion Contract

This design operation is complete when:

- `docs/design/event_model.md` and the validated
  `docs/design/equal_version_replay_decision-v1.json` define byte-identical duplicate, non-identical
  equal-version, current-writer, genesis, and checkpoint-tail behavior without
  an arrival-order or event-ID winner;
- `docs/design/conflict_attention.md` defines typed, bounded, scoped pull and
  clarification contracts, including the semantic/integrity separation;
- every requirement below has measurable deterministic evidence;
- identity, changed-surface, authority-chain, and gate ledgers are reconciled;
- independent spec, correctness, and test review leaves no confirmed P1/P2,
  `blocks_approval`, or `changes_required` finding in scope; and
- the linked implementation WorkPlan can resume without hidden conversation
  context or an unresolved semantic decision.

## Scope

Included:

- exact equal-version replay classification and fail-closed behavior;
- pull-based attention for semantic conflicts requiring user clarification;
- operator-only attention for storage-integrity incidents;
- append-only clarification and repair authority boundaries;
- provider/tool compatibility, pagination, authorization, idempotency,
  concurrency, observability, and verification contracts.

Excluded:

- selecting a conflicting storage event by timestamp, event ID, or arrival;
- making a model response an authenticated user clarification;
- a Hermes callback or proactive push channel;
- the complete event reducer, checkpoint implementation, policy migration,
  trust scheduler, or identity-lineage implementation.

Deferred:

- host-specific UI rendering beyond the provider text/typed contract;
- privileged operator repair commands and clean-generation rebuild mechanics;
- notification leases or cross-session reminder suppression.

## Constraints And Invariants

- Governing-source precedence follows root `AGENTS.md`.
- Exact duplicate delivery is idempotent; divergent equal-version bytes are
  corruption, not a factual tie.
- Candidate semantic state remains distinct from committed truth.
- Raw source and historical events remain immutable.
- Clarification appends evidence; it never edits or deletes prior events.
- A model cannot promote its own interpretation to a user decision.
- Authorization is checked before conflict or candidate content is read.
- An affected replay scope fails closed before any winner or partial projection
  becomes visible.
- Unrelated safely isolated scopes may remain available.

## Problem Definition

Hermes and similar harnesses call Memorii, but Memorii cannot push a message
back later. Today an unresolved semantic conflict can remain hidden from the
agent, while the canonical event model also contains contradictory equal-
version winner rules. The desired behavior is to piggyback bounded attention
items on ordinary pull responses, allow an agent to ask the user for semantic
clarification, and reject storage corruption without granting the agent repair
authority.

Actors are the end user, agent harness, provider adapter, Memorii retrieval and
tool services, semantic conflict owner, replay reducer, and privileged
operator. The behavior matters because silently selecting a storage winner can
change durable truth, while hiding semantic ambiguity prevents the user from
correcting memory through the only interaction channel the harness provides.

## Requirements Ledger

| ID | Requirement | Source | Priority | Acceptance criteria | Status |
| --- | --- | --- | --- | --- | --- |
| CAR-R01 | Classify exact duplicate, semantic disagreement, and storage-integrity conflict separately. | User decision; event model | Required | A closed classifier produces exactly one kind and divergent equal-version events can never enter the semantic lane. | specified |
| CAR-R02 | Reject non-identical equal-version history before winner or partial visibility at genesis and checkpoint-tail replay. | User decision; SIA-R10 | Required | Every arrival/event-ID/timestamp permutation returns the same typed integrity failure and unchanged prior state. | specified |
| CAR-R03 | Attach a typed `attention_required` page to ordinary agent tool pulls. | User decision | Required | Empty and non-empty pages validate strictly; the response includes total count, bounded items, and continuation cursor. | specified |
| CAR-R04 | Expose all authorized unresolved user conflicts through a paginated listing tool. | User decision | Required | Stable pagination returns every and only in-scope unresolved item without duplicates. | specified |
| CAR-R05 | Render user attention safely for text-only Hermes consumers. | User decision | Required | Text identifies the question, choices, conflict ID, and resolution tool without treating stored values as instructions. | specified |
| CAR-R06 | Record semantic clarification as append-only candidate evidence with exact conflict revision and idempotency binding. | User decision; Memorii invariants | Required | Retry is idempotent; stale revision or changed candidates rejects; no original source, event, claim, or contradiction record is overwritten. | specified |
| CAR-R07 | Support select-one, both-with-validity, neither, and an explicit unsure outcome that leaves the conflict open without mutation. | User Alice/Globex example | Required | Both-with-validity requires valid non-overlapping or explicitly overlapping intervals; unsure makes no resolution call and no option guesses absent dates. | specified |
| CAR-R08 | Keep integrity incidents operator-only. | User decision | Required | Agent pulls may disclose a sanitized incident and ID, but the user-resolution tool rejects the integrity kind before mutation. | specified |
| CAR-R09 | Authorize before reading conflict payloads and bind scope server-side. | Repository security invariants | Required | Missing, revoked, cross-tenant, or insufficient ingress yields non-disclosing denial and zero repository reads. | specified |
| CAR-R10 | Bound response size and make ordering deterministic. | Operational requirement | Required | Embedded pages contain at most three items; list pages default to 50 and cap at 100; order is user audience, creation coordinate, then conflict ID. | specified |
| CAR-R11 | Preserve compatibility for existing provider callers. | Existing provider contract | Required | Existing context/result fields retain meaning; additive typed fields have safe empty defaults; text output changes only when attention exists. | specified |
| CAR-R12 | Make conflict state and recovery observable without sensitive payload logging. | Operational requirement | Required | Metrics and errors expose kind, status, scope digest, and incident/conflict ID, never raw candidate text. | specified |

Requirement IDs are traceability values only and may not name production,
test, fixture, command, schema, artifact, or workflow identities.

## Non-Goals

- Automatic truth selection from newest timestamps, confidence, event IDs, or
  model preference.
- Treating ordinary conversation text as proof that the authenticated user
  authorized a repair.
- Resolving storage corruption through `memorii_resolve_conflict`.
- Sending unsolicited messages from Memorii to a host.
- Returning an unbounded global conflict dump on every pull.

## Existing-System Analysis

- `HermesMemoryProvider` is a synchronous adapter. `prefetch` returns text and
  lifecycle hooks return typed sync/write results; it has no callback channel.
- `ProviderMemoryService.prefetch_result` already owns a typed retrieval result
  and `ProviderToolCallResult` owns agent-tool responses.
- `ProviderToolDispatcher` owns existing tool schemas and dispatch.
- Memory evolution persists `ContradictionSet` records, but no provider
  attention, clarification ledger, or integrity-incident owner exists.
- Semantic ingestion M3 carriers are not canonical replay events. The M4
  reducer and incident producer remain separate implementation work.
- `docs/design/event_model.md` currently contradicts itself by naming event-ID
  precedence and arrival-first skipping for the same equal-version case.

## Canonical Contracts And Ownership

`docs/design/conflict_attention.md` owns the public/provider and persisted
attention semantics. `docs/design/event_model.md` owns the replay classifier.
The semantic-ingestion design remains the canonical owner of event and
observation reconstruction; its external decision is satisfied by the user-
approved event-model rule without changing its pinned traceability bytes.

Production behavioral owners proposed by the design:

- `memory_evolution/conflict_attention.py`: typed attention, clarification,
  authorization-independent domain logic, and repository protocol;
- `provider/models.py`: additive attention field on typed pull results;
- `provider/tools.py`, `provider/tool_schemas.py`, and
  `provider/tool_dispatch.py`: list/resolve tool contracts and thin dispatch;
- `provider/service.py`: authenticated composition and response attachment;
- `integrations/hermes_provider.py`: text-only rendering/delegation;
- future `memory_evolution/events.py`: integrity-incident production from the
  canonical replay reducer.

## Alternatives Considered

| Approach | Advantages | Disadvantages and risks | Decision |
| --- | --- | --- | --- |
| Pick newest timestamp | Simple and automatic | Clock/arrival dependent; corrupt data can become truth | rejected |
| Push callback from Memorii | Immediate user notification | Hermes has no callback contract; couples core to host | rejected |
| Put prose only in `prefetch` | Compatible with text consumers | Untyped, hard to paginate, easy to confuse with memory | rejected as sole contract |
| Typed attention plus Hermes formatter | Stable agent contract with text compatibility | Requires additive provider models and explicit auth | accepted |
| Let conversation directly repair conflict | Low friction | Model can misstate user intent; no revision binding | rejected |
| Append clarification candidate then re-run policy | Preserves provenance/history and existing validation | Resolution may remain pending until validated | accepted |

## Failure And Operational Analysis

- Missing/invalid authorization returns a non-disclosing unavailable result and
  does not inspect the conflict store.
- A stale `conflict_revision` rejects before append so the user never resolves
  a different candidate set than the one shown.
- Duplicate `operation_id` with byte-identical clarification is idempotent;
  divergent reuse rejects.
- Candidate values are data, escaped and length bounded. They are never copied
  into tool instructions or logs.
- A page cursor binds scope and ordering revision. Invalid, expired, or cross-
  scope cursors reject rather than restart silently.
- If replay detects storage corruption, it commits or emits the incident in a
  control-plane generation that does not depend on materializing the corrupt
  event. The affected scope remains unavailable.
- If an agent submits a semantic resolution for an integrity incident, the
  service returns `operator_action_required` with zero memory mutation.
- Rollback removes new readers/writers but retains appended clarifications and
  incidents. Older callers ignore additive empty fields.

## Verification Strategy

| Requirement family | Strongest proof | Failure signal |
| --- | --- | --- |
| Replay classification | Unit permutation/property tests plus JSONL restart integration | Typed conflict and byte-identical unchanged state |
| Typed attention | Model/schema tests and provider integration | Validation failure or missing/mis-scoped item |
| Pagination/order | Unit boundary/property tests | Duplicate, omission, unstable order, or cursor rejection mismatch |
| Clarification append | Store integration with retry/concurrency/stale revision | Mutation of prior bytes, duplicate append, or stale acceptance |
| Authorization/privacy | Repository-spy tests at public boundary | Any read before authorization or cross-scope disclosure |
| Hermes formatting | Adapter contract tests | Missing section, raw instruction execution, or existing-text drift when empty |
| Integrity separation | Tool and replay integration | Agent resolution mutates integrity incident or materializes winner |
| Compatibility | Existing provider/Hermes suites and package smoke | Existing result/context contract breaks |
| Identity hygiene | Field-aware gate plus representative mutations | Planning coordinate accepted in durable surface |

## Identity And Coordinate Hygiene

| Surface | Proposed or existing identity | Class | Behavioral owner or protocol meaning | Disposition | Proof |
| --- | --- | --- | --- | --- | --- |
| WorkPlan requirements | `CAR-R01` through `CAR-R12` | planning/evidence coordinate | traceability only | retain only here/design traceability | field-aware audit |
| Provider protocol | `memorii.conflict-attention.v1` | protocol identity | negotiated attention envelope | retain | old/new reader contract tests |
| Provider field | `attention_required` | behavioral identity | pending attention page inside negotiated envelope | retain | schema/model tests |
| Tool | `memorii_list_conflicts` | behavioral identity | paginated authorized listing | retain | tool schema/dispatch tests |
| Tool | `memorii_resolve_conflict` | behavioral identity | append semantic clarification candidate | retain | tool schema/dispatch tests |
| Error | `memory_integrity_conflict` | behavioral identity | divergent equal-version replay | retain | replay failure tests |
| Persisted clarification | `conflict_clarification` | behavioral identity | append-only user evidence | retain | restart/retry tests |

## Change Impact And Verification Closure

| Path or pattern | Surface class | Intended scope owner | Authority chain | Required gates | Status |
| --- | --- | --- | --- | --- | --- |
| `docs/design/event_model.md` | normative design | event-model owner | event model -> decision artifact -> replay contracts/tests | design review; diff check | in progress |
| `docs/design/conflict_attention.md` | normative design | conflict-attention owner | design -> provider/replay contracts/tests | design review; diff check | in progress |
| `docs/design/equal_version_replay_decision-v1.json` | normative decision artifact | event-model owner | bound design bytes -> validator -> replay contracts/tests | decision validator; design review | in progress |
| `docs/design/validate_equal_version_replay_decision.py` | design validator | event-model owner | decision artifact + bound bytes -> deterministic verdict | direct positive/negative execution | in progress |
| this WorkPlan | design governance | coordinator | user decision -> design baseline | direct inspection; diff check | in progress |

The semantic-ingestion architecture bytes changed in the linked replay and
projection closure to record the resolved decision register and complete
projection migration/history contracts. The traceability registry, structural
manifest, frozen vectors, checksums, and workflow pins remain unchanged. The
registered replay-decision condition is satisfied by the governing event-model
decision and bound artifact.

Gate ledger for this design operation:

| Job or gate | Exact local command | Changed surfaces | Required | Result |
| --- | --- | --- | --- | --- |
| Diff validation | `git diff --check` | all design files | yes | passed before review; rerun after remediation |
| Identity hygiene | `../.venv/bin/python -m memorii.tools.identity_hygiene --root .. --allowlist ../.agents/identity_hygiene_allowlist.json` from `memorii/` | durable names | yes | passed before review; rerun after remediation |
| Replay decision binding | `.venv/bin/python docs/design/validate_equal_version_replay_decision.py docs/design/equal_version_replay_decision-v1.json --repository-root .` | decision artifact and three bound documents | yes | passed, including negative mutation probe |
| Independent design review | three standard reviewers | complete design scope | yes | approved after closure checks |

### Pre-implementation validation matrix

| Behavior | Test owner and level | Defect detected | Observable failure | Gate and runtime placement |
| --- | --- | --- | --- | --- |
| Strict attention, option, interval, proposal, receipt-proof, and envelope models | `memorii/tests/unit/core/test_conflict_attention.py` | malformed or open-ended wire/state language | exact Pydantic validation error before repository access | deterministic unit shards; measure every node in timing manifest |
| Frozen replay-decision validator and every mutation family | `memorii/tests/unit/tools/test_equal_version_replay_decision.py` | changed rule/evidence ordering/document binding/schema key/type accepted | pristine artifact passes; each single-field, missing/extra-key, wrong-type, evidence member/order, path/digest, and decision-digest mutation fails | new 5-minute `equal-version-replay-decision` PR job; add it to the `unit-tests` aggregate dependencies |
| Exact duplicate versus semantic versus integrity classification | `memorii/tests/unit/core/semantic_ingestion/test_event_replay.py` | corruption treated as retry or semantic choice | typed integrity error and unchanged reducer state | semantic-ingestion generation job plus unit shard |
| Generic event/batch to semantic-profile conformance | replay contract unit owner above | schema ID alias, event/event-batch digest alias, repository mismatch, zero sequence, or incoherent derived offset | strict conformance rejection before reducer access | semantic-ingestion generation job plus unit shard |
| Divergent create and every event-ID, dedupe-key, and record-version binding | replay unit/integration owners above | same version accepted through a non-primary identity | one typed integrity error and unchanged state/indexes/position | generation job plus integration file |
| Same logical mutation retry before and after restart | replay unit/integration owners above | retry allocates a second event ID/batch position or diverges indexes | identical returned envelope/position, one committed event/batch, and byte-identical indexes/state; changed mutation digest rejects | generation job plus real JSONL integration |
| Arrival/event-ID/timestamp and genesis/checkpoint-tail permutations | `memorii/tests/unit/core/semantic_ingestion/test_event_replay.py` and `memorii/tests/integration/test_semantic_ingestion_replay.py` | order-dependent winner or partial visibility | byte-identical prior state/position and same incident | generation job; integration file added explicitly; collection lock repinned |
| Complete prefix, arbitrary midpoint, batch gap/duplicate/cross-repository/incomplete offsets/digest mismatch | replay unit/integration owners above | partial or discontinuous batch visibility | whole batch rejected and prior state/indexes/position unchanged | generation job plus integration file |
| Historical upcast, mixed-schema equal-version, future, and retired-without-upcaster events | replay unit/integration owners above | incomparable envelopes treated as duplicates or winners | deterministic upcast comparison or typed schema/integrity rejection | generation job plus compatibility job |
| Empty/three/overflow attention and snapshot pagination under concurrent changes | `memorii/tests/unit/core/test_conflict_attention.py` | omission, duplication, unstable order, mutable snapshot | exact snapshot-relative IDs/count and typed cursor rejection | deterministic unit shards with measured timing |
| Authorization before attention read | `memorii/tests/unit/core/test_provider_tools.py` and `memorii/tests/integration/test_conflict_attention_persistence.py` | forged scope or payload read before denial | repository spy remains at zero reads | unit shard plus generation integration job |
| Hermes canonical untrusted-data rendering | `memorii/tests/unit/integrations/test_hermes_conflict_attention.py` | newline, delimiter, Markdown fence, or tool-like stored text alters instruction grammar; empty response drifts | exact JSON-string escaping including `<`, `>`, backtick, and `&`; byte-identical legacy text when empty | deterministic unit shard |
| Clarification actions, cited user turn, and optional confirmation receipt | `memorii/tests/unit/core/test_conflict_attention.py` | model attributed as user or invalid interval/cardinality accepted | typed denial and zero append | deterministic unit shard |
| Explicit unsure host response | provider/Hermes unit owners above | unsure becomes an invented resolution action or hidden write | tool schema rejects `unsure`; submit, receipt consumption, operation/proposal/transition append are never called; `total_pending` is unchanged | deterministic unit shard with repository/receipt spies |
| CAS, exact/divergent retry, two-writer race, interruption, and reopen | `memorii/tests/integration/test_conflict_attention_persistence.py` | duplicate evidence or stuck/ambiguous state | exactly one transition/proposal and deterministic restart state | generation integration job; real JSONL store |
| Clarification claim, crash, lease reclaim, stale owner, exhaustion, restart, and fresh clarification | conflict-attention unit/integration owners above | stuck submitted conflict or reset retry budget | exact attempt ledger and reopen after third retryable failure | unit shard plus real JSONL integration |
| Confirmation expiry, replay, and two-operation nonce race | conflict-attention unit/integration owners above | forged or multiply consumed user attribution | typed rejection and exactly one possible nonce consumption | unit shard plus real JSONL integration |
| Integrity resolution rejection | unit and replay integration owners above | ordinary agent repairs corruption | `operator_action_required` and zero mutation | unit plus generation integration job |
| Legacy/new compatibility | `memorii/tests/unit/core/semantic_ingestion/test_provider_compatibility.py` | strict legacy reader receives new envelope | exact frozen old/new serialized fixtures | append this exact file to the `provider-compatibility` job argv; retain its 15-minute timeout after measured execution |
| Redacted observability | `memorii/tests/unit/core/test_conflict_attention.py` | question/candidate leaks to logs or metrics | captured output contains identifiers but no payload text | deterministic unit shard |
| Rollout enable, append, disable, and re-enable | provider and persistence owners above | rollback reads/deletes ledger or loses exact state | disabled reads/submissions with byte-identical retained reconstruction | unit shard plus real JSONL integration |
| Host delivery | external `host-integration-certification` owner | authenticated attention never reaches intended user | signed `ConflictAttentionHostDeliveryEvidence.v1` binds host build, protocol, hashed tenant/principal, test conflict ID, pull/render/user-ack coordinates, and evidence digest | deployment certification gate; required for host-delivery claims, explicitly outside library PR approval |

The implementation WorkPlan must read the current workflow directly before
editing it, record before/after collection counts and measured runtime, and
avoid creating a new broad gate when an existing explicit generation or
compatibility owner can carry the unique failure signal.

The implementation changes the `semantic-ingestion-generation` job's collect
and run argv by adding exactly
`tests/integration/test_semantic_ingestion_replay.py` and
`tests/integration/test_conflict_attention_persistence.py`, then repins its
exact collection count from observed output. It records measured combined
runtime against the existing 15-minute budget and raises that timeout only with
evidence. Every new unit node is measured into `tests/ci/unit-test-durations.json`
and verified through all four deterministic shard runs. The standalone
`equal-version-replay-decision` job installs only pytest, runs the validator
test with `-W error -p no:cacheprovider`, and is added to the `unit-tests`
aggregate `needs` and success check so it cannot be skipped by a green shard.

Known failures: none at baseline. Baseline revision is
`2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93` on branch
`semantic-indexing-m4` with a clean tree.

## Sources Of Truth

Precedence:

1. `docs/design/memorii_spec.md`
2. `docs/design/memorii_storage_details.md`
3. `docs/design/event_model.md`
4. `docs/IMPLEMENTATION_RULES.md`
5. `docs/design/semantic_ingestion_architecture.md`
6. `docs/design/conflict_attention.md`
7. linked WorkPlans

The user's 2026-08-02 decisions provide external authority for fail-closed
equal-version handling and pull-based user attention. The design records those
decisions; it does not rely on chat history after completion.

## Current State

Verified facts:

- The branch is clean at the recorded baseline.
- Hermes has no callback path.
- Provider tool results and typed prefetch results are existing additive
  extension points.
- Contradiction sets exist; clarification and replay-integrity incident owners
  do not.
- The historical equal-version inconsistency is resolved by the frozen
  fail-closed decision artifact and reconciled event-model rules.

Interpretation:

- A typed attention page can be added compatibly.
- Integrity incident production depends on the M4 replay slice, but its public
  lane and authority restriction can be implemented first.

## Assumptions And Open Questions

Verified facts: listed under Current State.

Working assumptions:

- Legacy contradiction records without authenticated tenant and scope
  provenance are not public attention producers.
- A host can pass authenticated ingress out of band when invoking Memorii
  tools; authentication is never accepted from tool JSON arguments.

Unresolved questions: none that change the specified first slice.

External decisions: resolved by the user on 2026-08-02.

## Milestones Or Experiments

### Freeze replay and attention contracts

- Purpose: eliminate the governing ambiguity and specify the pull workflow.
- Bounded scope: the two design documents and this WorkPlan.
- Expected artifacts: corrected event model and conflict-attention design.
- Verification: diff/identity checks and three independent reviews.
- Status: complete.

## Progress Log

- 2026-08-02: Reconstructed the Hermes/provider pull path, confirmed absence of
  callbacks, and classified semantic versus integrity conflicts. Next action
  was to draft the governing contracts.
- 2026-08-02: User selected fail-closed equal-version handling and pull-based
  user attention. This removed the external semantic decision.
- 2026-08-02: Two bounded remediation passes closed event/profile ownership,
  replay batch atomicity and identity indexes, authenticated clarification,
  receipt nonce safety, retry exhaustion, snapshot pagination, strict schemas,
  Hermes untrusted-data encoding, rollout rollback, and executable gate
  ownership. Three independent closure checks found no residual blocker.

## Evidence Log

- `memorii/memorii/integrations/hermes_provider.py`: synchronous adapter only.
- `memorii/memorii/core/provider/models.py`: existing typed prefetch result.
- `memorii/memorii/core/provider/tools.py`: existing typed tool result.
- `memorii/memorii/core/memory_evolution/models.py`: persisted contradiction
  sets.
- `docs/design/event_model.md` Sections 8-10: conflicting winner rules.
- Readiness reports from code mapper, spec auditor, and test reviewer are
  recorded in `docs/work/semantic_ingestion/implementation.plan.md`.

## Decision Log

- Decision: divergent equal-version events fail closed; no timestamp, event-ID,
  or arrival-order winner. Date: 2026-08-02. Alternatives: newest timestamp,
  event-ID ordering, first arrival. Rationale: deterministic safety and no
  silent corruption repair. Owner: user/event-model owner.
- Decision: surface user-decidable conflicts on subsequent pulls. Date:
  2026-08-02. Alternative: proactive callback. Rationale: Hermes is pull-only.
  Owner: user/product owner.
- Decision: ordinary agents cannot resolve storage integrity incidents. Date:
  2026-08-02. Alternative: expose candidate selection. Rationale: repair is a
  privileged storage operation, not truth clarification. Owner: user/product
  owner.

## Review Log

### Full design review

Reviewers: `spec_auditor`, `correctness_reviewer`, and `test_reviewer`.
Scope: the complete event-model/conflict-attention draft, current provider and
storage boundaries, the semantic-ingestion external-decision register, tests,
workflows, and this WorkPlan.

Confirmed findings and coordinator dispositions:

- Missing governing replay decision artifact: `Not applicable /
  changes_required / governance`, `contract_conformance_action`. Confirmed and
  resolved by the closed JSON artifact, bound document digests, and validator.
- Replay envelope, identity indexes, canonical bytes, and checkpoint position
  were underdefined: `Not applicable / changes_required / architecture`.
  Confirmed and resolved by distinct event/dedupe/record identity, canonical
  typed-value digest, repository batch positions, atomic indexes, and complete
  checkpoint bindings.
- Public attention APIs could not enforce authorization-before-read:
  correctness reviewer classified the affected authenticated pull scenario as
  `P2 / changes_required / security`; spec reviewer classified the design gap
  `Not applicable / changes_required`. Confirmed. The design now keeps legacy
  methods unchanged and defines attention-aware methods with out-of-band
  authenticated ingress resolved exactly once before repository access.
- Agent tool calls could be forged as direct user evidence: `P1 /
  changes_required / security`, `eligible_p1_p2`. Confirmed. The ordinary
  Hermes path now writes an agent-interpreted proposal tied to a retained user
  turn and cannot commit truth; direct user attribution requires a one-time
  action-bound host confirmation receipt.
- Clarification lifecycle lacked a linearizable transaction: `P2 /
  changes_required / concurrency`. Confirmed and resolved by an append-only
  ledger, exact revision preimage, operation receipt, one CAS generation, and
  closed validation successor states.
- Revision-bound cursor could starve complete pagination: `P2 /
  changes_required / availability`. Confirmed and resolved by a retained
  as-of-watermark snapshot and signed keyset cursor; totals are snapshot-
  relative.
- Additive strict-model compatibility claim was false: `P2 /
  changes_required / compatibility`. Confirmed and resolved by separate
  negotiated/versioned envelopes and unchanged legacy result types.
- Requirement-to-test-to-gate detail was incomplete: `Not applicable /
  changes_required / verification`. Confirmed and resolved by the executable
  pre-implementation matrix with owners, levels, failure signals, and gate
  placement.
- Remaining reports that no implementation/tests currently exist are valid
  implementation evidence gaps, not design defects. They are preserved in the
  implementation validation matrix and cannot be used to claim M4 behavior.
- Existing small in-memory replay tests using wall-clock time: `Not applicable
  / follow_up / test quality`. Recorded; they are not accepted as M4 evidence.

Remediation validation at this completed WorkPlan's historical closure bytes:

- event model SHA-256:
  `9ce93e4a826f3e47b2e41fa06d2ec1e40bb0cad2475fa0527d9bb2c9ab3acdec`;
- conflict-attention design SHA-256:
  `b7cbc4f02e7b0f2b7e429c32874817ffbc71bb44c6a3e47149c4854c7f3029ea`;
- replay decision artifact SHA-256:
  `ccab22ccccbdab658a3555e9d8eb652b0c24e9ac6041a0b984768a7beb6ac3ea`;
- validator SHA-256:
  `41a50fa6847a5c96704536521842761b3400c79fb8e75096193c87b72d480262`;
- semantic-ingestion design remains byte-identical at
  `2923340bc6417d516983714e5fe69b7bab0f2257652d28a043cfb273b53aaed3`;
- decision validator, negative mutations for all nine normative fields and
  three document bindings, `git diff --check`, and field-aware identity hygiene
  all exit 0.

These hashes are retained as historical evidence, not current authority. The
linked `remaining-replay-projection-contract-closure.design.plan.md` supersedes
the semantic architecture, conflict-attention, and replay-decision artifact
bytes for implementation; its final authority pins must be used when M4
resumes.

### Targeted delta and closure review

- The spec auditor's generic-versus-semantic event ownership finding was
  confirmed and resolved by one base `event_digest`, batch-owned positive log
  sequence, tuple-derived offsets, registered semantic specializations, and
  strict conformance proof. Closure: resolved, no residual blocker.
- The correctness reviewer's Hermes prompt-data finding was confirmed and
  resolved by exact JSON-string encoding, mandatory delimiter/fence escaping,
  a fixed untrusted-data grammar, and mutation tests. Closure: resolved, no
  residual blocker.
- The test reviewer's validator, logical retry, unsure/no-call, and gate-owner
  findings were confirmed and resolved in the executable validation matrix.
  Closure: all four resolved, no residual blocker.
- All reviewer dispositions are reconciled; unsupported or deferred P1/P2
  findings: none.

### Implementation-feasibility amendment

The first implementation review proved that the existing nested legacy result
models are intentionally neither strict nor deeply frozen. The design's phrase
"unchanged strict legacy models" was therefore false and conflicted with the
compatibility requirement. The correction preserves those legacy models and
methods byte-for-byte while making the new envelope accept only validated
instances, deep-copy them, and serialize an immutable construction-time wire
snapshot. The bound decision artifact was rebased to this clarified design.

The same review found that ordinary JSON parsing admitted duplicate keys in the
decision artifact. The validator now rejects duplicates recursively before
semantic validation. Spec, correctness, and test closure reviews confirmed both
corrections with no residual blocker.

## Blockers And Limits

- Current blockers: none.
- Review/remediation budget: one full design review and at most two bounded
  remediation passes.
- Environment limits: hosted CI and operational Hermes evidence are not local
  design evidence.

## Next Action

None; the design operation is complete. Resume the linked implementation
WorkPlan at the frozen decision and design hashes above.

## Outcome And Retrospective

Approved for implementation after one full review, two bounded remediation
passes, and three independent closure checks. The design avoids the M3 failure
mode of coding against ambiguous persisted semantics: generic log envelopes,
semantic event payloads, conflict attention, and host authority now have one
owner each, and every material failure family has an explicit proof owner.
