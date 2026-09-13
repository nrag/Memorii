# Semantic Ingestion Closure Resume

Work type: implementation. Coordinator: root. Status: active Stage 1, not
closed.
Current committed baseline: `dbb42d33c521ae7b3881e7fb3f61a3a12aff7aa5`
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

Stage 1 has a complete dirty implementation candidate: an installed evaluator,
registered schema and profile authority, signed immutable object repository,
registration-bound independent fence, snapshot-scoped approval verifier,
signed result publisher, and serialized production deployment publisher. The
public installed path succeeds from real Ed25519 authority state and fails
closed for authority, configuration, provider, history, and persistence faults.

The read-only preflight at `stage1_preflight_r13_r14_map.md` confirms zero
production callers. The pre-coding test review requires protected construction,
complete multi-cell recomputation, immutable publish/retry/restart behavior, a
digest-only activation bridge, lifecycle/history failures, and installed-package
import isolation. Production may not import `acceptance`.

Coordinator validation records 130 acceptance tests and 278 combined affected
tests passing, plus Ruff, first-party Pyright, independent vector, diff, and
isolated wheel-build proof. CI now installs the wheel into a fresh environment,
checks both fixed providers, invokes the installed command, and runs the real
configured success/failure fixture. R14 remains partial only until independent
candidate review and any confirmed remediation complete.

## Ownership And Next Action

The linked acceptance persistence/runtime-bootstrap design is approved at
`../acceptance-authority-persistence/design.plan.md`. It specifies the registered
artifact family, fenced durable repository, production revocation checkpoint
evidence, nonmutating lease-held evaluation snapshot, standard installed
runtime, noninjectable command, CI job, and complete failure matrix. Root owns
the current dirty candidate until one implementation writer resumes it.

Next action: freeze and independently review the complete Stage 1 candidate.
