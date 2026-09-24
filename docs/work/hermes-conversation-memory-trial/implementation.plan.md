# Hermes Conversation Memory Trial Implementation

- Work ID: `hermes-conversation-memory-trial-implementation`
- Work type: implementation
- Delivery fidelity: Level 2 early real-world testing
- Status: `in_progress`
- Coordinator: `/root`
- Base branch: `semantic_ingestion_m5`
- Base revision: `3cfc1efc521c98ba4c8dfa048af8546cf4ec0d3e`
- Last updated: 2026-09-23
- Parent: `docs/work/hermes-conversation-memory-trial/design.plan.md`
- Governing design: `docs/design/hermes_conversation_memory_trial.md`

## Objective And Completion Contract

Run Memorii through the installed Hermes CLI as one current Bootstrap V3
runtime. A free-form assertion from a completed conversation turn must pass the
source-bound model proposal, deterministic validation, atomic semantic writer,
and protected reader. The fact must be recalled in a later session and after a
same-volume restart. Completion also requires a clean Windows Docker run from
the committed revision. No development connector, fixed proposal, seeded fact,
test authority, or raw transcript recall can satisfy the contract.

## Scope And Decisions

This is an unreleased product. The candidate has one current Bootstrap V3
runtime and intentionally provides no V1/V2 runtime profile, compatibility
branch, migration, or rollback path. `memorii.project_assertions@1` is the
bounded semantic resource policy for the first trial; it is not a second
runtime profile. Local Level 2 authorization selects the normal first-party
factory and normal semantic pipeline but cannot produce production signing or
release evidence.

The first trial supports free-form project owner, status, and deadline facts.
Ontology learning and broader personal/enterprise predicates remain a linked
future design concern and do not block this Level 2 learning loop.

## Requirement State

| Requirement | Current evidence | State |
| --- | --- | --- |
| HCM-01 | One first-party provider and service-factory entry point; strict installed resource and fresh local sidecar validation at ingress, egress, pre-publication, recovery, and read; development factory declaration removed | locally verified; Windows image pending |
| HCM-02 | Complete Hermes user/assistant pair enters one governed two-child operation; transcript substitution and incomplete turn deny; replay is stable | locally verified |
| HCM-03 | Fake only the OpenAI Responses edge; source-quoted free-form proposal reaches the canonical V3 materializer, validators, graph group commit, and ledger | locally verified; live OpenAI Docker call pending |
| HCM-04 | One stable installation/resource task scope, sessionless reusable projections, exact user/agent grants, installation-bound raw-user consistency lock, absent/changed-author denial, later-session recall, cross-user/agent denial, and store reopen | locally verified |
| HCM-05 | Callback returns after durable admission; one worker owns two durable provider attempts; startup reconstructs a missing handoff from sealed ingress before activation; atomic graph commit, duplicate idempotence, and reopen are proven | locally verified for Level 2; Windows restart pending |
| HCM-06 | `memorii-hermes status` reports authority; `memorii-hermes inspect` reports source, graph, ledger, terminal, projection, and retrieval-visible counts without constructing a runtime | locally verified; Windows output pending |

## Production Entrypoint Bindings

| Trigger | Exact production path | Non-test callers | Result |
| --- | --- | --- | --- |
| Operator authorization | `memorii-hermes` -> `hermes_local_authority.main` -> `authorize_local_level2` | one console entry point | verifies installed bytes and atomically writes the installation-bound sidecar |
| Hermes discovery | `hermes_agent.memory_providers:memorii` -> `MemoriiHermesMemoryProvider.initialize` | Hermes plugin loader | accepts exactly one service factory with the first-party value |
| Service composition | `memorii.hermes.provider_service:installed` -> `build_local_level2_runtime_binding` | one provider bridge caller | verifies authority, activates the ledger, builds the provider and completed-turn runtime |
| Completed turn | bridge `sync_turn` -> `HermesCompletedTurnRuntime.sync_completed_turn` -> `HermesCompletedTurnAdmissionService` | one bridge caller | atomically admits the complete pair and returns after queueing the durable operation |
| Semantic worker | `HermesCompletedTurnRuntime` single worker -> provider coordinator -> V3 recovery/normalization/graph owners | one factory-owned daemon | performs remote work, two-attempt retry, startup recovery, and terminal commit outside the Hermes callback |
| Model proposal | current V3 host bundle -> `BootstrapV3OpenAIProjectAssertionsTransport` | one installed factory-composed runtime | performs the source-bound OpenAI request; returns candidates only |
| Semantic commit | completed-turn runtime -> provider coordinator -> V3 normalizer -> atomic graph-group CAS | one installed runtime caller | commits typed graph, observation ledger, terminal state, and runtime-context projection atomically |
| Recall | bridge `prefetch` -> completed-turn runtime `prefetch` -> scoped context reader | one bridge caller | issues fresh query/session/user-bound grants and returns committed runtime context |
| Inspection | `memorii-hermes inspect` -> JSONL Memory Plane snapshot | one console entry point | read-only operational counts; no model or runtime activation |

There is no production entry point in
`tools/hermes_development_connector/pyproject.toml`. The Dockerfile installs
only `memorii[live]`, so a clean image has exactly one first-party factory.

## Authority And Transaction Boundary

