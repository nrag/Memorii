# Authorize and read an exact learned catalog

- Work ID: learned-catalog-owner-and-read-design
- Work type: design
- Delivery fidelity: Level 2, installed local agent work and household trials
- Status: active, enablement decision approved
- Coordinator: Codex
- Created: 2026-11-27
- Last updated: 2026-11-27
- Parent WorkPlan: [learned catalog milestone](milestones/learned-catalog-review-and-recall.plan.md)
- Related WorkPlans: [evaluation recovery](debug-learned-evaluation-recovery.plan.md), [completed catalog discovery](milestones/packaged-catalog-discovery.plan.md)
- Canonical inputs: [ontology design](../../design/learned_ontology.md) Sections 6–8 and 12–13, [signed-in household constraints](../learned-ontology/ontology-capability-audit.md)
- Expected outputs: reviewed owner authority, selected effective catalog, and historical rebase boundary

## Objective and baseline

An authorized local operator can review a learned proposal and its paired
result, make a recorded decision, select an approved immutable version,
and look up its relation through the existing protected read tools. A
same-scope rollback preserves the authorization and historical meaning of
facts. Scope revocation, exact-parent failure, or an unavailable dependency
must stop the affected operation with a typed outcome.

Current callbacks capture principal and agent identity. They verify the
scope through the core owner policy, but no separate catalog-management
grant is present. Activation and rollback can select before refreshing the
local structured authority. The read workflow intentionally treats the
selected learned overlay as unavailable. The parallel v8 working tree adds
bounded catalog metadata reads and reuses the historical version-key owner.
Keep that work separate. Review the immutable installed evidence path when
both changes are composed.

## Approved enablement decision

The governing contract separates catalog management from fact grants and
catalog visibility for protected reads. The user approved one standing
policy with two trusted provisioning paths:

- The signed-in local profile owner enables learning once for that
  agent's exact catalog. Persist the opt-in across launches. Pause or
  revoke it through the same operator boundary. Starting the agent or
  enabling an unrelated tool grants no management permission.
- Virtual Employee enables the policy by default when its trusted
  provisioner enrolls an agent in a workspace, subject to workspace
  policy. The verified generic host setup issues the distinct scoped
  authority. Workspace disablement, agent removal, and a revoked
  provisioning binding withdraw it. Agent or workspace labels supplied
  in transcripts or tool arguments confer no authority.

Use the same scope-owned policy in core. Its identity includes the
verified installation or workspace partition and the exact authenticated
agent catalog coordinate. A local consent and VE provisioning receipt
can select policy for their own coordinate only. The partition is key
even when principal, agent, or delivery IDs coincide. Do not enable
tenant-wide publication or read another user's facts under workspace
enrollment. Evidence, candidate, and fact access retain their own grants.

Standing enablement lets the learner collect scoped evidence, group
recurrences, propose, and evaluate unattended. The activation decision
remains result-specific. Existing paired evaluation, mandatory vetoes,
observed same-scope recurrence, the calibrated 0.95 promotion threshold,
and exact evaluator/scope applicability all remain required for
automatic promotion. Until that evidence exists, candidates remain
pending and normal packaged reads continue without a key. Manual review
is available for exceptions and early testing. An enabled policy grants
no provider transport or network authorization.

## Authority write and revocation contract

Keep a versioned, typed management record separate from fact and read
grants. The canonical owner uses the current record as a conditional
write precondition on a management mutation. Issuance and revocation
compare and replace that same coordinate. Retry of the same enablement
is idempotent. A new enablement after revocation has a newer generation,
so an old prepared attempt cannot resume under it. Source adapter
configuration and publisher output cannot create the record.

Manual decision, automated decision and rollback carry distinct actor
or policy evidence. Record proposal, exact evaluation, policy identity
and generation, owner scope, parent version and decision in durable
selection evidence. On restart, verify a prepared attempt's original
authority before pointer CAS. Finish bookkeeping for an already selected
attempt from its durable witness. Suspend future selection when the
policy is paused on the exact coordinate. Existing current fact and
read grants still govern serving historical data.

Start with local operator enablement and the core authority fence.
Exercise the installed local prompt-free workflow and ordinary denial
before expanding metadata and rebase.

### Managed host provisioning contract

Memorii owns the generic provisioning port and its durable reconciliation.
Trusted host composition injects a verifier and an already bound memory
plane. The verifier resolves enrollment to one exact workspace partition,
principal and agent, then returns a typed decision with the desired
`enabled` or `paused` state and a monotonic per-coordinate enrollment
revision. A later re-enrollment of the same coordinate must carry a newer
revision. Compose the provisioning port in the deployment control path.
Keep source receipts, task receipts, transcripts and agent-facing tools
outside that path.

