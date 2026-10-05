# Semantic Forgetting Implementation

- Work ID: semantic-forgetting-implementation
- Work type: implementation
- Delivery fidelity: Level 2 (early real-world testing) — real forget
  journeys across happy scenarios and common operational failures;
  persistence, retry, recovery, authorization, and universal invariants
  preserved; adversarial tamper matrices and old-binary (non-proxy)
  evidence recorded as Level 3 deferrals.
- Status: active
- Coordinator: main Codex thread
- Created: 2026-10-03
- Last updated: 2026-10-03
- Parent WorkPlan: docs/work/semantic-forgetting-design/design.plan.md
  (complete; produced the design)
- Related WorkPlans: docs/work/durable-memory-implementation/ (the release
  arc this extends)
- Canonical inputs:
  - docs/design/semantic_forgetting.md — the approved design baseline
    (commit 4780db61; requirements FGT-R1..R17)
  - docs/design/durable_execution_and_solver_runtime.md (amended forget
    section)
  - docs/design/event_model.md (7.3, 14.1)
- Expected outputs: production implementation of FGT-R1..R17 through the
  canonical paths named in design §6.10; the §10 verification families;
  regenerated typed-value publication + repinned release candidate; CI
  green; updated current-state documentation.

## Objective

Implement revocation-based semantic forgetting end to end: the
`revocation_directive` record kind in the append-only semantic log with
its full schema authority chain; the governance-owned enforcement
publication; the revoked-identity view gating every serving path; the
tombstone reader-edit ledger; the upgraded forget plan/apply control plane
with dependency closure, typed journal v2, pending-epoch riding
publications, and boot/mode-resume reconciliation; solver
`revalidation_required` marking; the owner-forensic lineage surface; and
the cross-path parity and crash-cut test families — with the release
candidate repinned and CI green.

## Design Baseline

- Canonical design: docs/design/semantic_forgetting.md at 4780db61
  (requirements FGT-R1..R17; §6.10 authority chain; §10 verification)
- In-scope: all of FGT-R1..R17
- Approved deviations: none
- Unresolved design questions: none (design §13 records two bounded
  implementation-judgment items: suppression_id hash construction; status
  counts owner-visible — default yes)

## Completion Contract

Every requirement FGT-R1..R17 has production implementation evidence
through the canonical entry points (nonzero production callers, exact
composition-root callsites), deterministic verification evidence per
design §10, the typed-value publication regenerated via the authoring
script and the release candidate repinned, all required local jobs pass,
CI green on the pushed head, identity-hygiene gate green with mutation
proof, no validated P1/P2 remains, and the closure record per
`.agents/PLANS.md` is complete. First-release readiness (the follow-on
arc) is out of scope for this WorkPlan beyond leaving the branch green.

## Scope

Included: design §6.1-§6.10 contracts, §6.7 view, §6.8 matrix rows, §10
families, authority-chain regeneration, candidate repin, CI registration.

Excluded: physical selective erasure, backup rewriting, cross-installation
propagation, model/host-initiated forget, retention semantics changes,
performance budgets, adversarial matrices beyond fail-closed decode,
old-binary non-proxy evidence (Level 3 deferrals per design §9).

## Constraints And Invariants

- Frozen pydantic contracts: extra="forbid", strict, closed Literals;
  unknown values fail closed everywhere.
- Append-only history; fold stays kind-agnostic create|update; no record
  removal; persisted==genesis replay equality must keep holding.
- Tier A epoch equality must never break (pending-increment contract).
- Publication regeneration ONLY via
  memorii/scripts/generate_observation_registry_publication.py; never
  hand-edit signed manifests; candidate repin LAST.
- Flock self-deadlock rule: code called inside an open transaction takes
  connection= and reuses the caller's connection.
- manual_write_transaction requires explicit handle.commit().
- Owner's uncommitted files (hermes doc, benchmark docs) never committed.
- Identity hygiene: behavioral names only; requirement IDs stay ledger
  values; mutation proof for new surfaces.
- Time-bomb rule: authorization dates issued at datetime.now(UTC).

## Identity And Coordinate Hygiene

