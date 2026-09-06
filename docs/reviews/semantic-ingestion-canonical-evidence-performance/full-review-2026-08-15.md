# Design Review: Canonical Evidence Performance Proposal

## Review Metadata

- Review ID: semantic-ingestion-canonical-evidence-performance-full-2026-08-15
- Review mode: full
- Review outcome: Changes required
- Design path: `docs/reviews/semantic-ingestion-canonical-evidence-performance/proposal-baseline-2026-08-15.md`
- Design baseline: SHA-256 `42424f7470fe3b44f14778a8e0ddc93870c91c3c76c823fa6d9a4bde9a0f0ee6`
- Implementation baseline: live 2026-08-15 worktree; exact owner hashes are recorded below
- Review date: 2026-08-15
- Reviewers: Codex coordinator; independent `spec_auditor` `01a008b2-6c69-7f73-a161-d5a8783f705c`; independent `correctness_reviewer` `01a008b2-b2b2-7912-ab1e-dd200ac907a2`; independent `test_reviewer` `01a008b2-b480-75a2-865c-234d6a6dc775`
- Included scope: canonical body and wire encoding, content-addressed validation, source-normalization persistence/reload, graph-authority handoff, exact checkpoint retry, compatibility, security, lifecycle, resource bounds, and verification
- Excluded scope: implementation, current retry-test correction, persisted-schema or digest change, graph traversal, retry policy, M4, and unrelated performance work

Implementation owner identities inspected:

| Owner | SHA-256 |
| --- | --- |
| `memorii/memorii/core/semantic_ingestion/contracts.py` | `19fe1cc4a3bff129e191ecddb946020a68b565cd835395594baad5bdb0281f3e` |
| `memorii/memorii/core/memory_evolution/ingestion_contracts.py` | `d71af10fe0d5b71c02c815001b9c889696332d7361d57a8c0c6ab95ad824ad6e` |
| `memorii/memorii/core/semantic_ingestion/source_normalization_repository.py` | `37e6fbf3a189a1065e3f5b919240b289b22cdf988a5d3c0dfc2d315005095314` |
| `memorii/memorii/core/semantic_ingestion/bootstrap_graph_repository.py` | `8bdcb46c0b183103f1ff0c2f6e74f1dce74b748d357f61c82ef1ce7e293f12d7` |
| `memorii/memorii/core/memory_evolution/atomic_store.py` | `8f1319ab1e2e52b7fdc5b98777e8e55d5025becafb5766b684589188808fb2a5` |

## Executive Assessment

The proposal correctly identifies repeated canonical construction as the
dominant measured cost and correctly forbids wire, digest, validation, retry,
and authority weakening. The architecture is conditionally feasible, but it
is not implementation-ready.

The proposed `VerifiedCanonicalContract` has one byte field and one digest
field even though current production has at least three distinct identities:
the domain-bound content body, the typed semantic envelope, and the persisted
member payload. The proposal also wraps completed contracts after much of the
measured recursive work has already occurred. It does not define the codec- or
validation-level mechanism required to reuse repeated descendants during
decode and nested model construction. Finally, “trusted internal handoff” is
not a closed trust rule and could bypass deliberate forged-model rejection or
dynamic lease, fence, epoch, scope, writer, and tenant checks.

No implementation should begin from this baseline. A revised design must
separate identity roles, place reuse inside the codec/validation construction
path, define evidence issuance and lifetime, preserve dynamic authority checks,
and freeze falsifiable correctness, resource, and performance acceptance.

## Governing Sources

Precedence follows root `AGENTS.md`:

1. `docs/design/memorii_spec.md` SHA-256 `5d24a08e7ca048c85d75aef7eb8eb264e9a869cadcd0ebd5d07d7e368f1d6cc5`
2. `docs/design/memorii_storage_details.md` SHA-256 `9ce9b03722be2344d93847f425a04a9a147369c900a32b1ceed21bb34ffb1f37`
3. `docs/design/event_model.md` SHA-256 `9ce93e4a826f3e47b2e41fa06d2ec1e40bb0cad2475fa0527d9bb2c9ab3acdec`
4. `docs/IMPLEMENTATION_RULES.md` SHA-256 `c962791b8ba6e3dcf7f59778151299f74821a1a152bc387a2e78a6fad7e41dea`
5. `docs/design/semantic_ingestion_architecture.md` SHA-256 `83a9fe92adde7cb45072c8d2b8aa43c0eaa68df456df0c4aab35f9002af14364`
6. Frozen proposal baseline and measured diagnostic evidence
7. Current production code and tests as feasibility and behavior evidence

