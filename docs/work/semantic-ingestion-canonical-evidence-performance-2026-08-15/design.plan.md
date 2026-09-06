# Canonical Evidence Performance Design WorkPlan

- Work ID: semantic-ingestion-canonical-evidence-performance-2026-08-15
- Work type: design
- Status: under-review
- Coordinator and sole writer: Codex
- Last updated: 2026-08-16 (DREV-001/DREV-002 exactness remediation)
- Canonical design: `docs/design/semantic_ingestion_canonical_evidence_performance.md`

## Objective and fixed scope

Design invocation-local canonical evidence reuse to eliminate repeated immutable
descendant validation while preserving exact bytes, digests, errors, authority,
persistence, replay, retry, and terminal behavior. Scope excludes production or
test edits, test execution, public/persisted changes, global caching, and
post-result tuning.

## Requirements and evidence maturity

- `R1` exact immutable, nonce-local reuse; legacy validation otherwise: specified.
- `R2` public bytes/digests/errors and dynamic authority/persistence unchanged: specified.
- `R3` real private bridge and nested `ValidationInfo.context` delivery are trace-falsifiable: derivable.
- `R4` actual claimed/found/reconcile/retry lifecycle and durable reads are complete: derivable.
- `R5` one full digest per eligible identity, global budget, capacity/RSS limits: derivable; baseline capture pending.
- `R6` closed receipt/event/fixture/run schemas reject false evidence: derivable.

## Authority and identity ledger

- Public API and persisted identities: unchanged behavioral identities.
- Arena, nonce, bridge observations, receipts, and run records: ephemeral design-evidence identities; never persisted product state.
- Fixture source paths and their SHA-256 identities: evidence inputs in `standard-fixture-manifest-v1.json`.
- Baseline receipt: required future immutable evidence at the location named by the fixture manifest; no baseline result is claimed.
- Candidate lock: immutable, non-self-referential evidence ledger over settled normative artifacts; it excludes the WorkPlan and itself.

## Feasibility and alternatives

A bounded Pydantic `ValidationInfo.context` spike established that context
reaches nested validators, equal descendants can reuse a validated result, and
a changed body with a claimed old digest still receives full validation and
rejects. Rejected alternatives are global/LRU caching, outer-wrapper-only
caching, and deleting validation. A rope/raw-fragment encoder is out of scope
unless this bounded arena fails its fixed gate and a new design is approved.

## Review history and coordinator classification

- Initial full review: the former proposal conflated body/envelope/persisted
  identity, missed nested validation, and lacked trust/lifetime/performance
  proof. Confirmed as `Not applicable` / `changes_required` design and
  verification findings; remediated by the three-role arena and fixed gates.
- First delta review: decoder return type, actual lifecycle route, durable graph
  effect boundary, and matrix detail were confirmed `Not applicable` /
  `changes_required`; remediated in the binding and verification contracts.
- DREV-005: confirmed `Not applicable` / `changes_required` verification and
  integration conformance finding. This pass adds closed event discriminants,
  bridge/context sequences, linkage, and mutation-to-receipt mappings.
- DREV-006: confirmed `Not applicable` / `changes_required` lifecycle,
  transaction, and integration conformance finding. This pass corrects the
  owner chains; inventories all cited initial/retry/generation/recovery reads;
  separates acknowledgement-loss reload; splits found terminal/retry/graph-
  absent paths; and makes successor bindings reachable.
- DREV-007: confirmed `Not applicable` / `changes_required` verification and
  operability conformance finding. This pass adds JSON Schemas, closed rows,
  pinned fixture identities, deterministic capacity vectors, run records, and
  the honest baseline-capture gate.
- Strict closure pass: DREV-005 now supplies a named receipt-level linkage
  algorithm and positive/negative chain vectors. DREV-006 separates terminal
  persist acknowledgement loss from group-checkpoint acknowledgement loss,
  binds reconcile-without-handoff and writer authority, and closes successor
  finalization hops. DREV-007 closes exact fixture shape and lock-bound run
  identities without inventing a baseline.
