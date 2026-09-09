# Public Observation Binding Preflight

Baseline: 7a92bce208ecfb7d8ff199e629edb09f663d1948. Read-only Spark mapper:
public_observation_bindings. Root inspected the actual callsites before writing.

The mapper's approximate line numbers, invented lock names, duplicate read-only
class description and claim that provider activation is private are rejected.
The corrected map below is the implementation authority, not its raw summary.
Searches: `rg -n 'def read_write_snapshot' memorii/memorii`, provider/capability
constructor searches, and direct reads of all listed callsites.

| Requirement | Trigger / exact baseline callsite | Validation -> read -> outcome | Caller evidence / state |
| --- | --- | --- | --- |
| R17,R19 snapshot time | graph_observation_paging.py:256 and :322 | authenticated context/current grant -> MemoryPlaneService.read_write_snapshot -> detached cohort collaborator -> registered snapshot/page | Two first-page callers; created_at currently uses earlier auth time, correction required |
| R17,R19 atomic inventory | memory_plane/service.py:170 -> store.py:356 / :613 | InMemory `_lock`; JSONL `_locked(exclusive=False)` and `_current_records_unlocked` -> cloned records and full write revision | Service delegate has one backend dispatch; both backends need additive timed API inside these locks |
| R17 authority boundary | memory_plane/unit_of_work.py:121; store.py:383 | UoW rejects root snapshots; ReadOnly currently inherits ordinary full-write snapshot | Both must reject new timed snapshot before clock; existing snapshot API unchanged |
| R19 detached authority | atomic_store.py:8494 | explicit revision/records/time -> ReadOnly snapshot store -> ledger replay, immutable group requests, graph delta verification, graph/reference/event reconstruction | Zero production callers; internal tests only; public integration remains absent |
| R19 provider composition | provider/service.py:505,:559,:632 and semantic_ingestion/capability.py:405,:502 | composed authorized ingestion runtime -> same canonical atomic store and registry authority | Provider activation exists; public graph/time observation methods and concrete cohort provider do not |

The new timestamp is host-clock authority sampled while writes are excluded.
It is not request time or a persisted commit attestation. No callback is added
to public requests. A detached inventory cannot resample a timestamp and claim
the live backend's atomic authority.

Required path proof: two backend contention tests, service forwarding,
UoW/read-only denial, both first-page paths using the locked timestamp, unchanged
full-write continuation fences. These prove only the timed runtime component;
the public endpoint still requires a concrete complete materializer and host.
