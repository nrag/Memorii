# Hermes Completed-Turn Delivery Failure

- Work ID: `hermes-completed-turn-delivery-failure`
- Work type: debugging
- Delivery fidelity: Level 2 early real-world testing
- Status: active
- Coordinator: `/root`
- Created: 2026-09-23
- Last updated: 2026-09-23
- Parent WorkPlan: `docs/work/hermes-conversation-memory-trial/implementation.plan.md`
- Related WorkPlans: None
- Canonical inputs: Windows Docker observation at branch head `10b67a5781e2eeaab656b1ee2b6eacd7a274a928`; pinned Hermes image `nousresearch/hermes-agent@sha256:eaa1c0b93eea54dadb8b072ffaffd569f93af444eacc2f3a`
- Published correction revisions:
  `e21e4886ffc292e941b5af2ada28ccd9f5eb469b` (primary-context binding) and
  `f5e903d8f1c1a01fc8e7db7098fa882234e08394` (Windows Docker profile bytes)
- Expected outputs: confirmed host delivery root cause, smallest production-path correction, focused regression proof, rebuilt Windows Docker verification

## Objective

Make one completed Hermes CLI conversation turn invoke the installed Memorii
provider through Hermes' normal external-memory lifecycle so the turn is
durably admitted under `/opt/data/memorii/memory-plane` and becomes eligible
for semantic ingestion and later recall.

## Completion Contract

Complete only when the pinned installed Hermes path has a confirmed causal
explanation, the exact failure reproduces deterministically, the smallest
production-path correction is implemented, focused host/bridge regression
proof passes, and the Windows container shows a committed projection and
later-session recall. No direct provider call or development connector can
satisfy this contract.

## Scope

Included: the pinned Hermes completed-turn lifecycle, Docker packaging needed
to make that lifecycle call the installed provider, Memorii bridge compatibility,
and focused Level 2 verification. Excluded: portals, development connectors,
V1/V2 profiles, production signing, and broad upstream Hermes redesign.
Deferred: exhaustive Hermes platform matrices.

## Constraints And Invariants

- Keep Hermes as the conversation harness and `MemoriiHermesMemoryProvider` as
  the installed external-memory provider.
- Preserve one Bootstrap V3 runtime, local Level 2 authority, durable admission,
  two-attempt provider retry, and atomic semantic commit.
- Do not substitute a direct Python ingestion call for the Hermes provider
  lifecycle.
- Accept only the configured Level 2 primary CLI execution class; keep
  delegated, child, shared, and alternate-platform contexts denied.

## Expected And Observed Behavior

Expected: Hermes documents that it syncs conversation turns to the selected
external provider after every response. Observed: authorization and provider
selection succeed, a conversation completes, but
`/opt/data/memorii/memory-plane/memory_records.jsonl` does not exist. The
failure is an integration-contract defect in Memorii's interpretation of
Hermes' normal primary workspace metadata.

## Hypothesis Ledger

1. **Disproved: pinned Hermes never calls `sync_turn`.** Hermes 0.20
   has a reported defect where `_sync_external_memory_for_turn()` exists but
   has zero production callers. The installed Hermes 0.21.4 source instead has
   completed-turn callers in `agent/turn_finalizer.py` and
   `agent/codex_runtime.py`.
2. **Disproved for the storage mount: Memorii was selected in a different Hermes home.** The CLI
   could read configuration outside `/opt/data`, leaving the authorized home
   unused. The running container mounts the fresh named volume
   `hermes-memorii-l2-20260923204036` read/write at `/opt/data`; the remaining
   environment/home binding still needs one direct process check.
3. **Confirmed root cause: provider initialization fails and Hermes swallows
   it.** Hermes' primary provider contract supplies
   `platform="cli"`, `agent_context="primary"`,
   `agent_workspace="hermes"`, an agent profile, and no parent session.
   Memorii forwarded only the workspace value and its factory rejected every
   non-null workspace as delegated/shared execution. Hermes' memory manager
   logs and swallows the initialization error, leaving a discoverable provider
   object with no initialized runtime. Completed-turn delivery then cannot
   admit a source, and no Memory Plane file is created.
4. **Confirmed second root cause: Windows Docker build context changes signed
   profile bytes.** Docker `COPY` preserves CRLF bytes from the Windows working
   tree, while the Level 2 profile validates resource and component-source
   digests against LF distribution bytes. The installed log identifies the
   first mismatch as `project_assertions.output_schema.v1.json`; Hermes swallows
   that initialization exception, so completed-turn calls find no initialized
   provider.

## Experiments

### Installed host-call inventory

- Prediction under hypothesis 1: the pinned source contains a helper or manager
  dispatch but the completed conversation path has no caller.
- Prediction under hypothesis 2: configured home/provider output differs from
  `/opt/data` or `memorii`.
