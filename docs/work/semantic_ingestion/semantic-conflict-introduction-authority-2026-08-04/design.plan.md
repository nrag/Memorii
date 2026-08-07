# Semantic Conflict Introduction Authority Design

- Work ID: semantic_conflict_introduction_authority
- Work type: design
- Status: completed and independently approved
- Coordinator and sole canonical-design writer: Codex main thread
- Created: 2026-08-04
- Last updated: 2026-08-04
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related completed design: `docs/work/semantic_ingestion/conflict-attention-replay-design.plan.md`
- Canonical inputs: `docs/design/conflict_attention.md`; `docs/design/semantic_ingestion_architecture.md`; `docs/design/event_model.md`; user decision recorded 2026-08-04
- Expected output: implementation-ready amendments to the two canonical designs and this reviewable decision record

## Objective

Close the persisted-authority gap discovered during final M4 review. A
committed contested temporal or trust projection must create one durable,
authorized semantic-conflict introduction in the same memory-plane
conditional write. Provider and Hermes pulls must reconstruct the corresponding
question after success, lost acknowledgement, process restart, or conflict-
ledger loss without inventing scope, display content, or a winner.

The user approved the coordinator recommendation:

1. the memory-plane semantic transaction is the canonical introduction owner;
2. the file conflict ledger is a recoverable listing and clarification
   projection, never the canonical introduction owner;
3. temporal and trust contests for the same semantic slot and candidate set
   coalesce into one question whose revision binds both projection digests;
4. a host-owned resolver supplies authorized scopes and bounded safe display
   text from persisted provenance, and unavailable authority fails closed.

## Current Exact Next Action

Resume the parent implementation WorkPlan at the shared
`ProjectionCommitRequest` and same-store semantic-conflict authority boundary.

## Problem And Impact

Production M4 can commit a projection with `outcome="contested"`, and the
Provider/Hermes surfaces can display and resolve an attention item already in
the conflict repository. No production path joins those two behaviors. A real
semantic disagreement therefore remains invisible to the user even though its
contested projection is durable.

A best-effort append to the separate conflict JSONL is unsafe. Appending after
the semantic transaction can lose the question on crash; appending first can
show a question for a transaction that never committed. The canonical
introduction and contested projection must share one atomic owner.

## Requirements Ledger

| ID | Requirement | Source | Acceptance | Status |
| --- | --- | --- | --- | --- |
| SCI-R01 | Persist one strict canonical semantic-conflict introduction atomically with every newly committed user-decidable contest | User decision; `conflict_attention.md` sections 5.1-5.2; SIA-R10/R18 | No committed contest lacks its introduction and no introduction exists without its committed projection generation | specified |
| SCI-R02 | Derive identity, revision, candidates, provenance, policy, and predecessor only from frozen committed inputs | Conflict-attention design; Memorii invariants | Retry, restart, genesis, and checkpoint-tail reconstruction reproduce byte-identical introduction bytes | specified |
| SCI-R03 | Coalesce temporal and trust contests only for the same semantic slot and exact candidate set | User decision | Matching contests yield one question binding both projection digests; differing slots or candidate sets never merge | specified |
| SCI-R04 | Resolve scopes and safe display through host-owned authenticated authority | User decision; `conflict_attention.md` sections 5.1 and 7 | Missing, stale, revoked, cross-tenant, unsafe, or incomplete authority fails closed before disclosure | specified |
| SCI-R05 | Make the conflict ledger a recoverable materialized projection of canonical introductions | User decision | Loss, truncation before a complete projection boundary, lost acknowledgement, and restart rebuild without omission, duplication, or reinterpretation | specified |
| SCI-R06 | Preserve clarification idempotency and revision binding across rematerialization | `conflict_attention.md` sections 5.2-5.3 | Existing exact clarifications remain valid for the same introduction revision; stale or changed candidate sets reject | specified |
| SCI-R07 | Preserve legacy provider behavior and explicit attention enablement | `conflict_attention.md` section 8 | Legacy methods remain unchanged; attention-aware methods expose only authorized reconstructed items | specified |
| SCI-R08 | Make rollout, rollback, observability, migration, and resource bounds explicit | Implementation rules | Old stores remain readable, activation is gated, rollback never deletes canonical introductions, and logs exclude candidate text | specified |

Requirement IDs are traceability values only. They may not name persisted
records, Python symbols, files, tests, fixtures, commands, workflow jobs, or
protocol discriminators.

## Scope And Non-Goals

Included: canonical introduction schema and codec; deterministic derivation;
coalescing; atomic publication; host scope/display resolution; conflict-ledger
materialization and rebuild; clarification binding; restart, retry, replay,
migration, rollout, rollback, compatibility, authorization, observability, and
resource limits.

