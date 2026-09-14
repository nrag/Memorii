# Native Declaration Compatibility Map (Observation Native Closure)

Scope: `docs/design/semantic_ingestion_observation.md` TypeExpr grammar vs current persisted native closure reached from
`IngestionObservationDelta`, `SourceFinalizationObservationDelta`, `GraphRevisionDelta`, and the carrier-set dependencies already in
`docs/work/semantic_ingestion/registry-publication/model-inventory-map.md`.

Verified read-only source lines (2026-09-07):
- `docs/design/semantic_ingestion_observation.md:349-388` (grammar core: map keys, unions, optional/numeric roles)
- `memorii/memorii/core/memory_evolution/graph_effect_contracts.py:92-106`, `453-573`, `576-626`, `331-407`, `444-450`
- `memorii/memorii/core/memory_evolution/graph_records.py:39-49`, `60-64`, `98-158`, `255-267`, `378-433`, `448-461`, `478-484`
- `memorii/memorii/core/memory_evolution/reference_integrity.py:119-148`
- `memorii/memorii/core/semantic_ingestion/contracts.py:2283-2530`, `1177-1230`, `2458-2529`, `529-557`, `383-442`, `4414-4450`
- `memorii/memorii/core/memory_evolution/models.py:289` (`MemoryScope`)
- `memorii/memorii/domain/enums.py:50-60` (`SourceModality`)

## Closure covered
- Roots: `GraphRevisionDelta`, `IngestionObservationDelta`, `SourceFinalizationObservationDelta`, `IngestionObservationRecordMutation`,
  canonical record union members (`CanonicalSourceIntroductionRecord`, `CanonicalOperationIntroductionRecord`, `CanonicalOperationTerminalOutcomeRecord`,
  `CanonicalSourceTerminalOutcomeRecord`)
- Carrier dependencies: `SegmentGovernanceBinding`, `MessageAdmissionIdentity`, `GovernanceCarrierArtifact`,
  `SegmentGovernanceCarrierSet`, `MessageAdmissionCarrierSet`, `RequiredOutcomeScopeSet`
- Graph record chain: `GraphRecordMutation` → `SnapshotGraphRecord` → `canonical_graph_record_adapter` union (`EntityRevision`, `AliasRevision`, `TypeEvidence`, `ClaimAssertion`, `ClaimProjection`, `RelationRevision`, `ActionRevision`, `CitationRecord`, `ProvenanceRecord`, `TemporalTransitionRecord`, `IdentityLineageRecord`, `ReferenceDispositionRecord`)
- Temporal union/timestamps: `OperationTemporalDecisionBinding`, `TemporalReferenceEvidence`, `TemporalEvidenceDecisionClosure` (via closure of temporal records)
- Source spans: `SourceSpanReference` (incl. text artifact/span/proof chain)

## Compatibility table (field-level)

