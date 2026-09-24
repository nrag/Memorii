# Hermes Completed-Turn Delivery Failure

- Work ID: `hermes-completed-turn-delivery-failure`
- Work type: debugging
- Delivery fidelity: Level 2 early real-world testing
- Status: active
- Coordinator: `/root`
- Created: 2026-09-23
- Last updated: 2026-09-24
- Parent WorkPlan: `docs/work/hermes-conversation-memory-trial/implementation.plan.md`
- Related WorkPlans: None
- Canonical inputs: Windows Docker observation at branch head `10b67a5781e2eeaab656b1ee2b6eacd7a274a928`; pinned Hermes image `nousresearch/hermes-agent@sha256:eaa1c0b93eea54dadb8b072ffaffd569f93af444eacc2f3a`
- Published correction revisions:
  `e21e4886ffc292e941b5af2ada28ccd9f5eb469b` (primary-context binding) and
  `f5e903d8f1c1a01fc8e7db7098fa882234e08394` (Windows Docker profile bytes), and
  `826c9ee5875c8b2d99ccdd8a316b89fad0cc7af2` (Bootstrap decoder-source bytes), and
  `dc79ac8b098315d78c00b78a4af52adda0a31d7c` (Hermes transcript lifecycle and recovery), and
  `c647211705eee6ed947ce25ab0a6aca1c2265902` (Hermes persisted transcript markers)
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
5. **Confirmed third root cause: Windows Docker build context also changes
   Bootstrap V3 decoder-source bytes.** The installed factory reaches typed
   registry verification after the profile bundle succeeds, but
   `decoder-source-manifest.json` binds 6,516 rows over 36 unique Python
   sources to LF SHA-256 values. CRLF conversion invalidates each snapshot and
   raises `typed_value_registry_configuration_verification_failed` before
   Hermes obtains a runtime binding.
6. **Confirmed fourth root cause: Hermes 0.21.4 enriches transcript messages
   with host and model-carrier fields.** The completed-turn canonicalizer
   accepted only four keys and rejected the ordinary user-plus-assistant turn
   before source admission. Its role-specific known fields must be discarded
   from the canonical digest while role, content, and validated tool structure
   remain bound. Its tool-call rows also carry `call_id`, `response_item_id`,
   and optional `extra_content`, and it permits textless assistant tool-call
   rows; the canonicalizer must preserve only canonical tool identity/function
   structure and allow that bounded textless form.
7. **Confirmed fifth root cause: completed-turn runtime and legacy lifecycle
   hooks overlap.** Hermes calls session-end, pre-compress, and shutdown after
   completed-turn sync. Legacy hooks issue a second ingress that is absent-author
   incompatible, and shutdown clears the runtime before queued semantic work
   drains.
8. **Confirmed sixth root cause: lifecycle and read boundaries did not wait for
   completed-turn work.** An immediate prefetch could run before queued
   semantic work committed, while session-end and pre-compress returned without
   a durability barrier. Those completed-runtime hooks must drain and surface a
   worker failure without clearing retryable state; shutdown alone clears in
   `finally`.
9. **Confirmed seventh root cause: tool arguments were required to arrive as
   canonically encoded JSON.** Hermes preserves valid formatted or reordered
   JSON bytes. The canonicalizer must reject malformed JSON and duplicate keys,
   then bind a sorted compact encoding rather than rejecting valid transport
   formatting.
10. **Confirmed eighth root cause: `wait_for_idle()` consumed an unresolved
    worker failure.** A post-admission work failure could be removed by one
    lifecycle wait, allowing a later prefetch to look like a normal empty read.
    Failed admitted work must schedule one recovery sweep; successful recovery
    clears retained signals, while a failed sweep remains visible and does not
    schedule another sweep.
11. **Confirmed ninth root cause: repeated Level 2 authorization invalidates
    an initialized local capability checkpoint.** The rebuild instructions
    reissued `local-level2.json` in the existing home. Its new authorization
    digest no longer matches the six persisted bootstrap records, so capability
    initialization raises `capability initial freshness authority is
    unavailable`, which the provider exposes as `local Level 2 semantic runtime
    construction failed`. The immediate unreleased-product recovery is a clean
    Memorii root with one authorization; authorization renewal over retained
    semantic state requires a separate design rather than an implicit rewrite.
