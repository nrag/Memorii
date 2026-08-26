# Canonical Evidence Performance Implementation

- Work ID: semantic-ingestion-canonical-evidence-performance-2026-08-15
- Work type: implementation
- Status: blocked
- Coordinator: Codex
- Created: 2026-08-15
- Last updated: 2026-08-16 (requirements-first performance gate frozen)
- Parent WorkPlan: docs/work/semantic-ingestion-canonical-evidence-performance-2026-08-15/design.plan.md
- Related WorkPlans: docs/work/semantic-ingestion-canonical-evidence-performance-observability-2026-08-16/design.plan.md; docs/work/semantic-ingestion-canonical-evidence-production-performance-2026-08-16/debug.plan.md; docs/work/semantic-ingestion-codec-owned-attestation-2026-08-16/design.plan.md; docs/work/semantic-ingestion-validation-boundary-performance-2026-08-17/design.plan.md
- Canonical inputs: canonical evidence design and frozen lock
- Expected outputs: bounded production arena implementation followed by requirements-first evidence

## Current State

The DREV-009 bounded production slice now supplies the missing non-test caller:
`CanonicalEvidenceCaptureSupervisor.capture_cell` creates an isolated child,
obtains only `build_verified_production_host_authority`, constructs the selected
public root with the opaque authority, and calls public `sync_event` once. The
factory verifies production-trust material once and all four roots reject
legacy authority co-injection when the bundle is supplied. No tests or
validation commands were run, and no terminal durable receipt, ordered trace,
baseline, arena, or approval claim is made.

## Production Entrypoint Bindings

`docs/design/semantic_ingestion_canonical_evidence/production-entrypoint-bindings-v1.json`
records the implemented but unvalidated `CanonicalEvidenceCaptureSupervisor`
callsite and authority path. The future arena remains
`not_implemented_fail_closed`; no runtime persistence or durable-receipt
requirement is claimed complete.

## Constraints

The user replaced the baseline-first gate on 2026-08-16 after source-bound
profiling confirmed 1,845 redundant digest calls in one operation. Arena edits
are authorized only against the immutable uncached diagnostic manifest and the
frozen requirements-first contract. This authorization does not create an
M3.1 baseline or approval claim. Implementation must preserve the
owner/create-nonce/private-bridge/retry/finally-teardown/error-cancel/
concurrency/capacity contract.

## Progress Log

- 2026-08-16: feasibility-only tooling and contract remediation completed in
  linked design work; implementation remained blocked on a real public
  graph-authority composition path.
- 2026-08-16: DREV-009 bounded production slice implemented
  `production_authority.py`, `production_capture.py`, and explicit authority
  threading through direct, factory, filesystem, and Hermes roots. Evidence
  maturity is `implemented` only; no focused validation was run.

## Historical Remediation Boundary

The second design-remediation pass confirms the production implementation is
still blocked, not merely pending: no allowed evidence fixture can construct a
production-trust public host path without prohibited unit-test imports or the
private scenario constructor. The built-in default graph authority was not
changed. See `docs/reviews/semantic-ingestion-canonical-evidence-performance/delta-review-remediation-pass-2-2026-08-16.md`.

## Historical Pass-3 Status

DREV-002 through DREV-005 closed in the linked design/tooling slice before this
production slice. At that time the binding map had no non-test production
caller that reached the canonical owner with production-trust host authority.
Scenario/private helpers remain forbidden because they use scenario-test
material and private graph injection. This historical status does not describe
the implemented DREV-009 authority path above.

Evidence: `docs/reviews/semantic-ingestion-canonical-evidence-performance/delta-review-remediation-pass-3-2026-08-16.md`.

## Next Action

Run one bounded independent delta review of the requirements-first gate,
source-bound diagnostic authority, frozen capacity limits, and evidence matrix;
if it closes, implement the operation-scoped arena in the next slice.

