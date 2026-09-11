# Registered Continuation Runtime

Work type: implementation milestone. Status: closed for the bounded construction milestone 2026-09-11; follow-ups carried. Coordinator: root.
Parent: ../implementation.plan.md; campaign: completion-readiness/closure-plan.md.
Approved design: ../../ingestion-time-continuation/closure.md, candidate
d90458a82014c9a04d43646cf352044aba1aa5be7e4228c1f0ddddad762c9a42, promoted to
docs/design/semantic_ingestion_observation.md and explicit SIA endpoint dispatch.
Baseline d17466d5 plus authorized design-only changes. Preserve graph bytes for
existing publication and all historical schemas. R17/R19 remain partial until
the real detached cohort backend and provider composition are finished.

## Complete Behavior And Ownership

One worker owns new registered ingestion-time cursor model, closed issuer/decoder,
both paging endpoints and shared tenant/global bounded retention, feature-local
tests, new six authored role declarations and source/decoder selection inventories.
Canonical owners: graph_observation_public_contracts.py, observation_activation_runtime.py,
graph_observation_paging.py. Existing protected registered encoder/reader owns all
bytes; use no bespoke cursor encoding or permissive schema fallback. The proposal
names exact purpose/domain/shape and failure precedence. Public typed methods
must use distinct request/response models and explicit authorization purpose.
Root owns concrete detached backend, provider/factory integration, generated
artifact commands, all long tests, reviews and commits. No overlapping writer.

## Entry Binding And Change/Gate Ledger

Existing graph paging observe_graph -> registered issue/decode has one internal
caller and no provider caller. Ingestion-time gains parallel typed method ->
ingestion_time_input of real detached cohort owner -> registered cursor/page.
Root must add ordinary ProviderMemoryService/factory callers using host-held
authorities, registry/keys/budget. Missing trusted configuration fails closed.
Do not mark this packet complete with only a fixture cohort or unused module.

Add IngestionTimeAttestationCursorPayload.v1 to authored roles and canonical
decoder ownership; inventory changes77->78 explicit roots,179->180 schemas,
1075->1081 authored roles and1255->1262 total roles before other changes. Root
regenerates via reproduce_publication.py --refresh-generated and independent
verify_registry_vectors.py, updates packaging/source pins and runs applicable
workflow gates; no hardcoded count changes to hide missing schemas.
Identity names are behavioral; planning IDs remain traceability only.

## Validation And Limits

Round-trip both roots with separate verification key; reject cross-purpose,
wrong selected publication, malformed/overlimit shape/signature and all swapped
request/context/policy/predecessor/revision coordinates. Cover both attestation
kinds, first/final/empty page, revocation/expiry-before-decode, expiry during work,
write-race invalidation, restart/eviction and exact graph compatibility. Exercise
count/bytes/tenant/global capacity and concurrent/in-flight reservations; failed
construction releases capacity and quota never evicts another live token.
Feature-local tests join dedicated activation gate; full provider proof must
use the real backend. Root runs focused checks, then one consolidated candidate
suite and standard independent review. Local Python3.12 is not CI3.11 parity.
No signatures, external policy values or statistical outcomes are fabricated.

## Next Action

Construction is committed: 40bf61b adds graph_observation_native_projection.py
(one verified native operation -> observed stream records through the
registered emit path; 14 focused tests); f31ac1b adds
graph_observation_materialization.py (AtomicStoreGraphObservationCohortProvider:
merged ingestion+native stream with duplicate denial, group-request/event-batch
closure joins by transaction_group_id — the draft's graph-delta-digest join is
NOT retained and was corrected; snapshot creation time is the system interval),
graph_observation_host.py, and ProviderMemoryService.observe_graph /
observe_ingestion_time_attestations with non-disclosing fail-closed denials
when unconfigured (factory pass-through, no env guessing). Focused real-backend
tests: 6 passed (489s); provider service/factory regressions 57 passed; paging/
decoders/native projection 19 passed; Ruff and scoped Pyright clean.

