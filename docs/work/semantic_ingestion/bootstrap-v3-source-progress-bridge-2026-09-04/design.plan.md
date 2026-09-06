# Bootstrap-V3 Source Progress Persistence Bridge

- Work ID: bootstrap_v3_source_progress_persistence_bridge_2026_09_04
- Work type: design
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-09-04
- Last updated: 2026-09-04
- Parent implementation WorkPlan: `docs/work/semantic_ingestion/m4-closure-2026-09-04/implementation.plan.md`
- Related debugging WorkPlan: `docs/work/semantic_ingestion/conflict-authority-proof-failures-2026-08-04/debug.plan.md`
- Canonical design: `docs/design/semantic_ingestion_architecture.md`
- Baseline revision: `821b0bc7fd47ca0c55a18ccebb4b1628fa13689b`

## Objective

Define the smallest canonical persisted bridge that lets the live Bootstrap-V3
graph coordinator publish the three post-preplanning lifecycle states that
correspond to typed `SourceIngestionProgress` in its existing atomic
generations, prove exact equivalence to the V3 plan/attempt/lineage closure,
and recover without rebuilding authority.

## Completion Contract

The design operation is complete only when one frozen architecture candidate
defines the native V3 member grammar, atomic closure and acyclic digests,
initial/replan transitions, exact reload/recovery/concurrency, compatibility
and rollback, bounded production-entrypoint binding, and complete attack matrix;
the maintained requirements/evidence ledger maps each requirement to proof;
and independent specification, correctness, and test reviewers have been
reconciled under the repository finding-classification contract. It does not
claim any implementation, CI, or operational evidence.

## Constraints And Invariants

- Governing sources are `docs/design/memorii_spec.md`,
  `docs/design/memorii_storage_details.md`, `docs/design/event_model.md`,
  `docs/IMPLEMENTATION_RULES.md`, and this canonical architecture; the user
  authorized only this persistence bridge.
- Bootstrap V3 remains the sole transaction/checkpoint/idempotency/CAS owner;
  generic source progress describes lifecycle semantics but is not a V3 wire
  wrapper or alternate persistence owner.
- Replan preserves the original delivery and operation fence, final/reused V3
  bytes, and all sealed non-graph work; it may compile only the exact stale
  unfinished subset.
- Unknown or mismatched bytes fail closed before lineage, graph CAS, or result
  disclosure. No new provider API, replay/history closure, composition work,
  M3.1, M5, or unrelated Bootstrap revision belongs to this operation.

## Requirements

- B3SP-01: `BootstrapGraphPlanAtomicWriteRequestV3` remains the single owner of
  Bootstrap-V3 plan, attempt, and lineage generations.
- B3SP-02: its plan, attempt, and authorized-lineage generations carry exactly
  one typed progress member with discriminator `plan_published`,
  `attempt_published`, and `planned`, respectively.
- B3SP-03: the progress image binds the exact V3 plan, attempt, lineage,
  successor-authority, policy, counter, fence, lease, replay-bundle, and
  predecessor/final-result closure by typed references and digests at the first
  state where each exists. It may name an execution manifest only in `planned`
  and only when already sealed in that same generation; no parallel reconstructed
  authority is introduced.
- B3SP-04: the atomic store validates equivalence before visibility and reloads
  the exact committed progress bytes after lost acknowledgement, restart, or
  concurrent retry.
- B3SP-05: the external clarification-winner trigger resumes the original
  fence and may compile only the exact replanned unfinished group subset.
- B3SP-06: unknown, missing, duplicate, reordered, cross-generation, or
  substituted bridge members fail closed before lineage, CAS, or disclosure.

These IDs are planning metadata only and may not enter product symbols,
persisted values, fixtures, test names, commands, or workflow identities.

## Scope

Included: the normative typed bridge schema, canonical owner, atomic member
mapping, digest/equivalence rules, lifecycle transitions, recovery/concurrency,
compatibility/rollback, and the implementation/test binding plan.

Excluded: conflict-attention composition, general replay/history closure,
M3.1 closure, M5, provider API redesign, a second repository, delivery-derived
fallbacks, and unrelated Bootstrap-V3 changes.

## Alternatives

1. Extend the existing Bootstrap-V3 atomic generations with one typed progress
   member. Preferred because V3 remains the single owner and existing artifacts
   retain their bytes.
2. Wrap every Bootstrap-V3 artifact in generic source-checkpoint generations.
   Rejected unless feasibility disproves option 1 because it creates parallel
   generation ownership and a larger migration surface.
