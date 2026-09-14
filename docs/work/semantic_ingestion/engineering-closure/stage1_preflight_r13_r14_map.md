# Stage-1 Semantic Ingestion Preflight: R13 / R14 (HEAD dbb42d33)

Scope: production-entrypoint ownership and authority/validation boundaries only. No code changes.

Status summary:
- R13: chain is mapped to canonical classes/interfaces; no confirmed production caller path is currently present in `memorii/` source.
- R14: unmapped (`production_caller` is explicitly null); no production caller exists.
- This map is read-only and does not close either requirement.

Canonical owners (production):
- `memorii.tools.semantic_ingestion_execution_evidence`: execution gate owner (`RegisteredApprovalExecutor` + `_verify_registered_approval_execution`).
- `memorii.tools.semantic_ingestion_traceability_release`: release gate owner (`validate_release_candidate`, `commit_verified_release`, `verify_release_gate` path).
- `memorii.tools.semantic_ingestion_trust_resolver`: trust-material owner (`AcceptanceTrustResolver`, `ConfiguredAcceptanceTrustResolver`, `DefaultAcceptanceTrustResolver`).
- `memorii.tools.semantic_ingestion_signature_verifier`: verifier-material owner (`Ed25519VerificationKeyBinding`, `Ed25519SignatureVerifier`).
- `acceptance` package (`acceptance/statistical_certification.py`): statistical evaluator owner (currently no production caller in `memorii/`).

## Primary owning paths (execution chain)

### R13 (`acceptance` registration gate + release verifier)
1. Host/runtime composition constructs `AcceptanceTrustStore` + `VerifierHeldTrustMaterial` and binds verifier keys through a configured resolver.
2. `ConfiguredAcceptanceTrustResolver.resolve_registered_execution()` returns frozen composition trust; candidate bytes cannot replace this binding (`DefaultAcceptanceTrustResolver` returns `None`).
3. `RegisteredApprovalExecutor.from_resolver(...)` creates executor with returned `AcceptanceTrustStore`.
4. `RegisteredApprovalExecutor.execute(...)` dispatches into `_verify_registered_approval_execution(...)`.
5. `_verify_registered_approval_execution` verifies CTV form and registry/evidence-group selection, then calls:
   - `validate_release_candidate(..., verifier_material=authority.material, expected_release_roots=authority.expected_release_roots, now=now)`
   - `_verify_optional_generation_closure(...)` with `authority.material.verify_signature` and independent verifier
   - `_verify_release_bound_execution(...)` for report-level evidence
   - `commit_verified_release(...)` against `publication_store` + `watermark_store`

### R14 (`independent statistical evaluator`)
1. Deterministic acceptance algebra lives in `acceptance/statistical_certification.py` and `acceptance/arithmetic.py`.
2. `HeldBinding`, `evaluate_certificate(...)`, and `verify_certificate(...)` are entry functions.
3. No production runtime boundary currently imports/calls `acceptance.*`; tests call this package directly.
4. The accepted design (`../acceptance-numeric-boundary/design.plan.md`) and component tests exist, but there is no bound production caller or installed CLI bridge in the production package yet.

## production_entrypoint_bindings (R13/R14)

| requirement/behavior | production trigger | composition root | authority-bearing callsite + exact args | validation | durable outcome | production caller count | fallback/bypass | evidence path |
|---|---|---|---|---|---|---:|---|---|
| R13 — registered release authorization gate | Ingestion activation/pipeline path that builds registered executor | `RegisteredApprovalExecutor` (bound via `ConfiguredAcceptanceTrustResolver`) | `RegisteredApprovalExecutor.from_resolver(resolver)` -> `resolver.resolve_registered_execution()`; `RegisteredApprovalExecutor.execute(...)` -> `_verify_registered_approval_execution(...)`; `validate_release_candidate(registry=..., bootstrap_artifact, recovery_artifact, lifecycle_artifact, release_artifact, active_pointer_artifact, release_history_artifact, historical_release_artifacts, recovery_artifacts, verifier_material=authority.material, expected_release_roots=authority.expected_release_roots, now=...)`; `commit_verified_release(..., authority.material.verify_signature ...)` | CTV decoding + canonical registry load, evidence-group/profile selection, release candidate validation, generation closure verification (optional), bounded report verification, and signature verification at required slots via composition-held `Ed25519SignatureVerifier.verify(profile_id, public_key_digest, preimage, signature)` | Returns `TraceabilityGateAuthorized`-qualified commit path or raises `ExecutionEvidenceError`; writes can proceed only through `publication_store`/`watermark_store` in `commit_verified_release` | 0 confirmed production callers in `memorii/` code (tests only; no runtime host binding identified in repo scan) | `DefaultAcceptanceTrustResolver` yields `None` and blocks: no production authorization if composition fails to provide configured resolver. Legacy test-only style execution cannot authorize registered production flow | `memorii/memorii/tools/semantic_ingestion_trust_resolver.py`; `memorii/memorii/tools/semantic_ingestion_signature_verifier.py`; `memorii/memorii/tools/semantic_ingestion_execution_evidence.py:198-427`; `memorii/memorii/tools/semantic_ingestion_traceability_release.py`; `memorii/tests/unit/tools/test_scenario_fixture_authority.py`; `memorii/tests/unit/tools/test_semantic_ingestion_signature_verifier.py` |
| R14 — independent statistical evaluator integration | None in production (no call path confirmed) | `acceptance/statistical_certification.py` (acceptance-only package) | No production-facing callsite; only test/import callsites currently (`acceptance.statistical_certification.verify_certificate/evaluate_certificate`) | Bounded transport and byte/size checks, strict typed-value decoding, policy/evidence/effective-authority consistency checks, and certificate recomputation when called by acceptance owner context | In-memory certificate object; no persisted production decision yet | 0 production callers (`production_caller: null`) | Any policy/evidence candidate cannot trigger evaluator without separately built production call path; no fallback to production runtime. Test-only usage does not authorize deployments | `acceptance/statistical_certification.py`; `acceptance/arithmetic.py`; `acceptance/ctv.py`; `memorii/tests/unit/acceptance/test_statistical_certification.py`; `docs/work/semantic_ingestion/engineering-closure/milestones/03-independent-statistical-evaluator.plan.md`; `docs/work/semantic_ingestion/acceptance-authority/design.plan.md` |