- Reviewer demands for implementation/test execution during design review were
  classified unsupported: this design establishes specified/derivable evidence,
  not production implementation evidence.

## Frozen artifact set

- `docs/design/semantic_ingestion_canonical_evidence_performance.md`
- `docs/design/semantic_ingestion_canonical_evidence/production-entrypoint-bindings-v1.json`
- `docs/design/semantic_ingestion_canonical_evidence/verification-contract-v1.json`
- `docs/design/semantic_ingestion_canonical_evidence/event-schema-v1.json`
- `docs/design/semantic_ingestion_canonical_evidence/receipt-schema-v1.json`
- `docs/design/semantic_ingestion_canonical_evidence/performance-run-schema-v1.json`
- `docs/design/semantic_ingestion_canonical_evidence/standard-fixture-manifest-v1.json`
- `docs/design/semantic_ingestion_canonical_evidence/standard-fixture-schema-v1.json`
- `docs/design/semantic_ingestion_canonical_evidence/candidate-lock-v1.json`

Hashes are recorded after syntax/reference validation. This pass does not claim
approval or implementation readiness: baseline capture remains a
pre-implementation gate.

## Superseded next action

Targeted independent delta review of this frozen bounded contract-conformance
remediation. The reviewer must confirm DREV-005/006/007 closure and that the
baseline-capture gate is explicit rather than fabricated evidence.

## Independent review closeout (2026-08-16)

Independent targeted delta review for DREV-005, DREV-006, and DREV-007 has been
completed using the frozen candidate lock
`4b2af56947b56b006c5aa45b715fe95834c44b059665787f74c87fe49d6d0245`.

- DREV-005: confirmed closed. No remaining contract-conformance gap.
- DREV-006: confirmed closed. No remaining lifecycle/owner-chain gap.
- DREV-007: confirmed closed. No remaining fixture/lock-run closure gap.

All three lane-roles were run as part of the fresh full-design review:
`spec_auditor`, `correctness_reviewer`, and `test_reviewer`.

Outcome: no new P1/P2 findings. Findings remain `Not applicable` / `changes_required`
for contract-conformance evidence closure and are closed as recorded above. Final
approval decision: `Approved with follow-ups`.

Reconciliation evidence:

- candidate-lock integrity check passed for all locked artifact paths/hashes;
- candidate-lock references and manifest/fixture contract IDs match frozen values
  in the plan;
- lock-gated baseline capture is still pending before any production edits (pre-implementation only).


## Strict bounded contract-closure record

The confirmed DREV-005, DREV-006, and DREV-007 contract-conformance findings
were corrected without production or test edits. Their classifications remain
Not applicable / changes_required because they concern proof and binding
completeness, not demonstrated product regressions. Evidence maturity is
derivable for the closed schemas, receipt-linkage algorithm, binding ledger,
operation map, exact fixture/candidate-lock contract, and artifact-validator
vectors. Baseline performance capture remains pending; no performance result is
claimed.

Frozen companion identities for the targeted delta review:

- Design: c066bf2f9edd58260b68fa4dddf5d4ffc3290a9201a78c444c6355cc3f8a09ae
- Verification contract: c19605422f6ada0ac94df0425e4abf21e1e8f4ef5fd4efcd4b4998fc93256319
- Binding map: e8d3b40cb3858630ebdae71655e8a59e976c2bfd8228d5d22a7c5f18bd64cdcd
- Event schema: 8785b893874c50e312942a2a16a1d725ed97e4dbccfbe5849f3de605dd6a4179
- Receipt schema: 6c4816b5660829309b683af32e196d8c39f6f19aee619bb3d9b96ac8b92356e8
- Performance run schema: 0f5e71144b98b8cb929f91a2fe6eca2ee9af6e0425014d40aab31dd40a4bdad9
- Fixture manifest: a7619358561949fbcf5874c1b59c8a491aeec6c0a465c0ce09d6675ca35ab960
- Fixture schema: b888851bb438361ccaf80697978832b777ff150da353dbb625f6dcdc4826e613
- Candidate lock: 4b2af56947b56b006c5aa45b715fe95834c44b059665787f74c87fe49d6d0245

