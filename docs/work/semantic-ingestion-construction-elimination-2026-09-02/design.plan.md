# Construction-Elimination Design WorkPlan

- Work ID: `semantic-ingestion-construction-elimination-2026-09-02`
- Work type: `design`
- Status: `active`
- Coordinator: sole writer (main thread)
- Created: 2026-09-02
- Last updated: 2026-09-02
- Parent WorkPlan:
  `../semantic-ingestion-canonical-member-reuse-2026-09-01/implementation.plan.md`
  (paused implementation operation; its census CMR-EXP-008 and profiles
  CMR-EXP-005..007 are the measured baseline)
- Related WorkPlans:
  - `../semantic-ingestion-validated-canonical-closure-2026-08-17/design.plan.md`
    (approved v12 closure design; governs reuse trust rules)
  - `../semantic-ingestion-validation-boundary-performance-2026-08-17/design.plan.md`
    (frozen mandatory-boundary classification; governs which revalidation
    sites are internal-candidate)
- Canonical inputs: the paused operation's evidence directory; the
  governing design docs (`docs/design/semantic_ingestion_validated_canonical_closure.md`,
  `docs/IMPLEMENTATION_RULES.md`, `docs/design/event_model.md` for replay
  carriers); the frozen codec/vector/compatibility/arena/parity suites.
- Expected outputs: one frozen, reviewed fix-design for construction
  elimination on the delivery hot path, ready for a `$implement-design`
  successor.

## Objective

Cut the remaining object-construction redundancy on the enabled delivery
path — the pydantic proof-trees, repeat decode trees, and quadruple graph
revalidations measured by CMR-EXP-008 — without weakening any validator,
mandatory boundary, writer admission, or the six staged validations, and
without any GC state manipulation (rejected by the user for multi-session
concurrent hosts).

## Phase 1 — Problem And Baseline

Measured baseline (CMR-EXP-008, one enabled delivery at `585d51c`):

- ~800k+ tracked-container allocations; live set 283,850 objects at arena
  close; gen2 = 52% of GC time in 8 full scans; every pydantic instance
  costs instance + `__dict__` + `__pydantic_fields_set__` (~23k of the
  36k live `set` objects are per-instance bookkeeping).
- Construction engines, in order: (a) `model_validate` construction fans
  (816 explicit top-level calls; the codec's ~79 first-encounter
  anti-forgery revalidations build deep proof-trees that are discarded);
  (b) dump→validate round-trips (2,282 `model_dump` calls; the deep ones
  remain in graph planning and event replay); (d) decode re-materialization
  (106 decodes, 16,412 nodes, only 34 unique byte strings).

Requirements source: user direction 2026-09-02 ("analyze first, then attack
the three fixes"; GC disable/enable rejected for concurrent multi-session
hosts); the paused operation's completion contract (<5s enabled median,
accounting unchanged); AGENTS.md staged-validation invariants.

Included: fix 1 (proof-tree avoidance), fix 2 (decode-instance memo), fix 3
(graph-planning and event-replay round-trip conversion), and the unified
certification mechanism they share.

Excluded: any `gc` module state manipulation (user-rejected; the one-time
import-time `gc.freeze()` of permanent machinery is recorded as a deferred
follow-up requiring its own decision, not part of this design); canonical
bytes/digest/persisted-schema changes; benchmark/live certification.

## Phase 2 — Contract And Authority Boundaries

Non-negotiable (from AGENTS.md, the v12 closure design, and the VBP
boundary classification):

1. The six staged validations remain separate; mandatory boundaries
   (public/provider ingress, transport decode, persistence admission and
   transaction commit, reload/replay/recovery reads, writer admission,
   cross-operation) always run complete validation on their input.
2. First admission of any value runs complete validation. Reuse may only
   replace work already proven **for the exact same object or byte string
   within the same operation scope** — never by digest proximity, declared
   equality, or cross-operation state.
3. The codec's anti-forgery posture is preserved: an instance that cannot
   be proven to have been produced by complete validation in this
   operation pays the full existing path. `model_construct`,
   `model_copy(update=...)`, and any fresh identity are never certified.
4. Writer admissions and the arena's sealed-lease lifecycle are untouched.
5. Canonical bytes, digests, persisted schemas, and replay semantics are
   byte-identical (gated by the frozen suites and the diametric parity
   gate).
6. Disabled mode (`canonical_evidence_enabled=False`) allocates no
   registry and takes the full path everywhere; its digest accounting
   stays exactly 43,756.

Authority chain for the new mechanism: the arena's
`CanonicalDigestVerificationScope` (operation-local, thread-local,
bounded, purged at exit and capacity refusal) is the sole owner of the
validated-instance registry. Recording points are validation-success
sites that already exist inside the operation; consumers are
revalidation sites classified internal-candidate by the VBP census.

## Phase 3 — Reality Analysis (verified against current code)

### The unified mechanism: validated-instance registry

One identity-keyed registry `id -> instance` on the digest-verification
scope (same lifecycle as the landed memos: strong entry references, entry
bound at the frozen member-path envelope, purge on exit/refusal). An
entry certifies exactly: "this object's content passed complete pydantic
validation inside this operation." Recording points (all existing
validation-success sites):

- `_record_digest_verification` (`contracts.py`) — extends the landed
  content-addressed verification registry; ~244 in-operation entries at
  census.
