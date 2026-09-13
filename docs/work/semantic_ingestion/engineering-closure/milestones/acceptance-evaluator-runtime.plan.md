# Acceptance Evaluator And Deployment Bridge

- Parent WorkPlan: `../implementation.plan.md`
- Status: active; approved persistence design implementation
- Base revision: `dbb42d33c521ae7b3881e7fb3f61a3a12aff7aa5`
- Requirements: R14 primary; R13 related
- Design baseline: canonical SIA Section 5.6, the approved statistical numeric
  design, the accepted authority-successor contract, and the approved issuance-
  prefix correction

## Observable Outcome

An installed acceptance command evaluates an exact release/baseline/policy/
evidence set using constructor-held authority, independently recomputes every
declared statistical gate, publishes one immutable verified-result receipt and
passes only its verified approval-release and baseline digests to a production-
owned deployment-authorization issuer. Production imports no acceptance module,
schema, key, provider or arithmetic implementation.

## Canonical Owners And Boundaries

- `acceptance/capability_baseline_approval.py` owns the closed acceptance release,
  issuance snapshot, key history, checkpoint, receipt and verifier contracts.
- `acceptance/statistical_certification.py` retains independent numeric evaluation.
- `acceptance/evaluator.py` owns protected held-context construction, evaluation
  orchestration and immutable receipt publication.
- `acceptance/cli.py` is a thin installed entrypoint. Callers may identify input
  and output resources but cannot inject keys, histories, parser ceilings,
  providers, trust decisions or approval flags.
- `memorii.core.memory_evolution.deployment_authorization` owns the production
  request and issuer boundary and accepts only verified digests and stable target
  coordinates. It cannot import `acceptance`.
- Packaging and CI must install and invoke the acceptance command in an isolated
  target while retaining the production/acceptance import boundary.

Existing v1/v2 artifacts remain replay-only. The approved issuance-prefix V1
addition is additive; missing historical issuance snapshots require reissuance
and never timestamp reconstruction. No migration rewrites historical bytes.

## Validation Matrix

| Family | Required proof | Failure signal |
| --- | --- | --- |
| Protected construction | Installed command reaches constructor-held trust, current status, immutable histories, limits and held numeric context | Missing/outage/mismatch or attempted caller injection yields no certificate, receipt or issuance request |
| Complete statistics | Multi-cell enabled/unsupported coverage independently checks membership, event uniqueness, weights, missing outcomes, methods, bounds, Holm rank/alpha, threshold and fingerprints | Removed/extra cell, moved cluster, duplicate event, changed weight/threshold/fingerprint/IID declaration or undefined denominator rejects |
| Immutable receipt | First publish, byte-identical retry, lost acknowledgement, restart, substitution and interrupted write | Exactly one digest-addressed receipt; conflicting bytes and partial publication reject |
| Digest-only bridge | Real verified receipt feeds production issuer and ordinary activation consumes the resulting authorization | Omitted/substituted approval or baseline digest, removed bridge caller, unsigned fallback or wrong purpose denies before learned/graph mutation |
| Lifecycle | Issue/evaluation cutoffs, equal-time order, rotation, expiry, retirement, revocation, compromise, prefix fork/gap/reorder, terminal replacement and durable production-revocation ordering | Stale or invalid authority produces no verified result or deployment request |
| Packaging/isolation | Build and install distribution in an empty target; invoke the command with isolated imports | Missing command/module or either forbidden import direction fails the gate |

The current 169 authority-model and numeric tests are the construction baseline.
They do not satisfy this matrix because they use a synthetic caller-created
`HeldBinding` and have no installed command, receipt store or deployment bridge.

## Change, Authority And Gate Ledgers

Expected changed surfaces are the new acceptance owners, production digest-only
issuer boundary, package configuration, focused unit/integration/install tests,
canonical authority/schema declarations, generated registry/CTV authority and
the production-entrypoint ledger. Every generated digest, schema role, package
manifest and workflow pin downstream of those surfaces must be refreshed.

