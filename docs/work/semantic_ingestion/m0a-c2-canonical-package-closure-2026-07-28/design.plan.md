# M0A-C2 Canonical Package Authority Closure

- Work ID: semantic-ingestion-m0a-c2-canonical-package-closure-2026-07-28
- Work type: design
- Status: blocked after final round-20 non-convergence
- Coordinator: Codex main thread
- Created: 2026-07-28
- Last updated: 2026-07-28 (final round-20 closure)
- Parent WorkPlan: `docs/work/semantic_ingestion/m0a-trust-artifact-closure-2026-07-28/design.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/implementation.plan.md`
- Canonical inputs: architecture SHA-256 `57b50352cbe94b208aeff6e94130524f43aef339855f7eb7d15590e91b6d98b2`; recipe SHA-256 `fbd2b399f8e6caf5e742b9f839b77a3a9f0fac6772a4c3ef7910fb11ff573abc`; validator SHA-256 `c60c9350fbd1f90c97e725813d01bebcf0c66b062c518abb859ced53bd6bf3c6`; registry SHA-256 `38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`; immutable prior reports are historical evidence
- Expected outputs: a design-owned complete canonical C2 package, two independent standard-library elaborators, one independent executable verifier, immutable review reports, and evidence sufficient for a separate implementation WorkPlan

## Objective

Make the SIA-R03/R13 C2 package independently and deterministically
elaboratable without hidden choices. The frozen design and registry will
define every canonical byte rule, digest domain, fixed test signer, exact
fixture value, dependency edge, generation transition, and mutation outcome.
Two isolated elaborators that share no codec or validator helpers must derive
byte-identical `v1.json`; a third independent verifier must execute every
declared mutation and identify the earliest required rejection reason.

## Problem Definition

The prior C2 candidate was structurally shaped but not authoritative. Design,
implementation, and test authors could not reproduce its signatures, body
digests, finite ancestry, G1/G2/G3 state, runner bindings, or mutation verdicts
without relying on invented values or shared code. The affected actors are
design authors, independent implementers, reviewers, and the future
composition-owned approval gate. The desired outcome is one finite,
content-addressed, nonoperational package whose complete meaning and bytes are
derivable solely from frozen design and registry inputs.

## Completion Contract

This operation is complete only when:

- all requirements `C2CPA-001` through `C2CPA-011` are covered by normative
  design text and measurable evidence;
- no generic placeholder, empty required record/member collection, invented
  per-fixture key, plain datetime, ambient digest domain, or unresolved
  fixture reference remains;
- the exact 57 fixture IDs, kinds, inner schemas, finite values, direct edges,
  reference edges, sequences, G1/G2/G3 membership, and expected load counts
  are frozen in design-owned input;
- four fixed RFC 8032 test keys, purposes, public keys, and artifact
  coordinates are frozen and every signature verifies against them;
- both independent elaborators run in isolated standard-library processes,
  import no production/C1/validator/other-elaborator helper, and emit identical
  canonical bytes from only the frozen design and registry;
- the independent verifier decodes and re-encodes every CTV value, recomputes
  every domain-separated digest/signature/envelope/coordinate/edge, dynamically
  applies all 25 vector mutations and 29 nested generic substitutions, and
  asserts the earliest exact reason;
- canonical stability, Ruff, Pyright, `py_compile`, and `git diff --check`
  pass;
- fresh spec, correctness, and test review leaves no confirmed
  `blocks_approval` or `changes_required` finding.

## Scope

Included:

- design-side CTV, digest, signer, finite fixture, generation, and mutation
  authority;
- `docs/design/semantic_ingestion_architecture.md`;
- `docs/design/semantic_ingestion/traceability_golden_vectors/`;
- immutable design-review reports and this WorkPlan.

Excluded:

- production code, stores, public gates, integrations, and runtime tests;
- C1 fixture, registry, pin, and elaborator regeneration;
- operational identities, private keys, approval, or certification;
- M0B and M1+ work.

Deferred:

- implementation of the approved package in production;
- durable repository and composition integration under C3-C5.

## Requirements Ledger

| ID | Requirement | Source | Priority | Acceptance criteria | Status |
| --- | --- | --- | --- | --- | --- |
| C2CPA-001 | Complete CTV grammar including tagged UTC datetime, Unicode-scalar map order, and canonical decode/re-encode | C2-SPEC-04, C2-CORR-01 | Required | Three independent implementations reject noncanonical encodings and round-trip all fixtures | in progress |
| C2CPA-002 | Schema-specific body digest domains | C2-SPEC-02 | Required | Every typed schema has one frozen domain and verifier recomputation matches | in progress |
| C2CPA-003 | Four fixed RFC 8032 signer identities | C2-SPEC-01, C2-CORR-03 | Required | Seed/public key/purpose/coordinate table is exact and all signatures verify | in progress |
| C2CPA-004 | Exact nonempty finite ancestry and G1/G2/G3 values, edges, and sequences | C2-SPEC-03, C2-CORR-02 | Required | Design table fully determines all bodies and graph closure | in progress |
| C2CPA-005 | Exact runner artifact inner schemas | C2-TEST-01 | Required | Kind-to-schema table and all fixture bindings use the two runner body schemas | in progress |
| C2CPA-006 | Exact complete fixture inventory | C2-TEST-04 | Required | Both elaborators and verifier assert the same ordered 57 IDs | in progress |
| C2CPA-007 | Executable 25-vector mutation contract | C2-TEST-02, C2-TEST-04 | Required | Verifier applies each mutation and proves earliest exact verdict/reason | in progress |
| C2CPA-008 | Executable 29 nested generic-map substitutions | C2-TEST-04 | Required | Each typed fixture is mutated inside a declared nested value and rejected at the schema gate | in progress |
| C2CPA-009 | Two truly independent elaborators | C2-SPEC-04, C2-TEST-03 | Required | No shared codec/validator helpers; isolated byte-identical output | in progress |
| C2CPA-010 | Independent package verifier | all findings | Required | Independently recomputes semantics and fails closed on any mismatch | in progress |
| C2CPA-011 | Evidence preservation and C1/production isolation | authorization and prior closure | Required | Prior report remains immutable; diff proves no production/C1 edits | in progress |

