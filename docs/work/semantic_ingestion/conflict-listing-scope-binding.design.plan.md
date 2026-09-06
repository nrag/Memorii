# Conflict Listing Scope Binding Closure

- Work ID: conflict_listing_scope_binding_closure
- Work type: design
- Status: complete
- Coordinator and sole canonical-design writer: Codex main thread
- Created: 2026-08-02
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Governing sources: `docs/design/conflict_attention.md`;
  `docs/design/equal_version_replay_decision-v1.json`

## Objective

Close the implementation-discovered ambiguity between the complete current
authorization scope tuple and the caller-selected listing subset. The existing
cursor/snapshot schema named only `authorized_scope_ids`, while normative text
requires both exact authorization-snapshot equality and retained narrowed-list
equality. One field cannot represent both when the caller narrows a listing.

## Decision And Acceptance

- `authorized_scope_ids` and `scope_digest` bind the complete server-resolved
  current authorization snapshot.
- `listing_scope_ids` binds the nonempty canonical subset used to create the
  retained listing membership.
- New requests default `listing_scope_ids` to the complete authorized tuple;
  supplied scopes must already be a canonical subset.
- Continuation requires the current complete authorization tuple and digest to
  equal the cursor/snapshot authority and supplied `scope_ids`, when present,
  to equal `listing_scope_ids`.
- Any authorization expansion or reduction returns
  `invalid_conflict_cursor`; a changed listing subset returns
  `invalid_cursor_scope`; neither path reads conflict payload or starts a new
  snapshot.

The change is additive within uncommitted M4 protocol bytes. It does not change
legacy provider results or the frozen equal-version replay decision.

## Verification

- Design/artifact hashes and decision digest are rebound.
- The standalone artifact validator, 30 mutation tests, identity hygiene, and
  `git diff --check` pass.
- Independent spec, correctness/security, and test delta reviewers confirm the
  two bindings and exact failure families are derivable and test-owned.

## Review Budget

One three-role delta review and one bounded remediation pass. Stop only if a
new product choice cannot be derived from the existing fail-closed
  authorization contract.

Current canonical hashes after the amendment:

- conflict-attention design:
  `b2d58a05a77c4105d2ce41433024bcb88d41204b6f2de8a86e76b699d8eb66de`;
- semantic-ingestion architecture:
  `53b796de59dead7fb16902bc8c53c0225628b602e53c5ee4c9f91dd1fe1e2261`;
- event model:
  `9ce93e4a826f3e47b2e41fa06d2ec1e40bb0cad2475fa0527d9bb2c9ab3acdec`;
- replay-decision artifact:
  `f04b778e8e23632ff732199f6776ebbf740210d20778338bb7524b316f3ed241`;
- validator:
  `41a50fa6847a5c96704536521842761b3400c79fb8e75096193c87b72d480262`.

## Exact Next Action

None. The design operation is closed with all three delta reviewers approved
and `remaining_validated_p1_p2: []`. Resume the parent reader/list remediation.

## Review Findings

- Spec review: approved the separate complete authorization and listing-subset
  bindings with no residual semantic blocker.
- Correctness DREV: confirmed `P2 / changes_required / security` because the
  initial amendment did not explicitly order mismatch rejection before every
  ledger/snapshot/index/payload read. Resolved by the fixed continuation check
  ordering and no-read/no-append/no-fallback rule.
- Test DREV: confirmed `Not applicable / changes_required / verification` for
  missing explicit complete-set-versus-subset cases and stale prior-plan pins.
  Resolved by expanding D01's exact unit/integration assertions and updating
  all current authority hashes.
