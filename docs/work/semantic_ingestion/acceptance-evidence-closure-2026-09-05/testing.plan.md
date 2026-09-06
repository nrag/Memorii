# Semantic Ingestion Acceptance Evidence Closure

- Work ID: semantic_ingestion_acceptance_evidence_closure_2026_09_05
- Work type: testing
- Status: locally complete; immutable candidate review and hosted execution
  remain parent-owned
- Coordinator: Codex main thread
- Created: 2026-09-05
- Last updated: 2026-09-05
- Parent WorkPlan: `docs/work/semantic_ingestion/m4-closure-2026-09-04/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/milestones/m4-event-history.plan.md`; `docs/work/semantic_ingestion/testing.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md`; `docs/design/semantic_ingestion/traceability_registry/registry-v1.json`; `.github/workflows/pr-gates.yml`
- Expected outputs: three executable acceptance proofs already required by the traceability registry, exact workflow ownership, and revision-bound evidence

## Objective

Close the existing deterministic evidence gap for production composition,
event-replay integrity, and historical-truth evolution without changing product
semantics or expanding the M3.1/M4 implementation boundary.

## Completion Contract

Complete only when the registry-named behavioral acceptance selectors exist,
exercise their real production owners with discriminating assertions, pass with
their registered supporting tests, are collected by exactly one intended
required workflow job with adequate timeout headroom, and pass independent test
and correctness review at the frozen candidate revision.

## Scope

Included: acceptance tests for production conflict-attention composition,
event-replay integrity, and historical-truth evolution; exact traceability and
workflow binding; focused runtime and collection evidence; stale-selector
reconciliation.

Excluded: product-semantic changes, new replay behavior, new conflict-attention
features, non-fact materialization arms, M5, benchmark or live-provider claims,
and broad test-suite reorganization.

Deferred: whole-branch deterministic gates and hosted execution, which remain
owned by the parent completion WorkPlan after the candidate freeze.

## Constraints And Invariants

- Tests must use the canonical production composition and persistence owners.
- Existing validators, transaction owners, replay decoders, and serializers may
  not be mocked or bypassed.
- Each test must have a distinct failure signal and stable behavioral name.
- The three registry requirements remain traceability values only; they may not
  enter executable test or workflow identities.
- The acceptance job remains the single intended workflow owner unless current
  workflow structure proves a different existing owner is necessary.

## Identity And Coordinate Hygiene

| Surface | Identity | Class | Owner or meaning | Disposition | Proof |
| --- | --- | --- | --- | --- | --- |
| acceptance test functions | `test_production_composition`, `test_event_replay_integrity`, `test_historical_truth_evolution` | behavioral | registry-required supported behaviors | implement as prescribed | field-aware identity gate |
| WorkPlan ID | `semantic_ingestion_acceptance_evidence_closure_2026_09_05` | planning/evidence coordinate | testing operation only | retain only in this WorkPlan | repository identity search |

## Change Impact And Verification Closure

| Path or pattern | Surface class | Owner | Authority chain | Required gates | Status |
| --- | --- | --- | --- | --- | --- |
| `memorii/tests/acceptance/semantic_ingestion/test_sia_requirements.py` | acceptance tests | this WorkPlan | production composition/replay/history -> behavioral oracle | focused registered commands; acceptance job | implemented; registered group green |
| `docs/design/semantic_ingestion/traceability_registry/registry-v1.json` and derived pins | registry/generated authority | existing traceability owners | design -> registry -> manifests/checksums -> workflow | registry validation and self-test | authority chain repaired by parent; status promotion waits for final review |
| `.github/workflows/pr-gates.yml` | workflow/gate | existing acceptance job | tests -> job -> aggregate | workflow structure tests | exact owner verified |

## Test Contract And Topology

| Behavior | Defect detected | Level | Required observable | Intended gate | Status |
| --- | --- | --- | --- | --- | --- |
| production conflict-attention composition | public roots omit or bypass bounded attention authority | acceptance | enabled roots expose bounded authorized attention; disabled/missing authority fails closed | `semantic-ingestion-acceptance` | implemented and passing |
| event-replay integrity | corrupt, duplicate, or colliding history is accepted or partially exposed | acceptance plus existing store unit | exact replay or typed rejection with zero partial exposure | `semantic-ingestion-acceptance` | implemented and passing with support |
| historical-truth evolution | genesis/checkpoint or current/history projections diverge | acceptance plus existing integration | byte-equivalent authoritative state and preserved historical truth | `semantic-ingestion-acceptance` | implemented and passing with support |

The existing unit and integration nodes named by the registry remain supporting
proof. The new acceptance nodes must not duplicate their internal mechanics;
they must prove the public composition-to-outcome path.

