# Design Evidence And Review

Design baseline 63f90df2a4e822df430c32b209f03a671379189bc8e999e19d7f12ac5fbf94fe. Code baseline 4c390de14d63fd1e13961e77bcca2f6b82f693f5. The README and implementation plan already had local changes. This operation owns the canonical design and this directory only.

## Direct Code Map

- Installed memorii-consume constructs RuntimeCommandService. Dispatch invokes publish_runtime_change and persists a work projection containing a digest rather than payload bytes. deliver_outbox invokes a supplied callback in a raw write transaction, and only tests call it.
- Consolidator.from_solver_resolution is called by RuntimeStepService. The abstraction and user-finding methods lack installed callers and expect trusted booleans. MemoryDomain has no skill value. The new spec explicitly provides separate skill-candidate storage and defines input evidence instead of making these facts invisible.
- ProviderMemoryService.sync_event and WorkStateMemoryProjector own native capture and provider-event projection respectively. WorkStateService, managed recall, provider candidate staging, RuntimeSidecar, the spool and Hermes task binding are insertion points, not existing delivery endpoints.
- StorageAdministrationService.publish_memory_plane_batch already uses publication fence and in-transaction memory-plane schema and authority validation. publish_runtime_change signs runtime batches. The target design requires one new coordinated transaction using both owner seams where applicable. The managed worker receives no raw database handle.
- Existing backup includes the signed partition state. Existing operator restore supports generation changes. GrantEpochRegistry's independent epoch lookup/lock does not itself serialize grant mutation with target commit. Enrollment and generation/grant revalidation must be connected to the actual control owner.

## Mechanism Checks

Run from root with python3 docs/work/durable-delivery-design/delivery_mechanism_probe.py. SQLite 3.54.0. All three induced pre-commit SQL rollback cuts left no target effect/receipt and a pending claim. Committed reopen observed effect and receipt together with terminal queue state. An older backup lacked the later receipt. This is a SQL primitive demonstration. It does not validate the signed control protocol, process-crash behavior, independent target systems, performance or existing production writer safety.

Distribution arithmetic verified both 200-task distributions hit 10,000 execution and 50,000 solver nodes. After nodes and specified structural edges, 24,000 balanced and 24,090 concentrated runtime event slots remained for setup, typed state revisions and tail. Every task has space for its assigned source references. The 4,096 source-body allocation gives exactly 1 GiB, and a 256 KiB ASCII hex body was generated as specified. The full generator and performance acceptance remain unimplemented.

## Alternatives And Accepted Boundaries

The old callback relay could support external targets, but nothing in release scope requires distributed writes. It cannot safely provide an atomic effect and receipt via the current string callback. Reuse same-partition ownership and signed publication. Treat normal native ingest, managed work projections and explicitly accepted candidate staging as separate authorities. Use a hold rather than assume all pre-restore outcomes remain knowable. The standalone archive ref preserves the required output without automatically performing destructive retention or creating a memory fact.

## Independent Review Ledger

First candidate 5a43c6c6a6c280b8fa8793e5e770adcc54ce0d2efb05d0249d9fd0fbb596fcc8. Spec confirmed real closed-domain mismatch for skill and missing producer evidence. Correctness confirmed old queued intents could be rebound after restore. Test reviewer approved capacity and result/receipt proof families. Coordinator confirmed these are contract-conformance issues and scoped one batch: protected skill catalog, verified producer evidence and omission, and authenticated generation-bound origin proof across prepare/embedded/HTTP/spool. No policy or product ambiguity requires owner input.

Second candidate d5d5e211bed6ee6a6f8e2d1d49538c522879d42edd12b2c335dd7e48f3677df1. Whole-design review completed. Correctness and test reviewers approved. Spec confirmed two determinate clarifications: return exact decision selectors from the read operation, and bind a closed target scope separating skill from memory-plane domains.

Final candidate a51ec4e02a62b05a5b28dc2afed146263a56b125ac2bae8f9abbaf22cbb4f9f2. Targeted recheck by all three roles confirmed both clarifications and carried forward the final whole-design conclusions. Spec, correctness and test approved the frozen delivery scope. No remaining validated required design finding from the regrade. No product implementation or operational evidence is inferred from those approvals.

Coverage cross-check: DREV-001 closes in the per-output table, typed producer evidence and ordinals; DREV-002 in the read/decision interface and offer selectors; DREV-003 in closed target scope, current owner authorization, signed atomic effect/receipt/terminal state and installed proof; DREV-004 in generation-bound origin and restore hold/reconciliation cases; DREV-005 in the reference workload, sampling protocol and platform-bound artifacts. Required downstream changes include closed type and event registries, SQL catalog and checkpoint manifests, canonical digest fixtures, OpenAPI/client schemas and installed tests. The design names these artifacts and binds them to acceptance. Generated outputs and live source-kind inventories are implementation work. No existing semantic event format or benchmark policy is changed.

Final local checks: canonical SHA, all 18 requirement IDs, relative links and git diff --check passed. The SQLite probe passed on the preserved script. Full reference capacity, replay, installed worker and release checks are still due during implementation.
