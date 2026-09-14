# Source-Derived Traceability Refresh Map

Status: read-only correction for the native-policy-retention SIA amendment.
This map does not authorize a refresh or change any pinned value.

## Current Schema And Tooling Result

The amended source is `docs/design/semantic_ingestion_architecture.md`. The
current `recipe-v1.json` has the eight-root current-pin schema:

```text
authority_use
checked_fixture_outputs
fixed_signers
format
nested_substitution_cases
primitive_authority
primitive_fixtures
vector_cases
```

There is no compatible recipe or golden-source-package generator in the
bounded repository tooling.

`regenerate_recipe_v19.py` is stale for this recipe. Before writing, it reads
`direct_negative_cases`, `expanded_typed_values`, and
`field_coverage_ledger`, none of which exists in the current schema. Its
observed `KeyError: 'direct_negative_cases'` is therefore an exact schema
incompatibility, not a command-line problem. Its optional registry and design
updates must not be used as a current refresh route.

`materialize_remaining.py` and `elaborate_independent_b.py` require
`fixture_recipes`, also absent. `rebind_recipe_v17.py` pins a historical
registry SHA-256 and a fixed 56-root inventory. The migration scripts are
one-way historical transforms with fixed predecessor identities.
`elaborate_current_a.py` and `elaborate_current_b.py` require the older
`memorii-sia-c2-normative-fixture-recipe-v1` format. None can mutate the
current eight-root recipe from amended source bytes.

`validate_recipe.py` is compatible with the current shape, including
`primitive_authority`, but is a verifier only: it accepts recipe, design,
registry, and expected hashes and writes no candidate artifact. The prior
engineering-closure preflight labels this operation "Regenerate recipe/typed
manifest fixture", but its displayed command invokes this validation-only tool;
it is evidence of the same absence, not a supported producer.

## Existing Compatible Producers

Two current compilers can refresh their own independent artifacts after their
inputs are legitimately established:

| Producer | Canonical inputs | Artifact it writes | Owner boundary |
| --- | --- | --- | --- |
| `traceability_golden_vectors/validate_ctv_binding_authority_v2.py --write` | design, registry | `ctv-binding-authority-v2.json` | CTV v2 binding authority compiler |
| `traceability_golden_vectors/cgs_structural_manifest_prototype.py` | design, registry, already-authorized derivation ledger | `cgs-structural-manifest-prototype-v1.json` | structural-manifest prototype compiler |

The CTV compiler does not read the recipe or `v1.json`. The structural compiler
does not create its derivation ledger. No bounded tool writes
`structural_manifest_derivation_ledger-v1.json`,
`cgs_verification_attack_matrix-v1.json`, or
`lifecycle-root-signer-provenance-witness-v1.json`.

Once a compatible registry-refresh owner has established the registry bytes,
the exact existing CTV command is:

```sh
python3.12 -I docs/design/semantic_ingestion/traceability_golden_vectors/validate_ctv_binding_authority_v2.py \
  --design docs/design/semantic_ingestion_architecture.md \
  --registry docs/design/semantic_ingestion/traceability_registry/registry-v1.json \
  --authority docs/design/semantic_ingestion/traceability_golden_vectors/ctv-binding-authority-v2.json \
  --write --self-test
```

If, and only if, the ledger owner authorizes a replacement ledger, the exact
structural prototype command is:

```sh
python3.12 -I docs/design/semantic_ingestion/traceability_golden_vectors/cgs_structural_manifest_prototype.py \
  docs/design/semantic_ingestion_architecture.md \
  docs/design/semantic_ingestion/traceability_registry/registry-v1.json \
  docs/design/semantic_ingestion/traceability_golden_vectors/structural_manifest_derivation_ledger-v1.json \
  docs/design/semantic_ingestion/traceability_golden_vectors/cgs-structural-manifest-prototype-v1.json
```

The CTV authority contains derived `source_design_sha256` and
`source_registry_sha256`; editing workflow hash pins cannot substitute for its
compilation.

## Validation-Only Commands

The following are proof steps, not source generators:

| Command or gate | Inputs pinned or checked | Legitimate refresh action |
| --- | --- | --- |
| `validate_recipe.py` | current recipe, design, registry, explicit SHA-256 values | validate a future owner-produced candidate; cannot create one |
| `validate_source.py` | fixed `v1.json` and design | validate the frozen source package; cannot create one |
| `check_ctv_binding_authority_v2.py` | design, registry, authority, validator, checker | update design/registry/authority workflow SHA-256 values after reviewed compiler output |
| `check_cgs_structural_contract_v1.py --self-test` | design, registry, ledger, attack matrix, prototype, vector, checker | validate the full structural relation after the ledger owner and prototype compiler act |
| `check_lifecycle_root_signer_provenance_v1.py --self-test` | design, attack matrix, lifecycle witness, validator, checker | validate after any reviewed source-coordinate change |
| `run_scenario_ingress.py` plus `elaborate_scenario_a.py` and `elaborate_scenario_b.py` | scenario fixture, design, registry, CTV authority | produce temporary A/B evidence only; no canonical recipe or source-package output |

