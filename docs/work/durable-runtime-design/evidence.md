<!-- Current frozen design SHA-256: ec927db8397e567b4087767b11572a5a5ab734bce55137fc4e8655c1d0ed97d2; prior hashes below are review history. -->

# Baseline And Feasibility Evidence

Source HEAD: bad9eeefb43f7f42fb95d583b11859e2f2ca9eb8. Tree has pre-existing user Hermes design edit and prior assessment files; all results are local diagnostic evidence, not clean-tree CI parity.

## Actual Owners

- api/service.py::MemoriiRuntimeAPI.__init__/resume_task/get_state supplies no durable factory; resume reads injected stores.
- core/execution/service.py::RuntimeStepService.step writes nodes, edges, overlay, then events independently (lines 230-238), followed by a result event (281-300).
- stores/execution_graph/store.py, stores/solver_graph/store.py, stores/overlays/store.py, stores/event_log/store.py contain only InMemory implementations.
- core/persistence/replay.py reconstructs some node/edge snapshots only; no overlay/solver ownership/checkpoint recovery.
- core/directory/directory.py owns in-memory task/solver/session relationships.
- core/filesystem_storage/bundle.py contains memory-plane/work-state/decision/trace stores, no execution/solver graph stores. Provider memory durability is not contradicted.
- Hermes composition: integrations/hermes_memory_provider.py -> HermesProviderRuntimeBinding -> HermesMemoryProvider -> ProviderMemoryService; no durable runtime API construction.
- core/provider/service.py accepts optional solver/overlay dependencies; filesystem factory does not construct them.
- core/filesystem_storage/maintenance.py reports soft limits only.

Mapper queries: rg class implementations for ExecutionGraphStore/SolverGraphStore/OverlayStore/EventLogStore, all references to ResumeService/ReplayService/MemoriiRuntimeAPI, directory and factory reads, provider prefetch/tool paths and operator command inventory. Two default read-only agents independently confirmed; coordinator directly read all listed critical owners. Prior Spark role attempts in the assessment failed with unsupported-account model; default agents were used here. No mapping result is implementation proof.

## Baseline Test

Cwd memorii/, command `../.venv/bin/python -W error -m pytest tests/unit/core/test_resume_service.py tests/unit/core/test_replay_service.py tests/integration/test_harness_runtime_integration.py -p no:cacheprovider -q`.

Result: exit 0, 8 passed in 1.12s. These tests resume the same in-memory state. No new regression test or production implementation created.

## SQLite Mechanism Probe

Command `.venv/bin/python docs/work/durable-runtime-design/storage_probe.py`. Result exit 0; Python 3.12.14, SQLite 3.53.4.

| Experiment | Discriminating result |
| --- | --- |
| process exits before transaction commit | 0 event batches, 0 of 5 coupled state rows |
| process exits after commit before acknowledgement | 1 batch, all 5 state rows; durable delivery lookup succeeds |
| writer commits while reader holds snapshot | reader stays on revision 1, new snapshot sees revision 2 |
| SQLite backup API after commit | integrity_check ok, complete revision 2 |

The checked-in probe uses toy SQL rows, not Memorii schemas. It supports selecting SQLite as an atomic primitive; it does not prove power-loss behavior, filesystem trust, authority fencing, production replay, full-installation backup or cross-owner transactions. Implementation must supply those proofs.

## Design Review Readiness

Canonical design owns DUR-01 through DUR-14 acceptance criteria, proposed production entrypoints (zero until implemented), closed event/node shape inventory, authority chain, operations/migration and attack matrix. Existing signed semantic schemas are not changed. Product CI, release signatures, actual-host execution and live benchmark results are not claimed.

First frozen candidate SHA-256: c1f19b8d8340bdeed9b754542e376e1f91caa9aca5626bba80decba513ea2fcb. Three independent standard reviewers inspected this exact document without concurrent canonical edits; consolidated findings are in reviews.md. Relative-link check passed (9 links), requirement inventory passed (14 unique IDs), whitespace check passed.

## Independent Reducer Feasibility

Command `.venv/bin/python docs/work/durable-runtime-design/replay_probe.py` exited 0. Separate incremental and aggregate toy reducers agree for execution/solver/directory/overlay genesis and checkpoint-plus-tail state. Both reject non-identical equal-version records. A failed tail leaves its input checkpoint unchanged. Implementations do not call each other or share state reduction; they share input bytes and a toy JSON digest helper. This proves the proposed independent-reducer test shape is feasible, not agreement of production schema/replay implementations or full family coverage. Production-independent proof must use distinct reducer/control flow and must not import production normalization/replay/materialization; canonical encoded fixtures may be common inputs.

## Revised Candidate Checks

Final-review candidate SHA-256: 061f3ed4dc551fd8472f928cced6372b74a5100afda64e4e04b2212dd102e478. Relative-link check passed (9 links); independently counted unique requirement IDs remain DUR-01 through DUR-14; no trailing whitespace. Six first-cohort conformance families are mapped to their corrections in reviews.md. No additional production tests are claimed for a documentation-only revision. The shell has no unqualified python command; checks used the repository .venv/bin/python.

Current final candidate ec927db8397e567b4087767b11572a5a5ab734bce55137fc4e8655c1d0ed97d2: 9 relative links verified, all 14 unique requirement IDs present, no trailing whitespace. Changed authority surfaces: publication manifest/tuple and read verification; control registry/journal/intents/recovery; authorized generation restore/migration; initial owner bootstrap/genesis; corresponding identity and acceptance inventories. This is design-only conformance; production code and tests unchanged.

Final disposition: complete frozen design approved independently by spec, correctness and test roles; see reviews.md. Final hash rechecked unchanged and current headers agree. git diff --check passed; manual checks also covered the untracked new canonical file. No production implementation or release certification is implied.