## Non-Goals

- Defining operational trust authority.
- General-purpose serialization outside the frozen SIA CTV profile.
- Implementing persistence, concurrency, leases, or public composition.
- Reusing the prior candidate as authority merely because it is canonical JSON.

## Constraints And Invariants

- Governing precedence follows root `AGENTS.md`.
- All values are explicitly nonoperational and must not be accepted as real
  approval material.
- Test private seeds are design-visible and purpose-bound.
- No model output participates in package authority.
- Every schema, enum, reference, and lifecycle value fails closed.
- Elaborator independence is a source-level and process-isolation requirement,
  not merely separate entry points.
- The design operation has three revision rounds after the coherent initial
  draft; exhaustion triggers a precise blocker.

## Sources Of Truth

1. `docs/design/memorii_spec.md`
2. `docs/design/memorii_storage_details.md`
3. `docs/design/event_model.md`
4. `docs/IMPLEMENTATION_RULES.md`
5. `docs/design/semantic_ingestion_architecture.md`
6. `docs/reviews/semantic_ingestion/m0a-c2-non-convergence-2026-07-28.md`
7. This WorkPlan

The explicit user authorization selects the newly approved smaller design
operation but does not waive higher-precedence product invariants.

## Existing-System Analysis

Verified facts:

- the prior candidate has 37 fixtures and 25 vector descriptors but was
  generated by one elaborator importing validator helpers;
- its typed values use generic deterministic strings and empty collections;
- its signatures derive per-fixture seeds rather than fixed design identities;
- its verifier preserved structural evidence but now fails closed with
  `C2_INCOMPLETE_PACKAGE`;
- C1 and production owners remain outside this operation.

No existing production abstraction owns this design-only package. The
canonical owners are the semantic-ingestion design, frozen registry, and
isolated documentation tools.

## Assumptions And Open Questions

Verified facts: the user approved this smaller linked design operation and its
exact scope.

Working assumption: four public nonoperational RFC 8032 test seeds may be
published because they establish deterministic fixtures, not operational
authority.

Unresolved questions: none at creation. Any ambiguity in exact lifecycle
semantics that the governing design cannot settle will stop the operation
rather than be filled by convenience.

Decisions requiring external input: none currently.

## Alternatives Considered

| Approach | Advantages | Disadvantages and risks | Decision |
| --- | --- | --- | --- |
| Patch the prior candidate and validator | Small diff | Retains circular authority and hidden choices | Rejected |
| Freeze only output bytes | Easy reproduction | Does not explain semantics or permit independent elaboration | Rejected |
| Freeze one declarative finite input plus two independent elaborators and a third verifier | Auditable, deterministic, independently testable | More design/tooling volume | Selected |
| Introduce a production codec | Reusable later | Violates design-only/C1/production isolation | Rejected |

## Feasibility Evidence

The prior standard-library prototype proves RFC 8032, CTV encoding, and
canonical JSON are implementable without runtime imports. The discriminating
feasibility test is stronger: two independently written tools must emit the
same source hash and the verifier must reject targeted mutations for the same
earliest reason.

## Failure And Operational Analysis

Malformed, duplicate-key, noncanonical, unknown-schema, wrong-domain,
wrong-signer, dangling-edge, wrong-sequence, incomplete-generation, and
mutation-reason mismatches are terminal validation errors. Tool interruption
may leave only temporary output; checked-in authority changes only by atomic
replacement after full verification. Outputs are nonoperational, have no
migration or rollback effect, and cannot activate production. Rollback is
reverting the complete design/package/tool delta while retaining immutable
review evidence.

## Verification Strategy

Each requirement maps to independent deterministic execution. Elaborator A,
elaborator B, and verifier must not import one another. Static source scans
enforce forbidden imports. Separate processes derive outputs into temporary
directories. Byte equality, fixed hashes, schema-domain digests, RFC 8032
verification, exact inventory, exact graph closure, dynamic vector mutations,
nested substitutions, and decode/re-encode stability are asserted. Ruff,
Pyright, `py_compile`, and `git diff --check` close static evidence.

## Milestones

### M1: Freeze normative finite authority

- Purpose: define all formerly missing semantic inputs.
- Bounded scope: CTV, 56 bindings, digest domains, four signers, 57 fixtures,
  G1-G3, 25 vectors, and 29 nested substitutions.
- Expected artifacts: design tables/marked canonical input.
- Verification method: independent parse and completeness audit.
- Status: superseded; the cited recipe predates round 5 and is not evidence.

### M2: Independent elaboration

- Purpose: prove the design fully determines package bytes.
- Bounded scope: two standard-library tools with no shared helpers.
- Expected artifacts: byte-identical `v1.json` outputs.
- Verification method: isolated runs and SHA-256 equality.
- Status: superseded; the cited A/B outputs predate round 5 and are not evidence.

### M3: Independent executable verification

- Purpose: prove semantics and negative cases, not only byte stability.
- Bounded scope: third implementation, 25 vectors, 29 nested substitutions.
- Expected artifacts: fail-closed verifier evidence.
- Verification method: full dynamic execution with exact earliest reasons.
- Status: superseded; the cited verifier predates round 5 and is not evidence.

### M4: Static closure and independent review

- Purpose: determine implementation readiness.
- Bounded scope: design/package/tools and governing context.
- Expected artifacts: static-check evidence and immutable review reports.
- Verification method: Ruff, Pyright, `py_compile`, diff check, then fresh
  spec/correctness/test review and coordinator reconciliation.
- Status: pending.

## Progress Log

- 2026-07-28: created a new linked design WorkPlan after explicit user
  authorization. The blocked predecessor and immutable report remain
  unchanged. Next action is M1 finite-authority drafting.
- 2026-07-28: froze the determinate CTV token algebra, schema-specific body
  digest formula, four signer coordinates/purposes, and runner inner-schema
  pairs. Direct comparison of Sections 3.23.4.3 and the C2 inventory exposed
  a cardinality conflict: the exact 37 fixtures cannot carry the distinct
  artifact coordinates mandated by complete ancestry. Stopped before
  elaborator or source changes.