Status: superseded by the pass-3 reconciliation below.

## Remediation pass 3 (2026-08-16)

The bounded design/tooling slice closes the determinate DREV-002 through
DREV-005 contract-conformance actions without production or production-test
edits. The replacement lock supersedes
`feca7512b973c11f97e743424b1f1823cef8ac009ccc2088ddfcf0ce5698bf90` and
pins the shared resolver, all executable authorities, both schemas, the fixture
manifest, and the production-source manifest. The validator now verifies the
full lock authority set before processing records, binds source revisions to
the verified source-manifest identity, requires candidate per-identity count
one, and exercises the declared adversarial and threshold cases through final
acceptance.

DREV-004 is closed only as a specified-not-implemented design binding. The
exact existing `ProviderIngestionCoordinator._admit_with_writer_retry` branch
is writer-admission retry, not an arena retry; no hidden arena retry exists.
The future owner and explicit propagation parameters are recorded in the
binding map. This pass-3 DREV-001 status is superseded by the proof-contract
remediation below.
It requires the narrow external authorization recorded in the pass-3 report;
scenario/private bridges are forbidden because they inject scenario-test trust
and private graph authority instead of proving the public production path.

Evidence: `docs/reviews/semantic-ingestion-canonical-evidence-performance/delta-review-remediation-pass-3-2026-08-16.md`.
No approval or baseline claim is made; the invalid baseline remains invalid.

## DREV-001 proof-contract remediation (2026-08-16)

DREV-001 is now `Not applicable / changes_required / verification
contract_conformance_action`; the user decision is resolved. The bounded slice
adds positive AST grammar, typed production receipt/trace and latency linkage,
external pre-import SHA-256 trust, explicit pending-source fail closure, and
separate design-vector versus implementation gates. It makes no production,
baseline, or approval claim; DREV-002 through DREV-006 remain closed.
Frozen replacement lock: `6dcd4972149106eb0c6443c7665d3a5ac32ad4b02c8f9be43b3fb81818b7647e`,
superseding `9642ec00f247c77b8be0ce84efe69b2fdff21a99a26a1e1ca6d887082a0e7c2f`.

## Superseded next action (historical)

Independent targeted DREV-001/DREV-002 rereview of the superseding frozen proof contract.

## DREV-001 authorized remediation (2026-08-16)

The user authorized the narrow verified production-owned authority-composition
boundary and explicitly rejected raw graph-builder exposure and scenario-test
reuse. The design now names the future typed `VerifiedProductionHostAuthority`
and `build_verified_production_host_authority` owner, four-root threading,
production-issued receipt, diagnostic production trace, and static thin-fixture
contract. DREV-001 is correction-determinate and now requires independent
targeted proof-contract rereview. DREV-002 through DREV-006 remain closed. No production code,
production tests, baseline, or arena optimization was changed or authorized.

## DREV-001/DREV-002 Result-Lock Remediation (2026-08-16)

DREV-001 and DREV-002 remain `Not applicable / changes_required` until the
targeted rereview evaluates the newly frozen lock. The receipt contract now
uses a privately constructed typed object and non-serializable opaque operation
token; child identity/type validation is pre-serialization only, and serialized
bytes contain neither a token nor an issuance claim. The launcher freezes an
execution lock before capture and O_EXCL-creates a result lock after capture;
the external acceptance command requires each `--expected-result-lock-sha256`
before Python imports records. This plan's expected result-lock hash is
`not_available: production capture remains blocked`; any future capture ledger
must record the launcher-printed baseline and candidate hashes verbatim.

The reviewer request for a current runtime eight-cell proof is recorded as
blocked implementation evidence: it is unsupported as a prerequisite for
closing design exactness because no non-test production caller exists, but it
remains a mandatory post-implementation gate. It is not a separate design
finding and does not change the DREV-003 through DREV-006 dispositions.

