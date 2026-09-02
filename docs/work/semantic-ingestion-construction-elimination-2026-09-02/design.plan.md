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
   Reconciliation for the one boundary this design touches: a repeat
   decode of byte-identical input within the same operation discharges
   its validation obligation through the recorded verdict — the first
   decode ran the complete decode + typed validation + canonicity proof,
   validation is deterministic and context-free for identical bytes, and
   the replay is disabled whenever caller limits differ from the recorded
   call (rule 7). Nothing weakens a first decode of any bytes.
2. First admission of any value or byte string runs complete validation.
   Two hit forms are admissible for reuse, both strictly operation-local:
   (a) **identity** — the exact same object or byte string whose complete
   validation this operation already recorded; and (b) the landed
   substitution form already shipped for content-addressed digests — same
   concrete type, same declared digest, and full structural equality with
   the certified instance. Digest proximity alone, declared equality
   without structural equality, and any cross-operation state remain
   prohibited.
3. The codec's anti-forgery posture is preserved with
   **content-certification semantics**: no registry entry exists without
   complete validation of this exact content in this operation. A fresh
   object identity (including `model_construct` and `model_copy`) always
   takes the full path unless its own content completed validation here;
   nothing is ever certified by proximity or declaration alone.
4. **Instance sharing is gated on verified deep immutability.** Any
   consumer that returns or embeds a certified instance it did not freshly
   construct engages only for concrete types that pass a recursive
   immutability check — the type and every nested model type are
   `frozen=True` with no `Mapping`/`dict`/`list`/`set` field annotations —
   computed once per type at first encounter and cached on the type. Types
   failing the check (at minimum the four mutable sites found by review:
   `PredicateTrustRule.authority_rank_by_class` and
   `.decay_schedule_by_class`, `SemanticScopePolicy.embedding_head_lemmas`,
   and the non-frozen `MemoryScope` — reached from the decode roots
   `ClaimAssertion`, `SemanticGraphDelta`, `SemanticTerminalOutcome`,
   `BootstrapNativeOperationCompilationV3`, `SemanticScopePolicy`,
   `RequiredOutcomeScopeSet`) keep fresh construction and the full
   existing path, preserving today's construction isolation.
5. Writer admissions and the arena's sealed-lease lifecycle are untouched.
6. Canonical bytes, digests, persisted schemas, and replay semantics are
   byte-identical (gated by the frozen suites and the diametric parity
   gate).
7. `decode_semantic_contract` replay engages only for calls whose
   `max_nodes`/`max_depth` are both `None`, mirroring the landed
   canonicity-verdict rule; limited calls always execute fully.
8. Disabled mode (`canonical_evidence_enabled=False`) allocates no
   registry and takes the full path everywhere; its digest accounting
   stays exactly 43,756.

Authority chain for the new mechanism: the arena's
`CanonicalDigestVerificationScope` (operation-local, thread-local,
bounded, purged at exit and capacity refusal) is the sole owner of the
validated-instance registry and the decode-instance memo. Recording
points are validation-success sites inside the operation (Phase 3 lists
them exhaustively); consumers are revalidation sites whose inputs the
recording points actually certify.

## Phase 3 — Reality Analysis (verified against current code; revised
## v2 after independent review)

### The unified mechanism: validated-instance registry

One identity-keyed registry `id -> instance` on the digest-verification
scope (same lifecycle as the landed memos: strong entry references,
purge on exit/refusal). An entry certifies exactly: "this object's
content passed complete pydantic validation inside this operation."
Capacity: entries are capped at the frozen member-path envelope
(32,768); entries reference instances that are already part of the
operation's live object graph, so the registry adds entry tuples only,
not retained trees (the decode memo below is the one structure that
retains otherwise-dead instances and carries its own tighter cap).

Recording points — the exhaustive list; every point is a
complete-validation-success site, and every point records the **input**
instance that was validated (the established house semantics of
`certified_roundtrip` and the digest registry):

- `_record_digest_verification` (`contracts.py`) — the landed
  content-addressed verification registry; ~244 in-operation entries at
  census.
- `certified_roundtrip` success — the landed round-trip replay
  (`source_preparation.py`, `provider/ingestion.py`; the PreparedSource
  family).
- `decode_semantic_contract` success (new recording, shared with fix 2).
- `_revalidated_contract_instance` success — the codec's own proof;
  recording the input instance (whose content the proof just fully
  validated) extends certification to it under the content-certification
  rule; the freshly constructed proof instance is also certified as a
  by-product.
