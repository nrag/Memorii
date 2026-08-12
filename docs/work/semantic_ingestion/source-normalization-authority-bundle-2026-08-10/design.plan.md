# Trusted Host Source-Normalization Authority Bundle Design

- Work ID: semantic-ingestion-source-normalization-authority-bundle-2026-08-10
- Work type: design
- Status: under-review
- Coordinator: Codex main thread
- Created: 2026-08-10
- Last updated: 2026-08-10
- Parent WorkPlan: `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/source-alignment-producer-2026-08-10/design.plan.md`; `docs/work/semantic_ingestion/milestones/m3-semantic-pipeline.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md` before this delta SHA-256 `24c5406919eff69372db774136a5995f604608eea32d82a0580d1e236d21ea0d`; `docs/design/memorii_spec.md`; `docs/design/memorii_storage_details.md`; `docs/design/event_model.md`; `docs/IMPLEMENTATION_RULES.md`; parent implementation WorkPlan
- Expected outputs: an approved, implementation-ready source-normalization authority boundary and linked implementation resumption decision

## Objective

Define the trusted host packet that supplies every authority needed to produce
one graph-free source-normalization closure. The ordinary provider path must
create a complete proposal run and exact local analysis inputs without ambient
configuration, arbitrary installed resources, fabricated lifecycle coordinates,
or terminal-result reconstruction.

## Completion Contract

Complete only when the canonical design names owner, typed fields, validation,
production binding, persistence/replay behavior, compatibility boundary,
operational limits, and attack/evidence matrix; its frozen candidate then passes
specification, correctness, and test review with no remaining validated P1/P2,
blocks-approval, or changes-required finding. This plan does not implement the
packet or claim production reachability.

## Scope

Included: source-bound derivation authority, current publication authority,
sealed proposal-run production, local analyzer/temporal resource selection,
policy selection, bootstrap handoff promotion, provider composition, failure
behavior, and implementation proof.

Excluded: source-normalization persisted schemas/member algebra, graph
planning/commit/recovery semantics, remote proposal behavior, certified analyzer
replacement, and production code.

Deferred: code and evidence under the parent implementation WorkPlan after
this design approval.

## Non-Goals

This delta does not choose a new language, model, provider, release signer, or
stored schema; it only gives already approved authorities an explicit trusted
host boundary. It does not make a learned or remote provider an implicit
default, and it does not change graph-dependent semantics.

## Sources Of Truth

Precedence is `docs/design/memorii_spec.md`, then
`docs/design/memorii_storage_details.md`, then `docs/design/event_model.md`,
then `docs/IMPLEMENTATION_RULES.md`, then the canonical semantic-ingestion
architecture. This WorkPlan records the user-approved missing-boundary decision
but cannot override those sources.

## Constraints And Invariants

- Source, graph, terminal, and current authorization remain separate domains.
- The host is the sole authority issuer; core discovers no resource, policy,
  model, proposal producer, or writer state from ambient process state.
- Proposal output remains candidate evidence; existing validators and the
  atomic writer alone publish derived state.
- Derivation values are source/preparation/route-bound; volatile publication
  values are freshly checked but excluded from durable equality.
- Absence, ambiguity, stale controls, or resource failure fail closed before
  graph, terminal, or disclosure behavior.

## Problem Definition And Existing-System Analysis

`GraphFreeSourceNormalizationInputs` already needs proposal, analysis,
interpretation, policy, capability, publication, progress, fence, lease, writer,
and expected-generation authorities. Its invocation deliberately does not own
them. Certified Stanza/spaCy/Duckling lanes normalize source-local evidence but
cannot choose a run, policies, or write controls. `bootstrap_writer_handoff` is
the sole legitimate bridge into writer-safe preplanning, yet it does not supply
derivation policy. The canonical delta adds the missing host boundary without
changing existing persisted request/result/member contracts.

## Feasibility Evidence

The existing `GraphFreeSourceNormalizationInputs` type demonstrates every
required child authority and its strict stage checks demonstrate consumption
without a new persistence shape. Certified local adapters prove resource lanes
can emit source-local contracts. Remaining uncertainty is implementation
mapping: locate the exact composition constructors and bind the host provider
there before any claim of reachability.

## Requirements Ledger

| ID | Requirement | Source | Priority | Acceptance criteria | Status |
| --- | --- | --- | --- | --- | --- |
| SNAB-R01 | One explicit trusted-host packet owns all pre-graph authority. | User decision; SIA R01/R04/R19-R21 | Required | Exact packet fields, owner, and no-ambient boundary. | specified |
| SNAB-R02 | Proposal runs come from sealed route-bound authority. | SIA R04; proposal-run contracts | Required | Complete run and noncommit failures are defined. | specified |
| SNAB-R03 | Parser/temporal lanes use certified selected resources only. | SIA R08/R16 | Required | Exact binding, reservation, and no-fallback rule. | specified |
| SNAB-R04 | Policy, registry, publication, lease, writer, progress, and preparation coordinates are explicit. | SIA R20/R21 | Required | Derivation/publication split, preparation-bound CAS, and joins are defined. | specified |
| SNAB-R05 | Bootstrap promotion and normal roots work without global mutation. | SIA R19/R22 | Required | One handoff-to-stage flow and all root proof. | specified |
| SNAB-R06 | Replay and rollback preserve strict durable behavior. | SIA R10/R21 | Required | No bundle persistence; replay/rollback rule defined. | specified |
| SNAB-R07 | The complete authority boundary has measurable evidence. | AGENTS.md; PLANS.md | Required | Attack families and binding proof are defined. | specified |
| SNAB-R08 | The runtime has a mandatory handoff-authority signature and ephemeral complete-lane reservation. | SIA R08/R19-R21 | Required | Exact owner, lifetime, lane validation, closed noncommit reasons, and no-persistence rule are defined. | specified |
| SNAB-R09 | Trusted bootstrap declarations acquire separate route-bound proposal and certified four-lane analysis authority without changing prepared-route persistence. | User decision; SIA R08/R19-R21; bootstrap route contract | Required | Exact transient binding/set, digest domains, joins, projection, recovery boundary, production-binding plan, and attack matrix are frozen. | specified |
| SNAB-R10 | Recovery probes retained publication before building transient authority or bootstrap analysis bindings. | Review reconciliation; SIA R10/R19-R21 | Required | Immutable-key found-first probe, atomic predecessor-to-normalization-ready claim with store-issued live control/lease snapshot, coordinator/owner APIs, public-root and mutation/CI topology are exact. | specified |
| SNAB-R11 | Bootstrap analysis uses versioned persisted scalar provenance while preserving `PreparedSource` identity. | Approved external decision | Required | V3 codec/member placement, decoder rejection, atomic migration, and V1 derivation-only boundary are exact. | specified |
| SNAB-R12 | Recovery claim, four-lane reservation, and normal/evidence-only root split are atomic and closed. | Approved external decision | Required | Immutable key, claim/CAS/reclaim state machine, all four manifests, root migration/rollback, and evidence matrix are exact. | specified |
| SNAB-R13 | V3 bootstrap persistence is self-contained typed payload closure. | User-approved Option A | Required | Typed proposal/attempt and four lane payload carrier schemas, including native predicate/temporal candidates and results with no generic route wrapper, limits, joins, codecs, recovery, migration, rollback, and attack evidence are exact. | specified |
| SNAB-R14 | V3 bootstrap proposals retain the complete graph-free semantic operation algebra without a V2 reconstruction. | Implementation boundary discovery; SIA graph-free operation/alignment contract | Required | Closed five-kind members, nested fields/digests/limits, provenance-attempt joins, V3-native subject/interpreter/alignment, migration rejection, and attack evidence are exact. | specified |

Requirement identifiers are traceability values only and may not name code,
fixtures, schemas, workflows, diagnostics, or persisted values.

## Contract And Authority Boundary

The normative declaration is architecture section 3.4.2f.
`SourceNormalizationAuthorityProvider` is created only by provider composition
and receives admitted `PreparedSource` plus writer-safe bootstrap handoff state.
It returns one valid `SourceNormalizationAuthorityBundle` or a typed noncommit.
The mandatory runtime receives the invocation, exact `BootstrapWriterHandoffResult`,
bundle, and one ephemeral exact-lane reservation; it has no optional authority.
The graph-free stage consumes completed concrete inputs, never the provider or
the authority provider itself.

### Bootstrap analysis-route projection amendment