3. Derive progress only during recovery. Rejected because it violates exact
   found-first recovery and can reconstruct authority from ambient state.

## Contract And Authority Boundary

The design must specify, without hidden implementation choice:

- the precise typed reference from progress to each V3 plan, attempt, lineage,
  authority arm, final result, policy, counters, manifest, and replay bundle;
- exact member cardinality and ordering for initial plan, attempt, planned,
  replan plan, replan attempt, and replacement-lineage generations;
- digest preimages and the acyclic construction order;
- equivalence validation between progress references and retained V3 bytes;
- the only legal predecessor/successor states and original-fence joins;
- found-first recovery, concurrent same-request behavior, retry exhaustion,
  migration of existing generations, rollback, and fail-closed absence.

## Verification And Attack Matrix

- Initial and replan sequences persist exactly one matching progress member.
- Multi-group partial commit preserves final and unaffected V3 artifacts
  byte-for-byte and replaces only the declared stale subset.
- Missing, extra, duplicate, reordered, wrong-kind, wrong-digest, wrong-fence,
  wrong-lease, wrong-policy, wrong-counter, wrong-manifest, wrong-bundle,
  predecessor, partition, authority-arm, plan, attempt, and lineage mutations
  reject before visibility.
- Lost acknowledgement before/after each generation returns exact bytes.
- Concurrent identical publication has one linearization; conflicting
  publication rejects.
- Memory and independent JSONL reopen reconstruct identical authority.
- Existing pre-bridge durable generations have an explicit compatibility and
  recovery disposition; no silent upgrade or reconstruction is allowed.
- Field-aware identity hygiene rejects this WorkPlan's coordinates from every
  product and persisted identity.

## Requirement-To-Evidence Ledger

| Requirement | Behavioral selector / owner | Required proof and gate | Evidence maturity |
| --- | --- | --- | --- |
| B3SP-01 | `BootstrapGraphPlanAtomicWriteRequestV3`; V3 atomic store | one-write-owner and no-generic-wrapper architecture/test inspection | specified |
| B3SP-02 | `BootstrapGraphSourceProgressV3`; V3 assembler | three current-generation member closure vectors and strict codec round trips | specified |
| B3SP-03 | `BootstrapGraphAtomicMemberReferenceV3`, replan closure, counters | per-variant fields, reference/digest/timing mutations and exact byte preservation | specified |
| B3SP-04 | V3 store reload and idempotency boundary | memory/JSONL reopen, lost-ack, identical race, conflicting CAS, reclaimed lease | specified |
| B3SP-05 | V3 group-CAS related-conflict successor; original-fence closure reload | non-test `sync_event` production-root trace, subset-only recompile, one successor per conflicted group | specified |
| B3SP-06 | native member decoder and atomic validator | unknown/missing/duplicate/reordered/cross-generation/substitution family and process gate | specified |

The planned field-aware identity-hygiene checker adds the spelling family
`B3SP` (case, separator, and prefixed variants) to every product/persisted
identity surface while allowing it only in explicit WorkPlan traceability
fields. This requirement label is not a proposed code, test, fixture, command,
or wire identity.

## Production Entrypoint Bindings

This `production_entrypoint_bindings` ledger is the sole location for B3SP
traceability. The canonical binding map uses behavioral identities only and is
the implementation-facing owner.

| Runtime behavior | Non-test caller and composition root | Canonical owners/authority | Durable result / fail-closed absence | Required proof |
| --- | --- | --- | --- | --- |
| Related-conflict replan | `ProviderMemoryService.sync_event` through `ProviderIngestionCoordinator.ingest` | ordinary admitted V3 ingestion; group-CAS conflict branch, original request/fence/scopes/epoch, and exact closure reload | atomic V3 successor; absence/mismatch is noncommitting and cannot re-admit/re-render | production-root integration trace proves same fence and one admission |
| Progress publication/reload | Bootstrap V3 coordinator via assembler/repository/store | native plan/attempt/lineage write request plus current lease/writer/epoch | exact member bytes or typed CAS/recovery failure | memory and JSONL reopen plus transaction-boundary process gate |

