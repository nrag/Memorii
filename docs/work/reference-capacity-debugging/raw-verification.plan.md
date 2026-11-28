# Exact Raw Payload Verification

- Work type: debugging
- Fidelity: Level 2 performance diagnostics for the Level 3 startup gate
- Baseline: `1f978b06`, `codex/durable-delivery-implementation`
- Related: [startup breakdown](debugging.plan.md) and [publication contention](../pinned-verification/design.plan.md)
- Status: raw scan optimization verified. The startup gate remains open.

## Target And Constraints

Reduce the time to verify each exact retained v8 qualification fixture and report the distance from the 5 s startup budget. Preserve v7 as the installation default. Keep SQLite's transaction and verification-cookie protections for every staged v8 body, size, codec and digest. Preserve the SHA-256 domain, bounded reads, reference closure, index parity, signed manifest and exact replay checks.

## Competing Causes And Discriminating Tests

The prior startup profile found 4.47-4.67 s in raw checks, including synchronous macOS read advice during the native layout comparison. Both retained fixtures contain 20,481 bodies and about 5.17 GB. Compare the ordinary SQL projection with a bounded SQLite BLOB read that avoids projecting the body. Separately compare serialized advice with concurrent and disabled advice. Use fresh copies with zero resident main-file pages and verify the original signed tuple on every run. Choose a product change only if the measurements show improvement.

An installed before-and-after wheel comparison on both native Mac fixtures records total acquisition, service construction, raw verification, the rest of the manifest rebuild, and replay. These diagnostics do not repeat the full release matrix.

## Balanced Fixture Pilot

Each exploratory arm used a fresh copy with zero resident main-file pages and returned the original signed balanced tuple. There was one observation per arm on the same installed baseline wheel.

| Isolated change | Raw verification | Acquisition |
| --- | ---: | ---: |
| Existing projected BLOB and synchronous advice | 5.35 s | 9.82 s |
| Direct BLOB reads with synchronous advice | 5.00 s | 9.59 s |
| Projected BLOB with overlapped advice | 4.77 s | 9.04 s |
| Projected BLOB with no advice | 4.21 s | 8.64 s |

The candidate combines ordered metadata with direct SQLite BLOB reads and removes the advisory subprocess. Before allocating a full body, the SQLite owner checks the actual BLOB length against the declared size, then hashes the body under the existing domain and budget. Larger bodies retain the existing streaming verifier. All index, reachability, publication and replay checks still run. v7 does not enter this raw-storage verifier.

## Installed Wheel Comparison

The [paired measurements](raw-verification-comparison.jsonl) use the original signed heads from both `8e570195` qualification fixtures. The [runner](measure_raw_verification.py) uses fresh subprocesses, independent uncached copies, two pairs per distribution and alternating arm order. All eight copies had zero resident main-file pages before acquisition and verified the original signed tuple with checkpoint replay. The baseline wheel SHA-256 was `97ca205ebd9623cb8489f899093a3701e8f82a0c7ddfeb44a5c36ff70f851550`. The candidate wheel SHA-256 was `ab424903740ba728dffa520e5ab7e3c5efdcc347be48b3a32f3db4e7da9e8249`.

| Fixture | Median raw scan, baseline to candidate | Median acquisition, baseline to candidate | Median service open plus acquisition, baseline to candidate |
| --- | ---: | ---: | ---: |
| Balanced | 4.89 to 4.38 s | 9.52 to 9.12 s | 10.82 to 10.44 s |
| Concentrated | 4.73 to 4.24 s | 9.32 to 9.20 s | 10.76 to 10.51 s |

The qualification driver times acquisition after service construction. The fastest candidate acquisition was 8.83 s, 3.83 s above the gate. The candidate spent 4.50-5.03 s of acquisition outside the raw verifier, including the rest of the manifest and replay. Service construction added 1.28-1.36 s. The current results show consistent raw scan reductions under these conditions and leave little room to meet the target through further raw scan changes alone. These are native macOS diagnostics with two observations per arm. Linux and the full release matrix remain unverified for the candidate.

## Integrity And Review

All 87 focused tests passed from the installed candidate with warnings treated as errors, including the raw upgrade, metadata and body mutations, index tampering, retained WAL snapshot, recovery, checkpoint, older restore and pinned-verification cases. Ruff and whitespace checks passed. The bounds apply to the four queued full-body buffers. The verifier also uses a streaming chunk and transient row objects.

Independent correctness and test review found no remaining validated P1/P2 issues in this slice. The correctness reviewer reproduced a final-row implicit cursor ending before a subsequent BLOB open. For acquisition under explicit BEGIN, the WAL snapshot test verifies that the BLOB remains in the original read view. For the named-generation pre-BEGIN guard, the partition lock excludes cooperating publishers and the cookie check after materialization and replay rejects a same-head external commit. The existing acquisition and write custody checks still bind the forest to the signed digest.

## Next Action

Profile the remaining manifest and replay stages on the same fixtures before choosing the next startup optimization.
