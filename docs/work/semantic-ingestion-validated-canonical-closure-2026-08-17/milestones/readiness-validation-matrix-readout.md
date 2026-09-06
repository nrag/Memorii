# Readiness Validation Matrix Mapping

- Command source: `implementation-acceptance-v12.md`.
- Milestone mode: readiness-only (no production semantics changed yet).
- This matrix is read-only mapping only until hash drift is reconciled and implementation tests are authored.

## Lifecycle and Authority

| Acceptance row | Planned or observed command | Observable failure signal |
| --- | --- | --- |
| Disabled selection | `tests/unit/core/semantic_ingestion/...` (directed production-path matrix pending) | Any evidence lookup in disabled path, reservation side effect, outcome difference |
| Initial process refusal | `tests/unit/core/semantic_ingestion/...` (capacity rejection matrix pending) | Any partial authority or retained reservation under 5th 16 MiB simultaneous request |
| Sealed-only authority | `tests/unit/core/semantic_ingestion/...` (sealed-then-handoff matrix pending) | Lookup before seal, post-seal mutation, mixed enabled/fallback transitions |
| Five-coordinate scope | `tests/unit/core/semantic_ingestion/...` (scope mutation matrix pending) | Foreign coordinate hit or stale tenant/operation/fence/writer accepted |
| Capacity boundaries | `tests/unit/core/semantic_ingestion/...` + `vcc-exp-003b-compact-index-capacity` helpers | Wrong boundary behavior or leak across over-limit and one-over events |
| Close idempotence | `tests/unit/core/semantic_ingestion/...` (closure lifecycle matrix pending) | Non-monotonic close behavior, repeated re-open, or release drift |
| Linearizable leases | `tests/unit/core/semantic_ingestion/...` (lease race matrix pending) | Post-close lease grant or underflow on release |
| Terminal release | `tests/unit/core/semantic_ingestion/...` (terminal release matrix pending) | Missing release on non-terminal outcome or double release |
| Production ownership | Production entrypoint binding verifier + owner-ledgers | Missing typed handoff or invented owner in any mapped trigger |
| Writer admission | `tests/unit/core/semantic_ingestion/test_canonical_evidence_arena.py` planned | Sibling evidence reuse across two writer/retry invocations |

## Observability

| Acceptance row | Planned or observed command | Observable failure signal |
| --- | --- | --- |
| Closed modes | `tests/unit/core/semantic_ingestion/...` (observability mode matrix pending) | Unknown or content-bearing mode values |
| Closed terminal reasons | `tests/unit/core/semantic_ingestion/...` (terminal reason matrix pending) | Cause changes after closing or non-deterministic precedence |
| Typed counters | Dedicated output-contract test module (pending) | Non-integer/negative/overflowed counter payload |
| Reason latching | `tests/unit/core/semantic_ingestion/...` (terminal lifecycle matrix pending) | Cause changes after first terminal close |
| Reason precedence | `tests/unit/core/semantic_ingestion/...` (terminal precedence matrix pending) | Validation-failure/exception/cancel precedence inversion |
| Exact terminal cardinality | `tests/unit/core/semantic_ingestion/...` (snapshot cardinality matrix pending) | Missing or duplicate terminal snapshots |
| Content privacy | Privacy sentinel matrix (pending) | Sensitive traversal/value fields appear in emitted data |
| Sink outcomes | Sink matrix (pending) | Outcome outside recorded/unavailable or changed pipeline behavior |
| Sink isolation | Callback isolation matrix (pending) | Host callback acquires authority or blocks persistence outcome |

## Performance And Promise

| Acceptance row | Planned or observed command | Observable failure signal |
| --- | --- | --- |
| Digest reduction | `vcc-exp-002-digest-reduction-counterfactual` + production matrix harness (pending) | <90% reduction in repeated full digest computations |
| Canonical equivalence | `vcc-exp` evidence matrix (pending) | Canonical/semantic output mismatch under enabled, disabled, rejected modes |
| Independent trust | Trust-sequencing matrix (pending) | Validation or writer admission skipped in any mode |
| Capacity accounting | Capacity accounting matrix + reservation probes (pending) | Unbounded counters or mismatch against approved representation |

## Open note

- Test command identifiers in this readiness packet are intentionally explicit for scope but not yet fully materialized in file paths while write work is blocked by the current candidate/binding hash mismatch.