## Independently Reconstructed Requirements

| Requirement | Source | Design coverage | Acceptance criteria | Verification | Status |
| --- | --- | --- | --- | --- | --- |
| CEP-01 Preserve every domain-bound content body digest exactly | governing canonical contracts and proposal objective | contradictory | named body bytes, domain, digest field, and legacy vector agree | differential body vectors | changes required |
| CEP-02 Preserve typed semantic-envelope bytes and persisted payload digests exactly | storage/event contracts | partial | exact envelope schema/kind/bytes and payload SHA-256 agree | persisted differential vectors | changes required |
| CEP-03 Reject malformed, forged, copied, substituted, wrong-domain, wrong-type, and wrong-version inputs before effect | universal fail-closed invariant and current encoder | partial | closed issuer/verifier rule and zero-effect negative matrix | contract and integration mutations | changes required |
| CEP-04 Eliminate repeated descendant construction at the measured codec/validation sites | proposal objective and diagnostic | missing | exact callsite mechanism and bounded per-key counts | attributed construction counters | changes required |
| CEP-05 Preserve full cross-member closure, ordering, cardinality, and provenance validation | semantic-ingestion architecture | partial | member evidence cannot replace closure validation | normal/reopen corruption matrix | changes required |
| CEP-06 Preserve current lease, fence, epoch, scope, writer, tenant, and CAS checks | storage and transaction designs | unclear | representation evidence is explicitly non-authorizing | stale/foreign/concurrent mutations | changes required |
| CEP-07 Scope ephemeral evidence to exact operation/generation/request lifetime | replay and recovery requirements | missing | owner, lifetime, invalidation, memory/count bounds are explicit | retry/reopen/concurrency tests | changes required |
| CEP-08 Preserve exact checkpoint idempotency and no-duplicate-effect recovery | current graph transaction contract | partial | same bytes/digests, one effect, exact reload, bounded retry | pre/post-write lost-ack matrix | changes required |
| CEP-09 Prove exact compatibility separately from performance | testing/evidence rules | partial | frozen oracle covers bytes, digests, values, errors, state, effects | independent differential report | changes required |
| CEP-10 Demonstrate material runtime improvement without unbounded retention | proposal goal and operability lane | missing | fixed workload, counter rules, runtime and peak-byte thresholds | controlled repeated benchmark | changes required |

## Contract And Evidence Boundaries

The current authority chain is:

1. `_ContentAddressedContract` computes a declared digest over
   `domain + NUL + CTV(canonical body)`.
2. `encode_semantic_contract` revalidates the typed value, then encodes a
   separate schema/kind/payload envelope.
3. generation members retain those envelope bytes and independently bind their
   payload digest.
4. source-normalization reload verifies member sets, ordering, payload hashes,
   envelope type/kind, typed semantics, and cross-member closure.
5. graph planning and checkpoint persistence add current ingress, scope,
   fence, lease, writer, epoch, generation, and idempotency authority.

An optimized representation may attest immutable representation only. It may
not become durable authority, authorize a write, replace closure validation,
or survive a persisted reload without re-establishing trust from durable bytes.

Evidence maturity remains `specified` only. Current code is implemented and
the diagnostic is locally observed, but no optimized implementation or
candidate-bound differential evidence exists.

## Confirmed Findings