ingestion_time_input remains a typed denial: no persisted time-attestation
producer exists. The service-configured end-to-end proof is committed
(test_composed_graph_observation_service.py; 3 tests in ~500s on the real
activated backend): observe_graph returns real pages (4 ingestion + 5 native
kinds, real digests, contiguous positions, stale_cursor on exhaustion);
unconfigured endpoints fail closed without reading the memory plane; the
configured ingestion-time endpoint denies before the write-revision fence;
cross-purpose cursors deny at decode (invalid_cursor). Authority models must be
emitted through the writer registry before use (_registered_exact re-emits and
compares); page/policy digests are never placeholders on the wire.

Remaining for this milestone: full affected gates at one frozen candidate and
the three-role independent review before any R17/R19 promotion claim. The
ProjectionObservationIdentity reader-side re-derivation for observed projection
records remains an implementation obligation.

## Milestone Review Round 1 (2026-09-10, candidate ed55c520)

All three reviewers approve-with-actions; no rejection. Reconciled confirmed
changes_required (one remediation round, sole writer = root):

1. System-interval semantics (spec F1 / correctness F1, correctness rates P1):
   observed system_interval currently stamps snapshot.created_at on every
   record, contradicting the promoted commit-event-ownership rule; the verified
   event coordinate is already derived in _commit_values. Correct to per-version
   event-derived intervals.
2. Boundary records (spec F2): referenced-but-unchanged entities are resolved
   in the lookup but never emitted; boundary_ids/boundary_record_keys are
   hardcoded empty and reference_path is constant. Emit boundary records with
   real reference paths per the architecture's referenced-boundary rule.
3. Sibling arms (spec F3 / correctness F2): correction/retraction/action/
   identity arms structurally deny whole cohorts; current planner commits
   fact-only deltas. Determinate correction this round: record the explicit
   arm gap here (typed refusal retained); arm payload implementation is a
   separate milestone and must precede any arm-inclusive promotion claim.
4. Provider integrity-join denials have zero coverage (test F1): add tampered/
   substituted-authority tests hitting each fail-closed branch.
5. CI gate wiring (test F2): add the slow materialization test to unit-shards
   ignores, select materialization+composed suites in the activation job,
   refresh unit-test durations.

Recorded follow-ups: converse closures (retained-inventory, evidence-pair,
changes-without-intent) correctness F3-F5; projection_kind closed-literal
registration before first identity issuance (spec F4); view/time applicability
folded into the projection-record obligation (spec F5); exact-count composed
assertion, host-mismatch test, restart item, arm-coverage discharge (test
F3-F6); reader-side ProjectionObservationIdentity re-derivation (standing).

Baseline gate matrix at candidate ed55c520 (pre-remediation): the activation
job's exact selection plus the three new suites passed 118 cases in 4123.98s
under -W error on local CPython 3.14.7 (not CI parity). This is baseline
evidence; the binding gate run happens at the remediated candidate.

Remediation round 1 is committed (see git log: event-derived per-record
system intervals keyed by canonical record kind with same-time-successor
lineage retention; boundary records emitted from retained payloads with their
own events and per-use-site reference paths, preimage boundary/changed keys
closed and disjoint; nine integrity-join denial tests validated by
guard-deletion; CI wiring with shard ignore, activation-job selection and
honest durations, activation timeout raised 30->90 for the added suites).
Writer gates: native 16, materialization 17 (real backend, 1h42m-2h25m),
composed 3, paging/cohort 4; ruff+pyright clean. Coordinator re-ran the fast
suites (20 passed), ruff and scoped pyright. Reviewer re-check decisions:
boundary test uses a substituted-authority seam because the current planner
never produces cross-transaction references; boundary emission is a separate
cohort-level function; system_intervals keys use canonical record kinds.

## Milestone Closure (2026-09-11, candidate 0dc0217e)

The bounded delta review of remediation commit e1e1602c resolves all five
round-1 changes_required findings with no regression and authorizes closure
once the binding gate passes. Coordinator evidence at this candidate:
- binding activation-job selection (exact pr-gates list, 15 files,
  -W error, local CPython 3.14.7): 115 passed in 7210.76s (2h00m10s)
- slow real-backend suites independently re-run: 20 passed in 5927.30s
- fast suites (native projection/paging/cohort): 20 passed; full Ruff;
  scoped Pyright 0 errors