- 2026-07-28: targeted spec and correctness review independently confirmed the
  fixture cardinality conflict as `Not applicable / blocks_approval /
  verification-governance`. The coordinator selected the
  architecture-consistent in-scope correction: distinct fixture instances for
  every distinct ancestry artifact. The inventory now has 48 IDs.
- 2026-07-28: the same singular-artifact rule forced distinct G1/G2/G3
  generation manifests, pointers, indexes and fences plus pointer history
  through G1. The exact inventory is now 57 IDs.
- 2026-07-28: elaborator-A prototype now emits all 48 fixtures with tagged UTC
  datetimes, nonempty declared collections, schema-domain body digests, fixed
  RFC 8032 signer seeds/coordinates, and deterministic canonical source hash
  `680c6ed987b343cf85616761ca3cb241d245dcfbc437474951d6063d168f55c9`.
  Two consecutive reruns preserved the hash. This is feasibility evidence only:
  A still imports validator helpers, exact ancestry field overrides and
  cross-binding remain incomplete, and elaborator B does not yet exist.

## Evidence Log

- Blocked baseline:
  `docs/reviews/semantic_ingestion/m0a-c2-non-convergence-2026-07-28.md`.
- Frozen architecture SHA-256:
  `50720c92a4fa7d567806387212b76be4a6b52ac37d8a342cc3546a48e2908d5e`.
- Frozen normative recipe SHA-256:
  `91f8829754de107c27b9c7fdc13f9902be35294fb926ee823cf6720e1165c2a5`.
- Frozen registry SHA-256:
  `38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`.
- Frozen rejected candidate SHA-256:
  `b91599eee3eef49584db27a6b94b91eccbf560077466a94023b4eab5b3a504ec`.
- Current deterministic 48-fixture prototype SHA-256:
  `680c6ed987b343cf85616761ca3cb241d245dcfbc437474951d6063d168f55c9`.
- Frozen derived 57-fixture package SHA-256:
  `5f4a2e0f160acb36fcea22a82a31a07c8f4d3a7509177c2b1100f8f60d1579d1`.
- Remediation round 1 verification: two isolated standard-library elaborators
  emitted the frozen package byte-for-byte; the independent verifier reported
  `fixtures=57`, `vectors=25`, `nested=29`; Python 3.9 compilation and
  `git diff --check` passed.
- Targeted review evidence: both spec and correctness reviewers independently
  confirmed the singular-fixture cardinality conflict; coordinator resolved it
  through distinct instances without changing production or C1.

## Decision Log

- Decision: create a new WorkPlan rather than resume the exhausted predecessor.
  Date: 2026-07-28. Alternatives: reopen prior plan or abandon C2. Rationale:
  explicit authorization supplies a new smaller design operation while
  preserving non-convergence evidence. Consequence: new review baseline and
  budget.
- Decision: require declarative design authority plus two elaborators and one
  verifier. Date: 2026-07-28. Alternative: bless output bytes. Rationale:
  independent reproduction is the governing acceptance property.

## Review Log

Targeted review round 1 used `spec_auditor` and `correctness_reviewer` against
the cardinality conflict. Both confirmed that one singular fixture could not
represent multiple content-addressed ancestry members. Coordinator disposition:
confirmed and resolved by expanding to distinct fixture instances. A test
review could not start because the thread concurrency limit was reached; full
three-role review remains required after a coherent package exists.

Remediation round 1 resolved the confirmed independent-elaboration,
non-executable-mutation, Python-portability, and stale-baseline findings.
Elaborators A and B now accept only caller-supplied recipe, design, registry,
and output paths and share no sibling or validator imports. Two consecutive
isolated verifier runs reproduced source SHA-256
`5f4a2e0f160acb36fcea22a82a31a07c8f4d3a7509177c2b1100f8f60d1579d1`,
executed all 25 vector cases and 29 distinct nested substitutions, and rejected
one-byte design and registry mutations. The independent recipe/source
validators recomputed the frozen bindings, digest/signature material,
coordinates, DAG, lifecycle, and source cross-bindings. Scoped Ruff reported
`All checks passed`; scoped Pyright reported `0 errors, 0 warnings,
0 informations`; Python 3.9 `py_compile`, the elaborator import scan, and
`git diff --check` passed. Disposition: the four findings are resolved pending
fresh M4 review; no prior review is treated as final approval evidence.

## Blockers And Limits

Resolved blocker: Sections 3.23.4.2-3.23.4.3 require two distinct bootstrap
anchors, two distinct recovery roots, multiple recovery-policy histories, five
distinct lifecycle roots, and every artifact contained by the histories as a
separate generation member. The exact C2 inventory contains only one
bootstrap-anchor fixture, one recovery-root fixture, one recovery-policy
fixture/history, one lifecycle-root fixture, and one source record of
body/digest/coordinate per fixture. A fixture cannot author two distinct
artifact coordinates. Therefore an exact complete generation cannot be
derived while simultaneously preserving the 37-ID inventory and
every-contained-artifact membership rule.

Alternatives considered:

1. expand the fixture inventory so every distinct ancestry artifact has its own
   fixture and coordinate;
2. keep 37 fixtures but amend generation membership so history/root fixtures
   are self-contained aggregate authority and their embedded artifacts do not
   require separate generation members;
3. change the source-fixture schema to carry a nonempty ordered artifact
   collection rather than exactly one target body/digest/coordinate.

Alternative 1 most directly preserves generation completeness and is selected
under the authorized bounded plan. Alternative
2 preserves the inventory but changes trust/publication semantics. Alternative
3 preserves the former count but changes the closed source contract and all
vector addressing. Expanding the inventory preserves singular fixture authority and
does not collapse or omit distinct artifacts.

Revision budget: user-authorized maximum of 20 remediation rounds for this C2
instance. Rounds 1-10 and their closure are historical; round 11 is current.

Environment limits: standard library only for elaborators and verifier; no
network or operational keys.

## Next Action

Complete recursive declared-field type validation across all 56 roots, then run
fresh independent round-17 `spec_auditor`, `correctness_reviewer`, and
`test_reviewer` review.

## Outcome And Retrospective

Historical round-3 outcome: blocked after that review round. All M1-M3 execution,
stability, equality, checked-output, signature, graph, and vector claims are
invalid for the exact v3 baseline. Structural diagnostics remain useful, but
`validate_recipe.py` fails this exact recipe closed as
`V3_INCOMPLETE_AUTHORITY`.

