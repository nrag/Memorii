# Semantic Ingestion Engineering Closure Resume Packet

- Parent: `docs/work/semantic_ingestion/implementation.plan.md`
- Active packet: `milestones/05-authenticated-observer-comparator.plan.md`
- Status: target identity design approved; ledger activation implementation active; registry/checkpoint construction locally verified; acceptance-authority prerequisite remains blocked
- Baseline: M3.1/M4 complete at `58ec5cc5a1e463a934681facc81630c956c2197b`; dirty packaging/audit artifacts are prior authorized work.

Current checkpoint: the full-write snapshot storage primitive is implemented
and independently approved (snapshot-revision/closure.md); initial compatibility
run 54 passed, final focused run 19 passed, type/lint/identity checks pass.
Bounded numeric port and native source-finalization slices are independently approved. Group planner-binding retention passes its focused public-path test;
group CAS and authenticated query/comparison are unfinished. A shared ledger
transaction prerequisite is active under the approved operational profile direction in `../observation-ledger/design.plan.md`;
its minimal ordering model passes 19 checks with targeted independent test
consultation closing the required evidence gaps. The authenticated foundation
passes seven focused tests and root Pyright, but has no production query caller. The acceptance-authority
design is blocked at its stated review limit, with precise issue-time and verifier
boundary gaps recorded. Full M5/semantic ingestion closure has not been reached.

M0 corrected engineering is complete with 183 acceptance regressions; rejected
C2 history remains rejected. Release signing is deferred. No policy default is
invented. The user has no PKI preference; Ed25519 with PEM key interchange is
the recommended initial offline workflow, with external signing kept behind an
adapter. No production keys or signatures are being issued.

## Latest Verified Progress (2026-09-07)

Native policy retention is implemented and independently approved within its
bounded scope (../native-policy-retention/closure.md). Final JSONL reopen,
legacy, tuple-guard and policy-coordinate evidence passes; configured Pyright,
identity hygiene and the exact source gates pass. Operational registry
construction is active under ../registry-publication/implementation.plan.md.

The current workflow's CTV binding, lifecycle provenance, and structural manifest
checks all pass after compiler-derived artifact/pin refresh. This is local
execution, not a GitHub CI claim. The observation design correction is frozen in
`../observation-ledger/design-candidate-final.json` and approved for implementation.
Registry declaration/compiler/source/publication construction passes 65 focused
tests and explicit-file Pyright; exact evidence and file hashes are in
../registry-publication/construction-verification.json. Actual observation and
ledger payload models now cover 56 constructed profile-3 inventory rows plus the
17-variant stream alias. Local model verification is recorded in
../registry-publication/model-construction-verification.json; it is not a full
recursive declaration inventory or published registry. Native receipt/evidence
join verification now rejects coordinated receipt-ID substitution; seven tests
pass in 6.15s. Exact files are pinned in
../registry-publication/native-publication-model-verification.json. The original bounded construction workers finished at that checkpoint. New
source authoring, schema body validation and registry-role authoring assignments
are active; current ownership is in the registry-publication WorkPlan.
Production registry publication, projection publication, shared ledger and
public retrieval remain unimplemented.

The separate ../numeric-wrapper-wire/design.plan.md owns a newly discovered
persisted numeric wrapper omission. The tested proposal uses existing CTV maps
and an explicit decimal encoding-spec ID in the numeric source row. Its 5
positive and 14 negative feasibility cases pass. The user approved this form on
2026-09-07. All three reviewers approved the corrected amendment; it is promoted
under ../numeric-wrapper-wire/closure.md. No user decision remains for numeric
wire representation. Numeric parser/compiler/codec and public page/snapshot
model construction pass the selected 36-test check in 5.72s, recorded in
../registry-publication/numeric-public-model-verification.json. The untrusted
source draft now contains 77 roots and 179 schemas after the approved
acceptance-witness exclusion; source conformance and full registry publication
remain active. Replay/checkpoint and ingestion-time model tests
pass ten cases; new cursor/cohort shapes preserve the historical foundation.

## Current Work And Owners

Current registry checkpoint: 179 schemas, 1255 roles, 36 selected source files
and 6444 rows; full independent equality and 58 vectors pass. Runtime registry
construction and native candidate encoding have bounded independent approvals.
Ordinary, root self-digest and cursor signature integrity plus protected reader
pass 91 tests in 5.93s, with scoped Ruff/Pyright and all three bounded approvals.
See ../registry-publication/resume.md and registered-integrity-review.json for
exact candidate and evidence. No reachable public integrity reader exists yet.
Fixed checkpoint preimage/crypto construction passes five tests and all three
bounded reviews; external dispatch remains
fail-closed until protected replay/lifecycle authority exists. Ledger CAS, public
retrieval and comparison remain unfinished. The all-23 table still has 15
retained baseline-complete, six partial, one blocked and one not implemented.
Final CI and whole-branch review remain required.