`BootstrapDeclaredSegmentLanguageRoute` is declaration-only and cannot
masquerade as the generic classifier route that embeds resources. SNAB-R09 adds
the transient `BootstrapAnalysisRouteBinding` and source-ordered
`BootstrapAnalysisRouteBindingSet` under derivation authority. There is exactly
one binding for each bootstrap route and none for generic routes. The binding
closes route source/preparation/child/parent/artifact coordinates, copies the
exact declared language as selected language, and carries one exact
`SegmentLanguageResourceBinding`, proposal capability fingerprint, and the
Stanza, spaCy, predicate-event, and temporal-resolver manifest digests. Its CTV
domains and enclosing derivation digest are named in architecture section
3.4.2f. It is neither a `PreparedSource` mutation nor a generic route
serialization or prepared-route persistence form.

The canonical owner is `SourceNormalizationAuthorityProvider.build`; it builds
the set from the admitted prepared source and host-certified resources. The
canonical consumer is `SealedSourceNormalizationEvidenceProducer.produce`,
which joins the exact bootstrap route, binding, prepared segment, governance
carrier, and message-admission identity before producing the request-local
bootstrap analysis projection. Proposal and four analysis requests consume that
projection only at their request boundary; retained artifacts use scalar route,
binding, resource, capability, and lane-manifest provenance rather than a
generic route encoding. All absent, duplicate, foreign, re-ordered, artifact,
language, resource, capability, manifest-support, or generic/bootstrap-path
substitution cases noncommit before a producer or lane call. Replay/recovery
reads retained provenance and atomic state only; it does not construct a
binding, reserve capacity, or repeat a producer.

### Recovery-before-authority correction

SNAB-R10 makes recovery an explicit coordinator-owned retained-scalar probe
before `SourceNormalizationAuthorityProvider.build`. It derives only from the
immutable key, successful handoff marker's authenticated predecessor control,
and invocation source/preparation/operation/fence. It excludes caller current
generations, authority, publication coordinates, resources, policies, route
bindings, provider output, and prepared-source lookup. The store transaction
checks `found` first; otherwise it atomically advances the exact handoff
predecessor to one `post_handoff_normalization_ready` successor and issues a
claim containing the store-owned current control/lease/writer/progress snapshot.
`found` validates/reloads with zero transient effects; unavailable closes;
only `claimed` permits `SourceNormalizationAuthorityProvider.build(invocation,
handoff,recovery_claim)` and `normalize_after_recovery_claim(...)`. Publication
authority copies its control fields only from that claim snapshot. The old
authority-bound request/context, absent arm, marker-current-generation fields,
and caller generation override are not accepted shapes.

### Approved boundary reconstruction

The user approved V3 persisted `BootstrapAnalysisProvenanceV1` as a distinct
scalar-provenance arm, never a generic-route upcast and never a
`PreparedSource` field. All bootstrap proposal, analysis, request/result,
evidence-manifest, and atomic-reload containers carry it; generic containers
forbid it. V1/V2 reject it, V3 is strict and atomic pre-release migration, and
the preparation fingerprint remains byte-identical.

`BootstrapRecoveryKeyV1` is immutable across publish and retry. A probe finds
by that key before comparing caller generations; found reloads the recorded
generation. Otherwise it atomically issues an expiring fence-bound single-use
`BootstrapRecoveryClaimV1`. Only the claim holder may construct authority and
publish; the publication CAS consumes its nonce while writing the found index.
Live foreign claim is unavailable, expiry permits one revalidated reclaim, and
all claim races/replays/fence/generation substitutions fail closed.

Normal roots require one complete host bundle in an unreleased API migration.
Evidence-only is an explicit distinct root/service with zero semantic work,
not an optional legacy fallback. The reservation envelope is exactly the four
Stanza, spaCy, predicate-event, and temporal-resolver manifests. Architecture
section 3.4.2f is canonical for digest domains, codecs, state machine,
rollout/rollback, and root behavior.

### Option A payload carriers

V3 now retains `BootstrapProposalRunPayloadV3` plus exactly four
`BootstrapAnalysisLaneResultV3` values per bootstrap segment. Proposal attempts
and normalized proposals, and typed Stanza/spaCy/native-predicate/native-temporal payloads,
are carried directly under closed discriminated schemas with content digests,
registered byte/count limits, and exact source/segment/lane/provenance/resource
joins. Request/manifest/result/atomic/replay closures flatten and authenticate
those bytes. Reopen has zero external read-back, re-fetch, ambient lookup, or
V2 bridge. Migration is all-or-evidence-only; rollback retains evidence without
converting V3 typed payloads.

SNAB-R13 attacks mutate every canonical lane discriminator; each quota at
zero, limit, and limit-plus-one; attempt/proposal ordering and duplicates;
policy/authority substitution; carrier/member omission, extra, reorder, and
digest links; route/source/preparation/segment/resource/manifest joins; and
V3-only registry/reload variants. Memory and independent JSONL vectors publish,
crash/reopen, and compare byte-identical typed request/manifest/result/atomic/
trace closure while spying zero external read-back or ambient reconstruction.

They additionally mutate omitted/unknown/duplicate carrier fields and final
digests, derivation payload-limit authority absence/foreign substitution, and
source-wide proposal versus multi-segment four-lane cardinality. The predicate
and temporal arms are not generic `PredicateEventInventory` or
`TemporalResolution` values: each is a closed V3-native source/segment/
provenance/manifest-bound candidate/result tree with exact spans, quote bytes,
complete native source-field/authority-basis/provenance reference identity and
normalized-value shape, deterministic candidate identity, self-contained
ambiguity alternatives/value-basis keys, status/reason closure, digest, ordering,
and limits. Equal timestamps with unequal authenticated bases remain distinct;
ambiguous alternatives are retained but non-promotable. Each generic candidate/inventory/resolution, generic
route, V2 wrapper, manifest/fingerprint, provenance, segment, source, span,
reference, value, ambiguity, status, order, cardinality, or quota mutation
rejects before interpreter/publication/reopen effects. Each case asserts the
exact authority equality at proposal, lane, request, manifest,
result, atomic, and recovery boundaries before any effect.

The V3 proposal subtree tests mutate every transport request, attempt, subject,
quote, span, evidence, normalized-proposal, and codec field; swap quote/span/
artifact/provenance joins; and cover multi-segment source ordering, ordinal and
proposal duplicates, limit boundaries, V2-wrapper rejection, and memory/JSONL
reopen. The transport normalizer is the sole provider-byte mapping boundary.
Missing, duplicate, foreign, and reordered retained transport requests; swapped
`originating_attempt_digest`; and reordered, duplicate, or quote/span-mismatched
paired evidence items reject. Memory/JSONL reopen proves byte-identical typed
request/attempt/proposal/evidence closure with zero read-back.
They also mutate the single attempt-closure preimage and orphan/unreferenced
transport requests; retry vectors prove shared retained request digest with
distinct ordered attempts. Atomic closure nests requests only in the proposal
payload member.

SNAB-R14 replaces the V3 proposal shell with source-order canonical
`BootstrapProposalMentionV3` plus the closed discriminated operation algebra:
`fact`, `correction`, `retraction`, `action_state`, and `identity`. The exact
V3 records retain predicate ID, entity/literal object, polarity, commitment,
attribution, paired assertion/predicate/action/state/identity/branch evidence,
temporal qualifiers, correction/retraction coupling, action roles/participants,
and identity predecessor/successor/reference-assignment selector/disposition
fields. Every member is digested, quota-bounded, provenance-bound, and joined
to a retained request and originating attempt; it is never a `SemanticProposal`
or generic route wrapper. `BootstrapV3GraphFreeInterpreter` consumes only the
retained V3 proposal and four-lane carriers, emits V3 pre-alignment subjects,
interpretation, and alignment, and performs no V2 decode, generic-route
construction, ambient lookup, or external read-back.

SNAB-R14 vectors cover each discriminator and all sibling substitutions:
predicate/object/commitment/attribution/temporal, correction/retraction target,
action role/state/participant/branch, identity operation/selector/assignment,
and all quoted evidence pairs. They reject cross-kind/segment/provenance/
attempt substitutions; omitted/unknown/extra/duplicate/reordered member or
nested fields; digest and quote/span mutations; catalog-policy substitution;
and every nested byte/count quota at zero, limit, and limit-plus-one. Memory
and independent JSONL reopen vectors assert byte-identical V3 member/subject/
interpretation/alignment closure and zero legacy proposal, generic route,
external read-back, or ambient reconstruction.

