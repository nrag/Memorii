# Observation replay/checkpoint contract worker report

## Scope

Added the six profile-3 replay/checkpoint body models in
`memorii/memorii/core/memory_evolution/observation_replay_contracts.py`:

1. `ObservationReplayState`
2. `IngestionObservationReplayCheckpoint`
3. `ObservationCheckpointLifecycle`
4. `ObservationCheckpointSigningPreimage`
5. `ObservationCheckpointPublicationReceipt`
6. `ObservationCheckpointBundle`

The models use the existing `ObservationLedgerHead`, `ObservationLedgerEntry`,
and canonical native ingestion-record union. They are frozen, strict, and
closed to unknown fields. Only replay state and bundle carry the source-defined
body `schema_version`; checkpoint, lifecycle, preimage, and receipt do not add
one.

## Determinate validation

The new validators enforce direct coordinates that the approved contract makes
local and determinate: ledger head/entry sequence and tail coordinates, entry
predecessor links, ordered unique native record identities, replay-state and
bundle repository/activation joins, checkpoint/head/state/lifecycle joins,
receipt joins, and the genesis lifecycle predecessor shape. The signing
preimage also joins its supplied head and lifecycle to its checkpoint fields.
Checkpoint and preimage `created_at` values must be timezone-aware UTC; the
state tail also joins the final entry's `observation_revision_after` to the
head revision.

`test_observation_replay_contracts.py` constructs an actual native terminal
group delta, canonical records, ledger entry/head, state, lifecycle,
checkpoint, receipt, and signing preimage. Negative coverage rejects a
substituted receipt checkpoint coordinate, invalid genesis predecessor,
boolean schema version, non-UTC timestamps, and a substituted tail revision.

## Evidence

Executed without pytest (coordinator owns test execution):

```text
PYTHONPATH=memorii .venv/bin/ruff check memorii/memorii/core/memory_evolution/observation_replay_contracts.py memorii/tests/unit/core/memory_evolution/test_observation_replay_contracts.py
PYTHONPATH=memorii .venv/bin/pyright --pythonpath .venv/bin/python memorii/memorii/core/memory_evolution/observation_replay_contracts.py memorii/tests/unit/core/memory_evolution/test_observation_replay_contracts.py
```

Both completed with no findings. A direct non-test import and construction of
the complete typed checkpoint bundle also passed.

## Deliberate boundary

These are source-package shapes only. They do not calculate or validate the
profile-3 checkpoint, receipt, bundle, state, lifecycle-authority, or ledger
self-digests; validate signatures; resolve lifecycle history; sign; replay;
or perform CAS/publication/persistence. Those actions remain with the future
protected registry, authority, decoder, and store owners. No legacy digest
algorithm or numeric-wire codec was introduced.