The preflight map is `../stage1_preflight_r13_r14_map.md`. Its zero-caller
findings are accepted. Its proposed production adapter importing or constructing
`acceptance.HeldBinding` is rejected because SIA requires the one-way serialized
digest boundary described above.

## Delegation And Ownership

- `stage1_acceptance_map` (`code-mapper`, read-only production trace) completed
  the zero-caller preflight artifact.
- `stage1_acceptance_tests` (`test_reviewer`, read-only) completed the pre-coding
  family matrix and identified synthetic tests that cannot prove Stage 1.
- One implementation worker owns all overlapping production, acceptance, test,
  package, generated and milestone files until handoff. The coordinator owns
  commands, reconciliation, candidate freeze, reviews, commits and pushes.

## Completion Contract

Focused and affected authority-chain gates pass, installed-package execution and
import isolation pass, the production-entrypoint ledger shows nonzero canonical
callers with caller-removal/authority-removal/fallback mutations, and spec,
correctness and test reviewers approve the frozen candidate with
`remaining_validated_p1_p2: []` and no unresolved `changes_required` or
`blocks_approval` finding. R14 then becomes engineering-complete; external policy
approval, qualifying measurements and final signatures remain release conditions.

## Next Action

Commit the complete Stage 1 V2 remediation candidate, repeat all three
independent reviews on that exact revision, and reconcile every finding before
promoting R14.

## Signed Numeric-Context V2 Preparation (2026-09-12)

The frozen signed numeric-context feasibility chain now names the two missing
registered authority artifacts: `ApprovedCapabilityBaselineV2` and
`CapabilityBaselineApprovalReleaseV2`. The fenced authority commit's active
release digest is the fixed selection coordinate for the latter; it binds the
SHA-256 of the complete signed baseline bytes. Fixed V2 configuration carries
neither artifact and cannot select either. The feasibility candidate was
repinned after this clarification and its independent checker passes.

This records only the design/evidence preparation. Registry descriptor grammar,
V2 artifact schemas, the acceptance-owned manifest verifier, and evaluator
integration remain unimplemented; R14 stays partial.

## Independent Review Round 1 (aa41b0d2)

The spec, correctness, and test reviewers rejected the first implementation
candidate. The coordinator confirmed: omitted acceptance package resources;
non-durable and unreconciled production publication; active-successor release
rejection; missing production revocation reader/trust separation; unused trust
snapshot key declarations; incorrect genesis index-ahead recovery and
post-link retry acknowledgement; incomplete authority-path permission checks;
and insufficient full-artifact vectors, installed subprocess, multi-cell,
lifecycle, crash/retry, and recursive isolation evidence.

The test review also identified a scope conflict in this packet's bridge row.
Stage 1 proves production-owned publication of the exact serialized deployment
authorization. Ordinary semantic-ingestion activation consumes that artifact in
the already sequenced Stage 4 R13 integration; it is not part of bounded R14
promotion. The validation matrix is interpreted accordingly and the parent R13
row remains open.

All findings are `changes_required`; the validated product findings are
`DREV-001` through `DREV-006` and `R14-COR-01` through `R14-COR-03`. There is no
`blocks_approval` finding and no external decision is needed. The next candidate
must close every item with code and evidence before review repeats.

## Historical Paused Candidate (superseded)

Bounded implementation is present: `acceptance/capability_baseline_approval.py`
verifies closed signed active releases with constructor-held Ed25519 keys, an
immutable issuance key-event prefix, protected current key history and current
checkpoint. Its acceptance digests use the acceptance CTV encoder. The evaluator
recomputes the numeric certificate, prepares a digest-only production artifact,
O_EXCL-publishes the receipt, then makes that artifact visible; a receipt-store
failure cannot publish an authorization. The production artifact has a separate
production-only canonical-byte decoder/signature verifier. `memorii-acceptance-evaluate`
is packaged and loads exactly one installed configured runtime entry point.