Inherited from the design WorkPlan ledger; new behavioral identities this
implementation introduces (all behavioral/protocol class): record kind
`revocation_directive`; models `RevocationDirectiveRecord`,
`EntityRevocationTarget`, `ClaimRevocationTarget`, `SourceRevocationTarget`,
`RecordRevocationTarget`; `SuppressionRecord` (journal v2 envelope);
control field `pending_epoch_increments`; lifecycle members `revoked`
(ClaimLifecycleState, EntityLinkLifecycleState); event schema version
`memorii.semantic-memory-event.v1` extended additively (owner resolution
2026-10-04, no v2 mint); view component
`RevokedIdentityView`; governance entry `commit_forget_enforcement`;
marking reason `revoked_evidence`; forensic surface
`forensic_lineage_audit`. Mutation coverage added for each new surface in
M6. Ledger updated at each milestone.

## Change Impact And Verification Closure

Changed-surface, authority-chain, and gate ledgers live in the active
milestone packet; the index tracks cross-milestone state. The publication
authority chain (decoder-source-manifest → publication-manifest → role
artifacts → registry.json → candidate.json) is reconciled in M1 and
re-checked at every later milestone that touches a pinned file.

## Production Entrypoint Bindings

Ledger initialized by the code-mapper preflight artifact
(docs/work/semantic-forgetting-implementation/preflight-bindings.md);
updated per milestone with callsite/authority/proof. Zero-caller owners
are not implemented.

## Sources Of Truth

Design (4780db61) governs; AGENTS.md precedence otherwise; production code
citations in design §4.

## Current State

(2026-10-03) Operation started at 4780db61 (clean except owner's protected
files). Design review history and evidence: see parent WorkPlan.

## Assumptions And Open Questions

Verified facts: environment (memorii/.venv Python 3.14.7), CI jobs
durable-storage-integration / durable-runtime-integration run explicit
pytest file lists; unit additions need tests/ci/unit-shards.json
registration. Working assumptions: none beyond design-recorded judgment
items. Unresolved questions: none. External decisions: none.

## Milestones

| Milestone | Requirements | Bounded scope | Status |
| --- | --- | --- | --- |
| record-kind-schema-chain | FGT-R1, FGT-R12 | record kind + model + per-kind tables + codec/reference manifests + envelope v2/upcaster + publication regen + repin + focused tests | pending |
| governance-entry-view | FGT-R7, FGT-R2 (view core) | governance delta entry (native-group-commit pattern) + RevokedIdentityView + injection roots + fail-closed composition | pending |
| tombstones-reader-ledger | FGT-R3, FGT-R13 | lifecycle members + tombstone rewrites in the enforcement publication + every §6.3 reader edit | pending |
| control-plane-forget | FGT-R5, FGT-R6, FGT-R8, FGT-R9, FGT-R14 | typed selectors + closure + plan_digest + journal v2 + barrier/pending-epoch + one-transaction finalize + reconciliation + doctor/status | pending |
| serving-completion | FGT-R2 (matrix), FGT-R4, FGT-R15, FGT-R16 | every §6.8 row live + justification marking + forensic surface + no-un-forget property | pending |
| parity-crash-ci | FGT-R10, FGT-R11, FGT-R17 | parity family + crash-cut family + CI registration + identity-hygiene mutations + docs | pending |

Milestone packets under milestones/ as each opens. Milestone names are
organizational only and must not appear in outputs.

## Progress Log

- 2026-10-03: Operation opened at 4780db61. Next action: code-mapper
  preflight, then open the record-kind-schema-chain packet.
- 2026-10-03: CORE DESIGN IMPLEMENTED END TO END across five pushed
  commits: (1) f9de4478 grammar — `revocation_directive` record kind,
  target union, per-kind tables, codec/reference manifests, all-kinds
  fold fixture; (2) cc580edb reader ledger — revoked lifecycle enum
  members, retrieval allowlist gates, projection map, structured-fact
  all-versions + scoped-context link gates, content-free tombstone
  builders; (3) 652387c1 control plane — typed selector plans with
  content-free closure, journal v2 (stable suppression identity,
  v1-legacy reader, unknown fail-closed), journal-first barrier-gated
  apply, pending_epoch_increments + one-transaction finalize +
  boot completion (DUR-09 closed), drain call on barrier-release/boot
  (CORRECTED 2026-10-04: the drain is structurally inert — the
  enforcement emitter is never wired; see review findings),
  doctor/status/CLI; (4) c06de831 serving gates — RevokedIdentityView
  (protocol-typed) accepted at retrieval/scoped-context/structured-facts/
  entity-match/factory/sidecar (CORRECTED 2026-10-04: no production
  composition root performs the injection; only the managed-partition
  factory and harness sidecar do — see review findings); harness + resume
  justification marking;
  (5) 11b4ad8b governance entry — store method appending the directive
  delta through the full canonical commit (batch/replay state/reference
  ledger genesis-bootstrap/projection/checkpoint/aggregate) with
  tombstones + directive index record under one admission-governed CAS;
  end-to-end journey test green (directive materializes in replay,
  tombstones content-free, drain quiescent, epoch consumed atomically,
  Tier A green). Per-milestone packets under milestones/. Remaining:
  registry v2 mint (M1b), parity/crash families + CI registration (M6),
  forensic lineage surface + prefetch canonical filter, publication
  regeneration + candidate repin, broad gates + milestone review.
  Next action: migrate the five stale golden `.ctv` fixtures under the
  grammar change (see Known Failures), then broad gates + review; M1b
  is the recorded deviation pending the review round's decision.