R14 also freezes the complete native output subtree rather than treating its
observation/consensus/identity/coverage/dependency names as placeholders:
V3 canonical role and scope/temporal interpretation, two-role observations,
parser/scope/role-temporal consensus, role-consensus sets, operation alignment,
pre-partition mention/assertion/evidence/cluster/resolution, covered/unresolved
predicate-event dispositions, coverage audit, and source dependency group all
have strict fields, domains, ordering, and cardinality in architecture section
3.4.2f.3.1. V3 replaces `proposal_id`, member index, generic route/route-set,
V2 policy-fingerprint, and temporal-resolution-fingerprint joins with retained
proposal/member/operation/provenance/lane identities. Tests serialize, mutate,
and memory/JSONL-reopen every nested type and each replacement field, including
subject-alignment bijections, two-analyzer role spoofing, temporal-role gaps,
identity non-partitions, coverage/dependency under/over-coverage, atomic member
reorder, and prohibited V2/generic construction/read-back.

Parser-consensus vectors additionally require literal primary `stanza` and
corroborating `spacy` roles, each exact retained lane-result digest and typed
analyzer fingerprint, and distinct lane/fingerprint pairs before a stable
assignment. Duplicate, swapped, foreign, omitted, or fingerprint-substituted
lane inputs reject during decode, stable-assignment validation, and atomic
memory/JSONL reload with zero legacy construction or read-back.

Derivation authority has a source-bound CTV digest and yields artifacts retained
by the existing source-normalization generation. Publication authority is a
fresh control-token collection and is neither a new atomic member nor durable
equality input. Existing requests/members bind consumed derivation leaves, and
atomic CAS validates consumed publication leaves.
Its preparation fingerprint is a mandatory publication coordinate field,
preventing a same-source but different-preparation CAS or reopen substitution.

## Production Entrypoint Bindings

| Requirement | Trigger/root | Owner chain | Durable outcome | Proof/caller count | Status |
| --- | --- | --- | --- | --- | --- |
| SNAB-R01-R04 | `ProviderMemoryService.sync_event` -> `ProviderIngestionCoordinator.ingest` | admission -> `bootstrap_writer_handoff` -> atomic found-or-advance-and-claim -> `SourceNormalizationAuthorityProvider.build(invocation,handoff,recovery_claim)` -> `SourceNormalizationExecutionOwner.normalize_after_recovery_claim(...)` -> reservation/producers/stage -> atomic reload | reload or closed typed noncommit | binding artifact records exact future call and current implementation mismatch. | design-specified |
| SNAB-R05 | direct constructor, provider factory, filesystem bundle, Hermes -> provider service | every root requires provider plus runtime; removal reaches `authority_unavailable` only | closed typed noncommit, zero effects | four roots have no current provider/runtime binding. | design-specified |
| SNAB-R06-R08 | atomic reload/recovery and resource reservation | retained closure -> strict decoder/reopen; reservation lives only around one runtime call | exact prior generation or reject | no packet/reservation rebuild during reopen; implementation proof required. | design-specified |
| SNAB-R09 | `ProviderMemoryService.sync_event` -> `ProviderIngestionCoordinator._run_semantic_ingestion` -> `SourceNormalizationAuthorityProvider.build` -> `SealedSourceNormalizationEvidenceProducer.produce` | provider builds binding set under derivation authority; evidence owner projects only matching bootstrap routes | candidate artifacts retain scalar route/binding/resource provenance; recovery reloads it only | existing normal-root caller chain is mapped; route projection remains design-only. | design-specified, not implemented |
| SNAB-R10 | `ProviderMemoryService.sync_event` -> coordinator -> `BootstrapRecoveryClaimRepositoryV3.probe` -> found/unavailable return or claimed-only provider/runtime | probe constructs and hashes the strict V3 ready-control record, derives snapshot then claim, and atomically persists record plus claim; mandatory renewal port gates proposal, every lane, and publish | found reload has zero transient work; claim snapshot alone may authorize publication | current code remains nonconforming until the record/renewal-port migration. | design-specified, not implemented |
| SNAB-R13-R14 | claimed execution -> sealed proposal/four-lane producers -> `BootstrapV3GraphFreeInterpreter.interpret_and_align` -> source-normalization stage -> atomic V3 reload | V3 interpreter expands only retained closed operation members into provenance-keyed subjects/alignment | V3-only operation/interpreter/alignment closure or typed noncommit | design binding updated; no production V3 operation codec, interpreter, or reachability proof exists. | design-specified, not implemented |

## Alternatives Considered

1. Let core discover paths, policies, and controls from process configuration.
   Rejected: mutable unaudited values cannot prove authority.
2. Add all fields to `PreparedSource`. Rejected: immutable admission would be
   conflated with mutable lease/writer/publication controls.
3. Persist the whole packet. Rejected: current authorization and leases would
   pollute durable equality; retained child artifacts already provide history.
4. Reconstruct producer state from a terminal outcome. Rejected: reverses
   candidate/commit order and bypasses graph-free proof.
5. Use one host-issued bundle split into retained derivation and fresh
   publication authority. Accepted: deterministic replay plus current CAS.

## Failure, Security, Compatibility, And Operations

- Malformed packets, stale coordinates, missing policy, unreserved resources,
  revoked authorization, partial runs, or analysis disagreement are typed
  noncommits before graph/terminal access.
- The packet has no credentials or raw source bytes. Diagnostics retain only
  bounded reason codes and safe digests/control coordinates.
- Lost acknowledgement reloads retained members and never issues a new packet.
- Pre-release rollback disables the binding to evidence-only behavior.
  Post-publication bootstrap readers are strict V3 readers with the flattened
  scalar-provenance closure; V1/V2 and mixed readers reject.
- Composition reserves the certified analyzer envelope before construction;
  insufficient capacity is unavailable, not a fallback.

## Verification And Attack Matrix

| Family | Invariant and implementation evidence |
| --- | --- |
| authority completeness | Missing/duplicate/reordered/foreign source, route, policy, registry, or control leaf rejects before lane call. |
| proposal run | Exact segment-route bijection and authorization use points; partial/reordered/wrong-route/producer-missing run noncommits. |
| resource lanes | Manifest/hash/path/language/resource-reservation failure and single-lane/smaller-model fallback reject; expiration/reuse/release reject before a lane call. |
| publication | Fence/lease/writer/progress/preparation/generation mutation, stale CAS, lost acknowledgement, retry, and same/different-request concurrency prove validation and byte-identical reload. |
| promotion/root | Bootstrap handoff cannot mutate ambient config; direct/factory/filesystem/Hermes provider/runtime removal reaches named `authority_unavailable` with zero effects. |
| replay/compatibility | Restart uses retained members only; packet/member/decoder bridge injection and omitted preparation coordinate reject; pre/post-publication rollback is exact. |
| recovery ordering and generation causality | Key/marker/predecessor/control-transition/current-snapshot/lease/writer/progress/claim mutations; found/claimed/unavailable; handoff generation 1 to atomic normalization-ready claim generation 2; non-direct/missing/double advances; found-before-control lost acknowledgement; expired reclaim; claim/publication generation equality; and every swapped adjacent operation prove no transient call on found/unavailable and authority construction only from the store-issued claim snapshot. |
| bootstrap analysis route | One-to-one route/set cardinality, source order, every coordinate/digest, declaration-language equality, resource/capability/four-manifest equality and support, both digest domains, retry/replay/recovery, and lost acknowledgement validate; omission, duplicate, reorder, generic-route encoding, substitution, unsupported language, and result-provenance tampering fail closed with zero lane/producer call where validation precedes it. |
| disclosure | Every failure is tenant-safe and leaks neither source text nor foreign identifiers. |

### Archived pre-V3 topology (non-normative)

The following old selector table and node list are retained only as historical
review provenance. They confer no implementation, CI, recovery, or evidence
authority. Implementation must reject their V1/V2/`Absent` recovery shapes and
must not create any named old selector, job, timing inventory, receipt, or
aggregate. The sole active topology is the V3 inventory later in this WorkPlan.

Archived test ownership was:

| Family | Selector path | PR owner |
| --- | --- | --- |
| packet, producer, noncommit, preparation-coordinate contracts | `tests/unit/core/semantic_ingestion/test_source_normalization_authority.py` | `source-normalization-authority-boundary` |
| bootstrap route binding/set, request-local projection, generic-route exclusion, scalar retained provenance, and replay/recovery zero-rebuild | `tests/unit/core/semantic_ingestion/test_bootstrap_analysis_route_projection.py` and `tests/integration/test_source_normalization_authority_roots.py` | `source-normalization-authority-boundary` |
| recovery probe ordering and mutation matrix; direct/factory/filesystem/Hermes found versus absent; memory/JSONL lost-ack reopen | `tests/unit/core/semantic_ingestion/test_source_normalization_recovery_probe.py`, `tests/integration/test_source_normalization_authority_roots.py`, and `tests/integration/test_source_normalization_authority_recovery.py` | `source-normalization-authority-boundary` |
| dual-clock, nonce, reserve/consume/release, finally paths | `tests/unit/core/semantic_ingestion/test_source_normalization_resource_reservation.py` | `source-normalization-authority-boundary` |
| direct/factory/filesystem/Hermes, memory/JSONL, barriers, lost-ack/reopen/concurrency/rollback | `tests/integration/test_source_normalization_authority_roots.py` | `source-normalization-authority-boundary` |
| collection/count/overlap/timing/receipt/aggregate mutations | `tests/unit/tools/test_source_normalization_authority_gate.py` | same job plus timing and receipt aggregate |

