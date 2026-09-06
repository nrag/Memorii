# Semantic Ingestion Implementation Index

- Work ID: semantic_ingestion
- Work type: implementation
- Status: active
- Coordinator: Codex main thread
- Created: 2026-07-27
- Last updated: 2026-09-05
- Parent WorkPlan: None
- Related WorkPlans: `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/design.plan.md`; `docs/work/semantic_ingestion/conflict-authority-proof-failures-2026-08-04/debug.plan.md`; `docs/work/semantic_ingestion/testing.plan.md`; `docs/work/semantic_ingestion/terminal-persistence-performance-2026-08-09/testing.plan.md`; `docs/work/semantic_ingestion/scenario-v1-runtime-closure-2026-08-09/design.plan.md`; milestone-linked design, testing, and debugging plans
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md`; `docs/design/event_model.md`; `docs/design/conflict_attention.md`; `docs/design/equal_version_replay_decision-v1.json`
- Expected outputs: production implementation, deterministic verification, current-state documentation, and immutable reports under `docs/reviews/semantic_ingestion/`
- Current resume packet: `docs/work/semantic_ingestion/resume.md`
- Preserved historical WorkPlan: `docs/work/semantic_ingestion/history/implementation-through-2026-08-04.md`
- Migration manifest: `docs/work/semantic_ingestion/history/implementation-split-manifest.json`
- Current completion operation: `docs/work/semantic_ingestion/m4-closure-2026-09-04/implementation.plan.md`
- Current coordination candidate identity: the immutable Git commit produced by
  the coordinated M3.1/M4 freeze; the historical dirty-tree identity is not a
  final-candidate authority

## Objective

Implement every determinate semantic-ingestion requirement through canonical
production paths while keeping external activation fail closed until its
authority exists. Preserve exact replay, provenance, transaction, lifecycle,
authorization, compatibility, and evidence boundaries.

## Completion Contract

Complete only when every SIA-R01 through SIA-R23 obligation is verified or
explicitly excluded by the approved design; every milestone completion
contract is satisfied; active external gates remain honestly unavailable; the
complete changed surface passes its deterministic and hosted gates; and fresh
whole-branch specification, correctness, and test reviews leave no remaining
validated P1/P2, `blocks_approval`, or `changes_required` finding.

## Scope

Included: the determinate behavior, migrations, production composition,
verification, and current-state documentation defined by the frozen semantic-
ingestion design.

Excluded: retrieval interpretation/ranking/answer generation, invention of
externally owned topology or policy values, live certification without exact
revision-bound evidence, and unrelated redesign.

Deferred: only externally activated behavior whose required signed authority
does not yet exist. Its prescribed validators and fail-closed preapproval path
remain in scope.

## Constraints And Invariants

All root `AGENTS.md` invariants apply. In particular, preserve candidate versus
committed state, structural versus belief overlays, typed closed schemas,
single-writer transaction ownership, immutable history, independent evidence,
provider-envelope compatibility, and fail-closed unknown or unauthorized
state.

## Identity And Coordinate Hygiene

Milestone names are planning coordinates and may appear only in planning and
typed traceability evidence. Production, test, fixture, command, workflow, and
persisted identities remain behavioral or genuine protocol/migration names.

## Change Impact And Verification Closure

The active linked debugging WorkPlan is the sole detailed owner of its
in-flight changed-surface, authority-chain, gate, experiment, known-failure,
and evidence ledgers. M4 records only the debugging boundary, link, status,
completion dependency, and compact summary. This index owns only
cross-milestone dependencies, status, and final whole-branch closure. No
milestone may infer completion from another milestone's narrower evidence.

## Sources Of Truth

Use the precedence in root `AGENTS.md`. The approved design baseline is
`docs/design/semantic_ingestion_architecture.md`; the current conflict and
replay contracts additionally bind `docs/design/conflict_attention.md`,
`docs/design/event_model.md`, and the frozen replay decision artifact.

The preserved historical WorkPlan is the authority for all pre-split
decisions, evidence, review dispositions, hashes, and chronological records.
The index and milestone packets own current navigation and status.

## Current State

- Layer1: bounded independent compiler and hermetic gate complete.
- M0: historical proof/compatibility foundation remains mixed; completed
  compatibility and traceability slices are preserved, while the rejected C2
  authority is not approved for consumption.
- M1: complete.
- M2: complete.
- M3: graph-dependent production behavior is implemented and its reopened
  local four-root/two-backend matrix is green. Immutable shared-candidate,
  hosted, and independent-review closure remains.
- M4: active. The two confirmed P2 replan defects are corrected locally. After
  correcting the only stale bound-document hash from the first run, the full
  415-case family passes under warnings-as-errors. The coordinated
  completion operation is
  `docs/work/semantic_ingestion/m4-closure-2026-09-04/implementation.plan.md`
  (linked debug correction, composition reconciliation, replay/history,
  shared M3.1 regression, then one dual closure revision).
- M5: pending.

The earlier M3.1 empty final approval arrays are historical evidence, not a
current closure claim; both milestone arrays must be regenerated at the shared
final candidate.

The reviewed pre-plan tree was clean at
`821b0bc7fd47ca0c55a18ccebb4b1628fa13689b`. The WorkPlan edits make the tree
intentionally dirty until the next candidate is built. Earlier v81/v82 records
remain historical evidence only and cannot be reused for final closure.

## Assumptions And Open Questions

No new product-semantic assumption was introduced by the WorkPlan split. The
active debugging operation reports no external decision blocker. External
activation artifacts remain governed by their registered SIA-ED gates.

## Milestone Index

| Milestone | Requirements | Status | Detailed packet | Dependency |
| --- | --- | --- | --- | --- |
| Layer1 | SIA-R03, L1-008, L1-009 | complete | `docs/work/semantic_ingestion/milestones/layer1-independent-authority.plan.md` | frozen design and registry |
| M0 | SIA-R03, SIA-R13, SIA-R22 | blocked | `docs/work/semantic_ingestion/milestones/m0-proof-compatibility.plan.md` | Layer1 and external trust authority |
| M1 | SIA-R01, SIA-R04, SIA-R08, SIA-R12, SIA-R19, SIA-R22, SIA-R23 | complete | `docs/work/semantic_ingestion/milestones/m1-source-admission.plan.md` | M0 compatibility foundation |
| M2 | SIA-R10, SIA-R11, SIA-R20, SIA-R21 | complete | `docs/work/semantic_ingestion/milestones/m2-writer-atomicity.plan.md` | M1 admitted source |
| M3 | SIA-R02, SIA-R04 through SIA-R07, SIA-R09, SIA-R12 | active | `docs/work/semantic_ingestion/milestones/m3-semantic-pipeline.plan.md` | implementation retained; coordinated evidence closure after M4 corrections |
| M4 | SIA-R10, SIA-R18 | active | `docs/work/semantic_ingestion/milestones/m4-event-history.plan.md` | linked debug correction, replay/history, then dual closure |
| M5 | SIA-R03, SIA-R08, SIA-R13 through SIA-R17, SIA-R19 | pending | `docs/work/semantic_ingestion/milestones/m5-deployment-acceptance.plan.md` | M4 and external activation authority |

## Requirement Coverage Ledger

Detailed implementation and evidence rows live in the milestone packets. The
preserved historical ledger remains available under the archive heading
`Requirement Coverage Ledger`. Overlapping requirements mean a later milestone
adds integration or operational maturity; it does not invalidate earlier
bounded completion.

## Progress Log

- 2026-08-04: Preserved the complete 7,052-line pre-split WorkPlan byte-for-byte
  and replaced its canonical path with this index.
- 2026-08-04: Created one detailed packet per existing milestone without
  changing product scope, status, or evidence claims.
- 2026-08-04: M4 product work remained paused during the migration.
- 2026-08-04: Confirmed split-governance findings: linked cross-type ledger
  ownership, resume command/state detail, and executable split fidelity proof
  were incomplete. Remediation assigns linked debug as detailed owner and adds
  the manifest-driven verifier; final approval remains pending.
- 2026-08-05: Reopened M3 after a design-to-production audit proved approved
  source dependency groups, transaction group plans, append-only plan lineage,
  and exact attempt/plan/authorization result binding were absent from both
  production and the closure matrix.
- 2026-08-08: Removed the unsafe follow-up that fabricated all missing lineage
  inputs in the legacy pipeline. The terminal summary schema and its
  established persistence closure were restored unchanged.
- 2026-08-09: The coordinator implementation audit confirmed that the remaining
  M3 contract is a complete Step 5--8 graph-dependent vertical, not a missing
  repository hook. The existing atomic plan repository is present, but the
  accepted provider path has no sealed `SourceProposalAlignment`, graph snapshot
  bundle/read-set extensions, graph-dependent reconciliation and closure,
  planning-artifact repository, pure group compiler, or graph CAS owner. The
  legacy terminal pipeline may not synthesize these values. This conclusion is
  directly required by the approved coordinator sequence at
  `docs/design/semantic_ingestion_architecture.md` lines 17680--17725 and its
  loadable artifact/authorization rules at lines 17145--17210.

## Evidence Log

The executable split verifier and its manifest record archive metrics,
artifact hashes, requirement allocation, canonical-reference corpus, and active
obligation ownership. Fidelity requires the archived file to retain SHA-256
`eace351ffa26f42b707328e8a0a0a38206c8ba62d8f2603b90853116054a4a20`.
Run `.agents/scripts/verify_workplan_split.py` normally and with `--self-test`
after changing any indexed artifact, then refresh the manifest and its pin.

## Decision Log

All 14 pre-split decisions remain verbatim under the archive heading `Decision
Log`. No decision was amended by this migration. New decisions belong in the
active milestone packet and are summarized here only when they affect another
milestone.

- 2026-08-05: Classify missing source/group plan lineage as an M3
  implementation and evidence-scope gap, not a design gap. Preserve historical
  closure bytes, explicitly reopen M3, and require fresh evidence before
  restoring complete status. The user selected the complete approved contract.

## Review Log

All pre-split review rounds and dispositions remain verbatim under the archive
heading `Review Log` and the chronological milestone-specific sections. New
reviews write to the active milestone packet. Only cross-milestone or final
branch review results are summarized here.

- 2026-08-04: Three governance findings were confirmed and remediated by the
  indexed-plan ownership clarification, resume expansion, and executable
  fidelity verifier. This is not a final implementation or branch approval.

## Blockers And Limits

There is no remaining known local product-semantic blocker for M3.1/M4. Full closure
still requires an immutable committed candidate, exact-SHA hosted execution,
and final independent specification, correctness, and test review. M5
activation claims remain limited by externally owned authority. M0's rejected historical C2 baselines must not be consumed.

## Next Action

Freeze and push the bounded production-entrypoint ledger and JSONL physical-CAS
harness correction, require hosted checks to execute its exact SHA, and run the
whole-candidate reviews. Do not begin M5 or unrelated work during this closure.

## 2026-08-10 Bootstrap V3 Atomic Slice

The bounded atomic-schema writer added the strict scalar
`BootstrapAnalysisProvenanceV1`, a V3 atomic checkpoint decoder carrying the
immutable recovery key and live claim, and a V3 handoff marker minted by the
canonical bootstrap writer. The deterministic claim adapter now has one
consume-and-found linearization method, so a lost acknowledgement cannot leave
a consumed claim without a discoverable result. Focused repository and normal
vector tests passed (6 tests), as did scoped Ruff and Python compilation.

This is partial evidence only: the atomic store now persists unclaimed,
claimed, and Found recovery state and atomically renews or consumes an exact
claim; graph-free staging selects the V3 checkpoint
only when its caller supplies the complete V3 authority, and the durable CAS
now writes the keyed Found index with that generation but does not yet own the
claim lease state used by the coordinator. The actual public coordinator,
V3 memory/JSONL restart, and normal-root proof therefore remain pending. The
one next action remains the active linked design/implementation coordination
above.

### 2026-08-10 V3 self-contained carrier partial

The bounded contract slice now adds the strict V3 payload-limit policy and
source authority, closed proposal transport/attempt/normalized-operation
algebra (including all five operation discriminators), and a source-wide
self-contained proposal payload with exact attempt closure. These codecs are
registered and round-trip through the canonical semantic envelope. The V3
proposal run now retains that payload rather than relying on proposal payload
digests for external read-back; normalization request/manifest/result retain
the matching limit authority digests. Focused payload/route tests (`7 passed`),
Ruff, compilation, and diff checks pass.

This remains partial: V3-native lane payloads, the complete graph-free V3
algebra, atomic member decoder/reload migration, and memory/JSONL reopen proof
are not implemented by this bounded contract slice. It does not establish a
production-entrypoint binding or normal-root activation.

### 2026-08-10 V3 retained-byte decoder progress

The atomic persistence slice now registers the V3 retained member kinds and
decodes the persisted provenance, payload-limit authority, proposal payload,
ordered four-lane receipts, graph-free bundle, and source alignment directly
from the committed generation. Bootstrap Found recovery invokes this decoder
before returning a generation, so malformed, reordered, missing, or
type-swapped retained bytes cannot be rehydrated through a generic/V2 path.
Focused repository mutation tests, Python compilation, and scoped Ruff pass.

This is still partial. A direct complete V3 fixture must be constructed through
the atomic store for memory and independent JSONL lost-ack/reopen evidence; the
legacy stage is deliberately not used for that proof. No production-entrypoint
binding changes in this slice.

The follow-on contract delta introduces typed discriminated Stanza, spaCy,
predicate-event, and temporal lane payload carriers; source/segment-bound lane
results; V3 subject, dependency, interpretation, and alignment closure
carriers; and an atomic request closure that requires one proposal payload and
the exact four lanes per provenance. These contracts are registered and locally
validated, but the exhaustive native observation/consensus/identity/coverage
subtree and atomic-store memory/JSONL reload decoder are still pending.

### 2026-08-10 V3 configured-host fixture progress

The test fixture now constructs an immutable `PreparedSource` with the real
`BootstrapDeclaredSegmentLanguageRoute` shape, then issues the matching
`BootstrapAnalysisRouteBindingSet`, flattened provenance, complete V3 proposal
request, payload-limit authority, and the exact Stanza/spaCy/predicate/temporal
request factories. Focused fixture proof passes (`2 passed`), with scoped Ruff,
Python compilation, and diff checks clean. This proves only transient
authority/request closure; it does not yet publish through a configured host,
reload a V3 result, or bind a production caller. The stale V2 normal vector
still invokes removed `_recovery_request`/`normalize_after_bootstrap_handoff`
methods and must be replaced by this V3 fixture before normal-root evidence can
be claimed.

### 2026-08-10 V3 live-publication generation blocker

The configured host now injects a narrow atomic-store lease lookup into the
test authority issuer. The lookup joins the exact operation fence, current
operation/artifact generation, writer binding, and live lease; it rejects a
fabricated, stale, or foreign lease before authority issuance. This preserves
the CAS lease check rather than weakening it.

Direct public-root execution exposed a sequencing contradiction: the bootstrap
handoff marker and recovery claim are minted for generation `1`, while the live
preplanning control is generation `2` when the coordinator reaches authority
construction. The live lookup therefore correctly rejects the marker-derived
generation. Substituting generation `2` only in publication authority is also
invalid because the claimed recovery record remains generation `1` and the
owner requires those values to agree. The generation advances between handoff
minting and authority build. No override or compatibility fallback is valid;
the linked design correction must define one canonical marker/probe/claim
generation sequencing rule before V3 publication, reload, or JSONL evidence can
continue.

## Outcome And Retrospective

### 2026-08-11 V3 recovery schedule evidence (partial)

Focused JSONL-backed recovery proof now exercises one live claimant denying a
second probe, stale renewal and marker rejection, exact dual-clock expiry
reclaim against the unchanged ready snapshot, a pre-publication claimed-only
state with no Found record, and consumed-claim renewal rejection after Found.
The local recovery selector is still partial: memory contention, independent
process scheduling, and the complete canonical 20-node inventory remain
unimplemented. The selector manifest is deliberately not generated until every
specified node exists.

### 2026-08-10 V3 generation-causality store slice (partial)

The recovery contracts now use a strict V3 predecessor-authenticated probe,
store-owned normalization-ready control snapshot, snapshot-derived claim, and
generation-three found shape. Bootstrap handoff writes only the V3 predecessor
record. The atomic probe performs the generation-one-to-two control advance,
mints its lease and snapshot with the claim in the same compare-and-swap, and
the publication write records the consumed claim/snapshot and generation-three
found state. Focused repository and direct-provider regression checks pass.
This is partial implementation evidence only: the dedicated memory/JSONL race,
reclaim, restart, and exhaustive old-wire rejection suite remains to be added,
and the retired in-memory adapter must be removed rather than used as a V3
serialization path.

### 2026-08-10 V3 Found retry evidence

The writer-admission gate now decodes and compares the complete V3
normalization-ready snapshot, renewal claim, and Found consume closure rather
than accepting their record shapes. The direct public-root test publishes once,
then repeats the same operation and proves the Found branch performs zero new
proposal, Stanza, spaCy, predicate, or temporal calls. This establishes
same-process lost-ack recovery only; independent JSONL reopen, contention, and
expiry/reclaim remain pending.

Operation remains active. The plan split reduced routine context while retaining
all historical bytes and giving each milestone one explicit completion owner.

## Migration Crosswalk

| Preserved source section | Current owner |
| --- | --- |
| Header through M4 readiness/review material (historical lines 1-1499) | M4 packet plus archive |
| Objective through migration/rollout (historical lines 1500-1972) | this index; detailed historical text remains in archive |
| Milestones Or Experiments (historical lines 1973-2169) | seven milestone packets |
| Verification, progress, evidence, decisions, and reviews (historical lines 2170-6365) | archive; new evidence goes to active milestone |
| M0 current-pin closure (historical lines 6366-6561) | M0 and Layer1 packets plus archive |
| M3 closure and hosted-CI remediation (historical lines 6562-7015) | M3 packet plus archive |
| M4 core production slice (historical lines 7016-7052) | M4 packet plus archive |
