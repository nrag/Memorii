# Canonical Evidence Performance Design Review

- Work ID: semantic-ingestion-canonical-evidence-performance-review-2026-08-15
- Work type: investigation
- Status: complete
- Review mode: full
- Target: `docs/reviews/semantic-ingestion-canonical-evidence-performance/proposal-baseline-2026-08-15.md`
- Report: `docs/reviews/semantic-ingestion-canonical-evidence-performance/full-review-2026-08-15.md`
- Created: 2026-08-15

## Objective

Determine whether the canonical-evidence proposal is implementation-ready to
remove measured serialization amplification without weakening canonical byte,
digest, validation, authority, persistence, transaction, recovery, replay, or
failure behavior.

## Completion Contract

Complete only when the target is content-addressed, governing requirements and
production boundaries are independently reconstructed, all applicable review
lanes are covered, required independent passes are reconciled or their absence
is explicitly recorded, confirmed findings use the repository finding
contract, and an immutable report records the outcome and limitations.

## Scope

Included: canonical body and envelope encoding, content-addressed validation,
source-normalization publication/reload, graph-authority handoff, checkpoint
retry, compatibility, resource bounds, and verification sufficiency.

Excluded: implementation, test correction, persisted-schema or digest change,
graph traversal, retry policy, M4, and unrelated performance work.

## Current State

Repository inspection confirms that `contract_digest` hashes a domain-bound
canonical contract body, while `encode_semantic_contract` produces a distinct
schema/kind envelope. Existing encoding deliberately revalidates typed values
to reject forged `model_construct` and unsafe `model_copy` instances. The
proposal does not yet specify these two boundaries separately.

## Progress Log

- 2026-08-15: reconstructed requirements, measured baseline, codec ownership,
  repository reconstruction, persistence, replay, and exact retry boundaries.
- 2026-08-15: attempted the required three independent review lanes. Agent
  capacity prevented a complete cohort; one independent reviewer returned a
  frozen-candidate governance finding. The limitation will remain explicit.

## Next Action

Use `$build-design` to revise the proposal around the four confirmed findings,
then freeze and submit the material revision for a new full review.

## Outcome

The full review outcome is `Changes required`. Three independent substantive
lanes converged with coordinator inspection on four invariant-level gaps:
identity-role conflation, failure to intercept nested reconstruction, undefined
trust/authority lifetime, and non-falsifiable correctness/performance/resource
acceptance. The initial missing-baseline concern was resolved before the
substantive passes and is not an open finding.

Report:
`docs/reviews/semantic-ingestion-canonical-evidence-performance/full-review-2026-08-15.md`.
