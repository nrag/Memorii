# Observation Schema Publication Inventory

Status: design construction under the approved profile-3 direction. This is a
finite publication inventory for registry generation. It does not publish a
registry, assign a digest, enable ledger writes, or claim the parent ledger
complete.

## Publication Rule

Every row below is one `semantic_ingestion_typed_value` profile-3 registry entry
with `schema_version=1`. The schema ID is the value in the table, without its
`.v1` suffix. A row is emitted only after its complete recursive TypeExpr
closure, enum table, optional policy, numeric policy, digest/signature policy,
and decoder source identity have been authored under the grammar in
`operational-profile.md`. An entry contains its own root schema plus the
transitive schemas referenced from that root; a nested root is not copied into a
second hand-maintained declaration.

Each durable or public body has `read_status=active` once its owning capability
is enabled. Profile-2 diagnostic/history readers remain separately registered
historical routes and receive no profile-3 upcast. A schema may be loaded for
replay only after its original profile/binding/entry verifies; no profile-3
schema relabels a legacy local-observation chain as global audit.

All `*_digest` fields below use the profile declaration's `sha256` string
lexical rule. `schema_version`, sequence, stream position, page size and record
version use the exact integer TypeExpr with the stated nonnegative/positive
bound; they are never booleans. Every tuple remains a tuple in the schema
declaration, not a set inferred from a Python collection. Nullable values use
the registered optional policy, so omitted and null stay distinct.

## Durable Ledger And Terminal Roots

| Schema ID | Source field authority | Digest/signature policy | Transitive closure owner |
| --- | --- | --- | --- |
| `ObservationLedgerHead.v1` | `closed-contracts.md`, Store Record Schemas: repository, activation, sequence, revision, predecessor coordinates and head digest. | `head_digest` excludes only itself; no signature. | Observation persistence owns the root; strings and integer rules are profile-owned. |
| `ObservationLedgerEntry.v1` | `closed-contracts.md`: exact predecessor, semantic payload, result locator/result digest and entry digest. | `entry_digest` excludes only itself; no signature. | Observation persistence owns the root; `CanonicalIngestionObservationDelta` and `ObservationResultLocator` are dependencies. |
| `ObservationGroupSemanticPayload.v1`, `ObservationSourceSemanticPayload.v1` | `closed-contracts.md`: separate model roots with `terminal_group`/`source_finalization` literals and delta fields minus `observation_revision_before`, `observation_revision_after`, and `delta_digest`. | The external semantic payload digest binds the selected complete binding and body; no self field exists. | Observation contracts own the two models; ObservationLedgerSemanticPayload is only their union alias. |
| `IngestionObservationDelta.v1` | SIA Section 3.15.1 observation contract (`IngestionObservationDelta`): group delta fields, exact operation membership, graph delta link and record mutations. | Existing native digest fields are ordinary profile-3 fields; the pinned canonical native decoder validates them under their original domain and byte grammar. | Graph-effect contracts own `IngestionObservationRecordMutation`, canonical record union, governance and graph-delta link types. |
| `SourceFinalizationObservationDelta.v1` | SIA Section 3.15.1 observation contract (`SourceFinalizationObservationDelta`): source/delivery/governance carriers, operation IDs and full source outcome. | Existing native digest fields are ordinary profile-3 fields; the pinned canonical native decoder validates them under their original domain and byte grammar. | Graph-effect contracts own the source-terminal record plus carrier sets. |
| `IngestionObservationRecordMutation.v1` | SIA Section 3.15.1 observation contract (`IngestionObservationRecordMutation`): create-only kind, record kind/ID/version/body/digest. | Existing native digest fields are ordinary profile-3 fields; the pinned canonical native decoder validates them under their original domain and byte grammar. | Graph-effect contracts own the discriminated canonical record union. |
| `CanonicalSourceIntroductionRecord.v1` | SIA Section 3.15.1 observation contract, class of the same name. | Existing native digest fields are ordinary profile-3 fields; the pinned canonical native decoder validates them under their original domain and byte grammar. | Graph-effect contracts own governance, admission, source span and canonical identity dependencies. |
| `CanonicalOperationIntroductionRecord.v1` | SIA Section 3.15.1 observation contract, class of the same name. | Existing native digest fields are ordinary profile-3 fields; the pinned canonical native decoder validates them under their original domain and byte grammar. | Graph-effect contracts own ordered governance/admission/source-span dependencies. |
| `CanonicalOperationTerminalOutcomeRecord.v1` | SIA Section 3.15.1 observation contract, class of the same name. | Existing native digest fields are ordinary profile-3 fields; the pinned canonical native decoder validates them under their original domain and byte grammar. | Graph-effect contracts own terminal status, temporal-decision and lineage dependencies. |
| `CanonicalSourceTerminalOutcomeRecord.v1` | SIA Section 3.15.1 observation contract, class of the same name. | Existing native digest fields are ordinary profile-3 fields; the pinned canonical native decoder validates them under their original domain and byte grammar. | Graph-effect contracts own complete carrier sets, required scopes, operation/group result membership. |
| `GraphRevisionDelta.v1` | SIA22842-22855. | Existing native digest fields are ordinary profile-3 fields; the pinned canonical native decoder validates them under their original domain and byte grammar. | Graph-effect contracts own record changes, reference-edge entries, governance/admission and graph records. |
| `SourceObservationIntent.v1` | `closed-contracts.md`, Terminal Intent And Receipt Grammar. | `intent_digest` excludes only itself. | Native terminal contracts own the root; canonical source outcome and active schema fingerprint are dependencies. |
| `ObservationLedgerActivation.v1` | `closed-contracts.md`, Activation And Writer Fencing. | `activation_digest` excludes only itself. | Writer admission owns drain inventory, target epoch and writer/schema/codec fingerprints. |