Focused local proof: 68 acceptance tests pass under Python 3.12 with warnings
as errors; wheel construction includes the acceptance package and console
script; installing that wheel into the repository test environment succeeds,
`--help` executes, isolated imports succeed, and production source has no
`acceptance` import. The empty-target virtualenv attempt could not install the
declared `cryptography` dependency because this environment has no package
network access; the installed-wheel proof therefore used the local environment
with its already-installed dependency set.

This packet remains active. The remaining matrix work is canonical registry
promotion and generated authority, a durable repository implementation for the
acceptance history/checkpoint/revocation records, a configured host evaluator
runtime exercised through the installed command, full multi-cell mutation and
restart coverage, and normal semantic runtime consumption of the issued artifact.
The latter is deliberately deferred to Stage 4; R14 and R13 remain partial.

## Complete Stage 1 Candidate (2026-09-12)

The installed command now discovers one standard evaluator and one separately
owned serialized deployment publisher. It reads the fixed platform-data
configuration, opens a signed registration-bound SQLite fence, validates the
complete canonical authority object closure and signatures, and retains one
exclusive evaluation snapshot through approval verification, independent
statistical recomputation, signed receipt durability, and deployment
publication. Acceptance and production import neither other's package.

The public CLI has no evaluator or authority injection parameter. A real
Ed25519 fixture constructs and persists the registered trust, key, issuance,
release, checkpoint, and commit chain, then exercises the public discovery path
to a signed receipt and visible production authorization. Negative cases cover
bad signatures, missing authority, future checkpoints, insecure or aliased
configuration, provider cardinality, repository crashes, history corruption,
and concurrent publication.

Coordinator validation: 130 acceptance tests pass; the combined acceptance,
authority-feasibility, and production-composition selection passes 278 tests;
Ruff and the first-party Pyright selection pass; the independent vector checker
and diff check pass; and an isolated wheel builds with both provider entry
points and the console script. The required CI job installs that wheel into a
fresh virtual environment, resolves both providers and invokes the installed
command in a subprocess before running the configured success/failure suite.

R14 remains partial until the frozen candidate receives the three independent
reviews required by this WorkPlan. Ordinary provider activation consumption is
still Stage 4 and does not block the bounded R14 evaluator result.

## Durable Attempt Integration (2026-09-13)

Registered snapshot evaluations now derive an immutable attempt digest from the
selected authority commit and the exact candidate/request bindings, excluding
the local wall-clock sample. `AtomicEvaluationReceiptStore` persists the exact
prepared production authorization bytes and signed registered receipt bytes in
an fsync-backed absent-path attempt envelope before either downstream publish.
On a later invocation for the same commit and inputs, the evaluator loads those
bytes and skips both signer and deployment preparation; it publishes the
authorization first through exact-visibility reconciliation, then the receipt,
while the repository lease remains held. This is locally verified only: the
focused evaluator/repository/installed-runtime selection passes 20 tests and
Ruff/diff checks pass. Fault-injection restart and concurrent-retry proofs
remain required before R14 can be promoted.

## Signed Trust Declaration Binding (2026-09-13)

The selected authority view now carries the exact signed trust snapshot into
approval verification. Bootstrap `acceptance_keys` must byte-match exactly one
declared key; the declaration must include the approval purpose and contain the
release issue time in its half-open static interval. Issuance and current
lifecycle checks remain independently required. Installed fixture and legacy
evaluator fixtures now declare the exact approval purpose. Focused evaluator
and installed-runtime tests pass (10) with Ruff; negative declaration matrix
coverage and generic registered-artifact purpose enforcement remain pending.

## Historical Slice A Evidence (superseded 2026-09-12)

