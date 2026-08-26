# Performance, Rollout, Gates, And Final Closure

- Parent WorkPlan: `../implementation.plan.md`.
- Status: active; digest-reduction implementation landed 2026-08-26,
  broad-gate reconciliation and final closure pending.
- Requirements: `VCC-R01` primarily; full acceptance matrix for closure.
- Started: `2026-08-26`.
- Base revision: `e89aa28` (documentation reconciliation commit).

## Digest-Verification Reuse Implementation (2026-08-26)

Production-bound census evidence (methodology: every
`memorii.core.semantic_ingestion.contracts.contract_digest` call is one full
digest computation, counted through the real provider root with the complete
Atlas/Bob V3 fixture; script and JSON in `../performance/`):

| Mode | Total digest calls | Unique identities | Repeated calls | Wall clock | Public outcome |
| --- | --- | --- | --- | --- | --- |
| disabled (full path) | 49,054 | 324 | 48,730 | 491s | `source_only` |
| enabled (reuse active) | 2,054 | 332 | 1,722 | 174s | `source_only` |

Reduction: **95.8 percent total, 96.5 percent repeated** — above the 90
percent gate with margin. The dominant cost was the content-addressed digest
validator recomputing the full canonical digest on every reconstruction of
equal frozen artifacts (44,290 calls at one callsite), plus four hand-rolled
digest validators with the same shape.

Mechanism (owner and authority):

- `CanonicalDigestVerificationScope` in `canonical_evidence_arena.py` is the
  operation-local memo. An entry certifies that one exact instance's declared
  digest was verified by the full canonical computation. A later instance
  reuses it only under the same concrete type and declared digest plus full
  structural equality; anything else falls through to the full computation,
  so a forged declaration can never inherit an entry.
- The arena installs the scope on `__enter__` in enabled mode only, pops it on
  `__exit__`, purges it on close/exception, and purges it immediately when
  staging capacity refuses (rejected mode selects the full path). The memo is
  bounded by `MAX_ARENA_ENTRIES`, holds strong references (identity cannot be
  recycled), and never crosses operations, threads, or processes.
- `contracts.py` consults the scope from
  `_ContentAddressedContract.validate_content_digest` and the converted
  hand-rolled validators (`BootstrapAnalysisProvenanceV1`,
  `SegmentGovernanceBinding`, `MessageAdmissionIdentity`,
  `SegmentGovernanceCarrierSet`) through shared
  `_digest_verification_hit`/`_record_digest_verification` helpers.
- No digest algorithm, canonical encoding, domain, persisted schema, public
  API, or validator failure behavior changed; disabled mode is untouched.

Focused unit proof (`test_canonical_evidence_arena.py`, 35 passing):
within-operation reuse with zero additional computations, scope death on
arena close, disabled and no-arena full verification, forged-declaration
fail-closed inside an active scope, and capacity-refusal inlining of reuse.

Equivalence and regression evidence at this revision:

- Mode parity and composite family lease proofs: `2 passed in 890.71s`
  (enabled and disabled redelivery recovery produce identical outcomes,
  durable projections, and idempotence with the reuse active).
- Provider service, arena, and writer-admission focused suites: `44 passed`
  plus `1` known pre-existing failure (`test_provider_preserves_caller_owned_event_time`).
- Ruff clean on changed files; pyright error count on the changed production
  files is identical with and without this change (374 pre-existing errors,
  zero new).

Remaining in this milestone: broad-gate baseline reconciliation (the
pre-existing unit failures and the identity-hygiene allowlist drift), full
acceptance-matrix run, capacity/concurrency/privacy production-root
matrices, candidate refreeze, independent milestone/final reviews, CI wiring,
and current-state documentation updates. Remaining headroom (not required
for the gate): the per-child scope-set digest comprehension
(`contracts.py` required-outcome-scope loop) and the identity-cluster digest
still recompute; converting them would push the reduction beyond 97 percent.

## Broad-Gate Baseline Reconciliation (2026-08-26, partial)

Completed:

- `test_provider_service.py` is fully green (`41 passed`): the stale
  `test_provider_preserves_caller_owned_event_time` expectation was corrected
  to the ingress-gated writer-admission contract (resolved ingress creates
  the record; retained sources must carry the caller timestamp).
- `memorii.tools.identity_hygiene` passes (exit 0): the drifted
  `legacy_rejection_vector` location pin in
  `test_semantic_ingestion_pipeline.py` was updated from line 415 to the
  current line 450 (this branch's original dirty tree shifted the line; the
  rejecting test itself is unchanged).
- Fourteen bare `ProviderMemoryService(memory_plane=..., now_provider=...)`
  constructions in `test_semantic_provider_composition.py` now pass
  `host_bootstrap_material_verifier`, restoring installed-capability
  composition (profile, resolver, and runtime engage). Net effect on the
  module: 25 passing vs 22 before.

Explicitly remaining (not repairable by the shared-cause pattern):

- 43 failures in `test_semantic_provider_composition.py` (dominated by the
  18-case egress-mutation family) and 4 in
  `test_bootstrap_graph_coordinator_v3.py` are verified pre-existing at
  clean base `b9daf00a` and at every branch revision, with the branch's
  production changes reverted (stash and parent-commit file isolation both
  reproduce them). They fail because legacy fixtures encode composition
  expectations (ordinary-path checkpoints, hand-built minimal runtimes,
  resolver-less ingress) that predate the current V3/ingress-gated
  contracts. Each family needs its own causal fixture work; a hand-built
  minimal runtime, for example, engages composition but produces no
  preplanning control without the full local runtime parts.
- pyright on `contracts.py`/`canonical_evidence_arena.py` reports 374
  pre-existing errors with zero added by this branch (verified by
  parent-commit file isolation); repo-wide pyright debt predates this work.
- Disposition: the remaining legacy-fixture reconciliation is a dedicated
  debugging or test-architecture operation (`$debug-problem` or
  `$design-tests`), not a closure-feature defect; no product behavior
  evidence links these failures to the validated-closure changes.

## Next Action

Decide whether to open the dedicated legacy-fixture reconciliation
operation for the 47 remaining pre-existing failures, then proceed to the
final closure items: full acceptance-matrix run, candidate refreeze,
independent milestone and final reviews, CI wiring, and current-state
documentation updates.