Current round-4 outcome: review-ready design candidate under the expanded
10-round authorization. No implementation or approval claim is made.

## Final Non-Convergence Closure

The immutable final review is
`docs/reviews/semantic_ingestion/m0a-c2-v3-non-convergence-2026-07-28.md`.
No semantic remediation remains authorized under this WorkPlan.

| Gap | Attempts | Final evidence | Required external correction |
| --- | ---: | --- | --- |
| Concrete mutation denominator | 3 | 20 of 25 vectors use `mutation_kind=none`; only 5 vectors plus 29 nested plus 11 effective negative categories produce 45 concrete mutations | Supply 20 concrete vector mutations and one closed denominator |
| Oracle-free inputs | 3 | Primitive bodies retain derived coordinates/digests and therefore remain output-shaped authority | Use fixture-ID references only and derive all coordinates |
| Authority/body agreement | 3 | Primitive body templates contradict lifecycle and G1/G2/G3 scalar authority | Make every body field exactly equal the authoritative lifecycle/generation state |
| Mutation addressability | 3 | Vector, nested, and direct-negative targets use incompatible untyped path dialects | Supply one typed common mutation-target grammar |
| Governance baseline | 3 | Plans and evidence still cited superseded hashes and M1-M3 passes | Repin v3, invalidate old claims, and require new evidence after correction |

## Authorized Remediation Round 4

The user authorized up to 10 remediation rounds. The immutable round-3 report
remains historical evidence; all pre-round-4 execution claims remain invalid.

- Thirty ancestry, lifecycle, runner, generation, pointer, index, fence, and
  history bodies are exact field-for-field projections from
  `primitive_authority`.
- G1/G2/G3 member tuples are sorted unique fixture IDs. Generation, pointer,
  index, and fence sequences are 1/2/3 with exact immediate predecessor IDs.
- The recipe contains no derived `sia-traceability/v1/...` coordinate.
- All 25 top-level rows are concrete. With 29 nested and 12 direct-negative
  cases the honest denominator is exactly 66; no mutation kind is `none`.
- Every case uses the common typed scope/owner/path target, typed replacement,
  and `re_elaborate_target_and_all_dependents` propagation.
- Review-ready hashes are architecture
  `6637bf82a215ecc9859cb240fc09a4e5e3fa24cd9f6d15b769bdc42007f29798`,
  recipe
  `65c4fa4e8c2745efd2daa6d103fe5ed0a55a091c8a373ff1d0aaa1ad5b46465b`,
  rejected historical output
  `e4875ec3e8afcc8a8410b2dceac8b00b50c296711652695fce80f2eaa46463be`,
  and registry
  `38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`.
- Design-side validation proves canonical bytes, 57 fixtures/ledgers, exact
  authority projections, lifecycle and predecessor chains, closed member
  tuples, no derived coordinates, and 66 concrete common-grammar mutations.
  This is not implementation evidence.
- Round-4 next action is superseded by the round-5 candidate below.

## Remediation Round 5

- All 19 remaining authority-bearing typed templates moved into unique
  schema/version/value records under `primitive_authority.authority_bodies`;
  every typed fixture now projects field-for-field from one authority selector.
- Anchor/root/policy histories use explicit ordered authority selectors.
  Recovery-policy histories bind the sole exact threshold-2 policy and ordered
  roots `fixture-recovery-1`, `fixture-recovery-2`.
- The common mutation grammar now requires one leading `Root` segment and
  defines closed root objects for all five scopes, exact graph edge/member
  representations, typed relative resolution, and dependent re-elaboration.
  `$` is forbidden as a field.
- Vectors 21 and 23 use exact generation references
  `fixture-generation-1`/`fixture-generation-2`. Vector 21 restores G1 into G2
  and rejects at lifecycle policy. Idempotent G2 replay is a separate explicit
  accepting baseline; vector 22 is a concrete invalid G3 predecessor mutation.
- Every mutation has explicit `reject`, boundary, and reason. The separate
  baseline has explicit `accept`. The mutation denominator remains 66.
- Review-ready hashes are architecture
  `ea9cc51a78f0475cdb74c9af23cbeca5cf929385735e76fe3edb822e938bcf53`
  and recipe
  `8fe4928193ac9da34032a09399ac15bf01ee9dbde3cdb59e47dd517ff0f62f79`.
  Registry and rejected historical output remain unchanged.
- Round-5 next action is superseded by the round-6 candidate below.

## Remediation Round 6

- All 49 typed fixtures now have fully materialized tagged CTV expansions with
  exact schema/version. Their ledgers cover 2,119 scalar leaves; no expansion
  contains an opaque `$derive`.
- Recovery-policy history 0 has a unique ID, empty policies/roots, null
  threshold, and no policy dependency. History 1 uniquely selects policy 1,
  threshold 2, ordered recovery roots, and the policy dependency.
- All 12 direct negatives use declared scope-root paths. The validator resolves
  the first typed segment against the closed scope schema and rejects `$`.
- Vector 23 replaces correct G2 with distinct G1, making the predecessor
  mutation reachable.
- Review-ready hashes are architecture
  `a3804653ab2841ecc3e5e473699413768bc65d964948117de3d05437ec90efeb`
  and recipe
  `d406a25822a64dd668c24526fed07d064df393c7aa3f559740399452bc150ab7`.
- All historical non-convergence text and M1-M3 statuses are retained only as
  explicitly historical/superseded evidence. Current design-side validation is
  not implementation evidence.
- Round-6 next action is superseded by the round-7 candidate below.

## Remediation Round 7

- Regenerated all 49 tagged expansions after overlaying selected authority
  scalars. Policy history 0 now encodes an empty policy tuple; history 1 encodes
  exactly one policy. The frozen expansion denominator is 2,081 scalar leaves.
- The validator binds explicit design/registry hashes, parses declared schema
  fields, recursively validates CTV tags, canonical integers, real calendar
  datetimes, map ordering/uniqueness, field sets, ledger coverage, and
  expansion/authority scalar equality.
- All 66 targets are walked through constructed scope roots to an actual
  terminal value. Runner stream cases now mutate exact dependency indexes, and
  the nested recovery-policy case targets nonempty history 1. Equal
  replacements reject as no-ops.
