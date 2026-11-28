# Review and recall an approved learned catalog

- Order: 2. Status: complete at Level 2. Recovery checkpoint `74e70d06`. Local consent checkpoint `fecd58d4`. Final tested product and regression head `04c1fbd9`.
- Requirements: partial OLE-02/04/05/06/07/10/13 and selected learned OCI behavior.
- Dependencies: packaged discovery, plus approved exact-parent, owner-review and recovery design.

## Execution boundary

Use `LearnedRelationRuntime`, the selected-catalog authority and bundle
locator, the host callbacks in `hermes_factory.py`, and the protected
read workflow. Fix the reproduced evaluation publication recovery gap
before exposing broader owner maintenance. Establish transaction ownership
for current grants, durable selection and refresh. Freeze the proposal
state machine, exact parent representation, owner evidence projection,
and explicit rebase protocol. Verify prepublication interruption,
interrupted publication, evaluator unavailable/retry, and terminal retry
as distinct cases. Record recovery via the linked debugging design if the
reproduced defect needs a separate investigation.

The [evaluation recovery WorkPlan](../debug-learned-evaluation-recovery.plan.md)
owns the targeted proposal-state and retry changes. Owner controls,
parent proof and learned reads wait for that recovery boundary.
The [owner and learned-read design](../design-learned-catalog-owner.plan.md)
records local one-time consent, automatic trusted VE provisioning, and
the separate evidence gate for unattended promotion.

The local checkpoint adds `enable-local-catalog-management`,
`pause-local-catalog-management`, and `catalog-management-status` to
`memorii-hermes --help`. Each subcommand takes `--hermes-home`. Four
focused tests cover both persistent layouts, reopen, idempotence,
installation mismatch and a concurrent pause winning stale enablement.
The local factory consumes live consent for observation and recurrence.
Management writes compare the same grant digest as part of the proposal
and pointer write. They verify the host profile prerequisite at
transaction admission, while the durable pause is synchronized by the
grant CAS. Recovery finalizes a previously selected pointer. A prepared
attempt bound to a superseded grant cannot select after re-enable.
Deterministic tests cover pause before a pointer write, restart and
re-enable, host authorization withdrawn before the approval write, and
result retry on both sides of durable publication. Scoped Ruff and
Pyright passed, along with 44 focused core and CLI checks.

Independent review found that interrupted preparation could strand a
proposal and that checking host authority only at admission missed
withdrawal before the write. The implementation makes preparation an
atomic insert and retries a validated proposal on renewed eligible
submission. The write callback verifies host authority at transaction
admission. The reviewer confirmed the remediation.

## Managed provisioning checkpoint

Trusted deployment setup constructs `ManagedCatalogProvisioning` in
`memorii.core.semantic_ingestion.catalog_management` with a durable
workspace plane, the partition and agent catalog coordinate, and a
verifier for that coordinate. Enrollment and withdrawal call
`reconcile()`. The typed receipt includes the persisted enrollment
revision and grant generation. `build_learned_runtime()` binds the
same workspace plane and installs the exact-scope grant and transaction
checks. The verifier must revalidate without calling back into that
memory plane while a write is open.

The implementation preserves local v1 records. The managed v2 payload
adds the enrollment revision under the same grant coordinate and has a
separate origin. Policy writes, proposal transitions and selections
share the storage CAS. The no-key reference journey uses two persistent
managed SQLite partitions. It exercises default enrollment, initial
disablement, exact retry, stale and conflicting revisions after reopen,
same-state revision advance, withdrawal before selection, and denial
across workspaces with the same principal and agent IDs.

Independent review found and verified the fix for a same-workspace
scope gap in idempotent selection and recovery. The regression also
checks that a distinct agent in the same workspace cannot select, inspect
or recover the selected catalog. The focused learner and CLI modules
passed 45 tests. Scoped Ruff, Pyright and identity hygiene passed.
All 1,968 source manifest entries match.