12. **Confirmed tenth root cause: the preserved observation-ledger genesis is
    bound to the prior image's complete package identity.** The
    captured six-record inventory contains one activated writer bound to
    activation `3f5805...`, its matching activation artifact, and its ledger
    head, plus the three capability records. Every persisted record, inventory,
    authorization, and activation digest revalidates. Only the writer,
    observation-schema, and ledger-codec fingerprints differ from the current
    target because those identities deliberately include the complete installed
    Memorii package digest. The volume was initialized by an earlier image and
    then retained across source-changing rebuilds. This is an unsupported code
    upgrade of an unreleased Level 2 store, rather than a partial activation or
    same-build restart defect.
13. **Confirmed eleventh root cause: the real completed turn reaches durable source
    admission but a fully abstained extraction cannot terminalize.** After the
    package-bound store reset, Windows inspection reports two captured sources,
    26 total records, and write revision 19. Graph, ledger-entry, terminal, and
    runtime-context counts remain zero, while the log reports
    `hermes_completed_turn_semantic_worker_failed`. The complete traceback proves
    the model correctly abstained from the unsupported project-name statement,
    then Bootstrap V3 rejected the intentional zero-operation reduction and its
    empty lineage, plan, terminal-member closure, and schema-3 ledger replay.
    Recovery retained the source as pending and blocked later startup. The
    correction recognizes only an exact fully abstained proposal with no
    operation alignments, dependency groups, operation IDs, or group results;
    it persists an evidence-only terminal and one observation-ledger entry while
    producing no semantic graph revision or runtime projection.

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

### Bootstrap V3 decoder-source reproduction

- Hypotheses distinguished: a Bootstrap V3 registry defect, versus the same
  Windows source-byte conversion outside the project profile family.
- Prediction: every manifest-declared decoder source changes digest after CRLF
  conversion; an unprepared primary factory fails typed-registry verification,
  while preparation restores the declared source bytes and factory startup.
- Actual result: all 36 local LF source hashes match their repeated decoder
  manifest rows, and every CRLF replica differs. The opt-in Docker regression
  reproduces `typed_value_registry_configuration_verification_failed` before
  preparation, then authorizes a temporary Hermes home and starts the real
  factory inside the prepared image.

### Hermes 0.21.4 transcript and lifecycle reproduction

- Prediction: decorated user, assistant, and tool messages fail under the
  former closed four-key parser; lifecycle hooks issue legacy ingress despite a
  completed-turn runtime; CLI shutdown can clear queued work before it reaches
  the semantic worker.
- Actual result: the reported ordinary decorated user-plus-assistant pair
  reproduces canonicalization failure. Focused bridge doubles prove the former
  session-end and pre-compress paths invoked legacy ingress, while shutdown did
  not wait. Real Hermes tool-call carriers and textless tool-call rows also
  reproduce rejection. Role-specific canonicalization, lifecycle bypass, and
  shutdown drain tests now cover the shared boundary. Multimodal tool-result
  content remains a Level 2 follow-up because this bounded fix preserves only
  string content and does not silently coerce arbitrary carrier structures.
  Ordered bridge doubles now prove session-end, pre-compress, and prefetch each
  drain before returning or reading, and a drain failure leaves nonterminal
  bridge state intact. Formatted/reordered JSON arguments produce equal
  canonical transcript digests; malformed JSON and duplicate keys are denied.

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
- Hermes 0.21.4 logs show a completed turn reaches Memorii with documented
  role-specific transport fields. The prior parser rejects those fields before
  durable admission; its failure is independent of authority and storage.
- The opt-in Docker regression now loads the installed `memorii` entry point,
  drives it through real Hermes `MemoryManager` initialization, sync,
  queued prefetch, the CLI session-boundary queue, shutdown, reopen, and later
  prefetch, and monkeypatches only the disposable image's OpenAI transport to a
  fixed response. It supplies one decorated textless-tool-call transcript with
  real carrier fields and a matching tool row.
  The current probe injects one post-admission `_run_semantic_ingestion`
  failure before the serialized session boundary, then requires recovery,
  persisted reopen, and later recall.