## Decision Log

- 2026-10-04 (owner decision; resolves the 2026-10-03 M1b flagged
  deviation): the event-envelope schema stays
  `memorii.semantic-memory-event.v1` and additive grammar extensions
  extend it. Verified before deciding: nothing in the repository's
  golden fixtures or trial artifacts carries v0-stamped bytes — the v0
  reader in event replay is dormant fail-closed support, and v1 is the
  sole proven current write. The version rule is codified in the design
  (§6.10 item 5): additive-superset extensions extend the current
  version under strict decode; non-additive changes (removal, rename,
  reinterpretation, wire-layout change) mint a new version, and every
  grammar change mints after first external release. Minting a version
  without being able to state which change belongs in which version is
  prohibited.
- 2026-10-03 (flagged deviation for milestone review — design §6.10 item
  5): the event-envelope schema version remains
  `memorii.semantic-memory-event.v1` instead of minting v2. The grammar
  extension is an additive superset: the closed `GraphRecordKind` union
  gained one member, every pinned artifact regenerated through the
  authoring script, old batches replay unchanged, and an older binary
  rejects the new record kind at strict decode (the fail-closed
  compatibility rule the design itself specifies — covered by the
  strict-decode rejection tests). Minting v2 additionally requires the
  persisted-history compat cascade (byte-identical registry-1 history
  prefix, upcast-decision consultation of the current registry, and
  prefix-tolerant equality at atomic_store :7100/:8825) whose risk was
  judged disproportionate to the naming benefit at Level 2. The review
  round must either accept this recorded deviation (amending the design
  sentence) or schedule the v2 mint as a follow-up; it is not silently
  dropped.
- 2026-10-03: Milestone execution order adjusted by dependency analysis:
  record-kind grammar landed first (f9de4478); the governance publication
  entry (originally M2) is the hardest orchestration (full projection/
  checkpoint/aggregate/policy cascade — traced at atomic_store
  `_prepare_native_projection_publication`, `advance_semantic_replay_authority`,
  clarification/native precedents) and CONSUMES the other milestones'
  outputs (tombstone builders from M3, pending-epoch ride from M4, view
  refresh from M5). Execution order: reader ledger/tombstones → control
  plane → view + serving matrix → governance entry → registry v2 →
  parity/regen/repin. Requirement allocation is unchanged; only sequencing.
- 2026-10-03: The governance entry publishes through the store's standard
  conditional-write primitive (binding inherited from the composed
  memory-plane writer); the governance operation identity lives in the
  operation id/fence coordinates and the control-journal linkage, with no
  new writer-registry kind (the store itself is the enrolled writer).
  Recorded as a bounded reading of design §6.10 item 1 — enrollment,
  owner-gating, and validation are all preserved.

## Review Log

(none yet)

## Known Failures (milestone-close blocking, exact disposition)

| Command | Signature | Authority chain | Disposition |
| --- | --- | --- | --- |
| `pytest tests/integration/test_observation_ledger_activation.py tests/integration/test_observation_terminal_intent.py` (local, package cwd) | 5 failures: stale golden `.ctv` captures under the approved `revocation_directive` grammar change | the captured payloads embed the 12-kind codec manifest and snapshot counts | RESOLVED 2026-10-03: the migration engine (tests/fixtures/semantic_ingestion/migrate_current_terminal_fixture.py) now migrates all three `.ctv` captures, the memory-records plane (9 members, both manifest copies, reference ledger, terminal recovery, group-commit primary with ctv cascade into every construction-embedded reload tuple), and re-encodes each member with its original envelope family (contract vs atomic). The records plane is migrated first and the terminal-reload capture is written from the records-rebuilt reload model so both planes carry identical bytes. Both modules green: 47/47 (terminal intent 3/3, retained closure both variants, captured jsonl history preserved). |

