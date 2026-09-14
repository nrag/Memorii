# Numeric Promotion Preflight Map

## Coordinator Validation: Not An Executable Runbook

The claimed executable sequence below is rejected as closure evidence. The
checker validates existing output; it does not regenerate authority. Invoking
a pytest module directly does not execute its tests. Several scenario commands
are placeholders, not confirmed CLI invocations. Do not run or cite this sequence
as a verified regeneration procedure.

The actual compiler entry point is
`memorii/memorii/tools/semantic_ingestion_ctv_reference_compiler.py:950`:
`python -m memorii.tools.semantic_ingestion_ctv_reference_compiler --design PATH
--registry PATH --output PATH` with the production package on the development
import path. Its current grammar and inventory are explicitly v2/56 roots.
SIA's inventory-change rule already requires a new profile-registry version;
whether to preserve a changed content digest is not an external policy choice.
The arithmetic component design is approved; canonical authority promotion and
the independent baseline approval contracts remain separate unfinished work.

Coordinator read-only baseline reproduction used `compile_authority(design_bytes,
registry_bytes)` from that module and obtained byte-identical current authority:
SHA-256 `272617544ee6531f995f797f323b576bc4070282ff1dd2cd12e49cfb0c492f3b`.
No source or generated authority was overwritten. This verifies the current
compiler input/output boundary only, not the placeholder promotion sequence.

## Scope and Status
- Authoring scope: `docs/work/semantic_ingestion/statistical-acceptance/{proposal,closure,promotion-map}.md` (read-only analysis), production boundary tooling under `memorii/memorii/tools`.
- This artifact is a read-only preflight map only.
- `docs/work/semantic_ingestion/engineering-closure/numeric-promotion-preflight.md` is created per requested bounded output.

## Executive Determination
`numeric` promotion is currently blocked by unresolved semantic decisions in section 5.6 policy/encoding. Automated regeneration is mechanically viable only after normative approval of the new numeric schema inventory and binding policy.

- `production_entrypoint_bindings.json` currently records R14 as `unmapped` with `production_caller: null` and no canonical owner, and no production caller for the new numeric schema branch.
- The static chain remains compiler-driven:
  - design + registry + validator -> authority -> structural manifest -> cgs checks -> scenario/recipe/golden -> traceability release chain.

## Exact executable regeneration chain (ordered)
1. Edit design declarations in `docs/design/semantic_ingestion_architecture.md`:
   - Canonical numeric policy-vs-computation contract (policy inputs stay decimal policy type; computed p-values/bounds/enclosures become exact rational/interval types).
   - Any new `CapabilityStatisticalNumericEncodingRegistry` (or equivalent normative source object) and exact field-level `(encoding_spec_id, unit, range, inclusivity, reject_inexact)` entries.
2. Regenerate checked authority (strict closed checker):
   
   ```bash
   python3.12 -I docs/design/semantic_ingestion/traceability_golden_vectors/check_ctv_binding_authority_v2.py \
     --design docs/design/semantic_ingestion_architecture.md \
     --registry docs/design/semantic_ingestion/traceability_registry/registry-v1.json \
     --authority docs/design/semantic_ingestion/traceability_golden_vectors/ctv-binding-authority-v2.json \
     --validator docs/design/semantic_ingestion/traceability_golden_vectors/validate_ctv_binding_authority_v2.py \
     --expected-design-sha256 <new_design_sha256> \
     --expected-registry-sha256 <new_registry_sha256> \
     --expected-authority-sha256 <new_authority_sha256> \
     --expected-validator-sha256 3066e6ffb015823283e57945863c22d4ecf32164c52ae8199eb1535c7798f145 \
     --expected-checker-sha256 <new_checker_sha256>
   ```

   - Checker constants currently enforce `EXPECTED_SCHEMAS = 56`, `EXPECTED_ENUM_ROWS = 249`, `EXPECTED_PROFILE_DIGEST = 9dc8...7f` (see `check_ctv_binding_authority_v2.py`).
   - Baseline command pins (current frozen identity) in `static_tooling.md` require 56 schema/249 enum row counts and fixed design/registry hashes.