- Latest registry construction evidence: 1075 raw declaration files authored,
  bounded 895-role source audit without concrete conformance findings, and a
  finite 179-entry native decoder table. Publication authoring, source/manifest
  verification and compiler tests pass 60 cases in 5.40s, with exact hashes in
  ../registry-publication/publication-package-authoring-verification.json.
  Nested codec proof, bounded native emission corrections, offline source
  closure mapping and immutable registry history are active. No runtime
  publication, activation, ledger transaction or retrieval closure is claimed.

- Public-key adapter and configured resolver pass 47 focused adapter/release
  tests, including canonical release verification with real test-key signatures.
  Resolver-created registered execution now passes positive and tamper tests
  with coherent predecessor publication. Offline PEM signing and verification
  pass seven CLI/library tests; four-artifact prepare/sign/assemble passes 14
  integration tests. Lifecycle record/root signing passes 14 integration cases.
  The coordinator's pre-extension combined signing/provenance run passed 81;
  exact final file hashes are in `signing-local-evidence.json`. No package closure
  claim; complete host/policy emitters and final package review remain.
- `../acceptance-numeric-contract/design.plan.md` owns a bounded design
  correction: exact policy decimals remain unchanged, while computed values
  need conservative rational enclosures. Proposal/feasibility only so far;
  no canonical design or persisted schema change is approved. Three independent
  reviews rejected the round-two boundary evidence. That operation is paused
  and its exact files archived. `../acceptance-numeric-boundary/design.plan.md`
  records the rejected boundary reconstruction. Coordinator no-write probes
  reproduced an accepted changed null probability under the unchanged manifest,
  serialization before its cap, and locator bytes differing from canonical
  encoding. Independent consultation agrees. Its bounded design operation is
  blocked at the reconstruction limit; R14 is incomplete and not promoted.
- `../coordination-identity/testing.plan.md` owns the current-snapshot verifier
  repair. Historical v1 identity stays byte-identical. Current v2 excludes only
  its own file and pin; public default-verifier mutation tests pass and the
  bounded testing slice is independently approved. Final whole-candidate v2
  capture still waits for source freeze.
- `observer-readiness.md` records coordinator-validated storage reads and
  retained zero-effect finalization authority for the future public audit API.
- Python 3.12.14 with cryptography 50.0.1 is available in the root .venv.
  No commit or push has been made in this implementation turn.

## Next Action

Implement the approved target-authority prerequisite in
../observation-ledger/milestones/target-authority.plan.md, then complete activation
CAS. The canonical contract is docs/design/semantic_ingestion_activation_target.md;
its independent design closure is ../activation-target-identity/closure.json.
No owner decision remains for this boundary. Runtime activation still fails
before drain or write until implementation passes its acceptance contract.
No production signature is needed for engineering.

## Current Numeric Repair Evidence

`../statistical-acceptance/candidate.json` pins the new nonproduction component
candidate. Coordinator verification: 76 focused tests pass, Pyright has zero
errors, and the separate checker passes 33 vectors with eight altered-result
rejections in normal and optimized Python. Mandatory preverified context now
binds coverage, gate/frame, provenance/cluster and IID inputs independently of
policy parsing. All three standard reviewers approved successor candidate
502306dc39b966bf13ec261f1f81a6fb59e867816f2f889f491c0ac0037eb9da.
The bounded design closure is recorded in `../statistical-acceptance/closure.md`.
This does not yet promote canonical schemas or implement the full R14 owner.

## Current Integration Work

The approved kernel and strict verifier now live in the isolated root
`acceptance/` package, with its own closed CTV encoder and no production imports.
The bounded numeric port has all three independent approvals and 81 passing
tests; see `numeric-port-review.md` and `numeric-port-candidate.json`. Full
baseline/context verification, canonical promotion and CLI remain incomplete.

The independent baseline verifier requires acceptance-specific trust, lifecycle,
and signature-preimage contracts that the current architecture does not fully
declare. A linked `../acceptance-authority/design.plan.md` records that bounded
design prerequisite; no runtime verifier is fabricated from policy projections.
The corrected authority prerequisite is frozen in its `candidate.json`
(SHA-256 36fc5f46416de4667b0a02e7d300af3427155a7b1f3d400073f60e61819be5e0)
with all four source files archived. The coordinator reproduced seven feasibility
tests. All three delta reviews require changes: complete immutable lifecycle
and multi-key reduction, signer coordinates/preimages, bounded parsing and
accurate vectors. The linked review record reconciles the findings. One closed
state-machine reconstruction has now been reviewed and is blocked at its declared
budget. Candidate 7d4d19e2ade112a4102492b9cf27029b0bae9de35c917bc510275c139a1f3af4
passes 16 model tests, Ruff and Pyright, but all reviewers require the exact
issue-time key-state relation. The test reviewer also requires composed bounded
byte parsing and closure of the compact modeled shapes. The archived candidate
and reconciled findings are in the linked review record; no promotion is approved.

