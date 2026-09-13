# Changed Surface And Authority Ledger

Reconciled against live status during construction; freeze/closure hashes follow.
No unowned changed path. Prior completed design/evidence untracked at start are
preserved inputs, not new implementation edits.

| Path | Class/owner | Authority chain | Gates |
| --- | --- | --- | --- |
| memorii/memorii/core/scoped_context/*.py | new public schemas and internal read logic / implementation | approved design -> typed contract/authority/assembler -> provider outcome | focused roots, static, unit shards, identity, reviews |
| memorii/memorii/core/memory_evolution/state_repository.py | additive snapshot decoder / implementation | canonical record -> typed same-clone readers -> runtime | structured positives and negative readers, existing retrieval tests |
| memorii/memorii/core/memory_plane/service.py | read delegate / implementation | store snapshot -> provider | snapshot/fault/no-write tests |
| memorii/memorii/core/provider/{service,factory}.py | public API/root / implementation | explicit authority -> one snapshot -> release | both roots, compatibility recapture, unit shards |
| memorii/memorii/core/filesystem_storage/bundle.py | additive composition / implementation | library root -> factory with separate authority | filesystem root and unchanged bootstrap tests |
| memorii/memorii/integrations/hermes_provider.py | additive adapter / implementation | explicit trigger -> provider (one non-test caller) | Hermes real constructor and stripped-forwarding tests |
| memorii/pyproject.toml | type scope / implementation | new package -> scoped pyright | full static and package smoke; dependency declarations unchanged |
| memorii/tests/unit/core/test_scoped_context_activation.py | new fast tests / testing plan | request/authority contracts -> generic shards -> timing merge | measured node timings, six shard runs |
| memorii/tests/integration/test_scoped_context_production_binding.py | new exhaustive root tests / testing plan | real roots -> dedicated job -> Unit Tests aggregate | dedicated integration command and measured budget |
| memorii/tests/unit/tools/test_static_tooling_config.py | existing workflow-contract owner / testing plan | exact YAML job/argv/aggregate -> assertion | unit shards, focused structure check |
| memorii/tests/ci/{deterministic-job-owners,unit-test-durations}.json | timing evidence / testing plan | measured tests -> owner budgets/shard assignment | exact collection, no new default timings, merge |
| .github/workflows/pr-gates.yml | dedicated integration job/aggregate / testing plan | pytest target -> job -> Unit Tests result | workflow structure contract; hosted behavior explicitly not local proof |
| docs/development/scoped_memory_context.md | current usage / implementation | approved API -> opt-in usage and limits | code/doc agreement and example review |
| docs/work/scoped_context_implementation/** | operation evidence / coordinator and named reports | baselines -> source/test/gate records -> frozen review -> closure | hashes, ledgers and recorded maturity |

No canonical storage schema, registry, golden vector, ingestion design hash,
event contract, dependency requirement, or existing workflow pin is changed.
Existing pinned source authority chains therefore have zero changed nodes.
Package source fingerprint changes by construction; old live certification is
not reusable and no new provider or agent quality certification is claimed.
Existing ingestion authority/transaction behavior remains unchanged by additive
read-authority forwarding, so exhaustive write-transaction/terminal-persistence
matrices are outside this changed behavior; general old-root tests remain in
required unit shards. Reassess if final diff changes those boundaries.


Corrected candidate adds memorii/tests/unit/tools/test_ctv_binding_authority_pr_gate.py as a testing-plan owned workflow-contract surface. The exact Unit Tests needs/env/success assertion now includes the scoped job. Pins and existing requirements remain intact; dedicated CTV test job and owning unit shard5 are required final gates. All6imported correction files are recorded in imported-correction.json; no other product path changed after initial candidate.