The bounded schema/CTV/repository slice now provides the nine-artifact packaged
registry with complete field inventories, a deterministic generated manifest
bound to the source SHA-256, and an independent vector checker that imports no
acceptance runtime module. `acceptance.authority_repository` now uses
content-addressed immutable objects, an advisory index repaired from a
full-durability SQLite fence, coordinate CAS, and a lease-held nonmutating
evaluation snapshot. Its receipt store publishes exact bytes by O_EXCL link
after file fsync and rejects substitutions.

Focused evidence from `memorii/` with `.venv/bin/python`:

- `-W error -m pytest tests/unit/acceptance/test_acceptance_authority_repository.py tests/unit/acceptance/test_acceptance_schema_authority.py -p no:cacheprovider` — 5 passed.
- `-m ruff check` over the slice — passed.
- `pyright --pythonpath ../.venv/bin/python` over the slice tests and owners — 0 errors.
- `docs/design/semantic_ingestion/acceptance_authority_vectors/check_vectors.py` — passed.

This is only a locally verified bounded persistence substrate. It does not yet
decode the registered artifacts into lifecycle domain objects, compose a host
runtime, or provide a non-test production caller. The R14 binding therefore
remains partial with zero callers.

## Historical Slice A Remediation (superseded 2026-09-12)

The repository object path now writes a unique temporary, fsyncs it, creates
the digest final path by link-only publication, and fsyncs the object directory;
an existing object is accepted only for exact bytes. The schema helper now
binds the complete canonical profile bytes (including protected parser ceilings)
inside LP digest preimages and exposes closed-map/purpose/digest and signing
preimage validation helpers. Six focused schema/repository tests pass with
Ruff and Pyright. This remains partial: descriptor-level field types and full
artifact/history decoding are still required before the repository can serve
the approved lifecycle authority model.

## Historical Slice B Progress (superseded 2026-09-12)

The package declares one `memorii.acceptance_evaluator_runtime` provider,
`acceptance.host_runtime:InstalledAcceptanceRuntime`. The public CLI no longer
accepts evaluator injection and resolves the provider before candidate files
are opened. The fixed host configuration is derived from `sysconfig` platform
data at `etc/memorii/acceptance/runtime-v1.json`; it rejects non-absolute,
aliased, symlinked, or group/world-writable paths and constructor-holds trust
keys, registration, limits, clock and publisher coordinates. The PR workflow
includes a 20-minute installed-wheel provider job required by the semantic
ingestion aggregate.

Repository loads now optionally verify each signed registered artifact via a
constructor-held signing-preimage verifier, walk the selected release head,
and require exact equality of commit/checkpoint revocation evidence.

Focused evidence: evaluator, host-runtime and repository tests pass (17);
the complete acceptance directory passes (124); `git diff --check` passes.
The wheel built with `--no-build-isolation`, but final target-install entrypoint
proof and pyright closure are still pending. This checkpoint does not promote
R14.

## Fixed Resource Admission Matrix (2026-09-13)

Installed runtime construction now admits configuration, authority, fence,
receipt, and deployment-publisher coordinates only through secure existing
ancestry. The matrix covers direct and parent symlinks, group/world writable
fence/receipt/publisher coordinates, equal and nested failure domains including
fence-under-authority, and secure missing leaves. The focused installed-runtime
and authority repository selection passes 31 tests with Ruff and diff checks.

## Production Revocation Reader Boundary (2026-09-13)

Decision recorded: production-revocation evidence is cumulative ordered history.
For a non-genesis authority commit, unchanged active release requires an exact
unchanged evidence list. Changing predecessor active release `A` to successor
`B` (or null) requires the existing list as an exact prefix plus exactly one
new pair whose signed receipt names `A`; genesis cannot carry evidence.
`AcceptanceAuthorityRepository.compare_and_publish` enforces that transition
before advancing the fence. It requires the new receipt/checkpoint bytes in the
prepared set and checks them against the separately discovered read-only
production reader. Every recovery re-reads and independently validates the
stored pair against the current production mapping.

