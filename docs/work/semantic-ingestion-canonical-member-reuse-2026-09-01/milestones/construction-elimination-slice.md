# Milestone: Construction-Elimination Slice (registry, guard, conversions)

- Governing design: `../../semantic-ingestion-construction-elimination-2026-09-02/design.plan.md`
  (APPROVED WITH FOLLOW-UPS; frozen identity = the tree of commit `a49b32b`).
- Base revision: `e63d6f8`; sole writer: main thread.
- Requirements reconstructed independently from the approved design:

| ID | Requirement (from design Phase 2/3/4/5) | Evidence to record |
| --- | --- | --- |
| CE-1 | Validated-instance registry on `CanonicalDigestVerificationScope`: identity-keyed, strong entries, member-path entry cap, purge on exit/refusal, enabled-mode only, per-structure count properties | arena suite purge/refusal observers + counters |
| CE-2 | Deep-immutability gate: recursive annotation-parameter-tree check (reject Mapping/dict/list/set/mutable Sequence anywhere, `object`/`Any`, bare or non-frozen model annotations incl. `BaseModel`); cached per type at first encounter, never invalidated | gate unit tests (direct, nested, Annotated/tuple hiding, object/Any, bare BaseModel) |
| CE-3 | Recursive representational-identity guard at `_revalidated_contract_instance`: proof output always certified; input certified only behind per-node exact-type+equality recursion with pinned frozenset multiset pairing; closed domain by CE-2 | drift-mode tests (lax coercion, enum restore, nested enum restore, frozenset-nested) |
| CE-4 | Fix 1: codec proof skip for certified gate-passing instances; `contract` field shares the certified input for gate-passing types; gate-failing types always run the proof | arena/codec tests + frozen byte suites |
| CE-5 | Recording points: `_record_digest_verification`, `certified_roundtrip`, `decode_semantic_contract`, guarded codec proof, graph-family construction helper (adapter + `model_validate` branches incl. `:1329` temporal and `carriers.py`), `_CARRIER_ADAPTER` fallback | call-site verification + consumer tests |
| CE-6 | Fix 3 conversions: `record_kind` direct reads (`:1002-1004`, `:1497`, `payload_record_kind`), `_snapshot_record` passthrough, `SnapshotGraphRecord` adapter-line skips with binding checks always running, event-replay carrier direct use (type-family + gate) | graph/replay owner tests incl. certified-binding corruption + unpinned error surface (test-first) |
| CE-7 | Fix 2: decode-instance memo — unlimited calls only (neither consult nor record when limited), key `(expected_type, raw)`, 2,048 entries, sharing gated by CE-2 | decode-limits tests + aliasing tests |
| CE-8 | Phase 4 test families per the design's owner column (arena suite hosts codec rows; per-structure purge observers for the five unobserved structures incl. `_roundtrips`) | green focused suites |
| CE-9 | Measurement + gates: quiet-host v2 harness, construction-count probe, broad gate once at final revision | evidence files + gate logs |

Non-goals: any `gc` state change; schema/byte/digest changes; benchmark/live
claims. Completion criteria: CE-1..CE-8 locally verified with focused suites;
CE-9 recorded (broad gate may run in a following session window if the host
is loaded; the quiet-host measurement requires a quiet window by protocol).

## Progress

- 2026-09-02: opened at `e63d6f8`.
- 2026-09-02 (CE-1..CE-5, commit `da50413`): registry + decode-memo
  structures on the scope; the deep-immutability gate beside the scope
  owner (lazy on the memory-evolution side to break the package-init
  import cycle); the recursive representational-identity guard with
  backtracking frozenset pairing; the codec proof skip for certified
  gate-passing instances; digest-verification and round-trip recording
  points.  Arena + codecs + vector + parity + compatibility green.
- 2026-09-02 (CE-6/CE-7, commit `99ba698`): graph-family construction
  recording (create, materialize, snapshot, both reprojection branches,
  SnapshotGraphRecord admissions, carriers.py), the sharing-rule
  conversions (record_kind direct reads, `_snapshot_record` passthrough,
  adapter-line skips with binding checks always running, event-replay
  carrier direct use), and the decode memo with the limits rule.
  193 focused tests green; probe digest calls unchanged at 237.
- 2026-09-02 (CE-8): Phase 4 families landed in the arena suite — the
  three drift modes (the nested case proven against a gate-passing
  catalog wrapper with a clean-catalog positive control), gate verdicts
  for representative types including the gate-failing `ClaimAssertion`,
  decode-memo identity/limits/persistence, and per-structure purge
  observers for the new registry and decode memo on close and capacity
  refusal.