### DREV-001: Canonical evidence conflates body, envelope, and persisted identities

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: architecture and compatibility
- Affected scenario and prevalence evidence: every ordinary persisted semantic-ingestion member in source normalization, graph checkpoint, retry, and replay; no current product defect is asserted because this is a design review
- Design location: proposal steps 3 through 5
- Governing source or requirement: CEP-01 and CEP-02; canonical storage and event identity requirements
- Expected behavior: domain-bound body bytes/digest, typed envelope bytes/payload digest, envelope schema/kind, concrete type, and version remain distinct and exact
- Design behavior: `VerifiedCanonicalContract` specifies one `canonical_bytes` and one `digest`, and persisted load says it verifies a digest from those bytes without naming the identity role
- Evidence: `contract_digest` hashes the canonical body with a domain; `encode_semantic_contract` emits a schema/kind envelope; source-normalization members independently verify SHA-256 of the envelope payload
- Impact: an implementation can reject valid persisted members, accept envelope substitution, change existing digest values, or claim compatibility while comparing the wrong preimage
- Root invariant or contract boundary: content-body identity, semantic-envelope identity, and persisted-member identity are separate commitments
- Equivalence class and adjacent bypasses inspected: body digest construction, semantic envelope encode/decode, graph native member envelope, source-normalization member payload, checkpoint manifest, retry reload, and group-result record
- Positive behavior that must remain valid: all current body digest fields, digest domains, envelope bytes, envelope kinds/schemas, member payload digests, and rejection behavior
- Recommended invariant-level resolution: define a closed evidence algebra with separately named `content_body_bytes`, `content_digest_domain`, `content_digest`, `wire_bytes`, `wire_schema`, `wire_kind`, and `wire_payload_digest`; specify which fields exist and which owner consumes them; prohibit aliases between roles
- Verification needed: fixed vectors independently mutate body, body digest/domain, envelope payload, kind/schema/type/version, and persisted payload digest, preserving the legacy failure boundary
- Evidence maturity affected: specified, derivable, and locally verified

### DREV-002: The wrapper does not intercept the recursive descendant work

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: runtime architecture
- Affected scenario and prevalence evidence: the ordinary V3 provider path shared by direct, factory, filesystem, and Hermes roots; the diagnostic observed 42,343 digest constructions for 330 distinct domain-and-digest results
- Design location: proposal steps 3 through 8
- Governing source or requirement: CEP-04 and the stated performance objective
- Expected behavior: the mechanism reuses an already verified descendant at every decode and nested validation site responsible for the measured amplification
- Design behavior: the proposal wraps completed contracts and passes them between selected repositories, but defines no codec/validator integration for descendants embedded again in lanes, normalization core, atomic request, graph request, or checkpoint members
- Evidence: source-normalization reload decodes standalone lane members and then decodes larger members embedding those values; parent content validators canonicalize complete descendant trees; repository and atomic boundaries reconstruct full requests again
- Impact: an implementation can add wrapper complexity and memory retention while leaving the dominant recursive work intact
- Root invariant or contract boundary: reuse must be owned where canonical trees and nested typed models are constructed, not only after complete parent objects exist
- Equivalence class and adjacent bypasses inspected: fresh normalization, member decode, core/result/request decode, repository publication, graph checkpoint publication, idempotent reload, retry manifest, group commit, and terminal reload
- Positive behavior that must remain valid: every unique untrusted or persisted envelope is decoded and semantically validated before use; no validation result comes from ambient or cross-operation state
- Recommended invariant-level resolution: specify a bounded invocation-scoped evidence arena integrated with the canonical codec and nested model construction, keyed only after wire canonicality and payload identity are verified; define exact producer/consumer callsites, allowed reuse, limits, invalidation, and fallback to full validation
- Verification needed: attributed counters for duplicated lane/core/request descendants on fresh, reopen, retry, and corruption paths; each allowed key is constructed within its declared bound and every mutation still fails
- Evidence maturity affected: specified, derivable, implemented, and locally verified