## Gate Ledger

| Gate | Exact command or CI-only action | Required | Result |
| --- | --- | --- | --- |
| registered focused groups | commands from the three registry entries | yes | final candidate: 5 passed together under `-W error` in 60.10s |
| acceptance file | `python -W error -m pytest tests/acceptance/semantic_ingestion/test_sia_requirements.py -p no:cacheprovider` from `memorii/` | yes | 200 passed in 1071.05s |
| identity hygiene | `python -m memorii.tools.identity_hygiene --root .. --allowlist ../.agents/identity_hygiene_allowlist.json` from `memorii/` | yes | passed, exit 0 |
| workflow structure and traceability validators | repository-owned validators selected by current workflows | yes | local CTV, lifecycle, structural, selector-manifest, and equal-version validators pass; immutable hosted result remains parent-owned |
| hosted acceptance job | exact frozen SHA/ref | parent closure only | deferred to parent |

## Delegation And Cost Ledger

| Task | Role | Ownership | Rationale | Status |
| --- | --- | --- | --- | --- |
| current owner/test/workflow inventory | `code-mapper` / Spark-class | read-only | locate exact missing selectors and gates | complete |
| acceptance evidence implementation | `worker` / Terra-class | sole writer | keep tests, registry, workflow, and WorkPlan coherent | pending |
| final test/correctness review | standard reviewers | read-only | required topology closure | pending |

## Current State

All three registry-named selectors exist and pass through their canonical
owners. Production composition exercises both ordinary roots through verified
host-bootstrap authority and proves enabled access plus disabled/missing-
authority fail-closed behavior. Event replay proves exact retry, divergent
retry rejection without mutation, signed-checkpoint recovery, committed versus
zero-effect outcome shape, and corrupt-tail non-disclosure. Historical truth
proves a later higher-authority correction with an earlier valid interval,
immutable predecessor retention, temporal/trust projection, identity rekey,
historical audit, signed checkpoint, and file reopen.

The old unit support modules are removed. Canonical fixtures now live under
`tests.fixtures.semantic_ingestion`; every changed consumer imports that owner.
The current candidate manifest binds the complete direct fixture chain,
production owners, registered support nodes, and every import consumer.

## Assumptions And Open Questions

- Verified: the acceptance file is already collected by the required
  `semantic-ingestion-acceptance` workflow job.
- Verified: the registry already defines the three behavioral selector names.
- Working assumption: existing fixtures and public builders can express all
  three proofs without product changes.
- Unresolved: none locally; registry status promotion follows clean independent
  review of the frozen selector candidate.

## Progress Log

- 2026-09-05: Read-only inventory found the three missing registry-named
  acceptance selectors and their existing unit/integration supporting nodes.
  No product behavior gap was inferred from missing evidence alone.
- 2026-09-05: Ran a focused prototype against the real provider roots and
  durable replay owner. The factory rejects a standalone authenticated ingress
  resolver as an incomplete identity-lineage composition; the filesystem root
  has no resolver argument. The supported opaque production-authority path is
  present but this WorkPlan has no reusable fixture that can issue it through
  the real verifier. Prototype-only edits were reverted; no acceptance selector
  was retained.

## Evidence Log

- The three registered commands and their two supporting selectors passed
  together on the final candidate under `-W error`: 5 passed in 60.10s.
- R10 now persists both accepted and zero-effect terminals through the real
  terminal persistence service and JSONL memory plane, reconstructs a fresh
  atomic store, decodes the durable observation/artifact members, verifies
  replay-authority bindings, and distinguishes event, source-event, dedupe,
  and record identities.
- R18 now uses genuinely competing claim values and asserts the exact official
  predecessor selection plus regulator overlap selection with the official
  assertion retained as historical evidence.
- Every affected fixture consumer collected successfully: 445 tests in 8.90s.
- Direct acceptance selector runs after each correction remained green; the
  latest three-selector run passed in 21.08s before the shared fixture
  extraction, and the registered five-selector run proves the current tree.
- Scoped Ruff and compilation passed for the acceptance file and all three new
  canonical fixtures. Affected replay/policy consumers collected without old
  support-module imports.

- `rg` found no definitions for `test_production_composition`,
  `test_event_replay_integrity`, or `test_historical_truth_evolution` under
  `memorii/tests`.
- `.github/workflows/pr-gates.yml` already runs the containing acceptance file,
  but the exact registered nodes cannot currently collect.