Selector manifest is
`memorii/tests/ci/source-normalization-authority-boundary.json`; its collection
count is generated exactly from collection, never handwritten. Timing owner is
`source-normalization-authority-boundary-timing-inventory` with a 270-second
budget and no initial exemption. Three revision-bound receipts and
`source-normalization-authority-boundary-receipt-aggregate` are mandatory; that
aggregate is a dependency of the existing `source-alignment-producer` aggregate.

Archived node names included
`test_execution_owner_requires_all_constructor_dependencies`,
`test_execution_owner_call_order_and_phase_reason_table`,
`test_reservation_release_runs_once_for_every_phase_exit`,
`test_dual_clock_nonce_is_single_use`,
`test_lost_ack_recovery_does_not_reseal_or_reserve`, and
`test_publication_barriers_assert_linearization`,
`test_recovery_request_rejects_source_preparation_operation_fence_and_generation_mutations`,
`test_recovery_context_and_request_identity_mutations_reject`,
`test_recovery_result_union_rejects_unknown_extra_cross_variant_and_malformed`,
`test_recovery_unavailable_reason_is_closed_safe_and_translates_exactly`,
`test_recovery_wire_nested_types_are_closed_scalar_digest_only`,
`test_recovery_response_arm_digests_and_semantic_validators`,
`test_binding_artifact_matches_canonical_constructor_and_call_signatures`,
`test_recovery_found_and_unavailable_do_not_reseal`,
`test_recovery_absent_alone_advances`, and
`test_recovery_partial_or_ambiguous_index_is_unavailable`. The phase table test mutates
every reason into every wrong phase; the dependency test omits and substitutes
each constructor owner; the order test swaps every adjacent call; the finally
test raises at every phase and asserts one release; and the recovery test spies
for zero trusted-time, reservation, proposal, and evidence calls after a
persisted commit. Recovery wire mutations independently change
`request_identity`, `request_digest`, `derivation_authority_digest`, and
`publication_coordinate_digest`; substitute invocation, handoff, and authority
nested coordinates; use an unknown discriminator, extra field, cross-variant
field, malformed nesting, and raw or unknown reason string; and require decode
rejection or the exact safe `publication_unavailable` digest with zero effects.
The nested-wire inventory test recursively rejects optional fields, open model
types, `Any`, `object`, provider/callable fields, unvalidated digests, and
failure-arm values in the invocation, successful-handoff, authority, context,
request, and every result variant. Response mutations cover every field,
nested field, wrong-arm field, response/reason/index/result/atomic digest, and
generation relation; pre-read binding/request failures make zero repository
reads, while post-read result failures make zero execution/publication effects.

The current revision-bound binding artifact is
`docs/work/semantic_ingestion/source-normalization-authority-bundle-2026-08-10/production-entrypoint-bindings.json`.
The archived recovery-probe proposal added
`test_coordinator_probes_before_authority_provider_build`,
`test_found_probe_makes_zero_bootstrap_binding_reservation_proposal_and_lane_calls`,
`test_unavailable_probe_makes_zero_bootstrap_binding_reservation_proposal_and_lane_calls`,
`test_absent_probe_alone_builds_authority_and_advances`, and
`test_probe_identity_handoff_generation_and_index_mutation_matrix`. The CI
guard must assert these nodes are exclusively selected by the existing
`source-normalization-authority-boundary` manifest, included in its generated
collection/timing inventory, covered by each direct/factory/filesystem/Hermes
root row and memory/JSONL lost-ack reopen rows, and required by the receipt
aggregate; no separate permissive recovery job or timing exemption is allowed.
Implementation must refresh it with exact caller counts before writer work.
Unit contracts own closed reasons/signatures; memory/JSONL integration owns
publication/reopen/lost-ack/concurrency; root tests own public triggers and
zero effects; the CI selector/timing/receipt/aggregate owner remains explicit.

## Identity And Changed-Surface Ledger

| Surface | Identity | Class | Disposition | Proof |
| --- | --- | --- | --- | --- |
| WorkPlan requirements | SNAB-R01-R07 | planning/evidence | retain only here | field-aware identity check |
| Provider/bundle contracts | `SourceNormalizationAuthorityBundle`, `SourceNormalizationAuthorityProvider` | behavioral | accepted | durability test passes |
| Bootstrap route projection contracts | `BootstrapAnalysisRouteBinding`, `BootstrapAnalysisRouteBindingSet`, `BootstrapAnalysisRouteProjection` | behavioral/transient | accepted | exact source/route/resource derivation semantics |
| CTV domains | `source-normalization-derivation-authority.v1`, proposal and consensus authority domains | protocol | accepted | behavior/version-derived |
| Architecture section | 3.4.2f | documentation location | documentation only | no executable identity |

| Path | Surface class | Scope owner | Authority chain | Required gate | Status |
| --- | --- | --- | --- | --- | --- |
| `docs/design/semantic_ingestion_architecture.md` | normative design | this operation | host authority -> producer -> retained artifacts -> CAS/reload | design review | changed |
| this WorkPlan | design WorkPlan | this operation | decision -> design -> review | WorkPlan audit | changed |
| `production-entrypoint-bindings.json` | production-binding artifact | this operation | trigger -> handoff -> authority/runtime -> atomic reload | mapper refresh before code; review now | changed |
| `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/implementation.plan.md` and `docs/work/semantic_ingestion/resume.md` | implementation coordination | parent, linked here | design approval -> implementation resume | link audit | changed |

## Evidence Maturity And Current State

Certified Stanza/spaCy resource manifests and Duckling sidecar contract exist
as lane evidence. The host packet, mandatory runtime signature, and reservation
are specified only. The sealed proposal-run producer is implemented as a
host-injected transport/materialization owner, but no production caller wires
it into the execution owner. Production callers for
`GraphFreeSourceNormalizationStage.normalize` remain zero; no runtime
reachability, persistence closure, or CI claim is made.

## Assumptions And Open Questions

- Verified: stage-required authority exceeds invocation authority.
- Verified: existing retained outputs close durable derivation/publication data.
- Decision: user approved explicit trusted-host packet on 2026-08-10.
- No unresolved semantic decision remains; implementation must follow the
  frozen design and strict contracts.

## Milestone

| Purpose | Bounded scope | Expected artifact | Verification | Status |
| --- | --- | --- | --- | --- |
| Authority-boundary delta | canonical design and implementation pause | architecture section 3.4.2f and this plan | frozen independent review | active |

## Delegation And Cost Ledger

| Role | Work | Consumer | Status |
| --- | --- | --- | --- |
| Terra writer | sole canonical design/plan writer | this delta | active remediation writer |
| Independent cohorts | frozen spec/correctness/test review | approval decision | completed; coordinator validated findings |

## Progress Log

- 2026-08-10: Implemented the bounded trusted-host composition owner. `SourceNormalizationHostBundleBuilder` requires explicit proposal transport/materializer/retry/quote/span dependencies, all four local analysis lanes and interpreter, clocks, reservation limits, authority provider, and the runtime atomic store; it constructs the sealed proposal/evidence producers, recovery repository/stage, reservation provider, and execution owner. Direct provider construction, factory, filesystem, and Hermes each accept the one optional builder and the coordinator consumes only the resulting bundle. The absent path remains `source_alignment_authority_unavailable` before normalization. Focused composition tests, `ruff`, and `py_compile` pass. Parent requirements remain partial: the deterministic full real-adapter memory/JSONL lost-ack fixture is still outstanding.

- 2026-08-10: Added the four-root construction proof in `test_configured_public_roots_construct_the_real_normalization_execution_owner`. Direct construction, factory, filesystem, and Hermes now each instantiate `SourceNormalizationExecutionOwner` through the actual `SourceNormalizationHostBundleBuilder`, with no arbitrary success result. This proves configured reachability only. It does not prove authority issuance, atomic publication/reload, or lost-ack restart; SNAB-R05--R08 remain partial and the graph-dependent coordinator must not treat this as parent completion.

