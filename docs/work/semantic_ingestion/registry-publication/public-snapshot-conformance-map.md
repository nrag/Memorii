# Public Snapshot Conformance Map (Profile-3)

## Scope
Bounded, read-only mapping for public snapshot/cohort/cursor/page/time-attestation profile-3 surface and the legacy cursor preservation boundary. Design/doc contracts are treated as normative; runtime behavior is confirmed only where explicit source evidence exists.

## Evidence set (exact files)
- `docs/design/semantic_ingestion_observation.md`
- `docs/work/semantic_ingestion/observation-ledger/replay-snapshot-contract.md`
- `docs/work/semantic_ingestion/observation-ledger/schema-publication.md`
- `docs/work/semantic_ingestion/observation-ledger/readiness.md`
- `docs/work/semantic_ingestion/engineering-closure/observer-contract-map.md`
- `docs/work/semantic_ingestion/observation-ledger/entrypoint-verification-matrix.md`
- `docs/work/semantic_ingestion/registry-publication/model-inventory-map.md`
- `memorii/memorii/core/memory_evolution/graph_observation_contracts.py`
- `memorii/memorii/core/memory_evolution/graph_observation_cursor.py`
- `memorii/memorii/core/memory_evolution/graph_observation_records.py`
- `memorii/memorii/core/memory_evolution/graph_observation_streams.py`
- `memorii/memorii/core/memory_evolution/semantic_state.py`
- `memorii/tests/unit/core/memory_evolution/test_graph_observation_foundation.py`

`model-inventory`/doc SHA snapshots:
- `docs/design/semantic_ingestion_observation.md`: `7d790c9233b43eb78357cd6df1ed5547beb5e24ec8a2283e655216c90bcf3113`
- `docs/work/semantic_ingestion/observation-ledger/replay-snapshot-contract.md`: `324c15fba3e3648a6b6150b3b3546765aaab709d2c7a00942fccc4af8acea345`
- `docs/work/semantic_ingestion/observation-ledger/schema-publication.md`: `2511a659a042cfd70ae4bdbbe75cb43f2e8b8153c380c02f8e867f4b0a05387a`
- `docs/work/semantic_ingestion/observation-ledger/readiness.md`: `5c432bb89464b3dc41bf42e7c2b458cd1d9033cf56710a0121ff73096b5ded36`
- `memorii/memorii/core/memory_evolution/graph_observation_contracts.py`: `f2749a0b312b03f4f29833fd3adec0f110166b2271bb39cf088aac616f2406a8`
- `memorii/memorii/core/memory_evolution/graph_observation_cursor.py`: `be0b09d45b4fe26143ae22a54b9371308924a8f3558adfd261b2f04617b130f5`
- `memorii/tests/unit/core/memory_evolution/test_graph_observation_foundation.py`: `dffb50913959ba5b315b896373061fa8ca67e95f0d28d3aea22e7d696431a80c`
- `docs/work/semantic_ingestion/registry-publication/model-inventory-map.md`: `772f459c0b45501d19d71018a67197b931de15734cd2336ecf2eafa14d36cdeb`

## Canonical model closures required in profile-3

