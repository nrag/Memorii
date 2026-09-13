# Frozen Feasibility Fixtures

Run the proof with the repository virtual environment:

```sh
.venv/bin/python unsupported_cell_feasibility.py
```

`manifest-fixtures-v1.json` is literal test data, not generated input. It
contains canonical bytes, digest, signing preimage, signature, and public key
for baseline, release, coverage, gate, and sampling-frame artifacts. The checker independently
reimplements acceptance CTV-v1, consumes these literals, verifies Ed25519
signatures, and rejects both stale-signature content changes and validly
re-signed inconsistent joins before its parser-reachability sentinel.

The frozen projection coordinate is named `unsupported_cells_digest`; its
separate `ctv_sha256` identifies the canonical CTV bytes. These files are
design feasibility evidence only and are not a production evaluator, registry,
or installed CLI.
