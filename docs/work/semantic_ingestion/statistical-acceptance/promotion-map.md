# Statistical Acceptance Canonical-Promotion Impact Map

This is a read-only impact map for a future design promotion. It does not
approve a schema, select a policy value, change generated authority, or claim
runtime availability.

## Semantic Boundary

The current architecture has one schema-owned decimal wrapper,
`CanonicalDecimalQuantity`, at `docs/design/semantic_ingestion_architecture.md`
lines 2730-2732 and 2807-2815. Its `encoding_spec_id` is supposed to select
the exact scale, range, unit, and `reject_inexact` behavior. Policy values
therefore remain decimal quantities: in particular the threshold, nominal
alpha, lower/upper cluster range, and family-wise alpha in
`CertificationMetricGate`/`CapabilityStatisticalGateManifest` (32469-32494),
and monitoring policy thresholds, alpha budgets, and declared ranges
(32645-32672).

Computed values must not be silently rounded back into those policy fields.
The promotion needs distinct exact-point and outward rational-enclosure schema
types for computed p-values, confidence bounds, estimates, and spent alpha.
The immediately affected declared result fields are
`MonitoringMetricDecision.estimate`, `.lower_bound`, `.upper_bound`, and
`.alpha_spent` (32676-32683). Any new statistical certificate/result model
must carry the same split explicitly. Replacing every `CanonicalDecimalQuantity`
would be wrong: it would remove the exact-policy input boundary rather than
repair computed-result representation.

The existing prose names a numeric encoding-spec registry digest but supplies
only a structural component marker, not a machine-readable list of field
specifications. The six component source objects at 11620-11650 bind the policy
string `exact_field_constraints_and_no_ambient_numeric_default`; they do not
choose `encoding_spec_id`, scale, range, unit, or rounding for any field. A
promotion must add the missing policy-encoding authority as a separately
approved source and bind it to the appropriate schemas. It cannot infer values
from current CTV inventory, implementation defaults, a fixture, or held-out
evidence.

## Actual Authority Chain

| Surface | Exact owner and effect of promotion | Required follow-on |
| --- | --- | --- |
| Normative declarations | `docs/design/semantic_ingestion_architecture.md`: canonical numeric wrapper (2730-2815), current CTV profile/registry contract (2714-2725 and 11600-11690), statistical gate schema (32469-32494), and monitoring result schema (32645-32683). | Declare rational point/enclosure and policy/evidence kernel contracts; preserve decimal policy fields; add the exact field-policy encoding source and no-tolerance comparison rules. |
| CTV source compiler | `memorii/memorii/tools/semantic_ingestion_ctv_reference_compiler.py`. It parses only the marked architecture grammar, enum registry, schema inventory, and static Python fences, then derives the profile/binding authority. | Update only after the normative declarations are frozen. The compiler discovers declared roots/transitive types; it does not invent a numeric field policy. |
| CTV authority | `docs/design/semantic_ingestion/traceability_golden_vectors/ctv-binding-authority-v2.json`, validated by `validate_ctv_binding_authority_v2.py` and independently checked by `check_ctv_binding_authority_v2.py`. | Regenerate its grammar/enum/profile/schema fingerprints and every binding affected by a changed declared field or new top-level root. A changed inventory requires a profile-registry version under the architecture rule at 11612-11618. |
| CTV regression proof | `memorii/tests/unit/tools/test_semantic_ingestion_ctv_reference_compiler.py` and `memorii/tests/unit/tools/test_ctv_binding_authority_pr_gate.py`; the latter also pins workflow arguments. | Add exact point/enclosure vectors plus malformed, reversed, noncanonical, unknown-tag, and field-substitution mutations. Re-pin only hashes produced by the frozen authority; do not relax expected hash/count assertions. |
| Registry and structural closure | `docs/design/semantic_ingestion/traceability_registry/registry-v1.json`, `docs/design/semantic_ingestion/traceability_golden_vectors/structural_manifest_derivation_ledger-v1.json`, and `check_cgs_structural_contract_v1.py`. | Add/update the registry rows, schema inventory/closure claims, dependency DAG, structural manifest ledger, and attack cases for every new top-level schema or changed declared root. Existing 56-root expectations are explicit, not automatically safe to retain. |
| Golden/scenario evidence | `recipe-v1.json`, `scenario-first-v1.json`, `run_scenario_ingress.py`, `elaborate_scenario_a.py`, `elaborate_scenario_b.py`, `validate_recipe.py`, and `validate_scenario_manifest.py`. | Regenerate only after CTV authority and structural closure are coherent; update source digest pins and typed fixtures where changed schemas are represented. Both elaborators and the manifest validator must agree. |
| Signed release closure | `memorii/memorii/tools/semantic_ingestion_traceability_manifest.py`, `semantic_ingestion_traceability_release.py`, release signing/verifier tools, and the generation manifest/release/pointer artifacts. | A changed design, registry, CTV authority, structural manifest, golden manifest, or test/result artifact changes their raw/member digests and must flow through a new signed approval generation. No existing release/pointer or signature is reusable. |

