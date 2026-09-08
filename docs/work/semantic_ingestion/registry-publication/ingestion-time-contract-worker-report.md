# Ingestion-Time Contract Worker Report

- Scope: profile-3 `SourceRetentionTimeAttestation`,
  `TransactionGroupCommitTimeAttestation`, `SourceRetentionTimeWitness`, and
  the closed `ProductionIngestionTimeAttestation` alias.
- Status: complete for this bounded model-construction slice. The parent
  registry-publication milestone remains partial.

## Changed Paths

- `memorii/memorii/core/memory_evolution/graph_ingestion_time_contracts.py`
  adds strict, frozen, extra-forbidden roots with exact SIA fields, SHA-256
  digest lexical checks, Ed25519-hex signature lexical checks, nonempty
  coordinates, UTC datetimes, and the declared transaction chronology.
- `memorii/tests/unit/core/memory_evolution/test_graph_ingestion_time_contracts.py`
  provides valid source/group attestation union cases plus malformed chronology,
  non-UTC time, invalid signature, and unknown-field failures.

## Boundary And Verification

The contracts do not issue timestamps, sign witnesses, validate a profile-3
self-digest, access CAS/storage, expose a public observer route, or claim a
production caller. Those responsibilities remain with the future protected
decoder, signer, and composition owners; no `production_entrypoint_bindings`
update applies.

- Passed: `.venv/bin/ruff check` for both changed Python paths.
- Passed: `.venv/bin/pyright --pythonpath "$PWD/.venv/bin/python"` for both
  paths, with `0 errors, 0 warnings, 0 informations`.
- Passed: `compileall` and `git diff --check`.
- Not run by this worker: pytest, per coordinator ownership.