- 2026-08-10: User approved an explicit trusted-host packet. Result: linked
  design created and architecture delta specifies it. Evidence: this plan and
  section 3.4.2f. Next: freeze candidate and run required independent review.
- 2026-08-10: Candidate freeze recorded for the authority-bundle design scope.
  Reviewed revision is `4691c0374b3b01617a6a50fd83d4e3ff8a61aa84`; dirty-tree
  status digest is `4edffc8ca67c802483919269d18b15036bf2db762b7c5f72e7fbf7b3c7442f53`
  and full binary-diff digest is
  `58b65760483a5714fab24992c6a3b9f9a6f68d30b5b1357f2bddab652ab3d225`.
  The frozen architecture bytes are SHA-256
  `e888195750848802dc5eedee21046c29bc68a370560cb16d477fa128e66dec04`.
  The candidate scope is the new section 3.4.2f, its required 3.4.2g reference
  corrections, this WorkPlan, the parent pause/link, and the resume link.
  `git diff --check` passed and symbol/reference/one-next-action inspection
  passed. The required field-aware identity command was run from `memorii/`
  with the canonical allowlist but failed before scanning with
  `ValueError: legacy rejection exception requires an exact rejecting test
  proof`; it is an explicit review-readiness limitation, not a passing gate or
  a defect attributed to this delta. No semantic edit follows this freeze.
- 2026-08-10: Independent specification, correctness, and test cohorts found
  no P1/P2 product defect but confirmed Not-applicable contract-conformance
  gaps: incomplete binding artifact/signature, missing preparation coordinate,
  unspecified resource reservation, incomplete executable matrix, and stale
  identity exception coordinates. The candidate was unfrozen for one coherent
  remediation; architecture, binding artifact, and this plan now own it.
- 2026-08-10: Remediated candidate freeze recorded. Reviewed revision is
  `4691c0374b3b01617a6a50fd83d4e3ff8a61aa84`; dirty-tree status digest is
  `c0012b08b76d36b42a05f4f45a2de50eb3bf2e71bb97a1f9253ae6e148d02422`
  and full binary-diff digest is
  `1fa5aa1b62d1caa76286a81b40f5c86c2f653d769ddff76fb34f25f66acd3768`.
  Frozen architecture bytes are SHA-256
  `5113571399ebdbd8fa7642e33d7ec80e5484bc45fb3fc03eff7d6f22223b1408`;
  the binding artifact is SHA-256
  `f91a3aab23848055cc6bb2366fd9845274725b4af1a865ac778d6085f7135eb4`.
  `git diff --check`, JSON parsing, the field-aware identity gate, and the
  three targeted identity/rejection tests pass. Candidate scope is the revised
  architecture delta, this WorkPlan, binding artifact, exact allowlist repair,
  parent pause update, and resume update. No semantic change follows this
  freeze.
- 2026-08-10: Implemented the bounded sealed proposal transport/materialization
  owner in `sealed_proposal_producer.py`. It accepts only constructor-injected
  transport, request materializer, retry policy, span resolver, and projection
  quote verifier; validates exact authority/request joins; and seals request/
  response artifacts, retry attempts, outcomes, and a route-bijective run.
  Focused success, retry, rejection, and authority-substitution tests pass.
  Binding evidence remains `implemented_not_reachable`: no production root
  constructs the execution owner, so this slice is not runtime-complete.
- 2026-08-10: The first remediation delta review was rejected only because the
  separately owned Duckling debugging operation changed the full dirty-tree
  identity after freeze. That result is a stale-snapshot rejection, not a new
  semantic, correctness, test, or identity finding. After that operation
  completed, the unchanged design was re-frozen at HEAD
  `4691c0374b3b01617a6a50fd83d4e3ff8a61aa84`, dirty-tree status digest
  `393e84494c3d4f9b4f68ae375866eb1b1087f5c4525cb6f1df9355d228bc3bf9`,
  full binary-diff digest
  `1fa5aa1b62d1caa76286a81b40f5c86c2f653d769ddff76fb34f25f66acd3768`,
  architecture SHA-256
  `5113571399ebdbd8fa7642e33d7ec80e5484bc45fb3fc03eff7d6f22223b1408`,
  and entrypoint-binding SHA-256
  `f91a3aab23848055cc6bb2366fd9845274725b4af1a865ac778d6085f7135eb4`.
  `git diff --check`, JSON/reference checks, the field-aware identity gate, and
  the same three targeted identity/rejection tests pass (`3 passed`). No
  semantic design edit occurred between the remediation freeze and this stable
  re-freeze.
- 2026-08-10: Delta-2 reconciliation confirmed specification and test findings
  as Not-applicable `changes_required` contract-conformance gaps for sealed
  producer/resource protocols and executable PR topology. Correctness's
  zero-production-caller observation is a separate process/readiness interlock
  under the candidate-freeze rule, not a semantic defect. The candidate was
  unfrozen only for those bounded contract corrections.
- 2026-08-10: Delta-3 specification finding `DREV-001` confirmed as Not
  applicable, `changes_required`, contract-conformance. Two successive findings
  on execution/reservation authority triggered boundary reconstruction: one
  composition-owned execution owner and closed phase/reason/cleanup/replay
  state machine now replace local protocol patches. The test-review status was
  stale-snapshot only and introduced no test finding.
- 2026-08-10: Delta-3 remediation is complete. This is the final WorkPlan edit
  before candidate identity is computed and independently repeated; the
  terminal freeze evidence is reported to the coordinator without modifying
  this candidate afterward.
- 2026-08-10: Delta-4 test review is clean. Specification `DREV-001` remains a
  confirmed Not-applicable `changes_required` contract-conformance finding:
  the plan retained the obsolete four-argument runtime spelling and recovery
  lacked a typed owner/request/result contract. Remediation aligns the canonical
  three-argument execution call and adds the closed recovery repository,
  recovery-index validation, no-reseal behavior, binding calls, and mutation
  tests. The zero-caller readiness interlock is unchanged.
- 2026-08-10: Delta-4 remediation and WorkPlan reconciliation are complete.
  This is the final repository write before the candidate identity is computed
  and repeated; freeze evidence is reported without modifying the candidate.
- 2026-08-10: The separate implementation owner narrowly repaired the two
  repository identity families that prevented freeze (`c2` local variables and
  the milestone-derived terminal test name). The repository identity gate and
  both affected test files pass. The authority design is semantically unchanged;
  after this administrative entry, its exact stable-tree freeze is computed
  twice and reported without a later repository write.
- 2026-08-10: Delta-5 confirms two Not-applicable `changes_required`
  contract-conformance findings at the recovery boundary. Because this is the
  second successive recovery-boundary finding, the boundary is reconstructed
  as one closed contract: explicit strict validation context, authority-bound
  request identity, closed result variants and safe unavailable reasons, exact
  validation/read/outcome order, non-disclosing noncommit translation, and the
  complete codec and identity mutation family. The zero-caller readiness
  interlock is unchanged.
- 2026-08-10: Delta-6 confirms three Not-applicable `changes_required`
  recovery-wire contract-conformance findings. Remediation replaces broad
  invocation/handoff objects with strict recovery-only scalar/digest bindings,
  admits only successful handoff marker arms, makes every result variant
  self-validating with a response digest, removes per-call context from
  constructor dependencies, records canonical constructor/call signatures,
  and inventories every nested wire type against open/optional/unvalidated
  siblings. The zero-caller readiness interlock is unchanged.
- 2026-08-10: Delta-2 remediation candidate frozen at HEAD
  `4691c0374b3b01617a6a50fd83d4e3ff8a61aa84`, dirty-tree status digest
  `393e84494c3d4f9b4f68ae375866eb1b1087f5c4525cb6f1df9355d228bc3bf9`,
  full binary-diff digest
  `580eec71b92be6a3bb408bceb591e3ad4ed46d301e67b9948bbbbc45b7a96f79`,
  architecture SHA-256
  `bfa444f95a99d31f6fc98c66b4b482aa1e41d126e6b11de93b3239db0d34d0ef`,
  and entrypoint-binding SHA-256
  `05bd5144591864e7587e000c78f267f5a0b5361c0f87e690568831b5b9cbef60`.
  `git diff --check`, JSON/reference checks, and the field-aware identity gate
  pass. No semantic edit follows this freeze.

## Decision Log

- 2026-08-10: Accepted host-issued split authority. Alternatives and
  consequences are recorded above; core remains configuration-free and replay
  excludes current authorization.
- 2026-08-10: Accepted an ephemeral complete-lane reservation instead of a
  persisted reservation artifact. It is required at activation, released after
  one runtime call, and has no replay-equality role.