MIGRATION COMPLETE (2026-10-03): both fixture planes migrate green end to
end. Final engine structure (tests/fixtures/semantic_ingestion/
migrate_current_terminal_fixture.py): (1) publication-request.ctv is
migrated first and exports the authoritative request chain (handoff,
epoch, request, replay, lineage digests, group-result digests, canonical
record, finalization delta); (2) the memory-records plane migrates the
group-commit primary first (plan-member rebuild, authorization
group_plan_member_digest re-pin, persisted core + receipt cascade from
the rebuilt core), cascades the fresh request_ctv_digest into every
construction-embedded group_commit_reload (rebuilding each core and
re-pinning its receipt), re-pins delta/canonical-record
group_result_digests from the export, re-encodes every member with its
original envelope family (contract members via encode_semantic_contract,
atomic members via the atomic member encoder, no synthetic codec_key),
recomputes the manifest digest over a TUPLE of member dumps (CTV encodes
list and tuple differently), and captures the records-rebuilt terminal
reload model; (3) terminal-reload.ctv is written from that records
reload model (plane convergence); (4) publication-intent.ctv migrates
last. Store debug was instrumented only against a scratch copy and
restored; atomic_store.py is untouched. Durable lessons: original pinned
digests (group results 691439a7..., delta 27caf38a...) are STALE under
the grammar change because the rebuilt constructions legitimately
recompute (planning-state manifest reconciliation changes
group_plan_member digests); the store treats the records-plane manifest
members as authority for the v2 delta, so every embedded copy (request
delta, reload delta, wrapper) must carry the rebuilt values, not the
captured ones.

## Blockers And Limits

None beyond the known failure above. Budget: three review rounds per
milestone before blocking.

## Milestone Review Round (2026-10-04, three independent reviewers)

