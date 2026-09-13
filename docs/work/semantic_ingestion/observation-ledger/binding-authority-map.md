# Production Binding And Fixture Authority Map

Coordinator-reconciled map. The initial delegate inventory conflated runtime
schema registration with the fixed test-only traceability inventory. That
registration recommendation is rejected. No schema is registered by this map.

## Production Contract

SIA2676-2730 names memory_evolution/ingestion_contracts.py as the canonical owner
of CanonicalTypedValueProfile, CanonicalTypedValueProfileBinding,
CanonicalEncodedArtifact, CanonicalTypedValueProfileRegistryEntry and Registry.
SIA2825-2868 requires complete binding preimages, immutable unique entries,
embedded-binding decoder selection and verified historical bytes before upcast.
SIA32014 expressly applies that production contract to observations.

Current production ingestion_contracts.py:796 implements the binding dataclass
and shape validation; :1353-1424 implements artifact encoding/decoding. Its
optional expected_binding checks equality but does not supply a registry.
The current module docstring explicitly delegates registered schema field and
signature policy selection to callers. No implementation of the full
CanonicalTypedValueProfileRegistry or RegistryEntry was found by repository-wide
class search. Bootstrap_profile.py:573 provides a closed fixed-binding selector
for bootstrap artifacts only; it is not a runtime observation registry.

A ledger schema needs an immutable registered entry containing its exact schema,
enum, optional-field, numeric, digest/signature-policy and decoder fingerprints.
Unknown binding must reject before body decode. Existing envelope primitives
are reusable; arbitrary schema IDs plus well-shaped hashes are not registration.
The current observation helpers are unregistered construction, as already recorded.

## Distinct Nonoperational Fixture Boundary

SIA9288 explicitly identifies the 56-root traceability fixture inventory as
nonoperational. semantic_ingestion_ctv_reference_compiler.compile_authority
(:803) and validate_ctv_binding_authority_v2.py compile/check that fixed inventory.
They do not register arbitrary new runtime observation schema roots. Therefore
DO NOT expand the fixed 56 roots merely to add ledger storage types or change
the frozen fixture profile version for that reason.

A canonical design byte change still invalidates the fixture's pinned source
identity and structural evidence, even if none of its projected roots change.
Relevant existing consumers are traceability_registry/registry-v1.json;
traceability_golden_vectors/{ctv-binding-authority-v2.json,
structural_manifest_derivation_ledger-v1.json,cgs-structural-manifest-prototype-v1.json,
lifecycle-root-signer-provenance-witness-v1.json,recipe-v1.json}; the reference
compiler and hermetic checkers; and current-release-chain fixtures.

.github/workflows/pr-gates.yml:90-131 supplies exact checker commands AND expected
hash arguments. Copy the entire current command when verifying; a command with
its expected hash arguments omitted is not the workflow gate. Compiler parity
runs tests/unit/tools/test_semantic_ingestion_ctv_reference_compiler.py.
Canonical promotion must follow the affected source-pin/structural chain and
retain old frozen fixture identities as historical evidence. No canonical design
or generated fixture has changed in this bounded design operation.

## Remaining Design Work

Freeze exact production registry entries and decoder-selection ownership for
ledger head/entry, source intent, activation, replay and checkpoint preimages.
The registration mechanism is already normatively specified; production
implementation and concrete new entries are missing. The traceability fixture
compiler is not a substitute. Record this under R03/R17 rather than claiming
that a test-only marker creates runtime authority.
