# Retrieval Authority Map

Coordinator-corrected map. Existing projection-history authorities derive and
persist separate temporal and trust selections on the generic terminal path.
The native group path does not currently publish those generations. The observed
single-projection shape also lacks a defined combination rule. Earlier claims
of a complete native generation path and a simple paired interval were withdrawn
after root inspection; neither may be used as implementation evidence.

## Persisted Selection Authority

`SemanticIngestionAtomicStore` constructs its sole
`ProjectionHistoryRepository` at
`memorii/memorii/core/memory_evolution/atomic_store.py:1084`.  It exposes that
same owner at `memorii/memorii/core/memory_evolution/atomic_store.py:2673`; a
consumer must not recompute a winner from `ClaimProjection` or a terminal
bundle.

| ObservedClaimProjection field | Existing authoritative value | Owner and validation |
| --- | --- | --- |
| `projection_id` | Shared temporal/trust projection ID, derived from repository, source kind/ID, and source digest | `projection_history.py:5699-5729` |
| `claim_slot_key` | Resolved immutable assertion-key slot | `projection_history.py:5998-6021`; retained by both typed projection records in `semantic_state.py:611-615` and `718-722` |
| `selected_assertion_ids` | Canonically sorted winner IDs | `projection_history.py:6023-6085` and `semantic_state.py:646-668`, `755-777` |
| `contested_assertion_ids` | Canonically sorted top-but-contested IDs; no invented winner | same selection and membership validation; current contested views are exposed by `projection_history.py:4041-4059` |
| `valid_interval` | Resolver-produced projection interval | `projection_history.py:6160-6285`; temporal record `semantic_state.py:617-620`, trust record `724-728` |
| `system_interval` | No combined interval is declared. Temporal and trust pointers advance independently; a single interval must not be invented from their pair. | Separate pointer histories in semantic_state.py and projection_history._historical_pointer |
| `arbitration_as_of` | Trust generation and trust record coordinate | `semantic_state.py:724-728`, `867-910` |
| `trust_policy_fingerprint` | Trust record and active trust generation fingerprint | `semantic_state.py:717-728`, `867-910` |
| `temporal_policy_fingerprint` | Temporal record and active temporal generation fingerprint | `semantic_state.py:610-620`, `822-865` |
| `transition_reason` | No direct field exists on a typed projection record.  The only retained source is the active/history pointer's `publication_kind`, certificate digest, and sequence. | `semantic_state.py:1106-1223`; projection certificate/history entry decoded and validated by `projection_history.py:4661-4735`. The proposed profile must define this deterministic conversion. |
| `boundary` | Derived by the observation cohort and paging boundary, not a native claim field | no existing graph-record field; proposed observation owner remains responsible |
| `record_digest` | No single persisted observed-record digest exists.  The input authority is the temporal and trust `projection_digest` pair plus their generation digests; the proposed observed schema computes its own digest from those inputs. | `semantic_state.py:620`, `728`; selected generation membership `822-910` |

`ObservedClaimProjection` in the governing SIA explicitly needs both policy
coordinates and `arbitration_as_of`
(`docs/design/semantic_ingestion_architecture.md:31524-31538`).  A common projection_id can locate both authorities, but does not authorize
merging their selected sets or intervals. Temporal resolution can change the
trust partition at projection_history.py:6150-6198. The singular public shape
needs a governing interpretation before either authority is selected or merged.  `graph_records.ClaimProjection` only has
the graph link (`claim_assertion_id` and entity endpoints) at
`memorii/memorii/core/memory_evolution/graph_records.py:185-193`; it is not
selection authority.

## Current, Historical, And Replay Reads

