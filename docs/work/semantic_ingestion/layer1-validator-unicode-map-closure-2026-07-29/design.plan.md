# Layer 1 Validator Unicode And Map Grammar Closure

- Work ID: semantic-ingestion-layer1-validator-unicode-map-closure-2026-07-29
- Work type: design
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-07-29
- Last updated: 2026-07-29
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/layer1-validator-collection-closure-2026-07-29/design.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md` SHA-256 `67bf2620a0379761853861e416efba0816045ef4bf88e4808e701a9ac3bc993e`; `docs/design/semantic_ingestion/traceability_registry/registry-v1.json` SHA-256 `38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`; checked authority SHA-256 `89a98fc1e545f38c234ce42dbd164c85e3ddc6358856cca70e59dad7b1addc7b`; validator SHA-256 `830c63e33e8da7787aba57879e08587ecbbe583e25f00c225be3e24a19637d9c`; checker SHA-256 `2ca3da2c69b453e2107ab4e901345b4b5420288666561c566732849d56c811c1`
- Expected outputs: corrected design-side validator and checker, unchanged architecture/registry/authority/profile bytes, updated static-tooling pins, deterministic Unicode-scalar/map-arity evidence, and immutable independent design-review reports

## Objective

Correct the approved design-side CTV v2 validator so that it implements the
already normative strict Unicode-scalar UTF-8 serialization contract and the
closed two-argument `dict[str, T]` declaration grammar. The correction must
preserve the checked authority bytes, existing valid declaration behavior,
atomic publication guarantees, and hermetic checker boundary.

## Completion Contract

This design correction is complete only when:

- every accepted non-ASCII Unicode scalar is preserved exactly and emitted as
  strict UTF-8 JSON with no normalization;
- every lone surrogate or invalid UTF-8 input rejects before publication;
- marked UTF-8 schema content is accepted when otherwise valid;
- direct, quoted, nested, alias, inherited, reachable, and unprojected
  dictionary declarations reject unless they have exactly two arguments;
- valid `dict[str, T]`, finite tuples including `tuple[()]`, and the existing
  baseline declarations remain accepted;
- the validator self-test, exact two-replica checker, static checks, and
  atomic-publication evidence pass;
- the design, registry, checked authority, and profile identities remain
  unchanged;
- fresh independent `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer` passes leave no confirmed `blocks_approval` or
  `changes_required` finding in this bounded correction.

## Scope

Included:

- strict Unicode-scalar validation at design document, marked payload,
  canonical JSON, enum-registry, and authority serialization boundaries;
- UTF-8 canonical JSON output with `ensure_ascii=False`, sorted keys, compact
  separators, and one final LF;
- declaration-wide exact two-argument `dict` validation before projection can
  skip an unused declaration;
- validator-owned positive and negative self-test controls;
- checker identity/pin updates required by changed validator/checker bytes;
- `docs/development/static_tooling.md`, this WorkPlan, and immutable review
  reports.

Excluded:

- architecture semantics, registry members, checked authority contents,
  profile identity, reference compiler, implementation tests, CI workflow,
  production runtime code, and unrelated parser refactoring;
- Unicode normalization, case folding, lossy replacement, or ASCII-only
  fallback;
- new collection kinds or a broader Python annotation language.

Deferred:

- reference-compiler `tuple[()]`, Protocol annotation, Literal/Annotated
  metadata, and public-CLI paired evidence;
- CI job partitioning and exact pytest-argument structural enforcement;
- parent implementation repins and whole Layer1 review.

## Constraints And Invariants

- Section 3.23.4.2.1 is already normative: strings are Unicode scalar
  sequences; serialization is strict UTF-8; surrogates reject; no Unicode
  normalization occurs.
- A Python `str` containing a surrogate is not a valid Unicode-scalar string.
  Validation must recurse through keys and values before canonical emission.
- JSON object keys remain sorted according to the existing canonical contract.
  The correction may not change authority bytes when all frozen inputs are
  ASCII.
- `dict` is the only supported map declaration and requires exactly two type
  arguments; projection still independently requires the first normalized type
  to be `str`.
- Type-position strings are parsed as forward annotations. Literal values and
  Field metadata strings remain data and must not be reinterpreted as types.
- Failure before replacement preserves an absent target or a pre-existing
  target byte-for-byte and mode-for-mode, with no owned temporary residue.
- The checker remains executable only through the documented
  `python3.12 -I` content-addressed command and retains its audit isolation.
- Exactly one writer may modify the validator, checker, static tooling, and
  this plan at a time.
- The user-authorized bounded budget is five correction/review rounds.

## Sources Of Truth

1. `docs/design/memorii_spec.md`
2. `docs/design/memorii_storage_details.md`
3. `docs/design/event_model.md`
4. `docs/IMPLEMENTATION_RULES.md`
5. `docs/design/semantic_ingestion_architecture.md`, especially Section
   3.23.4.2.1 and the marked CTV v2 grammar
6. `docs/design/semantic_ingestion/traceability_golden_vectors/validate_ctv_binding_authority_v2.py`
7. `docs/design/semantic_ingestion/traceability_golden_vectors/check_ctv_binding_authority_v2.py`
8. `.agent/PLANS.md`, `.agent/skills/build-design/SKILL.md`, and
   `.agent/skills/review-design/SKILL.md`
9. Parent implementation WorkPlan and fresh Layer1 delta reviewer findings

If these disagree, the repository source precedence in `AGENTS.md` applies.
This WorkPlan may not amend the approved architecture.

## Problem Definition

The frozen architecture requires exact Unicode-scalar strings and strict UTF-8
canonical JSON. The current design validator serializes with
`ensure_ascii=True`, encodes marked payloads as ASCII, and does not reject
surrogate-bearing strings. It therefore rejects a valid non-ASCII schema
mutation while accepting an invalid surrogate mutation. Separately, its
declaration-wide type classifier validates collection arity for
list/tuple/set/frozenset but not `dict`, allowing an invalid unused
`dict[str]` or over-arity dictionary to escape validation before projection.

These are design-verifier defects, not ambiguities in product semantics. The
desired outcome is a narrow correction that makes the executable design
authority prove its own stated contract without changing valid authority.

## Requirements Ledger

| ID | Requirement | Source | Priority | Acceptance criteria | Status |
| --- | --- | --- | --- | --- | --- |
| VUM-001 | Canonical strings contain only Unicode scalar values and preserve them exactly | Architecture 3.23.4.2.1 | Required | Recursive valid non-ASCII controls emit literal UTF-8 bytes; lone surrogate controls reject before publication | approved |
| VUM-002 | Marked design payloads are strict UTF-8, not ASCII-only | Architecture 3.23.4.2.1 | Required | Coordinated valid non-ASCII declaration/registry mutation compiles; invalid UTF-8 and surrogates reject | approved |
| VUM-003 | Canonical authority JSON uses the frozen strict UTF-8 form | Architecture 3.23.4.2.1 | Required | `ensure_ascii=False`, compact sorted JSON plus one LF; frozen ASCII authority remains byte-identical | approved |
| VUM-004 | Every `dict` type declaration has exactly two arguments before projection | Closed CTV declaration grammar | Required | Direct, quoted, nested, alias, inherited, reachable, and unprojected one/three-argument maps reject; `dict[str, T]` accepts | approved |
| VUM-005 | Existing valid collection and publication behavior does not regress | Prior approved validator correction | Required | Baseline, `tuple[()]`, finite/variadic tuple, modes, atomic failures, and checker replicas pass | approved |
| VUM-006 | Content-addressed handoff remains exact and hermetic | Static tooling contract | Required | Validator/checker identities and static pins agree; exact `python3.12 -I` checker passes | approved |

## Non-Goals

- Changing the CTV v2 grammar or authority schemas.
- Supporting arbitrary Python calls, attributes, mappings, or annotations.
- Replacing the independent implementation compiler.
- Optimizing the complete Layer1 CI runtime.
- Implementing later semantic-ingestion milestones.

## Existing-System Analysis

- `canonical()` currently uses `ensure_ascii=True` and ASCII encoding, which
  produces valid ASCII escapes but contradicts the required literal UTF-8
  canonical form and does not reject surrogate-bearing Python strings.
- `marked()` decodes the full design as UTF-8 but then encodes every marked
  payload as ASCII, rejecting otherwise valid non-ASCII declaration content.
- `validate_type_expression()` invokes the shared collection validator for
  list/tuple/set/frozenset only. `dict` arguments recurse but arity is enforced
  later only if a declaration is projected by the normalizer.
- The independent implementation compiler already emits strict UTF-8 and
  rejects surrogates, so weakening it would create a circular workaround.
- Frozen current inputs are ASCII and should reproduce the same checked
  authority after the correction.

## Alternatives Considered

| Approach | Advantages | Disadvantages and risks | Decision |
| --- | --- | --- | --- |
| Keep ASCII escaping and treat it as equivalent JSON | No pin changes | Contradicts the exact-byte architecture and masks invalid scalars | Rejected |
| Normalize or replace invalid Unicode | Produces encodable output | Loses exact input identity and violates fail-closed behavior | Rejected |
| Validate only projected dictionaries | Minimal code | Leaves unused/Protocol/alias declarations as bypasses | Rejected |
| Share implementation compiler helpers | Less duplicate code | Destroys independent authorship and makes validation circular | Rejected |
| Add narrow recursive scalar validation plus declaration-wide `dict` arity | Directly implements existing semantics and preserves ownership | Requires new pins and comprehensive self-test evidence | Selected |

## Feasibility Evidence

- The independent compiler already demonstrates stdlib-only recursive
  Unicode-scalar validation and UTF-8 canonical output without changing the
  frozen authority bytes.
- Direct source inspection locates the validator defects in `canonical()`,
  `marked()`, and `validate_type_expression()`.
- The checked authority hash is stable because the frozen authority contains
  no non-ASCII scalar requiring a byte representation change.
- The existing validator self-test infrastructure supports coordinated marked
  design/registry mutations and publication failpoints.

## Failure And Operational Analysis

- Invalid UTF-8 fails while decoding source bytes. A decoded lone surrogate
  fails recursive scalar validation before digesting or writing output.
- A valid non-ASCII value must remain byte-identical through marked extraction,
  enum registration, canonical serialization, digesting, and output.
- One- or three-argument `dict` annotations fail during declaration validation,
  even when unused or hidden in a quoted/nested/Protocol path.
- No failure may truncate, replace, chmod, or leave temporary siblings at the
  target before the already documented atomic replacement boundary.
- Validator/checker pin changes are coordinated in one design revision; a
  mixed old/new bundle fails content-addressed identity checks.
- Rollback restores the prior validator/checker/static-tooling bundle. The
  architecture, registry, authority, and profile require no data migration.
- Observability remains deterministic exit status and exact diagnostic family;
  no network, clock, or ambient locale behavior is introduced.

## Milestones

### D1 - Correct Unicode And Dictionary Validation

- Purpose: make the executable design validator match the frozen scalar and
  declaration grammar.
- Bounded scope: validator, validator-owned self-tests, checker/pins, static
  tooling, and this WorkPlan.
- Expected artifacts: reviewed validator/checker hashes with unchanged
  authority and profile hashes.
- Verification: self-test; exact checker; targeted positive/negative probes;
  Ruff, Pyright, `py_compile`, report validation, and `git diff --check`.
- Status: complete.

### D2 - Independent Design Review And Freeze

- Purpose: establish that D1 is complete and did not broaden semantics.
- Bounded scope: fresh three-role read-only review, coordinator reconciliation,
  one correction worker if confirmed findings remain, and immutable reports.
- Expected artifacts: one or more immutable reports and a frozen approved
  design-tooling baseline.
- Verification: all confirmed findings mapped to direct evidence and no
  remaining `blocks_approval` or `changes_required` finding.
- Status: complete; fresh round-4 three-role review approved VUM-001 through VUM-006.

## Progress Log

- 2026-07-29: Fresh Layer1 implementation delta review exposed two
  design-verifier defects: ASCII-only/surrogate-permissive canonical handling
  and declaration-wide `dict` arity omission. Coordinator confirmed both
  against Section 3.23.4.2.1 and direct source. The parent implementation
  milestone is paused only at the affected verifier handoff. Next action:
  one design worker implements D1 under the five-round budget.
- 2026-07-29: D1 added recursive Unicode-scalar validation before canonical
  JSON serialization, strict UTF-8 marked-payload extraction/replacement, and
  declaration-wide binary-map validation. Validator-owned adversarial cases
  cover a coordinated `café` declaration/enum mutation, surrogate/invalid-UTF-8
  rejection, direct/quoted/nested/alias/inherited/Protocol one- and
  three-argument maps, unprojected valid maps, and `tuple[()]` preservation.
  The authority/profile and frozen source bytes remain unchanged. Next action:
  fresh independent three-role design review.
- 2026-07-29: Round-2 fresh spec and correctness reviews approved the bounded
  correction. The test review identified two family-completeness gaps:
  accepted Unicode evidence does not distinguish composed/decomposed nested
  keys and values, and valid binary-map evidence does not cover every sibling
  declaration route. The coordinator confirmed both as DREV-001 and DREV-002
  in immutable `docs/reviews/semantic-ingestion-layer1-validator-unicode-map-closure-2026-07-29/delta-round-01.md`.
  Next action: one evidence-only remediation worker closes both invariants.
- 2026-07-29: DREV-001 and DREV-002 were remediated without changing the
  grammar or frozen authority. The self-test now proves literal strict-UTF-8
  preservation of nested composed `café` and decomposed `cafe\u0301` object
  keys/values, exact compact sorted bytes, distinct encodings, and one final
  LF. It also proves the complete valid `dict[str, int]` route family: direct,
  whole-quoted, nested-list, reachable-alias, inherited, Protocol argument and
  return, and unprojected alias. Next action: final fresh three-role design
  review.
- 2026-07-29: Round-4 fresh spec, correctness, and test reviewers approved the
  complete candidate with no confirmed `blocks_approval` or
  `changes_required` finding. DREV-001 and DREV-002 are closed in immutable
  `docs/reviews/semantic-ingestion-layer1-validator-unicode-map-closure-2026-07-29/delta-round-02.md`.
  The design-tooling correction is frozen at validator `830c63e3...` and
  checker `2ca3da2...`. Next action: parent implementation handoff.

## Evidence Log

| Evidence | Result | Maturity |
| --- | --- | --- |
| Architecture lines 2344-2345 and Section 3.23.4.2.1 | Strings are exact Unicode scalar sequences; strict UTF-8; surrogates reject; no normalization | specified |
| Validator `canonical()` | Uses `ensure_ascii=True` and ASCII output | confirmed defect |
| Validator `marked()` | Encodes marked payload as ASCII | confirmed defect |
| Validator type classifier | Omits `dict` from preprojection arity validation | confirmed defect |
| Independent compiler Unicode test | Valid `café` emits literal UTF-8 and surrogate mutation rejects atomically | locally verified implementation evidence |
| Frozen input identities | Design `67bf2620...`, registry `38c45adc...`, authority `89a98fc1...`, validator `538a01f1...`, checker `2ca3da2...` | frozen starting baseline |
| D1 validator self-test | Passed; authority `89a98fc1...`, 56 schemas, 240 enum rows, profile `20edd38...` | locally verified |
| D1 targeted Unicode/map probes | Literal UTF-8 `café` emitted; escaped/byte surrogates and `dict[str]`/three-argument/nested maps rejected; `tuple[()]` accepted | locally verified |
| D1 exact isolated checker | `python3.12 -I ...check_ctv_binding_authority_v2.py` passed with validator `04ce1b5a...` and checker `2ca3da2...` | hermetic deterministic reproduction |
| D1 static checks | `py_compile` and `git diff --check` passed; coordinator located repository `.venv` and reran scoped Ruff (`All checks passed!`) and Pyright (`0 errors, 0 warnings, 0 informations`) | locally verified |
| Round-2 independent design review | Spec and correctness approved; test reviewer proposed DREV-001 and DREV-002; coordinator confirmed both against direct self-test evidence | reviewed / changes required |
| D3 validator self-test | Passed with authority `89a98fc1...`, 56 schemas, 240 enum rows, and profile `20edd38...` | locally verified |
| D3 exact isolated checker | `python3.12 -I` checker passed two hermetic replicas with validator `830c63e3...` and checker `2ca3da2...` | hermetic deterministic reproduction |
| D3 scoped static checks | `.venv/bin/ruff check` passed and `.venv/bin/pyright` reported `0 errors, 0 warnings, 0 informations`; `py_compile` and `git diff --check` passed | locally verified |
| D3 review-report validation | `validate_review_report.py delta-round-01.md` passed | locally verified |
| Round-4 final independent design review | Fresh spec, correctness, and test reviewers approved all VUM requirements and DREV closures; immutable `delta-round-02.md` | reviewed / approved |

## Decision Log

| Date | Decision | Alternatives considered | Evidence and rationale | Consequences |
| --- | --- | --- | --- | --- |
| 2026-07-29 | Reopen design tooling without reopening architecture semantics | Patch only the implementation compiler; weaken exact-byte requirements | The defects are in the approved validator and contradict explicit normative text | Layer1 implementation pauses until a reviewed validator/checker bundle exists |
| 2026-07-29 | Preserve design/registry/authority/profile bytes | Regenerate authority; change grammar | Frozen valid inputs are ASCII and already semantically correct | Only validator/checker/static-tooling pins may change |
| 2026-07-29 | Enforce Unicode scalar validity recursively before canonical serialization | Depend on JSON encoder errors; replace invalid characters | JSON can escape lone surrogates, so encoder success is not semantic validity | Invalid scalars fail before digest/publication |
| 2026-07-29 | Enforce `dict` arity in the declaration-wide type classifier | Keep normalizer-only enforcement | Unprojected and Protocol declarations can otherwise bypass it | All declaration paths share the same closed invariant |
| 2026-07-29 | Canonical UTF-8 also validates length-prefixed string inputs | Retain ASCII-only LP encoding; validate only JSON | CTV preimages are strict UTF-8 string components, and shared scalar validation prevents an adjacent surrogate bypass | ASCII frozen preimages remain byte-identical; non-ASCII future values are exact UTF-8 |
| 2026-07-29 | Prove accepted Unicode/map equivalence classes with self-test fixtures, not special runtime branches | Rely on one `café` substring and direct-map acceptance | DREV-001/002 require exact accepted-path evidence across recursive scalar and sibling map routes | No grammar or artifact semantics changed; only deterministic proof expanded |

## Review Log

| Round | Reviewers | Scope and findings | Coordinator disposition | Resulting action |
| --- | --- | --- | --- | --- |
| Pre-correction | Parent Layer1 `spec_auditor`, `correctness_reviewer`, `test_reviewer` | Correctness identified Unicode scalar/UTF-8 and unprojected `dict` arity gaps; spec/test found separate implementation-only tuple, Protocol, metadata, and CI gaps | Unicode and `dict` findings confirmed; other findings remain parent implementation work | Open this linked design correction |
| Round 2 | Fresh `spec_auditor`, `correctness_reviewer`, and `test_reviewer` | DREV-001 incomplete recursive exact-preservation proof and DREV-002 incomplete valid map-route family; immutable report `docs/reviews/semantic-ingestion-layer1-validator-unicode-map-closure-2026-07-29/delta-round-01.md` | Both confirmed as `Not applicable / changes_required / verification`; no semantic ambiguity | One remediation worker adds invariant-level accepted-path evidence, then final fresh review |
| Round 3 | One bounded design remediation worker | DREV-001 and DREV-002 corrected in validator-owned self-tests; no new finding | Implemented; pending final independent review | Freeze candidate validator `830c63e3...` and run fresh three-role review |
| Round 4 | Fresh `spec_auditor`, `correctness_reviewer`, and `test_reviewer` | All reviewers approved VUM-001 through VUM-006 and DREV-001/DREV-002 closure; test reviewer supplied only a non-blocking evidence-language clarification | Approved; checker replicas classified as hermetic reproducibility, not independent compilation | Complete this design WorkPlan and resume parent implementation |

## Blockers And Limits

- Iteration budget: five bounded correction/review rounds authorized by the
  user on 2026-07-29.
- Rounds used: four (D1 correction, first independent review, DREV remediation,
  and final independent review).
- Current blocker: none in this design correction.
- External limits: remote CI and branch-protection evidence are unavailable
  and are not required to correct this local design authority.
- Resume condition: satisfied by the approved round-4 frozen
  validator/checker bundle.

## Next Action

Parent coordinator freezes validator `830c63e3...` and checker `2ca3da2...` in
the implementation WorkPlan, then resumes the bounded Layer1 consumer
remediation.

## Outcome And Retrospective

Complete. The design validator now implements and behaviorally proves exact
Unicode-scalar UTF-8 handling and declaration-wide binary-map arity while
preserving the architecture, registry, checked authority, profile, and checker
bytes. Four bounded rounds were used; one authorized reserve round was not
needed. Remote CI and parent consumer enforcement remain explicitly outside
this design completion.