- `--self-test` proves fail-closed malformed integer, datetime, map order,
  missing field, and invalid index behavior; explicit source hashes exercise
  incompatible design/registry rejection.
- Historical rounds, reports, and M1-M3 evidence remain superseded and are not
  current approval evidence.
- Review-ready hashes are architecture
  `d8f2545f74050e22c8f706f76e67321e773a96365355079c5d610a84896d125f`
  and recipe
  `5bbe0ab6e44afcbd8019d5ca93e4545e22721ad9e72de17adc0032a73f00a92d`.
- Round-7 next action is superseded by the round-8 candidate below.

## Remediation Round 8

- Selector materializations and expanded CTV trees are complete and identical
  for all 49 typed fixtures. The exact recursive leaf denominator is 2,082.
- Fixture 41 embeds exact policy ID, threshold 2, both ordered recovery-root
  digests, null predecessor, and the policy signature.
- Strict CTV validation covers bytes, duration, set/frozenset, enum, Unicode
  scalar, integer, datetime, list, tuple, and map rules in addition to exact
  parsed schema fields and source hashes.
- All 66 cases carry terminal type/category. Resolution checks actual scope
  roots and terminal values, reference families, and no-op replacements.
- Adversarial mode covers malformed integer/datetime/map/bytes/duration/set/
  enum/Unicode and missing field/index; caller-supplied hashes fail incompatible
  design/registry inputs closed.
- Historical outcomes and evidence remain explicitly superseded.
- Review-ready hashes are architecture
  `96765d78ec563e9f16a83a7c9a38fb7dec18060c5de73682e275c40b057b315d`
  and recipe
  `6a460f23d37ad153b9eb1fe08cb7d8fbafad670157c11375c5bd383ffa37199e`.
- Round-8 next action is superseded by the round-9 candidate below.

## Remediation Round 9

- Removed `selector_materializations`. Every typed fixture selects one
  schema-complete authority body; the validator independently deep-materializes
  and compares the full stored expansion.
- Frozen denominators are 2,068 typed leaves, 14 raw leaves, and 2,082 total.
- Generation, pointer, and index mutations resolve through declared chain-state
  authority rather than nonexistent encoded-body fields.
- Validator enforces complete-tree equality, schema/CTV validation, terminal
  type/category presence, exact reference families, resolvable paths, and
  non-noop replacements. Adversarial mode exercises every CTV tag family and
  representative owner/path/index/source failures.
- Historical rounds and evidence remain superseded.
- Review-ready hashes are architecture
  `02b522b76c4f447ab7f6bee8eded6a499698f6ef7f684c58726647ef6ef6afe1`
  and recipe
  `92ed8a14788a4ea6213f5778f0307a37983468e1bea01858f27eb88759dd6d07`.
- Exactly one next action: obtain fresh independent round-9 design review.

## Remediation Round 10

- This section alone states current status; every earlier round/current-state
  statement is historical and superseded.
- The marked closed enum registry contains 11 canonical enum schemas and its
  payload is bound into the CTV profile. Duration and Unicode-scalar map-key
  validation now use the exact grammar and reject the legacy duration shape.
- Ordinary traversal observes and compares 2,068 typed leaves, 14 raw leaves,
  and 2,082 total rather than trusting metadata alone.
- `validate_candidate(...)` returns structured diagnostics from complete
  caller-supplied bytes. `--self-test` deep-copies complete candidate inputs
  and proves metadata-drift, missing-owner, no-op, and source-identity failures
  through ordinary validation.
- Current baseline hashes are architecture
  `93570981d938285ac5201044a365108a0f9d688dd3c78e50d16f15d95a8a88d8`,
  recipe
  `92ed8a14788a4ea6213f5778f0307a37983468e1bea01858f27eb88759dd6d07`,
  registry
  `38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`,
  and validator
  `8354a23f4f10e9f86d0012f9b3494b34a5815e9ef1e677a143f2805326537b63`.
- Exactly one next action: obtain final independent round-10 design review.

## Final Round-10 Non-Convergence Closure

- The immutable closure report is
  `docs/reviews/semantic_ingestion/m0a-c2-round10-non-convergence-2026-07-28.md`.
- The coordinator confirmed all seven final findings: absent recursive declared
  schema/enum application; unenforced terminal/replacement/reference/outcome
  matrices; absent profile, binding, and source-identity recomputation;
  unproved transitive enum exhaustiveness; skipped nested structured authority
  equality; incomplete full-input adversarial denominator; and no stable
  repository gate.
- Every finding and its product priority, approval disposition, type, attempted
  remediation, remaining uncertainty, and exact blocker is recorded in the
  immutable report. None is accepted as an approval limitation.
- The exact reviewed baseline remains architecture
  `93570981d938285ac5201044a365108a0f9d688dd3c78e50d16f15d95a8a88d8`,
  recipe
  `92ed8a14788a4ea6213f5778f0307a37983468e1bea01858f27eb88759dd6d07`,
  validator before closure sentinel
  `8354a23f4f10e9f86d0012f9b3494b34a5815e9ef1e677a143f2805326537b63`,
  and registry
  `38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`.
- The validator now fails this exact baseline closed with
  `ROUND10_INCOMPLETE_AUTHORITY`; its closure-sentinel SHA-256 is
  `e93ebf3665e6e4126bc5ba2daedf111c2f301cc69e3b56e4024aca204fb1446e`.
- Repository-local Ruff passed, repository-local Pyright reported zero errors
  and warnings, Python 3.12 compilation passed, and `git diff --check` passed.
- No production or C1 artifact changed. No further semantic remediation is
  authorized under this WorkPlan.
- Exactly one next action: obtain explicit authorization for a new narrow
  design iteration that supplies the missing executable authorities, or
  externally corrected design authority.

## Remediation Round 11

- The user authorized a second bounded block of ten rounds, increasing the
  cumulative ceiling from 10 to 20. The immutable round-10 non-convergence
  report remains unchanged historical evidence.
- Round 11 is limited to the seven confirmed residual design authorities:
  recursive declared-type validation; closed mutation compatibility;
  profile/binding/source-identity recomputation; transitive enum closure; deep
  nested authority equality; exhaustive full-candidate negative coverage; and
  a stable repository gate.
