# Exact Manifest And Checkpoint Acquisition

- Work type: debugging
- Fidelity: Level 2 diagnostics for the Level 3 capacity gate
- Baseline: `1d061699`, `codex/durable-delivery-implementation`
- Related: [raw verification](raw-verification.plan.md)
- Status: exact manifest and replay optimizations verified. Startup qualification remains open.

Reduce manifest and signed checkpoint replay work on both retained v8 fixtures. Keep v7 default, exact root and member digests, all committed row bytes, signature and prefix verification, replay index parity, duplicate rejection, and replay state equality. The five-second budget measures acquisition after service construction. Full release qualification is separate.

## Discriminating Measurements

Independent cold copies on the native Mac with zero resident main-file pages reproduced the original signed heads. The three replay binding catalogs took 1.80 s on balanced and 1.72 s on concentrated. Solver nodes took about 0.49 s per fixture. The complete signed checkpoint start took 1.26 s and 1.23 s, including about 0.33 s of typed parsing and 0.29 s of member digest calculation. Live replay-binding materialization took about 0.13 s. The checkpoint signature, prefix, anchor and final-state checks remain mandatory.

Test a sequential read with an independent covering primary-index parity check for the three binding catalogs. Preserve SQLite ordering and the same row and Merkle digest framing. For replay, use a lighter strict typed representation for checkpoint bindings, validate each tail event state once, and stream live binding comparisons against the expected indexes, consuming each identity once so duplicates, omissions and mismatched payloads still fail.

The balanced pilot took 1.68 s across the three catalogs using a sorted base walk and separate comparison of the index's keys and rowids. The preceding ordinary profile took 1.80 s. The production change uses this walk only for staged v8 and still computes the same signed roots from base rows. Checkpoint bindings retain strictly validated fields, ordering, canonical serialized bytes and signed digest framing. Replay consumes exact live bindings with no second live dictionary and shares each tail event's typed validation between binding and projection checks.

## Installed Results

The [paired measurements](manifest-replay-comparison.jsonl) used the [existing cold comparison runner](measure_raw_verification.py) on the native Mac. All eight fresh subprocesses and independent copies began with zero resident main-file pages, selected checkpoint replay, and verified their original signed qualification head. Two pairs per distribution alternated ordering. The baseline wheel SHA-256 was `ab424903740ba728dffa520e5ab7e3c5efdcc347be48b3a32f3db4e7da9e8249`. The candidate wheel SHA-256 was `e5686aca067eb6152791c150f7bb3eb82616a0c9ea2f997cf6187cd468441beb`.

| Fixture | Manifest excluding raw, median | Checkpoint and replay, median | Startup acquisition, median |
| --- | ---: | ---: | ---: |
| Balanced | 3.130 to 3.058 s | 1.831 to 1.590 s | 9.455 to 8.984 s |
| Concentrated | 3.205 to 3.122 s | 1.687 to 1.545 s | 9.147 to 9.011 s |

The fastest acquisition was 8.826 s, leaving 3.826 s to the five-second gate. The candidate's service construction plus acquisition took 10.107-10.392 s. The raw verifier was unchanged and raw timing differed between the paired arms. The figures measure startup on the retained macOS fixtures. Linux and the rest of the release matrix remain open.

## Verification

The installed candidate passed 96 focused tests with warnings treated as errors. The tests include independent covering-index mutation in all three staged replay binding indexes, malformed checkpoint bindings, legacy binding serialization parity, independent live replay mismatch checks, checkpoint-anchor and genesis replay, raw upgrade, restore, recovery, and incremental manifest parity. The checkpoint integration spy now observes parsing of the anchor and tail so it still proves that the prefix is skipped. Independent correctness and test review found no validated production P1/P2 issues and identified these verification additions. Ruff and whitespace checks passed.

## Next Action

Design a way to reduce full acquisition work under the same integrity contract. The measured raw scan and remaining manifest alone take more than the five-second budget.
