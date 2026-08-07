# M0A-C2 Layer 1 Canonical Serialization And Bindings

- Work ID: semantic-ingestion-m0a-c2-layer1-ctv-bindings-2026-07-28
- Work type: design
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-07-28
- Last updated: 2026-07-28
- Parent WorkPlan: `docs/work/semantic_ingestion/m0a-c2-canonical-package-closure-2026-07-28/design.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/implementation.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md`; `docs/design/semantic_ingestion/traceability_registry/registry-v1.json`
- Expected outputs: frozen CTV v2 authority, hermetic validator/checker, design evidence, and an explicit PR-gate implementation handoff

## Objective

Freeze one corpus-independent C2-only canonical typed-value profile, recursive
schema authority, enum registry, 56 schema fingerprints, and 56 binding
identities from design bytes alone.

## Completion Contract

This design WorkPlan can become `complete` only after all of the following
named evidence is present and reconciled:

| Requirement | Completion evidence |
| --- | --- |
| L1-001 | Frozen design and authority hashes prove the legacy v1 grammar, digest domain, and compatibility claim are unchanged |
| L1-002 | The frozen design hash identifies exactly one marked CTV v2 grammar and the authority records its exact profile preimage and digest |
| L1-003 | The frozen authority contains exactly 56 unique coordinates and the hermetic gate proves recursive compilation and fail-closed unsupported-type behavior |
| L1-004 | The frozen authority contains the exhaustive typed enum registry and mutation evidence rejects missing, extra, duplicate, aliased, or shadowed members |
| L1-005 | The frozen authority hash binds all 56 normalized graphs, fingerprints, binding preimages, and binding digests; two hermetic reproductions are byte-identical |
| L1-006 | Design rules and negative mutations prove v1/v2 non-interchangeability and mandatory v2 identity for C2 artifacts |
| L1-007 | Validator/checker hashes and import/input inspection prove compilation consumes only the pinned design, registry, authority, and standard library |
| L1-008 | The frozen design publishes every byte, formula, schema graph, enum, fingerprint preimage, and binding preimage required for a separately authored compiler; implementation proof remains pending and must share no parser/normalizer implementation with the design validator |
| L1-009 | The exact pinned PR command and fail-closed acceptance are recorded in the parent implementation WorkPlan as pending necessary enabling work; CI wiring remains deferred to implementation and is not achieved design evidence |

Completion additionally requires three fresh independent iteration-18 reviews
(`spec_auditor`, `correctness_reviewer`, and `test_reviewer`) over the complete
frozen candidate, coordinator reconciliation of every finding, no confirmed
`blocks_approval` or `changes_required` design finding, scope and exclusions
remaining unchanged, no unresolved design ambiguity, and all exact hermetic,
Ruff, Pyright 3.12, `py_compile`, and diff checks passing against the recorded
hashes.

## Problem Definition

C2 artifacts require stable schema and binding identities that two independent
implementations can reconstruct without importing production models or corpus
values. Without a closed static language, exhaustive enum authority, and
content-addressed evidence, equivalent-looking compilers can accept different
schemas or silently overwrite declarations. The desired outcome is one
fail-closed, reproducible design authority suitable for later implementation.

## Scope

Included: canonical serialization grammar, recursive schema/type graph,
profile preimage, enum authority, schema fingerprints, binding preimages,
machine-readable binding authority, compatibility, and deterministic
design-side validation.

Excluded: recipe or corpus values, signers, fixtures, package lifecycle,
generation topology, releases, mutations, verifier A/B, production, C1, and
modification of repository CI configuration in this design round.

Explicitly deferred: a separately authored production/reference compiler that
proves L1-008 without sharing the design validator's parser or normalizer, and
wiring the exact pinned command into repository PR CI with clean-checkout
evidence for L1-009. Both are pending necessary enabling work in the parent
implementation WorkPlan.

## Non-Goals

This layer does not define corpus values, signing, fixtures, release lifecycle,
generation topology, mutations, verifier A/B behavior, production wiring, C1,
or repository CI implementation.

## Requirements Ledger

| ID | Requirement | Source | Priority | Acceptance criteria | Status |
| --- | --- | --- | --- | --- | --- |
| L1-001 | Preserve legacy `semantic_ingestion_typed_value/v1` | Approved architecture | Required | No v1 grammar, digest, or compatibility claim changes | evidenced |
| L1-002 | Define C2-only `semantic_ingestion_typed_value/v2` | Approved architecture | Required | One exact marked grammar and profile preimage | evidenced |
| L1-003 | Freeze 56-coordinate recursive schema graph | Approved architecture | Required | Every coordinate maps once; unknown or unsupported type fails | evidenced |
| L1-004 | Freeze all named and inline enums | Approved architecture | Required | Exact schema IDs, typed scalar members, no aliases or declaration collisions | evidenced |
| L1-005 | Freeze 56 fingerprints and bindings | Approved architecture | Required | Machine artifact contains every preimage input and digest | evidenced |
| L1-006 | Fail-closed compatibility | Approved architecture | Required | v1 and v2 never interchange; every C2 artifact requires v2 | evidenced |
| L1-007 | Prove corpus independence | Approved architecture | Required | Validator accepts only pinned design, registry, and authority inputs | evidenced |
| L1-008 | Enable independent compilation | Approved architecture | Required | Design publishes complete deterministic bytes/formulas; implementation must derive the byte-identical full authority and equivalent key rejection with no shared parser/normalizer code | design complete; implementation proof handed off |
| L1-009 | Hand the approved gate to implementation | Repository workflow | Required handoff | Parent implementation plan records exact fail-closed PR CI acceptance without claiming execution | handoff complete; implementation pending |

## Constraints And Invariants

- Governing source precedence follows repository `AGENTS.md`.
- Public and persisted schemas remain explicit and unknown syntax fails closed.
- Design bytes, not Python imports, runtime reflection, corpus values, or
  fixtures, own the CTV v2 authority.
- Classes and aliases share one declaration namespace with no duplicate or
  last-write-wins behavior.
- Candidate design evidence cannot be represented as completed production or
  CI behavior, and same-validator replicas cannot be represented as an
  independently authored compiler.

## Sources Of Truth

In precedence order: repository `AGENTS.md`, `.agent/PLANS.md`, the approved
`docs/design/semantic_ingestion_architecture.md`, the raw registry,
`docs/development/static_tooling.md`, the content-addressed authority and
validator/checker, and this WorkPlan. If these disagree on product semantics,
the governing design wins and the review stops; the WorkPlan cannot amend it.

## Existing-System Analysis

