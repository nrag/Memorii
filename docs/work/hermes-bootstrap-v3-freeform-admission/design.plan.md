# Hermes Bootstrap V3 Free-Form Admission

- Work ID: hermes-bootstrap-v3-freeform-admission
- Work type: design
- Delivery fidelity: Level 2 early real-world testing
- Status: complete
- Coordinator: `/root`
- Created: 2026-09-23
- Last updated: 2026-09-23
- Parent WorkPlan: `docs/work/hermes-semantic-profile-runtime-contract/design.plan.md`
- Related WorkPlans: `docs/work/hermes-conversation-memory-trial/implementation.plan.md`
- Canonical inputs: `AGENTS.md`, `.agents/PLANS.md`, `docs/design/semantic_ingestion_architecture.md`, `docs/design/hermes_conversation_memory_trial.md`, `memorii/memorii/core/memory_evolution/bootstrap_profile.py`, `memorii/memorii/core/semantic_ingestion/source_preparation.py`, and `memorii/memorii/core/provider/ingestion.py`
- Expected outputs: a frozen Bootstrap V3 free-form admission contract and implementation evidence matrix

## Objective And Completion Contract

Replace the byte-equal `BootstrapGrammarCorpus` production allowlist with a
production-owned versioned policy that admits authenticated English free-form
segments under the installed project-assertions resource policy. Bootstrap V3
remains the only runtime/interface and all downstream V3 normalizer, candidate,
writer, graph/projection, and protected-read contracts remain unchanged.

The design completes when an implementation writer can change the exact typed
artifact schemas, classifiers, preparation producer, installation authority,
and verification without choosing an unstated fallback or fixture path. It does
not claim the code or Windows journey exists.

## Decision And Rejected Alternative

Retaining the literal corpus as the production allowlist is rejected. It makes
fresh natural-language user facts impossible by definition and contradicts the
Level 2 real Hermes journey. The corpus remains valuable as a versioned
conformance/golden evidence set. A generic language detector or ambient model
router is also excluded: admission remains bound to authenticated English host
evidence and installed policy bytes.

## Requirement And Authority Matrix

| Requirement | Exact behavior | Required evidence |
| --- | --- | --- |
| BFA-01 | A verified Bootstrap v2 profile binds a versioned policy and golden corpus through closed v1/v2 artifact, route, and proof unions. | Artifact/digest/version/migration plus durable decode/reload/normalizer tests. |
| BFA-02 | `classify_bootstrap_input` accepts only factory-issued fixed-`en` evidence and raw NFC policy-valid segments within scalar/byte/child caps. | Positive/negative equivalence matrix; no-language-detector boundary test. |
| BFA-03 | Selected input reaches the existing V3 proposal transport; rejected input has deterministic abstain/unsupported outcome and no egress/write. | Call-path and no-call tests. |
| BFA-04 | Production verifier and local adapter load identical installed policy bytes and bind their digests into existing host envelope/local sidecar. | Substitution and authorization tests. |
| BFA-05 | Old literal-profile bytes remain readable as corpus-only compatibility material but cannot activate free-form policy. | migration/rollback tests. |
| BFA-06 | Persisted route/proof decode has exactly one v1 native member and one v2 free-form member; no obsolete v2 shape is accepted. | discriminator and mixed/obsolete wire rejection tests. |
| BFA-07 | V1 and V2 Bootstrap coordinates/artifact families have closed decoders and no coercion. | v2 build/verify/persist/reopen, byte-identical v1 fixture, and cross-version substitution tests. |

## Changed Surface And Identity Ledger

| Surface | Owner | Change |
| --- | --- | --- |
| `bootstrap_profile.py` | Bootstrap profile owner | v2 grammar manifest/policy and legacy artifact decode. |
| `source_preparation.py` | Bootstrap preparation owner | policy classification, child proofs, deterministic outcomes. |
| `ingestion.py` | provider admission owner | existing classifier caller receives policy outcome only. |
| `resources/bootstrap_freeform_admission_policy.json` | production package resource owner | new installed policy source. |
| existing bootstrap corpus resource/artifact | production evidence owner | golden/conformance only, never route selection. |
| project assertions resources and local sidecar | integration resource owner | bind policy digest; no fixture authority. |

