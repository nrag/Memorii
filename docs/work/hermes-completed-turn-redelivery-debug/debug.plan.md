# Hermes Completed-Turn Redelivery Correction

- Work ID: `hermes-completed-turn-redelivery-debug`
- Work type: debugging
- Delivery fidelity: Level 2 early real-world testing
- Status: complete
- Coordinator: `/root`
- Created: 2026-09-24
- Last updated: 2026-09-24
- Parent WorkPlan: `docs/work/hermes-conversation-memory-trial/implementation.plan.md`
- Related WorkPlans: `docs/work/hermes-completed-turn-delivery/debug.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md` section 8.7; Hermes completed-turn provider bridge; Windows Level 2 Docker recall evidence.
- Expected outputs: idempotent completed-turn redelivery, completed-runtime lifecycle isolation, tagged tested Docker base with an immutable-image override, and focused regression proof.

## Objective

Make exact Hermes completed-turn redelivery idempotent when a later callback
has a different wall-clock time. When the completed runtime is active, route
legacy write and delegation callbacks only through its durability barrier.
Keep the tested Hermes tag explicit while requiring a full RepoDigest before
production signing.

## Completion Contract

The focused bridge regression must prove two exact redeliveries at different
callback times produce one retained operation and no collision. Legacy callback
tests must prove no legacy ingress or write occurs while the completed runtime
is active. The unit bridge/runtime suites and Ruff must pass. The Dockerfile
must select the tested Hermes tag and accept an explicit immutable-image build
override. The full Windows RepoDigest is an explicit release-signing blocker,
not a fabricated pin.

## Scope

Included: completed-turn timestamp derivation, bridge lifecycle routing,
focused tests, Docker base selection, and associated Level 2 design/evidence.

Excluded: semantic ontology changes, upstream Hermes changes, migration, and
production signing.

Deferred: adversarial transcript timestamp matrices, cross-platform image
matrices, and immutable image-digest capture for release signing.

## Constraints And Invariants

- Preserve the existing Hermes `sync_turn` ABI and fail closed for malformed or
  missing final persisted transcript timestamps.
- Retain source timestamps from the canonical completed transcript, not a
  callback-clock value.
- The completed runtime remains the only semantic-ingestion path when active;
  legacy hooks may drain it but must not issue ingress.
- A Docker tag is acceptable for Level 2 trial repeatability only; production
  signing requires the exact 64-character RepoDigest.

## Identity And Coordinate Hygiene

| Surface | Proposed or existing identity | Class | Behavioral owner or protocol meaning | Retain, rename, migrate, or reject | Proof |
| --- | --- | --- | --- | --- | --- |
| Runtime timestamp helper | `_completed_turn_timestamp` | behavioral | final persisted completed-turn event time | retain | focused runtime regression |
| Docker build argument | `HERMES_IMAGE` | behavioral | selected Hermes container image | retain | Dockerfile bridge assertion |

## Change Impact And Verification Closure

| Path or pattern | Surface class | Intended scope owner | Authority chain | Required gates | Status |
| --- | --- | --- | --- | --- | --- |
| `hermes_completed_turn_runtime.py` | product code | completed-turn runtime | canonical transcript -> admission -> source retention | focused runtime/bridge tests, Ruff | in progress |
| `hermes_memory_provider.py` | integration | Hermes bridge | callback -> completed-runtime drain -> no legacy ingress | focused bridge tests, Ruff | in progress |
| `Dockerfile.memorii` | dependency/workflow pin | Docker image composition | build arg -> tested image -> installed provider | bridge Dockerfile assertion | in progress |
| focused test files and related docs | test/documentation | correction proof | production path and operator guidance | focused tests, Ruff | in progress |

## Production Entrypoint Bindings

| Requirement | Canonical trigger and composition root | Exact callsite and arguments/authority | Owner chain: validation -> write/read -> outcome | Proof and caller count | Status or explicit blocker |
| --- | --- | --- | --- | --- | --- |
| stable completed-turn redelivery | Hermes `MemoryManager.sync_all` -> installed `MemoriiHermesMemoryProvider.sync_turn` | bridge passes the full `messages` transcript to `HermesCompletedTurnRuntime.sync_completed_turn`; runtime derives timestamp from final persisted assistant message | timestamp validation -> canonical digest/admission -> source retention -> atomic semantic operation | bridge regression uses installed first-party factory and provider; one bridge caller | in progress |
| legacy hook isolation | Hermes memory callbacks -> installed provider | `on_memory_write` and `on_delegation` call `_wait_for_completed_runtime` when present | provider initialization -> completed worker drain -> no legacy ingress/write | focused lifecycle test; two provider callbacks | in progress |

## Sources Of Truth