The Layer-1 authority is design-side tooling under
`docs/design/semantic_ingestion/traceability_golden_vectors/`; it does not
import `memorii` production packages. The architecture owns the marked grammar,
enum registry, inventory, and schema fences. The checker verifies pinned input
identities, runs the same validator in two isolated environments, invokes
adversarial self-tests, and compares generated bytes to the committed
authority. This proves hermetic deterministic reproduction, not independent
compilation. Repository PR CI does not
yet invoke this command; that integration belongs to the parent implementation
WorkPlan.

## Assumptions And Open Questions

- Verified facts: all 56 coordinates and 240 enum rows compile; two isolated
  runs of the same validator match; the design authority is corpus-independent.
- Working assumptions: repository CI can invoke the documented Python 3.12
  command without changing its semantics.
- Unresolved questions: none affecting this design.
- Decisions requiring external input: none. CI wiring remains authorized
  implementation work, not an external semantic decision.

## Decision Log

| Date | Decision | Alternatives considered | Evidence and rationale | Consequences | Owner |
| --- | --- | --- | --- | --- | --- |
| 2026-07-28 | Use profile ID/version `semantic_ingestion_typed_value` / `2` | Mutate v1; combine grammars | Durable v1 compatibility requires a distinct C2 domain | C2 artifacts require v2; v1 remains unchanged | Design |
| 2026-07-28 | Encode enum members as exact strings, booleans, canonical integer tokens, or null | Runtime enum reflection; untyped JSON coercion | Typed canonical tokens avoid language/runtime ambiguity | Unsupported values reject | Design |
| 2026-07-28 | Derive inline enum IDs from declaring owner and field; preserve inherited owner and marked alias ID | Consumer/root ownership; inferred aliases | Declaration identity is stable under inheritance and traversal | Compilers must retain declaring-owner provenance | Design |
| 2026-07-28 | Fingerprint the recursively normalized declared type graph | Source text; runtime reflection; corpus inference | The graph is formatting-, environment-, and corpus-independent | The static schema language must be closed and fail-closed | Design |
| 2026-07-28 | Bind profile digest, schema coordinate, and schema fingerprint | Coordinate-only or fingerprint-only identity | All three dimensions are required to prevent substitution | Every binding preimage exposes all three inputs | Design |
| 2026-07-28 | Defer independent compiler proof and PR CI wiring to implementation | Treat same-validator replicas as independent; modify production/CI during design; omit acceptance | Same-validator isolation proves reproducibility only; workflow ownership separates design evidence from implementation changes | L1-008 implementation proof and L1-009 PR enforcement remain pending and cannot be claimed achieved | Parent implementation coordinator |

## Alternatives Considered

| Alternative | Decision |
| --- | --- |
| Mutate v1 for C2 | Rejected: breaks durable legacy meaning |
| Permit both enum grammars in one profile | Rejected: noncanonical decoding |
| Fingerprint Markdown/Python source text | Rejected: formatting-dependent |
| Infer schemas from corpus values | Rejected: circular authority |
| Add a C2-only v2 profile | Selected |

## Feasibility Evidence

The standard-library design validator reconstructs the complete authority from
pinned source bytes, and the checker executes that same validator twice in
isolated environments. This proves deterministic hermetic reproducibility, not
independent compilation. The published bytes, formulas, graphs, and preimages
make a separately authored compiler feasible; its non-shared implementation
proof remains pending. Adversarial mutations exercise syntax, graph, enum,
declaration identity, fingerprint, binding, compatibility, and source-identity
failure paths in the design validator.

## Failure And Operational Analysis

Malformed syntax, unsupported annotations, unresolved references, duplicate
declarations, enum drift, digest drift, source replacement, or replica
disagreement terminate nonzero. No retry or concurrent mutation semantics
exist in this design-only compiler. There is no persisted-data migration:
legacy v1 remains readable and C2 requires v2. Rollback means restoring the
previous content-addressed design/authority/checker set together. CI
enforcement and operational monitoring remain pending implementation work.

## Verification Strategy

Each L1 requirement maps to the exact deterministic evidence in the Completion
Contract and Validation Matrix. The strongest applicable level is hermetic
reconstruction plus adversarial mutation for serialization and authority
claims, static analysis for tool integrity, direct inspection for dependency
isolation, and fresh independent review for specification completeness. The
separately authored compiler and future PR invocation are verified only during
implementation and are not part of the achieved design evidence.

## Validation Matrix

| Evidence | Required result |
| --- | --- |
| Marked grammar parse | Exactly one v2 grammar |
| Inventory parse | Exactly 56 unique Unicode-sorted coordinates |
| Recursive graph compile | Every reference resolves; unsupported annotation rejects |
| Enum compile | Every reachable Literal has one exact registry row |
| Authority recomputation | All fingerprints/profile/bindings byte-identical |
| Negative mutations | Missing/extra root, enum, member, edge, fingerprint, or binding rejects |
| Corpus isolation scan | No recipe, fixture, package, signer, or mutation input |
| Static checks | Ruff, Pyright, `py_compile`, and diff check pass |
| Independent compiler handoff | Separately authored production/reference compiler shares no parser/normalizer implementation, derives the byte-identical full authority from frozen design plus registry, and exhibits equivalent key rejection; pending implementation |
| PR-gate handoff | Exact clean-checkout pinned command is recorded as pending necessary enabling work in the parent implementation WorkPlan |

## Milestones Or Experiments

| Milestone | Purpose | Bounded scope | Expected artifacts | Verification | Status |
| --- | --- | --- | --- | --- | --- |
| Layer-1 authority | Freeze CTV v2 serialization, schema, enum, fingerprint, and binding authority | L1-001 through L1-008 design completeness | Design markers, registry, authority, validator, checker, static command | Hermetic deterministic reconstruction, adversarial mutations, static checks | under-review |
| Independent compiler handoff | Preserve L1-008 implementation proof without misclassifying same-validator replicas | L1-008 implementation evidence only | Parent implementation scope and validation entries | Separately authored compiler derives byte-identical full authority and equivalent key rejection without shared parser/normalizer code | pending implementation |
| PR-gate handoff | Preserve operational enforcement acceptance without changing CI in design work | L1-009 only | Parent implementation scope and validation entries | WorkPlan inspection now; clean-checkout PR failure proof during implementation | pending implementation |

## Progress Log

- 2026-07-28: Iterations 1-16 progressively closed grammar, provenance,
  hermeticity, inheritance, binding, schema-language, projection, enum, tagged
  union, and declaration-identity gaps. Each iteration preserved useful
  evidence below and advanced only after deterministic checks.
- 2026-07-28: Iteration 17 added the reverse real-member class-then-alias
  mutation, aligned this WorkPlan with `.agent/PLANS.md`, refreshed the
  validator pin, and set fresh independent review as the sole next action.
- 2026-07-28: Iteration 18 corrected the independent-compilation evidence
  claim. Two isolated same-validator runs remain deterministic hermetic
  evidence; a separately authored compiler proof is now explicitly pending in
  the parent implementation WorkPlan.

