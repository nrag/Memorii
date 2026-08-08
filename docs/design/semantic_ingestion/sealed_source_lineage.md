# Sealed Source Alignment and Append-Only Lineage Owners

- Status: approved (M4 prerequisite)
- Owner: M3 reopened lineage correction + M4 event history replay
- Governing documents:
  - docs/design/semantic_ingestion_architecture.md (SIA-R02, SIA-R04, SIA-R18)
  - docs/work/semantic_ingestion/milestones/m3-semantic-pipeline.plan.md (M3 reopened)
  - docs/work/semantic_ingestion/milestones/m4-event-history.plan.md (M4 blocked on M3)
- Related contracts: memorii/core/semantic_ingestion/contracts.py, pipeline.py, persistence.py

## 1. Problem

Approved M3 behavior required **graph-free SourceDependencyGroup formation**,
**graph-bound TransactionSemanticGroupPlan expansion**, **append-only
SourceTransactionPlanLineage**, and **terminal-result equality with the exact
attempt, plan, and GroupPlanningAuthorization**. Production persisted only one
opaque plan and one group-result digest for a source instead.

This is an implementation gap (not design). M3 was reopened to close this gap.
M4's replay/checkpoint authority depends on the corrected lineage contracts
being byte-stable before production execution can proceed past M3.

## 2. Sealed Source Alignment Requirements

### 2.1 Conceptual Boundary: Sealed vs. Plan State

A **sealed source** is the immutable retention of the original provider content
with its governance, admissions, and scope contracts bound to it at ingestion
time. The sealed state cannot change; any evolution must produce a new entry in
the lineage rather than mutating existing records.

`
Sealed Source (immutable)              Plan Lineage (append-only)
┌──────────────────────────────┐      ┌─────────────────────────────────────┐
│ source_text + provenance     │      │ entry_1: initial_group_plan         │
│ segment_governance_carriers  │────> │ entry_n: expanded_group_plan        │
│ message_admission_carriers   │      │ entry_n+1: future_expansion         │
│ governance_carrier_artifact  │      └─────────────────────────────────────┘
│ required_outcome_scopes      │
└──────────────────────────────┘
`

Every SourceTransactionPlanLineage carrier must **prove** that its constituent
governance, admissions, and scope objects match exactly what was sealed for the
source during retention. No drift is permitted between sealed and planned state.

### 2.2 Carrier Alignment Invariants

For every SourceTransactionPlanLineage created at pipeline line ~736:

1. **Governance carrier consistency** (validated in-line):
   `python
   artifact.segment_governance == lineage.segment_governance_carriers
   artifact.message_admissions  == lineage.message_admission_carriers
   artifact.required_outcome_scopes == lineage.required_outcome_scopes
   `

2. **Source identity consistency**:
   `python
   artifact.source_id            == lineage.source_id
   artifact.source_digest        == lineage.source_digest
   `

3. **Repository identity consistency**:
   `python
   initial_group_plan.repository_id == lineage.repository_id
   all(entry.authorizing_group_plan.repository_id == lineage.repository_id for entry in lineage.entries)
   `

4. **All three sets must originate from the same sealed governance artifact** at
   ingestion time (the governance_carrier_artifact stored alongside the source).

### 2.3 Alignment Enforcement Point

The pipeline creates both the sealed governance artifact and the lineage in a
single coherent step (lines ~680-748 of pipeline.py). The create() method on
SourceTransactionPlanLineage enforces alignment via its model_validator:

- _canonical_values ordering on all carrier sets
- Source identity cross-checks between carriers and source metadata
- Artifact-carrier equivalence: the governance artifact must contain exactly the
  same carriers, no more, no less

## 3. Graph-Bound Transaction-Plan Expansion

### 3.1 Invariant: No Ad-Hoc Mutation

Once a SourceTransactionPlanLineage is created and persisted:

- **No field may be mutated** (the model is frozen with rozen=True).
- **New entries are appended only**, never inserted at intermediate positions or
  replacing existing entries.
- **Only graph-bound operations can extend the lineage**. Ad-hoc in-process code
  must not produce new entries directly.

### 3.2 Expansion Path

The expansion path is:

`
TransactionSemanticGroupPlan (graph-bound, mutable within single transaction)
    ↓ [atomic commit of accepted terminal]
SourceTransactionPlanLineage.entries += TransactionGroupPlanLineageEntry (append-only)
    ↓ [persistence to JSONL / event log]
Persistent append (irrevocable)
`

The initial_group_plan in a SourceTransactionPlanLineage is always a
TransactionSemanticGroupPlanReference—a lightweight handle pointing into the
graph-bound transaction plan. The plan itself lives in graph state, not in the
lineage payload.

### 3.3 Supersession Chain Validation

Each new TransactionGroupPlanLineageEntry carries:

- supersedes_entry_digest: the digest of the entry it extends (None for the first
  entry in a group chain)
- operation_ids: the exact operations bound to this plan state

Validation ensures:

1. No cycles in the supersession chain
2. No cross-group links (a new entry can only extend entries within its own group)
3. One final entry per group at all times (no forking allowed)
4. Complete operation coverage in final entries

## 4. Append-Only Lineage Owners

### 4.1 SourceTransactionPlanLineage as Immutable Owner

The SourceTransactionPlanLineage model is the **immutable owner** of source-level
transaction planning state:

`python
class SourceTransactionPlanLineage(BaseModel):
    # ... fields frozen=True, extra='forbid'
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
`

### 4.2 Entry Lifecycle (Append-Only)