- No production, C1, elaborator-A, or elaborator-B change is authorized.
- The round-10 closure sentinel remains until every round-11 positive and
  negative check passes against one exact baseline.
- Schema-graph reconstruction found that only 46 of 56 inventory coordinates
  map directly to declared models. Eight `TraceabilityRegistryRoot.*`
  projections and two digest-tuple projections have no exact declared root
  shape, element type, ordering, cardinality, or duplicate policy.
- Two reachable fields remain explicitly open:
  `TraceabilityReportSchemaArtifact.schema_document: dict[str, object]` and
  `TraceabilityGoldenTypedInputFixtureBody.typed_input_value: object`.
  Choosing a finite projection or raw byte boundary changes the canonical
  schema/binding contract and cannot be inferred by the validator.
- Exactly one next action: obtain the external projection-versus-raw-boundary
  decision and exact shapes for these 12 unresolved graph nodes.

## Remediation Round 12

- This is the sole current-state section. Round-10 closure and round-11
  analysis remain historical evidence.
- Eight registry-root projections now have explicit wrapper and record models,
  stable identity keys, source order, exact empty/nonempty and cardinality
  rules, duplicate rejection, and their existing per-root digest domains.
- Both specialized digest tuples now carry exact `(id, version, digest)`
  coordinates in source-array order and reject empty, duplicate, reordered, or
  cardinality-mismatched input.
- The report-schema document and golden typed-input value now use
  `TraceabilityCanonicalContentBoundary`, binding schema/version, media type,
  canonical profile, nonempty bytes, size, and a domain-separated digest.
  Ambient dict/object input and dual-shape compatibility reject.
- Migration requires canonical legacy decoding and recomputation of every
  downstream binding; production and C1 remain unchanged.
- Architecture SHA-256 is
  `71edf574969476d535021f2bd8d04c4b26b2645cff5955de6684e8228af74b70`.
- Exact blocker: the recipe still contains two legacy `schema_document`
  projections and six legacy `typed_input_value` projections. Migrating them
  changes expansion trees, coverage paths, leaf denominators, item/root/
  generation/release bindings, and the recipe hash. Consequently the recursive
  56-root graph, exhaustive enum/Literal closure, recomputed source bindings,
  and complete static gate cannot be frozen truthfully against the current
  recipe this round.
- The validator remains fail-closed with `ROUND12_INCOMPLETE_AUTHORITY`.
- Frozen round-12 hashes are architecture
  `71edf574969476d535021f2bd8d04c4b26b2645cff5955de6684e8228af74b70`,
  unchanged recipe
  `92ed8a14788a4ea6213f5778f0307a37983468e1bea01858f27eb88759dd6d07`,
  validator
  `959cf2137d2ce6a18312d0049024967f80484e540d6f44123f3adbe8c3e492b4`,
  and unchanged registry
  `38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`.
- Repository-local Ruff passed, Pyright reported zero errors and warnings,
  Python 3.12 compilation passed, and `git diff --check` passed.
- Exactly one next action: migrate the eight legacy recipe values through an
  independent canonical-boundary generator, regenerate every dependent ledger
  and binding, and complete the recursive graph/static gate against that one
  new recipe baseline.

## Remediation Round 14

- The two previously missing typed-input authorities are frozen exactly:
  bootstrap-anchor fixture 01 and runner-report fixture 14, with their existing
  registered bindings and canonical CTV values. Both use
  `application/vnd.memorii.ctv+json;version=1`; ownership must preserve the
  existing acyclic dependency order.
- Exact blocker: the current recipe is a single minified authority document
  whose boundary migration changes six stored typed-value projections, two
  report-schema projections, three coverage ledgers, all leaf denominators,
  and downstream binding/source identities. No checked-in independent
  canonical-boundary generator exists, so rewriting those coupled values by
  hand would create unreviewable authority rather than independently derived
  evidence.
- Exactly one next action: add and independently review a standard-library
  boundary migration generator, then use it to regenerate the recipe and run
  the recursive/static gate against the resulting single baseline.

## Remediation Round 13

- Round 13 inspected the exact two `schema_document` and six
  `typed_input_value` legacy projections before writing the migration
  generator. The report-schema empty object can be canonically represented as
  `{}` under the declared JSON profile.
- The two authored golden typed-input payloads are not decodable legacy typed
  values. They are placeholder strings:
  `memorii-c2-golden-typed-input-fixture-typed-input-value-v1` and
  `memorii-c2-golden-vector-manifest-typed-input-value-v1`.
- Their sibling `target_schema_id` values are also unregistered placeholder
  identifiers and disagree with the schema IDs carried by
  `target_body_binding`. Consequently no standard-library generator can
  validate or canonically encode them under the declared target schema and
  binding without inventing a new typed value and target identity.
- The design does not freeze the golden typed-input media type. Selecting one
  changes the canonical boundary preimage and all dependent identities.
- No recipe, validator, package, production, C1, or elaborator artifact was
  changed. The round-12 sentinel and all immutable reports remain intact.
- Exactly one next action: externally freeze, for both golden typed-input
  occurrences, the complete valid typed payload, registered target schema and
  binding identity, and exact media type. Then the generator can migrate all
  eight projections and recompute downstream identities.

## Remediation Round 15

- Added the standard-library `migrate_recipe_v14_boundaries.py` with explicit
  recipe/design/registry/output paths and pinned round-14 input identities.
  Two isolated runs emitted byte-identical recipe SHA-256
  `c47ae5317ac404c6667949ba0a848f12115ae790e732ae58213037eb4b0ad64e`.
- The migration rejects unexpected legacy shapes, replaces both stored
  report-schema projections with canonical `{}` boundaries, and replaces the
  two authored plus two expanded typed-input values with exact fixture-01 and
  fixture-14 canonical CTV bytes. It regenerates all 49 stored expansions and
  coverage ledgers. New denominators are 2,096 typed, 14 raw, and 2,110 total.
- The validator independently checks boundary identity, size, canonical padded
  base64, and the domain-separated digest. It remains fail closed with
  `ROUND15_INCOMPLETE_AUTHORITY`.
