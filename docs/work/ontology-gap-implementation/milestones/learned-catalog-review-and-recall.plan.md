# Review and recall an approved learned catalog

- Order: 2. Status: durable result recovery, standing consent, managed reference-host provisioning, and the exact-parent installed read slice locally verified. Owner review, explicit rebase and remaining scope acceptance are open. Recovery checkpoint `74e70d06`. Local consent checkpoint `fecd58d4`.
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
