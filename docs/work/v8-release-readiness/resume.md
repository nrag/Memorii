# v8 release delivery resume

Active work covers the [installed operator](milestones/installed-operator.plan.md),
[distribution](milestones/supported-distribution.plan.md),
[managed recovery](milestones/managed-recovery.plan.md) and
[bounded runtime](milestones/bounded-runtime.plan.md).
Baseline identities and ordering are in the [implementation plan](implementation.plan.md).

The ontology plans and observation-ledger release preparation changed through
a separate concurrent workstream. Leave those files, prior audit drafts and
VirtualEmployee work outside this operation.

Independent specification, correctness and test reviews are reconciled in the
implementation plan. The owner made both scope decisions on 2026-11-27.
Runtime checkpoint `2a9e140b` is on the same remote branch. Its committed
wheel passed installed operator and migration proof. Pi 1.7.0 and OpenClaw
2026.11.10 both passed the application-level journeys on that wheel.
OpenClaw's dedicated context engine passed persisted-history and revoked
provider-request checks. Full image scans, installed custody and native
capacity remain open.

Evidence maturity starts at specified for new behavior. Docker can prove
functional behavior. Native capacity and exact-candidate certification need
their own evidence.