## Evidence Log

- Canonical design, registry, authority, validator, and checker paths and
  current SHA-256 identities are listed under Current State.
- The exact pinned command is in `docs/development/static_tooling.md`; it
  runs the same validator in two isolated environments and executes
  adversarial self-tests.
- The parent implementation scope and validation ledgers record the L1-008
  independent compiler and L1-009 PR gate as pending necessary enabling work.
- Iteration-specific hashes, mutations, review findings, dispositions, and
  resulting actions remain preserved below.

## Current State

The governing split is selected and recorded in the architecture: legacy v1
remains historical and unchanged; C2 uses only v2. The machine-readable v2
authority now contains the exact marked grammar, exhaustive enum registry,
56-coordinate inventory, recursively normalized type graphs, profile preimage,
schema fingerprints, and all 56 binding preimages/digests.

Iteration 2 found and corrected one declaration-derived omission in the marked
enum block: the structural-rules registry wrapper makes
`TraceabilityStructuralRuleSource.selector_kind` and
`TraceabilityStructuralRuleSource.effect` reachable, but neither row was
present. The exact inline rows were added from their declared Literals. No v1
formula, profile, digest, or compatibility claim changed.

Current frozen evidence:

- design SHA-256:
  `67bf2620a0379761853861e416efba0816045ef4bf88e4808e701a9ac3bc993e`;
- raw registry SHA-256:
  `38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`;
- authority SHA-256:
  `89a98fc1e545f38c234ce42dbd164c85e3ddc6358856cca70e59dad7b1addc7b`;
- authority validator SHA-256:
  `f0f74bc704e1eb1aab97cff3ea1bd7e6055dd60bab1c3fed0d63d24f4f026ea8`;
- hermetic checker SHA-256:
  `bc31ed0d15cf7aed3d7a7fdbe84d5df0f1e63df95aacde7a7a40dcabf8cbeba7`;
- v2 profile digest:
  `20edd38a4ef41e4abf7e1b9a65fe2745e65705f80ec8f93c48c658739b7660a0`.

The standard-library validator reads only explicit design, raw registry, and
authority paths. It imports no Memorii, Pydantic, corpus, recipe, signer,
fixture, package, or production module. It independently parses the unique
marked v2 grammar, distinct v2 exhaustive enum block, and exact
56-coordinate inventory; compiles every reachable class, inherited field,
alias, union, collection, nullability edge, constraint, enum, and finite model
reference; and recomputes every canonical byte, formula-domain preimage, and
digest.

Two consecutive `--write --self-test` runs produced byte-identical authority
bytes and the same SHA-256. Adversarial checks reject v1 profile substitution,
extra root, missing schema, enum-member addition, binding substitution, and v1
grammar substitution. Isolated `py_compile`, scoped Ruff, scoped Pyright, and
`git diff --check` pass.

## Blockers And Limits

No unresolved design blocker, ambiguity, or confirmed `blocks_approval` or
`changes_required` finding remains. Eighteen bounded design-review iterations
were used. The separately authored compiler proof and repository CI
enforcement are implementation responsibilities handed to the linked
implementation WorkPlan; their pending state does not weaken or reopen this
completed design. This WorkPlan may not repair corpus, package, production, or
CI behavior.

## Next Action

Execute the linked implementation WorkPlan's active Layer-1 milestone: build
the separately authored compiler and wire the exact pinned hermetic command
into the repository PR gate for SIA-R03/L1-008/L1-009.

## Iteration 3

- V2 has an exact token algebra independent of v1. Historical v1 enum marker
  bytes remain unchanged; the distinct v2 registry contains exactly 240 rows.
- Authority and validator use the required `traceability_golden_vectors`
  paths. Two consecutive write/self-test runs produced identical bytes.
- Hashes are architecture
  `b4891a2808c324f2ae29ba2bba913a4f71851bf80d93a76998d8f5f8cdade8be`,
  authority
  `af2cfd8ece8f59fae5b325cea84489b496d1df4279a4acbc31dc7b6b65c76082`,
  validator
  `1e50093b2a16c1e850533070d6c8ab9b32fabea462f7bcff9e6f345cab5a2b42`,
  and profile digest
  `20edd38a4ef41e4abf7e1b9a65fe2745e65705f80ec8f93c48c658739b7660a0`.
- Exactly one next action: fresh iteration-3 review by `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer`.

## Iteration 4 Provenance Blocker

- The requested historical source
  `git show 945d6ea:docs/design/semantic_ingestion_architecture.md` was
  inspected before any v1 edit. It contains no
  `[SIA-CTV-ENUM-REGISTRY-V1-BEGIN]` or
  `[SIA-CTV-ENUM-REGISTRY-V1-END]` marker and therefore no v1 block bytes to
  restore.
- Repository history for the architecture contains no later committed revision
  that introduces the marker. The marker was created only in the current
  uncommitted design sequence; its former 11-row bytes are not preserved as a
  committed blob or immutable history artifact.
- The current v1 marker contains the expanded 240-row content. Calling those
  bytes historical v1, reconstructing former formatting from chat, or selecting
  an inferred 11-row serialization would fabricate the raw/canonical digest
  authority that iteration 4 explicitly requires.
- No v1 or v2 block byte was changed in this iteration. The failed recovery
  attempt was read-only.
- Exactly one next action: provide a content-addressed blob containing the
  exact historical v1 marked block bytes, or explicitly authorize a new
  declared v1 baseline with acknowledged evidence loss and no claim of
  byte-for-byte historical restoration.

### Iteration-4 Coordinator Disposition And Resume

- The coordinator authorized the present 240-row v1 block as new baseline
  `semantic_ingestion_typed_value/v1-baseline-2026-07-28`, with explicit
  evidence loss and no historical, persisted, operational, compatibility, or
  certification claim. Its raw/canonical payload hashes are pinned in design.
- V1 is immutable from this baseline. V2 consumes only the distinct v2 marker.
- The validator now parses the v2 grammar as an exact closed key/value map and
  derives profile ID/version from that parsed grammar. Missing, extra,
  duplicate, malformed, or altered rows reject.
- Two write/self-test runs produced identical authority SHA-256
  `af2cfd8ece8f59fae5b325cea84489b496d1df4279a4acbc31dc7b6b65c76082`.
  Architecture SHA-256 is
  `b4891a2808c324f2ae29ba2bba913a4f71851bf80d93a76998d8f5f8cdade8be`;
  validator SHA-256 is
  `1e50093b2a16c1e850533070d6c8ab9b32fabea462f7bcff9e6f345cab5a2b42`.
- Ruff, Pyright, Python compilation, and diff checks pass.
- Exactly one next action: fresh iteration-4 three-role design review.

