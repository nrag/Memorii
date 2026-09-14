# Semantic Ingestion Closure Review

> Updated interpretation: the later completed M0 canonical-genesis/structural
> implementation was found after this audit. Its engineering work must be
> preserved; the old parent blocked summary is stale. PR #120 now exists and CI
> is running, and evidence retention has been repaired locally. See
> ../semantic_ingestion_completion_readiness/closure-plan.md for the corrected
> all-requirement plan and the user's engineering-versus-release boundary.

Reviewed commit: `191826cd3afb38bf605a337a71d576063b3bae5e`.
Verdict: **Do not close the parent semantic-ingestion program.**
Investigation complete; product implementation/acceptance remains incomplete.

The latest commit completes the separately approved SMC-R01-R10 scoped-context
API. It does not implement or certify all of M5. This review preserves the
bounded M1/M2 and M3.1/M4 closures; it does not infer regressions from missing
external authorization. No confirmed P1/P2 runtime defect was established by
this closure audit. The blockers concern required scope, authority and evidence.

## Findings

### 1. Required M5 implementation and acceptance are unfinished

Product priority: Not applicable. Approval disposition: blocks_approval.
Finding type: implementation completeness, operability, verification.

The six M5-linked slices in `docs/design/scoped_memory_context.md:546` are
explicit scheduling proposals. The current parent packet,
`docs/work/semantic_ingestion/milestones/m5-deployment-acceptance.plan.md:25`,
still requires deployment/trust mutation families; fake-clock monitoring,
outage, breach, deactivation and recovery; independent statistical recomputation;
authenticated structural observation with pagination, revocation and global
operation/fence bijection; activated-root fixtures; and live revision-bound proof.

Production has useful components, not the complete M5 path. The deployment
verifier in `memorii/memorii/core/semantic_ingestion/capability.py:109` is an
injected protocol. `source_normalization_authority.py` has an immutable
CapabilityRegistrySnapshot, not the executable monitor/registry transition
owner. Existing acceptance/traceability tools and supplied-cell capture harnesses
do not implement the complete production observation API and independent
comparator/statistics acceptance path. Repository runtime mapping found those
monitoring/statistics/observation owners absent, rather than merely unconfigured.

The new provider `retrieve_context` path at `core/provider/service.py:619`
resolves read authority and assembles a snapshot. It does not issue deployment
approval, monitor a capability, publish authenticated structural-observation
pages, or execute independent acceptance. Its real roots and tests remain valid
proof for its own narrower contract.

Required correction: implement and verify the determinate M5 slices under their
own WorkPlan. Synthetic authority can prove explicitly labeled deterministic
fixtures while external approval is unavailable; it cannot activate production
or count as live acceptance.

### 2. M0 trust closure and live activation authority remain unavailable

Product priority: Not applicable. Approval disposition: blocks_approval.
Finding type: external decision, governance, runtime activation.

M0 explicitly retains rejected C2 v3/round-10 authority as non-consumable:
`docs/work/semantic_ingestion/milestones/m0-proof-compatibility.plan.md:31`.
A separately approved corrected authority or linked design replacement is
required; completing later slices does not revive those rejected bytes.

The canonical external-decision register at
`docs/design/semantic_ingestion_architecture.md:316` still requires:

- POLICY: signed initial thresholds, multiplicity, cluster/freshness and
  monitoring rules from the product/ML acceptance owner.
- TRACEABILITY: independently provisioned bootstrap/recovery trust roots,
  recovery policy, lifecycle root and signed release/trust snapshot from the
  traceability and trust-root owners.

Bootstrap topology and equal-version replay are resolved; do not treat those as
new external blockers. Do not invent policy/trust values or defaults.

Coordinator reproduction on the reviewed source found no installed
`memorii.semantic_ingestion.host_capability` entry point. Default factory
construction returned no composed semantic runtime/profile and `invalid_config`.
The ordinary root's fail-closed behavior is expected without supplied authority;
it is not a demonstrated P1/P2 defect. A real deployment still needs supplied
host capability, verifier implementations and authenticated ingress, wired into
the actual host. The opt-in scoped API likewise legitimately requires explicit
host provisioning; absence of an ambient caller is not a defect in that API.