## Verification Matrix

Required deterministic evidence covers: authenticated English accepted with
different bytes from every golden corpus case; unauthenticated/missing/
mismatched/non-English language; empty/oversize/control-character/mixed-residue
segments; projection/source digest mismatch; child partition boundary and cap;
policy/catalog/component/sidecar substitutions; legacy profile migration and
rollback; egress only after selected policy route; and all downstream V3
normalizer/candidate/writer/graph/read contracts unchanged. The real Hermes
evidence is a fresh supported free-form fact -> commit -> cross-session and
post-restart protected recall using the pinned loader.

The required route/proof tests cover v1 corpus-only replay/read, v2 free-form
route/proof with full child coordinates and no corpus case ID, mixed/unknown
union decode rejection, exact byte-compatible legacy v1 fixture decode/replay/
audit, route and proof domain-preimage mutations, raw-span/scalar/UTF-8 slice/
source/projection/policy/profile binding substitutions, multi-child order and
pair-bijection checks, and every durable consumer. Language tests prove that
missing/tampered/expired/disagreed/non-`en` factory evidence denies pre-egress,
while Spanish under valid fixed-`en` evidence is not claimed detected by
admission and must abstain later if predicate/evidence validation cannot support
it. Policy tests cover `max_child_segments` 0, 1, 8, 9, 16, 17 and scalar/UTF-8
limits, NFC accepted/NFD rejected without rewriting raw bytes. Required phase
tests mutate installed policy/manifest after egress before commit and before
recovery, prove authority-unavailable/no visibility/no retry, and prove stale
leases cannot publish. Operational evidence uses two golden-absent assertions,
provenance, new-session recall, and post-restart recall.

The Section 8 envelope accepts only the closed verified-artifact union
`VerifiedBootstrapProfileV1 | VerifiedBootstrapProfileV2`; tests prove both use
the same Bootstrap V3 normalizer/writer/read path, no artifact version can
select a second runtime, v1 cannot start fresh free-form admission, and v2
cannot omit policy/golden-corpus bindings.

Required versioning evidence proves exact native v1 route/proof wire decode,
only the sole v2 route/proof schema IDs and discriminators, obsolete v2 shape
rejection, strict V1/V2 coordinate decode without coercion, real package-owned
V2 release build/verify/persist/reopen, and every cross-version identity or
digest substitution rejection.

## Final Cohort Review And Completion

The final spec, correctness, and test reviewers approved the frozen candidate
after the native v1 wire preservation, sole v2 route/proof union, strict V2
coordinate/release family, complete child-coordinate proof, fixed-English
authority, artifact-version compatibility, and phase-mutation corrections. No
confirmed finding remains that requires a Level 2 design amendment.

The bounded design completion contract is satisfied: free-form admission is
policy-governed inside the existing Bootstrap V3 runtime; corpus cases are
golden evidence only; exact v1 replay compatibility and v2 production material
are specified; downstream V3 normalizer/candidate/writer/graph/read contracts
remain unchanged. Implementation, installed-image, and Windows Docker evidence
is not claimed by this design WorkPlan.

The resumption target is
`docs/work/hermes-conversation-memory-trial/implementation.plan.md`. It must
reopen its own readiness, changed-surface, authority-chain, and evidence
ledgers before implementation.

## Next Action

None. The Bootstrap V3 free-form admission design remediation is complete.

## Candidate Freeze Record

The frozen governing candidate is:

| File | SHA-256 |
| --- | --- |
| `docs/design/semantic_ingestion_architecture.md` | `0e4145925284a3759488ca9045c0ba7f5a751c114cbb1bb7f4152699e35a62ce` |
| `docs/design/hermes_conversation_memory_trial.md` | `f6b5f5929286795072b9f134ea5daf5fdb906f6c5cf3f6329b6905ad6cebd560` |

Reviewers must reject mismatched candidate bytes. This WorkPlan is not
self-hashed.