Current proof-contract lock:
`24da95523b9a050266034cd6f3b923d52a4d8cc97cf83d32d83c1285bb2d99c3`,
frozen over the requirements-first design and superseding
`c620e09b4e578ca16717bc2d67a5aa95c7296dc60344d110b042151268855350`.

## DREV-001/DREV-002 bounded remediation status

The exactness remediation is tooling-only and determinate pending targeted
rereview. DREV-001 remains `Not applicable / changes_required / verification
contract_conformance_action`; DREV-002 remains `Not applicable /
changes_required / verification regression`. This historical fixture-only
evidence did not establish a non-test production caller or a runtime/persistence
claim before the present DREV-009 slice.

The final bounded remediation runs the lock-pinned static AST grammar validator
in isolated mode after external source-frame/source-byte verification and before
execution-lock creation or runner-target invocation. The verifier interpreter
is explicitly distinct from the runner target in the isolated repinned harness:
function type comment, assignment type comment, and type-ignore mutations must
run only the verifier, exit 64, leave no runner-target sentinel, and create no
execution/result lock. Source-frame variants retain their stronger before-any-
interpreter proof. Frozen outer-lock tamper remains a separate precondition
mutation.

The DREV-007/DREV-009 tooling delta threads independently resolved side locks
through public record/pair validation and adds a real external two-authority
`bind`/`validate` topology self-test with matching-hash mutation proof. The
implementation slice did not establish the zero-caller production binding; this
prior evidence makes no runtime, persistence, baseline, or approval claim.

## Final bounded DREV-007/DREV-009 proof assertions (2026-08-16)

The fixture-only final assertion delta is frozen in lock
`54ba23f7ff6633fdf5038470de7fdb47bdbef2963648823a575d32a9bee973c9`.
The external bind proof captures stdout and requires it to be exactly the SHA-256
of the O_EXCL-created binding; validation receives that captured hash, while a
same-path replay must exit 64 with the original binding bytes and hash unchanged.
The mixed-schedule proof repins one side to a schema-valid alternate
`execution_order` permutation, regenerates that side's records, retained
ordinals, execution lock, and result lock, and independently validates the
candidate pair before requiring the cross-side mixed-authority rejection with
matching external hashes. The durable proof changes only one result-lock receipt
`effect_digest`, preserves schema and replay uniqueness, recomputes result-lock
and comparison-binding hashes, and requires the result-lock-to-record receipt
equality rejection. No production code/tests, baseline, approval, or
production-entrypoint binding changed.

Focused JSON, Python compilation, and shell syntax checks passed for the prior
fixture-only slice. The full fixture self-test reached its terminal result and
exited 0 after approximately 270 seconds. Those results do not validate the
present production slice, which is `implemented` only and has the single
focused-validation next action above.

## Authority/source-frame family closure (2026-08-16)

- Decision: `CLOSED` for the bounded authority/source-frame manifest correction at candidate lock `24da95523b9a050266034cd6f3b923d52a4d8cc97cf83d32d83c1285bb2d99c3`.
- Deterministic evidence: all 7 required source paths matched current file SHA-256 values; all 10 required symbols were unique and exact; production manifest `source_frames` equaled `public_matrix.source_frame_map`; every one of the 21 candidate-lock artifact hashes matched; both linked WorkPlans referenced the frozen lock; external capture remained `specified_not_implemented_fail_closed`.
- Independent evidence: `correctness_reviewer` agent `01a00d48-e665-7e60-8013-3698cc2b7b00` returned `CLOSED` with no findings under the repository finding-classification contract.
- Approval boundary: this decision approves only the corrected authority/source-frame family. It does not approve or close the canonical-evidence arena/cache implementation, production performance evidence, external durable receipt/result-lock capture, or M3.1.

## Canonical-evidence arena implementation slice (2026-08-16)