3. Regenerate CTV compilation outputs and run authoritative CTV unit gate:

   ```bash
   PYTHONPATH=memorii .venv/bin/python memorii/tests/unit/tools/test_semantic_ingestion_ctv_reference_compiler.py
   PYTHONPATH=memorii .venv/bin/python memorii/tests/unit/tools/test_ctv_binding_authority_pr_gate.py -p no:cacheprovider
   ```
4. Regenerate registry-aware structural manifest and CGS contract:
   - Rebuild manifest prototype if registry/deps changed:
   
   ```bash
   python3.12 -I docs/design/semantic_ingestion/traceability_golden_vectors/cgs_structural_manifest_prototype.py \
     docs/design/semantic_ingestion_architecture.md \
     docs/design/semantic_ingestion/traceability_registry/registry-v1.json \
     docs/design/semantic_ingestion/traceability_golden_vectors/structural_manifest_derivation_ledger-v1.json \
     docs/design/semantic_ingestion/traceability_golden_vectors/cgs-structural-manifest-prototype-v1.json \
     --verify
   ```

   - Then validate contract and attack matrix:

   ```bash
   python3.12 -I docs/design/semantic_ingestion/traceability_golden_vectors/check_cgs_structural_contract_v1.py \
     --design docs/design/semantic_ingestion_architecture.md \
     --registry docs/design/semantic_ingestion/traceability_registry/registry-v1.json \
     --ledger docs/design/semantic_ingestion/traceability_golden_vectors/structural_manifest_derivation_ledger-v1.json \
     --matrix docs/design/semantic_ingestion/traceability_golden_vectors/cgs_verification_attack_matrix-v1.json \
     --prototype docs/design/semantic_ingestion/traceability_golden_vectors/cgs_structural_manifest_prototype.py \
     --vector docs/design/semantic_ingestion/traceability_golden_vectors/cgs-structural-manifest-prototype-v1.json \
     --expected-checker-sha256 <new_checker_sha256> \
     --self-test
   ```

5. Regenerate canonical acceptance scenarios and compare elaborators end-to-end:

   ```bash
   PYTHONPATH=memorii .venv/bin/python docs/design/semantic_ingestion/traceability_golden_vectors/run_scenario_ingress.py docs/design/semantic_ingestion/traceability_golden_vectors/scenario-first-v1.json <run_out.json>
   PYTHONPATH=memorii .venv/bin/python docs/design/semantic_ingestion/traceability_golden_vectors/elaborate_scenario_a.py docs/design/semantic_ingestion/traceability_golden_vectors/scenario-first-v1.json <run_out.json> <arch>.json <release_arch>.json ...
   PYTHONPATH=memorii .venv/bin/python docs/design/semantic_ingestion/traceability_golden_vectors/elaborate_scenario_b.py docs/design/semantic_ingestion/traceability_golden_vectors/scenario-first-v1.json <run_out.json> <release_arch>.json <release_arch>.json
   cmp <elab_a_manifest>.json <elab_b_manifest>.json
   cmp <a.structural_spool>.json <b.structural_spool>.json
   ```

   - Then validate manifest + expected hashes:

   ```bash
   PYTHONPATH=memorii .venv/bin/python docs/design/semantic_ingestion/traceability_golden_vectors/validate_scenario_manifest.py <elab_a_manifest>.json <a.structural_spool>.json
   ```

6. Regenerate recipe/typed manifest fixture if fixture includes affected schema signatures:

   ```bash
   PYTHONPATH=memorii .venv/bin/python docs/design/semantic_ingestion/traceability_golden_vectors/validate_recipe.py \
     --recipe docs/design/semantic_ingestion/traceability_golden_vectors/recipe-v1.json \
     --design docs/design/semantic_ingestion_architecture.md \
     --registry docs/design/semantic_ingestion/traceability_registry/registry-v1.json \
     --expected-recipe-sha256 <new> --expected-design-sha256 <new> --expected-registry-sha256 <new> \
     --self-test
   ```

