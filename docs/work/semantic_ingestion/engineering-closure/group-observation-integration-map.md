# Group Observation Integration Map

Status: read-only readiness map. This records current code ownership; it does
not claim that terminal-group observations are persisted.

## Actual production chain

The production route reaches the native group transaction through:

`ProviderMemoryService.sync_event` -> bootstrap graph host/coordinator ->
`AtomicStoreBootstrapGraphGroupCommitRepositoryV3.commit_or_reload` ->
`SemanticIngestionAtomicStore.commit_or_reload_bootstrap_graph_group_v3`.

The store's group-commit linearization owns the current graph snapshot and
preplanning control. It reads `control.observation_revision` as the observation
predecessor and derives `after_observation` from the predecessor and the sealed
`request.request_ctv_digest` under
`memorii.semantic-ingestion.bootstrap-graph-group-observation-revision.v3\0`.
It also derives graph before/after from the current snapshot and the same sealed
request, materializes accepted graph records from each operation reduction, and
creates the persisted group result/reload. The resulting core carries graph and
observation before/after values; it does not currently call
`build_terminal_group_observation_delta` or persist its returned type.

The source terminal path subsequently consumes only the sealed group result
construction. It must remain separate from a group observation transaction.

## Helper inputs and current owners

`build_terminal_group_observation_delta` is a pure validator/builder. Its
required inputs have these authoritative origins:

| Builder input | Retained/current owner | Readiness |
| --- | --- | --- |
| `request` | `BootstrapGraphGroupCommitRequestV3`, sealed by the group repository | Available. Supplies source/group/fence/delivery coordinates and ordered operation IDs. |
| `materialized_graph_records` | Accepted operation `reduction.effect_materialization` processed by group commit | Available only within group-commit materialization loop; must use the exact `CanonicalGraphRecord`/`SnapshotGraphRecord` outputs, not a summary. |
| `graph_revision_delta` | Group commit creates/owns graph revision state and accepted effect materialization | No typed `GraphRevisionDelta` is retained as a direct group-commit input/output at the helper call boundary. Its canonical before/after and record membership must be assembled from existing graph materialization authority; do not invent IDs. |
| source introductions | Planner/admission authority owns source spans, mention/entity revision and logical entity identity | Not present in the current group commit request/reduction result as canonical `CanonicalSourceIntroductionRecord` values. The store must be passed retained typed records from their canonical planner/admission owner. |
| operation introductions | Per-operation native planning/reduction inputs retain operation/predicate/span/provenance authority | Not materialized as `CanonicalOperationIntroductionRecord` in the current commit loop. Need an explicit authoritative conversion at the planner/materialization boundary. |
| operation terminal outcomes | Each ordered operation's native terminal status and effect materialization | Status is retained, but canonical `CanonicalOperationTerminalOutcomeRecord` fields including plan lineage, manifest, reason and graph-delta digest are not exposed as a single current typed carrier. |
| `observation_revision_before/after` | `control.observation_revision` and current group store derivation | Available in the group CAS. The helper must receive these exact values, not recompute from a terminal summary. |
| `observation_delta_id` | Server ownership required | No existing group-observation ID derivation is located in the group commit path. Must be defined from sealed request/materialized authority before integration. |
| `observation_schema_fingerprint` | Frozen observation schema authority | No retained schema-manifest binding currently reaches the group commit request. Do not take an ambient caller fingerprint. |
| governance/message carriers | `request` operation inputs, host authority and effect materialization | Available as typed carriers, but the helper requires canonical tuples matching every generated record and graph delta. |
| terminal status | Native operation terminal statuses and group disposition | Available; builder enforces committed iff committed outcomes and graph delta exist. |

## Exact integration boundary

The only coherent insertion point is inside the successful/noncommitting group
CAS construction in `SemanticIngestionAtomicStore` after native graph records
and all per-operation outcomes are materialized, and before immutable member
records, manifest, result/reload, control successor, and effects are committed.
That boundary has the sealed request, live predecessor control, derived
successor, materialized graph records, and writer/lease CAS authority. It can
place the typed observation delta in the same conditional write as its group
result and advance the already-derived observation revision atomically.

No source-terminal wrapper should carry this delta. A group terminal delta must
be persisted and reloaded through the group transaction's own explicit member
grammar and exact recovery validation.

## Missing canonical inputs

Current code does not retain enough typed canonical observation-record material
at the group store boundary to call the helper without manufacture. In
particular, source/operation introduction records, canonical operation terminal
outcomes, a typed graph revision delta with record membership, a server-derived
group observation ID, and a frozen schema fingerprint authority are absent from
the observed group commit contract. These are implementation prerequisites, not
permission to substitute `smallCTVsummary`, generic summaries, or inferred
provenance.

## Field-level carrier trace

The table distinguishes a field whose value exists in an authenticated carrier
from a missing value. A "conversion absent" row means all needed values are
present but no current code creates the canonical observation record.

