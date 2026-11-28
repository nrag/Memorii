# Discover the packaged catalog and recall a fact

- Order: 1. Status: verification pending. Readiness baseline: `c0fa889a`; design commit `326a8b6c`; pushed candidate `665319c0e44fcedd848c3f6ce8e8a5b2f19b3df1`.
- Requirements: OCI-01–04 and partial OLE-08/09/10/14. Parent coverage is unchanged until revision-bound evidence is recorded.
- Dependencies: existing packaged exact read closure, current host read opt-in and verified caller context.

The [linked discovery design](../../learned-ontology/design-packaged-catalog-discovery.plan.md)
passed targeted design and validation review. The host supplies the verified
subject. Otherwise use unresolved recall for clarification.

## Execution boundary

Start with an installed bill journey. Bind a discoverable read tool through
the approved transport to the existing protected core. Reuse
`catalog_read_binding.py`, `core/provider/catalog_read_workflow.py`, and
the catalog projection and protected snapshot owners. Confirm both the
Hermes and generic factories use that path. Existing Hermes tool listing
may pin a captured turn. Review the actual host tool hook, listing and
invocation together to avoid requiring captured-turn state or a write grant.

Section 13 freezes identical host-neutral browse, inspect and recall tool
schemas for both bindings, a separate 16-descriptor page and version-bound
cursor, and unchanged exact lookup rules. Use dedicated pure listing and
read dispatch. Existing exact clients and captured-turn writer tools
retain their response and authorization semantics. No persisted mutation
or migration is expected. Roll back exposure at its host binding.

## Acceptance and verification

- From a signed-in host's actual tool list, discover the bill relation and
  recall a provisioned date using a verified subject and the inspected digest.
  Repeat through both bindings after reopen with no credentials, model,
  network, write-tool grant or completed turn. Compare state or instrument
  dispatch to detect reads that pin, retain or write anything.
- In a work journey, clarify an ambiguous owner relation. Missing or
  unauthorized subject, denied account and stale catalog produce the
  contract statuses without values or protected counts. Verify current
  release grants and that catalog inspection never invokes the fact reader.
- Keep exact ID, normalized label/alias, ambiguity, empty and invalid input
  regressions. Exercise installed registration and package smoke to catch an
  implementation whose Python methods exist but have no agent-facing caller.

From `memorii/` using the index toolchain:

```sh
python -W error -m pytest -q -p no:cacheprovider \
  tests/unit/core/semantic_ingestion/test_catalog_inspection.py \
  tests/unit/core/semantic_ingestion/test_catalog_read_workflow.py \
  tests/integration/test_scoped_context_production_binding.py
```

Close with both real tool journeys, current applicable gates and a focused
test and scope review. Add the new tool registration paths to the binding
and identity ledgers at implementation. Agent tool-choice quality is
recorded separately from the deterministic installed acceptance.

## Delegation and evidence

- `catalog_tool_design_review` (Terra, read-only) verified the scoped tool,
  paging, authority and validation design. Closed without findings.
- `catalog_discovery_writer` (Terra, sole runtime and test writer) owns
  shared read workflow and host adapter changes plus focused verification.
- Coordinator ran 7 exact inspection and diagnosis unit tests on the
  readiness baseline with macOS Python 3.12.16 and warnings as errors.
  All passed. The larger baseline run passed those plus two composition
  checks. It was interrupted during installed fact provisioning when the
  candidate's own run superseded it. No baseline installed pass or failure
  is inferred.
- Code-readiness review identified the existing Hermes function envelope
  and always-composed read binding. A reviewed design clarification pins
  the original envelope and limits static advertisement to configured
  read opt-in. Runtime invocation rechecks live grants independently.
- The writer implemented both installed read-tool surfaces and regression
  coverage. Coordinator ran the two focused unit modules from `memorii/`
  on Python 3.12.16 with warnings as errors. **8 passed**. Repository Ruff,
  Pyright (0 errors, warnings or information), and the field-aware identity
  gate passed. `python -m memorii.tools.test_shards verify --config
  tests/ci/unit-shards.json` collected 5,340 unit tests across six shards.
  This establishes ownership and collection on the local toolchain.
- The targeted correctness reviewer checked the frozen protected authority,
  stale cursor, no fact read, registration and captured-tool compatibility
  code, with no P1/P2 findings. Final installed evidence and hosted gates
  are pending. The initial installed command started before the last
  fixture tripwire edit, so use the final hosted candidate for that check.