| Native symbol / field | Required TypeExpr form | Status | Evidence path | Notes |
| --- | --- | --- | --- | --- |
| `GraphRevisionDelta.source_ids` / `operation_ids` | `variadic_tuple<string>` | Compatible | `graph_effect_contracts.py:96-99` | Tuples are represented as `variadic_tuple`; ordering and uniqueness checks remain runtime policy only. |
| `GraphRevisionDelta.record_changes` → `GraphRecordChange` → `GraphRecordMutation` | `variadic_tuple<GraphRecordMutation>` | Compatible | `graph_effect_contracts.py:52-64` | Each mutation record is model-root-compatible. |
| `GraphRecordMutation.after_record` | `ModelRef` of `SnapshotGraphRecord` with exact payload alternatives | **Needs explicit declaration shaping** (not directly representable as-is) | `graph_records.py:378-384` | `after_record` is `SnapshotGraphRecord`; `SnapshotGraphRecord.payload` is `BaseModel` and is accepted by `canonical_graph_record_adapter` as a closed union of concrete payload models. Declaration-only schema must wire those payload alternatives explicitly as model refs. |
| `GraphRecordMutation.reference_edges_added|removed` | `variadic_tuple<ReferenceEdgeLedgerEntry>` | Compatible | `graph_effect_contracts.py:61-63`, `reference_integrity.py:119-130` | Tuple-of-model pattern maps to `variadic_tuple`; ordering/uniqueness checks remain runtime policy. |
| `ReferenceEdgeLedgerEntry.sequence` / `record_id` / digest fields | integer / string / string | Compatible | `reference_integrity.py:120-130,138-141` | No non-string map keys, no unsupported container shapes. |
| `IngestionObservationDelta.kind` | `Literal` | Compatible | `graph_effect_contracts.py:483-485` | This field is fixed literal (`terminal_group`); no enum indirection is needed for publication. |
| `IngestionObservationDelta.record_mutations` | `variadic_tuple<IngestionObservationRecordMutation>` | Compatible | `graph_effect_contracts.py:499` | Element model union validated by `record.kind` and `ingestion_record_kind` discriminators. |
| `IngestionObservationRecordMutation.record` (`Annotated[..., Field(discriminator="ingestion_record_kind")]`) | `union` w/ common discriminator field | Compatible | `graph_effect_contracts.py:444-450` | Discriminator + literal payloads present in all variants (`source_introduction`, `operation_introduction`, `operation_terminal_outcome`, `source_terminal_outcome`) satisfies grammar union requirements in docs/design/semantic_ingestion_observation.md:349-388. |
| `CanonicalSourceIntroductionRecord` / `CanonicalOperationIntroductionRecord` / terminal record fields | model refs + strings + optional scalars + digests + tuples | Compatible | `graph_effect_contracts.py:282-347`, `331-349`, `384-410` | Runtime ordering/uniqueness checks do not conflict with grammar; representable with `variadic_tuple` plus policy constraints. |
| `CanonicalOperationTerminalOutcomeRecord.temporal_decision_bindings` / `OperationTemporalDecisionBinding` | `variadic_tuple<OperationTemporalDecisionBinding>` | Compatible | `graph_effect_contracts.py:396-404`, `semantic_ingestion/contracts.py:1177-1184` | Discriminator union inside temporal binding (`reference_evidence`) has shared `kind`. |
| `OperationTemporalDecisionBinding.reference_evidence` | `union` with discriminator `kind` | Compatible | `semantic_ingestion/contracts.py:383-443` | Union alternatives (`authenticated_event_time`/`authenticated_document_time`) each carry matching literal discriminator. |
| `SourceSpanReference` fields (`projection_span`, `segment_local_span`, `text_mapping_proof`, `source_reference`) | model refs + union + optional scalar | Compatible | `semantic_ingestion/contracts.py:4414-4450` | No map-key issues; no non-scalar keys. |
| Carrier sets (`SegmentGovernanceCarrierSet.bindings`, `MessageAdmissionCarrierSet.identities`) | `variadic_tuple<model>` | Compatible | `semantic_ingestion/contracts.py:2317-2320`, `2429-2432` | Tuple ordering/uniqueness are semantic checks, not grammar blockers. |
| `GovernanceCarrierArtifact` fields (`segment_governance`, `message_admissions`, `required_outcome_scopes`, `canonical_payload`) | model refs + bytes + strings | Compatible | `semantic_ingestion/contracts.py:2458-2468` | Bytes fields and nested model refs are directly supported by finite grammar. |
| `RequiredOutcomeScopeSet.scopes` (`tuple[MemoryScope, ...]`) | `variadic_tuple<ModelRef MemoryScope>` | Compatible | `semantic_ingestion/contracts.py:2351-2354`, `memory_evolution/models.py:289`, `semantic_ingestion/contracts.py:12` | `MemoryScope` is a dedicated model imported from `memory_evolution.models`; this is not an enum wire-value field. |
| `SegmentGovernanceBinding.modality` / other `StrEnum` fields | `EnumRef` | Compatible *if enum schema exists* | `semantic_ingestion/contracts.py:2282-2294`, `domain/enums.py:50-60` | `SourceModality` is `StrEnum`; this requires enum declarations and references. |
| `ClaimAssertion` optional authority/trust fields (`claim_identity`, `source_authority_evidence`, `predicate_trust_rule`) | optional models + unions | Compatible (via optional policy) | `semantic_ingestion/contracts.py:1478-1484` and closure from `SnapshotGraphRecord` | Runtime optional semantics map to registered optional policy; omitted vs null remain distinct in profile grammar. |
| `PredicateTrustRule.authority_rank_by_class` / `decay_schedule_by_class` | `map<string, integer>` and `map<string, variadic_tuple<TrustDecayStep>>` | Compatible | `semantic_ingestion/contracts.py:529-538`, `520-527` | Map keys are strings; integer/date/timedelta values map to scalar/derived forms. |

### Incompatibility summary
- No concrete field type in the bounded native closure is structurally incompatible with the finite TypeExpr grammar (strings, ints, bytes, bool, union, model refs, tuple forms, and maps all align).
- One practical closure gap exists: `SnapshotGraphRecord.payload` is typed as `BaseModel` in source (`graph_records.py:381-382`), so declaration-only publication requires explicit closed payload alternatives as `ModelRef` entries (`EntityRevision`, `AliasRevision`, `TypeEvidence`, `ClaimAssertion`, `ClaimProjection`, `RelationRevision`, `ActionRevision`, `CitationRecord`, `ProvenanceRecord`, `TemporalTransitionRecord`, `IdentityLineageRecord`, `ReferenceDispositionRecord`) behind `SnapshotGraphRecord`/`GraphRecordMutation.after_record`.
- No unsupported non-string map keys, union-without-common-discriminator, or recursive graph cycles were observed in this bounded path.

This is a bounded direct-read report of the named roots and immediate native dependencies only; it is not a full transitive compatibility proof.

## Optional-policy / alias clarity
- Optional/nullable fields encountered (`message_admission_identities`, `message_admission_identity`, `predicate_id`, `graph_revision_delta_digest`, `reference_evidence`, etc.) are publication-feasible under registered optional-policy rows; this is not a grammar incompatibility.
- Alias-only symbols in this closure (`CanonicalIngestionObservationRecord` union wrapper, `IngestionObservationRecordKind`, `TemporalReferenceEvidence`) should be represented via their underlying model schemas and discriminator alternatives, not as independent schema roots.

### Bounded source-authoring risk note (not a proved conflict)
- `MemoryScope` used in `RequiredOutcomeScopeSet.scopes` is a model (`memory_evolution.models.MemoryScope`), so it is not an enum-style `EnumRef`.
- `GraphObservationRequest` / `IngestionTimeAttestationRequest` in `graph_observation_contracts.py` (same-owner `MemoryScope` path) also use `MemoryScope` and would carry the same model reference if included in a future source-authoring closure.
- If source-authoring enforces a global "no shared enum definition duplicates" invariant across independent leaf closures, that constraint is a process concern; this bounded read did not re-run the full inventory to prove or disprove a duplicate-definition conflict.
