# Implement the Memorii v8 release design

- Work ID: v8-release-delivery
- Work type: implementation
- Delivery fidelity: Level 3, first production release
- Status: active
- Coordinator: Codex
- Created: 2026-11-27
- Last updated: 2026-11-27
- Parent WorkPlan: [release design](design.plan.md)
- Related WorkPlans: [prior hardening](../v8-production-hardening/implementation.plan.md), [installed rehearsal](../installed-release-rehearsal/testing.plan.md)
- Canonical inputs: [approved design](../../design/v8_release_readiness.md), [typed boundaries and verification](validation.md), [durable runtime](../../design/durable_execution_and_solver_runtime.md)
- Expected outputs: installed operator and supported artifacts, independent recovery, bounded turn paths and release qualification

## Objective and completion contract

Implement through installed production roots. Production approval requires
clean rehearsals, exact artifact and supported host/OS evidence, the live
component gate, verified rollback and final branch review. Comparative
agent evaluation follows hardening under a separate design.

## Design baseline and custody

Started on branch codex/durable-delivery-implementation at
665319c0e44fcedd848c3f6ce8e8a5b2f19b3df1. Concurrent authorized ontology work
moved the branch through 8825330d and 694e5651 to 05663f34, including packaged
Hermes catalog tool routing and its tests. Release work resumed at 52948673.
The separate ontology work then published 20288a63. Preserve those edits
and existing untracked material.
Original approved design SHA-256 89a80f5af956fa2bf9025ca9f47742b3a98b15f0e73b0a28c73e4cb0c3310671.
Original verification SHA-256 6b1b61e338eac57a23de7ece64fb1341470b8192663aa9450e75df8127cf4ce2.
The 2026-11-27 owner-approved scope amendment was pushed as b1571306.
Current approved design SHA-256 247e39e570712ec0f6021dd46f3158dfe39aaee9b92ce8069df0a0cfb731ba8c.
Current verification SHA-256 bd2026ac48f671fb1ee07996c45c59956e23a5eeb9cfc9e5accc31b941d66eee.
The verified storage and secret handling regression baseline is c0fa889a.
Keep v8 as default and the 11-second verified acquisition budget.

Hosted adapters use existing owners for task, authentication and persistence.
Preserve signed publication, exact task/source scope, monotonic deny state
and deterministic replay. Behavioral names only on executable surfaces.
The parent ledgers establish authority, identity, test and rollout boundaries.
Each milestone records concrete names, gated paths and actual callers before
freeze. No prompt or catalog wire grammar change is planned.

## Milestones and requirements

| Milestone | Requirement | Scope and dependencies | State |
| --- | --- | --- | --- |
| [Installed operator](milestones/installed-operator.plan.md) | REL-01 | Typed owner enrollment and credential-bound read authority through installed CLI and sidecar | active |
| [Supported distribution](milestones/supported-distribution.plan.md) | REL-03 | Wheel metadata, pinned host images and safe supported dependencies. Can proceed independently until host acceptance. | active |
| [Managed recovery](milestones/managed-recovery.plan.md) | REL-02 | Independent custody, offline cutover, suppression, downgrade refusal and rollback | partial, offline proof passed |
| [Bounded runtime](milestones/bounded-runtime.plan.md) | REL-04, REL-05 | Hook deadlines, indexed durable intake, verified receipt and catalog reads, response release | partial, exact recall optimization deferred |
| [Release qualification](milestones/release-qualification.plan.md) | REL-06 | Exact reviewed revision, artifacts, gates, native platforms and whole-branch review after preceding milestones | specified |

REL-07 remains specified by the design for critical-adoption evaluation after
release hardening. Mixed spool binaries, rollover of current consent state,
and incompatible rollback must fail closed.

## Verification and review

Run warning-error pytest, Ruff, configured and scoped Pyright, identity
hygiene and the affected workflow gates. Record toolchain, revision, command,
exit and artifact identity. Document independent reviews at each frozen
milestone. Test fixtures alone establish no production composition outcome.
See the [resume packet](resume.md) for current owners and evidence.

## Release decisions on 2026-11-27

- REL-03. The owner approved changing the pinned host versions and
  recertifying their actual bundled dependencies.
  Both exact installed dependency trees reported High advisories. Pi also
  ships a bundled copy that package-manager overrides leave in the binary.
- REL-05. The owner approved retaining full exact-recall integrity
  verification and deferring the performance bound for exact recall only.
  Current checkpoints can exceed the 16 MiB decode cap in one signed record.
  The managed browse and inspection acceptance bounds still apply.
- REL-03. The owner approved the Python wheel and pinned host archives as
  the shipped distribution, with Docker reserved for validation.

## Independent checkpoint review

Spec, correctness and test reviewers inspected the local implementation.
Confirmed operational gaps include the incomplete content-free status record
and installed replacement bootstrap. Confirmed compatibility issue is the
former lack of a staged selector backfill for pre-index developer v8
installations. The reviewed raw payload upgrade route now accepts a signed
v8 input with absent selectors and rebuilds both owners in the staged copy.
The replay and migration suite passed 30 focused tests. Existing pre-index
stores deny the new bounded operations until the owner performs the cutover.
Exact package smoke still requires regenerated inventory on the frozen
candidate. Each belongs to its active milestone.

Confirmed verification and runtime issues were corrected locally. PR runtime
and storage gates now select the enrollment, socket release and replacement
tests. The backpressure check now compares the entire received frame prefix
to the exact bytes accepted by the socket before revocation. Serve and drain
hold a shared spool-selection lease. Registration requires the exclusive
lease. Generation-scoped capacity prevents ineligible prior-generation work
from blocking active work after cutover. Older rows remain available for
reconciliation. The integrated rerun passed 138 tests.

The inherited PR #126 Durable Storage gate failed six contention cases
because its probe matched a raw filename on a file descriptor acquired
through the private opener. The descriptor identity repair passed all nine
source-admission tests locally and was pushed as a8dd72b9.

## Next action

Qualify updated host dependencies while completing operator status and live
recovery custody, then freeze the release candidate.