## Automatic Versus Explicit Work

The compiler automatically derives fingerprints from declared static schema
fences and the closed 56-root inventory. It does **not** automatically decide
which numeric fields are policy inputs, which are computed evidence, their
units/scales/ranges, a rational enclosure grammar, or whether a field can
change from decimal to enclosure. Those are explicit normative declarations
and an approved numeric-encoding authority. The CTV component digest alone is
not evidence that a field-level policy registry exists.

## Finite Promotion Checks

After a frozen design and explicit field-policy authority exist, run these
bounded checks with newly computed hashes (never copied from this map):

```text
python3.12 -I docs/design/semantic_ingestion/traceability_golden_vectors/check_ctv_binding_authority_v2.py --design docs/design/semantic_ingestion_architecture.md --registry docs/design/semantic_ingestion/traceability_registry/registry-v1.json --authority docs/design/semantic_ingestion/traceability_golden_vectors/ctv-binding-authority-v2.json --validator docs/design/semantic_ingestion/traceability_golden_vectors/validate_ctv_binding_authority_v2.py --expected-design-sha256 <new> --expected-registry-sha256 <new> --expected-authority-sha256 <new> --expected-validator-sha256 <new> --expected-checker-sha256 <new>
PYTHONPATH=memorii .venv/bin/python -m pytest -W error memorii/tests/unit/tools/test_semantic_ingestion_ctv_reference_compiler.py memorii/tests/unit/tools/test_ctv_binding_authority_pr_gate.py -p no:cacheprovider
PYTHONPATH=memorii .venv/bin/python docs/design/semantic_ingestion/traceability_golden_vectors/validate_recipe.py --recipe docs/design/semantic_ingestion/traceability_golden_vectors/recipe-v1.json --design docs/design/semantic_ingestion_architecture.md --registry docs/design/semantic_ingestion/traceability_registry/registry-v1.json --expected-recipe-sha256 <new> --expected-design-sha256 <new> --expected-registry-sha256 <new>
```

Then run the existing scenario ingress plus both elaborators and compare their
manifest and structural-spool bytes, followed by the structural-contract
checker and release-generation validation for the same revision. The numeric
kernel must separately prove: decimal rejection remains exact for policy
fields; points/enclosures have no implicit conversion; every unsafe comparison
uses the conservative endpoint; arithmetic exhaustion/unresolved ordering has
no pass result; and altered policy/evidence/certificate bytes fail the public
verifier. No tolerance, float conversion, Decimal rounding, relaxed equality,
or "close enough" gate is an admissible remediation.

## Blockers Before Promotion

1. The canonical design must name the exact policy/evidence field inventory and
   the approved policy encoding authority; current CTV marker data is not it.
2. The new kernel/transport design must freeze CTV-compatible point/enclosure
   forms, certificate pairing, bounded arithmetic, and fail-closed outcomes.
3. Only then can exact generated hashes, registry/structural deltas, golden
   vectors, signed generation members, and production-entrypoint bindings be
   planned. This map makes no implementation or approval claim.
