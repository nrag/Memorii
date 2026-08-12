# Provider-Root Delivery Identity CTV Debug

- Work ID: `provider-root-delivery-identity-ctv-debug-2026-08-11`
- Work type: `debugging`
- Status: `active`
- Coordinator: `Codex main thread`
- Created: `2026-08-11`
- Last updated: `2026-08-11`
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/milestones/m3-semantic-pipeline.plan.md`; `docs/work/semantic_ingestion/source-normalization-authority-bundle-2026-08-10/design.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md`; `memorii/memorii/core/memory_evolution/atomic_store.py`; `memorii/memorii/core/memory_evolution/ingestion_contracts.py`; `memorii/memorii/core/memory_evolution/writer_admission.py`; `memorii/tests/unit/core/semantic_ingestion/test_semantic_atomic_store.py`; `memorii/tests/unit/core/semantic_ingestion/test_semantic_provider_composition.py`
- Expected outputs: exact root-cause record for the provider-root bootstrap handoff CTV failure, the smallest invariant-preserving fix, and focused proof that the path reaches the next downstream boundary without broadening generic CTV semantics

## Objective

Remove the deterministic provider-root handoff failure where the V3 bootstrap
marker digest path feeds a live `DeliveryIdentity` model into the closed CTV
encoder before source normalization begins.

## Completion Contract

Complete only after: the exact provider-root failure is reproduced
deterministically; at least two competing hypotheses are recorded; the causal
boundary is proved with a discriminating experiment; the fix is limited to the
V3 handoff marker digest constructor; direct regression proof shows the marker
now lowers typed nested members while the raw encoder still rejects arbitrary
models; and focused pytest, Ruff, `py_compile`, and `git diff --check`
evidence are recorded. Any newly exposed downstream blocker must be named and
kept distinct from the fixed CTV defect.

## Scope

Included: `BootstrapWriterHandoffMarkerV3.create`, its digest preimage
construction, the exact provider-root reproducer, and focused regression
coverage for the typed nested-member family.

Excluded: source-normalization design changes, writer-governance namespace
expansion, provider composition policy decisions, and unrelated M3 public-root
reachability blockers.

## Constraints And Invariants

- Preserve the closed CTV algebra. Raw Pydantic models must remain invalid CTV
  inputs.
- Do not add generic BaseModel coercion to the encoder.
- Do not bypass writer-governance validation or weaken fail-closed behavior.
- Keep the fix local to the digest-preimage constructor unless evidence proves
  the encoder contract itself is wrong.

## Expected And Observed Behavior

Expected: the normal provider root should either continue into the
source-normalization authority decision or fail at a later explicit semantic
gate. Constructing the V3 handoff marker must not crash on its own typed nested
members.

Observed before the fix: the exact provider-root smoke failed in
`BootstrapWriterHandoffMarkerV3.create` when `encode_typed_value(body)` reached
`DeliveryIdentity` and raised
`CanonicalTypedValueError("canonical_value_type_invalid")`. No source
normalization authority decision or terminal behavior was reached.

Classification: `implementation`.

## Reproducer

Exact deterministic reproducer before the fix:

```bash
PYTHONPATH=memorii .venv/bin/python -m pytest memorii/tests/unit/core/semantic_ingestion/test_semantic_provider_composition.py::test_normal_provider_root_without_normalization_authority_is_source_only -p no:cacheprovider
```

Expected signal: the provider root returns the source-only blocked result
asserted by the test.

Observed signal before the fix: the run failed with
`CanonicalTypedValueError("canonical_value_type_invalid")` from
`memorii/memorii/core/memory_evolution/ingestion_contracts.py` while hashing
the V3 bootstrap handoff marker body.

## Hypothesis Ledger

| ID | Hypothesis | Mechanism | Discriminator | Status |
| --- | --- | --- | --- | --- |
| H1 | `BootstrapWriterHandoffMarkerV3.create` hashes the raw `body` dict instead of a model-lowered Python dump. | The raw dict still contains nested `DeliveryIdentity`, `OperationFenceBinding`, and `SemanticWriterCommitBinding` models, which the closed CTV encoder rejects. | Compare the V3 constructor with the legacy V1 marker constructor and prove that `model_construct(...).model_dump(mode="python")` yields an encodable body while the raw dict does not. | confirmed |
| H2 | The CTV encoder contract is wrong and should recursively accept arbitrary Pydantic models. | If true, both the raw `DeliveryIdentity` and the raw V3 body should be valid CTV inputs, and the V1/V3 constructor difference would be incidental. | Call `encode_typed_value` directly on a raw `DeliveryIdentity`, on a raw dict containing it, and on the fully lowered Python dump. If only the lowered form encodes, the encoder contract is behaving correctly and the bug is the skipped lowering step. | disproved |

## Experiment Log

1. Direct encoder experiment:
   - Raw `DeliveryIdentity` -> `CanonicalTypedValueError("canonical_value_type_invalid")`
   - Raw `{"delivery_identity": identity}` -> same failure
   - Lowered `identity.model_dump(mode="python")` -> encodes successfully
2. Constructor-shape comparison:
   - `BootstrapWriterHandoffMarker.create` already uses
     `model_construct(...).model_dump(mode="python")` before hashing.
   - `BootstrapWriterHandoffMarkerV3.create` alone hashed the raw `body`.
3. Post-fix provider smoke:
   - The exact provider-root reproducer no longer fails in the CTV encoder.
   - The same smoke now reaches writer-governance and fails later with
     `SemanticWriterAdmissionError("unknown semantic control namespace is forbidden")`.

## Causal Chain And Correction

1. The provider root calls `bootstrap_writer_handoff`, which constructs a V3
   handoff marker.
2. `BootstrapWriterHandoffMarkerV3.create` built a raw `body` dict containing
   nested typed models and passed it directly to `encode_typed_value`.
3. The closed CTV encoder correctly rejects arbitrary model instances, so the
   hash preimage construction crashed before any source-normalization authority
   work could begin.
4. The legacy V1 marker constructor already solved this exact shape problem by
   lowering the body through the model before hashing.
5. The smallest safe fix is to make the V3 constructor use the same
   model-lowered Python dump before hashing. This removes the skipped-lowering
   defect without weakening the CTV encoder.

## Focused Evidence

- Direct regression proof:
  - `PYTHONPATH=memorii .venv/bin/python -m pytest memorii/tests/unit/core/semantic_ingestion/test_semantic_atomic_store.py -k 'ctv_encoder_still_rejects_raw_delivery_identity_models or bootstrap_writer_handoff_marker_v3_create_lowers_typed_nested_members' -p no:cacheprovider`
    passed `2` tests in `4.16s`.
- Integration-edge proof:
  - `PYTHONPATH=memorii .venv/bin/python -m pytest memorii/tests/unit/core/semantic_ingestion/test_semantic_provider_composition.py::test_normal_provider_root_without_normalization_authority_is_source_only -p no:cacheprovider`
    no longer fails in `encode_typed_value`; it now fails later with
    `SemanticWriterAdmissionError("unknown semantic control namespace is forbidden")`
    in `writer_admission.py`.
- Static hygiene:
  - `PYTHONPATH=memorii .venv/bin/python -m ruff check memorii/memorii/core/memory_evolution/atomic_store.py memorii/tests/unit/core/semantic_ingestion/test_semantic_atomic_store.py`
    passed.
  - `PYTHONPATH=memorii .venv/bin/python -m py_compile memorii/memorii/core/memory_evolution/atomic_store.py memorii/tests/unit/core/semantic_ingestion/test_semantic_atomic_store.py`
    passed.
  - `git diff --check -- memorii/memorii/core/memory_evolution/atomic_store.py memorii/tests/unit/core/semantic_ingestion/test_semantic_atomic_store.py`
    passed.

## Residual Risk And Follow-Up

- Residual risk: the provider-root path still does not complete. The next
  blocker is no longer a CTV crash; it is writer-governance rejecting the
  newly reached control write as an unknown semantic control namespace.
- This downstream blocker is a distinct implementation boundary. It should be
  handled as a separate M3 fix or debug slice rather than folded into this CTV
  correction.

## 2026-08-11 Follow-On: Bootstrap Recovery Writer-Governance Closure

### Expected And Observed Behavior

Expected after the CTV fix: the same provider-root smoke should either return
the source-only blocked result asserted by the test or fail at a later
explicit source-normalization authority gate. The bootstrap handoff write must
admit the new V3 recovery record without weakening unknown-namespace
rejection.

Observed before this follow-on fix: the exact provider-root smoke failed in
`SemanticGovernedWritePolicy.validate` with
`SemanticWriterAdmissionError("unknown semantic control namespace is forbidden")`.
The write set now included a legitimate
`semantic_ingestion_bootstrap_v3_recovery_index` control record introduced by
the V3 handoff path.

Classification: `implementation`.

### Reproducer

Exact deterministic reproducer before the follow-on fix:

```bash
PYTHONPATH=memorii .venv/bin/python -m pytest memorii/tests/unit/core/semantic_ingestion/test_semantic_provider_composition.py::test_normal_provider_root_without_normalization_authority_is_source_only -p no:cacheprovider
```

Expected signal: the provider root returns the source-only blocked result
asserted by the test.

Observed signal before the follow-on fix: the run failed with
`SemanticWriterAdmissionError("unknown semantic control namespace is forbidden")`
from `memorii/memorii/core/memory_evolution/writer_admission.py`.

### Hypothesis Ledger

| ID | Hypothesis | Mechanism | Discriminator | Status |
| --- | --- | --- | --- | --- |
| H3 | The V3 bootstrap recovery index was never registered in the semantic-control classifier. | The governed write contains a valid new recovery record, but `semantic_control_class` returns `unknown`, so writer admission rejects it before any handoff-specific validation runs. | Classify the exact bootstrap recovery and sibling source-normalization recovery coordinates directly. If they return `unknown`, the registry is incomplete. | confirmed |
| H4 | The classifier miss is the only problem. | If true, an in-memory-only registry patch should let the provider-root smoke pass. | Patch the registry in-memory only and rerun the provider-root smoke. If a second writer-admission error appears, the bootstrap handoff validator is still enforcing the old shape. | disproved |

### Experiment Log

1. Direct classifier experiment:
   - `semantic_ingestion_bootstrap_handoff_marker` -> `operation`
   - `semantic_ingestion_bootstrap_v3_recovery_index` ->
     `unknown` before the fix
   - `semantic_ingestion_source_normalization_recovery_index` ->
     `unknown` before the fix
2. In-memory registry patch experiment:
   - After temporarily classifying both recovery indices as `recovery`, the
     same provider-root smoke no longer failed at the unknown-namespace gate.
   - The same smoke then failed later with
     `SemanticWriterAdmissionError("atomic admission generation membership is incomplete")`.
3. Handoff validator inspection:
   - `_is_bootstrap_handoff_write` still accepted only the old 5-record
     marker-plus-control shape.
   - The V3 path now writes 6 governed records: one control record, three
     preplanning artifacts, one bootstrap handoff marker, and one bootstrap
     V3 recovery index.

### Causal Chain And Correction

1. The CTV fix allowed the normal provider root to reach writer admission for
   the first V3 bootstrap handoff write.
2. That write now legitimately includes the new
   `semantic_ingestion_bootstrap_v3_recovery_index` record.
3. The semantic-control classifier did not register either the bootstrap V3
   recovery index or the sibling source-normalization recovery index, so
   writer admission classified the bootstrap record as `unknown` and rejected
   the batch.
4. Even with the registry patched, writer admission still enforced the legacy
   5-record bootstrap handoff shape and misrouted the new recovery record into
   atomic-admission validation.
5. The smallest safe fix is twofold:
   - register the exact new recovery source kinds and ID prefixes as
     `recovery`; and
   - update `_is_bootstrap_handoff_write` to require the exact V3 6-record
     shape, including the unclaimed recovery record bound to the marker's
     recovery key and the control generation.

This preserves fail-closed rejection for unknown namespaces and for malformed
or mismatched bootstrap recovery records.

### Focused Evidence

- Writer-governance boundary proof:
  - `PYTHONPATH=memorii .venv/bin/python -m pytest memorii/tests/unit/core/semantic_ingestion/test_semantic_writer_admission.py -k 'recovery_indices_are_classified_as_recovery_namespaces or mismatched_bootstrap_recovery_namespace_stays_unknown or every_semantic_control_source_and_namespace_rejects_direct_cas' -p no:cacheprovider`
    passed `92` selected tests in `4.87s`.
- Provider normal-path proof:
  - `PYTHONPATH=memorii .venv/bin/python -m pytest memorii/tests/unit/core/semantic_ingestion/test_semantic_provider_composition.py::test_normal_provider_root_without_normalization_authority_is_source_only -p no:cacheprovider`
    passed `1` test in `12.46s`.
- Static hygiene:
  - `PYTHONPATH=memorii .venv/bin/python -m ruff check memorii/memorii/core/memory_plane/semantic_control.py memorii/memorii/core/memory_evolution/writer_admission.py memorii/tests/unit/core/semantic_ingestion/test_semantic_writer_admission.py`
    passed.
  - `PYTHONPATH=memorii .venv/bin/python -m py_compile memorii/memorii/core/memory_plane/semantic_control.py memorii/memorii/core/memory_evolution/writer_admission.py memorii/tests/unit/core/semantic_ingestion/test_semantic_writer_admission.py`
    passed.
  - `git diff --check -- memorii/memorii/core/memory_plane/semantic_control.py memorii/memorii/core/memory_evolution/writer_admission.py memorii/tests/unit/core/semantic_ingestion/test_semantic_writer_admission.py`
    passed.

### Residual Risk

- The exact normal provider-root smoke now passes and reaches its expected
  source-only outcome.
- The sibling
  `semantic_ingestion_source_normalization_recovery_index` namespace is now
  correctly classified, but this debug slice did not exercise its later
  generation-write admission path. Any future failure there is a distinct
  downstream boundary.

## Exact Next Action

Have the coordinator reconcile this writer-governance closure into the M3
milestone state and continue the remaining public-root and source-normalization
implementation blockers. This exact provider-root bootstrap handoff path no
longer needs a separate debug slice.
