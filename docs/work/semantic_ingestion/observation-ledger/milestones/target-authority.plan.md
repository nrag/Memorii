# Protected Activation Target Authority

Work type: implementation milestone. Status: active construction.
Parent: ../implementation.plan.md. Downstream: activation.plan.md.
Baseline: HEAD 191826cd3afb38bf605a337a71d576063b3bae5e, existing authorized dirty
tree preserved. Normative design: docs/design/semantic_ingestion_activation_target.md;
approved candidate b778c74490515a5c336bcec8784857678245c0a6760406b4fc9e95196ba72e62.
Design closure: ../../activation-target-identity/closure.json.

## Scope And Completion

Implement the target manifest, exact P/E/fingerprint recipes, protected deployment
and retention inputs, bootstrap checks, release preparation, and canonical
provider/runtime/writer/store target verification. Preserve unavailable activation
until the following activation CAS packet implements durable cutover. This
prerequisite cannot close R17 or claim successful ledger activation.

Complete only when real protected provider composition verifies the target and
rejects invalid configured authority without fallback; installed bootstrap and
release verification are exercised; exact byte-oracle vectors agree; focused
failure families, required affected gates and independent reviews pass. Final
activation success and JSONL trio recovery remain in activation.plan.md.

## Bounded Construction Sequence

1. Closed typed manifest/deployment rows and exact pure identity recipes.
2. Immutable retained configuration, package/deployment verification, standalone
   bootstrap and release preparation, using existing raw JSON and signing owners.
3. Protected capability/provider/runtime/writer/store forwarding and explicit
   host activation entrypoint. Target verification has a real composition caller;
   unfinished CAS remains fail closed, with no success-shaped fallback.
4. Frozen whole-prerequisite verification and standard independent review.

These are construction steps, not separate completion claims. Root owns evidence,
generated artifacts, test commands and final reconciliation. One worker owns
production edits and its focused tests; no overlapping writer is authorized.

## Requirements, Proof And Toolchain

T01-T08 and the target-specific test-to-gate map in
../../activation-target-identity/verification.md are the governing proof matrix.
The test reviewer approved its frozen final design scope. The approved independent
Python/JavaScript recipe evidence contains five exact preimages and 56 isolated
field-mutation results. Production tests must use its literal expected bytes,
never regenerate expected bytes using the production owner under test.

From memorii/: ../.venv/bin/python -W error -m pytest <focused files>
-p no:cacheprovider; ../.venv/bin/ruff check <changed files>;
../.venv/bin/pyright --pythonpath ../.venv/bin/python <changed production files>.
Root owns all test/long-command execution. Local Python 3.12.14 is not CI Python
3.11 parity. Required source-publication/package/shard/gate refresh follows the
live authority chain; no prior wheel or dirty-tree run is final certification.
Substantial subprocess/package gate additions route through a linked testing
WorkPlan before suite/CI changes; small feature-local tests remain here.

## Preflight And Authority Boundaries

Spark target_binding_map confirmed ProviderMemoryService.__init__ stores
_composed_semantic_runtime; BuiltInLocalHostSemanticIngestionCapability creates
writer/store with shared verified registry history; runtime holds both owners;
atomic activation and private writer entrypoints currently fail closed. Root
independently checked those symbols and constructor arguments. The mapper's
reference to a missing literal `signatureinterfaces` symbol is unsupported:
the requested concept is the existing verifier protocol/tools, not that symbol.

New core symbols and fields use behavioral target/deployment names. Requirement
IDs remain work metadata. Root updates the production binding ledger after actual
integration; no target caller is claimed merely because a type/helper exists.
No opaque Python issuer tokens, arbitrary host-request source roots, unsigned
runtime target fallback, or label hashes are authorized.

## Next Action

Resume durable observation ledger activation CAS using the verified target
context and the completed release-preparation packet.

## Current Construction Evidence

The helper and selected registry suite passes 54 tests (16.48s); three actual
provider target cases pass (17.40s), with real signatures/publication/file checks
and host metadata isolation. All seven production owners pass scoped Pyright;
Ruff import fixes pass. The full provider compatibility run is in progress and
has one failure awaiting its completed report. No broad success is claimed.

The bounded correctness consultation confirmed overlapping anchors; root fixed
lexical equality/ancestor/traversal plus canonical scripts anchor checks and
added five negative cases. Its integration follow-up identified a missing
activation-time deployment-authorization check. This is confirmed readiness work
before CAS, not a current successful unauthorized cutover (CAS remains absent).

## Current Ownership And Cost

Initial Terra worker declined the exclusively assigned four-file integration
slice without a concrete external blocker; no changes were made by that delegate.
Root took over and implemented provider/runtime/writer/store forwarding plus
three production-path tests. Terra correctness reviewer provided two bounded
consultations; root classified both findings and owns remediation. These are not
full milestone approvals. Terra bootstrap_writer now exclusively owns new
standalone tools/observation_activation_bootstrap.py and deployment docs; no
integration/source/test overlap. Root owns all tests, evidence and commands.
Substantial process/package suite work is routed through the separate linked
../../activation-deployment-tests/testing.plan.md, awaiting test matrix review.

Signatures are exercised with isolated keys, but production signing remains
deferred. Bootstrap, release tools, final gates and actual activation CAS remain
open. Production target verification now has a built-in capability caller;
no successful durable activation is claimed.

## Latest Reconciled Construction

Runtime now retains its host-verified profile and clock and verifies deployment
authorization on every explicit activation, including direct runtime calls.
Four targeted provider tests pass19.79s; invalid target configuration never falls
back. Standalone bootstrap and pre-execution origin guard pass14 fresh-process
cases9.55s (synthetic two-distribution closure with scripts/namespace/empty file).
Full installed candidate wheels, release preparation, host conversion and complete
matrix coverage remain open. The required package-smoke workflow now selects the
bootstrap tests; no GitHub execution is claimed. Linked testing packet records
exact path-to-gate allocation and open families.

Full provider compatibility exposed five recovery failures. Separate debugging
packet ../../recovery-index-validation/debugging.plan.md isolated legacy writer
model/map canonical mismatch and repaired the two existing field hooks. Eleven
contract tests and five failed public cases now pass; exact-candidate combined
16case run passed145.85s and bounded correctness/test review approved there. Registry sources/publication and
independent vectors were refreshed after that selected source changed. R17 remains
partial and durable activation remains unavailable.

## Release Preparation Slice Complete

The offline deployer, pinned isolated launcher, typed host conversion and target
release adapter are locally verified and independently reviewed. See
../release-preparation/closure.json and ../release-preparation-packet.md. The final
candidate binds the real21distribution/5632file deployment and1772file target;
all authority and installed tampering checks reject. Package-smoke runs the full
chain, but CI execution is not observed here. The activation CAS and remaining
parent proof families remain open. This supersedes earlier preparation-pending
statements; no full target-authority or R17 completion is claimed.