## Iteration 5 Source And Hermetic Closure

- The lingering v2 prose now references only
  `[SIA-CTV-ENUM-REGISTRY-V2-BEGIN/END]` and v2 digest/preimage domains. The
  preceding v1 prose is explicitly scoped to the declared v1 baseline.
- V2 source identity replaces only the separately marked v1 enum payload with
  a fixed sentinel before hashing. Source-level self-tests prove a v1-only
  mutation leaves complete v2 authority bytes unchanged, while v2 grammar,
  marker, profile, and registry mutations reject or change authority without
  changing the v1 marked payload.
- Every v2 grammar row is independently tested for missing and altered forms;
  extra, duplicate, profile-ID, profile-version, missing-marker, and
  substituted-marker mutations are also tested.
- The hermetic gate AST-checks the validator's imports against a closed stdlib
  allowlist, runs it with a runtime read audit from two initially empty
  temporary directories containing only copied design, registry, validator,
  and generated authority paths, proves A equals B equals checked authority,
  then validates both replicas without write mode.
- Frozen iteration-5 hashes are architecture
  `7d8f625bb01685d295e923cd6606866f15071c1c3b0f5e40a4d821c5785b4a64`,
  authority
  `14ffa5cbd23e7da088d286baf3e5db9746fafe9ae5f2907a6e9115e414b81431`,
  validator
  `ec6ecbe9f842a58a0e04e9f0ddff5c04f82ff624a10ffb1769cb6f4cd6625c73`,
  hermetic gate
  `7927a5a9d55e9eda57ded8745583eb729d189756780242e376fb1912e9a7da3f`,
  registry
  `38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`,
  and profile digest
  `20edd38a4ef41e4abf7e1b9a65fe2745e65705f80ec8f93c48c658739b7660a0`.
- The exact hermetic command documented in
  `docs/development/static_tooling.md` exits 0 with two replicas.
- Exactly one next action: fresh iteration-5 review by `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer`.

## Iteration 6 Gate Hardening

- The checker now requires and verifies expected SHA-256 arguments for the
  design, registry, checked authority, validator, and checker before executing
  validation. The checker self-hash is pinned externally in the reviewed
  static-tooling command, avoiding self-reference.
- It independently requires exactly 56 schema rows, 240 enum rows, and profile
  digest
  `20edd38a4ef41e4abf7e1b9a65fe2745e65705f80ec8f93c48c658739b7660a0`.
- It extracts the v1 marked payload and verifies the design-pinned raw digest
  `2920db6d459a29a2a411723c9cae77bdcfc6a166d82a02625acb3f918a62ba26`
  and canonical digest
  `87e0b38fe1db6505bc0b736f3a7d0fbabcbe028c49c9da702413ae73a048d8a5`.
  A v1-only mutation must fail this baseline-integrity check, while the
  validator's isolated v2 derivation self-test remains byte-identical.
- The validator source self-test mutates the raw registry bytes and proves the
  source identity changes so the checked authority rejects.
- Both isolated write/self-test and no-write runs execute via a checker-owned
  bootstrap that installs `sys.addaudithook` before `runpy.run_path`.
  Non-runtime file access is deny-by-default except the copied validator,
  design, registry, and authority; network, subprocess, process creation,
  environment mutation, and external file events reject.
- The AST gate retains the closed stdlib import allowlist and additionally
  rejects relative imports and top-level calls/reads other than the conventional
  `__main__` dispatch.
- Frozen iteration-6 hashes are design
  `7d8f625bb01685d295e923cd6606866f15071c1c3b0f5e40a4d821c5785b4a64`,
  registry
  `38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`,
  authority
  `14ffa5cbd23e7da088d286baf3e5db9746fafe9ae5f2907a6e9115e414b81431`,
  validator
  `ec4a2348dc78e25c45d8cb015abfb063f7ad736b510763875313c5b555c7beec`,
  and checker
  `d420f8cfe2099176b86c71fb33fcea7057e175d5c010a87ded6c3b3102b7dd1a`.
- Exactly one next action: fresh iteration-6 review by `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer`.

## Iteration 7 Inheritance Closure

- Iteration-6 `spec_auditor` and `correctness_reviewer` passes produced no
  confirmed correction in the Layer-1 scope. The `test_reviewer` identified
  one verification finding: `Compiler.class_fields()` silently ignored
  non-local base expressions.
- Coordinator disposition: confirmed; product priority `Not applicable`,
  approval disposition `changes_required`, finding type `verification`.
  Evidence was the prior loop, which recursed only for a local `ast.Name` and
  otherwise continued without rejection.
- The correction is fail closed and bounded to schema compilation. A class may
  have no base, the single inert external base `BaseModel`, or one single local
  declared model base. Unknown named bases, qualified bases, generic bases,
  multiple inheritance, and cyclic local inheritance reject.
- Source-level self-tests mutate a reachable `BaseModel` declaration to
  `UnknownBase`, `models.BaseModel`, `BaseModel[str]`, and two bases and require
  rejection. The complete baseline proves legitimate `BaseModel`; an injected
  local declared parent proves local inheritance remains supported.
- Canonical authority output, its SHA-256
  `14ffa5cbd23e7da088d286baf3e5db9746fafe9ae5f2907a6e9115e414b81431`,
  all 56 fingerprints/bindings, and profile digest remain unchanged. Updated
  validator SHA-256 is
  `6fbc5472134eddafdc972a1486c79f4f7dbe5d7667adc802eccf9b0bb9eee13f`;
  checker SHA-256 remains
  `d420f8cfe2099176b86c71fb33fcea7057e175d5c010a87ded6c3b3102b7dd1a`.
- Exactly one next action: fresh iteration-7 review by `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer`.

## Review Log