- Prediction under hypothesis 3: logs or a direct initialization probe reports
  a concrete exception before admission.
- Procedure: capture Hermes version, configured home/provider, installed entry
  points, exact source call sites, and `/opt/data` file inventory from the
  existing Windows container.
- Actual result: Hermes 0.21.4 at upstream revision `71a2fe39` has production
  callers in `turn_finalizer.py` and `codex_runtime.py`; `HERMES_HOME` is
  `/opt/data`; the named volume is mounted read/write. A local factory call
  using the exact primary context reproduces the rejection before service
  construction.

### Cross-platform signed-byte reproduction

- Hypotheses distinguished: a stale image or volume, versus byte conversion in
  the Windows Docker build context.
- Prediction: converting a verified LF profile resource to CRLF changes its raw
  SHA-256; normalizing only manifest-declared resources and component modules
  restores their declared digests. Semantic changes, lone carriage returns,
  and unsafe component coordinates remain rejected.
- Actual result: focused replicas prove deterministic CRLF-to-LF preparation
  restores every declared resource and component hash. Semantic drift, lone
  CR, and an unsafe module coordinate fail closed.

## Evidence Log

- Windows inspection returned
  `Memorii data was not found at /opt/data/memorii/memory-plane/memory_records.jsonl`
  after a successful authorization, provider setup, and conversation.
- `docker inspect` confirms a read/write Docker volume named
  `hermes-memorii-l2-20260923204036` is mounted at `/opt/data`; missing or
  misdirected volume attachment does not explain the absent file.
- Upstream Hermes issue #79339 reports that version 0.20 defines
  `_sync_external_memory_for_turn()` but never calls it from the real
  conversation loop. The user's installed 0.21.4 source disproves that as the
  current cause: it has callers in the turn finalizer and Codex runtime.
- The Memorii factory creates its JSONL Memory Plane on the installed provider
  path; the absence of the file proves no successful durable turn admission.
- Hermes' provider contract identifies `agent_workspace="hermes"` as normal
  primary profile metadata. Local reproduction against the reviewed revision
  with that exact value raises `LocalLevel2AuthorityError: local Level 2
  delegated or shared execution is unsupported` at `hermes_factory.py:72`.
- Local Docker verification found the previous `FROM` checksum has 48
  hexadecimal characters, and Docker requires a 64-character SHA-256 digest.
  This Level 2 Dockerfile now uses `nousresearch/hermes-agent:latest`, matching
  the user's successfully built Windows image. Selecting and release-validating
  an immutable base-image digest is deferred to Level 3 rather than inventing a
  checksum.

## Decision Log

- 2026-09-23: Treat the missing file as a host delivery failure until the
  installed pinned source discriminates the competing configuration and
  swallowed-error hypotheses. Do not change semantic ingestion or authority.
- 2026-09-23: Root cause confirmed at the host-context validation boundary.
  Correct the boundary to distinguish Hermes' fixed primary workspace marker
  from delegated/non-primary execution; preserve fail-closed denial for every
  other execution shape.
- 2026-09-23: The bridge now retains `platform` and `agent_context` in the
  typed factory context. The factory accepts exactly the pinned primary CLI
  tuple: `cli`, `primary`, `hermes`, and no parent session. Missing, alternate,
  non-primary, shared, and child contexts fail before local authority or
  service construction.

## Implementation And Verification

- Changed `memorii/integrations/hermes_memory_provider.py` to retain Hermes'
  `platform` and `agent_context` inputs in `HermesProviderServiceContext`.
- Changed `memorii/integrations/hermes_factory.py` to validate the exact
  primary-CLI context before loading authority or starting the runtime.
- Updated current Level 2 fixtures to use the pinned host's primary CLI shape
  rather than an absent workspace/context fixture.
- Added a factory denial equivalence-family regression for missing/alternate
  platform, missing/non-primary context, missing/alternate workspace, and a
  parent session.
- Added a bridge regression that initializes with the pinned primary CLI
  values, completes a normal turn, waits for the worker, and proves both a
  durable semantic source and a runtime-context record in the Memory Plane.
- Remediated the review finding that non-string `parent_session_id` values
  were normalized to `None` in the bridge. The typed context now retains the
  raw host marker, and the factory accepts only literal `None`. Focused bridge
  coverage proves integer and opaque-object parent markers reach factory
  validation, are denied, and cannot construct a service.
- `PYTHONPATH=memorii .venv/bin/pytest -q
  memorii/tests/unit/integrations/test_hermes_memory_provider_bridge.py`:
  `24 passed in 132.58s`.
- `PYTHONPATH=memorii .venv/bin/python -m pytest -q
  memorii/tests/integration/test_hermes_bootstrap_v3_product.py -p
  no:cacheprovider`: `3 passed in 1226.03s`. This re-proves durable retry,
  revocation during egress, persistence, reopen, recall, and pre-handoff
  restart recovery using the real primary CLI context and production agent
  identity.
