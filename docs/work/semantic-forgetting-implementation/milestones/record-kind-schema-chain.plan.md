# Milestone: record-kind-schema-chain

- Parent: docs/work/semantic-forgetting-implementation/implementation.plan.md
- Requirements: FGT-R1, FGT-R12
- Status: pending
- Base revision: 4780db61

## Purpose

Land the `revocation_directive` record kind with its complete schema,
codec, and publication authority chain so later milestones can author and
replay directives through the normal machinery.

## Bounded Scope

- `GraphRecordKind` closed union + `revocation_directive`; canonical owner
  `graph_records.py`; the duplicate declaration in `event_replay.py`
  collapses to an import of the canonical owner.
- `RevocationDirectiveRecord` model (design §6.1) + the closed
  discriminated target union (`EntityRevocationTarget`,
  `ClaimRevocationTarget`, `SourceRevocationTarget`,
  `RecordRevocationTarget`) — frozen, strict, extra="forbid",
  content-free fields only.
- The four per-kind tables: `CommittedRecord`,
  `NonOwningGraphRecord`, `_CARRIER_UNION_MEMBER_TYPES`, `graph_record_id`
  names map.
- `canonical_graph_codec_manifest()` entry; typed failure for the
  snapshot's `codec_by_kind` lookup on a missing entry.
- `generated_reference_schema_manifest` edges for the directive's target
  references; `advance_reference_integrity`/`extract_reference_edges`
  learn the kind.
- Event envelope schema: `memorii.semantic-memory-event.v2` current write;
  v1 deprecated-readable via identity upcaster; registry history
  monotonic; new batches pin the new registry revision.
- Typed-value publication regeneration via
  `memorii/scripts/generate_observation_registry_publication.py`; release
  candidate repinned LAST.

## Expected Artifacts

Changed production: `core/memory_evolution/graph_records.py`,
`core/semantic_ingestion/event_replay.py`,
`core/memory_evolution/reference_integrity.py`,
`core/memory_evolution/atomic_store.py` (codec lookup typed failure only).
Regenerated: `core/memory_evolution/observation_registry_sources/**`,
`docs/work/semantic_ingestion/observation-ledger/release-preparation/candidate.json`
(+sidecar). New tests: strict-model rejection, manifest totality, registry
monotonicity + upcaster replay, codec identity map, reference-edge
extraction.

## Non-Goals

No governance entry, no view, no tombstones, no control-plane changes
(later milestones). No change to the fold.

## Acceptance Criteria

1. A `revocation_directive` record passes `_GraphRecord` self-validation,
   envelope validation (`SemanticMemoryEventPayload` create), the fold
   (materializes like any record), and `graph_record_id` returns
   `revocation_id`.
2. Unknown fields/kinds/target variants reject under strict validation;
   a manifest missing the codec entry produces the typed failure (not a
   raw KeyError).
3. Registry history: replaying a v1 batch under the v2 registry works via
   the identity upcaster; a batch pinning an absent registry coordinate
   fails closed.
4. Reference ledger: directive target edges extract and the ledger
   reconciles against replay (existing integrity checks stay green).
5. Publication regenerated via the authoring script only; decoder-source
  manifest, publication manifest, role artifacts, and registry.json
  consistent; candidate repinned; publication/registry verification
  scripts pass.
6. Focused unit tests green; full local unit suite + ruff + pyright green
   at the milestone head.

## Verification Commands

From `memorii/`: `.venv/bin/python -W error -m pytest tests/unit -p
no:cacheprovider -k "revocation or event_replay or graph_records or
reference_integrity or observation_registry"`, then the full gates
(unit suite via shards if needed), `ruff check memorii tests`, `pyright`.
Publication regeneration per the script's documented invocation; candidate
reproduction checks per the release-preparation packet.

## Identity Ledger Additions

All new names behavioral (see index ledger). No planning coordinates.

## Progress

- 2026-10-03: packet opened; awaiting code-mapper preflight before the
  first writer edit.
- 2026-10-03 (M1a slice — grammar extension, no schema-version change):
  preflight frozen (../preflight-bindings.md). Landed: `revocation_directive`
  in `GraphRecordKind` (canonical owner graph_records.py; event_replay's
  duplicate Literal collapsed to an import); `RevocationDirectiveRecord` +
  target union (`EntityRevocationTarget`/`ClaimRevocationTarget`/
  `SourceRevocationTarget`/`RecordRevocationTarget`) + `RevocationClosureCoordinate`
  with canonical-ordering, closure-digest, and content-free-field
  validators; the four per-kind tables (NonOwningGraphRecord union,
  CommittedRecord via NonOwning, `_CARRIER_UNION_MEMBER_TYPES`,
  `graph_record_id` map); codec manifest entry (totality auto-extends) and
  typed `_graph_codec_entry` failure in atomic_store; reference-schema
  manifest entry (`revoked_targets[].logical_entity_id`, logical, many,
  logical_projection_key) + extractor branch. Fixture:
  `all_canonical_graph_records` gains the directive so the all-kinds
  fold/checkpoint-tail/genesis-replay test exercises it (counts 12→13,
  13→14). New suite
  tests/unit/core/memory_evolution/test_revocation_directive_record.py
  (6 tests: union/manifest totality, roundtrip, snapshot binding, target
  variants + edges, strict rejections incl. content-free field-set
  assertion). Smoke + focused suites + ruff repo-wide + scoped pyright
  green.
- Verification posture for the M1a slice: broad-dir runs
  (tests/unit/core/memory_evolution +
  tests/unit/core/semantic_ingestion) are multi-hour locally; per the
  cost-awareness rule the broad gates run ONCE at the milestone candidate
  revision (after M1b + publication regeneration), not after each
  sub-slice. Focused evidence for this slice: the four directly pinned
  suites green (test_event_replay.py incl. the extended all-kinds
  fold/checkpoint/genesis test; test_identity_lineage_prerequisites.py;
  test_graph_observation_native_projection.py; the new directive suite),
  ruff repo-wide, scoped pyright (0 errors), plus a partial broad run
  (~20% of both dirs, all green, before being stopped as multi-hour;
  the known-slow test_canonical_evidence_production_limits.py excluded
  per the environment-sensitive known-failure note). Slice committed;
  milestone remains open until M1b + regen + broad gates.
- Sequencing decision: the envelope schema v2 mint (with the v1 identity
  upcaster and the persisted-history compat cascade — registry-1 must stay
  byte-identical as a history prefix, the upcast decision must consult the
  current registry, and the read-side equality checks at atomic_store
  :7100/:8825 must become prefix-tolerant) is split into M1b, executed
  after the behavior milestones so a compat surprise cannot strand the
  grammar work. Design §6.10 ordering supports this (registry item 5,
  after the governance entry). Publication regeneration + candidate repin
  run once, after all production edits settle (repin LAST constraint).