On authorized enrollment, the host submits `enabled` by default unless
workspace policy disables it. Policy disablement, agent removal and
authority withdrawal submit `paused` for the same coordinate. The host
retains the pending lifecycle operation and retries until Memorii confirms
the durable result. The runtime refuses to manage the catalog if its
trusted workspace binding cannot be verified. An invalid or absent
enrollment decision cannot create or replace a grant.

Memorii checks the verifier's coordinate against the bound workspace plane
and applies the decision with CAS to the shared grant record. An exact
retry returns the applied state and generation. An older revision or a
different state at the same revision is refused. Each accepted newer
revision advances the grant generation, even when the desired state is
unchanged. Acknowledged withdrawal fences catalog mutations and invalidates
prepared selections from older generations. A commit that wins the same
store fence before withdrawal remains part of catalog history. The host
does not report withdrawal complete until it receives acknowledgment.

Memorii can implement and verify the contract with a production-shaped
reference host that controls two workspace partitions. Cover enrollment
by default, policy disabled at enrollment, retry after a lost
acknowledgment, stale enable after withdrawal, identical agent IDs in two
workspaces, invalid proof, and withdrawal before a selection write. Run
the journey without a model key. VE implements its enrollment verifier
and lifecycle calls when it wires its deployment. Reserve deployed VE
qualification for that hookup. Memorii's contract and reference-host
acceptance can proceed independently.

### First local operator checkpoint

Add enable, pause and status to the installed `memorii-hermes` operator
CLI. Verify the OS owner, private installation identity and matching
persisted primary operator context. Derive the canonical operator from
that installation and use the context's canonical primary agent. This
setup authority is independent of the expiring runtime profile and
transport authorization. Runtime consumption requires current host
authority in addition to the standing policy.
No free-form agent label or caller-supplied installation is sufficient
for a grant. Another agent requires a verified profile registration path.
Select the same initialized managed or recognized legacy store as the
factory, with legacy bootstrap disabled. No semantic worker, write-tool
authority, credential or model provider participates.

The repository stores one current closed v1 management policy record
for the installation partition and exact agent catalog. An absent
record reports disabled. Enable and pause compare and replace the typed
record at its deterministic coordinate, incrementing the generation on
a state change. An identical retry reports the existing generation.
Reads reject incorrect record type, scope/partition and malformed bytes.
Report only state, generation and authority origin through status.
Factory-managed status uses the same repository and scope.

The first checkpoint provisions and displays standing authorization.
It does not consume it yet for candidate or pointer mutations. The next
checkpoint fences those actual writes and attaches the learning policy.
No new managed action is exposed until its precondition and revocation
tests pass. The Virtual Employee adapter requires the separate verified
workspace enrollment issuer and store fence. The generic source root
alone lacks that provisioning proof.

The focused Level 2 design review passed this checkpoint boundary.
The preflight identified `memorii-hermes` and the canonical persistent
plane selector as the local composition path. It also confirmed that
current generic production source verification and managed enrollment
carry source or task authority, with no current workspace catalog grant
issuer. The installed local command verifies the stable private
installation and persisted primary owner independently of the
expiring model-transport sidecar. The implementation reviewer flagged
wording that could imply the CLI required the sidecar. The design now
states which proof setup uses and which additional check consumption
requires.

## Exact version and recovery constraints

- New effective versions carry their exact verified parent version. Parent
  content equality alone is insufficient. The owner view may display a
  verified evidence reference, declaration, paired outcomes, and recorded
  decision only within its authorized scope.
- Preserve the stored authority for historical, seed-bound, and genuinely
  unbound legacy reads. A reader cannot fill an absent parent or rewrite
  old facts. Rebase of a provable early overlay requires explicit owner
  action and selects independently verified immutable bytes.
- If refresh fails after a valid durable selection, status reports that
  selection and the pending refresh separately. Retry preserves the
  selected attempt identity. Current suppression and protected-release
  checks remain after read assembly.
- The independent evaluation repair does not consume the owner-management
  grant. Executing evaluation and retrying an unrecorded result require
  exact same-parent and pinned binding/corpus/budget evidence. Startup can
  finalize a result already durable without invoking evaluation.

## Production seams and evidence requirements

The existing provider and completed-turn observation callsites put the
selected catalog's `version_digest` in the recurrence evidence coordinate.
The proposal field is named `parent_catalog_digest` and has older callers,
so establish provenance before interpreting a historical value as a
version identity. Start the new activation path from a verified selected
bundle and check the exact parent again with the selection precondition.
If the original proposal's parent is unavailable or ambiguous, preserve
the existing pointer and report that outcome. Same content under another
packaged version is insufficient.