Excluded: automatically choosing a semantic winner; changing equal-version
storage-corruption behavior; adding callbacks to Hermes; treating model output
as user confirmation; redesigning unrelated projection, graph, or provider
contracts.

## Decision Alternatives

| Alternative | Consequence | Decision |
| --- | --- | --- |
| Same-store canonical introduction plus recoverable listing projection | Reuses the semantic conditional write and provides deterministic crash/restart recovery | approved |
| Recoverable cross-file transaction journal | Adds a second transaction substrate and recovery protocol across memory-plane and conflict files | rejected by user in favor of same-store authority |
| Best-effort or retrying post-commit append | Can orphan a committed conflict or expose inconsistent state | prohibited |
| Read-time inference from contested projections only | Cannot safely invent host authorization scope or display text and weakens immutable revision binding | prohibited as canonical behavior |

## Initial Authority And Evidence Boundaries

- `SemanticIngestionAtomicStore` owns the canonical transaction boundary.
- Projection-history records are committed evidence inputs, not attention
  records and not authorization authority.
- The new introduction is committed state, distinct from later clarification
  proposals and conflict-ledger listing snapshots.
- `FileConflictAttentionRepository` may materialize, index, paginate, and retain
  clarification transitions, but it cannot originate or reinterpret the
  canonical introduction.
- The authenticated host resolver is authoritative for tenant/scope and safe
  bounded display projection. Model output and internal IDs are insufficient.
- Local tests establish deterministic behavior. Hosted CI and operational host
  configuration remain separate evidence classes.

## Reconciled Design Decisions

Parallel transaction, provenance, composition, and test maps were reconciled
against the production call paths and governing designs. The canonical design
draft now fixes these previously hidden choices:

- the complete semantic-conflict ledger is memory-plane authoritative:
  introductions, projection-driven successors, current pointers,
  clarification proposals and receipts, work/attempt history, and retained
  listing snapshots all use one same-store repository; a file ledger is an
  optional rebuildable cache and remains separately usable for integrity
  incidents;
- semantic-conflict records follow projection-history precedent as typed
  same-transaction authority records rather than adding a producer-supplied
  `AtomicGenerationMember`; ordinary and clarification semantic publication
  paths both prepare them before their one conditional write;
- the conflict ID is stable over tenant, semantic slot, valid-time partition,
  and exact basis tuple. Scope belongs in the revision. Matching temporal and
  trust candidate sets coalesce; differing sets remain separate; combined and
  split forms explicitly resolve and introduce their respective identities;
- every contested candidate is joined to its own governed source/admission
  index. The disclosure scope is the canonical union of all contender required
  scopes in one tenant, never the newest source scope or a caller filter;
- an active host display resolver supplies bounded safe question/option bytes
  and an immutable same-store authority record and pointer. The semantic CAS
  preconditions both, so rotation, revocation, or expiry cannot race a prepared
  commit. The store validates candidate equality, provenance, scope union,
  authority freshness, render budget, and limits. Missing or unsafe authority
  blocks the semantic transaction instead of committing a hidden contest;
- every committed group carries a canonical per-contest resolution tuple and
  pointer preconditions. The store derives zero, one, or many post-write
  contests and requires an exact bijection; it rejects missing, duplicate,
  extra, or swapped resolutions before publication;
- candidate-set coalescing sorts unique candidate ID/digest pairs and is
  independent of projection tuple order; display ordering remains a separate
  frozen host-authority choice;
- protocol version 1 rejects an unrepresentable candidate set outside 2..16;
  it never truncates, votes, or silently partitions one semantic contest;
- projection changes and user clarification contend on the same current-
  conflict pointer CAS. This closes the stale-revision race that would remain
  if clarification state were authoritative in a separate file. Claimed work
  that loses to a natural projection successor becomes a typed `superseded`
  terminal result with no semantic effect or processing receipt;
- canonical conflict history has its own replay prefix/current-pointer
  bindings in a v2 replay aggregate and signed v2 checkpoint. A v1 checkpoint
  maps only to the unique empty conflict authority. Existing stores receive no
  implicit backfill; activation is forward-only and rollback retains bytes;
- compatibility is explicit: a new reader opens a pre-feature empty-authority
  store and legacy Provider/Hermes bytes stay unchanged. After the first v1
  conflict record, old-binary rollback is unsupported; supported rollback uses
  the v1-capable reader with reads and conflict-producing writes disabled;
- integrity incidents remain in their independently recoverable control-plane
  repository. One composite provider repository freezes both semantic and
  integrity child watermarks into a single retained membership/cursor so the
  public list never exposes two inconsistent pagination domains.