Required correction: resolve the registered authority dependencies, reconcile
M0's still-required corrected proof, then verify real authorized composition.

### 3. Current full-program hosted acceptance is absent

Product priority: Not applicable. Approval disposition: blocks_approval.
Finding type: verification, integration.

GitHub independently confirms run 34042442561 succeeded with all 47 jobs at
`58ec5cc5a1e463a934681facc81630c956c2197b`, event `pull_request`.
That supports the recorded M3.1/M4 closure. The subsequent base commit changed
only coordination documents and a scheduled workflow relative to that candidate;
its prior runtime/tests did not change. The scoped addition is separately tested.

For current branch `semantic_ingestion_m5`, GitHub returned no PR and no runs.
`.github/workflows/pr-gates.yml:3` triggers on pull_request/merge_group targeting
main, not branch pushes. Thus pushing 191826c did not execute those hosted gates.
Local test success and unchanged-behavior carry-forward are not hosted proof.

Required correction: run the full required PR/merge-group gates on the eventual
complete candidate, retaining the exact executed SHA/ref/event and artifacts.
After M0/M5 acceptance, obtain fresh parent-level approval. Running CI for the
current incomplete candidate alone cannot resolve findings 1 or 2.

Verified external evidence: historical-hosted-run.json and hosted-evidence.json.
Run URL: https://github.com/nrag/Memorii/actions/runs/34042442561

### 4. Scoped evidence needs durable packaging for fresh-checkout verification

Product priority: Not applicable. Approval disposition: changes_required.
Finding type: verification, operability.

The final scoped source manifest matches the committed product/tests. However,
49 files named by its review manifest are not tracked, because `.gitignore:59`
ignores `*.log`. Local files exist, and the committed receipts contain command,
exit status, elapsed time and log hashes, but a fresh checkout cannot retrieve
those logs to validate their hashes or inspect the recorded pass summaries.

Three WorkPlan/resume paths also changed during administrative completion.
Their pre-completion bytes are archived, and this is not product source drift;
verification tooling must explicitly distinguish reviewed metadata from its
subsequent completion record. See scoped-evidence-portability.json.

Required correction: retain the immutable referenced logs in a deliberate
committed artifact location or durable external archive, or publish sufficiently
complete structured test receipts with a verifiable retained output. Bind the
final committed-source execution/CI artifacts to that evidence. This finding
limits reproducible parent closure; it does not negate the observed local passes.

## All-Requirement Coverage

Status here distinguishes recorded bounded implementation from remaining parent
acceptance. It is not a new exact-current-revision certification of every code
path; the review did not rerun the full program or claim absence of all latent
bugs. Each row was checked against the normative ledger at architecture:214,
its milestone allocation and the completed or missing acceptance evidence.

