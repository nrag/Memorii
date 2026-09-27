# Provider-Neutral Coverage Observation And Recurrence

- Parent WorkPlan: `../implementation.plan.md`; order 4; state `active`
- Requirement allocation: OLE-01, OLE-02, OLE-08 and OLE-11 primary; OLE-12 `partial` for model capability; other requirements remain open
- Dependency: catalog identity and retained-source path from milestone 2; complete base from milestone 3 for final gap-versus-coverage proof; record actual base/head SHA and tree state.

## Journey And Boundary

Any authenticated adapter supplies retained source evidence through the same core contract. The monitor records an inert `CoverageObservation` with pinned catalog, provenance and diagnostic trajectory. With no ontology model it persists `discovery_pending_no_capability` plus `not_evaluated` across restart, without candidate or fact. With an explicitly bound host/local/authorized remote `ontology_observe` capability, only grounded unsupported relation/subtype spans may enter scope-local recurrence after attribution distinguishes schema coverage from extraction, protected retrieval, or agent exposure failures. Three verified independent origin lineages across two sessions trigger a proposal-eligible group; copied transcripts and subagent restatements count once.

## Owners And Changes

Extend common source admission after `core/memory_evolution/admission.py:97` and read/correction traces at `core/provider/ingestion.py:1214`, `service.py:915`, and persistence without changing committed fact truth. Core, not adapter/model, derives origin lineage from verified upstream identity and immutable source bytes. Persist the closed processing/outcome state machine, bounded queue, idempotency identity, failure signature and privacy-safe status projection. Add provider-neutral typed `ontology_observe`/`ontology_propose` capability manifests with explicit egress permissions; untrusted model output passes exact span, scope, type, alias and proposition checks. Two independent adapters supply equivalent envelopes. Ineligible/uncertain/unsupported statuses cannot bypass source retention or semantic writer.

## Proof And Closure

Run source admission, provider outage, recovery, retry, changed observer binding, duplicate lineage, two-session recurrence, quoted/hypothetical/ambiguous text, wrong-domain, extraction-failure, recall-miss and cross-scope cases. Verify identical and transformed bytes with one core-verified upstream origin count as one lineage; different verified origins count independently, and adapter-claimed or forged origin IDs cannot satisfy recurrence. Assert no candidate/fact for pending or uncertain states, one group for correlated copies, and zero raw source disclosure outside grants. Run two-adapter conformance with equal core observations and one installed-root path. Execute focused tests, static/type, persistence/recovery, applicable integration gates and current workflow pins. A fake model proves only plumbing; a live host/local/remote quality result is separate and binding-specific. Do not activate a catalog in this milestone.

- Next action: bind the no-capability observation into the admitted-source atomic transaction with selected-catalog and authenticated origin-lineage authority, then prove JSONL reopen and zero candidate/fact through one installed root.

## Frozen Schema And Trace Map (2026-09-27)

The canonical owner is `core/semantic_ingestion/coverage_observation.py`. No
prior ontology-coverage owner exists. Existing `SourceObservation` is the
retained transcript handoff and remains distinct from the new inert diagnostic
record.

| Signal | Existing production trigger | M4 insertion boundary |
| --- | --- | --- |
| Source admission | `ProviderMemoryService.sync_event` -> `ProviderIngestion._ingest_semantic_source` -> `GovernedSourceAdmissionService.prepare_atomic` -> `SemanticIngestionAtomicStore.publish_admitted_source` | Append the initial coverage record to the same admitted-source transaction after resolving the exact selected catalog and core-derived origin lineage. No observer produces durable `discovery_pending_no_capability/not_evaluated`; an authorized binding produces `queued/not_evaluated`. |
| Extraction trajectory | `_run_semantic_ingestion` returns the closed `SemanticTerminalOutcome` after source preparation and provider/domain validation | Update only the observation trajectory after the terminal is durable; extraction failure, abstention and policy denial remain diagnostic attribution and cannot become an unsupported-relation/type classification. |
| Protected retrieval | `ProviderMemoryService.retrieve_context` and the installed Hermes prefetch/read paths return a protected scoped result | Record a privacy-safe recall result/failure signature joined to the exact source observation only when current source/fact/catalog grants authorize that diagnostic update. Do not retain query or result text in the public status projection. |
| Correction/retraction | Default-catalog structured correction/retraction enters `submit_structured_fact`, native planning and one group CAS | Record the authorized downstream correction coordinate after commit; it is evidence for attribution, never direct proof that the catalog lacks a type or relation. |

The frozen v1 observation carries the design idempotency tuple `(source_id,
source_digest, catalog_digest, observer binding version or none)`, exact source
scope digest, core-derived origin-lineage digest, session/principal/agent,
catalog scope/digest, optional exact span, observer provider/model/prompt/
transport/egress/schema identity, closed semantic outcome, separate processing
state, bounded failure signature, attempt count and a content digest. Pending,
queued, running and unavailable states require `not_evaluated`; only classified
observations may claim `unsupported_relation` or `unsupported_entity_type`.

The first construction candidate implements that typed record and an
INTERNAL_CONTROL repository. Four focused tests pass in 4.43 seconds; Ruff,
scoped Pyright and whitespace pass. It proves idempotent durable pending state,
zero semantic/user fact records, a distinct queued identity for an authorized
binding, and fail-closed tamper/false-gap validation. It has no production
caller yet and does not change any milestone or requirement count. Exactly one
next action: bind the no-capability record into the admitted-source atomic
transaction with selected-catalog and authenticated origin-lineage authority,
then prove JSONL reopen and zero candidate/fact through one installed root.