| Target record / field family | Exact current carrier | State at group CAS |
| --- | --- | --- |
| `CanonicalSourceIntroductionRecord.source_id`, `source_digest`, `operation_id`, `operation_fence_id` | `BootstrapGraphGroupCommitRequestV3.source_plan_lineage_entry.source_id/source_digest`, `source_operation_id`, `operation_fence_binding.operation_fence_id` (`contracts.py:12426`) | Available. |
| source-introduction delivery digests | `request.operation_fence_binding.delivery_principal_binding_digest/delivery_key_digest` (`contracts.py:12426`) | Available. |
| source-introduction segment governance/message admission/artifact | `request.control_epoch` and the retained normalized/planning authority reachable from `ordered_operation_inputs[*].reduction.native_compilation.operation_input`; group request itself has `required_outcome_scopes` and fence but not a direct canonical source-introduction tuple | Carrier values exist upstream, but no direct group request field selects the per-mention binding/identity. Input-carrier addition is required. |
| source-introduction `mention_span`, `entity_revision_id`, `logical_entity_id`, independently asserted type evidence | normalized proposal/entity-resolution authority inside each operation's `native_compilation.operation_input` | The group request retains the operation input transitively, but the current store loop (`atomic_store.py:11572`) never extracts a mention/entity-resolution projection or specifies which mentions belong to this group. Conversion and group-membership rule are absent. |
| operation-introduction source/group/fence/delivery fields | request lineage/fence/group fields above | Available. |
| operation-introduction operation kind and predicate | `ordered_operation_inputs[*].reduction.native_terminal.operation_kind`; predicate is in the nested normalized proposal/operation input, not the terminal itself (`contracts.py:11186`) | Operation kind available; predicate carrier exists upstream but requires an explicit projection. |
| operation-introduction owned source spans | nested `native_compilation.operation_input.normalized_proposal` span/provenance material | Carrier exists upstream; no existing operation-to-owned-span selection is retained at the commit loop. |
| operation-introduction governance/message tuples | nested operation input governance carriers plus request `required_outcome_scopes` | Carrier exists upstream; canonical sorted tuple conversion is absent. |
| operation-terminal outcome source/group/fence/delivery/governance | same request and nested operation-input carriers | Values available by the same conversions as operation introduction. |
| terminal `final_status` | `reduction.native_terminal.status` and `BootstrapGraphOperationCommitResultV3.final_status` (`contracts.py:11186`, `atomic_store.py:11650`) | Available, with mapping required (`accepted` is not the observation record's `committed`). |
| terminal retry disposition | Group result is terminal once the CAS completes; no typed `retry_disposition` carrier exists | Derivable server policy, but needs an explicit constant/mapping at the canonical outcome constructor. |
| terminal graph-delta digest | Per-operation `graph_digest`, produced at `atomic_store.py:11605-11621` and stored in `BootstrapGraphOperationCommitResultV3.graph_delta_digest` | Available for current legacy per-operation delta, but it is not `GraphRevisionDelta.delta_digest`. |
| terminal temporal decisions / plan lineage / execution manifest / reason codes | `native_compilation`, planning authorization/lineage, request pre-execution manifest, and `native_terminal.reason_codes` | Individual carriers exist; no single canonical terminal-outcome projection exists. The plan-lineage and manifest digests are direct request fields; temporal decision mapping remains unimplemented. |
| `GraphRevisionDelta` before/after/group/operation IDs | `before_graph`, `after_graph`, request group/operation IDs at `atomic_store.py:11545-11570` | Available. |
| Graph delta source IDs/governance/message/artifact | request lineage source plus nested operation governance/admission carriers | Source ID available; governance/message/artifact need explicit projection from retained nested authority. |
| Graph delta record changes | `all_materialized_records`, built from `materialization.record_intents` at `atomic_store.py:11572-11605` | Available as canonical graph records. Conversion to sorted `GraphRecordChange` and its read/write-set digests is absent. |
| Graph delta ID/read/write set | Current code derives only legacy per-operation `graph_digest` from typed materialized record dumps (`atomic_store.py:11606-11621`) | Server derivation is required; no external fact is missing, but a separate `GraphRevisionDelta` derivation convention has not been implemented. |
| observation predecessor/successor | `control.observation_revision` and group CAS derivation (`atomic_store.py:11555-11570`) | Available. |
| observation delta ID/schema fingerprint | Server-owned derivation precedent now exists for source finalization in `observation_persistence.py:45-75` | No user or external input is missing. Group-specific domain tuple and frozen schema function must be implemented at the store owner. |

The implementation prerequisite is therefore not broad new provenance. It is a
typed projection boundary that carries the already-retained nested operation
input authority into canonical introduction/outcome records, plus server-owned
`GraphRevisionDelta` and observation-coordinate derivations. It must be placed
before the group transaction's immutable member/manifest assembly so the exact
records and delta can be committed and reloaded atomically.

## Coordinator-Validated Planner Retention Boundary

The fact planner already selects the subject and entity-object mention candidates
in `bootstrap_graph_planning.py:185-336`; these carry entity revision, logical
identity and type evidence. Source normalization seals one governance binding,
matching admissions, exact evidence constructions and temporal constructions in
`source_normalization_stage.py:99-168`. The mapping is dropped before the retained
native fact effect; this is a missing typed carrier, not a new product decision.
Retain the selected, validated mapping in the fact effect through reduction into
the group request. The normal planner is currently fact-only; other accepted arms
require their own selector, never an inferred reuse of the fact mapping.

Store projection must compare actual before/after snapshot records by canonical
kind/ID and actual reference ledger changes. Derive graph delta identity and write
set from sorted exact mutations under behavior-owned CTV domains. Read-set digest
comes from the sealed group member. New persisted carriers must preserve historical
bytes with explicit grammar dispatch, and legacy reload must not synthesize audit.
The prior broad 'missing canonical inputs' section is superseded by this precise
retention correction; no external provenance or user policy value is missing.
