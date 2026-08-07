# Semantic Ingestion Behavioral Contract Identities

- Work ID: semantic-ingestion-behavioral-contract-identities-2026-08-02
- Work type: design
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-08-02
- Last updated: 2026-08-02
- Parent WorkPlan: docs/work/semantic_ingestion/m3-temporal-trust-resolution-2026-08-02/design.plan.md
- Related WorkPlans: docs/work/semantic_ingestion/implementation.plan.md
- Canonical inputs: docs/design/semantic_ingestion_architecture.md; memorii/memorii/core/semantic_ingestion; memorii/memorii/core/provider/ingestion.py
- Expected outputs: approved behavioral identity map; revised canonical design; linked implementation WorkPlan

## Objective

Remove delivery-milestone names from every new semantic-ingestion public Python
symbol, persisted schema identifier, digest domain separator, codec identity,
record/source identity, test artifact, and current-state description before the
unshipped contract becomes externally depended upon. Retain independently
meaningful schema version numbers such as `.v1`.

## Completion Contract

The design operation is complete only when the canonical design defines a
closed old-to-new identity map, migration/compatibility semantics, authority
regeneration consequences, and an exact verification matrix; independent
specification, correctness, and test reviews report no unresolved validated
P1/P2 or approval-required finding; and the closure arrays are empty.

## Scope

Included: identities introduced across governed source admission, writer-safe
preplanning persistence, and semantic candidate-to-terminal resolution,
including `memorii.m3.*`, `memorii.semantic-ingestion.m3.*`, every M1/M2/M3
public/private Python symbol or runtime label, milestone-named tests/support
files/fixtures/CI steps, requirement IDs used as test or product names (for
example `R22`), generated or frozen artifacts containing derived identities,
and normative design text that names these as durable contracts.

Excluded: historical WorkPlan chronology; genuine protocol version suffixes;
domain concepts that independently use words such as `milestone`; requirement
IDs represented as typed data inside the traceability registry/checker and
their explicit malformed-input tests; prompt-domain requirement IDs; algorithm
names such as BM25; M4 replay behavior; compatibility aliases for an unshipped
contract.

Deferred: removal of historical milestone narration from archived design and
WorkPlan evidence where it does not define a current identifier.

## Constraints And Invariants

- The product is unshipped, so old milestone-derived bytes are rejected rather
  than upcast or accepted through aliases.
- Behavioral names must identify contract purpose, not delivery sequence.
- Digest domains remain unique and versioned.
- Regeneration must follow the existing design/registry/authority chain; frozen
  bytes may not be hand-edited.
- Candidate/committed, structural/overlay, provider/domain validation, and M4
  replay boundaries remain unchanged.
- Existing user edits and the bounded CI test-store compatibility correction
  are preserved.

## Sources Of Truth

Precedence follows root `AGENTS.md`. The immediate authorities are
`docs/design/memorii_spec.md`, `docs/design/memorii_storage_details.md`,
`docs/design/event_model.md`, `docs/IMPLEMENTATION_RULES.md`, and
`docs/design/semantic_ingestion_architecture.md`, followed by production code,
generated artifacts, and tests as implementation evidence.

## Current State

Verified facts:

- Production contains 63 unique `memorii.m3.*` digest/schema identifiers, one
  `memorii.semantic-ingestion.m3.v1` envelope, and one
  `memorii.semantic-ingestion.m3.closed-codec.v1` fingerprint.
- Production exposes milestone-derived classes, aliases, errors, services, and
  private helper names across semantic ingestion and provider composition.
- Three milestone-named test files/support modules have already been renamed to
  behavioral names; their 54-test suite and deterministic 2,584-test shard plan
  pass.
- These contracts are unshipped and therefore need no compatibility alias.

Interpretation: preserving milestone identities now creates avoidable public
API and persisted-byte migration debt.

## Assumptions And Open Questions

Verified: `.v1` is a real contract version and remains. Working assumption:
the canonical namespace is `memorii.semantic-ingestion.<behavior>.v1` and the
closed envelope is `memorii.semantic-ingestion.contract-envelope.v1`.
Unresolved: none requiring external input. External decisions: none.

## Milestones Or Experiments

1. Identity inventory and authority-chain map. Status: complete. Produce a
   closed mapping and distinguish normative identifiers from historical prose.
2. Canonical design revision. Status: complete. Specify rejection of old bytes,
   regeneration, rollback, and verification.
3. Independent design review. Status: complete. Run specification, correctness,
   and test review and reconcile findings.
4. Design closure and implementation handoff. Status: complete. Freeze the
   approved map and create a separate linked implementation WorkPlan.

## Progress Log

- 2026-08-02: User identified that preserving `memorii.m3.*` would make later
  correction harder. Confirmed the concern and broadened the inventory to all
  current semantic-ingestion milestone-derived contract and symbol identities.
  Next action: freeze the complete behavioral replacement map.
