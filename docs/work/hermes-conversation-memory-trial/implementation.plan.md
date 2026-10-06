# Hermes Conversation Memory Trial Implementation

- Work ID: `hermes-conversation-memory-trial-implementation`
- Work type: implementation
- Delivery fidelity: Level 2 early real-world testing
- Status: `complete`
- Coordinator: `/root`
- Base branch: `semantic_ingestion_m5`
- Base revision: `3cfc1efc521c98ba4c8dfa048af8546cf4ec0d3e`
- Published implementation revision: `450eccd3`
- Evidence-only descendant revision: `63658193b8a4c296b553bb6c3e7fd89392566b2a`
- Last updated: 2026-09-24
- Parent: `docs/work/hermes-conversation-memory-trial/design.plan.md`
- Governing design: `docs/design/hermes_conversation_memory_trial.md`

## Objective And Completion Contract

Run Memorii through the installed Hermes CLI as the sole current Bootstrap V3
runtime. A free-form assertion from a completed conversation turn must pass the
source-bound model proposal, deterministic validation, atomic semantic writer,
and protected reader. The fact must be recalled in a later session and after a
same-volume restart. No development connector, fixed proposal, seeded fact,
test authority, or raw transcript recall satisfies the contract.

## Scope And Decisions

This unreleased candidate has one Bootstrap V3 runtime and no V1/V2 runtime,
compatibility branch, migration, or rollback path. `memorii.project_assertions@1`
is a bounded semantic resource policy, not another runtime profile. It supports
free-form project owner, status, and deadline facts for the Level 2 trial.
Ontology learning and broader personal and enterprise predicates remain a
linked future design concern.

The local Level 2 authority selects the installed first-party factory and normal
semantic pipeline. It intentionally does not claim production signing or
release certification.

## Requirement State

| Requirement | Current evidence | State |
| --- | --- | --- |
| HCM-01 | One first-party provider and service-factory entry point; strict installed resource and fresh local sidecar validation at ingress, egress, pre-publication, recovery, and read; development factory declaration removed | verified locally and in the Windows image |
| HCM-02 | Complete Hermes user/assistant pair enters one governed two-child operation; transcript substitution and incomplete turn deny; replay is stable | locally verified |
| HCM-03 | Fake only the OpenAI Responses edge; source-quoted free-form proposal reaches the canonical V3 materializer, validators, graph group commit, and ledger | verified locally and through live OpenAI in Windows Docker |
| HCM-04 | One stable installation/resource task scope, sessionless reusable projections, exact user/agent grants, installation-bound raw-user consistency lock, absent/changed-author denial, later-session recall, cross-user/agent denial, and store reopen | locally verified |
| HCM-05 | Callback returns after durable admission; one worker owns two durable provider attempts; startup reconstructs a missing handoff from sealed ingress before activation; atomic graph commit, duplicate idempotence, and reopen are proven | verified locally and by same-volume Windows restart and recall |
| HCM-06 | `memorii-hermes status` reports authority; `memorii-hermes inspect` reports source, graph, ledger, terminal, projection, and retrieval-visible counts without constructing a runtime | verified locally and from the Windows container |

## Production Boundary

The production path is:

`hermes_agent.memory_providers:memorii` ->
`MemoriiHermesMemoryProvider` ->
`memorii.hermes.provider_service:installed` ->
`build_local_level2_runtime_binding` ->
`HermesCompletedTurnRuntime` ->
Bootstrap V3 normalization, graph-group commit, scoped runtime-context recall.

The Dockerfile installs only `memorii[live]`. The development connector has no
production entrypoint. The model emits candidate quote hints only; local schema,
predicate, source-span, provenance, lifecycle, and transactional validators
decide committed state. Invalid received candidates become durable
`evidence_only` terminals. Transport failure remains retryable.

The exact non-work changed surface is frozen in
`docs/work/hermes-conversation-memory-trial/candidate-manifest.json`. WorkPlan
and review evidence under `docs/work/` remain appendable without changing the
product candidate.

## Deterministic Evidence

