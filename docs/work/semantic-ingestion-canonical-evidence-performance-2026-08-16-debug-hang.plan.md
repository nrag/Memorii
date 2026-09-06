# Canonical Evidence Hang Fix

- Work ID: semantic-ingestion-canonical-evidence-performance-debug-hang-2026-08-16
- Work type: debugging
- Status: complete
- Coordinator: Codex
- Created: 2026-08-16
- Last updated: 2026-08-16
- Parent WorkPlan: `docs/work/semantic-ingestion-canonical-evidence-performance-2026-08-15/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic-ingestion-canonical-evidence-performance-2026-08-15/design-review.plan.md`; `docs/work/semantic-ingestion-canonical-evidence-performance-2026-08-15/implementation.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_canonical_evidence_performance.md`; `docs/design/semantic_ingestion_canonical_evidence/performance-run-schema-v1.json`; `docs/design/semantic_ingestion_canonical_evidence/verification-contract-v1.json`; `docs/design/semantic_ingestion_canonical_evidence/event-schema-v1.json`; `docs/design/semantic_ingestion_canonical_evidence/receipt-schema-v1.json`; `docs/design/semantic_ingestion_canonical_evidence/production-entrypoint-bindings-v1.json`; `docs/design/memorii_spec.md`.
- Expected outputs: localized recovery-hang root-cause proof, smallest safe patch on V3 recovery decode paths, and a clear evidence record that hangs now fail fast.

## Objective

Root-cause and mitigate the bootstrap V3 recovery hang observed in `recover_bootstrap_v3_source_normalization`/`validate_bootstrap_v3_reloaded_members` without changing persisted semantics.

## Completion Contract

Complete when:

- the recursive decode path in V3 recovery is proven to fail fast on pathological payloads, 
- changed files are syntax-valid and import-safe,
- no behavior beyond guarded recovery decode boundaries is altered, and
- the parent implementation WorkPlan is updated with final decision/evidence references.

## Scope

Included: typed decoding limits in `decode_typed_value`, bounded recovery contract decoding in V3 bootstrap validation and recovery reload paths, and debug evidence entry.

Excluded: production feature changes, semantic contract shape redesign, or test suite expansion.

## Constraints And Invariants

- Recovery remains fail-closed: malformed or non-canonical member bytes return unavailable/invalid instead of hanging.
- Public bytes and payload digests are unchanged for valid inputs.
- No relaxed schema acceptance is introduced in recovery.

## Findings and Remediation

- Classification: `root cause confirmed`.
- Finding: unbounded typed decode paths in bootstrap V3 recovery/reload could recurse deeply before caller failure, producing hangs.
- Impact: operational recovery path could stall on malformed persisted members.
- Fix implemented:
  - `memorii/memorii/core/memory_evolution/ingestion_contracts.py`: add optional node/depth guard and recursion-safe handling in `decode_typed_value`, with `CanonicalTypedValueError("canonical_typed_value_depth_limit")` on depth overflow.
  - `memorii/memorii/core/semantic_ingestion/contracts.py`: thread optional node/depth hints through `decode_semantic_contract`.
  - `memorii/memorii/core/semantic_ingestion/source_normalization_repository.py`: enforce bounded decoding for all V3 recovered members in both `validate_bootstrap_v3_reloaded_members` and `_validate_bootstrap_v3_member_closure`.
  - `memorii/memorii/core/memory_evolution/atomic_store.py`: use bounded `decode_semantic_contract` in bootstrap reload/replay paths for fixed-depth safety.

## Evidence

- Syntax validation run: `.venv/bin/python -m py_compile memorii/memorii/core/memory_evolution/ingestion_contracts.py memorii/memorii/core/semantic_ingestion/contracts.py memorii/memorii/core/semantic_ingestion/source_normalization_repository.py memorii/memorii/core/memory_evolution/atomic_store.py`
- Depth guard smoke test: `decode_typed_value` returns `CanonicalTypedValueError canonical_typed_value_depth_limit` on deeply nested typed payload.

## Next Action

- Resume implementation-plan-level closure with independent reviewer evidence once replay proof/run command is completed.
