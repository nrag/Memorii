# Observation Public Contract Worker Report

- Scope: remaining profile-3 public observation body roots in
  `graph_observation_public_contracts.py` only.
- Status: complete for this bounded schema slice; registry publication and its
  parent milestone remain partial.

## Delivered

- Strict, frozen, extra-forbidden profile-3 context, authorization-decision,
  and page-policy bodies. They deliberately defer registered self-digest
  verification and do not inherit legacy digest logic.
- Cursor-free request-coordinate models, corresponding request models with
  cursor, purpose-specific graph/ingestion snapshot models, closed snapshot and
  response aliases, and graph/ingestion page bodies.
- Snapshot and page coordinate checks join profile-3 cohort revisions/write
  revisions, authorization decisions, request revisions/selectors,
  preimage/resolved cohort bodies, stream positions, and schema fingerprint
  where declared. The authenticated context digest remains a retained model
  coordinate; a future runtime authorizer owns its context join.
  Page bodies also require the declared canonical record/attestation order and
  do not exceed their total page size; snapshots require complete graph stream
  key coverage or unique canonical attestation ordering.
- Feature-local tests construct joined profile-3 graph snapshot/page and
  ingestion-time page cases, then reject bad write revisions, page positions,
  purpose-era schema-version booleans, and cohort revisions.

## Boundary And Verification

No authorizer, provider service, token/cursor wire, signer, decoder, paging
implementation, or persistence behavior was added. The existing v1 foundation
and cursor modules are imported only for approved selector/failure reuse and
remain unchanged. No `production_entrypoint_bindings` update applies.

- Passed: `.venv/bin/ruff check` for the module and feature-local test.
- Passed: `.venv/bin/pyright --pythonpath "$PWD/.venv/bin/python"` with
  `0 errors, 0 warnings, 0 informations`.
- Passed: `compileall` and `git diff --check`.
- Not run by this worker: pytest, per coordinator ownership.