- **Graph-family adapter construction** — one shared owner helper wraps
  every `canonical_graph_record_adapter().validate_python` success in
  `graph_records.py`/`graph_planning.py` and records the constructed
  instance: `_GraphRecord.create` (`graph_records.py:101-107`),
  `_materialize_planning_payload` (`graph_planning.py:1465`),
  `_snapshot_record` (`:1344`), `_rebuild_reprojected_record`
  (`:1340`), `SnapshotGraphRecord.validate_payload`
  (`graph_records.py:372`) and `validate_record` (`:380`). Without these
  recording points no graph record is ever certified and fix 3 is inert
  (review round 1, findings 1/2 of two reviewers).
- **Event-replay carrier adapter** — the `_CARRIER_ADAPTER.validate_python`
  success in `build_semantic_memory_event` itself records the carrier, so
  even the uncertified fallback path certifies for later boundaries.

Coverage against the census's 79 first-encounter encode roots:
content-addressed and BootstrapV3 contracts (~45 classes) via the digest
registry; `PreparedSource` via `certified_roundtrip`; decoded reloads via
fix 2; graph records and carriers via the adapter recording points.
Instances constructed by owner code with no recording point stay
uncertified and pay the full path — the design claims no universal skip.

### Fix 1 — codec proof-tree avoidance

`encode_semantic_contract`'s lean path (and
`_build_validated_semantic_contract_result`) consults the registry before
constructing the proof tree: certified instance → skip the
`model_validate(restore_closed_wire_enums(payload))` construction, keep
emission and all other stages identical; uncertified → the existing
proof, which then certifies the instance (input and proof output). The
result's `contract` field then shares the certified input instance for
deeply immutable types (Phase 2 rule 4); mutable-field types keep the
freshly constructed proof instance as `contract`. The lowered payload is
still materialized (emission needs it); the memo footprint is unchanged.

### Fix 2 — decode-instance memo

`decode_semantic_contract` memoizes `(expected_type, raw bytes) ->
model` on the same scope, **engaging only when `max_nodes` and
`max_depth` are both `None`** (rule 7; identical bytes can legitimately
succeed or reject under different limits, and the bounded recovery
decoders in `source_normalization_repository.py` share payloads with the
unbounded delivery path). First decode always runs the full decode +
`model_validate` + canonicity cross-check and records the instance; the
memo serves only byte-identical unlimited repeat decodes. Sharing is
gated on the deep-immutability check (rule 4); the six mutable-root kinds
keep full fresh construction. Capacity: 2,048 entries (60x the measured
34 unique raws per delivery), first-wins, no eviction. Raw
`decode_typed_value` dict trees stay unmemoized (mutable, aliasing
hazard). Census: 106 calls, 34 unique raws, 11k redundant nodes.

### Fix 3 — graph-planning and event-replay conversions

Verified sites (complete family from review round 1):

- `graph_planning.py:1002-1004` (sort subscript): the sort key runs the
  union adapter over `item.model_dump()` solely to read `.record_kind`,
  a `Literal` field on every concrete union member (all 12 verified).
  Direct attribute read on certified instances; uncertified items keep
  the adapter path.
- `graph_planning.py:1497` (`_planning_payload`) and
  `graph_records.py:396-401` (the `payload_record_kind` property): the
  same dump-to-read-one-field pattern, per property **access**; direct
  field read on certified instances (the property keeps its dump path
  for uncertified payloads).
