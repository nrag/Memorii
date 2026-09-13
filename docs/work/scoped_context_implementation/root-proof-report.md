# Scoped Context Root Proof

## Covered Production Chains

`FilesystemStorageBundle.build_provider_memory_service` and
`HermesMemoryProvider.retrieve_context` both reach
`ProviderMemoryService.retrieve_context` with the injected
`ScopedHostReadAuthority`. The factory composition is exercised directly for
authority absence. All three deny without authority and do not use `prefetch`
or another live-reader fallback.

The real-root suite proves one snapshot read for request-local optional
selection, typed backend/decode translation to `UNAVAILABLE`, and no write by
the scoped read path. The snapshot mutation test writes only from its test
callback after capture, proving the returned activation remains based on the
captured clone.

## Command

From `memorii/` on 2026-09-06:

`../.venv/bin/python -W error -m pytest -q tests/integration/test_scoped_context_production_binding.py -p no:cacheprovider --durations=20`

Result: 109 passed in 17.61 seconds.

## Bounded Corrections

`ScopedContextAssembler` now filters to committed, runtime-visible authorized
records before decoding owned payloads. It also excludes generic typed
nonclaim current records with no `valid_from`; transcript and committed plain
context retain the explicit design exception. Both corrections are covered by
Filesystem and Hermes integration cases.

This is root-test evidence only. The coordinator owns updates to the canonical
production-entrypoint binding ledger and broader completion reconciliation.
