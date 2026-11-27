# Managed Pi and OpenClaw intake

- Work ID: managed-harness-intake
- Work type: implementation
- Delivery fidelity: Level 2, pinned installed host journeys; publication approval remains in the release WorkPlan
- Status: completed
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
extracts the exact text from native user blocks. Verify that governed admission
commits the exact text and both hosts deliver it to the model after restart.
Revoke the enrollment and verify capture and recall fail closed.

## Scope and constraints

Signed resume began at `1baa03b3`. Native capture began at `bc01cc2e` on
`codex/durable-delivery-implementation`.
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
| Native capture and recall | Owner runtime grant, governed provider admission, signed observation, independent runtime read grant | Exact positive bytes, redelivery, recovery, restarted model request and revoked read |

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

## Native source enrollment

- Owner-approved scope is installation, generation, credential, principal,
  one task and one exact native source. The source is a Pi session ID or a
  dedicated local OpenClaw gateway session key. OpenClaw accepts correlated
  local user turns and excludes channel and forwarded provenance.
- The provider retains text and its admission index in a signed memory-plane
  publication. The managed queue contains a digest, command and original
  signed origin. The owner drain re-resolves exact stored evidence and the
  live enrollment after reopening.
- Native append uses the task version at preparation as its lower bound
  under the publication fence. It cannot replace newer task state. A stale
  enrolled resume can release a no-op receipt only while the task is active.
  Paused-task resume and other task mutations retain exact revision checks.
- A separate current read grant is required at recall. The operation releases
  up to four committed messages from the same enrollment; source suppression
  and enrollment revocation are checked again on read. Lifecycle archives
  still require a separate exact source grant that the operator can issue
  from the committed native spool entry.
- The scope covers capture acknowledged by Memorii. It does not recover
  messages lost before the native adapter delivered them to the sidecar.
  External OpenClaw channel account and sender enrollment is outside this
  release slice.

## Native capture evidence

- Capture revision `7b9cc31d`. Both offline Linux ARM64 container journeys
  used the same freshly installed wheel. Imports resolved to site-packages
  with the checkout package disabled, and the default partition format was
  v8. Wheel SHA-256
  `7f191dbde9dc2c6ddd0d9ca28309147c72e4e308b06cf89e22cd9ed100ae64d3`.
- Pi 0.99.2 and OpenClaw 2026.9.7 each committed two exact native user
  messages. Retry returned the same signed receipt, changed same-ID text
  conflicted, and another task or source could not recall the data. Pytest
  also proved that two distinct native deliveries with identical text remain
  separate observations.
- The pinned OpenClaw gateway supplied `runId:user` as the native transcript
  idempotency key and omitted the optional prompt-hook admission fields.
  Capture joins the transcript and awaited prompt hook by that exact key on
  a local user turn.
- After restarting the host and sidecar, the actual model request contained
  the prior text in a separately marked Memorii contribution. This test used
  a deterministic offline stub. After revocation the next actual request
  lacked that contribution, and both capture and recall returned denied.
- The capture recovery fixture proved commit from the owner drain after
  losing the sidecar between durable intake and dispatch. An independent
  task version advance did not overwrite newer task state or block the
  append. Revocation denied the corresponding pending drain. The read
  fixture revoked the independent read grant during assembly and checked
  refusal at release.
- Exact owner release for two captured source records passed the existing
  managed pause archive path. The operator smoke also verified exact retry,
  refusal of a pending entry, and explicit archive-release revocation.
- 36 focused Python tests passed with warnings treated as errors. Generated
  OpenAPI parity, Ruff, native adapter syntax checks, and staged whitespace
  checks passed. The selected atomic store patch excluded all concurrent
  ontology hunks.

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
- Native capture review identified task-version races, unauthenticated lock
  creation, read revocation during recall, and missing lifecycle grant
  issuance. The guarded append, pre-lock authorization, read-epoch
  revalidation and explicit owner issuance address those findings.

## Next action

None. The selected native-source capture and restart recall scope is complete.
