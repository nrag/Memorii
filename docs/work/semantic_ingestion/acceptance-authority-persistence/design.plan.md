# Acceptance Authority Persistence And Runtime Bootstrap

- Work ID: semantic_ingestion/acceptance-authority-persistence
- Work type: design
- Status: complete
- Coordinator: root
- Created: 2026-09-12
- Last updated: 2026-09-12
- Parent WorkPlan: `../engineering-closure/implementation.plan.md`
- Related WorkPlans: `../acceptance-authority-successor/design.plan.md`, `../acceptance-issuance-prefix/design.plan.md`, `../statistical-acceptance/design.plan.md`
- Canonical inputs: `../../../design/semantic_ingestion_architecture.md`, the accepted authority-successor and issuance-prefix proposals, repository publication persistence, and the Stage 1 implementation preflight
- Expected outputs: `proposal.md`, feasibility evidence, frozen candidate identity, and independent design reviews

## Objective

Define the remaining persisted and composition-root contracts needed for the
installed acceptance evaluator to reconstruct protected authority after a
restart, publish immutable results, and pass only verified digests across the
production boundary. The result must let Stage 1 implementation resume without
inventing a wire shape, transaction rule, bootstrap authority, or recovery rule.

## Completion Contract

The design is complete when the proposal defines closed registered artifact
families, canonical encoding and digest ownership, atomic publication and CAS
semantics, restart and interruption behavior, installed runtime composition,
authority-chain promotion, migration and rollback, identity hygiene, and a
family-complete verification matrix. Repository evidence must establish the
chosen persistence and entry-point mechanisms are feasible. A frozen candidate
must receive spec, correctness, and test review with no unresolved
`blocks_approval` or `changes_required` finding and no validated P1/P2 defect.

## Problem Definition

The accepted authority designs define verification semantics but deliberately
leave production persistence, registered schema promotion, and the configured
evaluator runtime unimplemented. The current Stage 1 candidate can evaluate
with an in-memory repository and injected test runtime, but cannot reconstruct
protected authority from durable bytes through the installed command. Treating
its Python dataclasses or test fixtures as authority would leave rollback,
restart, and caller-injection gaps in the release gate.

## Requirements Ledger

| ID | Requirement | Source | Priority | Acceptance criteria | Status |
| --- | --- | --- | --- | --- | --- |
| AP-01 | Every acceptance authority and receipt artifact has one closed registered canonical-map schema, profile binding, purpose, digest domain, and bounded decoder. | SIA 5.6; authority successor; issuance prefix | Required | Complete artifact inventory and field-level mutation matrix are explicit. | specified |
| AP-02 | Issuance publishes the immutable snapshot and approval release as one committed pair conditional on exact key-history head and status generation. | Issuance-prefix atomic capture | Required | Stale CAS exposes neither member; exact retry is idempotent. | specified |
| AP-03 | Key, release, checkpoint, production-revocation, and evaluation-receipt histories survive restart and reject truncation, fork, substitution, and torn publication. | SIA lifecycle; authority successor | Required | Durable owner, recovery algorithm, and terminal outcomes are explicit. | specified |
| AP-04 | The current checkpoint advances with an external monotonic fence and cannot make uncommitted prepared objects authoritative. | SIA fail-closed currentness; repository precedent | Required | Crash points before/after object, index, and fence writes have deterministic recovery. | specified |
| AP-05 | The installed evaluator obtains exactly one host-owned immutable configuration and exposes no CLI or environment override for trust, histories, limits, policies, clocks, or issuers. | SIA one-way boundary; Stage 1 test review | Required | Real installed entry point composes the durable repository and rejects zero/multiple/invalid providers. | specified |
| AP-06 | Acceptance and production remain separate packages joined only by canonical deployment-authorization bytes and verified digests. | SIA 5.1 and deployment authorization | Required | Static/import and cross-decoder tests prove both directions. | specified |
| AP-07 | Registry source, generated authority, frozen vectors, checksums, workflow pins, and CI gates advance as one reviewed authority chain. | build-design; issuance-prefix promotion | Required | Every downstream node and regeneration/validation owner is named. | specified |
| AP-08 | Existing unregistered or incomplete artifacts never become current through migration or fallback. | issuance-prefix compatibility | Required | Inventory classifies legacy/mixed/corrupt state; migration requires reissuance. | specified |