| Iteration | Reviewer | Finding | Disposition | Evidence and action |
| --- | --- | --- | --- | --- |
| 6 | `spec_auditor` | No confirmed correction | already resolved/no action | Complete Layer-1 authority reviewed |
| 6 | `correctness_reviewer` | No confirmed correction | already resolved/no action | Complete Layer-1 authority reviewed |
| 6 | `test_reviewer` | Non-local base expressions could be silently ignored | confirmed; `Not applicable` / `changes_required`; verification | Iteration 7 rejects unsupported inheritance and adds source mutations |
| 7 | three-role independent review | Local `BaseModel` shadowing could be accepted as the inert external base | confirmed; `Not applicable` / `changes_required`; verification | Iteration 8 rejects declared or aliased `BaseModel` |
| 7 | three-role independent review | Local-inheritance positive proof asserted only changed source output | confirmed; `Not applicable` / `changes_required`; verification | Iteration 8 asserts graph ownership/order plus fingerprint/binding semantics |
| 7 | three-role independent review | Zero-base preservation and reachable local inheritance cycles lacked explicit proof | confirmed; `Not applicable` / `changes_required`; verification | Iteration 8 adds semantic preservation and rejection checks |
| 8 | three-role independent review | Reserved `BaseModel` detection covered only class and simple assignment bindings | confirmed; `Not applicable` / `changes_required`; verification | Iteration 9 uses a general module-binding collector and exact mutation matrix |
| 9 | three-role independent review | Module-scope augmented assignment and deletion targets were omitted from reserved-name collection | confirmed; `Not applicable` / `changes_required`; verification | Iteration 10 collects `AugAssign`/`Delete` targets and tests three exact forms |
| 10 | three-role independent review | Dynamic namespace mutation remained possible because unsupported executable module syntax was parsed rather than rejected as outside the static compiler language | confirmed; `Not applicable` / `changes_required`; verification | Iteration 11 defines and enforces a closed declarative schema-fence AST subset |
| 11 | three-role independent review | Class bodies were not part of the closed static schema language and Protocol/StrEnum could normalize as empty models | confirmed; `Not applicable` / `changes_required`; verification | No current authority output was wrong and no product scenario was demonstrated, so not P2; iteration 12 closes projected model bodies and exceptions |
| 11 | three-role independent review | Unsupported `Field(...)` semantics could be silently ignored, including `default=` | confirmed; `Not applicable` / `changes_required`; verification | Current reachable outputs use supported ge/gt/le only, so no demonstrated product defect; iteration 12 defines and enforces the closed projection |
| 12 | three-role independent review | Traversed local parents were omitted from the recorded projection set | confirmed; `Not applicable` / `changes_required`; verification | Existing graph bytes already inherited fields, so no product output defect; iteration 13 records closure and proves inherited defaults |
| 12 | three-role independent review | Projected `Annotated` metadata was stripped without validation | confirmed; `Not applicable` / `changes_required`; verification | Current closure has one legitimate routing discriminator and no wrong output; iteration 13 authorizes only that exact form |
| 12 | three-role independent review | Enum JSON parsing accepted duplicate object names before canonical comparison | confirmed; `Not applicable` / `changes_required`; verification | Authority-input ambiguity required correction but no demonstrated product scenario; iteration 13 applies strict duplicate rejection |
| 13 | three-role independent review | Literal-alias fast-path unwrapped `Annotated` without invoking metadata validation | confirmed; `Not applicable` / `changes_required`; verification | Iteration 14 shares one validated unwrap helper between literal resolution and normalization |
| 13 | three-role independent review | Metadata negatives did not prove the real Literal-alias resolution path across direct, quoted, aliased, and nested wrappers | confirmed; `Not applicable` / `changes_required`; verification | Iteration 14 adds the complete path/category mutation matrix |
| 13 | three-role independent review | Strict JSON behavior lacked duplicate checked-authority root and nested-row evidence | confirmed; `Not applicable` / `changes_required`; verification | Iteration 14 tests both shapes in validator and hermetic checker paths |
| 14 | three-role independent review | Authorized discriminator metadata was checked by owner name but not by the wrapped tagged-union structure | confirmed; `Not applicable` / `changes_required`; verification | Current union was valid and no wrong output was demonstrated; iteration 15 validates the exact model/tag set |
| 15 | three-role independent review | A tagged-union member class name could be shadowed by an alias because class and alias maps were separate | confirmed; `Not applicable` / `changes_required`; verification | Iteration 16 enforces one global declaration namespace and tests all 28 names |
| 15 | three-role independent review | The documented Layer-1 command is not yet enforced by the repository PR gate | confirmed; `Not applicable` / `changes_required`; implementation/verification | Necessary enabling work is recorded in the parent implementation scope and validation ledgers; CI modification is outside this design round |
| 16 | three-role independent review | Alias-before-class coverage did not explicitly prove the reverse real-member class-before-alias order | confirmed; `Not applicable` / `changes_required`; verification | Iteration 17 inserts an alias after the real first tagged-member class and requires declarations-only rejection |
| 16 | three-role independent review | WorkPlan status and completion evidence did not conform completely to `.agent/PLANS.md` | confirmed; `Not applicable` / `changes_required`; governance | Iteration 17 uses `under-review`, adds every required common/design section, and maps L1-001 through L1-009 to named completion evidence |
| 17 | three-role independent review | Two isolated executions of the same validator were incorrectly described as independent compilation evidence | confirmed; `Not applicable` / `changes_required`; verification/governance | Iteration 18 limits that claim to deterministic hermetic reproducibility and records a separately authored no-shared-parser/normalizer compiler as pending implementation evidence |
| 17 | three-role independent review | Parent implementation WorkPlan header used prose outside the allowed status vocabulary | confirmed; `Not applicable` / `changes_required`; governance | Iteration 18 sets the exact header status to `blocked` and retains the reason in the blocker section |
| 18 | `spec_auditor` | Explicit approval; no remaining specification finding | already resolved; approval | Complete frozen Layer-1 candidate and L1-001 through L1-009 handoff reviewed |
| 18 | `correctness_reviewer` | Explicit approval; no remaining correctness or feasibility finding | already resolved; approval | Complete authority, validator/checker contract, failure behavior, and implementation boundary reviewed |
| 18 | `test_reviewer` | Explicit approval; no remaining verification finding | already resolved; approval | Hermetic evidence correctly scoped; independent compiler and PR-gate proofs explicitly pending implementation |

## Iteration 8 Semantic Inheritance Proof

- `Compiler` now rejects either a locally declared class or local alias named
  `BaseModel` before it can treat that name as the single permitted inert
  external base. Exact source mutations cover both shadowing forms.
- The local-inheritance positive test now inspects the target schema's
  `normalized_graph` directly. It requires
  `layer1_self_test_field` first, `declaring_owner=Layer1SelfTestBase`, the
  canonical scalar-string annotation and required-field policy, followed by
  the baseline fields in their original order. It also requires the target
  fingerprint and binding to change while the v2 profile remains identical.
- Removing the legitimate `BaseModel` base must preserve the target normalized
  graph, schema fingerprint, and binding byte-for-byte. A reachable two-class
  local inheritance cycle must reject.
- Baseline authority remains unchanged at
  `14ffa5cbd23e7da088d286baf3e5db9746fafe9ae5f2907a6e9115e414b81431`;
  all 56 bindings and profile digest remain unchanged. Validator SHA-256 is
  `b628522ed8368925799cda613c34536b9eb2d6235528a76587654bf0a61abeed`;
  checker SHA-256 remains
  `d420f8cfe2099176b86c71fb33fcea7057e175d5c010a87ded6c3b3102b7dd1a`.
- Exactly one next action: fresh iteration-8 review by `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer`.

