# Semantic Ingestion Engineering Closure Plan

Baseline: `191826cd3afb38bf605a337a71d576063b3bae5e`, PR #120.
Current status (2026-09-12): implementation active; 15 requirements retain
completed engineering behavior and 8 remain partial or unimplemented. This
table was rebuilt from production paths and the three-role closure review at
`4ff7f53c10092f423494fff55fbc055d2f3fdf4c`. That revision is clean, pushed,
and has no failed PR checks; its long-running Observation Ledger Activation
check is still pending. Release signing is not the only remaining work.
User-directed completion boundary: engineering
readiness must not wait for actual production signing. Runtime still rejects
unsigned, untrusted, expired or revoked activation material.

## Completion Labels

| Label | Required evidence | What it does not claim |
| --- | --- | --- |
| Engineering complete | Real owners and command paths implemented; every applicable SIA contract tested; independent algorithms and observed graphs verified; real cryptography exercised with isolated test keys; ordinary host roots integrated; exact-candidate CI/reviews pass; portable evidence and unsigned release assembly work | Production policy approval, issuance of real signatures, live capability approval |
| Release ready for approval | Final policy values, capability/dependency fingerprints, sampling/data identity, release sequence and trusted signers are explicitly supplied; unsigned artifacts and their dependency graph validate; acceptance measurements are reported without hidden defaults | Signatures or deployment permission |
| Release authorized | Required owners approve/sign exact bytes; production public-key/trust verification succeeds; required statistical evidence and exact-release acceptance pass | Blanket approval of later changed fingerprints |

Missing production signatures alone will not block engineering completion.
Missing signer/verifier code, public-key configuration, independent evaluator,
audit observer, monitor, or deterministic test proof WILL block it. Passing
synthetic data only proves those mechanisms: actual capability quality must be
measured with its predeclared policy/data before a release approval claim.
The original signed-activation design remains unchanged. Parent status should
ultimately read "engineering complete; release authorization pending" rather
than imply that unsigned artifacts authorize runtime use.

## What Exists And What Needs Signing Work

The original assessment below is retained as planning context. Concrete Ed25519
verification, configured trust resolution, PEM offline signing, release assembly,
lifecycle-signing tools, installed-wheel preparation and protected activation
now have deterministic and CI evidence. R13 remains partial because the complete
acceptance-authority/release integration and final trusted release are outstanding;
see the current table below and
[signing progress](../semantic_ingestion/engineering-closure/milestones/02-release-crypto-trust.plan.md).

The repository now has unsigned preparation, external-sign, assembly and verify
workflows. The final YubiKey-backed cloud-KMS adapter and trusted deployment
configuration remain release work. The historical inventory that follows
explains the seams from which that workflow was built.

At the refreshed candidate, the engineering closure review found three distinct
product-work packages still open: the acceptance-authority/evaluator entrypoint,
the scheduled capability monitor with atomic demotion, and the independent
structural comparator plus configured ingress/revocation negatives. These do not
require production private keys and must not be reclassified as signing work.

Historical baseline:

`semantic_ingestion_traceability_release.py:105` defines a SignatureVerifier
callback; verifier-held trust material supplies that callback and key/certificate
digests. `core/semantic_ingestion/capability.py:109` similarly declares a host
verification protocol. These are useful contract seams, not a PEM/public-key
loader or an end-to-end signing command. The `sign_record` helper in
`semantic_ingestion_execution_evidence.py:184` is explicitly legacy test HMAC
and is not accepted by the approval path. No shipped release/policy signing CLI
or concrete semantic-ingestion public-key adapter was found.

Engineering deliverables:

1. Extend the existing release/authority tool owners with prepare, external-sign,
   assemble and verify entrypoints. Reuse canonical digest/profile rules; do not
   invent a second serialization or sign ad-hoc JSON. Names/argv must be fixed
   in the implementation packet before code, and listed as unavailable until built.
2. Prepare unsigned typed policy/coverage/monitoring/deployment/release manifests
   plus a signing-request manifest. Each request states artifact, digest/preimage,
   signature profile, purpose, eligible signer/key ID, dependencies and output.
   Order dependent artifacts deterministically. Final content values must be
   supplied before these become the release's final signable bytes.
