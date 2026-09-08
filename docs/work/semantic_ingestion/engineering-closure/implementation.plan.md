# Semantic Ingestion Engineering Closure Implementation Index

- Work ID: semantic-ingestion-engineering-closure
- Work type: implementation
- Status: active observation design under approved separate projection semantics; acceptance-authority prerequisite remains blocked
- Coordinator: Codex main thread
- Created: 2026-09-06
- Last updated: 2026-09-06
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion_completion_readiness/closure-plan.md`
- Canonical inputs: frozen SIA architecture and closure plan
- Expected outputs: six bounded implementation packages and fail-closed activation
- Current resume packet: `docs/work/semantic_ingestion/engineering-closure/resume.md`
- Active milestone packet: `docs/work/semantic_ingestion/engineering-closure/milestones/05-authenticated-observer-comparator.plan.md`

## Design Baseline, Scope And Constraints

Start HEAD: 191826cd3afb38bf605a337a71d576063b3bae5e; merge base with
origin/main: b4f6c24b091a28bd3d1f65102c742478fc7276b3. Architecture SHA-256:
b469653e3ef92e9cc1bf45e797a2c7dff8eac4d9ee792ad94ada3a54bfbe05da.
Read governing spec, storage details, event model and implementation rules under
AGENTS.md precedence. Include remaining engineering and preserve completed
milestones; exclude actual production signature issuance, choosing substantive
quality policy values, paid evaluation without its required approval, and
unrelated redesign. Synthetic/test-key evidence does not certify a capability.
All root invariants, strict schema and trust boundaries remain applicable.

## Objective

Complete user-authorized engineering work for all SIA-R01..R23. Retain complete
behavior and defer only real signatures, trusted deployment material, and
signed release issuance.

## Completion Contract

Every package proves its bounded requirements through canonical production
paths. A runtime or persistence claim requires a current
`production_entrypoint_bindings` entry proving a non-test caller reaches the
canonical owner with required authority and observed outcome.

## Packages

| Order | Packet | Requirements | Status |
| --- | --- | --- | --- |
| 1 | evidence/M0 reconciliation | R01-R04, R07, R09-R13, R18, R20-R23 | partial; final candidate proof deferred |
| 2 | release crypto/trust | R03, R08, R13, R16, R19 | partial; signing locally verified, host/review unfinished |
| 3 | independent statistics | R05, R06, R14 | numeric component approved; authority prerequisite blocked at review limit; canonical promotion/runtime owner pending |
| 4 | monitor/registry | R08, R15, R16, R19 | not implemented; queued after prerequisite contracts |
| 5 | observer/comparator | R03, R13, R17 | bounded source-finalization approved; group carrier implementation active; authenticated query/comparison pending |
| 6 | host closure | R01-R23 | blocked on incomplete packages |

## Initial Ledgers

`production_entrypoint_bindings.json` is an initial map, not closure proof. No
policy value, decimal registry, threshold, backend, or trust root is defaulted.
Prior authorized dirty packaging/audit artifacts are preserved.

## Delegation And Cost Ledger

Current correction: the numeric authority writer's claimed reconstruction was
not integrated: the new release reducer had zero verifier callers while seven
old-model tests still passed. Coordinator rejects that completion claim and
transfers the four linked design/proof files to `authority_reconstruction_owner`
(Terra worker) for the same bounded reconstruction. No new review round or
canonical promotion is implied. Source-terminal spec/correctness reviews are
active on the separately frozen debug candidate; test review awaits a free
collaboration slot. Monitor matrix consultation is complete. The Spark monitor
preflight was not usable; coordinator records the rejected claims and verified
facts in `monitor-binding-preflight.md` instead of treating it as a binding.

- `numeric_promotion_map`: code-mapper/Spark, read-only canonical authority
  regeneration preflight; active, owns only numeric-promotion-preflight.md.
- `numeric_runtime_owner`: worker/Terra, sole writer of isolated acceptance
  library/tests; component implemented and coordinator reproduced 77 tests.
  Independent baseline verification exposed undeclared acceptance authority
  contracts. Writer now owns only the linked acceptance-authority design draft;
  runtime context/CLI and R14 remain incomplete.
- `observer_persistence_owner`: worker/Terra, completed pure observation builder
  and three focused tests. Coordinator owns corrections and runtime integration;
  helper approval does not prove a transaction caller. Delegate now maps source
  finalization integration read-only in its separate evidence artifact.

- `closure_preflight`: code-mapper/Spark, read-only; completed bounded maps.
  Coordinator rejected unsupported claims that release verifier types were
  absent and that terminal recovery exposed observation deltas. Corrected
  release chain below; validated observer facts in observer-readiness.md.
- `release_readiness`: explorer/Spark, read-only signing inventory; complete.
- `correctness_review`: correctness reviewer, read-only statistical consultation;
  complete. Exact inputs preserved; computed-real representation needs correction.
- `signer_matrix`: test reviewer, pre-coding consultation; complete. Its initial
  full-review freeze objection does not apply to a pre-coding matrix. Coordinator
  also corrected its raw-key hash suggestion to the existing domain-bound test
  profile. No full approval claimed.
- `coordination_update`: worker/Terra; administration complete; sole writer now
  for distinct coordination-identity testing operation.
- `numeric_writer`: worker/Terra, sole writer of numeric design/feasibility files;
  draft refinement active, no canonical architecture or product edits.
- `crypto_adapter`: worker/Terra, sole writer of adapter/tests/dependency and
  release packet; implementation active. Its fixture ownership now includes
  the acceptance generation-package helper so real signatures are assembled
  before member-DAG digests. No overlap with other writers.
- `offline_signer`: worker/Terra, sole writer of separate PEM signer module,
  tests and offline-signing evidence. CLI sign/verify focused tests pass;
  canonical verifier reuse and candidate freeze are being finalized.
- `numeric_correctness`, `numeric_spec`, `signer_matrix`: read-only numeric
  delta reviews reconciled; second bounded correction addresses complete typed
  proof bindings, manifest-owned resource budgets and executable boundary proof.
- Coordination identity correction is independently approved for its bounded
  testing slice. The coordinator reproduced fidelity and public-path mutation
  self-tests. Historical v1 bytes remain unchanged; current final identity
  capture still waits for the whole candidate freeze.
- Coordinator took sole ownership of the single-signer CLI, integration test
  and shared canonical signing helpers after the worker handoff. Fixed actual
  module invocation, immutable re-preparation, duplicate config rejection,
  closed template shape/purpose, and verification-before-output behavior.
  Four-artifact API/CLI integration now passes 14 tests; shared release
  provenance plus integration passes 40 tests, Ruff and targeted typing pass.
- `lifecycle_signing`: worker/Terra owns only the separate lifecycle CLI,
  integration tests and evidence; coordinator owns its shared canonical helper.
- `numeric_boundary`: worker/Terra owns the new linked complete numeric boundary
  reconstruction. Previous two-round proposal/proof is paused and archived;
  three reviewers confirmed remaining type, allocation and validator gaps.
- Coordinator rejected the reconstruction after no-write public-entrypoint
  probes accepted a changed binomial null under the same manifest and showed
  serialization before its byte cap. Direct comparison also found an extra
  newline in purported canonical locator bytes. Independent read-only
  consultation confirmed the contract gaps; the linked design records its
  exhausted reconstruction budget and exact obligations. No production numeric
  contract was changed and R14 remains incomplete.
- `observer_storage_map`: code-mapper/Spark read-only exact current storage/auth
  trace; prior broad map did not establish a usable complete cohort reader.

## Release Preflight

Read-only mapping identifies `SignatureVerifier` at
`memorii/memorii/tools/semantic_ingestion_traceability_release.py:105` and
`VerifierHeldTrustMaterial` at line 150; `_signature` at line 456 calls the
configured verifier with profile, key, payload, and raw signature. The actual
registered production executor calls `resolver.resolve_registered_execution()`
at `memorii/memorii/tools/semantic_ingestion_execution_evidence.py:210` and
`validate_release_candidate` with `authority.material` at line 342.
The traceability-release alias resolves `_validate_release_candidate` at `:1966`
through `:2640`. At the baseline `verify_release_gate` had zero production
callers. The new configured resolver now supplies the Ed25519 verifier;
successful registered-executor evidence now verifies publication and tamper
rejection under explicit test-backend opt-in. Detached
signing has a separate executable CLI. Neither claim closes release assembly.

## Readiness Limit

Section 5.6 decimal registration is absent from the initial map. Classify it
before serialized statistical output; isolated nonserialized numeric work may
proceed after its owner map. This does not block the whole operation.
The numeric component design is approved at
`../statistical-acceptance/design.plan.md`. Independent baseline trust and
current-status authority are a separate prerequisite now being specified in
`../acceptance-authority/design.plan.md`; its initial drafts are not approved.
The older `acceptance-numeric-contract` plan remains rejected history.

## Verification Limitation

The historical v1 candidate identity is frozen evidence and was restored from
`HEAD`; it cannot certify subsequent source edits. The linked testing operation
now supplies a v2 capture/verifier with exact literal self-exclusions and
public-path tamper tests. Fidelity verification and self-tests pass. Final
closure must capture and verify a separate v2 identity after all candidate
writers finish; no current whole-candidate proof is claimed yet.

## Next Action

Implement operational registry publication under
../registry-publication/implementation.plan.md, starting with the closed
raw-declaration parser and then complete source/decoder publication. Design
candidate215ab5f272d7b27589da04c9c1dd4a9fa0f1d8f01413d542ea72bffa4c924b9e
is approved; native ledger/projection/retrieval runtime remains partial.

## Stop And Resume Decision

The user explicitly reopened the correction on 2026-09-06. The active linked
design is `../statistical-acceptance/design.plan.md`; the older rejected
prototypes remain unchanged. The observer work proceeds independently. The
stop record below is historical, not the current operation status.

The initial worker drafts of the new kernel and wire proof were incomplete.
Coordinator inspection caught reversed tail selection, unbound sorted-result
pairing, incomplete inversion, unmetered operations and a double-encoded
locator before any readiness claim. The coordinator took sole ownership of
`bounded_math.py` and `wire_contract.py`; workers retain disjoint tests,
independent mathematical checking and read-only observer/promotion maps. This
is construction work, not a completed review round. No canonical promotion or
production statistical implementation is yet claimed.

The independent numeric reconstruction failed its explicit completion contract
and exhausted its recorded iteration allowance. `.agents/PLANS.md`
Non-Convergence requires stopping speculative work and recording the blocker.
The blocked design packet contains the exact failures and smallest next input:
a revised bounded design approach, not a production key, signature or policy
value. This is an engineering design failure and must not be attributed to the
user's deferred release issuance.

Unrelated completed work is preserved. The coordinator's combined signing gate
passed 81 tests; a final test-only evidence extension passed all 14 lifecycle
cases, Ruff and typing. `signing-local-evidence.json` records exact source/test
hashes and separates those runs. No product files changed after that combined
gate. No final standard independent package/branch approval, current CI, full
host integration or 23/23 completion is claimed. The observer/monitor packages
are unfinished, not rejected designs. No commit or push was made in this work.

## Change, Authority And Gate Ledgers

| Surface | Owner | Required proof | State |
| --- | --- | --- | --- |
| prior scoped evidence logs/map/verifier and .gitignore | prior retention testing plan | clean-export integrity/tamper proof | retained, locally verified |
| parent/index/resume/M0/M5/split manifest | package 1 | split fidelity and current candidate identity | fidelity passed; identity repair linked |
| signature adapter, tests, pyproject | package 2 | known-answer, real owner integration, typing/lint/package, final CI | active |
| numeric proposal/experiments | linked numeric design | exact certificates, independent verifier, design review | proposal only |
| split verifier and evidence tests | linked coordination-identity testing | tracked/untracked self-exclusion and unrelated-tamper proof | active |

Detailed gate commands/results remain in each owner packet. Current workflows
must be read and their complete affected gate matrix run at final freeze; no
focused test substitutes for that evidence. No known product test failure has
been classified pre-existing. Historical identity validation is a distinct
recorded evidence limitation, not product approval.

## Identity, Migration And Rollout

Use behavioral module/type/test names; requirement IDs appear only in these
traceability records. Existing persisted and canonical artifact bytes remain
unchanged until an approved contract correction and its authority chain exist.
Trust is explicitly configured; an absent verifier remains unavailable. Rollback
must never enable unsigned activation or a retired semantic fallback. All new
public/persisted types, package imports and tests must enter the final identity
and package gates; detailed inventories belong to their packets.

## Evidence Maturity, Review And Limits

No package or parent completion is asserted by this index. Record specified,
derivable, implemented, locally verified, independently reproduced, CI enforced
and operational evidence separately. Review budgets: one coherent cohort per
packet, at most two bounded remediation rounds before recording the unresolved
cause. Final whole-branch review remains required. Actual production signatures
are deferred by user instruction; no substantive policy defaults are invented.

The retained scoped-context verifier is revision-bound to 191826c. After the
new cryptography dependency edit it correctly rejects the current pyproject
digest; this is not a historical-log corruption or a passing current proof.
Reproduce that historical package using `--root` on an export of its recorded
source commit with the retained evidence overlay, as in the previous retention
checks. Final engineering closure requires new evidence for the changed source,
not rewriting the old scoped-context manifest to make it pass.

## Current Coordinator Update

The authority reconstruction passes 16 model checks, Ruff and Pyright but its
one conformance review did not converge. The linked design is blocked at its
explicit budget; exact issue-time key authorization, composed bounded byte-entry
proof and closed compact shapes remain required. This is an engineering design
blocker, not missing user signing material. No canonical promotion is authorized
by that rejected candidate.

Independent observer work continues. Root is completing historical source replay
under the captured package environment. `group_projection_owner` (Terra worker)
may write only a new group projection module and focused new tests; existing
source production/test files are frozen against that writer. It must project
retained authority and real graph changes without invented provenance, and report
any indeterminate semantic field before implementation. Root executes all pytest.
An unintegrated projection helper cannot close a runtime requirement.
