# Canonical Evidence Performance Observability Remediation

- Work ID: semantic-ingestion-canonical-evidence-performance-observability-2026-08-16
- Work type: design
- Status: under-review
- Coordinator: Codex
- Created: 2026-08-16
- Last updated: 2026-08-16
- Parent WorkPlan: docs/work/semantic-ingestion-canonical-evidence-performance-2026-08-15/design.plan.md
- Related WorkPlans: docs/work/semantic-ingestion-canonical-evidence-performance-2026-08-15/implementation.plan.md; docs/work/semantic-ingestion-canonical-evidence-performance-observability-review-2026-08-16/design-review.plan.md
- Canonical inputs: review report, canonical evidence design, fixture contracts
- Expected outputs: remediated design, frozen executable lock, feasibility-only tooling

## Objective

Resolve the six confirmed review findings without production code or production-test
changes, preserving the invalid baseline and the production-arena baseline gate.

## Scope

Included: exact public matrix contract, future lifecycle ownership, cell algebra,
fixture repin, executable lock, and fail-closed fixture tooling. Excluded:
production arena implementation, a baseline capture, approval, and CI rollout.

## DREV Ledger

| Finding | Disposition | Remediation evidence |
| --- | --- | --- |
| DREV-001 | correction determinate; targeted review pending | user-authorized production-owned verified authority factory/bundle, thin-fixture AST contract, diagnostic receipt/trace contract, and four-root threading; implementation remains blocked |
| DREV-002 | remediated | lock pins runner, recipe, and validator; no WorkPlan identity in performance schema |
| DREV-003 | remediated | eight-cell schema and validator equations/capacity mutations |
| DREV-004 | remediated design only | explicit owner/create/pass/retry/finally/cancel/concurrency/capacity lifecycle contract |
| DREV-005 | remediated | current fixture bytes repinned and included in the replacement lock |
| DREV-006 | remediated | feasibility tooling permitted before baseline; production arena edits remain blocked |

## Production Entrypoint Bindings

`production-entrypoint-bindings-v1.json` is the preflight mapping. The public
matrix is specified and statically audited, but the current non-test production
caller count for built-in graph-authority injection is zero. This is an explicit
implementation blocker, not a completed runtime claim.

## Evidence

- Static matrix proof rejects private construction and unit-test imports.
- JSON schemas and current fixture hashes are checked before freezing the lock.
- The sole artifact validator runs its positive and mutation self-test.
- No benchmark was run; the historical invalid baseline was not modified.

## Completion Contract

This bounded design slice is complete only after the targeted delta review
evaluates the new lock and tooling. It does not complete the parent milestone.

## Progress Log

- 2026-08-16: second remediation pass added a source-manifest receipt and
  fixture-manifest verification, exact lifecycle callsite table, and fail-closed
  validator mutations. One-cell public-path feasibility is blocked because the
  only full deterministic authority fixture imports prohibited unit-test helpers
  and is scenario-only. Report: `docs/reviews/semantic-ingestion-canonical-evidence-performance/delta-review-remediation-pass-2-2026-08-16.md`.

## Superseded Next Action

Independent targeted DREV-001/DREV-002 rereview of the superseding frozen proof contract.

## DREV-001/DREV-002 regression remediation (2026-08-16)

- DREV-001 remains `Not applicable / changes_required / security+verification` pending independent rereview. The exact AST dataflow template, origin-token receipt/trace contract, frozen artifact-manifest binding, and external pre-import trust root are now specified and locally self-tested.
- DREV-002 is reopened only as `Not applicable / changes_required / verification regression` pending the same rereview: the shared resolver, schema consumption, pending-to-capture-ready transition, root-specific source map, hostile-CWD launcher, and executable-authority hashing were tightened without any production/test edit.
- DREV-003 through DREV-006 remain closed. No baseline, production implementation, or approval claim is made.
- Frozen regression lock: `6dcd4972149106eb0c6443c7665d3a5ac32ad4b02c8f9be43b3fb81818b7647e`, superseding `9642ec00f247c77b8be0ce84efe69b2fdff21a99a26a1e1ca6d887082a0e7c2f`.

## Authorized DREV-001 correction

The external decision authorizes only the narrow production-owned typed verified
authority composition boundary. It rejects raw `BootstrapGraphHostBundleBuilder`
exposure, `ProviderMemoryService._from_scenario_test_host`, scenario-test trust
material, arbitrary verifier bypass, and fixture-built receipts or traces. The
implementation prerequisite may precede baseline capture; arena optimization
remains blocked until a valid baseline. DREV-002 through DREV-006 remain closed.

## DREV-001/DREV-002 Result-Lock Delta (2026-08-16)

