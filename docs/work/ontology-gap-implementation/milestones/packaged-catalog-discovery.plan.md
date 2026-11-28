# Discover the packaged catalog and recall a fact

- Order: 1. Status: blocked on subject selection. Readiness baseline: `c0fa889a`; approved design and candidate head pending.
- Requirements: OCI-01–04 and partial OLE-08/09/10/14. Parent coverage is unchanged until revision-bound evidence is recorded.
- Dependencies: existing packaged exact read closure, current host read opt-in and verified caller context.

The [linked discovery design](../../learned-ontology/design-packaged-catalog-discovery.plan.md)
owns the unresolved subject authority decision. Hosting an exact recall port
with a canonical subject ID does not establish a subject search contract.

## Execution boundary

Start with an installed bill journey. Bind a discoverable read tool through
the approved transport to the existing protected core. Reuse
`catalog_read_binding.py`, `core/provider/catalog_read_workflow.py`, and
the catalog projection and protected snapshot owners. Confirm both the
Hermes and generic factories use that path. Existing Hermes tool listing
may pin a captured turn. Review the actual host tool hook, listing and
invocation together to avoid requiring captured-turn state or a write grant.

Freeze tool registration, bounded discovery semantics, result ordering and
ambiguity, and the source of verified subject selection first. Section 13
has two exact lookup arms. Preserve those semantics. If discovery extends
lookup or exposes subject search, record the new contract and disclosure
boundaries in the linked design before coding. No persisted mutation or
migration is expected. Existing exact clients retain their response
semantics. Roll back exposure at its host binding.

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