| Model root | Required profile-3 shape | Canonical owner (if present) | Native dependency path | Producer/consumer status (runtime + tests) | Conformance status |
| --- | --- | --- | --- | --- | --- |
| `GraphObservationCohortPreimage.v1` | Complete new `ResolvedGraphObservationCohort` field set minus `cohort_digest`, including: `graph_revision`, `observation_revision`, `memory_plane_write_revision`, `temporal_projection_generation_digest`, `temporal_projection_pointer_digest`, `trust_projection_generation_digest`, `trust_projection_pointer_digest`, `observation_schema_fingerprint`, `changed_record_keys`, `boundary_record_keys`; no self-digest | `missingtarget-only` (N/A) | `ResolvedGraphObservationCohort` from `graph_observation_contracts.py:171` + native projections from `semantic_state.py` + `projection_history.py` per replay prose | No callsites found | Missing runtime type + no registry binding |
| `GraphRecordObservationSnapshot.v1` | `schema_version`, `snapshot_token`, protected creation time, `memory_plane_write_revision`, `authenticated_context_digest`, `purpose` (`graph_observation`), `authorization_decision`, cursor-free request coords, `cohort_preimage`, `resolved_cohort`, immutable stream | `missingtarget-only` (N/A) | `GraphObservationRequestCoordinates` and `GraphObservationCohortPreimage` + native projection selectors (`ProjectionHistoryRepository.current/historical`) + canonical records from detached snapshot | No callsites found | Missing root + no persistence path |
| `IngestionTimeObservationSnapshot.v1` | Same root shape as above with `purpose='ingestion_time_attestation'` and `ProductionIngestionTimeAttestation` stream | `missingtarget-only` (N/A) | `IngestionTimeAttestationRequestCoordinates`, `GraphObservationCohortPreimage`, native projection selection path | No callsites found | Missing root + no persistence path |
| `GraphObservationRequestCoordinates.v1` | Exactly `GraphObservationRequest` fields minus cursor; no additional fields | `missingtarget-only` (N/A) | `GraphObservationRequest` + page-policy request binding | No callsites found | Missing root + no decoder source |
| `IngestionTimeAttestationRequestCoordinates.v1` | Exactly `IngestionTimeAttestationRequest` fields minus cursor; no additional fields | `missingtarget-only` (N/A) | `IngestionTimeAttestationRequest` + page-policy request binding | No callsites found | Missing root + no decoder source |
| `GraphObservationRecordKey.v1` | Exactly record_kind and primary_key, per typed pair in observation design1409-1410 | `missingtarget-only` (N/A) | `GraphObservationStreamRecord`-style keying pattern implied by stream docs | No callsites found | Missing type; two-member shape is explicit in governing prose |
| `GraphObservationPage.v1` | Profile-3 stream record variant closure + cursor + cohort + snapshot token + page policy + `memory_plane_write_revision` + continuation preconditions | `missingtarget-only` (N/A) | `GraphObservationStreamRecord` union + cursor payload + snapshot/write-revision invariants | No production callsite in code | Missing root and method chain |
| `IngestionTimeAttestationPage.v1` | Same as above for attestation stream path | `missingtarget-only` (N/A) | Attestation stream + memory-plane snapshot closure | No production callsite in code | Missing root and method chain |
| `SourceRetentionTimeAttestation.v1` | Exact SIA field inventory at30211-30258; see coordinator correction below | `missingtarget-only` (N/A) | Native source-retention projection sources not present in this packet | No callsites found | Missing root + incomplete field spec in this pass |
| `TransactionGroupCommitTimeAttestation.v1` | Exact SIA field inventory at30211-30258; see coordinator correction below | `missingtarget-only` (N/A) | Native transaction-group commit provenance | No callsites found | Missing root + incomplete field spec in this pass |
| `SourceRetentionTimeWitness.v1` | Exact SIA field inventory at30211-30258; see coordinator correction below | `missingtarget-only` (N/A) | Native retention witness/pointer closure | No callsites found | Missing root + incomplete field spec in this pass |
| `GraphObservationCursorPayload.v1` | Existing fields + required nonnegative `snapshot_write_revision`; payload must be signed over complete fields except `signature`; continuation requires exact `snapshot_write_revision`/snapshot token replay checks | `memorii/memorii/core/memory_evolution/graph_observation_contracts.py:232` | Memory-plane full-write snapshot revision (`MemoryPlaneService.read_write_snapshot`) and authorizer context | Closure tests in `test_graph_observation_foundation.py` only; no production use | Present but missing profile-3 field `snapshot_write_revision` (`graph_observation_contracts.py:232` now ends at `system_as_of` then `signature`) |

## Legacy schema compatibility boundary

- `GraphObservationRecordKind` in current contracts includes `claim_projection` (`graph_observation_contracts.py:18-23`).
- `GraphObservationStreamRecord` union in `graph_observation_streams.py` includes `TemporalClaimProjectionStreamRecord` and `TrustClaimProjectionStreamRecord` (with no `claim_projection` variant), indicating partial profile-shift in stream payload types.
- Current cursor codec domain is hardcoded to `memorii.graph-observation.cursor.v1\0` (`graph_observation_cursor.py:23`) and accepts only version `v1` payloads (`graph_observation_cursor.py:74-76`).
- Design contract for profile-3 cursor signing domain is `memorii.graph-observation.cursor.v3` (schema-publication and replay contract sections), while existing code/docs evidence confirms legacy bytes must stay on existing route.

## production_entrypoint_bindings (boundary-only)