- `certified_roundtrip` success — the landed round-trip replay.
- `decode_semantic_contract` success (new recording, shared with fix 2).
- `_revalidated_contract_instance` success (the codec's own proof) —
  certifies instances for later boundaries.

Coverage check against the census's 79 first-encounter encode roots:
content-addressed and BootstrapV3 contracts (~45 classes) certify via the
digest registry; `PreparedSource` certifies via `certified_roundtrip`
(producer/prepare edge); decoded reloads certify via fix 2. Instances
constructed by owner code with no recording point stay uncertified and
pay the full path — the design claims no universal skip.

### Fix 1 — codec proof-tree avoidance

`encode_semantic_contract`'s lean path (and `_build_validated_semantic_
contract_result`) consults the registry before constructing the proof
tree: certified instance → skip the `model_validate(restore_closed_wire_
enums(payload))` construction, keep emission and all other stages
identical; uncertified → the existing proof, which then certifies the
instance. The lowered payload is still materialized (emission needs it);
the memo footprint is unchanged.

### Fix 2 — decode-instance memo

`decode_semantic_contract` memoizes `(expected_type, raw bytes) -> frozen
model` on the same scope (bounded entries plus retained-bytes caps).
Frozen models are deeply immutable (tuple/frozenset containers per the
contract families), so sharing the instance is sound; raw
`decode_typed_value` dict trees stay unmemoized (mutable, aliasing
hazard). The memo's canonicity-verdict replay (already landed) is
unchanged; first decode still runs the full decode + model_validate +
canonicity cross-check. Census: 106 calls, 34 unique raws, 11k redundant
nodes.

### Fix 3 — graph-planning and event-replay conversions

Verified sites:

- `graph_planning.py:996-1011`: the sort key runs the discriminated-union
  adapter over `item.model_dump()` solely to read `.record_kind`, which
  is a `Literal` field on the concrete `_GraphRecord` classes. Direct
  attribute read `item.record_kind` on certified instances; uncertified
  items keep the adapter path.
- `graph_planning.py:1343` (`_snapshot_record`): re-validates a record
  that `_materialize_planning_payload` just constructed through the same
  adapter; the certified path passes the constructed payload through, and
  `SnapshotGraphRecord.validate_record` skips its re-validation when
  `self.payload` is certified (its `validate_payload` field validator
  still normalizes non-instance inputs). Four adapter validations per
  record collapse to one (the construction).
- `event_replay.py:817` (`build_semantic_memory_event`): re-validates a
  store-owned carrier through `_CARRIER_ADAPTER` for discrimination plus
  re-proof; a certified carrier instance is used directly (it is already
  a member of the union), anything else keeps the full adapter call and
  its exact error surface.

### Alternatives considered

- Base-class `model_validator` recording hooks on ~270 contract classes:
  broader coverage but new validation surface on every class and import
  coupling in graph/replay owners; rejected for this bounded design (the
  recording points above cover the measured delivery roots).
- `gc.freeze()` at import time for the ~40k permanent machinery objects:
  safe (no concurrency semantics) but out of scope per user direction;
  recorded as a deferred decision with its measured 15%-of-scan-set value.
- Per-site ad-hoc flags: rejected — one registry with one trust rule
  instead of N special cases.

## Phase 4 — Verification And Attack Model

| Family | Attack / case | Required result |
| --- | --- | --- |
| Forgery (identity) | `model_construct` instance reaching any consumer | not in registry → full validation; forged content rejected with the existing error |
| Forgery (copy) | `model_copy(update=...)` of a certified instance | new identity → full path; invalid update rejected exactly as today |
| Copy (content-equal) | plain `model_copy` of a certified instance | new identity → full path (conservative; never re-certified by proximity) |
| Cross-operation | registry content after arena close/purge | empty; next operation takes full paths |
| Capacity refusal | over-limit entry after refusal | registry purged with the existing `_inert_verification_scope_after_refusal` |
| Boundaries | decode of new bytes; writer admission; persistence commit; provider ingress | complete validation unchanged; disabled-mode digest count exactly 43,756 |
| Determinism | digest-call counts across repeated deliveries | identical within a mode |
| Byte identity | frozen codec/vector/compatibility suites; fused-vs-reference differential; diametric parity | green; canonical bytes unchanged |
| Concurrency | two arenas on separate threads | thread-local registries; no cross-thread hits |
| Aliasing (fix 2) | mutation attempt on a shared decoded model | frozen models reject assignment; containers are tuples/frozensets |
| Graph sites | uncertified `item` (dict or constructed-by-bypass) at each converted site | adapter path and existing errors preserved |
| Accounting | arena snapshot fields, terminal-snapshot contract | unchanged field set and values |

Evidence classes: deterministic unit tests for every attack row (arena +
codec + graph + replay owners); the paused operation's wall-clock harness
for before/after; profiles for construction-count deltas. No live or
operational claim.

## Phase 5 — Draft Design Summary

One registry, four recording points, four consumers, all riding the
landed arena scope lifecycle. Implementation shape: ~6 production files
(`canonical_evidence_arena.py`, `contracts.py`, `graph_planning.py`,
`graph_records.py`, `event_replay.py`, plus the decode recording site),
focused tests beside the existing arena/codec suites, and the paused
operation's gates for acceptance. Rollback is the existing
`canonical_evidence_enabled=False` switch (registry allocates only in
enabled mode). No public, persisted, wire, or schema change; no new
identities beyond one private runtime symbol family owned by the arena.

Evidence maturity: census and profiles are locally verified measurements;
this design is `specified`; every fix is `derivable` from the frozen
recording/consumer lists above; nothing is `implemented` yet.

## Progress Log

- 2026-09-02: opened from the paused implementation operation's census
  (CMR-EXP-008) and the user's fix ordering (1 → 3 → 2). Phase 3 sites
  verified against `585d51c`.

## Next Action

Freeze the candidate (this document) and run the independent review
cohort (`spec_auditor`, `correctness_reviewer`, `test_reviewer`).