## Review Log

- 2026-08-10 cohort: all reviewers reported no validated P1/P2 product
  finding. The coordinator confirmed Not-applicable contract-conformance
  findings with `changes_required` or `blocks_approval`: binding artifact and
  callable signature; preparation in the control chain; resource reservation;
  executable matrix; and stale allowlist coordinates. Disposition:
  `contract_conformance_action`. One coherent remediation is applied; delta
  review is required after the next candidate freeze.
- 2026-08-10 first delta attempt: stale-snapshot only. The Duckling debug
  operation changed the shared dirty-tree identity after candidate freeze, so
  the review could not attest one revision. Disposition: evidence invalidated;
  no product or contract finding. The unchanged design is re-frozen above for
  a fresh delta cohort.
- 2026-08-10 delta-2: specification finding confirmed, Not applicable,
  `changes_required`, contract-conformance: sealed producer and reservation
  protocols were incomplete. Test finding confirmed, Not applicable,
  `changes_required`, contract-conformance: exact selector/count/timing/receipt/
  aggregate ownership was incomplete. Correctness zero-caller observation is
  confirmed as process/readiness interlock only: current repository evidence
  shows no production caller, so `.agents/PLANS.md` bars final approval; no
  wrong product behavior or semantic correction is demonstrated.
- 2026-08-10 delta-3: `DREV-001` confirmed, Not applicable,
  `changes_required`, contract-conformance. Correction: canonical execution
  owner, constructor dependency closure, exact run signature/call order,
  trusted dual-clock reservation lifecycle, closed phase-to-reason table,
  unconditional cleanup, recovery/no-reseal edge, binding call inventory, and
  exact missing test nodes. Test review was stale-status only; no test finding
  was accepted. Only specification and test delta review remain eligible.
- 2026-08-10 delta-4: test review clean. Specification `DREV-001` confirmed,
  Not applicable, `changes_required`, contract-conformance. Correction: plan,
  architecture, and binding artifact now agree on the three-argument owner;
  recovery is a strict repository with source/preparation/operation/fence/
  generation/request identity, closed `found|absent|publication_unavailable`,
  exact validation, and no-reseal mutation proof. Only specification delta
  review is eligible.
- 2026-08-10 delta-5: both recovery-contract findings are confirmed, Not
  applicable, `changes_required`, contract-conformance. Correction replaces
  the open recovery edge with an explicit frozen validation context, request
  fields for derivation-authority and publication-coordinate digests, a strict
  discriminated result union, a closed safe unavailable-reason vocabulary and
  bounded digest, exact noncommit translation, and mutation coverage for both
  identity and wire closure. Only affected specification delta review is
  eligible.
- 2026-08-10 delta-6: all three findings are confirmed, Not applicable,
  `changes_required`, contract-conformance. Correction closes the invocation,
  successful-handoff, authority, context, request, and response wire as one
  recursively audited scalar/digest boundary and adds artifact-to-signature
  conformance proof. Only affected specification delta review is eligible.
- 2026-08-10 delta-7: the bounded affected specification review approves the
  frozen authority-bundle contract with no remaining semantic or
  contract-conformance gap. No architecture change is required. The design
  remains blocked solely by the separately classified zero-production-caller
  implementation/readiness interlock.
- 2026-08-10 composition prerequisite: direct inspection confirms one shared
  non-test `ProviderIngestionCoordinator._run_semantic_ingestion` callsite.
  It receives the actual successful `BootstrapWriterHandoffResult`, invokes the
  injected `SourceNormalizationAuthorityProvider`, and passes invocation,
  handoff, and returned authority to the injected
  `SourceNormalizationExecutionOwner`. Direct, factory, filesystem, and Hermes
  roots all reach this callsite through `ProviderMemoryService`; an absent pair
  or unavailable authority fails closed before normalization, terminal, graph,
  or generation effects. The refreshed binding artifact records one caller for
  each root. Four focused public-entry composition checks pass (`4 passed`).
  The zero-production-caller interlock is therefore satisfied and the frozen
  design advances to correctness review without a semantic change.

## Blockers And Limits

The user approved the required product/architecture decisions on 2026-08-10.
The following superseded alternatives remain rejected:

1. Generic-route upcast or implicit provenance: rejected because it obscures
   bootstrap declaration authority and cannot close persisted codecs.
2. Caller-generation-only recovery and snapshot absence: rejected because a
   post-publish retry cannot find a durable result and has no publish ownership.
3. Three-lane reservation: rejected because predicate detection is a required
   local lane with separate manifest authority.
4. Optional legacy normal composition: rejected because it permits an
   authority-free normal path; explicit evidence-only is the limited mode.

Rollout is one unreleased V3 atomic publication of codecs/registry/manifests,
all normal-root constructors, claim index/store migration, vectors, and test
topology. Partial/mixed schemas or roots fail closed to explicit evidence-only.
Rollback disables V3 normal ingestion and selects evidence-only; it neither
decodes a V3 bootstrap record as V1/V2 nor restores the optional legacy API.
The prior reviewer snapshot and named selector/timing/receipt aggregate are
stale planning artifacts, not implementation evidence. Replacement tests and
CI topology must be generated from the finalized V3 collection before code.

The replacement verification matrix must cover: every V3 provenance field and
generic/bootstrap discriminator mutation; V1/V2/mixed decoder rejection and
atomic V3 migration rollback; found-before-generation post-publish retry;
claim issuance, live-foreign denial, expiry/reclaim, nonce replay, CAS consume,
lost acknowledgement, and competing-process schedules; all four reservation
manifest substitutions/omissions; and direct/factory/filesystem/Hermes normal
roots versus the explicit evidence-only root. A future CI manifest is generated
from those collected nodes, with exclusive shard/timing/receipt ownership and
no claimed job name, count, budget, or aggregate until then.

The sole canonical future V3 inventory is one collection with these families:
`bootstrap_v3_codec_and_registry`, `bootstrap_v3_operation_algebra`,
`bootstrap_v3_provenance_projection`,
`bootstrap_recovery_key_and_claim`, `bootstrap_four_lane_reservation`,
`bootstrap_normal_roots`, `bootstrap_evidence_only_roots`, and
`bootstrap_v3_memory_jsonl_reopen`. Each family owns positive, field-mutation,
replay/concurrency, and rollback cases as applicable; one generated manifest,
one generated timing inventory, and one receipt aggregate derive from that
collection. All earlier named selectors, test-node names, shard counts, timing
budgets, receipts, and aggregate dependencies in this WorkPlan are superseded
and must not be copied into implementation or CI.

The one exact future selector is
`memorii/tests/ci/bootstrap-v3-authority-boundary.json`, schema version `1`,
with canonical fields `requirement_id,root,backend,outcome,signal,node_id,pytest_selector`.
Its complete finite node inventory contains exactly 20 entries:
`codec_registry_v3_rejects_v2_mixed`,
`v3_operation_algebra_rejects_v2_and_cross_kind`,
`provenance_projection_all_fields`,
`handoff_marker_authenticates_predecessor`, `probe_found_precedes_current_control`,
`atomic_predecessor_advance_claim_and_reclaim`,
`normalization_ready_record_preimage_and_order`,
`normalization_ready_record_crash_atomicity`,
`claim_control_snapshot_renewal_and_abort`,
`live_claim_before_proposal`, `live_claim_before_stanza`,
`live_claim_before_spacy`, `live_claim_before_predicate`,
`live_claim_before_temporal`, `live_claim_before_publish`,
`four_lane_envelope_mutations`, `normal_root_requires_bundle`,
`evidence_only_has_zero_semantic_effects`, `memory_claim_race_restart`, and
`jsonl_claim_race_restart`. Every node has one row for each applicable root
(`direct,factory,filesystem,hermes`), backend (`memory,jsonl`), outcome
(`found,claimed,unavailable,aborted`), and observable zero-effect or
publication signal; invalid combinations are absent rather than defaulted.
The selector's generated `inventory_count` must equal `20` and is recomputed
from this one list; a handwritten count or a second inventory is forbidden.

The deterministic schedule table is exactly: handoff predecessor generation 1
-> memory two-claimant atomic normalization-ready generation-2 advance/claim ->
crash after claim -> reopen -> publish generation 3/lost-ack -> found;
independent-process JSONL repeats the race -> claim expiry/reclaim over the
byte-identical still-live ready record/snapshot -> crash before/after CAS ->
reopen -> found. An expired embedded lease aborts and requires a new handoff.
Each schedule
mutates marker predecessor, control transition/digest, claim snapshot, nonce,
fence, both generations, lease/writer/progress, both clocks,
provenance, and all four lane manifests, and asserts one winner/zero forbidden
external effects. The planned future job is
`bootstrap-v3-authority-boundary`, collection count derives from the selector,
has one generated timing inventory, three revision-bound receipts, and one
`bootstrap-v3-authority-boundary-aggregate`. These names are design-only:
there is no current job, count, timing, receipt, aggregate, or evidence claim.