1. `docs/design/semantic_ingestion_architecture.md` section 8.7.
2. `memorii/memorii/core/semantic_ingestion/hermes_completed_turn_runtime.py`.
3. `memorii/memorii/integrations/hermes_memory_provider.py`.
4. The existing Windows Level 2 recall and build observations recorded in the
   linked completed-turn delivery plan.

The design governs runtime behavior; the confirmed bridge review findings
govern this correction's bounded failure cases.

## Current State

Verified facts: the completed-turn admission delivery ID excludes callback
time, but retained source contents were constructed using callback time. A
later exact redelivery therefore collides with the existing source. Completed
runtime installs also let `on_memory_write` and `on_delegation` enter legacy
ingress, where the absent operator identity is rejected. The previous Docker
base was `latest`; the recorded digest prefix contains only 48 hex characters.

Interpretation: the failure is an implementation and packaging correction in
the Level 2 production-shaped path.

## Hypothesis Ledger

1. **Confirmed:** source collision is caused by `received_at` entering durable
   source timestamps while delivery identity excludes it. A persisted final
   transcript timestamp removes the mutable callback input.
2. **Confirmed:** active completed runtime does not guard legacy write and
   delegation hooks, so those hooks issue an incompatible legacy ingress.
3. **Confirmed:** the recorded image digest cannot pin Docker because it is not
   a full SHA-256; the tested release tag is supported by the observed Hermes
   version, while the exact RepoDigest remains unresolved.

## Experiments

### Exact completed-turn redelivery

- Hypothesis being tested: transcript timestamp, rather than callback time,
  stabilizes exact redelivery.
- Discriminating observation: two callbacks with distinct injected bridge
  clock values retain exactly two source records and one runtime projection.
- Procedure: initialize the first-party provider, sync one timestamped
  completed transcript twice, drain after each callback, and inspect records.
- Expected outcomes: old behavior raises a collision; corrected behavior has
  one semantic operation.
- Actual result: the bridge regression is implemented; the shared-worktree test
  runner exceeded the interactive 30-second observation window before returning
  a terminal result.
- Conclusion: implementation is ready for the focused full bridge run.

### Completed-runtime legacy callbacks

- Hypothesis being tested: draining and returning prevents legacy ingress.
- Discriminating observation: fake legacy provider has no calls and the
  completed runtime drains for both hooks.
- Procedure: invoke memory-write and delegation callbacks with an active fake
  completed runtime and rejecting ingress issuer.
- Expected outcomes: no legacy invocation and no ingress issuance.
- Actual result: `test_completed_runtime_lifecycle_hooks_drain_before_read_or_return_without_legacy_ingress`
  passed (1 passed, 33 deselected, 9.17s).
- Conclusion: both legacy callbacks drain and do not issue legacy ingress.

## Progress Log

- 2026-09-24: Confirmed the mutable timestamp collision mechanism and active
  completed-runtime legacy-hook bypass from the reviewed bridge paths.
- 2026-09-24: Implemented transcript-bound timestamp retention, runtime-active
  legacy callback draining, and the Docker tag/override. Targeted timestamp
  tests passed; the full bridge regression remains running beyond the
  interactive observation window. Next action: obtain its terminal result and
  run the configured full Pyright gate in the repository environment.

## Evidence Log

- The existing `HermesCompletedTurnAdmissionRequest.delivery_id` excludes
  `completed_at`; `_prepare_governed_child_source` retains it in each source.
- The bridge uses `datetime.now(UTC)` for each `sync_turn` callback.
- `Dockerfile.memorii` previously selected `nousresearch/hermes-agent:latest`.
- `pytest -q memorii/tests/unit/core/semantic_ingestion/test_hermes_completed_turn_runtime.py -k 'timestamp or canonicalization' -x`:
  13 passed, 5 deselected, 8.61s (one sandbox cache warning).
- `pytest -q memorii/tests/unit/integrations/test_hermes_memory_provider_bridge.py -k completed_runtime_lifecycle_hooks -x`:
  1 passed, 33 deselected, 9.17s (one sandbox cache warning).
- `ruff check --no-cache` over the changed Python surfaces and `git diff --check`:
  passed.
- Installed-bridge exact-redelivery regression: `1 passed in 251.64s`.
- Full configured Pyright: `0 errors, 0 warnings, 0 informations`.

## Decision Log

- 2026-09-24: use the final assistant message's persisted timestamp as the
  completed-turn time. It is the canonical terminal event that Hermes supplies
  with the completed transcript and supports exact redelivery.
- 2026-09-24: treat legacy write/delegation callbacks as completed-runtime
  drain barriers, because their evidence has already been represented by the
  completed transcript path.
- 2026-09-24: use `v2026.9.21` as the Level 2 default and provide
  `HERMES_IMAGE` override; do not invent the missing RepoDigest.

## Blockers And Limits

- The exact Windows `RepoDigest` is unavailable. It blocks production signing
  and immutable-image release evidence, but not the bounded Level 2 correction.

## Next Action

None. The correction returns to the parent PR review.