### DREV-003: Trusted handoff lacks a closed issuance, immutability, and authority rule

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: security, transactions, and lifecycle
- Affected scenario and prevalence evidence: forged `model_construct` or unsafe `model_copy` values, stale or foreign authority, acknowledgement-loss retry, and concurrent same- or different-operation execution
- Design location: proposal steps 3 through 8
- Governing source or requirement: CEP-03, CEP-05, CEP-06, and CEP-07; fail-closed validation and transaction authority requirements
- Expected behavior: only named producers issue representation evidence; consumers verify exact value/byte identity; evidence is immutable, operation-scoped, and non-authorizing; all dynamic authority checks remain immediate before CAS
- Design behavior: “private frozen” and “verify evidence metadata” do not define an issuer capability, deep immutability, value-to-byte binding, callsite allowlist, lifetime, invalidation, or dynamic-authority split
- Evidence: current semantic encoding deliberately revalidates to reject forged model copies and constructs; atomic checkpoint publication separately validates current ingress, scope, fence, lease, writer, epoch, generation, and idempotency under the linearized transaction
- Impact: an implementation can trust a wrapper whose value differs from its bytes, reuse evidence after authority changes, bypass cross-member closure, or turn representation validity into stale write authority
- Root invariant or contract boundary: immutable representation evidence is distinct from current authorization and durable recovery authority
- Equivalence class and adjacent bypasses inspected: new seal, persisted load, direct wrapper construction, forged value/bytes, nested mutation, repository handoff, partial member closure, stale lease/epoch/fence, cross-tenant retry, same-key concurrency, and process reopen
- Positive behavior that must remain valid: forged and malformed input fails before store access or effect; every reopen re-establishes trust from durable bytes; dynamic authority is rechecked immediately before write; retry remains exactly idempotent
- Recommended invariant-level resolution: define a closed typestate and production-binding table naming issuer, input trust class, evidence roles, exact consumer, lifetime, invalidation, mandatory closure checks, and mandatory dynamic checks; direct/unknown evidence takes the full validation path
- Verification needed: per-callsite forged-wrapper/value mismatch, wrong role/domain/type/version, nested substitution, partial/reordered closure, stale authority, cross-tenant, concurrent same-key/different-key, and reopen tests with zero unauthorized effect
- Evidence maturity affected: specified, derivable, implemented, and locally verified

### DREV-004: Correctness, performance, and resource acceptance are not falsifiable

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: evidence_action
- Confidence: high
- Finding type: verification and operability
- Affected scenario and prevalence evidence: all proposed optimized paths, especially deeply nested normalization authority and retry-held checkpoint evidence
- Design location: proposal steps 1, 2, 9, and 10 plus measured baseline
- Governing source or requirement: CEP-08, CEP-09, CEP-10 and repository evidence-maturity rules
- Expected behavior: a revision-bound corpus, observer, workload, category rules, allowed residual counts, runtime sampling protocol, numerical thresholds, and retained-memory bounds make both compatibility and performance independently falsifiable
- Design behavior: the proposal gives one in-memory count and qualitative requirements for “no unexplained” work and “material” improvement without a command, fixture identity, category algorithm, threshold, or peak-memory bound
- Evidence: current persistence/recovery tests prove the reconstruction path, not the proposed mechanism; the 42,343/330 measurement is not bound to a repository runner or result artifact; retained bytes can trade CPU for unbounded memory
- Impact: an implementation can move work to an uninstrumented path, omit recovery variants, retain every descendant indefinitely, or improve profiled counters without improving ordinary latency
- Root invariant or contract boundary: compatibility proof, authority proof, runtime performance, and resource bounds are separate evidence classes
- Equivalence class and adjacent bypasses inspected: valid/invalid body and envelope, flat/deep/repeated descendants, fresh/reopen/retry, success/failure cleanup, direct/factory/filesystem/Hermes, in-memory/JSONL, and concurrent operations
- Positive behavior that must remain valid: no global cache, no timeout substitution, exact bytes/digests/state/effects, and full trust-boundary validation
- Recommended invariant-level resolution: freeze the legacy oracle and benchmark fixture; define category-level construction budgets, fixed normal/recovery matrices, median/p95 unprofiled latency, profiled attribution, peak retained bytes, cleanup, and concurrency limits before implementation
- Verification needed: deterministic old-versus-new compatibility report plus a separate repeated performance/resource report over the fixed workload and environment
- Evidence maturity affected: specified, derivable, locally verified, independently reproduced, and CI enforced

## Requirements Coverage

CEP-01 through CEP-10 were inspected across direct body construction, semantic
envelope encoding/decoding, normalization publication/reload, graph checkpoint
publication/reload, retry/recovery, forged values, concurrency, and performance
measurement. No requirement is complete enough for implementation. Findings
DREV-001 through DREV-004 cover the complete known family rather than isolated
callsite examples.

## Architecture And Feasibility

The objective is feasible without wire or digest changes, but not through the
proposed outer wrapper alone. A viable revision requires:

1. distinct typed identity roles for content body and wire/persisted envelope;
2. a bounded invocation-scoped evidence arena integrated with codec and nested
   validation construction;
3. verified issuance and exact lifetime/invalidation rules;
4. explicit preservation of closure and dynamic transaction checks;
5. fallback to full validation for every unknown or mismatched evidence case.

This is a material architecture revision and requires a new full review
baseline after `$build-design` remediation.

## Failure, Security, And Operations

The current proposal does not specify behavior for fabricated evidence,
value/byte disagreement, stale evidence, generation replacement, cross-tenant
reuse, concurrent operations, memory exhaustion, or cleanup after exception.
All must fail closed or fall back to full validation without creating durable
effects. Representation evidence must never authorize a write or become a new
persisted truth source.

## Verification And Evidence Maturity

The proposal is partly specified but not derivable. Current implementation and
tests establish legacy behavior only. The diagnostic establishes a hotspot and
duplicate-result cardinality but is not a revision-bound benchmark. There is no
optimized local, independent, CI, or operational evidence.

Required proof must keep separate:

- body digest equivalence;
- envelope and persisted payload equivalence;
- semantic and anti-forgery equivalence;
- closure and transaction-authority equivalence;
- recovery/effect equivalence;
- construction-count reduction;
- unprofiled latency;
- peak retained memory and cleanup.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Residual risk | Status |
| --- | --- | --- | --- | --- | --- |
| identity-role aliasing | one bytes/digest pair represents body and envelope | rejection, substitution, or compatibility break | closed multi-role evidence algebra | low after vectors | open |
| incomplete speedup | wrapper added after descendant construction | complexity and memory without runtime gain | codec-integrated attributed mechanism | medium until prototype | open |
| validation bypass | forged or stale wrapper accepted | unauthorized or corrupt persistence | closed issuer/consumer typestate and fallback | low after adversarial proof | open |
| stale authority reuse | representation evidence treated as authorization | incorrect CAS/retry result | preserve all dynamic checks separately | low after concurrency proof | open |
| memory amplification | every nested byte representation retained | latency, OOM, or denial of service | bounded arena, lifetime, peak-byte gate | medium until measured | open |
| benchmark gaming | counters move outside observer | false performance claim | fixed external observer and wall/CPU/memory evidence | low after independent reproduction | open |

## Rejected Or Consolidated Findings

- The initial missing-baseline governance finding is already addressed by the
  frozen proposal SHA-256 recorded in this report; it is not an open finding.
- Reviewer body/envelope findings are consolidated into DREV-001.
- Reviewer forged-wrapper, stale-authority, lifecycle, reopen, and concurrency
  findings are consolidated into DREV-003.
- Reviewer corpus, matrix, threshold, and resource findings are consolidated
  into DREV-004.
- No P1 or P2 product defect is assigned. This review evaluates an unimplemented
  design; the determinate architecture and evidence defects still require
  correction before approval.

## Required Changes Before Approval

1. Replace the single byte/digest tuple with a closed, role-separated evidence
   algebra covering body, wire envelope, and persisted payload identities.
2. Specify a codec/validator-integrated reuse mechanism that intercepts the
   measured descendant reconstruction rather than only wrapping parent values.
3. Define exact trusted producers/consumers, issuance, deep immutability,
   lifetime, invalidation, limits, fallback, closure validation, and dynamic
   authority preservation.
4. Freeze production-entrypoint bindings and a falsifiable differential,
   recovery, concurrency, performance, and retained-memory acceptance matrix.

## Non-Blocking Follow-Ups

None. The identified work is required for implementation readiness and must not
be deferred as optimization polish.

## Final Outcome

**Changes required.** The design goal is valid and conditionally feasible, but
the frozen proposal cannot yet guarantee either performance improvement or
preservation of core promises. No bounded implementation slice or parent
milestone is approved by this report.

## Review Limitations

No production implementation or optimized prototype exists, so feasibility is
established from current ownership and code paths rather than measured optimized
behavior. One correctness reviewer reported 13 focused legacy tests passing;
that result was not rerun by the coordinator and is treated only as reviewer
context, not closure evidence. The review does not assess M4, graph traversal,
or unrelated terminal-persistence performance.