| requirement/behavior | production trigger | composition root | authority-bearing callsite + exact arg | validation | durable outcome | production caller count | fallback/bypass | evidence path |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Query public graph observation page | external `observe_graph` API | `ProviderMemoryService.observe_graph` (not yet defined in codebase) | _No callsite currently defined; `rg -n "def observe_graph"` returns no symbol_ | authorizer/registry/snapshot/continuation should be enforced per entrypoint matrix | No durable observation API behavior exists | 0 production callers (missing symbol) | none (no API entrypoint) | `docs/work/semantic_ingestion/observation-ledger/entrypoint-verification-matrix.md:21`, `docs/work/semantic_ingestion/engineering-closure/observer-contract-map.md:5`
| Query public ingestion-time attestations | external `observe_ingestion_time_attestations` API | `ProviderMemoryService.observe_ingestion_time_attestations` (not yet defined in codebase) | _No callsite currently defined; `rg -n "observe_ingestion_time_attestations"` returns no symbol_ | request-coordinate binding + page-policy + reauthorization should be enforced per entrypoint matrix | No durable attestation page behavior exists | 0 production callers (missing symbol) | none (no API entrypoint) | `entrypoint-verification-matrix.md:22`, `observer-contract-map.md:35-40`
| Cursor foundation (cryptographic wire, limits, continuation checks) | internal cursor issue/verify | `graph_observation_cursor.py` + `GraphObservationCursorCodec` | `decode()` and `GraphObservationCursorSigner.sign()` in same module | strict canonical decode, curve checks, continuation failure checks (`revoked_access`, `stale_cursor`, `invalid_cursor`) | Token-level cursor issuance/verification only | 0 production callers; only local unit tests + module internals | test-only path can mint/parse cursors | `graph_observation_cursor.py:59-102`, `test_graph_observation_foundation.py:91-120`, `-130-137`, `-196-239`
| Profile-3 cursor payload write-revision binding | public page continuation | `GraphObservationCursorPayload` contract in `memorii/memorii/core/memory_evolution/graph_observation_contracts.py` | `GraphObservationCursorPayload.model_validate(...)` inside `GraphObservationCursorCodec.decode` and `GraphObservationCursorSigner.sign`; argument is full decoded payload dict | decode-stage model validation; continuation binding cannot check revision until `snapshot_write_revision` is present | Cursor continuity cannot enforce write-revision alignment; current behavior validates legacy fields only | 0 production callers (no public observation page runtime; closure tests only) | no fallback binding; continuation path treats revision as absent field | `graph_observation_contracts.py:232`, `graph_observation_cursor.py:59-102`, `test_graph_observation_foundation.py:91-120`, `test_graph_observation_foundation.py:130-137`, `test_graph_observation_foundation.py:196-239` |
| Legacy cursor route preservation | any profile-3 migration attempt | unchanged cursor schema route | retain `v1` route and `_CURSOR_DOMAIN` until explicit v3 implementation exists | historical compatibility preserved in code and doc note | no route migration yet | none | `graph_observation_cursor.py:23`, `:70-76`, `docs/work/semantic_ingestion/observation-ledger/replay-snapshot-contract.md:246`, `docs/work/semantic_ingestion/observation-ledger/schema-publication.md:276-283`

## Native dependency closure map (resolved + known)

- `ObservedTemporalClaimProjection` and `ObservedTrustClaimProjection` are implemented in `graph_observation_records.py` and embed native projection records + pointers from `semantic_state.py` (`TemporalProjectionRecord`, `TrustProjectionRecord`, `ActiveTemporalProjectionPointer`, `ActiveTrustProjectionPointer`) and enforce native chain constraints in model validators (`graph_observation_records.py:120-149`, `151-179`).
- `GraphObservationStreamRecord` is an alias in `graph_observation_streams.py` (type alias only; not a registry root) over profile-3-style stream record variants.
- `ObservedClaimProjection` is not the profile-3 request/page target in schema/docs (replaced by separate temporal/trust models in replay/snapshot design).
- `MemoryPlaneService.read_write_snapshot` exists and returns detached full-write snapshots (`memory_plane/service.py:170-173`), but there is no production callsite wiring it into graph observation paging in current code.

## Residual unknowns (bounded)

- Concrete field sets for `GraphObservationRecordKey.v1`, `SourceRetentionTimeAttestation.v1`, `TransactionGroupCommitTimeAttestation.v1`, `SourceRetentionTimeWitness.v1` are not fully enumerated in this packet and require the next authoring pass against source design rows and registry source.
- No production implementation for `observe_graph`/`observe_ingestion_time_attestations` exists yet; `observer-contract-map.md` and `entrypoint-verification-matrix.md` treat these as future interface obligations.
- The legacy `claim_projection` vs profile-3 projection-set split requires a single synchronized change in both contract and stream binding when the public observation service is implemented; today it is mixed in runtime contracts (`claim_projection` still in `GraphObservationRecordKind`) and stream payloads (`temporal`/`trust` variants only).

## Coordinator Source Correction

The mapper did not inspect the requested SIA field inventories. Its missing-field
notes are not design blockers. SourceRetentionTimeAttestation is at SIA30211,
TransactionGroupCommitTimeAttestation at30222, SourceRetentionTimeWitness at30243,
IngestionTimeAttestationPage at31472, and GraphObservationPage at31822. Their
exact declared fields govern; pages additionally gain memory_plane_write_revision.
GraphObservationRecordKey is the explicit (record_kind, primary_key) pair from
the observation supplement. Cohort preimage excludes cohort_digest; it must not
inherit the legacy self-digest field or validator. No extra request-coordinate
fields are authorized beyond the corresponding request minus cursor.
