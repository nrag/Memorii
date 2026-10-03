# Semantic Forgetting Implementation

- Work ID: semantic-forgetting-implementation
- Work type: implementation
- Delivery fidelity: Level 2 (early real-world testing) — real forget
  journeys across happy scenarios and common operational failures;
  persistence, retry, recovery, authorization, and universal invariants
  preserved; adversarial tamper matrices and old-binary (non-proxy)
  evidence recorded as Level 3 deferrals.
- Status: active
- Coordinator: main Codex thread
- Created: 2026-10-03
- Last updated: 2026-10-03
- Parent WorkPlan: docs/work/semantic-forgetting-design/design.plan.md
  (complete; produced the design)
- Related WorkPlans: docs/work/durable-memory-implementation/ (the release
  arc this extends)
- Canonical inputs:
  - docs/design/semantic_forgetting.md — the approved design baseline
    (commit 4780db61; requirements FGT-R1..R17)
  - docs/design/durable_execution_and_solver_runtime.md (amended forget
    section)
  - docs/design/event_model.md (7.3, 14.1)
- Expected outputs: production implementation of FGT-R1..R17 through the
  canonical paths named in design §6.10; the §10 verification families;
  regenerated typed-value publication + repinned release candidate; CI
  green; updated current-state documentation.

## Objective

Implement revocation-based semantic forgetting end to end: the
`revocation_directive` record kind in the append-only semantic log with
its full schema authority chain; the governance-owned enforcement
publication; the revoked-identity view gating every serving path; the
tombstone reader-edit ledger; the upgraded forget plan/apply control plane
with dependency closure, typed journal v2, pending-epoch riding
publications, and boot/mode-resume reconciliation; solver
`revalidation_required` marking; the owner-forensic lineage surface; and
the cross-path parity and crash-cut test families — with the release
candidate repinned and CI green.

## Design Baseline

- Canonical design: docs/design/semantic_forgetting.md at 4780db61
  (requirements FGT-R1..R17; §6.10 authority chain; §10 verification)
- In-scope: all of FGT-R1..R17
- Approved deviations: none
- Unresolved design questions: none (design §13 records two bounded
  implementation-judgment items: suppression_id hash construction; status
  counts owner-visible — default yes)

## Completion Contract

Every requirement FGT-R1..R17 has production implementation evidence
through the canonical entry points (nonzero production callers, exact
composition-root callsites), deterministic verification evidence per
design §10, the typed-value publication regenerated via the authoring
script and the release candidate repinned, all required local jobs pass,
CI green on the pushed head, identity-hygiene gate green with mutation
proof, no validated P1/P2 remains, and the closure record per
`.agents/PLANS.md` is complete. First-release readiness (the follow-on
arc) is out of scope for this WorkPlan beyond leaving the branch green.

## Scope

Included: design §6.1-§6.10 contracts, §6.7 view, §6.8 matrix rows, §10
families, authority-chain regeneration, candidate repin, CI registration.

Excluded: physical selective erasure, backup rewriting, cross-installation
propagation, model/host-initiated forget, retention semantics changes,
performance budgets, adversarial matrices beyond fail-closed decode,
old-binary non-proxy evidence (Level 3 deferrals per design §9).

## Constraints And Invariants

- Frozen pydantic contracts: extra="forbid", strict, closed Literals;
  unknown values fail closed everywhere.
- Append-only history; fold stays kind-agnostic create|update; no record
  removal; persisted==genesis replay equality must keep holding.
- Tier A epoch equality must never break (pending-increment contract).
- Publication regeneration ONLY via
  memorii/scripts/generate_observation_registry_publication.py; never
  hand-edit signed manifests; candidate repin LAST.
- Flock self-deadlock rule: code called inside an open transaction takes
  connection= and reuses the caller's connection.
- manual_write_transaction requires explicit handle.commit().
- Owner's uncommitted files (hermes doc, benchmark docs) never committed.
- Identity hygiene: behavioral names only; requirement IDs stay ledger
  values; mutation proof for new surfaces.