## Iteration 9 Reserved-Name Binding Closure

- Inspection found no canonical `BaseModel` import in the actual design
  fences. Therefore every module-scope binding of the reserved name rejects;
  no import form is allowlisted.
- A general AST module-binding collector covers class, sync/async function,
  simple and destructuring assignment, annotated assignment, Python 3.12
  `TypeAlias`, import and from-import aliases, named expressions, module-level
  for/async-for targets, with/async-with targets, exception names, and match
  pattern captures. It traverses module control flow and evaluated class/function
  headers without incorrectly treating function/class bodies or lambda-local
  names as module bindings. Star imports reject because they can bind the
  reserved name opaquely.
- Adversarial source tests now require rejection for a class, simple alias,
  annotated assignment, real Python 3.12 `type BaseModel = str`, destructuring
  assignment, import alias, from-import alias, sync function, and async
  function. The gate runs under Python 3.12, whose `ast.TypeAlias` parser path
  is exercised directly.
- Valid baseline authority remains unchanged at
  `14ffa5cbd23e7da088d286baf3e5db9746fafe9ae5f2907a6e9115e414b81431`;
  all 56 bindings and profile digest remain unchanged. Validator SHA-256 is
  `dfb2d27bca423d191759fd3ffe199830fe0bd9c0767ff64a46adaadb9575cf26`;
  checker SHA-256 remains
  `d420f8cfe2099176b86c71fb33fcea7057e175d5c010a87ded6c3b3102b7dd1a`.
- The exact pinned hermetic gate, scoped Ruff, Python 3.12 workspace-safe
  compilation, `git diff --check`, and scoped Pyright with
  `--pythonversion 3.12` pass. Pyright without the declared version uses older
  local stdlib stubs that do not expose `ast.TypeAlias`; this is a tooling
  version selection, not an unexecuted type-alias test.
- Exactly one next action: fresh iteration-9 review by `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer`.

## Iteration 10 Final Direct-Target Closure

- `ModuleBindingCollector.visit_AugAssign()` now collects the direct target and
  visits its right-hand expression. `visit_Delete()` collects every direct
  deletion target. Therefore attempts to augment or delete the reserved
  `BaseModel` name fail before schema compilation.
- Exact Python 3.12 source mutations `BaseModel += str`,
  `BaseModel @= str`, and `del BaseModel` all reject.
- Inspection found no remaining direct module target form requiring another
  collector branch. Assignment, annotation, type alias, named expression,
  import, definition, loop, context-manager, exception, and match targets are
  already covered. `global` declares scope but creates no binding, `nonlocal`
  is invalid at module scope, and comprehension iteration targets have their
  own non-module scope; none is treated as a missing direct module binding.
- Valid baseline authority remains unchanged at
  `14ffa5cbd23e7da088d286baf3e5db9746fafe9ae5f2907a6e9115e414b81431`;
  all 56 bindings and profile digest remain unchanged. Validator SHA-256 is
  `7c48a813a4015e5e78247644c541aba7b8d74a91be6fd6c7b794a3d144a00777`;
  checker SHA-256 remains
  `d420f8cfe2099176b86c71fb33fcea7057e175d5c010a87ded6c3b3102b7dd1a`.
- Exactly one next action: fresh iteration-10 review by `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer`.

## Iteration 11 Closed Static Schema Language

- The architecture now states the closed v2 schema-fence contract. A parseable
  Python fence contributes schema authority only when it contains a
  module-level class. Such a fence permits only undecorated direct class
  declarations with at most one direct-name base and single-name declarative
  aliases composed from the exact static expression forms required by the real
  source. Non-schema example fences contribute no declarations.
- The validator enforces that closed subset before collecting declarations.
  Imports, functions, Python 3.12 type-alias statements, annotated,
  destructuring, augmented, dynamic, or subscript assignment, deletion,
  arbitrary expressions, conditionals, loops, context managers, try/except,
  match, and all other executable module statements reject. This is a static
  schema compiler and never simulates `globals()`, `vars()`, or Python
  namespace execution.
- Behavioral source tests require rejection for named expression, sync/async
  loop, sync/async context manager, exception binding, match capture, star
  import, and `globals()`/`vars()` subscript assignment and deletion. They
  reject because the statements are outside the closed schema language, not
  because dynamic targets are incorrectly treated as supported bindings.
- All actual schema fences compile unchanged. The profile, grammar, enum
  registry, 56 normalized graphs, fingerprints, and bindings are byte-identical
  to iteration 10. Required architecture documentation changes only the
  separately recorded `source_design_sha256`, so checked authority SHA-256 is
  now
  `62ae8cdd83267f47ceca360ea5a0ce425c3934b483954516f3bc13ddf59a4b68`;
  profile digest remains
  `20edd38a4ef41e4abf7e1b9a65fe2745e65705f80ec8f93c48c658739b7660a0`.
  Design SHA-256 is
  `54709052ebb5cd58711c393522ae25bf80cbecd00528a0ceaac1c67761aa0059`;
  validator SHA-256 is
  `f3a0495beced66696e377e9350bd9ca20ed4515b9a0db6974c41b4f8c026e4fb`;
  checker SHA-256 remains
  `d420f8cfe2099176b86c71fb33fcea7057e175d5c010a87ded6c3b3102b7dd1a`.
- Exactly one next action: fresh iteration-11 review by `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer`.

## Iteration 12 Class Body And Field Projection Closure

- Inventory reconstruction found 639 classes: 631 model-like declarations
  containing only simple annotated fields, seven direct `Protocol` classes
  containing ten undecorated synchronous ellipsis method stubs, and one
  `SourceKind(StrEnum)` containing four literal-string members. The CTV
  projection is now explicitly the 56 roots plus transitive declarations and
  aliases. Protocol/StrEnum exceptions are exact, normative outside CTV, and
  reject if they become reachable instead of becoming empty schemas.
- Model-like class bodies now reject methods, async methods, nested classes,
  assignments, decorators/validators, expressions, control flow, dynamic
  annotations, `globals()`, `vars()`, `setattr()`, and unsupported defaults.
  Protocol stub signatures and StrEnum literal bodies are structurally
  validated against their exact current inventories.
- All 154 real `Field(...)` calls use only `ge`, `gt`, `le`, and three
  `default=None` occurrences. The projection now permits no positional
  arguments and only unique `default`, `ge`, `gt`, and `le` keywords.
  Constraints must be non-boolean integer literals. Defaults must be canonical
  null/string/boolean/integer literals, are normalized explicitly, and never
  authorize field omission. Unknown keywords, duplicate keywords, `**kwargs`,
  factory, alias, discriminator, unsupported constraint, nonliteral value, and
  arbitrary default calls reject.