The canonical production-entrypoint binding owner is
`docs/design/semantic_ingestion_canonical_evidence/production-entrypoint-bindings-v1.json`.
Its bridge record maps the production chain:
`ProviderMemoryService.sync_event` (`service.py:619`) ->
`ProviderIngestionCoordinator.ingest` (`ingestion.py:268`) ->
`_ingest_semantic_source` (`ingestion.py:358`) -> `_run_semantic_ingestion`
(`ingestion.py:1087`) -> `build_builtin_bootstrap_graph_execution_v3`
(`bootstrap_graph_builtin.py:431`) -> coordinator construction (`:421`) -> V3
plan repository/store. The continuation is the coordinator's real group-CAS
conflict branch followed by `_related_conflict_successor` and exact
`reload_resume_closure_for_original_fence`. It carries the original admitted
request, complete fence, principal binding, scopes, epoch, lease, and writer;
it validates then reloads/writes one typed successor. The required proof uses
the real group-CAS conflict, not a monkeypatched persistence method; unavailable
or invalid closure must produce typed noncommit with no replacement. The canonical map's
mapper preflight is identity
`bootstrap_graph_source_progress_binding_preflight_2026_09_04`, date
2026-09-04, baseline `821b0bc7fd47ca0c55a18ccebb4b1628fa13689b`.

## Test And Gate Allocation

| Behavioral selector | Direct owner | Required scenarios | Gate / receipt / timing owner |
| --- | --- | --- | --- |
| `test_bootstrap_graph_source_progress_contracts.py` | generic unit shards | strict member-reference grammar; variant cardinality/order; counter digest, timing, policy join, monotonicity; all field and discriminator mutations | unit-test shards; `unit-test-durations.json` new node entries |
| `test_bootstrap_graph_source_progress_store.py` | generic unit shards | native validation before visibility; exact reload; duplicate/conflicting write; pre-bridge refusal; rollback preservation; lost acknowledgement and reclaimed lease | unit-test shards; `unit-test-durations.json` new node entries |
| transaction-boundary source-progress rows | dedicated transaction-boundary shards | real V3 group-CAS conflict; exact closure reload and native three-generation successor sequence; no normalized event/admission/full-pipeline call | memory and independent-JSONL receipts; `unit-test-durations.json` new node entries |
| `bootstrap-graph-transaction-boundary.json` | transaction-boundary selector | add `source_progress_initial`, `source_progress_related_conflict`, `source_progress_lost_ack`, and `source_progress_reclaimed_lease` scenario rows for direct, factory, filesystem, and Hermes roots, each in memory and JSONL independent-process backends | `bootstrap-graph-transaction-boundary`, per-cell receipts, aggregate receipt union |

Each new transaction-boundary row asserts the native three-generation member
sequence, exact retained-member bytes, one original delivery/admission, expected
CAS/effect counts, typed non-disclosure where applicable, and the native
progress/reload digest. The JSONL process rows independently reopen persisted
members. The `bootstrap-graph-transaction-boundary` workflow owns shard
execution; `bootstrap-graph-transaction-boundary-aggregate` owns exact receipt
union/budget validation; `deterministic-job-owners.json` owns job timeout and
budget; `unit-test-durations.json` owns individual timing inventory. No test,
selector, fixture, command, or CI job name contains a WorkPlan requirement ID.

## Review Findings And Disposition

| Finding | Classification | Coordinator disposition | Remediation |
| --- | --- | --- | --- |
| `plan_published` named successor authority and manifest before either was available | P1 / changes_required / lifecycle | confirmed | Rebuilt the state grammar: plan contains only plan/replay/counters; authority begins in attempt and manifest only when already sealed in planned. |
| Snapshot digest was used as observed counters and no native counter artifact existed | P1 / changes_required / integrity | confirmed | Added `BootstrapGraphObservedCountersV3`, strict construction timing, monotonic counts, policy join, and a dedicated member/reference. |
| Reference prose did not specify strict fields or legal V3 member grammar | P2 / changes_required / persisted grammar | confirmed | Added exact reference fields and legal repository/member/kind/payload/generation table. |
| Existing generic checkpoint implementation purportedly formed part of this design diff | Not applicable / changes_required / governance | unsupported against `git diff`; implementation conformance action accepted | Explicitly excluded generic schema changes and require reverting the generic checkpoint before bridge implementation. |
| Generic policy/counter extension paragraph contradicted the native-only bridge | P1 / changes_required / persisted-schema compatibility | confirmed | Superseded that paragraph: generic schemas/digest domains remain unchanged and generic code delta must be reverted. |
| Production binding and test allocation lacked current callsite/count/gate specificity | P2 / changes_required / verification | confirmed | Added the canonical binding-map record, exact root chain/counts, and named unit/transaction-boundary/receipt/timing allocations. |
| Canonical binding-map record retained WorkPlan coordinates | Not applicable / changes_required / identity governance | confirmed | Removed B3SP traceability from canonical evidence; it remains only in this WorkPlan. |