7. Rebuild traceability release chain artifacts (manifest/release/pointer/trust) via owner-composition tooling only after all above identities are frozen. Existing release/pointer/signature identities become invalid when design/registry/authority/manifest/member bytes change.

## Exact boundary map (one-shot view)

| requirement/behavior | production trigger | composition root | authority-bearing callsite + exact arg | validation | durable outcome | production caller count | fallback/bypass | evidence path |
|---|---|---|---|---|---|---|---|---|
| Schema authority derivation for numeric field policy | `proposal.md` acceptance of policy/data-carrying schema changes | `memorii/memorii/tools/semantic_ingestion_ctv_reference_compiler.py` (compiler + checker split) | _No production caller_; owner is design/registry edit + checker pipeline. | `check_ctv_binding_authority_v2.py` (`--design`, `--registry`, `--authority`, `--validator`, count/digest checks + snapshot-replay self-test) | Frozen `ctv-binding-authority-v2.json` with exact profiles/schema counts and sha256s + validator binding | 0 in `production_entrypoint_bindings.json` | `proposal.md` historical/rejected paths are test-only and not production | `docs/work/semantic_ingestion/statistical-acceptance/promotion-map.md`; `docs/work/semantic_ingestion/statistical-acceptance/closure.md`; `docs/work/semantic_ingestion/engineering-closure/production_entrypoint_bindings.json` |
| Structural manifest/body binding impacted by numeric schema edits | source change + registry change affecting Sections 1–5 mappings | `memorii/tools/semantic_ingestion_traceability_manifest.py` and `semantic_ingestion_traceability_registry.py` | `build_structural_manifest(design_bytes, registry)`; schema roots from `TraceabilityRegistry(source)` | `check_cgs_structural_contract_v1.py` (ledger/body/prototype/vector/attack matrix validation, `--self-test`) | New `cgs-structural-manifest-prototype-v1.json` + canonical structural bytes/digests | 0 direct production callsite in boundary map | `test_cgs_structural_contract_v1` and attack probes | `docs/design/semantic_ingestion/traceability_golden_vectors/check_cgs_structural_contract_v1.py`; `docs/design/semantic_ingestion/traceability_golden_vectors/structural_manifest_derivation_ledger-v1.json`; `cgs_structural_manifest_prototype.py` |
| Numeric policy/golden semantics validation (scenario + manifest) | fixture run post-closure change | `docs/design/semantic_ingestion/traceability_golden_vectors/run_scenario_ingress.py` (+ `_a/_b`) | `elaborate_scenario_a(...ingress_runner=run_scenario_ingress.py)`; `elaborate_scenario_b(...ingress_runner=run_scenario_ingress.py)`; `validate_scenario_manifest(...expected_*/actual_*)` | self-consistency of A/B manifest paths, structural spool equality, manifest validator checks | Updated scenario fixtures and expected hashes (`scenario-first-v1.json`/`recipe-v1.json` derivatives) | 0 direct production callsites | scenario/recipe evidence is non-production test evidence unless mapped in owner package | `docs/design/semantic_ingestion/traceability_golden_vectors/validate_scenario_manifest.py`; `elaborate_scenario_a.py`; `elaborate_scenario_b.py` |
| Release identity closure after numeric authority promotion | any changed byte in design/registry/manifest/fixture/evidence | `memorii/memorii/tools/semantic_ingestion_traceability_release.py` + release/coverage execution owner | `traceability_release.py` manifest/coverage/release construction callpoints (owner package, not present as production HTTP trigger) | existing release verifier gates (bootstrap/recovery/lifecycle/anti-rollback, active pointers, publication fence) | New bootstrap/lifecycle/coverage/release/pointer artifacts and signed bytes |
| Signature/verifier composition | unchanged by design-only numeric contract but invalidated by byte churn | `memorii/memorii/tools/semantic_ingestion_signature_verifier.py` + adapter owner | `VerifierHeldTrustMaterial.verify_signature` inputs remain externally provisioned | trust and registered signer/root checks only; cannot be authority input for numeric schema logic | Signature inputs stay independent; acceptance/release bytes must be re-signed if changed | 1 test-owner mapped partial (R13) | `test_configured_resolver...` demonstrates verifier path with test fixture, not canonical acceptance mapping | `docs/work/semantic_ingestion/engineering-closure/production_entrypoint_bindings.json` (R13 partial), `docs/work/semantic_ingestion/engineering-closure/observer-contract-map.md` |