- Full Ruff passed for `memorii` and `tests`.
- Configured Pyright passed with 0 errors and 0 warnings.
- Equal-version replay vectors: 30 passed.
- CTV compiler parity: 259 passed.
- Static tooling contract: 19 passed.
- Unit owner: 4,509 collected across six node-balanced shards under the 1,200-second target; maximum estimated shard 826.520 seconds.
- Hermes product module: exactly 5 scenarios collected.
- Invalid-candidate product regression: 1 passed in 835.55 seconds.
- Equal-text bridge replay regression: 1 passed in 826.52 seconds.
- Completed-turn close and post-close regression: 1 passed in 397.02 seconds.
- Installed default-image Hermes `MemoryManager` lifecycle: 1 passed in 1867.18 seconds.
- Project assertion adapter/profile focus: 9 passed in 18.85 seconds.
- Production entrypoint preflight validates all five caller counts as exactly 1.
- Candidate manifest v2 validates 301 changed paths and includes the deleted
  legacy Bootstrap preparation test.

## Candidate Freeze

- Candidate product revision: `a13f58ae4092f2e7ab5afaac2f0b08402e8dc1d7`
- Candidate manifest SHA-256: `d8b5d4419ceebb85b90799dcb9a3afbe937ad9b1fb5ef296c3c669af6f230ded`
- Candidate file count: 301
- Changed-files digest: `af02487f0c0a5b7f449e9d9e005b62ca8a4423a598cfc1f6ff7c70134885d636`
- Manifest scope: every changed product, design, generated, Docker, workflow,
  and test path outside `docs/work/`
- Deletion coverage: `memorii/tests/unit/core/semantic_ingestion/test_bootstrap_text_preparation_producer.py`

## Windows Operational Evidence

The user built the repository `Dockerfile.memorii` on Windows from runtime
revision `450eccd3`, used a named volume mounted at `/opt/data`, authorized the
local Level 2 profile, and exercised the installed Hermes CLI with live OpenAI.
The run first produced an evidence-only abstention for an unsupported project
name statement and then fully committed the supported free-form assertion
`Mars Venus 008 project owner is Ada.` After a same-volume container restart,
a new Hermes session answered `Ada` to `Who owns Mars Venus 008`.

Read-only inspection reported four captured sources, 73 graph records, three
observation-ledger entries, one fully committed operation, one evidence-only
operation, one retrieval-visible record, and one runtime-context projection.
Materialized-store inspection identified the exact projection as committed
semantic `memory_evolution` state with `visibility=runtime_context` and
`runtime_context_projection_kind=bootstrap_v3_claim_assertion`. The raw turn
and recall-query records remained `internal_control`. The successful 21:00
runtime window contained provider registration and activation with no later
initialization, synchronization, or semantic-worker failure. Earlier 18:41 to
18:48 failures remain append-only diagnostic history and predate the successful
run.

The final candidate pins Hermes `v2026.9.21` by RepoDigest
`sha256:6bece0644e29a347e5ae17db43c36938c86f171c6f5e0cef18aa2075d331f3a3`.
The prior candidate image is `sha256:d1525f997595fa3feb7085f66aa52174ff8065f42159a40f735920872c1265cf`. Hermes v0.21.4 reports Memorii installed, available, and active, and installed metadata exposes exactly the `memorii` provider and `installed` service factory. Fresh current-revision GitHub product and installed-image proof remain before merge.

## Review State

Earlier independent reviewers identified missing deletion coverage, missing
canonical entrypoint evidence, invalid candidates left recoverable, and
insufficient equal-text position proof. Those corrections are implemented in
the frozen candidate. Final delta review must bind to the evidence-only head
that contains this WorkPlan and the regenerated manifest.

```yaml
remaining_validated_p1_p2: []
remaining_blocks_approval: []
level_2_candidate_disposition: approved
operational_evidence_pending: []
```

## Next Action

Create and complete the separate Level 2 pull-request review for evidence-only
descendant `63658193b8a4c296b553bb6c3e7fd89392566b2a` plus this WorkPlan closure.

## Outcome

Level 2 is complete. The installed Windows Docker production path performed a
live model-backed semantic commit and protected later-session recall across a
same-volume restart. This is early real-world integration evidence; production
signing, release certification, learned ontology support, and Level 3 rollout
evidence remain separate work.