- `.venv/bin/ruff check memorii/memorii/integrations/hermes_memory_provider.py
  memorii/memorii/integrations/hermes_factory.py
  memorii/tests/unit/integrations/test_hermes_memory_provider_bridge.py
  memorii/tests/integration/test_hermes_bootstrap_v3_product.py` and
  `git diff --check`: passed.
- Added `tools/prepare_project_assertions_docker_context.py`. Before install,
  it normalizes CRLF to LF only for the profile manifest, its fixed
  manifest-declared resource members, and component-source modules. It rejects
  invalid UTF-8, lone CR, unknown resource names, unsafe module coordinates,
  malformed SHA-256 values, semantic resource drift, and source-fingerprint
  drift, while preserving exact runtime verification.
- Changed `Dockerfile.memorii` to run that preparation tool after `COPY` and
  before editable install, then call `load_project_assertions_bundle()` inside
  Hermes' virtual environment as a post-install build gate.
- Added `.gitattributes` LF policy for the profile resources and each
  fingerprinted source module.
- Added focused CRLF-replica, semantic-drift, lone-carriage-return, and unsafe
  component-module tests. `PYTHONPATH=memorii .venv/bin/python -m pytest -q
  memorii/tests/unit/tools/test_prepare_project_assertions_docker_context.py
  memorii/tests/unit/core/semantic_ingestion/test_project_assertions_profile.py`:
  `6 passed in 18.60s`.
- `PYTHONPATH=memorii .venv/bin/python -m pytest -q
  memorii/tests/unit/integrations/test_hermes_memory_provider_bridge.py`:
  `24 passed in 128.86s`. The existing bridge suite now asserts that the pinned
  Dockerfile includes preparation and the installed-profile gate.
- `PYTHONPATH=memorii .venv/bin/python
  tools/prepare_project_assertions_docker_context.py --source-root memorii`,
  scoped Ruff, and `git diff --check`: passed.
- `docker build --no-cache -f Dockerfile.memorii -t
  hermes-memorii-profile-prep-test .`: passed. Docker executed the production
  `COPY` -> preparation -> editable install -> installed bundle-gate chain and
  produced image `hermes-memorii-profile-prep-test:latest`. The same chain is
  the non-test caller used by the Windows build.
- The opt-in Docker regression builds a minimal disposable context containing
  only `Dockerfile.memorii`, the preparation tool, `memorii/pyproject.toml`,
  `memorii/memorii`, and the root `acceptance` package. It converts every
  manifest resource and fingerprinted component source to CRLF, proves the
  unprepared output-schema bytes differ from their declared digest, builds the
  real Dockerfile, and invokes `load_project_assertions_bundle()` in the
  resulting image. `MEMORII_RUN_DOCKER_TESTS=1 PYTHONPATH=memorii
  .venv/bin/python -m pytest -q
  memorii/tests/unit/tools/test_prepare_project_assertions_docker_context.py
  -k docker_build`: `1 passed, 5 deselected in 144.14s`.

## Review Log

- Frozen Windows-build correction manifest:
  `docs/work/hermes-completed-turn-delivery/windows-build-correction-manifest.json`.
  Its base is `306c4fd281cae1fa527a1ea91ccbd2ffa5123303` and its
  post-remediation SHA-256 is
  `d47dbeae03b0e208bcdb1eff41edf616eede346ee20ebb563cc5bd3169ec79f7`.
  Targeted correctness review approved the product correction with no finding.
  Final test delta review verified the updated manifest, confirmed both prior
  verification findings resolved, and reported no remaining P1 or P2 finding.
- Targeted test review found two confirmed correction gaps. P2
  (`changes_required`, verification): the prior proof built an LF working tree,
  so it did not demonstrate the real Windows CRLF failure boundary. Resolved by
  the opt-in minimal-context Docker regression above. P3 (`follow_up`,
  verification): component-source drift lacked a direct assertion. Resolved by
  a focused semantic revision of `project_assertions.py`, which preparation
  rejects through the declared component fingerprint.
- Initial root-cause consultation declined approval because no correction
  candidate or current binding ledger existed. That was a valid readiness
  blocker rather than a product finding.
- First frozen-candidate test review reported no finding. Correctness review
  found one P2 sibling bypass: non-string parent markers were normalized to
  `None` before factory validation. The finding is confirmed and resolved by
  preserving raw markers plus integer/opaque bridge-path denial tests.
- Current correction manifest:
  `docs/work/hermes-completed-turn-delivery/correction-manifest.json`, SHA-256
  `b68e2aa8905bc4d2fcee02f556590a4798d2d522078647d500e25daaa320ab4d`.
  Final targeted correctness and test delta reviews independently verified all
  four hashes and reported no remaining finding. Both approved the bounded
  correction; Windows operational evidence remains pending.