3. Add a concrete public-key/certificate verification adapter for the approved
   signature profile and configuration for trusted public keys/roots by purpose.
   The PKI/KMS/HSM integration supplies signatures; the repository never needs
   committed private keys. Choose the actual organization's backend/profile
   explicitly when implementing, without changing domain-signature semantics.
4. Wire the adapter through existing verifier-held trust and host composition.
   Request/candidate files cannot choose their own trusted public key. A valid
   signature is necessary but signer role, artifact purpose, binding, validity,
   revocation and monotonic release policy must also validate. Production trust
   roots remain independently provisioned, not self-authorized by the release.
5. Exercise the real crypto adapter with isolated disposable test keys and the
   external-signer interface. Test wrong key/purpose, altered bytes, unknown
   profile, expiry, revocation, rollback, rotation and signed round trips. Merely
   injecting a verifier returning True does not complete this work.
6. Supply a dry-run/preflight command that reports all missing final inputs and
   never turns unsigned manifests into active capabilities. Once final policy,
   identity and trust inputs are approved, issuing signatures should require
   operational configuration and signing actions, not product code changes.

A public-key file can support verification once this adapter is built and wired.
A raw key alone does not encode which policy/release it is authorized to approve.

## M0 Correction: Preserve Completed Engineering

The previous closure review overstated the M0 blocker by relying on the stale
parent packet. The later
`docs/work/semantic_ingestion/m0-canonical-genesis-structural-contract-implementation-2026-07-31/implementation.plan.md`
is explicitly complete (line 5). It records corrected genesis provenance,
canonical structural-manifest derivation, independent full-body/envelope/spool
proof, atomic publication/rollback, fixed composition-owned approval authority,
183 passing acceptance regressions and final reviews (lines 855-882).
It explicitly says operational activation inputs do not block deterministic
implementation. This is why progressing to M1-M4 was legitimate.

The older rejected C2 attempts exposed recursive typing/enum closure, closed
mutation/outcome matrices, preimage recomputation, independent derivation,
nested authority equality, an honest mutation denominator and stable gates.
Those rejected bytes remain rejected historical evidence. Their existence does
not prove those defects survive in the later corrected implementation.

Remaining engineering work here is a bounded current-evidence crosswalk and
coordination-status reconciliation: map the old blockers to the completed
replacement's current owners/gates, retain retired recipes as rejected, and
update the stale parent M0 summary through its WorkPlan split-manifest process.
If that audit identifies an actually uncovered obligation, repair that specific
obligation. Do not restart M0 or count absent real release signatures as missing
M0 implementation. Provider compatibility/protected results are already covered
by M1 and must retain their current behavior.

## Independent Statistical Acceptance

The purpose is to determine whether the exact capability meets a fixed quality
contract, using an evaluator that cannot inherit the ingestion implementation's
mistakes. The design's Section 5.6 already specifies the statistical machinery;
implement it rather than selecting new thresholds during coding.

Flow:

1. Freeze a coverage manifest: enabled and explicitly unsupported combinations
   of language, predicate/construction and behavior lane. List every required
   metric and the exact capability/dependency fingerprints.
2. Freeze the sampling frame, provenance-derived independent clusters, weights,
   missing-data handling, metric definitions and thresholds before observing
   held-out outcomes. Paraphrases/variants of one source or authoring seed are
   dependent evidence, not extra independent samples.
3. Run ordinary ingestion and obtain authenticated structural observations.
   Independently authored expected outcomes supply event-level correctness,
   false-promotion, missed-fact, unsupported-abstention and other declared labels.
4. A separate acceptance evaluator reconstructs clusters, denominators and
   metrics from raw evidence, not runtime counters. Per the governing design,
   exact-binomial applies only to proven IID cluster-any-failure; weighted
   Hoeffding covers the other bounded independent-cluster estimands; all primary
   claims use the declared Holm-Bonferroni family. Bootstrap diagnostics are not
   a substitute for the primary gates or independent implementation.
5. Emit every cell/metric result, cluster count, p-value/bound, adjusted alpha,
   threshold and pass/fail decision with exact input/version fingerprints.
   Missing evidence/cells, duplicated events or undefined denominators fail
   closed under the declared missing-data policy.

Engineering proof uses known finite examples, an independently authored
recomputation and isolated synthetic policy values. It must reject removed
cells, moved clusters, duplicate samples, altered weights/thresholds, partial
metric families and changed dependency fingerprints. Existing benchmark
calibration code is not automatically the new acceptance authority.

