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

## Next Action

Run the broad-gate baseline reconciliation: triage and fix or explicitly
classify the pre-existing unit failures and the identity-hygiene allowlist
drift, then rerun the full broad gate set at one frozen revision.
