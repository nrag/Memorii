# M0A Trust Artifact And Complete Generation Design Closure

- Work ID: semantic-ingestion-m0a-trust-artifact-closure-2026-07-28
- Work type: design
- Status: ready for fresh design review
- Coordinator: Codex main thread
- Created: 2026-07-28
- Last updated: 2026-07-28 (C2 remediation round-2 review baseline)
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/traceability-design.plan.md`; `docs/work/semantic_ingestion/traceability-registry-closure-2026-07-27/design-revision.plan.md`
- Canonical inputs: baseline `docs/design/semantic_ingestion_architecture.md`
  at SHA-256 `f277fb262b2f8335aad4207f511942c5680510ff827b0291fe9c9ff4b0af6ea6`;
  drafted D1 exceptional-remediation-round-4 revision at SHA-256
  `db5a6bc7a9a02c0b71e08ea20d2b351280c0f0db63909a2d68e7712c30029e03`;
  approved signature-corrected baseline at SHA-256
  `158277cd433c85714253359e134c94ece0f3ad59d2b3f1b9a403c295417a397e`
- Expected outputs: the smallest reviewed design correction that makes the remaining SIA-R03/SIA-R13 M0A contract implementable without invented trust or artifact semantics

## Objective

Close the exact trust-artifact and complete-generation specification gaps that
block M0A implementation. The revised design must define every byte-backed
artifact, canonical preimage, signature binding, durable pointer transition,
and topological verification step needed for the public approval gate.

## Completion Contract

The design completion contract in `.agent/PLANS.md` applies. Completion also
requires:

- a closed release-bound trust-snapshot schema and canonical preimage;
- a closed signed durable active-release-pointer schema, digest/signature
  preimage, persistence owner, atomic advance, restart and recovery semantics;
- a closed signed lifecycle-root envelope consistent with the design prose;
- one unambiguous canonical typed-value/profile rule for every signed or
  digest-bearing traceability artifact;
- a closed complete-generation manifest or equivalent byte-backed DAG contract
  that lets the public approval gate load and independently recompute the
  structural, coverage, execution, trust, release, and pointer artifacts;
- measurable mutation, restart, concurrency, substitution, and incomplete
  generation acceptance criteria;
- fresh independent `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer` review with no confirmed `blocks_approval` or
  `changes_required` finding in this bounded scope.

## Scope

Included:

- SIA-R03 and SIA-R13 traceability trust artifacts and complete-generation
  approval only;
- exact schemas, canonical bindings, lifecycle, persistence, recovery, and
  verification semantics necessary to implement the existing approved
  behavior.

Excluded:

- M0B provider-envelope compatibility;
- M1+ semantic result lookup;
- external authority identities, keys, signatures, or production values;
- unrelated ingestion, retrieval, storage, provider, or benchmark redesign.

Deferred:

- externally issued operational acceptance artifacts under
  `SIA-ED-TRACEABILITY-001`; deterministic validators and typed unavailable
  behavior remain required.

## Constraints And Invariants

- Acceptance authority remains outside production packages and composition.
- No release, trust snapshot, registry source, coverage approval, execution
  record, or caller-supplied key may bootstrap its own authority.
- Every artifact is closed, typed, canonical, domain-separated, content
  addressed, and loaded by exact digest.
- Readers observe either the prior complete generation or the new complete
  generation; no partial generation may authorize.
- Rollback is a new higher-sequence signed release, never pointer rewind.

## Sources Of Truth

Precedence follows `AGENTS.md`. The affected governing sources are:

- `docs/design/memorii_spec.md`
- `docs/design/memorii_storage_details.md`
- `docs/design/event_model.md`
- `docs/IMPLEMENTATION_RULES.md`
- `docs/design/semantic_ingestion_architecture.md`
- `.agent/PLANS.md`
- `.agent/skills/build-design/SKILL.md`
- `.agent/skills/review-design/SKILL.md`

## Current State

Verified facts:

- The frozen design defines release, bootstrap, recovery-policy, lifecycle
  record, structural, coverage, and execution schemas.
- It requires a release-bound trust snapshot and signed durable active pointer
  but defines neither artifact's closed schema or canonical preimage.
- `TraceabilityTrustLifecycleRoot` lacks signature fields although governing
  prose calls it signed.
- Current implementation uses locally invented pointer/lifecycle envelopes and
  cannot load or independently recompute the complete artifact generation.

Interpretation:

- These are governing design gaps. Implementing the remaining M0A contract
  against the current baseline would require unauthorized semantic invention.

## Assumptions And Open Questions

Verified:

- External root values remain outside this design and are not required for
  deterministic schema/validator implementation.

Working assumptions:

- The smallest correction extends the existing typed traceability schema
  inventory rather than introducing a second trust system.

Unresolved:

- None within the bounded schema closure. External operational artifact values
  remain deliberately unresolved under `SIA-ED-TRACEABILITY-001`.

External decisions:

- None for schema closure. `SIA-ED-TRACEABILITY-001` supplies values only.

## Milestones

### D1 - Close trust artifacts and generation semantics

- Purpose: make R03/R13 implementable without locally invented formats.
- Scope: exact schemas/preimages, generation DAG, durable pointer/CAS/recovery,
  trust snapshot, lifecycle-root envelope, failure semantics, verification.
- Expected artifact: revised
  `docs/design/semantic_ingestion_architecture.md`.
- Verification: targeted schema/architecture/test review followed by fresh
  three-role independent review.
- Status: ready for fresh design review.

## Progress Log

- 2026-07-28: M0A implementation resumed by user authorization. Independent
  exploration and spec audit confirmed four remaining gaps. Direct inspection
  confirmed missing trust-snapshot and active-pointer schemas, lifecycle-root
  signature mismatch, and absent complete-generation byte closure.
- 2026-07-28: D1 writer added the smallest canonical design closure: closed
  release-bound trust snapshot, signed lifecycle-root envelope, signed durable
  active-pointer/CAS contract, and one pointer-bound complete-generation
  manifest with independent topological reconstruction and typed unavailable
  versus rejected outcomes. Added explicit profile/binding boundary and
  measurable mutation/restart/concurrency/production-isolation acceptance
  criteria. No production or test artifact was changed.
- 2026-07-28: D1 review round 1 confirmed eight closure defects. Remediation
  defines immutable release and pointer histories, release-state overlays,
  complete trust histories, closed generation-member union and coordinate/DAG
  rules, exact purpose-scoped signer coordinates and signature preimages,
  durable index/lease/watermark semantics, and independently authored golden
  vectors. The canonical registry source now registers headings 3.23.4.2-.4
  and the unique `SIA-I319` anchor.
- 2026-07-28: D1 review round 2 confirmed nine determinate closure findings.
  Remediation replaces self-referential lifecycle eligibility with prior-root
  or independently provisioned genesis references; binds coverage/evidence to
  the exact release snapshot; closes raw design, report/environment/test/result
  member encodings; adds recovery-policy and lifecycle-record signature
  preimages; closes store-owned reader authorization/time/lease/watermark
  semantics; and defines the independently authored golden-vector manifest.
- 2026-07-28: D1 review round 3 confirmed three remaining determinate closure
  findings. Final-budget remediation closes domain-separated stdout/stderr
  stream artifacts including explicit empty and alias policy, makes every
  independently authored typed input a generation member, supplies a canonical
  non-runtime golden-vector source package, and defines finite G1-to-G2-to-G3
  historical-manifest loading, retention, rejection, and vector semantics.
- 2026-07-28: After round-3 non-convergence, the user explicitly authorized
  one exceptional bounded fourth remediation and fresh review. The sole writer
  corrected exactly the six recorded gaps: lifecycle-root signer selection,
  independently durable index anti-rollback fencing, disjoint generation-member
  discriminators, versioned golden-fixture schema identity, independently
  elaboratable exact vector inputs/mutations, and unambiguous G1/G2/G3 counts.
- 2026-07-28: The user explicitly authorized a final bounded fifth round for
  golden-source materialization only. Closure inspection found that exact
  accepted vectors cannot be independently authored from the approved sources:
  the repository publishes neither concrete canonical profile-registry entries
  nor a deterministic nonoperational signature fixture. The writer stopped
  without fabricating bindings/signatures or using implementation code as an
  oracle.
- 2026-07-28: The user authorized a bounded design correction for that blocker.
  The design now fixes exact grammar and schema-inventory byte regions, a
  primitive non-circular profile/entry/registry digest construction, 52 closed
  M0A schema coordinates, component-source and digest rules, the deterministic
  RFC 8032 Ed25519 profile and three published test keys, and an acyclic finite
  non-authoritative trust-ancestry recipe. Operational trust remains external.
  Materialization must use two independent elaborators and replace every
  schematic body, alias, and placeholder signature before M0A can pass.
- 2026-07-28: A one-character transcription error was found in the
  `fixture-bootstrap-1` reference signature table. The old table value had
  129 hex characters, was invalid hex, and could not represent any byte
  sequence; it contradicted the normative 64-byte RFC 8032 profile and
  published empty-message vector. The sole writer removed the extra `5`,
  preserving all other design semantics and leaving production and C1 files
  untouched. This changes the raw design SHA-256 from
  `9c439884c67eeef05a58dbf51ae890280a6daa1fef266a56be5ae1971c0e58f2` to
  `158277cd433c85714253359e134c94ece0f3ad59d2b3f1b9a403c295417a397e` and
  invalidates the digest-bound C1 pinned output pending regeneration.

## Evidence Log

- Frozen design digest:
  `f277fb262b2f8335aad4207f511942c5680510ff827b0291fe9c9ff4b0af6ea6`.
- Existing focused R03/R13 suite passes 37 tests but uses placeholder structural,
  coverage, and execution roots and therefore does not prove closure.
- Architecture map:
  `verify_registered_approval_execution()` does not receive structural,
  coverage, execution-root, approval, or evidence-record bytes.
- `git diff --check` after the design edit exits 0. The design now owns the
  previously invented pointer/lifecycle/generation semantics; implementation
  remains intentionally unmodified until review freezes this revision.
- Drafted design checksum after final consistency scan:
  `6deafb63fdadcd5d412db6676bca8fab7f0bc3686295f27731fc2afe7236e266`.
- Canonical registry source checksum:
  `38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`.
- Canonical golden-vector source raw SHA-256:
  `64c109e6ed1eed71e3d0a577fdd363a5396597783ccdb3aff427ff4ec844b9da`.
- Canonical golden-vector source content identity
  (`SHA-256("memorii:sia-traceability-golden-vector-source:v1\\0" ||
  source_bytes)`):
  `8ca60c8166c810cc4a8f42b0b831d94c7072fb2638d525dac42d17aee5e3fa77`.
- Independent extraction emits 147 unique heading hashes; the registry has
  exactly 147 unique nonempty defaults and 19 unique anchor bindings.
- The registry bytes equal fresh `canonical_document(json.loads(bytes))`
  byte-for-byte. The golden-vector source bytes equal fresh canonical compact
  JSON plus one terminal newline byte-for-byte. `git diff --check` exits 0.
- The current registry loader predictably rejects the new 147-heading source
  because implementation and focused tests still hard-code the obsolete count
  144. That is an M0A implementation change, not a reason to omit the three
  new normative headings from the design-owned source package.
- Exceptional round-4 structural checks pass: design and registry contain the
  same 147 unique numbered headings/defaults; `SIA-I319` occurs once in the
  design and once in registry bindings; all 28 generation-member discriminator
  tags are unique; the canonical golden source has 10 sorted unique fixtures
  and 25 sorted unique vectors, no dangling fixture reference, canonical
  base64, byte-derived expected digests, exact `1/0`, `2/1`, `3/2` G1/G2/G3
  total/historical counts, and zero ordinary historical traversal.
- Frozen exceptional-round-4 design SHA-256:
  `db5a6bc7a9a02c0b71e08ea20d2b351280c0f0db63909a2d68e7712c30029e03`.
- Round-5 audit: the binding formula requires concrete profile/grammar digest,
  schema fingerprint, enum registry, optional-field policy, numeric-spec
  registry, digest/signature exclusion policy, and decoder digest values for
  every schema. Repository search finds only their conceptual definitions.
  `signature_profile_id` remains unconstrained text, and no algorithm,
  deterministic parameters, nonoperational keys, or reference signatures are
  published. Exact schema-valid envelopes, preimages, and signatures therefore
  cannot be independently materialized or double-elaborated.
- Revised design SHA-256 after the fixture-authority correction:
  `9c439884c67eeef05a58dbf51ae890280a6daa1fef266a56be5ae1971c0e58f2`.
- Independent standard-library elaboration from only the marked design bytes
  produces raw design identity
  `1d5611950b822ce15392f955d0ecab61c4f47b1a79fdb3127522a77232e1185a`,
  905 grammar bytes and grammar digest
  `c870cf8d68545e9eaf1d534726f9207aee9b6085be7da5006de9e2ad82e276f9`,
  2,293 inventory bytes and inventory digest
  `c44fb9e09d0f65642af69fdcccc38ee41307096f712f7b273148571b59b20277`,
  profile digest
  `fd85f9d328df8585a063517fe0478f1f904f7874ae06a46aee1a0cdfb20fd5b9`,
  and 52-entry registry digest
  `1768410c6279cd8f9e15d318b2b9c175e416bad4ada437dd924ce6e5ec965a7d`.
- The closed M0A typed schema inventory contains 52 unique Unicode-scalar
  sorted coordinates. Its exact bytes and the profile grammar bytes are
  delimited by unique standalone markers and exclude Markdown fence bytes.
- OpenSSL independently reproduced the public keys for all three published RFC
  8032 seeds and reproduced both non-empty reference signatures. The empty
  message signature remains the published RFC 8032 vector; the installed
  OpenSSL `pkeyutl` rejects zero-byte input before signing and therefore cannot
  serve as its local re-elaborator.
- OpenSSL independently derived successor bootstrap key
  `30526b2d745e0bdffd9d0f60d8215221a924203660c7582d9f952300419638ed`
  from the design-fixed seed and reproduced its one-byte-message reference
  signature. A separate Node implementation independently reproduced the same
  52-entry profile-registry digest as the Python standard-library elaboration.
- `git diff --check` exits 0 after the correction. No production source or test
  file was changed by this design operation.
- Focused traceability-registry tests report 6 passed and 20 failed. Every
  failure enters through the pre-existing implementation constant requiring
  exactly 144 heading defaults while the already revised canonical registry
  contains 147. This is the implementation mismatch already recorded above;
  it is not caused by the fixture-authority section and was not changed during
  this design-only operation.
- Signature-table correction evidence: the old
  `fixture-bootstrap-1` reference signature contained
  `...2249015555fb...`, 129 hex characters and therefore invalid hex. The corrected value is
  the published RFC 8032 empty-message vector
  `...224901555fb...`, 128 hex characters / 64 bytes, and direct decoding
  confirms `hex_length=128`, `byte_length=64`, and exact vector equality.
- The existing OpenSSL review evidence remains applicable: it independently
  reproduced the three published RFC 8032 public keys and both non-empty
  reference signatures, while the installed `pkeyutl` rejects a zero-byte
  signing input. The corrected empty-message value is therefore verified
  against the published RFC 8032 vector, not newly attributed to that local
  OpenSSL invocation.
- `git diff --check` exits 0 after the signature correction. The focused C1
  fixture-authority suite reports 6 passed and 1 expected failure: its pinned
  `c1-v1.expected.json` output SHA-256 remains
  `3d1bb02bffdb2db17d41269394d69284234e2aebdcd9348a93a3419b6b1e575e`,
  whereas both current elaborators produce
  `f2f16fd6014baf71aafe21acbd174aaee8fbd61fa7657fbfec3326499c9a2826` and
  a design-document digest of
  `73682f757212da1bef14d6348304f92cbccc0155fd2b3bd557e60e5bc40a601c`.
  This is the intended invalidation of the C1 baseline; regeneration is
  deferred and no C1 file was changed.

## Decision Log

- Decision: pause M0A implementation and run linked `$build-design` /
  `$review-design` closure.
- Alternatives: locally infer formats from current code; weaken the approval
  gate; define the missing contracts in the canonical design.
- Rationale: only the third alternative preserves source precedence,
  independent verification, and fail-closed trust semantics.
- Consequence: implementation remains paused until the revised baseline passes
  independent design review.
- Decision: represent a complete acceptance publication with
  `TraceabilityApprovalGenerationManifest` plus a minimal signed CAS pointer,
  rather than copying an artifact-coordinate tuple into every pointer.
- Alternatives: pointer-bound closed tuple; a manifest plus pointer-bound
  pointer digest; manifest plus pointer intent.
- Rationale: the tuple duplicates closure semantics at all readers; embedding
  a pointer digest in a manifest whose digest is named by the pointer creates a
  fixed-point cycle. The selected manifest binds topologically ordered immutable
  members and a pointer intent, while the pointer binds the completed manifest.
- Consequence: public verification has one immutable closure proof and a
  cycle-free pointer reconstruction; the active pointer remains the sole
  mutable acceptance coordinate.
- Decision: immutable release envelopes always retain
  `issued_state=active`; one signed content-addressed release history is the
  authority for later superseded/revoked/compromised state.
- Alternatives: rewrite/resign prior releases; infer state from the current
  pointer; immutable release plus signed history overlay.
- Rationale: rewriting breaks content identity, while pointer inference cannot
  reconstruct revocation or historical state. The selected overlay preserves
  immutable bytes and replayable monotonic state.
- Consequence: R1 remains byte-identical when R2 supersedes it; public approval
  must load the complete release history and reject a missing/forked prefix.
- Decision: `active_pointer_intent` is inline non-member manifest data; the
  signed candidate pointer is appended to immutable pointer history only after
  the manifest exists.
- Alternatives: separately address the intent; include candidate pointer as a
  generation member; inline intent.
- Rationale: member inclusion creates a digest fixed point, while a separate
  intent adds an unnecessary authority-like artifact. Inline intent binds the
  transition without recursion.
- Consequence: the current index selects signed pointer history; the pointer
  selects the completed manifest; no artifact bootstraps its own digest.
- Decision: derive signer eligibility deterministically from complete trust
  histories and the prior verified lifecycle root rather than introducing a
  second signer-eligibility snapshot artifact.
- Alternatives: opaque eligibility digest; separately signed eligibility
  snapshot; explicit prior-state derivation.
- Rationale: an opaque digest is unverifiable and a second snapshot duplicates
  release-trust state. Prior-state derivation is acyclic, independently
  replayable, and gives genesis one separately provisioned case.
- Consequence: lifecycle records cannot cite their own record/root; revoke and
  compromise authenticate under pre-transition eligibility and deny all
  post-transition issuance immediately.
- Decision: golden vectors are one versioned, content-addressed,
  independently authored verification fixture pinned by release and generation,
  never runtime authority.
- Alternatives: codec-generated expectations; prose-only examples; independent
  pinned vector source.
- Rationale: only the independent source detects shared encoder/verifier defects
  without creating a new trust root.
- Consequence: every new body, preimage, envelope, field, and tamper has exact
  bytes and verdicts, while operational authority remains solely external under
  `SIA-ED-TRACEABILITY-001`.
- Decision: treat stdout and stderr as distinct domain-separated raw generation
  artifacts and require one explicit member of each kind for every selected
  runner report.
- Alternatives: embed streams in the report envelope; omit empty streams;
  address both streams under one generic raw-blob kind.
- Rationale: separate addressed members preserve exact runner evidence,
  distinguish empty from absent output, and make cross-stream substitution and
  unauthorized cross-report aliasing measurable.
- Consequence: registry artifact policy explicitly controls exact-byte sharing,
  while default policy forbids it; stream membership and dependencies are
  derived rather than caller-selected.
- Decision: make historical generation-manifest coordinates terminal for
  current-generation membership while requiring exact historical manifest
  bytes to remain loadable and independently verifiable.
- Alternatives: recursively import every historical generation member; trust
  pointer digests without loading historical manifests; finite manifest-only
  predecessor verification.
- Rationale: recursive import creates unbounded/fixed-point closure, while
  digest-only trust cannot detect missing or substituted repository bytes.
- Consequence: G1/G2/G3 require exactly one/two/three total manifest loads,
  historical manifests and pointer bytes remain retained, and older ordinary
  members may be collected only below the signed watermark with no lease.
- Decision: bind current-index publication to a separately durable monotonic
  fence/minimum-generation record.
- Alternatives: trust signed pointer history alone; sign the mutable index;
  store a generation and predecessor-linked fence in an independent
  anti-rollback failure domain.
- Rationale: signatures do not prevent replay of valid old bytes, while the
  independent monotonic minimum detects restoration of an internally valid old
  index/history/fence backup.
- Consequence: pointer publication compares and advances index and fence
  together; indeterminate coupling is unavailable, restored older generations
  reject, and byte-identical lost-ack replay is idempotent.
- Decision: correct only the `fixture-bootstrap-1` reference-signature literal
  to the normative published RFC 8032 64-byte empty-message vector.
- Alternatives: retain the malformed 129-hex-character table literal; use the normative
  RFC 8032 vector named by the profile and the published test vector.
- Rationale: retaining the literal leaves the table internally contradictory
  and makes the stated `R || S` 64-byte contract impossible to reproduce. The
  normative vector is independently specified by RFC 8032 and agrees with the
  existing OpenSSL/public-key review evidence without changing any other
  trust, schema, profile, or lifecycle semantics.
- Consequence: the frozen design and all digest-bound C1 outputs require a new
  baseline. C1 regeneration is deliberately deferred to the fresh targeted
  review; production code and C1 fixture files remain outside this correction.

## Review Log

- Preimplementation `spec_auditor`: confirmed missing pointer/trust-snapshot
  contracts, lifecycle-root signature mismatch, reduced structural artifact,
  incomplete generation loading, and nondurable watermark.
- Coordinator disposition: the first group is a design ambiguity and blocks
  implementation; the latter implementation gaps remain deferred until the
  design correction is approved.
- D1 writer disposition: the bounded ambiguity is drafted for fresh independent
  review; no external key, identity, signature, release, or trust-root value
  was invented.
- D1 review round 1: all findings confirmed as `changes_required` in the
  bounded R03/R13 design scope. Remediation covers release/pointer histories,
  closed member union and raw-byte members, purpose-scoped signer/preimage
  schemas, coverage/evidence body formulas, complete trust histories,
  index/CAS/lease/watermark recovery, golden vectors, and canonical registry
  heading/anchor updates. No requirement was weakened.
- D1 review round 2: all nine bounded findings confirmed as
  `changes_required`. The design now has exact prior-state lifecycle signer
  references and genesis behavior, purpose equality across bodies/preimages/
  coordinates, exact trust-snapshot equality, raw design preimage and strict
  bytes, deterministic eligibility derivations, closed registry/raw/typed
  evidence members, recovery-policy signing, acceptance-store-only durable
  leases/watermarks/time witnesses, and a versioned pinned golden-vector
  source/schema/digest. The loader's 144 count and public-gate implementation
  remain implementation tasks and were not treated as design findings.
- D1 review round 3: the three bounded findings were confirmed as
  `changes_required`. Remediation adds closed stream and typed-fixture
  generation members, exact domains/coordinates/schema bindings/ownership/
  dependencies/cardinality, explicit-empty and no-alias defaults, finite
  historical-manifest successor closure and GC rules, typed failure codes, and
  independently authored successor/stream vectors in the canonical source
  package. No production code or tests were changed.
- D1 non-convergence review: all six findings were validated as
  `Not applicable / changes_required`. The user authorized one exceptional
  bounded fourth round. Each finding now has a determinate design correction
  and exact vector/check evidence; none was dismissed, downgraded, or expanded
  into adjacent implementation scope. Fresh independent review remains
  required before approval.
- D1 materialization round 5: authorization was accepted, but complete exact
  golden materialization is blocked by missing authoritative canonical-binding
  and cryptographic fixture inputs. Existing schematic bytes were not relabeled
  as complete evidence. No production code, tests, registry semantics, or
  unrelated design behavior changed.
- Targeted RFC 8032 correction review: fresh `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer` inspected the sole one-character
  design delta and its C1-baseline invalidation. No reviewer reported a
  `blocks_approval`, `changes_required`, P1, or P2 finding. The coordinator
  confirmed the old value was 129 hex characters and invalid hex, the new
  value is the exact 128-character/64-byte RFC 8032 vector, and no other design
  bytes changed. Disposition: approved; the frozen design baseline advances to
  `158277cd433c85714253359e134c94ece0f3ad59d2b3f1b9a403c295417a397e`.

## Blockers And Limits

- The profile/binding/signature/trust-ancestry design ambiguity is resolved by
  the revised canonical design. M0A remains incomplete, rather than
  design-blocked: the schematic golden source must be independently
  materialized to the exact new contract and double-elaborated before it is
  acceptance evidence.
- Design remediation budget: original 3 rounds plus exceptional rounds 4 and 5
  were used. This user-authorized blocker correction is separately bounded to
  the missing fixture-authority contract and does not reopen other design
  scope.
- External operational trust artifacts remain unavailable and cannot certify
  activation.

## Next Action

Materialize one complete non-raw C2 fixture and its exact body/preimage/
signature/envelope/reference/dependency bytes using the independent standard-
library elaborator, then run the source validator before expanding the remaining
fixtures. Do not regenerate the C1 pin until the C2 delta design review approves
the updated baseline.

## M0A-C2 Reopen: Encoding Map And Finite Golden Source

### Current State

- Verified fact: the canonical typed-value codec is already defined in Section
  3.15.1, including model-map encoding, complete binding, canonical-value
  digest, generic outer-envelope digest, and signature-preimage rules. The
  former claim that missing codec syntax blocked C2 is unsupported.
- Verified fact: `docs/design/semantic_ingestion_architecture.md` now has the
  closed C2 artifact encoding/membership map. It makes each body binding,
  generic `CanonicalEncodedArtifact.v1` outer binding, body-versus-envelope
  digest, signature-preimage location, coordinate, and dependency source
  explicit, including the pointer-intent cycle exception.
- Verified fact: the new canonical source package at
  `docs/design/semantic_ingestion/traceability_golden_vectors/v1.json` contains
  28 Unicode-scalar-sorted finite fixtures (including non-member pointer-history,
  reader-authorization, and time-witness inputs) and 25 sorted cases. It is
  test-only,
  has no operational authority values, and covers ancestry, structural,
  coverage, environment/report, streams, execution, release/history, pointer,
  index/fence, lease, watermark, and G1/G2/G3 transition cases.
- Working assumption: the acceptance-independent author owns the fixture bytes;
  these are not runtime inputs, operational trust roots, or a C1 output.

### M0A-C2 Decision Log

- Decision: use the universally registered `CanonicalEncodedArtifact.v1` outer
  envelope for every typed C2 artifact rather than inventing one envelope per
  kind.
- Alternatives: leave body/envelope terminology implicit; define per-kind outer
  envelopes; use raw JSON for typed artifacts.
- Rationale: the selected alternative preserves the existing CTV codec owner,
  gives every verifier one binding-selection path, and prevents body/envelope
  digest substitution without creating a new digest cycle.
- Consequence: raw design, registry, report/profile, blob, and stream members
  remain raw by their already-defined domains; only typed artifacts use the
  generic envelope.

- Decision: source fixtures carry a direct `depends_on_coordinates` set
  separately from their complete `exact_reference_coordinates` set, and carry
  explicit inner-body and outer-envelope schema/version/binding fields.
- Alternatives: infer dependencies from all references; overload one
  schema/binding pair for both the inner typed body and the outer canonical
  envelope; introduce an unconstrained scenario object.
- Evidence and rationale: the closed source-fixture schema had no place to
  represent direct DAG edges required by the C2 membership map, while runner
  report/observation fixtures need both their declared inner-body binding and
  the generic outer-envelope binding. Reference enumeration is not an edge
  relation, and one overloaded pair would permit an implementation to invent
  which binding governed a byte sequence.
- Consequence: direct dependencies are now independently checkable and cannot
  be inferred from incidental body/preimage/signature references. Raw members
  use null outer fields; typed members require all outer fields.

- Decision: replace the stale representative 28-fixture source inventory with
  the explicit 38-fixture complete-generation inventory while preserving the
  approved 25 mutation cases.
- Alternatives: omit unrepresented kinds; encode generation manifest/pointer
  intent as prose aliases; add unconstrained scenario payloads.
- Rationale: the former finite list omitted raw design/registry/report/profile/
  blob artifacts and the golden/generation-manifest construction bodies that
  the M0A contract requires the public gate to load and verify.
- Consequence: C2 source identity and all C1-bound output pins are invalidated
  pending materialization and fresh review; no production behavior changes.

- Decision: keep `active_pointer_intent` inline within the approval-generation
  manifest fixture rather than creating a standalone source fixture.
- Evidence and rationale: the governing C2 map explicitly gives that value no
  independent envelope, digest, coordinate, or signature, while every source
  fixture requires a registered inner binding and expected artifact material.
  A standalone target would force an invented schema binding or contradict the
  no-independent-artifact rule.
- Consequence: the exact inventory is 37 fixtures, and one existing manifest
  mutation case must name the inline `active_pointer_intent` field.

### M0A-C2 Evidence Log

- `python3` standard-library canonical/source-shape/reference check passed:
  canonical compact JSON plus final LF, exact closed top-level keys, 28 sorted
  fixtures and 25 vectors, unique/dangling-reference checks, canonical base64
  round trips, and verdict/reason algebra.
- `git diff --check` passed.
- Runner-schema inventory/reference check passed with 54 unique Unicode-scalar
  sorted entries. The existing isolated C1 elaborator deliberately stops at its
  obsolete 52-entry guard; no C1 output was regenerated or edited.
- Updated raw design SHA-256:
  `c507e69914c9e563e6d08e101d32833a80f6f467d27e79deb8b7210df6345498`.
- Golden-source raw SHA-256:
  `9fab8032b7098703bf9d3e3a709dfe49d57cfcd4044f0cebec762fb6cdacd8f6`.
- No production module, production test, C1 fixture, C1 expected output, or
  registry heading was changed. The registry requires no update because this
  delta adds no heading.
- Source-schema audit: `TraceabilityGoldenVectorSourceFixture` formerly had
  only `exact_reference_coordinates` and one target schema/binding pair, but
  the C2 map requires exact direct dependency edges and a generic outer
  `CanonicalEncodedArtifact.v1` binding in addition to the inner body binding.
  The bounded correction adds the closed fields; no production artifact is
  affected.
- Independent C2 elaboration now derives 54 current binding digests from the
  marked grammar/inventory bytes rather than the stale 52-entry C1 guard. It
  materialized the full `fixture-01-bootstrap_anchor` CTV body, its
  domain-separated body digest
  `d0dd276c5ab89d24ddaaffb93bad4118bec63a77249359808fd7513082e7352e`,
  generic outer-envelope bytes, and outer artifact digest
  `ca3a615cf32361797979e89f411c72ab94f240e973ade3bebc998085e9f4ec75`.
  The source validator now advances through that fixture and fails at the next
  still-schematic fixture, proving that no placeholder pass remains.
- The next ancestry fixture, `fixture-02-bootstrap_anchor_history`, now embeds
  the complete first anchor plus its digest, names that anchor as both its sole
  direct dependency and exact reference, and has body/artifact digests
  `43f7ceaaaee2b1a76fc56596db8a4ea64040c6fd2616c05d45ad75b81ce954a9` /
  `3870d07d33ac6b98f22cdd371ee09d2f610ebcbff9a859279e5aed16e7ff69fe`.
  The validator advances through both materialized fixtures and stops at the
  first remaining schematic recovery-root fixture.
- The isolated bulk materializer now removes empty bytes and zero digests from
  all 37 source fixtures and the validator reports `37` fixtures and `25`
  vectors with canonical source bytes. This is mechanical elaboration evidence,
  not final schema-coverage evidence: remaining fixture maps must still be
  expanded to each declared body's exact required field set, signed where the
  schema requires a signature, and connected to the complete dependency DAG.
  The current source must not be approved until that field-level pass completes.

### M0A-C2 Review Log

- Pending: fresh independent `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer` delta review. Scope is the C2 map, source-package finite
  fixtures/cases, source canonicality/reference integrity, and C1-pin
  non-regeneration. The coordinator must classify each finding under the
  repository product-priority and approval-disposition contract before any
  further revision.

### M0A-C2 Runner Artifact Closure

- Decision: add closed typed inner schemas
  `TraceabilityRunnerEnvironmentObservationBody.v1` and
  `TraceabilityRunnerReportBody.v1`, inventory entries, and exact member
  binding IDs; both remain inside the existing generic
  `CanonicalEncodedArtifact.v1` envelope.
- Alternatives: leave a registry-selected body binding undefined; model both
  artifacts as raw canonical JSON; add the two closed typed body schemas.
- Evidence and rationale: the first alternative makes independent CTV fixture
  elaboration impossible, while raw JSON contradicts the already normative
  typed-envelope/evidence contract. The third alternative is narrow, preserves
  current ownership, and makes every evidence binding reproducible.
- Consequences: environment observation records profile and observed-component
  digests; runner reports bind the loaded schema, selected command/tests,
  observation, result/stream artifacts, and terminal outcome. Neither is a
  signer, authority, or production configuration. No registry heading changed.

## Round-5 Materialization Blocker

| Gap | Required exact input | Evidence of absence | Why it blocks | Smallest next step |
| --- | --- | --- | --- | --- |
| Canonical profile identity | Published grammar bytes and grammar/profile digest | Design gives a formula but no concrete profile artifact | Every binding and canonical envelope preimage depends on it | Publish one reviewed nonoperational profile artifact |
| Per-schema bindings | Fingerprint, enum/optional/numeric/exclusion registries, decoder and binding digests for every R03/R13 schema | No traceability typed-profile registry source exists | Guessed values make accepted bytes schema-invalid and circular | Publish immutable registry entries |
| Signature fixtures | Exact algorithm, deterministic parameters, test keys and reference signatures | Signature profile is open text; operational keys are explicitly excluded | Exact signatures and signer-coordinate artifacts cannot be verified | Publish a test-only deterministic signing fixture |
| Trust ancestry | Byte-complete bootstrap/recovery/lifecycle/release references under those bindings and keys | Operational values are deferred and current golden references are nonoperational | Trust snapshot, pointer, lease, watermark and generation closure cannot materialize transitively | Include non-authoritative byte-complete ancestry |

## Non-Convergence

The original three-round candidate SHA-256
`af18c2067d3f2674d8c072b1399423cc8e38ef21745c6e8e011d24c5597a4388`
did not converge. The user authorized one exceptional fourth round. The six
recorded gaps have the following remediation disposition pending fresh review.

| Gap | Requirement | Severity | Attempts | Round-4 disposition | Required next step |
| --- | --- | --- | --- | --- | --- |
| Lifecycle-root signer rules conflict for `revoke` and `compromise` | R13 | Not applicable / changes_required | 4 | Corrected with one final-action rule and exact accept/wrong-signer vectors | Fresh review |
| Current pointer index lacks durable anti-rollback state | R13 | Not applicable / changes_required | 4 | Corrected with typed index generation, independent monotonic fence/minimum, atomic CAS/restart semantics, and valid-old-backup replay vector | Fresh review |
| Generation-member discriminator has duplicate tags | R03, R13 | Not applicable / changes_required | 4 | Corrected with 28 disjoint concrete tags and exact schema/version/binding IDs | Fresh review |
| Golden fixture schema ID conflicts with its `.v1` binding | R03, R13 | Not applicable / changes_required | 4 | Corrected to exact `TraceabilityGoldenTypedInputFixtureBody.v1` identity | Fresh review |
| Golden source is not independently elaboratable | R03, R13 | Not applicable / changes_required | 4 | Corrected with closed exact byte/reference/mutation/digest/coordinate/load fields and canonical source | Fresh review |
| G1/G2/G3 load-count requirements conflict | R03, R13 | Not applicable / changes_required | 4 | Corrected to 1/2/3 total, 0/1/2 historical, and zero ordinary historical traversal | Fresh review |

The required external authorization was supplied. At that historical boundary,
fresh independent review, not further writer invention, was the prescribed
step.

### Exceptional round-4 review result

- Fresh `spec_auditor`, `correctness_reviewer`, and `test_reviewer` independently
  confirmed one remaining `Not applicable / changes_required|blocks_approval`
  verification-governance gap.
- The golden source is canonical JSON but its non-stream fixtures name complete
  target schemas while containing only toy bodies such as
  `{"generation_id":"G1"}`, `{"index_generation":2}`, or
  `{"final_action":"revoke"}`.
- Expected envelope bytes repeat those toy bodies rather than complete
  `CanonicalEncodedArtifact` envelopes. Complete profile bindings, signer
  coordinates, reference bytes, lifecycle/pointer/history/repository state, and
  concrete post-mutation artifacts are absent.
- An implementation would therefore have to synthesize the exact values the
  independent source is required to fix.

| Gap | Requirement | Severity | Attempts | Why unresolved | Required next step |
| --- | --- | --- | --- | --- | --- |
| Golden-vector source is canonical but not schema-valid or independently elaboratable | R03, R13 | Not applicable / blocks_approval | 4 | Schematic fixtures cannot produce exact typed bodies, preimages, envelopes, repository transitions, or verdicts without implementation invention | Materialize complete independently authored exact artifacts and mutations for every declared vector, then review the immutable source |

### M0A-C2 Materialization Resolution

- The round-5 materialization blocker and exceptional-round schematic-source
  finding above are resolved by the independently authored source at
  `docs/design/semantic_ingestion/traceability_golden_vectors/v1.json`.
  Its canonical raw SHA-256 is
  `b91599eee3eef49584db27a6b94b91eccbf560077466a94023b4eab5b3a504ec`;
  two consecutive isolated materializer runs preserved that identity.
- All 29 typed fixtures contain the exact recursively declared top-level and
  nested schema fields. The independent validator walks literals, unions,
  nullable values, tuples, lists, maps, nested models, strings, datetimes,
  booleans, CTV integers, and CTV bytes without importing C1 or production
  code. All eight raw fixtures match their exact design, registry, JSON, or
  stream/test/result byte contracts.
- The validator independently recomputes body, generic-envelope, artifact,
  binding, coordinate, dependency, and reference closure. It verifies one
  RFC 8032 Ed25519 signature over the exact CTV preimage for each of the 13
  signed artifact kinds. It also enforces G1/G2/G3 loads of `1/0`, `2/1`,
  and `3/2`, with zero ordinary historical traversal.
- Mutation evidence rejects all 29 generic-map substitutions at recursive
  schema validation and all 25 vector case mutations at exact-case validation.
  The validator reports 37 fixtures and 25 vectors. Ruff, Pyright with zero
  errors or warnings, `git diff --check`, and the standalone validator pass.
- No production module, production test, C1 fixture, C1 expected output, or C1
  pin was imported, regenerated, or edited by this materialization.

Superseded review step: the fresh `spec_auditor`, `correctness_reviewer`, and
`test_reviewer` delta review was run and is reconciled in the bounded
non-convergence closure below.

## M0A-C2 Bounded Non-Convergence Closure

The preceding materialization-resolution claim is superseded. Three bounded
C2 remediation passes ended with fresh independent review reproducing
authority, semantic, security, and verification defects. C2 and M0A are
blocked; no fourth semantic remediation is authorized.

Frozen evidence:

- architecture SHA-256:
  `e2ba649d86481e9be437a86c6227b0933891f0f5294fb312887d8881c2bb7d1f`
- registry raw SHA-256:
  `38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`
- preserved nonconformant source SHA-256:
  `b91599eee3eef49584db27a6b94b91eccbf560077466a94023b4eab5b3a504ec`
- pre-closure validator SHA-256:
  `2ca262ff618bdcb565ee13e29cf89b0fd0916f823806b03dca89eb2fffd0adee`
- fail-closed evidence validator SHA-256:
  `5ba50b5eaf3e8ce2bf31d2348f5f034f05e47baa5c5b9d8932ce09c9cb74dd83`
- preserved materializer SHA-256:
  `ea3896b82b6fd67a5e3d455d3f94fb97df19b5bc8ce0016bcac81ee0cfc28db6`

All fresh findings are confirmed. The spec findings are `Not applicable /
changes_required / verification-governance`: invented per-fixture SHA-256
signing seeds replace the four fixed RFC 8032 table keys and coordinates;
typed body digests use plain SHA-256 instead of schema-specific domains;
generic values and empty tuples do not instantiate finite ancestry or G1/G2/G3
and body references are not cross-bound to graph edges; datetimes are plain
strings rather than tagged UTC CTV; and the validator/materializer share code
instead of forming two independent elaborators.

The correctness findings are confirmed as `Not applicable / blocks_approval`:
CTV is incomplete for datetime, map ordering, and decode/re-encode canonicality;
generic placeholders, empty records/members, wrong fixed scalars/sequences, and
an incomplete DAG do not define lifecycle closure; invented signing seeds lack
published key, purpose, and coordinate resolution. Finding types are
verification, lifecycle, and security.

The test findings are confirmed: runner fixtures use
`CanonicalEncodedArtifact.v1` as the inner schema rather than the new runner
body schemas and lack kind-to-schema assertions (`Not applicable /
changes_required / verification`); signatures, CTV, and accepted evidence are
not independently executed (`Not applicable / changes_required /
verification-trust`); the materializer imports validator helpers and no second
elaborator or C2 test exists (`Not applicable / blocks_approval /
verification-trust`); exact 37-ID inventory, dynamic application of all 25
vectors, and end-to-end execution of the claimed 29 mutations are absent
(`Not applicable / changes_required / verification-coverage`).

| Gap | Attempts | Why unresolved | Smallest next step |
| --- | ---: | --- | --- |
| Complete CTV and schema-specific digest contract | 3 | The frozen design/candidate does not supply tagged UTC datetime, full canonical decode/re-encode rules, or the required digest domains | Design author supplies the complete canonical syntax and domains |
| Fixed trust keys, purposes, and signer coordinates | 3 | Per-fixture derived seeds are invented and cannot establish the four authoritative RFC 8032 identities | Design author supplies all fixed test keys, purposes, and resolvable coordinates |
| Finite ancestry and G1/G2/G3 closure | 3 | Generic values, empty tuples, wrong fixed scalars/sequences, and uncross-bound references leave exact bodies, members, and DAG semantics underdetermined | Design author supplies every exact finite value and dependency |
| Independent elaboration and executable mutation proof | 3 | One materializer imports validator helpers; no second independent elaborator or end-to-end vector execution exists | Supply two independent elaborators and executable 37-fixture/25-vector proof |

`validate_source.py` now preserves its structural diagnostics but raises
`C2_INCOMPLETE_PACKAGE` for the frozen candidate rather than emitting a
success-shaped result. This is evidence preservation, not remediation or
approval.

Resolved historical action: obtain either an external design-author-provided complete
canonical package, or a newly approved smaller design WorkPlan that explicitly
supplies exact finite G1/G2/G3 values and two independent elaborators.

### C2 cryptographic fixed-point blocker

- Verified conflict: every `TraceabilityApprovalGenerationManifest` is required
  to list the `golden_vector_manifest` as a generation member, so the generation
  manifest digest depends on the golden-manifest digest. The golden-manifest
  body contains every exact fixture/vector, including
  `fixture-37-approval_generation_manifest`,
  `fixture-49-approval_generation_manifest_G2`, and
  `fixture-50-approval_generation_manifest_G3`, so its digest in turn depends
  on the final bytes and digests of those generation manifests.
- The resulting equations are cyclic: `G = H(generation_body(V))` and
  `V = H(golden_body(G))`. This is not a topologically elaboratable content-
  addressed DAG and cannot be resolved by two independent implementations
  without inventing a fixed-point or exclusion rule absent from the design.
- Alternatives requiring design authority: (1) move final generation-manifest
  vectors into a separate verification package that is not a generation member
  (recommended); (2) omit the golden-vector member from generation manifests,
  contradicting the required-member/release pin; or (3) make those vectors bind
  pre-manifest body templates rather than final expected artifact bytes/digests.
- Resolved historical action: select and specify one cycle-breaking alternative before
  resuming C2 elaboration. Existing candidate bytes are non-authoritative.

#### Fixed-point resolution and executable evidence

- Coordinator decision: select alternative 1. The release-pinned golden
  manifest excludes final generation-manifest/pointer/index/fence/history
  fixtures that depend on the generation being verified. Those cases move to
  the signed, content-addressed, post-activation-only
  `TraceabilityGenerationVerificationPackage`; it is never a generation
  member, activation input, trust authority, retention pin, or fallback.
- Schema consequences: add
  `TraceabilityGenerationVerificationPackageBody.v1` and
  `TraceabilityGenerationVerificationPackageSignaturePreimage.v1`, taking the
  closed CTV inventory from 54 to 56 sorted entries. The package is visible only
  from the acceptance verification index keyed by an already verified release,
  generation manifest, and active pointer tuple.
- Alternatives rejected: omitting the release-pinned golden member would weaken
  the generation closure; hashing final generation bytes inside that same
  member retains the fixed point; binding only a template would no longer be an
  exact final-artifact vector.
- Executable evidence: self-contained elaborator A imports no validator,
  production, C1, or sibling helper. Two consecutive runs are byte-stable.
  Independent elaborator B imports only the standard library. The dynamic
  verifier runs A twice, B, the schema/domain/signature/DAG validator, and all
  25 vector verdicts.
- Stable source SHA-256:
  `4c6ca9bbdac62f63cd7c57bf37490f006138d89151c62815827a992e451211f4`.
- Verifier result: `57` fixtures, `25` vectors, matching stable source digest;
  validator independently reports the same inventory and digest.

#### Remediation round 1: normative finite recipe

- Decision: make `recipe-v1.json` the sole design-authority input and treat
  `v1.json` as derived output. The recipe explicitly freezes all 57 body/raw
  values, inner/outer bindings, preimages/signatures, coordinates, direct and
  reference edges, G1/G2/G3 load counts, 25 top-level cases, 29 nested
  substitutions, and the four fixed RFC 8032 signer coordinates.
- Alternatives: continue deriving fixture values from schema field names;
  embed the recipe in prose; use runtime captures. The first is non-authoritative,
  the second is not machine-checkable, and the third violates nonoperational
  fixture isolation. The canonical JSON recipe is selected.
- Consequences: elaborators may read only the recipe, frozen design, and raw
  registry; derived package bytes cannot be an input oracle. Any recipe-byte
  change requires a new frozen identity and fresh review. Production and C1
  remain outside this operation.
- Recipe raw SHA-256:
  `91f8829754de107c27b9c7fdc13f9902be35294fb926ee823cf6720e1165c2a5`.
- Derived source raw SHA-256 after the matching design binding refresh:
  `5f4a2e0f160acb36fcea22a82a31a07c8f4d3a7509177c2b1100f8f60d1579d1`.
- Architecture raw SHA-256:
  `50720c92a4fa7d567806387212b76be4a6b52ac37d8a342cc3546a48e2908d5e`.
- Recipe-authority evidence: `validate_recipe.py` independently checked the
  canonical recipe identity; exact root, fixture, binding, and signer field
  sets; 57/25/29/4 closed counts; sorted unique identifiers; coordinate and
  reference closure; base64 encodings; and exact fixture/vector cross-bindings
  to the frozen derived package. `validate_source.py` separately accepted all
  57 fixtures and 25 vectors at source SHA-256
  `5f4a2e0f160acb36fcea22a82a31a07c8f4d3a7509177c2b1100f8f60d1579d1`.
  Python 3.12 compilation, Ruff, Pyright (`0 errors, 0 warnings`), and
  `git diff --check` passed for the recipe-authority validator.
- Remediation correction: fixture 13 now has the exact
  `TraceabilityRunnerEnvironmentObservationBody.v1` inner binding and fixture
  14 has the exact `TraceabilityRunnerReportBody.v1` inner binding;
  `CanonicalEncodedArtifact.v1` remains outer-only. Materialization recomputed
  both bodies, envelopes, artifact identities, and every downstream dependency
  and reference. The 29 substitution cases now cover 29 distinct typed schemas
  at 29 distinct non-root paths that resolve to nested declared CTV type tags;
  each exact replacement is an invalid type tag and records the observed
  `typed_domain_semantic_validation` /
  `schema_invalid_type_tag` outcome.
- Correction evidence: `validate_recipe.py` accepted the complete
  kind-to-inner map, resolved all 29 paths, proved path and typed-schema
  uniqueness, rejected valid-tag replacements, and cross-bound the full
  downstream closure to the derived package. `validate_source.py` accepted 57
  fixtures and 25 vectors. Python 3.12 compilation, Ruff, Pyright
  (`0 errors, 0 warnings`), and `git diff --check` passed.
- Round-1 next action is superseded by the round-2 authority redesign below.

#### Remediation round 2: primitive authority and executable semantics

- Decision: replace the output-oracle interpretation with primitive recipe
  format `memorii-sia-c2-primitive-recipe-v2`. Only primitive authority,
  complete signer inputs, and mutation inputs are authoritative. Existing
  materialized fixtures remain under `checked_fixture_outputs` solely as
  non-authoritative mismatch expectations; an elaborator may compare them only
  after independent derivation.
- Exact state: the recipe fixes authority/channel IDs; anchors 1/2 and rotation
  chain; recovery roots and policy; lifecycle records 1-4 and roots 1-5;
  release/snapshot; executed/pass runner values; G1/G2/G3 ordered members,
  pointer/index/fence sequences and predecessors, histories, and `1/0/0`,
  `2/1/0`, `3/2/0` load counts. Null predecessors exist only at named genesis
  entries.
- Signer authority: all four records now carry exact seed, public key, key
  digest, coordinate, reference message/signature, profile, and closed exact
  purpose list. The design requires independent seed-to-key, key-digest,
  coordinate, reference-signature, preimage-field, purpose, binding, and body
  digest verification.
- Encoding and validation: the design now specifies strict schema-aware CTV
  integer, calendar datetime, Unicode scalar, literal/enum, collection
  ordering/duplicate, tag, closed-field, decode/re-encode, graph traversal,
  cycle/topology, lifecycle, authorization, generation-member, and
  pointer/index/fence/history validation.
- Mutation evidence: all mutations must be applied to copied bytes/artifact/
  graph state and observed through the normal ordered pipeline. The design
  freezes the earliest-boundary families and requires all 25 top-level, 29
  nested, plus wrong signer/purpose/key, dangling/self/two-node/descendant
  cycle, sequence/predecessor, and generation-member negative cases.
- Interfaces and acceptance: design-side and future implementation validators
  take explicit input paths and have no checked-in path/digest globals.
  Approval criteria require isolated temporary A/B execution, input mutation
  matrix, A/A stability, A/B exact equality, checked-output equality only
  after derivation, hermetic supported-Python repository test, and all static
  gates. These are measurable implementation criteria, not claims of current
  implementation evidence.
- Review-ready baselines:
  - architecture SHA-256
    `0ebfe227b09c70d6ede74980a13eb0a49a20ba4960aad49a345524f185de0a30`
  - primitive recipe SHA-256
    `5a89edf2f3cb75ecc80e19de2850920a8474807ee7664329b871501ac16c397e`
  - non-authoritative checked output SHA-256
    `5f4a2e0f160acb36fcea22a82a31a07c8f4d3a7509177c2b1100f8f60d1579d1`
- Design-side evidence: canonical recipe validation accepted eight exact roots,
  four complete signer primitive records, lifecycle `1..4`, root terminals
  `1/2/3/3/4`, generation/pointer/index/fence `1..3`, executed/pass runner
  state, 57 checked fixtures, 25 vectors, and 29 nested cases. This does not
  claim A/B or executable mutation completion.
- Round-2 review baseline is superseded by the closed round-3 input below.

#### Remediation round 3: closed oracle-free elaboration input

- Decision: replace the incomplete v2 state plus checked-output oracle with
  `memorii-sia-c2-oracle-free-elaboration-input-v3`. The canonical input has
  no expected body bytes, digests, envelopes, signatures, coordinates, or
  checked outputs.
- Fixture closure: all 57 artifacts now have a closed primitive record naming
  exact kind/schema/version, raw bytes or typed body template, dependency
  fixture IDs, and signer IDs. Explicit nonoperational constants replace the
  prior fixture-ID-plus-field placeholders. Named `$derive` records are limited
  to schema-governed deterministic outputs.
- Field coverage: 57 ledger records cover 1,685 body-input leaves exactly once
  as primitive or named deterministic derivation. Design approval additionally
  requires fresh review to confirm schema-transitive field completeness.
- Lifecycle correction: records 1-3 are exact `activate` transitions with null
  policy/replacement; record 4 is exact `recover` with recovery policy and
  replacement, sequences 1-4, and immediate predecessors. Roots commit terminal
  sequences `1/2/3/3/4`.
- Mutation closure: 25 top-level vectors, 29 nested substitutions, and 12
  direct negatives form a closed denominator of 66. Direct negatives cover
  signer, purpose, public key, dangling/self/two-node/descendant cycles,
  sequence, predecessor, and missing/duplicate/wrong-kind members with exact
  target, replacement, earliest boundary, and reason.
- Historical-output disposition: `v1.json` is retained only as
  `rejected_historical_output` and links to the superseding recipe digest. It
  is neither authority nor expected output. New checked outputs require the
  separate linked implementation operation and isolated A/B agreement.
- Evidence invalidation: all earlier M1-M3 elaboration, stability, equality,
  checked-output, signature, graph, and executable-vector evidence predates v3
  and is invalid for approval. Round-1/round-2 hashes and pass claims remain
  historical only.
- Review-ready baselines:
  - architecture SHA-256
    `f70611d0879bd9daa8dc0c80beab50250d6c99e67b633e37bc6ae9376bfe9f5b`
  - oracle-free recipe SHA-256
    `44698181d560e7a0a5d133ec142448ab247445af4197dbadd27bc7b3ca366291`
  - rejected historical output SHA-256
    `e4875ec3e8afcc8a8410b2dceac8b00b50c296711652695fce80f2eaa46463be`
- Design-side validation: the explicit-path validator accepted canonical input,
  exact 57/57/4/25/29/12 denominators, placeholder exclusion, dependency-ID
  closure, exact leaf coverage, corrected lifecycle actions/sequences/
  predecessors/policy/replacement, exact root terminals, and the required
  direct-negative reason families. This is design consistency evidence only.
- Exactly one next action: obtain fresh independent design review of the v3
  architecture, recipe, field-coverage ledger, lifecycle, and negative matrix;
  after approval create a linked `$implement-design` WorkPlan.