| SIA requirement | Behavior | Supported status | Remaining parent obligation |
| --- | --- | --- | --- |
| R01 | Immutable source/provenance and authorized admission | M1 bounded complete | Current parent acceptance evidence |
| R02 | Candidate-only model output until validation/commit | M3 bounded complete | Current parent acceptance evidence |
| R03 | Complete independent traceability and revision-bound evidence | Partial: Layer1 and later bounded evidence | M0 corrected trust/proof plus M5 acceptance |
| R04 | Typed source-to-terminal owner chain | M1/M3 bounded complete | Current parent acceptance evidence |
| R05 | Independent semantic role/scope/attachment evidence | M3 bounded complete | Current parent acceptance evidence |
| R06 | Temporal detection/attachment evidence | M3 bounded complete | Current parent acceptance evidence |
| R07 | Registered prompt/schema/redaction authority | M3 bounded complete | Current parent acceptance evidence |
| R08 | Local-first bootstrap and explicit remote use | Partial: safe ordinary/bootstrap roots exist | M5 authorized-root acceptance |
| R09 | Current source-bound egress authorization | M3 bounded complete | Current parent acceptance evidence |
| R10 | Atomic canonical events and complete replay | M2/M4 bounded complete | Current parent acceptance evidence |
| R11 | Single writer and certified cutover | M2 bounded complete | Current parent acceptance evidence |
| R12 | Closed temporal/lifecycle algebras | M1/M3 bounded complete | Current parent acceptance evidence |
| R13 | Lifecycle-checked acceptance keys/releases | Partial: fail-closed tools/protocols exist | M0 authority and M5 release/key acceptance |
| R14 | Independent statistical certification | Not closed | M5 implementation, policy and independent recomputation |
| R15 | Deterministic monitoring/registry transitions | Not closed | M5 monitor owner and race/outage/recovery proof |
| R16 | Bootstrap dependency topology/certification | Partial: bootstrap topology resolved | M5 certification/acceptance for activated bundle |
| R17 | Authorized structural observation/independent comparator | Not closed | M5 API/comparator/bijection/authorization proof |
| R18 | Replayable historical truth and conflicts | M4 bounded complete at 58ec5cc | Current parent acceptance evidence |
| R19 | Normal authorized production composition | Partial: bounded roots and scenario proofs | M5 real authorized host/root acceptance |
| R20 | Lease fencing/recovery/stable allocation | M2 bounded complete | Current parent acceptance evidence |
| R21 | Process-safe crash-atomic generations | M2 bounded complete | Current parent acceptance evidence |
| R22 | Provider compatibility/protected results | M1 compatibility/access behavior complete | Reconcile still-open M0 proof allocation; not a new compatibility defect |
| R23 | Stable public delivery/composite replay | M1 bounded complete | Current parent acceptance evidence |

M1/M2 records: `docs/work/semantic_ingestion/milestones/m1-source-admission.plan.md`
and `m2-writer-atomicity.plan.md`. M3/M4 records: sibling `m3-semantic-pipeline.plan.md`,
`m4-event-history.plan.md` and `m4-closure-2026-09-04/implementation.plan.md`.
Parent allocation: `docs/work/semantic_ingestion/implementation.plan.md:126`.

## Remaining Work In Order

1. Create the M5 implementation operation and inventory real authority,
   deployment, observation, monitor and acceptance owners. Reconcile the remaining
   M0 corrected-proof boundary without reviving rejected artifacts.
2. Implement complete deterministic validation, monitoring, independent
   statistics/structural observation and authorized fixture-root proofs. Use
   clearly labeled synthetic authority where allowed, with no activation claim.
3. Obtain POLICY/TRACEABILITY owner artifacts and connect real authenticated
   host capabilities. Complete signed, exact-revision live acceptance.
4. Publish portable evidence, execute all required hosted gates on the final
   candidate and repeat parent closure review with all required arrays empty.

These are additional implementation/authority/acceptance operations. They were
not performed by this read-only closure review.

## Independent Reconciliation And Validation

Three independent roles reviewed the program: ingestion_closure_spec,
ingestion_closure_runtime and ingestion_closure_evidence. All reject parent
closure. Runtime initially used P1/P2 labels for missing authorization/owners;
coordinator rejected those severity inferences and the reviewer withdrew them.
They are N/A closure blockers, not proven supported-path regressions. The
suggestion to reopen scoped API for no ambient host caller was also withdrawn.

Coordinator verified source hashes, missing committed log paths, exact historical
GitHub run, empty current PR/run lists, workflow triggers, historical-to-base and
base-to-current scope, and default host capability absence. Runtime reviewer
also executed 145 scoped integration tests successfully. No full-suite rerun or
live/provider quality certification was performed for this investigation.

Review completion: every one of the 23 requirements has a status and remaining-work mapping;
all findings were reconciled; no product source/test/workflow was changed.
Parent closure remains blocked by findings 1-3, with finding 4 changes required.
