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

Continue the real detached cohort/persistence contract and provider integration
while preserving the reviewed registered cursor/retention component.

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

Current next action: implement the concrete authenticated public observation call chain.