The machine-readable proof map is
`verification-map-v1.json`. Its ownership is nonduplicative: derivation and replay live in the
existing event/projection owners; atomic crash/restart evidence uses the exact
terminal-persistence owner; repository state-machine tests remain in the
conflict repository owner; one provider/Hermes vertical integration proves
authorized pull and clarification after restart; factory tests prove default
filesystem composition. Exact collection pins and timing inventories change
only for owners that gain nodes.

## Validation And Attack Matrix Skeleton

- same-store commit success, precondition failure, crash before/after durable
  write, lost acknowledgement, exact retry, divergent retry, and two-writer
  contention;
- temporal-only, trust-only, matching coalesced, mismatched candidates,
  mismatched slots, predecessor revision, resolved successor, and reopened
  contest;
- missing/partial/stale/revoked/cross-tenant scope authority and unsafe or
  oversized display values, all with zero disclosure;
- file-ledger loss, partial tail, duplicate materialization, stale revision,
  rematerialization after clarification, restart, and concurrent listing;
- genesis and signed checkpoint-tail reconstruction with byte-identical
  introduction and listing output;
- legacy provider methods, attention-disabled composition, filesystem default
  composition, Hermes rendering, cursor snapshots, and clarification retry;
- field-aware identity hygiene and measured test ownership in the current CI
topology.

## Review Ledger

Round 1 ran on 2026-08-04 with independent specification, correctness, and
test reviewers. Every finding was inspected against the named production path.

| Finding | Classification | Coordinator disposition | Remediation |
| --- | --- | --- | --- |
| Per-contest authority was prose-only and absent from the committed request | P2 / changes_required / architecture | confirmed | Added strict contest key, resolution, pointer-precondition, commit-input schemas and exact zero/one/many bijection |
| Resolver revocation could race semantic CAS | P2 / changes_required / security | confirmed | Added same-store host-owned authority record/pointer, expiry rule, writer separation, and exact CAS preconditions |
| Conflict replay/checkpoint closure was prose-only | Not applicable / blocks_approval / architecture | confirmed | Added closed replay binding, v2 aggregate/checkpoint membership, ordering, genesis, tail validation, and failure code |
| Same set with different projection order would fail coalescing | P2 / changes_required / runtime behavior | confirmed | Candidate-set identity now sorts unique ID/digest pairs; display order is separate |
| Claimed clarification versus natural projection change was not total | P2 / changes_required / runtime behavior | confirmed | Added complete race table, atomic semantic terminal transaction, and typed superseded result |
| Legal field maxima could exceed Hermes page capacity | P2 / changes_required / compatibility | confirmed | Added 8 KiB renderer-bound budget and worst-case three-item precommit validation |
| Persistence compatibility and rollback target were ambiguous | Not applicable / blocks_approval / compatibility | confirmed | Defined v1 authority envelope, empty-store read compatibility, no implicit migration, and unsupported old-binary/new-record rollback |
| Proof owners, counts, timings, and exclusion were not machine-readable | Not applicable / changes_required / verification | confirmed | Added `verification-map-v1.json` with exact nodes, jobs, timing owners, budgets, and duplicate exclusions |
| Existing file-ledger concurrency tests are scheduler-sensitive | P3 / follow_up / determinism | accepted limitation | Canonical race proof uses explicit CAS barriers; cache lock tests remain non-authoritative |
| Design-bound artifact hashes became stale | Not applicable / changes_required / governance | confirmed | Pending regeneration after canonical prose convergence |
| Composite pagination lacked child-qualified identity and a total cursor order | P2 / changes_required / integration | confirmed | Added strict composite member, child binding, snapshot, v2 cursor, ordinal, collision, authorization-before-read, and resolution-routing contracts |
| Migration cutover and scheduled trust decay could publish contests outside ordinary ingestion | P2 / changes_required / architecture | confirmed | Added conflict-authority input to both cutovers and scheduled reprojection, with the same projection/conflict CAS and clarification race |
| Factory composition and rollback/version proof owners were absent | P2 and Not applicable / changes_required / verification | confirmed | Added exact factory, compatibility, rollback/re-enable, cutover/decay nodes and reconciled planned selector counts/timing policy |
| Generic projection preparation/publication could bypass conflict authority | P2 / changes_required / transactional consistency | confirmed | Made conflict authority mandatory on `ProjectionCommitRequest`, bound it in both certificates, and required prepare/direct publish to validate and write the unified closure |
| Requirement sources used unresolved `CAR-Rxx` shorthand | Not applicable / changes_required / governance | confirmed | Replaced every shorthand with the exact canonical `conflict_attention.md` section authority before implementation |

No P1 finding was reported. The final delta review ran after bound-artifact
validation on the frozen revision below. The specification auditor, correctness
reviewer, and test reviewer independently reported no remaining validated
P1/P2, `blocks_approval`, or `changes_required` finding. The coordinator
inspected and accepted those clean results; the design is approved for
implementation.