- The candidate was pushed to `origin/codex/durable-delivery-implementation`.
  [Candidate PR run](https://github.com/nrag/Memorii/actions/runs/46094271168)
  started after the candidate push. The exact installed witness passed
  locally from the same candidate (1 passed in 333.67 seconds, Python
  3.12.16 with warnings as errors). It exercised all 56 descriptors,
  bill and work recall through both installed tool hooks, absent subject,
  stale and malformed pagination, scope withdrawal and no browse fact
  query or durable read-time mutation. The existing optional Hermes ABI
  stand-in was used for the deterministic test. An isolated archive build using Python
  3.11 `pip wheel --no-deps --no-build-isolation` and an isolated install
  successfully loaded all three advertised tool schemas from the wheel
  under Python 3.12. This is a focused packaging check.
- The other 145 tests in `test_scoped_context_production_binding.py` passed,
  giving 146 passed across the two disjoint local commands. The legacy
  uninitialized bridge and no-key captured-turn tool-list regressions
  passed (2 tests). All used warnings as errors on Python 3.12.16.
- The candidate wheel also passed the installed work and bill witness in
  the local Linux Hermes rehearsal image with `--network none` (1 passed
  in 277.17 seconds). An ephemeral copy of the test imported the real
  `agent.memory_provider` instead of installing the optional ABI stand-in.
  The test verified that Memorii imports came from the extracted candidate
  wheel, with test provisioning in a disposable container. This verifies
  the tool hooks through the real ABI. Agent tool-choice quality was not
  measured.
- A subsequent probe against the same wheel and Linux image reproduced
  a stock-host routing defect. Hermes `agent/agent_init.py:1303` calls
  `MemoryManager.add_provider` before `initialize_all`. The manager
  populates `_tool_to_provider` from the initial schemas and does not
  refresh it after initialize. In the probe, the provider emitted the
  three configured schemas after registration, but
  `manager.has_tool("memorii_browse_catalog")` was false. Stock init also
  does not supply `catalog_read_opt_in`. The passing witness exercises
  configured provider hooks and the real ABI, which do not establish stock
  agent routing. This is a P2 for stock-host manual testing. Ask whether
  stock operator setup and routing are required in this milestone.

## Stock Hermes scope

The user approved stock Hermes support and assigned the separate storage
fix to parallel v8 work. The reviewed stock design uses a process-level
opt-in, pre-initialization schemas and existing grants. The stock writer
owns only the Hermes and shared read binding code and focused tests.
The offline installed witness must exercise the actual Hermes manager
and include an absent optional raw user ID, current grants, and removal
of the opt-in. Configured-host scope and tests carry forward.

The stock candidate checks the same literal opt-in before initialization,
at authenticated invocation, and at release. The registered tools
respond through the stock Hermes JSON dispatch ABI. The independent
review confirmed the exact scope and grant references and surfaced two
input/timing cases. The candidate now rejects a malformed supplied user ID
and returns JSON denial for a cached route after opt-in withdrawal before
initialization. Both cases are covered in the integration fixture.
The focused unit run passed 10 tests. Scoped Ruff and clean candidate
Pyright passed. The actual router and candidate gates remain in progress.

## Package Smoke repair

The [linked debugging WorkPlan](../debug-release-proof-members.plan.md)
owns the stale release member hashes and their CI verification.
Package Smoke passed on PR #126 at `8825330d`. The stock implementation
will refresh any changed proof members before pushing its own gate run.

## Changed surfaces and gate ledger

| Surface and identity | Path and authority | Evidence |
| --- | --- | --- |
| `CatalogBrowseRequest`, `CatalogBrowseResponse`, `listed`, version and cursor | `core/semantic_ingestion/catalog_inspection.py` owns the grammar. `core/provider/catalog_read_workflow.py` owns authorization, complete declaration projection, version-matched paging and release in the existing read snapshot. | Contract tests and shared read suite pass. Installed stale/invalid, full paging and release proof pending. |
| Three reviewed tool names, function schema and dispatch | `hermes_factory.py` → `catalog_read_binding.py` → provider service → protected workflow. Hermes `get_tool_schemas` retains legacy ordering and routes known reads directly. Generic `get_read_tool_schemas` and `handle_read_tool_call` use the same binding. | Installed bridge/generic integration uses provisioned bill and work subjects and the real factory bindings. No new manifest, authority or storage bytes. |
| Focused existing tests | `test_catalog_inspection.py` covers paired cursor and schema. `test_scoped_context_production_binding.py` exercises both installed endpoints, reopen, no fact reads on browse, no writes and withdrawn grant. | Unit pass. Candidate revision needs the installed job. |

Use `.github/workflows/pr-gates.yml` from candidate SHA. Static Analysis
runs repo Ruff, Pyright and identity hygiene. Package Smoke runs the
installed wheel/preparation checks. Scoped Context Integration runs the
full installed module. Unit Test Shards and Unit Timing Inventory prove
compatibility and count ownership. Unit Tests aggregates all of its
required jobs. Record actual PR #126 run and tested merge SHA separately
from candidate head. Keep the manual work and household witness results
and `remaining_validated_p1_p2` in the closure record.
