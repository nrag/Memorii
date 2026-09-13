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

Freeze the implemented Stage 1 candidate and run the required independent spec,
correctness, and test reviews. Reconcile and remediate every confirmed finding
before promoting R14.

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
