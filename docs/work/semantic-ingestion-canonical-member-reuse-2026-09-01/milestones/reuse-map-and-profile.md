# Milestone: Reuse Map And Profile (ready decision)

- Revision: `34a5230` (STEP ZERO) with probes at the same tree.
- Evidence: `../evidence/cmr-exp-001-census-v1.json-line` (pure counters),
  `../evidence/cmr-exp-002-profile-summary-v1.json` and
  `../evidence/cmr-exp-002-profile-v1.txt` / `.pstats` (cProfile, 265.6s under
  ~5.4x instrumentation overhead; relative attribution only).
- Decision: `ready` — production edits authorized for the slice plan below.

## Cost attribution (relative, cProfile exclusive seconds)

| Block | Functions | Exclusive s (profiled) | Notes |
| --- | --- | --- | --- |
| Canonical emission | `_json` 4.64M calls, `_json_string` 3.96M, `walk` 581k | 36.7 + 21.6 + 15.7 | every with-spans encode emits the tree TWICE: the span walk plus the divergence cross-check `result != _json(normalized)` at `memory_evolution/ingestion_contracts.py:907` |
| Shared emission overhead | genexpr 7.6M, isinstance 21.6M, regex search 3.96M, str.encode 5.8M, bytes.join 1.38M, sorted 513k, `_validated_keys` 360k | 31.2 + 19.7 + 14.7 + 10.0 + 13.3 + 6.6 + 2.8 | dominated by the same double emission |
| Member-evidence minting | sha256 586,964 + hexdigest; dataclass `__init__` 599,030 | ~11 + 8.7 | ~4,800 spans per whole-tree encode; consumed only by the arena-staged root's lease verification (`atomic_store.py:1220`, `:4338-4342`) — minted for all 121 encodes |
| Normalization/lowering | `_normalized_typed_json` 849k, `canonical_contract_value` 646k | 12.5 + 5.4 | |
| Pydantic | `validate_python` 3,105 (5.3), `create_schema_validator` 428 (3.9), `traverse_schema` (3.2), `__eq__` 431,700 (4.4), `restore_closed_wire_enums` 254,827 (1.7) | ~17.4 | codec anti-forgery revalidation is one `model_validate` per encode; the rest is nested/round-trip validation |
| Decode | `_decode_typed_value` 105k | 1.6 | |

Multiplicity (census): **120 encode-result calls, 79 unique `(type, id)`**;
decodes 14 / 10 unique. Same-instance repeat leaders: lane results 24→12
(the stage's per-member double encode at
`semantic_ingestion/source_normalization_stage.py:374-375`), request core
9→7, reduction authority 9→7, normalization result 6→5.

## Site classification (mandatory vs internal-candidate)

Mandatory full-validation boundaries (unchanged by every slice): the codec's
anti-forgery `model_validate` on first admission of any instance;
`decode_semantic_contract` byte decode; atomic-store persistence admission
and writer handoff; reload/replay/recovery doors; public/provider ingress.

Internal-candidate surfaces (reuse allowed within one operation scope):
repeat `encode_semantic_contract` of an instance already certified by this
operation's codec; per-member double encode in the normalization stage;
repository reload comparisons re-encoding retained instances
(`source_normalization_repository.py:141,163,288-293`,
`transaction_group_plan_repository.py:91,128`); persistence artifact
re-encodes and retained-member comparisons (`persistence.py:571-773,953,965`);
sort-key and assembler re-encodes (`bootstrap_graph_terminal_preparation.py`,
`bootstrap_graph_artifact_assembler.py:292-304,484-536`,
`bootstrap_v3_evidence.py:125,148`, `bootstrap_v3_proposal.py:311`).

## Facts verified before edits

- `encode_semantic_contract_result` has exactly two production callers
  (`provider/ingestion.py:877`, `:980`), both with explicit staging; the
  bytes API `encode_semantic_contract` is the high-multiplicity surface.
- `CanonicalClosureScopeOwner.admit` deduplicates by cache key (duplicate
  returns `False`, no state change), so a memo-hit staging call stays
  correct; the staged root's first encode in the live path is a fresh
  instance (post-publication `model_validate`), so staging paths take the
  full pipeline.
- The arena's own test asserts `result.canonical_contract_bytes ==
  encode_semantic_contract(value)` (`test_canonical_evidence_arena.py:304`),
  gating lean/full byte equivalence; no test observes spans or evidence
  through the bytes API.
- `member_evidence` consumers: only the atomic store lease verification.
- The digest-verification scope already provides the operation-local,
  thread-local, bounded, purge-on-exit/refusal lifecycle the new memos ride.

## Slice plan (ordered, measured between slices)

1. **Slice A — codec certified-result memo + lean bytes path.**
   `encode_semantic_contract` consults an identity-keyed operation memo
   (strong refs; hit = the exact object this operation's codec already
   validated and encoded; miss = lean pipeline: lower → single `_json`
   emission → anti-forgery `model_validate` → record). The lean path emits
   once through the same `_json` writer (no span walk, no cross-check, no
   per-span digests, no evidence minting). `encode_semantic_contract_result`
   keeps the full pipeline and memoizes full results. Disabled mode allocates
   no memo (unchanged accounting).
2. **Slice D — member-granular reuse inside remaining encodes** (lowering /
   normalization / emission memos so parents splice certified child
   emissions), per the approved Cross-Root Reuse contract. Only as needed
   after measuring A.
3. **Slice C — per-site internal round-trip elimination**
   (`model_validate(model_dump())` sites whose input authority is an
   operation-local validated value), each site individually classified;
   mandatory boundaries untouched. Only as needed after measuring A(+D).

## Failure and authority analysis (Slice A)

- A memo hit requires object identity with an instance this operation's
  codec fully validated; forgeries require a new object identity and take
  the full path. The key is not caller-declarable (unlike digests), so no
  declaration-plus-equality check is needed; this matches the approved
  threat model (arbitrary trusted-process code execution out of scope).
- The memo rides `CanonicalDigestVerificationScope`: purged at arena exit and
  on capacity refusal, bounded entries, strong references prevent id reuse,
  enabled mode only.
- No validator, gate, accounting assertion, byte, or persisted shape changes:
  byte identity is by construction (same normalization, same writer) and is
  gated by the frozen suites plus the arena byte-equality assertion.
