# Semantic Ingestion Architecture Implementation

- Work ID: semantic_ingestion
- Work type: implementation
- Status: active
- Coordinator: Codex main thread
- Created: 2026-07-27
- Last updated: 2026-08-04
- Parent WorkPlan: None
- Related WorkPlans: `docs/work/semantic_ingestion/semantic-conflict-introduction-authority-2026-08-04/design.plan.md`; `docs/work/semantic_ingestion/debug-trust-decay-cutover.plan.md`; `docs/work/semantic_ingestion/testing.plan.md`; `docs/work/semantic_ingestion/m0a-trust-artifact-closure-2026-07-28/design.plan.md`; `docs/work/semantic_ingestion/m0a-c2-layer1-ctv-bindings-2026-07-28/design.plan.md`; `docs/work/semantic_ingestion/layer1-validator-collection-closure-2026-07-29/design.plan.md`; `docs/work/semantic_ingestion/layer1-validator-unicode-map-closure-2026-07-29/design.plan.md`; `docs/work/semantic_ingestion/layer1-heading-default-closure-2026-07-29/design.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md`; `docs/design/event_model.md`; `docs/design/conflict_attention.md`; `docs/design/equal_version_replay_decision-v1.json`
- Expected outputs: production implementation, deterministic verification, current-state documentation, and immutable reports under `docs/reviews/semantic_ingestion/`
- Current resume packet: `docs/work/semantic_ingestion/resume.md`

## Current Exact Next Action

Complete the linked
`conflict-authority-proof-failures-2026-08-04` debugging operation, then resume
the canonical conflict authority implementation at the provider/factory/cache
composition slice. Preserve one atomic owner; do not add an after-commit
conflict-file append.

New coordinators and delegates must begin with
`docs/work/semantic_ingestion/resume.md`. This full WorkPlan remains the
canonical historical log and should be loaded only for a named historical
question or when updating its required ledgers.

### Coordination Efficiency Gate (2026-08-04)

Before resuming product edits, the coordinator added the resume-packet,
artifact-only task-packet, writer-completion, command-ownership, and frozen-
candidate review contracts to `.agents/PLANS.md`; linked all four long-running
workflow skills to that shared contract; and installed matching global worker,
Spark read-only, and Terra reviewer instructions without changing model tiers.

| Task | Role/tier | Result | Status |
| --- | --- | --- | --- |
| Contract consistency forward test | explorer / Spark-class | no contradictions or missing enforceable fields | complete |
| Current clarification ownership map | code-mapper / Spark-class | provider, repository, atomic-store, admission, and test owners identified | complete |
| Smallest current race discriminator | error-detective / Spark-class | existing single-node race test identified; deterministic per-order proof remains required | complete |

All modified repository skills and installed TOML definitions validated, and
repository diff hygiene passed. The next product action remains the linked
debugging WorkPlan's same-plane clarification lifecycle correction.

### Authority Slice Progress (2026-08-04)

The core authority writer added the strict canonical conflict authority input,
typed same-store introduction/pointer preparation, mandatory request plumbing,
and the v2 replay aggregate/checkpoint binding with a v1 empty-authority read
path. The ordinary projection, policy-cutover, and scheduled trust-decay
constructors now pass an explicit canonical empty input until their host-owned
resolver path prepares a nonempty authority closure. Focused static checks and
the projection-history selector passed; replay selector output was incomplete
in the local command capture and remains to be rerun after the full closure.


## M4 Semantic Conflict Introduction Blocker (2026-08-04)

Final whole-branch correctness review confirmed one M4 product gap. Production
projection publication can durably produce `outcome="contested"` temporal and
trust records, and Provider/Hermes can list and resolve a conflict already in
the conflict-attention repository, but no production path constructs and
publishes the corresponding `semantic_disagreement` attention. Only tests and
manual callers invoke `FileConflictAttentionRepository.append_open`. The
ordinary end-user clarification path is therefore unreachable for a real
semantic contest.

- Product priority: `P2`.
- Approval disposition: `changes_required`.
- Finding type: runtime behavior and transactional consistency.
- Affected scenario: two valid observations remain incomparable under the
  active trust/temporal policy. Memorii retains a contested projection, but the
  next Hermes pull contains no question for the user.
- Evidence: `ProjectionHistoryRepository` prepares the contested temporal and
  trust projections inside `SemanticIngestionAtomicStore`'s conditional
  memory-plane write. Repository-wide construction search finds no production
  `ConflictAttention(kind=semantic_disagreement)` and no production
  `append_open` caller. The filesystem and provider factories also do not
  configure the conflict repository for ordinary composition.

The governing conflict-attention design defines the immutable introduction,
candidate-revision binding, scope, display, listing, and clarification
semantics, but it does not assign the introduction to a durable transaction
owner. The deployed conflict ledger is a separate JSONL file. Calling it after
the semantic commit can orphan a committed contest on crash; calling it before
the semantic commit can expose a contest whose source transaction never
committed. This missing persisted boundary is
`Not applicable / blocks_approval / architecture`, because choosing it changes
the canonical persisted authority and crash-recovery protocol.

The coordinator recommendation is:

1. persist a strict canonical semantic-conflict introduction in the same
   memory-plane conditional write as the contested projection;
2. make the file conflict ledger a recoverable materialized listing and
   clarification projection of that same-store authority, never the canonical
   introduction owner;
3. coalesce temporal and trust contest evidence for the same semantic slot and
   candidate set into one user question whose revision binds both projection
   digests;
4. require a host-owned resolver to supply authorized scopes and bounded safe
   display text from persisted provenance; unavailable authority fails closed
   rather than guessing.

Alternative resolution was to extend the filesystem transaction substrate
with one recoverable cross-file journal that atomically owns both authorities.
The user approved the recommended same-store authority on 2026-08-04. A plain
best-effort or retrying post-commit append remains rejected. The linked design
WorkPlan is completed and independently approved on exact canonical design
SHA-256 values `0b5a8a9246fb3d0d2cf18d0589d3b412778f0caa167bac331c3ae9a7b7ec1a68`
and `7391e4f0ee09888ad6ea15d074b6fc349477c6a661a56c41d174e32cde4a5e80`.
Its final bound-artifact validation included a clean three-role delta review
and `279 passed` focused CTV/compiler mutation tests in 329.33 seconds.

Current implementation closure arrays pending design and remediation:

- `remaining_validated_p1_p2: [semantic-conflict-introduction-unreachable]`
- `remaining_blocks_approval: [semantic-conflict-introduction-authority]`
- `remaining_changes_required: [semantic-conflict-introduction-unreachable]`

### Final-gate evidence before the design correction

The current dirty candidate completed the planned deterministic local gate
matrix before this blocker was recorded:

- seven terminal-persistence shards passed `156/156`; their common plan digest
  is `73fe12b5a3757522bf2e42dcb428aa8726a7a5f56b6560ba2845c6fb08c96bbe`,
  and the CI-shaped merge proved 156 unique planned nodes with no gaps,
  duplicates, or failed artifact;
- semantic generation integration passed `34/34`, provider compatibility
  passed `14/14`, projection history passed `84/84`, and public SIA acceptance
  passed `197/197` in 1,303.55 seconds;
- frozen replay-decision validation passed `30/30`; the combined CTV compiler,
  CTV PR-gate, generation-closure, and scenario-authority selector passed
  `327/327`; all three hermetic exact CTV authority checkers passed;
- benchmark contracts passed `311/311`; isolated wheel build/install, package
  imports, removed-module checks, dry-run evaluation, and artifact validation
  passed;
- repository Ruff, behavioral identity hygiene, configured Pyright (`0 errors,
  0 warnings, 0 informations`), and `git diff --check` passed.

Final test review also required a complete equal-version conflict permutation
proof. The test-only remediation now covers seven arrival/timestamp/event-ID
orders at genesis and signed checkpoint-tail replay, real file append/reopen
zero-change rejection, exact duplicate retry after restart, and divergent
same-dedupe rejection. Its warning-strict focused selector passed `10/10`;
Ruff and unit-shard verification passed, and every added node has a measured
duration in the canonical inventory. No product defect was exposed by this
stronger proof.

These are local results from the dirty tree at Git HEAD
`2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93`. They are not clean-revision or
hosted GitHub CI certification. Final whole-branch approval remains blocked by
the semantic-conflict introduction authority above, so no M4 administrative
completion is claimed.

## Delegation And Cost Ledger

This ledger supersedes the earlier practice of leaving useful read-only slots
idle while the coordinator performed repository mapping, test triage, or
long-command polling.

| Phase | Bounded task | Role and model tier | Writer or read-only | Why this tier | Output or evidence | Status |
| ----- | ------------ | ------------------- | ------------------- | ------------- | ------------------ | ------ |
| implementation | Complete the remaining reference-only post-cutover proof and any directly required product correction | worker, Terra-class | sole writer | Persisted temporal semantics and transaction boundaries need high-judgment mutation | focused tests and changed-surface report | ready to resume |
| implementation | Map affected call paths and sibling bypasses before each coherent edit batch | code-mapper, Spark-class | read-only | Fast bounded repository tracing does not need reviewer-level reasoning | owning paths, symbols, and unresolved branches | required in parallel |
| verification | Triage failures and choose the smallest discriminating command | error-detective, Spark-class | read-only | Fast evidence reduction avoids repeated broad-suite execution | ranked cause, focused command, and result | required in parallel |
| verification | Reconcile workflow selectors, counts, durations, and duplicate ownership | explorer, Spark-class | read-only | Mechanical CI topology inventory belongs in the linked testing operation | `docs/work/semantic_ingestion/testing.plan.md` evidence | handed off |
| coherent milestone review | Audit requirements, correctness, and proof coverage concurrently | spec_auditor, correctness_reviewer, test_reviewer; Terra-class | read-only | Independent semantic judgment is required only at a coherent review boundary | classified findings tied to the candidate revision | pending candidate |
| graph/identity implementation | Complete canonical graph authority, lineage semantics, atomic reservations, replay, and focused proof | worker, Terra-class | sole writer | Persisted identity and transaction semantics require coherent high-judgment mutation | 25 focused + 10 smoke, Ruff, scoped Pyright | complete |
| graph/identity review | Audit the complete focused-green milestone concurrently | spec_auditor, correctness_reviewer, test_reviewer; Terra-class | read-only | Independent approval judgment at a coherent boundary | classified findings | in progress |
| graph/identity remediation | Converge persisted planning, authority, closure, concurrency, audit, and commit-time materialization contracts | worker, Terra-class | sole writer | Cross-layer persisted semantics required one coherent owner | targeted spec/correctness/test deltas; 95 core + targeted durability evidence | complete |
| test/CI topology | Remove duplicate required-job ownership and refresh pins/timings/aggregation | worker, Terra-class | sole writer | Workflow/timing artifacts require coherent mutation after Spark inventory | linked testing WorkPlan | in progress |

The coordinator owns the WorkPlan, decisions, evidence reconciliation, and
completion judgment. It does not duplicate delegated read-heavy exploration.
Exactly one agent owns each long-running command and reports only material
transitions and final evidence. Full review runs once per coherent milestone;
bounded remediation receives targeted delta review.

### M4 Temporal And Policy Review Reconciliation (2026-08-03)

The coherent temporal/policy slice review ran specification, correctness, and
test passes concurrently, with an independent Spark evidence audit.

- The dedicated reference-only false-to-true cutover/write/restart proof passes.
  A misplaced copy of its precondition in an asserted-interval sibling test was
  removed; both exact nodes then passed in 117.62 seconds and Ruff passed.
- Correctness review found no P1/P2 product defect. Normal publication compares
  the terminal policy bundle with active projection authority, cutover advances
  the writer epoch through CAS, and stale pre-cutover publication fails closed.
- The test review's three P2 labels are reclassified because missing proof alone
  does not demonstrate broken product behavior. They are `Not applicable /`
  `changes_required / verification`, remediation eligibility `evidence_action`:
  strengthen assertion-level normal-ingress proof; add temporal unavailable,
  race, rollback, and lost-ack parity; and prove scheduled-decay membership and
  serialization with trust cutover.
- These evidence actions form one bounded test-only remediation batch. Any test
  that exposes wrong production behavior stops the batch and returns the defect
  for product-impact classification before production code changes.

Current exact evidence: 14 projection-history nodes, 11 scheduler nodes, and 17
policy-migration nodes collected on dirty HEAD
`2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93`. Dirty-tree results remain
diagnostic until revision-bound closure.

The linked trust-decay cutover debugging operation is complete. Its original
P2 and follow-up pre-persistence validation defect are fixed. Targeted spec,
correctness, and test review report no remaining required finding. The temporal
slice now includes active-policy assertion identity, unavailable-slot behavior,
A-to-B-to-A immutable history, lost-ack recovery, scheduled-decay membership,
tamper and membership mutation, both decay/cutover race orders, literal retry,
and JSONL reopen proof. The next product slice is identity lineage.

### M4 Identity Lineage Validation Matrix (2026-08-03)

The current code preserves immutable assertion provenance fields and carrier
bytes but lacks a typed lineage transition/disposition algebra, resolver,
closure validation, and lineage-aware agent read. The approved implementation
and proof boundary is:

| Contract | Required implementation | Strongest proof and failure signal |
| -------- | ----------------------- | ---------------------------------- |
| alias | preserve canonical identity, add source-grounded name, rewrite zero references | typed unit/mutation; invalid arity or disposition fails closed |
| rekey | one predecessor to one successor, preserve logical ID | resolver plus atomic-store current/historical proof |
| merge | many predecessors to one new logical ID | complete reverse closure; type/arity/cycle rejection |
| split | one predecessor to multiple new logical IDs, explicit assignment only | no default fan-out; omitted/extraneous/ambiguous disposition rejection |
| bootstrap and concurrency | require audited activation; serialize same-predecessor operations | two-writer barrier, one winner, exact retry, zero partial state |
| replay and persistence | preserve all transition/disposition bytes and system-time prefixes | live/genesis/checkpoint-tail/JSONL/duplicate parity; corrupt/partial fail closed |
| immutable provenance | never rewrite assertion revision/logical-at-assertion or valid-time evidence | combined pre/during/post transition matrix |
| agent read | expose scoped ancestry, assertion-time identity, current resolution, disposition basis, and system-as-of | core resolver, Provider GRAPH_AUDIT, Hermes serialization, denial/revocation without existence leakage |

Identity operations without a graph-owned compiled transition and derived
reverse-reference closure remain unresolved/noncommitting. The validator must
derive affected references from canonical schema/state rather than trust a
caller-supplied list. Every rejection proves no event, lineage carrier, graph
revision, pointer, or writer epoch change. These are validation requirements,
not P1/P2 findings before implementation exists.

### M4 Identity Lineage Review Round 1 (2026-08-03)

Focused final-tree evidence was 24 tests in 12.79 seconds, clean Ruff across the
lineage-changed surfaces, and scoped configured Pyright with zero findings. The
coherent spec, correctness, and test review confirmed four P2 product gaps:

- `P2 / changes_required / integration`: production composition has no graph-
  owned compiler, so every ordinary identity operation remains unresolved and
  only test-local fake compilers can produce transitions.
- `P2 / changes_required / data integrity`: reverse-reference closure derives
  only claim subject/object references rather than every registered physical
  and logical reference family.
- `P2 / changes_required / replay integrity`: cycle detection checks predecessor
  reachability toward successors rather than successor reachability toward
  predecessors, allowing A-to-B followed by B-to-A.
- `P2 / changes_required / authorization`: Provider/Hermes accepts caller-built
  audit scope without authenticated host ingress, server-derived authorization,
  full-scope capability, revocation, or non-disclosing denial.

The remediation must compose one snapshot/transaction-owned compiler, derive
total closure from the canonical reference registry and immutable base snapshot,
fix cycle direction and validate lineage before checkpoint/successful replay
return, and require authenticated server-derived scope before any audit lookup.
Real atomic-store alias/rekey/merge/split, multi-kind closure, bootstrap,
two-writer retry, multi-transition checkpoint, and Provider/Hermes denial tests
replace fake-only proof. No external decision is required.

Readiness inspection confirmed the approved design names the canonical owners
`memory_evolution/reference_integrity.py` and
`memory_evolution/transaction_coordinator.py`, but those modules and the
accepted identity-operation IR do not yet exist. This is an implementation
prerequisite within the authorized M4 scope, not a new semantic choice. The
legacy best-effort `MemoryGraphStore` and scans of materialized records are
explicitly rejected as completeness authority. The prerequisite slice must
land through the existing semantic replay/atomic-store authority before the
four lineage findings can be remediated.

### M4 Identity Lineage Review Round 2 (2026-08-03)

The prerequisite/remediation candidate passed 30 focused tests, scoped Ruff,
and scoped Pyright. Targeted review confirmed cycle direction, replay-before-
success validation, atomic ledger composition, stale-state rejection, and the
authorization rule algebra, but the production authority remained incomplete:

- `P2 / changes_required / trust boundary`: accepted identity intent is an
  arbitrary callback bound only by operation ID, not a canonical atomic-store
  artifact bound to the sealed candidate, source analysis/evidence, fence,
  read-set, and reservation authority.
- `P2 / changes_required / collision integrity`: successor revision/logical IDs
  lack typed reservations, snapshot absence proof, and expected-absent CAS
  intents in the same event/ledger commit.
- `P2 / changes_required / reference closure`: the generated manifest covers
  only the four carrier variants and the compiler still starts from claims,
  rather than every deployed graph/projection/reference codec and every active
  ledger edge for both physical and logical targets.
- `P2 / changes_required / composition`: default Provider/Hermes construction
  has neither the canonical accepted-operation source nor a concrete authorized
  scoped lineage reader/grant source.
- `Not applicable / changes_required / verification`: the two-writer proof is
  sequential and the checkpoint contains lineage only in the tail rather than
  restoring an already-materialized multi-transition prefix.

The final authority batch must persist accepted identity operations and
successor reservations under the semantic atomic store, derive closure from the
complete verified ledger/base/index registry with exact converse equality,
compose the real compiler/reader/authorizer in default factories, and prove
same-snapshot barrier retry plus checkpoint-after-lineage parity. The reviewers'
P1 labels are normalized to P2 because identity operations are important but
not the mainstream majority of ingestion traffic.

Readiness inspection found that the design-required `EntityRevision`,
`AliasRevision`, `TypeEvidence`, `ClaimProjection`, `RelationRevision`,
`CitationRecord`, `ProvenanceRecord`, `ReferenceDispositionRecord`, canonical
graph payload/snapshot/read-set/write-intent contracts, and planned successor
reservations have no production codec or repository. The deployed graph-event
union currently contains only claim, action, identity-lineage, and temporal
carriers; projection state is a separate authority and cannot be scanned as a
substitute graph base. The full graph-record substrate is therefore a required
M4 prerequisite milestone. The approved design resolves its semantics, so no
external decision is required and narrowing to the partial union is rejected.

### M4 Canonical Graph And Identity Lineage Focused-Green Checkpoint (2026-08-03)

The final authority batch implements the typed twelve-kind canonical graph
payload and codec manifest; authoritative graph snapshots and read-set/write-
intent contracts; planned successor reservations; accepted identity-operation
artifacts owned by the semantic atomic store; callback-free ordinary runtime
composition; source-grounded entity, alias, and disposition records; total
manifest-governed reference extraction and ledger converse validation; atomic
expected-absent reservation markers and CAS; lost-ack/reopen idempotence; and
lineage replay over prior committed batches.

Focused verification is green: 25 graph/identity tests passed in 166.98
seconds, followed by 10 post-static smoke tests. Alias, rekey, merge, and split
persist and reopen; two writers competing for the same successor serialize to
one winner; incomplete split is noncommitting; exact retry and reopen preserve
one reservation marker; and checkpoint after lineage one plus lineage-two tail
matches genesis replay byte-for-byte. Ruff is clean on the affected production
and test surfaces, and scoped configured Pyright reports zero errors and zero
warnings.

During verification, replay was corrected to derive reverse-reference closure
from prior committed batches rather than treating successor records introduced
earlier in the same atomic batch as pre-existing references. Repeated immutable
schema-manifest and type-adapter construction was cached to keep the complete
twelve-kind validation path bounded without changing semantics. No known
focused failure or external design blocker remains. Coherent specification,
correctness, and test review is now the exact next action.

### M4 Canonical Graph And Identity Lineage Review Round 3 (2026-08-03)

Concurrent specification, correctness, and test review validated four product
contract gaps and four verification gaps. The coordinator reproduced the
ownership gaps directly: accepted identity-operation publication has only test
callers; the default Provider factory supplies neither a concrete lineage
reader nor an authorizer; the durable type-evidence and reference-disposition
schemas omit design-required coordinates; the closed typed graph planning
projection is absent; and the audit certificate covers only a subset of the
required ledger/state coordinates.

The confirmed product findings are `P2 / changes_required`: ordinary identity
acceptance lacks a trusted terminal owner that creates the atomic-store
artifact and activates reference integrity; normal Provider/Hermes lineage
reads always deny because no concrete scoped reader/verified authorizer is
composed; durable type/disposition and audit-certificate schemas are lossy; and
identity compilation consumes durable replay state directly rather than the
required frozen planning artifact with transaction-owned commit coordinates.

The test findings are `Not applicable / changes_required / verification`:
prove a real conditional-write barrier between two stores, identity-specific
post-durable lost-ack and reopen retry, every canonical record kind plus
discriminator/codec/source mutations, exact canonical identity record output,
and normal composed Provider/Hermes allow/deny behavior. These form one bounded
remediation batch under the sole graph/identity writer. Targeted delta review,
not another whole-scope review, follows focused-green evidence.

### M4 Canonical Graph And Identity Lineage Review Round 4 (2026-08-03)

The round-3 remediation produced 118 focused passes, 10 durability/contention
passes, clean Ruff, clean configured Pyright, and all-kind signed-checkpoint
parity. Targeted delta review nevertheless confirmed five remaining P2 product
defects: the serialized commit-coordinate placeholder differs from the
governing schema; closure reprojection is still hard-coded to three record
families rather than manifest/lifecycle driven; ordinary writer authority can
directly preseed a structurally valid forged frozen plan; graph mutation
between compilation and separate plan publication can strand a stale immutable
artifact; and graph-audit authorization can be revoked after authorization but
before the first disclosure read.

Four test-only gaps are `Not applicable / changes_required / verification`:
identity-specific two-JSONL CAS/freeze/lost-ack proof, populated pre-bootstrap
certificate catch-up, real-reader Hermes deny/full zero-read behavior, and
inner-payload mutations for all twelve kinds across genesis and checkpoint-tail
replay. The accepted-only compatibility finding is rejected as a released-
compatibility defect: both accepted-only and frozen artifacts are uncommitted
M4 work, so accepted-only bytes now fail closed with a typed migration-required
outcome and zero state change.

One bounded remediation batch owns canonical coordinate serialization,
manifest-driven reprojection, store-owned decision verification, atomic stale-
plan rejection/replanning, same-store authorization revalidation, and the four
verification actions. Targeted delta review follows; CI topology remains in the
linked testing WorkPlan.

### M4 Canonical Graph And Identity Lineage Closure (2026-08-03)

Rounds 5 through 7 replaced side-channel planning coordinates with typed
in-record placeholders, added the design-required durable `recorded_at` and
`system_interval` fields, and moved materialization to the authoritative commit
boundary. One commit timestamp and final `graph_revision_after` now materialize
and re-digest identity, correction, retraction, graph-record, event, and planned
reference-ledger bytes; retry and reopen reuse the committed bytes.

The store owns and seals the identity decision verifier; callers cannot inject
a publication verifier. Frozen artifacts bind trusted decision authority,
replay and ledger snapshots, successor reservations, and pending planning
state. Publication, reservations, graph effects, and ledger changes use the
same CAS; stale plans recompile once, freeze is rechecked under the transaction
lock, and independent JSONL writers produce one winner. Scoped graph audit
re-resolves host ingress and current scopes immediately before disclosure and
revalidates the grant in the reader.

Reference reprojection is generated from manifest/lifecycle paths, including
nested and repeated logical references and prior dispositions, while immutable
physical/provenance references remain historical. Every planned reference-ledger
add/remove is materialized at the real final revision and compared field-by-
field with the durable ledger mutation before CAS. The test-only serialized
planning applicator remains independent of production planners.

Final graph/identity evidence includes 95 broader core passes, 13 commit-time
terminal passes, 9 identity/temporal ledger passes, 6 independent planning-
oracle passes, all-kind signed-checkpoint/genesis parity and corruption
rejection, plus populated bootstrap, bootstrap race, lost-ack, freeze, tamper,
same-successor JSONL contention, sequential rekey, and Hermes scoped/full/
revocation proofs. Ruff, configured Pyright, and `git diff --check` are clean.
Targeted specification, correctness, and test reviewers report no remaining
required finding.

- `remaining_validated_p1_p2: []`
- `remaining_blocks_approval: []`
- `remaining_changes_required: []`

### M4 Projection History Slice A Review Round 1

The first Slice A candidate added separate typed temporal/trust projection
generations, commit certificates, append-only pointer histories, replay
bindings, atomic graph/event/projection publication, exact retry, current,
historical, and contested views, and JSONL/checkpoint validation. Focused writer
evidence was 11 projection-history cases, 13 checkpoint cases, 65 combined
projection/event/atomic regressions, real ordinary and clarification paths,
clean recovery, configured Pyright with zero findings, clean Ruff, and clean
diff hygiene.

Independent review confirmed three bounded Slice A defects:

- `P2 / changes_required / writer authorization`: public detached projection
  publication can bypass the semantic writer and write projection-only records.
  Projection publication must be an atomic-store-only guarded capability and
  the projection namespaces must be governed at both admission layers.
- `P2 / changes_required / current-read coherence`: direct current reads accept
  an omitted graph revision and can expose a stale generation. Every public
  current read must resolve and compare authoritative replay graph state; an
  unchecked default is forbidden.
- `P2 / changes_required / checkpoint recovery`: standalone checkpoint-tail
  replay validates embedded projection binding shape but has no independent
  persisted projection-history resolver. It must require and compare a complete
  external binding before returning any replay state.

Required evidence corrections are a real policy-relative A-to-B terminal
history, resolver-produced equal-time/equal-rank contested outcome, real
higher-authority current plus historical prior, three-pointer JSONL deletion,
reorder, duplicate, predecessor/cycle/substitution mutations, a failpoint in a
real terminal atomic transaction, and signed-checkpoint plus graph-revision
mutations bound to actual persisted projection history. Temporal/trust migration
and identity lineage were also reported absent; those are intentionally the
next planned Slice B and Slice C and are not claimed complete by Slice A.
No user decision is required.

### M4 Projection History Slice A Review Round 2

Round-2 implementation closed detached projection publication, authoritative
current-read graph resolution, and independent checkpoint binding validation.
It also added the canonical claim slot/value/assertion and immutable entity
reference schema chain with exact source authority through terminal, carrier,
event, replay, and real same-policy arbitration. Focused evidence included 14
projection-history tests, 42 event/replay tests, 13 semantic-pipeline tests,
real atomic terminal/reopen paths, frozen compatibility, clean Ruff, and
configured Pyright with zero findings.

Independent review confirmed six determinate Slice A corrections:

- `P2 / changes_required / writer authorization`: replay, checkpoint,
  clarification, recovery, and integrity authority/control namespaces remain
  outside both governed-write guards. Centralize one closed semantic-authority
  classifier shared by both layers and require the narrow atomic owner
  capability, not merely detached valid bytes.
- `P2 / changes_required / source authority`: standard terminal persistence
  can combine a fence for source A with accepted analyses/claim evidence from
  source B. Require exact source ID and digest equality before any write.
- `P2 / changes_required / transaction closure`: the canonical event batch's
  graph-delta digest is not compared with the co-persisted graph-delta member.
  Require exact equality and terminal/group/observation closure before replay.
- `P2 / changes_required / checkpoint secret`: the public checkpoint resume
  authority exposes its HMAC key provider and secret. Keep signing material
  private and expose only validation operations.
- `P2 / changes_required / valid-time projection`: single-valued arbitration
  currently groups an entire slot regardless of interval. Partition canonical
  valid-time atoms first, arbitrate only overlapping assertions, and coalesce
  adjacent identical results.
- `P2 / changes_required / same-key co-support`: after selecting the winning
  value key, every eligible assertion for that same key remains selected
  support regardless of lower rank; authority is not increased by count.

Same-policy trust decay was also reported absent. That is explicitly the next
Slice B scheduler/decay contract and is not being treated as implemented by
Slice A. Policy A-to-B migration and rollback likewise remain Slice B; identity
lineage remains Slice C. Final CI collection/timing pins remain deferred until
the complete M4 inventory is known. No user decision is required.

## M4 Reader/List Slice Review

The first implementation candidate added strict contracts, canonical JSONL
conflict/snapshot storage, authenticated cursor pagination, opt-in provider and
Hermes pulls, and basic restart tests. Coordinator evidence was 27 focused
tests, 76 legacy provider/compatibility tests, focused Ruff, and configured
Pyright with zero findings.

Confirmed review findings:

- `P2 / changes_required / integration compatibility`: the legacy schema set
  advertised `memorii_list_conflicts` although only authenticated attention
  dispatch could call it. The new tool must live on a paired negotiated schema
  and dispatch surface; legacy discovery/dispatch remains byte-compatible.
- `P2 / changes_required / security error handling`: invalid scope/cursor
  request models leaked Pydantic diagnostics instead of exact opaque error
  codes.
- `Not applicable / changes_required / authorization conformance`: continuation
  must require exact current authorized-scope equality, not subset acceptance.
- `Not applicable / changes_required / verification governance`: the real
  integration test, workflow selector/count, key/cursor/snapshot mutation
  families, stable tamper mutation, rollout behavior, and timing entries were
  missing or incomplete.
- Final test DREV: confirmed `P2 / changes_required / security and
  verification`. An unavailable snapshot was detected only after `_read_all`
  materialized conflict payloads. The correction resolves snapshot metadata
  first and returns `invalid_conflict_cursor` before the full payload path.

All findings are determinate. No user decision or design amendment is needed.

### Reader/List Remediation Evidence

- The negotiated provider/Hermes schema and authenticated dispatch are paired;
  legacy schema discovery and dispatch remain unchanged.
- Cursor and snapshot bytes separately bind complete current authorization and
  the retained listing subset, with exact pre-read mismatch rejection.
- Strict request parsing returns only the closed opaque error codes. Cursor
  signing, retained verification, rotation, revocation, expiry, future time,
  unavailable snapshots, restart, and no-fallback behavior have deterministic
  tests.
- The real provider/Hermes-to-JSONL integration owner is
  `memorii/tests/integration/test_conflict_attention_persistence.py` and is
  included in the 15-minute `semantic-ingestion-generation` job. Exact
  collection is 271 tests.
- Coordinator gates: 76 focused slice tests, 112 legacy provider/compatibility
  tests, 35 workflow/static contract tests, and all 271 semantic-generation
  tests passed. The generation run completed in 279.93 seconds. Focused Ruff
  passed and configured Pyright reported zero findings. The deterministic
  four-shard planner collected 2,839 tests with all estimates below 600 seconds;
  full shard execution remains a final M4 closure gate.
- The final retention race is closed by validating snapshot metadata and
  decoding conflict payloads from one immutable line image under one shared
  lock. A deterministic competing retention writer proves the current read
  linearizes before removal and the next read returns
  `invalid_conflict_cursor` before payload decode. The bounded test delta
  reviewer approved with `remaining_validated_p1_p2: []`; 26 targeted tests,
  focused Ruff, configured Pyright, and shard-plan verification pass.
- A post-remediation 271-test generation rerun had 270 passes and one unrelated
  pre-existing in-memory concurrent-delivery lease race; the same generation
  gate passed before this remediation. The isolated failure is being rerun and
  remains final-gate evidence rather than a conflict-reader finding.

## M4 Clarification And Recovery Review

The first D02/D03 candidate implemented strict clarification requests, atomic
append-only submission, nonce/receipt idempotency, a lease-fenced three-attempt
processor, negotiated resolve dispatch, and a standalone proof-carrying
integrity-control repository. Local evidence was 93 focused tests, configured
Pyright with zero findings, clean Ruff, 15 static-workflow tests, a 287-test
exact collection, and a 2,855-test four-shard plan within budget. The 286-test
generation selection before the final unsure-family addition passed in 300.79
seconds; the added unsure family passed separately.

Confirmed independent-review findings:

- `P2 / changes_required / runtime integration`: durable submitted work has no
  production scheduler/composition with the ordinary idempotent semantic
  pipeline, so a real resolution can remain `clarification_submitted`.
- `P2 / changes_required / recovery authority`: repair generations accept
  caller-supplied authority and clean-replay metadata; release does not require
  replay-authority-produced verification.
- `P2 / changes_required / integrity lifecycle`: a new incident affecting an
  already-frozen partition is not durably linked, so an older repair can release
  a partition after later corruption.
- Verification findings require provider/Hermes-to-real-processor tests,
  negative source/receipt matrices, persisted corruption/release races, and
  supported/unknown/retired schema behavior rather than model-only checks.

All product findings are confirmed and determinate. Their smallest coherent
remediation is the next canonical event/replay slice because live append,
genesis replay, checkpoint-tail replay, incident isolation, repair
verification, and processor scheduling must share one production authority.
No user decision is needed.

### Canonical Replay Integration Review Round 1 (2026-08-03)

The first composed event/replay candidate passed the exact 295-test semantic
generation selector, a 102-test conflict/replay family, 65 static/config tests,
Ruff, configured Pyright, identity hygiene, and three of four complete unit
shards. The remaining four shard failures were deterministic generated-design
authority drift. Two independent authority generators produced byte-identical
replacement bytes; the CTV authority and exact current pins were regenerated
without weakening any validator or count.

Independent spec, correctness/security, and test review confirmed this bounded
remediation set:

- `P2 / changes_required / replay compatibility`: the individual historical
  event decoder upcasts registered source schemas, but persisted batch readers
  validate the nested event as the current schema before calling it. Historical,
  mixed, future, retired, ambiguous, and source-digest-invalid batch families
  therefore lack a real fail-closed authority path.
- `P2 / changes_required / checkpoint freshness`: checkpoint resume accepts
  default revision floors and unattached caller policy/registry objects. It must
  require the current store-owned monotonic lifecycle authority and reject an
  absent, stale, substituted, revoked, or rolled-back authority.
- `P2 / changes_required / replay closure`: the active atomic store reconstructs
  graph event state only. It must persist and reconstruct observation, progress,
  replay-artifact closure, and trusted checkpoints through one production
  replay-authority aggregate.
- `P2 / changes_required / integrity composition`: the default provider atomic
  store has no mandatory freeze guard or incident reporter, and runtime
  validation accepts host stores without them. Canonical reads/appends must
  freeze and publish sanitized attention through the real production boundary.
- `P2 / changes_required / recovery correctness`: replaying the original corrupt
  authority cannot prove repair. Recovery must publish a distinct append-only
  clean generation bound to the retained incident bytes, replay that generation
  independently, preserve the corrupt generation, and release only against the
  latest incident/control CAS.
- `P2 / changes_required / concurrency`: the standalone event repository reports
  integrity only after releasing event admission, allowing an affected append
  to commit before freeze. Incident isolation and affected admission must share
  one linearization order with an explicit lock order.
- `P2 / changes_required / clarification composition`: the ordinary authorized
  runtime still exposes only a protocol seam. It needs a production adapter to
  the idempotent semantic transaction/receipt owner, normal builder composition,
  restart adoption, lease renewal, and three-attempt reopen behavior.

The associated deterministic tests must exercise these behaviors through the
real JSONL/atomic-store and public Provider/Hermes paths, including checkpoint
key lifecycle and substitution matrices, processor failure/renewal/source-proof
families, corruption/release races, and exact no-partial-state assertions. A
reported provider-compatibility import-path concern is unsupported on the
current tree: the workflow-structure test executes the exact command from its
declared working directory and passes all 15 tests.

All confirmed findings are determinate and require no external semantic choice.
Projection history remains the next vertical slice only after this round closes.

### Canonical Replay Integration Review Round 2 (2026-08-03)

The round-1 writer implemented all seven assigned boundaries. Final writer
evidence was 131 warning-strict replay/conflict/clarification tests, 75
provider-composition tests plus three final atomic-linearization reruns, clean
Ruff and diff hygiene, and scoped Pyright with zero findings. Coordinator
artifact closure regenerated the CTV and CGS structural authorities from the
current governing design. The clean-room CTV suite passed 259 tests, the CTV
PR-gate suite passed 20 tests, and the exact CTV, lifecycle-root, and CGS
structural checkers accepted the new pinned authorities.

Fresh independent review confirmed that the first remediation still left the
following determinate product gaps:

- `P2 / changes_required / restart correctness`: the default checkpoint
  authority is process-random while persisted replay state binds its lifecycle
  digest, so a default-composed durable store cannot reopen after its first
  canonical commit. Persistent composition must use a stable protected
  store-owned or required host-owned authority; an ephemeral authority cannot
  authorize durable writes.
- `P2 / changes_required / registry lifecycle`: persisted batches require their
  registry digest to equal the active registry. A legitimate registry upgrade
  therefore makes supported prior batches unreadable. Replay must resolve the
  exact immutable registry authority named by each batch through monotonic
  registry history before member upcast.
- `P2 / changes_required / replay closure`: aggregate bindings for observation,
  progress, and artifacts are not resolved back through their exact fenced
  generation, payload digest, typed reducer, or cross-member reference closure.
  Genesis and checkpoint resume must reconstruct and compare the complete
  replay authority rather than merely list opaque coordinates.
- `P2 / changes_required / checkpoint trust`: checkpoint creation accepts
  retired/revoked keys and resume accepts keys revoked or compromised after
  issuance. Signing and current resume must use the current active,
  unexpired, uncompromised lifecycle authority and must reject all key,
  signature, snapshot, watermark, and registry substitutions before exposure.
- `P2 / changes_required / clarification recovery`: receipt lookup does not load
  and verify the paired transaction record. An orphan or substituted receipt
  can resolve attention without a semantic transaction.
- `P2 / changes_required / semantic commit integrity`: the default clarification
  adapter records an arbitrary decision-provider outcome directly. An accepted
  answer must re-enter the ordinary governed validation/temporal/trust/terminal
  pipeline and atomically bind its actual semantic result and graph/event effect
  to the receipt; `insufficient` remains an explicit no-commit outcome.
- `P2 / changes_required / retry behavior`: production adapter operational
  failures escape unclassified while the processor retries only
  `ClarificationPipelineError`. Real provider/Hermes scheduling must durably
  record attempts one through three, reopen on exhaustion, adopt a post-commit
  receipt after restart, and never duplicate semantic effects.
- `P2 / changes_required / production recovery`: ordinary provider composition
  has a durable global freeze but no production-owned clean-generation builder,
  privileged repair/release service, or exact-subset release path bound to the
  same atomic admission coordinate.
- `P2 / changes_required / recovery provenance`: declared authoritative source
  digests are detached from the clean-generation verifier. A typed privileged
  request must bind retained corrupt bytes, authoritative sources, generated
  clean bytes, clean-generation digest, and independent replay result.

Required verification additions include the full checkpoint-key lifecycle,
real bound-member deletion/substitution and cross-generation reference cases,
accepted clarification ordinary-pipeline effects, production retry/reopen and
post-commit-crash adoption, source/receipt proof mutations with byte-identical
rejection, real clean-generation mutation before release, and isolate/release
races. The semantic-generation selector now collects 310 tests while CI still
pins 295; the exact count and timing inventory must be updated only after the
round-2 inventory is final.

No external semantic decision is required. The reported provider-compatibility
import concern remains disproven by the exact workflow-working-directory test.

### Canonical Replay Integration Review Round 3 (2026-08-03)

Round 2 closed the assigned restart, registry-history, complete-member,
checkpoint-lifecycle, paired-receipt, semantic-effect, retry-classification,
and clean-recovery contracts. Final writer evidence on the atomic clarification
effect bytes was 110 focused tests in 522.84 seconds, 24 store-contract passes
plus one skip, seven replay/conflict integration passes, repository Pyright
with zero findings, clean Ruff, and clean diff hygiene. Accepted clarification
now atomically publishes the transaction, receipt, ordinary typed terminal
effect, graph delta, canonical event batch, replay state/aggregate, checkpoint,
lifecycle, and registry history; retry adoption proves one receipt and one
event effect, and missing effect bytes fail closed.

Correctness/security re-review found no remaining P1/P2 in the repaired
restart, registry, receipt, lifecycle, CAS, or lost-ack paths. Spec and test
review nevertheless confirmed four remaining production-integration defects:

- `P2 / changes_required / replay closure`: member reference validation sees
  only siblings from the same generation. SIA-R10 explicitly permits a
  dependency from the same or an earlier complete generation. Reconstruction
  must carry the verified cumulative prior closure and reject only absent,
  later, or substituted dependencies.
- `P2 / changes_required / clarification composition`: the adapter can run the
  ordinary semantic pipeline only when a context provider is injected, but
  both normal local/provider builders omit it and therefore always return
  `insufficient`. Normal composition needs a production resolver backed by the
  retained authenticated user event, scope, policy, trust, and local analyzer.
- `P2 / changes_required / recovery composition`: the production provider root
  still does not own or expose the clean-generation repair/release service.
  Normal construction must bind freeze/incident, retained corrupt evidence,
  clean build/replay, and exact-subset privileged release to the same atomic
  admission linearization authority.
- `P2 / changes_required / recovery provenance`: a legacy generic repair path
  still accepts verification with empty authority-source digests. Provenance
  must be mandatory on every public repair path; empty, detached, or substituted
  source-to-clean-generation bindings fail closed.

The final proof matrix must additionally execute checkpoint key lifecycle and
signature/snapshot/watermark mutations, real Provider/Hermes retries through
attempts one to three and post-commit crash adoption, source/receipt expiry and
binding mutations with byte-identical durable rejection, durable JSONL
aggregate deletion/substitution across reopen, prior-generation dependency
success/substitution, and normal-production incident-to-release restart/races.
The current inventory is 318 tests; workflow count/timing pins remain
intentionally stale until this final integration and the later projection slice
settle. No user decision is required.

### Canonical Replay Integration Review Round 4

The round-3 writer closed the cumulative prior-generation dependency lookup,
normal provider/Hermes clarification context, same-memory-plane privileged
recovery composition, and non-empty clean-generation source provenance. Exact
writer evidence was 326 warning-strict tests in 599.10 seconds, 100 broader
terminal/integrity/provider/filesystem tests in 451.28 seconds, six focused
recovery/race tests, configured Pyright with zero findings, clean Ruff, and
clean diff hygiene. The durable filesystem composition now retains typed
repair requests, verifies retained generation-manifest and member bytes,
prepares a clean replay without changing frozen active authority, releases the
exact repaired subset, atomically activates, and reconciles a simulated crash
after release and before activation across JSONL reopen.

Fresh independent review confirmed three remaining P2 runtime defects:

- `P2 / changes_required / recovery transactionality`: activation durably
  writes `activated` before mandatory registry-history/checkpoint-lifecycle
  closure is validated. A missing authority record can therefore fail only
  after commit and leave a falsely terminal clean generation. Validate the
  complete mandatory authority set and clean plan before the activation CAS;
  invalid candidates remain frozen and non-terminal.
- `P2 / changes_required / replay closure`: stage/planned progress may cite an
  arbitrary artifact or terminal digest, while reconstruction treats arbitrary
  nested digest-shaped strings as satisfied dependencies. References must be
  typed, and satisfaction must come only from validated canonical producer
  bytes in the same or an earlier complete generation.
- `P2 / changes_required / clarification provenance`: a verifier-provided
  source-event digest is retained separately from the locally selected raw
  event and can be combined with different text. The governed raw ingress
  record needs a host-verified canonical source binding, and clarification must
  require exact event ID, digest, and bytes through retry/restart.

The test reviewer also classified four determinate verification corrections as
`Not applicable / changes_required`: complete checkpoint key/signature/digest
mutation coverage; durable JSONL aggregate/member/index deletion and
substitution across reopen; processor-level attempts one through three,
post-commit receipt adoption, lease reclaim, and concurrent stale-owner proof;
and production-boundary principal/tenant/scope/source/expiry/revocation/receipt
negative provenance coverage with zero durable effects. The exact workflow
count remains intentionally stale at 295 versus the current observed 326; it
will be repinned once the projection slice fixes the final inventory. No user
decision is required.

Round-4 implementation closed all three prior P2s and passed the stable exact
warning-strict selector with 354 tests in 823.81 seconds. Configured Pyright
reported zero findings; Ruff and diff hygiene passed. Independent delta review
confirmed the pre-commit recovery-authority validation, typed producer closure,
and exact clarification source-byte binding, then found one further bounded P2:

- `P2 / changes_required / recovery completeness`: a repair request may supply
  a valid contiguous prefix of the retained canonical event batches and omit
  later retained state. Normal recovery has no authorized-loss disposition, so
  its authority-source tuple must equal the complete retained canonical tuple
  exactly; omission, duplication, reordering, or substitution rejects before
  release.

The test reviewer retained two `Not applicable / changes_required` evidence
gaps. Tests must drive `ConflictClarificationProcessor.process_next` through
attempts one through three and a semantic commit followed by an exception,
proving exact receipt adoption and no duplicate invocation; and normal
Provider/filesystem/Hermes composition must behaviorally prove incident,
freeze, complete clean rebuild, exact release, restart, and a racing write.
The CI collection pin remains a known final-inventory correction. No user
decision is required.

Round-5 implementation made retained batch equality exact, converted retry and
post-commit adoption tests to the real processor, and added the real
filesystem/Provider/Hermes incident-to-release race. That behavior proof found
and fixed a stale corruption observation that could re-freeze after release by
placing source admission and preplanning verification/publication under the
same reentrant replay-integrity linearization. The stable warning-strict exact
selector passed 361 tests in 1,354.18 seconds; configured Pyright reported zero
findings, Ruff and diff hygiene passed, and captured file hashes were identical
before and after the run.

Fresh independent review confirmed those corrections, then found one bounded
cross-path defect:

- `P2 / changes_required / clarification recovery`: accepted clarification
  commits publish canonical event batches and replay state directly but do not
  publish equivalent typed generation-member provenance. Clean recovery derives
  its complete source set from generation members and can therefore omit the
  clarification event, lose its graph effect, and invalidate its receipt. The
  clarification commit also bypasses the shared integrity linearization and can
  interleave release/activation. Persist clarification event authority in the
  same complete typed generation model (or equivalently extend retained-source
  derivation with exact transaction/receipt-bound provenance), serialize the
  complete commit, and prove ordinary event plus accepted clarification through
  filesystem reopen/recovery and a deterministic clarification/release race.

No user decision is required.

### M4 Projection History Slice A Review Round 3

Round-3 implementation closed the central authority classifier, source fence,
event/graph/group/observation closure, checkpoint facade, valid-time atom, and
same-key co-support findings. Evidence included 57 direct-CAS authority cases,
142 writer-admission/event-replay tests, 14 projection-history tests, eight
valid-time atom families, durable partial-overlap reopen, source-swap and
cross-group-delta zero-effect cases, trusted recovery/clarification paths,
clean Ruff, and configured Pyright with zero findings. Correctness and test
review reported no remaining Slice A P1/P2 behavior gap.

Specification review found three final boundary corrections:

- `P2 / changes_required / current event authority`: a pre-M4 early return
  accepts opaque or noncanonical `event_batch` bytes on a current committed
  group and still advances graph/control state. Current committed requests must
  reject unknown or wrong-schema event batches; any historical import is a
  distinct non-committing migration path.
- `P2 / changes_required / source provenance`: fence/source equality applies
  only to accepted terminals, but non-committing terminals may retain source
  analyses. Validate every present analysis/evidence source ID and digest before
  lease or write, while zero-analysis non-committing outcomes remain valid.
- `P2 / changes_required / checkpoint key security`: hiding the atomic-store
  authority did not close the public `MemoryPlaneService` raw protected-secret
  retrieval API. Replace raw checkpoint-secret access with a backend-owned
  signer/verifier capability that never returns key bytes; public callers get
  verification/resume only.

Same-policy decay remains the explicit next Slice B scheduler contract. Final
collection/timing pins remain deferred. No user decision is required.

Round-7 implementation independently enumerated accepted clarification
transaction/receipt/event closures and required exact one-to-one typed recovery
authority. The final JSONL matrix covered 12 missing, extra, duplicate,
cross-bound, sequence, and generation mutations; every rejection preserved the
frozen control and valid event bytes across two reopens. Recovery-owner tests
passed 53/53, generation closure passed 39/39, and all three independent
reviewers reported no remaining P1/P2 or changes-required item. The final held
revision passed the complete exact warning-strict selector with 380/380 tests in
1,739.85 seconds; repository Ruff, identity hygiene, configured Pyright, staged
and unstaged diff hygiene passed. Pre/mid/post hashes were identical for
`atomic_store.py`
(`efe4b0043e5caefc8ab0a1f860071ca1b2cc3c644621df83d42a92eff13ae23f`)
and `test_semantic_terminal_persistence.py`
(`3fbdb6d5faaa110aa94df37835772ab8ac1a313ea3408d4aae407062eb8a8fa7`).

The replay, integrity-recovery, conflict attention, clarification, provider,
Hermes, and durable restart slice is closed. The workflow collection pin remains
a known final-inventory correction. The exact next action is the remaining M4
projection/history/identity-lineage slice. No user decision is required.

Round-6 implementation added a typed clarification recovery-authority binding,
placed the entire public clarification commit/retry under the shared reentrant
integrity linearization, and proved ordinary plus accepted clarification through
JSONL corruption, exact two-batch recovery, release, reopen, graph/receipt
restoration, deterministic release race, retry, and five content-mutation
families. The stable exact selector passed 368 tests in 1,460.18 seconds;
generation closure passed 39 tests; configured Pyright, Ruff, identity hygiene,
and diff hygiene passed.

Fresh independent review confirmed the binding content and race behavior, then
found one missing cardinality invariant:

- `P2 / changes_required / clarification recovery closure`: validation runs
  only for existing clarification authority records. Deleting the authority
  record can remove the accepted clarification from the derived source tuple,
  allowing recovery to retain only an earlier contiguous prefix. Recovery must
  independently derive every accepted clarification transaction/receipt/event
  closure and require exactly one matching authority binding. Missing, orphaned,
  duplicate, cross-bound, or sequence-substituted bindings reject before source
  derivation or release. Add deletion and cardinality mutations across reopen.

No user decision is required.

### M4 Projection History Slice A Review Round 4

Round-4 implementation removed the current committed opaque-event escape,
applied fence/source validation across every terminal status, and replaced
public checkpoint key retrieval with backend-owned opaque signing and public
verification/resume only. Focused evidence covered current-event mutation,
all terminal statuses, checkpoint forgery/reopen, 157 replay/atomic/admission
tests, provider frozen bytes, clean Ruff, and configured Pyright with zero
findings.

Specification review found no residual issue. Correctness review found one
remaining bounded P2: a canonical event batch can carry matching source, fence,
graph delta, revisions, and writer epoch but a foreign
`transaction_group_id`; projection publication then attributes the effect to
that foreign operation. Require exact equality with the terminal operation
before replay/projection and add a complete zero-effect regression. The test
reviewer also requested the already enforced typed-source-authority rejection
be parameterized across every non-committing status; this is a non-blocking
evidence improvement and is included in the same bounded correction. Final
full terminal execution, workflow helper, collection pin, and timing inventory
remain milestone-final verification work. No user decision is required.

### M4 Projection History Slice A Review Round 5

Round-5 implementation bound canonical event-batch transaction-group identity
to both the terminal and admitted operation and expanded typed
source-authority tests across every non-committing status. Correctness and test
rereview found no residual issue in that delta. Specification rereview found
one final lower-level bypass: non-committing direct atomic-store requests have
no event batch, so the store did not decode the terminal group and relied on
service-layer source validation. Move the shared terminal/fence/source/artifact/
observation validator into the atomic store and apply it to committed and
non-committing requests alike; add sealed direct-store foreign-analysis and
foreign-authority zero-effect regressions. No user decision is required.

### M4 Projection History Slice A Closure

Rounds 6 through 8 closed the direct atomic-store terminal bypass, validated
terminal-bearing source checkpoints before write, byte-bound group publication
to the unique planned terminal and closure, restricted terminal artifacts to
the canonical planned generation, and made the terminal/closure artifact index
mandatory and byte-canonical. Direct checkpoint/group, preplanning injection,
artifact-index mutation, retry, reopen, provider lost-ack, recovery, Ruff,
configured Pyright, and diff-hygiene gates passed. Final independent
specification, correctness, and test reviews each report:

- `remaining_validated_p1_p2: []`
- `remaining_changes_required: []`

Slice A is complete for immutable temporal/trust projection generations,
append-only pointer history, current/historical/contested queries, canonical
claim identity and source authority, same-policy non-decayed arbitration,
valid-time atomization, atomic graph/event/projection publication, replay,
checkpoint, and recovery. Same-policy decay and policy migration are not claimed
by this closure; they are the exact next Slice B action. Final collection/timing
pins remain deferred. No user decision is required.

## M4 Readiness And Baseline (2026-08-02)

This is the authoritative current section for the newly authorized M4
implementation operation. It supersedes later historical statements that M4 is
awaiting authorization, while preserving their M3 closure evidence.

### Authorization, Revision, And Tree

- The user explicitly authorized starting M4 after M3 completion.
- Repository branch: `semantic-indexing-m4`.
- Base, merge-base, and current HEAD:
  `2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93`.
- Baseline tree state: clean; no tracked or untracked changes.
- Canonical semantic-ingestion design SHA-256:
  `53b796de59dead7fb16902bc8c53c0225628b602e53c5ee4c9f91dd1fe1e2261`.
- Governing event-model SHA-256:
  `9ce93e4a826f3e47b2e41fa06d2ec1e40bb0cad2475fa0527d9bb2c9ab3acdec`.
- Governing conflict-attention SHA-256:
  `b2d58a05a77c4105d2ce41433024bcb88d41204b6f2de8a86e76b699d8eb66de`.
- Frozen replay-decision artifact SHA-256:
  `f04b778e8e23632ff732199f6776ebbf740210d20778338bb7524b316f3ed241`.
- Replay-decision validator SHA-256:
  `41a50fa6847a5c96704536521842761b3400c79fb8e75096193c87b72d480262`.
- Identity-hygiene allowlist SHA-256:
  `ec39cf73769f061a7c7ca0f50a9c960e2ee556fb61f6d944f9d93aeaf6502d9a`.
- Pre-update implementation WorkPlan SHA-256:
  `c70ab38f81e9f25906a09f9280308540bdef66f07a1e2368099fb3b69a0225bf`.

### M3 Lessons Applied Before Coding

- A milestone coordinate may organize this WorkPlan but may not name a module,
  symbol, schema, fixture, test, command, artifact, diagnostic, or workflow job.
- The M3 `SemanticGraphDelta`, `SemanticEventInputBatch`, and
  `SemanticObservationDelta` are bounded candidate-to-terminal persistence
  carriers. They are not canonical event-log, observation-ledger, or replay
  authorities and cannot acquire those semantics by analogy.
- Persisted semantics must be reconstructed from the governing sources before
  adding types. A source-precedence conflict stops implementation instead of
  being hidden behind a local default or a passing fixture.
- Each vertical slice must own its complete source-to-store-to-replay path,
  affected artifacts, collection/timing data, workflow selectors, and review
  identity before closure.
- One writer owns overlapping production, test, and documentation changes;
  independent agents remain read-only until coherent implementation exists.

### Independently Reconstructed M4 Contract

SIA-R10 requires full-state, idempotent memory events derived from typed
`create|update` graph-record mutations; distinct envelope, logical-dedupe, and
record identities; one contiguous repository batch log; atomic graph/event/
dedupe/observation/artifact publication; exact terminal introductions and
outcomes; deterministic schema decode/upcast; genesis and trusted-checkpoint
reconstruction; and fail-closed corruption before any partial state is exposed.

SIA-R18 requires immutable assertions and system-time history, deterministic
current/historical/contested projections, persisted server-owned arbitration
time, trust-decay scheduling, complete temporal/trust migration and cutover,
and append-only rekey/merge/split lineage with exact reference-disposition
closure. Rekey preserves a logical identity, merge creates one new logical
identity, and split creates new logical identities without default fan-out.

The current M3 path persists carrier and digest closure atomically, but it does
not have canonical full-state graph mutations, semantic event envelopes and
batch positions, a dedupe map, event/observation schema registries, checkpoint
trust verification, replay reducers, projection scheduling, policy migration,
or lineage/reference-closure views. Existing green M2/M3 tests are prerequisite
evidence only and do not establish M4 behavior.

### Resolved Historical Readiness Blocker: Equal-Version Conflict

The source hierarchy was contradictory at a persisted public-semantic boundary:

- `docs/design/event_model.md` Section 8.2 says same-version events use
  `event_id` ordering for precedence;
- its Sections 9.2 and 10 instead skip an event whenever the entity already has
  the same version, making the winner depend on arrival order; and
- `docs/design/semantic_ingestion_architecture.md` requires non-identical
  historical equal-version conflicts to reject without materializing a winner
  until `SIA-ED-REPLAY-001` is resolved.

The frozen decision artifact and reconciled governing documents now resolve
that contradiction: byte-identical duplicate envelopes are idempotent, while
non-identical equal-version events fail closed before any winner or partial
state is exposed. The text above is retained only as historical blocker
evidence and no longer prevents implementation.

Product priority: `Not applicable`. Approval disposition: `blocks_approval`.
Finding type: `external decision / persisted replay semantics`. Remediation
eligibility: `external_blocker`.

### Readiness Resolution And First Slice

This blocker is resolved by the user-approved fail-closed rule frozen in
`docs/design/equal_version_replay_decision-v1.json`, the reconciled base and
semantic event ownership in `docs/design/event_model.md`, and the pull contract
in `docs/design/conflict_attention.md`. The linked replay/projection closure
WorkPlan then completed two bounded remediation passes and final independent
spec, correctness/security, and test review with no residual semantic blocker.

The first bounded implementation slice is rollout step 1 only:

- strict conflict option, attention item, page, access-context, interval,
  proposal, confirmation, work, and provider-envelope models;
- exact empty and non-empty versioned envelope serialization without changing
  legacy result models or methods;
- deterministic Hermes JSON-string rendering for bounded untrusted question
  and option data, with empty output causing no legacy-text drift;
- replay-decision validator mutation tests and its required PR gate/aggregate
  dependency.

Conflict repository reads, snapshot pagination, list/resolve dispatch,
clarification persistence/processing, replay incident production, and operator
repair are explicitly later slices. This slice does not install callbacks,
fabricate empty success from a configured repository, or claim end-to-end user
delivery.

### M4 Rollout Step 1 Closure

- Production contracts now define strict conflict-attention items and pages,
  access context, candidate validity intervals, clarification proposals,
  confirmation receipts, work records, and additive provider envelopes. The
  envelopes preserve the existing legacy result APIs and freeze their exact
  construction-time JSON wire representation.
- Hermes rendering is pull-only and deterministic. It adds at most three safe
  conflict cards to an existing tool response, leaves empty responses byte-for-
  byte unchanged, enforces an exact UTF-8 budget, and treats every question and
  option as untrusted data rather than prompt instructions.
- The equal-version replay decision is executable governance: the validator
  binds the governing document hashes, rejects unknown or duplicate JSON keys,
  and is owned by a five-minute PR gate that participates in aggregate unit-test
  success.
- Compatibility evidence freezes the complete legacy prefetch/tool schema,
  representative bytes, independent reader behavior, and a separately pinned
  manifest root. The wheel build includes both new production modules.
- Deterministic evidence at this revision: 79 focused contract tests, 20 exact
  CTV workflow-contract tests, 36 provider-service tests, 30 decision-gate
  tests, 15 static-tooling tests, and 13 frozen legacy-compatibility tests pass;
  full Ruff, configured Pyright, identity hygiene, shard verification, wheel
  build, and `git diff --check` pass.
- Independent `spec_auditor`, `correctness_reviewer`, and `test_reviewer`
  closure found no residual rollout-step-1 blocker. Confirmed findings about
  exact Hermes budgeting, the three-card cap, legacy-byte freezing, duplicate
  JSON keys, and envelope copy behavior were corrected and re-reviewed.

This closes only rollout step 1. No repository reader, list tool, resolution
write, clarification processor, replay-incident producer, or operator repair
path is claimed by this evidence.

### Full M4 Continuation Authorization And Vertical Slices

On 2026-08-02 the user authorized uninterrupted implementation through the
complete M4 milestone and asked the coordinator to stop only for an external
semantic decision. The remaining work is ordered by dependency, not by a
planning coordinate embedded in any executable identity:

1. Resolve authenticated host ingress once, derive a non-disclosing conflict
   access context, and implement the append-only conflict ledger's stable
   snapshot reader, signed keyset cursor, ordinary three-item pull, and explicit
   bounded listing tool. Authorization and feature availability are checked
   before every ledger read.
2. Implement clarification requests, authorized source-user-event proof,
   optional one-time confirmation verification, idempotent operation receipts,
   atomic open-to-submitted transition, and the fenced three-attempt processor
   state machine. No proposal becomes committed semantic truth directly.
3. Replace the M3 event-input carrier with the canonical semantic event and
   batch log, complete binding indexes, immutable observation ledger, schema
   registry/upcast boundary, genesis replay, signed checkpoint validation, and
   storage-integrity incident production. Graph, event, observation, artifact,
   and progress visibility remain one transaction.
4. Reconstruct current, historical, contested, and lineage views from immutable
   assertions and transitions, including deterministic trust-decay scheduling,
   policy migration/catch-up/cutover, and exact rekey/merge/split reference
   disposition closure.
5. Add append-only operator recovery commands over frozen integrity scopes and
   require a new clean generation plus successful replay verification before
   unfreeze. Original conflicting bytes remain immutable.

Every slice has one production/test writer, then focused verification and the
three required read-only closure reviews. The final branch receives fresh
whole-scope spec, correctness, and test review after all deterministic gates.

### Remaining M4 Validation Matrix

| Behavior | Strongest local proof and failure signal | Test/gate owner |
| --- | --- | --- |
| Authorization before attention access | Repository spy proves missing, invalid, revoked, cross-tenant, and insufficient ingress cause zero reads; attention pull returns the unchanged nested legacy result with an empty page while explicit list/resolve return typed non-disclosing errors | provider and Hermes unit/contract tests; provider compatibility job |
| Snapshot pagination | Property and mutation tests vary page sizes, scopes, concurrent introductions/resolutions, every-page boundaries, expiry, signature, protocol, scope, watermark, sort key, retained-snapshot availability, and restart; any duplicate/omitted snapshot member or silent restart fails | conflict-ledger unit tests plus process-safe JSONL integration owner; deterministic unit shards |
| Clarification submission | Action cardinality, candidate membership, interval overlap policy, exact source-user-event proof, receipt claim/expiry/revocation/nonce race, stale revision, exact/divergent retry, and concurrent CAS tests; any partial ledger append or direct truth mutation fails | conflict-ledger/service unit tests and memory-plane process-safety integration |
| Processor recovery | Claim/crash/renew/expiry/reclaim/stale-token, retry/terminal failure, third-attempt exhaustion, restart, and fresh clarification tests compare complete ledger/work bytes and attempt budget | processor state-machine unit/property tests and restart integration |
| Event and observation authority | Every graph-record kind create/update mapping, delta/event bijection, introduction/outcome cardinality, zero-mutation terminals, exact retry, divergent event/dedupe/record-version collisions, complete-batch atomicity, and artifact failpoints; any graph/event/observation/progress divergence fails | semantic replay unit/property tests and semantic-ingestion generation-closure job |
| Schema and replay | Independent construction, supported/deprecated upcast, future/retired/ambiguous/digest-invalid schemas, genesis prefixes, trusted checkpoint tails, position gaps/duplicates/regression/cross-repository substitution, snapshot/signature/key lifecycle, corruption, and restart compare canonical bytes and indexes | dedicated replay integration owner, exact workflow selector, timing inventory, package/static gates |
| Integrity incident and recovery | Every corruption family freezes only a proven-isolated scope, emits sanitized attention without conflicting payload data, rejects user resolution, preserves original bytes, and requires append-only repair plus clean replay before unfreeze | replay/recovery integration tests and operator authorization tests |
| Temporal/trust projection | Interval-prefix and bitemporal properties permute arrival, valid time, system time, trust rank/decay, scheduler downtime, command dedupe, and policy migration races; current reads reject mixed/stale policy fingerprints | projection/scheduler unit properties and restart/migration integration |
| Identity lineage | Rekey preserves logical identity, merge creates one successor logical identity, split creates new identities, every reverse reference has exactly one valid disposition, historical provenance is immutable, and no split default fan-out is possible | compiler/replay lineage property tests and structural graph integration |

The `test_reviewer` must approve this matrix or identify a determinate correction
before high-risk persistence and replay coding begins. New test nodes require
measured timing inventory; every workflow selector and aggregate dependency is
read directly and updated with its affected authority chain.

### M4 Validation Matrix And Gate Impact

The pre-coding `test_reviewer` confirmed that the first implementation slice,
once unblocked, must prove full-state mutation/event bijection, exact duplicate
idempotency, current-writer collision rejection, the selected historical
conflict rule at genesis and checkpoint tails, contiguous batch positions,
supported/retired/future schemas and deterministic upcast, corruption and
artifact closure, immutable terminal observations, and byte-equivalent genesis
and trusted-checkpoint reconstruction. Later slices own temporal/trust prefix
matrices, scheduler recovery, policy migration races, and rekey/merge/split
lineage closure.

Current workflow facts:

| Job or gate | Current command/identity | M4 impact | Readiness status |
| --- | --- | --- | --- |
| Semantic Ingestion Generation Closure | warning-strict semantic unit plus pipeline/process selection; exact 266-test collection lock | A replay integration owner must be added explicitly and the lock repinned | blocked before edit |
| Deterministic Unit Test Shards | four shards plus timing merge | Every new unit node requires measured timing; default estimates are not closure evidence | blocked before edit |
| Static Analysis | Ruff, field-aware identity hygiene, configured Pyright | New behavioral/protocol names and structured fields must pass mutation-backed identity checks | ready after design decision |
| Package Smoke | wheel install and package/import checks | New public contracts must be present only when intentionally exported | ready after design decision |
| Semantic Ingestion Acceptance | warning-strict public acceptance | Later replay/observation acceptance must not be inferred from current traceability tests | future slice |

No deterministic command was run as M4 product evidence because no product,
schema, test, fixture, generated artifact, dependency, or workflow file has
been changed. Baseline M3 CI history remains historical evidence only.

### M4 Identity And Changed-Surface Ledgers

| Surface | Identity | Class | Disposition | Proof/status |
| --- | --- | --- | --- | --- |
| WorkPlan coordinate | M4 | planning/evidence coordinate | retain only in WorkPlan prose | permitted context |
| Prospective event contracts | `SemanticMemoryEvent`, `SemanticMemoryEventBatch`, `SemanticReplayCheckpoint` | behavioral/protocol | retain design-prescribed names only after readiness | blocked before creation |
| Prospective executable names | any name containing M4, R10, R18, phase, round, or task coordinates | prohibited planning-derived identity | reject | field-aware identity gate required |

| Path | Surface class | Scope owner | Authority chain | Required gates | Status |
| --- | --- | --- | --- | --- | --- |
| `docs/work/semantic_ingestion/implementation.plan.md` | implementation governance | M4 coordinator | governing sources -> readiness decision -> milestone plan | `git diff --check`; direct coordinator inspection | current edit |

The blocked authority chain is:
`event_model.md -> semantic_ingestion_architecture.md -> event/schema contracts -> atomic store -> replay/observation authorities -> tests/timing -> pr-gates.yml`.
It cannot advance past the first edge until `SIA-ED-REPLAY-001` is resolved.
There are no known local test failures to classify at this boundary.

### Readiness Reviews And Next Action

- `code-mapper`: confirmed the canonical live path is provider ingestion ->
  semantic pipeline -> terminal persistence -> atomic generation store, and
  confirmed that M3 event inputs are not replay events.
- `spec_auditor`: confirmed the event-model contradiction is an external
  persisted-semantics blocker and that no canonical replay/checkpoint owner
  currently exists.
- `test_reviewer`: confirmed existing tests prove bounded M2/M3 persistence,
  not SIA-R10/R18, and supplied the required equivalence-class matrix and CI
  placement constraints.

Coordinator disposition: the readiness findings were confirmed and are now
resolved by the frozen reviewed design above.

Exactly one next action: use one implementation writer for the bounded rollout
step 1 models, Hermes renderer, validator mutation test, and required PR gate;
then run deterministic local verification and independent closure review.

## Active M1/M2 Defect Remediation

The user authorized correction of four validated product defects before any M3
implementation. This section supersedes every historical `Current next action`
statement below; those statements remain only as chronological evidence.

Remediation eligibility:

- `M1-REM-01`: `P1 / changes_required / runtime compatibility`, SIA-R08,
  SIA-R16, SIA-R19. A canonical bootstrap artifact carries distribution and
  repository/package identity fields that the runtime fingerprint schema
  rejects. The mainstream automatic local bootstrap therefore cannot consume
  its governing artifact. Correct the exact closed fingerprint schema,
  identity rules, domain-separated digest, component-root construction, and
  runtime component verification.
- `M1-REM-02`: `P2 / changes_required / authorization`, SIA-R01 and SIA-R22.
  Ordinary governed ingress derives protected scopes from public event
  `session_id`/`task_id`/`user_id` fields, and the M2 handoff currently
  substitutes an empty set for evidence-only admission. An important hostile
  or misconfigured adapter can therefore reduce or substitute authorization.
  Required scopes must come from host-authenticated message governance and be
  checked against current authorization before any write.
- `M2-REM-01`: `P2 / changes_required / lease fencing`, SIA-R20 and SIA-R21.
  Checkpoint, terminal-group, and finalization entry points recover by request
  digest before validating the current writer, fence, request body, and lease.
  A stale post-reclaim worker can receive success-shaped recovery. Validate the
  complete current authority before exact-generation recovery.
- `M2-REM-02`: `P2 / changes_required / multitenant persistence`, SIA-R11,
  SIA-R20, and SIA-R21. M2 record namespaces use the caller-visible operation
  ID even though two authenticated principals or tenants may validly reuse the
  same public delivery ID. The second authorized delivery collides with the
  first operation. Derive control, artifact, manifest, generation, and lookup
  namespaces from the authenticated operation fence while retaining the public
  operation ID only inside the validated record.

Validation matrix: canonical and mutated fingerprint vectors; distribution
pairing and repository identity; component byte/symbol substitution; public
metadata substitution against authenticated required scopes; exact/superset,
partial, empty, cross-principal and cross-tenant authorization; stale,
expired, reclaimed, writer-rotated, fence-substituted and same-digest altered
checkpoint/group/finalization retries; and same-public-ID cross-principal and
cross-tenant admission/reopen. Focused unit/integration tests, Ruff,
Pyright, diff checks, applicable repository gates, coordinator inspection, and
fresh spec/correctness/test review are required for closure.

Implementation result (2026-08-01): one sole writer corrected all four runtime
owners. Bootstrap fingerprints now implement the closed canonical identity
fields, pairing rule, component/root domains, installed-distribution checks,
component bytes, and symbol resolution. Required scopes are host-authenticated
and remain distinct from current authorization and public event metadata. Every
generation retry validates its recomputed request digest, current writer,
operation fence, and active or exact sealed terminal lease before recovery.
Control, artifact, generation, writer-policy, lease, and lookup paths use the
operation-fence namespace; raw operation-ID compatibility is unique-only and
fails closed when ambiguous.

Coordinator verification (2026-08-01): repository Python 3.12.13 was restored
and the exact affected unit/integration partition passed `121 passed in
85.88s`; the complete `tests/unit/core/semantic_ingestion` directory passed
`130 passed in 82.09s`. Changed-scope Ruff passed and production-owner Pyright
reported `0 errors, 0 warnings, 0 informations`; `git diff --check` passed.
The first restored run exposed and caused correction of the stale raw-ID
writer-policy validator and ambiguous lease API, so static compilation alone
is not treated as behavioral evidence.

Independent review/remediation (2026-08-01): the first final review reproduced
one rolling-upgrade P2: pre-remediation raw operation-ID families could not
resume after the fence-namespace change. Compatibility now records a closed
namespace discriminator for new controls, treats an absent discriminator as a
legacy raw family, preserves that family across every read/write/retry, and
requires exact retained-fence equality before any legacy fallback result. A
foreign tenant sharing the public operation ID cannot read, lease, renew, or
generate against that family. JSONL tests cover legacy reopen/reclaim,
checkpoint/group/finalization, lost acknowledgement and exact retry; modern
checkpoint/group/finalization lost-ack restart; and two tenants sharing one
public ID through independent fence-namespaced generations and reopen.

Final coordinator verification (2026-08-01): the complete affected semantic
ingestion unit and process-safety partition passed `142 passed in 105.32s`;
changed-scope Ruff passed; production-owner Pyright reported `0 errors, 0
warnings, 0 informations`; and `git diff --check` passed. The spec delta review
reported no remaining demonstrated P1/P2 in the selected families. Targeted
correctness and test closure reviews are the sole remaining action.

Closure (2026-08-01): targeted correctness and test reviewers independently
reproduced the final cross-tenant and restart matrices and approved the selected
families with no remaining demonstrated P1/P2 or `changes_required` evidence
gap. The four requested defects and the namespace-compatibility siblings they
exposed are complete at locally verified evidence maturity. No M3 production,
schema, persistence, or test behavior was started.

Current next action: await explicit user direction to begin the separately
bounded M3 implementation milestone.

## M1 Bootstrap Profile Resumption

The approved bootstrap-profile design baseline is
`aae9faa1d7fce59c658308114286a33250245b764b2cef3dde51ad3a47f2f785` for
`docs/design/semantic_ingestion_architecture.md`. M1 is authorized as a
source-only slice: deterministic test signing roots may be fixtures, while
operational root signing/provisioning remains an external release gate and is
not stored in this repository. M1 excludes reservations, fences, leases,
writers, allocations, candidates, graph mutation, and M2/M3 execution.

M1 status: complete and mergeable. The operational HSM/KMS-signed release and separately provisioned host
trust root remain the agreed deployment/shipping gate; deterministic test
authority is not represented as operational evidence.

Historical M1 next action: complete. The former restriction on beginning M2
was superseded by the explicit M2 authorization recorded below.

M2 authorization: the user explicitly authorized starting M2 on 2026-08-01.
The active repository/design baseline is commit
`a76a9a34a69c98060fdb2d7171781e7d942f15a2` with
`docs/design/semantic_ingestion_architecture.md` SHA-256
`e7de038a5cad8f8d95536d60d35621472a79588e100c2da8633a9dd1fcfb5e7a`.
This supersedes the stale M1-only next-action restriction below without
changing the recorded M1 history.

Progress: M1 now has closed source-only contracts, a deterministic test-only
trust fixture, fail-closed release/anchor verification, disposition mapping,
and provider admission wiring. Governed source, protected admission index, and
selection/verification/outcome evidence now publish in one source-only memory
plane transaction. Focused admission/contract tests pass; the one next action
  is complete: the host root is an opaque atomic verification operation, all
  public capability-injection seams are removed, canonical artifact envelopes
  and exact bindings are enforced, and no M2 service is constructible from an
  M1 production root.

Earlier M1 evidence (2026-08-01): the focused direct/factory/Hermes/filesystem,
admission, compatibility, persistence, and failure suite passed 98/98 in 17.71
seconds. Repository Ruff passed, Pyright reported zero errors/warnings, and
`git diff --check` passed. The full unit inventory was also run: 2,264 passed,
136 failed, and 18 errored in 453.70 seconds. Those non-M1 failures are retained
as deferred M2/M3 provider-evolution expectations or stale controlled
traceability authority; they were not skipped, weakened, or used to re-enable
M2. Fresh independent spec, correctness, and test reviewers found no remaining
code-level M1 blocker or reproducible M1 P1/P2 defect. Operational external
signed-release provisioning remains a shipping gate, not local verification.

Mergeability repair evidence (2026-08-01): deferred evolution verification now
uses a `MemoryEvolutionProviderHarness` located exclusively under test support;
the installed core package contains no harness. The production benchmark
runner requires an explicit M2 provider factory and fails immediately with an
M1-boundary error when none is supplied; benchmark verification calls pass the
test-only harness directly, with no ambient pytest monkeypatch. The
declarative CTV authority and heading registry
were regenerated without changing the frozen v1 release body or CTV profile
digest. The final full unit gate passes 2,421 tests with two explicit skips
when this sandbox denies process-semaphore capability; the process assertions
remain unchanged for capable hosts. The affected provider/evolution selection
passes 241/241 and the final benchmark boundary selection passes 32/32. The
post-format authority suites pass 277/277 and the structural authority suite
passes 28/28. Repository Ruff, repository-scoped Pyright, and
`git diff --check` pass.

The three CLI artifact tests that exercise the deferred M2 benchmark retain
their full artifact assertions and explicitly install the test-only provider
composition within each test. The combined affected core-benchmark and CLI
selection passes 52/52; normal production CLI composition remains M1-only.

Final independent delta closure (2026-08-01): the correctness reviewer
confirmed both boundary findings resolved. The M2 harness is excluded from the
installed package, verification callers inject it explicitly, ordinary M1
benchmark calls fail before runtime setup, and no reproducible M1 P1/P2 blocker
remains. The test reviewer found no merge-blocking evidence gap.
- Current implementation-round budget: 50 bounded rounds authorized on
  2026-07-29. One coherent worker implementation, one independent review pass,
  or one consolidated remediation batch counts as one round; focused commands
  and administrative ledger updates within that action do not create separate
  rounds. Full review is reserved for coherent milestones or material contract
  changes; bounded remediation receives delta review.

### Prospective Product-Impact Remediation Control

Starting 2026-07-30, the product-impact remediation gate in
`.agent/PLANS.md` governs all new Layer1 and later review findings. Only a
validated `P1` or `P2` product defect may enter another design or
implementation remediation round. The coordinator must identify the supported
broken scenario, direct canonical-path evidence, requirement, and reason the
scenario is mainstream or important before assigning remediation.

Missing or weak tests, evidence-maturity gaps, approval labels, critical-sounding
invariants, and hypothetical unsupported malformed inputs do not independently
establish P1/P2. Classify them as a predefined bounded evidence action,
record-only follow-up, or external blocker. A review with no newly validated
P1/P2 defect does not open another product-remediation round. Historical review
entries remain unchanged as evidence of decisions made under the earlier
workflow; every unresolved historical claim must pass this gate before any new
remediation.

## M0A-C2 Round-20 Final Blocker

M0A-C2 is blocked after exhausting its authorized 20 design rounds. The
immutable closure report is
`docs/reviews/semantic_ingestion/m0a-c2-round20-non-convergence-2026-07-28.md`.
No C2-dependent implementation, regeneration, approval, or consumption may
proceed from that blocked baseline. At that historical boundary, resumption
required explicit authorization or corrected design authority. The approved
Layer-1 design WorkPlan now supplies a separately frozen replacement boundary
for only the Layer-1 SIA-R03/L1-008/L1-009 milestone; this does not erase or
reinterpret the historical non-convergence record.

Layer-1 implementation handoff: the prior Layer-1 registry/authority baseline
is superseded. The linked heading-default design correction is complete and
approved. Its frozen replacement keeps design `67bf2620...`, validator
`830c63e3...`, checker
`2ca3da2c...`, and profile `20edd38a4...`, while replacing registry
`38c45adc...` with `8e6395e2...` and authority `89a98fc1...` with
`f7c0d000...`. The implementation milestone must now apply the exact 148-member
consumer/state-machine handoff and wire the exact pinned
`check_ctv_binding_authority_v2.py` command from
`docs/development/static_tooling.md` into the repository PR gate. Acceptance
requires a clean checkout to run the pinned design/registry/authority/
validator/checker identities, two hermetic reproductions, all source mutation
self-tests, and fail the PR on any nonzero result. Design review does not claim
that CI integration already exists.

The same milestone must also implement the pending independent-compilation
proof. A separately authored production/reference compiler must share no
parser or normalizer implementation with the design validator, consume only
the frozen design and registry inputs, derive the byte-identical complete
authority (profile, grammar, enum registry, inventory, all normalized graphs,
fingerprints, binding preimages, and binding digests), and exhibit equivalent
fail-closed rejection for the key invalid syntax, declaration, enum, graph,
profile, fingerprint, and binding cases. Two isolated executions of the design
validator prove hermetic deterministic reproducibility only; they are not
independent-compilation evidence.

## Objective

Implement every determinate requirement in the frozen semantic-ingestion design through canonical production paths. Before external activation decisions exist, ordinary composition must fail closed as `profile_unapproved`, retain governed evidence, and produce no learned execution or graph mutation. Completion requires production-path evidence, requirement-appropriate deterministic validation, justified scope, and fresh whole-branch independent review.

## Completion Contract

The implementation completion contract in `.agent/PLANS.md` applies in full. Additionally:

- every SIA-R01 through SIA-R23 row has a production path and proportionate verification;
- every material changed file maps to the Scope Ledger;
- implementation, persisted/public types, tests, prompts, artifacts, migrations, and current-state documentation agree;
- invalid, unsupported, unauthorized, stale, ambiguous, and externally unapproved states fail explicitly and safely;
- validation does not use the implementation under test, production semantic helpers, or benchmark expectations as its own oracle;
- no hard-coded fixture/provider/tenant/language path, bypassed owner, parallel
  truth source, speculative abstraction, or validated P1/P2 implementation
  defect remains;
- no unresolved external authority or semantic decision prevents determinate
  completion, and predefined verification evidence is either complete or
  recorded as unavailable without inflating it into a product defect;
- revision-sensitive evidence binds the frozen design digest and exact candidate tree.

Externally activated topology and statistical certification cannot be claimed until the corresponding signed artifacts exist. Their prescribed pre-approval behavior and artifact-validation paths remain implementation requirements.

## Design Baseline

- Canonical design: `docs/design/semantic_ingestion_architecture.md`
- Active approved Layer-1 design checksum: SHA-256
  `45727e6870e2087823bfe6250c3c3319a3d540e45fb66c686267409b087b2c1c`
- Active Layer-1 repository baseline: commit
  `945d6ea03649ca13c800e84bcb9972797e0f0a31` on
  `live-benchmark-repair`
- Active approved Layer-1 raw registry SHA-256:
  `d38aa788adfb7703d970507f496b903ddf460797fe60274ddd5ebf9c22054c46`
- Active approved Layer-1 authority SHA-256:
  `9f650d2f018e3863ad5f5512bf80dbdac1d22fa584cebe9f868c347a2f0143a4`
- Active Layer-1 validator SHA-256:
  `826541e7864583bbe3c32e3f153c008f07a881f33d38861237dfac80d9f3657e`
- Active Layer-1 checker SHA-256:
  `e2c35870a99e587f34cbffc701f42587520ee015009cd51647367da56716c732`
- Active Layer-1 profile digest:
  `9dc8b3d01e3f78ed6a11c7668cbb576b09f48ddf107c5efe441bb8bad234fd7f`
- Active Layer-1 in-scope requirements: SIA-R03, L1-008, and L1-009
- Active Layer-1 approved deviations: None
- Active Layer-1 unresolved design questions: None
- Superseded Layer-1 registry/authority baseline:
  `38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`
  and
  `89a98fc1e545f38c234ce42dbd164c85e3ddc6358856cca70e59dad7b1addc7b`.
  No implementation or validation command may mix these with the pending
  replacement candidate.
- Historical implementation design checksum: SHA-256
  `158277cd433c85714253359e134c94ece0f3ad59d2b3f1b9a403c295417a397e`
- Historical blocked C2 v3 design baseline: architecture SHA-256
  `f70611d0879bd9daa8dc0c80beab50250d6c99e67b633e37bc6ae9376bfe9f5b`,
  oracle-free recipe SHA-256
  `44698181d560e7a0a5d133ec142448ab247445af4197dbadd27bc7b3ca366291`,
  rejected historical output SHA-256
  `e4875ec3e8afcc8a8410b2dceac8b00b50c296711652695fce80f2eaa46463be`,
  and registry SHA-256
  `38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`.
  This baseline is not approved for implementation.
- Historical C2 round-4 review candidate: architecture SHA-256
  `6637bf82a215ecc9859cb240fc09a4e5e3fa24cd9f6d15b769bdc42007f29798`
  and oracle-free recipe SHA-256
  `65c4fa4e8c2745efd2daa6d103fe5ed0a55a091c8a373ff1d0aaa1ad5b46465b`.
  It remains blocked from implementation pending fresh design approval; all
  pre-round-4 evidence is stale.
- Canonical traceability registry replacement candidate:
  `docs/design/semantic_ingestion/traceability_registry/registry-v1.json`;
  raw-file SHA-256
  `8e6395e2657eb1a51e5eef7d9b88b5d43b974a58f7f786ed135f6758262bfec1`;
  domain-separated source identity
  `6acb473684fdc80a5d89ab44f751ae1f39c9e01ea589a9f4b116f7b0dc116332`.
  The prior raw checksum `38c45adc...` and source identity `66c3414e...` are
  superseded Layer1 inputs; historical earlier values remain historical only.
- Candidate/design-review baseline: commit `237053aef26fae2df7e6b44144e61a1b780bf7ad`
- Production-code assessment baseline recorded by the design: commit `44cd7773a75ac8545ddcf799c76dc94c0240f788`
- Pinned provider compatibility baseline: commit `f76850fc45f09d21a40b5a7302d173ce642ec9d6`, blob `307921e7648fcaf5e11244200a7fb3c1f402e817`, source SHA-256 `38b80a29a991ebfb1076cccc437c2406d43da031982a6c8fe57f755e1e58dbbd`
- Base branch: `live-benchmark-repair`
- In-scope requirements: SIA-R01 through SIA-R23
- Approved deviations: None
- Approved exclusions: natural-language retrieval interpretation, ranking, answer generation, and agent-level quality claims
- External decisions: `SIA-ED-TOPOLOGY-001`, `SIA-ED-REPLAY-001`, `SIA-ED-POLICY-001`, and `SIA-ED-TRACEABILITY-001`
- Known limitation: substantive topology/resource values,
  statistical/monitoring thresholds, and traceability trust
  roots/identities/keys/signed releases are externally owned. The historical
  equal-version replay algebra is resolved and is not an external limitation.

The design is frozen by checksum. A material change stops the affected milestone and requires a linked design WorkPlan and the repository design/review workflow before this baseline can move.

## Scope

Included:

- complete determinate behavior of SIA-R01 through SIA-R23;
- fail-closed pre-approval behavior for all three external-decision gates;
- authenticated admission/recovery/result access, delivery migration, semantic writer ownership, atomic persistence, replay, observations, acceptance isolation, monitoring, production composition, tests, migrations, and current-state documentation;
- independently captured compatibility and traceability evidence.

Excluded:

- retrieval interpretation/ranking/answer generation;
- selecting externally owned topology, statistical, monitoring, resource,
  host, or model values;
- live certification without approved artifacts, credentials, and exact-revision workflow evidence;
- unrelated cleanup or redesign.

Deferred, without weakening fail-closed implementation:

- active learned local/remote capability deployment pending `SIA-ED-TOPOLOGY-001`;
- `SIA-ED-REPLAY-001` is resolved by the frozen fail-closed artifact and is not
  deferred;
- statistical activation thresholds and monitoring values pending `SIA-ED-POLICY-001`.
- traceability release issuance and acceptance pending `SIA-ED-TRACEABILITY-001`; deterministic source/manifest/release/lifecycle validators and fail-closed behavior remain in scope.

## C2 V3 Final Non-Convergence Blocker

The exact v3 baseline above is blocked by the immutable report
`docs/reviews/semantic_ingestion/m0a-c2-v3-non-convergence-2026-07-28.md`.
All earlier M1-M3 elaboration, equality, stability, checked-output, graph,
signature, and vector claims are invalidated. The implementation plan may not
consume the v3 recipe or resume C2 work.

### C2 Round-10 Final Non-Convergence

The user-authorized linked C2 design operation exhausted all ten remediation
rounds without approval convergence. Its immutable final report is
`docs/reviews/semantic_ingestion/m0a-c2-round10-non-convergence-2026-07-28.md`.
The exact blocked baseline is architecture
`93570981d938285ac5201044a365108a0f9d688dd3c78e50d16f15d95a8a88d8`,
recipe
`92ed8a14788a4ea6213f5778f0307a37983468e1bea01858f27eb88759dd6d07`,
reviewed pre-sentinel validator
`8354a23f4f10e9f86d0012f9b3494b34a5815e9ef1e677a143f2805326537b63`,
and registry
`38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`.

C2-dependent implementation remains blocked by the seven confirmed gaps
recorded in that report. The design validator now rejects the exact recipe
with `ROUND10_INCOMPLETE_AUTHORITY`. Do not implement, regenerate, approve, or
consume C2 from this baseline.

Historical round-10 next action: an external design author supplies a corrected
complete oracle-free recipe whose bodies exactly equal authority, whose 25
vectors include 20 concrete mutations, whose graph uses fixture-ID references
only, and whose mutations use one typed common target grammar; or the user
explicitly authorizes a fourth design remediation beyond the exhausted budget.

## Constraints And Invariants

All universal invariants in `AGENTS.md` apply. In particular:

- candidate state is distinct from committed state;
- transport validation is distinct from domain-semantic, provenance, lifecycle, and transaction validation;
- raw source, semantic projection, and segment-local text use distinct closed artifact coordinates;
- current authorization is revalidated but excluded from durable delivery/fence/allocation identity;
- structural graph state is distinct from versioned temporal, trust, status, and identity overlays;
- one canonical semantic writer owns all governed semantic mutation;
- acceptance and benchmark oracle state cannot enter production extraction, reconciliation, persistence, or retrieval;
- public and persisted schemas are typed, closed, version-bound, and fail closed;
- immutable event history is never deleted to represent revision or backtracking;
- provider compatibility envelope bytes remain unchanged.

## Sources Of Truth

Precedence follows `AGENTS.md`:

1. `docs/design/memorii_spec.md`
2. `docs/design/memorii_storage_details.md`
3. `docs/design/event_model.md`
4. `docs/IMPLEMENTATION_RULES.md`
5. `docs/design/semantic_ingestion_architecture.md`
6. `docs/plans/engineering_hardening_closure_matrix.md`
7. `docs/plans/agent_integration_readiness.md`
8. `AGENTS.md`

Workflow and evidence sources:

- `.agent/PLANS.md`
- `.agent/skills/implement-design/SKILL.md`
- `docs/development/static_tooling.md`
- `docs/development/benchmark_certification.md`
- final same-checksum design closure reports under `docs/reviews/semantic_ingestion/`

Current code and tests establish implemented state but do not override approved behavior.

## Current State

Verified at baseline:

- the working tree was clean at `237053aef26fae2df7e6b44144e61a1b780bf7ad`;
- the design contains 23 normative requirements and three external-decision gates;
- the revised design contains 23 normative requirements and four external-decision gates;
- the pushed commit changed design/review/WorkPlan artifacts, not the provider/storage/factory compatibility surfaces;
- `ProviderEvolutionOutcome` at HEAD is byte-identical to the pinned Git blob;
- no SIA requirement is complete.

Partial reusable mechanisms:

- SIA-R02: typed extraction, semantic compilation, grounding, claim policy, and graph validation;
- SIA-R06/R12/R18: temporal/lifecycle models and partial graph history/lineage;
- SIA-R07: prompt registry, renderer, schema binding, and redaction;
- SIA-R10/R20/R21: operation CAS/fencing/recovery, memory-plane unit of work, and crash-atomic JSONL batch replacement;
- SIA-R22/R23: frozen provider lifecycle envelope, caller delivery ID, and restart replay.

Missing cross-cutting owners:

- authenticated semantic source admission and protected result-access index;
- closed SIA contract family and canonical codec profile;
- semantic writer epoch/cutover authority;
- multi-authority atomic generation, semantic event/observation/artifact replay;
- independent linguistic/scope/temporal consensus;
- source-bound egress governance;
- acceptance trust/release isolation, topology authorization, statistical gate, monitor, and structural observation API;
- R03 traceability and trusted execution-evidence tooling.

The former missing-registry ambiguity is resolved by the revision-3 canonical source package. It provides 144 explicit heading defaults matching all 144 Section 1-5 numeric headings, 23 requirement bindings, one structural rule registry, assertion/report/runner/test-group roots, overrides, anchors, and artifact DAG. Real trust/release values remain externally withheld, so acceptance must fail closed without them.

## Assumptions And Open Questions

Verified facts:

- the same-checksum final closure review treats C3/C4 as post-authorization rollout gates;
- pre-approval `profile_unapproved` behavior is determinate;
- the three external choices are fully registered with exact fail-closed behavior and unblock conditions.

Working assumptions:

- literal placeholders resolve to Work ID `semantic_ingestion`, the supplied absolute design path, and base branch `live-benchmark-repair`;
- implementation milestones may complete determinate pre-approval paths while externally activated/certified claims remain unavailable.

Unresolved questions:

- exact package/file subdivision inside the canonical owners will be chosen by the milestone worker after searching existing contracts, then recorded as decisions;
- whether a compliant Python >=3.11 project environment already exists locally remains to be established before validation.

Decisions requiring external input:

- only the four registered `SIA-ED-*` artifacts. They do not block implementation of prescribed fail-closed behavior.

## Current-System Map

Production flow:

`HermesMemoryProvider` -> `ProviderMemoryService` -> `ProviderIngestionCoordinator` -> `MemoryPlaneService.prepare_provider_event` -> raw transcript records plus `EvolutionCoordinator` -> `MemoryEvolutionService` -> extraction/semantic compilation/validation/claim policy -> memory graph and generic memory-plane writes.

Composition roots:

- `memorii/memorii/core/provider/factory.py`
- `memorii/memorii/core/filesystem_storage/bundle.py`
- direct `ProviderMemoryService` construction in `memorii/memorii/core/provider/service.py`
- `memorii/memorii/integrations/hermes_provider.py`

Canonical reusable owners:

- source/transcript and generic records: `memorii/memorii/core/memory_plane/`
- provider boundary and pinned envelope: `memorii/memorii/core/provider/`
- extraction, semantic compilation, temporal/lifecycle projection, leases: `memorii/memorii/core/memory_evolution/`
- prompt authority: `memorii/memorii/core/prompts/` and `memorii/memorii/core/llm_provider/`
- execution/solver events only: `memorii/memorii/domain/events.py`, `memorii/memorii/stores/event_log/`, `memorii/memorii/core/persistence/replay.py`
- filesystem generation substrate: `JsonlMemoryPlaneStore`

Finite governed-writer inventory:

1. `MemoryPlaneService.write_records`, `stage_record`, `upsert_record`, `conditionally_write_records`, `commit_candidate`, and `seed_runtime_memory_object`.
2. `MemoryPlaneStore` concrete `write_records`, `upsert_record`, and `apply_batch`.
3. `MemoryGraphStore.upsert_snapshot`.
4. Direct `MemoryEvolutionService` completion/entity-link/contradiction/source/progress/temporal-anchor writes.
5. Claim-policy persistence writes.
6. Evolution operation repository and initial source/operation batch.
7. Provider no-transcript fallback write.
8. Candidate-promotion executor.
9. Work-state projection writes; these must be classified as governed semantic or explicitly non-semantic.
10. Provider and Hermes ingress hooks.
11. Test/benchmark constructors and direct writes, which enter the migration certificate but are not production writers.

The generic store is a technical choke point, not the semantic owner. A typed semantic-ingestion atomic-store facade must gate governed writes without making unrelated memory domains depend on semantic-ingestion policy.

## Requirement Coverage Ledger

| Requirement | Required behavior | Implementation | Validation | Status |
| --- | --- | --- | --- | --- |
| SIA-R01 | Exact source/provenance admission, authenticated scope, stable delivery identity and recovery | Raw transcript/replay substrate only; governed admission absent | Admission conformance, scope/auth/recovery/replay/failpoint tests | not started |
| SIA-R02 | Candidate-only model output through all semantic and commit gates | Proposal-only typed transport, one bounded registered repair, source-derived independent analysis, and terminal persistence implemented; proposer evidence fields and local/remote path mixing reject | Named `SIA-T02-CANDIDATE-*` plus malformed/repair, substitution, zero-effect, and accepted-control tests pass locally | M3 implementation candidate; review pending |
| SIA-R03 | Canonical registry, dual structural manifest, revision-bound trusted execution evidence and fail-closed release gate | C1 is historically complete; the Layer1 independent compiler and PR wiring exist, but the approved 148-member registry/authority replacement has not yet been applied to both loaders and all consumers; later M0A ancestry/acceptance owners remain blocked | Corrected design slice proves exact 148/148 mapping and CTV authority; parent must repin/load/verify the complete registry, manifest, execution, release, workflow, and four-marker paths before Layer1 closure | in progress |
| SIA-R04 | Closed typed pipeline contracts with exact governance/attempt/plan/result lineage | Closed M3 contracts now bind proposal-attempt, source-analysis, sealed-operation, prompt, egress, immutable policy-pair, carrier, binding-set, and persistence lineage | Named `SIA-T04-LINEAGE-*`, codec, cross-operation/role swap, lost-ack, reopen, and exact retry tests pass locally | M3 implementation candidate; review pending |
| SIA-R05 | Independent certified role/scope/attribution/attachment evidence | Proposal carries only alignment hints; independent source analysis exclusively owns parser, scope/voice/negation, attribution, identity, attachment, and temporal evidence | Named `SIA-T05-CONSENSUS-*`, assessor substitution, analyzer disagreement, attachment mutation, and role-crossing tests pass locally | M3 implementation candidate; review pending |
| SIA-R06 | Independent textual time plus closed authenticated-evidence matrix | Complete immutable policy-bundle resolver implements required/optional/atemporal, authenticated reference-open-start, eligibility/rank/equality/contest, provenance retention, and no stitching | Named `SIA-T06-TEMPORAL-*` and every `SIA-T06-TR-*` ledger suffix pass in the self-contained integration owner | M3 implementation candidate; review pending |
| SIA-R07 | Registered prompt/schema/owner/redaction/visibility authority | Strict proposal-only semantic prompt, schema-parity model, runtime owner, immutable prompt binding, sanitized trace/wire metadata, and no raw request bypass implemented | Named `SIA-T07-PROMPT-*`, prompt conformance, owner/substitution, redaction, and serialized-source tests pass locally | M3 implementation candidate; review pending |
| SIA-R08 | Certified local-first path after approval; preapproval evidence-only | Active legacy factory; topology gate absent | Preapproval factory/no-network/no-fallback and postapproval artifact tests | not started |
| SIA-R09 | Current per-segment source-bound remote egress authorization | Remote execution requires exact registered prompt plus current source/segment egress binding; each bounded wire attempt revalidates signed lifecycle/CAS authority and records its decision digest | Named `SIA-T09-EGRESS-*`; denial, substitution, revocation, stale CAS, and repair rotation remain zero wire | M3 implementation candidate; review pending |
| SIA-R10 | Canonical semantic events, terminal observations, artifact-closed replay | Bounded immutable preplanning introduction and exact artifact closure implemented; full events/observations/replay remain M4 | Introduction idempotency and generation closure pass; genesis/checkpoint/collision/corruption are blocked by the governing equal-version replay conflict | blocked |
| SIA-R11 | One certified writer with epoch, migration, drain, cutover and rollback | Complete M2 writer/method inventory, exact bindings, store-inspected drain, certified coordinate migration with target projections, monotonic cutover, and forward-only rollback are implemented across direct/generic/provider roots | In-memory/JSONL stale/forged binding, migration/collision/reopen/rollback, active lease, and paused cross-cutover process tests pass | M2 complete |
| SIA-R12 | Closed discriminated temporal/lifecycle algebras end to end | Closed M3 proposal, analysis, policy bundle, temporal/reference/atemporal carrier, lineage, terminal, event-input, observation, group, and artifact codecs reject legacy/unknown variants | Named `SIA-T12-PIPELINE-*` plus round trips, wrong-kind, role, provenance, and digest mutations pass locally | M3 implementation candidate; review pending |
| SIA-R13 | Lifecycle-bound acceptance evidence isolated from production, including traceability bootstrap/recovery/release trust | C1 test-only RFC 8032 fixture keys/profile are extracted from the corrected frozen design, pinned, and isolated; no operational acceptance owner exists | C1 design-table/fixed-vector/invalid-hex and production-import isolation tests pass; fresh C1 review and lifecycle/acceptance gates remain required | in progress |
| SIA-R14 | Predeclared independent statistical certification for every lane | Existing benchmark tooling is not SIA certification | Independent recomputation and manifest completeness | not started |
| SIA-R15 | Deterministic typed capability monitoring | Absent | Fake-clock boundary/race/outage/recovery state-machine tests | not started |
| SIA-R16 | One authorized dependency/resource topology | Config/factories only; authorization absent | Bidirectional manifest/package/asset/profile mutation tests | not started |
| SIA-R17 | Direct authenticated structural observation and independent closed oracle | Existing benchmark oracle is insufficient | Global-bijection/comparator/cursor/auth/revocation/import-boundary tests | not started |
| SIA-R18 | Replayable history, trust evolution and identity lineage | Partial graph history/identity substrate | Temporal/trust/lineage prefix and migration-race replay matrices | blocked by `SIA-ED-REPLAY-001` before implementation |
| SIA-R19 | Normal production roots use selected owner and no legacy writer | Provider, Hermes, and filesystem roots discover one host-installed, authorization-bound runtime builder; public constructors expose no caller-owned M3 activation/dependency controls | Normal-root shared-pipeline, absent/ambiguous capability, and unauthorized-runtime evidence-only tests pass; full topology activation remains later certification scope | M3 composition candidate; review pending |
| SIA-R20 | Renewable fenced leases, bounded recovery, stable allocation namespace | M2 lease controls now cover M3 before proposal through finalization, renew across learned-stage boundaries, content-address stage progress, reacquire expired same-owner leases, and expose immutable terminal exhaustion | Fake-clock same-owner reclaim/exhaustion, stage checkpoint, stale-token, lost-ack/reopen, active-lease cutover, and process fencing tests pass | M2 complete; M3 integration candidate review pending |
| SIA-R21 | Process-safe crash-atomic admission/progress/group/finalization generations | All M2 transactions plus M3 learned-stage checkpoints publish through guarded in-memory/JSONL generations with exact control/graph/observation/read-set/artifact/writer/lease CAS | Admission/stage/checkpoint/committed/non-committing/finalization, failpoint, reopen, lost-ack, and concurrent-delivery tests pass | M2 complete; M3 integration candidate review pending |
| SIA-R22 | Frozen provider envelope plus sole opaque authorized semantic-result lookup | M0B envelope compatibility verified; lookup/index/repository remain absent and are reserved for M1+ | M0B independent baseline bytes/schema/corpus/public-path/legacy-reader gate passes; authorization-spy tests remain planned for M1 | M0B complete; M1 pending |
| SIA-R23 | Byte-preserving delivery normalization, governed envelopes and composite replay | Legacy stripping normalizer and replay only | Cross-adapter Unicode/byte/migration/fan-out/restart tests | not started |

## Scope Ledger

| Change | Classification | Requirement | Rationale | Status |
| --- | --- | --- | --- | --- |
| Maintain this implementation WorkPlan and immutable reports | required | SIA-R03 | Durable governance and evidence | in progress |
| Independent design structure/coverage/evidence tooling | required | SIA-R03 | Prevent prose-only and stale/circular completion claims | planned |
| Wire the pinned CTV Layer-1 authority command into the repository PR gate | necessary enabling work | SIA-R03 | Design-only validation is not enforced until CI invokes the exact content-addressed hermetic command | active Layer1 milestone |
| Implement a separately authored CTV Layer-1 production/reference compiler | necessary enabling work | SIA-R03 | The design validator's two isolated runs prove deterministic hermetic reproduction, not independent compilation; an implementation sharing no parser/normalizer code must derive the same full authority and reject equivalent invalid cases | active Layer1 milestone |
| Frozen provider compatibility corpus | required | SIA-R22 | Preserve independently captured legacy bytes and validators | planned |
| Canonical ingestion contracts, codec and source governance | required | R01, R04, R12, R23 | Establish trusted typed boundary before orchestration | planned |
| Authenticated ingress, admission/recovery authorization and protected index | required | R01, R09, R22, R23 | Remove caller authority and prevent result disclosure | planned |
| Delivery-coordinate migration and composite fan-out recovery | required | R11, R23 | Preserve replay while activating exact-byte v1 coordinates | M2 complete; later replay consumers remain M4 |
| Semantic writer manifest/epoch/cutover | required | R11, R20, R21 | Gate every governed writer and mixed-version process | M2 complete |
| Atomic semantic store and generation publication | required | R10, R20, R21 | Couple source/control/graph/event/observation/artifact visibility | M2 complete; full replay remains M4 |
| Candidate analysis/reconciliation/terminal pipeline | required | R02, R04-R07, R09, R12 | Implement semantic correctness and fail-closed outcomes | implementation candidate; independent review pending |
| Semantic event/replay/history/lineage projection | required | R10, R18 | Deterministic reconstruction and immutable history | planned |
| Deployment authorization, preapproval composition and monitoring | required | R08, R15, R16, R19 | Replace ungated active composition safely | planned |
| Acceptance trust, statistics, observation and closed oracle | required | R03, R13, R14, R17 | Independent non-production proof | planned |
| Current-state, migration, rollout and rollback documentation | required | R03, R08, R11, R16, R19, R23 | Keep operational truth aligned | planned |
| Retrieval ranking/query interpretation/answer generation | excluded | None | Explicit design non-goal | excluded |
| External topology/replay/policy values | deferred | R08, R10, R14-R16, R18, R19 | Externally owned; fail-closed behavior still implemented | deferred |
| Existing unrelated repository behavior and cleanup | unrelated | None | Preserve user scope | excluded |

Every changed file will be added to this ledger with its requirement mapping during its milestone.

## Validation Matrix

| Requirement | Main risk | Verification level | Evidence and observable failure | Status |
| --- | --- | --- | --- | --- |
| R01 | Derivation before durable authorized source or identity drift | Backend contract + process/failpoint integration | Missing source/provenance, partial scopes, forged recovery, or auth rotation mutates/forks identity | planned |
| R02 | Candidate output commits after any failed gate | Production-path integration + adversarial mutations | Any malformed/unsupported/partial candidate produces graph/event delta | planned |
| R03 | Circular or stale traceability evidence | Two independent static tools + mutation tests | Missing/orphan unit, wrong tree/design digest, unexecuted/forged evidence passes | planned |
| R03 Layer-1 PR enforcement | Reviewed authority gate can be bypassed by omission | Clean-checkout CI execution of exact pinned static-tooling command | Any changed identity, nonreproducible output, rejected mutation, or nonzero validator result fails the PR | active Layer1 milestone |
| R03 Layer-1 independent compilation | Design validator is mistaken for an independent implementation | Separately authored production/reference compiler with no shared parser/normalizer implementation | From the frozen design and registry it derives the byte-identical full authority and returns equivalent rejection for key invalid syntax, declaration, enum, graph, profile, fingerprint, and binding cases | active Layer1 milestone |
| R04 | Invented or cross-bound IDs/carriers/statuses | Schema/property tests + definition/reference audit | Round trip accepts dangling/substituted lineage or ambiguous planning state | planned |
| R05 | Surface words accepted with wrong semantic roles/scope | Independent analyzer integration + metamorphic/minimal pairs | Disagreement, ambiguity, negation or attribution mutation promotes | planned |
| R06 | Temporal omission/misattachment changes truth | Matrix/property/replay tests with fake clock | Missing proposer time, wrong basis/attachment, DST mutation promotes or replays differently | planned |
| R07 | Prompt substitution or secret leakage | Registry-to-transport contract + byte-capture integration | Wrong digest/owner/schema reaches provider or secret appears in bytes/traces | planned |
| R08 | Unapproved or fallback capability mutates | Production factory integration + network denial | Preapproval learned call/graph effect or silent proposer switch occurs | planned |
| R09 | Stale/mismatched egress reaches wire | Real adapter capture endpoint + policy mutation/race tests | Any denied/stale/swapped decision creates wire activity | planned |
| R10 | Replay diverges or exposes dangling artifacts | Genesis/checkpoint integration + corruption/failpoints | Reconstructed graph/control/observation differs or partial generation becomes visible | planned |
| R11 | Stale/legacy writer bypasses epoch | Static inventory + multiprocess/mixed-version migration tests | Binding-free/stale writer changes revision or incomplete generation activates | planned |
| R12 | Impossible/unknown lifecycle or temporal state survives | Exhaustive discriminated schema round trips | Unknown variant or basis/provenance substitution deserializes | planned |
| R13 | Acceptance authority leaks into production | Trust-lifecycle contract + AST/import/package boundary | Revoked/wrong-purpose release validates or production imports acceptance types | planned |
| R14 | Missing lane or self-calculated metric activates | Independent event-level recomputation | Omitted lane, invalid multiplicity/cluster/bound, or stale evidence passes | planned |
| R15 | Nondeterministic or stale capability state | Pure state-machine/property + fake-clock race tests | Same policy/evidence differs or breach/staleness remains active | planned |
| R16 | Unsupported dependency/profile activates | Signed artifact and bidirectional manifest mutation tests | Missing/extra/duplicate asset/license/owner/profile validates | planned |
| R17 | Oracle undercompares or leaks structure | Production observation E2E + independent comparator | Ambiguous alignment succeeds, unexpected record ignored, or unauthorized query discloses | planned |
| R18 | Late arrival/migration/identity change loses history | Prefix/replay/migration contention matrices | Current/history/contested/lineage views differ after reorder/rekey/merge/split | planned |
| R19 | Normal roots retain legacy/fallback writer | Default-constructor integration for every profile/root | Factory bypasses coordinator or claims active before authorization | planned |
| R20 | Stale lease commits or reclaim changes IDs | Fake-clock + multiprocess/crash/restart tests | Old token writes, allocation bytes change, or recovery budget never terminalizes | planned |
| R21 | Partial transaction/generation visible | Backend-neutral conformance + deterministic failpoints | Reader sees subset, lost-ack duplicates, corrupt generation reopens | planned |
| R22 | Legacy wire drift or result lookup leaks | Independent frozen corpus + auth/repository-spy E2E | Any envelope byte/validator drift or repository read precedes authorization | planned |
| R23 | Delivery normalization collides or composite replay duplicates | Cross-adapter golden/property + migration/process tests | Whitespace/NFC/case bytes change, collision activates, or completed child repeats | planned |

Each milestone must name exact test IDs/commands, the behavior proved, defect detected, appropriateness of level, and failure signal before its worker starts.

### Layer1 Independent Compiler Validation Matrix

Implementation round 1 independently challenged the Layer1 matrix before
compiler coding. The six proposed gaps are confirmed as
`Not applicable / changes_required / verification or CI evidence`: they concern
proof completeness, isolation, and automation rather than a demonstrated
product-behavior P2 scenario. The worker must close these families as one
coherent milestone rather than one case per review round.

| Family | Required scenarios | Pass/fail signal |
| --- | --- | --- |
| Baseline and full-byte equality | Two fresh Python 3.12 processes compile frozen design plus registry | Exact authority bytes/SHA, 56 schemas, 240 enums, and profile digest match; first byte/path difference is reported |
| Syntax and grammar | Marker, fence, grammar-row, duplicate, omission, and malformed-source families plus valid controls | Invalid input exits nonzero before publication; valid controls compile |
| Declarations | Class/class, alias/alias, both cross-kind orders, identical duplicates, bases, bodies, defaults, dynamic forms, forward refs; positive direct/alias/quoted/inherited/tagged-union controls | Invalid forms reject; positive graphs preserve owner and order semantics |
| Enum | Missing/extra/duplicate/type-confused members, aliases, inline literals, inherited owners, order/substitution, empty enum | Invalid rows reject; valid mutation changes enum digest and dependent bindings |
| Graph | Unresolved/recursive/cyclic/open/dynamic/unsupported annotations, inheritance, discriminator, edge/subtree substitutions; positive nested/alias/inherited/union controls | Invalid graph rejects without output; valid mutation changes only affected graph/fingerprint/binding |
| Profile | ID/version/grammar/preimage/domain/length/digest changes and one valid profile mutation | Mismatches reject; valid mutation changes profile and every dependent binding |
| Fingerprint | Graph bytes, domain/version/length/schema coordinate, supplied preimage/digest | Tampering rejects; valid graph mutation changes fingerprint and binding |
| Binding | Profile/schema/version/enum/fingerprint/policy/domain/length/preimage/digest substitutions | Recomputed values agree; mismatch rejects with no partial output |
| Cross-implementation rejection | Hand-authored invalid corpus for every family, not generated by the design validator | Both implementations return the same accept/reject verdict and publish no output on rejection; diagnostic text need not match |
| Design-validator public publication | Final reviewed validator/checker; direct, quoted-child, nested, alias, inherited, reachable/unprojected invalid collection/type family; absent and pre-seeded targets; valid controls | Invalid subprocess exits nonzero and leaves absent target absent or seeded bytes/mode identical with no temp sibling; partial-write/file-fsync/replace failures preserve prior state; real post-replace directory-sync failure surfaces with complete new bytes; unsupported sync succeeds; valid subprocess atomically publishes exact checked-authority bytes |
| Isolation | Static dependency scan plus runtime file/process/network audit; validator, checked authority, recipe, fixtures, corpus, and production package absent | Forbidden dependency/event fails; compiler succeeds with only its source, frozen design, registry, stdlib, and output |
| Anti-replay controls | Valid semantic mutations for grammar, declaration/graph, enum, profile, and binding inputs | Compiler emits changed internally consistent authority rather than replaying frozen bytes |
| Determinism and environment | Fresh directories with varied hash seed, locale/TZ, umask, and cwd under Python 3.12 | Output bytes remain identical; no ambient time/path/randomness |
| Compatibility and rollback | V1-only source mutation, V1/V2 substitution, mixed identities, restored complete bundle | V1-only mutation leaves V2 stable; mixed identities reject; restored bundle reproduces itself |
| CI enforcement | Fresh-checkout Python 3.12 job runs independent matrix and exact checker; mutate each pinned file and force invalid compiler case | Every mutation/nonzero result fails the dedicated PR job |

Static scanning alone cannot prove independent authorship. Implementation must
also record separate authorship, prohibit shared parser/normalizer code, and
pass runtime isolation with the validator and checked authority absent.

## Test And Evidence Manifest

Evidence ownership rules:

- production behavior tests exercise public/provider/filesystem boundaries or the typed canonical owner, not private helper call counts;
- deterministic fakes may control clocks, faults, signatures, or provider bytes but may not derive expected semantic output from the implementation or fixture expectation under test;
- R03 structure/coverage and trusted-execution verification use separately implemented code paths and mutation corpora;
- R17 acceptance code imports no production semantic helper, and production imports no acceptance/oracle type;
- R22 fixtures are extracted from the pinned baseline blob in an isolated worktree/environment and are immutable target-test inputs;
- concurrency/recovery tests use deterministic failpoints plus subprocess execution; uncontrolled scheduling alone is insufficient;
- live/operational evidence is never replaced by dry-run, fake-provider, or unit evidence.

| Milestone | Test/evidence IDs and planned paths | Level and failure signal |
| --- | --- | --- |
| M0 | `SIA-T03-STRUCT-*`, `SIA-T03-EVIDENCE-*` in `memorii/tests/unit/tools/test_semantic_ingestion_traceability*.py`; `SIA-T22-COMPAT-*` in `memorii/tests/unit/core/semantic_ingestion/test_provider_compatibility.py`; immutable corpus under `memorii/tests/fixtures/semantic_ingestion/provider_compatibility/` | Independent static/tool contract tests. Missing/orphan/duplicate structure, wrong digest/revision, failed/unexecuted/forged evidence, or any legacy byte/schema/validator mutation must fail. |
| M1 | `SIA-T01-ADMISSION-*`, `SIA-T04-CONTRACT-*`, `SIA-T08-PREAPPROVAL-*`, `SIA-T12-ALGEBRA-*`, `SIA-T19-ROOT-*`, `SIA-T22-LOOKUP-*`, `SIA-T23-DELIVERY-*` under `memorii/tests/unit/core/semantic_ingestion/` and `memorii/tests/integration/test_semantic_ingestion_admission.py` | Schema/property plus provider/Hermes/filesystem integration. Unauthorized or malformed input must cause zero provider/reservation/graph reads or writes; preapproval roots retain evidence but make zero learned calls/effects; legacy bytes remain exact. |
| M2 | `SIA-T10-ATOMIC-*`, `SIA-T11-WRITER-*`, `SIA-T20-LEASE-*`, `SIA-T21-GENERATION-*` under unit storage tests and `memorii/tests/integration/test_semantic_ingestion_process_safety.py` | Backend conformance, deterministic failpoints, subprocess contention/restart. Readers see old or complete generations only; stale/binding-free writers and tokens cannot change revisions. |
| M3 | `SIA-T02-CANDIDATE-*`, `SIA-T04-LINEAGE-*`, `SIA-T05-CONSENSUS-*`, `SIA-T06-TEMPORAL-*`, `SIA-T07-PROMPT-*`, `SIA-T09-EGRESS-*`, `SIA-T12-PIPELINE-*` under unit contract/property tests and `memorii/tests/integration/test_semantic_ingestion_pipeline.py` | Independent analyzer fixtures and controlled capture transport through the canonical production coordinator. Any ambiguity, disagreement, malformed candidate, prompt substitution, or stale policy yields terminal evidence and zero graph/wire effect. |
| M4 | `SIA-T10-REPLAY-*`, `SIA-T18-HISTORY-*` under unit replay/property tests and `memorii/tests/integration/test_semantic_ingestion_replay.py` | Genesis/checkpoint, order/permutation, migration and corruption integration. Reconstructed bytes/views must match or conflict must reject before exposure. |
| M5 | `SIA-T03-RELEASE-*`, `SIA-T08-ACTIVATION-*`, `SIA-T13-TRUST-*`, `SIA-T14-STATS-*`, `SIA-T15-MONITOR-*`, `SIA-T16-TOPOLOGY-*`, `SIA-T17-OBSERVE-*`, `SIA-T19-ACTIVE-ROOT-*` under acceptance-only unit/integration/package tests | Independent trust/statistics/comparator, fake-clock monitor, signed-artifact mutation, observation authorization/cursor, no-network factory and package-boundary proof. Any stale/revoked/incomplete artifact or unauthorized observation fails without disclosure or mutation. |

Per-milestone evidence records must contain the frozen design digest, candidate tree digest, command, working directory, interpreter/version, exit status, collected test IDs, artifact digests, and reviewer round. M0 will define the typed evidence record and verifier before later milestones emit completion evidence.

## Change Map

Expected canonical change areas:

- new semantic-ingestion contracts/services under `memorii/memorii/core/` with explicit owners rather than a monolith;
- provider ingress, ingestion coordinator, factory, filesystem bundle, and Hermes adapter as thin integration boundaries;
- memory-plane/store protocols only where necessary to host a typed atomic semantic transaction boundary;
- memory-evolution compiler/leases/graph/history reused behind the new coordinator;
- prompt/LLM transport extended through registered source-bound authority;
- acceptance-only tooling outside production core, with static import/package isolation;
- SIA-specific unit, contract, integration, process, migration, rollback, and acceptance tests;
- current-state and operational documentation.

Non-applicable except for explicit typed handoff/import-boundary checks:

- retrieval ranking and answer generation;
- execution/solver graph semantics;
- host-framework-specific business logic in core.

## Migration, Rollout, And Rollback

Migration:

1. Capture immutable R22 provider fixtures before target changes.
2. Inventory all public/raw child delivery IDs and governed writer entry points.
3. Build a content-addressed target delivery-coordinate generation from preserved evidence.
4. Reject ambiguity/collision absent evidence-backed owner disposition.
5. Backfill reference/writer manifests and independently certify complete source/reference coverage.
6. Drain or terminalize old-epoch operations.
7. Atomically publish the complete target generation and advance the writer epoch.
8. After activation, read/write only typed target coordinates; preserve immutable legacy evidence.

Rollout:

- shadow/acceptance evidence first;
- ordinary composition is `profile_unapproved`, evidence-only, with zero learned call/graph mutation before signed topology/profile authorization;
- activate one exact approved capability bundle at a time;
- remote proposal remains explicit opt-in plus current per-source authorization;
- C3 default-active composition and C4 exact-revision live certification apply only to the authorized candidate.

Rollback:

- rollback authority is named by the topology artifact;
- deactivate to evidence-only atomically;
- never reactivate legacy writers or silently switch proposers;
- preserve event/source/observation/artifact history and delivery mappings;
- use the certified prior generation/epoch only under the design's monotonic authorization rules.

Mixed-version behavior:

- old/binding-free writers cannot change governed semantic state after cutover;
- in-flight old-epoch work drains or terminalizes before epoch advance;
- cross-cutover replay executes only missing composite children and cannot duplicate effects;
- non-identical historical equal-version replay rejects under the resolved
  `SIA-ED-REPLAY-001` artifact.

## Milestones Or Experiments

### Layer1 - Independent CTV compiler and enforced hermetic gate

- Requirements: SIA-R03, L1-008, L1-009.
- Observable behavior: a separately authored compiler consumes only the frozen
  design and registry, derives the byte-identical complete Layer-1 authority,
  and rejects the key invalid syntax, declaration, enum, graph, profile,
  fingerprint, and binding cases equivalently; every PR executes the exact
  pinned hermetic checker and fails on any nonzero result.
- Canonical owners: a new production/reference compiler that shares no parser
  or normalizer implementation with the design validator; the repository's
  existing PR workflow for gate invocation. The design validator remains the
  design oracle and must not be imported or copied into the independent
  compiler.
- Expected changes: the smallest implementation module and behavioral tests
  needed for independent compilation, the existing PR workflow, current-state
  documentation, and this WorkPlan's ledgers. No schema, authority, design,
  product-runtime, persistence, migration, or public API change is authorized.
- Verification: compare the independently produced complete authority
  byte-for-byte with SHA-256
  `f7c0d00080b02343f57fc69adee47ef0d7db1846641b1a7bb11fc7bc0b97c74e`
  from registry
  `8e6395e2657eb1a51e5eef7d9b88b5d43b974a58f7f786ed135f6758262bfec1`;
  run a cross-implementation key-rejection matrix; run the exact command in
  `docs/development/static_tooling.md` from a clean checkout; prove the PR gate
  fails for identity drift, reproduction disagreement, mutation acceptance, or
  any nonzero checker result; run focused Ruff, Pyright 3.12, compilation, and
  repository diff checks.
- Non-goals: changing the reviewed replacement design/registry/authority
  bytes, reusing the design parser/normalizer, repinning or implementing the
  blocked M0A-C2 authority, modifying product runtime behavior, or claiming
  external certification.
- Completion: independent full-authority equality and equivalent key
  rejection pass; the exact hermetic gate is enforced in PR CI; every changed
  file is justified; fresh `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer` passes leave no confirmed `blocks_approval` or
  `changes_required` finding.
- Status: complete for the bounded Layer1 replacement milestone; round-20
  whole-scope review and targeted delta verification left no validated P1/P2
  defect, and the complete focused partition passes locally

### M0 - Independent proof and compatibility foundation

- Requirements: R03, R13, R22
- Observable behavior: two independent canonical-registry/structural-manifest paths reject incomplete, stale, forged, noncanonical or wrong-revision coverage; lifecycle/release validators reject absent or self-authorizing external roots; target tests consume a separately captured immutable provider baseline corpus.
- Owners/artifacts: canonical registry loader, independent structural generator/checker, fail-closed lifecycle/release/evidence verifier, acceptance fixture extractor, immutable fixture data.
- Persistence/compatibility: no production semantic behavior; provider envelope remains unchanged.
- Tests: structure/coverage/evidence mutations; schema/enum/default/nullability/validator/canonical-byte fixtures.
- Non-goals: ingestion contracts, active composition, graph writes.
- Completion: both canonical-registry/manifest paths, absent-root fail-closed lifecycle/release gate, evidence verifier, and frozen compatibility corpus pass independent mutation tests; exact paths/digests/commands are recorded. External release acceptance remains unavailable rather than simulated.
- Status: blocked outside the active Layer1 replacement boundary

### M1 - Authenticated governed source admission and safe ordinary roots

- Requirements: R01, R04, R08, R12, R19, R22, R23
- Observable behavior: exact source/provenance and governance carriers persist atomically before derivation; durable identity is stable across authorization rotation; recovery/result lookup is authenticated and non-disclosing; provider envelope is unchanged; every ordinary root is `profile_unapproved`, evidence-only, with zero learned call or graph effect before authorization.
- Owners: ingestion contracts/codec, ingress resolver, source normalizer/store, protected admission index, delivery migration, provider/Hermes thin adapters.
- Persistence: admission generation, typed public/composite delivery coordinates, pre-planning state.
- Tests: invalid/partial scopes, cross-principal/tenant, replay/conflict/lost ack, Unicode/whitespace/collision, lookup repository-spy, composite fan-out, every provider/Hermes/filesystem root with extractor/wire/lease/graph spies.
- Non-goals: active semantic promotion, approved topology values, and learned calls.
- Completion: all admission roots use the canonical owner and no unauthorized read/mutation path exists.
- Status: complete. M1 is merged at `a76a9a34...`; its source-only admission,
  bootstrap-profile, provider-envelope, protected-result, and ordinary-root
  contracts passed the recorded full verification and independent closure
  reviews. Operational HSM/KMS release signing and separately provisioned host
  trust remain deployment gates, not incomplete M1 source implementation.

### M2 - Single writer, leases and atomic generations

- Requirements: R10, R11, R20, R21
- Observable behavior: one current semantic writer/fence publishes complete source/control/graph/event/observation/artifact generations; stale writers and partial failures have zero visibility.
- Owners: semantic atomic-store protocol, writer manifest/epoch, operation/lease/allocation coordinator, filesystem generation adapter.
- Migration: finite writer inventory, target certificate, drain/cutover/rollback.
- Tests: every writer entry point, mixed process/version, failpoints, crash/reclaim, slow renewal, lost ack, corruption/reopen, idempotent retry.
- Non-goals: learned semantic acceptance.
- Completion: backend conformance and migration/cutover suites pass with exact complete-generation visibility.
- Status: complete. Final independent spec, correctness, and test reviews found
  no remaining M2 changes-required or blocking finding. The
  single atomic-store owner now covers admitted-source handoff, discriminated
  checkpoint generations, committed and non-committing terminal-group
  generations, source finalization, complete lease bindings, exact retry
  recovery, and generation manifests. The writer owner now has a complete M2
  method/kind inventory, content-addressed delivery-coordinate migration,
  independent certification, store-inspected drain, monotonic cutover, and
  forward-only rollback. M3 supplies real learned semantic payloads and M4
  supplies full event/replay semantics; M2 persists their closed typed bytes
  atomically and continues to reject a `SIA-ED-REPLAY-001` winner algebra.

#### M2 Admission-To-Preplanning Validation Matrix

| Test ID/family | Behavior proved | Defect detected | Level and failure signal | Planned command |
| --- | --- | --- | --- | --- |
| `SIA-T11-WRITER-INVENTORY`, `SIA-T11-WRITER-CURRENT-EPOCH`, `SIA-T11-WRITER-STALE-OR-UNBOUND` | The finite governed-record/method inventory is closed and only the certified current binding creates a handoff | A generic, stale, mismatched, or binding-free writer changes any governed revision | Static audit plus in-memory/filesystem contract; any missing inventory entry, accepted invalid binding, or changed snapshot fails | `.venv/bin/python -W error -m pytest memorii/tests/unit/core/semantic_ingestion/test_semantic_writer_admission.py -p no:cacheprovider` |
| `SIA-T20-LEASE-CLAIM-RENEW`, `SIA-T20-LEASE-STALE-FENCE`, `SIA-T20-LEASE-RECOVER-EXHAUST`, `SIA-T20-LEASE-STABLE-ALLOCATION` | Current-owner renewal, stale-owner fencing, bounded recovery, and authorization-independent stable allocation | A stale token persists, recovery is unbounded, or volatile authorization changes durable identity | Fake-clock backend contract; wrong mutation, nonterminal exhaustion, or changed fence/allocation bytes fails | `.venv/bin/python -W error -m pytest memorii/tests/unit/core/semantic_ingestion/test_semantic_operation_lease.py -p no:cacheprovider` |
| `SIA-T21-PREPLAN-ATOMIC`, `SIA-T21-ARTIFACT-CLOSURE`, `SIA-T21-FAILPOINT-*` | State, immutable introduction, artifact bytes, index, and closure are prior-or-complete on both backends | Any dangling reference or subset becomes visible after a deterministic failure | In-memory/JSONL conformance with deterministic state/artifact/index/replace failpoints; fresh-reader snapshot inequality fails | `.venv/bin/python -W error -m pytest memorii/tests/unit/core/semantic_ingestion/test_semantic_atomic_store.py -p no:cacheprovider` |
| `SIA-T21-PROCESS-SAME-DELIVERY`, `SIA-T21-PROCESS-DISTINCT-DELIVERY`, `SIA-T21-REOPEN-CORRUPT`, `SIA-T21-LOST-ACK-RETRY` | Process-safe serialization, fail-closed reopen, and exactly-one acknowledged generation | Concurrent duplicate/subset publication, corruption acceptance, or retry duplication | Deterministically synchronized subprocess integration; missing required process capability is reported as unavailable evidence, not silently treated as proof | `.venv/bin/python -W error -m pytest memorii/tests/integration/test_semantic_ingestion_process_safety.py -p no:cacheprovider` |
| `SIA-T10-INTRODUCTION-IDEMPOTENT` | First preplanning publication has one stable introduction and exact retry creates no duplicate | Retry invents a new identity or prematurely writes graph/terminal effects | Backend contract/integration; count/byte mismatch or any graph event/terminal outcome fails | Included in the atomic-store and process-safety commands above |

The first slice delivers `implemented` and `locally verified` evidence only.
Full SIA-R10 event/observation schemas, upcasts, signed checkpoints, collision
algebra, corruption replay, and genesis reconstruction remain M4 work and may
not be inferred from a green M2 generation suite.

### M3 - Candidate-to-terminal semantic pipeline

- Requirements: R02, R04-R07, R09, R12
- Observable behavior: source-only analysis and certified consensus produce accepted or unresolved terminal groups; every failed/ambiguous/unauthorized path has zero graph effect.
- Owners: proposal adapter, analysis/reconciliation contracts, role/scope/temporal consensus, prompt authority, egress governor, transaction planner.
- Persistence: immutable attempt/plan/authorization/terminal lineage through M2 store.
- Tests: malformed/partial proposals, semantic minimal pairs, arbitrary names/languages, named `SIA-T06-TR-*` temporal trust ledger (eligibility/rank/equality/incomparability/no-stitch/plural-text/schema/closure/store/policy/legacy), prompt substitution/redaction, remote zero-wire policy mutations.
- Non-goals: externally approved capability activation and statistical threshold selection.
- Completion: canonical production path demonstrates accepted controls and evidence-only negative/failure cases without fallback.
- Status: authorized to implement from completed linked design revision
  `5451fb354f79256cd95bf3d6ca2ec0796c40952b5d025bdb040b8ff2b08f94e8` at
  current tree baseline `42671e90f35edfc006583e5ddf889927d2602717`. The prior
  undefined bound-combination blocker is resolved. The design freezes a typed,
  policy-fingerprinted trust-selection algebra: policy eligibility is “high
  enough”; the unique top eligible interval governs; equal interval values
  co-support without merged provenance; and equal-ranked or incomparable
  non-identical top evidence is retained as contested with no accepted temporal
  assertion. No bounds are ever synthesized or stitched.
  The implementation handoff must thread one complete trust snapshot and
  server-owned arbitration coordinate through normalization, capability,
  assessment, reconciliation, compile/CAS, persistence, event/replay, and
  expected/observed comparison. `TemporalEvidenceDecisionClosure` is the sole
  temporal decision authority; a contested terminal retains the exact same
  decision closure but writes no accepted projection. M3 is unshipped, so all
  pre-closure/legacy accepted temporal bytes reject before publication, decode,
  replay, or upcast. Each accepted operation and terminal outcome must instead
  carry canonical ordered `OperationTemporalDecisionBinding` values; finite,
  open-end, and atemporal accepted claim/action records require a non-null
  binding. The same role-bound binding is required for correction replacement
  and transition evidence, retraction, identity lineage, planning/durable
  transitions, event/replay, expected/observed records, and committed or
  non-committing operation terminals.

Implementation candidate (2026-08-02): `memorii.core.semantic_ingestion` now
owns the complete bounded M3 candidate-to-terminal path. A leaf contract module
defines closed candidates, policies, role-bound attachment/decision bindings,
accepted carrier families, terminal binding sets, event-input/observation/group
carriers, artifact closure, and closed codecs. Independent assessment is a
required injected boundary; model-provided parser consensus cannot authorize
promotion. The resolver applies one complete trust and temporal snapshot,
retains all evidence, never stitches bounds, co-supports equal intervals, and
terminalizes contested or ineligible inputs without graph effect.

Accepted fact, action, correction, retraction, and identity candidates compile
to exact durable carrier families and persist through one M3-to-M2 owner using
the existing lease/checkpoint/atomic-group/finalization sequence. Accepted
groups publish exact graph, M3 event-input, observation, result, and artifact
closure members; nonaccepted groups publish no graph or event effect. Retry,
lost acknowledgement, filesystem reopen, and cross-operation terminal swaps
are checked against exact fence-bound generation bytes. This is an M3 event
input, not an M4 replay engine; full event history, checkpoint reconstruction,
and replay remain reserved for M4.

Normal provider, Hermes, and filesystem roots share the same explicit M3
composition. The semantic prompt is registered with an exact runtime owner,
schema-parity model, redaction policy, immutable source-preserving request, and
sanitized metadata. Signed egress lifecycle/CAS state is rebound and rechecked
immediately before every transport attempt, including the one bounded repair.
Absent assessor, policy, egress authority, writer admission, or atomic store
stays fail closed and noncommitting.

Local evidence currently includes 177 semantic-ingestion unit tests, four
process-safety/provider-recapture integration tests, prompt conformance, exact
traceability/parser and generated-authority checks, repository Ruff, documented
Pyright with zero findings, and clean diff validation. This is an implementation
candidate rather than completion evidence until the required fresh independent
spec, correctness, and test reviews classify the complete current diff. Current
next action: run those three independent reviews and remediate only confirmed
findings without entering M4.

### M4 - Events, replay, history, trust and identity lineage

- Requirements: R10, R18
- Observable behavior: genesis/checkpoint replay reconstructs exact graph, operations, observations, artifact closure, temporal/trust overlays and identity lineage; historical equal-version conflict fails closed.
- Owners: semantic event authority, observation ledger, replay/checkpoint authority, projection scheduler.
- Persistence/migration: canonical create/update mutations, deterministic upcast, reference closure and policy/identity migration.
- Tests: all record kinds, order permutations, exact duplicate/current-writer collision, historical conflict, corruption, late arrival, trust decay, rekey/merge/split and migration races.
- Non-goals: changing the frozen equal-version fail-closed algebra.
- Completion: every active read schema reconstructs byte-equivalent authoritative state from genesis and signed checkpoint.
- Status: active; rollout step 1 is complete and the authenticated conflict
  reader/list slice is next.

### M5 - Authorized deployment validation, monitoring and independent acceptance

- Requirements: R03, R08, R13-R17, R19
- Observable behavior: signed topology/release/profile artifacts are validated; deterministic monitoring deactivates stale/breached bundles; acceptance observes structure without production semantic helpers; authorized fixture bundles prove the selected-owner path without asserting unavailable operational approval.
- Owners: deployment authorization verifier, capability registry/monitor, provider/filesystem roots, acceptance trust/statistics/oracle, production structural observation authorizer.
- Rollout: preapproval path implemented now; activated path tested with independently signed fixtures but not claimed operational without external artifacts.
- Tests: no-network/preapproval zero-mutation, manifest/package/asset/profile mutations, trust lifecycle/import boundary, independent statistics, observation cursor/auth/revocation, global comparator.
- Non-goals: inventing topology/resource/statistical values or claiming live certification.
- Completion: all deterministic preapproval and artifact-validation behavior passes; unavailable external activation/live checks are recorded revision-specifically.
- Status: pending

## Verification Commands

Focused command per milestone:

- `python -W error -m pytest tests/unit/core/semantic_ingestion tests/integration/test_semantic_ingestion_* -p no:cacheprovider`

Repository gates from `memorii/`:

- `python -W error -m pytest tests/unit -p no:cacheprovider`
- `python -m ruff check memorii tests`
- `pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"`

Deterministic evaluation:

- `python -m memorii.tools.run_eval --suite memory_evolution_sim_v1 --mode all --dry-run --storage-root .memorii --sim-profile adversarial --sim-scenario-count 10 --sim-noise-rate 0.35 --seed 7`
- `python -m memorii.tools.run_eval --suite memory_evolution_runtime_v1 --mode all --dry-run --storage-root .memorii --sim-profile long_horizon --sim-scenario-count 10 --sim-noise-rate 0.35 --seed 7`

Packaging/wheel/install checks follow `docs/development/static_tooling.md`.

Live provider/statistical certification follows `docs/development/benchmark_certification.md` only after approved artifacts and credentials exist and must bind the exact clean candidate revision. Fake-oracle/dry-run evidence is never reported as provider certification.

Compliant local environment: repository `.venv/bin/python` is Python 3.12.13 with pytest 9.0.3, Ruff 0.15.21, and Pyright 1.1.411. Commands will use `.venv/bin/python` and `.venv/bin/pyright` from the repository root, or equivalent relative paths from `memorii/`.

## Progress Log

- 2026-08-02: Completed the M3 final-writer remediation candidate. Protected
  lifecycle lookup now reports exact accepted-candidate or committed-terminal
  state only after authorization; proposal transport is proposal-only and all
  parser/scope/voice/negation/attribution/identity/temporal authority comes
  from one content-addressed independent source analysis. Arbitration consumes
  one self-authenticating immutable trust/temporal snapshot pair. The temporal
  matrix now closes required, optional, atemporal, authenticated-reference,
  open-end, co-support, contest, and no-stitch behavior, including nullable
  atemporal durable carriers. Remote use has no raw-request or boolean-egress
  bypass, and exact prompt/egress/policy/proposal/analysis/seal lineage survives
  terminal codecs. M3 acquires its renewable lease before proposal, records
  content-addressed learned-stage progress, renews across stage boundaries,
  reacquires expired same-owner leases, and exposes terminal recovery
  exhaustion. Provider, Hermes, and filesystem activation is host-owned through
  one authorization-bound runtime builder with no public dependency injection.
  Added the self-contained canonical named evidence owner
  `tests/integration/test_semantic_ingestion_pipeline.py`, covering the
  `SIA-T02/T04/T05/T06/T07/T09/T12` families and every `SIA-T06-TR-*` ledger
  suffix. A blocking-assessor proof verifies that an in-flight learned stage
  renews its lease rather than merely heartbeating before and after the call;
  repeated concurrent exact-delivery proofs verify one planning generation on
  both memory and JSONL backends while preserving later progress checkpoints.
  The focused `-W error` milestone gate passes 217 tests. Repository
  Ruff, documented Pyright, `git diff --check`, exact CTV authority, lifecycle
  signer provenance, and CGS self-tests pass. A full unit run passed 2,578 tests
  with three declared skips and found only the pre-existing blanket naming
  scanner conflict with the design-required node coordinates; the scanner now
  permits only the exact approved prefixes in that single evidence file, and
  its focused regression passes. The final exact `-W error` / no-cache full
  unit rerun from the documented `memorii/` working directory passes 2,579
  tests with three declared skips in 1,833.73 seconds. A prior root-directory
  launch with a relative `PYTHONPATH=memorii` is excluded from evidence because
  it contaminated a child process's import path; the affected static-tooling
  assertion passed alone and in the exact documented full gate.
  Next action: obtain fresh independent spec, correctness, and test review of
  this exact remediation revision.

- 2026-08-02: Completed the coherent M3 candidate-to-terminal implementation
  candidate for R02, R04-R07, R09, and R12 without entering M4 replay. Closed
  candidate, policy, temporal, attachment/decision, carrier, terminal,
  event-input, observation, group, and artifact contracts now flow through one
  independent-assessor gate and one M3-to-M2 persistence owner. Normal provider,
  Hermes, and filesystem composition share the same fail-closed path; exact
  prompt authority and signed egress lifecycle/CAS are revalidated at each wire
  attempt. The publication audit repaired only missing Markdown delimiters in
  the approved design, added the omitted `3.5.1` registry default, and rebuilt
  the canonical authority. Superseded semantic-review design SHA-256
  `5451fb354f79256cd95bf3d6ca2ec0796c40952b5d025bdb040b8ff2b08f94e8`
  is retained as history; the delimiter-only raw design, registry, and authority
  identities are `45727e6870e2087823bfe6250c3c3319a3d540e45fb66c686267409b087b2c1c`,
  `d38aa788adfb7703d970507f496b903ddf460797fe60274ddd5ebf9c22054c46`,
  and `9f650d2f018e3863ad5f5512bf80dbdac1d22fa584cebe9f868c347a2f0143a4`.
  The exact prompt/static/CTV/scenario/traceability selection passes 501 tests
  with one declared skip in 1429.45 seconds; four critical authority smoke
  tests pass in 222.79 seconds. The full unit inventory passes 2,568 tests with
  three declared skips in 1806.73 seconds; repository Ruff passes, documented
  Pyright reports zero errors and warnings, exact CTV, lifecycle-signer, and CGS
  self-test gates pass, and `git diff --check` is clean. Next action: obtain
  fresh independent spec, correctness, and test review of this exact candidate.

- 2026-08-01: Implemented and remediated the first bounded M2
  admission-to-preplanning slice. `SourceAdmissionAccepted` and its protected
  index now carry the exact server-derived operation fence/allocation binding.
  Exact Section 3.13 writer-admission, commit-binding, and ownership-manifest
  contracts guard reserved writer/operation/artifact IDs and every service,
  unit-of-work, in-memory, and JSONL write route. First publication is exactly
  one control plus canonical introduction/index/closure generation; later
  lease writes require a verified prior complete generation. Renewable leases
  reject live reacquisition, advance the ownership epoch on every expiry,
  preserve the admitted allocation namespace, and terminalize after the
  store-owned recovery budget. The final affected selection passes 89 tests
  with one existing process-capability skip; scoped Ruff, changed-file Pyright
  (zero errors/warnings), and `git diff --check` pass. Three independent full
  reviews found five supported P2 defects; one consolidated remediation round
  closed handoff cross-wiring, generic/direct writer bypass, same-token expiry,
  writer restart/concurrent initialization, and open persisted state. Targeted
  delta reviews additionally closed absent-policy restart, partial-generation,
  required-scope tenant/digest, and reserved-ID poison siblings. Final spec,
  correctness, and test deltas reproduced the prior attacks and found no
  remaining supported P1/P2 defect in this slice. Failpoints, subprocess
  contention, corruption/lost-ack, and independent artifact decoding remain
  predefined evidence actions; M3/M4 behavior remains excluded.

- 2026-08-01: The user separately authorized starting M2 after M1 completion.
  Reconciled the active merged baseline at commit `a76a9a34...` and design
  SHA-256 `e7de038a...`. A pre-implementation `test_reviewer` found the
  requirement-level matrix insufficient but identified no material semantic
  blocker for a narrow admission-to-preplanning handoff. Added exact writer,
  lease, atomic-generation, subprocess, lost-ack, and introduction-idempotency
  families with commands and failure signals. Full SIA-R10 replay remains M4;
  `SIA-ED-REPLAY-001` remains fail-closed. Next action: one worker implements
  the bounded handoff through the canonical atomic-store owner and runs its
  focused unit checks.

- 2026-08-01: Remediated the second full-review findings. Normal roots now
  discover exactly one installed host capability via the production entry-point
  group without user configuration; a verified capability's ingress resolver
  cannot be overridden. M1 returns the actual retained governed-source ID,
  Hermes forwards authenticated ingress for every write/delegation/snapshot
  hook, metadata-poor records retain exact adapter-produced UTF-8 bytes without
  synthetic session/task/user context, and M1 composition no longer constructs
  or exposes `MemoryEvolutionService`, its operation repository, or an
  evolution coordinator. Bootstrap artifacts are consumed as raw canonical
  typed-value bytes, the corpus requires the complete disposition/reason
  inventory, and deterministic trust verification exists only in tests. Added
  authorization read-order, replace-failure, lost-ack, installed-root, and
  no-network proofs. The selected M1/R22/root suite passes 80 tests in 16.37
  seconds; repository Ruff, Pyright, and `git diff --check` pass. The full unit
  gate's remaining first failure is a historical end-to-end benchmark that
  expects the default M1 provider to stage a semantic candidate; this is an
  obsolete M2 expectation and remains under test migration, not a reason to
  restore M2 reachability. Next action: fresh independent delta review; do not
  begin M2.

- 2026-08-01: Replaced the placeholder bootstrap boolean with a closed,
  content-addressed artifact graph: trust anchor, profile manifest, grammar
  capability manifest, exact grammar corpus, ordered component fingerprints,
  and installed module-content root. Runtime now verifies release-to-anchor,
  every cross-artifact digest, and package component bytes before constructing
  a `VerifiedBootstrapProfile`. Classification consumes only authenticated
  language/governance evidence plus exact whole-segment corpus bytes; public
  event language cannot authorize selection. Added truthful disabled,
  unavailable, supported, unsupported, and abstained protected outcomes while
  keeping exact outcome kinds out of the coarse public envelope. Added
  installed capability loading through factory, Hermes, and filesystem roots;
  altered-component rejection; JSONL reopen/lost-ack retry; and explicit
  disabled/non-English tests. The focused M1/R22/root selection passes 76
  tests in 14.85 seconds; repository Ruff, Pyright, and `git diff --check`
  pass. The full historical unit gate is not green: its first reproduced
  failure is the pre-M1 benchmark assertion that default provider writes stage
  a semantic candidate, behavior intentionally unavailable in source-only M1.
  Next action: independent full M1 review and explicit reconciliation of
  remaining product/evidence findings; do not begin M2.

- 2026-08-01: Reconciled the fresh M1 spec, correctness, and test reviews. The
  green 70-test selection did not close M1. Confirmed product defects were:
  ordinary roots lacked a complete host capability, retry identity compared a
  regenerated timestamp, lookup trusted a caller-constructible authorization
  context, release verification did not validate anchored artifacts, runtime
  classification trusted the public language field instead of authenticated
  corpus evidence, and disabled/unavailable evidence was incomplete or
  untruthful. The M2 execution branch remains absent. Remediation now excludes
  generated timestamps from immutable retry equality, bundles the host-owned
  ingress resolver with bootstrap authority, requires public lookup to resolve
  opaque host ingress freshly, and passes authenticated ingress through Hermes
  metadata-poor hooks. The selected suite passes 70 tests in 15.63 seconds and
  scoped Ruff/Pyright pass. Remaining next action: implement the pinned
  artifact/component validator and authenticated corpus selector with truthful
  five-outcome evidence; do not begin M2.

- 2026-08-01: Completed the coherent M1 source-only implementation candidate.
  Removed the constructor-reachable M2 evolution branch; introduced the typed
  host bootstrap capability and external trust/release verification boundary;
  propagated that capability through provider factory, filesystem, and Hermes
  composition; added deterministic whole-segment English classification;
  routed authenticated metadata-poor snapshots through governed evidence-only
  admission; and changed protected lookup to decode a frozen discriminated M1
  outcome rather than disclose an untyped dictionary. Missing host authority
  remains fail-closed, while deterministic trust material is test-only and
  operational installer/OS trust provisioning remains the shipping gate.
  The selected M1/R22/provider-root suite passes 70 tests in 15.24 seconds;
  scoped Ruff, scoped Pyright, and `git diff --check` pass. Next action:
  independent spec/correctness/test review of this exact candidate; do not
  begin M2.

- 2026-08-01: Implementation is paused at the operation boundary. The R08/R19/
  R22 ordinary-root conflict is now owned by the linked design WorkPlan
  `docs/work/semantic_ingestion/bootstrap-local-profile-2026-08-01/design.plan.md`.
  That plan defines the user-authorized built-in local bootstrap profile and
  must complete design review before this implementation plan repins its design
  checksum, changes the blocker/disposition, or resumes M1. Next action:
  await the linked design WorkPlan's reviewed approval and exact architecture
  digest; do not implement the bootstrap profile or begin M2.

- 2026-08-01: M1 remediation round 2 separated Hermes composite children from
  public delivery validation. `ProviderEvent` continues to reject the reserved
  `composite:v1:` namespace, while the Hermes adapter can call the private
  internal composite-event construction path only with a coordinate produced
  by the canonical domain-separated constructor. A trusted-ingress Hermes
  fan-out test passed. The focused M1 plus frozen R22 compatibility run
  produced 18 passing tests and two R22 failures:
  `test_r22_service_and_hermes_public_paths_preserve_captured_bytes` and
  `test_r22_current_target_service_scenarios_match_baseline_behavior` expect
  historical transcript/candidate/evolution-outcome bytes, whereas M1's
  unresolved topology decision requires an ordinary `profile_unapproved`
  evidence-only path with no learned stage or outcome. Preserving those bytes
  would require either fabricating terminal lifecycle outcomes or executing
  the prohibited learned path. This is an explicit `Not applicable /
  blocks_approval / design-authority` ambiguity between R08/R19 preapproval
  behavior and R22's frozen public-path corpus; no compatibility fabrication
  was added. Next action: obtain a governing decision that identifies whether
  R22's public corpus applies only to an approved-profile fixture or defines
  the required preapproval envelope, then rerun the focused R22 matrix; do not
  begin M2.

- 2026-08-01: M1 remediation round 1 moved ordinary provider ingress behind an
  injected production-owned `AuthenticatedIngressContextResolver`. Absent
  ingress now returns the frozen coarse envelope with `ingress_unavailable`
  and performs zero writes; `session_end` and `pre_compress` retain only their
  metadata-poor raw evidence. Trusted ingress atomically retains a strictly
  validated internal governed source and protected index before the existing
  `profile_unapproved` gate. Source digests now use the canonical typed-value
  profile over every immutable record field; source and index both have absent
  preconditions, replay verifies full record equality, and fence construction
  recomputes every digest. Public IDs reject the reserved composite namespace,
  Hermes derives child IDs domain-separately, and startup reconciliation is
  disabled while the profile remains unapproved. Evidence:
  `pytest tests/unit/core/semantic_ingestion/test_m1_admission.py -q
  -p no:cacheprovider` passed 6 tests; focused Ruff, Pyright, import smoke,
  and `git diff --check` passed. Next action: obtain independent M1 review of
  the resolver/admission boundary and run its complete focused matrix; do not
  begin M2.

- 2026-08-01: M1 implementation added the canonical exact-byte public delivery
  identity and stable principal/fence contracts in
  `memorii/memorii/core/memory_evolution/ingestion_contracts.py`, a protected
  admission-only authorization index and opaque result accessor in
  `memorii/memorii/core/memory_evolution/admission.py`, and a default
  `profile_unapproved` provider ingress branch. The ordinary provider root now
  retains only raw transcript evidence and performs no extraction, operation,
  lease, work-state projection, semantic mutation, graph mutation, or fallback.
  The legacy provider lifecycle envelope was not extended. Focused evidence:
  `.venv/bin/python -m pytest tests/unit/core/semantic_ingestion/test_m1_admission.py
  -q -p no:cacheprovider` passed (4 tests), and focused Ruff passed after
  formatting only newly touched M1 files. Existing historical provider tests
  expecting default semantic evolution now fail by design and require their
  assertions to be migrated to an approved-profile test seam in a later,
  explicitly authorized milestone. Next action: independently inspect the M1
  diff and run the complete M1-focused verification matrix without beginning
  M2 writer, lease, or generation work.

- 2026-07-31: User authorized M1 implementation and explicitly prohibited
  starting M2 before M1 completion. Resumed the implementation workflow from
  the existing dirty-tree M1 candidate; all pre-existing edits are treated as
  user-owned partial work and must be preserved. Next action: one M1 worker
  inspects the candidate against R01/R04/R08/R12/R19/R22/R23, completes the
  narrow canonical path and feature-local verification, and reports exact
  remaining gaps without entering M2.

- 2026-07-27: Created the initial WorkPlan and froze design SHA-256 `f94e7603...` at production baseline `44cd7773...`.
- 2026-07-27: Initial spec audit reported five planning gaps and treated C3/C4 versus preapproval behavior as a blocker.
- 2026-07-27: User pushed the completed design/review/WorkPlan artifacts at `237053ae...` and directed implementation to continue.
- 2026-07-27: Fresh same-checksum spec audit reconciled C3/C4 as post-authorization rollout sequencing, not a preapproval semantic conflict. Reactivated the WorkPlan.
- 2026-07-27: Architecture, test/evidence, and change-history explorers mapped all requirements, writer paths, reusable mechanisms, validation levels, compatibility constraints, and six vertical milestones.
- 2026-07-27: Rebuilt requirement, scope, validation, migration, and milestone ledgers. Next action: independent pre-implementation test review.
- 2026-07-27: `test_reviewer` confirmed six validation gaps. Five are the expected absent target implementation assigned to M1-M5; TREV-006 exposed a planning gap. Added the test/evidence manifest, evidence independence rules, planned IDs/paths, and exact failure signals. Moved preapproval ordinary-root gating into M1 so unsafe legacy default behavior does not survive until the last milestone.
- 2026-07-27: Located the compliant repository `.venv` and recorded tool versions. Next action: start M0 with one worker.
- 2026-07-27: M0 worker implemented an initial independent parser/checker/evidence-verifier foundation and pinned provider compatibility corpus. Coordinator verification found Pyright and completeness gaps; remediation round 1 corrected Pyright, section regex, and expanded compatibility cases.
- 2026-07-27: Three independent M0 reviewers confirmed that both parsers omit required grammar units/parent semantics, no real frozen-design manifest exists, execution trust is underspecified in code, and the provider corpus does not yet prove isolated/full compatibility. Remediation round 2 stopped on a validated design ambiguity: the frozen design requires complete reviewed traceability registries and approvals but supplies only their schemas.
- 2026-07-27: Paused implementation under the cross-workflow rule and opened linked `docs/work/semantic_ingestion/traceability-design.plan.md`. Partial M0 artifacts remain untracked and must not be treated as completion evidence.
- 2026-07-27: Design revision 3 added canonical registry source SHA-256 `19c15d0...`, complete release/lifecycle semantics, and `SIA-ED-TRACEABILITY-001`; fresh closure review approved the design at SHA-256 `b88cf96b...`.
- 2026-07-27: Fresh spec audit confirmed the prior semantic registry ambiguity is resolved. Reactivated M0 against the new baseline; external traceability trust values remain a deliberate fail-closed gate, not an implementation blocker.
- 2026-07-27: Fresh revision-3 `test_reviewer` confirmed seven implementation/proof gaps. R03/R13 gaps are assigned to revised M0; R22 envelope/capture gaps are revised M0; authorized semantic-result lookup remains explicitly M1 and cannot be used to claim R22 complete.
- 2026-07-27: Revised M0 implementation and remediation round 1 completed the 13-kind dual structural paths, canonical registry-expanded manifest, registered runner-report checks, externally rooted fail-closed release/lifecycle verifier, and reproducible order-preserving provider compatibility capture. Coordinator inspection found and remediated unresolved parent references and six static typing failures before review.
- 2026-07-27: Coordinator integrity evidence now reports 8,920 frozen-design units across all 13 kinds, 8,915/8,915 non-null parent references resolving to emitted invariant IDs, 33 focused tests passing, Ruff passing, Pyright reporting zero findings, and `git diff --check` clean. Next action: fresh independent M0 review.
- 2026-07-27: M0A implementation pass/round 0 made both raw registry loaders recompute and bind specialized report-schema/runner-profile artifacts, made caller-HMAC evidence fail closed, bound the report entry point to verified release roots, and applied replayed active lifecycle signer eligibility to release and pointer signatures. Signed successor, rotation, threshold-recovery, and explicit higher-sequence rollback histories now have deterministic fixtures, including rejection for incomplete threshold material and an unauthorized rollback target. The complete focused M0A suite, exact Ruff/Pyright, and `git diff --check` pass.
- 2026-07-28: M0A-C1 initially implemented two fixture-only isolated
  elaborators for the marked grammar, 52-coordinate inventory, profile
  registry, and RFC 8032 test vectors. The original pin was invalidated when
  the linked design review approved the one-character RFC-vector correction;
  it is retained only as superseded history.
- 2026-07-28: M0A-C1 remediation bound both isolated elaborators plus an
  independent test-owned parser to the corrected design signer table. Both
  reproduce byte-identical output SHA-256
  `f2f16fd6014baf71aafe21acbd174aaee8fbd61fa7657fbfec3326499c9a2826`,
  including design identity `73682f...`, grammar `c870cf...`, inventory
  `c44fb9...`, profile `fd85f9...`, and registry `32b69f...`. The reviewed
  129-character one-extra-`5` mutation rejects as invalid hex. No ancestry,
  persistence, public gate, or production authority changed. Next action:
  fresh independent C1 milestone review.
- 2026-07-29: Layer1 L1-009 wired the exact content-addressed CTV v2 hermetic
  checker command from `docs/development/static_tooling.md` into a standalone
  Python 3.12 PR job. The checker reproduced the pinned full authority and
  rejected an authority-byte mutation before parsing it. L1-008 remains active:
  this gate only proves the existing design-side validator's two hermetic
  reproductions and is not independent-compilation evidence.
- 2026-07-29: Implementation round 1 of 50 completed a fresh pre-coding
  `test_reviewer` pass. The family-complete matrix now binds baseline equality,
  syntax, declarations, enums, graph, profile, fingerprint, binding,
  cross-implementation verdicts, clean-room isolation, anti-replay,
  determinism, compatibility, rollback, and Python 3.12 CI behavior before the
  compiler worker begins.
- 2026-07-29: Implementation round 2 of 50 added the separately authored,
  stdlib-only `semantic_ingestion_ctv_reference_compiler`. It consumes only
  design and registry bytes, compiles the complete 56-schema/240-enum
  authority, publishes atomically, and matched the frozen authority byte for
  byte in two fresh Python 3.12 processes. Static import inspection and an
  audited isolated execution passed with the design validator and checked
  authority absent. A valid reachable-field mutation recomputed the affected
  graph, fingerprint, binding, and source identity rather than replaying
  frozen bytes. Representative marker, grammar, and declaration failures
  preserved absent or pre-existing output. The family-complete rejection and
  CI matrix remains active for later bounded rounds.
- 2026-07-29: Implementation round 3 of 50 closed the independent compiler
  matrix in one consolidated batch. The compiler now validates the exact
  ordered 28-model generation-member contract and discriminator mapping,
  validates nested `Annotated` metadata before Literal fast paths, emits
  strict Unicode-scalar UTF-8 JSON, closes collection arity/ellipsis forms,
  and preserves foreign PID temporary files on atomic-publication collision.
  A hand-authored 25-case corpus produced equivalent nonzero/no-output
  verdicts from both compilers across syntax, grammar, declaration, enum,
  graph, profile, and tagged-union families. The dedicated Python 3.12 PR job
  now runs the independent matrix, pin/tamper/workflow suite, and exact pinned
  checker, with constrained pytest and PyYAML dependencies declared for a
  fresh checkout. Two collection-shape cases remain a recorded
  frozen-validator verification gap rather than being weakened in the
  reference compiler.
- 2026-07-29: Implementation remediation round 5 of 50 closed the confirmed
  round-4 implementation findings without changing or repinning any frozen
  input or verifier. The compiler now rejects Python 3.12 class/function type
  parameters and non-simple annotated assignments. Public-CLI tests cover
  those forms, portable default temporary storage, registry identity drift
  and failures, dual-compiler anti-replay with independent formula checks, and
  checker tampering that passes its recomputed input SHA before failing
  reproduction.
- 2026-07-29: Layer1 implementation handoff completed one bounded consumer
  integration round for SIA-R03/L1-008/L1-009. The standalone PR job and both
  consumer test modules now pin validator `538a01f1...` and checker
  `2ca3da2c...` and invoke authority tooling with exactly `python3.12 -I`.
  The public validator `--write` subprocess matrix proves invalid direct,
  whole-quoted, quoted-child, nested, alias, inherited, reachable/unprojected,
  and tuple quoted-ellipsis collection/type cases leave absent targets absent,
  preserve preseeded bytes and mode `0640`, and leave no temporary siblings.
  Valid sibling controls publish bytes exactly equal to the separately authored
  compiler output. The independent compiler now applies the closed collection
  arity grammar to unprojected aliases as well, so the full collection/type
  corpus has matching fail-closed verdicts. No frozen design, registry,
  authority, validator, checker, profile, architecture, or runtime behavior
  changed.

## Evidence Log

- 2026-08-01 M2 first slice: production owners are
  `memorii/memorii/core/memory_evolution/writer_admission.py`,
  `memorii/memorii/core/memory_evolution/atomic_store.py`, the admitted handoff
  in `admission.py`/`ingestion_contracts.py`, and generic enforcement in
  `memory_plane/service.py`, `memory_plane/store.py`, and
  `memory_plane/unit_of_work.py`. Feature tests are
  `test_semantic_writer_admission.py`, `test_semantic_atomic_store.py`, and
  `test_semantic_operation_lease.py`. From `memorii/`, the affected pytest
  selection (new M2 tests, M1 admission, memory-plane store contract and
  convergence) passed 89 with one existing skip; changed-scope Ruff passed;
  changed-file Pyright reported zero errors and warnings; `git diff --check`
  passed. Full repository Pyright was not usable as slice evidence because the
  current main baseline reports unrelated pre-existing errors outside changed
  files; those were not altered or suppressed.

- `git rev-parse HEAD` -> `237053aef26fae2df7e6b44144e61a1b780bf7ad`.
- `git branch --show-current` -> `live-benchmark-repair`.
- `shasum -a 256 docs/design/semantic_ingestion_architecture.md` -> frozen checksum above.
- `git rev-parse f76850f:memorii/memorii/core/provider/models.py` and HEAD resolve to blob `307921e7648fcaf5e11244200a7fb3c1f402e817`.
- Existing compatibility/provider/storage/factory surfaces are unchanged from the pinned baseline; the range adds semantic compilation plus design/review artifacts.
- Architecture exploration produced the finite writer inventory and identified `MemoryPlaneStore` as substrate rather than semantic owner.
- Test exploration identified existing scaffolds but no direct SIA proof, the circularity risk in current fake oracles, and the missing independent R22 corpus.
- Same-checksum result-access closure review supports preapproval evidence-only implementation and postauthorization C3/C4 activation.
- Revision-3 traceability closure review: `docs/reviews/semantic_ingestion/traceability-registry-closure/review-round-04.md`.
- Canonical registry validation: superseded by the frozen M0A registry's exact 147/147 Section 1-5 heading defaults, 23/23 requirement bindings, and 23 evidence groups.
- `.venv/bin/python --version` -> Python 3.12.13; pytest 9.0.3; Ruff 0.15.21; Pyright 1.1.411.
- Revised M0 focused suite from `memorii/`: `../.venv/bin/python -m pytest tests/unit/tools/test_semantic_ingestion_traceability.py tests/unit/tools/test_semantic_ingestion_traceability_registry.py tests/unit/tools/test_semantic_ingestion_traceability_manifest.py tests/unit/tools/test_semantic_ingestion_traceability_evidence.py tests/unit/core/semantic_ingestion/test_provider_compatibility.py -q` -> `33 passed in 129.85s`.
- Post-remediation-round-3 execution of the same focused suite -> `40 passed in 90.24s`.
- Frozen structural assertion -> `8920` units, `8915` non-null parents, `13` unit kinds, all parents resolve.
- Exact changed-surface Ruff invocation -> `All checks passed!`; exact changed-tool Pyright invocation -> `0 errors, 0 warnings, 0 informations`; `git diff --check` -> clean.
- M0A pass/round 0 from `memorii/`: `../.venv/bin/python -m pytest tests/unit/tools/test_semantic_ingestion_traceability_registry.py tests/unit/tools/test_semantic_ingestion_traceability_evidence.py -q -p no:cacheprovider` -> `25 passed in 2.58s`; changed-surface Ruff -> `All checks passed!`; exact changed-surface Pyright -> `0 errors, 0 warnings, 0 informations`; `git diff --check` -> clean.
- Final M0A focused deterministic suite from `memorii/`: `../.venv/bin/python -m pytest tests/unit/tools/test_semantic_ingestion_traceability.py tests/unit/tools/test_semantic_ingestion_traceability_registry.py tests/unit/tools/test_semantic_ingestion_traceability_manifest.py tests/unit/tools/test_semantic_ingestion_traceability_evidence.py -q -p no:cacheprovider` -> exit `0` (30 focused test progress marks); changed-surface Ruff -> `All checks passed!`; exact changed-surface Pyright -> `0 errors, 0 warnings, 0 informations`; `git diff --check` -> clean.
- Layer1 L1-009, repository root: the exact command under `C2 Layer 1 CTV v2
  binding authority` in `docs/development/static_tooling.md`, run with
  `python3.12`, exited `0` and reported `schemas=56 enum_rows=240 replicas=2`.
  A copied authority file with one appended ASCII space exited nonzero with
  `authority SHA-256 mismatch`. `python3.12 -m py_compile
  memorii/tests/unit/tools/test_ctv_binding_authority_pr_gate.py` and `git diff
  --check` exited `0`. Pytest was unavailable in the local Python 3.12
  interpreter (`No module named pytest`), so the new black-box pytest module
  remains unexecuted locally.
- Layer1 final handoff, from `memorii/`: repository `.venv` Python `3.12.13`
  ran `python -m pytest -q -W error
  tests/unit/tools/test_semantic_ingestion_ctv_reference_compiler.py
  tests/unit/tools/test_ctv_binding_authority_pr_gate.py -p no:cacheprovider`
  -> `91 passed in 238.06s` (`3:58.77` elapsed), below the five-minute PR
  budget. The command exercises actual subprocesses whose authority,
  validator, and checker entry points are `python3.12 -I`; it includes exact
  pinned checker reproduction and all prior syntax, declaration, enum, graph,
  profile, fingerprint, and binding cases. Scoped Ruff -> `All checks passed!`;
  scoped Pyright -> `0 errors, 0 warnings, 0 informations`; Python `3.12`
  `py_compile` and repository `git diff --check` -> exit `0`. The system
  `python3.12` lacks pytest, so the repository Python 3.12 virtual environment
  hosted pytest while the tested subprocess contract remained exact.
- Layer1 implementation round 2, repository root:
  `.venv/bin/python -m pytest -W error
  memorii/tests/unit/tools/test_semantic_ingestion_ctv_reference_compiler.py -p
  no:cacheprovider` -> `8 passed in 2.67s`; scoped Ruff -> `All checks passed!`;
  scoped Pyright -> `0 errors, 0 warnings, 0 informations`; Python 3.12
  `py_compile` and `git diff --check` -> exit `0`. Two subprocess outputs
  equal frozen SHA-256
  `89a98fc1e545f38c234ce42dbd164c85e3ddc6358856cca70e59dad7b1addc7b`,
  contain 56 schemas and 240 enum rows, and bind profile digest
  `20edd38a4ef41e4abf7e1b9a65fe2745e65705f80ec8f93c48c658739b7660a0`.
  The runtime audit allowed only compiler/design/registry/output, its atomic
  sibling temporary output, and interpreter/stdlib roots.
- Layer1 implementation round 3, repository root: focused reference-compiler
  pytest -> `40 passed`; PR pin/tamper/workflow pytest -> `10 passed in
  53.27s`; final combined matrix and gate suite -> `50 passed in 80.93s`;
  post-CI-dependency structural workflow test -> `1 passed, 9 deselected in
  0.11s`; scoped Ruff -> `All checks passed!`; scoped Pyright -> `0 errors, 0
  warnings, 0 informations`; Python 3.12 `py_compile` and scoped `git diff
  --check` -> exit `0`. The exact pinned checker exited `0` and reported
  authority SHA-256
  `89a98fc1e545f38c234ce42dbd164c85e3ddc6358856cca70e59dad7b1addc7b`,
  56 schemas, 240 enum rows, and two replicas. The configured CI performs
  baseline reproduction in both the gate test and final checker; measured
  local execution remains below five minutes, while actual remote CI
  execution is still required for CI-enforced maturity evidence.
- Layer1 implementation remediation round 5, from `memorii/`:
  `../.venv/bin/python -m pytest -W error
  tests/unit/tools/test_semantic_ingestion_ctv_reference_compiler.py
  tests/unit/tools/test_ctv_binding_authority_pr_gate.py -p no:cacheprovider`
  -> `55 passed in 188.52s`. Scoped Ruff -> `All checks passed!`; exact scoped
  Pyright with `--pythonpath ../.venv/bin/python` -> `0 errors, 0 warnings, 0
  informations`; Python 3.12 `py_compile` and scoped `git diff --check` -> exit
  `0`. The exact pinned checker exited `0` and reported authority SHA-256
  `89a98fc1e545f38c234ce42dbd164c85e3ddc6358856cca70e59dad7b1addc7b`,
  56 schemas, 240 enum rows, and two replicas. The combined matrix plus
  separate checker measured about 3 minutes 51 seconds locally. A remote
  GitHub execution and branch protection remain unavailable external evidence
  and are not claimed.

## Decision Log

### D01 - Placeholder resolution

- Date: 2026-07-27
- Decision: Work ID is `semantic_ingestion`; design path is the supplied absolute path; base branch is `live-benchmark-repair`.
- Alternatives: block on literal placeholders or invent another branch.
- Rationale/consequence: current repository context provides reproducible values; all evidence uses them.

### D02 - External decisions are rollout gates

- Date: 2026-07-27
- Decision: implement prescribed fail-closed behavior now; do not select external values. Apply C3/C4 only to a later externally authorized activation candidate.
- Alternatives: stop all implementation; treat current ungated active composition as satisfying C3.
- Evidence: design R08/R14/R16/R19, canonical external-decision register, Gate F, and final closure review.
- Consequence: preapproval production composition becomes evidence-only; no active/certified claim without artifacts.

### D03 - Proof foundation precedes production mutation

- Date: 2026-07-27
- Decision: M0 implements independent R03 trace/evidence tools and captures R22 compatibility corpus before target changes.
- Alternatives: add evidence after implementation or serialize the target model as its own baseline.
- Rationale/consequence: prevents circular proof and undetected compatibility drift.

### D04 - Typed semantic atomic store, not generic-store policy

- Date: 2026-07-27
- Decision: introduce a typed semantic-ingestion atomic-store owner above the generic memory-plane substrate.
- Alternatives: put semantic policy directly into `MemoryPlaneStore`; let current writers self-enforce.
- Rationale/consequence: creates one semantic owner without coupling unrelated domains or preserving bypasses.

### D05 - Preserve the legacy envelope out of band

- Date: 2026-07-27
- Decision: never add semantic result fields or aliases to `ProviderEvolutionOutcome`/`ProviderSyncResult`; use the separately authorized opaque lookup.
- Alternatives: enrich the existing response or add a versioned alias.
- Rationale/consequence: wire change set remains empty and old callers remain byte compatible.

### D06 - Traceability trust values are an external gate, not implementation defaults

- Date: 2026-07-27
- Decision: implement the complete revision-3 canonical registry, structural/release/lifecycle validators and fail-closed absent-root behavior; never synthesize bootstrap/recovery roots, identities, keys, trust snapshots, approvals, or signed releases.
- Alternatives: remain blocked despite determinate source data; use test/self-signed values as production authority.
- Evidence: Section 3.23.4.1, `registry-v1.json`, `SIA-ED-TRACEABILITY-001`, and closure round 04.
- Consequence: M0 can complete deterministic implementation while architecture acceptance remains unavailable until externally provisioned artifacts exist.

### D07 - Do not synthesize the incomplete M0A golden source

- Date: 2026-07-28
- Decision: stop M0A after correcting the determinate 147-heading registry contract; do not create profile bindings, typed envelopes, signature preimages, signatures, ancestry histories, or acceptance-store generations from schematic fixture values.
- Alternatives: derive missing bytes from the current verifier or production models; accept toy fixture bodies as complete artifacts.
- Evidence: the frozen source fixture `current-index-g2` contains only `{"index_generation":2}`, has no artifact coordinate, and records empty signature-preimage/signature lists, while Section 3.23.4 requires complete byte-equal typed bodies, coordinates, signatures, envelope bytes, dependencies, and G1/G2/G3 load/restart artifacts.
- Consequence: deterministic verification remains fail-closed. A complete independently authored source package is the smallest required external input; M1 and R22 remain excluded.

### D08 - Fixture-authority recipe is a deterministic test-data contract

- Date: 2026-07-28
- Decision: supersede D07's materialization stop. Three fresh independent reviews validated that the frozen fixture-authority recipe uniquely determines the M0A test artifacts, so implement two isolated elaborators and require byte-for-byte agreement before publishing the source package.
- Alternatives: retain the schematic source or derive expected values from production/verifier code.
- Evidence: coordinator remediation instruction following unanimous reviewer inspection of frozen SHA-256 `9c439884c67eeef05a58dbf51ae890280a6daa1fef266a56be5ae1971c0e58f2`.
- Consequence: fixture elaboration remains acceptance-only; the independent elaborator imports neither Memorii, Pydantic, the verifier, nor the first elaborator.

### D09 - Advance C1 to the approved signature-corrected design baseline

- Date: 2026-07-28.
- Decision: invalidate the original C1 pin and regenerate from frozen design
  SHA-256 `158277cd433c85714253359e134c94ece0f3ad59d2b3f1b9a403c295417a397e`.
- Alternatives: retain the old digest-bound output; hard-code the corrected
  signature independently of the design table.
- Evidence: the linked design WorkPlan records three-role approval of the sole
  one-character design delta; the old value had 129 hex characters and was
  invalid hex, while the corrected value is the exact 128-character/64-byte
  RFC 8032 vector.
- Consequence: each elaborator and an independent test parser must extract the
  fixed signer table from design bytes; byte-equal output is repinned only
  after RFC-vector and one-extra-`5` rejection checks pass.

### D10 - Equivalent rejection and independent evidence

- Date: 2026-07-29.
- Decision: `L1-008` equivalent rejection means the same accept/reject verdict
  and zero output publication on rejection. Exception types and diagnostic
  text are not stable cross-implementation contracts.
- Decision: two executions of one validator remain reproducibility evidence
  only. Independent reproduction requires separate authorship, no shared
  parser/normalizer implementation, runtime success with the design validator
  and checked authority absent, complete byte equality, anti-replay positive
  mutations, and the family matrix above.
- Disposition: the reviewer-labeled P2 findings are coordinator-classified as
  `Not applicable / changes_required` because the demonstrated impact is
  verification and CI-evidence completeness, not a product scenario.
- Resulting action: one clean-room Layer1 compiler worker.

### D11 - Clean-room compiler boundary

- Date: 2026-07-29.
- Decision: the Layer1 reference compiler is an installable stdlib-only CLI
  under `memorii.tools`; it owns its marked-block scanner, closed AST
  declaration parser, graph projector, canonical serializer, digest formulas,
  and atomic output publication. It imports no design-side tool or production
  semantic helper and treats the frozen authority only as a post-compilation
  black-box comparison target.
- Alternatives: import or invoke the design validator; replay checked bytes;
  share a parser/normalizer helper; place the compiler beside fixture tools.
- Evidence: byte-identical full-authority reproduction, audited isolated
  execution without validator/authority files, static import scan, and a valid
  semantic mutation producing internally consistent changed output.
- Consequence: baseline derivation is independently reproduced and locally
  verified. L1-008 remains active until the family-complete equivalent
  rejection matrix is closed; the independent compiler is not yet CI-enforced.

### D12 - Closed-profile matrix refinement

- Date: 2026-07-29.
- Decision: profile ID/version, grammar revision, and grammar rows are frozen
  constants. Round 3 proves drift rejection and does not invent an in-version
  profile mutation. Anti-replay uses only design-authorized declaration/graph
  and enum mutations, which recompute fingerprints, profile state where
  applicable, and dependent bindings.
- Alternatives: weaken frozen constants or add a test-only profile branch.
- Evidence: Section 3.23.4.2.1, baseline equality, valid reachable-field
  mutation, and a valid enum mutation byte-matched by both compilers.
- Consequence: all applicable matrix behavior is tested without inventing
  semantics.

### D13 - Derived-authority compiler boundary

- Date: 2026-07-29.
- Decision: do not add an authority-validation API to the independent
  compiler. Its approved contract consumes design and registry bytes and
  derives authority bytes.
- Alternatives: add a second API that accepts arbitrary authority bytes.
- Evidence: independent formula recomputation detects
  profile/graph/fingerprint/binding tampering, and the pinned checker compares
  a supplied authority with independently reproduced output after identity
  validation.
- Consequence: the reviewer suggestion is unsupported/speculative in this
  implementation scope and would create an unapproved parallel contract.

## M0A 2026-07-28 Blocker Record

- Scope: SIA-R03 and SIA-R13 only. The frozen design digest is `9c439884c67eeef05a58dbf51ae890280a6daa1fef266a56be5ae1971c0e58f2`.
- Completed determinate correction: both independent raw registry loaders now require the design-authorized exact 147 nonempty numeric Section 1-5 heading defaults; tests pin the revised registry source identity `66c3414e869d3cb8a010c376bcbd53e19f48124bb841c88a5836bcc5ea67bfd1`.
- Confirmed blocker: `docs/design/semantic_ingestion/traceability_golden_vectors/v1.json` is canonical JSON but not a materialized `TraceabilityGoldenVectorSourcePackage` under the frozen contract. It contains schematic fixture bodies, absent artifact coordinates, empty signature material, and no complete trust/lifecycle/release/generation/pointer/history byte closure.
- Required input to resume: one independently authored, canonical source package whose every fixture and mutation records the complete typed-input/body/preimage/signature/envelope/coordinate/reference/dependency/load-count bytes required by Sections 3.23.4.2-3.23.4.4, plus two independently implemented elaborator outputs pinned to the same digest. It must be supplied without importing production code or using the approval verifier as an oracle.
- Verification: from `memorii/`, `../.venv/bin/python -m pytest tests/unit/tools/test_semantic_ingestion_traceability_registry.py tests/unit/tools/test_semantic_ingestion_traceability_manifest.py -q -p no:cacheprovider` completed with only the stale source-identity assertion before it was updated; the existing acceptance suite remains `8 passed` but does not prove full generation reconstruction and is not completion evidence.
- Next action: obtain and independently review the complete externally authored golden-vector source package; do not expand implementation scope until it is present.

### Remediation Round 1

- Disposition: D07's blocker conclusion is superseded by three fresh independent reviews. The source recipe is to be materialized as test/verification implementation, not treated as an external design input.
- Scope: R03/R13 M0A only. Implement isolated dual elaboration, canonical source replacement, complete-generation verification, and adversarial lifecycle/public-boundary tests. R22 and M1 remain excluded.
- Next action: inspect the exact fixture schema and acceptance-store contracts, then implement the two elaborators from the frozen design bytes and registry bytes only.

### Remediation Round 1 Evidence

- Two isolated standard-library elaborators under `memorii/tests/fixtures/semantic_ingestion/traceability_golden_vectors/` now independently re-elaborate `v1.json` from frozen design bytes, registry bytes, and the source package; neither imports Memorii, Pydantic, the approval verifier, or its sibling elaborator. The source was replaced only after byte equality.
- Added acceptance-owned immutable generation publication with compare-and-advance fence semantics, idempotent same-candidate lost-ack retry, stale-CAS rejection, and torn/nonmonotonic rejection. The public registered approval entry point optionally binds caller-supplied release/pointer/history bytes to the current accepted generation.
- From `memorii/`: focused M0A pytest suite reported `37 passed in 20.06s`; scoped Ruff reported `All checks passed!`; scoped Pyright reported `0 errors, 0 warnings, 0 informations`; repository-root `git diff --check` passed.
- Next action: fresh independent review of the materialized source and generation-store boundary, then remediate only validated M0A findings.

### M0A Independent Review Round 2

- Reviewers: fresh `spec_auditor`, `correctness_reviewer`, and `test_reviewer` over frozen design SHA-256 `9c439884c67eeef05a58dbf51ae890280a6daa1fef266a56be5ae1971c0e58f2` and the complete round-one candidate.
- Finding M0A-R2-01: `Not applicable / changes_required / verification and trust`. Confirmed. The two elaborators share a generic four-field wrapper and SHA-512 pseudo-signature; they do not independently implement the marked CTV grammar/inventory/profile registry, exact typed schemas, Ed25519 reference vectors, byte-complete ancestry, or all 25 verdicts. Action: remove both elaborators and their generated source; replace with exact independent implementations and a strict source executor.
- Finding M0A-R2-02: `Not applicable / blocks_approval / security architecture`. Confirmed. The public approval API still accepts caller-owned authority and artifact bags, and the optional generation store merely compares values. Action: replace the public boundary with a composition-owned acceptance service whose closed request contains only reader authorization/request coordinates.
- Finding M0A-R2-03: `P2 / changes_required / persistence and concurrency`. Confirmed. The in-memory generation store lacks signed manifests, filesystem durability, fsync, interprocess locking, atomic index/fence CAS, restart/torn-write validation, leases, time witnesses, and retention watermarks. Action: remove the in-memory reference shortcut and implement the acceptance-only durable repository contract.
- Finding M0A-R2-04: `P2 / changes_required / execution evidence`. Confirmed. Existing acceptance tests authorize synthetic `b"passed"` bytes rather than immutable canonical signed runner attestations bound to the full command/environment/tree/release/trust/artifact closure. Action: reject synthetic result bytes and load the attestation only through its manifest coordinate.
- Finding M0A-R2-05: `Not applicable / changes_required / verification coverage`. Confirmed. Missing process/restart/failure/concurrent-writer, complete generation-member, signature/profile/binding, public golden-vector, and production isolation/package tests prevent R03/R13 closure. Action: add the required adversarial suite after canonical owners exist.
- Finding M0A-R2-06: `Not applicable / changes_required / scope governance`. Confirmed. Round-one shortcuts must be removed rather than layered over; R22/M1 remain excluded.
- Coordinator disposition: all six findings are confirmed. Round-one completion evidence is invalidated and must not be used for R03/R13 approval.
- Next action: delete the round-one generic elaborators/store/API seam, then implement the exact acceptance-owned profile and fixture authority as the first independently verifiable vertical slice.

## M0A Final Non-Convergence

- Date: 2026-07-28
- Status: blocked after three implementation/remediation attempts.
- Design baseline: SHA-256 `9c439884c67eeef05a58dbf51ae890280a6daa1fef266a56be5ae1971c0e58f2`.
- Scope: SIA-R03/R13 M0A only. R22, M1, and adjacent cleanup remain excluded.
- Valid retained work: the two independent registry loaders and their tests enforce the frozen exact 147-heading contract and pinned registry source identity.
- Invalid work removed: the generic four-field fixture wrappers, SHA-512 pseudo-signatures, optional caller-supplied generation store, in-memory store, associated tests, and the generated golden source bytes. None is completion evidence.

| Gap | Requirement | Product priority / disposition / type | Attempts | Exact remaining implementation work | Smallest next action |
| --- | --- | --- | ---: | --- | --- |
| Exact dual fixture elaboration is absent | R03, R13 | Not applicable / blocks_approval / verification trust | 3 | Implement two isolated encoders from the marked CTV grammar and 52-entry inventory; recompute every component/binding/entry/registry digest; verify RFC 8032 keys/reference signatures; materialize the complete ancestry topology, typed bodies, signature preimages, Ed25519 signatures, envelopes, coordinates, references, and all 25 verdicts; require byte equality before publishing `v1.json` | Implement and independently known-answer-test only the complete CTV/profile-registry plus RFC8032 layer, then freeze its equal output digest before ancestry work |
| Acceptance-owned durable repository/service is absent | R03, R13 | P2 / blocks_approval / persistence and security | 3 | Implement immutable content-addressed members, closed signed generation manifests, exact kind/schema/binding/dependency closure, atomic current-index and independent fence CAS with fsync/interprocess lock, restart/torn-write recovery, monotonic watermark, reader authorization/lease/time witness, and typed outcomes | Build backend conformance tests for genesis publish, G1/G2/G3 advance, stale CAS, lost acknowledgement, rollback, torn restart, and concurrent writers before exposing a public service |
| Public gate remains caller-authorized | R03, R13 | Not applicable / blocks_approval / architecture security | 3 | Replace the current argument-heavy approval function with a composition-owned service; its public request contains only the closed reader authorization/request coordinate, and the service loads provisioned trust plus pointer-selected manifest/members and recomputes structural, coverage, execution, lifecycle, release, generation, and pointer closure | Introduce the closed request/result types and composition root only after the durable repository contract exists |
| Canonical signed execution evidence is absent | R03, R13 | P2 / changes_required / execution evidence | 3 | Load manifest-selected signed runner attestations binding command, cwd, interpreter, collected IDs, outcomes, test/result/stdout/stderr/environment artifacts, tree/design revision, release, and trust snapshot; reject synthetic pass bytes | Replace the registered R03/R13 acceptance fixtures with one real immutable attestation and adversarial byte/signature/binding mutations |
| Required adversarial and isolation proof is absent | R03, R13 | Not applicable / changes_required / verification coverage | 3 | Add all 25 public golden-vector executions, member missing/extra/mix/substitution cases, signature/profile/binding mutations, process/restart/failure/concurrency tests, and production import/wheel isolation proving fixture keys and acceptance authority are unreachable | Run focused tests plus Ruff, Pyright, package/import isolation, and `git diff --check` only after the four owners above are complete |

- What was learned: the frozen recipe is determinate; the failure is implementation non-convergence, not design ambiguity or missing external authority. Partial generic encodings create circular approval evidence and must not remain in the tree.
- Exact blocker: no complete independently double-elaborated fixture package or acceptance-owned durable generation reader exists. Without those two artifacts, the public R03/R13 gate cannot be made approval-capable.
- Next action: start a new linked implementation WorkPlan limited to the CTV/profile-registry and RFC8032 known-answer layer; do not resume public approval or persistence work until two isolated implementations produce identical pinned bytes.

## M0A User-Authorized Continuation

- Date: 2026-07-28.
- Authorization: the user explicitly directed the coordinator to continue and
  finish M0A after the recorded three-round non-convergence.
- Design baseline remains frozen at SHA-256
  `158277cd433c85714253359e134c94ece0f3ad59d2b3f1b9a403c295417a397e`.
- Scope remains SIA-R03/R13 M0A only. R22, M1, and adjacent cleanup remain
  excluded.
- The non-convergence record remains immutable evidence. This continuation uses
  smaller vertical milestones and does not reinterpret failed attempts as
  completion evidence.

### Continuation milestones

1. `M0A-C1` canonical fixture authority: implement two isolated
   CTV/profile-registry elaborators and RFC 8032 known-answer verification;
   freeze byte-equal profile and binding-registry outputs. No ancestry,
   persistence, or public-gate behavior is in scope.
2. `M0A-C2` byte-complete ancestry and golden package: materialize the exact
   trust topology, typed bodies, preimages, Ed25519 signatures, envelopes,
   coordinates, G1/G2/G3 fixtures, and every declared mutation verdict from
   the frozen C1 outputs.
3. `M0A-C3` durable acceptance repository: implement immutable
   content-addressed generation members, signed manifest closure, atomic
   pointer/index/fence CAS, fsync/reopen recovery, monotonic watermark, reader
   authorization/lease/time witness, concurrency, and typed outcomes.
4. `M0A-C4` composition-owned approval path: replace caller-owned authority
   and artifact bags with the repository-selected generation; independently
   recompute structural, coverage, execution, lifecycle, release, generation,
   and pointer closure and validate canonical signed runner evidence.
5. `M0A-C5` whole-milestone proof: execute all golden mutations through the
   public boundary, process/restart/failure/concurrency tests, production
   import/wheel isolation, deterministic gates, and fresh three-role review.

### Historical continuation step

Run fresh independent C1 milestone review against frozen design SHA-256
`158277cd433c85714253359e134c94ece0f3ad59d2b3f1b9a403c295417a397e`.
Do not begin C2 ancestry, persistence, or public-gate work before review
dispositions are recorded.

## Review Log

### M2 admission-to-preplanning review and remediation round 1

- Reviewers: `spec_auditor`, `correctness_reviewer`, and `test_reviewer` over
  the complete bounded slice, followed by targeted and final delta reviews.
- Confirmed `P2 / changes_required / eligible_p1_p2` product defects: caller-
  substituted operation/source/delivery/scope handoff; declarative-only writer
  manifest with generic/direct/restarted-backend bypass; expired same-token
  lease reuse; non-idempotent restart/concurrent writer initialization; open
  persisted operation state; current-capability partial-generation publication;
  required-scope tenant/digest substitution; and reserved-ID poisoning.
- Coordinator disposition: confirmed and consolidated by the writer/storage
  boundary root causes. One remediation round implemented exact admitted
  bindings, common guarded-write authorization, fail-closed absent-policy
  handling, independent exact generation-shape validation, closed state,
  restart-safe admission, and token-independent expiry fencing.
- Final delta evidence: prior cross-wiring, generic/direct, reopened backend,
  partial-control, scope-substitution, same-token, initialization-race, and
  reserved-ID attacks fail closed with unchanged snapshots. No final reviewer
  reproduced a remaining supported P1/P2 defect. Deterministic failpoints,
  real-process contention, corruption/lost-ack, and independent artifact-byte
  decoding are `evidence_action`, not product remediation.

### Layer1 implementation round 4 reconciliation

- Reviewers: fresh `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer` over the stable round-3 candidate.
- `spec_auditor`: the frozen-validator collection-shape divergence remains
  confirmed, classified `Not applicable / blocks_approval / verification`.
  It requires a linked design workflow rather than a frozen verifier change
  in this implementation operation. The proposed compiler
  authority-validation API is unsupported because the approved compiler
  derives authority from design and registry inputs.
- `correctness_reviewer`: Python 3.12 nonempty `ClassDef.type_params` and
  `FunctionDef.type_params`, plus `AnnAssign.simple != 1`, were missing from
  the closed declaration grammar. Classified
  `Not applicable / changes_required / verification`; confirmed and resolved
  with defensive AST checks and
  cross-implementation public-CLI mutations. The macOS-only temporary path
  was `Not applicable / changes_required / verification`; confirmed and
  replaced by the portable default temporary directory.
- `test_reviewer`: registry identity/atomic-failure coverage,
  dual-compiler reachable-field anti-replay, independent formula validation,
  and checker reproduction-mismatch evidence were incomplete. Classified
  `Not applicable / changes_required / verification`; confirmed and resolved.
  The checker tamper supplies the tampered authority's recomputed expected SHA
  so rejection occurs after the initial identity check.
- External evidence: a remote GitHub job run and required branch protection
  are unavailable. Local workflow configuration and timing do not establish
  `CI enforced` maturity.

### Layer1 linked design final-review non-convergence

- Fresh final linked-design `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer` confirmed that validator candidate SHA-256 `3d5e215d...`
  closes the collection/type classifier and reproduces authority
  `89a98fc1...`, 56 schemas, 240 enum rows, and profile `20edd38a...`.
- DREV-005 is confirmed: direct `Path.write_bytes` publication truncates the
  destination before validation and is not crash-safe. This is a design-local
  `Not applicable / changes_required / transactional consistency` defect.
- DREV-006 is confirmed: tuple quoted-child and recorded zero-item boundary
  self-test proof is incomplete. This is `Not applicable / changes_required /
  verification`.
- DREV-007 is confirmed as an implementation handoff: after design approval,
  repin the workflow and both test consumers to the reviewed validator and run
  the explicit public subprocess absent/pre-seeded/valid matrix above.
- Immutable evidence:
  `docs/reviews/semantic-ingestion-layer1-validator-collection-closure-2026-07-29/delta-round-03.md`.
- The linked design WorkPlan initially exhausted its 3/3 correction budget and
  was explicitly reopened. Replacement final round 10 approved the exact
  validator/checker pair above; implementation repin and public proof may now
  proceed.
- The user authorized up to 10 additional bounded design-revision rounds on
  2026-07-29. The linked design WorkPlan used replacement final round 10 and is
  now complete.
- Additional design rounds 1-6 produced validator `facdcbd1...` and checker
  `a79736c0...`; exact authority reproduction passes. Fresh review confirmed
  DREV-011/DREV-012 resolved, then found DREV-013 isolated-startup and
  DREV-014 exact-audit-path gaps. Immutable evidence:
  `docs/reviews/semantic-ingestion-layer1-validator-collection-closure-2026-07-29/delta-round-04.md`.
  `docs/reviews/semantic-ingestion-layer1-validator-collection-closure-2026-07-29/delta-round-05.md`.
  `docs/reviews/semantic-ingestion-layer1-validator-collection-closure-2026-07-29/delta-round-06.md`.
- Additional design round 7 produced checker `ed90fb68...` with canonical
  `python3.12 -I` startup, a same-directory stdlib-shadow proof, and denial
  evidence bound to the exact injected path.
- Additional design round 9 produced validator `538a01f1...` and
  checker `2ca3da2c...`. The isolated checker now certifies the actual captured
  checker entry's exact clean non-isolated rejection, and the validator's
  seeded-mode failure assertion passes scoped Pyright without weakening runtime
  evidence. Exact gates reproduce authority `89a98fc1...`.
- Replacement final design round 10 approved the unchanged five-identity
  baseline after all three reviewers verified matching start/end hashes and no
  confirmed `blocks_approval` or `changes_required` finding. Immutable evidence:
  `docs/reviews/semantic-ingestion-layer1-validator-collection-closure-2026-07-29/delta-round-08.md`.
- The coordinated implementation batch repinned
  `.github/workflows/pr-gates.yml`,
  `memorii/tests/unit/tools/test_ctv_binding_authority_pr_gate.py`, and
  `memorii/tests/unit/tools/test_semantic_ingestion_ctv_reference_compiler.py`
  to the approved validator/checker pair, require the exact `python3.12 -I`
  invocation, and execute the public absent/pre-seeded/valid subprocess matrix
  above. Coordinator integrity checks pass; independent implementation review
  remains.

### Layer1 final handoff review reconciliation

- Fresh `spec_auditor`: approved the complete SIA-R03/L1-008/L1-009 handoff;
  no concrete fidelity or scope gap.
- Finding `L1-HANDOFF-001`: confirmed, `Not applicable / changes_required /
  verification`. The independent compiler permits `Field(...)` through its
  generic closed-expression check for every alias, while only inventory roots
  are normalized. A copied design containing an unprojected
  `Layer1UnprojectedBad = Field(default=None)` therefore publishes successfully
  in the reference compiler and rejects in the approved design validator.
  Correct the independent declaration-validation invariant for aliases and
  model annotations while preserving valid model-field defaults and the exact
  discriminated-union metadata form; add direct, quoted, nested, alias,
  inherited, and unprojected behavioral cases.
- Finding `L1-HANDOFF-002`: confirmed, `Not applicable / changes_required /
  verification and compatibility`. Invalid public writes prove bytes, mode,
  absence, and cleanup, but valid public writes prove only exact bytes and
  cleanup. Add actual `python3.12 -I ... --write` success cases for an absent
  target (`0644`) and preseeded regular targets (preserved `0640` and `0600`).
- Finding `L1-HANDOFF-003`: confirmed, `Not applicable / changes_required /
  CI verification`. The workflow declares `timeout-minutes: 5`, but its
  structural test would pass if that budget disappeared. Assert the parsed
  timeout while retaining measured execution as supplementary evidence.
- The removed redundant checker execution has no confirmed gap: exact identity,
  recomputation, and post-identity semantic-tamper paths remain exercised.
- Resulting action: one implementation remediation worker, then focused/full
  deterministic gates and fresh three-role delta review.

### Layer1 handoff remediation round 1

- Scope: SIA-R03/L1-008/L1-009 only. Changed the independently authored CTV
  reference compiler, its two public black-box test modules, and this parent
  WorkPlan. The frozen architecture, registry, authority, validator, checker,
  profile, review reports, and runtime implementation remain excluded.
- `L1-HANDOFF-001` disposition: remediated locally. A declaration-wide,
  independently authored type-position validator now walks every alias, model
  annotation, and Protocol annotation before root projection can skip it. It
  rejects `Field(...)` as a type expression in direct, whole-quoted, nested,
  alias, inherited, and unprojected forms. Model-field defaults remain governed
  by the existing keyword-only `Field` default-policy validator. Frozen
  `Annotated[..., Field(discriminator=<string>)]` routing metadata remains
  metadata-only; this preserves the required `artifact_kind` control and the
  other frozen unprojected discriminator aliases without treating `Field` as a
  type.
- `L1-HANDOFF-002` disposition: remediated locally. Actual isolated public
  validator `--write` subprocesses now prove exact independently compiled
  bytes, no temporary sibling, absent-target mode `0644`, and regular
  preseeded target mode preservation for both `0640` and `0600`.
- `L1-HANDOFF-003` disposition: remediated locally. The workflow structural
  test parses the CTV job with `yaml.BaseLoader` and asserts
  `timeout-minutes == "5"`; the workflow timeout was not changed.
- Evidence: the Field/type and public-mode affected subset passed `23` tests
  in `12.85s`. The complete two-file Layer1 suite from `memorii/` passed
  `116` tests in `244.98s` (`4:05.69` elapsed), below the five-minute budget.
  Scoped Ruff passed; scoped Pyright using `--pythonpath ../.venv/bin/python`
  reported `0 errors, 0 warnings, 0 informations`; Python 3.12 `py_compile`
  passed. The repository Python 3.12 virtual environment supplied pytest;
  tested authority/validator/checker subprocesses remain exact
  `python3.12 -I` commands. Remote CI execution and branch protection remain
  unverified.

### Layer1 handoff remediation-round-1 delta review

- Fresh `spec_auditor` and `test_reviewer`: approved `L1-HANDOFF-001..003`.
- Fresh `correctness_reviewer`: confirmed one family-level declaration-grammar
  mismatch as `L1-HANDOFF-004`, `Not applicable / changes_required /
  verification and compatibility`.
- The independent type validator still accepts bare or quoted ellipsis, set
  literals, dictionary literals, and ellipsis in ordinary generic arguments
  for unused declarations, while the approved validator rejects them. It also
  rejects valid unused declaration data forms accepted by the approved
  grammar, including `Literal[SomeName]` and
  `Annotated[str, Field(default=None)]`.
- Coordinator disposition: confirmed by direct comparison of both closed
  classifiers. The shared invariant is separation of type positions from
  literal/metadata data positions, not the individual examples.
- Smallest correction: independently implement closed data-expression and
  Field-metadata validators; reject bare/quoted ellipsis outside the exact
  second position of `tuple[T, ...]`; remove set/dictionary acceptance from
  type positions; validate `Literal` arguments as data and all `Annotated`
  metadata as Field data. Preserve the projected generation-member exact
  discriminator enforcement in `_Projector._annotated`.
- Resulting action: one remediation-round-2 worker, paired
  cross-implementation accept/reject tests for the complete adjacent family,
  full deterministic gates, and fresh three-role delta review.

### Layer1 handoff remediation round 2

- Scope: `L1-HANDOFF-004` only. The independently authored reference compiler,
  its public subprocess corpus, and this parent WorkPlan changed. Frozen
  architecture/design inputs, registry, authority, approved validator/checker,
  workflow pins/timeout, existing public mode coverage, review reports, and
  runtime code remain unchanged.
- Disposition: remediated locally. The compiler now separates closed data
  expressions (`Name`, `Constant`, tuple/list, and unary signed data),
  Field metadata (direct `Field(...)`, no `**kwargs`, every value closed data),
  and type expressions. Quoted types parse recursively but quoted/bare
  ellipsis reject except the native second child of exact `tuple[T, ...]`;
  set/dictionary literals reject as types; `Literal` consumes data and
  `Annotated` validates a projected first type plus Field-data metadata. The
  stricter projected `TraceabilityGenerationMember` artifact-kind check remains
  solely in `_Projector._annotated`.
- Evidence: paired isolated public subprocesses reject bare/quoted ellipsis,
  set/dictionary literals, and generic ellipsis while retaining absent and
  preseeded target bytes/mode/no-temporary guarantees. Byte-identical accepted
  controls cover unprojected `Literal[SomeName]`,
  `Annotated[str, Field(default=None)]`, and discriminator metadata. The
  affected subset passed `22` tests in `12.01s`; the complete two-file Layer1
  suite passed `137` tests in `257.66s` (`4:18.37` elapsed), below the
  unchanged five-minute budget. Scoped Ruff passed; scoped Pyright with
  `--pythonpath ../.venv/bin/python` reported `0 errors, 0 warnings, 0
  informations`; Python 3.12 `py_compile` and `git diff --check` passed.
  The repository Python 3.12 virtual environment supplied pytest, while all
  tested authority/validator/checker subprocesses remain exact `python3.12 -I`
  commands. Remote CI and branch-protection evidence remain unverified.

### Layer1 implementation round 3 verifier-gap disposition

- Finding: the frozen design validator accepts reachable `list[str, int]` and
  `tuple[..., str]` annotations even though Section 3.23.4.2.1 requires closed
  collection arity and exact `tuple[T, ...]` ellipsis placement.
- Classification: `Not applicable / changes_required / verification`.
- Evidence: the hand-authored black-box probes produced design-validator exit
  `0`; the reference compiler's direct public-CLI tests reject both with
  nonzero status and no output publication.
- Disposition: confirmed. Preserve fail-closed reference behavior and enforce
  its tests in Python 3.12 CI. Do not modify or repin the frozen
  validator/checker in this implementation round. Fresh reviewers must decide
  whether this narrower legacy evidence-path gap blocks L1-008 approval or is
  an accepted limitation.

### Pre-implementation contract audit round 1

- Reviewer: read-only `spec_auditor`.
- Finding 1: missing R03 executable traceability/evidence architecture. `Not applicable`, `changes_required`, verification/governance. Disposition: confirmed; M0.
- Finding 2: ordinary-composition/C3/C4 conflict. `Not applicable`, `blocks_approval`, governance. Initial disposition: confirmed.
- Finding 3: authenticated ingress/result-access boundary absent. `P2`, `changes_required`, security/architecture. Disposition: confirmed; M1.
- Finding 4: finite writer/cutover inventory absent. `P2`, `changes_required`, persistence/migration. Disposition: confirmed; inventory now recorded, implementation in M2.
- Finding 5: pinned compatibility fixture absent. `P2`, `changes_required`, compatibility. Disposition: confirmed; M0.

### Pre-implementation contract re-audit

- Reviewer: same read-only role against pushed same-checksum closure artifacts.
- Finding SIA-PLAN-001: WorkPlan incorrectly blocked on a superseded conflict. `Not applicable`, `changes_required`, governance/rollout. Disposition: confirmed. The prior conflict disposition is superseded; preapproval and postapproval phases reconcile the sources.
- Finding SIA-PLAN-002: stale revision facts. `Not applicable`, `changes_required`, governance/verification. Disposition: confirmed and resolved in this revision.
- Result: no determinate implementation behavior requires invention; only the three registered external values remain withheld.

### Explorer reconciliation

- Architecture explorer's assertion that M1 cannot start until source reconciliation is unsupported after the same-checksum spec re-audit; design precedence and rollout gates resolve it.
- All other architecture/test/history observations were validated against direct symbols and incorporated above.

### Pre-implementation test review

- Reviewer: fresh read-only `test_reviewer`.
- TREV-001 through TREV-005: confirmed as target implementation/proof gaps, classified P1 for default composition, admission, atomicity and semantic promotion; P2 for acceptance/operability. Actions: M1 moves preapproval root gating forward; M1-M5 test matrices now include the required public-boundary, security, failpoint, independent semantic, trust, monitoring and observation cases.
- TREV-006: `Not applicable`, `changes_required`, verification/governance. Confirmed and resolved at planning level by the Test And Evidence Manifest. Actual evidence remains pending implementation.
- No current SIA behavior is marked verified from legacy tests.

### M0 independent review round 1

- Reviewers: fresh read-only `spec_auditor`, `correctness_reviewer`, and `test_reviewer` over the complete repository.
- Confirmed R03 findings (`Not applicable`, `changes_required`): closed grammar is incomplete; list continuations/nested blocks, schema/diagram units, Section-5 boundary, and parent-ID resolution are incorrect; no full frozen-design manifest/default/rule/override/anchor/approval registry exists; execution evidence lacks the specified canonical trust/lifecycle and real-execution bindings.
- Confirmed R22 findings (`P2`, `changes_required`): extraction is not dependency/runtime isolated; declaration order and corpus immutability are not bound; validator branches and complete legacy response-path compatibility are incomplete; tool portability is insufficient.
- Coordinator evidence: both parsers emitted 7,947 units but every non-null parent reference failed to resolve; a continuation-byte mutation could leave both manifests equal; a ledger with an unmapped requirement was accepted; arbitrary byte strings could be signed as a passing execution; schema/dump comparison erased field order.
- Resulting action: remediation round 2 assigned to the sole M0 worker.

### M0 remediation round 2

- Worker confirmed the full manifest cannot be produced without inventing contents absent from the design/repository.
- Coordinator disposition: `design ambiguity`, `blocks_approval`, finding type governance/verification.
- Direct evidence: Section 3.23.4 requires one explicit default for every heading, closed structural rules, assertion registry, overrides/anchors, coverage approvals, and lifecycle-bound trust artifacts. Repository search finds only schema declarations and constraints, not the required contents or approved owner/reviewer bindings.
- Resulting action: stop M0 and link a design WorkPlan. No M0 requirement is verified.

### Registry design closure and implementation re-audit

- Design revision/review operation supplied the complete canonical registry and release/trust semantics; round 04 approved the internal design.
- Fresh `spec_auditor` found no remaining behavior requiring invention.
- Confirmed implementation findings (`Not applicable`, `changes_required`): existing M0 helpers use the obsolete grammar and caller-supplied mappings; evidence uses caller HMAC secrets instead of fail-closed external release/lifecycle validation; WorkPlan baseline was stale.
- Coordinator disposition: confirmed. WorkPlan baseline and scope are updated; code remediation is the next action.

### Revision-3 pre-implementation test review

- Reviewer: fresh read-only `test_reviewer` over design SHA `b88cf96b...`, registry SHA `19c15d0...`, WorkPlan, partial M0 and full repository.
- M0-TREV-01/02 (`Not applicable`, `changes_required`, R03): confirmed. Existing helpers do not load canonical registry, implement 13-kind grammar, resolve parents, validate roots/DAG/canonical JSON, or independently byte-compare the structural manifest.
- M0-TREV-03/04 (`Not applicable`, `changes_required`, R03/R13): confirmed. Caller HMAC evidence is prohibited; revised M0 must implement typed absent-root fail-closed release/lifecycle gates plus synthetic rejection fixtures, registered report/environment bindings, DAG publication and rollback rejection without claiming external approval.
- M0-TREV-05/06 (`P2`, `changes_required`, R22): confirmed. Revised M0 must make corpus capture reproducible and environment-bound, preserve output order, expand validator/lifecycle coverage, and exercise the legacy public serialization path.
- M0-TREV-07 (`P2`, `changes_required`, R22): confirmed as planned M1 scope, not an M0 blocker. M0 may establish envelope compatibility only and must leave R22 `in progress`.
- No validation finding requires external behavior invention. `SIA-ED-TRACEABILITY-001` prevents active release acceptance, not deterministic fail-closed implementation.

### Revised M0 coordinator integrity check and remediation round 1

- Coordinator confirmed the first revised implementation still emitted heading-path hashes in `parent_invariant_id`; all 8,915 non-null references were unresolved although 28 tests passed. Disposition: confirmed, `P2`, `changes_required`, verification. Remediated by resolving heading parents after invariant construction and assigning list/table/fence descendants to their direct structural parents.
- Coordinator confirmed the release gate only returned unavailable after four presence checks. Disposition: confirmed, `Not applicable`, `changes_required`, security/governance. Remediated with canonical externally provisioned bootstrap/recovery/lifecycle/release verification, injected asymmetric verification, lifecycle ordering/time/action checks, and typed unavailable/rejected/authorized results without inventing authority material.
- Coordinator confirmed the independent checker did not rebuild registry-expanded manifest bytes. Disposition: confirmed, `Not applicable`, `changes_required`, verification/governance. Remediated with an independently implemented registry/default/rule/override/anchor expansion and exact canonical byte comparison.
- Coordinator found one Ruff and six exact Pyright errors. Disposition: confirmed, `Not applicable`, `changes_required`, verification. The same remediation writer corrected them without casts or weakened validation.
- Remaining limitation: real activation remains typed unavailable because `SIA-ED-TRACEABILITY-001` intentionally withholds authority identities, keys, and signed artifacts. This does not count as passing external acceptance.
- Resulting action: run fresh independent `spec_auditor`, `correctness_reviewer`, and `test_reviewer` over the full M0 repository state.

### Revised M0 independent review round 1

- Reviewers: fresh read-only `spec_auditor`, `correctness_reviewer`, and `test_reviewer` over the complete frozen design, canonical registry, WorkPlan, and repository.
- Confirmed R03 traceability findings (`Not applicable`, `changes_required`, verification/governance): duplicate heading paths collapse to the last occurrence; the independent coverage API still accepts caller mappings; full R01-R23 self/secondary/default/rule/override/anchor and coverage-approval closure is not proved; specialized report/profile registry digests are not recomputed.
- Confirmed R03/R13 trust findings (`Not applicable`, `changes_required`, security/verification): execution evidence does not consume the registered runner report; runner schema/environment fields are insufficiently validated; lifecycle record/root signatures and digests, recovery policy, release root bindings, issuer eligibility, active pointer and successor/rollback chains are incomplete. The current synthetic empty-lifecycle release can authorize while legitimate successors reject.
- Confirmed R22 M0 compatibility finding (`P2`, `changes_required`, compatibility/verification): corpus/environment/capture bytes are not immutably checked; validator coverage is partial; tests do not exercise the public nested provider serialization and legacy-reader boundary.
- Unsupported/duplicate dispositions: requests for the authenticated semantic-result lookup remain planned M1, not an M0 remediation item; repeated descriptions of the same trust, mapping, and R22 proof defects are consolidated into the findings above.
- Resulting action: send the consolidated confirmed findings to one M0 remediation-round-2 worker and rerun coordinator checks plus fresh reviewers after material correction.

### Revised M0 remediation round 2

- Implemented occurrence-safe duplicate-heading parents, independent raw canonical registry loading/rebuild, release-bound registered-report verification, typed coverage approvals/root validation, nonempty lifecycle rejection, and active-release-pointer continuity/root checks.
- Focused incremental suites, changed-set Ruff/Pyright, and `git diff --check` passed after each increment.
- Non-convergence: despite repeated continuations, the sole worker did not complete signed lifecycle/recovery-policy replay integrated with issuer eligibility/release authorization or the isolated exhaustive R22 `ProviderMemoryService`/`ProviderSyncResult` public-envelope and legacy-reader proof. No design ambiguity was identified.
- Disposition: remaining findings stay confirmed; preserve the valid partial corrections and assign only these two bounded gaps to the final allowed M0 remediation round.

### Revised M0 remediation round 3

- Implemented canonical signed lifecycle-root and record replay, independently provisioned recovery-policy/root validation, issuer eligibility state, complete registry/release-root bindings, and signed active-pointer checks. Deterministic synthetic signatures test the contract without representing operational authority.
- Expanded compatibility capture bindings for baseline/source/archive/tool/runtime/distribution/fixture digests and verified two byte-identical clean recaptures. Added `ProviderSyncResult` public-envelope capture and legacy-reader evidence.
- Coordinator full focused suite passed `40` tests in `90.24s`; Ruff passed. A bounded same-round cleanup fixed five exact Pyright narrowing/resource-path errors; exact Pyright then reported zero findings and `git diff --check` remained clean.
- External limitation: real authority identities, keys, and signed releases remain unavailable, so operational activation remains typed unavailable.
- Resulting action: fresh independent milestone review round 2. Any confirmed changes-required finding blocks M0 because the three-round remediation budget is exhausted.

### Revised M0 independent review round 2

- Reviewers: fresh read-only `spec_auditor`, `correctness_reviewer`, and `test_reviewer`; all inspected the full repository and independently reported changes-required findings.
- Confirmed trust defect (`Not applicable`, `changes_required`, R03/R13): a cryptographically valid release signed by an unlisted, lifecycle-ineligible key returns `TraceabilityGateAuthorized`; lifecycle state is not applied to release issuer eligibility.
- Confirmed progression defect (`Not applicable`, `changes_required`, R13): the gate hard-requires genesis coordinates and supplies a singleton history to the pointer verifier, so a valid sequence-2 successor/rotation/higher-sequence rollback release rejects.
- Confirmed evidence bypass (`Not applicable`, `changes_required`, R03/R13): the tested approval-capable path still accepts caller-supplied HMAC issuer secrets and does not require the registered release-bound report/environment path.
- Confirmed registry/report integration defect (`Not applicable`, `changes_required`, R03): specialized report-schema/profile roots and nested artifacts are not fully recomputed/validated, and the release-bound report/coverage APIs are not exercised end to end.
- Confirmed compatibility proof defect (`P2`, `changes_required`, R22): the capture tool emits `ProviderSyncResult` and capture-manifest data, but the committed tests discard or never assert those artifacts, never exercise the actual public/legacy reader path, and do not bind the checked capture-tool/environment digests.
- Duplicate descriptions across reviewers were consolidated; M1 result lookup findings were excluded. The focused suite still passed 40 tests, demonstrating insufficient proof rather than resolving these defects.
- Result: M0 is blocked. Three revised-baseline remediation rounds are exhausted with confirmed changes-required findings remaining.

### User-authorized M0 closure split

- Date: 2026-07-27
- Authorization: the user explicitly approved continuing implementation beyond the exhausted original M0 remediation budget.
- Scope remains unchanged; no design revision or new behavior is authorized.
- M0A - Trust and evidence closure: R03/R13 lifecycle-qualified issuer authorization, successor/rotation/recovery/rollback release progression, specialized registry/report/profile validation, and one release-bound evidence path. Budget: up to 3 remediation rounds.
- M0B - Provider-envelope compatibility closure: R22 content-addressed reproducible capture, exact `ProviderSyncResult` public serialization, service path, and frozen legacy-reader proof. Budget: up to 3 remediation rounds.
- Sequencing: M0A is the only next milestone. M0B remains pending until M0A completes independent review.

### M0A pass/round 0

- Reviewer: coordinator implementation pass; independent review has not yet run.
- Scope: R03/R13 registry specialization, lifecycle signer eligibility, release-bound evidence, and legacy HMAC authority removal only.
- Result: confirmed registry, lifecycle progression, and caller-HMAC findings are remediated in code. The fixtures cover signed successor, rotation, threshold recovery, explicit higher-sequence rollback, incomplete threshold rejection, and release-bound report/environment validation; focused deterministic checks pass.
- Resulting action: one independent M0A review round over the complete current R03/R13 state.

### M0A independent review round 1

- Reviewers: fresh read-only `spec_auditor`, `correctness_reviewer`, and `test_reviewer`; full current R03/R13 state reviewed.
- Confirmed registry defect (`Not applicable`, `changes_required`): the independent raw-byte rebuild still uses generic formulas for specialized report/profile roots and disagrees with the generator on the canonical registry.
- Confirmed release defects (`Not applicable`, `changes_required`): complete history and signed current pointer remain optional; expired releases authorize; lifecycle rotations can introduce unprovisioned targets; issuer intervals are not preserved for historical releases.
- Confirmed recovery defects (`Not applicable`, `changes_required`): threshold counting is not distinct-root based and revoked/compromised/expired recovery roots can remain eligible.
- Confirmed evidence defects (`Not applicable`, `changes_required`): a caller can construct `TraceabilityGateAuthorized`; group/schema/profile inputs are caller-selected; the verifier does not resolve the execution root/mappings/registered schema/profile from the canonical registry or compare the complete environment observation.
- Confirmed evidence-coordinate defect (`Not applicable`, `changes_required`): registered R03/R13 pytest nodes do not exist or do not match implemented test names, so the registered commands are uncollectable.
- Duplicate reports were consolidated. All findings are determinate implementation corrections; no design ambiguity exists.
- Resulting action: one M0A remediation-round-1 worker.

## Blockers And Limits

- Milestone remediation budget: 3 rounds each.
- M0 remediation rounds used against the old baseline: 2; the revised approved baseline restarts M0 conformance review because the governing contract and canonical inputs changed materially.
- Final review budget: 3 rounds.
- Current Layer-1 design blocker: none. The approved registry
  `8e6395e2...` / authority `f7c0d000...` handoff is implemented and locally
  verified across both 148-member loaders, consumer pins, exact structural
  coverage, acceptance/evidence paths, and the four public marker families.
  Fresh independent round-20 review and targeted delta verification found no
  remaining validated P1/P2 defect. Evidence
  against registry `38c45adc...` / authority `89a98fc1...` is historical and
  cannot prove the replacement candidate. Remote CI and branch protection
  remain unavailable external evidence. Historical M0A-C2 non-convergence and
  the stale C1 52-schema fixture package remain outside this replacement
  Layer-1 boundary.
- External activation/certification limit: the three `SIA-ED-*` artifacts are unavailable; their fail-closed paths remain implementable.
- Environment limit: live/external certification dependencies remain unavailable; deterministic local tooling is available in `.venv`.
- Design movement: any material checksum change stops the affected milestone.
- External acceptance limit: traceability architecture acceptance requires the separately provisioned artifacts in `SIA-ED-TRACEABILITY-001`; their absence must be represented by typed fail-closed outcomes.

| Gap | Requirement | Severity | Attempts | Why unresolved | Required next step |
| --- | --- | --- | --- | --- | --- |
| Missing registry contents | R03 | formerly Not applicable / blocks_approval | Resolved by design revision 3 | Canonical package and review now exist | Implement revision-3 contract |
| Exact closed trust-artifact schemas and canonical preimages incomplete | R03, R13 | Not applicable / changes_required | M0A rounds 1-3 | Purpose ownership and watermark are fixed, but complete schema migration remains unfinished | Authorize a smaller schema-closure milestone |
| Full structural/coverage/execution artifact-byte closure incomplete | R03, R13 | Not applicable / changes_required | M0A rounds 1-3 | Approval still lacks independent loading/recomputation of the complete generation | Authorize a smaller artifact-closure milestone |
| Specialized registry/report/profile validation incomplete | R03 | resolved | M0A remediation round 1 | Canonical raw specialized-root parity passes | Closed for M0A |
| Public provider-envelope compatibility proof incomplete | R22 | resolved | M0B rounds 1-3 | Capture provenance, validator/default coverage, reader independence, public failure paths, RFC 8785 encoding, and reader completeness now pass the focused deterministic gate | Closed for M0B; M1 result lookup remains separate |
| Legacy payload byte representation conflicts | R22 | resolved | M0B review round 1 | The design now preserves declaration-order legacy payload bytes and applies RFC 8785 only to outer corpus/manifest artifacts | Closed by the M0B byte-domain design decision |
| Layer1 validator consumer handoff | SIA-R03, L1-008, L1-009 | resolved | Complete approved-pin handoff through bounded round 20, including typed parser-hostile and regex-overflow closure | Local public parity, exact 148/148 coverage, CI structure, exact checker, static gates, acceptance/evidence, complete focused suites, and final independent review pass | Closed; preserve the pinned candidate |
| Equal-version replay semantics conflict | SIA-R10, SIA-R18 | resolved | M4 readiness audit plus linked design WorkPlan | The user-approved fail-closed rule is frozen in the bound decision artifact and reconciled with the event model and conflict-attention design | Closed; preserve the frozen hashes and validator gate |

## Historical Next Action (Superseded)

Complete `docs/work/semantic_ingestion/remaining-replay-projection-contract-closure.design.plan.md`,
freeze its canonical hashes and reviews, then resume with the authenticated
conflict reader and snapshot-paginated `memorii_list_conflicts` slice.

This action was completed or superseded by the later M4 implementation record.
The only active next action is at the top of this WorkPlan.

## Outcome And Retrospective

The M0B design contradiction and all validated M0B changes-required findings
are resolved. M0B is complete against the frozen two-domain provider-envelope
contract. M0A remains separately blocked, M1 result lookup remains pending, and
no production provider envelope changed.

- 2026-08-01: M2 completed after final requirement reconciliation and three-role
  closure review. The focused semantic-ingestion suite passes 128 tests; the
  affected provider/storage suite passes 74 tests with one pre-existing
  environment-dependent skip. Scoped Ruff passes, scoped Pyright reports zero
  findings, and `git diff --check` is clean. Independent spec, correctness, and
  test reviewers report no remaining M2 changes-required or blocking finding.
  SIA-R10's full event/replay algebra remains M4 and learned semantic payload
  behavior remains M3.

- 2026-08-01: Full M2 closure review round 1 found one P1 and seven P2/code or
  evidence defects. All were confirmed and remediated: evidence-only writers
  now reject graph/event effects at API and guarded-store boundaries; writer
  cutover freezes new old-epoch admissions before drain inspection and
  atomically persists the verified migration plan/certificate/activation with
  the successor epoch; planned leases reclaim; lease expiry is rechecked under
  the backend write lock; reserved generation identities are rejected; prior
  complete artifact generations can satisfy later closure; group graph,
  observation, read-set, and final-result closure CAS are enforced; and M2
  atomic admission can publish prepared M1 evidence plus pending operation in
  one batch. The focused M2 suite passes 54 tests, scoped Ruff passes, scoped
  Pyright reports zero findings, and the next action is fresh independent
  three-role review of this remediation delta.
- 2026-08-01: M2 closure review round 2 confirmed the round-1 graph authority,
  revision CAS, reclaim, collision, and artifact-reuse fixes, then found four
  further P2 contract gaps and five required evidence gaps. Remediation now
  rejects partial atomic-admission recovery; requires exact checkpoint,
  terminal-group, and finalization singleton cardinalities plus complete first
  planned closure; clears and verifies terminal leases; persists the migration
  checkpoint and complete migrated target records atomically with the successor
  writer; verifies target-record digests against the finite plan; synchronizes
  process contention; and covers JSONL group/finalization lost-ack recovery,
  multi-group closure order, active old-epoch leases, authorization rotation,
  empty checkpoints, and duplicate terminal members. The focused M2 suite now
  passes 59 tests and scoped Pyright reports zero findings. Next action: fresh
  independent round-3 closure review.

### M0A remediation round 1

- Scope: R03/R13 only; no R22 or M1 changes.
- Remediated the independent raw specialized report-schema/profile root rebuild,
  mandatory complete release history and signed current pointer, current-release
  expiry rejection, single-active-release enforcement, and release-bound raw
  registry approval orchestration.
- Added registered, collectable R03 and R13 acceptance coordinates and changed
  their registry status to `repository_evidenced`; R03 now enumerates every
  parametrized mutation node explicitly and in deterministic order.
- Evidence: focused traceability suites passed `33` tests; the broader R03
  traceability tool suites passed; R03 and R13 collect-only selections produced
  exactly `11` and `1` nodes respectively; changed-set Ruff and `git diff
  --check` passed; independent raw manifest rebuild equals the generator.

### M0A independent review round 2

- Fresh `spec_auditor`, `correctness_reviewer`, and `test_reviewer` confirmed the specialized raw-root parity and mandatory history/pointer-presence fixes.
- Confirmed expiry defect: current release detection compares separately decoded dictionaries by identity, so an expired active release can authorize.
- Confirmed lifecycle/recovery defects: successor roots are not independently provisioned; issuance-time signer intervals are not retained; recovery counts signer aliases rather than distinct eligible roots and does not exclude revoked/compromised/expired roots.
- Confirmed evidence defects: the lower-level helper remains public and accepts caller authority; registered schema/profile resolution and complete environment comparison are incomplete.
- Confirmed registered evidence weakness: R03/R13 acceptance nodes are metadata/self-coordinate checks rather than end-to-end trusted execution.
- Disposition: all are determinate `Not applicable` / `changes_required` findings. Assign one M0A remediation-round-2 worker.
- Environment note: Pyright reached only two missing-import findings for
  `pytest` in existing unit tests when pointed at the supplied venv; no changed
  production module error was reported.
- Resulting action: fresh independent M0A review round 2.

### M0A remediation round 2

- Scope: R03/R13 only; no R22 or M1 changes.
- Replayed lifecycle authority as provisioned typed root coordinates with
  signer eligibility intervals; current release selection now uses the signed
  pointer/release digest coordinate and enforces the inclusive issued/expiry
  boundary. Rotation and recovery require independently provisioned successor
  roots, while revoke and compromise terminate the target interval.
- Recovery signatures now bind distinct policy-listed recovery-root digests;
  replay rejects duplicate aliases, inactive, expired, revoked, compromised,
  or unprovisioned recovery roots. The policy signer is checked against the
  active bootstrap interval.
- The caller-authority report helper is private. The sole public approval
  orchestrator loads the raw registry, resolves group/schema/profile by their
  registered coordinates, invokes the release gate, and validates closed
  report schema, runner identity/time ordering, and all ten runner-environment
  profile categories before returning a report.
- Evidence: focused lifecycle/evidence tests passed `31`; lifecycle suite
  passed `24` after expiry-boundary additions; changed-set Ruff and `git diff
  --check` passed. The supplied parent-relative venv path was absent from this
  checkout; the repository `.venv/bin/python` was used instead.
- Resulting action: fresh independent M0A review round 3, with reviewers to
  confirm the registered R03/R13 acceptance nodes are end-to-end normative
  orchestrator proofs rather than metadata-only coordinates.

### M0A independent review round 3

- Confirmed recovery-purpose defect: recovery roots can sign ordinary releases/pointers directly instead of being limited to threshold recovery.
- Confirmed artifact-closure defect: structural, coverage, and execution-root bytes are not loaded/recomputed by the public approval orchestrator.
- Confirmed external-trust defect: caller-supplied verifier-held material remains an approval input instead of an acceptance-owned root-channel dependency.
- Confirmed durable rollback defect: monotonicity lacks an independently persisted authenticated watermark outside caller-supplied history.
- Confirmed closed-schema/lifecycle defects: typed trust artifact fields, recovery-root/policy succession, historical purpose-qualified intervals, and concrete runner observations remain incomplete.
- Confirmed registry-coordinate defect: registered R03/R13 nodes are stale after acceptance-test renaming and exact commands fail collection.
- Disposition: consolidated `Not applicable` / `changes_required` findings. Use the final M0A remediation round; any remaining confirmed finding blocks M0A.

### M0A remediation round 3 - non-convergence

- Implemented purpose-separated recovery roots, composition-owned `AcceptanceTrustStore`, an acceptance-owned monotonic watermark, executable registered R03/R13 nodes, and direct recovery-key release/pointer rejection.
- Evidence: 34 focused tests passed; exact registered nodes collect and execute; Ruff passed; Pyright reported zero findings; `git diff --check` passed.
- Remaining confirmed gaps:
  - the approval path does not independently load and recompute the full structural-manifest, coverage-root/approvals, execution-root/records, and exact mapping artifact generation;
  - bootstrap/recovery/policy/lifecycle/release/pointer artifacts have not all migrated to the exact closed typed schemas and canonical preimages in the design.
- These are determinate implementation gaps, not design ambiguities. M0A is blocked after exhausting its authorized three-round budget, and M0B remains pending.

### User-directed M0B continuation

- The user explicitly directed implementation to continue and finish M0B while preserving M0A's blocked findings.
- Scope is R22 legacy provider-envelope compatibility proof only; this does not make overall M0 complete.
- Budget: implementation pass plus up to three remediation rounds.
- Completion requires an immutable environment-bound capture manifest, exhaustive independently captured validator behavior, exact `ProviderEvolutionOutcome` and `ProviderSyncResult` bytes, actual service/integration public serialization, a frozen independent legacy reader, reproducible clean recapture, and tamper rejection.

### M0B implementation pass

- Scope: SIA-R22 legacy provider-envelope compatibility proof only. No provider
  production model, service, or integration semantics changed; M1 result lookup
  remains out of scope.
- Replaced the initial narrow fixture with
  `memorii/tools/extract_provider_compatibility_fixture.py`, which validates the
  pinned commit/tree/blob/source, executes a self-contained capture program from
  a temporary `git archive` extraction, and binds immutable inputs plus the
  capture tool/program, interpreter executable/version/digest/implementation,
  Pydantic and installed-distribution fingerprints, archive digest, generated
  sibling-file digests, and corpus digest. The manifest intentionally excludes
  its own digest and documents that boundary to avoid a self-digest paradox.
- Captured `ProviderEvolutionOutcome` and `ProviderSyncResult` JSON schemas,
  field order/default/null behavior, enum members, accepted/rejected boundary
  cases, 2,880 lifecycle-validator branch vectors, ordered SyncResult cases,
  and canonical Unicode-preserving public bytes. The corpus additionally
  executes the baseline `ProviderMemoryService.sync_event` and
  `HermesMemoryProvider.sync_turn` public paths from the archive.
- Added the separately authored dependency-free frozen legacy reader and target
  tests that replay every matrix vector, validate manifest/file/corpus bindings,
  reject a field-order mutation, run two clean recaptures with byte equality,
  and demonstrate corpus tamper-digest rejection.
- Evidence: from repository root,
  `./.venv/bin/python memorii/tools/extract_provider_compatibility_fixture.py --repository . --output memorii/tests/fixtures/semantic_ingestion/provider_compatibility --python "$(pwd)/.venv/bin/python"` exited 0;
  `cd memorii && ../.venv/bin/pyright --pythonpath "$(../.venv/bin/python -c 'import sys; print(sys.executable)')" tools/extract_provider_compatibility_fixture.py tests/unit/core/semantic_ingestion/test_provider_compatibility.py` reported 0 errors;
  `../.venv/bin/python -m pytest -q tests/unit/core/semantic_ingestion/test_provider_compatibility.py tests/unit/core/test_provider_service.py -p no:cacheprovider` reported 42 passed;
  exact scoped Ruff passed; `git diff --check` exited 0.
- Status: M0B implementation pass complete; independent review remains required
  before R22 can be marked verified. M0A remains blocked and this evidence does
  not close it or authorize M1 work.

### M0B independent review round 1

- Completed reviewers: fresh `spec_auditor`, fresh `test_reviewer`, and a substitute fresh `correctness_reviewer`; the original correctness pass was interrupted before completion and is not counted.
- Confirmed `P2` / `changes_required` implementation gaps:
  - outcome matrix omits `extraction_failure_code`, `primary_failure_code`, `retryable`, and `attempt_count` boundaries;
  - fresh captures are not compared byte-for-byte with committed evidence and no manifest verifier rejects coordinated tampering;
  - runtime/dependency provenance is collected in the wrapper rather than the child interpreter executing the baseline;
  - the capture tool generates the purported independent reader, whose type/null/default/enum checks are incomplete;
  - `ProviderSyncResult` omission/default/invalid cases and actual retryable/terminal/primary/fallback/mixed service/Hermes paths are incomplete.
- Confirmed `Not applicable` / `blocks_approval` design conflict:
  - the design requires the baseline payload bytes to use UTF-8 RFC 8785 JSON, which sorts object keys lexicographically;
  - the same section freezes model declaration order for the legacy payload bytes;
  - these differ (`attempt_count` first under RFC 8785 versus `operation_id` first under declaration order).
- Coordinator disposition: pause remediation and resolve the governing representation. The narrow recommended resolution is to make RFC 8785 the outer content-addressed artifact encoding while preserving opaque legacy public payload bytes in declaration order, but that semantic split requires design approval.

### M0B byte-domain design decision

- Governing design SHA-256:
  `f277fb262b2f8335aad4207f511942c5680510ff827b0291fe9c9ff4b0af6ea6`.
- The governing design now defines two disjoint representations.
- `LegacyProviderPayloadBytes` preserve the pinned baseline serializer's model
  declaration order, mapping insertion order, explicit nulls, enum strings,
  compact separators, and UTF-8 strings. They are opaque compatibility bytes
  and are never RFC 8785-normalized.
- The capture corpus and manifest are outer RFC 8785 artifacts. Their
  designated `*_bytes` strings decode back to the exact legacy payload bytes;
  outer canonicalization may not parse or reserialize those strings.
- Result: the `Not applicable / blocks_approval` M0B design finding is closed.
  The confirmed P2 implementation findings from review round 1 remain frozen
  and are the only authorized M0B remediation scope.
- Verification after the design-only change: the unchanged provider
  compatibility suite passed 6 tests, the unchanged traceability-registry suite
  passed 26 tests, and the implementation worktree received no unstaged edit.
  M0B must still replace the outer capture serializers with verified RFC 8785
  encoding and keep the embedded declaration-order `*_bytes` strings opaque.

### M0A remediation round 3

- Scope: R03/R13 only; no R22 or M1 changes.
- Recovery roots now remain in a purpose-qualified recovery interval and cannot
  sign ordinary releases or active pointers. Threshold recovery still installs
  only independently provisioned bootstrap/release successors.
- The public registered-approval entry point now takes an
  `AcceptanceTrustStore` constructed at composition time. It no longer accepts
  `VerifierHeldTrustMaterial` or a verification callback from the request; the
  store also owns the durable monotonic active-release watermark.
- Release verification rejects a history/pointer coordinate below the stored
  watermark and a same-coordinate digest substitution. A higher coordinate is
  the only permitted progression.
- Registered R03/R13 command nodes now exist as actual end-to-end acceptance
  tests, not metadata-only coordinates. Added negative tests cover a recovery
  root directly signing a release/pointer and replay below an owned watermark.
- Evidence: focused release/approval suite -> `34 passed`; exact registered
  collect-only -> `2 tests collected`; exact registered execution -> `2
  passed`; changed-surface Ruff -> `All checks passed!`; exact changed-surface
  Pyright -> `0 errors, 0 warnings, 0 informations`; `git diff --check` ->
  clean.
- Resulting action: coordinator conducts the required final independent M0A
  review and classifies every finding.

### M0B remediation round 1

- Scope: R22 only. M0A remains blocked and M1 remains excluded.
- Replaced ordinary sorted/indented outer JSON with an explicitly bounded
  UTF-8 RFC 8785/JCS encoder for corpus and manifest artifacts. The committed
  bytes have no newline or indentation. The compatibility payload strings stay
  opaque: the outer codec receives them as strings and never parses or
  reserializes their declaration-order JSON.
- The isolated archive child now fingerprints its own executable, version,
  implementation, Pydantic distribution, dependency versions, and installed
  distribution files. A missing separately owned reader is now an explicit
  capture failure; the extractor neither creates nor rewrites it.
- Regenerated the corpus with actual NUL, emoji, combining Unicode, lifecycle
  failure-code/attempt/retry axes, SyncResult omission/default/null/invalid
  vectors, and child-bound runtime provenance. The independently owned reader
  now validates closed field order, required types, null/default representation,
  enum sets, list/mapping shape, and nested outcomes.
- Added the independently implemented outer-byte verifier and a separately
  owned expected-manifest SHA-256 root. It checks exact JCS bytes, corpus/file
  bindings, committed-root equality, clean recapture equality, and corpus or
  manifest tampering rejection.
- Evidence: repository-root capture completed successfully; from `memorii/`,
  `../.venv/bin/python -m pytest -q tests/unit/core/semantic_ingestion/test_provider_compatibility.py tests/unit/core/test_provider_service.py -p no:cacheprovider`
  -> `42 passed`; scoped Ruff -> `All checks passed!`; scoped Pyright -> `0
  errors, 0 warnings, 0 informations`; `git diff --check` -> clean.
- Next action: coordinator performs the required independent M0B remediation
  review and classifies findings against the frozen two-domain contract.

### M0B remediation round 1 follow-up

- Corrected the frozen reader's enum-container annotation from invariant
  `set[str | None]` to covariant `collections.abc.Container[str | None]`.
  Scoped Pyright now checks the reader itself, rather than excluding it.
- The prior deterministic service capture was insufficient for the frozen M0B
  public-path finding. The isolated baseline program now additionally captures
  actual `ProviderMemoryService`/`HermesMemoryProvider` bytes for deterministic
  abstention, retryable provider failure, terminal non-retryable output failure,
  committed primary extraction, committed fallback extraction, and an ordered
  mixed Hermes turn. Controlled extractors are used only inside the archived
  capture program; production provider code remains unchanged.
- Regenerated the content-addressed corpus and manifest; updated the separate
  expected-manifest authority after the reader/tool/corpus binding changed.
- Evidence: from `memorii/`, exact focused provider/service tests -> `42
  passed`; scoped Ruff -> `All checks passed!`; scoped Pyright including
  `legacy_reader.py` -> `0 errors, 0 warnings, 0 informations`; `git diff
  --check` -> clean.
- Next action: coordinator conducts M0B independent review against the
  expanded public-path corpus.

### M0B independent review round 2 dispositions

- `P2 / changes_required / compatibility`: confirmed that Python `repr` is not
  ECMAScript number serialization at the RFC 8785 thresholds. Remediated by a
  manifest-bound Node.js ECMAScript primitive encoder and independent fixed
  known-answer vectors for negative zero, exponent thresholds, controls,
  Unicode, and UTF-16 member ordering.
- `P2 / changes_required / verification`: confirmed that SyncResult verdicts
  discarded original inputs, target tests did not recreate public service
  scenarios, and the reader omitted cross-field invariants. Remediated with
  retained input/normalized-byte/error verdicts, current-target controlled
  scenarios, and closed reader lifecycle checks plus adversarial mutations.
- `Not applicable / changes_required / governance`: confirmed executable root
  loading and skip-on-missing-git weakened the claimed deterministic gate.
  Remediated with a strict static SHA-256 authority artifact, tamper test, and
  fail-closed tool/gate prerequisites. The repository authority proves only
  deterministic repository consistency; operational acceptance remains
  unavailable until an external acceptance owner supplies the root through its
  independent channel.

### M0B remediation round 2

- Scope: R22 M0B only. Production provider owners, M0A, and M1 are unchanged.
- The outer corpus and manifest use a standards-native ECMAScript implementation
  of RFC 8785 number/string serialization and UTF-16 key ordering. The exact
  executable, version, binary digest, and canonicalization-program digest enter
  the capture manifest.
- SyncResult validation records the original JSON input and either exact
  normalized legacy bytes or the baseline error class. Cases cover omissions,
  explicit null, unknown members/domains, nested outcomes, non-string IDs and
  reasons, and wrong list/mapping/outcome containers. Target tests replay every
  verdict through current `ProviderSyncResult.model_validate`.
- Current target tests reconstruct abstention, retryable failure, terminal
  invalid output, committed primary, committed fallback, and ordered mixed
  Hermes scenarios. They compare parsed behavior with baseline capture and pass
  current public bytes through the frozen reader; `service_path_bytes` remains
  diagnostic scenario evidence, not a new exact-byte oracle.
- Reader validation now implements all frozen baseline cross-field lifecycle
  invariants and rejects negative field/type/enum/order/nested mutations.
  Unicode tests assert actual NUL, emoji UTF-8, and combining-code-point values;
  opaque embedded strings survive outer round trip without parsing, and member
  order mutation changes the corpus digest and fails the pinned manifest root.
- Static repository authority is `expected_manifest.sha256`; it is parsed as a
  strict literal and never executed. Coordinated artifact substitution fails
  unless this independently owned root is also changed, which the tamper test
  rejects. External operational trust is explicitly not supplied by this
  repository proof.
- Evidence from `memorii/`: focused compatibility/provider suite collected 47
  tests and reported `47 passed in 26.43s`; that suite performs two fresh
  isolated recaptures and byte-compares each corpus/manifest with committed
  evidence. Scoped Ruff reported `All checks passed!`; scoped Pyright reported
  `0 errors, 0 warnings, 0 informations`; repository-root `git diff --check`
  exited successfully with no output.
- Next action: coordinator performs the independent M0B remediation-round-2
  review and classifies every finding against the frozen two-domain contract.
- Superseded M0A-C1 pin: output digest
  `3d1bb02bffdb2db17d41269394d69284234e2aebdcd9348a93a3419b6b1e575e`
  was bound to the pre-correction design and is not completion evidence.
- M0A-C1 remediation evidence from `memorii/`:
  `../.venv/bin/python -m pytest tests/unit/tools/test_semantic_ingestion_fixture_authority.py -q -p no:cacheprovider`
  -> nine test functions, 24 collected items, `24 passed in 67.02s`. The suite
  executes offline
  `python -m pip wheel . --no-deps --no-build-isolation` plus archive,
  installed-target, and unimportability checks with `PIP_NO_INDEX=1`. Scoped
  Ruff -> `All checks passed!`; scoped Pyright -> `0 errors, 0 warnings, 0
  informations`; repository-root `git diff --check` -> clean. Both isolated
  elaborators reproduced pinned output digest
  `f2f16fd6014baf71aafe21acbd174aaee8fbd61fa7657fbfec3326499c9a2826`
  in
  `memorii/tests/fixtures/semantic_ingestion/traceability_golden_vectors/c1-v1.expected.json`.
- M0A-C1 next action: fresh independent C1 milestone review against frozen
  design `158277cd433c85714253359e134c94ece0f3ad59d2b3f1b9a403c295417a397e`
  and the bounded fixture-only scope.

### M0A-C1 independent review round 1

- Reviewers: fresh `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer` over the frozen C1 design and complete fixture-only candidate.
- Finding C1-R1-01: `Not applicable / changes_required / verification trust`.
  Confirmed. The independent elaborator copied design table values without
  independently deriving, signing, and verifying all four RFC 8032 vectors.
- Finding C1-R1-02: `Not applicable / changes_required / input validation`.
  Confirmed. Neither elaborator separately proved the strict raw-design,
  marker-cardinality, standalone-marker, or exact-fence preflight.
- Finding C1-R1-03: `Not applicable / changes_required / verification
  coverage`. Confirmed. The mutation harness could pass after only the first
  elaborator rejected and lacked valid-hex field, signer-order, and duplicate
  signer mutations.
- Finding C1-R1-04: `Not applicable / changes_required / provenance and
  isolation`. Confirmed. The pin did not independently enumerate the exact 52
  schemas and four vectors, and production/wheel exclusion was not proved.
- Finding C1-R1-05: `Not applicable / changes_required / governance`.
  Confirmed. The active registry baseline mislabeled the historical raw
  checksum and did not distinguish it from the domain-separated source
  identity.
- Coordinator disposition: all five findings are confirmed and determinate.
  Remediation is limited to C1 test fixtures, tests, and WorkPlan evidence.

### M0A-C1 remediation round 1

- The independent elaborator now implements its own pure RFC 8032 key
  derivation, deterministic signing, canonical point/scalar checks, and
  verification for every extracted signer row. The successor seed is still
  independently derived from its fixed domain.
- Each elaborator separately validates strict raw design bytes, final LF,
  standalone unique markers, and exact adjacent `text` fences before
  extraction. The test harness always executes both paths and requires
  identical rejection outcomes.
- Independently owned pins enumerate all 52 ordered schema IDs and all four
  fixed signer vectors. Adversarial coverage includes each seed/public/message/
  signature field, signer swaps/duplicates, marker/fence variants, CRLF, BOM,
  NUL, CR, and final-LF mutations.
- Production AST/text scanning finds no fixture path, ID, or seed. A local
  no-network wheel built with `--no-build-isolation`; archive, installed-tree,
  and import checks found no C1 fixture, elaborator, package path, or private
  seed.
- Active registry evidence is raw SHA-256 `38c45adc...` and domain source
  identity `66c3414e...`; `19c15d0a...` is historical only.
- Next action: fresh independent C1 milestone review. C2 ancestry, persistence,
  and public-gate work remain excluded.

### M0A-C1 independent review round 2

- Reviewers: fresh `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer` over the complete round-1 C1 candidate.
- Finding C1-R2-01: `P2 / changes_required / execution evidence`. Confirmed.
  Current broader M0A tests still use synthetic approval/runner evidence. This
  is outside the bounded C1 profile/fixture-authority layer and is assigned to
  M0A-C4; no acceptance-gate change is authorized in C1.
- Finding C1-R2-02: `Not applicable / changes_required / error contract`.
  Confirmed. The standard-library elaborator leaked `UnicodeEncodeError` for
  non-ASCII bytes inside an otherwise valid UTF-8 marked block instead of the
  common fail-closed `ValueError`.
- Finding C1-R2-03: `Not applicable / changes_required / package isolation`.
  Confirmed. Manual wheel evidence existed, but the focused suite did not
  execute the offline build/archive/install/import isolation proof.
- Finding C1-R2-04: `Not applicable / changes_required / evidence
  accounting`. Confirmed. The WorkPlan reported only passed items and did not
  distinguish nine test functions from their parametrized collected items or
  record the exact executable wheel command.
- Coordinator disposition: all findings are confirmed. C1-R2-02 through
  C1-R2-04 are determinate C1 fixes; C1-R2-01 remains required and is assigned
  to C4 without modifying the current gate.

### M0A-C1 remediation round 2

- The standard-library marked-block extractor now translates
  `UnicodeEncodeError` to the common `ValueError`; both elaborators reject the
  UTF-8 non-ASCII marked-content mutation.
- The focused suite now executes an offline
  `python -m pip wheel . --no-deps --no-build-isolation` with
  `PIP_NO_INDEX=1`, inspects archive paths and relevant contents, installs the
  wheel into an isolated target, and proves the fixture module is absent and
  unimportable.
- The C1 test module contains nine test functions and collects 24 parametrized
  test items. Exact final pass counts and commands are recorded below.
- Next action: fresh independent C1 milestone review. C2 and the C4
  approval/runner remediation remain excluded from this writer scope.

### M0A-C1 final review and completion

- Reviewers: final fresh `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer` over the frozen design SHA-256
  `158277cd433c85714253359e134c94ece0f3ad59d2b3f1b9a403c295417a397e`,
  the complete C1 fixture-only candidate, and its production-isolation proof.
- Disposition: no validated C1 `blocks_approval` or `changes_required` finding
  remains. The synthetic execution-evidence concern remains assigned to C4 and
  is not C1 scope.
- Completion evidence: the two isolated elaborators reproduce the pinned C1
  bytes and all 24 focused test items, including offline wheel isolation; C1
  remains strictly test-only and does not add a durable store, public gate, or
  production runtime dependency.
- C1 status: complete. C2 is now active with the frozen C1 profile registry,
  exact binding pins, and fixture-only Ed25519 vectors as its only authority.

### M0A-C2 materialization audit

- Scope: C2 only -- two isolated fixture elaborators and the checked-in
  non-authoritative golden source at
  `docs/design/semantic_ingestion/traceability_golden_vectors/v1.json`. No
  durable acceptance store, public approval gate, or production runtime change
  is authorized.
- Verified blocker: Section 3.23.4's C2 fixture recipe is not sufficient to
  derive the required exact bytes. The grammar at lines 7002-7027 names value
  categories such as `tuple=tagged_declared_order` and
  `bytes=tagged_rfc4648_standard_base64_required_padding`, but it does not
  define the tag tokens, delimiters, escaping, or complete serialized grammar
  for `CanonicalTypedValueEncode`. Therefore it cannot determine even one
  schema-valid body or envelope byte sequence independently.
- Verified blocker: the scalar ancestry table at lines 7194-7241 gives IDs,
  times, a few sequences, and a topological narrative, but it does not provide
  the complete typed bodies or values for the required structural, coverage,
  execution, report/environment, test/result, stream, release-history,
  generation-member, or pointer-history fixtures. Section 3.23.4.4 requires
  those exact bytes and their complete dependencies, while Section 3.23.4.2
  requires a release-bound snapshot containing each qualified issuer's complete
  eligibility derivation. Those values are not derivable from the frozen
  design or C1 output.
- Consequence: materializing `v1.json`, body/preimage/signature/envelope bytes,
  artifact coordinates, generation roots, or 25 verdicts would require
  invented semantics and would violate the frozen-design and independent-fixture
  constraints. No C2 source, elaborator, or test was written.
- Historical blocker recommendation: obtain a design correction that defines the complete CTV
  byte syntax and supplies a closed finite typed-input table for every C2
  fixture (including structural/coverage/execution and G1/G2/G3 members), then
  resume C2 from the frozen C1 pins.

### M0B independent review round 3 dispositions

- `P2 / changes_required / compatibility`: confirmed the reader admitted three
  non-baseline domain spellings. Corrected its closed set to the exact pinned
  `MemoryDomain` values: `transcript`, `semantic`, `episodic`, `user`,
  `execution`, and `solver`; added every-domain positives on every SyncResult
  domain list and spurious-domain negatives.
- `Not applicable / changes_required / artifact ownership`: confirmed the
  manifest mislabeled the separately supplied reader as generated output.
  Reclassified it as an explicit immutable capture input with path and digest;
  only files actually emitted by capture remain under `generated_files`.
- `P2 / changes_required / verification`: confirmed duplicate object keys,
  unhashable enum/domain values, and incomplete reader replay were not proved.
  The reader now rejects duplicate keys at every nesting level, type-guards
  before membership checks, and returns controlled `ValueError` failures.
  Every accepted lifecycle-matrix byte string and accepted SyncResult verdict
  is now replayed through the reader while target rejection checks remain.

### M0B remediation round 3

- Scope: final authorized R22 M0B remediation only. Production provider owners,
  M0A, and M1 remain untouched.
- Fresh captures accept the legacy reader only as an explicit external input.
  The independent verifier receives that path separately and validates the
  manifest input coordinate/digest; fresh output directories need contain only
  actual generated outputs and remain independently verifiable.
- Regenerated corpus, manifest, and static repository root after tool/reader
  changes. Duplicate-root, duplicate-nested, unhashable enum/domain, exact
  domain-set, full accepted-matrix reader replay, fresh recapture equality, and
  generated-versus-input ownership are included in the focused gate.
- Evidence from `memorii/`: focused compatibility/provider suite collected 49
  tests and reported `49 passed in 26.90s`; its recapture test produced two
  fresh outputs using the explicit reader input and byte-compared both corpus
  and manifest with committed evidence. Scoped Ruff reported `All checks
  passed!`; scoped Pyright reported `0 errors, 0 warnings, 0 informations`;
  repository-root `git diff --check` exited successfully without output.
- The three-round M0B remediation and independent-review budget is exhausted
  after coordinator round-3 verification. Any remaining confirmed gap must be
  reported as the exact blocker rather than opening another remediation loop.

### M0B completion judgment

- Frozen design SHA-256:
  `f277fb262b2f8335aad4207f511942c5680510ff827b0291fe9c9ff4b0af6ea6`.
- Coordinator reran the exact focused compatibility/provider suite after the
  final remediation: `49 passed in 28.34s`. The suite includes two isolated
  recaptures byte-equal to the committed corpus and manifest.
- Coordinator reran scoped Ruff (`All checks passed!`), scoped Pyright (`0
  errors, 0 warnings, 0 informations`), and `git diff --check` (clean).
- Direct diff inspection confirms the M0B milestone did not modify canonical
  provider models, service, or Hermes integration owners. Every M0B material
  file maps to R22 compatibility capture, evidence, or validation.
- Three fresh independent reviewer rounds completed. All P2 and
  `Not applicable / changes_required` M0B findings were validated and
  remediated within the three-round budget. No validated P1, P2, or
  changes-required M0B finding remains.
- The static repository manifest root proves deterministic candidate
  consistency only. External operational acceptance remains unavailable and
  is not represented as completed certification.
- M0B status: complete. This does not complete overall M0, close the separately
  blocked M0A requirements, or implement the M1+ opaque result lookup.

### M0A-C2 bounded non-convergence closure

- Status: blocked after three bounded remediation passes. No further semantic
  remediation is authorized under this WorkPlan.
- Frozen architecture/source/registry SHA-256 values are respectively
  `e2ba649d86481e9be437a86c6227b0933891f0f5294fb312887d8881c2bb7d1f`,
  `b91599eee3eef49584db27a6b94b91eccbf560077466a94023b4eab5b3a504ec`,
  and
  `38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`.
- Fresh spec review confirmed four `Not applicable / changes_required /
  verification-governance` gaps: invented signing seeds instead of four fixed
  keys/coordinates; plain rather than schema-domain body digests; generic
  ancestry/G1-G3 values without edge cross-binding; and incomplete UTC CTV plus
  shared elaboration.
- Fresh correctness review confirmed three `Not applicable / blocks_approval`
  gaps: incomplete canonical CTV; placeholder lifecycle bodies and incomplete
  DAG; and unsigned authority semantics based on invented keys without purpose
  or coordinate resolution.
- Fresh test review confirmed runner inner-schema mismatch, weak/non-executed
  signature and accepted-evidence checks, absent independent double
  elaboration/C2 test, and absent executable exact-inventory/vector/mutation
  coverage. Dispositions are `changes_required` except independent elaboration,
  which `blocks_approval`; all have product priority `Not applicable`.
- The exact gap/attempt/evidence table and immutable finding reconciliation are
  recorded in the linked design WorkPlan and
  `docs/reviews/semantic_ingestion/m0a-c2-non-convergence-2026-07-28.md`.
  The preserved validator now raises explicit `C2_INCOMPLETE_PACKAGE` for the
  frozen source. This prevents a success-shaped result without claiming a
  semantic correction.

Historical bounded non-convergence next action: obtain either an external design-author-provided complete
canonical package, or a newly approved smaller design WorkPlan that explicitly
supplies exact finite G1/G2/G3 values and two independent elaborators.

### M0A-C2 remediation round 19 of 20

- Status: blocked by a validated design-authority contradiction after the
  executable mutation engine replaced the former label-derived outcome.
  Rounds 1-18 and their blockers remain immutable historical evidence; they do
  not describe the current candidate.
- Frozen design SHA-256:
  `71d3b9442c3bcda831c8e84ee83e4143c4615fa3bfddb0d05caca74867efeec6`.
  Frozen recipe SHA-256:
  `8431ee000251a0372976028f0aafc0e0d6738421ba91a67c1a5a6e76c35a48f1`.
  Registry SHA-256:
  `38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`.
- The marked enum registry is reconstructed independently from all 56
  inventory roots and their reachable aliases, inherited declarations,
  unions, `Annotated` members, collections, and inline `Literal` fields. It
  contains 238 exact named or declaring-class/field-qualified schemas with
  type-sensitive canonical scalar members.
- All 49 authority and expansion CTV trees were regenerated with 297
  schema-qualified enum nodes. Bare Literal values reject. The regenerated
  coverage ledger observes 2,686 typed leaves and 14 raw leaves, for an exact
  2,700-leaf denominator.
- All 56 binding identities, the profile identity, embedded bindings, and
  canonical content-boundary bytes/digests/sizes were regenerated from the
  frozen design and enum payload. Boundary validation recomputes canonical
  bytes, identity, size, and digest.
- The ordinary validator copies and applies each of the 25 top-level, 29
  nested, and 12 direct-negative mutations through the common typed path
  resolver. It then observes the first canonical/typed, provenance, dependency,
  lifecycle, generation, or stream failure before comparing the recorded
  boundary/reason. Sixty-five mutations reach their declared actual outcome.
  `negative-two-node-cycle` does not: replacing
  `fixture-19-release.dependencies[0]` with
  `fixture-02-bootstrap_anchor_history` leaves an acyclic graph because
  fixture 02 depends only on fixture 01 and has no path to fixture 19.
- Deterministic evidence before the graph contradiction:
  recursive enum/schema/binding/boundary validation passes for 57 fixtures and
  2,700 leaves. `py_compile`, scoped Ruff, scoped Pyright, and
  `git diff --check` pass. The ordinary executable-66 gate correctly fails at
  `negative-two-node-cycle`; no success claim or self-test pass is recorded.
- Validator SHA-256:
  `a838923871e987bce63c58e8eb916be15f6b31e132e8053c45398762b119eefb`.
  Regenerator SHA-256:
  `d05a558084a8f7ab37ed51e4bb82b0aad827a6243ba37268ffab9a2be130b5a1`.
- Legacy `verify_c2.py` remains linked future implementation debt because it
  invokes an obsolete CLI/source shape. It is not design-completion evidence
  and was not used by this round.
- Smallest required design correction: make the two-node replacement name a
  fixture that directly depends on fixture 19 (fixture 37 currently does), and
  make the descendant-cycle case use a different fixture whose path back to
  fixture 19 has length greater than one. Then regenerate enum/profile/binding
  identities and rerun all 66 mutations under a newly frozen reviewed design
  checksum.

### M0A-C2 remediation round 20 of 20

- Status: implementation complete and ready for fresh independent review. The
  remediation budget is exhausted after this review.
- Frozen design SHA-256:
  `4020901b7b50d1a3ea2eee774af52234ef2b9f943176af506a9f15fc41f777b0`.
  Frozen recipe SHA-256:
  `9d5dbe525c22707d33878a7ce6788ba267816e5aff2f79500aa40286cbb2e1e8`.
  Registry SHA-256:
  `38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`.
- The final authorized correction makes the two-node case
  `fixture-19-release -> fixture-37-approval_generation_manifest ->
  fixture-19-release`. The distinct descendant case uses
  `fixture-22-current_pointer_index -> fixture-21-active_release_pointer ->
  fixture-19-release`. The validator independently proves exact return-path
  lengths one and at least two before applying either mutation.
- The enum registry remains the exact independently reconstructed mapping of
  238 reachable named or declaring-class/field-qualified schemas. All 49 typed
  fixture authorities/expansions contain 297 schema-qualified enum tokens and
  bind the regenerated profile, all 56 schema bindings, embedded boundary
  bytes, sizes, and digests.
- The observed denominator is 2,686 typed leaves plus 14 raw leaves, totaling
  2,700. Every one of the 25 top-level, 29 nested, and 12 direct-negative
  mutations is copied, applied through the common path grammar, and evaluated
  by state/schema/graph invariants before its observed first boundary/reason is
  compared with authority. All 66 pass; no outcome is selected from
  `mutation_kind`.
- Final verification:
  `validate_recipe.py --self-test` passes with 57 fixtures, 66 executed
  mutations, and 2,700 leaves; isolated `py_compile` passes; scoped Ruff
  reports `All checks passed!`; scoped Pyright reports zero
  errors/warnings/information; and `git diff --check` passes.
- Validator SHA-256:
  `1840ea4c43b7cad9386dac2f7a41c3d89e628e0775431a8b481628be85d797b4`.
  Regenerator SHA-256:
  `770a3a8dfe6fde570e635f9075cb037cbf64d883e1e61d48d365ddb92f89b0aa`.
- Legacy `verify_c2.py` remains linked future implementation debt and is not
  design-completion evidence.

### Layer1 final remediation batch

- Scope: confirmed Layer1 handoff findings only. Changed canonical CI wiring,
  the independently authored compiler, its public black-box matrix, and the
  PR-workflow structural test. The frozen architecture, registry, authority,
  profile, validator/checker source, static-tooling document, and runtime code
  remain unchanged.
- Approved consumer bundle: design
  `67bf2620a0379761853861e416efba0816045ef4bf88e4808e701a9ac3bc993e`;
  registry `38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`;
  authority `89a98fc1e545f38c234ce42dbd164c85e3ddc6358856cca70e59dad7b1addc7b`;
  validator `830c63e33e8da7787aba57879e08587ecbbe583e25f00c225be3e24a19637d9c`;
  checker `2ca3da2c69b453e2107ab4e901345b4b5420288666561c566732849d56c811c1`;
  profile `20edd38a4ef41e4abf7e1b9a65fe2745e65705f80ec8f93c48c658739b7660a0`.
- Requirement coverage: SIA-R03/L1-008 retain the independently authored,
  stdlib-only authority compiler and byte-equality proof. L1-009 now consumes
  the approved validator identity in every consumer and has two required
  Python 3.12 five-minute PR jobs: the complete compiler/public parity matrix
  and the dependency-free exact authority checker. No test selector weakens
  the matrix command; its argv is parsed with `shlex` and asserted exactly.
- Behavioral closure: declaration-wide validation rejects one- and
  three-argument `dict` forms before projection across direct, quoted, nested,
  alias, inherited, unprojected, and Protocol argument/return routes. The
  compiler accepts and normalizes `tuple[()]` as the finite zero-item tuple.
  It preserves projected maps' `str` key rule. Paired real `python3.12 -I`
  public paths cover rejected Literal/Annotated metadata, valid signed/tuple/
  list data, Protocol valid controls, valid maps, exact byte equality,
  absent/preseeded atomic output, modes, and no temporary siblings. Unicode
  parity now proves literal UTF-8 `cafe` with acute and fail-closed lone
  surrogate publication for both implementations.
- Review-finding dispositions: tuple zero-item normalization, Protocol
  declaration coverage, Literal/Annotated data closure, Unicode parity,
  declared map arity, exact workflow argv, and five-minute timing risk are
  remediated. The first post-change full run exposed one stale workflow
  validator pin; it was corrected from `538a01f1...` to `830c63e3...` and the
  final full run passed.
- Validation: focused new parity family `55 passed`; final exact two-file
  Python 3.12 matrix command from `memorii/`:
  `../.venv/bin/python -m pytest -W error tests/unit/tools/test_semantic_ingestion_ctv_reference_compiler.py tests/unit/tools/test_ctv_binding_authority_pr_gate.py -p no:cacheprovider`
  -> `204 passed in 233.99s`. The separate exact repository-root checker
  command from `docs/development/static_tooling.md` passed with `replicas=2`,
  `schemas=56`, and `enum_rows=240` in approximately 107 seconds. Scoped Ruff
  passed, scoped Pyright reported `0 errors, 0 warnings, 0 informations`,
  Python 3.12 `py_compile` passed, and `git diff --check` was clean.
- Scope ledger: `.github/workflows/pr-gates.yml` is required L1-009 CI
  enforcement; the compiler and compiler test are required SIA-R03/L1-008
  parity/grammar proof; the PR-gate test is necessary L1-009 validation; this
  WorkPlan entry is required durable evidence. No unrelated files changed by
  this batch.
- Limitation: remote GitHub Actions duration and branch-protection enforcement
  are unavailable locally. Local deterministic timing shows the matrix command
  is under five minutes and the independent checker is a separate five-minute
  job, but only CI can supply enforcement evidence.
- Next action: coordinator integrity check followed by fresh three-role Layer1
  review of the complete current branch.

- Cleanup verification: focused grammar/parity evidence reported `86 passed`
  (with unrelated cases deselected) and the workflow structural test passed.
  The exact complete two-file suite reran after the content-preserving cleanup:
  `204 passed in 230.14s`. Scoped Ruff passed; scoped Pyright reported `0
  errors, 0 warnings, 0 informations`; Python 3.12 `py_compile` and `git diff
  --check` passed. The existing exact checker evidence remains applicable
  because its pinned inputs and invocation were not changed by this cleanup.

### Layer1 scope-integrity cleanup

- Coordinator finding: the first final-remediation diff included formatter-only
  reflow in the three owned Python files beyond the required grammar and
  evidence changes. This was `Not applicable / changes_required / governance`;
  it did not alter tested behavior but was unjustified scope churn.
- Remediation: reconstructed each owned Python file from its staged baseline
  using `git show :<path>` as read-only evidence, then restored unchanged
  formatting with explicit patches. The compiler diff is now limited to binary
  `dict` arity and finite `tuple[()]` handling. The test diffs contain only the
  approved validator pin, map/tuple/Protocol/Literal/Annotated/Unicode parity
  evidence, and required workflow structure assertions. `.gitignore` was
  already user-modified and was not read, changed, formatted, or included.
- Next action: coordinator integrity check followed by fresh three-role Layer1
  review of the complete current branch.

### Layer1 coordinator integrity check after cleanup

- Behavioral fidelity: direct inspection confirms the independently authored
  compiler has only two production changes: declaration-wide binary `dict`
  arity and finite `tuple[()]` normalization. The workflow pins approved
  validator `830c63e3...`, preserves checker `2ca3da2...`, and separates the
  complete parity matrix from the dependency-free exact checker into two
  required Python 3.12 jobs, each with `timeout-minutes: 5`.
- Scope integrity: unstaged requirement-mapped diff is workflow `17/3`,
  compiler `5/1`, PR-gate test `43/24`, and compiler test `214/2`. Broad
  formatter churn was removed. The staged `.gitignore` addition for
  `docs/reviews` is a user-owned unrelated change, explicitly excluded from
  this remediation and preserved without modification.
- Validation integrity: coordinator reran scoped Ruff and Pyright
  (`0 errors, 0 warnings, 0 informations`), Python 3.12 `py_compile`, and
  `git diff --check`; all passed. The repository `.venv` is Python `3.12.13`
  with pytest `9.0.3`. Its exact matrix argv passed `204` tests in `232.13s`
  (`233.10s` elapsed). The bare local `python3.12` lacks pytest, while the
  workflow explicitly installs its bounded pytest/PyYAML dependencies before
  using that executable. This local dependency absence is recorded rather
  than treated as CI execution evidence.
- Hermetic checker integrity: coordinator reran the exact repository-root
  `python3.12 -I` command. It reproduced authority `89a98fc1...`, 56 schemas,
  240 enum rows, and two replicas in `113.89s`.
- Generality and architecture integrity: map/tuple behavior is implemented in
  the closed declaration and projection contracts; production code contains
  no test, provider, tenant, or fixture-specific branch. Protocol,
  Literal/Annotated, Unicode, publication, and exact-argv additions remain
  black-box evidence only.
- Remaining limitation: remote GitHub Actions duration and branch-protection
  enforcement are unavailable. Local command timing provides substantial
  per-job headroom but is not represented as remote enforcement.
- Next action: fresh independent three-role Layer1 review of the complete
  current candidate.

### Layer1 fresh review after scope cleanup

- Fresh `correctness_reviewer`: approved with no confirmed correctness defect.
  Its focused public-path probes passed `22` tests and it independently
  verified the exact checker, map/tuple implementation, atomic behavior,
  workflow split, and user-owned `.gitignore` exclusion.
- `L1-SPEC-001`: `Not applicable / changes_required /
  governance-verification`. Confirmed. The active baseline near the start of
  this WorkPlan still names validator `538a01f1...`, while approved design,
  static tooling, workflow, tests, and current evidence name `830c63e3...`.
  Historical pins remain valid history; only the active baseline is stale.
- `L1-TEST-001`: `Not applicable / changes_required / verification`.
  Confirmed. Protocol argument/return parity covers ellipsis, list arity,
  Field-as-type, and direct maps but omits adjacent tuple, Literal, and
  Annotated invalid/valid siblings. Smallest correction is a paired public
  Protocol corpus with atomic validator-output assertions.
- `L1-TEST-002`: `Not applicable / changes_required / verification`.
  Confirmed. The surrogate test changes the declaration but not the marked
  enum row, so enum mismatch can reject before scalar validation. A coherent
  declaration-plus-registry surrogate mutation and composed/decomposed
  reachable controls are required.
- `L1-TEST-003`: `Not applicable / changes_required /
  compatibility-verification`. Confirmed. V1-only compatibility and V1/V2
  substitution currently execute only the independent compiler. The approved
  validator must show byte-identical V1-only success and atomic substitution
  rejection.
- `L1-TEST-004`: `Not applicable / changes_required / CI verification`.
  Confirmed. The cleaned complete matrix takes about 233-236 seconds, leaving
  only 64-67 seconds for checkout, Python setup, and dependency installation
  within the same five-minute job. Without remote timing this is not reliable
  total-job evidence. The existing complete test files are natural
  complementary partitions: one compiler-parity job and one PR-gate/tamper
  job, each selector-free and five minutes, plus the existing dependency-free
  exact-checker job.
- The test reviewer noted but did not separately classify the lack of a
  positive checker invocation inside unit tests. Coordinator disposition:
  unsupported as an additional requirement. The standalone exact job is the
  intentional positive production-path proof and has been executed locally;
  duplicating it inside a partition would add circular runtime without
  improving the exact job contract.
- Next action: one worker closes the five confirmed findings as a single
  bounded evidence/CI remediation, preserving the scope-cleaned production
  diff.

### Layer1 final review remediation

- Review dispositions: `L1-SPEC-001` is remediated by updating only the active
  Layer1 validator baseline to `830c63e33e8da7787aba57879e08587ecbbe583e25f00c225be3e24a19637d9c`;
  historical hashes remain unchanged. `L1-TEST-001` is remediated by paired
  real public Protocol argument and return tests for closed invalid tuple,
  Literal, and Annotated forms plus valid map, zero-item tuple, Literal-name,
  and Annotated-default controls. `L1-TEST-002` now mutates both the reachable
  declaration and marked v2 enum row for surrogate rejection, and proves
  composed/decomposed UTF-8 scalars remain distinct without normalization.
  `L1-TEST-003` adds validator parity and atomic v1/v2 substitution evidence.
  `L1-TEST-004` divides the former combined matrix into selector-free compiler
  parity, PR-gate/tamper, and dependency-free exact-checker Python 3.12 jobs.
- Validation: focused new Protocol/Unicode/v1 and workflow structure evidence
  passed (`55 passed` plus the structural test). The bare local `python3.12`
  interpreter lacks pytest, so the exact CI test argv cannot execute locally
  before CI installs its declared bounded dependencies. The repository Python
  3.12 virtual environment ran equivalent complete commands: compiler parity
  `226 passed in 139.38s` (160.62s five-minute headroom) and PR-gate/tamper
  `8 passed in 110.94s` (189.06s headroom). The separate exact checker passed
  with 56 schemas, 240 enum rows, and two replicas. Combined regression passed
  `234 passed in 245.80s`; scoped Ruff passed; scoped Pyright reported `0
  errors, 0 warnings, 0 informations`; Python 3.12 `py_compile` and `git diff
  --check` passed.
- Scope: `.github/workflows/pr-gates.yml` is required L1-009 enforcement; the
  two black-box test modules are required SIA-R03/L1-008/L1-009 evidence; the
  compiler remains unchanged in this remediation because review identified no
  production behavior defect. User-owned `.gitignore` remains preserved.
- Limitations: only CI can prove dependency installation, actual runner setup
  overhead, required-check branch protection, and remote enforcement. No local
  timing result is represented as remote CI execution evidence.
- Next action: coordinator integrity check followed by fresh three-role Layer1
  review of the complete current branch.

### Layer1 verification-only remediation

- `L1-TEST-005` now proves exact workflow trigger/branch/permission governance;
  `L1-TEST-006` parses the first static-tooling bash fence with a closed
  extractor and binds its exact tokens to the dependency-free job; `L1-TEST-007`
  proves projected non-string maps reject while unprojected/Protocol exceptions
  remain outside CTV projection; `L1-TEST-008` proves accepted finite zero-item
  tuple forms remain byte-identical and normalize as finite empty tuples.
- Focused verification passed `30` tests; complete two-file regression passed
  `262 passed in 266.16s`. Scoped Ruff, Pyright, Python 3.12 `py_compile`, and
  `git diff --check` passed. The exact checker and the per-job timing commands
  were unchanged from the immediately preceding passing run; remote CI and
  branch-protection remain unavailable locally.
- Next action: coordinator integrity check followed by fresh three-role Layer1
  review of the complete current branch.

### Layer1 coordinator integrity check after verification-only remediation

- Workflow trigger/branch/permission governance and the normative first
  static-tooling checker command are now exact structural contracts. The
  workflow and documented commands normalize to identical tokens and bind all
  five frozen identities.
- Public paired projected-map rejection covers direct, whole-quoted, nested,
  reachable-alias, and inherited non-string keys. Unprojected/Protocol
  two-argument exceptions remain accepted by both implementations and alter
  only the bound source-design identity, preserving normalized authority
  closure.
- Public paired finite zero-item tuple acceptance covers direct, whole-quoted,
  nested, reachable-alias, inherited, unprojected, and existing Protocol
  routes. Every projected form exposes exact
  `items=[]/variadic=false` topology; both implementations emit identical
  authority bytes.
- Coordinator revision-bound partitions: compiler parity `244 passed in
  159.45s` (`160.13s` elapsed), PR governance/tamper `18 passed in 115.09s`
  (`115.92s` elapsed), and exact checker authority `89a98fc1...`, 56 schemas,
  240 enum rows, two replicas in `113.65s`. All retain more than 139 seconds
  before five minutes, excluding CI setup overhead.
- Scoped Ruff, Pyright (`0 errors, 0 warnings, 0 informations`), Python 3.12
  `py_compile`, and `git diff --check` remain clean. Production compiler and
  three-job workflow semantics did not change in this evidence-only round.
- User-owned `.gitignore` remains excluded and untouched; remote Actions and
  branch-protection remain unavailable external evidence.
- Next action: fresh independent three-role Layer1 review.

### Layer1 coordinator integrity check after final review remediation

- Direct inspection confirms active WorkPlan, workflow, both test consumers,
  static tooling, and completed linked design plan all name validator
  `830c63e3...`; historical pins remain historical only.
- Compiler production diff remains exactly declaration-wide binary `dict`
  arity plus finite `tuple[()]` handling. No production change was added for
  review-only Protocol, Unicode, compatibility, or CI evidence.
- The workflow has three complementary required Python 3.12 jobs, each with
  `timeout-minutes: 5`: complete compiler parity, complete PR-gate/tamper, and
  dependency-free exact checker. Structural tests parse exact argv with
  `shlex` and reject selectors; no test item is omitted between the two
  complete files.
- Coordinator revision-bound gates: compiler partition `226 passed in
  140.04s` (`140.93s` elapsed); PR-gate partition `8 passed in 113.92s`
  (`115.00s` elapsed); exact checker authority `89a98fc1...`, 56 schemas, 240
  enum rows, and two replicas in `113.28s`. Each command leaves more than 150
  seconds before its five-minute boundary, excluding CI setup overhead.
- Scoped Ruff, Pyright (`0 errors, 0 warnings, 0 informations`), Python 3.12
  `py_compile`, and `git diff --check` pass. Bare local `python3.12` lacks
  pytest; CI explicitly installs bounded dependencies, and local test timings
  use the repository Python `3.12.13` virtual environment.
- Protocol argument/return, coherent surrogate, composed/decomposed Unicode,
  and V1-only/substitution cases now execute both real public implementations.
  Invalid validator paths preserve bytes, modes, and temporary-file absence;
  valid paths compare exact authority bytes.
- User-owned staged `.gitignore` remains unrelated, excluded, and untouched.
  Remote Actions setup duration, execution, and branch-protection enforcement
  remain unavailable external evidence.
- Next action: fresh independent three-role Layer1 review.

### Layer1 replacement review reconciliation

- Fresh `spec_auditor` and `correctness_reviewer`: approved the complete
  Layer1 spec and runtime/reference behavior with no confirmed finding. Both
  verified the frozen identities, independent compiler, exact checker,
  partitioned jobs, and scope boundary.
- `L1-TEST-005`: `Not applicable / changes_required / CI verification`.
  Confirmed. The workflow structural test proves jobs, dependencies, timeouts,
  and argv but does not assert the `pull_request` and `merge_group` triggers on
  `main`. Removing an event can leave all local tests green while preventing
  the required PR gate from running.
- `L1-TEST-006`: `Not applicable / changes_required /
  governance-verification`. Confirmed. The exact workflow checker command and
  in-test `EXPECTED` pins are not compared to the normative first CTV command
  in `docs/development/static_tooling.md`; documented pin drift could leave CI
  green while misdirecting manual/repository verification.
- `L1-TEST-007`: `Not applicable / changes_required / verification`.
  Confirmed only for reachable projected maps. Section 3.23.4.2.1 and both
  projectors require `str` keys, but the public paired corpus has only arity
  failures. Add direct, whole-quoted, nested, reachable-alias, and inherited
  non-string-key rejection with atomic validator-output evidence.
  Coordinator rejects the proposed unprojected/Protocol rejection as
  unsupported: the approved design review explicitly keeps declaration-wide
  preprojection validation to arity and applies string-key semantics only
  when a type enters CTV projection. Those exception routes should be
  represented as deliberate parity controls rather than silently tightened.
- `L1-TEST-008`: `Not applicable / changes_required / verification`.
  Confirmed. `tuple[()]` acceptance is proved directly and in Protocol
  argument/return positions, but not through the adjacent whole-quoted,
  valid quoted-child where accepted by both approved parsers, nested,
  reachable-alias, inherited, and unprojected routes. Projected routes require
  the exact finite zero-item graph; exception routes require compile parity
  without unrelated projected closure.
- Reviewer note about already staged review reports despite the user-owned
  `.gitignore` addition is commit hygiene outside Layer1 implementation
  semantics. The coordinator preserves both the staged user change and staged
  artifacts without changing the index.
- Next action: one worker adds the four bounded verification families without
  changing production compiler behavior or CI partition scope.

### Layer1 closure review round 1 reconciliation

- The original fresh `spec_auditor` did not return after repository access and
  was interrupted. A fresh replacement `spec_auditor` completed a direct
  frozen-design and complete-state inspection without receiving another
  reviewer's findings; it approved SIA-R03/L1-008/L1-009 with no confirmed
  `blocks_approval` or `changes_required` finding.
- Fresh `test_reviewer`: approved the complete behavior-based validation
  matrix. It reran both selector-free public partitions (`244 passed` and
  `18 passed`) and the exact isolated checker (56 schemas, 240 enum rows, two
  replicas). It retained remote Actions duration and branch-protection as
  unavailable external evidence.
- `L1-CLOSURE-001`: `Not applicable / changes_required /
  verification-trust`. Confirmed from the fresh `correctness_reviewer` and
  coordinator direct inspection. `_marked()` validates exactly one
  line-anchored block, but `_replace_marked_payload()` then locates the
  replacement start with an unanchored `document.find(begin)`. Marker-shaped
  prose before the real block can make both public compilers accept while
  producing different source-design identities; marker-shaped closing prose
  after the block can make the clean-room compiler reject a document the
  design validator accepts.
- Causal issue: validation and replacement use different span-selection
  semantics. Impact: byte-identical independent compilation is not general for
  all valid non-authority prose. Smallest correction: return the exact
  validated byte span from one parser, reuse it for extraction and
  replacement, and add paired public acceptance/parity controls for both
  marker-shaped prose positions. The design remains determinate and is not
  reopened.
- Next action: exactly one worker implements `L1-CLOSURE-001` without changing
  the validator, workflow partitioning, authority semantics, or unrelated
  files.

### Layer1 closure remediation round 1 and coordinator integrity check

- The sole writer introduced one `_marked_span()` byte parser shared by
  extraction and V1 redaction, added two real-public-CLI prose controls, and
  changed only the assigned compiler and test module. Focused tests reported
  `2 passed`; the compiler partition reported `246 passed in 164.36s`; the PR
  partition reported `18 passed in 112.90s`; the exact checker reproduced 56
  schemas, 240 enum rows, and two replicas. Ruff, Pyright, `py_compile`, and
  `git diff --check` passed.
- `L1-CLOSURE-001` is resolved for unanchored opening and closing
  marker-shaped prose: both compilers now accept and emit byte-identical
  authority with an independently recomputed source-design digest.
- `L1-CLOSURE-002`: `Not applicable / changes_required /
  verification-trust`. Confirmed during coordinator direct inspection before
  fresh review. The new parser still collects every line-anchored closing
  sentinel after the validated begin and rejects more than one, while the
  approved validator's complete-block matcher selects one complete block and
  ignores an orphan closing sentinel outside it. It also treats an
  invalid-suffix closing candidate as immediately malformed instead of
  continuing to the next complete match. Thus validation and replacement now
  share a span, but public accept/reject parity is still not general across the
  validator's complete-block language.
- Smallest correction: make the independent byte parser enumerate complete,
  non-overlapping anchored begin/end block matches with the validator's
  end-of-line rule, require exactly one complete match, and use that exact
  payload span for both extraction and replacement. Add paired public controls
  for orphan anchored sentinels and invalid-suffix candidates plus a true
  second complete block rejection. Do not change the design validator,
  workflow, authority, or unrelated behavior.
- Next action: exactly one worker implements and validates
  `L1-CLOSURE-002`, followed by coordinator inspection and a fresh three-role
  review.

### Layer1 closure remediation round 2 and coordinator integrity check

- The sole writer replaced sentinel counting with an independently authored
  byte parser for the validator's complete, non-overlapping marked-block
  language. It selects line-anchored begins, skips closing candidates without
  end-of-line termination, chooses the earliest complete close, ignores
  incomplete orphan candidates outside complete blocks, requires exactly one
  complete block, and returns one payload span used by both extraction and
  V1 redaction.
- Added real-public-CLI parity controls for orphan anchored closing and opening
  sentinels, an invalid-suffix close followed by the valid close, and two
  genuine complete blocks. Accepted cases compare byte-identical authority
  and use a separate regex implementation to recompute the exact redacted
  source-design digest; the duplicate complete-block case rejects in both
  public compilers.
- Worker evidence: focused controls `6 passed`; complete compiler partition
  `250 passed in 173.57s`; PR-gate partition `18 passed in 113.31s`; exact
  checker reproduced authority `89a98fc1...`, 56 schemas, 240 enum rows, and
  two replicas. Ruff, Pyright, `py_compile`, and diff checking passed.
- Coordinator direct inspection confirmed the parser's anchoring,
  end-of-line, earliest-valid-close, non-overlapping match, single-complete-
  block, and shared-span behavior against the approved validator. Coordinator
  reran the six adversarial controls (`6 passed, 244 deselected in 9.81s`),
  scoped Ruff, Pyright (`0 errors, 0 warnings, 0 informations`),
  `py_compile`, unstaged `git diff --check`, and staged
  `git diff --cached --check`; all passed.
- Scope integrity: production change remains confined to the independent
  compiler's general marked-block boundary; validation remains confined to
  the paired public compiler corpus. The design validator, authority,
  registry, checker, workflow, and intentionally staged index were not changed
  by the remediation.
- `L1-CLOSURE-002` is locally resolved. No local implementation blocker is
  known; evidence maturity is `locally verified` and requires fresh
  independent review before milestone closure.
- Next action: fresh independent three-role Layer1 review of the complete
  candidate.

### Layer1 heading-default design correction completion

- Trigger: final Layer1 implementation review discovered numeric heading
  `3.23.4.2.1` was absent from the canonical direct-default registry, making
  the independent structural rebuild fail.
- Linked WorkPlan:
  `docs/work/semantic_ingestion/layer1-heading-default-closure-2026-07-29/design.plan.md`.
  Outcome: complete and approved after one full affected-boundary review and
  bounded delta convergence.
- Approved replacement identities: design `67bf2620...`; registry
  `8e6395e2...`; authority `f7c0d000...`; validator `830c63e3...`; checker
  `2ca3da2c...`; profile `20edd38a4...`; domain-separated registry identity
  `6acb4736...`.
- Approved semantic delta: exactly one explicit direct heading default,
  `3.23.4.2.1 -> [SIA-R03,SIA-R13]`, producing exact 148/148 Sections 1-5
  heading coverage. CTV schema, enum, graph, profile, and binding semantics are
  unchanged.
- Implementation handoff: update both closed loaders from 147 to the reviewed
  148 contract; prove exact heading-set equality and complete malformed/
  missing/extra/duplicate/empty/unknown/order/fallback mutations; exercise
  manifest, execution-evidence, release/history/pointer, and acceptance paths;
  repin workflow, static tooling, and tests; and cover grammar V2, schema
  inventory V1, enum V2, and enum V1 through both public compilers.
- Recovery handoff: H1/H2 failure aborts the unpublished coherent candidate.
  H3+ never rewinds files, pins, releases, or pointers; recovery is only a
  signed higher-sequence H4 successor, while old records remain immutable
  history.
- Exclusion: C2 recipe/package, migration/rebind tooling, validators,
  elaborators, verifier, and C2 static command remain stale and blocked. They
  must not be repinned or used as Layer1 evidence.
- Immutable local review reports:
  `docs/reviews/semantic-ingestion-layer1-heading-default-closure-2026-07-29/full-round-01.md`,
  `delta-round-01.md`, `delta-round-02.md`, and `final-round-01.md`.
- Next action: one implementation worker applies the complete approved handoff
  without modifying or consuming blocked C2 authority.

### Layer1 final review round 1 reconciliation

- Fresh `spec_auditor`: approved the scoped Layer1 CTV compiler and gate
  behavior with no confirmed finding, while preserving broader R03 and remote
  enforcement as outside this milestone.
- `L1-FINAL-001`: `Not applicable / changes_required /
  integration-verification-traceability`. Confirmed from the fresh
  `correctness_reviewer` and coordinator reproduction. The frozen design added
  numeric heading `3.23.4.2.1`, but the canonical registry lacks its required
  direct heading default. The independent structural-manifest rebuild fails
  with `unit has no registered heading default` (`1 failed, 25 passed`), so
  the design bundle and complete R03 traceability path are internally
  inconsistent even though the CTV-only checker remains green.
- Disposition: design ambiguity/design-bundle defect. The missing requirement
  set is an explicit author-selected registry decision and all registry-bound
  identities change after correction. Layer1 implementation stops against
  design SHA `67bf2620...`; the linked
  `layer1-heading-default-closure-2026-07-29` design WorkPlan must correct,
  independently review, and freeze a replacement baseline.
- `L1-FINAL-002`: `Not applicable / changes_required / verification`.
  Confirmed in principle from the fresh `test_reviewer`. The shared marked
  parser governs grammar V2, inventory V1, enum V2, and enum V1, while the
  adversarial complete-block parity family currently targets only enum V1.
  After the design bundle is repinned, one implementation remediation must
  parameterize real-public-path acceptance/rejection and independent affected-
  field/digest oracles across all four marker families. The proposed
  non-ASCII case applies only to payloads whose closed grammar permits it and
  must not broaden accepted text grammars.
- The test review's candidate-tree/runner-environment note is an accepted
  later-R03 limitation, not a Layer1 correction; remote Actions and branch
  protection remain unavailable. Its diagnostic-specific semantic-tamper
  assertion is a `P3 / follow_up` test-quality improvement and is not required
  for safe Layer1 approval.
- Next action: complete the linked design correction before any further
  implementation edit or final review.

### Layer1 148-heading consumer handoff and coordinator integrity check

- Implementation scope: updated the canonical registry loader and independently
  authored checker to the reviewed 148-heading contract; added exact
  Sections-1-through-5 heading-set equality to both structural-manifest paths;
  repinned only the Layer1 workflow, static-tooling command, PR-gate test, and
  compiler test to registry `8e6395e2...` and authority `f7c0d000...`; updated
  the domain-separated source expectation to `6acb4736...`; and added
  behavioral mutation and four-marker public-path proof.
- Scope integrity: the C2 recipe/package, validators, elaborators, migration
  tools, verifier, and lower static-tooling C2 command have no unstaged changes.
  The intentionally staged index was not altered. The frozen design, validator,
  checker script, and profile are unchanged; only the reviewed registry and
  regenerated authority inputs differ from their staged historical versions.
- `L1-HANDOFF-001`: `Not applicable / changes_required / verification`.
  Coordinator confirmed that the initial manifest mutation test targeted
  `## 3.23.4.2.1.` while the design heading is
  `#### 3.23.4.2.1 C2-only canonical typed-value profile v2`, so none of its
  three mutations changed the document. One test-only remediation now requires
  the exact heading to occur once and proves missing, extra, and parent-fallback
  rejection in both manifest paths. Targeted evidence: `3 passed`; complete
  registry/manifest evidence: `37 passed`.
- `L1-HANDOFF-002`: `Not applicable / follow_up / compatibility`.
  A coordinator broad probe reproduced three failures in the separately frozen
  C1 fixture-authority package because its elaborators still require the
  historical 52-schema inventory while the active design contains 56 schemas.
  This package is not a consumer named by the approved heading-default handoff,
  is not invoked by the Layer1 PR-gate partition, and cannot be silently
  repinned inside this milestone. Preserve the failures as evidence for a
  separate C1 compatibility decision; do not count that probe as Layer1
  validation success.
- Coordinator deterministic evidence: full public compiler partition
  `258 passed in 214.79s`; Layer1 PR-gate partition
  `18 passed in 112.42s`; registry/manifest partition
  `37 passed in 147.71s`; traceability, execution-evidence, and acceptance
  partition `29 passed in 5.27s`; scoped Ruff passed; scoped Pyright reported
  zero errors and warnings; both staged and unstaged `git diff --check`
  passed.
- The exact isolated checker exited zero for design `67bf2620...`, registry
  `8e6395e2...`, authority `f7c0d000...`, validator `830c63e3...`, and checker
  `2ca3da2c...`, reporting 56 schemas, 240 enum rows, and two byte-identical
  replicas.
- Coordinator integrity judgment: behavioral, scope, validation, and generality
  checks find no known Layer1 implementation blocker after the bounded
  test-only remediation. Evidence maturity remains `locally verified`; fresh
  independent three-role review is required for completion.
- Current next action: run fresh independent `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer` passes over the complete
  replacement Layer1 candidate and reconcile every finding.

### Layer1 148-heading fresh review round 1 reconciliation

- Fresh `spec_auditor`: approved the active Layer1 replacement slice and
  correctly kept stale C1 fixture authority and blocked C2 outside its
  completion judgment.
- `L1-148-R1-01`: `P2 / changes_required / runtime behavior and
  compatibility`. Confirmed from the `test_reviewer` and direct coordinator
  inspection. The design makes signed release envelopes immutable issuance
  facts whose `issued_state` remains `active`, with a separately signed,
  append-only history entry recording supersession. Current
  `verify_active_release_pointer` instead requires mutable release `state`
  values and exactly one release envelope marked active, while
  `verify_release_gate` requires every historical release to equal the current
  registry roots. The current successor test re-signs the genesis release as
  superseded. This cannot preserve an old 147-source release byte-for-byte
  across the approved 148-source H3/H4 successor transition.
- `L1-148-R1-02`: `Not applicable / changes_required / verification`.
  Confirmed from the `test_reviewer` and direct test inspection. The
  four-marker test proves public compiler byte parity and atomic missing/
  duplicate rejection, but it does not independently derive and assert the
  marker-specific authority projection required by the approved handoff:
  grammar profile identity/digest, exact 56-coordinate inventory, exact
  240-row enum-v2 registry/digest, and enum-v1 isolated/redacted source
  behavior.
- `L1-148-R1-03`: `P2 / changes_required / runtime behavior and
  verification`. Confirmed from the `correctness_reviewer` and direct
  reproduction logic. Both structural paths reduce numeric Sections 1-5
  headings to sets before equality, so a duplicate heading occurrence is
  erased even though the design requires each registered path to occur exactly
  once. Both parsers must reject duplicate emitted paths before registry-set
  comparison, with a paired public-path mutation test.
- Reviewer disagreement: the spec auditor's approval is preserved as an
  independent result but does not override the two reviewers' evidence-backed
  findings. Each confirmed issue maps directly to an approved handoff
  acceptance condition; none is a proposed scope addition or C2/C1 repair.
- Remediation policy: use exactly one implementation worker for the three
  confirmed findings. Preserve immutable old release bytes and source identity,
  implement the signed append-only history transition rather than a mutable
  state shortcut, keep current-registry approval on the selected current
  release, add restart/rewind/mixed-generation negative evidence, reject
  duplicate design headings in both structural implementations, and add
  independent marker projections without importing compiler helpers.
- Current next action: finish the two bounded read-only implementation maps,
  then give their evidence and these three confirmed findings to exactly one
  remediation worker.

### Layer1 148-heading remediation round 1 and coordinator integrity check

- One sole writer remediated all three confirmed round-1 findings. Both
  structural parsers now reject duplicate numeric Sections 1-5 heading
  occurrences before exact registry-set equality; the paired mutation suite
  covers missing, extra, parent fallback, and duplicate paths.
- Release envelopes now preserve immutable `issued_state=active`. The release
  gate consumes a separately signed, canonical, append-only history whose
  closed entries bind their digest chain, release identity/digest/coordinate,
  prior active digest, terminal transition, and effective time. Historical
  release bytes are supplied separately and must resolve one-for-one by exact
  digest; missing, duplicate, altered, or unreferenced artifacts reject. Only
  the selected tail must bind the active 148-source registry roots.
- The successor proof now starts from immutable historical 147-source bytes
  with source identity `66c3414e...`, issues a current 148-source higher
  sequence, and authorizes it through a fresh verifier instance. Re-signed or
  reordered history semantics, missing predecessor material, old-pointer
  rewind, altered old bytes, old release as current, and current-root mismatch
  reject through the public gate.
- The history signature is checked against the replayed lifecycle at the tail
  transition time. `verify_active_release_pointer` independently enforces the
  selected current release's required roots, so direct callers cannot bypass
  the current registry boundary. Release/history coordinate integers reject
  boolean substitution.
- The four public marker families now retain public compiler/validator byte
  parity and atomic absent/preseeded failure behavior while test-local formulas
  independently derive grammar bytes/preimage/digest, the exact sorted 56
  schema inventory, enum-v2 canonical bytes/preimage/digest, profile preimage
  and digest, all schema binding formulas, and enum-v1 redacted source-design
  isolation. Marker-appropriate invalid payloads reject; enum-v1 remains
  intentionally opaque to the v2 compilers.
- Coordinator evidence after the final bounded corrections: release,
  registry, manifest, traceability, execution-evidence, and acceptance
  partition `67 passed in 167.58s`; marker/formula subset `13 passed,
  245 deselected in 32.53s`; full compiler partition
  `258 passed in 200.64s`; PR gate `18 passed in 119.62s`; exact checker
  reproduced authority `f7c0d000...`, 56 schemas, 240 enum rows, and two
  replicas. Scoped Ruff and repository-configured Pyright both passed with
  zero diagnostics; staged and unstaged diff checks passed.
- Scope integrity: no C1 fixture-authority or C2 package/tooling file changed
  in this remediation, and the intentionally staged index remains untouched.
- Known bounded-schema limitation: the current release module retains its
  pre-existing flat `canonical_profile_id`, signature profile, and key fields.
  The design's complete typed `canonical_profile_binding` and nested
  `signer_coordinate`, generation-manifest, pointer-index, and pointer-fence
  schemas belong to later M0A artifact-closure milestones. This round does not
  claim those broader schemas complete; it closes the reviewed Layer1 H3/H4
  behavior only.
- Current next action: run fresh independent `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer` passes over the complete
  materially remediated Layer1 candidate.

### Layer1 148-heading fresh review round 8 reconciliation

- Three fresh read-only reviewers completed independent full-state passes.
  Exact raw-design identity, independent manifest equality, durable
  watermark/seal failure behavior, and the pinned authority/compiler/PR
  partitions retained meaningful proof. The reviewers did not approve Layer1
  closure because two runtime and four proof gaps remain.
- `L1-148-R8-01`: `P2 / changes_required / primitive validation and trust
  lifecycle`. Confirmed unanimously and independently reproduced. Python
  `bool` currently satisfies the recovery-policy integer threshold check and
  lifecycle record sequence equality. Require `type(value) is int`, positive
  exact lifecycle sequences, and signed boolean-threshold/sequence negatives
  before watermark mutation.
- `L1-148-R8-02`: `P2 / changes_required / security and trust lifecycle`.
  Confirmed from correctness review and direct code/design comparison.
  Recovery authorization currently reduces configured and supplied roots to
  sets, so a valid threshold quorum in noncanonical order can authorize.
  Preserve supplied binding order, require the exact policy-order selected
  roots, and require canonical signer-ID order. Add signed reversed-order,
  duplicate-root-with-distinct-ID, and threshold-minus-one negatives that
  reach quorum validation before the intentionally unsupported final recovery
  root envelope.
- `L1-148-R8-03`: `Not applicable / changes_required / verification`.
  Confirmed from test review. Fully re-signed current-root evidence covers
  registry source identity and structural manifest only, while production
  compares every registry-derived root and seven external roots. Add a
  parameterized, fixed-authority mutation matrix over every required current
  root with an unchanged real file watermark/seal. A generic root-binding
  rejection is an adequate failure signal where production deliberately
  reports one fail-closed reason.
- `L1-148-R8-04`: `Not applicable / changes_required / verification`.
  Confirmed in bounded form from test review. Add otherwise-valid wrong-root
  envelope signer controls for activate, rotate, revoke, and compromise;
  recovery threshold-minus-one, duplicate root under distinct IDs, reversed
  policy order, and inclusive-start/exclusive-expiry controls; and the three
  flat-alias pairs bootstrap/recovery, bootstrap/successor, and
  recovery/successor. Each negative must precede watermark mutation. This
  proves the existing bounded bridge; it does not authorize the deferred typed
  threshold root envelope.
- `L1-148-R8-05`: `Not applicable / changes_required / public trust-boundary
  verification`. Confirmed from test review. Rejecting an obsolete
  caller-created `registry=` keyword does not prove the public function uses
  supplied canonical raw registry bytes. Add a loader-valid canonical registry
  mutation that changes a registered heading/root while holding release and
  composition authority fixed; require the public path to reconstruct it,
  reject the resulting current-root mismatch, and preserve the file
  watermark/seal. Retain unmodified bytes as the success control.
- `L1-148-R8-06`: `Not applicable / changes_required / execution-evidence
  verification`. Confirmed from test review and direct inspection. The
  parameterized legacy caller-HMAC mutation test is vacuous because that API
  rejects all inputs before examining records. Retain one explicit legacy API
  rejection invariant, remove the unsupported per-field implication, and add
  canonical schema-valid public report mutations for revision, tree digest,
  command, selected/collected IDs, outcome, result-artifact digest, and
  environment-observation digest. Use a pre-provisioned candidate coordinate
  so report rejection proves no additional durable mutation without implying
  that a valid release pointer depends on one report.
- The test review's suggestion for a newly subprocess-produced signed report
  is retained as later evidence-strengthening work, not a determinate Layer1
  correction: current local fixtures prove parser/state-machine behavior, and
  operational trust certification remains unavailable under
  `SIA-ED-TRACEABILITY-001`.
- The coordinator separately inspected recovery-root purpose separation and
  activation semantics. The complete typed root/lifecycle histories and
  recovery-root activation package are part of the explicitly deferred M0A
  artifact closure; this bounded flat bridge must not claim that later
  behavior. Round 8 may improve only behavior already exposed by the bridge
  and must continue to fail final recovery-root envelope authorization closed.
- Current next action: assign exactly one remediation writer all six confirmed
  findings, then rerun focused and complete Layer1 checks and repeat the
  coordinator integrity review.

### Layer1 148-heading remediation round 8 and coordinator integrity check

- Recovery policy thresholds and lifecycle record sequences now require exact
  positive `int` values; booleans reject before equality, cardinality,
  ordering, signature eligibility, or durable state. Fully re-signed
  threshold/sequence boolean controls preserve the exact sealed watermark.
- Recovery records retain binding order. Distinct eligible roots may form any
  exact-threshold subset, but their positions must be strictly in original
  policy-tuple order and signer IDs must be canonical. A three-root,
  threshold-two non-prefix subset proves `[r1, r3]` is not hard-coded away,
  while `[r3, r1]`, duplicate-root/different-ID, threshold-minus-one, and
  noncanonical signer-ID controls reject at their causal validation boundary.
- The existing bounded bridge now has otherwise-valid, cryptographically
  signed wrong-root-envelope controls for activate, rotate, revoke, and
  compromise. Recovery-root effective-at is inclusive and expires-at is
  exclusive; the accepted boundary reaches only the intentionally unsupported
  final-recovery envelope. Flat signer alias evidence covers
  bootstrap/recovery, bootstrap/successor, and recovery/successor pairs.
- Fully re-signed current releases are mutated over registry source identity,
  every registry-derived root, and all seven external roots while fixed
  composition authority and a real file watermark/seal remain unchanged.
  This proves the complete root-comparison loop rather than two representative
  fields.
- The public registered-execution boundary now receives a canonical,
  loader-valid raw registry mutation with fixed release/authority bytes and
  rejects the reconstructed source/root mismatch. Public canonical report
  mutations cover revision, tree digest, command, selected/collected IDs,
  result outcome, result artifact, and environment-observation digest. The
  outcome mutation intentionally fails the frozen schema constant and is not
  described as schema-valid.
- Legacy caller-HMAC tests now assert only the supported invariant: that API is
  unconditionally not approval-capable, independent of caller record content.
  Per-field report evidence is owned by the registered public path, eliminating
  the prior circular/vacuous implication.
- Coordinator inspection rejected an initial over-restrictive implementation
  that required the first `threshold` policy roots. The corrected general
  algorithm compares selected policy positions, permitting any threshold-sized
  subset in policy order without accepting a reordered quorum.
- Coordinator deterministic evidence on the complete post-remediation
  candidate: Layer1 behavior/evidence partition `150 passed in 191.14s`;
  exact hermetic authority checker reproduced `f7c0d000...`, 56 schemas, 240
  enum rows, and two replicas; public compiler partition `258 passed in
  201.63s`; PR-gate tamper partition `18 passed in 115.62s`;
  scoped Ruff passed; repository-configured Pyright reported zero errors and
  warnings; staged and unstaged `git diff --check` passed. The pinned authority
  and compiler/PR evidence is bound to this complete candidate.
- Scope integrity: changes remain confined to exact primitive and recovery
  quorum validation plus direct trust/root/registry/report evidence in the
  existing Layer1 owner and tests. No design, registry, authority pin, C1/C2
  artifact, typed signer envelope, generation repository/index/fence, or
  closed-request service changed.
- Coordinator integrity judgment: all six confirmed round-8 findings are
  remediated with causal, non-circular evidence. Evidence maturity remains
  `locally verified`; fresh independent three-role review is required before
  Layer1 completion.
- Current next action: run fresh independent `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer` passes over the complete
  post-remediation Layer1 candidate.

### Layer1 148-heading fresh review round 11 reconciliation

- Fresh spec and test reviewers approved the bounded candidate. Correctness
  review found one reproducible lifecycle-state bypass; two approvals do not
  override it.
- `L1-148-R11-01`: `P2 / changes_required / security and lifecycle state`.
  Confirmed from correctness review and direct inspection. Lifecycle replay
  pre-populates `recovery_active` with every independently provisioned,
  policy-listed recovery root, so threshold recovery can use roots whose
  required non-genesis `activate` records never occurred. The later activation
  branch is therefore non-gating.
- Correction: keep provisioned recovery roots authenticated and available for
  target lookup, but initialize lifecycle-active recovery state empty. Only a
  valid, ordinary-bootstrap-authorized non-genesis `activate` transition may
  add a recovery root to `recovery_active`; `recover`, revoke, or compromise
  must require that active state. Add a signed recover-before-activation
  negative with exact file watermark/seal non-mutation.
- Positive evidence must distinguish record acceptance from the intentionally
  unsupported final-recover root envelope. At minimum, activated roots followed
  by a threshold recovery must reach only
  `lifecycle_root_recover_signature_threshold_unsupported`; strongest bounded
  evidence appends an ordinary post-recovery rotation and authorizes a release
  under its final successor.
- `L1-148-R11-F01`: `P3 / follow_up / verification`. Add re-signed empty and
  missing bootstrap `target_authority_id` controls for the exact nonempty claim
  when convenient. Production already rejects both before lifecycle use; this
  is not a demonstrated runtime defect.
- Remote CI and branch-protection state remain unavailable external evidence.
  Local exact public-acceptance selection and structural enforcement are
  verified and must not be represented as remote CI execution.
- Current next action: assign exactly one remediation writer
  `L1-148-R11-01`, then rerun focused/complete Layer1 gates and fresh
  independent review.

### Layer1 148-heading remediation round 11 and coordinator integrity check

- Provisioned and policy-listed recovery roots now begin lifecycle-inactive.
  Independent provisioning authenticates the root and permits later target
  lookup, but only a valid non-genesis `activate` record signed by one eligible
  ordinary authority adds it to `recovery_active`. Recovery-root revoke,
  compromise, and threshold recovery require that causal active state.
- A fully signed threshold recovery placed immediately after bootstrap genesis
  now rejects with `recovery_root_not_lifecycle_eligible`. The test provisions
  a real file watermark and bootstrap seal and proves both remain byte-for-byte
  unchanged. The positive chain explicitly activates both roots, reaches the
  intentional final-recover-envelope rejection, then appends an ordinary
  rotation and authorizes release, history, and pointer artifacts under the
  final successor.
- During the positive-chain inspection, the sole writer found a second
  concrete defect: the per-binding recovery-root digest reused the
  `root_digest` name and overwrote the lifecycle-root digest later used for
  envelope verification. `L1-148-R11-02` is classified `P2 /
  changes_required / lifecycle correctness`; the recovery binding now uses
  the purpose-specific `recovery_digest` local, preserving the independently
  reconstructed lifecycle-root digest through final envelope verification.
- Coordinator behavioral inspection confirmed recovery roots never enter the
  ordinary `active` or returned signer-interval maps. Activation records use
  the eligible ordinary record signer for the lifecycle-root envelope.
  Recovery replacement adds an ordinary successor, while the known flat
  envelope limitation still fails closed when `recover` is the final action;
  no deferred typed multi-signature envelope was introduced.
- Coordinator deterministic evidence on the complete post-remediation
  candidate: Layer1 behavior/evidence partition `158 passed in 194.10s`;
  exact hermetic checker reproduced authority `f7c0d000...`, 56 schemas, 240
  enum rows, and two replicas; public compiler partition `258 passed in
  198.57s`; PR-gate structural/tamper partition `18 passed in 115.13s`; exact
  warning-strict public acceptance command `25 passed in 8.87s`; Ruff passed
  for all 26 changed Python files; repository-configured Pyright reported zero
  errors and warnings; staged and unstaged `git diff --check` passed.
- Scope integrity: round 11 changes are limited to the already exposed
  recovery lifecycle state owner and direct signed behavior tests. The design,
  registry, pinned authority, C1/C2 artifacts, typed signer envelope,
  generation repository/index/fence, and public closed-request service are
  unchanged.
- `L1-148-R11-01` and `L1-148-R11-02` are remediated with causal,
  non-circular behavior evidence. `L1-148-R11-F01` remains a P3 test follow-up;
  remote CI and branch-protection execution remain unavailable external
  evidence and are not claimed.
- Coordinator integrity judgment: no confirmed round-11 blocking,
  changes-required P1/P2, scope, or architecture concern remains in the
  bounded Layer1 candidate. Evidence maturity remains `locally verified`;
  fresh independent three-role review is required before Layer1 completion.
- Current next action: run fresh independent `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer` passes over the complete
  post-remediation Layer1 candidate.

### Layer1 148-heading fresh review round 12 reconciliation

- Three fresh reviewers completed independent full-state passes. Spec audit
  approved the bounded candidate. Test review found one public handoff defect
  and one missing causal proof. Correctness review reproduced two distinct
  trust-policy defects. Coordinator inspection confirmed those four cores,
  adjusted the proof-only finding's product priority, and found one additional
  recovery-state replay defect. One approval does not override the confirmed
  findings.
- `L1-148-R12-01`: `P2 / changes_required / runtime integration`. Confirmed.
  The core release gate accepts one primary plus a tuple of additional
  recovery artifacts and compares their exact set with independently held
  trust material. The sole registered public approval execution accepts and
  forwards only the primary artifact. Any valid threshold-two policy therefore
  fails the canonical consumer handoff with
  `trust_not_independently_provisioned`, even though direct gate tests pass.
  Add the additional typed tuple to the public function, forward it unchanged,
  and prove an activated threshold recovery followed by ordinary rotation
  through the registered execution/report path. Missing and duplicate
  additional roots must fail before watermark/seal mutation.
- `L1-148-R12-02`: `Not applicable / changes_required / verification`.
  Confirmed with adjusted priority: current production removes a recovery root
  from active state on revoke/compromise, so no product defect was
  demonstrated and P2 is unsupported. Existing tests prove the terminal
  transition itself but never append a later signed recovery using that root;
  deleting the state removal would remain green. Add revoke and compromise
  chains followed by threshold recovery and require
  `recovery_root_not_lifecycle_eligible` plus exact file watermark/seal
  non-mutation.
- `L1-148-R12-03`: `P2 / changes_required / security and trust policy`.
  Confirmed and independently reproduced. Generic signed-envelope validation
  selects `public_key_or_root_certificate_digest` before
  `policy_signer_key_or_certificate_digest`, while later recovery-policy
  eligibility checks only the latter. Because the bounded policy envelope
  does not reject the alternate field, an attacker can add the public-key
  field, sign the policy with that key, leave the policy signer field naming
  the bootstrap key, and authorize threshold recovery plus a final release.
  Require each signed artifact kind to name its exact signer-key field and
  reject the alternate key field before signature verification. Add the
  fully re-signed attacker-policy chain with durable non-mutation evidence.
- `L1-148-R12-04`: `P2 / changes_required / security and lifecycle time`.
  Confirmed and independently reproduced. Recovery-policy expiry uses
  `effective > expires_at`, accepting recovery exactly at expiry while every
  signer/root interval is start-inclusive and expiry-exclusive. Use
  `effective >= expires_at` and add a signed equality-boundary recovery chain
  that preserves watermark/seal bytes.
- `L1-148-R12-05`: `P2 / changes_required / security and lifecycle replay`.
  Confirmed by coordinator direct inspection against the frozen lifecycle
  requirement. Recovery-root activation overwrites `recovery_active` without
  recording prior activation. A duplicate activation can reset an active
  interval, and a later activation after revoke/compromise can revive the
  terminated root, contradicting the requirement that a revoked or
  compromised root is ineligible for every later lifecycle record and that
  stale-root replay rejects. Record every activated recovery coordinate in an
  append-only seen/tombstone set, reject any second activation, and add signed
  duplicate-active and post-terminal reactivation negatives with unchanged
  durable state.
- The spec approval correctly confirms exact 148-heading parity, current
  purpose separation, and the explicitly deferred flat final-recover envelope,
  but did not inspect the multi-root registered consumer or alternate
  recovery-policy key field. Its approval is retained as independent evidence,
  not treated as dispositive.
- Remote CI and branch-protection execution remain unavailable external
  evidence. The known P3 issued-at lower-bound, empty/missing bootstrap
  authority, and contention-timeout follow-ups remain nonblocking and must not
  be conflated with these changes-required findings.
- Current next action: send `L1-148-R12-01` through
  `L1-148-R12-05` to exactly one remediation writer, then rerun focused and
  complete Layer1 gates and fresh independent review.

### Layer1 148-heading remediation round 12 and coordinator integrity check

- The sole registered approval execution now accepts an explicit tuple of
  additional recovery artifacts and forwards it unchanged to the canonical
  release gate. The primary root remains required for compatibility, while the
  gate remains the only owner of exact-set and duplicate validation; no
  parallel trust or verification path was introduced.
- Public behavior evidence constructs two independently provisioned recovery
  roots, explicitly activates both, performs threshold-two recovery to one
  provisioned successor, ordinarily rotates to the final bootstrap, and
  authorizes the signed final release, history, pointer, environment
  observation, report, and artifact set through
  `verify_registered_approval_execution`. Missing and duplicate additional
  roots raise `ExecutionEvidenceError` with the expected gate reason and leave
  the real watermark record and bootstrap seal byte-identical.
- Signed envelope validation now receives the exact signer-key field from each
  artifact owner. Bootstrap/recovery/successor roots require only
  `public_key_or_root_certificate_digest`; recovery policies require only
  `policy_signer_key_or_certificate_digest`; presence of the alternate known
  field rejects before signature verification. A fully re-signed attacker
  policy that previously authorized now rejects with
  `signature_key_field_ambiguous` without durable mutation.
- Recovery-policy intervals now use the same start-inclusive,
  expiry-exclusive rule as root and signer intervals. A signed recovery at
  exact policy expiry rejects with
  `recovery_policy_not_lifecycle_eligible` and preserves the sealed watermark.
- Recovery activation now records an append-only seen coordinate. A second
  activation while active and reactivation after revoke or compromise both
  reject as `lifecycle_activation_duplicate_or_stale`; neither resets nor
  revives eligibility. Separate revoke/compromise-then-recover chains prove
  the terminated root is excluded from later recovery, also with exact durable
  non-mutation.
- Coordinator inspected both production owners and the public/registry tests.
  Validation occurs before the release gate's atomic compare-and-advance;
  recovery roots remain outside ordinary signer intervals; final-action
  recovery still fails closed pending the deferred typed threshold envelope.
  No hard-coded signer, provider, tenant, fixture ID, or test-only production
  branch was added.
- Coordinator deterministic evidence on the complete post-remediation
  candidate: Layer1 behavior/evidence partition `161 passed in 196.93s`;
  exact hermetic checker reproduced authority `f7c0d000...`, 56 schemas, 240
  enum rows, and two replicas; public compiler partition `258 passed in
  198.72s`; PR-gate structural/tamper partition `18 passed in 115.20s`; exact
  warning-strict public acceptance command `28 passed in 9.89s`; Ruff passed
  for all 26 changed Python files; repository-configured Pyright reported zero
  errors and warnings; staged and unstaged `git diff --check` passed.
- Scope integrity: round 12 changed only the existing release gate, registered
  execution handoff, and direct Layer1 tests. It did not alter the design,
  registry, pinned authority, C1/C2 package, typed recovery envelope,
  generation repository/index/fence, or public closed-request service.
- `L1-148-R12-01` through `L1-148-R12-05` are remediated with causal,
  non-circular behavior evidence. Evidence maturity remains `locally
  verified`; fresh independent three-role review is required before Layer1
  completion.
- Current next action: run fresh independent `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer` passes over the complete
  post-remediation Layer1 candidate.

### Layer1 148-heading fresh review round 13 reconciliation

- Three fresh reviewers completed independent full-state passes. Test review
  approved the bounded evidence and retained only existing P3/external
  follow-ups. Spec audit found one public atomicity defect. Correctness review
  reproduced one signed cross-purpose alias acceptance. Coordinator confirmed
  both and found one additional invalid action/target-kind path. Test approval
  and green gates do not override these findings.
- `L1-148-R13-01`: `P2 / changes_required / persistence and approval
  atomicity`. Confirmed. The registered public execution calls the release
  gate, whose final step atomically advances a higher release watermark, and
  only afterward validates the runner observation/report/artifact closure. A
  malformed report can therefore reject the public request after durable
  acceptance state changed. Existing no-mutation report tests pre-provision the
  candidate's identical coordinate, reducing compare-and-advance to an
  idempotent no-op and missing the higher-coordinate failure.
- Correction for `L1-148-R13-01`: preserve one canonical release owner but
  separate non-mutating release validation from final compare-and-advance.
  The direct release gate remains a validate-then-commit wrapper. Registered
  execution must validate the release into an internal typed candidate,
  validate the complete runner/report/artifact closure using that candidate's
  verified bindings, and only then invoke the same private atomic commit
  owner. Add a lower pre-provisioned coordinate, valid higher signed release,
  report-failure matrix with byte-identical watermark/seal/temp state, and a
  valid retry that advances exactly once. Do not expose a success-shaped
  public validation-only API or duplicate watermark logic.
- `L1-148-R13-02`: `Not applicable / changes_required / security and
  compatibility`. Confirmed with the reviewer's priority. A fully re-signed
  release can add `policy_signer_key_or_certificate_digest` while retaining
  the authorized `issuer_key_or_certificate_digest`; the release digest and
  signature validate, the alternate cross-purpose alias is ignored, and the
  release authorizes. The bounded flat bridge must reject every known
  signer-key field except the exact field owned by that artifact kind.
  Release/pointer allow only the issuer field; independently signed roots and
  policy already use their exact fields; lifecycle-root envelopes derive
  signers and allow none. Add public signed alias-injection negatives before
  durable commit. Complete typed closed-schema migration remains later M0A and
  is not silently pulled into this correction.
- `L1-148-R13-03`: `P2 / changes_required / security and lifecycle action
  semantics`. Confirmed by coordinator inspection. The flat replay accepts
  both `rotate` and `recover` when the target resolves only in
  `recovery_active`, while every replacement is required to be a bootstrap
  anchor. Ordinary rotation can therefore consume a recovery root to install
  ordinary bootstrap authority, and threshold recovery can replace a recovery
  root while leaving the existing bootstrap active. Both contradict
  purpose-separated action semantics. In the bounded bridge, `rotate` and
  `recover` must target an active bootstrap coordinate; activated recovery
  roots remain valid targets only for revoke/compromise. Add fully signed
  recovery-target rotate/recover negatives with exact durable non-mutation.
- The correctness reviewer found no further issue in multi-root forwarding,
  one-time recovery activation, terminal-root exclusion, policy expiry,
  post-recovery ordinary rotation, or watermark store failure behavior. The
  test reviewer independently reproduced the exact checker and warning-strict
  public acceptance partition and correctly kept remote CI, issued-at lower
  boundary, empty/missing bootstrap authority, and contention orchestration as
  nonblocking follow-ups.
- Current next action: send `L1-148-R13-01` through
  `L1-148-R13-03` to exactly one remediation writer, then rerun focused and
  complete Layer1 gates and fresh independent review.

### Layer1 148-heading remediation round 13 and coordinator integrity check

- The release owner now has one private non-mutating validation phase that
  returns a frozen `_VerifiedReleaseCandidate` containing only validated
  release ID/digest, exact epoch/sequence, and immutable root-binding pairs.
  No public request parameter accepts that internal candidate, and no public
  path returns its authorization view before commit. This is package
  encapsulation, not a claim that Python underscore names are an access-control
  boundary. `_commit_verified_release` is the sole release-module owner of
  `compare_and_advance`; the existing public release gate remains
  validate-then-commit.
- Registered approval execution loads and independently reconstructs the
  registry, validates the release candidate, derives a temporary authorized
  view only for the pure report verifier, validates the complete environment,
  report, artifact, and root closure exactly once, commits the private
  candidate through the shared owner, and returns the saved verified report
  only after commit succeeds. A commit rejection or unavailable outcome
  returns the existing safe public `ExecutionEvidenceError`.
- Higher-coordinate public evidence provisions a sealed sequence-one
  watermark, supplies a valid signed sequence-two release/history/pointer, and
  separately corrupts the report command, runner observation, and required
  result artifact. Every failure preserves the watermark, bootstrap seal, and
  complete directory file/byte map. The unmodified sequence-two request then
  advances exactly once, and a second full request revalidates normally while
  remaining byte-idempotent.
- Known signer-key-field ownership is now purpose-exact throughout the bounded
  bridge. Roots allow only the public-key/root-certificate field; policy only
  its policy-signer field; release and pointer only the issuer field; lifecycle
  root envelope allows none; release history retains its existing exact field
  set. Fully re-signed release, pointer, and lifecycle-root cross-purpose alias
  injections reject before durable mutation. This does not claim the deferred
  complete typed closed-schema migration.
- Lifecycle `rotate` and `recover` now require their target coordinate to be in
  ordinary active bootstrap state. Activated recovery roots remain valid
  targets for revoke/compromise only and cannot be consumed to install
  ordinary authority. Fully signed recovery-target rotate and recover records
  reject with `lifecycle_target_not_ordinary_authority`; valid bootstrap
  rotation and threshold recovery remain positive.
- Coordinator inspection confirmed there is exactly one
  `compare_and_advance` invocation in the release module, the private candidate
  is frozen and carries no store/verifier/callback, report validation has no
  durable side effect, and the registered path performs no duplicate report
  evaluation within a request. No callback bypass, parallel source of truth,
  import cycle, public signature break, or watermark-owner change was
  introduced.
- Coordinator deterministic evidence on the complete post-remediation
  candidate: Layer1 behavior/evidence partition `168 passed in 197.69s`;
  exact hermetic checker reproduced authority `f7c0d000...`, 56 schemas, 240
  enum rows, and two replicas; public compiler partition `258 passed in
  200.00s`; PR-gate structural/tamper partition `18 passed in 115.71s`; exact
  warning-strict public acceptance command `32 passed in 11.50s`; Ruff passed
  for all 26 changed Python files; repository-configured Pyright reported zero
  errors and warnings; staged and unstaged `git diff --check` passed.
- Scope integrity: round 13 changed only the existing release gate, registered
  execution handoff, and direct Layer1 tests. It did not alter the watermark
  implementation, design, registry, pinned authority, C1/C2 package, typed
  recovery envelope, generation repository/index/fence, or public
  closed-request service.
- `L1-148-R13-01` through `L1-148-R13-03` are remediated with causal,
  non-circular behavior evidence. Evidence maturity remains `locally
  verified`; fresh independent three-role review is required before Layer1
  completion.
- Current next action: run fresh independent `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer` passes over the complete
  post-remediation Layer1 candidate.

### Layer1 148-heading fresh review round 14 reconciliation

- Three fresh reviewers completed independent full-state passes. Spec and
  correctness challenged the trust/service boundary and later signed
  execution-root closure. Test review found one bounded missing commit-outcome
  proof and retained three P3 follow-ups. Coordinator validated every finding
  against the frozen scope and current public paths.
- `L1-148-R14-01`: spec's `P2 / changes_required / security` private-candidate
  finding is unsupported as a product defect. Python underscores are not an
  access-control mechanism, but neither public API accepts a candidate or
  returns authorization before commit. The reproduction imports internal
  functions and supplies a caller-chosen store; it changes only that chosen
  store. A caller holding the actual composition-owned store could already
  invoke its public compare-and-advance method directly, so an unforgeable
  in-process dataclass would not create the missing service trust boundary.
  The WorkPlan claim is narrowed: public request APIs do not accept the
  candidate; internal modules intentionally share one package-private
  validation/commit contract. The later composition-owned service remains
  explicit M0A scope.
- Correctness finding on caller-supplied `AcceptanceTrustStore`, verifier,
  roots, watermark, and time is classified `outside scope / deferred`, not P1.
  The active milestone is explicitly a deterministic flat compatibility
  bridge and does not claim the deferred production closed-request service,
  composition root, authenticated monotonic clock, or externally provisioned
  `SIA-ED-TRACEABILITY-001` authority. Implementing those here would violate
  the recorded scope ledger. Existing public-shape tests prove callers cannot
  substitute authority through artifact/report fields; production service
  ownership remains later M0A.
- Correctness finding on complete signed execution-root and normative evidence
  membership is likewise `outside scope / deferred`, not P1. Full
  structural/coverage/execution artifact-byte generation closure and signed
  trust snapshot/evidence records are already named incomplete in the
  non-convergence ledger. Layer1 proves registered report/root binding and
  exact 148-heading consumer handoff; it does not claim the later complete
  generation or external approval.
- Correctness finding on clock movement between report validation and commit is
  classified `outside scope / deferred service boundary`. The deterministic
  bridge evaluates the supplied explicit verification instant once; the later
  acceptance-owned service/monotonic-time witness must acquire and revalidate
  operational time. No release remains authorized by the bounded bridge
  without passing its complete lifecycle/time checks at that explicit instant.
- `L1-148-R14-02`: `Not applicable / changes_required / verification`.
  Confirmed with adjusted product priority. Production currently maps
  `WatermarkUnavailable` to a typed unavailable gate result and unexpected
  compare outcomes to `watermark_store_indeterminate`; registered execution
  raises before returning the already-verified report. No runtime defect was
  demonstrated, so P2 is unsupported. Add a protocol-faithful counting store
  returning each outcome through the registered public boundary; assert exact
  safe `ExecutionEvidenceError`, no returned report or durable change, and
  exactly one compare-and-advance call.
- Test review's report-evaluation cardinality spy, cleanup-unlink fault, and
  lower-flake contention orchestration remain `P3 / follow_up`. Ordering and
  durable non-mutation are already behaviorally proven; a spy would primarily
  assert implementation structure. Cleanup failure policy belongs to the
  watermark store's later operability hardening and is not necessary for the
  confirmed public commit-outcome proof.
- Current next action: send `L1-148-R14-02` to exactly one writer, rerun
  focused/complete Layer1 gates, and perform fresh independent review.

### Layer1 148-heading remediation round 14 and coordinator integrity check

- The initial test-only writer became unresponsive without producing the
  assigned edit and was interrupted. It is not counted as a completed
  remediation. A fresh replacement became the sole writer and changed only
  the existing public acceptance test file; no overlapping writer remained
  active.
- A protocol-shaped counting watermark store now records the exact
  `(epoch, sequence, release_digest)` received from the fully validated public
  request while retaining immutable sentinel state. The registered approval
  path is exercised with a valid release/report closure and two commit
  outcomes: typed `WatermarkUnavailable("injected_watermark_unavailable")`
  and an unexpected result object.
- Both outcomes raise the exact safe public `ExecutionEvidenceError`, return
  no verified report, invoke compare-and-advance exactly once with the signed
  candidate coordinate/digest, and leave the fake's sentinel state unchanged.
  Tests do not instantiate or call private release candidates/helpers and
  therefore prove the public integration rather than mirroring commit
  internals.
- Coordinator direct validation: focused outcome cases `2 passed`; exact
  warning-strict public acceptance file `34 passed in 13.71s`; complete
  Layer1 behavior/evidence partition `170 passed in 199.02s`; scoped Ruff
  passed; repository-configured Pyright reported zero errors and warnings;
  `git diff --check` passed. The exact checker, 258-case compiler partition,
  and 18-case PR partition remain revision-applicable because this round
  changed only a selected acceptance test already structurally enforced by
  the workflow.
- The replacement writer initially reported an environment-wide Pyright
  failure from an incorrect environment invocation. Coordinator reran the
  repository-configured package-root command with the pinned `.venv` Python
  and obtained zero diagnostics; the transient report is not a repository
  finding.
- Scope integrity: no production, design, registry, pinned authority,
  watermark owner, workflow, C1/C2, typed envelope, service, clock, or
  generation file changed. `L1-148-R14-02` is remediated with direct public
  behavior evidence. Evidence maturity remains `locally verified`; fresh
  independent three-role review is required before Layer1 completion.
- Current next action: run fresh independent `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer` passes over the complete
  post-remediation Layer1 candidate.

### Layer1 148-heading fresh review round 10 reconciliation

- All three fresh reviewers completed independent full-state passes. Spec and
  correctness independently confirmed the same cross-authority trust-root
  defect. Test review confirmed the bounded behavior matrix but found that the
  public acceptance file is not enforced by any required PR job.
- `L1-148-R10-01`: `P2 / changes_required / security and target binding`.
  Confirmed unanimously across behavior reviewers and directly reproduced.
  `verify_release_gate` derives the lifecycle authority only from bootstrap,
  then authenticates recovery and successor roots without requiring their
  nonempty `target_authority_id` to equal it. A correctly signed foreign
  successor can become ordinary rotation authority; a foreign recovery root
  can enter policy/lifecycle processing. Require every independently
  provisioned bootstrap, recovery, and successor root to match the bootstrap
  authority before policy or lifecycle replay. Add signed foreign recovery and
  successor rotation/activation negatives with exact file watermark/seal
  non-mutation.
- `L1-148-R10-02`: `P2 / changes_required / verification and CI
  enforcement`. Confirmed from test review and workflow inspection. Required
  PR jobs run the exact authority/compiler partitions and `tests/unit`, but do
  not select the public registered-approval acceptance file. A regression in
  raw-registry reconstruction, release/root/report validation, durable
  seal/watermark handoff, or public anti-rewind can therefore merge with all
  current jobs green. Add an exact selector-free Python 3.11/3.12 PR command
  for
  `tests/acceptance/semantic_ingestion/test_sia_requirements.py -p
  no:cacheprovider`, and extend the workflow structural/tamper test to require
  it without `-k`, deselection, or exclusion.
- `L1-148-R10-F01`: `P3 / follow_up / boundary coverage`. The current release
  time test covers expiry equality but not exact issued-at inclusion and
  immediately-before-issued rejection. The production comparison is correct
  on direct inspection; add this signed boundary matrix in later evidence
  strengthening if it is not included with the bounded remediation.
- `L1-148-R10-F02`: `P3 / follow_up / test determinism`. Multiprocess
  watermark tests use bounded barriers/queues and fail closed rather than
  falsely passing, but scheduler pressure can make their 10-15 second
  deadlines flaky. Retain as a low-severity follow-up; changing contention
  infrastructure is not necessary enabling work for the two confirmed
  corrections.
- Reviewer note on staged versus unstaged state is confirmed operationally:
  the user intentionally preserved a staged earlier snapshot while current
  remediation remains unstaged. Validation and review bind the complete
  working-tree candidate, not index-only content. The coordinator must not
  stage, reset, or claim a commit revision.
- Current next action: assign exactly one remediation writer both confirmed
  round-10 findings, then rerun focused/complete Layer1 and workflow gates and
  fresh independent review.

### Layer1 148-heading remediation round 10 and coordinator integrity check

- Bootstrap authority is now an exact nonempty string. Every independently
  provisioned recovery and successor root must carry that same
  `target_authority_id` before policy loading, root-kind processing,
  provisioned-root/alias insertion, or lifecycle replay. No root field can
  install or coerce a new authority.
- Fully re-signed foreign recovery roots bind a correspondingly re-signed
  policy, and foreign successor roots bind a signed activation log; both
  reject with `provisioned_root_authority_invalid` before touching the sealed
  watermark. Existing same-authority recovery, activation, and rotation
  controls remain positive.
- The repository PR workflow now runs exactly
  `pytest -W error
  tests/acceptance/semantic_ingestion/test_sia_requirements.py -p
  no:cacheprovider` in the existing installed unit-test environment. The
  structural PR test requires exactly one named step, working directory
  `memorii`, the exact token sequence, and no `-k`, marker, deselection, ignore,
  or exclusion selector.
- Coordinator scope inspection confirmed the workflow addition reuses the
  existing Python 3.11 dependency installation and 15-minute budget, adds
  approximately nine local seconds, and does not duplicate compiler/tamper
  partitions or alter unrelated jobs.
- Coordinator deterministic evidence on the complete post-remediation
  candidate: Layer1 behavior/evidence partition `156 passed in 197.71s`;
  exact hermetic checker reproduced `f7c0d000...`, 56 schemas, 240 enum rows,
  and two replicas; public compiler partition `258 passed in 198.74s`; PR-gate
  structural/tamper partition `18 passed in 114.07s`; exact public acceptance
  command `25 passed in 8.63s`; scoped Ruff passed; repository-configured
  Pyright reported zero errors and warnings; staged and unstaged
  `git diff --check` passed.
- `L1-148-R10-F01` and `L1-148-R10-F02` remain explicit P3 follow-ups:
  issued-at lower-bound evidence and lower-flake contention orchestration.
  Neither masks a demonstrated runtime defect or weakens a required gate.
- Scope integrity: changes are limited to exact trust-root target binding,
  direct signed negatives, and required public-acceptance CI selection. C1/C2,
  typed envelopes/recovery histories, generation repository/index/fence, and
  the closed-request service remain untouched.
- Coordinator integrity judgment: both confirmed round-10 findings are
  remediated with causal evidence and enforced PR selection. Evidence maturity
  remains `locally verified`; fresh independent three-role review is required
  before Layer1 completion.
- Current next action: run fresh independent `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer` passes over the complete
  post-remediation Layer1 candidate.

### Layer1 148-heading fresh review round 9 reconciliation

- Three fresh reviewers completed independent full-state passes. The test
  reviewer approved the round-8 evidence. The spec and correctness reviewers
  each found one distinct, reproducible lifecycle-boundary defect; deterministic
  green gates do not override either behavior gap.
- `L1-148-R9-01`: `Not applicable / changes_required / lifecycle interval
  validation`. Confirmed from spec audit and direct inspection. Replacement
  and non-genesis activation admission reject `expires_at < effective_at` but
  accept equality, while every lifecycle interval is start-inclusive and
  expiry-exclusive. A successor with
  `expires_at == transition.effective_at` can therefore become `root_signer`
  despite being ineligible at root closure. Use the canonical interval
  predicate before installing/selecting a target. Add fully signed rotation
  and activation equality-boundary negatives plus valid inclusive-start
  controls, preserving the file watermark/seal.
- `L1-148-R9-02`: `P2 / changes_required / security and purpose separation`.
  Confirmed from correctness review and the coordinator's earlier purpose
  boundary inspection. Non-genesis `activate` accepts a recovery root, adds it
  to ordinary active signers, and selects the recovery key as lifecycle-root
  envelope signer. The design requires the post-transition active bootstrap
  signer for ordinary activation; recovery roots remain purpose-separated.
  For a recovery-root target, retain recovery state only, do not grant ordinary
  release/pointer/policy eligibility, and select the eligible ordinary
  bootstrap signer that authorized the activation record. Add paired
  cryptographically valid recovery-key rejection and bootstrap-key success
  controls, plus a release signed by the activated recovery key that must
  remain ineligible.
- The complete recovery-root history package and typed signer coordinates
  remain later M0A scope. This correction governs the already exposed flat
  `activate` behavior and cannot defer or hide its cross-purpose authorization
  defect.
- Fresh reviewer evidence: test review approved; correctness review ran a
  combined current-state partition of `397 passed in 397.82s`; spec review
  confirmed the frozen design identity and complete Layer1 collection. These
  results establish reproducibility but not correctness at the two uncovered
  boundaries.
- Current next action: assign exactly one remediation writer both confirmed
  findings, then rerun focused/complete Layer1 gates and fresh independent
  review.

### Layer1 148-heading remediation round 9 and coordinator integrity check

- Replacement and non-genesis activation targets now use the same
  start-inclusive, expiry-exclusive interval rule as every other lifecycle
  signer. Equality at `effective_at == expires_at` rejects before the target is
  installed or selected as lifecycle-root signer. Signed rotation and
  activation equality negatives preserve the file watermark/seal, while
  inclusive-start controls authorize.
- Non-genesis recovery-root activation remains in the purpose-separated
  recovery state and never enters the ordinary release/history/pointer signer
  intervals returned by lifecycle replay. Its lifecycle-root envelope signer
  is the exact eligible ordinary signer from the single activation-record
  binding, not the activated recovery key.
- Paired controls prove the identical recovery-root activation log rejects
  when its root envelope is signed by the recovery key and authorizes when
  signed by the active bootstrap key. A release/history/pointer set signed by
  the activated recovery key remains ineligible, preventing an indirect
  cross-purpose bypass.
- Coordinator inspection traced `ordinary_record_signer` only from a
  cryptographically verified, lifecycle-eligible ordinary record binding and
  confirmed recovery targets do not enter the ordinary `active` or returned
  interval maps. Bootstrap-target activation and ordinary rotation retain
  their post-transition signer behavior.
- Coordinator deterministic evidence on the complete post-remediation
  candidate: Layer1 behavior/evidence partition `154 passed in 192.03s`;
  exact hermetic checker reproduced `f7c0d000...`, 56 schemas, 240 enum rows,
  and two replicas; public compiler partition `258 passed in 199.64s`; PR-gate
  tamper partition `18 passed in 115.16s`; scoped Ruff passed;
  repository-configured Pyright reported zero errors and warnings; staged and
  unstaged `git diff --check` passed.
- Scope integrity: the change is limited to already exposed lifecycle target
  eligibility and recovery-root activation purpose separation plus direct
  tests. It does not implement the deferred typed signer envelope, complete
  recovery histories, generation repository/index/fence, C1/C2 artifacts, or
  closed-request service.
- Coordinator integrity judgment: both confirmed round-9 findings are
  remediated with causal, signed, non-circular evidence. Evidence maturity
  remains `locally verified`; fresh independent three-role review is required
  before Layer1 completion.
- Current next action: run fresh independent `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer` passes over the complete
  post-remediation Layer1 candidate.

### Layer1 148-heading remediation round 7 and coordinator integrity check

- Both structural implementations now validate the supplied raw design
  artifact before parsing: nonempty strict UTF-8, no BOM, NUL, or carriage
  return, and exactly one final LF. Each independently computes
  `SHA-256("semantic-ingestion-traceability\0" || raw_design_bytes)` without
  normalizing the digest preimage. Direct cross-implementation equality and
  malformed-transport negatives cover the exact identity contract.
- Lifecycle-root envelope verification now follows record replay and derives
  its signer from the final lifecycle action. Activation and ordinary rotation
  use the post-transition authority; revoke and compromise use the
  pre-transition authority. A final recovery action returns the explicit
  fail-closed
  `lifecycle_root_recover_signature_threshold_unsupported` outcome because the
  bounded flat root envelope cannot represent the required threshold
  signatures. This does not claim the deferred typed multi-signature envelope.
- Ordinary lifecycle records require exactly one binding and one signature.
  Recovery records require exactly the configured threshold of distinct,
  eligible, independently provisioned recovery roots. Extra ordinary or
  recovery signatures reject rather than being ignored.
- Flat signer-coordinate ambiguity detection now covers bootstrap, recovery,
  and provisioned successor roots. A profile/key pair owned by two distinct
  root coordinates rejects closed. Active pointers must carry the exact
  `semantic_ingestion_traceability_active_release_pointer` issuance purpose
  before their signed contents can authorize.
- Coordinator behavioral and architectural inspection traced these checks
  through the production manifest, independent checker, lifecycle replay,
  release gate, and registered public execution path. No caller-supplied
  registry object, inferred signer owner, silent fallback, or test-only
  production branch was introduced.
- Coordinator deterministic evidence on the complete current Layer1
  candidate: behavior partition `125 passed in 187.81s`; exact hermetic
  authority checker reproduced `f7c0d000...`, 56 schemas, 240 enum rows, and
  two replicas; public compiler partition `258 passed in 196.47s`; PR-gate
  tamper partition `18 passed in 113.81s`; repository-configured Pyright
  reported zero errors and warnings; scoped Ruff and staged/unstaged
  `git diff --check` passed.
- Repository-wide Ruff remains unavailable as clean completion evidence
  because the intentionally preserved, unrelated staged provider-compatibility
  baseline fixture has a pre-existing import-order diagnostic. The Layer1
  files changed in this milestone are Ruff-clean; this unrelated diagnostic
  is not remediated or counted as Layer1 scope.
- Scope integrity: round 7 changes are limited to exact raw-design identity,
  lifecycle signer selection/cardinality, all-root alias rejection,
  active-pointer purpose validation, and their direct tests. C1 fixture
  authority, C2 package/tooling, complete typed signer/profile envelopes,
  generation repository/index/fence, retention, and the production closed
  request service remain later M0A work.
- Coordinator integrity judgment: all five confirmed round-7 findings are
  remediated with behavior-level and non-circular evidence. Evidence maturity
  remains `locally verified`; fresh independent three-role review is required
  before Layer1 completion.
- Current next action: run fresh independent `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer` passes over the complete
  materially remediated Layer1 candidate.

### Layer1 148-heading fresh review round 7 reconciliation

- The fresh test reviewer approved the active behavioral evidence.
- `L1-148-R7-01`: `P2 / changes_required / integrity and trust identity`.
  Confirmed from spec audit despite its nonconforming severity label. Both
  structural implementations compute unqualified SHA-256 of design bytes and
  normalize carriage returns, while the design requires exact
  `SHA-256("semantic-ingestion-traceability\\0" || raw_design_bytes)` and
  rejects BOM, NUL, CR, invalid UTF-8/scalars, missing final LF, or more than
  one trailing LF. Implement independently in both paths and add exact-preimage
  plus paired malformed-byte tests. Repin only values actually derived from
  this identity.
- `L1-148-R7-02`: `P2 / changes_required / trust lifecycle`. Confirmed from
  correctness review. The lifecycle root envelope is always verified with the
  bootstrap key before replay. Derive the exact final-action root signer after
  replay: post-transition authority for ordinary activation/rotation,
  pre-transition authority for revoke/compromise. The current single-signature
  envelope cannot truthfully represent recovery-threshold root authorization;
  fail it closed until the deferred typed multi-signature envelope exists
  rather than accepting a bootstrap shortcut.
- `L1-148-R7-03`: `Not applicable / changes_required / trust lifecycle`.
  Confirmed from correctness review. Ordinary lifecycle records must contain
  exactly one signer binding and exactly one signature; appended valid but
  ineligible signatures cannot be ignored. Recovery records require exactly
  the configured threshold of distinct eligible recovery signers.
- `L1-148-R7-04`: `Not applicable / changes_required / security and purpose
  separation`. Confirmed from correctness review. The flat signer alias guard
  must cover every independently provisioned root kind, including recovery
  roots. Until typed coordinates exist, duplicate `(profile, key)` ownership
  across any two roots rejects closed.
- `L1-148-R7-05`: `Not applicable / changes_required / trust-boundary
  validation`. Confirmed from correctness review. Signed active pointers must
  contain the exact
  `semantic_ingestion_traceability_active_release_pointer` issuance purpose
  before digest/signature validation. Add a fully re-signed wrong-purpose
  negative and update valid fixture pointer bodies.
- The full typed lifecycle root multi-signature envelope remains later M0A
  artifact closure. This round removes the unauthorized bootstrap shortcut and
  records recovery-root authorization as unavailable under the current flat
  envelope; it does not claim recovery threshold completion.
- Current next action: send all five confirmed findings to exactly one writer,
  then repeat coordinator integrity checks and fresh independent review.

### Layer1 148-heading fresh review round 6 reconciliation

- The fresh spec auditor approved the bounded Layer1 scope.
- `L1-148-R6-01`: `P2 / changes_required / security and trust lifecycle`.
  Confirmed in demonstrated impact, bounded in remediation. The current flat
  profile/key bridge cannot distinguish two lifecycle roots that reuse the same
  key, so an active second root can make a revoked first-root signer appear
  eligible. The complete typed signer-coordinate envelope remains later M0A
  artifact-closure scope, but this bridge must fail closed whenever one
  `(profile, key)` maps to multiple provisioned root coordinates. Add a signed
  key-reuse/revocation negative. Do not infer an arbitrary root.
- `L1-148-R6-02`: `P2 / changes_required / security and trust lifecycle`.
  Confirmed from correctness review. Current release history and current
  pointer signer eligibility are checked at issuance/tail time but not always
  at authorization time. Require both issuance-time validity and use-time
  validity for the selected current history and pointer before watermark
  mutation. Historical release envelopes retain issuance-time semantics.
- `L1-148-R6-03`: `P2 / changes_required / integrity`. Confirmed from
  correctness review. Composition-owned external roots currently require only
  nonempty strings, while the design defines lowercase SHA-256 content
  digests. Require exact 64-character lowercase hex for every external root at
  trust-store/gate entry and update test fixtures to distinct valid digests.
- `L1-148-R6-04`: `P2 / changes_required / verification`. Confirmed from test
  review. Existing revoke/compromise evidence isolates the release signer, not
  the pointer signer. Add a still-active release signer plus revoked/
  compromised pointer signer test, assert the pointer-specific reason, and
  prove seal/current bytes unchanged.
- `L1-148-R6-05`: `P2 / changes_required / verification`. Confirmed from test
  review. Public forged-root evidence provisions the original release digest,
  so same-coordinate substitution can reject before proving root validation.
  Provision the forged candidate digest under fixed pre-mutation expected
  roots, assert the root-binding-specific public reason, and prove no
  watermark/seal mutation.
- The full nested `signer_coordinate` schema, profile binding, generation
  manifest, current index, and fence remain explicitly later M0A artifact
  closure. Round 6 must eliminate the demonstrated ambiguity/bypass but must
  not claim those complete typed envelopes are implemented.
- Current next action: send the five confirmed bounded corrections to exactly
  one writer, then repeat coordinator integrity checks and fresh independent
  review.

### Layer1 148-heading remediation round 6 and coordinator integrity check

- The flat compatibility bridge now rejects an ambiguous ordinary lifecycle
  signer whenever one `(signature_profile_id, key_digest)` maps to multiple
  distinct provisioned bootstrap-root coordinates. It never selects whichever
  interval happens to remain active. Signed shared-key revoke/compromise
  controls reject before watermark mutation; distinct-key rotation still
  authorizes.
- Current release history and current pointer signatures now require lifecycle
  eligibility both at their issuance/tail time and at `verification_time`.
  Pointer-specific and history-specific revoke/compromise controls keep the
  release signer active, assert the exact signer-specific rejection reason, and
  preserve seal/current bytes.
- Every composition-owned external root now requires exact lowercase
  64-character SHA-256 grammar before release parsing. Unit authority fixtures
  use distinct valid digest-shaped values rather than labels.
- Public forged structural-root evidence provisions the forged candidate's own
  digest under the fixed original expected roots. It therefore reaches and
  asserts current-root binding rejection rather than watermark substitution,
  while proving exact seal/current non-mutation.
- Scope integrity: the round eliminates demonstrated flat-key ambiguity and
  current artifact use-time bypasses but does not claim the design's full typed
  `signer_coordinate`, profile binding, generation manifest, index, or fence.
  Those remain later M0A artifact closure.
- Coordinator deterministic evidence: complete Layer1 partition
  `116 passed in 185.68s`; focused watermark/trust/public acceptance
  `90 passed in 55.81s`; scoped Ruff passed; repository-configured Pyright
  reported zero errors and warnings; staged and unstaged diff checks passed.
- Coordinator integrity judgment: all five confirmed round-6 bounded findings
  are remediated with causal and non-circular evidence. Fresh independent
  three-role review is required before Layer1 completion.
- Current next action: run fresh independent `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer` passes over the complete
  materially remediated Layer1 candidate.

### Layer1 148-heading fresh review round 5 reconciliation

- The fresh spec auditor approved the active Layer1 contract and found no false
  claim over the deferred complete repository/service work.
- `L1-148-R5-01`: `P2 / changes_required / security and trust lifecycle`.
  Confirmed from correctness review and direct design evidence. Every release
  signer is validated at issuance, but the selected current release signer is
  not revalidated at authorization/use time. A key revoked or compromised
  after issuance can therefore remain current when a different active key
  signs history/pointer. Recheck only the selected current release signer at
  `verification_time` before watermark mutation; historical releases retain
  issuance-time validation. Add signed revoke/compromise controls with an
  independent active history/pointer signer and unchanged watermark evidence.
- `L1-148-R5-02`: `P2 / changes_required / verification and concurrency`.
  Confirmed from test review. A shared start event without a ready count does
  not prove simultaneous contenders; unscheduled children can start after
  release. Use a process barrier or ready counter that the parent observes
  before release, retaining bounded joins, typed outcomes, conflicting
  provisioning/substitution, and exact final state.
- `L1-148-R5-03`: `P2 / changes_required / public failure verification`.
  Confirmed from test review. Public tests cover current-record
  missing/corrupt state, while seal deletion/corruption is only store-level.
  Add all-valid public registered-execution cases for missing and corrupt seal;
  assert the safe typed reason, no result, and no member mutation/recreation.
- `L1-148-R5-04`: `P2 / changes_required / crash-consistency verification`.
  Confirmed from test review. Atomic-replace failure is covered, but directory
  fsync failure after replace is not. Add advance and genesis-provision
  failpoints. For advance, prove unavailable/lost acknowledgement, exact
  recoverable on-disk state, and idempotent retry. For genesis, prove the
  seal-first partial state remains unavailable and is never silently completed
  or reset. No test may claim a failed directory fsync was durably committed.
- The test review's exact negative diagnostic request is retained as
  `P3 / follow_up`; typed broad outcomes plus success controls are adequate for
  this Layer1 slice, while exact golden-vector verdict coverage belongs to the
  later closed fixture contract.
- Current next action: send the four confirmed findings to exactly one writer,
  then repeat coordinator integrity checks and fresh independent review.

### Layer1 148-heading remediation round 5 and coordinator integrity check

- The release gate now revalidates only the selected current release signer's
  lifecycle eligibility at `verification_time` after current release, pointer,
  history tail, roots, and time window are authenticated but before watermark
  mutation. Historical release signatures remain evidence of valid issuance
  and are checked at their own issuance times.
- Signed multi-root controls revoke and compromise the current release signer
  while leaving a distinct history/pointer signer active. Both cases reject at
  current use time and preserve the pre-provisioned watermark bytes.
- Multi-process advance, conflicting provision, and same-coordinate
  substitution tests now use a parent-plus-all-workers barrier. The parent
  cannot release the cohort until every child reaches readiness; bounded joins,
  typed outcomes, and exact final bytes remain enforced.
- Public registered execution now covers both missing and corrupt bootstrap
  seals while retaining a valid current record. It reports the safe
  storage-missing/corrupt reason, produces no approval result, and neither
  changes the surviving record nor recreates a missing member.
- Directory-fsync failure after an advance is modeled as unavailable/lost
  acknowledgement: the replace-visible new record remains consistent with the
  unchanged seal and an idempotent retry succeeds. Failure after fresh genesis
  seal replacement leaves a seal-only partial state; later provision and
  compare remain unavailable and never silently complete or reset it.
- Scope integrity: changes are confined to current-signer lifecycle
  enforcement and acceptance watermark/release/public evidence. Historical
  trust semantics, C1/C2, provider runtime, and later repository/service scope
  are unchanged.
- Coordinator deterministic evidence: complete Layer1 partition
  `106 passed in 184.36s`; focused watermark/release/public acceptance
  `80 passed in 54.45s`; scoped Ruff passed; repository-configured Pyright
  reported zero errors and warnings; staged and unstaged diff checks passed.
- Coordinator integrity judgment: all four confirmed round-5 findings are
  remediated with direct behavior evidence. Fresh independent three-role review
  is required before Layer1 completion.
- Current next action: run fresh independent `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer` passes over the complete
  materially remediated Layer1 candidate.

### Layer1 148-heading fresh review round 4 reconciliation

- The fresh spec auditor approved the bounded Layer1 candidate and confirmed
  that the later generation/index/fence/repository/service contract remains an
  explicit non-goal rather than a hidden completion claim.
- `L1-148-R4-01`: `Not applicable / changes_required / trust boundary`.
  Confirmed from correctness review. The public registered-execution path
  independently parses raw registry bytes but validates only
  `registry.canonical_bytes` on a second caller object; the release gate then
  trusts that object's `source_identity` and `root_digests`. A forged object
  retaining the real bytes can replace identity and omit roots. Correction:
  reconstruct the complete canonical registry authority from raw bytes inside
  the public boundary, or compare every canonical field and use only the
  reconstructed value. Add the forged-object public negative.
- `L1-148-R4-02`: `Not applicable / changes_required / persistence and
  rollback`. Confirmed from correctness review. Separating `provision` from
  compare prevents implicit initialization, but deleting the record and
  calling exposed provisioning again resets the high-water coordinate.
  Correction: persist a separate immutable bootstrap seal before the mutable
  watermark; normal provisioning may be idempotent only for that sealed
  genesis and must never recreate a missing mutable record. Missing either
  member or conflicting seal fails unavailable/rejected. This seal is not a
  second current-coordinate source and does not implement the later signed
  generation repository.
- `L1-148-R4-03`: `P2 / changes_required / verification and concurrency`.
  Confirmed from test review. Existing process starts lack a synchronization
  barrier and do not contend on provisioning, so scheduler serialization can
  hide a missing lock. Add a shared release event, bounded joins, collected
  typed outcomes, and concurrent conflicting provisioning. Require one sealed
  genesis, no unavailable ordinary advances, maximum final state, and no
  deadlock. The maximum advance may coexist with legal earlier advances.
- `L1-148-R4-04`: `P2 / changes_required / public failure and replay proof`.
  Confirmed from test review. Store-level deletion and public corruption are
  proven separately, but public all-valid unprovisioned/deleted state is not.
  Add public registered-execution negatives for both, requiring
  `watermark_storage_missing`, no accepted result, and no implicit write.
- `L1-148-R4-05`: `P2 / changes_required / failure-path verification`.
  Confirmed from test review. Inject an `OSError` at atomic publication after
  a valid prior state, prove typed unavailable, unchanged canonical prior
  bytes, no temporary survivor, and exactly-once successful retry after fault
  removal. Exercise the public/release boundary where practical; the store
  failpoint remains a white-box operational test.
- The correctness review's stronger whole-directory/failure-domain concern is
  retained as the known reason this bounded bootstrap seal is not the complete
  signed current-index/fence repository. Layer1 must reject partial member loss
  and record-only deletion; independent rollback-resistant storage for loss of
  the entire directory remains later M0A scope and is not claimed here.
- Current next action: send all five confirmed findings to exactly one writer,
  then repeat coordinator integrity checks and fresh independent review.

### Layer1 148-heading remediation round 4 and coordinator integrity check

- The public registered-execution boundary no longer accepts a caller-created
  `TraceabilityRegistry`. It reconstructs the complete canonical registry,
  source identity, and every root digest from `registry_bytes` through
  `load_registry_bytes`, and passes only that reconstructed authority to the
  release gate. A forged object retaining real canonical bytes but replacing
  identity/root metadata cannot be supplied through the public signature.
- The watermark store now publishes an immutable canonical bootstrap seal
  before its mutable high-water record. Both members are protected by the same
  cross-process lock and individually use file fsync, atomic replace, and
  directory fsync. Provisioning is fresh only when both are absent, idempotent
  only for the sealed genesis when both members remain valid, and cannot
  recreate a missing record or seal. Compare validates that current state is
  not below or substituting the sealed genesis.
- Barriered multi-process tests concurrently exercise ordinary advances and
  conflicting genesis provisioning with bounded joins and collected typed
  outcomes. They prove no deadlock, no unavailable ordinary contenders, a
  successful maximum/final canonical maximum, exactly one sealed genesis, and
  only valid rejection of losing provision candidates.
- Public registered execution now proves all-valid unprovisioned and
  provisioned-then-record-deleted state returns
  `watermark_storage_missing`, creates no accepted result, and does not create
  or recreate the record. Partial record/seal loss also fails closed at the
  store boundary and cannot be reprovisioned.
- Publication-failure evidence injects `OSError` at atomic replacement after a
  valid sealed prior state. The operation returns unavailable, retains exact
  prior seal/current bytes, removes temporary artifacts, then advances once and
  remains idempotent after fault removal.
- Scope integrity: changes are confined to canonical raw registry loading, the
  public registry authority handoff, the bounded acceptance watermark owner,
  and existing Layer1 unit/acceptance evidence. The bootstrap seal is immutable
  genesis metadata, not a parallel current pointer or replacement for the
  later signed generation/index/fence repository.
- Coordinator deterministic evidence: complete Layer1 partition
  `99 passed in 179.38s`; focused watermark/public acceptance
  `27 passed in 15.16s`; scoped Ruff passed; repository-configured Pyright
  reported zero errors and warnings; staged and unstaged diff checks passed.
- Coordinator integrity judgment: all five confirmed round-4 findings are
  remediated. Record/seal partial loss and publication races fail closed;
  whole-directory rollback remains an explicit later repository/storage
  requirement and is not claimed here. Fresh independent three-role review is
  required before Layer1 completion.
- Current next action: run fresh independent `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer` passes over the complete
  materially remediated Layer1 candidate.

### Layer1 148-heading fresh review round 3 reconciliation

- All three fresh reviewers completed independent full-state passes. The spec
  auditor's composition-root finding is valid for the broader M0A public
  approval service but is outside this bounded Layer1 handoff: the complete
  closed request, acceptance repository, current pointer index/fence, manifest
  member loading, and production composition root are already recorded as the
  later M0A-C3/C4 blocker and explicitly excluded here. Dependency-injecting an
  `AcceptanceTrustStore` into the low-level verifier does not establish that
  later public service and must not be claimed as complete. Disposition:
  `outside scope`, retained as an existing `Not applicable /
  changes_required / security architecture` M0A finding.
- `L1-148-R3-01`: `P2 / changes_required / persistence and rollback`.
  Confirmed from correctness review and direct store inspection. A missing
  watermark record is currently treated as uninitialized during ordinary
  verification, so deleting an established record permits a lower coordinate
  to advance. Correction: separate one-time composition provisioning from
  compare-and-advance; normal verification must return unavailable whenever
  the record is absent. Prove deletion after advance cannot authorize rewind.
- `L1-148-R3-02`: `P2 / changes_required / lifecycle and time semantics`.
  Confirmed from correctness review. The signed selected tail entry can have
  `effective_at` after verification time and still authorize. Require tail
  effectiveness at verification time before watermark mutation, with signed
  public negatives and unchanged durable state.
- `L1-148-R3-03`: `P2 / changes_required / verification and trust boundary`.
  Confirmed from test review. The unit file shadows the production gate with a
  helper that silently injects an in-memory store and derives expected roots
  from candidate release bytes. Even where a particular test is not a root
  test, this hides required authority and permits circular future assertions.
  Replace it with explicit fixed pre-mutation fixture authority and explicit
  store arguments. Add all-valid missing-store and corrupted durable-store
  unavailable assertions.
- `L1-148-R3-04`: `P2 / changes_required / verification and replay`.
  Confirmed from test review. The gate-level replay proof isolates the
  watermark, but the public successor test changes old registry/structural
  roots, so its final generic exception is not causal evidence of durable
  rewind rejection. Add a same-root public successor/reopen/predecessor proof
  with an observable watermark-specific failure signal. Retain the historical
  147-to-148 proof as compatibility evidence, not anti-rewind evidence.
- `L1-148-R3-05`: `P2 / changes_required / history integrity verification`.
  Confirmed from test review. Production has strict predecessor ordering but
  lacks signed behavioral tests for equal/earlier successor issuance,
  equal/earlier transition effectiveness, effectiveness before issuance, and
  future-effective selected tails. Add full-gate mutations and prove no
  watermark mutation.
- `L1-148-R3-06`: `P2 / changes_required / concurrency evidence`. Confirmed in
  substance from test review. Child-process compare results are discarded, so
  the test can pass if every contender returns unavailable and the parent
  subsequently creates the maximum. Collect every child typed outcome, require
  no unavailable result, require the maximum candidate to advance, allow only
  order-valid advance/reject outcomes for lower candidates, and inspect the
  reopened canonical record directly. The reviewer's suggestion that exactly
  one process must advance is unsupported because serialized increasing
  candidates may legally advance before the maximum; that portion is not
  adopted.
- Fresh deterministic evidence on the reviewed pre-remediation candidate:
  exact hermetic checker passed with authority `f7c0d000...`, 56 schemas, 240
  enum rows, and two replicas; public compiler partition `258 passed in
  202.15s`; PR-gate partition `18 passed in 121.61s`; Layer1 behavior
  partition `76 passed in 162.31s`; watermark store `8 passed`; scoped Ruff,
  Pyright, and diff checks passed. These green results do not override the six
  confirmed proof/runtime findings.
- Current next action: send the six confirmed findings to exactly one
  remediation writer, then repeat coordinator behavioral, scope, validation,
  and architecture checks before fresh independent review.

### Layer1 148-heading remediation round 3 and coordinator integrity check

- The acceptance watermark owner now separates explicit, locked one-time
  `provision` from ordinary `compare_and_advance`. Verification never infers
  genesis from missing state: a missing or deleted record returns
  `watermark_storage_missing`, malformed state returns
  `watermark_storage_corrupt`, and neither path writes. Provisioning is
  idempotent only for the exact existing coordinate and digest; conflicting
  provisioning rejects.
- Deletion-after-advance evidence now removes the durable record, reopens the
  store, and proves a lower coordinate is unavailable rather than recreated.
  The multiprocess test collects every child outcome, rejects unavailable
  results, requires the maximum coordinate to advance, permits only
  serialization-valid lower outcomes, and directly decodes the final canonical
  record as the maximum.
- The selected signed release-history tail must now be effective at or before
  verification time before any watermark operation. Signed full-gate
  mutations cover equal/earlier successor issuance, equal/earlier transition
  effectiveness, effectiveness before issuance, and future-effective tails;
  each rejection preserves the pre-provisioned watermark bytes.
- The test-local shadow gate and its silent candidate-derived root/store
  defaults were removed. Gate calls now use the production function with an
  explicit fixed pre-mutation expected-root map and explicit intended store.
  All-valid missing-store behavior is directly unavailable, and corrupt
  persisted state reaches the public registered-execution boundary and returns
  an `ExecutionEvidenceError` containing the safe
  `watermark_storage_corrupt` reason.
- Public same-root successor evidence provisions a fixed predecessor,
  authorizes and durably advances a successor, reopens the same store, and
  submits an otherwise-valid predecessor. Its observable failure is
  `active_pointer_watermark_rewind`, isolating anti-rewind behavior from root,
  signature, history, or report mismatch. The separate immutable 147-to-148
  test remains compatibility evidence.
- Scope integrity: round-3 runtime changes are confined to the acceptance
  watermark owner, release effective-time check, and safe public gate
  diagnostic. The closure writer changed only the registry and acceptance test
  files. No C1 fixture authority, C2 recipe/package, provider/runtime path,
  public closed-request service, or later generation/index/fence contract was
  changed.
- Coordinator deterministic evidence: complete Layer1 behavior partition
  `83 passed in 168.58s`; durable watermark store `9 passed in 4.88s`; public
  acceptance file `11 passed in 5.67s`; scoped Ruff passed;
  repository-configured Pyright reported zero errors and warnings; staged and
  unstaged diff checks passed. The unchanged exact compiler/checker evidence
  from the reviewed candidate remains `258 passed`, `18 passed`, and exact
  authority `f7c0d000...` with 56 schemas, 240 enum rows, and two replicas.
- Coordinator integrity judgment: all six confirmed round-3 Layer1 findings
  are remediated with behavior-level, non-circular evidence. The broader
  composition-owned closed-request service remains explicitly unimplemented
  later M0A scope and is not claimed by this milestone. Evidence maturity
  remains `locally verified`; fresh independent three-role review is required
  before Layer1 completion.
- Current next action: run fresh independent `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer` passes over the complete
  materially remediated Layer1 candidate.

### Layer1 148-heading fresh review round 2 reconciliation

- All three fresh reviewers rejected closure. Their independently reproduced
  boolean-coordinate finding is confirmed: Python `bool` currently satisfies
  the release/pointer integer checks and compares equal to history coordinate
  `1`, despite the WorkPlan's fail-closed claim.
- `L1-148-R2-01`: `P2 / changes_required / persistence and concurrency`.
  Confirmed from correctness review and the H3/H4 contract. The optional,
  mutable in-memory `TraceabilityReleaseWatermark` performs a non-atomic
  check-then-write. A fresh verifier with no retained watermark can authorize
  a valid superseded sequence-1 pointer after sequence 2 was accepted. A local
  lock is insufficient; every authorization must use an acceptance-owned
  durable atomic compare-and-advance boundary or return unavailable.
- `L1-148-R2-02`: `P2 / changes_required / schema validation and trust
  boundary`. Confirmed unanimously. Release and active-pointer epoch/sequence
  values must use exact positive-integer checks that exclude booleans before
  sorting, equality, conversion, or watermark use. Add signed end-to-end
  boolean release, pointer, and combined mutations and prove watermark state is
  unchanged.
- `L1-148-R2-03`: `P2 / changes_required / history integrity`. Confirmed from
  correctness review. Successor issuance and entry-effective times are not
  required to be strictly later than the predecessor transition, so an
  authorized signer can append a backdated higher sequence. Require monotonic
  issuance/effective order and valid transition time bounds with a signed
  public-gate negative.
- `L1-148-R2-04`: `P2 / changes_required / verification and security`.
  Confirmed from test review. Current-root negative tests corrupt bytes or
  select the wrong current artifact, but never re-sign a semantically valid
  current release/history/pointer with a wrong registry identity or required
  root. Add those public-gate controls so deletion of current-root validation
  cannot pass.
- `L1-148-R2-05`: `P2 / changes_required / verification and security`.
  Confirmed from test review. The watermark suite covers lower-coordinate
  rewind but not same-coordinate/different-digest substitution or
  same-coordinate/same-digest idempotency. Add atomic-store assertions for
  both, including no state change on rejection.
- `L1-148-R2-06`: `P2 / changes_required / verification`. Confirmed by direct
  inspection. Existing tests compare canonical construction with verifier
  acceptance and compare two independent rebuild invocation modes, but do not
  directly assert canonical manifest bytes equal the raw-registry independent
  approval rebuild. Add the cross-implementation byte equality assertion.
- The disclosed flat profile/signer envelope and later generation/index/fence
  schema work remain recorded outside this Layer1 slice; reviewers did not
  classify them as current blockers. Stale C1 and blocked C2 remain excluded.
- Current next action: complete the bounded read-only durable anti-rewind
  ownership map, then assign one remediation worker all confirmed round-2
  findings.

### Layer1 148-heading remediation round 2 and coordinator integrity check

- One sole writer implemented an acceptance-owned durable anti-rewind boundary
  for the release gate. `FileTraceabilityReleaseWatermarkStore` owns one
  canonical, exact-schema `(epoch, sequence, release_digest)` record, serializes
  compare-and-advance with the repository's cross-process exclusive lock, and
  publishes through file fsync, atomic replace, and directory fsync. Reopen,
  same-coordinate idempotency, substitution, rewind, malformed state, and
  multi-process contention are covered. Storage or corruption failures return
  typed unavailable outcomes; production has no in-memory or success-shaped
  fallback.
- Release and pointer coordinates now require exact positive integers before
  sorting, equality, history comparison, or watermark mutation, excluding
  booleans. Successor issuance and effective times must be strictly later than
  the predecessor transition. The signed semantic negatives prove boolean
  substitution and backdating reject without advancing the watermark.
- The release gate now requires composition-owned exact external release roots
  and returns unavailable when that trust channel is absent or malformed.
  `AcceptanceTrustStore` carries this authority into the sole registered public
  approval path. The current selected release must equal both registry-derived
  roots and every externally reconstructed root; the prior presence-only empty
  root fallback was removed.
- Coordinator validation found and rejected an initially circular unit oracle:
  a forged structural root had been reused as its own expected value. The
  corrected unit test captures root truth before mutation, and a public
  acceptance test holds the composition-owned authority fixed while re-signing
  the release, history, and pointer with a forged structural digest. Correct
  roots authorize; the forged root rejects.
- Public execution now forwards immutable historical release artifacts, so the
  acceptance proof authorizes a signed current 148 successor over immutable
  147-source bytes, reopens the same file-backed watermark idempotently, and
  rejects a valid superseded coordinate. The gate-level proof separately uses
  equal current roots for both generations so the old-coordinate rejection is
  attributable to durable anti-rewind state rather than a root mismatch.
- The canonical structural manifest is now directly byte-compared with the
  independently rebuilt manifest from raw registry bytes. Signed wrong current
  registry/structural roots, same-coordinate different-digest releases,
  strict-time violations, and unchanged-state failures have direct behavioral
  assertions.
- Coordinator deterministic evidence after the final correction:
  release/registry/manifest/traceability/execution-evidence/acceptance
  partition `76 passed in 162.31s`; durable watermark store `8 passed in
  4.12s`; scoped Ruff passed; repository-configured Pyright reported zero
  errors and warnings; staged and unstaged `git diff --check` passed.
- Scope integrity: the correction is confined to the acceptance watermark
  owner, release gate, public execution handoff, and their existing Layer1
  tests. It does not modify C1 fixture authority, C2 recipe/package tooling,
  provider/runtime behavior, or the later full generation manifest/index/fence
  contract.
- Coordinator integrity judgment: the six confirmed round-2 findings and the
  additional non-circular current-root defect are remediated with behavior-level
  evidence. Evidence maturity remains `locally verified`; fresh independent
  three-role review is required before Layer1 completion.
- Current next action: run fresh independent `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer` passes over the complete
  materially remediated Layer1 candidate.

### Layer1 148-heading fresh review round 15 interim reconciliation

- The fresh `spec_auditor` and `correctness_reviewer` completed independent
  full-state passes. The original `test_reviewer` did not return a report or
  status after repeated bounded waits and was interrupted; it is not counted
  as a completed review. A fresh read-only `test_reviewer` with the same
  independent mandate is running as the required replacement.
- `L1-148-R15-01`: `P2 / changes_required / security and lifecycle replay`.
  Confirmed from direct lifecycle-owner inspection. `activate` rejects a
  previously seen ordinary coordinate, but `rotate` and `recover` currently
  accept an independently provisioned bootstrap replacement without checking
  whether that coordinate already has an active or terminal interval. A
  revoked or compromised ordinary root can therefore be reinstalled as a
  replacement. Correction: make ordinary-root coordinate use append-only
  across activation and replacement, and add fully signed
  revoke/compromise-to-rotate and revoke/compromise-to-recover negatives that
  prove no watermark or evidence-seal mutation.
- `L1-148-R15-02`: `Not applicable / changes_required / verification and
  traceability`. Confirmed against frozen design section 3.23.4.1 and both
  raw-registry loaders. The production loader omits unique
  `structural_rules[].rule_id`, unique `anchor_bindings[].anchor`, and
  exactly-empty v1 `overrides` checks. The independent loader also omits those
  checks, permits duplicate per-node DAG dependencies, and does not perform
  the specified deterministic Kahn reconstruction. Correction: enforce the
  complete closed root policy independently in both loaders and add paired
  raw-registry mutations, structural-manifest-path rejection where
  applicable, and registered public-path no-watermark-mutation evidence.
- Scope disposition: both corrections are bounded implementation of the
  already-frozen Layer1 registry/lifecycle contract. They do not authorize a
  new trust service, signer envelope, generation repository, C1 fixture
  migration, or C2 package change.
- Current next action: complete the replacement test review, freeze any
  additional directly validated findings, then assign the entire round-15
  remediation set to exactly one writer.

### Layer1 148-heading fresh review round 15 final reconciliation

- The replacement `test_reviewer` completed the required third independent
  review. It independently confirmed the same two gaps and produced no
  additional bounded finding. The original unresponsive test review is not
  counted.
- Review disposition is closed: `L1-148-R15-01` and `L1-148-R15-02` are
  confirmed and enter remediation. No finding is duplicate outside this pair,
  no material design ambiguity remains, and the composition-owned
  closed-request/trust-loader/clock boundary remains a recorded later-M0A
  residual rather than a Layer1 finding.
- Required evidence for `L1-148-R15-01`: fully signed ordinary-root
  revoke/compromise then rotate/recover replacement attempts reject; durable
  watermark and evidence seal remain byte-identical; a fresh never-used
  replacement remains eligible so the correction does not prohibit valid
  rotation or recovery.
- Required evidence for `L1-148-R15-02`: canonical raw mutations for duplicate
  DAG dependency, duplicate structural-rule ID, duplicate anchor, and nonempty
  v1 overrides reject in both independent loaders. The independent loader
  reconstructs deterministic Kahn order. Applicable structural-manifest and
  registered public paths reject malformed registry bytes before durable
  watermark or seal mutation.
- Current next action: exactly one remediation writer owns both runtime
  corrections and their behavioral tests, followed by direct coordinator
  inspection and all applicable Layer1 gates.

### Layer1 148-heading remediation round 15 and coordinator integrity check

- One sole writer remediated the two confirmed findings. Ordinary bootstrap
  coordinates now enter the lifecycle interval/tombstone map on their first
  installation and `rotate` or `recover` rejects any replacement already in
  that map with `lifecycle_replacement_coordinate_reused`. The correction is
  evaluated before replacement installation and does not alter fresh
  provisioned-coordinate eligibility.
- Fully signed `revoke` and `compromise` cases activate and terminate an
  ordinary secondary root, then attempt both ordinary rotation and
  threshold-recovery replacement back to that coordinate. Each reaches the
  exact reuse rejection and preserves byte-identical durable watermark and
  bootstrap seal. The existing threshold recovery followed by rotation to a
  never-used provisioned root remains the positive generality control.
- The production registry loader now enforces unique structural-rule IDs,
  unique anchor names, exactly-empty v1 overrides, duplicate-free known DAG
  dependencies, and deterministic source-order-tie-break Kahn order. The
  independent raw loader implements the same invariants with its own code path
  and does not import the production validator or encoder.
- Paired canonical raw-registry mutations cover a duplicate DAG dependency,
  duplicate rule ID, duplicate anchor, and nonempty override through both
  loaders and the independent structural rebuild. The registered public path
  exercises each malformed source with a provisioned watermark and proves the
  watermark record and seal remain byte-identical.
- Coordinator behavioral and architecture inspection confirmed both
  production rejection paths and their independent implementations. The five
  materially changed files map directly to `L1-148-R15-01` or
  `L1-148-R15-02`; no design, registry authority, CTV package, workflow,
  closed-request service, C1/C2, or generation-repository file changed in this
  remediation.
- Deterministic evidence on the complete remediated candidate: Layer1 behavior
  partition `169 passed in 198.73s`; independent compiler `258 passed in
  198.22s`; PR-gate partition `18 passed in 114.52s`; exact pinned authority
  checker passed with authority `f7c0d000...`, 56 schemas, 240 enum rows, and
  two replicas; scoped Ruff passed; repository-configured Pyright and explicit
  production-owner Pyright both reported zero errors and warnings; staged and
  unstaged diff checks passed.
- A full-repository Ruff invocation still reports the pre-existing import
  order in
  `tests/fixtures/semantic_ingestion/provider_compatibility/ProviderEvolutionOutcome.baseline.py`.
  That fixture is outside this remediation and was not modified. Explicit
  Pyright of the accumulated test files likewise exposes pre-existing
  untyped-helper errors outside the repository-configured include set; no
  round-15 changed line introduced one. These observations are not represented
  as green changed-test static evidence.
- Coordinator integrity judgment: both confirmed round-15 gaps are remediated
  with behavior-level, non-circular evidence. Evidence maturity remains
  `locally verified`; fresh independent three-role review is required before
  bounded Layer1 completion.
- Current next action: run fresh independent `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer` passes over the complete
  materially remediated Layer1 candidate.

### Layer1 148-heading fresh review round 16 reconciliation

- Three independent read-only lanes completed full-state review. The
  collaboration thread limit prevented allocating a new test-review thread, so
  the previously interrupted `test_reviewer` instance was resumed for a new
  post-remediation pass. Its interrupted round-15 attempt produced no report
  and is not counted; this round-16 pass is the required third completed
  independent review and was not shown the other reviewers' findings.
- `L1-148-R16-01`: `P2 / changes_required / architecture and verification`,
  SIA-R03. Confirmed against frozen section 3.23.4.1 and the declared registry
  source models. Both loaders accept canonical packages with unknown
  root-record members, fail to resolve requirement bindings against the exact
  `(assertion_template_id, assertion_version)` coordinate, and do not enforce
  numeric requirement-binding or bytewise assertion-template/test-group
  order. Correction: independently enforce complete v1 member shapes, typed
  coordinates, exact reference resolution, and specified order in each
  loader. Paired raw-loader, independent rebuild, and public durable
  non-mutation evidence is required.
- The correctness review's malformed `artifact_dag.depends_on` finding is a
  confirmed subcase of `L1-148-R16-01`, not a separate architecture gap. The
  production loader treats `""` as an empty dependency sequence because it
  does not require `list[str]`; the independent loader already rejects it.
  Both loaders must reject string, null, object, numeric, and mixed-element
  dependency representations before DAG operations.
- `L1-148-R16-02`: `P2 / changes_required / trust lifecycle`. Confirmed
  against the final-record envelope-signer rule in frozen section 3.23.4. A
  recovery-root `revoke` or `compromise` record can be signed by active
  ordinary root A while the envelope remains authorized by stale `root_signer`
  B selected by an earlier activation. Correction: derive the terminal
  recovery-root envelope signer from the cryptographically verified
  `ordinary_record_signer`, reject if absent, and prove B-envelope/A-record
  rejection, A-envelope/A-record acceptance, and durable non-mutation.
- `L1-148-R16-03`: `P2 / changes_required / verification and lifecycle
  replay`. Production already rejects ordinary-coordinate reuse through later
  `activate`, but no signed revoke/compromise test would fail if that
  tombstone check were deleted. Add ordinary-root terminal-then-reactivate
  public gate negatives with exact reason and unchanged watermark/seal, plus
  a distinct never-used activation success control.
- `L1-148-R16-04`: `Not applicable / changes_required / verification and
  registry integrity`. Production already performs deterministic Kahn
  comparison, but the duplicate-edge tests cannot detect removal of that
  comparison. Add a dependency-valid canonical mutation that swaps two
  independently ready nodes so ordinary topological validity remains while
  the specified source-order Kahn result differs. Both loaders, independent
  structural rebuilding, and the registered public path must reject before
  watermark/seal mutation.
- Scope disposition: all four corrections implement or prove the frozen
  registry/lifecycle contract in the existing canonical owners. They do not
  authorize the deferred typed multi-signer envelope, terminal-recovery public
  service, generation repository, C1 fixture migration, C2 package, or any
  authority/design change.
- Current next action: exactly one remediation writer owns the two bounded
  production corrections and all paired behavioral evidence, followed by
  direct coordinator integrity inspection and the applicable deterministic
  gates.

### Layer1 148-heading remediation round 16 and coordinator integrity check

- The same sole writer retained ownership of the overlapping registry,
  lifecycle, and test surfaces. Both raw loaders now independently enforce
  exact closed-v1 ordinary-root member keys and nested evidence-group shapes,
  exact positive template coordinates, exact binding resolution, R01-R23
  numeric binding order, bytewise template/group order, empty overrides, and
  dependency `list[str]` shape before DAG operations. The closed thirteen-node
  v1 DAG order is explicit in each independent implementation; no loader
  imports the other's constants or validator.
- Canonical mutations cover unknown members across every ordinary nonempty
  root, unresolved assertion version, binding/template/group order, string,
  null, object, numeric, and mixed dependency shapes, and a dependency-valid
  independently-ready node swap. Each mutation rejects in both loaders and
  independent structural rebuilding. The registered public path uses the same
  mutation classes and proves byte-identical watermark and bootstrap seal.
- Terminal recovery-root `revoke`/`compromise` now sets the lifecycle envelope
  signer from the already verified ordinary record signer and fails closed if
  no such signer exists. Signed A/B/R cases reject a stale B envelope over an
  A-signed final record, accept the matching A envelope, and preserve durable
  state on rejection.
- Signed ordinary-root revoke/compromise histories now attempt later
  `activate` of the terminal coordinate and reach the exact tombstone
  rejection with unchanged watermark/seal. A separately provisioned,
  never-used coordinate activates and authorizes a re-signed release,
  establishing that the invariant forbids resurrection rather than valid
  extension.
- Coordinator inspection traced all corrections through the canonical raw
  loaders and lifecycle replay owner. The hard-coded thirteen-node order is
  the frozen closed-v1 artifact order declared by the approved design, not a
  fixture/test exception or general future-version registry. The five changed
  files map directly to `L1-148-R16-01` through `L1-148-R16-04`; no authority,
  design, workflow, C1/C2, trust-service, or generation-repository file changed
  in this remediation.
- Deterministic evidence on the complete remediated candidate: focused
  round-16 matrix `33 passed`; complete Layer1 partition `202 passed in
  214.40s`; independent compiler `258 passed in 202.37s`; PR-gate partition
  `18 passed in 118.22s`; exact pinned authority checker passed with authority
  `f7c0d000...`, 56 schemas, 240 enum rows, and two replicas; scoped Ruff
  passed; explicit production-owner and repository-configured Pyright each
  reported zero errors and warnings; staged and unstaged diff checks passed.
- Shortcut classification remains unchanged: temporary-file naming and
  re-raising cleanup in the durable watermark owner are normal atomic
  publication mechanics; the exception-class body `pass` and skipped/xfailed
  wording are declarative/error-reporting code, not stubs or disabled tests.
  The unrelated baseline-fixture import-order issue found by full-repository
  Ruff remains outside this remediation and was not modified.
- Coordinator integrity judgment: all four confirmed round-16 corrections are
  implemented and proven at behavior level without weakening or widening the
  frozen contract. Evidence maturity remains `locally verified`; fresh
  independent three-role review is required before bounded Layer1 completion.
- Current next action: run fresh independent `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer` passes over the complete
  materially remediated Layer1 candidate.

### Layer1 148-heading remediation round 18 and coordinator integrity check

- The sole remediation writer confined the change to the canonical source
  loader, the independent raw-byte loader, and their direct unit/acceptance
  evidence. The independent loader now rejects every non-array root before
  concatenation, indexing, or iteration; its canonical encoder independently
  enforces NFC Unicode scalars and emits quote/backslash plus lowercase
  four-hex control escapes.
- Both loaders independently recurse through the JSON Schema subset consumed
  by execution evidence. They reject invalid nested `anyOf`, `const`, object,
  array, string, and scalar nodes by closed keyword/type/constraint rules,
  without importing the execution validator or a schema framework and without
  pinning checked-in schema bytes.
- Direct evidence replaces every array root with object/null/string/number;
  proves LF/tab canonical parity and typed lone-surrogate rejection; and
  rebinding specialized digests proves nested report-schema rejection. The
  valid-typed alternate registry identity/design path and schema/profile
  version-two mutations also rebind dependent digests and prove both loaders,
  independent rebuild, and the registered public boundary reject without
  changing the provisioned watermark or bootstrap seal.
- Deterministic evidence from `memorii/` under
  `../.venv/bin/python` (Python 3.12.13):
  `-m pytest tests/unit/tools/test_semantic_ingestion_traceability_registry.py -q -p no:cacheprovider`
  passed (243 collected); `-m pytest
  tests/acceptance/semantic_ingestion/test_sia_requirements.py -q -p
  no:cacheprovider` passed (170 collected); scoped Ruff over the two loaders
  and those test modules passed. `git diff --check` passed.
- Coordinator integrity judgment: all four round-18 corrections are now
  locally verified with typed failure staging and durable non-mutation
  evidence. No C1/C2 semantics, later M0A services, frozen authority bytes,
  or unrelated behavior changed. Evidence maturity remains locally verified;
  the next action is a fresh bounded read-only review, not another product
  remediation round unless a supported P1/P2 scenario is demonstrated.

### Layer1 148-heading fresh review round 17 reconciliation

- Three new full-state passes completed using the existing named reviewer
  instances because the collaboration service could not allocate additional
  reviewer threads. Each reviewer was instructed to discard its prior
  conclusion, re-read the complete post-remediation state, and not inspect the
  other round-17 lanes. All three completed read-only review.
- `L1-148-R17-01`: `P2 / changes_required / registry authority,
  architecture, and verification`, SIA-R03. Unanimously confirmed against
  frozen section 3.23.4.1 and the declared specialized models. The ordinary
  roots are closed, but both loaders still accept unknown outer report-schema
  members and unknown nested runner-profile policy members when dependent
  group digests are consistently rebound. Scalar metadata is not type/literal
  checked, and unhashable schema/profile IDs can escape as raw `TypeError`
  before a typed loader rejection.
- Smallest correction for `L1-148-R17-01`: independently validate the exact
  frozen-v1 scalar metadata; exact report-schema outer/root-document keys,
  primitive coordinate types, fixed literals, and positive versions before
  set construction; and every nested runner-profile policy's exact keys,
  primitive/container types, and frozen literals. Do not implement a new
  schema framework, C2 content-boundary migration, or shared validator.
  Paired mutations must rebind all affected group digests so rejection cannot
  be caused by stale digests. Cover unknown specialized members, scalar
  substitutions, unhashable/non-string IDs, malformed versions, independent
  rebuild, and public watermark/seal non-mutation.
- `L1-148-R17-02`: `Not applicable / changes_required / verification and
  registry integrity`, SIA-R03. Confirmed from the test review. The current
  independently-ready-node swap is rejected first by the explicit closed-v1
  node-order check, so it does not prove the later Kahn reconstruction.
  Correction: retain the exact node order and all dependency shape/identity
  checks but add a back-edge such as
  `bootstrap_trust_anchor.depends_on = ["recovery_trust_roots"]`. Require both
  loaders and independent rebuild to reject because deterministic Kahn order
  cannot reproduce the declared order; the public path must preserve
  watermark and seal.
- Scope disposition: both corrections close the already-approved v1 registry
  loader and verification contract. They do not authorize content-boundary
  schema redesign, C1/C2 changes, trust-service composition, typed signer
  envelope migration, or generation repository work.
- Current next action: exactly one remediation writer owns both independent
  specialized/scalar validation implementations and their non-circular
  behavioral evidence, followed by direct coordinator integrity inspection
  and all applicable deterministic gates.

### Layer1 148-heading remediation round 17 and coordinator integrity check

- The same sole writer changed only the two raw registry loaders and their
  existing unit/public acceptance owners. Both loaders independently enforce
  the four exact frozen-v1 scalar metadata values before structural expansion.
  Report-schema items require the exact outer keys, fixed ID/version/profile/
  media literals, and the closed root JSON-schema document shape with typed
  properties/required members. Coordinate types are checked before set
  construction, so lists, booleans, strings, zero, and other malformed values
  return the loader's typed rejection instead of `TypeError`.
- Every runner-profile nested policy now has an explicit closed key set,
  required primitive/container types, and the frozen literal constraints
  declared by the approved v1 models. Variable version/digest/marker content
  remains variable where the model permits it; there is no exact whole-profile
  digest shortcut, shared validator, Pydantic dependency, or speculative
  versioning framework.
- A 56-case specialized/scalar corpus mutates unknown outer and nested members,
  scalar values/types, unhashable and non-string coordinates, malformed
  versions, nested container shapes, and policy literals. After every
  mutation, all affected test-group specialized digests are recomputed, so
  rejection is caused by closed shape/type/literal validation rather than a
  stale digest. Both loaders, independent structural rebuilding, and public
  registered execution reject; public cases preserve byte-identical watermark
  and bootstrap seal.
- Deletion-sensitive Kahn evidence retains the exact thirteen-node source
  order and legal, unique, known dependency strings while making
  `bootstrap_trust_anchor` depend on later `recovery_trust_roots`. It therefore
  passes explicit node-order and dependency-shape checks and rejects only when
  deterministic Kahn reconstruction cannot reproduce the declared order. The
  public path again proves durable non-mutation.
- Coordinator inspection confirmed all changed validations execute before
  coordinate-set construction or manifest building. The four materially
  changed files map directly to `L1-148-R17-01` or `L1-148-R17-02`; no release,
  design, source-registry, authority, workflow, C1/C2, trust-service, or
  generation-repository file changed in this remediation.
- Deterministic evidence on the complete remediated candidate: focused
  round-17 matrix `143 passed in 39.13s`; complete Layer1 partition `316 passed
  in 240.39s`; independent compiler `258 passed in 199.93s`; PR-gate partition
  `18 passed in 115.74s`; exact pinned authority checker passed with authority
  `f7c0d000...`, 56 schemas, 240 enum rows, and two replicas; scoped Ruff
  passed; explicit production-owner and repository-configured Pyright each
  reported zero errors and warnings; staged and unstaged diff checks passed.
- Coordinator integrity judgment: both confirmed round-17 corrections are
  implemented and proven without a content-hash shortcut, stale-digest oracle,
  shared validator, or scope expansion. Evidence maturity remains `locally
  verified`; a fresh post-remediation three-role review is required before
  bounded Layer1 completion.
- Current next action: run independent `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer` passes over the complete
  materially remediated Layer1 candidate.

### Layer1 148-heading fresh review round 18 reconciliation

- Three existing named reviewer instances completed new independent full-state
  passes over the post-round-17 candidate. They were instructed to discard
  prior conclusions and not inspect the other round-18 lanes.
- `L1-148-R18-01`: `P2 / changes_required / registry grammar and runtime
  failure`, SIA-R03. Confirmed. The independent loader does not perform the
  production loader's universal array-root check before concatenation,
  indexing, or iteration. Canonical object/null/scalar substitutions for an
  array root can therefore escape as raw Python exceptions through independent
  rebuild and the registered public boundary. Add a local independent
  all-array-root guard and paired per-root typed/non-mutation evidence.
- `L1-148-R18-02`: `P2 / changes_required / canonical compatibility and typed
  failure`, SIA-R03. Confirmed against frozen canonical profile text.
  Independent `_canonical` delegates strings to `json.dumps`, which uses short
  control escapes rather than mandatory lowercase four-hex escapes. A
  production-canonical open string containing LF/tab is rejected by the
  independent loader, while an escaped lone surrogate can leak
  `UnicodeEncodeError`. Replace only the independent string branch with its own
  NFC/Unicode-scalar validation and quote/backslash/four-hex-control encoder.
  Prove LF/tab parity and typed lone-surrogate rejection.
- `L1-148-R18-03`: `P2 / changes_required / report-schema grammar and failure
  staging`, SIA-R03. Confirmed. Both source loaders validate only the root
  report-schema container and accept invalid nested executable schema nodes
  when group digests are rebound. Independently validate in each loader the
  recursive JSON Schema subset actually consumed by
  `execution_evidence._validate_schema`: supported keyword sets and value
  types; compatible `type`/keyword combinations; nonempty valid `anyOf`;
  object properties plus unique required names consistent with the property
  map; array item/minimum/uniqueness constraints; string
  length/pattern/date-time declarations; const-only nodes; and rejection of
  unsupported keywords/types. Do not import the execution validator or a
  schema framework and do not pin exact checked-in schema bytes. Add
  rebound-digest loader/rebuild/public no-mutation mutations.
- `L1-148-R18-04`: `Not applicable / changes_required / verification and
  registry authority`, SIA-R03. The test reviewer labeled this P2, but direct
  production inspection shows exact equality checks already reject the
  values; the gap is deletion-sensitive proof rather than demonstrated broken
  product behavior. Add valid-typed alternate `registry_id`, `design_path`,
  report schema version `2`, and runner profile version `2` cases with
  specialized digest rebinding through both loaders, rebuild, and public
  durable non-mutation.
- The Kahn back-edge, recovery-envelope signer, ordinary tombstone, specialized
  digest-rebinding, and nested profile findings from prior rounds are resolved
  and were not reopened. Scope remains the approved v1 registry loader and
  evidence boundary; C2 content migration and later M0A services remain
  excluded.
- Current next action: exactly one writer owns the independent array/string
  corrections, both recursive schema-dialect validators, and their behavioral
  evidence, followed by direct coordinator inspection and all deterministic
  gates.

### Layer1 148-heading remediation round 19

- Confirmed `P2 / changes_required / registry grammar and runtime failure`,
  SIA-R03: raw public approval inputs with approximately 1100 structural
  nesting levels or a 5000-digit JSON integer could reach implementation-
  dependent `RecursionError` or `ValueError` before typed rejection. This is
  an important malformed-trust-boundary scenario because the registered
  approval API accepts raw registry bytes before any durable state mutation.
- The sole writer added separate, clean-room byte transport checks in the
  production registry loader and independent approval loader. Each bounds
  only raw JSON nesting (256) and numeric token width (1024), excludes quoted
  content, and normalizes residual decoder/canonicalizer `RecursionError` or
  `ValueError` to that loader's public typed error. No shared parser helper,
  general resource-limit framework, C1/C2 behavior, M0A service, or frozen
  authority artifact changed.
- New focused evidence exercises deeply nested array, object, and schema
  payload shapes plus an oversized integer token through both loaders and
  independent manifest rebuilding. The registered public path rejects each
  with `TraceabilityCoverageError` while preserving byte-identical provisioned
  watermark and bootstrap-seal files.
- Local deterministic checks: AST syntax parsing, direct Python 3.12 loader
  matrix (all four malformed payloads reject with the respective typed error;
  canonical authority still loads in both paths), focused unit evidence
  (`4 passed, 243 deselected`), focused public evidence (`4 passed, 170
  deselected`), scoped Ruff, and `git diff --check` passed. The focused
  commands used `memorii/../.venv/bin/python` from `memorii/` with
  `PYTHONDONTWRITEBYTECODE=1` and `-p no:cacheprovider`.
- Current next action: final round-20 read-only review of the complete
  Layer1/M0 candidate; do not open another remediation unless a newly
  demonstrated supported P1/P2 product scenario satisfies the remediation
  gate.

### Layer1/M0 remediation round 20 delta

- Confirmed `P2 / changes_required / registry grammar and runtime failure`,
  SIA-R03: a digest-rebound canonical registry may contain the otherwise
  allowed pattern `a{999999999999999999999999999999}`. Python raises
  `OverflowError` rather than `re.error` while compiling that schema pattern,
  which escaped both source loaders and the registered public approval path
  before durable-state mutation. This is an important malformed
  trust-boundary scenario because registered approval accepts raw registry
  bytes and must fail with its typed boundary error.
- Each clean-room schema-dialect validator now catches `OverflowError` beside
  `re.error` solely at its existing `re.compile` call and converts it to the
  loader's established typed pattern-compilation error. Regex policy and all
  other validation semantics are unchanged.
- Paired rebound-digest evidence proves production loading,
  independent loading, and independent structural rebuilding reject the
  pattern with their respective typed errors. Registered public execution
  rejects before committing and preserves byte-identical pre-provisioned
  watermark and bootstrap-seal files.
- Local deterministic evidence: focused loader/rebuild test `1 passed, 247
  deselected`; focused registered-public test `1 passed, 174 deselected`.
- Bounded final status: the round-20 delta is implemented and locally
  verified; no further Layer1/M0 remediation is authorized without a newly
  demonstrated supported P1/P2 product defect under the remediation gate.
- Current next action: coordinator runs the final bounded read-only
  round-20 review and reconciles only supported P1/P2 findings.

### Layer1/M0 final round-20 reconciliation

- The final spec and test reviewers found no validated P1/P2 defect. The
  correctness reviewer reproduced one `P2 / changes_required / registry
  grammar and runtime failure`: Python `re.compile` could raise
  `OverflowError` for a digest-rebound canonical report-schema pattern and
  leak it through both loaders and registered public approval.
- The bounded round-20 delta normalized that implementation exception to each
  loader's existing typed error and added paired production-loader,
  independent-loader, rebuild, and public durable-nonmutation evidence.
  Targeted correctness and test re-review reproduced the exact case, confirmed
  the P2 resolved, and found no demonstrated regression.
- Coordinator verification on the complete post-delta candidate passed:
  `423 passed in 186.77s` for the Layer1 registry/acceptance partition, scoped
  Ruff passed, and `git diff --check` passed under repository Python 3.12.13.
- Non-remediation observations are record-only proof-strengthening: rename one
  redundant rebuild test and optionally snapshot the complete store-directory
  inventory in public negative tests. Neither demonstrates broken supported
  behavior and neither enters another remediation round.
- Bounded conclusion: Layer1 SIA-R03/L1-008/L1-009 is complete at locally
  verified and CI-enforced evidence maturity with no remaining validated P1/P2
  implementation defect. Remote CI/branch-protection observation remains
  unavailable external evidence. Broader M0A schema/artifact closure remains a
  separate blocked milestone and is not claimed complete.
- Current next action: keep the completed Layer1 candidate pinned and leave the
  separate M0A blocker paused pending a separately authorized milestone.

## M0 Current-Pin Schema And Artifact Closure

- Date: 2026-07-30.
- Authorization: the user explicitly directed the coordinator to finish the
  two remaining M0 blockers before beginning M1.
- Status: blocked pending linked current-pin C2 recipe design correction.
- Requirements: SIA-R03 and SIA-R13 only.
- Current inputs: design SHA-256
  `67bf2620a0379761853861e416efba0816045ef4bf88e4808e701a9ac3bc993e`;
  registry SHA-256
  `8e6395e2657eb1a51e5eef7d9b88b5d43b974a58f7f786ed135f6758262bfec1`;
  Layer1 authority SHA-256
  `f7c0d00080b02343f57fc69adee47ef0d7db1846641b1a7bb11fc7bc0b97c74e`;
  profile digest
  `20edd38a4ef41e4abf7e1b9a65fe2745e65705f80ec8f93c48c658739b7660a0`.
- Historical C1 and C2 status: the 52-schema C1 authority and C2 round-20
  design/registry pins are provenance only. They are stale against the current
  56-schema design and 148-heading registry and are not an oracle or completion
  evidence. Do not repair or republish them as current authority.
- Included blocker 1: implement the current design's exact closed canonical
  typed-value profile/binding/envelope subset for bootstrap, recovery,
  lifecycle, trust snapshot, coverage, execution, release, pointer/history,
  generation manifest/member, and their signature-preimage contracts.
  Unknown fields, variants, bindings, profiles, domains, purposes, enum values,
  noncanonical encodings, and decode/re-encode inequality fail before
  authorization.
- Included blocker 2: add one byte-backed acceptance generation boundary that
  loads the closed ordered member set, validates member coordinates, kinds,
  schemas, bindings, digests, dependencies and order, independently rebuilds
  the structural manifest from exact design/registry bytes, recomputes coverage
  and execution roots from the complete member bytes, and compares every root
  with the signed release before the existing durable watermark commit.
- Canonical owners: typed contracts and canonical codec under `memorii.core`;
  thin trust/release adaptation in
  `semantic_ingestion_traceability_release.py`; structural reconstruction in
  the existing manifest/checker owners; coverage/execution/generation
  verification in `semantic_ingestion_execution_evidence.py`.
- Explicit exclusions: M1 result lookup, ordinary semantic-ingestion runtime,
  a general public composition service, C3 generation repository/index/fence
  redesign, external operational keys/releases, and operational certification.
  Existing watermark non-mutation remains the only persistence obligation in
  this bounded closure.
- Validation matrix: exact valid-byte round trip for every in-scope body,
  envelope and preimage; separately authored canonical-byte parity; missing,
  extra, duplicate, reordered, wrong-kind/schema/binding/profile/dependency,
  dangling, cross-generation, digest-mismatched and substituted members;
  structural unit/mapping mutation; coverage approval/root mutation; execution
  observation/report/evidence/root mutation; G1/G2/G3 positive closure; and
  public typed rejection with byte-identical watermark/bootstrap-seal state.
- Completion: current-pinned deterministic package bytes pass both the runtime
  codec and independent verifier; the public registered approval path accepts
  only after independently recomputing structural, coverage and execution
  byte closure; the complete focused suite, Ruff, Pyright and diff checks pass;
  fresh spec, correctness and test reviewers leave no validated P1/P2 defect.
- Current next action: wait for the linked current-pin C2 design correction to
  publish an explicit, reviewed operand graph; no implementation writer may
  invent fixture selectors, preimages, or replacement primitive bytes.

### M0 current-pin implementation readiness blocker

- The first implementation pass added a strict canonical CTV/envelope owner
  and made registered approval reject absent generation bytes. It also
  demonstrated one current-pinned G1 structural package path. These edits are
  incomplete implementation evidence and must not be cited as M0 closure.
- Two independent readiness audits confirmed that the normative recipe at
  `docs/design/semantic_ingestion/traceability_golden_vectors/recipe-v1.json`
  is stale: its shape and identities are bound to historical design
  `4020901b...` and registry `38c45adc...`, while the current design requires
  the v1 recipe/root contract under design `67bf2620...`, registry
  `8e6395e2...`, authority `f7c0d000...`, and profile `20edd38a...`.
- The implementation may not invent the missing current fixture values or use
  its own codec/verifier as the fixture oracle. Operational
  `SIA-ED-TRACEABILITY-001` material is not required for deterministic
  non-operational fixtures; the blocker is solely the mismatched normative
  recipe authority.
- The current structural manifest is large but derivable: independent rebuild
  observed 31,048,708 canonical bytes, 12,114 units, 67,280 mappings, and
  digest `cc1cbe328d2257e2ec1450898d160afea2102794ae470b6641754162b6b11b9c`.
  Implementations must stream or spool it rather than weaken artifact closure.
- Exact blocker: a linked design operation must reconcile the finite C2 recipe
  format, eight v2 roots, 56-schema/240-enum authority, current registry
  identity, non-operational G1/G2/G3 primitive inputs, and streaming
  materialization contract. Only then may implementation resume.
- Current next action: complete and independently approve the linked
  current-pin C2 recipe design correction; preserve partial implementation
  edits without treating them as evidence.

### M0 Current-Pin Closure Progress

- 2026-07-30: Added the first canonical `memorii.core` CTV owner at
  `memorii/memorii/core/memory_evolution/ingestion_contracts.py`. It implements
  a strict tagged scalar/collection algebra, embedded binding validation,
  length-prefixed canonical-artifact preimage, digest verification, and
  decode/re-encode rejection. The execution boundary now requires a complete
  byte-backed generation input before any report verification or watermark
  commit, validates member coordinates/digests/dependency order, independently
  rebuilds the structural root from exact design and registry bytes, and checks
  structural/coverage/execution roots against the release.
- Evidence: Python 3.12 `py_compile`, scoped Ruff, and `git diff --check`
  passed. The pre-existing raw-only R03 acceptance fixture now deterministically
  rejects with `generation closure is incomplete`; this is an intentional
  transition, not completion evidence.
- Current next action: materialize the finite current-pinned G1/G2/G3 package
  from independent test fixtures, then complete closed per-kind schema,
  signature-preimage, coverage, and execution reconstruction tests before
  considering this milestone complete.

### M0 Current-Pin Operand-Authority Blocker

- 2026-07-30: the linked design operation completed a reproducible complete
  audit of `recipe-v1.json`. Every derived ledger row is missing exact
  operands: 1,452 total, partitioned as 678 `v2_profile_or_binding`, 453
  `canonical_body_or_identity_digest`, 264
  `artifact_coordinate_or_envelope`, 31
  `signature_preimage_or_signature`, and 26
  `structural_or_generation_root`. The audit tool at
  `docs/design/semantic_ingestion/traceability_golden_vectors/audit_current_recipe_operands.py`
  emits every affected fixture/path and found zero rows with explicit operands.
- The current recipe format is itself unable to close that gap because
  `validate_recipe.py` accepts derived rows only with generic `depends_on` and
  `derivation_rule_id` fields and rejects an `operands` field. Formula-family
  labels do not select a source fixture/path, design/registry/profile constant,
  preimage construction, or topological edge.
- Fixture 35 independently conflicts with the frozen current design: its
  primitive CTV content bytes/media type are v1, while C2 requires v2 before
  body decoding. Ownership marks those fields primitive, so no implementation
  derivation can repair them without a reviewed recipe/design change.
- Status: M0 remains blocked. This is a `Not applicable / blocks_approval /
  design-authority` finding, not a P1/P2 product defect: no supported runtime
  path consumes the non-operational C2 candidate, and M1 must not start.
- Current next action: obtain the linked design WorkPlan's exact corrected
  recipe authority: explicit operands/preimages for all 1,452 derived paths,
  a complete acyclic selector graph, and a resolved fixture-35 v1/v2
  primitive decision, then run independent design review before resuming M0.

### M0 scenario-first authority decision

- The user superseded field-first fixture authoring with scenario-first
  authority: freeze semantic entities, facts, relationships, temporal and
  attribution state first; deterministically render an interaction from that
  scenario; run the real semantic extraction path on only the interaction; and
  require the normalized extracted projection to equal the original scenario.
- The hidden scenario is comparator authority only and cannot enter production
  extraction, prompts, retrieval, or persistence. This preserves simulator and
  oracle isolation.
- Traceability coverage/execution artifacts derive from the exact rendered
  source and actual extraction run. They may not contain manually selected
  expected digests or reuse production extraction as their own oracle.
- Current next action: complete and approve the linked scenario-first C2
  design, then resume the two blocked M0 implementation owners against it.

### M0 test-retention and naming closure

- 2026-07-31: completed a case-by-case audit of the historical C1 fixture and
  flat traceability-registry negative suites before pruning them. Current CTV
  provenance, persistence, watermark, hostile-parser, graph, recovery, and
  lifecycle suites already supersede the obsolete cases.
- Migrated the remaining useful behaviors into current owners: canonical raw
  registry-byte rejection, closed heading-default and nested registry-member
  rejection, duplicate numbered-heading rejection, and production source/wheel
  isolation for scenario fixture authority. All public rejection cases assert
  byte-identical watermark and bootstrap-seal state.
- Removed the historical C1 fixture suite and its five fixture/elaborator files,
  the obsolete flat registry suite, two duplicate scenario harnesses, and the
  broken unreferenced `verify_c2.py` for the historically blocked package.
- Renamed reader-facing scenario fixture modules and all private `_M0_*` /
  `_verify_m0_*` generation symbols to stable contract-based names. Frozen
  signed fixture identifiers and exact design heading bytes retain their
  protocol identities because renaming them would alter the contract bytes.
- Evidence: 27 migrated negative cases passed in 149.52 seconds; the complete
  current generation, scenario authority, and structural-manifest partition
  passed 60 tests in 862.74 seconds; the compact loader-parity and strengthened
  source/wheel-isolation partition passed 6 tests in 76.53 seconds; the exact
  noncanonical registry-byte cases passed 3 tests in 24.01 seconds; full Ruff,
  Pyright, workflow YAML parsing, and `git diff --check` passed.
- Review classification: these were bounded evidence-maintenance actions, not
  P1/P2 product defects. The historical verifier suggestion was rejected after
  direct reproduction showed that it targets a blocked, non-authoritative
  package and cannot run against the current validator CLI.
- Delta review found one confirmed `Not applicable / changes_required /
  verification` gap: deletion of the monolithic registry suite also removed
  direct production-loader, independent-loader, and structural-rebuild parity.
  A five-case compact current-contract parity suite now preserves canonical
  equality and representative canonicality, closed-member, heading-default,
  and parser-depth rejection without restoring obsolete flat lifecycle tests.
- The compatibility review's `Not applicable / blocks_approval` concern about
  deleting `memorii.tools.semantic_ingestion_scenario_test_trust` is unsupported:
  `memorii.tools` is documented as developer tooling, the module explicitly
  declared itself test-only, exported nothing through the package initializer,
  had no production composition path, and violated the production/test
  isolation invariant by being shipped. A production compatibility shim would
  reintroduce the defect because test fixtures are intentionally absent from
  wheels.
- Current next action: complete delta review, run repository static checks, and
  commit only the M0/CI fixes while excluding unrelated M1 and process changes.

### M3 prompt and egress authority increment (2026-08-02)

- Implemented the canonical M3 prompt authority in
  `memorii/memorii/core/semantic_ingestion/prompt_authority.py` and registered
  `semantic_ingestion_proposal:v1`. The authority loads YAML through the
  existing registry/renderer path, binds the prompt content/schema/owner/
  visibility/redaction coordinates, preserves source text verbatim in its own
  wire field, deep-sanitizes non-source metadata, retains immutable wire/trace
  metadata bytes, and revalidates a content-addressed authority digest before
  serialization. This blocks a `model_copy` binding substitution before a
  transport call.
- Implemented source-bound egress lifecycle and transport verification in
  `memorii/memorii/core/semantic_ingestion/egress.py`. Host-owned signature and
  signer-lifecycle verifiers are mandatory; the package provides no local trust
  fallback. The read-only transport interface is distinct from the write ACL.
  Install/activate/rotate/revoke/forward-only rollback, CAS, byte-idempotent
  command replay, expiry, and exact tenant/source/segment/classification/
  provider/model/region/retention/training bindings fail closed. Pipeline use
  reloads and verifies the active exact decision immediately before wire
  serialization; missing/outage/revoked/mismatched policy makes zero calls.
- Added `test_prompt_and_egress_authority.py` for SIA-T07 and SIA-T09 source
  preservation, nested secret removal, immutable copies, registration
  substitution rejection, lifecycle CAS/revocation, and capture transport
  zero-wire proof. Focused M3 tests passed `11 passed in 1.47s`; the complete
  semantic-ingestion unit selection passed `150 passed in 97.66s`; process
  safety integration passed `3 passed in 8.00s`; scoped Ruff, scoped Pyright
  (`0 errors, 0 warnings, 0 informations`), and `git diff --check` passed.
- Current next action: bind authenticated provider source governance to the
  egress binding at normal `ProviderIngestionCoordinator` composition, then
  finish the remaining M3 accepted-carrier/replay surfaces. This increment is
  locally verified, not M3 closure evidence.

### M3 authenticated egress handoff increment (2026-08-02)

- Extended the canonical authenticated ingress handoff with optional
  `AuthenticatedSemanticEgressGovernance`. It is produced only by the host
  resolver and carries classification/provider/model/region/retention/training
  settings; it intentionally excludes caller event metadata and source identity.
  Admission supplies the retained source ID/digest and coordinator derives the
  sole current single-segment ID from that digest.
- Normal `ProviderMemoryService`, factory, and coordinator composition now
  construct the complete egress binding from that authenticated tenant/governance
  plus admitted evidence, build the registered semantic prompt, and demand an
  exact current egress decision immediately before wire serialization. Missing
  governance, prompt, egress repository, or current decision remains
  evidence-only with zero transport calls.
- Verification: bootstrap admission + prompt/egress selection passed `45
  passed in 87.46s`; scoped Pyright remained clean. The remaining M3 current
  next action is accepted-carrier and replay implementation; no public event
  metadata is used as authority.

### M3 authorization, evidence, lifecycle, and recovery closure (2026-08-02)

- Re-pinned the M3 implementation boundary to the complete authenticated
  authorization read set: exact trust/temporal policy pair, optional exact
  egress decision/binding, and externally verified deployment authorization
  epoch/decision. The pipeline re-reads that set at stage start, after remote
  response, before independent analysis, and before sealing; the persistence
  owner rechecks it before planning and immediately before a committing group.
  Any mutation, revocation, expiry, verifier outage, or stale read is
  non-promoting and no stale accepted group is committed.
- Added host-authenticated source authority and source-interval evidence bound
  to the admitted source ID/digest, policy revision, provenance digest, and
  authority-evidence digest. Independent analyses must return those exact
  artifacts. Assertion, parser, attribution, identity, attachment, and textual
  temporal spans are range-checked against the admitted source; temporal
  attachment spans must exactly equal the canonical textual-evidence union.
- Replaced self-created runtime authorization with a host verifier port over
  externally supplied authorization bytes. Every use is bound to the verified
  bootstrap profile/release and server time; target substitution, byte-digest
  mismatch, expiry, signer lifecycle denial, revocation, verifier outage, and
  epoch mutation fail closed. Added the ordinary zero-egress production runtime
  constructor and deterministic local producer/analyzer. Its certified narrow
  grammar abstains outside supported input, emits two independent stable role
  interpretations, invents no identity, and carries only exact authenticated
  temporal/source evidence.
- Persisted content-addressed accepted-candidate and committed-terminal
  lifecycle transitions instead of projecting lifecycle from request digests or
  control state. Protected lookup now reads the actual typed lifecycle member
  after authorization and verifies it against the exact terminal artifact.
  Planned generations retain the full terminal artifact and authorization read
  set; exact retries compare all three artifacts.
- Added typed durable retry progress and full terminal checkpointing for policy,
  transport, planning, group, and finalization outages. Retry counts recover
  from generation evidence and remain bounded across sessions. Reconciliation
  reloads the exact terminal artifact and resumes only persistence/finalization,
  never proposer or analyzer work.
- Normal provider, Hermes, and filesystem roots exercise the same installed
  runtime path. M3 provider tests now own their fixtures instead of importing
  private helpers from other test modules. The PR workflow contains an explicit
  exact M3 unit, integration, and process-safety step. A final ordinary-root
  proof installs the production local runtime, admits the bootstrap-supported
  `Atlas owner is Bob.` form, performs no wire call, and commits the complete
  graph/event/group/observation effect set; the focused local-provider and
  pipeline selection passed `21 passed in 28.89s`.
- Local verification at this boundary: the complete M3 semantic unit,
  integration, and process-safety slice passed `225 passed in 153.04s`; the
  focused provider/pipeline/persistence set passed `24 passed in 25.16s` after
  removing cross-test imports; repository Ruff passed; configured repository
  Pyright reported `0 errors, 0 warnings, 0 informations`; and
  `git diff --check` passed. The public SIA acceptance plus generation-exactness
  gate passed `236 passed in 1327.74s`.
- Current next action: hand the complete M3 delta and exact evidence above to
  fresh independent spec, correctness, and test reviewers.

### M3 recovery and transaction-authority closure (2026-08-02)

- Wired the public `ProviderMemoryService.reconcile_memory_evolution` boundary
  to the provider coordinator. Before any policy, proposer, or analyzer call,
  selected M3 operations now persist one content-addressed, authenticated,
  secret-free execution retry plan. It retains the exact source bytes and
  identity, authenticated ingress/governance, prompt and policy coordinates,
  verified bootstrap and deployment coordinates, an opaque authorization
  secret reference, and the bounded attempt budget.
- Reconciliation reloads that plan after process restart and resumes policy,
  proposal, or independent-analysis outages without caller redelivery. Planned
  redelivery and reconciliation first recover the sealed terminal artifact and
  cannot invoke learned stages. Retry counts recover from durable generations;
  the fourth retry request persists `retry_exhausted` and later public reconcile
  calls do no work.
- Extended committed group requests with typed
  `AuthorizationReadSetPrecondition`. The memory-plane in-memory lock or JSONL
  process lock now executes the exact current-authority comparison inside the
  same conditional-write critical section, immediately before record
  preconditions and mutation. A deterministic rotation on that callback rejects
  the write while graph revision, group results, and graph/event members remain
  absent. The prior boolean precheck remains defense in depth, not the atomicity
  claim.
- Made the in-memory egress repository thread-safe and explicitly local/test
  scoped. Added a process-safe JSONL egress command repository with signed
  command replay, per-record digests, file locking, CAS mutation, atomic replace
  plus fsync, reopen validation, byte-idempotent command IDs, and fail-closed
  malformed/legacy input. Concurrent processes rotating from revision 1 prove
  exactly one success and one stale-CAS rejection.
- Added public JSONL service evidence for policy-read, proposal, and analysis
  outage restart; bounded exhaustion; and lost acknowledgements after execution
  plan checkpoint, terminal group, and finalization. Every recovered operation
  contains exactly one execution plan, group result, and source result. Removed
  remaining test-module fixture imports through a self-contained M3 support
  owner, and pinned the exact M3 workflow argv in the workflow-structure test.
  The public verified-runtime/coordinator/JSONL integration additionally pins
  independently stated wire, terminal, graph, event, and source-result byte
  digests and proves byte-identical reopen with no duplicate effects. Replaced
  scheduler sleep in the heartbeat evidence with a deterministic fake
  clock/barrier that asserts the durable lease remains live through the learned
  stage. The public coordinator additionally proves zero wire use for mutation
  of every tenant/source/segment/classification/provider/model/region/retention/
  training binding and for invalid signature, ineligible signer, expiry, and
  repository outage (`14 passed in 36.26s`).
- Exact current-revision evidence: the workflow-locked M3 unit, integration,
  and process-safety selection passed `251 passed in 266.67s`; focused public
  recovery/lost-ack coverage passed `7 passed in 58.31s`; static/prompt gates
  passed `148 passed, 1 skipped in 19.90s`; repository Ruff passed; configured
  Pyright reported `0 errors, 0 warnings, 0 informations`; and
  `git diff --check` passed. The public SIA acceptance plus generation-exactness
  gate passed `236 passed in 1362.06s`; the production dependency closure it
  exercised was unchanged by the subsequent deterministic test-only evidence
  additions.
- Current next action: hand this round-3 delta and the completed public
  acceptance/generation evidence to fresh independent spec, correctness, and
  test reviewers.

### M3 same-store authority and legal terminal closure (2026-08-02)

- Replaced the round-3 callback-only atomicity claim with a typed
  `SemanticAuthorizationAuthorityRecord` stored in the same memory plane as
  operation control, graph, event, observation, and result records. Initial
  activation and later rotation/revocation use record-digest CAS. Committing
  groups and policy-bearing noncommitting groups carry the expected authority
  record identity, revision, coordinates digest, and canonical record digest;
  the JSONL or in-memory conditional write validates that digest in the same
  transaction as effects. A deterministic rotation immediately before the
  group CAS rejects before any graph revision, group result, graph member, or
  event member is published.
- Corrected the protected lifecycle algebra to the canonical Section 3.23.0
  transitions. Accepted work persists
  `selected_pipeline_pending -> accepted_candidate` with the actual candidate
  digest and then `accepted_candidate -> committed_terminal` with the exact
  predecessor digest. Nonpromoting work persists `unsupported_input` or
  `abstained` and never emits `committed_terminal`; protected lookup validates
  the typed lifecycle against the terminal artifact and returns a normal
  nonpromoting outcome.
- Replaced control-only `retry_exhausted` publication with an ordinary
  evidence-only terminal containing `retry_budget_exhausted`, a noncommitting
  group/observation, terminal operation, source summary, source result, and
  abstained lifecycle. Reopen and later reconciliation observe the terminal
  source result and perform no learned replay.
- Moved deployment verification into durable preplanning behavior. A verifier
  outage retains and checkpoints a secret-free execution plan plus retry
  progress; a denied, revoked, expired, or malformed authorization closes as a
  legal evidence-only/abstained terminal with zero wire use rather than escaping
  as an uncaught exception. An activation-time verifier outage retains the
  structurally complete runtime solely so the first admitted operation can
  persist those recovery coordinates.
- Corrected the earlier round-3 evidence statement: the current workflow-locked
  exact M3 unit, integration, and process-safety argv passed `251 passed in
  261.50s` after the final byte-shape fix; generation closure passed `39 passed
  in 170.97s`; and public SIA
  acceptance passed `197 passed in 1168.87s`. The latter two commands together
  are the current `236`-test public acceptance/generation contract. These runs
  used the current dirty implementation revision and are deterministic local
  evidence, not live provider certification.
- The public frozen-artifact proof now pins the SHA-256 of the complete JSONL
  journal and the exhaustive decoded generation/member/kind/payload-digest map,
  then proves byte-identical reopen. That proof exposed unordered frozenset
  projection in the writer manifest; the persisted manifest now serializes
  governed kinds and store methods in canonical sorted order, and independent
  processes produce the same full-file SHA. The PR workflow now separately
  rejects any collection other than exactly 251 tests while retaining the
  statically pinned execution argv. Final repository Ruff, configured
  Pyright (`0 errors, 0 warnings, 0 informations`), and `git diff --check`
  passed.
- Current next action: hand this round-4 delta to fresh independent spec,
  correctness, and test reviewers.

### M3 authoritative authorization and current-time closure (2026-08-02)

- Replaced the operation-local authority mirror with
  `M3AuthorizationAuthorityRepository`, a source-scoped canonical authority
  backed by the same atomic memory-plane/JSONL store as M3 effects. Externally
  verified activate, rotate, and revoke commands enter through
  `VerifiedM3AuthorizationControlPlane` and update the record only through
  revision and record-digest CAS. Both accepted groups and policy-bearing
  noncommitting groups require the current same-store authority precondition;
  expiry, revocation, coordinate mismatch, or a concurrent replacement rejects
  before graph, event, observation, group-result, or terminal effects.
- Bound every durable `M3ExecutionRetryPlan` to the source-scoped authority
  scope, deterministic record ID, observed revision, optional coordinates
  digest, and a canonical authority-reference digest. This preserves the
  pre-activation revision-zero state without inventing authority coordinates
  and makes later recovery audit the exact authority identity expected when
  planning began.
- Changed remote egress verification to use a fresh server-current time before
  each wire request and immediately after each response or repair. Commit-time
  authority validation independently reads server-current time from the
  same-store repository. `arbitration_as_of` remains immutable decision/audit
  evidence and no longer authorizes transport after expiry. Fake-clock tests
  prove expiry before request is zero wire, expiry after response prevents a
  repair request, and expiry before commit produces zero persistent effects.
- Removed the M3 `retry_exhausted` transition and mutation entry point. The
  decoder now rejects a legacy control with that state using the explicit
  `legacy retry_exhausted control requires explicit terminal migration`
  diagnostic; current retry exhaustion remains an ordinary durable
  evidence-only terminal. Verification also covers a verified authority
  revocation against policy-bearing noncommit, lost-ack replay, malformed
  terminal JSONL rejection, a genuinely blocked learned analyzer with active
  heartbeat renewal, and forward-only egress rollback across reopen,
  idempotent command replay, and stale-command rejection.
- Re-pinned the complete public JSONL SHA-256 to
  `ae0260f16a5d1e51d460ea9bccea463814e3483f6e973a61aa06caf298f65aff`
  and the exhaustive member map for the new authority-bound plan/progress
  bytes. The workflow collection lock is now exactly `257 tests collected`.
  The exact M3 unit/integration/process selector, public acceptance and
  generation-exactness commands, focused reopen/rollback/migration/heartbeat
  proofs, repository Ruff, configured Pyright (`0 errors, 0 warnings, 0
  informations`), and `git diff --check` all passed at this dirty current
  revision. This is deterministic local evidence, not live provider
  certification.
- Current next action: hand this round-5 delta to fresh independent spec,
  correctness, and test reviewers.

### M3 stage-snapshot and recovery-authority closure (2026-08-02)

- Added one immutable `AuthorizationStageSnapshot` per authorization use point.
  Each snapshot captures one server-current timestamp, the exact policy,
  deployment, egress decision/binding, same-store authority record identity,
  revision, coordinates digest, and canonical record digest observed at that
  instant. The production provider performs no second clock or egress read for
  a stage. Proposal, response, analysis, sealing, and commit transitions compare
  exact snapshot authority coordinates; expiry, revocation, repository outage,
  or binding mutation is nonpromoting. The ordinary allowed remote path still
  performs exactly one wire request.
- Added a typed, content-addressed `M3RecoveryAuthorityBinding` to every
  recovered learned execution. Recovery loads the retry plan and same-store
  authority before policy, proposer, or analyzer work, then verifies the exact
  plan digest, authority record ID/revision/coordinates/record digest, and read
  set. Revision-zero recovery may activate the first verified authority, but it
  atomically checkpoints the resulting recovery binding with durable progress
  before any learned call. Existing revision-one recovery rejects rotation,
  revocation, coordinate-only mutation, expiry, and plan substitution with zero
  transport or assessor calls.
- Strengthened public evidence at the real service/JSONL boundary. Lost
  acknowledgements after terminal checkpoint, group commit, and finalization
  reopen with zero proposer and assessor calls and no duplicate effects.
  Writer-enabled accepting-assessor tests mutate every egress binding field,
  signature, signer eligibility, expiry, and repository availability and prove
  zero wire, graph, event, or accepted publication. The learned-stage renewal
  seam is injectable; its integration proof now uses a deterministic scheduler
  with exact heartbeat order and no sleep, timeout, or wall-clock race.
- Exact current-revision evidence: the focused provider/pipeline/persistence
  matrix passed `94 passed in 170.98s`; the warning-strict workflow-locked M3
  selector passed `260 passed in 280.05s`; generation exactness passed `39
  passed in 173.02s`; and public SIA acceptance passed `197 passed in 1160.61s`.
  The workflow collection lock is re-pinned to exactly `260 tests collected`.
  Repository Ruff passed, configured Pyright reported `0 errors, 0 warnings, 0
  informations`, workflow-structure tests passed `14 passed in 6.71s`, and
  `git diff --check` passed. These are deterministic local results from the
  current dirty implementation revision, not live-provider certification.
- Current next action: hand this round-6 delta and its exact immutable evidence
  to fresh independent spec, correctness, and test reviewers.

### M3 retry-plan fence and redelivery closure (2026-08-02)

- Bound every `M3ExecutionRetryPlan` to the exact admitted operation fence and
  source. The plan now carries the operation-fence binding digest, admitted
  source ID/digest, source-byte digest, and a domain-separated admitted-source
  binding digest. Model validation recomputes the source bytes and both
  canonical digests. Checkpoint and recovery compare the plan with the exact
  fence operation, authenticated principal, allocation/source binding, and
  source coordinates; coordinator recovery additionally reloads the admitted
  source record and compares its UTF-8 bytes before lease acquisition, policy
  reads, authority mutation, checkpoints, transport, or assessment.
- Changed identical redelivery to recover and validate the unique persisted
  plan before attempting to build one. A recovered plan is never reconstructed
  from current mutable deployment or authority state; it enters the same exact
  recovery-authority audit as process restart. Proposal outage followed by
  authority rotation and identical redelivery now returns retryable pending
  with one retained execution plan and zero new proposer or assessor calls.
  A deliberately foreign plan is rejected at the fence/source boundary before
  lease or learned work.
- Stage authorization now calls the closed `verify_current_egress` boundary
  once with the stage's single server-current time. It revalidates complete
  `ProviderEgressDecision` bytes so Pydantic `model_copy` cannot bypass the
  decision digest. `AuthorizationStageSnapshot` independently recomputes the
  decision digest over policy ID/revision/fingerprint/expiry and every tenant,
  source, segment, provider, model, region, retention, classification, and
  training binding coordinate. The normal public coordinator mutation matrix
  covers all binding fields plus stale policy ID, revision, fingerprint,
  decision digest, signature, signer, expiry, and repository outage.
- Re-pinned the complete frozen public JSONL journal SHA-256 to
  `d887e9f7bd0959a847755a4f132d975f573314e01a83b7eb2c611de716452f86`.
  Only the execution-plan payload digest and its checkpoint-progress digest
  changed; the independently pinned wire, terminal, graph, event, observation,
  and result bytes remained identical.
- Exact current-revision evidence: the new adversarial matrix passed `20 passed
  in 57.86s`; the complete affected provider/pipeline/persistence matrix passed
  `100 passed in 196.78s`; and the warning-strict workflow-locked M3 selector
  passed `266 passed in 312.63s`. The workflow collection lock is re-pinned to
  exactly `266 tests collected`. On the same final production/runtime bytes,
  generation exactness passed `39 passed in 171.53s` and public SIA acceptance
  passed `197 passed in 1155.60s`. Repository Ruff passed, configured Pyright
  reported `0 errors, 0 warnings, 0 informations`, workflow-structure tests
  passed `14 passed in 6.82s`, and `git diff --check` passed. These are
  deterministic local results from the current dirty implementation revision,
  not live-provider certification.
- Current next action: hand this bounded round-7 correction and exact evidence
  to fresh independent spec, correctness, and test reviewers.

## M3 Administrative Completion (2026-08-02)

This section is the authoritative current status for this implementation
WorkPlan. It supersedes every earlier chronological `Current next action`
statement above without deleting the evidence history.

M3 status: complete. The final round-7 `spec_auditor`,
`correctness_reviewer`, and `test_reviewer` closures are clean. The coordinator
accepted the three independent closures after reconciling them against the
final implementation, exact selectors, persisted-artifact identities, and
round-7 remediation evidence.

- `remaining_validated_p1_p2: []`
- `remaining_blocks_approval: []`
- `remaining_changes_required: []`

Exact local revision and tree state at closure:

- Git HEAD: `42671e90f35edfc006583e5ddf889927d2602717`.
- Tree state: dirty local working tree, no staged paths, 32 modified tracked
  paths, 19 untracked paths, and 41 total porcelain entries. The tracked binary
  patch SHA-256 is
  `d4cef536d10205511d5b9fa0bc3cc5c9bd58597a3170ac0c4981fcc85dbe3441`;
  the sorted modified/untracked content-manifest SHA-256 is
  `70f6ffdbc6f796efefd949b7db8f52ef0aecef8ba9e250815c8f9a25e3f779be`.
- Canonical design path
  `docs/design/semantic_ingestion_architecture.md` has SHA-256
  `45727e6870e2087823bfe6250c3c3319a3d540e45fb66c686267409b087b2c1c`.
- Registry `semantic-ingestion-traceability-registry-v1`, format
  `memorii.semantic-ingestion.traceability-source.v1`, grammar revision
  `sia-traceability-v1`, has file SHA-256
  `d38aa788adfb7703d970507f496b903ddf460797fe60274ddd5ebf9c22054c46`.
- CTV binding authority format `memorii-sia-ctv-binding-authority-v2` has file
  SHA-256
  `9f650d2f018e3863ad5f5512bf80dbdac1d22fa584cebe9f868c347a2f0143a4`,
  embedded source-design identity
  `79573a3dfb8e388097abfdf9d96257146f2b4f9defebb33dc718af923829eb40`,
  embedded source-registry identity
  `d38aa788adfb7703d970507f496b903ddf460797fe60274ddd5ebf9c22054c46`,
  and typed-value profile identity
  `9dc8b3d01e3f78ed6a11c7668cbb576b09f48ddf107c5efe441bb8bad234fd7f`.
- Frozen public M3 JSONL identity is
  `d887e9f7bd0959a847755a4f132d975f573314e01a83b7eb2c611de716452f86`.

Local CI parity and evidence are complete for the final dirty revision:

- warning-strict exact M3 unit/integration/process selector: `266 passed in
  312.63s`, with the workflow and structural test collection lock at exactly
  `266 tests collected`;
- complete affected provider/pipeline/persistence matrix: `100 passed in
  196.78s`, including the round-7 adversarial matrix at `20 passed in 57.86s`;
- warning-strict public SIA acceptance: `197 passed in 1155.60s`;
- warning-strict generation exactness: `39 passed in 171.53s`;
- workflow-structure verification: `14 passed in 6.82s`;
- repository Ruff passed, configured Pyright reported `0 errors, 0 warnings,
  0 informations`, and final `git diff --check` passed.

Limitations are explicit. This is deterministic local evidence from a dirty
working tree, not a commit or clean-tree certification. GitHub CI was not
executed, so local command parity is not a hosted-check result. M4 and M5 are
outside the authorized M3 scope; neither milestone has been designed,
implemented, reviewed, or started by this closure.

Outcome: M3 is implemented and locally verified through its complete approved
contract, including prompt/egress authority, candidate-to-terminal semantics,
temporal trust resolution, same-store authorization, atomic persistence,
restart/redelivery recovery, lifecycle publication, process safety, and
fail-closed mutation behavior. All final approval arrays are empty and no
known M3 P1/P2 or approval-required correction remains.

Retrospective: the decisive improvements came from replacing boolean or
operation-local authority checks with immutable stage snapshots and same-store
CAS records, binding retry plans to exact fence/source bytes, and proving
restart, redelivery, lost-ack, expiry, mutation, and concurrency behavior at
public service boundaries. Deterministic scheduling and frozen byte-level
artifacts removed timing and replay ambiguity. The remaining dirty-tree and
hosted-CI limitations are evidence-provenance constraints, not hidden product
claims.

Historical M3 next action: superseded by the user's explicit M4 authorization
and the M4 readiness blocker recorded at the top of this WorkPlan.

### Post-completion hosted-CI remediation (2026-08-02)

GitHub Actions run `30763550088`, job `91538240194`, exposed three failures in
deterministic Unit Test Shard 1 at committed revision
`7b5313a0d4953510258acec4818f4b595ce6278f`. M3 added the optional
`transaction_precondition` callback to the atomic memory-plane batch contract,
but five test-only `InMemoryMemoryPlaneStore` subclasses retained the previous
override signature. Three orchestration tests exercised the new keyword: one
reported the `TypeError` directly and two timed out because their worker
threads failed before reaching test barriers.

The bounded correction updates every stale test subclass to accept and forward
the callback unchanged. The complete orchestration and atomicity families pass
`27 passed in 2.92s`. Exact local parity for deterministic Unit Test Shard 1
passes `1025 passed, 1 skipped in 383.69s`; Ruff and `git diff --check` pass.
A direct ad hoc Pyright invocation over the complete orchestration test file
continues to report three pre-existing `_ManualHeartbeat` protocol mismatches,
none on changed lines and none introduced by this correction. The configured
repository Pyright result recorded at M3 closure remains the authoritative
static gate. GitHub CI must be rerun after this correction is published.

Historical post-M3 next action: superseded by the M4 readiness blocker recorded
at the top of this WorkPlan.

## M4 Core Conflict-Authority Production Slice (2026-08-04)

The bounded core production slice is implemented. Projection commits, temporal
and trust advances, policy cutovers, trust decay, ordinary terminal writes, and
accepted clarification writes now carry one mandatory typed
`SemanticConflictAuthorityCommitInput` through the shared projection-history
choke point. Server-derived immutable source/admission scope, resolver
authority validity, resolver-record and resolver-pointer CAS, conflict active
pointer CAS, immutable introductions/transitions, pointer history, and
new/changed/resolved/re-opened/no-op lifecycle handling are included in the
same semantic write. Temporal/trust projection and migration certificates bind
the conflict-authority input digest, including exact-retry validation.

Replay authority and checkpoints carry the v2
`SemanticConflictReplayBinding`; prospective checkpoint construction derives
the binding from the current store plus the pending same-CAS authority records.
Legacy v1 remains limited to the unique empty conflict history. The core model
also validates the exact fixed Hermes item rendering and the three-item page
budget without adding provider/factory/composite/Hermes composition to this
slice.

Local bounded evidence on the final production bytes:

- scoped `py_compile` and Ruff passed;
- projection-history plus projection-scheduler suites passed `25 passed in
  34.94s`;
- the two previously failing policy-migration checkpoint/catch-up nodes plus
  the event-replay suite passed `64 passed in 245.76s`.

The seven exact mapped M4 test nodes are deliberately not authored in this
production-writer slice; the coordinator assigned them to a separate sole test
writer. Host resolver composition is also outside this core-authority slice
and remains a subsequent bounded integration responsibility.

Current next action: exactly one test writer adds the seven mapped M4
authority/replay/terminal nodes against these stabilized production bytes and
runs their focused selector before independent review.