Reuse the package-indexed historical locator and the protected snapshot
owner. The new relation descriptor is an authenticated projection of the
exact selected learned closure, including its verified parent and edit.
Use the existing historical catalog binding at fact release. Exercise a
complete effective relation inventory, parent alias ambiguity, current
learned read, prior installed fact, and same-scope rollback after reopen.
Exercise incomplete immutable parent material and foreign account/agent
authority over both inspect and recall. Coordinate the selected metadata
projection with the parallel v8 implementation before editing it.

The first-party factory's current callbacks are the mutation boundary.
The core owner is still responsible for comparing the proposal and current
scope to the authority immediately before an approval, rejection,
activation or rollback write. Log the checked authority in the durable
selection evidence. A failure before the authoritative write retains the
actual old pointer. A failed post-write refresh exposes the real selected
attempt and its replay/refresh progress, preserving retry identity.

## Retry of unpublished evaluation work

Result publication and evaluator execution have different recovery
contracts. A result that was already durably published is finalized from
those exact bytes. A new execution requires a durable attempt anchor
binding the existing proposal ID and its immutable parent version to the
registered evaluator binding, corpus, and budget. Record the anchor before
calling the executor. A retry reuses the same frozen inputs. The old
proposal ID stays stable and its frozen evidence does not change. Pre-edit
v1 proposal records and historical results must remain decodable.

The existing observer-to-recurrence entrypoint revalidates the exact
scope, retained source evidence and current selected parent before an
evaluator executes. Propagate unavailable capability state explicitly.
If the selected version changed, or the binding, corpus, budget, or
source proof differs or cannot be verified, stop the attempt without
changing the pointer or facts. A previously unavailable result may
reenter evaluation under the same verified attempt commitments.
Pre-existing interrupted rows without enough to prove those commitments
remain inert. They require a separately authorized new proposal when
the exact old parent cannot be proved. A terminal or approved proposal
never starts another execution.

The current admission path can substitute a live learned pointer for the
observation's version and derive a new proposal ID. Retry must instead
resolve the existing proposal from its pinned identity and require the
observed, anchored, and currently authorized version and scope to agree.
A changed head cannot turn a retry into a new admission. The current
frozen evaluator binding digest covers the corpus and budget. Expand the
retry evidence to include the registered execution contract as well.
For the first retry path, support the provable packaged parent and require
the isolated evaluator roots to verify that exact parent. An overlay
without equivalent isolated-runtime proof remains unavailable.

Use a scoped durable attempt claim and generation fence before an executor
starts. Publication must compare the current generation so a completed
older run cannot replace a newer attempt. Retain the unavailable
generation's result as evidence of that attempt. Membership growth in the
recurrence group cannot rewrite the proposal. Revalidate every original
evidence reference under current retained ingress and suppression. The
current observer recovery authorizes one observation at a time and does
not by itself prove all evidence in the proposal.

The registered execution identity must cover how each isolated store is
composed, how the verified parent and inert candidate are chosen, and
which typed proposal, writer and protected reader bindings execute. Freeze
the versioning and artifact proof before enabling retry. A checked-in
corpus digest, budget digest, or package version string alone cannot
identify the executor. A missing executor is retryable only against an
identity already proven in the durable attempt. An attempt-only sweep
does not reconstruct work interrupted before any attempt was published.

The provider currently recovers coverage observations before the factory
attaches the candidate admission callback and isolated evaluator. The
complete installed retry must reenter eligible groups only after that
composition barrier, with current retained-source authority, exact parent
proof, and at most one evaluation attempt per proposal per recovery sweep.
Exercise interruption before first durable result, same-binding unavailable
retry, changed binding or parent, revoked evidence, and terminal
idempotence. Distinguish a durable reopen test from installed startup
evidence. Neither path may approve, select, or replay a candidate.

A component probe confirmed two distinct executors with the same current
corpus and budget have the same evaluator binding digest. It also
confirmed the packaged seed and default catalogs have equal catalog
digests and distinct version digests. Future preflight must reject both
binding substitutes. The reviewer identified the startup composition and
current source-authorization seams. The registered executor identity
still needs a concrete, reviewed version and artifact rule.

## Completion and next action

Local implementation compares the current consent in the same
conditional write as a proposal or pointer mutation. The prepared
selection's decision digest commits to the exact grant record. Recovery
finalizes a proven selected pointer and declines selection from a
superseded grant. The local host profile is validated at transaction
admission. The explicit catalog pause operation is the durable revocation
that serializes with catalog mutations.

Implement the managed provisioning port with a trusted reference host
and verify it through the same mutation and recovery rules.