This is the single coherent design-remediation round for the confirmed findings.
No production code or tests were changed.

## Evidence Maturity

The bridge contract remains `specified`; its revised staged grammar is
derivable after the post-remediation feasibility check. Current code exposes
plan fields and replay authority before authorization, authority/attempt only
after authorization, and lineage only after attempt. It does not expose a
native counters artifact, replay-bundle member, or manifest at plan time; these
are explicit minimal extensions rather than inferred fields. The bridge is not
implemented, locally verified, independently reproduced, CI enforced, or
operationally verified. The final targeted delta reviews approved the frozen
design; implementation evidence is owned by the linked implementation WorkPlan.

## Design Delta

Architecture Section 4.8.3.4 now selects the existing Bootstrap V3 atomic
generation as the only persisted owner. It adds these behavioral identities:

| Identity | Class | Owner | Purpose |
| --- | --- | --- | --- |
| `BootstrapGraphSourceProgressV3` | behavioral schema | `contracts.py` | V3-native three-state lifecycle projection. |
| `BootstrapGraphReplayBundleV3` | behavioral schema | `contracts.py` | Typed normalization replay closure available before plan publication. |
| `BootstrapGraphObservedCountersV3` | behavioral schema | `contracts.py` | Native per-generation measured counters; never a snapshot alias. |
| `BootstrapGraphAtomicMemberReferenceV3` | behavioral schema | `contracts.py` | Strict typed reference to one decoded native member. |
| `bootstrap_graph_source_progress` | protocol member kind | V3 atomic-member codec registry | Strict encoded native progress payload. |
| `replay-bundle` | behavioral member identifier | V3 atomic assembler | The sealed replay closure member per progress generation. |
| `observed-counters` | behavioral member identifier | V3 atomic assembler | The current-generation counters member. |
| `source-progress` | behavioral member identifier | V3 atomic assembler | The one lifecycle-progress member per progress generation. |
| `_related_conflict_successor` | behavioral entry point | Bootstrap V3 coordinator | Original-fence successor after the real V3 group-CAS conflict. |
| `reload_resume_closure_for_original_fence` | behavioral repository port | Bootstrap V3 repository/store | Found-first exact closure reload with original-fence authority. |

All B3SP requirement labels remain WorkPlan-only planning metadata and do not
enter any product identity above. Existing V3 schema version `3` is a protocol
version, not a planning coordinate.

## Authority And Implementation Binding

The runtime binding is fixed, not optional:

`ProviderMemoryService.sync_event` -> `ProviderIngestionCoordinator.ingest` ->
`BootstrapGraphDependentCoordinatorV3._execute_attempt` group-CAS conflict ->
`BootstrapGraphDependentCoordinatorV3._related_conflict_successor` ->
`AtomicStoreBootstrapGraphPlanRepositoryV3.reload_resume_closure_for_original_fence` ->
`AtomicStoreBootstrapGraphPlanRepositoryV3` /
`checkpoint_bootstrap_graph_transaction_v3`.

The same original admitted request, `OperationFenceBinding`, delivery-principal
binding, required outcome scopes, and current control epoch traverse this
chain. It does not construct a new provider event, source admission, delivery
identity, generic `SourceIngestionProgress`, or repository. The store must
return the exact decoded V3 `source-progress` member used by the coordinator.
Any absence or mismatch is typed, noncommitting, and fail-closed.

## Feasibility Evidence

| Question | Evidence | Result |
| --- | --- | --- |
| Is there one V3 atomic owner? | `BootstrapGraphPlanAtomicWriteRequestV3` and `checkpoint_bootstrap_graph_transaction_v3` | Yes; preserve it. |
| Can each generation obtain native plan/attempt/lineage authority before publication? | `build_plan_checkpoint`, `build_attempt_checkpoint`, `build_authorized_lineage_checkpoint`; V3 model-field inspection | Yes. |
| Are policy/fence/lease/writer/epoch values available at their owning boundaries? | V3 plan/attempt fields and enclosing request/control epoch | Yes. |
| Is a real observed-counters artifact available? | Attempt construction and assembler inspection | No; current code aliases `graph_snapshot_digest`, so add native measured counters. |
| Are replay bundle and execution manifest references available in every generation? | Current assembler ordering | Replay bundle must be added before plan; manifest is not available until after lineage and is optional only there. |
| Can recovery be found-first without a wrapper? | Existing write-digest idempotency and exact V3 reload | Yes; add bridge validation to that path. |
| Can the trigger be narrow and production-reachable? | Existing V3 group-CAS conflict and production service/coordinator composition | Yes; retain its atomic successor binding. |

