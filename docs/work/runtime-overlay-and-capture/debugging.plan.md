# Managed solver selection and source capture

- Work ID: runtime-overlay-and-capture
- Work type: debugging
- Delivery fidelity: Level 2, verification of the two known runtime failure families
- Status: complete
- Coordinator: Codex
- Created: 2026-11-27
- Last updated: 2026-11-27
- Parent WorkPlan: ../managed-harness-intake/implementation.plan.md
- Related WorkPlans: ../ontology-read-workflow/implementation.plan.md
- Canonical inputs: ../../design/durable_execution_and_solver_runtime.md, ../../design/memorii_storage_details.md
- Expected outputs: selected-overlay test coverage and a fenced active-task source admission

## Objective and completion contract

Close the failing managed solver-state assertion and prevent native source
retention when task pause wins the publication fence. Keep v8 as the
installation default. Include the already-developed ontology inspection and
recall slice with the matching package-preparation inventory on the same
branch. This operation records targeted checks and leaves full release
qualification to its governing work.

## Incident and reproduction contract

At clean pushed base `0bbc68a2`, the managed tool unit test expected
`overlay:harness` but received `None`. The test seeded graph rows without
persisting the active solver and overlay selections. The capture reproducer
committed a managed pause after the intake precheck and before the first
governed source write. Capture returned denied, while a lookup still found
the submitted raw bytes and the spool held no observation.

## Hypotheses and outcomes

| Symptom | Hypothesis | Discriminating result |
| --- | --- | --- |
| Missing overlay | State reader dropped an explicitly selected overlay | Disproved. The old fixture persisted neither selection pointer. |
| Missing overlay | The managed reader correctly withheld an unselected overlay | Confirmed. Selection and unselected behavior are now both exercised against managed tool reads. |
| Source retained after pause | Intake selected an already inactive task | Disproved. The task was active in the initial snapshot and the test paused it immediately before source publication. |
| Source retained after pause | The source publisher rechecked grant and installation mode while omitting current task lifecycle | Confirmed. The capture owner now supplies a live check executed inside the publication fence. |

## Scope, authority and rollout

The task selection remains explicit. Legacy and managed state-read contracts
retain their current ancestry. The governed provider still owns the raw
source and its admission index. The capture guard rechecks exact credential,
grant, scope, and active lifecycle before the SQL write under the publication
fence. A source already admitted before a later pause retains its existing
governed custody. The SQLite catalog version and backup formats require no
migration. The native recovery test is selected by Durable Runtime Integration.

The ontology slice adds protected catalog inspection and structured recall
diagnosis through the Hermes and authenticated source bindings. Its separate
plan owns acceptance limits. VirtualEmployee work is outside this branch change.

## Progress and verification

- Reproduced both failures on the clean base. Independent fixture analysis
  confirmed the solver result reflects the intended explicit-selection contract.
- The solver fixture and selected/unselected assertions passed 29 focused
  warnings-as-errors cases. The capture pause regression failed on the
  clean base by finding an extra signed source publication and passed after
  the fix. Independent review reproduced all three capture fault cases.
- Fix commit `2ea415c8`. The integrated runtime and storage selection passed
  45 checks with warnings as errors, including checkpoint-tail and staged
  v8 payload tests. Whole-tree Ruff, Pyright and behavioral identity hygiene
  passed. The CI job includes the capture regression. No live component
  certification or full release gate is claimed.
- Read-only staging map identified 25 ontology paths including its design,
  implementation and tests. Refreshed the existing package inventory and
  companion checksum against the integrated code and workflow. The newly
  changed persistence publisher is now an explicit member.

## Next action

None for this debugging operation. The ontology WorkPlan tracks its own
remaining acceptance evidence.