| Requested view | Existing call | Authority checks already performed |
| --- | --- | --- |
| current temporal | `ProjectionHistoryRepository.current_temporal` at `projection_history.py:3969-3989` | decodes complete namespace, validates pointer/generation/projection closure, requires policy fingerprint and current replay graph revision |
| current trust | `current_trust` at `projection_history.py:3991-4018` | same closure checks, policy and graph revision checks, plus due-decay rejection at the requested system time |
| historical temporal | `historical_temporal` at `projection_history.py:4077-4082` | chooses the retained historical pointer then materializes only that generation |
| historical trust | `historical_trust` at `projection_history.py:4084-4089` | same retained-pointer construction for trust |
| checkpoint/replay consistency | `replay_bindings`, `validate_replay_bindings`, and `validate_checkpoint_bindings` at `projection_history.py:4173-4205` | two kind bindings commit the complete history prefix, active pointer, generation digest, and replayed graph revision |

`_load_kind` decodes all certificate, generation, history-entry, projection, and
active-pointer records and invokes `_validate_loaded` before returning a view
(`projection_history.py:4661-4735`).  `_temporal_view` and `_trust_view` select
only the generation's canonical projection digests
(`projection_history.py:5224-5236`).  This is the validator to reuse for a
snapshot-only observation read; a facade must use an immutable snapshot-backed
record reader with the same canonical memory records, then call these existing
methods.  It must not call live-store `current_*` after choosing a graph
snapshot, because those methods intentionally consult current replay authority.

The current `graph_state_snapshot()` is not that composition: it captures
replayed graph records and the reference-integrity ledger
(`atomic_store.py:7975-8066`), while projection-history records are separate
internal-control records.  The concrete missing integration is therefore a
detached, snapshot-consistent projection-history read surface (or an equivalent
snapshot bundle containing its exact canonical records and replay bindings).
It is not missing claim-selection data and does not require an additional
terminal arbitration-bundle join.

## Native Claim Evidence To Projection Publication

The native fact planner creates the retained graph claim link and its evidence
joins:

| Required input | Retained native authority |
| --- | --- |
| Claim-to-entity graph link | `ClaimProjection.create` from `claim_id` and selected entity revisions, `bootstrap_graph_planning.py:292-318` |
| Citation/provenance join | Citation cites the claim and provenance names the operation source; the planner also retains each `BootstrapNativeEvidenceProjectionV3`, `bootstrap_graph_planning.py:318-364` |
| Claim selection inputs | `_claim_assertion` writes `claim_identity`, `source_authority_evidence`, `predicate_trust_rule`, accepted temporal evidence, and temporal decision binding, `bootstrap_graph_planning.py:434-469`; `ClaimAssertion` rejects a partial authority closure in `semantic_ingestion/contracts.py:1476-1509` |
| Generic materialized selection publication | persistence.py:360-403 -> persist_terminal_group -> atomic_store._semantic_event_authority_updates:12735 -> projection-history prepare; this path is not the native group entrypoint. |
| Native publication gap | bootstrap_graph_repository.py:402-414 -> atomic_store.commit_or_reload_bootstrap_graph_group_v3:11409; canonical event/replay/reference records at 11720-11870 omit projection-history publication. |
| Preflight versus persistence | atomic_store:8670 calls prepare only for conflict-authority preflight. The 7450-7577 call is clarification publication. Neither proves native group generation publication. |

`projection_records_from_replay_state` refuses any typed claim missing
`claim_identity`, `source_authority_evidence`, or `predicate_trust_rule`
(`projection_history.py:5983-6021`) and computes selected/contested/retained
membership from those retained inputs.  These are reusable canonical inputs and validators; they do not establish
that native group publication calls them. The missing native integration must
publish complete generation/certificate/pointer/replay authority in the same
CAS as the accepted native effects, with existing validation and retry guards.

## Exact Remaining Work Boundary

Three distinct tasks remain:

1. Integrate canonical projection-history publication into the native group CAS;
   helper or generic-path tests cannot establish that behavior.
2. Compose the existing projection validators against one detached store snapshot,
   including complete history and replay bindings, without live-store fallbacks.
3. Resolve the public single-projection interpretation. Temporal/trust selections
   and publication histories can differ. No merged winner, combined system interval
   or transition reason is currently justified by the inspected contract.

The third item is a public semantic boundary; the first two are determinate
implementation work. The source of any selected output must remain independently
checkable against persisted production authority.