- A local authorize -> initialize -> reauthorize -> initialize reproduction
  produces the Windows state exactly: six Memory Plane records, write revision
  four, then `capability initial freshness authority is unavailable` chained
  under `local Level 2 semantic runtime construction failed`. This confirms the
  user's new empty inspection is caused by reauthorization of retained
  bootstrap state, not transcript delivery.
- The uploaded diagnostic archive reproduces the later Windows reload failure
  byte for byte. A predicate-level replay reports all activation, inventory,
  authorization, repository, head, and record-byte checks true. The only false
  predicates are the current and activation writer fingerprints, observation
  schema fingerprint, and ledger codec fingerprint. Their common preimage
  includes the installed package-root digest, so rebuilding with changed source
  correctly changes all three.
- Starting from the archive's unchanged installation ID, sidecar authorization,
  and operator binding while omitting only `memory-plane`, the current image
  activates successfully and a second factory construction against the same
  newly created store succeeds. The local Docker proof prints
  `fresh_activation_and_same_build_reopen: ok`.
- A production-path regression sends the unsupported project-name sentence,
  requires one durable observation-ledger terminal with zero graph revision and
  zero retrieval projection, reopens the same Level 2 store, then ingests the
  supported owner sentence and recalls it. The focused test passes in 300.88
  seconds. The earlier, narrower abstention-and-reopen proof passes in 85.52
  seconds. Ruff and the three normalization grammar checks also pass.
- Targeted test review required proof through Hermes' installed
  `MemoryManager` rather than only the provider's completed-turn runtime. The
  opt-in Docker probe now sends decorated persisted rows through
  `initialize_all`, `sync_all`, the session boundary, shutdown, a fresh manager,
  then a supported owner fact and a second fresh-manager recall. Its local
  non-Docker suite passes with `10 passed, 1 skipped`; execution of the Docker
  branch remains Windows trial evidence because Docker is unavailable here.
- The same review requested an exact evidence-only outcome and zero semantic
  effect. Inspection now derives terminal outcomes from the persisted canonical
  source-result member and the regression requires exactly
  `{"evidence_only": 1}`, one ledger entry, zero graph revision deltas, and
  zero retrieval-visible/runtime-context projections. The requested
  `graph_record_count == 0` assertion was rejected because that field counts
  the terminal's durable evidence members, which must exist for a completed
  no-op; graph-effect absence is represented by the revision/projection fields.
- After the remediation and final registry refresh, the focused production
  runtime proof passes with `1 passed, 3 deselected in 332.21s`; registry
  publication reproduction, all 58 independent vectors, scoped Ruff, and diff
  integrity pass.
- Targeted correctness closure approved the bounded Level 2 slice with no
  remaining validated P1/P2. Targeted test closure approved the probe topology
  and the graph-effect interpretation with no remaining validated P1/P2, but
  retains one `Not applicable / changes_required / verification` item: this Mac
  cannot execute the opt-in installed-image Docker test, so the successful
  Windows Docker result must be bound before final Level 2 closure.

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
- Generalized the build tool to `tools/prepare_memorii_docker_context.py`.
  Before install, it normalizes CRLF to LF only for the project profile's fixed
  members and component modules, plus the Bootstrap V3 decoder manifest's
  declared source files. It strictly validates manifest literals, safe
  package-relative coordinates, repeated-row consistency, UTF-8, line endings,
  and every declared SHA-256 without weakening runtime verification.
- Changed `Dockerfile.memorii` to run that preparation tool after `COPY` and
  before editable install, then call `load_project_assertions_bundle()` inside
  Hermes' virtual environment as a post-install build gate.
- Added `.gitattributes` LF policy for the profile resources and each
  fingerprinted source module.
- Added focused CRLF-replica, semantic-drift, lone-carriage-return, and unsafe
  component-module tests. `PYTHONPATH=memorii .venv/bin/python -m pytest -q
  memorii/tests/unit/tools/test_prepare_memorii_docker_context.py
  memorii/tests/unit/core/semantic_ingestion/test_project_assertions_profile.py`:
  `6 passed in 18.60s`.