Verdict: NOT ready — the grammar and control-plane spine satisfy the
design, but the serving-enforcement promise ("no read path may ever
surface the content again") is not delivered on the production serving
plane. Confirmed findings (all verified against code):

P1 / changes_required (blocks FGT-R2/R3/R8/R11):
- RV1 No production composition root injects the revoked view into the
  provider serving plane (hermes_factory, hermes_provider,
  authenticated_source, filesystem bundle, production_capture all pass
  none); absence is treated as unfiltered, but the design requires
  absence to be a fail-closed composition error.
- RV2 Enforcement publication has no production trigger: the emitter is
  None forever (no setter), the barrier-release/boot drains are inert,
  enforce_forget has no production caller, the CLI has no enforce
  command.
- RV3 observe_graph has no revocation enforcement (neither view nor
  replay-projection exclusion; the retired-claim set never sees
  revocation directives).

P2 / changes_required:
- RV4 identity-lineage host-grant reads serve revoked content (R16 host
  half; provider/service.read_identity_lineage applies no view).
- RV5 memory-plane query surface (get_record/list_records/query_records,
  pagination, cursors) unfiltered; the design requires pre-slice
  filtering (no host caller of query_records yet; exposure is via
  internal consumers).
- RV6 runtime-step retrieval admits revoked ids into
  available_evidence_ids.
- RV7 legacy graph queries: no tombstones for graph_node/graph_edge, no
  view, REVOKED missing from graph_persistence validity map (KeyError
  crash) and from temporal never-eligible states.
- RV8 learned-ontology coverage/index serving has no revoked-source
  ineligibility.
- RV9 the serving view never refreshes at apply-time (journal write);
  long-lived processes serve revoked content until restart.
- RV10 suppression journal filename collision (same second + same
  coordinate count) silently destroys a prior entry.
- RV11 the applied directive carries an empty closure manifest and a
  synthetic authority digest (audit fidelity, no serving impact).
- RV12 the §10.1 parity family is a reduced single test: ten matrix rows
  unwalked, no cursor exhaustion, per-path deltas, restart, in-window
  oracle, or crash-cut family; mixed pre/post-extension fold replay
  untested.

P3 / follow_up (recorded, not blocking): forensic negatives (empty
coordinate, cross-coordinate leakage, non-entity kinds), rank-competition
prefetch pin, older-binary strict-decode proxy, fixture-manifest drift
check, migration idempotence, malformed-coordinate IndexError, plan_digest
field disagreement between index-record writers, closure class 2-3
under-enumeration, derived-index projection consistency, doctor revoked
counts, operator inspection surfaces (do not exist; vacuous row).

Revision order (dependency-sorted): RV1+RV2+RV9 first (composition and
enforcement spine — everything else hangs off them), then RV3/RV4/RV5/
RV6/RV7/RV8 serving gates, then RV10/RV11 durability and audit fidelity,
then RV12 the full parity family. Test-reviewer finding "forensic suite
absent from CI" already fixed (1c1feb13).

RV1+RV2+RV9 LANDED (2026-10-04): the provider factory requires the
revoked-identity gate (absence fails closed; empty_revoked_view() is the
explicit ephemeral statement); every production root derives
RefreshingRevokedIdentityView from its control root (hermes factory,
filesystem bundle/builder, hermes provider bare-plane branch,
authenticated source, production capture; managed-partition open and the
harness sidecar switched to the refreshing gate, which re-derives on
suppression-journal writes so long-lived processes observe revocations
without restart); StorageAdministrationService gained
set_forget_enforcement_emitter and ProviderMemoryService.
wire_forget_enforcement connects the Hermes root's drain to its runtime
store; the CLI gained `forget enforce`. Acceptance:
tests/integration/test_forget_composition_gates.py (factory refusal,
journal-write observation without restart, mode-resume drain publishing
the directive), registered in both durable CI jobs.

RV4+RV6+RV7-maps LANDED (2026-10-04): host-grant identity-lineage reads
exclude revoked identities before the audit view digests are computed
(revoked view threaded through the scoped reader and the provider
factory); query_runtime_memory excludes revoked records so
available_evidence_ids never contains them; REVOKED added to the legacy
graph validity map (no KeyError) and the temporal never-eligible set.
Lineage 14/14, visibility/execution/recall 17/17 green. REMAINING in
this band: observe_graph exclusion (RV3), memory-plane query-surface
pre-slice (RV5), legacy graph_query view + graph tombstones (RV7 rest),
ontology serving (RV8).

RV3 LANDED (2026-10-04): the graph-observation cohort provider excludes
revoked identities from every observation stream (ingestion, native
projection, boundary, claim projections) before the merge and preimage,
so paging stays exact; build_host_graph_observation_runtime requires the
gate. Composed observation suite 11/11 green.

RV5+RV8 LANDED (2026-10-04): the record-query surface consults the
revoked-identity view pre-slice inside the read transaction
(SqliteMemoryPlaneStore.query_records accepts the gate; scan pages
collect serving-eligible rows from the cursor's raw offset so pages and
revision-bound cursors stay exact; record_lookup denies revoked ids) and
the only host-facing entry (MemoryPlaneService.query_records_host) fails
closed without a gate — internal integrity readers keep the unfiltered
store API by design, per the caller inventory that showed every
production list_records/get_record caller is internal. Learned-ontology
coverage statuses exclude revoked sources at the provider read. Query
parity 15/15 (revocation exclusion + pagination exactness + lookup
denial + fail-closed wrapper), store contract suites green.

RV7-rest LANDED (2026-10-04): the legacy graph query family serves
through a revoked-identity-gated snapshot (MemoryGraphQueryService filters
nodes and dangling edges before every query; MemoryEvolutionService
threads its injected view), and the forget closure now enumerates
graph_node/graph_edge records referencing revoked identities, rewriting
them at enforcement as superseding REVOKED-lifecycle versions (structural
identity preserved; literal text never lives there). Combined with the
earlier REVOKED validity/never-eligible maps, the legacy row is closed.
Evolution suites (retrieval/execution/temporal) 112 passed; forget
suites 7/7; ruff/pyright clean.

RV11 LANDED (2026-10-05): the applied revocation directive binds the
plan-time closure enumeration (every record coordinate the plan carried,
under the established reference_disposition carrier kind, canonical and
digest-pinned per the model's own formula) and records the owner
capability digest presented at apply — the suppression journal gained an
optional authority_capability_digest field (legacy entries default None
and keep the documented synthetic fallback); the composition-gates drain
test asserts both bindings against the materialized directive. All
forget suites and static gates green.

RV12 LANDED (2026-10-05): the §10.1 parity family expanded
(tests/integration/test_forget_parity_family.py, registered in both
durable CI jobs): the in-window oracle (the journal alone gates serving
between apply and enforcement), the runtime-step row, the host
record-query row walked to cursor exhaustion with no duplicates and
exact termination, the legacy graph row including the REVOKED tombstone
rewrite and gated snapshot, and the §10.3 crash-cut (apply → close →
reopen → drain completes the directive). The mixed pre/post-extension
fold replay landed in test_event_replay.py (thirteen pre-extension kinds
in the head batch, directive-only tail, genesis equality). Recorded as
follow-ups (P3): per-path delta-count tables for every matrix row and
endpoint-level walks for entity-match/structured-fact/observe-graph,
which require authenticated-ingress fixtures beyond the shared plane
fixture; their gates are already pinned by the composition sweep and the
observation suite respectively.

FIX PROGRESS (2026-10-05): the shared scenario quote authority is now
parametrized on the source text (default unchanged) and the multi-fact
root-composition test states its own text; instrumentation proved the
fix advances the failing chain past proposal sealing to a NEW layer —
publication_linearized/publication_conflict in the scenario publication
CAS — confirming the quote-authority diagnosis and exposing the next
layer for the dedicated debugging operation (pre-existing, CI-excluded
suite; not a release-chain gate). The pr-gates registration for the
parity-family suite (missed by the memorii/docs-scoped add in 5f0e29d8)
is committed here. MEASURED (2026-10-05): the fix takes the suite from
24 failures to 8 (40 passed); the remaining 8 cluster behind the
publication_linearized/publication_conflict layer — the dedicated
debugging operation's entry point, with the single-fact fixtures
unaffected.

ROOT-CAUSE DIAGNOSIS (2026-10-05, instrumentation fully reverted): the
root-composition failures chain is
sync_event -> _run_semantic_ingestion ->
SourceNormalizationExecutionOwner.normalize_after_recovery_claim ->
SealedBootstrapV3ProposalProducer.produce returns None ->
seal_bootstrap_proposal_run rejected ("bootstrap quote cannot be
resolved exactly") because the shared scenario quote authority
(_SingleTextQuoteAuthority in test_semantic_provider_composition.py:885)
resolves against a HARD-CODED single-fact text ("Atlas owner is Bob.")
while the failing tests propose multi-fact quotes ("Atlas owns Bob."
etc.) against multi-sentence source texts — every multi-fact proposal
seal fails, the terminal becomes evidence_only/
source_alignment_authority_unavailable, and the tests expect
source_only. The fixture-builder variant of the resolver
(source_normalization_fixture_builder.py:310) resolves against the real
source text and is the correct model. BOUNDED FIX (next cycle): make
the shared builder's quote authority resolve against the invocation's
actual source text (fixture-builder semantics), or have the multi-fact
tests supply their own authority; then re-bisect whether 3214def8
merely exposed it. Working tree instrumentation reverted; only the
pr-gates registration from RV12 remains modified.

SEPARATE PRE-EXISTING DEFECT (recorded 2026-10-04, needs its own
debugging operation): tests/unit/core/semantic_ingestion/
test_bootstrap_graph_root_composition.py fails locally (24 tests; sample
assertion: sync_event not blocked "source_only") at 3214def8 and every
later commit — it predates this revision and is invisible to CI because
the file is in unit-shards.json's ignore list and no dedicated job runs
it. Not caused by the revision; do not fix by weakening; investigate
under a separate debugging WorkPlan.

## CI Queue Note (2026-10-05)

GitHub runner backlog held nine branch runs (no workflow concurrency
group; ~500 queued jobs). The seven superseded runs (through 4ffce526)
were cancelled to free runner capacity; the authoritative run for
6489add4 (37266156716) is watched with a completion notification. Review
round 2 launches when it completes green; superseded reds need no triage
(cancelled, and their commits are ancestors of 6489add4).

## Next Action

The forensic lineage surface (R16) and the prefetch canonical-channel
filter landed with their acceptance tests
(tests/integration/test_forget_forensic_lineage.py: owner-capability
forensic retained lineage for named coordinates + refusal without
capability; canonical prefetch assembly excludes revoked records under
the injected view; record selectors now resolve any committed record,
matching the design's direct-selector scope). Watch the PR-gates run for
the fixture migration (82f31c0e) and fix any red checks; then run the
milestone review round — the M1b registry-v2 deviation decision is the
recorded open item and needs the owner because it changes a persisted
schema-version boundary.
