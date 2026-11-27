# Managed Pi and OpenClaw intake

- Work ID: managed-harness-intake
- Work type: implementation
- Delivery fidelity: Level 2, pinned installed host journeys; publication approval remains in the release WorkPlan
- Status: blocked
- Coordinator: Codex
- Created: 2026-11-27
- Last updated: 2026-11-27
- Parent WorkPlan: ../durable-memory-implementation/implementation.plan.md
- Related WorkPlans: ../installed-release-rehearsal/testing.plan.md
- Canonical inputs: ../../design/durable_execution_and_solver_runtime.md, installed rehearsal evidence
- Expected outputs: signed runtime submission and pinned-host restart evidence

## Objective and completion contract

Use the installed managed sidecar and owner drain to continue the provisioned
task on both hosts. Read the persisted task state after restart. Verify Pi
extracts the exact text from native user blocks. Verify whether a governed
provider can admit and recall that text on the installed path.

## Scope and constraints

Base revision is `1baa03b3` on `codex/durable-delivery-implementation`.
Retain v8 defaults, keep unrelated ontology work outside the change, and use
local offline model stubs. Runtime command authority and provider evidence
authority remain separate. There is no persisted-format change.

## Identity, impact, and production bindings

| Surface | Owner and binding | Verification |
| --- | --- | --- |
| Native session hooks | Pinned Pi extension and OpenClaw plugin; operator-provisioned task | Real host turns before and after restart |
| Command preparation and intake | RuntimeSidecar, installation-issued bearer, finite task command grant, signed operation origin | Real loopback calls and owner-verified durable spool |
| Drain | Installed memorii-consume --managed --drain | Signed committed receipts, empty repeat drain |
| Read and compare-and-swap | HarnessStateService, RuntimeReadGrant, task_version | Read persisted goal and check task version independently of global revision |
| Provider capture | GovernedSourceAdmissionService and runtime provider-source owner | Check exact native text at the prepare boundary; observe the fail-closed installed path |

`task_version` is an optional, additive envelope property. The sidecar emits it
from the authorized task snapshot when a caller sets `include_task_version`.
The default v1 wire shape and digest remain compatible. OpenAPI and both SDKs
support explicit opt-in. Global `revision` retains its snapshot and pagination
meaning.

## Progress and decisions

- The spec audit confirmed that global revision can advance while the task
  version remains fixed. Managed resume compares against the task version.
- Both hosts prepare a command and attach the signed origin on intake. The
  managed owner drains the pending spool with current grants.
- Pi normalizes native user text blocks and ignores empty or non-text input.
  Both host callbacks report preparation refusal without submitting an unsigned
  command. Action dispatch and result have no managed authority in the current
  composition.
- Test evidence distinguishes a native message text match, a committed resume,
  and a post-reopen authorized runtime state read.
- An actual Pi CLI startup fork bypassed the interactive fork hook. The
  installed extension now checks the operator-selected native session ID at
  each request hook. OpenClaw binds its hooks to one explicit session key.
- OpenClaw reuses the prepared operation after an ambiguous intake response.
  The pinned gateway can write a continuation transcript without running the
  prompt hook, so the scoped transcript hook can also trigger the same resume.

## Evidence log

- The wheel was built from a clean source snapshot with just the scoped Python
  edits. Both Docker runs used Python 3.11 on Linux ARM64, the same offline
  wheel, the repository's separate native adapter assets, a deterministic local
  provider, and fresh installations with schema v8. The packaged Python
  import resolved to site-packages after disabling the checkout source path.
  Wheel SHA-256:
  `eac19c2b9a05d6b4207ce59db0fc581926fac6ea35bece70e1cde2bc3bce7355`.
- The focused Python sidecar, schema, and adapter suite passed 28 tests with
  warnings treated as errors. Generated OpenAPI parity and all 10 TypeScript
  SDK tests passed. The larger run passed 39 tests and reproduced the same
  solver-overlay expectation failure as the clean `1baa03b3` base in
  `test_model_tools_serve_bound_views_and_state_plain_unavailable`.
- Pi 0.99.2 and OpenClaw 2026.9.7 each submitted two signed resume intents
  and produced two committed receipts with the original operation origins.
  Repeat drains were empty. Both reattached to the same active task after
  the host and sidecar restarted. The authenticated read returned its goal
  and an advanced global revision while the task version stayed constant.
- Pi's actual CLI fork of an existing native session and OpenClaw's
  unrelated native session produced zero commands and zero observation
  requests for the bound Memorii task.
- Both real user inputs on each host matched their exact text fingerprints
  at the preparation boundary. All four observation requests returned the
  closed `unsupported_configuration` code, and none entered the spool.
- Pi extension SHA-256:
  `29bced1c504792fb3f51f3ce282922ba89c34efd0759081952661d3b318f2fbd`.
  OpenClaw plugin SHA-256:
  `b320431c296441b9d93a2f016f3099f02a7b0268e595e30d17459810c39662ff`.

## Blockers and limits

The installed sidecar and bearer-free owner drain have no provider-source
resolver for either host. A transcript hash cannot satisfy the canonical
admission contract. The installed path returns unsupported_configuration
before admitting an observation. Full capture and agent-facing source recall
require a trusted native delivery binding, governed provider admission, durable
re-resolution during drain, and an authorized context or read path.
The remaining choice is whether the installation owner can enroll a narrowly
scoped native source, or whether each input must originate from a separately
verified upstream provider. The completed managed resume path can use its own
command grants under either policy.

## Delegation and review

- Spec auditor, read-only: traced prepare, intake, drain, revision, and provider
  ownership. Confirmed distinct task and runtime revisions and absent durable
  provider composition. No edits.
- Correctness reviewer, read-only: identified v1 wire compatibility and
  ambiguous intake retry issues. Added opt-in response shape and exact retry
  retention. Reviewed native pins and requested setup documentation, now in
  the README.
- Test reviewer, read-only: requested a closed source rejection code and a
  valid Pi fork origin. Adopted both checks. Scoped evidence establishes
  reattachment and readback of an active task.

## Next action

Resolve the owner policy for production native source admission before
wiring capture and agent recall.
