# Authorize and read an exact learned catalog

- Work ID: learned-catalog-owner-and-read-design
- Work type: design
- Delivery fidelity: Level 2, installed local agent work and household trials
- Status: blocked on owner authorization choice
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

## Material authority decision

The governing contract separates catalog management from fact grants and
catalog visibility for protected reads. Select how the first local owner
explicitly acquires the distinct management authority:

- A separate local catalog-management opt-in. The verified signed-in
  profile owner explicitly enables scoped review decisions, selection,
  and rollback. Review the revocation and persistence owner before coding.
- Existing trusted host setup. An installer supplies a distinct scoped
  catalog-management capability through verified host configuration.
  Stock setup stays a separate future capability.

Neither option authorizes management from a source transcript, a read
grant, a fact-write grant, or a model result. Both require current grant
checks at the mutation boundary and an authority-linked selection
precondition. A stale identity cannot mutate a catalog.

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
- The independent evaluation repair may proceed with no owner-management
  decision. Executing evaluation and retrying an unrecorded result require
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

Freeze the chosen authority source and scope-revocation semantics, the
version/projection and explicit-rebase contracts, and installed positive
and ordinary failure tests. Complete focused independent review before
owner or read-path implementation.
