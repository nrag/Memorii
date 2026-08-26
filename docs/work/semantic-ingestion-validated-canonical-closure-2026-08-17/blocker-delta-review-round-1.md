# Blocker Delta Review Round 1

Date: 2026-08-17

Candidate lock:
`2a339d7131e7e70bf667a9e969a8cb04c979ef33db9c59c1b8b1d5f64be78dd6`

Scope: `VCC-DREV-001` and `VCC-DREV-008` only.

Four independent targeted reviewers first confirmed the candidate manifest and
all 26 tracked hashes. The initial governance stop caused by the absence of a
new freeze is resolved by candidate v2. Substantive review found three
remaining determinate corrections.

| ID | Product priority | Approval disposition | Finding type | Coordinator classification | Required correction |
| --- | --- | --- | --- | --- | --- |
| `VCC-DREV-001A` | Not applicable | changes_required | architecture / feasibility | confirmed | Normalizer map/set ordering calls `_json` before final root serialization, so the prototype emits multiple span reports. Introduce a non-span ordering-byte helper used only by `_normalized_typed_json`; invoke `_json_with_spans` exactly once for the final normalized root and assert one invocation for every accepted CTV family. |
| `VCC-DREV-001B` | Not applicable | changes_required | runtime behavior / compatibility | confirmed | The prototype calls `check` once per emitted node and again through scalar `_json`, changing cancellation behavior. Preserve the existing callback order and count exactly, and add stateful success/failure threshold equivalence cells for every accepted CTV family. |
| `VCC-DREV-008A` | Not applicable | changes_required | governance / verification | confirmed | The ledger validator checks nonempty fields and cross-file token presence rather than exact row-local bindings. Encode and validate structured target parameters, ordered call edges, per-row caller query/count, validation boundary, durable-writer edge/outcome, fallback branch, status, and executable planned-proof IDs. Add deterministic mutations for wrong authority parameter, disconnected owner edge, wrong caller count, missing durable writer, and missing fallback/proof. |

## Disposition

- `VCC-DREV-001`: `OPEN`.
- `VCC-DREV-008`: `OPEN`.
- Candidate v2 remains the immutable identity of this targeted
  `CHANGES_REQUIRED` decision and is not approved for implementation.
- Findings `VCC-DREV-002` through `VCC-DREV-010`, excluding `008`, were not
  reviewed and retain their round-one dispositions.