The fixed `memorii.acceptance_production_revocation_reader` provider is owned
by `memorii.core.memory_evolution.deployment_authorization` and imports no
acceptance module. Its least-privilege configuration contains only
`reader_root`; it serves canonical content-addressed receipt/checkpoint bytes
and a current mapping. Acceptance holds distinct production Ed25519 keys and
verifies canonical registered decoding, purpose/signature/digest, exact prior
release join, epoch advancement, time order, membership, checkpoint ancestry,
and current mapping byte equality. The installed host validates the reader root
with the other fixed paths and cannot share its failure domain.

Focused proof: `test_production_revocation_boundary.py` has a signed
generation-two success/restart read, wrong signer, stale mapping, membership,
epoch, and malformed mapping rejections. The repository suite proves both
replacement-before-revocation rejection and one-pair append/reopen
revalidation through `compare_and_publish`, including extra, reordered, and
prefix-substituted history rejection; installed CLI fixture remains on the
actual fixed composition root. The independent verifier accepts a signed
checkpoint whose current epoch is later than the receipt's advanced epoch and
fails closed on reader outage after restart. The three focused suites pass 41
tests;
Ruff and diff checks pass. A source Pyright scan has no first-party finding;
the six reported paths are existing environment-only unresolved `cryptography`
and `pydantic` imports. A built wheel contains the distinct
`memorii.acceptance_production_revocation_reader` provider. This is bounded
R14 remediation evidence, not the complete R14 review slice.

## Installed-Wheel Public Entry-Point Proof (2026-09-13)

`memorii/tests/integration/installed_acceptance_wheel_proof.py` prepares the
real signed authority/config/input fixture, writes it at the installed
interpreter's `sysconfig` data coordinate, and invokes only the installed
`memorii-acceptance-evaluate` executable from outside the checkout with
`PYTHONPATH` removed. It asserts both `acceptance` and `memorii` originate
under the fresh venv, then verifies the printed registered receipt, one durable
attempt envelope, and the exact production authorization output. The same
runner proves zero-output rejection for a bad candidate signature, missing
authority object, future checkpoint, insecure or symlinked configuration,
insecure authority root, and missing evaluator/publisher/revocation-reader or
duplicate evaluator providers.

The `acceptance-authority-runtime` CI job now builds a wheel, creates the
fresh venv, inventories all three fixed providers, and runs that proof before
the focused source suites. Local execution completed with a newly created venv
and wheel-installed package from a secure temporary location; child execution
had `PYTHONPATH` unset. The environment's ordinary fresh dependency install
could not finish because its SciPy download repeatedly stalled, so the local
proof used only a temporary dependency path to the existing local venv while
still requiring both tested packages to resolve from the fresh wheel venv.
Ruff, diff check, and the three focused acceptance suites pass (41 tests).

## Recursive Import Isolation (2026-09-13)

The fixed serialized boundary is now guarded by a recursive AST audit over all
packaged `acceptance/**/*.py`, all `memorii.core.memory_evolution` and
`memorii.core.semantic_ingestion` modules, semantic-ingestion production tools,
and any production integration modules. Acceptance cannot statically import
`memorii`; the production graph cannot statically import `acceptance`, for
either `import` or absolute `from ... import ...` syntax. Nested mutation
fixtures prove both directions are detected.

The installed-wheel runner performs a second successful in-venv evaluation and
writes `import-origins.json` for every loaded `acceptance.*` and `memorii.*`
module. It rejects if any loaded module has no file origin or resolves outside
that venv. Local wheel proof, including the imported-origin inventory, passes;
the focused host/CLI suites pass 20 tests, Ruff and diff check pass.

## Unsupported-Cell Binding Design (2026-09-12)

