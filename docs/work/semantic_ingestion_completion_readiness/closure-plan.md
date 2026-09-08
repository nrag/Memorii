# Semantic Ingestion Engineering Closure Plan

Baseline: `191826cd3afb38bf605a337a71d576063b3bae5e`, PR #120.
Current status (2026-09-08): implementation active; 15 requirements retain
completed baseline behavior and 8 still have engineering work open. The current
dirty-tree candidate has not completed final CI and whole-branch review.
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

The following assessment describes the original planning baseline. Concrete
Ed25519 verification, configured trust resolution, PEM offline signing, release
assembly and lifecycle-signing tools now have local test evidence. R13 remains
partial because complete host configuration/integration and final candidate
proof are outstanding; see the current table below and
[signing progress](../semantic_ingestion/engineering-closure/milestones/02-release-crypto-trust.plan.md).

The current repository is not yet a ready-made "sign a few files" workflow.
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

Updated 2026-09-08 against the implementation packets and recorded local
evidence at HEAD `191826cd3afb38bf605a337a71d576063b3bae5e` plus the authorized
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
local checks: activated writer admission and actual ledger transactions,
production retrieval/cohort selection and provider composition are outstanding.
Ingestion-time continuation also requires a design correction because the
shared cursor requires graph-only coordinates absent from that API.
No requirement row is promoted
by these helper and compatibility results. Current details and evidence are in
`../semantic_ingestion/observation-ledger/milestones/append-replay.plan.md`.

| ID | Current status | Completed or locally verified work | Remaining engineering work | Release-only condition |
| --- | --- | --- | --- | --- |
| R01 | Baseline complete | M1 source/provenance/admission proof retained | Final candidate regression only | Deployment-wide authorization |
| R02 | Baseline complete | M3 candidate/validation/commit proof retained | Final candidate regression only | Capability activation approval |
| R03 | Partial | Corrected M0 crosswalk, historical evidence retention, coordination-identity repair | Freeze current evidence/source identities; finish owner/verification crosswalk, portable final package and review | Signed real release/evidence approval |
| R04 | Baseline complete | M1/M3 typed owner and terminal-chain proof retained | Final candidate regression only | None distinct |
| R05 | Baseline complete | M3 semantic evidence validation retained | Final regression; include semantic metrics in the still-open R14 evaluation | Approved capability quality evidence |
| R06 | Baseline complete | M3 temporal matrix retained | Final regression; include temporal metrics in the still-open R14 evaluation | Approved capability quality evidence |
| R07 | Baseline complete | Registered prompt/redaction bindings retained | Final fingerprint/regression checks | Approval of changed fingerprints if applicable |
| R08 | Partial | Existing host boundaries and locally tested crypto/trust primitives retained | Finish real host/local/no-network/authorized-root matrix and monitor/registry integration | Real trusted deployment artifacts |
| R09 | Baseline complete | Current-policy egress authorization and retained negative proof | Final policy-rotation/regression checks | Real remote policy only if enabled |
| R10 | Baseline complete | M2/M4 exact event/replay proof retained | Final candidate regression only | None distinct |
| R11 | Baseline complete | Single-writer, cutover and rollback proof retained | Final candidate regression only | Activation/migration authorization if used |
| R12 | Baseline complete | Closed temporal/lifecycle contract proof retained | Final candidate regression only | None distinct |
| R13 | Partial | Ed25519/public-key verification, configured resolver, PEM offline signing, release assembly and lifecycle signing locally tested; offline wheel preparation, pinned bootstrap launcher and unsigned target/signature flow exercised on 21 installed distributions | Complete remaining release runtime/host configuration, remaining assembly integration, portable final evidence and independent closure | Actual trusted keys, signatures and monotonic release publication |
| R14 | Blocked | Independent numeric evaluator/kernel port approved; 81 tests and 33 independent vectors recorded | Resolve acceptance-authority issue-time, bounded byte-entry and closed-shape design; finish held-context/CLI assembly and full policy/data evaluation | Actual product policy approval/signature and qualifying measurements |
| R15 | Not implemented | Monitor readiness and validation matrix documented | Implement production monitor, atomic registry/CAS transitions, freshness/outage/breach/recovery and in-flight demotion/reactivation proof | Approved monitoring policy and real evidence windows |
| R16 | Partial | Bootstrap topology retained; bounded native policy retention independently approved | Integrate and prove complete bundle/profile validation through the new registry, activation and host paths | Approve/sign final bundle fingerprints |
| R17 | Partial | Full-write snapshot primitive approved; observation models, source declarations, body/native codecs and registry history locally tested; 58 independent construction vectors and full 179-entry output agree; protected reader locally tested; host/provider/writer/store registry composition passes five focused tests; native candidate encoding has independent byte-oracle proof; registered ordinary/self-digest/cursor integrity and protected reader pass 91 tests; fixed checkpoint preimage/crypto passes five tests; both slices independently approved; target-identity design approved; protected target helpers and selected registry cases pass 54 tests; four actual provider target/authorization cases pass;14 fresh-process bootstrap checks pass; five provider recovery failures corrected and rerun green; independently reviewed offline preparation verifies 5632 files and prepares/resolves a 1772-file signed test target; six authority and five installed tampering checks reject; full preparation CI is wired but unobserved | Durable activation has 24 passing integration cases and bounded spec/correctness/test approval, including concurrency, restart and historical-byte preservation; exact ledger hash-preimage amendment accepted and promoted; finish its runtime integration, refresh final packaging and obtain CI evidence; finish checkpoint external-context authority and registry integration, ledger/group CAS, public authenticated pagination/retrieval, independent comparator and end-to-end proofs | Real caller trust and acceptance witnesses |
| R18 | Baseline complete | M4 historical/conflict/lineage replay proof retained | Final candidate regression only | None distinct |
| R19 | Partial | Existing capability/ingress seams, configured trust resolver and bounded storage/policy prerequisites | Complete ordinary host composition for verified registry, writer/store, monitor, replay and observation APIs; run all host-root proofs | Install approved real host configuration |
| R20 | Baseline complete | Lease/recovery/exhaustion proof retained | Final candidate regression only | None distinct |
| R21 | Baseline complete | Crash-atomic generation/backend proof retained | Final candidate regression only | None distinct |
| R22 | Baseline complete | Provider compatibility/protected-result proof retained; stale M0 inference reconciled | Final regression; current evidence capture tracked under R03 | None distinct |
| R23 | Baseline complete | Delivery normalization/composite replay proof retained | Final candidate regression only | None distinct |

