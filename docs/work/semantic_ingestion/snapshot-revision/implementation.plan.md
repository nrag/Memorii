# Full Write Snapshot Implementation

- Work type: implementation
- Status: complete, bounded storage primitive only
- Parent: ../observation-ledger/design.plan.md
- Baseline: 191826cd3afb38bf605a337a71d576063b3bae5e, authorized dirty tree.
- Design: ../observation-ledger/replay-snapshot-contract.md, Snapshot Ownership
  And Activation Preconditions only; coordinator-confirmed determinate internal
  contract with independent targeted DREV-003 closure. The wider ledger/profile
  design is not approved by this bounded implementation.

## Objective And Scope

Add a detached all-record write-revision snapshot and matching conditional
write guard to the existing memory-plane service and both built-in stores.
Keep existing data-revision behavior and JSONL bytes unchanged. This is the
storage primitive required by later activation/checkpoint integration; it does
not claim those zero-caller ledger owners are implemented or close parent R17.

Owner paths: core/memory_plane/store.py, service.py and unit_of_work.py; focused tests in
tests/unit/core/test_memory_plane_write_snapshot.py. Governing storage/event
invariants remain unchanged. No model/profile/signature authority is added.

## Contract And Proof

| Requirement | Exact behavior and verification |
| --- | --- |
| Complete token | read_write_snapshot returns full batch revision plus detached records; controls/runtime/mixed/empty successful batches advance it |
| Compatibility | read_snapshot/revision return the original data revision; existing expected_revision guard retains its semantics |
| Atomic guard | expected_write_revision is None or exact nonnegative int; reject stale or malformed input before mutation; both supplied guards must match |
| All routes | stage/upsert/write/apply_batch share the full counter; service forwards the new guard through the canonical store |
| No partial effect | Failed CAS/record precondition/policy callback changes neither token nor records |
| Durability | JSONL reuses persisted batch revision, survives reopen and independent instances; no rewrite of historical records required |

Production binding: MemoryPlaneService.read_write_snapshot -> canonical
MemoryPlaneStore.read_write_snapshot; MemoryPlaneService.conditionally_write_records
-> MemoryPlaneStore.apply_batch(expected_write_revision). Built-in store methods
run under their existing locks. New schema-free API names describe behavior.
Custom store implementations must implement the new capability before ledger
activation; old service paths must not start passing an unexpected keyword when
the caller has not requested this capability.

The full-write snapshot/guard capability is root-store-only. A unit of work
contains speculative pending records and cannot supply a committed full-store
token. Its protocol methods explicitly reject read_write_snapshot or a non-null
expected_write_revision before staging or changing authorization. Ordinary nonempty UOW
commit still advances the underlying store counter. This mirrors its existing
root-only transaction-precondition restriction and preserves candidate versus
committed state.

Focused matrix: both backends, internal-control insertion with unchanged data
revision, ordinary runtime writes, empty batch, combined guards, negative/bool
revision, detached records, exact no-write comparison, JSONL reopen and two
independent instances. Existing store-contract, JSONL, visibility and convergence
families check compatibility. Tests remain feature-local; no new CI architecture.

## Execution And Evidence

Root owns all test processes and this plan. Exactly one existing Terra worker
owns the three production files and one new test file. Read-only independent
reviewers inspect the frozen bounded candidate afterward. Existing worker reuse
is necessary because new agent spawn reached the session limit; root supplied
the inspected exact backend/service map rather than inventing a production call.

Validation uses root .venv Python 3.12.14, warnings as errors, no pytest cache;
focused pytest, Ruff and Pyright plus existing relevant store suites. Record
candidate hashes and results before bounded review. No runtime benchmark or
external credentials are needed for this deterministic storage contract.

## Next Action

None for this completed slice; resume the parent observation-ledger design.

## Construction Discovery

Pyright identified MemoryPlaneUnitOfWork as another implementation of the store
protocol. Root inspected its speculative snapshot semantics and extended the
sole worker scope to that owner. The new root-only operation must reject there;
delegating a live token through a staged view is forbidden. The worker also
replaces an incompatible legacy-store subclass test with an old-signature
instance spy, avoiding casts or suppression. No test process has run yet.

## Verification And Review Reconciliation

Root verification: initial combined focused/compatibility run 54 passed in
6.85s. The one positive dual-current-guard test added afterward passes for both
backends; final focused file 19 passed in 1.07s. Ruff, Pyright, whitespace and
identity checks pass. The three production files did not change after the
initial run. candidate.json pins the final four-file candidate.

The test gap was a required evidence action (Not applicable), not a demonstrated
P2 runtime defect. Independent test review confirms closure. Correctness review
withdrew its callback-order finding after inspecting actual current-authority
barriers; existing lock/callback/CAS ordering is intentional and preserved.
Spec review withdrew an empty-UOW concern: empty staged commit is a no-op, not
a committed root batch. No new I/O or counter change is introduced for it.

The first spec attempt confused the files-map candidate digest with the manifest
self hash; the replacement manifest states the exact digest algorithm. During
review coordination, the positive test edit landed before a pause reached the
worker. Root recorded the old candidate as superseded, reran focused validation,
and requested review against the new frozen identity. No production edit was
made during review. Full parent ledger/M5 and hosted CI remain unclosed.

## Bounded Closure

All three independent review duties are satisfied for candidate
e84b6eaae5242b5cc94d7e032675b558993f30fc079833112ef20f6439514ea3.
remaining_validated_p1_p2: []
No unresolved required evidence/conformance finding remains in this primitive.
Parent R17 remains partial: activation, checkpoint and observer consumers are
not implemented here. Current-branch/CI certification and the parent WorkPlan
identity recapture remain explicitly separate. See closure.md and candidate.json.