- 2026-08-02: Three independent read-only inventories confirmed 63 digest
  domains, two codec/envelope identities, 20 named Python owners, and additional
  lease, member-ID, discriminator, admission-revision, provider-fingerprint,
  thread-label, CI-label, test-fixture, and scenario-coordinate families. The
  canonical design now specifies a closed hard-cutover map, old-byte rejection,
  no aliases, regeneration ownership, rollback, and acceptance checks. Next
  action: independently review the coherent design delta.
- 2026-08-02: User expanded scope to M1/M2 debt and requirement-ID leakage such
  as `R22` in production and tests. The prior design review was interrupted.
  A repository-wide classified audit and linked testing WorkPlan are now
  required before the coherent design can be reviewed.
- 2026-08-02: Expanded audits classified the full current surface. The design
  now removes M1/M2/M3 and C2 from public symbols, runtime/persisted values,
  positive fixtures, executable test/command/group names, CI labels, and
  diagnostics. Stable `SIA-Rxx`/`SIA-T-*` identifiers remain only as typed
  traceability metadata and explicit negative vectors. Next action: run a fresh
  independent review of the expanded coherent design.

## Evidence Log

- `rg` inventory over production found 63 unique `memorii.m3.*` identities,
  two milestone-derived semantic-ingestion codec/envelope identities, and the
  `M3*` symbol family.
- Renamed-test verification: `54 passed in 189.44s`; shard verification reports
  `collected: 2584`, counts `[12, 1026, 718, 828]`.
- Read-only correctness and test inventories identified non-prefix persisted
  values (`m3_graph_delta`, lease coordinates, member IDs, terminal-plan kinds,
  writer-admission revision, and provider fingerprint) and the runtime frozen
  JSONL oracle that must be regenerated through execution.

## Decision Log

- 2026-08-02: Reject compatibility aliases. Alternative: retain old names and
  migrate later. Rejected because the contract is unshipped and aliases would
  make milestone language permanent.
- 2026-08-02: Retain `.v1` suffixes. They express contract versions rather than
  implementation milestones.

## Review Log

Inventory review round: `spec_auditor`, `correctness_reviewer`, and
`test_reviewer` supplied direct repository maps. Coordinator disposition:
confirmed the complete identifier families; rejected the correctness review's
deprecated-alias suggestion because the governing design explicitly treats the
candidate-to-terminal contract as unshipped and the user requested removal
before debt hardens. No inventory finding is a blocker; the coherent design
delta now requires independent review.

Expanded inventory round: the three reviewers confirmed two M2 persisted
identities, 66 M3 digest domains plus non-prefix persisted/runtime families,
24 requirement-named integration nodes, requirement-derived executable
group/command/acceptance-node identities across R01-R23, two CI display names,
positive fixture labels, and scenario-C2 authority coordinates. Coordinator
disposition: confirmed and incorporated. Stable requirement/test IDs inside
typed traceability metadata are retained; executable uses are renamed.

Expanded design review round 1 produced three convergent changes-required
families. `DREV-001` identified overlapping and incomplete C2 rewrite rules;
confirmed and remediated with a total disjoint grammar covering bare,
hyphenated, slash, M1/M2, format, release, history, and revision forms plus an
exactly-one-match proof. `DREV-002` identified missing retention/regeneration
detail; confirmed and remediated with the explicit 24-node rename table, closed
family matrix, field-aware allowlist contract, and independently regenerated
public-wire vector. The spec review also identified active normative milestone
prose; confirmed and behaviorally reworded at the live trust, admission,
resource, lifecycle, result-access, temporal-binding, durable-owner, and
write-schema boundaries. Fresh delta review is required.

Final delta reviews closed the scenario grammar, active prose, exact context
allowlist, canonical requirement-universe owner, and independent scenario
coordinate oracle. The specification, correctness, and test reviewers report
no residual P1/P2, blocks-approval, or changes-required finding.

```yaml
reviewed_revision: 7b5313a0d4953510258acec4818f4b595ce6278f
tested_revision: not_applicable (design operation; deterministic implementation gates belong to the linked implementation)
tree_state: dirty, nine porcelain entries, design SHA-256 c065b7a7e3a71d6c9be5be7dbe0c5a99175f0fdf99b34c7217bcadb07195ae25
workflow_identities: [.github/workflows/pr-gates.yml]
ci_event: not_executed
ci_executed_sha: not_applicable
ci_executed_ref: not_applicable
remaining_validated_p1_p2: []
remaining_blocks_approval: []
remaining_changes_required: []
local_ci_parity: design review and git diff --check only
acceptance_gate_inventory: [CTV authority, CGS generation, scenario authority, traceability acceptance, exact semantic selector, unit shards, static analysis]
github_run_urls: []
pr_head_sha: 7b5313a0d4953510258acec4818f4b595ce6278f
pr_base_sha: 42671e90f35edfc006583e5ddf889927d2602717
merge_base_sha: 42671e90f35edfc006583e5ddf889927d2602717
required_checks_green: false (implementation not yet published)
```

## Blockers And Limits

No current blocker. Historical prose is not rewritten unless it asserts a
current normative identity. M4 behavior remains out of scope.

## Next Action

Implement the approved behavioral-identity cutover through the linked
implementation WorkPlan.