- registry reproduction byte-compare and 58 vectors passed at promotion
- activation-job timeout pre-sized to 240 minutes per measured budget
  (delta-review P3, resolved)
remaining_validated_p1_p2: []

Closure scope: the registered public graph-observation construction
milestone — native structural projection (fact arm + typed sibling-arm
refusals), detached cohort provider with event-derived per-version system
intervals and referenced-boundary emission, host composition, public
ProviderMemoryService methods with non-disclosing fail-closed denials,
ProjectionObservationIdentity.v1 registration, canonical field-semantics
addendum, and the composed real-backend end-to-end proof. Parent R17/R19
remain partial pending whole-candidate CI and the follow-ups below.

Carried follow-ups (must precede any arm-inclusive or projection-record
promotion claim): sibling-arm payload implementation (correction/retraction/
action/identity); reader-side ProjectionObservationIdentity re-derivation for
observed projection records; projection_kind closed-literal registration
before first identity issuance; view/time applicability with projection
records; converse closures (retained-inventory, evidence-pair,
changes-without-intent); exact-count composed assertion; host-mismatch test;
restart item; persisted ingestion-time attestation producer. Local CPython
3.14.7 evidence is not CI parity; GitHub CI execution of the activation job
(including its new timeout) remains a separate evidence-maturity step.

## Current Component Evidence (2026-09-08)

Root took sole ownership after checking delegated output. Both cursor roots,
authorization ordering, shared retention reservations and expiry/final/failure
cleanup are implemented. Focused graph/ingestion/public-contract tests:13 passed
in46.45 seconds on local Python3.12.14. Full independent registry compilation
agrees for180 schemas/1262 roles;58 mutation/construction vectors pass. These
are local component results, not provider integration or operational evidence.
New ingestion-time test is selected by the activation CI job; CI has not run
for this working tree. Canonical scoped Pyright and the full activation job
are running locally. Root owns their terminal results.

Frozen component candidate: continuation-component-candidate.json SHA256
0d257b415f324cdc8cfe68415227eb9d74534adf053acd84cdb3cfc280308321.
Spec/correctness/test reviewers are read-only for this bounded component.
Root owns all mutations and commands. Detached authority/membership modules are
work in progress, with no public provider caller and no integration claim.
Ingestion-time persistence has a separate unapproved design packet; no producer
or durable start-time/clock binding is claimed. Parent R17/R19 stay partial.

## Corrected Component Checkpoint

Candidate90c58da62428f3caeab8ee7bca03116a24009d35e97aa705e1d757987a61362c
supersedes the initial component review identity. Confirmed corrections CP001-004
cover first-page revision denial, typed capacity denial, decode-time expiry
precedence and snapshot policy-age expiry. Both endpoints now have corresponding
regression assertions.26 paging/contract tests and13 codec/cursor tests pass;
full Ruff/scoped Pyright pass;180-schema independent equality and58 vectors pass.
Full activation was interrupted after findings and is not passing evidence.
See continuation-component-evidence/manifest.json. No full milestone closure.

## Final Retention Delta And Gate Refresh

Final component candidate d19c7bfc93eebd730ff14f0125ee5887d0975cbc5a72008905f28c28244c0729
adds caller-bound stale-policy quota release.30 paging/contract tests pass in
68.60 seconds;13 unchanged codec/cursor tests pass. Correctness and test delta
reviews approve this component only. See continuation-component-review.json.
The governing-design edit required CTV authority/structural-vector regeneration
and current workflow/document/test pin refresh. No algorithms, semantic ledger,
attack matrix or lifecycle witness were relaxed. The equal-version decision's
SIA byte binding was refreshed using its existing digest function; decision
rules, owner/date and evidence families are unchanged, and all30 decision tests
pass. Current-turn SIA changes do not modify equal-version replay semantics.
Full hermetic and black-box source gates are being collected; no passing claim
is made until terminal outcomes are recorded. This is not a milestone closure.