```yaml
base_revision: 10b67a5781e2eeaab656b1ee2b6eacd7a274a928
reviewed_revision: working-tree correction manifest b68e2aa8905bc4d2fcee02f556590a4798d2d522078647d500e25daaa320ab4d
tested_revision: working-tree correction manifest b68e2aa8905bc4d2fcee02f556590a4798d2d522078647d500e25daaa320ab4d
tree_state: dirty only for the four-file correction and this debugging WorkPlan
changed_surface_inventory_complete: true
scope_delta_resolved: true
authority_chains_complete: true
required_local_jobs:
  - focused Hermes bridge suite
  - Bootstrap V3 Hermes product suite
  - scoped Ruff
  - diff and manifest integrity
passed_local_jobs:
  - focused Hermes bridge suite: 24 passed
  - Bootstrap V3 Hermes product suite: 3 passed
  - scoped Ruff: passed
  - diff and manifest integrity: passed
known_local_failures: []
failure_exclusions: []
remaining_validated_p1_p2: []
remaining_blocks_approval: []
remaining_changes_required: []
local_ci_parity: focused Level 2 correction gates only
required_checks_green: true
```

The cross-platform Docker correction is separately bound as follows:

```yaml
base_revision: 306c4fd281cae1fa527a1ea91ccbd2ffa5123303
reviewed_revision: f5e903d8f1c1a01fc8e7db7098fa882234e08394, candidate manifest d47dbeae03b0e208bcdb1eff41edf616eede346ee20ebb563cc5bd3169ec79f7
tested_revision: f5e903d8f1c1a01fc8e7db7098fa882234e08394, candidate manifest d47dbeae03b0e208bcdb1eff41edf616eede346ee20ebb563cc5bd3169ec79f7
changed_surface_inventory_complete: true
scope_delta_resolved: true
authority_chains_complete: true
passed_local_jobs:
  - CRLF preparation and installed-profile tests: 7 passed, 1 skipped
  - opt-in real Docker CRLF regression: 1 passed
  - focused Hermes bridge suite: 24 passed
  - no-cache production Docker build: passed
  - scoped Ruff and diff integrity: passed
known_local_failures: []
failure_exclusions: []
remaining_validated_p1_p2: []
remaining_blocks_approval: []
remaining_changes_required: []
required_checks_green: true
remaining_operational_evidence:
  - Windows Hermes conversation, durable inspection, restart, and later-session recall
```

## Production Entrypoint Bindings

| Trigger | Composition root and caller | Context authority and validation | Durable/read outcome |
| --- | --- | --- | --- |
| Docker image build | `Dockerfile.memorii` after `COPY` -> preparation tool -> editable `uv pip install` -> installed `load_project_assertions_bundle()` | The tool permits only fixed resource and module coordinates, converts only CRLF, and verifies every declared resource and component SHA-256. The installed runtime repeats exact validation. | Build fails closed for drift or malformed bytes; a successful image contains the bytes accepted by the production provider factory. |
| Hermes external-provider initialization | Hermes `MemoryManager.initialize_all` -> installed `MemoriiHermesMemoryProvider.initialize` -> sole `memorii.hermes.provider_service` factory | Bridge retains `platform`, `agent_context`, profile identity, workspace, parent session, user, home, and session. Factory accepts exactly `cli` + `primary` + `hermes` + no parent before authority/service construction. | Successful binding constructs the JSONL Memory Plane, current Bootstrap V3 runtime, durable completed-turn worker, and protected reader. |
| Completed user/assistant turn | Hermes 0.21.4 `turn_finalizer.py` or `codex_runtime.py` -> `MemoryManager.sync_all` -> the initialized bridge's `sync_turn` | Existing raw-author consistency, canonical transcript, current authority, installation/profile, agent, session, and source checks remain unchanged. | Atomic source admission creates `memory_records.jsonl`; worker commits graph, ledger, terminal outcome, and runtime-context projection. |
| Later query | Hermes prefetch -> initialized bridge -> completed-turn runtime protected reader | Existing installation, agent, query, purpose, grant, and freshness checks remain unchanged. | Returns committed project assertion or an empty non-disclosing result. |

Non-test production caller counts remain one installed provider entry point and
one installed service-factory entry point. The correction changes only the
context admitted at that existing composition root.

## Blockers And Limits

The macOS workspace cannot read the user's Windows Docker container. Exact
pinned-source and runtime evidence must be returned from that container.

## Next Action

Obtain the published cross-platform build correction, rebuild the Windows image
without cache, re-authorize the existing Level 2 volume against the rebuilt
image, then repeat one Hermes conversation, inspection, later-session recall,
and restart test.

## Outcome And Retrospective

Active investigation; no completion claim.
