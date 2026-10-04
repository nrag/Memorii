# Gates And Workflow Authority

The machine-readable [workflow inventory](workflow-inventory.json) is copied from all three actual workflow files at the planning baseline, retaining each job's exact commands, matrix, working directory, Python version, environment references, dependencies, conditional execution, permissions and uploads. Hashes bind this snapshot. It is evidence of configuration, not evidence that a job ran or that branch protection requires it. Refresh directly from live workflows at each coherent candidate and before closure.

## Local Commands

Cwd memorii/, CI-equivalent selected environment (ordinary jobs Python 3.11, canonical checks Python 3.12; dependencies `.[local,dev]`). Local .venv is 3.12.14 and does not prove 3.11 parity. Obtain separate compatible environments before claiming their results. Package requires Python >=3.11; adding SQL/backend/client dependencies requires reviewed manifest/install/package proof.

```bash
python -m pip install -e '.[local,dev]'
python -m ruff check memorii tests
python -m memorii.tools.identity_hygiene --root .. --allowlist ../.agents/identity_hygiene_allowlist.json
pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"
python -W error -m pytest tests/unit -p no:cacheprovider
python -m memorii.tools.test_shards verify --config tests/ci/unit-shards.json
python -m memorii.tools.test_shards run --config tests/ci/unit-shards.json --index 0
python -m memorii.tools.test_shards run --config tests/ci/unit-shards.json --index 1
python -m memorii.tools.test_shards run --config tests/ci/unit-shards.json --index 2
python -m memorii.tools.test_shards run --config tests/ci/unit-shards.json --index 3
python -m memorii.tools.test_shards run --config tests/ci/unit-shards.json --index 4
python -m memorii.tools.test_shards run --config tests/ci/unit-shards.json --index 5
```

A complete ordinary unit run can aid diagnosis; exact shard/timing/aggregate evidence is still needed for CI parity. Do not repeatedly run both after micro-edits. Execute the copied workflow commands with their actual pins/environments, not a simplified substitute, for canonical authorities, package/installed preparation, seven semantic-terminal shards, timing inventories, provider/scoped/semantic/graph-boundary and benchmark artifact checks. The inventory holds exact commands to avoid stale duplicated shell blocks. Expand matrix parameters explicitly per candidate; save each result and generated/timing artifact. Never blindly execute GitHub secret-bearing/live steps from this configuration snapshot.

## Current Job Families And Applicability

| Workflow family | Required handling for this implementation |
| --- | --- |
| PR static-analysis | Ruff, Pyright and identity command; all new owners/schema/tests/manifests included |
| PR unit-test-shards, unit-timing-inventory, unit-tests | Six complete unit shards, timing upload/verify and aggregate dependencies; preserve warning mode and exact ownership |
| PR semantic-terminal-persistence + timing | Seven complete shards and timing inventory; memory-plane backend changes affect these paths |
| PR semantic-ingestion history, equal-version, CTV compiler/exact/PR-tamper jobs | Preserve all frozen decision/design/registry authority; execute pinned jobs for affected authority chains and final candidate |
| PR package-smoke and hermes-installed-image-lifecycle | Existing installed package preparation and Docker gate; new SQLite/client/resources must work outside source checkout |
| PR provider-compatibility, scoped-context-integration, observation-ledger-activation | Retain real authorization/capture/query/publication behavior with shared backend |
| PR semantic generation/projection/scenario/acceptance, Hermes Level2 product, acceptance authority and semantic aggregate | Existing complete semantic/ontology and generated authority behavior must remain; Level2 proof is not Level3 deployment approval |
| PR bootstrap-graph-transaction-boundary + aggregate | Existing 4 roots x 2 backends preserved; linked testing operation adds shared-SQLite production coverage and measures cost without weakening old format/diagnostic coverage |
| PR benchmark-contract-tests/artifacts/aggregate | Deterministic fake-oracle/artifact/prompt/quality-contract regressions retained; not proof that agents improve |
| canonical-evidence-parity-scheduled | Python3.12 mode parity (2 tests) and admission limits (3 tests); baseline is scheduled, not required PR enforcement. Shared storage rollout must obtain current affected evidence and avoid claiming required CI until actual gate policy exists |
| benchmark-scheduled | Existing component live policy/matrix/aggregation at designated exact candidate, separate from deferred comparative agent benchmark; credentials/provider access required later |

The JSON inventory records all individual job IDs, including matrix members and needs relations omitted from prose. Normal branch-required versus candidate-required checks must be read from repository settings/run evidence at release; this plan does not infer settings from job names.

## Planned New Enforcement (Not Yet Present)

Linked design-tests work owns final suite layout/runtime budgets and CI amendments before implementation adds substantial tests: shared partition/schema/identity contracts; process crash and replay; installed JSONL adoption/migration/rollback; actual Hermes/OpenClaw/Pi conformance; operations/full-install backup; Linux/macOS package matrix; independent reducer and engineering resource fixtures; runtime schema/OpenAPI/TS/tool generation parity. Behavioral job/test names only, no milestone IDs. Bind required aggregate dependencies explicitly; optional scheduled placement cannot replace release-required proof. Exact generated names/cardinalities are pinned after initial codec inventory.

## Revision And Closure Record

For every gate record cwd, interpreter/SQLite/dependency resolution, env names, exact command, exit, logs/artifacts, workflow hash, GitHub event, executed SHA/ref, run URL and tree fingerprint. PR head, merge-group and synthetic-merge identities differ. Refresh package hashes after any installable change. CI-only actions and Linux/macOS/native host behavior require their actual evidence. Any product/test/fixture/generated/dependency/workflow edit after final review invalidates closure; rerun affected checks and fresh whole-branch review.

At plan creation every implementation gate is **not run**. Current credentials/host versions/runners are not established. No known-failure waiver exists. Release-conformance cannot close while a required gate is missing, red, stale or only promised.

## Planned TypeScript SDK Gates

Current TS manifest/lockfile/runtime support: absent. Planned root: sdk/typescript. Before implementation, pin Node and npm versions and package-lock.json in SDK/toolchain/workflow metadata; record platform/runtime versions and reproducible dependency resolution. Exact supported version selection is an engineering readiness action, not an implicit claim that local Python gates cover the client. Node/package-manager availability and registry access remain unverified.

Cwd sdk/typescript, after the planned manifest defines these nonwatch scripts:

```bash
npm ci
npm run check:generated
npm run typecheck
npm test
npm run build
npm pack --dry-run
npm run test:installed
```

`check:generated` regenerates schema/client declarations from frozen Python/OpenAPI inputs and compares complete bytes/union inventory; `test:installed` packs the built SDK, installs it in a clean temporary project outside the source checkout, imports its public exports and runs valid/denied/stale-version/receipt protocol smoke against the installed sidecar. Scripts do not exist yet; create and enforce them through the linked testing WorkPlan before claiming client delivery. Save package tarball member inventory/digest, Node/npm/dependency identity, sidecar wheel hash and exact revision. CI must add the pinned Node environment and SDK job/aggregate rather than relying on Python tests or generated-file presence.