Requirement IDs are documentation-only traceability coordinates and must not
appear in persisted bytes, public symbols, filenames outside this WorkPlan, CLI
names, runtime errors, registry identities, or workflow names.

## Scope

Included: acceptance-only authority persistence and decoding; immutable result
receipt persistence; the protected installed runtime bootstrap; production
revocation-receipt input; canonical registry and CI promotion; recovery,
migration, and verification.

Excluded: substantive policy values, real keys or signatures, qualifying live
measurements, ordinary provider activation consumption, monitoring, public
observation/comparison, and changes to production semantic arithmetic.

## Constraints And Invariants

- Preserve the canonical SIA release and verified-approval fields.
- Preserve the accepted complete issuance prefix and separate current-history
  reduction; timestamps do not reconstruct an issuance prefix.
- Acceptance imports no production semantic, routing, reconciliation,
  persistence, or arithmetic helper. Production imports no acceptance module.
- A prepared file is not authority. Only an externally fenced commit is current.
- Protected configuration may narrow signed/parser ceilings; artifact bytes
  cannot expand them.
- Missing, ambiguous, corrupt, stale, unsupported, or unavailable state fails
  before receipt or deployment publication.

## Existing-System Analysis And Feasibility

- `memorii.tools.semantic_ingestion_release_persistence` already proves the
  required content-addressed object, replaceable current index, append-only
  external fence, exact retry, restart recovery, and torn-write model.
- `acceptance.cli` and its installed-wheel test prove Python entry-point
  discovery can require exactly one runtime without exposing authority flags.
- `acceptance.ctv` and the accepted numeric work prove a separate acceptance
  canonical encoder can operate without importing production codecs.
- The remaining feasibility work is to enumerate the registry promotion chain
  and confirm the publication primitive can atomically select a multi-object
  acceptance transaction without weakening its external-fence invariant.

## Identity Ledger

| Surface | Identity | Class | Behavioral meaning | Disposition | Proof |
| --- | --- | --- | --- | --- | --- |
| persisted artifact | `AcceptanceTrustSnapshot` | behavioral | immutable static acceptance key declarations | retain from authority design | closed schema tests |
| persisted artifact | `KeyLifecycleEvent` | behavioral | one ordered acceptance key transition | retain | reduction and mutation tests |
| persisted artifact | `AcceptanceApprovalIssuanceSnapshot` | behavioral | exact release-time key-history prefix | retain | prefix tests |
| persisted artifact | `CapabilityBaselineApprovalRelease` | behavioral | signed baseline approval lifecycle record | retain canonical SIA name | release tests |
| persisted artifact | `AcceptanceCurrentCheckpoint` | behavioral | protected selected release/key heads and revocation receipts | clarify predecessor name | recovery tests |
| persisted artifact | `ProductionRevocationReceipt` | behavioral | durable production epoch advancement proof | retain | ordering tests |
| persisted artifact | `ProductionEpochCheckpoint` | behavioral | signed current production epoch proof retained with a revocation receipt | new | currentness/restart tests |
| persisted artifact | `AcceptanceEvaluationReceipt` | behavioral | immutable verified evaluation/deployment publication binding | clarify current generic name | retry/restart tests |
| persisted artifact | `AcceptanceAuthorityCommit` | behavioral | externally fenced transaction selecting a complete authority state | new | crash matrix |
| entry-point group | `memorii.acceptance_evaluator_runtime` | protocol | exactly one installed host composition provider | retain current candidate | isolated install tests |
| command | `memorii-acceptance-evaluate` | behavioral | evaluate protected acceptance inputs and publish result | retain current candidate | installed command test |
| provider | `InstalledAcceptanceRuntime` | behavioral | standard fail-closed platform configuration owner | new | installed success/removal tests |
| configuration | `runtime-v1.json` under the platform data directory | protocol | protected evaluator resource bindings | new versioned configuration | permission/injection tests |
| persistence port | `AcceptanceAuthorityFence` | behavioral | independent linearizable current-commit authority | new | concurrency/restart tests |
| persistence adapter | `SqliteAcceptanceAuthorityFence` | behavioral | standard separately managed durable fence | new | full-durability and registration tests |
| integration port | `ProductionRevocationEvidenceReader` | behavioral | serialized receipt and current production epoch evidence | new | signature/currentness tests |
| coordinator | `AcceptancePublicationCoordinator` | behavioral | serialize lifecycle commit and deployment publication | new | race and recovery tests |
| internal capability | `AcceptanceEvaluationSnapshot` | behavioral | bind one trusted time and authority commit under the evaluation lease | new, nonpersisted | handoff/race mutation tests |