DREV-001 and DREV-002 remain `Not applicable / changes_required` pending a
targeted rereview. The frozen contract replaces serialized origin-token trust
with typed, private, opaque-operation-token validation before serialization;
the serialized projection contains no token or issuance assertion. The launcher
freezes an execution lock before capture and atomically O_EXCL-writes a result
lock after capture, prints its SHA-256, and externally compares that hash from
`--expected-result-lock-sha256` before Python record import. Expected baseline
and candidate result-lock hashes are `not_available: capture blocked`; they
must be entered verbatim in the evidence ledger after production capture.

The requested present-day eight-cell runtime proof is blocked implementation
evidence because the required non-test production caller is absent. It is
unsupported as a design-exactness prerequisite, retained as a mandatory
post-implementation gate, and not elevated into a separate design finding.

## Whole-design remediation (2026-08-16)

The latest whole-review findings A-G are all classified `Not applicable / changes_required`; no P1/P2 product defect is validated. The detailed reconciliation and evidence are durable in `docs/reviews/semantic-ingestion-canonical-evidence-performance/whole-design-remediation-2026-08-16.md`. The design now specifies the arena algorithm, opaque verified authority and four-root conflict rule, the pending non-test production supervisor, frozen two-lock comparison authority, exact schedule/environment/p95 policy, post-implementation lifecycle/security gates, and terminal trace/durable receipt proof. The replacement lock `d1760d12f207bdc363361b628ae7d00a33ba3644fce54f4935739bfae075aeb0` supersedes `ebc2e9b4927e93877b5ee3b8b6742b6f6485128bd860c4569f51b6ecaab13f30`.

No production code/test, baseline, runtime capture, persistence proof, CI, or approval claim changed.

## DREV-007/DREV-008/DREV-009 remediation (2026-08-16)

- DREV-007 (`Not applicable / changes_required / verification`): the former
  comparison object is split into a lock-pinned concrete PRE-CAPTURE schedule
  authority and an O_EXCL POST-CAPTURE result binding. The latter binds two
  distinct side authority/implementation/source/execution/result/record
  identities and is externally hash-checked before Python import.
- DREV-008 (`Not applicable / changes_required / verification+operability`):
  schedule authority fixes the environment, algorithm, seeded order, one
  warmup, one discard, and retained ordinals `0..19`; schema and validator
  require exactly 20 samples. p95 is nearest-rank, with focused boundary and
  one-unit checks.
- DREV-009 (`Not applicable / changes_required / production-execution
  evidence`): each cell and result lock now require a typed successful terminal
  durable-effect receipt and no-duplicate proof. This is a contract/tooling
  closure only: the non-test production caller and durable runtime proof remain
  `specified_not_implemented_fail_closed` in the binding ledger.
- Whole-review A-C and F-G remain reconciled as specified, pending-production
  bindings. D/E/G receive the strengthened two-side schedule/result and typed
  durable-terminal contract. No production code/test, baseline, capture,
  persistence proof, CI, or approval claim changed.
- New frozen lock: `a7edc0cbe9e657951aede230fd5d0f2bd1763f4a9347eaef68807fbd48bc72c1`, superseding
  `059f875cd6fca3ad2bf82754e69d21838f8e04d0942fa0744f1472146143fcfc`.

The proof-topology delta separately resolves and passes each temporary side
authority lock/source manifest through public record/pair validation. Its actual
external CLI topology proof uses real `bind` then `validate`, positively loads
both result locks, and runs matching-hash DREV-007/DREV-009 negatives through
the same path. At frozen lock
`a7edc0cbe9e657951aede230fd5d0f2bd1763f4a9347eaef68807fbd48bc72c1`,
the validator `--self-test` passed; Python compilation, launcher shell syntax,
all frozen JSON parsing, resolver integrity, and `git diff --check` also passed.
This remains tooling-only evidence: no baseline, production caller, persistence
proof, CI, or approval claim changed.

## DREV-007 Mixed-Schedule Vector Correction (2026-08-16)

The temporary alternate schedule formerly mutated the schema-fixed `seed`, so
the candidate failed side validation before the intended cross-side check. The
vector now uses a schema-valid alternate `execution_order` permutation, then
regenerates the candidate records, retained ordinals, execution lock, and
result lock and validates that candidate pair against its repinned authority
before external `bind`/`validate`. The matching external hashes therefore reach
only `comparison sides have mixed fixture, environment, or schedule authority`.
No production code/test, baseline, runtime capture, persistence proof, CI, or
approval claim changed.

Frozen correction lock:
`54ba23f7ff6633fdf5038470de7fdb47bdbef2963648823a575d32a9bee973c9`,
superseding
`d5117196f9169c0c9eba94b6c3dd2173431c69c567db40dfcc4765d144e7d514`.
The full fixture self-test reached a terminal exit 0 after approximately 270
seconds; this remains tooling-only evidence.

## Current Next Action

Targeted DREV-007/DREV-009 rereview against frozen lock
`54ba23f7ff6633fdf5038470de7fdb47bdbef2963648823a575d32a9bee973c9`.
