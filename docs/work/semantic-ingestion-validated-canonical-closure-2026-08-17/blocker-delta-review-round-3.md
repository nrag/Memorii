# Blocker Delta Review Round 3

Date: 2026-08-17

Candidate lock:
`0cf54b92d4a06f0fa7eb005371d2603e03140bfc67e43c1f19fc7e52e662e4a5`

Parent candidate lock:
`67d87db1c82425602a557f924900d4be4e183fdfbcb6ff6406dcad26099738ea`

Mode: independent targeted delta review.

Scope: `VCC-DREV-001C`, `VCC-DREV-001D`, `VCC-DREV-001E`, and
`VCC-DREV-008B` only, including regressions within their affected semantic
boundaries. No production code or repository tests changed during review.

The `spec_auditor`, `correctness_reviewer`, and `test_reviewer` independently
verified the candidate lock and all 40 tracked artifact hashes. The bounded
decision is `CHANGES_REQUIRED`.

## Reconciled Findings

| ID | Product priority | Approval disposition | Finding type | Coordinator classification | Status | Required correction |
| --- | --- | --- | --- | --- | --- | --- |
| `VCC-DREV-001C` | Not applicable | changes_required | architecture / verification | already resolved | `CLOSED` | None. The prior correction required counting the proposed final span-writer seam rather than its public encoder. `WriterSession.span_json` is that prototype seam, its count is taken inside the enabled owner, and duplicate map and set final writes fail. Requiring a production span writer before implementation would inflate design-feasibility evidence into implementation evidence. |
| `VCC-DREV-001D` | Not applicable | changes_required | runtime behavior / compatibility verification | confirmed | `OPEN` | Observe actual callback invocation order at the codec normalizer/emitter boundary. The current reordered attack changes recorded labels while invoking `check()` in the original order. Add stateful reorder, omission, and extra-invocation attacks that preserve bytes and, for reorder, preserve callback count. |
| `VCC-DREV-001E` | Not applicable | changes_required | verification | confirmed | `OPEN` | Construct decoded set/frozenset members that force `_HashableCtvMap`, `_ImmutableCtvList`, `_ImmutableCtvTuple`, `_ImmutableCtvSet`, `_TagAwareCtvSet`, and `_TagAwareCtvFrozenSet`; assert fixture types and run byte, decoder/re-encoder, span, writer-count, and corrected callback proofs for every wrapper and nested combination. |
| `VCC-DREV-008B` | Not applicable | changes_required | governance / verification | confirmed | `OPEN` | Replace same-file/same-token checks with owner-qualified AST or bounded runtime traces proving each directed call or construction edge, authority argument, reachable validation/fallback branch, and durable or no-write outcome. Reject reversed, invented, duplicate-symbol, unreachable-boundary, capture-only-root, optional-authority-bypass, and R08 durable-write substitutions. |

All three open findings are determinate `contract_conformance_action` work.
They do not establish a P1 or P2 product defect and do not authorize production
or repository-test changes during this design operation.

## Direct Evidence

- Candidate validation passed with 40 matching tracked artifacts and no
  failures for the frozen v4 lock.
- `vcc_exp_006_complete_owner_seam_proof.py` records the reorder marker before
  calling `check()` and therefore does not reorder callback execution.
- Its `decoded_immutable_*` fixtures decode simple top-level containers; the
  production decoder creates immutable wrappers only when converting decoded
  set members through `_hashable_ctv_value`.
- `validate_production_entrypoint_bindings_v4.py` compares declared edges with
  the independent expected rows but does not inspect corresponding caller AST
  edges. It accepts the current `VCC-R04` chain even though production
  `encode_typed_value` calls `_normalized_typed_json` and `_json`, not the
  declared reverse direction.
- `VCC-R02` similarly declares `_json` calling persistence, while `_json` is a
  serializer with no persistence edge. `VCC-R08` declares the arena calling
  `sync_event`, while `sync_event` constructs and owns the arena lifecycle.

## Reviewer Observation Reconciliation

- The test reviewer's proposed reopening of `VCC-DREV-001C` is `unsupported`.
  It substitutes current-production instrumentation for the prior report's
  bounded prototype span-writer requirement. Production implementation must
  later prove the same invariant, but that is a separate evidence state.
- The spec and correctness reviewers' closure of `VCC-DREV-001C` is accepted as
  `already resolved`.
- All three reviewers' `VCC-DREV-001D` concerns are one confirmed
  family-complete finding: the proof substitutes labels instead of changing
  callback execution.
- All wrapper-coverage observations reconcile into confirmed
  `VCC-DREV-001E`. Proposed malformed-input additions are `outside scope`
  because the frozen finding requires complete accepted-algebra coverage, not
  a new rejected-input matrix.
- All ledger-path observations reconcile into confirmed `VCC-DREV-008B`; the
  reversed `VCC-R04` edge is a concrete false positive accepted by the current
  validator, and the remaining bypasses are adjacent members of the same
  owner-qualified reachability invariant.

## Disposition

- `VCC-DREV-001C`: `CLOSED`.
- `VCC-DREV-001D`: `OPEN`.
- `VCC-DREV-001E`: `OPEN`.
- `VCC-DREV-008B`: `OPEN`.
- Candidate v4 remains the immutable identity of this targeted
  `CHANGES_REQUIRED` decision and is not approved for implementation.
- This bounded delta decision does not make a whole-design approval claim.