## Changed-Surface And Authority-Chain Ledger

This linked design operation owns this directory, the compact parent
status/link, and the new canonical subsection in
`docs/design/semantic_ingestion_architecture.md`. The existing dirty Stage 1
code remains a paused implementation candidate and is not design evidence
beyond feasibility.

Authority chain to specify: canonical SIA and accepted amendments -> acceptance
schema source -> generated schema/profile authority -> independent canonical
vectors -> runtime decoders -> durable repository/bootstrap -> package manifest
-> installed-command integration -> workflow pins -> aggregate PR gate.

## Verification And Attack Model

The proposal must cover every field omission/addition/type/enum mutation;
duplicate keys; map-order and Unicode boundaries; byte/depth/node/string/integer
ceilings; digest/signature substitution; history gap/fork/reorder/truncation;
equal-time event order; stale CAS; concurrent issuers; prepared-only debris;
failure before/after object, index, fence, and directory fsync; lost
acknowledgement; exact and conflicting retry; restart; legacy/mixed/corrupt
inventory; zero/multiple/invalid entry points; configuration/environment
injection; receipt collision; production-revocation ordering; and both forbidden
import directions.

Deterministic local tests establish implementation invariants. Installed-wheel
and workflow tests establish packaging and CI execution. None supplies external
policy approval, real signatures, qualifying measurements, or release
certification.

## Alternatives Considered

1. Reuse the existing content-addressed publication plus independent monotonic
   fence. Accepted because its interruption and recovery semantics already have
   direct repository evidence and it keeps prepared objects non-authoritative.
2. Store independent JSONL files and infer the latest valid state on startup.
   Rejected because independently durable files cannot prove atomic issuance or
   prevent a coherent older prefix from becoming current after truncation.
3. Use a database-specific transaction implementation as the normative model.
   Rejected because Memorii must remain backend-neutral; a storage adapter may
   provide the same compare-and-publish contract later.
4. Let callers pass a configuration file or runtime factory path to the CLI.
   Rejected because it turns trust roots, histories, limits, and issuers into
   caller-controlled evaluation inputs.

## Failure And Operational Analysis

All failures return a non-success exit with no new current checkpoint or visible
deployment authorization. Failures before durable receipt publication create
no receipt; an indeterminate or failed production publication may leave the
signed evaluation-only receipt for exact reconciliation, but it is never an
activation-success signal and the command emits no success digest. Prepared
content-addressed debris may be garbage-collected only after proving it is not
named by any committed fence record. Rollback creates a later signed/fenced
transition; it never rewrites history or decrements an epoch. Backup/restore
must restore object history, current index, and independent fence together;
otherwise startup reports unavailable rather than selecting a best effort tail.

## Evidence Maturity

The trust and lifecycle semantics are specified and their bounded models are
locally verified. The Stage 1 evaluator and installed entry-point mechanism are
implemented in a dirty candidate and locally verified. Durable acceptance
repository, registered schemas, generated authority, configured host runtime,
CI enforcement, operational keys, and release evidence remain unimplemented.

## Initial Review Reconciliation

- Spec DREV-001 is confirmed as `Not applicable / changes_required / runtime
  integration`; its P1 label is rejected because the reviewed unit is an
  unimplemented design and the dirty command is not released. The correction
  names the standard installed provider, fixed configuration source, and real
  installed-path proof.