Command evidence: a bounded `PYTHONPATH=memorii .venv/bin/python -c ...` field
check exited 0 for the actual plan/attempt/lineage source/request/normalization/
policy/fence/lease/writer/epoch joins. The coordinator ordering is proven by
`build_plan_checkpoint` -> authorization -> `build_attempt_checkpoint` ->
`build_authorized_lineage_checkpoint`. That same inspection confirmed the
existing snapshot-digest counter alias, so counters are a required native
artifact rather than an available input. A final static preflight also found
zero production callers for the two proposed bridge symbols, as required for
their `specified_not_implemented` status. No code or test was changed by this
design operation. Field-aware governance proof ran `rg -n 'B3SP'` across the
repository excluding this WorkPlan and returned no matches; the only remaining
matches are the explicit requirement and hygiene fields in this WorkPlan. The
architecture SHA is unchanged by this governance-only correction.

## Required Implementation And Verification

- Extend only the V3 contracts/codec registry, V3 assembler, V3 repository
  port, V3 atomic store, V3 coordinator, and the existing provider handoff.
- Revert the current generic contract/store/replay checkpoint delta before those
  native changes; generic schemas and digest domains remain unchanged.
- Validate the complete atomic-member equivalence grammar before persistence and
  after every reload; do not delegate to generic source-progress storage.
- Add focused memory and JSONL reopen tests for initial, partial replan, lost
  acknowledgement, identical/concurrent requests, conflicting requests,
  reclaimed lease, pre-bridge generations, rollback, retry exhaustion, exact
  byte preservation, native counter timing/monotonicity, and every
  member/reference mutation family in the architecture matrix.
- Add a transaction-boundary JSONL/process gate proving the persisted sequence
  and no visibility of partial member closures.
- Add production-root transaction evidence that `sync_event` reaches the real
  group-CAS related-conflict successor with the original fence and no new admission.

## Rejected Alternative

The generic-wrapper alternative was evaluated and rejected. It would create
parallel current-generation, idempotency, and CAS authority and require
translation of V3 authority into a second persisted grammar. It cannot prove
byte equivalence of retained V3 artifacts at found-first recovery. Recovery
derivation is separately rejected because no persisted boundary proves whether
missing progress is an acknowledgement loss or missing authority.

## Decisions And Blockers

- User authorized the targeted bridge and everything needed to implement it on
  2026-09-04.
- Bootstrap-V3 is the selected canonical persistence owner; the generic wrapper
  and derived recovery alternatives are rejected.
- No external blocker is known. The feasibility check found two determinate,
  minimal contract extensions and no need to duplicate or translate authority.

## Delegation Ledger

| Task | Role | Access | Status |
| --- | --- | --- | --- |
| Contract draft and feasibility | sole design writer | canonical design and this WorkPlan | complete |
| Frozen design review | spec, correctness, test reviewers | read-only | complete; no remaining findings |

## Final Review Closure

- Specification review: approved the frozen native-only bridge after the
  staged-availability and identity-governance corrections.
- Correctness review: approved the exact atomic-member grammar, acyclic digest
  closure, found-first recovery, compatibility, and rollback behavior.
- Test review: approved the named unit, mutation, JSONL/process, production-root,
  receipt, and timing-owner allocation after governance remediation.
- `remaining_validated_p1_p2: []`
- `remaining_blocks_approval: []`
- `remaining_changes_required: []`

## Frozen Review Candidate

- Canonical design path: `docs/design/semantic_ingestion_architecture.md`
- Canonical design SHA-256:
  `f7937f2871e07ca36cf58710d8ae6288f4f49f7f238ba468be5a49c4487e04f0`
- Frozen section: `4.8.3.4 Bootstrap V3 source-progress bridge`
- Candidate scope: the bounded bridge section plus this design WorkPlan and
  compact resume routing; pre-existing production/test edits are implementation
  evidence only and are not part of design approval.
- Freeze rule: any canonical-design edit invalidates this identity and requires
  a new SHA-256 before delta or full review.
- Canonical binding-map SHA-256: `ff8d73644df3ab53b5d52d31475a339569a018ca9d329832454e9c36acbc0c4f`.

## Exact Next Action

Execute slice 1 of
`docs/work/semantic_ingestion/bootstrap-v3-source-progress-bridge-2026-09-04/implementation.plan.md`:
revert only the superseded generic checkpoint delta, then implement the native
V3 progress/reference/replay/counter contracts and assembler member closures.
