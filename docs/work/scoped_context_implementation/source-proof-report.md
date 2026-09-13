# Scoped Context Source And Lifecycle Proof

## Bounded Outcome

The scoped source/lifecycle slice is complete. `ScopedContextAssembler` now
applies typed entity-link half-open validity at the same reference time used
for canonical record lifecycle filtering. The existing common closure retains
the union of canonical and typed evidence source IDs, and structured output
returns the transitive selected-claim source closure from the detached snapshot.

`ProviderMemoryService.retrieve_context` is the canonical production owner.
Both `FilesystemStorageBundle.build_provider_memory_service` and
`HermesMemoryProvider.retrieve_context` call it with the provisioned authority;
that owner invokes `ScopedContextAssembler._assemble_structured` after its
single snapshot read. The binding ledger records this non-test production path.

## Added Or Moved Proof

- `test_real_roots_exclude_invalidated_and_boundary_expired_typed_entity_links`
  proves typed `EntityLinkState.INVALIDATED` and `valid_to == reference_time`
  reject mandatory and optional release for filesystem and Hermes.
- `test_real_roots_require_active_claim_provenance_for_mandatory_and_optional`
  proves an active committed claim with no canonical or typed evidence is
  mandatory-unresolved and produces an optional provenance omission.
- `test_real_roots_emit_typed_and_canonical_evidence_ids_at_utf8_byte_boundary`
  proves sorted evidence-ID union and exact UTF-8 mandatory byte admission.
- `test_real_roots_return_unique_sorted_transitive_structured_source_closure`
  proves selected claim -> canonical semantic source -> raw transcript evidence
  output is unique and sorted through both roots.
- `test_real_roots_answer_current_and_historical_structured_claims_from_evolution`
  moved the prior full-evolution positive from the unit file and proves both
  current and historical structured answers through both roots.

## Verification

From `memorii/`, using repository `.venv` Python 3.12.14:

```text
../.venv/bin/python -W error -m pytest -q \
  tests/unit/core/test_scoped_context_activation.py \
  tests/integration/test_scoped_context_production_binding.py \
  -p no:cacheprovider
70 passed in 16.64s

../.venv/bin/python -m ruff check \
  memorii/core/scoped_context/service.py \
  tests/unit/core/test_scoped_context_activation.py \
  tests/integration/test_scoped_context_production_binding.py
All checks passed!
```

## Limits

This is a bounded local source/lifecycle proof, not completion of the parent
implementation or testing WorkPlans. It does not establish hosted CI,
cross-platform runtime behavior, broader fault-matrix coverage, or final
review approval.
