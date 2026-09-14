# Observed Payload Projection Map

Coordinator-reconciled read-only map. The earlier delegate draft used nonexistent
effect type names and omitted existing source records; it was not accepted as
verified evidence. This replacement separates directly inspected fields from
unresolved projection work. All code paths below are relative to memorii/memorii.

| Observed variant | Current canonical owner | Projection state |
| --- | --- | --- |
| Entity | core/memory_evolution/graph_records.py:130 EntityRevision | Identity, active/retired lifecycle and source_evidence retained. Canonical type, valid/system intervals and operation/source closure require additional authoritative joins. |
| Alias | graph_records.py:138 AliasRevision | Identity, namespace, normalized key, source_evidence retained. Intervals and binding evidence conversion need exact owner. |
| Type evidence | graph_records.py:154 TypeEvidence | Entity reference, type, origin, source evidence, authority, valid interval, recorded_at and proof ancestry/policy retained; system interval is not automatically recorded_at. |
| Claim assertion | core/semantic_ingestion/contracts.py:1476 ClaimAssertion | _TemporalCarrier supplies operation/temporal binding/valid interval/digest. Optional AcceptedClaimIdentity plus source authority/trust rule are all-or-none; legacy absent form cannot synthesize identity. Remaining observed fields need exact joins. |
| Claim projection | graph_records.py:185 ClaimProjection | Current record contains one claim_assertion_id and endpoints. Selected/contested sets, arbitration and interval history are not fields of this record. |
| Relation | graph_records.py:195 RelationRevision | Entity endpoints/predicate retained. Literal-object arm and supporting assertion/source/interval joins are not fields of this record. |
| Action | contracts.py:1517 ActionRevision | Temporal carrier and statement digest retained. No role/branch/applicability fields declared here. |
| Citation | graph_records.py:205 CitationRecord | Citation/cited record identity and optional entity identity retained. Source span and source digest not declared here. |
| Provenance | graph_records.py:213 ProvenanceRecord | Provenance/source identity and optional entity identity retained. Other observation fields require existing authority joins. |
| Temporal transition | contracts.py:1542 TemporalTransitionRecord | Operation/temporal carrier, correction/retraction kind, transition/statement identity and nullable system interval retained. Full projection requires exact transition authority. |
| Identity transition | contracts.py:1523 IdentityLineageRecord | CompiledIdentityLineageTransition is explicitly retained and checked against operation/statement/temporal binding. Inspect that typed transition before declaring missing fields. |
| Reference disposition | graph_records.py:221 ReferenceDispositionRecord | Target kind/id/path, predecessor/successor IDs, disposition/basis/source_evidence retained; inherited _GraphRecord supplies record_digest. |
| Source introduction | core/memory_evolution/graph_effect_contracts.py:282 CanonicalSourceIntroductionRecord | Exact source/delivery/governance/admission/span/entity/type-proof/operation/fence fields and digest retained. Observed entity wrapper and server boundary classification remain conversion. |
| Operation introduction | graph_effect_contracts.py:336 CanonicalOperationIntroductionRecord | Exact operation/source/fence/group/kind/predicate/spans plus full governance/admission carriers retained. Observed digest tuples derive from these exact carriers. |
| Operation terminal | graph_effect_contracts.py:390 CanonicalOperationTerminalOutcomeRecord | Exact status, nullable graph link, temporal bindings/reasons plus authority coordinates retained. Production persistence pending. |
| Source terminal | graph_effect_contracts.py:190 CanonicalSourceTerminalOutcomeRecord | Existing source-finalization delta retains canonical source outcome; observed scope/carrier digests derive from its typed carrier sets. Bounded source persistence verified separately. |

No implemented observation view selector or public stream is claimed. Temporal
compilation and lineage authorization are different concerns and do not prove
current/historical/lineage observation membership. Canonical graph records carry
inherited digest/version fields; absence in the subclass declaration is not
absence of the field. Boundary status comes from authenticated cohort closure,
never a caller flag. Remaining graph projection gaps require tracing canonical
replay/history before any new persisted representation is proposed.
