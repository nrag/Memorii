# Construction-Elimination Design WorkPlan

- Work ID: `semantic-ingestion-construction-elimination-2026-09-02`
- Work type: `design`
- Status: `complete`
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
  close; gen2 = 1.045s of 1.718s total GC time (60.8%) in 8 full scans; every pydantic instance
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
   prohibited. Consumer-side admissibility: an identity hit is consumable
   only when the certified concrete type belongs to the consumer's
   expected type family, verified at runtime (mirroring the landed
   registry's type-keyed lookup) — an instance certified at another
   recording point but outside the consumer's family takes the full
   path.
3. The codec's anti-forgery posture is preserved with
   **content-certification semantics**: no registry entry exists without
   complete validation of this exact content in this operation. A fresh
   object identity (including `model_construct` and `model_copy`) always
   takes the full path unless its own content completed validation here;
   nothing is ever certified by proximity or declaration alone.
4. **One closed sharing rule governs every instance-sharing consumer.**
   A sharing consumer is any site that returns or embeds a certified
   instance it did not freshly construct: fix 1's result `contract`
   field, fix 2's memo return, and fix 3's `_snapshot_record` payload
   passthrough, `SnapshotGraphRecord` re-validation skips, and
   `build_semantic_memory_event` carrier direct use. A sharing consumer
   engages only when the instance's concrete type passes the
   deep-immutability gate: the type and every nested model type are
   `frozen=True`, no field annotation anywhere in its parameter tree
   (including inside tuple/union/`Annotated` arguments) contains
   `Mapping`/`dict`/`list`/`set` or any mutable `Sequence`, no field is
   annotated `object`/`Any`, and no field is annotated with a bare or
   non-frozen model type (including `BaseModel` itself — `BaseModel`'s
   own config is not frozen). The check is computed once per concrete
   type at first encounter and cached; cached verdicts are never
   invalidated. Gate-failing kinds — including `ClaimAssertion`, whose
   annotation tree contains the `PredicateTrustRule` mappings, making it
   gate-failing even though it is a carrier kind and union member that
   fix 3 constructs and consumes — keep fresh construction and the full
   existing path at every sharing consumer, preserving today's
   construction isolation. Attribute reads that never share an instance
   (the `record_kind` conversions at `graph_planning.py:1002-1004`,
   `:1497`, and the `payload_record_kind` property) need no gate.
   Exhaustively derived failing set at the frozen baseline (final-gate
   derivation, superseding the intermediate 57/276 figures): **59 of the
   333** decode roots fail — 16 via the `Mapping` sites, 41 via the
   non-frozen `MemoryScope`, 1 via the non-frozen `SourceObservation`
   (one root double-counted across the first two buckets), and 2
   (`GraphSemanticSnapshotBundleV3`, `BootstrapGraphSnapshotAuthorityV3`)
   via the bare `BaseModel` annotation on `SnapshotGraphRecord.payload`,
   through which a gate-passing-only reading would share embedded
   `ClaimAssertion` instances; 274 pass. Two landed identity-keyed
   behaviors also meet the sharing-consumer definition and are
   explicitly exempt from this design's enumeration as preserved landed
   behavior: `certified_roundtrip`'s hit returning its cached validated
   twin, and `encode_semantic_contract_result`'s `_encoded_results` hit
   returning its cached result.
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
## through candidate v4 after three review rounds)

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
- `_revalidated_contract_instance` success — the codec's own proof.
  The proof output is always recorded (it is fully validated by
  construction). The **input** is recorded only when it is
  representationally identical to the proof by a **recursive** per-node
  check: at every nesting level — top-level fields, nested-model fields,
  and tuple/frozenset elements — `type(node_input) is type(node_proof)`
  and the values compare equal. Plain equality is insufficient at any
  depth: pydantic `__eq__` compares `__dict__`s with `==`, which is
  type-blind for `(str, StrEnum)`, `(bool, int)`, `(int, float)`, and
  `(Decimal, float)`. Three empirically confirmed drift modes drive the
  recursion requirement: top-level lax coercion (`"3"` where `int` is
  declared), top-level enum restore (a plain `str` where
  `ClaimValueType` is declared — restored in the payload copy, with
  StrEnum equality making `input == proof` true), and **nested enum
  restore at depth >= 2** (a plain `str` inside
  `predicates[i].object_literal_type` of a gate-passing root passes the
  one-level guard end-to-end and would be certified and shared). For
  **frozenset nodes the letter requires an explicit element pairing**:
  plain set equality and `(exact type, ==)`-paired multiset matching are
  both insufficient (set `==` is type-blind at element interiors; nested
  frozensets defeat terminal pairing), so implementations must pair
  elements by canonical-encoding sort (or an equivalent recursive
  multiset matcher over encodings) before applying the per-node check.
  The recursion domain is closed for gate-passing types (rule 4 excludes
  every mutable container, `object`/`Any` field, and bare/non-frozen
  model annotation, so every node is a frozen model, tuple, frozenset,
  or immutable scalar), making the check total.
- **Graph-family construction** — one shared owner helper wraps the
  complete-validation construction sites for the graph-record unions and
  records the constructed instance: `_GraphRecord.create`
  (`graph_records.py:101-107`), `_materialize_planning_payload`
  (`graph_planning.py:1465`), `_snapshot_record` (`:1344`),
  `_rebuild_reprojected_record`'s adapter branch (`:1340`) **and its
  temporal-carrier branch (`:1329-1336`, `type(record).model_validate`,
  confirmed missing by two reviewers in round 2)**, the carrier
  constructions in `carriers.py` (`compile_accepted_carriers` and its
  helpers' `model_validate` sites), and
  `SnapshotGraphRecord.validate_payload` (`graph_records.py:372`) /
  `validate_record` (`:380`). The sort-subscript adapter call
  (`graph_planning.py:1002-1004`) is a consumer fallback, not a
  construction site. Without these recording points no graph record or
  carrier is certified and fix 3 is inert (round 1, two reviewers).
- **Event-replay carrier adapter** — the `_CARRIER_ADAPTER.validate_python`
  success in `build_semantic_memory_event` itself records the carrier, so
  even the uncertified fallback path certifies for later boundaries.

Coverage against the census's 79 first-encounter encode roots:
content-addressed and BootstrapV3 contracts (~45 classes) via the digest
registry; `PreparedSource` via `certified_roundtrip`; decoded reloads via
fix 2; graph records and carriers via the graph-family construction
recording points (adapter and `model_validate` constructions alike).
Instances constructed by owner code with no recording point stay
uncertified and pay the full path — the design claims no universal skip.

### Fix 1 — codec proof-tree avoidance

`encode_semantic_contract`'s lean path (and
`_build_validated_semantic_contract_result`) consults the registry before
constructing the proof tree: a certified instance **of a rule-4
gate-passing type** skips the `model_validate(restore_closed_wire_
enums(payload))` construction and the result's `contract` field shares
the certified input instance; emission and all other stages are
identical. Gate-failing types always run the proof and keep the freshly
constructed proof instance as `contract`. Uncertified inputs run the
existing proof, which then certifies the proof output and — subject to
the representational-identity guard — the input. The lowered payload is
still materialized (emission needs it); the memo footprint is unchanged.

### Fix 2 — decode-instance memo

`decode_semantic_contract` memoizes `(expected_type, raw bytes) ->
model` on the same scope, **engaging only when `max_nodes` and
`max_depth` are both `None`** — limited calls neither consult nor record,
mirroring the landed canonicity-verdict bypass in full (rule 7; identical
bytes can legitimately succeed or reject under different limits, and the
bounded recovery decoders in `source_normalization_repository.py` share
payloads with the unbounded delivery path). First decode always runs the
full decode + `model_validate` + canonicity cross-check and records the
instance; the memo serves only byte-identical unlimited repeat decodes.
Sharing is gated on the deep-immutability check (rule 4); every
gate-failing kind keeps full fresh construction. Capacity: 2,048 entries
(60x the measured 34 unique raws per delivery), first-wins, no eviction.
Raw `decode_typed_value` dict trees stay unmemoized (mutable, aliasing
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
  payloads (`:794`) and `create()`/reprojection/carrier-constructed
  outputs (`:941-999`; including the `carriers.py`-constructed
  `identity_record` and the `:1329`-constructed temporal carriers), all
  certified at their construction recording points in the v3 family.
  The certified **gate-passing** path passes the payload through
  (gate-failing kinds — concretely `ClaimAssertion` — keep the full
  adapter path, rule 4), and `SnapshotGraphRecord` skips only the
  **adapter re-validation lines** (`validate_payload`'s revalidate call
  when the input is a certified gate-passing instance, and
  `validate_record`'s redundant adapter call under the same condition);
  the
  binding checks in `validate_record` (`record_id == graph_record_id`,
  `record_version`, `record_digest`, `codec_fingerprint`,
  `persistence_schema_fingerprint` against the manifest) and payload
  normalization run on **every** path. For records certified at a
  construction recording point, the four adapter validations collapse to
  one (the construction); records constructed at sites outside the
  recording family conservatively keep the full count.
- `event_replay.py:817` (`build_semantic_memory_event`): a certified
  carrier instance that is both a `CommittedRecord` union member
  (runtime type-family check, rule 2) and gate-passing (rule 4 — so
  `ClaimAssertion` carriers keep the adapter path) is used directly;
  anything else keeps the full adapter call and its exact
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
| Copy (content-equal) | plain `model_copy` of a certified instance at the **identity/byte-keyed structures** (instance registry, decode memo, fix-1/2/3 consumers) | new identity → full path (conservative). The landed `_verified` digest registry's substitution hit for a content-equal copy is unchanged behavior (rule 2(b)) | arena suite |
| Representational drift | all empirically confirmed modes: top-level lax coercion (`"3"` for `int`), top-level enum restore (plain `str` for `ClaimValueType`), nested enum restore at depth >= 2 (`predicates[i].object_literal_type`), and drift nested inside frozensets (including frozenset-of-frozensets) | input fails the recursive representational-identity guard (with the pinned frozenset element pairing) at its depth → not certified → full path; never shared | arena suite |
| Immutability gate | the 59 exhaustively derived gate-failing decode-root kinds at every sharing consumer — including `ClaimAssertion` at the fix-3 consumers and the two bare-`BaseModel`-payload snapshot bundles at the fix-2 memo | full fresh construction and revalidation; per-type cached verdict rejects them | arena suite (shared consumer family) |
| Immutability gate | a type whose annotation parameter tree contains `Mapping`/`dict`/`list`/`set` or a mutable `Sequence` anywhere — direct, nested-model, or inside tuple/union/`Annotated` arguments — or an `object`/`Any`-annotated field | rejected by the first-encounter computation → full path; cached verdicts are never invalidated (nothing is recomputed) | arena suite |
| Cross-operation | post-close lookup miss **per structure**. Complete family: the seven `CanonicalDigestVerificationScope` structures (`_verified`, `_encoded_results`, `_encoded_bytes`, `_lowered_values`, `_roundtrips`, the new instance registry, the new decode memo) plus the emission scope's `_emitted`/`_strings`/`_canonicity_verified`. Observed today: `_verified`, `_encoded_bytes`, `_emitted` only — new close-purge observers required for `_encoded_results`, `_lowered_values`, `_roundtrips`, the instance registry, and the decode memo | post-close full-path re-execution observed via the existing arena-suite counter pattern (behavioral miss primary); per-structure count properties per the Phase 5 identity budget | arena suite |
| Capacity refusal | over-limit entry after refusal | same complete family, same observation mechanism — one refusal-purge observer per currently-unobserved structure | arena suite |
| Decode limits | bounded `max_nodes`/`max_depth` call for bytes already decoded unbounded; and a limited call followed by an unlimited call | limited calls neither consult nor record; the limit still rejects; the later unlimited call takes the full first-decode path | arena suite (codec rows extend the arena suite — no separate codec suite file exists) |
| Boundaries | decode of new bytes; writer admission; persistence commit; provider ingress | complete validation unchanged | existing suites |
| Accounting | disabled-mode digest calls; arena snapshot field set; terminal-snapshot contract | digest count exactly 43,756 via the PBD-EXP-014 v2 harness (revision-bound local evidence in the successor's gate ledger, not a CI claim); exact field tuple of both snapshot dataclasses pinned as a deterministic unit assertion in the arena suite | harness (counts) + arena suite (field pins) |
| Determinism | digest-call counts across repeated deliveries | identical within a mode | PBD-EXP-014 v2 harness |
| Byte identity | frozen codec/vector/compatibility suites; fused-vs-reference differential; diametric parity; certified-path bytes at converted sites | green; canonical bytes unchanged | existing suites + converted-site owners |
| Concurrency | two arenas on separate threads | per-arena memo/registry counters differ; a thread-A-certified instance misses in thread B (discriminating assertion; the existing nonce test does not discriminate memo cross-talk) | arena suite |
| Aliasing (fix 2) | mutation attempt on a shared decoded model | frozen models reject assignment; every gate-failing kind is never shared (59 at the frozen baseline) | arena suite |
| Graph sites | uncertified `item` (dict or bypass-constructed) at every converted site | adapter path and existing errors preserved | graph owners |
| Graph bindings | **certified** payload with corrupted envelope binding fields (`record_id`/`record_version`/`record_digest`/fingerprints) inside an active arena | `snapshot_graph_record_binding_mismatch` still raised — the skip never drops the binding checks | graph owner (the existing corruption matrix runs without an arena and cannot catch this) |
| Replay surface | forged/bypass-constructed carrier → `build_semantic_memory_event` | exact `SemanticEventReplayError` type and message (currently unpinned anywhere — test-first) | replay owner |

Evidence classes: deterministic unit tests for every row except the
 Accounting row's digest-count clause and the Determinism row (both
revision-bound local evidence via the paused operation's PBD-EXP-014 v2
harness, recorded as a required local command in the successor's gate
ledger); the Accounting row's field-tuple pins remain deterministic unit
tests in the arena suite; profiles for construction-count deltas. No
live or operational claim. All codec-behavior rows extend the arena
suite — no separate codec suite file exists.

## Phase 5 — Draft Design Summary (v4)

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
schema change; new identities are limited to private runtime symbols
owned by the arena and codec modules plus minimal per-structure count
properties on the arena and emission scope (the `emitted_entries`
precedent) so the Phase 4 purge rows are observable without unsanctioned
white-box reads.

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

## Review Round 2 (delta) — Reconciliation Ledger (2026-09-02)

Candidate v2 SHA-256:
`53f27ac6ff52e27a7e7d1d7dde8b7f7159f97f370b198381e3e8278182820709` at
commit `33e4a38`. Targeted delta review by the same cohort on the
revised sections only.

| Finding | Source | Classification | Coordinator disposition |
| --- | --- | --- | --- |
| Recording family missed `_rebuild_reprojected_record`'s temporal-carrier branch (`graph_planning.py:1329-1336`) | spec delta-1 (P2) + correctness D2-1 (same site) | P2 / changes_required / architecture | **confirmed** — v3 adds the branch and the `carriers.py` constructions to the family; the "every adapter success" claim is scoped to construction sites with `:1003` named a consumer fallback |
| Input-recording at the codec proof certifies drifted representations (lax-coercion and enum-restore modes, empirically proven; `input == proof` true for the enum mode) | correctness D3-1 | P2 / changes_required / runtime behavior | **confirmed** — v3 records the proof output always and the input only behind a per-field representational-identity guard (`type(...) is type(...)` and equality for every field); new Phase 4 drift row |
| Consumer-side type-family match for identity hits not pinned | spec delta-2 | Not applicable / changes_required / governance | **confirmed** — v3 rule 2 adds the runtime type-family admissibility condition |
| "Copy (content-equal)" row contradicted rule 2(b) and landed behavior (a plain `model_copy` hits the landed `_verified` substitution) | spec delta-3 | Not applicable / changes_required / verification | **confirmed** — row scoped to the identity/byte-keyed structures; landed substitution hit recorded as unchanged |
| Purge-row structure family incomplete (seven digest-scope structures + emission scope; landed `_encoded_results`/`_lowered_values` also unobserved; rows disagreed) | test delta-2 | Not applicable / changes_required / verification | **confirmed** — v3 enumerates the complete family once, marks observed members, requires close+refusal observers per unobserved member |
| "Empty per structure" demanded an observation mechanism the design neither sanctioned nor budgeted | test delta-3 | Not applicable / changes_required / verification | **confirmed** — behavioral miss primary; Phase 5 identity budget sanctions minimal per-structure count properties |
| Evidence-classes paragraph misrouted the field-tuple pin into the harness class | test delta-4 | Not applicable / changes_required / verification | **confirmed** — exclusion scoped to the digest-count and determinism clauses only |
| Immutability "recomputed" row wording admitted an unconstructible reading | test delta-1 | Not applicable / changes_required / verification | **confirmed** — first-encounter computation; cached verdicts never invalidated |
| Gate letter lacked annotation-tree recursion and `object`/`Any` rejection; "six kinds" understated the measured 59 failing roots | correctness D1-1 + spec delta-5 | P3 / follow_up / architecture | **confirmed and folded into v3** (the measured set is now quoted) |
| `carriers.py` constructions and the `:1329` branch outside the family; corrected caller sentence still false for `outputs[0]`; "four-to-one" claim overstated | correctness D2-1 | P3 / follow_up / architecture | **confirmed and folded into v3** — family extended; sentences corrected; the collapse claim scoped to construction-recorded records |
| Fix-1 internal tension (skip vs. keeping a fresh `contract` for gate-failing types) | correctness (minor) | P3 / follow_up / architecture | **confirmed and folded into v3** — lean skip engages only for gate-passing types |
| Document carried both gen2 figures (52% and 60.8%) | spec delta-4 | P3 / follow_up / evidence precision | **confirmed** — stale Phase 1 figure corrected |
| Determinism stated in two rows; "codec owner test" names no existing suite file | test delta-5/6 | Not applicable / follow_up / verification | **confirmed and folded into v3** — Accounting row clause removed; codec rows re-homed to the arena suite |

No `blocks_approval` findings. Both round-2 P2 defects are determinately
corrected in candidate v3; every follow-up is folded or recorded.

## Review Round 3 (convergence verification) — Reconciliation Ledger (2026-09-02)

Candidate v3 SHA-256:
`63551dab661dfbf78945d1b7709ca641cc8d81aa39d6b97504f64b558b81f876` at
commit `09b0117`. All three reviewers verified the v3 corrections;
spec_auditor returned CLEAN; test_reviewer returned one residual
`changes_required` plus three polish follow-ups; correctness_reviewer
returned two validated P2s in the same semantic boundary (instance
sharing) that rule 4 governs — triggering the PLANS reconstruction rule
(two successive confirmed findings on one boundary: reconstruct the
boundary, do not patch).

| Finding | Source | Classification | Coordinator disposition |
| --- | --- | --- | --- |
| The representational-identity guard was one level deep; a third drift mode at nesting depth >= 2 (nested enum restore inside `predicates[i].object_literal_type` of a gate-passing root) passes it end-to-end and is certified and shared; 145 of 276 gate-passing roots carry such leaves | correctness R3-1 | P2 / changes_required / runtime behavior | **confirmed — boundary reconstructed**: the guard is now specified as a recursive per-node exact-type-and-equality check over the closed domain of gate-passing types (rule 4 excludes every mutable container and `object`/`Any`, so every node is a frozen model, tuple, frozenset, or immutable scalar, making the check total); the Phase 4 drift row names all three empirically confirmed modes |
| Fix 3's letter never applied the rule-4 gate at its sharing consumers, while `ClaimAssertion` (a carrier kind, union member, and gate-failing type by annotation) flows exactly through them | correctness R3-2 | P2 / changes_required / architecture | **confirmed — boundary reconstructed**: rule 4 restated as the one closed sharing rule enumerating every sharing consumer by name (fix 1 `contract` field, fix 2 memo return, fix 3 payload passthrough / `SnapshotGraphRecord` skips / carrier direct use); fix 3 states the gate condition and the `ClaimAssertion` consequence at each site; attribute-read conversions explicitly need no gate |
| Gate-failing count is 57, not 59 (16 + 41 + 1 - one true bucket overlap) | correctness R3-3 + test R3-3 (arithmetic) | P3 / follow_up / verification | **confirmed and corrected** — 57 of 333 with the corrected overlap note |
| Residual phantom "codec owner test" owner cell (Aliasing row) contradicting the evidence-classes paragraph | test R3-1 | Not applicable / changes_required / verification | **confirmed** — cell re-homed to the arena suite |
| Immutability row parenthetical omitted tuple/union/`Annotated` hiding places | test R3-2 | P3 / follow_up / verification | **confirmed and folded** — parameter-tree wording |
| Aliasing row retained the stale "six kinds" framing | test R3-4 | P3 / follow_up / verification | **confirmed and folded** |
| Editorial residue: stale v2 section tags; coverage sentence said "adapter recording points" while the family includes `model_validate` constructions; `:1003` vs `:1002-1004` | spec R3 (non-finding) | record-only | **folded** — tags updated, sentence corrected; ledger rows keep their original `:1003` citations as history |

No `blocks_approval` findings. Both round-3 P2s are resolved by
reconstructing the sharing boundary as one closed rule rather than
another patch.

## Final Gate And Approval Decision (2026-09-02)

Candidate v4 SHA-256:
`dbc20978c5d1113eaeb3b4fd07ae7adf322b2169f4f8cd01d3ba2b1e349ca12e` at
commit `71ae1cb`. Final correctness verification on the two round-3
reconstructions: **the recursive guard rejected the round-3 nested drift
mode end-to-end and no fourth mode escaped within the closed domain; the
five-site gate enumeration verified clean at every sharing consumer.**
Three findings:

| Finding | Source | Classification | Coordinator disposition |
| --- | --- | --- | --- |
| The gate-failing family is 59, not 57: two further roots (`GraphSemanticSnapshotBundleV3`, `BootstrapGraphSnapshotAuthorityV3`) fail via the bare `BaseModel` annotation on `SnapshotGraphRecord.payload`; under the 57-family the fix-2 memo would share decoded bundles embedding mutable `ClaimAssertion` instances | final gate A | P2 / changes_required / verification | **confirmed and corrected in v5** — rule 4 now fails bare/non-frozen model annotations (including `BaseModel`); the exhaustively derived set is quoted (16 + 41 + 1 − 1 overlap + 2 = 59 failing, 274 passing); the intermediate 57/276 figures and the runtime-scan-derived "145 of 276" estimate are superseded |
| Frozenset element-pairing underspecified; equality-based implementations re-open a drift hole on six live frozenset-carrying roots | final gate B | P3 / follow_up / verification | **confirmed and folded into v5** — the guard letter pins canonical-encoding-sort pairing (or equivalent recursive multiset matching); the Phase 4 drift row adds the frozenset-nested mode |
| The "closed" sharing-consumer enumeration omitted two landed identity-keyed behaviors that meet its definition (`certified_roundtrip` hits, `_encoded_results` hits) | final gate C | P3 / follow_up / architecture | **confirmed and folded into v5** — both named and exempted as preserved landed behavior |

**Approval decision.** The v5 corrections are figure-exhaustiveness and
specification-pinning edits derived from the final gate's own
reproduced measurement; they widen the gate-failing family (strictly
conservative: more kinds keep the full path) and add an implementability
pin, introducing no new semantic surface. No fifth review round was run;
the coordinator verified the arithmetic and the monotone-safety of the
corrections directly. Under the recorded scope, sources, and review
method (three full cohort rounds, one delta round, one reconstruction
gate, one final gate — 38 findings, all reconciled above, zero
`blocks_approval`, zero unresolved `changes_required`):

- Final design outcome: **APPROVED WITH FOLLOW-UPS**.
- Frozen candidate v5 SHA-256: recorded in the Progress Log below.
- Follow-ups carried to the successor: the deferred `gc.freeze()`
  import-time decision (out of scope by user direction); the
  schema-level freeze of the four mutable field sites and
  `MemoryScope`/`SourceObservation` (candidate follow-up that would
  shrink the gate-failing family); the immutable-container conversion
  alternative recorded in Phase 3.
- Production code changed by this design operation: `false`.

## Progress Log

- 2026-09-02: opened from the paused implementation operation's census
  (CMR-EXP-008) and the user's fix ordering (1 → 3 → 2). Phase 3 sites
  verified against `585d51c`.
- 2026-09-02: candidate v1 (SHA-256 `b4aafd0b…1e4c`) reviewed by the full
  cohort; 15 findings reconciled above (two P2 design defects confirmed
  and corrected); candidate v2 drafted.
- 2026-09-02: candidate v2 (`53f27ac…0709`) delta-reviewed by the cohort;
  13 findings reconciled above (two P2 defects corrected — the missing
  temporal-carrier/carrier recording points and the representational-
  drift certification hole); candidate v3 drafted.
- 2026-09-02: candidate v3 (`63551da…876`) convergence-verified; seven
  findings reconciled above (two P2s in the sharing boundary — the
  one-level guard and the ungated fix-3 consumers — resolved by
  reconstructing rule 4 as the closed sharing rule and making the guard
  recursive over its closed domain); candidate v4 drafted.
- 2026-09-02: candidate v4 (`dbc209…a12e`) final-gate verified (guard and
  enumeration clean); three findings reconciled above; candidate v5
  frozen and **approved with follow-ups**. Frozen candidate v5 SHA-256:
  `284fa5b63b631871efda10575e49a3f5e15c1f078b8dbb040dc1dd65d5660f47`;
  the design operation is complete.

## Next Action

Design operation complete. Resume the paused parent implementation
operation (`../semantic-ingestion-canonical-member-reuse-2026-09-01/`)
under `$implement-design` with this approved candidate v5 as the
governing fix-design; its first slice is the validated-instance registry
with the recursive guard and the closed sharing rule, followed by the
fix-3 conversions, fix 2, the Phase 4 test families, and the quiet-host
re-measurement.
