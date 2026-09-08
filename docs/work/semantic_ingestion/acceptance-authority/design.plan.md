# Acceptance Authority Feasibility

- Work ID: semantic-ingestion-acceptance-authority
- Work type: design
- Status: blocked (declared reconstruction/review budget exhausted)
- Coordinator: root
- Created: 2026-09-06
- Last updated: 2026-09-06
- Parent WorkPlan: ../engineering-closure/implementation.plan.md
- Related WorkPlans: ../statistical-acceptance/design.plan.md; ../engineering-closure/milestones/03-independent-statistical-evaluator.plan.md
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md`; `review.md`
- Expected outputs: `proposal.md`, model, focused proof

## Objective

Specify and exercise a fail-closed, nonproduction release-chain authority
model for proposed SIA approval.

## Scope And Limits

The four files own immutable A->T->B replay, checkpoint/key-ledger/receipt
binding, bounded JSON scanning, and local proof. Canonical CTV, runtime,
persistence, CLI, registry, and production integration are excluded. Older
post-terminal release actions are intentionally unsupported.

## Evidence

Tests call `verify_current_release` through the new chain, covering A->T->B,
zero-active terminal state, two-key rotation/unrelated entries, later selected
key revocation, trusted re-signing tamper, illegal transitions, receipts, CTV
bytes, and scanner boundaries. This is bounded model evidence, not canonical or runtime verification;
the trusted provider and keys are honest fixtures. No production entry point
exists, so no `production_entrypoint_bindings` update or runtime claim applies.

## Completion Contract

One coherent verifier replaces the retired lifecycle reducer and every stated
model invariant has a focused proof. Root must run:
`pytest docs/work/semantic_ingestion/acceptance-authority/test_authority_feasibility.py`.

## Progress

The closed reconstruction is locally verified: 16 tests pass in 0.29 seconds
under Python 3.12.14 with warnings treated as errors. Ruff passes. Original
rejected candidate archives remain unchanged. All three independent reviewers
require changes; `review.md` records the confirmed temporal-authority and bounded
verifier evidence gaps. The declared reconstruction budget is exhausted. No
production signature or external policy value is needed to resolve these gaps.

## Next Action

Resolve the issue-time authorization contract in an explicitly bounded successor
design operation before canonical promotion or runtime implementation.

## Requirements And Decision Ledger

- Preserve canonical release/verified-result fields and independent acceptance
  ownership; no production or simulator import may supply acceptance truth.
- Define closed signer, snapshot, global key-state, pointer, checkpoint, receipt
  and limit contracts; unsigned currentness and caller-provisioned keys reject.
- Preserve exact policy decimals and all user-deferred release values. Choosing
  an Ed25519 adapter or record grammar does not choose thresholds or a real key.
- Use immutable A->T->B state records with immediate-predecessor links and a
  capability-scoped lineage. Independent spec consultation confirms that SIA
  permits this construction; older-noncurrent terminal actions are optional and
  deliberately unsupported. Never rewrite a signed active record.
- Complete all authority/receipt/resource checks before promotion. New static
  snapshots and trust-root rollover are excluded from this bounded protocol;
  staged keys support ordinary signing-key rotation within a lineage.

## Changed Surfaces And Evidence

The four proposal/model files are the only current writable design surface.
Root owns all four files after the replacement writer relinquished ownership.
Root alone executes pytest and freezes candidates. Governing SIA remains
b469653e3ef92e9cc1bf45e797a2c7dff8eac4d9ee792ad94ada3a54bfbe05da.
`candidate-initial.json` and `history/36fc5f46416de4667b0a02e7d300af3427155a7b1f3d400073f60e61819be5e0.tar`
retain rejected review identities; current `candidate.json` is historical until
the next explicit freeze. `review.md` owns reconciliation. No source/compiler/
registry change or downstream regeneration is represented as complete.

The first complete-entrypoint model run passed nine cases and exposed one
masked parser-ceiling test: the escaped string exceeded raw bytes first. After
independent ceiling vectors were added, ten tests passed in 0.19s. Coordinator
inspection then found missing actual signing-key rotation and a comparison
between independent production and acceptance epochs. Both are corrected and
exercised through the public verifier. The final 16-case run also proves global
key predecessors, rejection of undeclared keys/unknown states, signed coordinate
substitution, duplicate JSON keys and escaped surrogate boundaries. The scanner
rejects unsupported depth configurations rather than relying on recursion failure.
`feasibility.log` retains the final coordinator-observed output. This does not
establish full schema, timestamp, CTV, runtime, or operational authority proof.

## Review And Convergence Contract

Original full review and one delta review are reconciled in `review.md`.
Successive findings in the same authority boundary triggered one complete
state-machine reconstruction, not additional example patches. Its budget is
one coherent reconstruction plus one targeted conformance verification. A
remaining indeterminate semantic decision or failure to converge after that
verification stops this linked design with exact evidence; it cannot silently
consume another speculative redesign. Engineering authoring omissions are not
attributed to missing production signatures or external quality values.

Before approval, all three independent roles must accept this fixed design
scope, exact hashes, the actual verifier call path, failure vectors and honest
evidence limits. Missing runtime/CI proof remains a parent implementation
obligation, not feasibility success. Completion requires an explicit closure
record with no unresolved required conformance finding or validated P1/P2.

## Identity And Promotion Chain

New durable names describe signing, release state, current status, key state,
revocation receipt and verifier limits. WorkPlan/requirement coordinates remain
traceability-only. Feasibility constants are not shipped protocol bindings.
Canonical promotion requires SIA -> new profile/root inventory -> independent
compiler/checker -> registry/structural manifest -> vectors/checksums/CI pins.
Original v1/v2 evidence remains byte-identical. This operation does not bypass
the later production-entrypoint ledger or final branch checks.
