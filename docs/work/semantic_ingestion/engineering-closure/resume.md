# Semantic Ingestion Closure Resume

Work type: implementation. Coordinator: root. Status: active Stage 1, not
closed.
Current committed baseline: `aa41b0d2cce5e4271e823c0950fa119c036bafc9`
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

Coordinator validation records 175 acceptance tests passing, plus Ruff,
zero-error first-party Pyright, schema-complete vectors for all 13 registered
artifacts, the signed numeric-context feasibility matrix, diff, and an isolated
installed-wheel proof with one success and 14 fail-closed cases. CI now installs the wheel into a fresh environment,
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

Next action: commit and independently review the complete Stage 1 V2 candidate.