## DREV-001/DREV-002 exactness remediation (2026-08-16)

This bounded design/tooling update is determinate and complete pending targeted
rereview. DREV-001 remains `Not applicable / changes_required / verification
contract_conformance_action`: the static fixture parses with `type_comments=True`
and rejects module type ignores plus function and assignment type comments;
self-mutations cover function type comments, assignment type comments, and
`# type: ignore` as well as decorator, annotation, type parameter when
parser-supported, default/keyword-default, async, and generator forms.
DREV-002 remains `Not applicable / changes_required / verification regression`:
`source_frames` is the canonical capture-ready inventory, requiring exact
cardinality, unique symbols and sources, and binding-map/source-manifest
symbol/path/SHA-256 equality in the pre-import gate and shared resolver. A
lock-pinned isolated launcher self-test copies the lock, contracts, launcher,
and minimal capture-ready source fixtures, repins only that temporary candidate,
and proves each source-frame mutation exits 64 without either lock or fake
interpreter invocation; outer-lock tamper remains a separate precondition test.

No production code/tests, baseline, runtime capture, persistence proof, or
approval changed. DREV-003 through DREV-006 remain closed.

Frozen replacement lock:
`43fd356d48656dbe7f949ac1f6c9546021012fc745a560c44741adb58e959dd9`,
superseding `4112399022e0c39401e9bb818a4c0e9e79631473adbf7703f63ef122398dd06c`.

Local evidence at this freeze: `.venv/bin/python -m py_compile` for the two
fixture modules, `.venv/bin/ruff check` for those modules, `/bin/sh -n` for the
launcher, and `jq empty` for the changed lock/contracts/grammar/source manifest
all exited 0. `canonical_evidence_artifact_validator.py --self-test` exited 0,
including the isolated capture-ready launcher mutation harness. A direct
current-lock capture probe exited 64 at the pending source-frame boundary and
created neither execution nor result lock. This is local tooling evidence only;
it is not baseline, runtime, persistence, production-caller, CI, or approval
evidence.

## DREV-001 ordering remediation (2026-08-16)

This final bounded tooling correction moves the lock-pinned static AST grammar
validator to the capture gate after external source-frame/source-byte
verification and before execution/result lock creation or runner-target
invocation. The isolated repinned harness now distinguishes the verifier
interpreter from the runner target: function type comment, assignment type
comment, and type-ignore mutations invoke the verifier, exit 64, leave no
runner-target sentinel, and create neither lock. Existing source-frame vectors
continue to prove rejection before either interpreter invocation. No production
code/tests, baseline capture, persistence proof, production caller, or approval
claim changed. The replacement lock
`ebc2e9b4927e93877b5ee3b8b6742b6f6485128bd860c4569f51b6ecaab13f30`
is frozen last and supersedes
`43fd356d48656dbe7f949ac1f6c9546021012fc745a560c44741adb58e959dd9`.

Local tooling evidence: fixture compilation, focused Ruff, launcher shell
syntax, changed JSON syntax, direct isolated grammar validation, and the
artifact-validator `--self-test` all passed. The self-test covers all retained
source-frame vectors plus the three repinned type-comment/type-ignore capture
vectors. A direct current-lock capture probe exited 64 without either lock.
This is local tooling evidence only and does not alter the blocked production
caller, baseline, persistence, CI, or approval state.

## Current next action

The linked observability remediation has frozen whole-design replacement lock
`d1760d12f207bdc363361b628ae7d00a33ba3644fce54f4935739bfae075aeb0`,
superseding `ebc2e9b4927e93877b5ee3b8b6742b6f6485128bd860c4569f51b6ecaab13f30`.
All A-G findings are `Not applicable / changes_required`; detailed evidence is
owned by `docs/work/semantic-ingestion-canonical-evidence-performance-observability-2026-08-16/design.plan.md`.

Targeted delta review of the new whole-design findings against that replacement lock.
