# Observation Registry Publication Model Inventory Map

Scope: schema publication rows in `docs/design/semantic_ingestion_observation.md` and `docs/work/semantic_ingestion/observation-ledger/schema-publication.md`.

| Root model | Status | Canonical implementation file | Evidence notes |
| --- | --- | --- | --- |
| `ObservationLedgerHead.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/observation_ledger_contracts.py:55` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservationLedgerEntry.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/observation_ledger_contracts.py:234` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservationGroupSemanticPayload.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/observation_ledger_contracts.py:115` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservationSourceSemanticPayload.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/observation_ledger_contracts.py:170` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `IngestionObservationDelta.v1` | `present` | `memorii/memorii/core/memory_evolution/graph_effect_contracts.py:483` | Class exists; canonical owner for ingestion observation deltas.
| `SourceFinalizationObservationDelta.v1` | `present` | `memorii/memorii/core/memory_evolution/graph_effect_contracts.py:576` | Class exists.
| `IngestionObservationRecordMutation.v1` | `present` | `memorii/memorii/core/memory_evolution/graph_effect_contracts.py:453` | Class exists.
| `CanonicalSourceIntroductionRecord.v1` | `present` | `memorii/memorii/core/memory_evolution/graph_effect_contracts.py:282` | Class exists.
| `CanonicalOperationIntroductionRecord.v1` | `present` | `memorii/memorii/core/memory_evolution/graph_effect_contracts.py:331` | Class exists.
| `CanonicalOperationTerminalOutcomeRecord.v1` | `present` | `memorii/memorii/core/memory_evolution/graph_effect_contracts.py:384` | Class exists.
| `CanonicalSourceTerminalOutcomeRecord.v1` | `present` | `memorii/memorii/core/memory_evolution/graph_effect_contracts.py:182` | Class exists.
| `GraphRevisionDelta.v1` | `present` | `memorii/memorii/core/memory_evolution/graph_effect_contracts.py:92` | Class exists.
| `BootstrapGraphNativeProjectionPublicationReceiptV3.v1` | `constructed-unpublished` | `memorii/memorii/core/semantic_ingestion/bootstrap_graph_projection_publication.py:98` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `BootstrapGraphNativeReplayAuthorityEvidenceV3.v1` | `constructed-unpublished` | `memorii/memorii/core/semantic_ingestion/bootstrap_graph_projection_publication.py:137` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `BootstrapGraphNativeReplayCheckpointEvidenceV3.v1` | `constructed-unpublished` | `memorii/memorii/core/semantic_ingestion/bootstrap_graph_projection_publication.py:148` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `SourceObservationIntent.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/observation_ledger_contracts.py:275` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservationLedgerActivation.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/observation_ledger_contracts.py:282` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ReferenceEdgeLedgerEntry.v1` | `present` | `memorii/memorii/core/memory_evolution/reference_integrity.py:119` | Class exists and used as dependency.
| `GraphRecordMutation.v1` | `present` | `memorii/memorii/core/memory_evolution/graph_effect_contracts.py:52` | Class exists.
| `SegmentGovernanceBinding.v1` | `present` | `memorii/memorii/core/semantic_ingestion/contracts.py:2283` | Class exists.
| `MessageAdmissionIdentity.v1` | `present` | `memorii/memorii/core/semantic_ingestion/contracts.py:2397` | Class exists.
| `GovernanceCarrierArtifact.v1` | `present` | `memorii/memorii/core/semantic_ingestion/contracts.py:2458` | Class exists.
| `SegmentGovernanceCarrierSet.v1` | `present` | `memorii/memorii/core/semantic_ingestion/contracts.py:2317` | Class exists.
| `MessageAdmissionCarrierSet.v1` | `present` | `memorii/memorii/core/semantic_ingestion/contracts.py:2429` | Class exists.
| `RequiredOutcomeScopeSet.v1` | `present` | `memorii/memorii/core/semantic_ingestion/contracts.py:2351` | Class exists.
| `SourceSpanReference.v1` | `present` | `memorii/memorii/core/semantic_ingestion/contracts.py:4414` | Class exists.
| `OperationTemporalDecisionBinding.v1` | `present` | `memorii/memorii/core/semantic_ingestion/contracts.py:1177` | Class exists.
| `ObservationReplayState.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/observation_replay_contracts.py:60` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `IngestionObservationReplayCheckpoint.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/observation_replay_contracts.py:106` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservationCheckpointLifecycle.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/observation_replay_contracts.py:125` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservationCheckpointSigningPreimage.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/observation_replay_contracts.py:144` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservationCheckpointPublicationReceipt.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/observation_replay_contracts.py:182` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservationCheckpointBundle.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/observation_replay_contracts.py:193` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `AuthenticatedGraphObservationContext.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_public_contracts.py:55` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `GraphObservationAuthorizationDecision.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_public_contracts.py:63` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `GraphObservationPagePolicySnapshot.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_public_contracts.py:78` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `GraphObservationCohortSelector.v1` | `present` | `memorii/memorii/core/memory_evolution/graph_observation_contracts.py:156` | Class exists.
| `ResolvedGraphObservationCohort.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_snapshot_contracts.py:117` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `GraphObservationRequest.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_public_contracts.py:119` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `IngestionTimeAttestationRequest.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_public_contracts.py:123` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `GraphObservationFailure.v1` | `present` | `memorii/memorii/core/memory_evolution/graph_observation_contracts.py:150` | Class exists.
| `GraphObservationCursorPayload.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_snapshot_contracts.py:121` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `GraphObservationCohortPreimage.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_snapshot_contracts.py:113` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `GraphRecordObservationSnapshot.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_public_contracts.py:154` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `IngestionTimeObservationSnapshot.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_public_contracts.py:190` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `GraphObservationRequestCoordinates.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_public_contracts.py:93` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `IngestionTimeAttestationRequestCoordinates.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_public_contracts.py:111` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `GraphObservationRecordKey.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_snapshot_contracts.py:50` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `GraphObservationPage.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_public_contracts.py:245` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `IngestionTimeAttestationPage.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_public_contracts.py:292` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `SourceRetentionTimeAttestation.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_ingestion_time_contracts.py:26` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `TransactionGroupCommitTimeAttestation.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_ingestion_time_contracts.py:43` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservedEntityReference.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_records.py:44` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservedAssertionEntityReference.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_records.py:50` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservedEntityRevision.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_records.py:55` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservedAliasRevision.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_records.py:68` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservedTypeEvidence.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_records.py:81` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservedClaimAssertion.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_records.py:95` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservedTemporalClaimProjection.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_records.py:120` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservedTrustClaimProjection.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_records.py:151` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservedRelation.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_records.py:182` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservedActionRoleBinding.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_records.py:209` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservedActionRevision.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_records.py:215` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservedCitationRecord.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_records.py:234` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservedProvenanceRecord.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_records.py:245` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservedTemporalTransition.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_records.py:285` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservedCertifiedTextEffectiveTime.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_records.py:258` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservedAuthenticatedReferenceEffectiveTime.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_records.py:265` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservedSystemRecordedEffectiveTime.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_records.py:272` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservedIdentityTransition.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_records.py:303` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservedReferenceDisposition.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_observation_records.py:318` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservedSourceIntroduction.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_ingestion_observation_records.py:27` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservedOperationIntroduction.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_ingestion_observation_records.py:107` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservedOperationTerminalOutcome.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_ingestion_observation_records.py:123` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservedSourceTerminalOutcome.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_ingestion_observation_records.py:144` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `ObservedSourceOutcomeConsistencyAssessment.v1` | `constructed-unpublished` | `memorii/memorii/core/memory_evolution/graph_ingestion_observation_records.py:182` | Explicit profile-3 body owner; protected decoder, complete source declaration and runtime binding remain unverified. |
| `GraphObservationStreamRecord` | `constructed-alias` | `memorii/memorii/core/memory_evolution/graph_observation_streams.py` | Explicit 17-variant discriminated union; declaration publication remains incomplete. |
| `GraphObservationRecordKind` | `alias-only` | `memorii/memorii/core/memory_evolution/graph_observation_contracts.py:18` | `typing.Literal[...]` enum-like alias, not a root schema.