Actual thresholds, alpha allocation, minima and supported coverage require
explicit product/ML policy choices. They can be recorded as unsigned approved
inputs and evaluated before final signing; they cannot be guessed from runtime
traffic or selected after seeing held-out results. This plan does not assert
that a deterministic smoke pass is statistical certification.

## Authenticated Structural Observation And Comparison

The observer is a read-only audit API over a fixed graph/observation revision.
The new retrieval API returns useful selected context under a budget; acceptance
instead requires a complete, paginated view of every record in the authorized
operation cohort, including terminal operations that made zero graph changes.

Production observer responsibilities:

- Resolve trusted out-of-band caller authority before seed/cohort/index lookup.
  Request scope can narrow permission, never grant it.
- Derive server-owned cohort membership from canonical introduction/outcome and
  observation records; follow only allowed reference edges. Include required
  boundary records and exclude unrelated tenants, tasks and operations.
- Freeze graph/observation revision, cohort, view, time and page policy. Return
  one ordered `(record_kind, primary_key)` stream with a total page limit across
  kinds; every record appears exactly once.
- Bind the cursor to that snapshot/cohort/policy and reauthorize every page.
  Forged, stale, expired or revoked access returns the design's typed empty
  failure, without revealing identifiers, digests, cohort existence or pages.

Acceptance comparator responsibilities:

- Own the expected graph before ingestion, hidden from production. It may share
  public wire schemas, not production extraction/normalization/reconciliation,
  compiler, lineage repair or retrieval helpers used to derive expected results.
- Establish the unique global operation/fence bijection, then compare complete
  record sets, typed fields, references, scope, evidence, temporal values and
  terminal effect shapes. Generated-ID differences are handled only through the
  design's allowed alignment, not guessed aliases or semantic repair.
- Identify the first structural divergence; missing/extra/duplicated records,
  wrong polarity/time/provenance, absent zero-effect outcomes and ambiguous
  alignments fail. Correct retrieval text cannot compensate for a wrong graph.

Proof: ingest through actual factory/filesystem/Hermes roots, audit via the
public observer, then compare independently. Cover multiple principals/scopes,
pagination, concurrent revisions, revoked second page, forged cursor, omitted
caller/authorizer, missing/unexpected records and zero-mutation cases. A direct
store read in the harness is not proof that the authenticated API works.

## Ordered Engineering Work Packages

| Order | Work package | Exit criteria | SIA allocation |
| --- | --- | --- | --- |
| 1 | Evidence retention and M0 status reconciliation | Exact historical logs/snapshots portable; M0 corrected implementation crosswalk replaces stale blocker inference; existing gates retained | R03,R13,R22 |
| 2 | Release assembly, real crypto adapter and host trust configuration | Unsigned preparation and external-sign/verify paths work; test-key cryptographic round trips and lifecycle attacks pass; production unsigned/test-root activation denied | R03,R08,R13,R16,R19 |
| 3 | Independent statistical evaluator | Full frozen cell/metric coverage, independent recomputation and adversarial corpus pass; clear unsigned policy inputs and no fabricated quality claim | R14 |
| 4 | Capability monitor and atomic registry transitions | Fake-clock freshness/outage/breach/recovery, in-flight demotion races and explicit reactivation pass through production triggers | R15 plus R08,R16,R19 |
| 5 | Authenticated observer and independent structural comparator | Complete scoped snapshot pagination, unique fence alignment, no hidden helper/oracle dependencies, fault/auth tests pass | R17 plus R03,R13 |
| 6 | Real host composition and whole-program engineering closure | Host capability/ingress/verifiers/monitor/audit wiring through all roots; exact-candidate complete CI, portable receipts and fresh parent reviews | R08,R16,R19 and regression preservation of all 23 |

Orders 3 and 5 may develop in parallel after wire/authority inputs are frozen;
monitor integration depends on the policy/evidence and status contracts. Use one
writer per overlapping owner. Each packet must define exact files, typed
interfaces, migration/rollback, production triggers and its required checks
before implementation. This document does not create unsigned bypasses or an
alternative source of truth.

Engineering completion is separate from the release-signing checklist. Final
production signatures, real trust deployment and signed release authorization
are deferred by user direction. Required predeclared quality evaluation remains
visible and must precede any actual capability acceptance claim.

## All 23 Requirement Allocation