- `graph_planning.py:1343` (`_snapshot_record`): re-validates records
  from two callers — `_materialize_planning_payload`-constructed
  payloads (`:794`) and `create()`/reprojection-constructed outputs
  (`:941-999`) — both now certified at their construction recording
  points. The certified path passes the payload through, and
  `SnapshotGraphRecord` skips only the **adapter re-validation lines**
  (`validate_payload`'s revalidate call when the input is a certified
  instance, and `validate_record`'s redundant adapter call); the
  binding checks in `validate_record` (`record_id == graph_record_id`,
  `record_version`, `record_digest`, `codec_fingerprint`,
  `persistence_schema_fingerprint` against the manifest) and payload
  normalization run on **every** path. Four adapter validations per
  record collapse to one (the construction).
- `event_replay.py:817` (`build_semantic_memory_event`): a certified
  carrier instance (already a `CommittedRecord` union member) is used
  directly; anything else keeps the full adapter call and its exact
  error surface (`SemanticEventReplayError("semantic event carrier
  validation failed")`) — a surface currently pinned by no test and
  therefore added test-first by the successor.

### Alternatives considered

- Base-class `model_validator` recording hooks on ~270 contract classes:
  broader coverage but new validation surface on every class and import
  coupling in graph/replay owners; rejected — the named recording points
  cover the measured delivery roots, including the graph family.
- Converting the four mutable field sites to immutable containers
  (freezing `MemoryScope`, `Mapping` → frozen mappings): removes the
  immutability gate's failings list but is schema-adjacent work outside
  this design's frozen scope; recorded as a candidate follow-up.
- `gc.freeze()` at import time for the ~40k permanent machinery objects:
  safe (no concurrency semantics) but out of scope per user direction;
  recorded as a deferred decision with its measured 15%-of-scan-set value.
- Per-site ad-hoc flags: rejected — one registry with one trust rule
  instead of N special cases.

## Phase 4 — Verification And Attack Model

| Family | Attack / case | Required result | Owner |
| --- | --- | --- | --- |
| Forgery (identity) | `model_construct` instance (content-valid or invalid) reaching any consumer | full path; if its content never validated here it is uncertified — invalid content rejected with the existing error; valid content validated fresh | arena suite, extended per consumer |
| Forgery (copy) | `model_copy(update=...)` of a certified instance | new identity → full path; invalid update rejected exactly as today | arena suite + new consumer owners |
| Copy (content-equal) | plain `model_copy` of a certified instance | new identity → full path (conservative) | arena suite |
| Immutability gate | each of the six mutable-root kinds at every sharing consumer | full fresh construction and revalidation; gate check cached per type rejects them | arena + codec + graph owners |
| Immutability gate | deeply immutable type with a nested `Mapping`/`list`/`set` added later | gate recomputed per type at first encounter → rejects → full path | codec owner test |
| Cross-operation | registry, decode memo, `_roundtrips`, and instance registry content after arena close/purge | empty per structure; next operation takes full paths — **one close-purge observer per structure** (including the landed, currently untested `_roundtrips` memo) | arena suite |
| Capacity refusal | over-limit entry after refusal | every scope structure purged via `_inert_verification_scope_after_refusal` — one refusal-purge observer per structure | arena suite |
| Decode limits | bounded `max_nodes`/`max_depth` call for bytes already decoded unbounded | memo disabled for limited calls; the limit still rejects | codec owner test |
| Boundaries | decode of new bytes; writer admission; persistence commit; provider ingress | complete validation unchanged | existing suites |
| Accounting | disabled-mode digest calls; arena snapshot field set; terminal-snapshot contract | digest count exactly 43,756 via the PBD-EXP-014 v2 harness (revision-bound local evidence in the successor's gate ledger, not a CI claim); exact field tuple of both snapshot dataclasses pinned; digest-call determinism across repeated deliveries via the same harness | harness + arena suite |
| Determinism | digest-call counts across repeated deliveries | identical within a mode | PBD-EXP-014 v2 harness |
| Byte identity | frozen codec/vector/compatibility suites; fused-vs-reference differential; diametric parity; certified-path bytes at converted sites | green; canonical bytes unchanged | existing suites + converted-site owners |
| Concurrency | two arenas on separate threads | per-arena memo/registry counters differ; a thread-A-certified instance misses in thread B (discriminating assertion; the existing nonce test does not discriminate memo cross-talk) | arena suite |
| Aliasing (fix 2) | mutation attempt on a shared decoded model | frozen models reject assignment; the six mutable-root kinds are never shared | codec owner test |
| Graph sites | uncertified `item` (dict or bypass-constructed) at every converted site | adapter path and existing errors preserved | graph owners |
| Graph bindings | **certified** payload with corrupted envelope binding fields (`record_id`/`record_version`/`record_digest`/fingerprints) inside an active arena | `snapshot_graph_record_binding_mismatch` still raised — the skip never drops the binding checks | graph owner (the existing corruption matrix runs without an arena and cannot catch this) |
| Replay surface | forged/bypass-constructed carrier → `build_semantic_memory_event` | exact `SemanticEventReplayError` type and message (currently unpinned anywhere — test-first) | replay owner |

Evidence classes: deterministic unit tests for every row except the two
harness-attributed accounting/determinism rows (revision-bound local
evidence via the paused operation's PBD-EXP-014 v2 harness, recorded as a
required local command in the successor's gate ledger); profiles for
construction-count deltas. No live or operational claim.

## Phase 5 — Draft Design Summary (v2)

One registry, six recording-point groups, four consumer families, one
deep-immutability gate, all riding the landed arena scope lifecycle.
Implementation shape: ~6 production files (`canonical_evidence_arena.py`,
`contracts.py`, `graph_planning.py`, `graph_records.py`,
`event_replay.py`, plus the shared graph adapter recording helper), the
immutability check owned beside the codec contracts, focused tests
beside the existing arena/codec/graph/replay suites per the Phase 4
owner column, and the paused operation's gates for acceptance. Rollback
is the existing `canonical_evidence_enabled=False` switch (registry and
memo allocate only in enabled mode). No public, persisted, wire, or
schema change; no new identities beyond private runtime symbols owned by
the arena and codec modules.

Evidence maturity: census and profiles are locally verified measurements
(this design quotes them exactly: gen2 = 1.045s of 1.718s total GC time
= 60.8%, in 8 scans); this design is `specified`; every fix is
`derivable` from the frozen recording/consumer lists and the enumerated
capacity values above; nothing is `implemented` yet.

## Review Round 1 — Reconciliation Ledger (2026-09-02)

Frozen candidate v1 SHA-256:
`b4aafd0b83cb9c1fa3eabeb1fd3a21194782b33e176d4136a7b36492b4721e4c`
(the digest quoted in the review dispatch dropped one character — a
transcription error recorded here; all three reviewers reconciled the
on-disk file at that hash). Reviewers: `spec_auditor`,
`correctness_reviewer`, `test_reviewer`, all read-only against commit
`b674895`.

| Finding | Source | Classification | Coordinator disposition |
| --- | --- | --- | --- |
| Fix 3 inert: frozen recording points never certify graph records/carriers | spec#1 + correctness#2 (independently confirmed) | P2 / changes_required / architecture | **confirmed** — v2 adds the graph-family adapter recording points and the carrier adapter recording point; coverage claims corrected |
| Fix 2 memo key omits `max_nodes`/`max_depth` (bounded recovery decodes share payloads with unbounded delivery decodes) | spec#2 (P2) vs correctness#4 (P3, claiming all callers use defaults) | changes_required | **confirmed at P2** — coordinator re-verified `source_normalization_repository.py:133-250` passes `_BOOTSTRAP_V3_RECOVERY_MAX_TYPED_NODES/DEPTH`; v2 rule 7 disables replay for limited calls (the landed canonicity-verdict pattern) |
| "Deeply immutable decoded models" premise false — 4 mutable field sites, 6 decode roots; sharing consumers alias | correctness#1 | P2 / changes_required / runtime behavior | **confirmed** — v2 Phase 2 rule 4: per-type verified deep-immutability gate; failing kinds keep fresh construction; schema-level freeze recorded as candidate follow-up |
| Trust-rule letter contradicted the landed digest-registry hit form | spec#3 | Not applicable / changes_required / governance | **confirmed** — v2 rule 2 names both admissible hit forms |
| Recording point did not specify which instance is recorded | correctness#3 | Not applicable / changes_required / verification | **confirmed** — v2 specifies input-instance recording with content-certification semantics (rule 3), matching landed house semantics |
| Fix 2 mandatory-decode carve-out unreconciled | spec#4 | Not applicable / changes_required / governance | **confirmed** — v2 rule 1 reconciliation sentence |
| `SnapshotGraphRecord` skip could drop binding checks | spec#5 (P3) + test#3 (changes_required) | P3 + verification | **confirmed** — v2 binds the skip to the adapter re-validation lines only; new attack row for certified-payload-with-corrupted-bindings |
| Registry capacity envelopes unspecified | spec#6 + test#8 | P3 / follow_up | **confirmed** — v2 freezes entry caps (32,768 instance registry referencing already-live objects; 2,048 decode memo) |
| Digest-count/determinism rows mislabeled as unit-test evidence | test#2 | Not applicable / changes_required / verification | **confirmed** — v2 Phase 4 re-attributes both rows to the PBD-EXP-014 v2 harness as revision-bound local evidence in the successor's gate ledger |
| Per-structure purge tests missing; landed `_roundtrips` memo untested | test#5 | Not applicable / changes_required / verification | **confirmed** — v2 attack rows require one close-purge and one refusal-purge observer per structure and sweep `_roundtrips` |
| Event-replay error surface pinned nowhere | test#4 | Not applicable / changes_required / verification | **confirmed** — v2 marks it test-first work with a dedicated row |
| Concurrency row non-discriminating | test#6 | follow_up | **confirmed** — v2 row names the discriminating assertion |
| Accounting field-set pin | test#7 | follow_up | **confirmed** — v2 row pins both snapshot dataclass field tuples |
| gen2 percentage misquoted (52% vs 60.8%) | spec#7 | P3 / follow_up / evidence precision | **confirmed** — v2 quotes the exact census arithmetic |
| `_snapshot_record` second-caller description wrong; full sibling site family incl. `payload_record_kind` per-access dumps | correctness#2 (family enumeration) | P2 (same root as fix-3 inertness) | **confirmed** — v2 Phase 3 lists the complete family and corrects the caller description |

No `blocks_approval` findings. All confirmed `changes_required` findings
are resolved in candidate v2 (this document); all `follow_up` items are
incorporated into Phase 4 or recorded above.

## Progress Log

- 2026-09-02: opened from the paused implementation operation's census
  (CMR-EXP-008) and the user's fix ordering (1 → 3 → 2). Phase 3 sites
  verified against `585d51c`.
- 2026-09-02: candidate v1 (SHA-256 `b4aafd0b…1e4c`) reviewed by the full
  cohort; 15 findings reconciled above (two P2 design defects confirmed
  and corrected); candidate v2 drafted.

## Next Action

Refreeze candidate v2 and run one targeted delta review with the cohort
on the revised sections (recording points, immutability gate, limits
rule, capacity envelopes, Phase 4 rows).