- `PYTHONPATH=memorii .venv/bin/python -m pytest -q
  memorii/tests/unit/integrations/test_hermes_memory_provider_bridge.py`:
  `24 passed in 128.86s`. The existing bridge suite now asserts that the pinned
  Dockerfile includes preparation and the installed-profile gate.
- `PYTHONPATH=memorii .venv/bin/python
  tools/prepare_memorii_docker_context.py --source-root memorii`,
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
  memorii/tests/unit/tools/test_prepare_memorii_docker_context.py
  -k docker_build`: `1 passed, 5 deselected in 144.14s`.
- The strengthened opt-in Docker regression CRLF-converts both signed profile
  and every decoder-declared source. It first authorizes a temporary home in
  the unprepared source tree and proves exact typed-registry verification
  failure. It then builds the real Dockerfile, authorizes a temporary Hermes
  home inside the image, and proves the real primary factory constructs its
  completed-turn runtime. `MEMORII_RUN_DOCKER_TESTS=1 PYTHONPATH=memorii
  .venv/bin/python -m pytest -q
  memorii/tests/unit/tools/test_prepare_memorii_docker_context.py -k
  docker_build`: `1 passed, 10 deselected in 285.66s`.
- `PYTHONPATH=memorii .venv/bin/python
  tools/prepare_memorii_docker_context.py --source-root memorii` and
  `PYTHONPATH=memorii .venv/bin/python -m pytest -q
  memorii/tests/unit/tools/test_prepare_memorii_docker_context.py
  memorii/tests/unit/core/semantic_ingestion/test_project_assertions_profile.py`:
  `12 passed, 1 skipped in 48.00s`. The focused Hermes bridge suite also
  passed: `24 passed in 144.90s`. Scoped Ruff and `git diff --check` passed.

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
- The Windows runtime exposed the decoder-source byte family after the frozen
  correction passed its profile-only gate. This is a confirmed Level 2 P1
  (`changes_required`, runtime behavior): ordinary Hermes initialization fails
  on Windows CRLF checkouts. The earlier frozen correction remains unchanged.
  The generalized candidate is frozen in
  `windows-bootstrap-build-correction-manifest.json`, SHA-256
  `a79bc92231f4a6664668710d3cbde8e160a60bedd243259149602129e5d8ae2b`.
  Targeted correctness and test reviewers verified every hash and deletion,
  approved the correction, and reported no remaining P1 or P2 finding.
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

The generalized Bootstrap decoder-source correction is bound as follows:

```yaml
base_revision: fa0763952a142a34ee6a04e4e65ef95d6649c77a
reviewed_revision: 826c9ee5875c8b2d99ccdd8a316b89fad0cc7af2, candidate manifest a79bc92231f4a6664668710d3cbde8e160a60bedd243259149602129e5d8ae2b
tested_revision: 826c9ee5875c8b2d99ccdd8a316b89fad0cc7af2, candidate manifest a79bc92231f4a6664668710d3cbde8e160a60bedd243259149602129e5d8ae2b
changed_surface_inventory_complete: true
scope_delta_resolved: true
authority_chains_complete: true
passed_local_jobs:
  - signed profile and decoder preparation plus bridge suites: 36 passed, 1 skipped
  - opt-in real CRLF Docker factory regression: 1 passed
  - scoped Ruff, preparation, and diff integrity: passed
known_local_failures: []
failure_exclusions: []
remaining_validated_p1_p2: []
remaining_blocks_approval: []
remaining_changes_required: []
required_checks_green: true
remaining_operational_evidence:
  - Windows Hermes conversation, durable inspection, restart, and later-session recall