- Spec DREV-002 is confirmed as `P2 / changes_required /
  transaction-lifecycle integration`. The correction replaces an undefined
  cross-boundary CAS with an acceptance-owned exclusive publication
  coordinator, exact retry/reconciliation, and lifecycle serialization.
- Spec DREV-003 is confirmed as `Not applicable / changes_required /
  persisted-contract authority`. The complete normative contract is promoted
  into the canonical SIA architecture before implementation resumes.
- Correctness DREV-001 is confirmed as `Not applicable / changes_required /
  architecture-operability`. The correction defines the fence protocol,
  registration, namespace, failure domain, credential source, standard SQLite
  adapter, and fail-closed outcomes; the existing file fence remains test-only.
- Correctness DREV-002 is confirmed as `P2 / changes_required /
  security-transaction consistency`. The correction defines the serialized
  production receipt/current-epoch evidence reader and independent acceptance
  verification under protected production trust.
- Correctness DREV-003 is confirmed as `Not applicable / changes_required /
  integration conformance`; its P2 label is rejected because the bypass is in
  an uncommitted test-oriented candidate. The public CLI callable must remove
  evaluator injection and tests must use installed discovery.
- Correctness DREV-004 is confirmed as `P2 / changes_required /
  security-transaction consistency`. The artifact family now includes the
  signed `ProductionEpochCheckpoint`; every acknowledged revocation persists
  the exact receipt/checkpoint digest pair for restart validation.
- Test TREV-001 is confirmed as `Not applicable / changes_required /
  verification governance`. The design fixes the job, aggregate, selectors,
  timeout, standard-provider subprocess path, and workflow mutations.
- Test TREV-002 is confirmed as `P2 / changes_required / transaction
  verification`. Receipt publication now uses a locked temporary-file write,
  durable atomic final visibility, and every interruption boundary in the
  matrix.
- Test TREV-003 is confirmed as `P2 / changes_required / compatibility
  verification`. The explicit inventory and rollback matrix covers the full
  family before and after restart.
- Final correctness DREV-005 is confirmed as `Not applicable /
  changes_required / identity governance`. The identity ledger now contains
  `ProductionEpochCheckpoint`, and both persisted inventory rows name exact
  receipt/checkpoint pairs.
- Final spec DREV-005 is confirmed as `P2 / changes_required /
  transaction-lifecycle integration`. `AcceptanceEvaluationSnapshot` now binds
  the trusted instant, checkpoint, commit, and exclusive lease through
  verification, receipt construction, retry, and publication.
- Final spec DREV-006 is confirmed as `P2 / changes_required /
  transaction-lifecycle behavior`. Snapshot creation now reads the selected
  checkpoint and samples time without publishing authority. The canonical
  design explicitly supersedes the predecessor model's equality rule and the
  matrix requires an unchanged commit/checkpoint/fence for every rejection and
  partial failure.
- Final correctness DREV-006 is resolved by the same correction: no checkpoint
  is signed during evaluation, so no new status-signing authority is required
  on the normal evaluator path.
- Final correctness DREV-007 is confirmed as `Not applicable /
  changes_required / transaction-lifecycle architecture`. The coordinator now
  retains the snapshot's already-held lease through revalidation and
  publication and releases it only after confirmed publication or reconciled
  terminal failure; it never reacquires the lease.

All twelve findings, including the R14 ledger correction, are addressed in two
contract-level corrections. A final candidate and whole-design review are
required; no earlier approval survives the canonical design changes.

## Completion

Candidate `candidate-approval-v3.json` has SHA-256
`b67f996ef7f3988a9c75045e996e0eaec97f45ec71fd75f8d13a20491811bb09`.
Spec and test reviewers approved the preceding whole-design candidate with all
remaining arrays empty. The final bounded lease correction changed no schema,
identity, verification family, or requirement; the correctness reviewer
verified the v3 hashes and approved DREV-007 with all remaining arrays empty.
No unresolved validated design defect, governance change, or external semantic
decision remains within this slice.

## Next Action

Resume the parent Stage 1 implementation and implement this approved contract.
