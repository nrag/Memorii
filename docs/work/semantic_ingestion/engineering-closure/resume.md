# Semantic Ingestion Closure Resume

Work type: implementation. Coordinator: root. Status: active Stage 1, not
closed.
Current committed baseline: `cde2708c`
on `semantic_ingestion_m5`. Index: `implementation.plan.md`. Active packet:
`milestones/acceptance-evaluator-runtime.plan.md`. Previous resume preserved at
`archive/resume-ac8819eaa31c8adadc54db2ca8a7ae60376d5b9e90752e4c0106cae995302039.md`.

## Current State

The 23-row table records 15 engineering-complete requirements and eight open:
R03, R08, R13, R14, R15, R16, R17 and R19. The approved closure sequence is
R14 evaluator/bridge, R15 monitor, R17 comparator/authentication, complete host
composition for R08/R16/R19, then frozen evidence/release preparation for
R03/R13. Actual production keys, signatures and qualifying release measurements
remain release conditions.

Stage 1 has a complete V2 remediation candidate: an installed evaluator,
registered schema and profile authority, signed immutable object repository,
registration-bound independent fence, snapshot-scoped approval verifier,
signed result publisher, and serialized production deployment publisher. The
public installed path succeeds from real Ed25519 authority state and fails
closed for authority, configuration, provider, history, persistence, terminal
lifecycle, and expiry faults. The installed runtime reconstructs its complete
numeric context from five signed V2 artifacts; configuration cannot inject
specs, alpha, gates, IID assertions, memberships, or coverage dispositions.

The read-only preflight at `stage1_preflight_r13_r14_map.md` confirms zero
production callers. The pre-coding test review requires protected construction,
complete multi-cell recomputation, immutable publish/retry/restart behavior, a
digest-only activation bridge, lifecycle/history failures, and installed-package
import isolation. Production may not import `acceptance`.

The latest dirty remediation adds a fixed installed authority-publication command
and proves a real signed successor through the fenced repository and independent
production-revocation reader. The public installed evaluation path uses the
successor without a numeric configuration change, reconciles a lost receipt
after durable production publication, and rejects 23 lifecycle, schema,
signer/policy, currentness, conflict, provider, path, history, and persistence
cases over the frozen multi-cell corpus. The 13-artifact independent checker now
mutates purpose, version, complete descriptor types, digest, and signature.

Round-2 review found one P2 rollback defect plus bounded evidence gaps. The
correction enforces direct monotonic active-release succession and rejects a
signed R2-to-R1 rollback through the installed publication command. It also
recursively mutates every registered descriptor family, pins the frozen
multi-cell topology, and rejects zero, duplicate, and nonconforming publication
runtime discovery before candidate reads. Coordinator validation records 182
acceptance, 76 statistical-contract, and 119 authority/design feasibility tests
passing with warnings as errors, plus Ruff, zero-error supported first-party
Pyright, the independent checker, diff validation, and a rebuilt installed-wheel
proof with 24 fail-closed cases. Correctness and test delta review approved the
committed correction. Specification delta review found two final proof-only
gaps: structural/cardinality descriptor mutations and an observable assertion
that provider discovery fails before candidate reads. The current bounded delta
adds every declared map, pair, numeric, length and collection boundary and
asserts the exact `acceptance_runtime_configuration` failure for all three
provider-cardinality cases. The rebuilt installed-wheel proof passes with 24
fail-closed cases. R14 remains partial until that exact proof delta is committed
and independently verified.

## Ownership And Next Action

The linked acceptance persistence/runtime-bootstrap design is approved at
`../acceptance-authority-persistence/design.plan.md`. It specifies the registered
artifact family, fenced durable repository, production revocation checkpoint
evidence, nonmutating lease-held evaluation snapshot, standard installed
runtime, noninjectable command, CI job, and complete failure matrix. Root owns
the current dirty candidate until one implementation writer resumes it.

Next action: commit the final R14 proof delta and return that exact revision to
the specification and test reviewers.
