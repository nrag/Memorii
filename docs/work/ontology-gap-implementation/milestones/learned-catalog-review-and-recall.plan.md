# Review and recall an approved learned catalog

- Order: 2. Status: durable result recovery, local standing consent and the local runtime mutation fence verified. Managed enrollment and calibrated promotion remain open. Recovery checkpoint `74e70d06`. Local consent checkpoint `fecd58d4`.
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
admission. The reviewer confirmed the remediation. The managed
provisioning contract can be implemented and verified in Memorii with
a trusted reference host and two workspace partitions. Production
qualification follows when Virtual Employee implements the enrollment
verifier and lifecycle delivery. Source and task enrollment receipts
do not confer this authority.

Represent the exact immutable packaged parent and validate the whole
effective catalog. Old overlays without sufficient evidence are unavailable
until an authorized, validated rebase. No silent backfill, fact rewrite or
read-triggered repair. Rollback selects a previously verified same-scope
ancestor using pointer CAS. Retain the owner and version on existing facts.
Freeze any persisted schema compatibility policy before implementation.

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