This closes Memorii's reference-host provisioning slice. Production
qualification follows when Virtual Employee wires its trusted enrollment
verifier and lifecycle delivery to the port. A source or task receipt
alone confers no provisioning authority.

Represent the exact immutable packaged parent and validate the whole
effective catalog. Old overlays without sufficient evidence are unavailable
until an authorized, validated rebase. No silent backfill, fact rewrite or
read-triggered repair. Rollback selects a previously verified same-scope
ancestor using pointer CAS. Retain the owner and version on existing facts.
Freeze any persisted schema compatibility policy before implementation.

## Installed learned-read checkpoint

Readiness baseline `e49b6445`, Level 2, same v8 branch. The host-facing
Hermes and authenticated-source read surfaces already share their verified
read binding and the provider's protected snapshot. At baseline the exact
read workflow rejects learned versions before projecting descriptors.
Existing installed tests exercise older typed fact recall and expect exact
inspection and diagnosis to be unavailable for the early parentless overlay.
Keep that behavior for early rows without independent parent proof.

The bounded acceptance matrix uses one authorized `mentors` witness and
the packaged household bill baseline. Exercise each learned-read surface
after closing and reopening durable storage, with the model key absent
and network entry points forbidden. Verify the expected relation and fact
from the same exact learned closure, an inherited packaged declaration,
and denial under an invalid grant. Preserve the explicit unavailable
result where the exact parent cannot be verified. Use the existing stock
household journey as separate packaged regression evidence.

The implementation worker owns the overlapping product and test files.
The read mapper supplies entrypoint and pin evidence. The coordinator
owns the plan, reconciles the candidate and runs scoped closure.

The installed activation uses the verified packaged selector and fences
the base pointer and immutable version at first selection. Browse and
inspection follow the stored ancestry inside the same metadata read.
Diagnosis uses the authorized semantic snapshot and the same verified
descriptor inventory. The preserved durable failure isolated a mismatch
between the learned version's relation IDs and the shared predicate
interface. Exposing the verified IDs through that interface restored
exact diagnosis with the same fact fields as the direct protected read.
No persisted schema changed.

Product and test checkpoint `eec43ead`. The focused bridge test
`test_learned_replay_of_a_preselection_capture_reopens_jsonl` passed in
55.62 seconds on Python 3.12.16 with warnings as errors. It uses both
real Memorii composition roots and the existing optional Hermes ABI
stand-in. The reopened public tool calls enumerate the complete effective
catalog, inspect the learned declaration and inherited bill alias, and
recall the same protected fact as direct typed read. Both bindings deny
exact inspection and diagnosis when only the parent grant remains.
The old version selector yields `catalog_changed` after rollback and
the retained fact keeps its original catalog identity. The test removes
the OpenAI key and rejects DNS and socket connections.

The 49 focused core/CLI tests and 19 local Package Smoke bootstrap and
release-tool tests passed. Scoped Ruff, Pyright and identity hygiene
passed. The three touched entries were refreshed in the release pin
and all 1,968 source entries match. The same frozen candidate wheel
passed the learned read journey in 55.61 seconds in the local
`memorii-rehearsal-hermes:d62a3abd` image with `--network none`.
The disposable fixture initialized managed SQLite and loaded the
provider and factory from installed entrypoints against the real
Hermes ABI. It verified the Memorii import and distribution paths
inside the extracted wheel. The separately provisioned household bill
and work baseline passed at parent `e49b6445` in 336.69 seconds.

The targeted reviewer verified parent CAS, matching historical
authority and protected release across both callers.
`remaining_validated_p1_p2: []` for this read slice. A separate foreign
account or agent trial, explicit legacy rebase, and direct race evidence
for a packaged parent change at first selection remain outside the
new witness. The separate
`test_installed_learned_overlay_preserves_default_entity_relation_lifecycle`
passed in 127.47 seconds. It rejects a new selection from a parent
content digest, then verifies that an early parentless overlay remains
unavailable through the combined workflow after reopen and retains
authorized direct current and historical reads.

