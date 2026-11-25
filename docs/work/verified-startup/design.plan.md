# Verified Startup Design

- Operation: design
- Fidelity: Level 2 feasibility and architecture toward Level 3 release qualification
- Baseline: `0f66fc113c6747a1fd8bd0d53c5e4e53e4814d0b`
- Canonical draft: [Verified Startup](../../design/verified_startup.md)
- Parent evidence: [Manifest and replay](../reference-capacity-debugging/manifest-replay.plan.md)
- Status: exploratory design and targeted review complete. Cold production approval depends on an explicit Tier B amendment and demonstrated platform custody.

## Evidence And Decision

The first installed open has no reusable verification cookie or authenticated forest. Named staged v8 misses call the same raw, catalog and history verifier that established the current integrity contract. Keep the existing verification owner for supported harness reconnects. Prototype whole-image authentication for a named read-only generation as a separate cold-start path. Retain ordinary cold verification for active installations. The cold path requires actual immutable-view custody and signed, current image identity.

Two isolated zero-residency image reads established sequential SHA-256 feasibility. The main files from the retained qualification fixtures were copied with the existing macOS uncached copy helper. A fresh Python process performed a full `hashlib.file_digest` SHA-256 over each copy and recorded elapsed wall time and image size. [Raw spike observations](image-hash-macos.jsonl)

## Identity And Evidence Ledger

| Surface | Identity and authority | Maturity |
| --- | --- | --- |
| Existing transports, signature purposes, control and SQLite schemas | Existing typed runtime endpoints and records retain their authority. The package stays v7-default. | Existing implementation |
| Candidate seal | `verified_image.json`, one optional control-owner artifact. `memorii.verified-image.v1` is its separate signing purpose. No requirement or fixture ID is embedded in either. | Proposed format |
| Image lease and verifier profile | Both are internal. The lease owns the exact read view. The profile is build-owned and invalidated by any compatibility change. A production identity or platform API is deferred to the feasibility implementation. | Specified constraints, open feasibility |
| Reconnect and acquisition verification | Existing native capacity distributions and signed identities, plus installed restart and corruption cases from the requirements ledger. No new public command or CI name proposed. | Existing fixtures, new evidence planned |

## Review And Exit

The specification, correctness and test reviewers examined the frozen draft and the raw spike. Confirmed contract and evidence gaps are addressed in the draft. They covered authenticated control snapshot selection, drain without blocking protected readers, native image and erasure custody, installed owner lifecycle, and observable fallback/denial and corruption tests. No production activation is approved. Keep the custody provider, trusted launcher/discovery packaging and governing Tier B amendment open until separately designed and demonstrated on the supported platforms.

## Next Action

Prototype an owner-staged sealed read-only acquisition on private fixture copies, instrument zero logical verifier calls at cold open, and measure hashing plus acquisition and preserved-head corruption rejection on both workloads before choosing a production custody provider.