- The three current `default=None` fields are exactly
  `ActionTransitionRoleRequirement.minimum_cardinality_override`,
  `ActionTransitionRoleRequirement.maximum_cardinality_override`, and
  `OracleEffectRoleCardinality.maximum_cardinality`; projection reconstruction
  proves all three owners are outside the 56-root closure. A synthetic
  reachable `Field(default=None)` is normalized as literal null and changes its
  fingerprint.
- Negative tests cover dynamic class annotation/globals/setattr, method,
  nested class, class assignment, decorated validator, arbitrary default call,
  positional Field default, factory, alias, discriminator, kwargs expansion,
  unsupported constraint, and Protocol/StrEnum reachability. Positive tests
  prove the exact exception inventory and its disjointness from CTV.
- Architecture documentation changed only `source_design_sha256`; comparison
  with iteration 11 proves profile, grammar, enum registry, inventory, all 56
  normalized graphs, fingerprints, and bindings byte-identical. Frozen hashes:
  design
  `de36e5cb487fbad5a6f93fb9c915f3e75ab3084e11177f2170d93c38c595de87`,
  authority
  `2d2016998b219ecd1b3250d89c10a11b4d049e564d8200570948f2588c1f5661`,
  validator
  `d1aeaea8b14709ac594356870236884ad81a750395d07d3b69e31db8b52eb19d`,
  checker
  `d420f8cfe2099176b86c71fb33fcea7057e175d5c010a87ded6c3b3102b7dd1a`.
- Exactly one next action: fresh iteration-12 review by `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer`.

## Iteration 13 Projection Metadata And Strict JSON

- `class_fields()` now records every traversed local parent in
  `projected_classes` before recursion. The local-inheritance proof asserts
  parent membership directly. A second inherited-parent fixture carries
  `Field(default=None)` and proves closure membership, declaring owner,
  normalized literal-null default, changed fingerprint, and changed binding.
- Reachability inventory contains exactly one projected `Annotated` metadata
  form:
  `TraceabilityGenerationMember = Annotated[..., Field(discriminator="artifact_kind")]`.
  Architecture classifies it as routing/tag selection over already declared
  alternatives, outside the CTV value domain. The validator permits only this
  exact single discriminator-only metadata call and validates it through
  direct, quoted-forward-reference, and alias-expanded annotations before
  stripping the wrapper.
- Direct, quoted, and alias-expanded `default_factory` mutations reject.
  Additional tests reject default, alias, constraint, positional, kwargs,
  arbitrary call/name, and multiple metadata items. A positive test inspects
  and validates the exact legitimate discriminator metadata.
- V2 enum JSON and checked authority JSON use duplicate-name rejection in the
  validator; the hermetic checker applies the same strict loader to the v1
  baseline and checked authority. A complete duplicated v2 enum key/value
  mutation rejects before canonical comparison.
- Architecture documentation changes only `source_design_sha256`; comparison
  with iteration 12 proves profile, grammar, enum registry, inventory, all 56
  normalized graphs, fingerprints, and bindings byte-identical. Frozen hashes:
  design
  `49002f2aa29c101462d0e1fafb134c9b02f786366f27c1b9ba5f27a3145be359`,
  authority
  `195e126231af20f2bb50fb83233c39aff18c2a585fdd4dc3e4520c3dcfa8e8d4`,
  validator
  `6a2018b56eb60c94f2bb5c8cfd1458594989e1e104e5e0875c6ea09326485e91`,
  checker
  `79667e0faab90bcef63a193c59db739d299304cda41e8cba9b6ebdda3c809764`.
- Exactly one next action: fresh iteration-13 review by `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer`.

## Iteration 14 Literal Alias And Checked-Authority Closure

- `annotated_parts()`, `validate_annotated_metadata()`, and
  `unwrap_annotated()` now form one shared path. Both `resolved_literals()` and
  general `normalize()` invoke it before removing an `Annotated` wrapper, so
  Literal aliases cannot bypass metadata validation.
- The only allowed metadata owner is the exact
  `TraceabilityGenerationMember` union alias with its single exact
  `Field(discriminator="artifact_kind")`. The same discriminator on a literal
  alias explicitly rejects.
- Literal-path tests cover direct and quoted annotations, a reachable alias,
  and nested aliases. They reject default, factory, alias, constraint,
  positional, kwargs, arbitrary call/name, multiple metadata, and invalid
  discriminator forms. The legitimate routing discriminator remains a positive
  proof through the shared helper.
- Strict-loader tests construct a duplicate complete top-level checked-authority
  key and a duplicate `binding_digest` inside the first schema row. Both reject
  before candidate comparison in the validator and through the checker's
  authority-shape path.
- Architecture documentation changes only `source_design_sha256`; comparison
  with iteration 13 proves profile, grammar, enum registry, inventory, all 56
  normalized graphs, fingerprints, and bindings byte-identical. Frozen hashes:
  design
  `370dcf833da4cb16748a3532b577990e04e005fa0325941dec32e6adcec179ae`,
  authority
  `d09779f35454062625eeedb4db74ad88d8e58ef9af551b8b82f0def9be6ab3be`,
  validator
  `7306452ea8fd4e22c9c3d641d2d7eaed51a9932acd1b6ea97c77a3e0652934cf`,
  checker
  `bc31ed0d15cf7aed3d7a7fdbe84d5df0f1e63df95aacde7a7a40dcabf8cbeba7`.
- Exactly one next action: fresh iteration-14 review by `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer`.

## Iteration 15 Tagged Union Exception Closure

- The sole metadata exception now validates both its exact owner and its
  wrapped type. `TraceabilityGenerationMember` must contain the exact ordered
  28-model union frozen by the design declaration.
- Every alternative must be a direct declared model, expose exactly one
  inherited-or-local `artifact_kind` field, and annotate that field with
  exactly one string Literal. Discriminator values must be unique, and the
  complete ordered `(model, discriminator)` tuple must equal the frozen design
  inventory. Alias expansion or quoted forms cannot substitute another wrapped
  type.
- The positive test validates all 28 current alternatives and values.
  Mutations replace the wrapped type with a Literal, scalar, nonunion model,
  unknown member, and nonmodel; introduce a model lacking `artifact_kind`; and
  duplicate a real discriminator. Every mutation rejects through the tagged
  union validator.
- Architecture documentation changes only `source_design_sha256`; comparison
  with iteration 14 proves profile, grammar, enum registry, inventory, all 56
  normalized graphs, fingerprints, and bindings byte-identical. Frozen hashes:
  design
  `e00770e321302f9894d92a0dc299878f3bf05350069acbf22065eeb7e6d83e03`,
  authority
  `767fd2a2ad66aec9001f5fa6d2e1255b53e9e2527910c226b55c8d3f9f6154d9`,
  validator
  `66a8b1a9ab9242f39182861674a119413f6da965b0781312d09d308966539ba5`,
  checker
  `bc31ed0d15cf7aed3d7a7fdbe84d5df0f1e63df95aacde7a7a40dcabf8cbeba7`.