This seven-field selector is the sole active planned topology. All earlier
`source-normalization-authority-boundary` rows, old recovery test names,
receipts, timing budgets, and aggregate references are historical and must be
deleted rather than implemented. Active recovery names are only
`BootstrapRecoveryKeyV3`, `BootstrapWriterHandoffMarkerV3`,
`BootstrapRecoveryProbeV3`, `BootstrapNormalizationReadyControlRecordV3`,
`BootstrapRecoveryControlSnapshotV3`,
`BootstrapRecoveryClaimV3`, `BootstrapRecoveryFoundV3`,
`BootstrapRecoveryUnavailableV3`, `BootstrapRecoveryRenewedV3`,
`BootstrapRecoveryAbortedV3`, `BootstrapRecoveryClaimRepositoryV3`, and
`BootstrapRecoveryClaimRenewalPort`; `BootstrapRecoveryClaimedV3` is only the
probe response envelope. Every other recovery symbol and V1/V2/Absent
vocabulary is excluded.

The future `normalization_ready_record_preimage_and_order` selector constructs
the strict version-3 record body, computes its digest, derives the snapshot,
then derives the claim. It rejects snapshot/claim/found/result fields in the
record, every field substitution and reorder, digest-only replacement, and any
store/reload/renew/publish failure to recompute all three layers. Its paired
crash selector proves the atomic probe never exposes record-without-claim or
claim-without-record in memory or independent-process JSONL.

The future `handoff_marker_authenticates_predecessor` selector owns the mandatory
construction vectors: mutating only the V3 marker leaves the immutable recovery
key unchanged; mutating `handoff_request_digest` changes the key and rejects the
marker/probe join; the marker's predecessor generations/control digest cannot be
used as current publication authority; and handoff, atomic generation-2 claim,
generation-3 found, and reopen round-trip byte-identically with the same key.
The paired current-control selector proves generation-1 lease rejection,
store-issued generation-2 snapshot acceptance, caller generation-2 override
rejection, and found-before-current-control lost-ack recovery. These vectors are
future test requirements, not current execution evidence.

Final V3 candidate freeze uses `git status --porcelain=v1 -z` and records
status digest `1615b31a6f4892a454b40b9b26beda4259ffc161b4892494711af917141a34aa`.
This is the last WorkPlan write before review; no later repository edit is part
of this candidate.

The schedule rows are canonical and finite: `same_key_contention`,
`expiry_reclaim`, `lost_ack`, `pre_cas_nonce_abort`, `pre_cas_fence_abort`,
`pre_cas_generation_abort`, `pre_cas_server_clock_abort`,
`pre_cas_monotonic_clock_abort`, `pre_cas_provenance_abort`,
`pre_cas_four_lane_abort`, and `mixed_version_rollback`. Each has two actors
where applicable, named `claim_issued|before_effect|before_cas|after_cas`
barriers, server/monotonic clock values, durable `unclaimed|claimed|found`
state, and forbidden-call assertions. Memory rows are deterministic in-process;
JSONL rows use independently started processes. No schedule has an implicit
retry, default actor, clock, durable state, or permitted external effect.

## Next Action

Freeze the bounded V3 generation-causality correction and request a targeted
specification and correctness review.

Delta-7 changed only WorkPlan review/readiness state. The architecture remains
frozen at the approved delta-6 candidate; the entrypoint artifact has since
been refreshed only with implementation reachability evidence.

- 2026-08-10: Added focused public-entry producer regression coverage for the
  fail-closed missing parser lane and resource-binding/reservation mutation
  family. It exercises `SealedSourceNormalizationEvidenceProducer.produce`
  using a canonical `PreparedSource`, invocation fence, and consumed
  reservation. At the time these unit tests did not constitute production-
  caller evidence; that earlier `implemented_not_reachable` observation is now
  superseded by the inspected shared coordinator callsite and four-root binding
  artifact above.

Composition-prerequisite reconciliation is complete. This is the final
WorkPlan write before the under-review candidate identity is computed and
independently repeated; no repository write may follow the freeze.

- 2026-08-10: Reopened this authority design for the bounded bootstrap
  analysis-route projection amendment. Architecture section 3.4.2f now defines
  strict transient route binding/set authority, exact request-local projection,
  scalar retained provenance, fail-closed behavior, and replay/recovery
  non-reconstruction. The binding artifact records the future canonical owner
  chain. This amendment contains no production or test implementation claim.

- 2026-08-10: Test review confirmed a Not-applicable `blocks_approval`
  recovery-order contradiction: the previous design constructed authority (and
  therefore could construct bootstrap analysis bindings) before recovery. The
  coherent SNAB-R10 remediation makes recovery a coordinator-owned scalar probe
  from successful handoff/invocation/current-generation/index identity only.
  `found`/unavailable terminate before provider construction; absent alone
  builds authority and invokes the renamed runtime method. Architecture,
  production binding, root/mutation matrix, and CI topology now define the
  required implementation proof. The candidate is unfrozen pending a fresh
  full cohort; no production/test implementation is claimed.

- 2026-08-10: SNAB-R10 remediation candidate frozen for a fresh full cohort.
  `git diff --check` and binding-artifact JSON parsing pass. The pre-freeze
  dirty-tree status digest is
  `7f32aace5eab51fcb75df1962709ad04d590c9109eb4f06c1886fdbb25eff0de`;
  architecture and binding-artifact SHA-256 values are respectively
  `081763c8218faf64cbd7980ae1ab349b20bbad5f1b3a8f0037fa2100be23a304` and
  `332f8c87c63011cc8d63e4d3f4a9727d924b2663e2ebc4ee0f142709bb941164`.
  The coordinator records final stable identities and requests the full
  specification/correctness/test cohort. No repository write follows this
  freeze.

- 2026-08-10: Full-review reconciliation confirmed semantic
  `blocks_approval` findings, irrespective of reviewer priority labels. The
  recovery key/current-generation rule cannot recover a post-publish result;
  the transient no-upcast statement conflicts with persisted generic-route
  schemas; absent has no atomic fence-bound expiring publish claim; the
  reservation omitted predicate-event manifest authority; and the asserted
  mandatory normal composition conflicts with optional legacy API surfaces
  without a configuration/migration decision. The review also identified stale
  plan/test topology claims: future selectors, timing inventory, receipts, and
  aggregate names are not current evidence. This WorkPlan is blocked rather
  than selecting a persisted schema, recovery claim, reservation, or public API
  semantic unilaterally.

- 2026-08-10: User approved the recorded resolution. The boundary is
  reconstructed as strict V3 persisted bootstrap scalar provenance outside
  `PreparedSource`; immutable-key found-or-claim recovery with atomic
  fence-bound expiry/reclaim/consumption; four-lane reservation; and mandatory
  normal roots with explicit evidence-only mode. Previous freezes and future
  selector/timing/receipt names are superseded pending a fresh V3 collection.
  No production code, codecs, migration, test, or CI implementation is claimed.

- 2026-08-10: Approved SNAB-R09--R12 reconstruction frozen for full review.
  Scope is architecture section 3.4.2f, this WorkPlan, and the binding ledger.
  The revised candidate replaces the stale recovery/route-projection topology;
  no prior freeze, selector, receipt, or implementation claim applies.

- 2026-08-10: Full-review reconciliation found V2/V3 closure, recovery
  causality/representability, first four-lane, and CI inventory gaps. The
  reconstructed contract now has exhaustive flattened V3 surfaces, handoff-
  minted immutable recovery key and `Found|Claimed|Unavailable` claim/index
  state machine, typed four-manifest envelope, and one canonical future V3
  inventory. Earlier V2 and topology wording is superseded. Implementation
  mismatch observations remain prerequisites only; no code or CI claim is made.

- 2026-08-10: SNAB-COR-01 and SNAB-COR-03 remediation supersedes the remaining
  active old recovery vocabulary with V3 `Probe -> Found|Claimed|Unavailable`,
  adds bounded dual-clock `renew_or_abort` live validation before every external
  effect and publish, and replaces contradictory topology rows with the one
  canonical future selector/schedule contract. Normal-root and V3 production
  implementation remain prerequisites, not design evidence.