The prior locator-tuple draft was superseded after design review because SIA
section 5.6 makes the signed coverage and gate manifests, rather than caller
locators, the complete coverage authority. The linked design
`../../statistical-unsupported-cell-binding/design.plan.md` now defines the
complete signed numeric-context authority chain: coverage, gate, and sampling
frame manifests derive every held numeric field; unsupported abstention gates
retain normal evidence and Holm participation; and V2 retains no V1 replay API.
Its frozen-literal signed-manifest feasibility proof uses `.venv/bin/python`,
validates all derived-authority coordinates before parser reachability, and
passes locally. Its candidate records literal signed baseline/release/manifest
fixtures, the separate CTV byte checksum, and a distinct sampling-frame digest;
no production authority is claimed. No
production schema, runtime, test, CI, or public CLI change is included here;
R14 remains partial pending delta review and a separately owned implementation
slice.

## V2 Cutover Candidate (2026-09-12)

The host, evaluator, installed CLI fixture, and wheel proof now consume the
five-artifact V2 chain. The verifier reconstructs the complete numeric context
from signed baseline, release, coverage, gate, and sampling-frame bytes. The
evaluator compares every release authority coordinate with the certificate
before publishing a receipt or deployment authorization. V1 runtime config and
certificate markers have no authorizing path.

Local evidence: 175 acceptance tests pass; the installed wheel passes one
public success and 14 fail-closed cases; schema-complete independent vectors
cover all 13 registered artifacts; the signed multi-cell feasibility matrix,
Ruff, first-party Pyright, and diff checks pass. R14 remains partial until the
frozen successor receives independent specification, correctness, and test
review. Next action: commit the successor and run those three reviews.

## Stage 1 V2 Review Remediation Candidate (2026-09-13)

The first frozen V2 runtime candidate at `531e4a80` passed its local gates but
all three independent reviews identified two confirmed P2 defects: fixed
configuration selected baseline/release bytes instead of the fenced candidate,
and numeric artifacts were not constrained to one configured signer and trust
policy. The test review also found unclosed SQLite fence connections and
insufficient frozen-vector proof. The candidate was not promoted.

The remediation makes fixed configuration own only coverage, gate and
sampling-frame manifests, trust keys, expected signer, and trust-policy digest.
After the repository lease selects the active release, the evaluator resolves
the candidate baseline/release against those fixed manifests and hashes the
exact V2-marked policy/evidence into its held binding. An installed successor
release therefore requires no numeric configuration edit. Mixed signer/policy
chains, unversioned or V1 policy/evidence, stale authority, and tampering fail
closed. SQLite fence calls now close connections on every return and exception.

The 13 registered authority vectors now contain valid deterministic Ed25519
digests/signatures. Their acceptance-independent checker verifies each
digest/signature and rejects a body mutation. A separate frozen signed V2
corpus exercises five gates, four cells, ten memberships, explicit unsupported
cells, non-uniform weighted clusters, exact-binomial and weighted-Hoeffding
methods, and a successor release through the installed wheel. CI regenerates
both frozen vector sets, rejects drift, and runs the isolated public wheel proof.

Local remediation evidence: 242 acceptance/wire tests pass with warnings as
errors; Ruff passes; explicit first-party Pyright reports zero errors; vector
generation/checking and diff checks pass; and the isolated wheel proof publishes
one signed receipt and deployment authorization while passing all 14 installed
negative cases. This remains a review candidate; R14 is partial until fresh
specification, correctness, and test reviews of the exact commit are reconciled.

## V2 Numeric Authority Cutover (in progress, 2026-09-12)

The authority registry now carries the five V2 artifacts and the V2 approval
release retains the existing release digest, epoch, sequence, predecessor,
issue/expiry, lifecycle, and signer fields. `acceptance.numeric_context_authority`
strictly reconstructs signed coverage dispositions, the full numeric authority,
and a preverified numeric certification context from the five manifest bytes.
The frozen signed fixture was reissued with the V2 lifecycle release. Focused
positive/tampered-signature proof passes. Host/evaluator/config and legacy
fixture migration remain required before this becomes a production cutover;
this evidence does not claim that the V2 runtime path is live.