The final source-gate pass completed279 cases:276 passed and3 failed solely on
stale expected design/artifact hashes or the previously missing activation-job
aggregate dependency. All3 corrected cases pass focused reruns (2 in3.33s,1 in
1.42s). All three hermetic workflow gates pass, including their isolated and
mutation checks. Final scoped Pyright reports0 errors/warnings; full Ruff and
identity hygiene pass. Portable logs retain the initial failures and the reruns;
no single-run all-green or GitHub-CI claim is made. The local source-test run
used macOS/Python3.12 and took589.38s, not equivalent to Ubuntu CI timing.

## Detached Authority And Membership Checkpoint

Current frozen candidate: detached-cohort-candidate.json SHA256
2edcc99e59c601676be791c59c03744264cc806f36c808a444133606b0a39aac.
Root owns these production/test files and all commands. The reader reconstructs
graph, event, reference and observation state from one detached store snapshot;
its protected creation time is explicit. Source/operation membership closes
over transaction/fence siblings and co-committed graph deltas, checking every
source's complete private scope grant and terminal result. Three focused native
delta tests pass; spec/correctness bounded reviews approve. The full activated
provider/reopen test is still running and is not yet passing evidence.

The first two local attempts were interrupted before test completion (152.82s
for a test-coordinate correction,316.14s for review corrections). Neither is
passing evidence. The current attempt uses frozen corrected code. Final scoped
Pyright passes; portable evidence will record the terminal provider result.
No public endpoint,17-stream materializer or time-attestation producer exists yet.

The frozen expanded provider test completed successfully:1 passed in1472.96s
(24m32s). It includes real activation, source+operation selection, no live-clock
resampling, scope/missing-delta refusal, later-write snapshot stability and JSONL
reopen/exact retry. The3 native-delta unit tests pass, plus1 CI-selection check
in0.40s. Explicit CI selection is the only delta from the approved code candidate;
its identity is detached-cohort-ci-candidate.json SHA256
214718332b88138b841838ca6098d712b5423a0bf0f73ce8263b6962618d25c9.
Portable evidence is in detached-cohort-evidence/manifest.json; final test review
is now ready. No remoteCI or public endpoint completion is claimed.

## Final Internal Reader Review Disposition

Confirmed: Not applicable / blocks_approval / verification. The detached reader
and membership resolver have zero production callers; the real-storage test
calls them directly. Spec/correctness approval and passing local checks establish
internal feasibility only. R19 and this runtime milestone remain incomplete.
Disposition: required evidence_action paired with the already planned concrete
public caller and bounded materializer implementation; no synthetic caller or
requirement promotion. All local commands have finished.


## Public Composition Construction

Base6029030d is pushed. Root owns existing paging, capability, provider, host
configuration and integration tests. Terra worker observation_materializer owns
only new concrete materialization modules and focused tests. Spark
retention_retry_map refreshes the public binding map read-only. Test reviewer
consultation requires real ProviderMemoryService triggers, exact same registry
and snapshot authority, purpose/pre-read denial, context/current-grant checks,
continuation freshness, cross-purpose cursors and restart. A time-attestation
page cannot succeed until genuine persisted attestations exist. No fixture
cohort may stand in for the provider integration proof.

## Internal Adapter Checkpoint And Review Corrections

Public composition is parked in the linked provenance design's
public-composition-draft.patch; the concrete materializer is not present.
The registered access adapter and four ingestion projection variants are internal
preparation only. Root coordinates; repair_projection_tests (Terra worker) owns
only the projection test repair; access_projection_review (Terra correctness)
provides bounded read-only consultation. No full milestone approval is requested.

Confirmed corrections: bind selected native records exactly to ledger mutations
and source finalizations, and reject noncanonical authorized-scope identities.
The proposed paging timestamp was removed: an authorization-time clock sample
cannot establish the atomic store snapshot's system time. A genuine atomic
snapshot/time binding remains an integration obligation. These are determinate
corrections; no public runtime completion is claimed. Fixture repair uses real
native deltas and covers zero/multiple introductions plus substituted records.

Frozen registered-ingestion-prep-evidence/candidate.json passed5 projection and
21 access/workflow checks. Full Ruff, scoped Pyright and identity hygiene pass.
Bounded correctness consultation approves the corrected internal slice only;
review.md reconciles the remaining public-entrypoint finding. All local checks
finished; no GitHub CI or parent completion is claimed. The test writer handed
off; root owns the final checkpoint. Commands and portable logs are in
registered-ingestion-prep-evidence/manifest.json.