### Native Value Compatibility

Native graph/effect values are exact owner-validated embedded values. Profile 3
commits all their bytes, including their native digest fields, as ordinary fields.
It never computes those native digests using a profile-3 binding. The finite
static decoder table invokes the exact existing canonical model owner, including
its complete native digest validation. The pinned decoder implementation source
closure includes these native validators and their canonical encoder; registry
data cannot select a callback or supply a digest algorithm. The table is finite
and checked against the publication inventory, not the fixture-56 compiler.

This rule also covers transitive existing graph records and carrier values.
New ledger head/entry/state/intent/activation and public observation outputs use
their declared profile-3 policies. Creating a post-activation ledger entry around
a newly committed native delta is supported; wrapping historical terminal1/2
results to fabricate global audit is forbidden. Verification must discriminate
valid native nesting, changed body with retained digest, substituted profile-3
hash, unknown owner/version and forbidden historical wrapping.

### Exact Durable Dependencies

The following are roots already named by SIA and must be published as separate
entries when they occur as an artifact body: `ReferenceEdgeLedgerEntry.v1`,
`GraphRecordMutation.v1`, `SegmentGovernanceBinding.v1`,
`MessageAdmissionIdentity.v1`, `GovernanceCarrierArtifact.v1`,
`SegmentGovernanceCarrierSet.v1`, `MessageAdmissionCarrierSet.v1`,
`RequiredOutcomeScopeSet.v1`, `SourceSpanReference.v1`, and
`OperationTemporalDecisionBinding.v1`. Their field authority remains the
existing SIA definitions; the observation registry does not duplicate them or
loosen their fields. If a dependency is only nested, its declaration remains in
the consuming root's transitive schema closure and does not create an independent
write endpoint.

## Replay, Checkpoint And Activation-Read Roots

| Schema ID | Source field authority | Digest/signature policy | Transitive closure owner |
| --- | --- | --- | --- |
| `ObservationReplayState.v1` | `replay-snapshot-contract.md`, Replay State Grammar. | `state_digest` excludes only itself. | Observation replay owns head, ordered entries and ordered canonical audit records. |
| `IngestionObservationReplayCheckpoint.v1` | SIA23010-23022 and the replay-snapshot signing supplement. | `checkpoint_digest` commits the registered checkpoint signing preimage, excluding the checkpoint digest and signature; including the signature here would create a cycle. | Observation replay owns the checkpoint body and typed head/replay links. |
| `ObservationCheckpointLifecycle.v1` | `replay-snapshot-contract.md`, Checkpoint And Signature Dependency Order. | `authority_digest` excludes only itself. | Observation replay authority owns lifecycle history/current authority. |
| `ObservationCheckpointSigningPreimage.v1` | `replay-snapshot-contract.md`: exact purpose `observation_checkpoint`, repository/activation/sequence/head/lifecycle and checkpoint fields excluding checkpoint digest/signature. | It is the signed preimage; it has no self digest or signature field. | Observation replay authority owns purpose and lifecycle; replay owns the state/checkpoint closure. |
| `ObservationCheckpointPublicationReceipt.v1` | `replay-snapshot-contract.md`: exact repository/activation/checkpoint/lifecycle/state/head receipt fields. | `receipt_digest` excludes only itself. | Observation replay authority owns publication receipt. |
| `ObservationCheckpointBundle.v1` | `replay-snapshot-contract.md`: schema version, repository, activation, sequence, head, replay state, checkpoint, lifecycle, receipt and bundle digest. | `bundle_digest` excludes only itself; it includes the signed checkpoint and receipt. | Observation replay owns the root and all checkpoint dependencies. |