## Nested numeric schema edits vs new top-level schema inventory
- **Nested-field change inside existing top-level schema root:**
  - Keeps top-level schema count at the same cardinality (historical expectation remains 56 unless root set changed).
  - Regenerates transitive schema binding digests for that root and every dependent body/reference chain that mentions it.
  - Expected to change `ctv-binding-authority-v2.json` profile/binding row payload(s) and `design/registry/profile` hashes if schema references are in registry-root claims.

- **New top-level numeric schema root (new canonical schema declaration in architecture):**
  - Increments schema inventory (`schemas` array and transitive root assumptions).
  - Requires a profile/version decision for top-level versioning and a re-baselined authority hash set. In practice this is a structural registry/versioning migration event.
  - Requires any registry assertions/requirements referencing the new root to be added in `registry-v1.json` and mapped in structural ledger.

## Primary owner/call stack by layer
- **Layer / entrypoint**: `docs/design/semantic_ingestion_architecture.md` (normative text)
- **Compiler / static gate**: `semantic_ingestion_ctv_reference_compiler.py` -> `check_ctv_binding_authority_v2.py` -> `validate_ctv_binding_authority_v2.py`
- **Registry binding gate**: `semantic_ingestion_traceability_registry.py` (validation/roots)
- **Structural derivation**: `semantic_ingestion_traceability_manifest.py` + `check_cgs_structural_contract_v1.py`
- **Golden evidence**: `run_scenario_ingress.py` + `elaborate_scenario_a.py`/`elaborate_scenario_b.py` + `validate_scenario_manifest.py`

## Blockers vs mechanical work

### Requires semantic decision (approval-level boundary)
1. Freeze the exact numeric policy-to-computation split and whether each field remains policy input vs computed evidence.
2. Approve exact numeric encoding registry object(s) for all new/changed numeric fields (scale/units/range/inclusivity/reject_inexact).
3. Decide whether to add new top-level numeric schema roots or only mutate existing top-level schema shapes.
4. Approve whether Monitoring/coverage artifacts can be regenerated under existing profile or require profile-version bump.

### Mechanical regeneration-only tasks (run with fixed frozen semantics)
1. Regenerate authority + hash pins via CTV checker.
2. Run `test_semantic_ingestion_ctv_reference_compiler.py` and `test_ctv_binding_authority_pr_gate.py`.
3. Regenerate registry-driven structural manifest and run cgs contract self-test.
4. Re-run scenario A/B and manifest self-consistency checks.
5. Re-run recipe/scenario hash checks and update fixture pins.
6. Rebuild signed release/manifest/pointer artifacts and publication flow in owner package.

## Unknowns and fastest next checks
- **Unknown:** whether a new top-level schema in Sections 1.5/5.6 is required or nested mutation suffices for the target computed-result fields. 
  - Fastest next check: diff only changed schema-bearing fields through compiler output before modifying schema-count assumptions.
- **Unknown:** whether current `validator.py` can prove decimal-policy and exact-computed split constraints without helper schema source.
  - Fastest next check: execute current checker command after adding only explicit encoding registry entries and inspect first-failure deltas.
- **Unknown:** whether `recipe-v1.json` / `scenario-first-v1.json` represent all affected numeric surfaces in current test corpus.
  - Fastest next check: run `validate_recipe.py` and `validate_scenario_manifest.py` on the new run outputs and inspect any expected-reason substitutions.