## Schema/persistence interfaces and durable artifacts touched

### R13
- `memorii.tools.semantic_ingestion_traceability_release.VerifierHeldTrustMaterial` / `AcceptanceTrustStore` carry verifier material, expected roots, watermark/publication stores, and anti-rollback state.
- `validate_release_candidate` binds to release-root schema profiles and signature-guarded release artifacts (e.g., `SemanticIngestionTraceabilityReleaseBody.v1`, `TraceabilityReleaseHistoryBody.v1`).
- Persistence writes are driven by `commit_verified_release` (watermark/publication) and do not grant authority on their own.
- CLI signing helpers (`semantic_ingestion_release_signing.py`, `semantic_ingestion_lifecycle_signing.py`, `semantic_ingestion_offline_signing.py`) prepare/assemble artifacts and signatures but are not the production gate.

### R14
- `acceptance` package defines its own closed CTV and numeric algebra (`statistical_acceptance_certificate.v1`), separate from production serializer.
- No production package dependency from `memorii/` to `acceptance/` in production source.
- No runtime persistence owner or registry/profile promotion path is mapped for evaluator outputs.

## Smallest coherent implementation slice (next closure step)

### R13 slice
- **Objective:** wire one production entrypoint to the registered executor path.
- **Minimal files:** production host/runtime composition owner + `memorii/memorii/tools/semantic_ingestion_execution_evidence.py` + `memorii/memorii/tools/semantic_ingestion_trust_resolver.py`.
- **Success condition:** runtime path constructs and uses `ConfiguredAcceptanceTrustResolver` and reaches `RegisteredApprovalExecutor.execute` before persistence.

### R14 slice
- **Objective:** add a production adapter boundary that builds `HeldBinding` and calls evaluator methods in the host approval path.
- **Minimal files:** one bounded production boundary module in `memorii/` and tests covering call routing + deny/allow transitions.
- **Success condition:** evaluator outputs are produced, persisted/recorded, and observed from runtime caller context (not tests only).

## Side-effect boundaries and prohibited bypasses

- **R13**: signature verification cannot be supplied by candidate payloads; resolver + trust material are composition-owned (`ConfiguredAcceptanceTrustResolver` docs+tests + implementation).
- **R13**: signature verifier is exact-coordinate by `(profile_id, public_key_digest)`; duplicate bindings rejected.
- **R13**: legacy release verification path is explicitly allowed for migration but does not authorize the registered production execution branch.
- **R14**: acceptance package is explicitly decoupled from production; no import-time or production call dependency from `memorii/`.
- **R14**: any attempt to treat this as production authority without host composition is a bypass of the currently unmapped boundary.

## Branch points and confidence

- **R13 highest-risk branches**
  - Resolver availability (`None` vs configured) short-circuits authorization.
  - `validate_release_candidate` / `commit_verified_release` outcomes: any unauthorized candidate fails closed before publication.
  - Optional generation closure and strict transport/path dependencies can fail with non-authority reasons and block commit.
  - Anti-rollback/provisioning path is part of commit gate (`authority.verified_anti_rollback_registration` / `anti_rollback_resolver`) and can reject if not supplied.

- **R14 highest-risk branches**
  - No production boundary ownership: explicit unmapped call path.
  - Context pre-construction (`HeldBinding`) remains external requirement; evaluator alone cannot bootstrap authority.
  - Accepted authority design for R14 prerequisite is blocked (acceptance-authority reconstruction budget reached), so no safe production elevation path exists yet.

## Unknowns + fastest next checks

- **R13 unknown**: exact runtime composition callsite count for production callers (operator host wiring) is not directly counted from current evidence; only internal execution path is proven in tests.
  - Fastest next check: trace `build_verified_production_host_authority` / production host factory callsite from live service startup and confirm it injects `ConfiguredAcceptanceTrustResolver` (not `DefaultAcceptanceTrustResolver`) into registered approval flow.

- **R14 unknown**: no public production caller exists for evaluator outputs.
  - Fastest next check: locate and verify authoritative host runtime adapter that feeds `HeldBinding` and calls `acceptance.statistical_certification.verify_certificate` from deployment path; currently absent.

- **R14 unknown**: acceptance-authority prerequisites (R14 prerequisite state machine) remain incomplete.
  - Fastest next check: reconcile against `docs/work/semantic_ingestion/acceptance-authority/design.plan.md` and implement canonical host adapter only after design successor closure.