- 2026-08-10: SNAB-R09 candidate frozen for independent review. Frozen scope:
  architecture section 3.4.2f, this WorkPlan, and the revision-bound
  production-entrypoint binding artifact. `git diff --check` and JSON parsing
  pass. The candidate is at HEAD `4691c0374b3b01617a6a50fd83d4e3ff8a61aa84`;
  pre-freeze dirty-tree status digest was
  `7f32aace5eab51fcb75df1962709ad04d590c9109eb4f06c1886fdbb25eff0de`.
  The frozen architecture SHA-256 is
  `52835e5ff38c29acf4e90bf33f15f6d83685da708c6cfc060d805f7535e84c74` and
  the binding-artifact SHA-256 is
  `048f3a07e36563d5ef31efd3d860b075fbedc265722dc7c6906f0292a58692fe`;
  the coordinator records the final WorkPlan identity with the reviewer packet.
  Review scope excludes production code and existing unrelated dirty-tree
  changes. The binding entry explicitly records SNAB-R09 as design-specified,
  not implemented; no runtime completion is claimed.

- 2026-08-10: Bounded SNAB-R13/R14 correction closes the remaining bootstrap
  lane escape hatch. The V3 predicate-event and temporal lane payloads are now
  complete native contracts, including their candidate/result/reference/value/
  ambiguity/status/digest/limit rules; the lane union, interpreter, registry,
  reload/migration, and attack matrix explicitly reject generic inventories,
  resolutions, candidates, routes, and V2 wrappers. The binding artifact now
  names the same V3-only consumer boundary. This is a design-only correction;
  no production implementation, codec, public-root, persistence, or test
  evidence is claimed. The candidate is unfrozen until its revised identities
  are recorded and targeted review completes.

- 2026-08-10: Targeted review confirmed that the first native temporal carrier
  still collapsed authenticated reference identity and represented ambiguity
  only as evidence spans. The correction now retains source-field, authority
  basis and provenance, source-context and bootstrap provenance in the reference
  digest; derives each candidate ID from its full value-and-basis closure; and
  retains complete canonical ambiguity alternatives with recomputed value-basis
  keys. Ambiguous alternatives cannot attach or promote. Memory/independent-
  JSONL vectors cover equal-value/different-basis, substitution, duplicates,
  reorder, attachment, reload, and zero-read-back behavior. This remains a
  design-only correction pending targeted review.

- 2026-08-10: Native temporal correction frozen for targeted specification and
  correctness review. `git diff --check` and binding-artifact JSON parsing pass.
  The pre-freeze dirty-tree status-list digest is
  `caa96a1fb655832cd80604307fb06a41e7461cc6ca2488349cc7711d7fee4999`;
  architecture and binding-artifact SHA-256 values are respectively
  `e6e4d55c8eb24ec777584fb328f6165f7d3198ffe915e6fd05e5cda0c7878042`
  and `7882cb12e0703f748b7a64fd0a316d7f07cc5ea63acbe36af1a3d4863dc5d85a`.
  No repository write follows this freeze; no production or test implementation
  is claimed.

- 2026-08-10: Implemented the bounded SNAB-R13/R14 native predicate/temporal
  lane slice. `BootstrapAnalysisSourceEvidenceV3`, native predicate candidate
  and lane payload, native temporal reference/candidate/ambiguity/lane payload,
  their closed codec registrations, and the V3-only lane interpreter are now
  present. The evidence producer converts generic adapter output only at the
  sealing boundary through the bootstrap request projection and persists no
  generic predicate inventory, temporal resolution, candidate, route, or V2
  wrapper. Focused native codec and identity-mutation vectors plus existing V3
  request vectors pass. This slice is locally verified, but not parent-milestone
  complete: the normal public root, atomic V3 recovery/reopen proof, and
  durable memory/JSONL race and restart proof remain pending.

- 2026-08-10: Public-root execution exposed a generation-causality conflict:
  handoff persisted generation 1 as if it remained current, while the
  coordinator advanced control to generation 2 before authority construction.
  The generation-1 lease then failed current-authority validation, while using
  generation 2 violated the claim/publication equality designed around the
  marker. The bounded correction keeps the immutable recovery key, changes the
  marker to authenticate the exact predecessor, and makes the recovery probe
  the single atomic found-first or predecessor-to-normalization-ready
  advance-and-claim transaction. Claimed returns a store-issued current
  control/lease/writer/progress snapshot; authority and publication copy only
  that snapshot. Canonical generation 1 -> claimed generation 2 -> found
  generation 3, concurrency, crash, lost-ack, expiry/reclaim, substitution,
  migration, and memory/independent-JSONL schedules are specified. Existing
  production marker/probe/claim fields are nonconforming implementation
  evidence, not design authority. No code is changed by this correction.

- 2026-08-10: V3 generation-causality correction frozen for targeted
  specification and correctness review. `git diff --check` and binding-artifact
  JSON parsing pass. The coordinator-repository pre-freeze status-list digest is
  `dcbcaebb5f18b716b06cfdb7086a732aa488df94b425488ebc3ff958642536a1`;
  architecture and production-binding SHA-256 values are respectively
  `30712ebc70098532dfb2ca828826e6421e914c40f5a461a22515b39ecca1d8da`
  and `b4d3e96778a98d99734f9a42f3f9537b3eecb24ea817bd21b6ccd38bc866150f`.
  The reviewed delta is design-only: existing production V3 generation fields
  remain nonconforming until the parent implementation resumes after approval.

- 2026-08-10: Targeted generation review found three remaining contract gaps:
  the normalization-ready control state had no independently versioned complete
  record/preimage, live-claim renewal was not a mandatory typed composition
  dependency, and the active atomic-storage text still allowed V2 bootstrap
  interpretation. The bounded correction defines
  `BootstrapNormalizationReadyControlRecordV3`, freezes construction as record
  body -> record digest -> snapshot -> claim in one probe transaction, and
  requires recomputation at store/reload/renew/publish. It adds the claim
  repository and host-facing renewal port to the owner, host builder, and all
  four normal roots; the evidence producer receives the port and returns the
  latest claim or exact abort. Runtime order is now reserve complete envelope ->
  renew -> proposal -> consume -> renew inside each of four lanes -> interpret
  -> renew -> publish. Bootstrap persistence is exclusively the strict V3
  request/member/found/replay/trace family; V2 remains generic-only historical
  storage and mixed forms reject. The sole active planned gate is
  `bootstrap-v3-authority-boundary`; old V1/V2/Absent recovery and selector
  topology are archived as non-normative provenance. This is design-only and
  makes no production or test completion claim.

- 2026-08-10: The generation-record, renewal-port, V3 atomic-family, and gate
  correction is frozen for targeted specification and correctness review.
  `git diff --check` and binding JSON parsing pass. The coordinator-repository
  status-list digest is
  `dcbcaebb5f18b716b06cfdb7086a732aa488df94b425488ebc3ff958642536a1`;
  architecture and production-binding SHA-256 values are respectively
  `b4de39a74b1e345e61529e15f2aad64189d0dccf6caae9865041216b4627fe7c`
  and `0a272ac1a334ebdb23344db6f9552ef3cc514419d7066553376c148985535afa`.
  No repository write follows this freeze in the design-writer task.

- 2026-08-10: Final targeted remediation scopes V2 readers exclusively to
  generic-route checkpoints and makes bootstrap publication/reload/replay/
  trace/rollback V3-only. The active recovery namespace now enumerates the
  ready record, snapshot, key, marker, probe, claim, four result arms,
  repository, and renewal port while rejecting retired symbols. The atomic V3
  family adds the exact `BootstrapSourceNormalizationRequestV3`, keeps the ready
  record in separate control-CAS state, and stores four identically named
  `bootstrap_analysis_lane_result` envelopes in fixed provenance order before
  the native evidence/interpreter/alignment closure. Exact category and run
  order rejects payload, discriminator, and reorder substitution. The selector
  and binding now derive the sole inventory count of 20 from one byte-identical
  canonical list, with count/list mutation required to fail.

- 2026-08-10: Surgical final candidate frozen for targeted specification and
  correctness review. `git diff --check`, binding JSON parse, and the assertion
  that canonical inventory equals selector inventory with count 20 pass. The
  status-list digest is
  `dcbcaebb5f18b716b06cfdb7086a732aa488df94b425488ebc3ff958642536a1`;
  architecture and production-binding SHA-256 values are respectively
  `28759c156bc3ba2a5617b0071d6d46029120663c6bcf3a393f4b5044c22fccaf`
  and `18f3ab7c644c3f30caf11bf01c6c97327d2c60e2275f657d693527d9fe318965`.
  No repository write follows this freeze in the design-writer task.