- Coordinator scope disposition: the oracle-free recipe intentionally excludes
  derived body/preimage bytes, digests, signatures, envelopes, coordinates,
  roots, release bindings, and derived-package source identity. Those outputs
  belong exclusively to the linked implementation WorkPlan and must not become
  parallel recipe authority.
- The round-15 sentinel was removed after normal and `--self-test` validation
  passed the migrated recipe. The stable static gate pins architecture
  `bff1640cd6feff8561972ca30785a88e3d64503c4b72ec23826000f6fb55f90b`,
  recipe
  `c47ae5317ac404c6667949ba0a848f12115ae790e732ae58213037eb4b0ad64e`,
  and registry
  `38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`.
- Review-ready generator SHA-256 is
  `ba7e4df5fe9ef92a815401e705a9a45d37d320ce56d95fbbe4dce27b31366dcd`;
  validator SHA-256 is
  `8c6178cd4b89888df5b86ad7fe0a88947759e19effe0c5c9d5d4505a7cf08965`.
- Exactly one next action: fresh independent round-15 three-role design review.

## Remediation Round 16

- Round 16 began with the mandatory legacy-replay preservation check before
  modifying the migrated candidate.
- Exact blocker: the required v14 recipe bytes with SHA-256
  `92ed8a14788a4ea6213f5778f0307a37983468e1bea01858f27eb88759dd6d07`
  are absent from the workspace. The current recipe and Git index both contain
  only the migrated round-15 bytes with SHA-256
  `c47ae5317ac404c6667949ba0a848f12115ae790e732ae58213037eb4b0ad64e`.
  No temporary or history copy of the legacy bytes exists.
- The migration generator pins `92ed8a...` as its input, but a hash pin is not
  sufficient to reconstruct the byte sequence. Reverse-engineering the legacy
  recipe from the migrated output would require guessing replaced target IDs,
  bindings, placeholder values, coverage paths, and denominators and therefore
  would create new authority rather than preserve immutable evidence.
- No candidate, generator, validator, signer, generation, mutation, production,
  or C1 semantic change was made in this round.
- Exactly one next action: restore the exact v14 recipe bytes from an external
  immutable source or backup at
  `docs/design/semantic_ingestion/traceability_golden_vectors/history/recipe-v14-92ed8a14788a4ea6213f5778f0307a37983468e1bea01858f27eb88759dd6d07.json`;
  then replay the generator twice and resume the round-16 closure.

### Round-16 Coordinator Disposition And Resume

- The coordinator classified loss of the v14 bytes as an accepted historical
  evidence limitation. The migration generator and its v14 pin are historical,
  non-authoritative, excluded from completion, and make no compatibility
  claim. Reverse reconstruction is forbidden.
- The round-15 `c47ae...` recipe became newly authored canonical authority.
  Round 16 corrected every canonical-content boundary to include the mandated
  final LF and recomputed exact sizes and content digests. The resulting recipe
  SHA-256 is
  `fa51378729e729695bb7568ae4e32c412db139153057938e16d21e088896fff2`.
- The static gate now pins this current canonical recipe directly.
- Exact remaining blocker: signer known-answer/reference verification, the
  atomic G1-G3 table, recursive 56-root type graph and exhaustive enum closure,
  executable 66-case compatibility/outcome matrix, and full-candidate probes
  are not yet implemented together against this new baseline.
- Exactly one next action: implement those five closed validators and their
  adversarial probes against `fa513787...`, then run the complete pinned gate.

## Remediation Round 17

- Added independent four-signer schema, RFC 8032 seed/public-key/reference
  signature, key-digest, coordinate, purpose, and reference checks.
- Added atomic G1/G2/G3 identity/sequence/predecessor/manifest/pointer/index/
  fence validation, an exact 66-case descriptor/outcome digest, canonical
  boundary sibling checks, and full-candidate probes for each new family.
- Exact semantic blocker: declared
  `TraceabilityGoldenVectorArtifactKind` is the union of the 28-member
  `TraceabilityGenerationArtifactKind` and nine additional literals, so its
  transitive set has 37 members. The marked closed enum registry contains only
  the nine additions while simultaneously forbidding alias lookup or fallback.
  The two authorities cannot both govern exact CTV enum acceptance.
- Expanding the row to 37 is determinate but changes the marked enum digest,
  CTV profile, all 56 bindings, and recipe binding trees. Treating the row as a
  local delta instead requires changing the stated no-alias rule. Round 17 was
  scoped as design validation and did not authorize either profile-wide
  authority rewrite.
- Exactly one next action: select flattened 37-member enum authority with
  profile-wide recipe rebinding, or explicitly authorize compositional enum
  rows and define their resolution rule.

### Round-17 Coordinator Disposition And Resume

- The coordinator authorized the flattened 37-member enum authority and
  profile-wide recipe rebinding while preserving the no-alias-fallback rule.
- The marked registry, enum digest, CTV profile, all embedded schema bindings,
  and typed canonical-boundary payload bindings were independently recomputed.
  Frozen architecture SHA-256 is
  `57b50352cbe94b208aeff6e94130524f43aef339855f7eb7d15590e91b6d98b2`;
  recipe SHA-256 is
  `fbd2b399f8e6caf5e742b9f839b77a3a9f0fac6772a4c3ef7910fb11ff573abc`.
- Validator SHA-256 is
  `480fb7e3a0817cbb8675fb512f8b6d608a88d26251bd9940d719809b948d463e`;
  deterministic rebinding-tool SHA-256 is
  `630ad1f70163bc4af0739b4fd587b28c2b6e1dc1e2dcaad00bc89be598475d38`.
- Normal and full-candidate self-test validation pass 4/4 signers, the atomic
  G1/G2/G3 table, 57 fixtures, 66 descriptor/outcome rows, exhaustive enum
  alias membership, exact content-boundary siblings, and 2,096/14/2,110 leaf
  accounting.
- Remaining validation work: generic CTV recursion and top-level field closure
  pass, but the validator does not yet interpret every nested annotation,
  union, collection element, nullability branch, and constrained scalar across
  the 56-root graph. No semantic choice is unresolved; this is bounded code
  completion and must precede review.
- Exactly one next action: complete recursive declared-type validation, then
  run fresh independent round-17 spec, correctness, and test review.