The operator CLI binds installation ID, canonical Hermes home, current
Bootstrap V3 release, project-assertions resource digests, execution class,
model, expiry, and explicit OpenAI egress acknowledgement. The factory reloads
and validates that authority before it constructs the runtime. The model emits
candidate quote hints only. Local parsing, predicate validation, source-span
closure, temporal/trust policy, writer admission, and the graph transaction
decide committed state. The graph-group CAS writes the committed typed claim,
observation ledger, terminal evidence, and runtime-context projection under
one Memory Plane revision.

## Changed Surface

The candidate changes the current Bootstrap profile/resource contracts,
source preparation and normalization, provider composition, atomic graph
store/projection, local observation activation, Hermes bridge/factory/CLI,
generated typed registry publication, focused tests, governing designs, and
the Docker build context. Generated observation registry files were refreshed
with the repository publication tool because writer and decoder-bound source
digests changed.

The exact product/design/test surface is recorded in
`docs/work/hermes-conversation-memory-trial/candidate-manifest.json`. WorkPlan
and evidence files under `docs/work/` are deliberately excluded so review
records can be appended without changing the implementation candidate.

## Deterministic Evidence

- Product integration:
  `PYTHONPATH=memorii .venv/bin/python -m pytest memorii/tests/integration/test_hermes_bootstrap_v3_product.py -q -p no:cacheprovider`
  -> `3 passed in 2153.19s`. The main scenario deterministically blocks the
  provider after callback admission, proves typed restart authority is sealed
  before egress, proves no early projection, fails the first durable provider
  attempt, succeeds on the second without redelivery, commits two facts,
  denies substituted users and agents, reopens the store, and exercises status
  and inspection. The second scenario revokes authority during active egress
  and proves that no semantic commit becomes visible. The third stops after
  atomic turn admission and before handoff, reopens the production factory on
  the same JSONL store, reconstructs the handoff from sealed typed ingress,
  commits and recalls exactly once, and proves duplicate replay adds no model
  call or record.
- Focused current-runtime, project-profile, admission, and Hermes bridge suite
  -> `59 passed in 36.45s`. It includes the installation-bound operator,
  absent/changed raw-author denial before turn admission, and rejection of a
  second raw-user context on the same local installation.
- Registry publication refresh -> role count `1269`, entry count `181`, then
  `58` positive/rejection registry vectors passed with zero failures.
- Ruff, `py_compile`, and `git diff --check` pass for the changed runtime and
  test surface.
- Product integration proves free-form turn, graph and ledger commit,
  runtime-context projection, exact replay idempotence, changed-source denial,
  incomplete-transcript denial, later-session recall, and same-store reopen.
  The OpenAI HTTP response is the only faked edge.

## Candidate Freeze

- Candidate manifest: `docs/work/hermes-conversation-memory-trial/candidate-manifest.json`
- Candidate manifest SHA-256: `255f4ae8796b123a7f121ab098dab605a1bda6ce8ca47dd1cc1914b21922feb3`
- Candidate file count: `253`
- Manifest scope: every changed or untracked product, design, generated,
  Docker, and test file outside `docs/work/`
- Exclusions: `.git`, local environments/caches/build outputs, and mutable
  WorkPlan/review evidence under `docs/work/`
- Review scope: HCM-01 through HCM-06 at Level 2; production signing,
  certification, ontology learning, hostile local storage, and compatibility
  are excluded.

## Operational Evidence Still Required

The macOS workspace cannot access the user's Windows Docker daemon. After this
candidate passes independent review, it must be committed and pushed so the
Windows checkout can build the exact revision. The operator run must use the
repository `Dockerfile.memorii`, one new clean named volume, local Level 2
authorization, the Hermes CLI, a new-session query, `memorii-hermes inspect`,
and a same-volume container restart. That run supplies the remaining live
OpenAI, installed-image, and Windows evidence.

## Final Level 2 Review

The frozen candidate received independent spec, correctness, and test review
against manifest SHA-256
`255f4ae8796b123a7f121ab098dab605a1bda6ce8ca47dd1cc1914b21922feb3`.
All three reviewers reported no current P1/P2 findings. They independently
confirmed the installed factory path, installation-bound identity isolation,
typed retained restart authority, missing-handoff reconstruction, durable
two-attempt retry, atomic commit, protected recall, and exact replay behavior.

The earlier review findings are resolved: an absent or changed raw Hermes
author is rejected before admission; a second raw user cannot reuse the same
local installation authority; and startup reconstructs work admitted before a
handoff marker from sealed typed ingress before observation-ledger activation.
The factory-path reopen test proves one commit and one model call after that
recovery, with no duplicate on replay.

```yaml
remaining_validated_p1_p2: []
remaining_blocks_approval: []
level_2_candidate_disposition: approved
operational_evidence_pending:
  - clean Windows Docker image and named volume
  - live OpenAI proposal through installed Hermes
  - later-session recall
  - same-volume container restart and recall
```

The intentionally removed V1/V2 profile APIs leave older pre-cutover test
fixtures that import those APIs unable to collect as one broad historical unit
suite. Restoring the retired production interfaces would violate the selected
single Bootstrap V3 product boundary. Migrating or retiring that historical
test architecture is separate `$design-tests` work. The Level 2 acceptance
claim is bounded to the current Bootstrap V3 and Hermes product suites recorded
above; it does not claim whole-repository unit-suite compatibility.

## Next Action

Commit and push the independently approved candidate, then run the clean
Windows Docker conversation, inspection, later-session recall, and same-volume
restart trial from that exact revision.

## Outcome

The local Level 2 implementation is runnable and locally verified. The overall
WorkPlan remains in progress until the reviewed revision is committed, pushed,
and confirmed through the clean Windows Docker conversation and restart test.