2026-09-08 owner decision: complete retained policy context is approved. The linked observed-provenance design operation is active for its corrected feasibility and review; the semantic-choice blocker is resolved.

The linked provenance design is complete:13 checks and all three bounded
reviews approve the promoted retained-context recipe. No user policy-context
decision remains. Public materializer and snapshot/time binding are still open.

## Public Integration Resumption At 7a92bce2

The tree was clean. The approved provenance recipe is no longer a design
dependency. Root is mapping exact retained graph fields; no fixture or
co-produced-record guess supplies public authority.

Delegation/cost ledger: public_observation_bindings (Spark code-mapper,
read-only) refreshes provider/store entrypoint bindings; graph_projection_authority
(Spark explorer, read-only) traces entity/relation/action field authorities.
atomic_observation_time (Terra worker, sole code writer) owns only store,
service, unit-of-work, paging and their feature-local tests. The existing test
reviewer provided a bounded preimplementation matrix; no full review is claimed.
Root owns documents, all pytest commands, evidence reconciliation and commit/push.

Timed snapshot scope: additive full-write snapshot with protected UTC sample
inside the backend lock, carried into both paging snapshot roots. Preserve the
existing two-value snapshot API and persisted bytes. Read-only inventories and
units of work cannot mint fresh snapshot time. Authorization remains before
read/clock authority; continuation still fences every write.

Validation matrix: both backends with barrier-controlled competing writer
(separate JSONL handle); detached records; one UTC sample; invalid/raising clock
releases locks; read-only/UoW reject before sample; both endpoints distinguish
authorization from snapshot creation time and age; pre-read denials; control
and empty writes stale both continuation kinds. Existing paging tests own
mechanics; a later actual provider proof must own public integration.

Changed-surface/authority ledger: memory_plane store/service/UoW and paging
are implementation only; their feature-local tests are verification surfaces.
No registered model, codec, persisted format or generated artifact changes are
planned for the timed snapshot. New names must describe snapshot behavior.
The activation job in .github/workflows/pr-gates.yml selects both paging tests;
focused results will not be reported as a full activation or CI pass.

## Timed Snapshot Checkpoint And Public Integration Blocker

Both backend timed snapshots and both paging creation times are implemented.
The first test run exposed a wrong two-store in-memory fixture (1 failed,
52 passed); corrected shared-store contention and genuinely distinct auth/read
clock samples pass53 tests. Bounded correctness consultation reports no findings
on the four frozen production files. An expanded typing check exposed test
harness annotations; root corrected them rather than claiming baseline failure.
Final commands and hashes are recorded in public-integration-evidence/manifest.json.
No full activation job, current CI, public runtime or parent closure is claimed.

The public construction work revealed an actual contract gap: projection
observation_id lacks a registered preimage/hash recipe; entity/relation field
semantics are not completely specified by native records. Terra correctness
consultation confirmed the identity gap. Root rejected claims that source IDs,
claim identity, operation joins or reference paths do not exist; those are
ordinary implementation obligations. The actual unresolved choices, proposal,
and parked unverified drafts belong to the separate design operation
../../graph-observation-materialization/design.plan.md. All worker ownership
has returned to root. The user question is pending; provenance is not reopened.

The bounded test delta required two evidence corrections: control-only and
empty-batch writes now stale both continuation kinds while leaving data revision
unchanged; invalid and raising clocks now prove lock release using another
thread (and a second JSONL handle). The combined run passes57 cases; after an
explicit lambda capture formatting correction all24 store cases pass again.
These are required evidence actions, not newly found product defects.

## Post-Closure CI Evidence And Branch-Debt Triage (2026-09-11)

PR #120 at head 5596828f: Observation Ledger Activation SUCCESS on GitHub CI,
including both new real-backend suites under the 240-minute budget — the
milestone's CI leg. Pre-existing branch failures reproduce identically at
pre-session baseline a7c6a9ed and are NOT caused by this operation: unit
shard 1 (test_terminal_request_reload_rejects_in_memory_corrupt_closure),
shard 4 (architecture explicit-owners and cross-module private-symbol tests
violating via bootstrap_graph_projection_publication.py,
observation_activation_package.py and
semantic_ingestion_activation_target_release.py), shard 2 workflow-structure
and Package Smoke — none of this operation's modules appear in any violation.
These are merge-blocking branch debt for a separate bounded operation.