### Consolidated Completion Campaign (2026-09-08)

User objective: reduce the eight open requirements to fewer than three through
one coordinated production completion effort. Target all seven rows other than
R14 for engineering closure, and complete R14's engineering integration too;
retain R14 as open if independently qualifying policy/data measurements remain
unavailable. This is a target, not a status change or permission to weaken any
row's existing acceptance contract. Actual production signatures remain deferred.

The recent sequencing concentrated on R17/R19 components while the monitor and
whole-host packages stayed paused. Replace that sequencing with the dependency
order below. Commits remain incremental and reviewable, but a component commit
is not the stopping point for this campaign.

| Order | Complete production outcome | Requirements advanced | Exit evidence |
| --- | --- | --- | --- |
| 1 | Resolve acceptance issue-time/key-history ordering, bounded public byte entry and closed artifact shapes; resolve ingestion-time continuation coordinates through linked successor design operations | R14,R15,R16,R17 | Approved determinate contracts and executable boundary proof; preserve rejected design history and existing graph cursor bytes |
| 2A | Implement capability monitoring and atomic lifecycle/registry transitions using the completed authority/configuration path | R08,R15,R16,R19 | Production trigger handles freshness, outage, breach, demotion, in-flight races and explicit reactivation; deterministic clock/CAS evidence |
| 2B | Finish activated ledger failure paths, checkpoint authority, real detached scoped observation/retrieval, ingestion-time pagination and independent structural comparison | R03,R17,R19 | Ordinary provider APIs exercise every supported stream, scope isolation, authorization/revocation, pagination, restart, lost acknowledgement, contention and noncommitting outcomes; comparator detects incorrect structure independently |
| 3 | Assemble release/runtime configuration, complete bundle/profile validation and wire monitor, registry, ledger and observation owners through every supported host root | R08,R13,R16,R19 | Direct/factory/filesystem/Hermes, local/no-network and authorized-root matrix; installed release preparation/sign/verify with isolated test keys; invalid configuration fails closed |
| 4 | Assemble the held-context statistical evaluator/CLI and independent evaluation path | R14 | Approved authority checks precede independent numeric evaluation; complete policy/cell coverage, adversarial inputs and reproducible results; no invented thresholds or quality claims |
| 5 | Freeze one integrated candidate, regenerate all affected authority/package artifacts, run consolidated gates and independent whole-scope review, and publish portable evidence | R03 plus all eight | Exact candidate, host proof, CI identity, full regression/acceptance crosswalk and retained artifacts; every row closed against its own original criteria |

Workstreams2A and2B may overlap only after their respective contracts are ready
and file ownership is disjoint. A single writer owns shared provider, factory,
registry and atomic-store integration. Focused checks accompany risky changes;
the broad consolidated pass and three-role integrated review follow complete
production wiring. Confirmed corrections receive affected delta checks rather
than restarting every review after each component edit.

Requirement closure targets:

- R03: portable exact-candidate evidence and complete requirement/owner/gate map.
- R08: all supported host, local/no-network and authority-boundary behaviors.
- R13: complete configured release preparation/assembly/sign/verify integration;
  actual production keys and signatures remain release-only.
- R14: corrected authority, held-context evaluator and CLI; substantive approved
  policy/data and qualifying measurements remain explicit if unavailable.
- R15: live production monitor and atomic capability transition lifecycle.
- R16: complete bundle/profile verification on publication, activation and use.
- R17: durable ledger/checkpoint, authenticated scoped observation/retrieval and
  independent structural comparison, including failure families.
- R19: all these owners reached through ordinary supported host composition.

Progress reporting must name rows closed, concrete production behavior added,
and exact remaining blockers. Do not count test totals or helper approvals as
row closure. Intermediate expected count remains8 while shared implementation
is underway; the integrated acceptance pass targets0-2 open, ideally only R14's
external quality evidence. If more than two rows still lack required evidence,
report the target missed and continue the authorized engineering work; do not
relabel partial work to meet the count.

Exactly one campaign next action: create the linked bounded successor design
packets for acceptance authority and ingestion-time continuation, mapping each
existing rejection to a determinate contract and proof before implementation.

Updated 2026-09-08 against the implementation packets and recorded local
evidence at baseline `8785d9f3a2bb237e579da1242efbd0c8be31d7e2` plus the authorized
working-tree changes. These are engineering progress labels, not release or
final-candidate approval:

- **Baseline complete (15):** completed M0-M4 behavior is retained; no new
  implementation gap is currently assigned to that row. Every row still needs
  its applicable final-candidate regression/authority gates and review.
- **Partial (6):** some relevant implementation/evidence exists, but the full
  requirement is unfinished.
- **Blocked (1):** R14's acceptance-authority design reached its recorded
  conformance limit. Its approved numeric component remains complete.
- **Not implemented (1):** R15's production monitoring/transition work remains.

**Eight requirements remain open: R03, R08, R13, R14, R15, R16, R17 and R19.**
This is not a 15/23 final engineering-approval claim. Production signing alone
does not block any engineering status here. Quality measurement and final
candidate proof remain separate obligations.

Current R17/R19 construction progress: complete-prefix replay has14 passing
focused cases; native group audit construction passes a real provider-commit
case; schema-3 source reload retains and reconstructs its sealed request;
registered cursor emission verifies with a separate public key. The two
snapshot missing-member rejection cases pass. The expanded integration gate
passes52 cases, including registered native-evidence and graph-paging
construction. Exact group-recovery entry joins also pass2 isolated regressions. The paging fixture verifies contiguous pages, reauthorization,
changed-scope rejection and intervening-write invalidation. These remain bounded
local checks. The current production round replaces the blanket activated-write
rejection with closed transaction validation and canonical detached replay,
shares protected reader limits, fixes strict JSON terminal recovery, and aligns
schema-3 source outcomes with committed group result digests. The actual provider
now passes two-source ingestion, four durable group/source ledger entries, JSONL
reopen and acknowledged retry under the later head without duplicate entries
(1 test,1269.55s). The consolidated suite passes281 tests1108.52s; the separate
compatibility delta passes160 tests69.31s. Four legacy-route rejection cases,
two limit-consistency cases, the lease-expiry guard,58 regenerated registry
vectors, lint, type and identity checks pass. Code/spec reviews found no further
concrete defect. Activated public lost-acknowledgement, contention, authorization
failure and noncommitting-outcome proofs remain required before append/replay
approval; acknowledged retry is not lost-acknowledgement proof.
Public retrieval and provider composition remain incomplete. Detached authority
and cohort membership are locally verified at6029030d; registered graph/time
paging now has the approved separate cursor coordinates. The concrete materializer,
persisted time-attestation producer and successful public retrieval proof remain.
The owner approved complete retained policy context on 2026-09-08. Its
corrected recipe is canonically promoted after13 passing checks and three
independent approvals; the policy-choice/design blocker is resolved.
No requirement row is promoted
to complete by this production write/recovery checkpoint. Current details and evidence are in
`../semantic_ingestion/observation-ledger/milestones/append-replay.plan.md`.