- `PYTHONPATH=memorii .venv/bin/python -m pytest -q
  memorii/tests/acceptance/semantic_ingestion/test_sia_requirements.py::test_production_composition
  memorii/tests/acceptance/semantic_ingestion/test_sia_requirements.py::test_event_replay_integrity
  memorii/tests/acceptance/semantic_ingestion/test_sia_requirements.py::test_historical_truth_evolution
  -p no:cacheprovider` exited 1 in 19.03s for a prototype that was reverted:
  (1) factory rejected standalone resolver injection with `identity lineage
  audit composition is incomplete`; (2) an event replay negative vector used a
  new dedupe identity and therefore did not raise; (3) two genesis terminal
  records collided on the canonical record/version reservation. These latter
  two signals confirm the acceptance test must reuse canonical vector support,
  not recreate event mechanics.
- `PYTHONPATH=memorii .venv/bin/python -m pytest --collect-only -q
  memorii/tests/acceptance/semantic_ingestion/test_sia_requirements.py::test_production_composition
  memorii/tests/acceptance/semantic_ingestion/test_sia_requirements.py::test_event_replay_integrity
  memorii/tests/acceptance/semantic_ingestion/test_sia_requirements.py::test_historical_truth_evolution
  -p no:cacheprovider` exited 4 in 10.96s, correctly reporting all three
  registry selectors absent after the prototype was reverted.
- `PYTHONPATH=memorii .venv/bin/python -m compileall -q
  memorii/tests/acceptance/semantic_ingestion/test_sia_requirements.py` passed,
  and `.venv/bin/ruff check
  memorii/tests/acceptance/semantic_ingestion/test_sia_requirements.py` passed,
  in the same 14.9s scoped verification command.

## Decision Log

- Decision: add the missing acceptance evidence through a linked testing
  WorkPlan rather than enlarging the implementation plan.
  Rationale: this is a substantial test/CI evidence correction with no approved
  product-semantic change.

## Review Log

Earlier review findings that the selectors underproved fail-closed production
composition, replay artifacts, and real historical correction/rekey behavior
were confirmed and corrected. Final correctness and test review is pending on
the frozen complete dependency manifest.

## Blockers And Limits

No external blocker. Whole-branch gates and hosted execution remain parent
closure responsibilities and are not acceptance-selector product scope.

## Next Action

Freeze this evidence with the shared M3.1/M4 candidate, then obtain exact-SHA
hosted execution and clean independent correctness and test review before
promoting only the three existing registry evidence statuses.

## Current Correction

Parent designated the existing deterministic host verifier and built-in local
capability fixture, with production-domain material issued only through
`build_verified_production_host_authority` as in `production_capture._capture_child`.
The acceptance selectors now pass: event replay plus support (2 tests, 9.72s),
historical truth plus support (2 tests, 11.26s), and production composition
(1 test, 17.96s). Collection found all three selectors in 7.72s; scoped Ruff
and compile pass. The prior blocker is resolved; workflow and traceability
structure validation remains.

Maintainability correction: the acceptance file now imports terminal fixture
authority from `tests.fixtures.semantic_ingestion.semantic_terminal_fixture`;
it no longer mutates `sys.path` or dynamically imports a unit-test module.
The three selectors pass together (3 tests, 23.27s), collection finds all
three (6.80s), and scoped Ruff/compile pass.

The terminal fixture's clean-room source-authority dependency is also now
fixture-local (`clean_room_request_fixture`), so the acceptance path imports
no `tests.unit` module. The exact selectors pass again (3 tests, 19.95s), and
Ruff/compile pass for both fixture modules and the acceptance file.

Fixture ownership correction: `semantic_terminal_fixture` and
`clean_room_request_fixture` are now the sole fixture-package owners; all
test consumers import them through `tests.fixtures.semantic_ingestion`, and
the duplicate unit support modules were removed. The three selectors pass
again (3 tests, 21.08s); affected event-replay and policy-migration consumers
collect (32 tests, 10.70s), and scoped Ruff/compile pass.

The selected workflow/traceability command ran 17 checks in 12.10s: 16 passed,
including `test_pr_workflow_structurally_runs_complete_matrix_and_exact_pinned_checker`.
`test_registry_loaders_and_structural_rebuild_agree_on_canonical_bytes` failed
because the concurrently changed design now has numeric headings absent from
the registry's `heading_defaults`; this is an upstream design/registry authority
chain mismatch, not an acceptance-selector failure. Identity hygiene did not
reach a terminal result within the local command runner's 30-second execution
cap and remains parent-owned retry evidence.

## Outcome And Retrospective

The scoped testing operation is locally complete. The three registered
acceptance behaviors use canonical production owners, the full containing file
passes 200 tests under warnings-as-errors, and the local authority and identity
gates pass. No product semantics or adjacent feature scope was added. Final
approval remains deliberately parent-owned because it must bind an immutable
candidate and hosted result.
