# Registered Continuation Runtime

Work type: implementation milestone. Status: active. Coordinator: root.
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

The linked design is closed and promoted (8a0ed7d feasibility, 66770e7
promotion): field semantics are canonical in the observation addendum and
ProjectionObservationIdentity.v1 is a registered self-digest root (181
schemas/1269 roles; 58 vectors; promotion.json binds the bytes). Public
integration is unblocked. Current construction: one Terra writer owns the new
production module graph_observation_native_projection.py plus focused tests
(structural stream families from retained native authority through
emit_registered_observation_artifact; every ambiguous join denies). Root owns
provider/host/service wiring afterward, then real ProviderMemoryService proof.
No fixture cohort may stand in for the provider integration proof.

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