No checkpoint schema receives a generic signature exclusion. The checkpoint
policy explicitly selects ObservationCheckpointSigningPreimage as its preimage
owner, including the external lifecycle and head coordinates required by the
replay-snapshot supplement. The preimage has no self-digest or signature field.
Bundle and receipt policies include their referenced checkpoint digest and
signature wherever declared; they cannot inherit the checkpoint exclusion.

## Public Observation And Retrieval Roots

SIA31314-31815 is the field authority for every public request, cursor, page,
failure and observed payload below. The schema IDs deliberately match the
normative class names, which gives registry generation a stable, finite list.

| Family | Root schema IDs |
| --- | --- |
| Authorization and request | `AuthenticatedGraphObservationContext.v1`, `GraphObservationAuthorizationDecision.v1`, `GraphObservationPagePolicySnapshot.v1`, `GraphObservationCohortSelector.v1`, `ResolvedGraphObservationCohort.v1`, `GraphObservationRequest.v1`, `IngestionTimeAttestationRequest.v1`, `GraphObservationFailure.v1` |
| Cursor, cohort and retained snapshot | `GraphObservationCursorPayload.v1`, `GraphObservationCohortPreimage.v1`, `GraphRecordObservationSnapshot.v1`, `IngestionTimeObservationSnapshot.v1`, `GraphObservationRequestCoordinates.v1`, `IngestionTimeAttestationRequestCoordinates.v1`, `GraphObservationRecordKey.v1` |
| Stream and responses | `GraphObservationPage.v1`, `IngestionTimeAttestationPage.v1`, `SourceRetentionTimeAttestation.v1`, `TransactionGroupCommitTimeAttestation.v1`, `SourceRetentionTimeWitness.v1`; `GraphObservationStreamRecord` is the closed stream-variant type alias below, never a registry root. |
| Structural payloads | `ObservedEntityReference.v1`, `ObservedAssertionEntityReference.v1`, `ObservedEntityRevision.v1`, `ObservedAliasRevision.v1`, `ObservedTypeEvidence.v1`, `ObservedClaimAssertion.v1`, `ObservedTemporalClaimProjection.v1`, `ObservedTrustClaimProjection.v1`, `ObservedRelation.v1`, `ObservedActionRoleBinding.v1`, `ObservedActionRevision.v1`, `ObservedCitationRecord.v1`, `ObservedProvenanceRecord.v1`, `ObservedTemporalTransition.v1`, `ObservedCertifiedTextEffectiveTime.v1`, `ObservedAuthenticatedReferenceEffectiveTime.v1`, `ObservedSystemRecordedEffectiveTime.v1`, `ObservedIdentityTransition.v1`, `ObservedReferenceDisposition.v1` |
| Ingestion payloads and assessment | `ObservedSourceIntroduction.v1`, `ObservedOperationIntroduction.v1`, `ObservedOperationTerminalOutcome.v1`, `ObservedSourceTerminalOutcome.v1`, `ObservedSourceOutcomeConsistencyAssessment.v1` |

`GraphObservationCohortPreimage.v1` has exactly the replay-snapshot supplement
fields: all resolved-cohort fields except `cohort_digest`, snapshot graph and
observation revisions, full memory-plane write revision, exact temporal and
trust generation digests, exact temporal and trust pointer digests, observation
schema fingerprint, and disjoint sorted unique
`changed_record_keys`/`boundary_record_keys`. Its `cohort_digest` policy is
external to the preimage model, which has no self-digest field. The public
ResolvedGraphObservationCohort now includes every one of these coordinates,
as declared in replay-snapshot-contract.md, and uses its own registered
self_digest binding over all fields except cohort_digest. The stream
retains each selected generation and complete pointer in its corresponding
projection record; the cohort commits their digest coordinates without
constructing a combined projection state.
The two snapshot model roots have exactly the server-owned
fields in that supplement: schema version, snapshot token, protected creation
time, `memory_plane_write_revision` as a nonnegative integer, authenticated context digest, purpose,
authorization decision, cursor-free request, cohort preimage/resolved cohort,
and one immutable discriminated stream. Its `purpose` is exactly
`graph_observation` or `ingestion_time_attestation`, matching the authorizer
purpose literal in SIA31391; the former permits only
`GraphObservationStreamRecord` items and the latter only
`ProductionIngestionTimeAttestation` items. Their exact request-coordinate and
stream types are declared in replay-snapshot-contract.md; the GraphObservationSnapshot
union alias is not a registry root. This is retained server state, not a
caller-supplied body. Its snapshot token is not a digest or authorization
substitute.

