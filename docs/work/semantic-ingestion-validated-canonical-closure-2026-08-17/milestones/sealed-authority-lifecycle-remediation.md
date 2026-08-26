# Sealed Authority Lifecycle Remediation

- Parent WorkPlan: `../implementation.plan.md`
- Status: active, bounded correction recorded
- Base revision: `b9daf00a0e6956e51106756f1baaf23190c688bb`
- Scope: private canonical-evidence lifecycle owner, repository-owned terminal
  dispatcher, and focused production-root proof

## Requirements And Boundaries

This slice corrects ambient pre-seal reuse, process reservation capacity, and
linearized terminal cleanup. It is partial for `VCC-R01` through `VCC-R12`:
it does not establish traversal-issued member spans, producer-to-writer typed
authority propagation, writer/replay proof, performance reduction, CI, or a
frozen candidate.

The canonical owner is
`memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py`.
No public or persisted schema changes are made. Disabled and capacity-refused
operations retain the existing full path; rejection creates no sealed lookup
authority.

## Implemented Behavior

- Process capacity is 67,108,864 bytes with 16,777,216-byte reservations, so
  four operations reserve and the fifth refuses; a later operation reacquires.
- Staging accepts only pre-seal admissions. Ambient lookup is rejected and the
  codec no longer imports or calls an ambient accessor. Codec staging is an
  explicit typed parameter; ordinary codec calls always validate fully.
- The typed-value codec now emits exact paths/spans while writing the canonical
  bytes. Each span is copied into compact member evidence, so equal values stay
  unambiguous by their traversal paths without a post-hoc byte search.
- Sealed lookup requires the same object-identity `CanonicalBinding` plus exact
  tenant, operation, generation, fence, and writer coordinates and returns an
  immutable releasable lease.
- Admission, close, lease release, terminal latching, reservation release, and
  emission are serialized by the owner lock. Every sealed lookup receives a
  unique private token, so equal cache keys can drain in any order without
  aliasing. The first close cause is latched while outstanding leases drain.
- `ProviderMemoryService` owns one repository retaining dispatcher and injects
  it into direct, composite, and memory-write arenas. It receives only a typed
  content-free snapshot. Sink failures, unavailable outcomes, and malformed
  return values map to unavailable and do not alter closure or product state.
- Terminal metrics preserve counts after payload clearing and remain
  content-free typed snapshots.
- The prepared-source writer-handoff family now stages the revalidated prepared
  contract, seals after its persisted generation and current writer admission
  are known, leases exact bytes through `bootstrap_writer_handoff`, and releases
  in the coordinator `finally`. The atomic owner revalidates the loaded object,
  scope (including authenticated tenant), current writer, digest, and member
  evidence before using lease bytes.

## Evidence

Working directory: `memorii/`

```text
../.venv/bin/python3.12 -W error -m pytest tests/unit/core/semantic_ingestion/test_canonical_evidence_arena.py -p no:cacheprovider
29 passed in 9.94s (deterministic lifecycle, multi-lease, terminal, privacy,
and unavailable-sink arena proof)

../.venv/bin/python3.12 -m ruff check memorii/core/semantic_ingestion/canonical_evidence_arena.py tests/unit/core/semantic_ingestion/test_canonical_evidence_arena.py
All checks passed

../.venv/bin/python3.12 -W error -m pytest tests/unit/core/semantic_ingestion/test_bootstrap_graph_coordinator_v3.py::test_verified_production_root_leases_prepared_bytes_into_writer_handoff -p no:cacheprovider
1 passed in 32.72s

../.venv/bin/python3.12 -W error -m pytest tests/unit/core/test_provider_service.py::test_default_provider_composition_is_source_admission_only -p no:cacheprovider
1 passed in 9.34s
```

Focused tests prove pre-seal rejection, post-seal admission rejection, all five
coordinate mutations, fifth reservation/reacquisition, deterministic multi-lease
close/release, duplicate/stale/foreign release rejection, all supported terminal
reasons, content privacy, unavailable-sink parity, and disabled/refused full-path
behavior.

`build_production_entrypoint_bindings_v11.py` regenerated the v11 ledger and
oracle from the stabilized sources. The v11 validator passed all 32
source/contract mutations; it binds the explicit owner, staging, seal, lookup,
lease, and atomic tenant/writer checks and rejects the removed ambient/nonce
tokens. This is source-shape evidence for the prepared-source family only.

## Production Entrypoint Binding Ledger

| Requirement | Non-test caller | Authority proof | Status |
| --- | --- | --- | --- |
| lifecycle owner | `ProviderMemoryService.sync_event` | constructs the private arena and hands it explicitly to ingestion | partial, production-root test + v11 |
| prepared-source coordinator/writer | `ProviderIngestionCoordinator._bootstrap_prepare_and_handoff` | stages, binds/seals, leases, and calls `bootstrap_writer_handoff`; atomic checks tenant/operation/generation/fence/writer | partial, 19 focused tests + v11 |
| replay and other durable consumers | ordinary provider pipeline | no family-complete sealed lease proof | incomplete |

The prepared-source writer-handoff row is partial; replay and all other durable
consumers remain incomplete. Candidate v1 is superseded by this remediation and
must not be used as a current candidate.

## Candidate Freeze

Implementation candidate v1 remains the prior scoped dirty-tree freeze, not the
approved `candidate-manifest-v12.json` design lock. It is superseded by the
multi-lease and dispatcher edits; no replacement freeze is claimed in this
slice.

## Redelivery Evidence

`test_verified_production_root_redelivery_uses_a_fresh_sealed_lease` drives two
exact public-root deliveries of one admitted source. It records distinct arena
owners/capability issuers, two fresh leases, `started` then `already_started`,
fresh writer reads, immutable prepared/marker records, rejected substitution of
the released first lease, and terminal reservation release for both owners.
The atomic idempotent-marker return now follows loaded prepared-byte, scope,
lease-liveness, and current-writer checks. This proves only prepared-source
redelivery; replay terminal/persistence and other durable families remain
incomplete.

## Identity And Delegation Ledger

- Authority identity: the sealed lease carries tenant, exact operation,
  generation, fence, and writer digest/epoch; no nonce or ambient context is a
  binding coordinate.
- Evidence identity: `test_verified_production_root_leases_prepared_bytes_into_writer_handoff`
  proves the real production-root prepared-source family; it does not prove
  replay or sibling durable families.
- Delegation: code-mapper consultation supplied caller/source mapping;
  test-review consultation supplied the focused proof boundary; this agent is
  the sole writer for the overlapping remediation artifacts.

## Round-One Findings And Remaining Gaps

- Confirmed: duplicate-key multi-lease aliasing was a real lifecycle leak; the
  private-token correction is locally verified.
- Confirmed: observability was success-shaped at the composition root; the
  repository-owned dispatcher correction is locally and production-root
  verified. The related test-coverage finding is duplicate and not separately
  counted.
- Remaining partial: recovery/replay, composite, memory-write, Hermes, and
  other durable consumers; all-root entrypoint proof; performance reduction;
  candidate refreeze and independent audit. This slice does not claim them.

## Next Action

Map one recovery or replay root with a fresh private owner and an exact durable
consumer before extending the closure to the remaining trigger families.
