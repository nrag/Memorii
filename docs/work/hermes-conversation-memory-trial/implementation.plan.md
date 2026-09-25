# Hermes Conversation Memory Trial Implementation

- Work ID: `hermes-conversation-memory-trial-implementation`
- Work type: implementation
- Delivery fidelity: Level 2 early real-world testing
- Status: under-review
- Coordinator: `/root`
- Base revision: `d0c96305397f03c1e4a09e548f0fbd62602b3f95`
- Candidate product revision: `ef187110ca53d10cab6e4bfa0f3c7f65149a475b`
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
| HCM-01 | one installed Hermes provider and service-factory entrypoint; installed resource validation | verified in the pinned candidate image |
| HCM-02 | complete user/assistant pair admission, stable position identity, replay idempotence, incomplete-turn denial | verified locally |
| HCM-03 | only model transport is faked in deterministic tests; typed candidates reach V3 materialization and commit | verified locally and once with live OpenAI on Windows |
| HCM-04 | installation/user/agent scope isolation, later-session recall, reopen | verified locally; live same-volume Windows recall observed |
| HCM-05 | durable admission, two-attempt retry, startup recovery, atomic commit, invalid-candidate terminalization | verified locally |
| HCM-06 | `memorii-hermes` status and inspect expose authority and committed-state counts without runtime construction | verified locally and in Windows container |

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
- Candidate manifest v2 validates 300 changed paths and includes the deleted
  legacy Bootstrap preparation test.

## Candidate Freeze

- Candidate product revision: `ef187110ca53d10cab6e4bfa0f3c7f65149a475b`
- Candidate manifest SHA-256: `7616ae1bb6bedc122c40897a34c39d911b6e98432e446bde48598ff003efc940`
- Candidate file count: 300
- Changed-files digest: `eaa90709e703d7f5ccf78b8f9a4c2de6ecf1e1e71cc09808bc2bac26b40b5c7a`
- Manifest scope: every changed product, design, generated, Docker, workflow,
  and test path outside `docs/work/`
- Deletion coverage: `memorii/tests/unit/core/semantic_ingestion/test_bootstrap_text_preparation_producer.py`

## Operational Evidence

The prior Windows Docker run used the repository Dockerfile, a named volume at
`/opt/data`, local Level 2 authorization, installed Hermes, and live OpenAI. It
committed `Mars Venus 008 project owner is Ada.` and, after a same-volume
restart, answered `Ada` to `Who owns Mars Venus 008`. Inspection showed one
fully committed operation, one retrieval-visible record, and one runtime-context
projection. Materialized-store inspection confirmed a committed semantic
`bootstrap_v3_claim_assertion`; raw transcript records remained internal
control data.

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
remaining_blocks_approval:
  - final revision-bound spec/correctness/test delta review
  - current required GitHub checks
level_2_candidate_disposition: under_review
```

## Next Action

Commit and push the frozen evidence head, run final independent delta review,
and require green checks before merge.
