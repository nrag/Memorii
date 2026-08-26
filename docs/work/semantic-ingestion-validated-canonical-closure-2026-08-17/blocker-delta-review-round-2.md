# Blocker Delta Review Round 2

Date: 2026-08-17

Candidate lock:
`67d87db1c82425602a557f924900d4be4e183fdfbcb6ff6406dcad26099738ea`

Scope: `VCC-DREV-001A`, `VCC-DREV-001B`, and `VCC-DREV-008A` only.

All three independent reviewers verified the candidate lock and all 32 tracked
artifact hashes. The bounded decision is `CHANGES_REQUIRED`.

## Reconciled Findings

| ID | Product priority | Approval disposition | Finding type | Coordinator classification | Required correction |
| --- | --- | --- | --- | --- | --- |
| `VCC-DREV-001C` | Not applicable | changes_required | architecture / verification | confirmed | The proof counts calls to the replacement public encoder, not invocations of the actual final span-writer seam. Instrument the span writer itself; inject a second final write for map and set cases and require the public proof to fail on count other than one. |
| `VCC-DREV-001D` | Not applicable | changes_required | runtime behavior / compatibility verification | confirmed | Count and four threshold outcomes do not distinguish callback reordering with the same count. Record a complete path-aware callback schedule for baseline and enabled owner traversals, require exact equality, and prove reordered and extra callbacks fail. |
| `VCC-DREV-001E` | Not applicable | changes_required | verification | confirmed | The 11 fixtures omit accepted `datetime`, `timedelta`, decoded immutable map/list/tuple/set wrappers, and nested ordered combinations. Add every accepted algebra family and run all byte, decoder, writer-count, callback, and span-integrity assertions for each. |
| `VCC-DREV-008B` | Not applicable | changes_required | governance / verification | confirmed | The v3 validator compares the ledger with itself. Coordinated parameter/binding or chain/edge substitutions can pass, the repeated count `5` is repository-wide rather than scoped to the declared `capture_cell` edge, and validation/durable/fallback tokens need not be connected to the row path. Add an independently authored frozen expected-row contract and symbol-scoped AST edge/count validation; trace existing validation, fallback, and durable outcomes from each row anchor, including explicit no-write evidence for `VCC-R08`. Add coordinated-mutation cells. |

## Conflicting Reviewer Observation

The test reviewer classified `VCC-DREV-008A` as closed because all five
isolated mutations failed. That closure is `unsupported` after validating the
spec auditor's coordinated-mutation counterexample: the generator and ledger
can change together while the validator still passes. The stronger finding is
therefore confirmed as `VCC-DREV-008B`.

## Disposition

- `VCC-DREV-001`: `OPEN`.
- `VCC-DREV-008`: `OPEN`.
- Candidate v3 remains the immutable identity of this targeted
  `CHANGES_REQUIRED` decision and is not approved for implementation.
- Findings outside the targeted scope retain their prior dispositions.
