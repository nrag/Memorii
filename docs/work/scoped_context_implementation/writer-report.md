# Scoped Context Writer Report

2026-09-06 construction checkpoint; this bounded slice is **not complete**.

Changed product identities: `core/scoped_context/{contracts,authority,index,service}.py`,
`MemoryPlaneService.read_snapshot`, `EvolutionStateRepository.from_snapshot`,
`ProviderMemoryService.retrieve_context`, and separate authority forwarding in
the provider factory, filesystem root, and Hermes root. Added focused unit
coverage in `memorii/tests/unit/core/test_scoped_context_activation.py`.

Focused proof: `.venv` Python 3.12.14 ran 43 tests successfully in 5.69 seconds
with warnings as errors; changed-path Ruff passed. The existing roots retain
their compatibility tests. Current production `retrieve_context` caller count
is zero, because the new filesystem and Hermes opt-in triggers have no embedding
host invocation. The implementation binding ledger is updated as partial.

Outstanding acceptance work: exact failure algebra, provenance/lifecycle and
all-six-domain eligibility, structured snapshot-only runtime and 18-pair proof,
release-race/restart/exhaustive root tests, dedicated integration CI job and
timing inventory, public current-state usage documentation, and a non-test
production caller with authority. These gaps mean no SMC-R01--R10 requirement
is claimed complete by this checkpoint.

Latest focused command completed successfully with `.venv` Python 3.12.14:
`ruff check` on all changed scoped paths, `pyright --pythonpath` on the changed
production paths (0 errors), then the 43 focused tests in 5.35 seconds.
