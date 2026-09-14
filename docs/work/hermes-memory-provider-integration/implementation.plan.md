# Hermes Memory Provider Integration

- Work ID: hermes-memory-provider-integration
- Work type: implementation
- Delivery fidelity: Level 2 early real-world testing
- Status: Level 2 integration runnable; production authority deferred to Level 3
- Coordinator: `/root`
- Created: 2026-09-13
- Last updated: 2026-09-14
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion_completion_readiness/closure-plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md`, `docs/design/memory_evolution_runtime.md`, `docs/design/scoped_memory_context.md`, current Hermes `MemoryProvider` ABC
- Expected outputs: installable Hermes memory-provider entry point, persistent local configuration, focused host-contract tests, operator instructions

## Objective

Make the installed Memorii Python distribution directly discoverable and usable as the active external memory provider in a real Hermes process. Hermes must initialize one local persistent provider, recall context before turns, capture completed turns with stable replay identities, forward common lifecycle hooks, and reopen the same state after restart.

## Completion Contract

The operation completes when the installed entry point is discoverable through the current Hermes plugin contract; initialization uses the active `hermes_home` and its profile-local persistent root; focused tests prove availability, initialization, committed recall, completed-turn capture, lifecycle forwarding, stable replay identity, restart reopening, and explicit pre-initialization/configuration failures; package metadata, current-state documentation, and operator commands agree; applicable lint, type, packaging, identity-hygiene, and focused test gates pass; and independent specification, correctness, and test reviews report no validated P1/P2 or required correction.

## Scope

Included: an in-process Hermes `MemoryProvider` bridge, pip entry-point registration, Level 2 local filesystem configuration, deterministic delivery identifiers derived from Hermes turn evidence, lifecycle forwarding, focused tests, and exact setup/validation documentation.

Excluded: a Memorii daemon or HTTP API, changes to Hermes core, hosted multi-node storage, final signing/release packaging, adversarial plugin-loading hardening, and broad host/platform certification.

Deferred to Level 3: signed release artifacts, immutable version pinning guidance, hostile local-storage testing, exhaustive Hermes version/platform matrices, and production operational certification.

## Constraints And Invariants

- Keep the bridge in process and thin; canonical behavior stays in `ProviderMemoryService` and `HermesMemoryProvider`.
- Use Hermes's `hermes_agent.memory_providers` entry-point contract and current `MemoryProvider` lifecycle without importing Hermes from normal Memorii package roots.
- Use the active profile's `hermes_home`; do not hardcode `~/.hermes`.
- Preserve durable JSONL state across process restart.
- Preserve scope separation and stable non-empty operation IDs; retries of the same completed turn must reuse the same identity without collapsing distinguishable turns.
- Fail explicitly when called before initialization or when the storage configuration is invalid.
- Level 2 prioritizes working happy scenarios and common failures. Production signing and adversarial hardening remain deferred.

## Design Baseline

- Canonical design: `docs/design/semantic_ingestion_architecture.md` at base revision `93788d92`.
- Supporting designs: `docs/design/memory_evolution_runtime.md`, `docs/design/scoped_memory_context.md`.
- In-scope requirements: normal Hermes production composition for semantic ingestion and retrieval (`SIA-R19`), persistent provider lifecycle and replay, scoped provider forwarding.
- Approved deviation: none. This binds the existing adapter to the external host contract without changing persisted or public Memorii semantics.
- Unresolved design questions: none; Hermes is a thin host adapter and filesystem persistence is already canonical.

## Requirement Coverage Ledger

| Requirement | Implementation | Tests | Other evidence | Status |
| --- | --- | --- | --- | --- |
| Installed Hermes discovery | Python entry point returns a concrete Hermes `MemoryProvider` | entry-point/ABC contract test | built wheel metadata inspection; real Hermes loader at `ee445299` | implemented, locally verified |
| Persistent startup and restart | One selected factory returns a configured runtime binding; bridge starts canonical ingestion once | configured initialization/reopen test | development connector setup command | Level 2 development factory implemented; production factory deferred |
| Recall and completed-turn capture | Forward `prefetch` and `sync_turn` with scope, host-issued ingress, and stable delivery identity | configured committed-recall and source-capture/replay test | production binding ledger | implemented, locally verified |
| Common lifecycle hooks | Forward turn-author binding, session end, pre-compress, memory write, delegation, and session switch where Hermes exposes them | hook dispatch, durable memory-write/session-switch, and shared-participant isolation test | compatibility notes | implemented, locally verified |
| Common failure behavior | Explicit unavailable/pre-init/invalid-root and invalid factory/binding behavior | negative tests | setup diagnostics | implemented, locally verified |

## Change Map

- Provider boundary: optional `memorii/memorii/integrations/hermes_memory_provider.py`; no core semantic changes. It imports the external Hermes ABC only when Hermes loads its entry point.
- Packaging: add `hermes_agent.memory_providers` entry point to `memorii/pyproject.toml`.
- Configuration: storage root resolves to `<hermes_home>/memorii`. Exactly one `memorii.hermes.provider_service` factory returns a typed runtime binding containing the configured service and authenticated-ingress issuer. The repository development connector supplies deterministic ephemeral scenario authority only for Level 2 trials.
- Tests: focused fake-Hermes contract, persistent restart, replay, and failure coverage.
- Documentation: README installation, activation, validation, and process model.
- Non-applicable: schemas, persisted format, transactions, prompts, registries, generated artifacts, migrations, and CI workflow shape.

## Identity And Coordinate Hygiene

| Surface | Proposed or existing identity | Class | Behavioral owner or protocol meaning | Action | Proof |
| --- | --- | --- | --- | --- | --- |
| Entry point/provider name | `memorii` | behavioral identity | Hermes external memory provider | retain | discovery contract test |
| Host bridge class/module | behavior-derived Hermes provider name | behavioral identity | Hermes ABC adapter | add | identity-hygiene gate |
| Entry-point group | `hermes_agent.memory_providers` | protocol identity | current Hermes package discovery protocol | retain | installed metadata test |
| Work ID and requirement IDs | plan-only values | planning/evidence coordinate | traceability only | reject from executable names | identity-hygiene gate |

## Changed-Surface Ledger

| Path or pattern | Surface class | Intended scope owner | Authority chain | Required gates | Status |
| --- | --- | --- | --- | --- | --- |
| `memorii/memorii/integrations/hermes_memory_provider.py` | product integration | this plan | Hermes lifecycle -> deployment runtime binding -> canonical adapter -> provider service | focused tests, ruff, pyright | complete locally |
| `memorii/pyproject.toml` | package metadata | this plan | installed distribution -> Hermes entry-point discovery | metadata test, package build/check | complete locally; wheel built and inspected |
| `memorii/tests/unit/integrations/test_hermes_memory_provider_bridge.py` | tests | this plan | host contract -> production call path | focused pytest | complete locally |
| `README.md` | current-state documentation | this plan | install/config -> runtime behavior | doc review | complete locally |

## Production Entrypoint Bindings

| Requirement | Canonical trigger and composition root | Exact callsite and arguments/authority | Owner chain: validation -> write/read -> outcome | Proof and caller count | Status or blocker |
| --- | --- | --- | --- | --- | --- |
| Installed Hermes discovery/startup | Hermes selects `memory.provider: memorii`; package entry point constructs provider; Hermes calls `initialize(session_id, hermes_home=...)` | `MemoriiHermesMemoryProvider.initialize` resolves root, calls exactly one `memorii.hermes.provider_service` factory with `HermesProviderServiceContext`, validates `HermesProviderRuntimeBinding`, then calls `build_started_hermes_memory_provider(service=binding.service)` | selected factory validates authority -> canonical started adapter activates/reconciles -> durable profile store | real Hermes loader and development connector prove discovery, initialization, capture, and reopen | Level 2 runnable; signed production factory remains Level 3 work |
| Turn persistence and recall | Hermes calls `on_turn_start(...)`, `sync_turn(...)`, and `prefetch(...)` | bridge binds the current participant, derives transcript-hash delivery identity, and gets `AuthenticatedHostIngress` only from `binding.issue_ingress(HermesIngressRequest)` before passing it to canonical `HermesMemoryProvider` | Hermes evidence -> selected ingress issuance -> provider validation -> durable write/read -> rendered context | configured lifecycle/replay/reopen/shared-participant test; real loader captured and reopened two source records | Level 2 connected; derived-memory promotion remains policy-owned |

## Validation Matrix

| Behavior | Proof | Failure detected | Signal |
| --- | --- | --- | --- |
| Entry point loads a Hermes ABC subclass | isolated fake-Hermes import plus installed metadata | undiscoverable or incompatible plugin | assertion/import failure |
| Initialization opens durable profile-local storage once | temporary profile startup and reopen | ephemeral state or repeated activation | missing recall/state mismatch |
| Completed turn is durably captured and committed memory is recallable | configured factory sync plus prefetch/reopen | host calls do not reach Memorii or durable state is not reopened | durable semantic-source cardinality and rendered committed context |
| Same delivery retries idempotently | repeated identical completed message evidence | duplicate ledger/memory writes | two user/assistant semantic-source records after retry |
| Lifecycle hooks forward | fixture issuer records typed hook requests; JSONL assertions cover explicit memory writes before and after a session switch | dropped hooks, missing explicit writes, or stale switched scope | exact hook/session assertions plus durable source records |
| Misuse fails clearly | pre-init, unavailable factory, unusable root, and invalid ingress cases | silent no-op or hidden fallback | typed exception/unavailable reason with unchanged source count |

## Migration, Rollout, And Rollback

No persisted-data migration is introduced. Rollout is opt-in by installing the distribution in Hermes's Python environment and selecting `memory.provider: memorii`. Rollback selects another provider or disables external memory; the Memorii storage directory remains intact for later reuse. Mixed-version behavior is bounded by the tested current Hermes ABC and documented as Level 3 matrix work.

## Verification Commands

- `.venv/bin/python -W error -m pytest tests/unit/integrations/test_hermes_memory_provider_bridge.py -p no:cacheprovider -q`
- `.venv/bin/python -W error -m pytest tests/unit/core/semantic_ingestion/test_provider_compatibility.py -p no:cacheprovider -q`
- `.venv/bin/python -m ruff check memorii/integrations/hermes_memory_provider.py tests/unit/integrations/test_hermes_memory_provider_bridge.py`
- `.venv/bin/python -m pyright --pythonpath "$(.venv/bin/python -c 'import sys; print(sys.executable)')"`
- `.venv/bin/python -m memorii.tools.identity_hygiene --root .. --allowlist ../.agents/identity_hygiene_allowlist.json`
- Build wheel and inspect `hermes_agent.memory_providers` metadata.
- Load the entry point through the current Hermes plugin loader and real `MemoryProvider` ABC.
- Applicable existing provider tests and current workflow-required deterministic gates will be inventoried before closure.

## Gate And Known-Failure Ledger

| Gate | Required | Result and revision |
| --- | --- | --- |
| Focused Hermes bridge tests | yes | 9 passed within the combined 22-test run at `a862b361` |
| Existing provider compatibility tests | yes | 13 passed within the combined 22-test run at `a862b361` |
| Ruff and pyright | yes | ruff changed paths passed; complete configured pyright exited 0 with no diagnostics at `a862b361` |
| Identity hygiene | yes | exited 0 with no diagnostics |
| Wheel metadata/build | yes | root environment built `memorii-0.1.0-py3-none-any.whl`; archive contains the bridge and the expected `hermes_agent.memory_providers` entry point |
| Current Hermes contract | yes | current `NousResearch/hermes-agent` revision `ee445299` loaded the entry point through `plugins.memory.load_memory_provider`; concrete class satisfies the real ABC and returns the explicit missing-factory diagnostic |
| Development connector package and setup | yes | both wheels built; exact provider/factory entry points inspected; setup unit tests passed |
| Real Hermes development initialize/capture/reopen | yes | current loader reported available; two completed-turn source records persisted and reopened |
| Current PR CI | external evidence | PR #120 merged green at `410ce4a8`; connector commits require a successor PR for hosted gates |

Known candidate limitation: the development connector imports repository test authority and must be installed editable from this checkout. It proves the real Hermes/plugin/storage path before release signing, but it is not production authority or release evidence.

Candidate freeze: development connector implementation commit `3dd29f4e`; revision-bound candidate refresh `424e27df`; preflight artifact `docs/work/hermes-memory-provider-integration/production-entrypoint-preflight.md`.

## Delegation And Cost Ledger

| Delegate | Role/tier | Ownership | Rationale | Status/output |
| --- | --- | --- | --- | --- |
| `/root/hermes_plugin_preflight` | read-only Spark code mapper | Hermes contract and production binding artifact | required entrypoint preflight | completed; identified existing adapter, absent entry point, and activation-authority boundary |
| `/root/hermes_plugin_writer` | sole Terra writer | product, tests, packaging, docs, this plan updates | one coherent integration slice | completed; produced bounded candidate at base `93788d92` |
| `/root/hermes_bridge_spec_review` | read-only specification reviewer | candidate authority and requirement alignment | final bounded review | blocked approval because production factory has zero callers and candidate identity was not frozen |
| `/root/hermes_bridge_correctness_review` | read-only correctness reviewer | Hermes runtime and scope behavior | final bounded review | confirmed missing factory; found shared-participant defect, corrected after review; initialization-reporting concern remains upstream/operational |
| `/root/hermes_bridge_test_review` | read-only test reviewer | candidate evidence and behavior coverage | final bounded review | blocked approval until candidate identity and preflight artifact are recorded |

## Progress And Decisions

- 2026-09-13: Selected the in-process pip entry-point path because Hermes natively discovers `hermes_agent.memory_providers`; no network service is required.
- 2026-09-13: Selected Level 2 persistent local operation and common failures. Signing, hostile storage, and broad platform certification are deferred.
- 2026-09-13: Default filesystem construction fails closed because semantic activation requires deployment-owned authority. The bridge therefore discovers exactly one deployment-owned `memorii.hermes.provider_service` factory rather than importing scenario authority or weakening activation.
- 2026-09-13: The factory returns `HermesProviderRuntimeBinding`, pairing the exact canonical `ProviderMemoryService` with an issuer for `AuthenticatedHostIngress`. The bridge never reconstructs principal/session handles from Hermes text or metadata.
- 2026-09-13: Focused configured-factory evidence used existing scenario fixtures only in test code. It started the canonical adapter, proved profile-local recall, completed-turn idempotence (two durable semantic source records after a replay), lifecycle ingress requests, and restart reopening.
- 2026-09-13: A stronger assertion that a captured turn was immediately recallable failed: capture produced durable source records, while committed retrieval continued to return only the seeded committed record. The Level 2 bridge contract therefore claims durable turn capture and committed-memory recall separately; semantic evolution remains owned by the configured runtime policy.
- 2026-09-13: Built and inspected the wheel, then checked the entry point against current Hermes revision `ee4452991d17534aa561f31ee55596d082aa94e7`. Hermes loaded the concrete provider through its actual plugin loader and real ABC. Availability correctly remained false because no deployment service factory is installed.
- 2026-09-13: Correctness review identified stale startup-user recall in shared sessions. The bridge now consumes Hermes `on_turn_start(author_id=...)`, uses that participant for recall and lifecycle ingress, and has a two-participant isolation regression.
- 2026-09-13: The participant scope is stored in a `ContextVar`, matching Hermes's copied-context prefetch worker. A controlled interleaving proves Alice's suspended prefetch cannot observe Bob's later turn identity.
- 2026-09-13: The JSONL test now distinguishes two equal-content turns by completed-transcript position, deduplicates each replay, verifies explicit-memory-write persistence across session switch, rejects invalid ingress without a write, and confirms the retained IDs reopen unchanged.
- 2026-09-13: Session-end, pre-compress, and delegation remain forwarding compatibility hooks. Their structured semantic promotion depends on canonical host envelope authority and is not claimed as bridge-owned durable capture; completed turns already provide the Level 2 transcript capture path.
- 2026-09-13: Independent reviews confirmed the bridge cannot honestly close interactive validation while the production service-factory caller count is zero. This is an external deployment/signing blocker, not a reason to add a test-authority fallback.
- 2026-09-14: Added an explicit, separately installed development connector. The real Hermes loader discovered it, initialized the canonical provider, captured a completed turn into durable semantic-ingestion source records, and reopened those records on a second start. The connector uses deterministic ephemeral scenario authority and does not alter the production provider package or signing contract.
- 2026-09-14: PR #120 had already merged at `410ce4a8` before the connector commits were pushed. Local focused, package, and real-loader checks pass; hosted gates for `3dd29f4e` require a successor PR.

## Next Action

Run an interactive Hermes turn with the development connector and inspect the profile-local source ledger; production signing and the deployment-owned factory remain the Level 3 next action.
