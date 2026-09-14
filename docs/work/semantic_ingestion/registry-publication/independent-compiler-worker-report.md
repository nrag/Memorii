# Independent Compiler Worker Report

- Scope: new `acceptance/observation_registry_compiler.py` and its isolated
  unit tests only.
- Inputs: `docs/design/semantic_ingestion_observation.md` and raw files under
  `memorii/memorii/core/memory_evolution/observation_registry_sources` only.
- Implementation: independent strict raw JSON intake, role/type/policy/DAG
  validation, exact LP/SHA-256 profile-to-registry derivation, optional source,
  decoder-source, and publication manifest checks, and immutable reports that
  retain source identities and complete preimage bytes.
- Current package status: the observed source tree has grammar/schema/policy
  roles and all 179 null-only upcast roles. The 179 decoder roles, registry
  role, decoder-source manifest and publication manifest are not yet produced,
  so the package is expected to reject as incomplete. No parity or
  runtime-publication claim is made by this worker.
- Verification: `.venv/bin/python -m py_compile
  acceptance/observation_registry_compiler.py
  memorii/tests/unit/acceptance/test_observation_registry_compiler.py`,
  `.venv/bin/ruff check acceptance/observation_registry_compiler.py
  memorii/tests/unit/acceptance/test_observation_registry_compiler.py`, and
  `.venv/bin/pyright --pythonpath .venv/bin/python
  acceptance/observation_registry_compiler.py
  memorii/tests/unit/acceptance/test_observation_registry_compiler.py` passed.
  The worker did not run pytest or parity commands; root owns those processes.
- Correction: no separate source-role manifest API or invented schema remains.
  The compiler accepts only raw roles plus the normative decoder-source and
  publication manifests.
- Completion correction: `compile_observation_registry` now requires the
  registry role. `derive_observation_registry` is the separate, explicitly
  non-verifying authoring derivation path. Admission compares the complete
  literal grammar, enforces protected positive raw-byte/node/depth limits,
  validates optional row shapes and numeric owner/representation/bound rules,
  and caps decoder-source reads with the same protected raw-byte limit.
- Added discriminating unit families for literal grammar mutation, missing
  registry, extra optional field, numeric owner/representation/inverted bounds,
  and protected limits. These are construction tests only; root owns pytest and
  independent parity closure.