The exact CTV and structural checker invocations are in
`.github/workflows/pr-gates.yml` under `ctv-binding-authority-exact`. CI invokes
no producer.

## Hash And Coordinate Fan-Out

The design amendment changes raw design SHA-256. The currently determinable
fan-out is:

1. `registry-v1.json` raw SHA-256, only if a compatible registry owner proves
   its source-derived content changes.
2. `ctv-binding-authority-v2.json` raw SHA-256; its source design/registry
   hashes, grammar/enum/profile/binding digests, and affected schema
   fingerprints.
3. If authorized, the structural ledger raw SHA-256, prototype-vector raw
   SHA-256, derived ledger digest, and structural coordinates.
4. Transient scenario ingress manifests, which record the design, registry,
   and CTV-authority SHA-256 values and must be recreated for evidence.
5. Workflow CTV expected hashes for design, registry, and authority. The
   validator/checker hashes change only if those code files change.

A future compatible current-pin compiler would additionally determine the
`recipe-v1.json` raw SHA-256 and all embedded design/registry/body/artifact/
signature values. A compatible package producer would then determine `v1.json`
raw SHA-256 and copied fixture bytes. Neither value can be obtained safely by
manual pin replacement. `validate_source.py` has an approved source hash
constant, so even generated package bytes require explicit owner review and
promotion before they validate.

## Blocker

The concrete blocker is the absence of a current-pin recipe/source-package
compiler compatible with the current eight-root recipe schema. The smallest
next action is for the golden-source owner to supply or designate a compiler
whose declared inputs are the current recipe schema, amended design, and
registry, then review its output before any canonical recipe, `v1.json`, or CI
pin is changed. This map does not decide whether the amendment changes enum
inventory, structural-ledger coordinates, lifecycle witness inputs, or the
approved golden-source baseline.

## Applied Bounded Refresh Evidence (2026-09-07)

The native-policy-retention amendment changed raw design SHA-256 from
`b469653e3ef92e9cc1bf45e797a2c7dff8eac4d9ee792ad94ada3a54bfbe05da` to
`69140e58d650fbe9f59d69de2da06d846b6c4a9040256d82d29fced76e918e79`.
The registry remains
`70143b278e0fd72886362f4174c726c9ecf877b1e288d3dd2c196a78f385413e`.

The CTV compiler was run by the coordinator with `--write --self-test` against
the amended design and unchanged registry, producing candidate SHA-256
`653119939fa33484e4f16da25d332590202408dc9ed1b75daf9954c45183dd43`.
A structural JSON comparison found exactly one semantic difference from the
prior authority: `source_design_sha256`. The profile and all 56 schema rows are
unchanged. The candidate was promoted verbatim.

The isolated structural prototype compiler was run against the amended design,
unchanged registry, and unchanged authorized ledger. It produced SHA-256
`5b6fcc67103ba4d18842c89a68e3d2da95f3a70be143b7fd38b1aa06606519ec`, which
was promoted verbatim. An isolated compile against the HEAD design reproduced
the prior vector byte-for-byte. The amended result changes only values derived
from raw design bytes: its raw design digest, design-derived unit positions,
and consequently the structural body/envelope bytes and their digests. The
ledger, matrix, and lifecycle witness contain no raw-design SHA literal and
remain at their prior SHA-256 identities.

Pins were refreshed without changing checker algorithms:

| Surface | New SHA-256 or pin |
| --- | --- |
| CTV authority artifact | `653119939fa33484e4f16da25d332590202408dc9ed1b75daf9954c45183dd43` |
| structural prototype vector | `5b6fcc67103ba4d18842c89a68e3d2da95f3a70be143b7fd38b1aa06606519ec` |
| lifecycle provenance checker | `58f81fe028a4a89cb30f43bc1a88779a5567652eb11075785e7fe7e232228938` |
| structural contract checker | `f05835dcbf0dc319855e34f79b6b051371ced0ce40f6d345fd78a729d62e7825` |

The lifecycle and structural checkers now pin the amended raw design hash; the
structural checker also pins the compiler-derived vector hash. The PR workflow
now pins the amended design, refreshed CTV authority, and the two changed
checker sources. The CTV validator and CTV checker source hashes are unchanged.
The coordinator owns the final exact gate executions.

The required `ctv-binding-authority-exact` workflow gates consume only the
design, registry, CTV authority, lifecycle matrix/witness/validator, structural
ledger/matrix/prototype/vector, and checker pins. They do not consume
`recipe-v1.json` or `traceability_golden_vectors/v1.json`. The separate
`semantic-ingestion-generation` required job runs
`tests/unit/tools/test_generation_closure_exactness.py`; its source references
`v1.json` only as an asserted metadata path and does not read either frozen
artifact. Thus the unavailable current-pin recipe/package producer remains a
separate source-package closure blocker, but it does not block this bounded
CTV/lifecycle/structural refresh.