## Frozen Remediation Revision And Evidence

The delta-review baseline is frozen by these exact bytes:

- `docs/design/conflict_attention.md` SHA-256
  `0b5a8a9246fb3d0d2cf18d0589d3b412778f0caa167bac331c3ae9a7b7ec1a68`;
- `docs/design/semantic_ingestion_architecture.md` SHA-256
  `7391e4f0ee09888ad6ea15d074b6fc349477c6a661a56c41d174e32cde4a5e80`;
- equal-version decision digest
  `b95828ee2021b8a0dabb1373733833a4e78b6f0e7dd3fdc0fd6080714a8166c3`;
- CTV authority SHA-256
  `29dc9aa8faa36387f5a18918f6feb4b39c02cdb4abcd02d9ed35cf8d1d690254`;
- CGS structural vector SHA-256
  `4588f9b50240aca5f07c6fb63bea17cb74aca4e7c397fe6fc7f3699f31d4986f`.

Final remediation validation on 2026-08-04 passed the equal-version artifact validator, exact
CTV authority checker, lifecycle-root signer-provenance checker (6 accepted,
41 rejected, 2 replicas), CGS structural-contract self-test, JSON proof-map
parse, `git diff --check`, and 279 focused CTV/compiler mutation tests. The
independently compiled CTV graph remained exactly 56 schemas and differed from
the prior authority only in the bound source-design digest. The final
cutover/composite delta regenerated all hashes above and the exact validators,
proof-map JSON parse, and `git diff --check` passed on those bytes.
The final mutation run completed with `279 passed` in 329.33 seconds on the
same frozen bytes.

Collection baselines are now selector-specific: semantic generation 34 -> 36,
terminal persistence 156 -> 159, projection history 84 -> 86, provider
compatibility 14 -> 15, and duration-balanced unit shards 3,035 -> 3,040. The
historical 266/271 monolithic runs in the parent plan are retained evidence for
older revisions, not current selector pins. Dedicated jobs use their explicit
15-minute workflow budget and must record measured wall time/headroom; unit and
terminal nodes update their existing timing inventories.

## Changed-Surface And Authority-Chain Ledger

| Surface | Class | Owner | Authority chain | Required evidence | Status |
| --- | --- | --- | --- | --- | --- |
| `docs/design/conflict_attention.md` | normative design | conflict-attention owner | user decision -> persisted introduction/listing/clarification contracts | clean final three-role review; exact validation; diff check | approved |
| `docs/design/semantic_ingestion_architecture.md` | normative design | semantic transaction owner | contested projection -> canonical introduction -> atomic publication/replay | clean final three-role review; bound artifact audit | approved |
| `docs/design/equal_version_replay_decision-v1.json` and validator | bound design artifact | replay-decision owner | canonical design bytes -> artifact hashes -> validator/tests/workflow | exact validator; mutation tests | regenerated and validated |
| CTV/CGS binding artifacts and gate pins | generated design authority | traceability owner | canonical design bytes -> independent compiler -> content-addressed gates | exact checkers; 279 mutation tests | regenerated and validated |
| `verification-map-v1.json` | verification design | test-architecture owner | requirement -> exact node -> one required job/timing owner | JSON parse; clean final test review | approved |
| implementation WorkPlan | governance | coordinator | design approval -> implementation resume | direct inspection | ready to resume |
| this WorkPlan | governance | coordinator | user decision -> design evidence -> review closure | direct inspection; diff check | completed |

## Delegation And Cost Ledger

| Task | Role/tier | Access | Output | Status |
| --- | --- | --- | --- | --- |
| Map transaction, codec, and replay ownership | code mapper / Spark-class | read-only | exact symbols and compatibility constraints | completed and reconciled |
| Reconstruct scope/display provenance and host seams | explorer / Spark-class | read-only | closed authority inputs and failure cases | completed and reconciled |
| Inventory tests, timing owners, and attack families | explorer / Spark-class | read-only | validation matrix and CI impact | completed and reconciled |
| Draft canonical design amendments | coordinator | sole writer | coherent frozen contract | remediated after round 1 |
| Whole-design review | spec, correctness, test reviewers / Terra-class | read-only | classified findings | final delta clean; approved |

## Completion Contract

This design operation completes only when the canonical designs specify every
persisted field, derivation preimage, owner, transaction step, replay and
rebuild rule, authorization/display boundary, compatibility behavior, limit,
and verification owner; affected bound artifacts and hashes are current; and
fresh specification, correctness, and test review reports no remaining
validated P1/P2, `blocks_approval`, or `changes_required` finding.