- Candidate lock: `24da95523b9a050266034cd6f3b923d52a4d8cc97cf83d32d83c1285bb2d99c3` supersedes `0731a9ef2753a8fd3908af27901f3def58de91db2c443d6b83bc159e4eddbdaf`.
- Implemented: operation-local arena lifecycle at provider sync/write boundaries; exact canonical bytes/type/profile/codec/domain key; private nonce; successful-validation-only admission; 128-entry, 65,536-byte item, 1,048,576-byte operation, and 67,108,864-byte process reservation limits; no eviction, overwrite, negative cache, or cross-operation entries.
- Evidence: targeted arena family `5 passed in 12.79s`; touched production modules compiled successfully.
- Remaining: full production-path behavior/performance capture, operation-charge and process-reservation executable boundaries, cancellation/retry lifecycle proof, independent family review, and M3.1 approval remain open.

## Production arena evidence checkpoint (2026-08-16)

- Candidate diagnostic manifest: `docs/work/semantic-ingestion-canonical-evidence-production-performance-2026-08-16/evidence/candidate-diagnostic-v1.json` SHA-256 `ee57050114123061ae4d306c72c7bdb307e1a7862c34592b5b1428c266e1c509`. It is diagnostic evidence and does not certify M3.1.
- Production `ProviderMemoryService.sync_event`: `6.934712s` candidate versus `10.204397s` recorded uncached diagnostic, reduction `0.3204`; required reduction `0.75`, therefore threshold not met.
- Targeted arena proof family: `9 passed in 8.44s`, covering exact reuse, invalid non-admission, nonce substitution, entry/item/operation/process limits, no eviction, cross-arena isolation, concurrency, and idempotent exceptional teardown.
- Residual profile: `contract_digest` remains 1,526 calls / 4.662 cumulative seconds and `encode_typed_value` remains 1,863 calls / 5.658 cumulative seconds. That proposed next action was evaluated by the safe-byte-reuse feasibility slice and superseded by its NO-GO decision.

## Safe canonical-byte reuse feasibility decision (2026-08-16)

- Decision: `NO-GO` for further implementation under the current approved design. Evidence: `docs/work/semantic-ingestion-canonical-evidence-production-performance-2026-08-16/evidence/safe-byte-reuse-feasibility-v1.json` SHA-256 `2f7c12bb0df1b98eb4005908544d0b769715baaa34bfdd0219966594eb311577`.
- Same-mode feasibility only: arena enabled `2.483143s`; process-saturation legacy fallback `2.637856s`; observed improvement `0.0587` versus required `0.75`. This same-revision comparison is not M3.1 certification.
- Security boundary: the canonical codec emits whole-value bytes only and has no trusted subtree-byte or validator-attestation output. Caller digest, object identity, shallow immutability, secondary fingerprint, and cross-operation sharing shortcuts remain prohibited.
- Finding classification: `Not applicable / blocks_approval / architecture and verification`; the missing codec-owned subtree attestation contract prevents a determinate safe performance correction under the approved design.
- Sole next action: pause this implementation milestone and open a linked `$build-design` operation for codec-owned subtree attestations or an explicitly revised performance contract before further production optimization.

## Linked codec-owned attestation design operation (2026-08-16)

- The linked design operation is active at `docs/work/semantic-ingestion-codec-owned-attestation-2026-08-16/design.plan.md`.
- This implementation WorkPlan is blocked pending an independently approved design and executable feasibility evidence. Production optimization, review, and M3.1 closure remain paused.
- The linked design WorkPlan now owns the detailed requirements, authority chain, experiments, attack matrix, and sole next action.

## Validation-boundary design handoff (2026-08-17)

- The opaque-attestation design returned `NO-GO_OPAQUE_HANDLE_PROPAGATION` and is abandoned with evidence preserved.
- The user selected the recommended broader validation-boundary architecture direction. The active linked design is `docs/work/semantic-ingestion-validation-boundary-performance-2026-08-17/design.plan.md`.
- This implementation operation remains blocked. No production optimization, review, or M3.1 closure resumes until the new design is independently approved.
