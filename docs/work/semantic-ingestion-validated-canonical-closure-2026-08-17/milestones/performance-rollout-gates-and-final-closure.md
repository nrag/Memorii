# Performance, Rollout, Gates, And Final Closure

- Parent WorkPlan: `../implementation.plan.md`.
- Status: complete (final closure 2026-09-03 at `7c5152b`; gate evidence and
  dispositions below).
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

## Final-Closure Session (2026-09-03)

Acceptance-matrix gap analysis (row-by-row mapping against
`implementation-acceptance-v12.md`) found nine NOT-FOUND cells. Two were
already evidenced outside tests (the production-bound digest-reduction census
above and the successor v2 harness); the remaining seven are closed or
dispositioned as follows:

- Production-root capacity refusal: `test_process_reservation_exhaustion_at_the_root_uses_the_full_path`
  in `memorii/tests/unit/core/semantic_ingestion/test_canonical_evidence_production_limits.py`
  — four deliveries held in-flight at the writer handoff exhaust the 64 MiB
  process reservation (4 x 16 MiB), the fifth real delivery's arena is refused
  at construction (`capacity_rejected_full_path` / `capacity-refused`, no
  sealed lease reaches its handoff), its public outcome equals the enabled
  warm delivery's, and reservation release permits later reacquisition. A
  content-size refusal is structurally unreachable: canonical contracts are
  digest-based (`RetainedSourceTextArtifact` stores `content_digest` +
  scalar length), so the 2 MiB per-entry envelope is crossed by structure,
  not payload bytes.
- Production-root concurrency: `test_concurrent_inflight_writers_hold_isolated_leases_at_the_durable_boundary`
  — two deliveries in flight simultaneously (first paused at the durable
  boundary while the second completes): distinct arenas, tokens, owners, and
  scopes; both leases carry member evidence and drain released; exactly two
  `enabled/completed` terminal snapshots; all controls terminal.
- Production-root privacy: `test_terminal_snapshots_carry_no_delivery_sentinel_in_any_field`
  — every snapshot field name and string value is scanned recursively against
  the delivery content, its sha256, the leased canonical root digest and
  contract type, and the task/user scope coordinates; nothing appears. The
  same scanner runs over the capacity and concurrency phases' snapshots.
- Arena-local matrix cells: the 32,768 member-path envelope exact/one-over
  boundary, first-terminal-cause latching through conflicting closes
  (exception/cancelled/validation-failed orders), and a hostile
  observability sink (raising or returning an unknown outcome) are added to
  `test_canonical_evidence_arena.py` (62 passing).
- The new production-limits module is slow-tier (one full-path delivery per
  test): excluded from the unit shard plan and owned by the scheduled
  canonical-evidence cadence workflow with an exact collection-count pin,
  mirroring the mode-parity tier.

Gate repairs in the same session:

- `identity_hygiene` (124 findings, all structured keys of the regenerated
  durations artifact): resolved with behavioral parametrize IDs on the three
  scanner corpus tests plus a 1:1 durations-key remap; exit 0 with the
  mutation corpus (6 coordinate spellings x 18 surfaces, 13 traceability
  binding shapes, 3 concealment shapes) passing.
- Unit shard plan: 4 -> 6 shards on the re-measured corpus (~487s estimated
  per shard, unchanged 600s target, `pr-gates.yml` matrix updated in lockstep);
  both shard configs verify green.
- The CI pyright command was discovered red (868 errors; clean merge base
  `2a7a55e` reports 0 under the identical config — the errors are
  branch-introduced, dominated by loose `object`/`BaseModel` annotations in
  `atomic_store.py` and `writer_admission.py`); delegated to a single
  annotation-precision writer as the type-gate remediation.
- Both production-entrypoint binding validators (v11, v14) fail on
  source-hash drift against the current tree; regeneration at the frozen
  revision is a freeze-gate step.
- Known failure RESOLVED 2026-09-03 (commit `e4dfda8`):
  `test_semantic_provider_composition.py::test_public_flow_prepared_source_contract_is_frozen_across_runs`.
  Complete causal chain: the preparation fingerprint transitively covers the
  bootstrap profile's verified component digests, which pin live component
  source bytes (`find_spec(...).origin` read) and installed package versions
  by design (`verify_bootstrap_profile`). Its absolute value therefore moves
  with the environment and with any fingerprinted-module edit — confirmed by
  body dumps differing only in `route_digest`/`bootstrap_profile_manifest_digest`/`component_root_digest`
  across sessions, checkouts, and the type-remediation commit — while the
  cross-run equality invariant passes everywhere. The hex-pinned constant was
  unpinnable; the test now pins the environment-independent source digest and
  checks the fingerprint shape, with the coupling documented in the test. The
  remaining broad-gate failures from the equivalence record are the
  environmental stanza-assets node (host asset availability, unchanged
  disposition) and the hygiene-clean node (fixed 2026-09-03).

## Milestone Closure (2026-09-03)

Independent review round at frozen candidate `542cd86`: `spec_auditor`
APPROVED (three P3 follow-ups, all addressed or recorded);
`test_reviewer` returned one `changes_required` (mirrored workflow pin
assertions red at the frozen revision) — fixed at `78f844e`;
`correctness_reviewer` returned one validated P2 `changes_required`
(reservation-proof failure presenting as a wedged holder thread) —
diagnosed as the test's arrival/start-order release-join mismatch, fixed at
`1b07094` with both reviewers' follow-ups applied. Targeted delta reviews:
both APPROVED with empty remaining lists. The candidate was refrozen at
`7c5152b` (validator 9/9, clean tree); the production-limits module holds
two green runs at the fixed revision (`3 passed in 244.91s` at load 7-10
and `3 passed in 388.09s` at load 31).

Final gate evidence at `7c5152b`: ruff clean; CI pyright command 0 errors;
identity hygiene exit 0; both shard plans verify (6 x ~487s, 7 x ~569s
against the unchanged 600s target); package smoke green; bindings v11
(32/32) and v14 (5/5) regenerated and passing; manifest v2 validated 9/9;
workflow collection pins and mirrors consistent; selector manifest valid.
Broad unit gate (adopted xdist command): two runs at sustained external
host load 17-70 recorded `5 failed, 4081 passed, 2 skipped` (junit at
`../evidence/final-broad-gate-junit.xml`); every failure is dispositioned
in the parent Final Closure Record (one stable environmental analyzer-assets
node; four load-conditioned wall-clock-deadline/subprocess-timeout nodes
with prior representative-load green evidence from the 2026-09-02
equivalence runs and isolation greens at load ~8; the isolated CI shard
runner is their wired authoritative environment).

The milestone and the parent operation close together. Non-blocking
follow-ups (path-level retained-pending handoff proof, recovery-race lease
drift, bounded observability retention, durations backfill for eight new
fast nodes) are recorded in the parent plan's decision log.