## Owner operations and rebase checkpoint

Baseline `f2b1e25a` on `codex/durable-delivery-implementation`, Level 2.
The sole owner operations worker maps existing approval and refresh into
both installed bindings. The coordinator takes over the shared runtime
after those core edits freeze and owns the rebase and scope witnesses.
The independent rebase mapper confirmed that the existing selection
operations and grant CAS suffice when the proposal binds the exact
superseded pointer and the independently verified packaged version.

The rebase port accepts no caller-supplied parent or evaluation. It
requires the selected parentless version, its selected attempt and its
original active proposal to agree. The packaged selector must resolve
the exact version named in that proposal. A matching content digest is
insufficient. A fresh versioned proposal keys on the prior pointer and
exact package, repeats paired evaluation, and requires owner approval
and activation. The new version retains the exact semantic parent.
The prior overlay remains historical and the pointer CAS does not replay
or rewrite its facts.

The acceptance matrix uses the no-key learned work witness through
both installed bindings and the earlier household bill baseline. It
checks owner evidence and terminal rejection across reopen, durable
selection under ordinary refresh failure, exact-parent rebase and
idempotent prepare, same-scope rollback, unchanged historical claims,
and denial for ambiguous legacy parent, stale or withdrawn authority,
and cross-account or peer-agent read configurations. Existing sealed
unbound and seed-bound read fixtures check carrier-specific denial.

Owner review returns the closed declaration, current retained evidence,
paired outcomes, verified parent and selected version, and recorded
decision. The owner approval and rebase responses are typed receipts
with the proposal ID and lifecycle. Receipt callers can obtain evidence
through the separately guarded review call. A candidate whose historical
parent cannot be verified reports unavailable parent status without a
version ID. Terminal rejection survives reopen.

Independent review found three issues and confirmed the fixes. The
receipt removes raw evidence from action responses, startup preserves
the durable selection even while grant publication remains unavailable,
and status derives selected version and attempt from the same pointer.
`remaining_validated_p1_p2: []` for the reviewed owner/rebase paths.
The owner fixture reopens the generic binding while publication still
fails, reports the same attempt as pending, and retries without changing
the selection identity.

Local Python 3.12.16 passed 74 focused owner, learner, catalog and
scope tests after correcting the seed-bound foreign-agent expectation:
the required reference is unresolved and returns no rows or identifiers.
The separate sealed genuinely unbound restart proof passed with the
scoped suite. The legacy overlay fixture also passed, rejecting an
ambiguous parent before changing any record. The peer read-only witness
uses the separate catalog opt-in and deliberately opens without the
optional structured writer sidecar. Fresh peer writer enrollment
against an already active observation ledger is outside this read proof.
The 19 local Package Smoke bootstrap/release tools, scoped Ruff, Pyright
and identity hygiene passed. All 1,968 source-manifest hashes match.

The durable retry checkpoint below implements recovery of unavailable
execution against the original registered executor, parent, corpus and
budget. Calibrated automatic promotion remains deferred as designed.

Product checkpoint `5f6aae55`. The durable no-key JSONL journey
reconstructed a provable parentless overlay, recorded eight fresh paired
cases, selected a new version after explicit approval and confirmed the
original version and claim records were byte-equivalent after selection.
Rollback and reopen retained protected learned recall across both
bindings. The binding denial initially surfaced the exact scope error
instead of the generic owner error expected by the fixture. A focused
reopen of those same persisted records verified both peer read and owner
denials and both foreign-account startup refusals. The test now asserts
the exact scope error.