| ID | Current status | Completed or locally verified work | Remaining engineering work | Release-only condition |
| --- | --- | --- | --- | --- |
| R01 | Engineering complete | Source retention, provenance and admission owners retain their M1 proof and current unit/acceptance gates pass | Parent closure record only | Deployment-wide authorization |
| R02 | Engineering complete | Candidate, semantic validation and commit paths retain M3 proof; current scenario and transaction gates pass | Parent closure record only | Capability activation approval |
| R03 | Partial | M0 crosswalk and historical evidence are retained; release preparation is restricted to tracked members; current provider observation supplies portable structural evidence | Freeze the eventual post-remediation candidate and publish the final owner/gate/evidence package | Signed real release/evidence approval |
| R04 | Engineering complete | Typed evidence ownership and terminal-chain validation retain M1/M3 proof under current gates | Parent closure record only | None distinct |
| R05 | Engineering complete | Semantic evidence validation and required metric inputs are retained | R14 must consume these metrics before release approval; no additional R05 production code identified | Approved capability quality evidence |
| R06 | Engineering complete | Temporal construction/decision matrix and exact replay remain covered | R14 must consume these metrics before release approval; no additional R06 production code identified | Approved capability quality evidence |
| R07 | Engineering complete | Registered prompt, redaction and fingerprint bindings pass the current authority/generation gates | Parent closure record only | Approval of changed fingerprints if applicable |
| R08 | Partial | Built-in local/no-network profile, protected activation, configured trust, installed-wheel bootstrap and provider observation composition are implemented and CI exercised | Implement monitor/status integration and configured host-ingress rejection/revocation proof across supported roots | Real trusted deployment artifacts |
| R09 | Engineering complete | Current-policy egress authorization and negative paths remain covered | Parent closure record only | Real remote policy only if enabled |
| R10 | Engineering complete | Exact event, graph and replay authority retain M2/M4 proof; current persistence shards pass | Parent closure record only | None distinct |
| R11 | Engineering complete | Single-writer, cutover, retry, restart and rollback behavior remain covered | Parent closure record only | Activation/migration authorization if used |
| R12 | Engineering complete | Temporal/lifecycle contracts and current projection-history gates pass | Parent closure record only | None distinct |
| R13 | Partial | Ed25519 verification, configured resolver, PEM external signing, release/lifecycle assembly, installed preparation, protected target validation and test-key tamper matrix are implemented | Complete acceptance-authority/evaluator-to-deployment binding, final host/release evidence and cloud-KMS signer adapter selected for the release | Actual trusted keys, signatures and monotonic release publication |
| R14 | Partial | Independent arithmetic/CTV evaluator passes 81 focused tests and 33 independent vectors; issuance-prefix design correction passes 103 checks | Promote the acceptance-authority contract; ship an installed evaluator/CLI with protected held context and verified-result publication; run the complete approved policy/data evaluation | Product policy approval/signature and qualifying measurements |
| R15 | Not implemented | Readiness, authority preflight and deterministic validation matrix exist | Implement the scheduled production monitor, immutable evidence-window evaluation, atomic registry/status CAS demotion, zero-traffic freshness, outage/breach handling, restart and explicit reactivation | Approved monitoring policy and real evidence windows |
| R16 | Partial | Bootstrap topology, 181-schema/1269-role registered publication, native policy retention, installed package preparation and protected target activation are implemented | Bind the monitor/status owner across activation and use; close the configured ingress/root matrix and final package evidence | Approve/sign final bundle fingerprints |
| R17 | Partial | All 17 graph observation families, registered projection identity reconstruction, event-derived intervals, scoped pagination, durable ingestion-time seals and public ProviderMemoryService methods are implemented; real activated JSONL composition and CI exercise the path | Add an independently authored closed-world structural comparator through the paginated public API; prove missing/extra/time/provenance/fence mutations and configured host-ingress rejection plus between-page revocation | Real caller trust and acceptance witnesses |
| R18 | Engineering complete | Historical/conflict/lineage replay retains M4 proof and current projection-history gates pass | Parent closure record only | None distinct |
| R19 | Partial | Normal provider roots reach protected registry/target activation, atomic ledger writes/recovery, all 17 observations and ingestion-time attestations; installed package and host composition are CI exercised | Integrate monitor/status checks into every normal root and add meaningful configured ingress/revocation negatives; then refresh the caller ledger | Install approved real host configuration |
| R20 | Engineering complete | Lease, retry, recovery and exhaustion behavior remain covered by current persistence/transaction gates | Parent closure record only | None distinct |
| R21 | Engineering complete | Crash-atomic generation and backend behavior remain covered | Parent closure record only | None distinct |
| R22 | Engineering complete | Provider compatibility and protected-result behavior pass current recapture/scenario gates; stale M0 inference is reconciled | Parent closure record only | None distinct |
| R23 | Engineering complete | Delivery normalization, duplicate/redelivery rejection and composite replay pass current scenario gates, including substituted-redelivery rejection | Parent closure record only | None distinct |

Evidence and live work owners:

- [Retained M0-M4 proof crosswalk](../semantic_ingestion/engineering-closure/milestones/01-evidence-m0-reconciliation.plan.md).
- [Signing/trust evidence](../semantic_ingestion/engineering-closure/milestones/02-release-crypto-trust.plan.md) and [current signing evidence hashes](../semantic_ingestion/engineering-closure/signing-local-evidence.json).
- [R14 numeric approval and remaining authority blocker](../semantic_ingestion/engineering-closure/milestones/03-independent-statistical-evaluator.plan.md).
- [Monitor work](../semantic_ingestion/engineering-closure/milestones/04-monitor-registry-transitions.plan.md).
- [Registry publication work](../semantic_ingestion/registry-publication/implementation.plan.md): the current publication contains 181 schemas and 1269 roles, includes ProjectionObservationIdentity and ingestion-time attestation roots, has independent normalized-output/vector evidence, is composed by the protected host runtime, and is exercised by the current generation and package gates.
- [Observer/comparator work](../semantic_ingestion/engineering-closure/milestones/05-authenticated-observer-comparator.plan.md) and [final host/whole-program closure](../semantic_ingestion/engineering-closure/milestones/06-host-composition-closure.plan.md).