```

The Hermes 0.21.4 transcript and lifecycle correction is active and awaits
final targeted review. Focused proof includes
decorated ordinary and tool transcripts, JSON canonical equivalence and
duplicate-key rejection, runtime lifecycle/read barriers and retained-failure
state, legacy fallback, and shutdown drain/failure cleanup.

`PYTHONPATH=memorii .venv/bin/python -m pytest -q
memorii/tests/unit/integrations/test_hermes_memory_provider_bridge.py
memorii/tests/unit/core/semantic_ingestion/test_hermes_completed_turn_runtime.py`
passed after recovery remediation with `46 passed in 202.89s`. Scoped Ruff and
`git diff --check` passed.

- Current correction checks: `PYTHONPATH=memorii .venv/bin/python -m pytest -q
  memorii/tests/unit/integrations/test_hermes_memory_provider_bridge.py -k
  'completed_runtime_lifecycle or shutdown or legacy_lifecycle'` passed with
  `7 passed, 24 deselected in 10.79s`; the complete runtime canonicalization
  module passed `13 passed in 10.88s`. Scoped Ruff and `git diff --check`
  passed.
- Recovery delta checks prove a fail-once work item recovers before idle and
  clears its signal; a persistent recovery failure remains visible over
  repeated waits and schedules no additional sweep. The complete runtime module
  passed with `15 passed in 8.46s` before the aggregate run above.
- `MEMORII_RUN_DOCKER_TESTS=1 PYTHONPATH=memorii .venv/bin/python -m pytest
  -q memorii/tests/unit/tools/test_prepare_memorii_docker_context.py -k
  docker_build -p no:cacheprovider` passed after the final recovery evidence
  delta with `1 passed, 10 deselected in 331.66s`. The test builds the current
  CRLF-shaped image, loads the installed
  provider entry point through the real Hermes manager, commits a decorated
  tool-bearing turn, injects one post-admission semantic failure, recovers it,
  crosses the serialized CLI session boundary, shuts down, reopens the same
  store, and retrieves the committed project fact.
- The final installed-manager Docker rerun passed with `1 passed, 10
  deselected in 331.84s`. Its separate persistent-failure scenario now counts
  the actual `_recover_pending` invocation, proves exactly one recovery sweep
  runs, and proves repeated barriers neither hide the failure nor schedule an
  additional sweep.
- Initial targeted review found a P1 read-after-write/session-boundary race and
  a P2 rejection of valid provider-formatted tool JSON. Both are resolved:
  completed-runtime session hooks and reads drain admitted work, and tool
  arguments are strictly parsed with duplicate-key rejection then canonicalized
  for the transcript digest. The corrected candidate manifest is
  `hermes-transcript-lifecycle-correction-manifest.json`, SHA-256
  `cf6c6384eac07e3f84e69298a19d18c5e83e4c82aad1fc27f1814413fb4d34e8`.
- Final correctness review found one P2 recovery sibling: session-end could
  consume the only post-admission worker-failure signal before a later read.
  The runtime now schedules exactly one existing recovery sweep for failed
  admitted work, clears retained failures only after successful reconciliation,
  and reports unresolved recovery failures on every later barrier without an
  unbounded reschedule loop. The installed-manager Docker proof now covers both
  fail-once recovery and a separate persistent failure whose signal remains
  visible on repeated barriers while its recovery-attempt count stays fixed.
- Final test delta review verified manifest SHA-256
  `cf6c6384eac07e3f84e69298a19d18c5e83e4c82aad1fc27f1814413fb4d34e8`,
  all five member hashes, the complete changed-file inventory, and the actual
  `_recover_pending` caller proof. It re-ran the runtime suite with `15
  passed`, resolved the prior verification finding, approved the correction,
  and reported `remaining_validated_p1_p2: []`.
- The live Windows retry exposed Hermes persistence metadata that the earlier
  simulated manager input omitted. Pinned Hermes 0.21.4 source proves
  `turn_finalizer` persists before external-memory sync and
  `sync_flushed_message_markers` mutates each live row with `_db_persisted` and
  optional `_row_id`. The bounded correction accepts and discards exactly
  those two markers for every supported role while unknown fields remain
  denied and are named in the diagnostic.
- Frozen persisted-transcript manifest:
  `hermes-persisted-transcript-correction-manifest.json`, SHA-256
  `8ecbf2bf565cc3b703c777717f62412b8b06d84508e3b12d62dd43b8bb1fea63`.
  Correctness and test reviewers independently verified all three member
  hashes and the complete inventory, re-ran the marker-bearing runtime suite
  with `15 passed`, approved the delta, and reported
  `remaining_validated_p1_p2: []`.
- The complete runtime and bridge suites passed with `46 passed in 142.08s`.
  The installed Hermes Docker proof, now carrying `_db_persisted` and `_row_id`
  on user, assistant, and tool rows, passed ingestion, recovery, session
  boundary, reopen, and recall with `1 passed, 10 deselected in 372.27s`.
  Scoped Ruff and diff integrity passed.

The transcript and lifecycle correction is bound as follows:

```yaml
base_revision: 9e91df930107c62f76c89fbeaa66edda88a1cd77
reviewed_revision: working-tree correction manifest cf6c6384eac07e3f84e69298a19d18c5e83e4c82aad1fc27f1814413fb4d34e8
tested_revision: working-tree correction manifest cf6c6384eac07e3f84e69298a19d18c5e83e4c82aad1fc27f1814413fb4d34e8
changed_surface_inventory_complete: true
scope_delta_resolved: true
authority_chains_complete: true
passed_local_jobs:
  - completed-turn runtime and Hermes provider bridge suites: 46 passed
  - focused runtime review rerun: 15 passed
  - installed Hermes MemoryManager Docker regression: 1 passed, 10 deselected
  - scoped Ruff and diff/manifest integrity: passed
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
| Docker image build | `Dockerfile.memorii` after `COPY` -> preparation tool -> editable `uv pip install` -> installed bundle gate | The tool permits only fixed project-profile coordinates and Bootstrap decoder-manifest package paths, converts only CRLF, and verifies profile plus every declared decoder SHA-256. Runtime repeats profile and registry verification during factory initialization. | Build fails closed for drift or malformed bytes; a successful image contains the bytes accepted by the production provider factory and Bootstrap V3 registry. |
| Hermes external-provider initialization | Hermes `MemoryManager.initialize_all` -> installed `MemoriiHermesMemoryProvider.initialize` -> sole `memorii.hermes.provider_service` factory | Bridge retains `platform`, `agent_context`, profile identity, workspace, parent session, user, home, and session. Factory accepts exactly `cli` + `primary` + `hermes` + no parent before authority/service construction. | Successful binding constructs the JSONL Memory Plane, current Bootstrap V3 runtime, durable completed-turn worker, and protected reader. |
| Completed user/assistant turn | Hermes 0.21.4 `turn_finalizer.py` or `codex_runtime.py` -> `MemoryManager.sync_all` -> the initialized bridge's `sync_turn` | Role-specific known carrier fields are excluded from the canonical digest; unknown keys, malformed tool calls, and unmatched tool pairs remain denied. | Atomic source admission creates `memory_records.jsonl`; worker commits graph, ledger, terminal outcome, and runtime-context projection. |
| Completed-runtime lifecycle | Hermes session-end, pre-compress, and shutdown -> installed bridge | Session-end and pre-compress drain completed-turn work and bypass legacy ingress when the runtime exists. Failed admitted work schedules one reconciliation sweep; only successful recovery clears its failure signal. Shutdown clears in `finally`. Runtime-free installations retain legacy hooks. | One completed-turn execution path admits each turn; CLI process exit cannot silently discard queued semantic work or consume an unresolved failure. |
| Later query | Hermes `MemoryManager.prefetch_all` -> installed bridge -> completed-turn runtime protected reader | The bridge drains completed-turn work before protected prefetch; existing installation, agent, query, purpose, grant, and freshness checks remain unchanged. | Returns the just-committed project assertion or an empty non-disclosing result. |

Non-test production caller counts remain one installed provider entry point and
one installed service-factory entry point. The correction changes only the
context admitted at that existing composition root.

## Blockers And Limits

The macOS workspace cannot read the user's Windows Docker container. Exact
pinned-source and runtime evidence must be returned from that container.

## Next Action

Publish the reviewed correction, run the opt-in installed-image Docker probe on
the Windows host, and bind its successful result before the manual Hermes
conversation, restart, and recall trial.

## Outcome And Retrospective

Active investigation; no completion claim.