## AST/schema-source authoring-tool assessment

- `memorii/memorii/tools/semantic_ingestion_ctv_reference_compiler.py` exists, but this is the fixture-56/profile-2 binding authority compiler (`AUTHORITY_FORMAT = memorii-sia-ctv-binding-authority-v2`, `PROFILE_VERSION = 2`) and is explicitly separate from the observation-3 publication path.
- `memorii/memorii/core/memory_evolution/typed_value_declarations.py` accepts one declaration object at a time for runtime intake; it does not compile a complete source package with root sets, policy blocks, enum tables, and signed digests.
- `memorii/memorii/tools/semantic_ingestion_traceability.py` and `.../semantic_ingestion_traceability_registry.py` parse traceability/registry documents, not schema declaration package compilation.
- Result: no existing complete AST/schema-source declaration packager was found for the observation-3 publication roots; no fixture-56 tool should be reused for this path.

## Coordinator Conformance Note

Presence is not conformance. The existing ResolvedGraphObservationCohort and
GraphObservationCursorPayload predate the approved full-write snapshot and
separate-projection extensions. They require profile-3 construction/dispatch
without mutating historical cursor bytes. The model map is bounded discovery,
not an authoritative declaration source or proof of complete recursive closure.

Acceptance witness types are excluded by ../time-witness-boundary/closure.md.
The current production authoring inventory has 78 explicit roots and 180 total
root/helper schemas; decoder-owner-inventory.json records their finite native
class owners for static code construction, not runtime publication.