### Round-17 Current Review Baseline

- This section is the sole current-state authority; every earlier round status,
  blocker, hash, and next action is historical and superseded.
- The authorized budget remains 20 rounds. The candidate is ready for fresh
  round-17 design review.
- The validator verifies all four fixed signers and RFC 8032 references; the
  atomic G1/G2/G3 generation table; all 66 closed mutation descriptor/outcome
  rows; exact canonical-boundary identities and payload siblings; and the
  recursive 56-root graph across reachable unions, Literals/enums,
  collections, and nullability.
- Full-candidate self-tests cover signer, generation-table, mutation-matrix,
  boundary, recursive-schema, enum, source-identity, leaf, owner, path,
  reference, and no-op failures. The pinned normal and adversarial gates pass.
- Repository-local Ruff, Pyright, Python compilation, and
  `git diff --check` pass.
- Current hashes are architecture
  `57b50352cbe94b208aeff6e94130524f43aef339855f7eb7d15590e91b6d98b2`,
  recipe
  `fbd2b399f8e6caf5e742b9f839b77a3a9f0fac6772a4c3ef7910fb11ff573abc`,
  validator
  `c60c9350fbd1f90c97e725813d01bebcf0c66b062c518abb859ced53bd6bf3c6`,
  and registry
  `38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`.
- The stale `verify_c2.py` is linked implementation debt under the
  implementation WorkPlan, not a design-authority gap.
- Exactly one next action: obtain fresh independent round-17 review from
  `spec_auditor`, `correctness_reviewer`, and `test_reviewer`.

## Remediation Round 18

- The coordinator selected tagged CTV enum encoding for every registered
  Literal/enum alias; bare strings are forbidden for those typed fields.
- Exact semantic blocker: the recursive 56-root graph reaches inline
  `Literal[...]` fields that have members but no registered enum schema
  identity. Examples include
  `CanonicalTypedValueProfileBinding.profile_id` and class-local
  `issuance_purpose`, state, policy, and constant-version fields. The marked
  enum registry contains only 11 named aliases. An enum CTV token requires an
  exact `schema` as well as `member`.
- Three incompatible rules remain possible: register each inline Literal as
  `<declaring-class>.<field>`; coalesce equal member sets under newly named
  semantic aliases; or identify each declaration by a schema fingerprint.
  They produce different CTV bytes, enum-registry digest, schema fingerprints,
  profile digest, all 56 binding digests, boundary payloads, and recipe source
  identity. The governing design does not select among them.
- No recipe regeneration or validator relaxation is valid until that identity
  rule is frozen. Hash-only integrity does not resolve semantic identity.
- Exactly one next action: externally select the canonical schema-ID rule for
  inline reachable Literals (recommended:
  `<declaring-class>.<field>`, with inherited fields retaining their declaring
  owner), after which round 18 can flatten the registry and regenerate the
  complete tagged-enum baseline.

### Round-18 Inline Identity Disposition And Residual Blocker

- The coordinator selected exact inline schema IDs as
  `<fully-qualified-declaring-class>.<field_name>`, inherited fields retaining
  their original declaring owner, named aliases retaining their marked alias
  ID, and no coalescing or aliases. This rule is now normative architecture.
- Exact residual semantic blocker: reachable inline Literals include
  non-string values such as `Literal[1]` and `Literal[True]`, while the current
  CTV enum token and validator require `member` to be a nonempty string. The
  selected exact-value/no-alias rule forbids converting these values to `"1"`
  or `"true"`.
- The remaining determinate alternatives are to widen enum `member` to a typed
  canonical scalar preserving integer/boolean identity, or to keep enum tokens
  string-only and exclude non-string Literals from enum registration. These
  produce different grammar, registry, fingerprints, profile, bindings, and
  recipe bytes.
- Exactly one next action: externally select typed-scalar enum members
  (recommended) or explicitly exempt non-string Literals; then regenerate the
  transitive registry and tagged baseline.

### Round-18 Typed-Scalar Disposition

- The coordinator selected typed canonical scalar enum members. The normative
  token now admits exact string, boolean, canonical integer-token, or null
  members; member identity is type-sensitive and containers, floats,
  coercion, stringification, and aliases reject.
- The earlier inline-member representation blocker is resolved. The remaining
  work is mechanical but incomplete: expand the marked registry, regenerate
  all enum-tagged CTV and bindings, and update the validator and negative
  corpus for typed-member equality.
- Exactly one next action: complete that regeneration and run the full pinned
  round-18 gate before review.

## Final Round-20 Non-Convergence Closure

- This section is the sole current-state authority. Every earlier current
  status, baseline, blocker, and next action is historical and superseded.
- The immutable report is
  `docs/reviews/semantic_ingestion/m0a-c2-round20-non-convergence-2026-07-28.md`.
- Confirmed findings are: missing independent all-56 profile/binding
  recomputation; contradictory enum-member and profile-preimage grammar;
  absent common mutation/re-elaboration pipeline with case-specific shortcuts;
  incomplete non-fixture-root evidence; stale prior WorkPlan claims; and
  incomplete registry-negative/full-candidate coverage.
- Exact reviewed hashes are architecture
  `4020901b7b50d1a3ea2eee774af52234ef2b9f943176af506a9f15fc41f777b0`,
  recipe
  `9d5dbe525c22707d33878a7ce6788ba267816e5aff2f79500aa40286cbb2e1e8`,
  validator before closure sentinel
  `1840ea4c43b7cad9386dac2f7a41c3d89e628e0775431a8b481628be85d797b4`,
  regenerator
  `770a3a8dfe6fde570e635f9075cb037cbf64d883e1e61d48d365ddb92f89b0aa`,
  and registry
  `38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`.
- The closure validator fails the exact baseline with
  `ROUND20_INCOMPLETE_AUTHORITY`; its post-sentinel SHA-256 is
  `04a32316bb6f2bb21cf9936ea8a530b9a07cca33d51ceafc7c0491d87a73d553`.
  Repository-local Ruff, Pyright, Python 3.12 compilation, and
  `git diff --check` pass. No production or C1 edit is part of closure.
- Exactly one next action: obtain explicit authorization beyond 20 rounds, or
  externally corrected authority resolving every confirmed finding.
