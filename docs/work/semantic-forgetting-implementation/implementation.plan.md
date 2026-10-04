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
- 2026-10-03: CORE DESIGN IMPLEMENTED END TO END across five pushed
  commits: (1) f9de4478 grammar — `revocation_directive` record kind,
  target union, per-kind tables, codec/reference manifests, all-kinds
  fold fixture; (2) cc580edb reader ledger — revoked lifecycle enum
  members, retrieval allowlist gates, projection map, structured-fact
  all-versions + scoped-context link gates, content-free tombstone
  builders; (3) 652387c1 control plane — typed selector plans with
  content-free closure, journal v2 (stable suppression identity,
  v1-legacy reader, unknown fail-closed), journal-first barrier-gated
  apply, pending_epoch_increments + one-transaction finalize +
  boot completion (DUR-09 closed), drain on barrier-release/boot,
  doctor/status/CLI; (4) c06de831 serving gates — RevokedIdentityView
  (protocol-typed) injected at retrieval/scoped-context/structured-facts/
  entity-match/factory/sidecar; harness + resume justification marking;
  (5) 11b4ad8b governance entry — store method appending the directive
  delta through the full canonical commit (batch/replay state/reference
  ledger genesis-bootstrap/projection/checkpoint/aggregate) with
  tombstones + directive index record under one admission-governed CAS;
  end-to-end journey test green (directive materializes in replay,
  tombstones content-free, drain quiescent, epoch consumed atomically,
  Tier A green). Per-milestone packets under milestones/. Remaining:
  registry v2 mint (M1b), parity/crash families + CI registration (M6),
  forensic lineage surface + prefetch canonical filter, publication
  regeneration + candidate repin, broad gates + milestone review.
  Next action: migrate the five stale golden `.ctv` fixtures under the
  grammar change (see Known Failures), then broad gates + review; M1b
  is the recorded deviation pending the review round's decision.

## Decision Log

- 2026-10-04 (owner decision; resolves the 2026-10-03 M1b flagged
  deviation): the event-envelope schema stays
  `memorii.semantic-memory-event.v1` and additive grammar extensions
  extend it. Verified before deciding: nothing in the repository's
  golden fixtures or trial artifacts carries v0-stamped bytes — the v0
  reader in event replay is dormant fail-closed support, and v1 is the
  sole proven current write. The version rule is codified in the design
  (§6.10 item 5): additive-superset extensions extend the current
  version under strict decode; non-additive changes (removal, rename,
  reinterpretation, wire-layout change) mint a new version, and every
  grammar change mints after first external release. Minting a version
  without being able to state which change belongs in which version is
  prohibited.
- 2026-10-03 (flagged deviation for milestone review — design §6.10 item
  5): the event-envelope schema version remains
  `memorii.semantic-memory-event.v1` instead of minting v2. The grammar
  extension is an additive superset: the closed `GraphRecordKind` union
  gained one member, every pinned artifact regenerated through the
  authoring script, old batches replay unchanged, and an older binary
  rejects the new record kind at strict decode (the fail-closed
  compatibility rule the design itself specifies — covered by the
  strict-decode rejection tests). Minting v2 additionally requires the
  persisted-history compat cascade (byte-identical registry-1 history
  prefix, upcast-decision consultation of the current registry, and
  prefix-tolerant equality at atomic_store :7100/:8825) whose risk was
  judged disproportionate to the naming benefit at Level 2. The review
  round must either accept this recorded deviation (amending the design
  sentence) or schedule the v2 mint as a follow-up; it is not silently
  dropped.
- 2026-10-03: Milestone execution order adjusted by dependency analysis:
  record-kind grammar landed first (f9de4478); the governance publication
  entry (originally M2) is the hardest orchestration (full projection/
  checkpoint/aggregate/policy cascade — traced at atomic_store
  `_prepare_native_projection_publication`, `advance_semantic_replay_authority`,
  clarification/native precedents) and CONSUMES the other milestones'
  outputs (tombstone builders from M3, pending-epoch ride from M4, view
  refresh from M5). Execution order: reader ledger/tombstones → control
  plane → view + serving matrix → governance entry → registry v2 →
  parity/regen/repin. Requirement allocation is unchanged; only sequencing.