Registry history and native decoders now have completed service integration.
That does not supply R15's capability monitor or R17's independent comparator.
The parent closure package remains open until the remaining product work lands
and its exact candidate completes CI and independent review.

## Evidence Repair And PR State

Implemented locally in this planning task: narrow `.gitignore` exceptions for
49existing immutable logs; `evidence-retention.json`; exact archived review
metadata; and `verify_retained_evidence.py`. A clean export of 191826c overlaid
only with the proposed packaging changes verifies 152 reviewed files and 21 source
files. Altered/missing logs fail; restored bytes pass. Historical bytes/status
were not rewritten. See evidence-retention-checks.json. Packaging changes still
need commit/push to become available in PR checkout; no new commit is claimed.

PR #120 is open at `4ff7f53c10092f423494fff55fbc055d2f3fdf4c`.
At the 2026-09-12 refresh, every reported check has succeeded except the still
running Observation Ledger Activation job; no failure is present. The earlier
fully green run at `4e524f31` proves the preceding source candidate, not this
documentation head or a future remediation candidate.

## Handoff And Limits

This plan resolves the requested engineering-versus-signing scope. It does not
claim that M5 coding, final statistical thresholds/data, or real PKI choice are
already supplied. The first implementation packet should name the signing
backend/public-key profile and the existing canonical extension owners, freeze
M0 crosswalk/authority inputs, and establish engineering acceptance independently
from release issuance. No completed milestone is reopened solely for signatures.

## Public Observation Resumption Checkpoint

The additive timed snapshot, structural-field design, registered projection
identity, complete materializer, public provider methods and persisted
ingestion-time attestations are implemented. R17 remains partial solely for the
independent comparator and configured authorization/revocation proof described
in the table. R19 remains partial for those host negatives and the missing
monitor/status integration. The refreshed count remains 15 engineering-complete
and 8 partial/unimplemented; the remaining engineering work is explicit and is
not collapsed into deferred production signing.

## Evidence Progress Record (2026-09-12, PR #120 green at 4e524f31)

No open row is closed by this record; it captures evidence now held so the
next campaign step plans from reality. The eight-open count is unchanged.

- R17 (observation/retrieval): the public construction is complete and
  CI-enforced — all 17 stream families produced through the registered
  materializer (event-derived system intervals, boundary records, sibling
  arms, projection records with derived identities), scoped authenticated
  paging with non-disclosing denials, ingestion-time attestations minted at
  CAS and paged end-to-end (campaign M0-M3). REMAINING for the row: the
  independent structural comparator (not implemented; no production module),
  whole-branch review, and the frozen-candidate gate record.
- R19 (host composition): ProviderMemoryService public methods + factory
  pass-through proven on the real activated backend; Observation Ledger
  Activation job green in CI. REMAINING: the full host matrix breadth
  (filesystem/factory/Hermes, local/no-network, authorized roots).
- R03 (portable evidence): first fully green PR-gates run (34712825249),
  installed proof against a prepared deployment, git-tracked-only candidate
  manifest. REMAINING: complete requirement/owner/gate map and portable
  receipts at the frozen candidate.
- R13/R16 (release crypto/bundle verification): offline sign/verify chain,
  four-artifact flow and release-preparation proof remain CI-green; owner
  adopted Option B Tier-1 (FIDO-hardened cloud-KMS signing) — wiring awaits
  owner provisioning inputs (cloud, key alias, environment, officers).
  REMAINING: configured release assembly, bundle/profile verification on
  publication/activation, real signatures (deferred, now scheduled via
  Tier-1).
- R14 (statistical evaluator): unchanged — evaluator/CLI integration and the
  acceptance-authority successor decision remain open.
- R15 (monitor): unchanged — not implemented.
- R08 (host behaviors): unchanged beyond the factory/service observation
  path; matrix breadth open.

Sequencing note: the monitor (R15) and comparator (R17 leg) are the two
largest unbuilt production components; both were queued behind the contracts
this campaign has now delivered.
