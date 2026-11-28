# Installed release verification

- Work ID: v8-release-verification
- Work type: testing
- Delivery fidelity: Level 3, first production rollout
- Status: active
- Coordinator: Codex
- Created: 2026-11-27
- Last updated: 2026-11-27
- Parent WorkPlan: [implementation](implementation.plan.md)
- Related WorkPlans: [installed rehearsal](../installed-release-rehearsal/testing.plan.md), [reference capacity](../reference-capacity-qualification/testing.plan.md)
- Canonical inputs: [release design](../../design/v8_release_readiness.md), [acceptance matrices](validation.md), [static tooling](../../development/static_tooling.md)
- Expected outputs: pinned installed host proof, compatibility and release evidence with explicit gate ownership

## Objective and scope

Keep deterministic release-shaped evidence fast and keep real host, native
capacity and exact live component verification in their existing slower gates.
Retain established coverage while replacing editable native certificate inputs
with one pinned base wheel. Review changed workflow and artifact identities
before relying on the result.

| Proof | Existing or changed owner | Observable failure |
| --- | --- | --- |
| Exact operator task and source grants | Feature-local integration test `test_installed_native_operator.py`, existing runtime and storage tests | Wrong same-principal credential gains access, incomplete enrollment becomes active, retry mutates original task |
| Local host bounds and retry | SDK `npm test` on compiled client, real loopback and adapter callback tests | Scheme, remote or redirect escape, oversized body or shared deadline breach, changed persisted resume receipt on restart |
| Installed native assets | Existing host-container certification and host pins | Missing image, editable or wrong-digest Python, copied-over host assets, failed real host journey |
| Retained analyzer profile | Existing PR, canonical mode parity and live jobs with checkout-only pinned linguistic requirements | Lost test family, unsupported profile, unresolved engine or model task |
| Candidate platform capacity | Current reference-capacity workflow and exact fixture audit on configured runners | Mixed artifact scope, missing attempts, staged upgrade presented as fresh default, missed budgets |

## Evidence and gates

Unit and integration tests will use warning-error pytest and current relevant
static checks. Dedicated host jobs require actual container execution. Local
shimbed adapter and disposable Docker runs each retain their own evidence
limits. Prior staged capacity results remain historical. No test selection or
threshold change is authorized. Review changed CI dependency inputs against
their existing test owner and runtime. Exact final artifact and host
verification remain open.

The 2026-11-27 worktree at 694e5651 passed 137 focused Python tests with
warnings as errors, including real loopback release, indexed backup and
restore, native source authority and catalog selection. Ruff and configured
Pyright passed. Identity and static tooling passed 173 tests. The current
shard verifier collected 5,359 tests and passed. Node transport tests passed
20 cases, plus installed SDK and generated-schema checks. A clean install of
worktree wheel
`0bf004d7f8ff135185c88bb3f06c4fd85bb304f2515e62b6452e1b9aa0d610c9`
passed four operator/backup tests. The separate pinned host rehearsal used the
older wheel recorded by the supported distribution milestone. Both artifacts
are local worktree evidence. The targeted 137 tests exclude the broader Hermes
family. A separate broad run had 184 passes and one Hermes activation failure
before catalog dispatch. Clean baseline attribution is unresolved. A rerun
against the concurrent Hermes test update at 05663f34 was started. The
recorded test totals do not include this in-progress run.

Review fixes were checked at 05663f34 with 138 integrated passes. A further
five operator integration tests passed, including a foreground CLI subprocess
that denies spool registration while the service is live and allows it after
exit. The wheel rebuilt after spool and socket changes,
`d01b5b572baa15d96f9693f159a3b4245d97e0b5e352b7eac1c64b2bc5442598`,
passed an out-of-checkout run using the actual `memorii-operator` console
script for initialization, enrollment and foreground serving. The run crossed
same-principal credentials, captured over HTTP, restarted the process,
recalled and then denied the revoked scope. This is local macOS functional
evidence for a worktree wheel. It does not replace the candidate-bound host,
recovery and platform runs.

## Next action

Repeat the exact installed host and Hermes checks on a single candidate
digest after host pins, recovery custody and scoped recall are settled.