- Time-bomb rule: authorization dates issued at datetime.now(UTC).

## Identity And Coordinate Hygiene

Inherited from the design WorkPlan ledger; new behavioral identities this
implementation introduces (all behavioral/protocol class): record kind
`revocation_directive`; models `RevocationDirectiveRecord`,
`EntityRevocationTarget`, `ClaimRevocationTarget`, `SourceRevocationTarget`,
`RecordRevocationTarget`; `SuppressionRecord` (journal v2 envelope);
control field `pending_epoch_increments`; lifecycle members `revoked`
(ClaimLifecycleState, EntityLinkLifecycleState); event schema version
`memorii.semantic-memory-event.v2` with upcaster; view component
`RevokedIdentityView`; governance entry `commit_forget_enforcement`;
marking reason `revoked_evidence`; forensic surface
`forensic_lineage_audit`. Mutation coverage added for each new surface in
M6. Ledger updated at each milestone.

## Change Impact And Verification Closure

Changed-surface, authority-chain, and gate ledgers live in the active
milestone packet; the index tracks cross-milestone state. The publication
authority chain (decoder-source-manifest → publication-manifest → role
artifacts → registry.json → candidate.json) is reconciled in M1 and
re-checked at every later milestone that touches a pinned file.

## Production Entrypoint Bindings

Ledger initialized by the code-mapper preflight artifact
(docs/work/semantic-forgetting-implementation/preflight-bindings.md);
updated per milestone with callsite/authority/proof. Zero-caller owners
are not implemented.

## Sources Of Truth

Design (4780db61) governs; AGENTS.md precedence otherwise; production code
citations in design §4.

## Current State

(2026-10-03) Operation started at 4780db61 (clean except owner's protected
files). Design review history and evidence: see parent WorkPlan.

## Assumptions And Open Questions

Verified facts: environment (memorii/.venv Python 3.14.7), CI jobs
durable-storage-integration / durable-runtime-integration run explicit
pytest file lists; unit additions need tests/ci/unit-shards.json
registration. Working assumptions: none beyond design-recorded judgment
items. Unresolved questions: none. External decisions: none.

## Milestones

| Milestone | Requirements | Bounded scope | Status |
| --- | --- | --- | --- |
| record-kind-schema-chain | FGT-R1, FGT-R12 | record kind + model + per-kind tables + codec/reference manifests + envelope v2/upcaster + publication regen + repin + focused tests | pending |
| governance-entry-view | FGT-R7, FGT-R2 (view core) | governance delta entry (native-group-commit pattern) + RevokedIdentityView + injection roots + fail-closed composition | pending |
| tombstones-reader-ledger | FGT-R3, FGT-R13 | lifecycle members + tombstone rewrites in the enforcement publication + every §6.3 reader edit | pending |
| control-plane-forget | FGT-R5, FGT-R6, FGT-R8, FGT-R9, FGT-R14 | typed selectors + closure + plan_digest + journal v2 + barrier/pending-epoch + one-transaction finalize + reconciliation + doctor/status | pending |
| serving-completion | FGT-R2 (matrix), FGT-R4, FGT-R15, FGT-R16 | every §6.8 row live + justification marking + forensic surface + no-un-forget property | pending |
| parity-crash-ci | FGT-R10, FGT-R11, FGT-R17 | parity family + crash-cut family + CI registration + identity-hygiene mutations + docs | pending |

Milestone packets under milestones/ as each opens. Milestone names are
organizational only and must not appear in outputs.

## Progress Log

- 2026-10-03: Operation opened at 4780db61. Next action: code-mapper
  preflight, then open the record-kind-schema-chain packet.

## Decision Log

(none yet)

## Review Log

(none yet)

## Blockers And Limits

None. Budget: three review rounds per milestone before blocking.

## Next Action

Run the code-mapper preflight producing
docs/work/semantic-forgetting-implementation/preflight-bindings.md, then
open milestones/record-kind-schema-chain.plan.md and implement M1.