- 2026-10-03: The governance entry publishes through the store's standard
  conditional-write primitive (binding inherited from the composed
  memory-plane writer); the governance operation identity lives in the
  operation id/fence coordinates and the control-journal linkage, with no
  new writer-registry kind (the store itself is the enrolled writer).
  Recorded as a bounded reading of design §6.10 item 1 — enrollment,
  owner-gating, and validation are all preserved.

## Review Log

(none yet)

## Known Failures (milestone-close blocking, exact disposition)

| Command | Signature | Authority chain | Disposition |
| --- | --- | --- | --- |
| `pytest tests/integration/test_observation_ledger_activation.py tests/integration/test_observation_terminal_intent.py` (local, package cwd) | 5 failures: stale golden `.ctv` captures under the approved `revocation_directive` grammar change | the captured payloads embed the 12-kind codec manifest and snapshot counts | RESOLVED 2026-10-03: the migration engine (tests/fixtures/semantic_ingestion/migrate_current_terminal_fixture.py) now migrates all three `.ctv` captures, the memory-records plane (9 members, both manifest copies, reference ledger, terminal recovery, group-commit primary with ctv cascade into every construction-embedded reload tuple), and re-encodes each member with its original envelope family (contract vs atomic). The records plane is migrated first and the terminal-reload capture is written from the records-rebuilt reload model so both planes carry identical bytes. Both modules green: 47/47 (terminal intent 3/3, retained closure both variants, captured jsonl history preserved). |

MIGRATION COMPLETE (2026-10-03): both fixture planes migrate green end to
end. Final engine structure (tests/fixtures/semantic_ingestion/
migrate_current_terminal_fixture.py): (1) publication-request.ctv is
migrated first and exports the authoritative request chain (handoff,
epoch, request, replay, lineage digests, group-result digests, canonical
record, finalization delta); (2) the memory-records plane migrates the
group-commit primary first (plan-member rebuild, authorization
group_plan_member_digest re-pin, persisted core + receipt cascade from
the rebuilt core), cascades the fresh request_ctv_digest into every
construction-embedded group_commit_reload (rebuilding each core and
re-pinning its receipt), re-pins delta/canonical-record
group_result_digests from the export, re-encodes every member with its
original envelope family (contract members via encode_semantic_contract,
atomic members via the atomic member encoder, no synthetic codec_key),
recomputes the manifest digest over a TUPLE of member dumps (CTV encodes
list and tuple differently), and captures the records-rebuilt terminal
reload model; (3) terminal-reload.ctv is written from that records
reload model (plane convergence); (4) publication-intent.ctv migrates
last. Store debug was instrumented only against a scratch copy and
restored; atomic_store.py is untouched. Durable lessons: original pinned
digests (group results 691439a7..., delta 27caf38a...) are STALE under
the grammar change because the rebuilt constructions legitimately
recompute (planning-state manifest reconciliation changes
group_plan_member digests); the store treats the records-plane manifest
members as authority for the v2 delta, so every embedded copy (request
delta, reload delta, wrapper) must carry the rebuilt values, not the
captured ones.

## Blockers And Limits

None beyond the known failure above. Budget: three review rounds per
milestone before blocking.

## Next Action

The forensic lineage surface (R16) and the prefetch canonical-channel
filter landed with their acceptance tests
(tests/integration/test_forget_forensic_lineage.py: owner-capability
forensic retained lineage for named coordinates + refusal without
capability; canonical prefetch assembly excludes revoked records under
the injected view; record selectors now resolve any committed record,
matching the design's direct-selector scope). Watch the PR-gates run for
the fixture migration (82f31c0e) and fix any red checks; then run the
milestone review round — the M1b registry-v2 deviation decision is the
recorded open item and needs the owner because it changes a persisted
schema-version boundary.