All public `record_digest`, `page_digest`, `assessment_digest`, `decision_digest`
and `policy_digest` fields exclude only their own named field. `GraphObservation-
CursorPayload.v1` is signed under the cursor purpose; its signature preimage is
the complete cursor payload excluding only `signature`. The request and page
schemas have no implicit defaults, and the page's stream-record payload union is
exactly discriminated by `GraphObservationRecordKind` with matching outer kind,
primary key and record digest as required by SIA31912-31917.

The user-approved profile-3 observation route replaces the legacy
`claim_projection` stream kind with `temporal_claim_projection` and
`trust_claim_projection`. `ObservedTemporalClaimProjection.v1` has exactly
`observation_id`, complete owner-validated `TemporalProjectionRecord`, its
native `generation_digest`, complete owner-validated
`ActiveTemporalProjectionPointer`, same-kind
`successor_publication_pointer` or null, `boundary`, and `record_digest`.
`ObservedTrustClaimProjection.v1` has the corresponding complete
`TrustProjectionRecord`, `generation_digest`,
`ActiveTrustProjectionPointer`, same-kind successor pointer or null, boundary,
and record digest. In both cases `observation_id` is the profile-bound content
address of projection kind, repository, native generation digest, and native
projection digest; it is the stream primary key. The native `projection_id`,
publication time/sequence, policy fingerprint, transition reason encoded by
the pointer's `publication_kind`, and all native digests stay in their native
values. The adapter neither combines selections nor creates a transition reason.
Profile-2 and the existing `ObservedClaimProjection` bytes keep their historical
read routes and are never relabelled as either profile-3 model.

The approved decision is the profile-3 public-field authority for this
replacement. `semantic_state.py` owns the native projection, generation, and
pointer shapes (`TemporalProjectionRecord`, `TrustProjectionRecord`, their
generation models, and their active/history pointers);
`projection_history.py` owns the canonical selection and pointer-history rules.
No profile declaration duplicates or weakens those native validators.

`GraphObservationStreamRecord` is the following type alias, not a model root:

```text
GraphObservationStreamRecord =
  EntityRevisionStreamRecord | AliasRevisionStreamRecord |
  TypeEvidenceStreamRecord | ClaimAssertionStreamRecord |
  TemporalClaimProjectionStreamRecord | TrustClaimProjectionStreamRecord |
  RelationStreamRecord | ActionRevisionStreamRecord | CitationStreamRecord |
  ProvenanceStreamRecord | TemporalTransitionStreamRecord |
  IdentityTransitionStreamRecord | ReferenceDispositionStreamRecord |
  SourceIntroductionStreamRecord | OperationIntroductionStreamRecord |
  OperationTerminalOutcomeStreamRecord | SourceTerminalOutcomeStreamRecord
```

Every listed variant is an explicit profile-3 model in the enclosing page and
snapshot closure with exactly `record_kind`, `primary_key`, `record_digest`, and
`payload`. Its `record_kind` is respectively the literal
`entity_revision`, `alias_revision`, `type_evidence`, `claim_assertion`,
`temporal_claim_projection`, `trust_claim_projection`, `relation`,
`action_revision`, `citation`, `provenance`, `temporal_transition`,
`identity_transition`, `reference_disposition`, `source_introduction`,
`operation_introduction`, `operation_terminal_outcome`, or
`source_terminal_outcome`; its payload is respectively the like-named
`Observed...` model in the same order. The projection variants use only the two
new projection models above. A union alternative is selected by its literal
`record_kind`, and validates that `primary_key` equals the payload canonical
primary key and `record_digest` equals the payload record digest. There is no
generic `payload` union, implicit kind/payload pairing, or independent stream
record root.