Source-finalization integration is paused for linked
`../terminal-publication/debug-001.plan.md`. The exact public reproducer now
passes after selecting the native member codec; 13 native codec/builder tests
also pass. Genuine historical fixtures from HEAD exposed nonidentical legacy
intent encoding and standalone reload forward-reference initialization failure.
All three legacy contract types now re-encode byte-identically; persisted legacy
reload, zero-group finalization and 22 recovery/root cases pass. Shared codec
regressions pass 75 tests and assembly/record checks pass 18. The source candidate
was frozen; spec and correctness approve its bounded debugging slice. Test review
required four stronger public-boundary families. Actual CAS membership, all four
post-group authority substitutions and both persisted corruption/reopen cases now
pass. Historical public replay reaches an admission verification-digest mismatch:
the baseline fixture had one installed distribution, while this checkout discovers
two and falls back to source-checkout bootstrap identity. Component bytes are
unchanged; reconstructing the captured package environment is under consultation.
The test-only candidate 89907b04b2a9888ad6b708c859c3db1bde359dfb029dc24eed03a7780b80c9a5
now has targeted test approval and a passing final identity gate. Source debugging
is complete; see `../terminal-publication/closure.md`. No observer closure is claimed.
Group observation, authenticated query/comparison, monitor and final host closure
remain unfinished. Real signing and external quality values remain deferred.

## Current Continuation Checkpoint

Native group CAS construction is paused at the shared-ledger boundary; no group
persistence edits were made during this design reconstruction. Source-local
control revisions must not be presented as a global observation revision.
`../observation-ledger/closed-contracts.md` contains the draft intent/receipt,
head/entry, activation and checkpoint boundary. Complete its registered bindings
and actual transaction proof before frozen design review and runtime integration.
The separate acceptance-authority prerequisite remains blocked as recorded.
This historical checkpoint predates the later registry model construction.
Current owners and verification are in ../registry-publication/implementation.plan.md.

The shared-ledger transaction now also has four passing real JSONL backend
mechanics probes (head absence/digest conflicts, immutable collision, interleaving
and durable reopen), with neutral records and explicit semantic-policy exclusion.
The immediate prerequisite is the production profile registry/binding owner from
SIA3.15.1, which is specified but absent. The fixed 56-root traceability compiler
is test-only and must not be mistaken for runtime registration. See the linked
ledger binding-authority-map.md and backend-evidence.json. No full design or
production ledger approval has been issued.

## Latest Registry And Retrieval Checkpoint

The publication inventory now declares concrete native result locators, separate
model alternatives for revision-free payloads and retained snapshots, finite
signing policies and protected deployment pins. Native digest fields retain
native owner validation under profile3; no old byte rehashing is allowed.
These are design corrections, not a published runtime registry.

Root corrected the retrieval map after discovering that the native group commit
bypasses projection-history publication; generic terminal publication does not.
The required native CAS integration is determinate. The user subsequently
approved separate temporal/trust projections; the approved observation candidate
records that decision. No M5 completion is claimed. The numeric wire choice
described in Latest Verified Progress is a separate, newly identified decision.

Current registry checkpoint: witness-boundary conformance amendment is approved
and promoted under ../time-witness-boundary/closure.md. Acceptance witnesses are
removed from the production model/source inventory. The draft has 77 roots and
179 schemas, with all 895 proposed schema/policy roles parsing in the local
11-test source/public-boundary check. It is still untrusted and unpublished.
Finite native decoder table and source-directed materialization construction
are active with disjoint Terra owners; the registry WorkPlan records scope.


### Protected Target Integration Checkpoint

See ../observation-ledger/target-authority-construction.json for the latest exact
construction evidence. Target configuration now reaches provider/runtime/writer/
store; runtime checks current deployment authorization before explicit activation,
and atomic owner rechecks package authority before the still-unavailable CAS.
Four target/provider tests pass;14 standalone fresh-process bootstrap cases pass.
Release preparation and full installed host proof remain open. Five compatibility
failures were isolated to legacy writer canonical-field omission and corrected;
../recovery-index-validation/ owns the exact-candidate regression/review record.
The selected decoder source changed, so reproduction refreshed current publication
and all58independentvectors passed; older hashes above remain historical evidence.
No M5 closure, CI success or production signature is claimed.