- Exactly one next action: fresh iteration-15 review by `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer`.

## Iteration 16 Declaration Identity And Implementation Handoff

- Classes and aliases now share one global identifier namespace across every
  schema fence. Any duplicate class/class, alias/alias, or class/alias name
  rejects deterministically, including byte-identical duplicate declarations;
  no `setdefault` or last-write-wins behavior remains.
- A declarations-only mutation loop shadows each of the exact 28
  `TraceabilityGenerationMember` model names with an alias and requires
  rejection before enum parsing or comparison. Separate identical
  class/class and alias/alias mutations prove both same-kind collision paths.
- Architecture documentation changes only `source_design_sha256`; comparison
  with iteration 15 proves profile, grammar, enum registry, inventory, all 56
  normalized graphs, fingerprints, and bindings byte-identical. Frozen hashes:
  design
  `67bf2620a0379761853861e416efba0816045ef4bf88e4808e701a9ac3bc993e`,
  authority
  `89a98fc1e545f38c234ce42dbd164c85e3ddc6358856cca70e59dad7b1addc7b`,
  validator
  `599176838ddd1ffdc691fd659d30b50236a954cdcb5498fe5254947f31749b6f`,
  checker
  `bc31ed0d15cf7aed3d7a7fdbe84d5df0f1e63df95aacde7a7a40dcabf8cbeba7`.
- The missing PR invocation is confirmed necessary enabling work, not a design
  semantic defect. No CI or production file is changed in this design round.
  Layer-1 design approval may complete only with the handoff explicitly
  pending: the next authorized implementation milestone must wire the exact
  content-addressed command in `docs/development/static_tooling.md` into PR CI
  and prove clean-checkout failure on any nonzero gate result. The parent
  implementation WorkPlan scope and validation ledgers record this acceptance
  condition; it is not claimed executed.
- Exactly one next action: fresh iteration-16 review by `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer`.

## Iteration 17 Reverse Collision And Process Closure

- The declarations-only adversarial suite now covers both cross-kind orders
  with real tagged-union identifiers. Iteration 16 parameterized alias-before-
  class shadowing over all 28 members; iteration 17 inserts an alias after the
  real `TraceabilityRawDesignGenerationMember` class and before the next real
  class. The exact class-then-alias duplicate must reject before enum parsing,
  normalization, or candidate comparison.
- The authority bytes, all 56 normalized graphs, fingerprints and bindings,
  the 240-row enum registry, and the profile digest remain unchanged. Only the
  validator source identity changes. Frozen hashes are design
  `67bf2620a0379761853861e416efba0816045ef4bf88e4808e701a9ac3bc993e`,
  registry
  `38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`,
  authority
  `89a98fc1e545f38c234ce42dbd164c85e3ddc6358856cca70e59dad7b1addc7b`,
  validator
  `f0f74bc704e1eb1aab97cff3ea1bd7e6055dd60bab1c3fed0d63d24f4f026ea8`,
  and checker
  `bc31ed0d15cf7aed3d7a7fdbe84d5df0f1e63df95aacde7a7a40dcabf8cbeba7`.
- WorkPlan status is `under-review`. Its named Completion Contract maps
  L1-001 through L1-009 to frozen identities, hermetic and mutation evidence,
  three-role reconciliation, scope/exclusions, and absence of unresolved
  design ambiguity. L1-009 remains explicitly pending implementation:
  repository CI wiring is neither changed nor claimed as achieved evidence.
- Exactly one next action: fresh iteration-17 review by `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer`.

## Iteration 18 Independent Compilation Evidence Closure

- Two isolated runs of `validate_ctv_binding_authority_v2.py` are now described
  only as deterministic hermetic reproducibility evidence. They do not satisfy
  L1-008's implementation proof because both runs share one parser and
  normalizer.
- L1-008 design completeness remains required and evidenced by the frozen,
  exhaustive grammar bytes, enum registry, schema inventory, normalized graph
  rules, fingerprint formulas/preimages, and binding formulas/preimages.
  Actual implementation proof remains pending: a separately authored
  production/reference compiler must share no parser or normalizer
  implementation with the design validator, derive the byte-identical complete
  authority from the frozen design and registry, and produce equivalent
  fail-closed outcomes for key invalid syntax, declaration, enum, graph,
  profile, fingerprint, and binding cases.
- The parent implementation WorkPlan now records that compiler and the existing
  PR gate as separate pending SIA-R03 necessary-enabling scope and validation
  items. Its header uses exact `Status: blocked`; blocker detail remains in its
  dedicated prose. No architecture, authority, validator, checker, CI, or
  production byte changed, so iteration-17 hashes and static pins remain
  current.
- Exactly one next action: fresh iteration-18 review by `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer`.

## Iteration 19 Administrative Approval And Handoff

- Fresh iteration-18 `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer` passes each explicitly approved the complete frozen Layer-1
  candidate. Coordinator reconciliation found no confirmed
  `blocks_approval` or `changes_required` design finding and no unresolved
  design ambiguity.
- The Design Completion Contract is satisfied: the problem, scope, non-goals,
  L1-001 through L1-009, existing-system paths, decisions, alternatives,
  feasibility, failure/operational behavior, verification strategy, limits,
  and implementation handoffs are explicit and self-contained.
- Final frozen baseline: repository commit
  `945d6ea03649ca13c800e84bcb9972797e0f0a31` on
  `live-benchmark-repair`; design
  `67bf2620a0379761853861e416efba0816045ef4bf88e4808e701a9ac3bc993e`;
  registry
  `38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`;
  authority
  `89a98fc1e545f38c234ce42dbd164c85e3ddc6358856cca70e59dad7b1addc7b`;
  validator
  `f0f74bc704e1eb1aab97cff3ea1bd7e6055dd60bab1c3fed0d63d24f4f026ea8`;
  checker
  `bc31ed0d15cf7aed3d7a7fdbe84d5df0f1e63df95aacde7a7a40dcabf8cbeba7`;
  profile
  `20edd38a4ef41e4abf7e1b9a65fe2745e65705f80ec8f93c48c658739b7660a0`.
- Status is `complete`. Exactly one next action is the linked implementation
  WorkPlan's Layer-1 SIA-R03/L1-008/L1-009 milestone.

## Outcome And Retrospective

Layer-1 design is complete and approved against the frozen identities above.
All nine design requirements have explicit evidence or a completed
implementation handoff, and no unresolved validated design finding remains.
The separately authored compiler proof and PR-gate integration remain
deliberately unexecuted implementation work; this design close does not claim
production or CI behavior.