The full corrected witness passed in 166.83 seconds against the built
wheel in `memorii-rehearsal-hermes:d62a3abd` with managed SQLite, the
real Hermes ABI, installed entrypoint discovery, and `--network none`.
All five changed product files match the wheel's frozen build source.
The [hosted PR Gates run](https://github.com/nrag/Memorii/actions/runs/46118653960)
for product/test head `1a5816b0` was queued at verification handoff.

## Durable evaluation retry checkpoint

Baseline `7c32ea7d` on `codex/durable-delivery-implementation`.
PR [126](https://github.com/nrag/Memorii/pull/126) is the active v8
integration. The earlier owner/rebase product run passed Static Analysis
and Package Smoke. Its [Benchmark Contract Tests job](https://github.com/nrag/Memorii/actions/runs/46118653960/job/140898033936)
failed on 20 cross-module private imports in the parallel v8 installation
recovery and managed spool code. The separate gate mapper reproduced the
same failure on the baseline. Record it against the storage/harness owner.
Do not change storage behavior or weaken the architecture check for M2.
To unblock the branch, a disjoint worker made the shared helper and type
names explicit in their existing owners and updated the callsites.
An inverse-rename AST comparison established identifier-only changes.
The 35 architecture tests and 55 recovery/operator tests passed, along
with scoped Ruff and Pyright. Repair checkpoint `62dec2ce` passed all 312
tests selected by the Benchmark Contract Tests workflow on local Python
3.12.16. The combined retry candidate refreshed the seven source pins,
the affected operator-test pin and the installed factory pin.

The implementation worker owns the retry runtime and focused tests.
The code mapper traces the exact composition, and the coordinator owns
the plan, review, source pins, and hosted gate verification. Preserve
the unrelated Virtual Employee and v8 hardening work.

| Verification | Required observation |
| --- | --- |
| Unavailable and interrupted execution | Persist the scoped attempt before calling the executor. A new process resumes the same proposal, immutable parent, evidence and exact registered binding. Keep the unavailable generation's result. |
| Stale work | Changed package execution identity, corpus, budget, parent, management authority or retained source prevents execution or publication. A late completion cannot replace a newer generation. |
| Legacy and terminal states | An old unavailable row without the attempt proof stays inert. Published result recovery consumes exact stored bytes. Approved or terminal proposals do not execute again. |
| Installed no-key path | The factory registers the verified evaluator before the retry sweep. The reopened learner can reach owner review without selecting or replaying facts. |

Reuse the canonical installed package-root digest with a named executor
contract, along with the fixed corpus, budget and verified selected parent.
The package identity covers executable composition, writer and protected
reader dependencies shipped in the package. The Level 2 comparison is
against identical registered package bytes. Deployment compatibility
across supported platform and interpreter upgrades remains separate.

The persisted identities are `learned_ontology_evaluation_attempt_v1`
and `learned_ontology_evaluation_result_v1`. The typed attempt records
the proposal, scope, original version, evidence digest, registered
artifact/binding/corpus/budget, generation and lease or result digest.
Claim and publication use the existing memory-plane conditional-write
transaction. Approval, selection and replay remain separate. The startup
sweep reenters the original proposal only after the factory attaches the
evaluator and callback, and permits one attempt per proposal per sweep.
No earlier proposal or published result receives an inferred binding.

Frozen local evidence so far is 45 learner tests and 48 companion
context, owner, CLI and Package Smoke tests. Full Ruff, Pyright,
identity hygiene and all 5,399 unit test collection/shard assignments
passed. All 1,968 pinned source and test hashes match. The targeted
review traced both real composition roots and the atomic generation
fence. The installed authenticated-source restart faults and retries the
same proposal. The native Hermes section exercises the same installed
factory through normal admission. A follow-up probe found that generic
owner review compared the raw display user with the canonical retained
actor. The remediation verifies the sealed ingress and source authority
directly from the protected snapshot record. Generic owner review now
reports the three exact frozen evidence references before approval.
Separate no-key installed owner review/reopen and native explicit
rebase/recall passed (2 tests, 214.26 seconds). The final startup guard
limits automatic retries to ordinary provisioning opens, preserving the
standalone grant-revocation command boundary.

Product and regression head `4d23b90c08f36c5ad0b76997b352d18b8ccfe979`
passed all 93 focused tests, full Ruff and Pyright, and the 312 tests
selected by Benchmark Contract Tests from a clean archive. The final
no-key witness passed on the frozen owner-review delta in 484.23 seconds.
It exercised the temporary generic evaluator outage, retained attempt
receipts, exact owner evidence, approval, recall after reopen, and
independent Hermes parity. A separate final-byte regression verified
grant revocation before normal provisioning. The focused delta review
confirmed the owner evidence fix and reported no further Level 2 P1/P2.

The [hosted run for the retry implementation](https://github.com/nrag/Memorii/actions/runs/46120823118)
passed Package Smoke. The earlier [unit shard 5](https://github.com/nrag/Memorii/actions/runs/46118850736/job/140898639479)
also exposed a stale test expectation. A local installation without
catalog consent correctly retained a single unclassified observation.
The test now verifies pending discovery, no observer binding, and no
proposal or gap after reopen. This changes the test expectation for the
standing consent contract and leaves runtime byte-identical to `4d23b90c`.

The full scoped-context suite passed all 146 tests locally from the product
archive. The installed product wheel passed both the authenticated-source
outage and restart journey with native Hermes parity and the owner
review/rejection/reopen test in 459.71 seconds. The Hermes container had
network disabled and no OpenAI key. An import assertion confirmed the
distribution supplied the runtime under test.

[PR Gates run 46121219562](https://github.com/nrag/Memorii/actions/runs/46121219562)
tests the final code and test head `04c1fbd90ad5900be10cf4c8c15262c29a526ac3`.
The checkout log confirms the `pull_request` merge
`3d1dd7c3e94dc215d1674501b0892dd8b4f6a4e7` at `refs/pull/126/merge`.
Its tree matches the PR head. Static Analysis, Package Smoke, Scoped
Context Integration, Hermes Level 2 Product, Hermes Installed Image
Lifecycle, and Benchmark Contracts passed on that checkout.

## Acceptance and verification

- The local owner enables once and reopens or pauses the same agent
  policy without an API key. A verified VE provisioner enables on eligible
  workspace enrollment and withdraws authority on disablement or removal.
  Same identifiers in another workspace do not join. Grant withdrawal
  before a management commit wins the authority precondition.
- Enabled learning proceeds without per-candidate review. Without applicable
  calibrated promotion evidence, an evaluated candidate remains pending.
  Manual review is available to the authorized owner. Automatic activation
  requires the exact permitted policy and evidence.
- Owner can view the proposed declaration, verified evidence references,
  paired parent/candidate outcomes, abstentions, vetoes, parent/version
  status and recorded decision. Rejection is terminal across reopen.
  Deny unauthorized decisions with no mutation.
- Prove live approve, activate and select-prior grants on each exposed host
  path. Withdrawing authority before mutation leaves state unchanged.
  After valid activation or rollback, a failed refresh reports the durable
  result and pending refresh through scoped status. Verify CAS and retry.
- Inspect and recall an authorized `mentors` fact through both read
  bindings after restart. Verify ordinary parent reads, peer-agent and
  foreign-account denial, missing or ambiguous parent, same-scope rollback,
  retained historical meaning and revoked-source replay skip. Exercise
  seed-bound versus genuinely unbound readers separately, including malformed
  and out-of-scope records on each path.
- Rebase a provable early overlay through an explicit authorized selection.
  Missing or ambiguous parent evidence or withdrawn authority leaves the
  pointer and historical records unchanged.
- Exercise recovery on reopened durable storage. The baseline probe proves
  decoder disagreement on an in-memory store. It cannot close restart proof.

```sh
python -W error -m pytest -q -p no:cacheprovider \
  tests/unit/core/semantic_ingestion/test_learned_relation.py \
  tests/unit/core/test_scoped_context_activation.py \
  tests/unit/integrations/test_hermes_memory_provider_bridge.py \
  tests/integration/test_ingestion_time_seal_minting.py \
  tests/integration/test_scoped_context_production_binding.py
```

Close with installed restart/replay/rollback evidence, scoped decision and
recovery review, applicable gates and no open in-scope P1/P2. This packet
does not broaden the edit grammar or propose a new ontology.

## Level 2 closure

Complete for the M2 allocations of OLE-02/04/05/06/07/10/13 and OCI-01–04.
The work witness is the owner-approved `mentors` relation, including
exact-binding recovery, explicit rebase, scoped inspection, and protected
recall after reopen. The separate signed-in household witness retains its
packaged bill recall. Managed enrollment and withdrawal are verified at
Memorii's reference-host boundary. Virtual Employee deployment qualification
and automatic promotion calibration remain separate.

All 60 jobs in [PR Gates run 46121219562](https://github.com/nrag/Memorii/actions/runs/46121219562)
passed. [Unit Tests](https://github.com/nrag/Memorii/actions/runs/46121219562/job/140912186657)
closed the aggregate after all six shards and the
[host container gate](https://github.com/nrag/Memorii/actions/runs/46121219562/job/140905945354)
passed. Independent review confirmed the retry and scope fixes and the
test-only standing consent correction. The closure commit records that
evidence and changes only WorkPlan documentation.

```yaml
base_revision: 52948673192536a6a3a0ddbad2ceff5ccfb03a3a
reviewed_revision: 04c1fbd90ad5900be10cf4c8c15262c29a526ac3
tested_revision: 04c1fbd90ad5900be10cf4c8c15262c29a526ac3
tested_tree_digest: bc00f5923010faa4ed4e7a027001e024060bb3ea
tree_state: clean tracked sources at test freeze, matching the hosted merge tree
changed_surface_inventory_complete: true
scope_delta_resolved: true
authority_chains_complete: true
required_local_jobs: &local_level2
  - Focused learner, owner, scope, CLI, and package preparation regressions
  - Offline installed retry, review, rebase, and protected recall
  - Scoped Context Integration selection
  - Benchmark Contract Tests selection
  - Ruff, Pyright, identity hygiene, shard discovery, and source manifest validation
passed_local_jobs: *local_level2
known_local_failures: []
failure_exclusions: []
workflow_identities:
  - path: .github/workflows/pr-gates.yml
    sha256: 8ff8272b7a5e43d123f71693edafa11cf0988810f8af4c3041cedcf7ae5906af
ci_event: pull_request
ci_executed_sha: 3d1dd7c3e94dc215d1674501b0892dd8b4f6a4e7
ci_executed_ref: refs/pull/126/merge
remaining_validated_p1_p2: []
remaining_blocks_approval: []
remaining_changes_required: []
local_ci_parity: Local macOS Python 3.12.16 and an offline Linux Hermes image supplement the hosted runner and dependency matrix.
acceptance_gate_inventory:
  - Static Analysis
  - Package Smoke and Observation Ledger Activation
  - Scoped Context Integration
  - Hermes Level 2 Product and Hermes Installed Image Lifecycle
  - Semantic Ingestion and its dependencies
  - Benchmark Contracts and its dependencies
  - Unit Tests, all six unit shards, timing inventory, and host container certification
github_run_urls:
  - https://github.com/nrag/Memorii/actions/runs/46121219562
pr_head_sha: 04c1fbd90ad5900be10cf4c8c15262c29a526ac3
pr_base_sha: 885c7db7ad8bba1aa0dd7d88c8f162d26c3bed0d
merge_base_sha: 885c7db7ad8bba1aa0dd7d88c8f162d26c3bed0d
required_checks_green: true
```
