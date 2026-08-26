# Whole-Design Remediation: Canonical Evidence Performance

- Review baseline: `ebc2e9b4927e93877b5ee3b8b6742b6f6485128bd860c4569f51b6ecaab13f30`
- Replacement lock: `54ba23f7ff6633fdf5038470de7fdb47bdbef2963648823a575d32a9bee973c9`
- Scope: design, contracts, schemas, bindings, and fixture tooling only
- Outcome: changes required are remediated as design/tooling contracts; targeted delta review pending

## Reconciliation

| Finding | Product priority | Disposition | Type | Determination |
| --- | --- | --- | --- | --- |
| A: arena algorithm | Not applicable | changes_required | architecture | remediated; implementation pending |
| B: authority issuance/co-injection | Not applicable | changes_required | security | remediated; production proof pending |
| C: production caller/supervisor | Not applicable | changes_required | integration | remediated as pending capture-ready binding |
| D: two-lock comparison | Not applicable | changes_required | verification | remediated in frozen comparison authority contract |
| E: schedule/environment/p95 | Not applicable | changes_required | verification/operability | remediated in frozen schedule contract |
| F: lifecycle/security gates | Not applicable | changes_required | lifecycle/security verification | remediated as post-implementation gate family |
| G: terminal production execution | Not applicable | changes_required | production execution | remediated as trace plus durable-terminal requirement |

No P1/P2 product defect is asserted: current code is not claimed to implement
the arena or production supervisor. The design does not approve production
implementation, baseline capture, persistence behavior, or a performance result.

## Closed Contract Deltas

`CanonicalEvidenceArena` now has a named owner, non-recursive canonical-byte
key, typed validated value, private `ValidationInfo.context` propagation,
success-only caching, exact legacy fallback, bounded no-eviction saturation,
retry/recovery/concurrency rules, and `finally` teardown. The public four-root
binding requires a factory-issued opaque bundle, rejects legacy co-injection,
and names a non-test future `CanonicalEvidenceCaptureSupervisor` whose all-eight
trace ends in `_run_semantic_ingestion` plus a durable terminal receipt.

The former comparison authority is now a lock-pinned concrete PRE-CAPTURE
schedule authority and a POST-CAPTURE O_EXCL result binding. It fixes the
shared fixture/tool/workload/environment/algorithm/order/warmup/discard and
exact 20 retained ordinals; the result binding separately locks baseline and
candidate immutable authorities, implementations, sources, execution locks,
result locks, and record identities. Crossed, swapped, stale, same-id,
mixed-fixture/environment/schedule, warmup, and order defects reject.

D/E/G additionally require nearest-rank p95 over exactly 20 samples and a
typed all-eight terminal durable-effect receipt in both cells and result locks.
Each receipt carries the operation/root/backend/source linkage, durable
identity, effect digest, successful terminal status, replay identity, and
no-duplicate count. This is still design/tooling evidence: the named non-test
production supervisor and runtime durable proof remain pending.

## DREV-007/DREV-009 Proof-Topology Delta

Public `validate_record` and `validate_pair` now accept the already resolved
side authority lock. The external `main` resolves each supplied lock from its
own immutable root and threads it through its baseline and candidate pair;
neither side can fall back to the workspace-current lock or source manifest.

The validator's self-test now constructs two independent capture-ready temporary
authority roots with distinct source and implementation identities but identical
fixture, tool, schedule, and environment authorities. It invokes the real
external `bind` and `validate` commands with matching external hashes. Bind
stdout must equal exactly the created binding SHA-256, and a same-path bind must
exit 64 without changing the original bytes or digest; validate consumes that
captured stdout hash. An independently repinned, schema-valid alternate
`execution_order` permutation regenerates and independently validates the
candidate records, retained ordinals, execution lock, and result lock before
matching-hash external validation reaches only the cross-side mixed-authority
branch. A result-lock-only terminal `effect_digest` mutation preserves schema and
replay uniqueness, then repins its result-binding hash and reaches the
result-lock-to-record receipt-equality branch. These remain design/tooling-only
proofs, not a baseline, runtime, persistence, or approval claim.

## Local Evidence

- `jq empty docs/design/semantic_ingestion_canonical_evidence/*.json` passed.
- `.venv/bin/python -m py_compile` for the lock resolver and artifact validator passed.
- `jq empty` for the changed lock and verification contract passed.
- `.venv/bin/python -m py_compile` for the artifact validator and lock resolver passed.
- `/bin/sh -n memorii/tests/fixtures/semantic_ingestion/canonical_evidence_preimport_gate.sh` passed.
- The full fixture `--self-test` reached terminal exit 0 after approximately
  270 seconds against the replacement lock.
- Candidate lock hash is `54ba23f7ff6633fdf5038470de7fdb47bdbef2963648823a575d32a9bee973c9`, superseding `d5117196f9169c0c9eba94b6c3dd2173431c69c567db40dfcc4765d144e7d514`.

These are local tooling checks only. They do not prove a non-test production
caller, authority issuance, runtime arena behavior, terminal durable effect,
baseline/candidate capture, CI enforcement, or approval.

## Sole Next Action

Run a targeted DREV-007/DREV-009 rereview against replacement lock
`54ba23f7ff6633fdf5038470de7fdb47bdbef2963648823a575d32a9bee973c9`,
including a terminal full-fixture self-test result.
