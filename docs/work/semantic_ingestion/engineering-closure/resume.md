# Semantic Ingestion Closure Resume

Work type: implementation. Delivery fidelity: Level 2 early real-world testing.
Coordinator: root. Status: complete at Level 2; Level 3 release work deferred.
Current product baseline: `4497325b` on `semantic_ingestion_m5`. Index:
`implementation.plan.md`. Final packet:
`milestones/06-host-composition-closure.plan.md`. Previous detailed resume:
`archive/resume-ac8819eaa31c8adadc54db2ca8a7ae60376d5b9e90752e4c0106cae995302039.md`.

## Current Objective And Priority

Enable useful early real-world Hermes testing. Priority is fixed: make the
intended product workflow usable end to end; cover expected security,
reliability, quality, and common failures; then defer rare/adversarial hardening
to production preparation.

Level 2 requires Hermes ingestion, retrieval, ledger activation and monitoring,
public graph observation and ingestion-time attestations, and reconciliation.
It includes missing configuration, caller/scope denial, provider/extractor
failure, empty or partial work, retry, stale state, persistence/reopen,
duplicate/lost acknowledgement, and no-work behavior.

## Implemented Candidate

- `92b33d37` closes activated graph-control recovery and exhausted-control
  reconstruction with exact terminal lineage.
- `c2f331fd` exposes activation, monitor tick/scheduling, graph observation,
  ingestion-time attestation, and reconciliation through `HermesMemoryProvider`.
- `76389ffb` preserves coordinator-reported graph-observation substitution
  failures and sends the real Hermes provider through the public acceptance
  page-chain collector.
- `7b705077` covers unconfigured Hermes denials, malformed cursors, public
  all-root monitoring, and no-pending reconciliation.
- The current correction adds `HermesMemoryProvider.start_semantic_ingestion`
  and `build_started_hermes_memory_provider` so activation, recovery, and
  bounded monitoring have one host-owned configured construction sequence.
- `0dce4f5e`, `11954845`, and `393d6be3` align repository workflows with the
  selected delivery fidelity and usability-first priority.

The persistent graph changes only through ingestion, explicit reconciliation,
and monitor/conflict scheduler calls. Process start or stop and observation
reads do not rebuild it. Hosts should reconcile on startup/recovery and may run
a periodic monitoring tick. Pydantic forward-reference closure is process-local
schema preparation; its measured repeat cost is negligible and it is not a
persistent graph rebuild.

## Current Evidence

The consolidated Level 2 pass is green for 36 selected scenarios:

- retrieval and scoped context: 20 passed in 9.00s;
- all-root monitor integration: 1 passed in 10.32s;
- observation/common failures: 2 passed in 10.06s;
- ingestion and recovery: 13 passed in 215.73s.

The real composed Hermes observation/comparator test passed separately in
329.64s after the startup correction. It validates configured startup, a
nonempty complete public page chain, page digests,
ingestion-time attestations, scope denial, and the adapter path. Focused Ruff
and production-module Pyright checks are clean. Four fast lifecycle cases pass
in 8.37s. The bounded correction review approves the lifecycle-trigger fix with
no remaining Level 2 finding.

## Requirement State And Deferrals

The production-oriented 23-row closure table remains 17 engineering-complete
and six partial: R03, R08, R13, R16, R17, and R19. That Level 3 status does not
mean six blockers to early Hermes testing. R08, R16, R17, and R19 now have the
needed Level 2 public composition and common-failure evidence. R03 and R13 are
release evidence and authorization rows.

Deferred Level 3 work includes adversarial memory spoofing and forged topology,
exhaustive record-family/tamper/host matrices, final evidence packaging,
qualifying policy measurements, production key provisioning and signatures,
and exact-release CI/review. Existing fail-closed trust and integrity checks
remain in force.

## Completion State

No Level 2 action remains. Resume with a Level 3 production-release WorkPlan for
final evidence packaging, operational signing, qualifying measurements, and
production hardening.
