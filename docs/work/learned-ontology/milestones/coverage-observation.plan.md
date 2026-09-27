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

- Next action: freeze the installed origin-receipt producer and refreshed authority package, then obtain targeted correctness approval before recurrence aggregation.

## Frozen Schema And Trace Map (2026-09-27)

The canonical owner is `core/semantic_ingestion/coverage_observation.py`. No
prior ontology-coverage owner exists. Existing `SourceObservation` is the
retained transcript handoff and remains distinct from the new inert diagnostic
record.

| Signal | Existing production trigger | M4 insertion boundary |
| --- | --- | --- |
| Source admission | `ProviderMemoryService.sync_event` -> `ProviderIngestion._ingest_semantic_source` -> `GovernedSourceAdmissionService.prepare_atomic` -> `SemanticIngestionAtomicStore.publish_admitted_source` | A new source includes its selected-catalog observation in the first admission CAS. Exact retry omits a rebuilt member and reuses the persisted tuple; a separate verified reobservation insert backfills legacy sources and adds a new identity after catalog change while preserving old observations. No observer produces durable `discovery_pending_no_capability/not_evaluated`; an authorized binding produces `queued/not_evaluated`. |
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
caller yet and does not change any milestone or requirement count. The next
revision supersedes its original same-transaction proposal.

The first review found that the general constructor could skip directly to a
classified unsupported gap. The corrected initial constructor can create only
`discovery_pending_no_capability/not_evaluated` or `queued/not_evaluated`;
future running/classified/unavailable changes require a separate CAS transition
owner with predecessor state and attempt fence. Five contract tests pass.

The direct provider root now resolves the exact selected catalog, derives the
v1 direct-delivery origin lineage from authenticated principal and normalized
delivery identity, and includes the initial observation in a new source's first
admission CAS. Exact retries do not rebuild that immutable member from today's
catalog. A separate verified reobservation insert backfills a legacy-shaped
source, while catalog rotation adds a second observation and preserves the
first. An injected post-admission reobservation failure proves the initial
pending record already survived the source CAS. The combined real-provider
regression passes in 38.96 seconds.

The installed no-observer Hermes factory root passes in 20.07 seconds: exact
redelivery leaves one pending/not-evaluated record, direct JSONL reopen returns
the same digest-verified record, and no ontology candidate or gap fact exists.
Ruff and whitespace pass. Scoped Pyright reports no observation-contract
errors; seven existing diagnostics remain in unrelated later ingestion recovery
branches.

Targeted review of the crash-safe admission candidate found one Level-2 P2:
two callers that both saw no retained source could race across catalog rotation,
causing the losing caller's larger immutable admission tuple to be rejected.
The remediation reloads the winner through authenticated retained-source replay,
verifies exact source text and sealed Step-1 material, republishes the original
source tuple without a rebuilt coverage member, and then performs the normal
idempotent catalog-specific observation insert. Its deterministic two-thread
regression passes in 28.37 seconds and retains both catalog observations once.

`AuthenticatedOriginLineageEvidence` now carries a resolver-authenticated
authority/receipt pair with a content-validated core lineage digest. The generic
provider uses it when present and retains the direct authenticated
principal/delivery derivation otherwise. Two separate direct and forwarded
adapter deliveries with different operation IDs and transformed text persist
two observations with one shared verified lineage. Six contract checks plus the
catalog-race and adapter-coalescing paths pass as 8 tests in 70.82 seconds; the
original crash-safe admission path still passes in 36.42 seconds. Ruff, scoped
Pyright, compilation and whitespace pass. Counts remain 3/5 milestones and
5/14 requirements. The targeted review that followed is recorded next.

The exact `a5b9e42e` re-review approved the catalog-race remediation but found
one separate Level-2 P2: the authenticated origin evidence had no non-test
producer. The first-party local Hermes ingress issuer now accepts a bounded
host receipt only for direct-turn or delegation hooks, rejects malformed
digests, binds its authority to the verified installation and signed-in
operator, and emits `AuthenticatedOriginLineageEvidence` from its private
resolver evidence. The installed factory path admits transformed direct and
forwarded sources in two sessions as distinct observations with one lineage;
the new installed test passes, and the existing no-observer reopen path passes
beside it as 2 tests in 21.41 seconds.

Because `ingestion_contracts.py` belongs to the verified profile-3 decoder
source closure, the canonical generator refreshed all 184 dependent registry
declarations and manifests. Two consecutive generations produced the same
complete diff digest
`b1b894246fe75237bc29340200d430946b4cea4c8e7f4d413bd779985ce433a0`.
Counts remain 3/5 milestones and 5/14 requirements. Exactly one next action:
freeze the installed producer and generated package, then obtain targeted
correctness approval before recurrence aggregation.

Review of `f7ce04a6` found the factory issuer still accepted a raw digest and
the public callbacks did not supply it. The replacement removes that input.
`MemoriiHermesMemoryProvider.on_turn_start` now creates a content-validated
receipt from the observed immutable user-turn bytes and authenticated author,
stores it by session/turn coordinate, and lets a later public turn inherit it
only through an existing parent coordinate. The private factory resolver
verifies the receipt content and author, binds its authority to installation,
operator and agent, and otherwise leaves origin evidence absent. The normal
first-party completed-turn runtime carries the receipt through ingress and
atomically adds the pending observation to captured-source admission. Its
public callback test covers two transformed captured turns, forged-receipt
denial and one shared lineage without disabling the installed runtime or
calling `sync_event` directly. Four affected bridge tests pass in 20.40
seconds. Counts remain 3/5 and 5/14. Exactly one next action: freeze this public
callback correction and obtain targeted correctness approval before recurrence
aggregation.