Evidence and live work owners:

- [Retained M0-M4 proof crosswalk](../semantic_ingestion/engineering-closure/milestones/01-evidence-m0-reconciliation.plan.md).
- [Signing/trust evidence](../semantic_ingestion/engineering-closure/milestones/02-release-crypto-trust.plan.md) and [current signing evidence hashes](../semantic_ingestion/engineering-closure/signing-local-evidence.json).
- [R14 numeric approval and remaining authority blocker](../semantic_ingestion/engineering-closure/milestones/03-independent-statistical-evaluator.plan.md).
- [Monitor work](../semantic_ingestion/engineering-closure/milestones/04-monitor-registry-transitions.plan.md).
- [Active registry publication work](../semantic_ingestion/registry-publication/implementation.plan.md): 77 roots, 179 schemas and a constructed 1255-role publication candidate with 32 decoder source files; the consolidated construction check passes 168 tests, Ruff and Pyright. Independent normalized output bytes agree, and the wheel includes all 1257 registry JSON files. Complete rejection-vector publication, deployment pins and runtime composition remain pending; see [exact checkpoint evidence](../semantic_ingestion/registry-publication/registry-construction-checkpoint.json).
- [Observer/comparator work](../semantic_ingestion/engineering-closure/milestones/05-authenticated-observer-comparator.plan.md) and [final host/whole-program closure](../semantic_ingestion/engineering-closure/milestones/06-host-composition-closure.plan.md).

The registry-history and native decoder modules are prerequisites with no
completed service integration. They do not complete R15's capability monitor or
R17's authenticated observer. Missing final CI/review applies across all 23 rows.

## Evidence Repair And PR State

Implemented locally in this planning task: narrow `.gitignore` exceptions for
49existing immutable logs; `evidence-retention.json`; exact archived review
metadata; and `verify_retained_evidence.py`. A clean export of 191826c overlaid
only with the proposed packaging changes verifies 152 reviewed files and 21 source
files. Altered/missing logs fail; restored bytes pass. Historical bytes/status
were not rewritten. See evidence-retention-checks.json. Packaging changes still
need commit/push to become available in PR checkout; no new commit is claimed.

PR #120 is open at 191826c and CI is running. Saved pr120-status.json is a point-in-
time snapshot, not a final green claim. The previous "no PR/run" observation
was accurate before creation and is now superseded. The eventual packaging and
M5 code commits require CI at their own final SHA; do not transfer 191826c checks
to later product changes.

## Handoff And Limits

This plan resolves the requested engineering-versus-signing scope. It does not
claim that M5 coding, final statistical thresholds/data, or real PKI choice are
already supplied. The first implementation packet should name the signing
backend/public-key profile and the existing canonical extension owners, freeze
M0 crosswalk/authority inputs, and establish engineering acceptance independently
from release issuance. No completed milestone is reopened solely for signatures.