| Phase | Can Add Entries? | Can Remove Entries? | Can Modify Entries? |
|-------|------------------|---------------------|---------------------|
| In-process (pre-persist) | Yes | No | Yes (within create()) |
| After model_validator passes | No | No | No (frozen) |
| After persistence | No | No | No |

### 4.3 Entry Append Semantics

When extending lineage (planned for M4 implementation):

1. Create new TransactionGroupPlanLineageEntry instance(s)
2. Validate against existing entries using the same validators as create()
3. Extend entries tuple: 
ew_entries = lineage.entries + (new_entry,)
4. Extend inal_entry_digests: remove superseded digests, add new terminal digests
5. Compute new lineage_digest from the complete body
6. Persist atomically as a new JSONL record / event

### 4.4 Relationship to IngestionExecutionManifest

The IngestionExecutionManifest is **separate but complementary**:

| Aspect | SourceTransactionPlanLineage | IngestionExecutionManifest |
|--------|-------------------------------|---------------------------|
| Owner | Immutable plan lineage (append-only) | Execution state snapshot |
| Mutability | Frozen after creation; extend via append | N/A in M3 (None); to be filled in M4 |
| Scope | Source-level planning across groups | Stage-instance-level execution outcomes |
| Persistence | Committed group members, noncommitting group members | Same (both stored as optional with None fallback) |
| M3 status | Fully wired and validated | Stub: None everywhere; M4 will populate |

In M3, execution_manifest is deliberately None across all persistence paths.
This is safe because:

- Both fields are optional (| None) in SemanticTerminalOutcome
- The codec pattern encode_semantic_contract(value) if value is not None else encode_typed_value(None) handles the absent case
- Decoding both returns None when the encoded payload matches the typed-None sentinel
- All three member-generation functions (_checkpoint_members, _committed_group_members,
  _noncommitting_group_members) include both fields symmetrically

## 5. M3/M4 Boundary and Completion Contract

### 5.1 Completed in M3 (This Work)

- [x] Full SourceTransactionPlanLineage wiring into pipeline at line ~736
- [x] plan_lineage: SourceTransactionPlanLineage | None type on SemanticTerminalOutcome
- [x] .create() signature updated to accept SourceTransactionPlanLineage
- [x] _checkpoint_members() stores both plan_lineage and execution_manifest
- [x] _committed_group_members() stores both fields
- [x] _noncommitting_group_members() stores both fields
- [x] _final_members() stores only plan_lineage (no execution_manifest)—correct
  per design: final members are for the persisted terminal summary which doesn't need
  execution state in M3
- [x] Codec stability: None payloads serialize to typed-None sentinel; backward compatible
- [x] All validators on SourceTransactionPlanLineage enforce sealed alignment

### 5.2 Deferred to M4 (Sealed Source Alignment Implementation)

M4 must implement the following **graph-bound expansion** behavior documented herein:

1. **Append-only lineage extension**: The pipeline must expose a deterministic method
   for appending new TransactionGroupPlanLineageEntry instances to existing lineage,
   preserving all invariants from §3 and §4.

2. **IngestionExecutionManifest population**: During M4 replay and event production,
   the execution manifest stub (None) must be replaced with a full manifest containing:
   - execution_graph_fingerprint from canonical graph
   - All segment language routes (from sealed governance)
   - Governance/admission carriers (from sealed artifact)
   - capability_bindings (resolved from M4 event production)
   - source_outcomes and 	ransaction_group_outcomes (from M4 stage execution)
   - causal_blockers (if any stages are blocked)

3. **Lineage expansion proof**: A deterministic replay from genesis must reconstruct
   the exact same SourceTransactionPlanLineage entries by replaying all committed
   group deltas in order, producing byte-equivalent lineage.

4. **Sealed source alignment audit**: Post-expansion, verify that every appended entry's
   governance/admission/scopes match the sealed source artifact (§2.2). Any drift is a
   hard failure, not a warning.

### 5.3 M4 Dependency Chain

`
M3 lineage correction (this PR/WorkPlan)
    ↓ required for
Sealed source alignment implementation (M4 §5.2)
    ↓ required for
Event history replay from genesis/checkpoints (M4 completion)
    ↓ required for
Provider/factory/cache/Hermes composition (M4 remaining slices)
`

M4's status remains locked until this M3 lineage correction is complete, verified,
and reviewed. The blocked arrays in the M4 WorkPlan (emaining_validated_p1_p2,
emaining_blocks_approval, emaining_changes_required) cannot be cleared without
this foundation.

## 6. Code Location Map

| Artifact | File | Key Lines |
|----------|------|-----------|
| SourceTransactionPlanLineage model | contracts.py | 3807-3874 |
| IngestionExecutionManifest model | contracts.py | 3658-3730+ |
| plan_lineage field type (corrected) | contracts.py | 1402, 1556 |
| Pipeline wiring | pipeline.py | 64, 735-748 |
| _checkpoint_members() | persistence.py | 609-705 |
| _committed_group_members() | persistence.py | 708-742 |
| _noncommitting_group_members() | persistence.py | 745-775 |
| _final_members() (plan_lineage only) | persistence.py | 777-856 |

## 7. Test Evidence Required (Step E)

Before marking this M3 correction complete, the following must pass:

1. **	est_semantic_terminal_persistence.py**: Full terminal checkpoint round-trip,
   codec stability for both plan_lineage and execution_manifest, backward compat
   with pre-M3 persisted records (no execution_manifest field).

2. **	est_plan_lineage_contracts.py**: All lineage validator invariants (§3.3) covered
   by existing tests; any new invariant additions must have corresponding tests.

## 8. Review Findings and Classification (Step F Summary)

See the independent review section below for detailed findings from the spec/correctness/test
review of the refrozen candidate.