Converse-closure hardening committed (b2955d5a): retained-inventory,
evidence-pair and changes-without-intent closures with guard-deletion-validated
denial tests; fast native suite 17 passed; both new materialization denial
tests passed on the real backend; the full materialization regression re-run
was started by the coordinator. Next: sibling-arm payload milestone, then
projection records + reader-side identity, then the attestation-producer
design packet (owner decision), with the owner-requested production-keys/
trusted-deployment/signatures brainstorm between as scheduled.

Binding regression terminal result (coordinator-run): the full materialization
suite passed 19 cases in 3475.32s at b2955d5a — the converse-closure hardening
is now fully verified, not just analysis. All converse-closure follow-ups are
discharged; remaining carried work is the sibling-arm payloads, projection
records + reader-side identity re-derivation, and the attestation-producer
design packet.

## Sibling-Arm Payload Record (2026-09-11, commit ce7a68ee)

All four non-fact arms now project through the native projection owner:
correction/retraction transitions -> ObservedTemporalTransition (correction
derives the slot key from the retained replacement claim), action arms ->
ObservedActionRevision (role bindings resolved through recomputed planner
participant coordinates), identity arms -> ObservedIdentityTransition +
ObservedReferenceDisposition (per-use-site reference paths; complete retained
source spans only). Typed refusals are kept for genuinely unprovable joins.
Disclosed carrier insufficiencies (fail-closed, not guessed): retraction
transitions lack any retained claim-slot-key authority; action arms retaining
claims lack the fact member for polarity; no canonical recipe yet exists for
ActionTransitionApplicabilityKey digests (retained value copied only).
Evidence tier: envelope tests built from the real fact capture through the
real constructors (25 fast-suite cases, ruff, scoped pyright green); the
committed-path materialization regression is coordinator-run and recorded
below when terminal. No real non-fact cohort exists yet, so no real-backend
arm observation is claimed. The blanket unsupported-kind denial is replaced
by precise per-arm recipe denials.

Sibling-arm committed-path regression (coordinator-run): the materialization
real-backend suite passed 19 cases in 3375.96s at ce7a68ee. The sibling-arm
milestone is fully verified.

## Projection Identity Reader Record (2026-09-11, commit 80c75de5)

The standing reader-side obligation is discharged: observed projection
records are accepted only after the registered reader derives the expected
observation_id through the ProjectionObservationIdentity root from the same
selected publication (emit re-verification funnel + the paging snapshot
acceptance point; mismatch -> non-disclosing denied). Publications without
the identity root keep historical read routes unchanged (the compiled
production publication does not contain the root yet, so current behavior is
byte-identical until the next publication refresh). A producer helper derives
identities through the registered emit path. Guard-deletion validation and
substitution tests (kind/repository/generation/projection swaps, forged ids,
historical-publication forgeries) pass; 32 fast-suite cases, Ruff and scoped
Pyright green. Remaining known follow-ups: projection-record PRODUCTION
(observed temporal/trust projection records are still not emitted by the
public stream producer — view/time applicability rides with it) and the
applicability-key digest recipe disclosure.

## Projection Record Production Record (2026-09-11)

All 17 observation stream families are now produced: projection state is
retained in the detached image as committed memory-plane records, so
project_observed_claim_projections emits ObservedTemporalClaimProjection /
ObservedTrustClaimProjection with copied native payloads, retained
generation/pointers/successors, derived registered identities (publication
without the identity root denies), boundary keys, and preimage projection
digest pairs. View/time selection: current requires valid_at=None and a
generation whose base revision equals the detached graph revision; historical
requires valid_at and selects at system_as_of; lineage is a typed denial.
Fast-tier gates 53 passed, Ruff and scoped Pyright clean (coordinator-run);
the materialization real-backend suite re-run is coordinator-owned and
recorded when terminal. Remaining product work: the attestation campaign
(M0 clock fix first) per the approved design.