`GraphObservationRecordKind` in every profile-3 request, cursor, cohort,
snapshot, page, and stream declaration is exactly the seventeen literals above.
In particular, cursor `preceding_record_kind` uses that closed enum and cannot
carry `claim_projection`; an existing legacy cursor remains readable only by its
historical profile route.

## Source-to-Decoder Construction

The profile compiler takes a checked-in source package with one role per root
above: `schema/`, `enum/`, `optional/`, `numeric/`, `digest-signature/`,
`decoder/`, and null-only `upcast/`, plus the one profile grammar/registry role
defined in `operational-profile.md`. It rejects an inventory item missing any
role, a role not named here, duplicate coordinate, unresolved model/enum
reference, cycle, or a non-null profile-3 upcast.

For each root, `decoder/<schema>/<version>` names a stable decoder ID of the
form `memorii.semantic_ingestion.observation.<schema>.v1` and commits an
implementation-source digest. That digest is calculated by the publication
builder from the exact decoder source region selected by the checked-in decoder
manifest; it excludes generated profile/registry declaration constants, so it
cannot self-hash. At runtime `ingestion_contracts.py` contains the closed static
decoder-ID-to-decoder table and compares the source-published identity/digest
before publication. It does not import a module from registry data, inspect
annotations, or reflect a model. Nested decoder calls occur only after the root
binding is resolved and each nested TypeExpr reference is already in the verified
closure.

The deployment publication is deterministic:

1. Sort roots by `(schema_id, schema_version)` and emit every raw declaration
   source byte file under the profile's no-LF/RFC-8785 source rules.
2. Recompute closure fingerprints, policy digests, bindings and entry digests;
   sort entries by the same coordinate; then compute the profile-3 registry
   digest using the exact LP preimage in `operational-profile.md`.
3. Emit the exact external publication_manifest shape from operational-profile.md:
   role, profile_id, profile_version, ordered files (role and sha256), and
   registry_digest. The registry role already commits ordered entry digests;
   they are not repeated as undeclared manifest fields.
4. Protected deployment configuration supplies exactly publication_manifest_digest,
   registry_digest, and independent_vector_manifest_digest as lowercase SHA-256
   strings. These pins are deployment inputs, outside the source-role manifest.
   The vector manifest commits vector inputs, complete expected output bytes,
   independent implementation source identity and allowed shared inputs. A
   process verifies publication and registry pins before exposing the registry;
   release/package verification separately proves the vector manifest and
   independent parity. Requests cannot override any pin.

The real construction root is `ProviderMemoryService` in
`memorii/core/provider/service.py`: ordinary initialization invokes
`BuiltInLocalHostSemanticIngestionCapability.build_semantic_ingestion_runtime`
when verified host material and the bootstrap profile are present. That method
in `memorii/core/semantic_ingestion/capability.py` constructs the paired
`SemanticWriterAdmissionStore` and `SemanticIngestionAtomicStore`. Ledger mode
must add one required verified-registry parameter to this existing construction
path, verify the pinned registry once, and pass the same immutable object to
writer admission, atomic store, observation replay, and the public observation
service. An absent/mismatched registry leaves ledger mode unavailable; it must
not select a profile from a request or fall back to profile 2. The future
`ProviderMemoryService.observe_graph` and
`observe_ingestion_time_attestations` entrypoints receive the same configured
registry and protected authorizer/page/cursor configuration before taking the
memory-plane snapshot.

## Locator And Cursor Closure

The closed-contracts supplement declares ObservationGroupResultLocator and
ObservationSourceResultLocator as the two alternatives of ObservationResultLocator,
including exact native record identity recomputation and result-digest selection.
Both alternatives have their own schema roles in the entry's transitive closure.

The profile-3 cursor signing purpose is `graph_observation_cursor` and its domain
is `memorii.graph-observation.cursor.v3`. The signing preimage is the complete
registered cursor payload minus only signature; it includes the full binding
and purpose under the profile signing rules. This new registered route does not
reuse the foundation's unregistered `v1` wire signature domain. Existing v1
codec tests remain foundation evidence only. Profile-3 issuance and verification
must agree on the new route; an active profile-3 endpoint rejects a v1 cursor.
Snapshot purpose remains graph_observation or ingestion_time_attestation.

Raw declaration sources, decoder snapshots and full independent vectors remain
unpublished. This inventory closes names and field ownership; it does not claim
that complete source bytes or runnable registry generation already exist.
