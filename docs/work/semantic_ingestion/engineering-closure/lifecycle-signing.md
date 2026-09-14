# Lifecycle Detached Signing Slice

This slice provides a production `python -m`
`memorii.tools.semantic_ingestion_lifecycle_signing` entry point for one exact
current lifecycle-root CTV at a time. `--kind lifecycle_record` prepares every
record signer in record/list order; `--kind lifecycle_root` prepares the root
coordinate after record assembly. Requests include the explicit record and
signature indices, profile, public-key digest, purpose, and raw preimage bytes.

Assembly re-prepares from the stored raw CTV bytes, checks every supplied
coordinate against that fresh request, verifies raw detached Ed25519 signatures
against explicit PEM-derived bindings loaded through
`load_release_signing_bindings`, and delegates CTV reconstruction to the
current lifecycle owner. Record assembly recomputes the root digest and clears
the root signature, so root assembly must follow it. The CLI uses exclusive
file creation for request and assembled CTV outputs, requires every signature
path as `--signature INDEX=PATH`, and has no trust defaults, private-key input,
or legacy path.

The non-test production caller is:

```text
semantic_ingestion_lifecycle_signing.main
  -> assemble_lifecycle_signatures
  -> assemble_current_lifecycle_detached_signatures
  -> Ed25519SignatureVerifier.verify
```

The required authority is independently supplied trusted PEM binding
configuration in the existing release-signing grammar. Candidate CTV fields
only name profile/key coordinates; they cannot introduce a public key or a
digest domain. Signing preparation does not validate lifecycle history,
authorize a lifecycle action, select trust policy, or activate a release.
Those remain the existing lifecycle/release validators.

## Local Evidence

From `memorii/` on Python 3.12.14 and cryptography 50.0.1:

```text
../.venv/bin/python -W error -m pytest tests/integration/test_semantic_ingestion_lifecycle_signing.py -p no:cacheprovider -k 'not cli'
13 passed, 1 deselected in 7.92s

../.venv/bin/python -W error -m pytest tests/integration/test_semantic_ingestion_lifecycle_signing.py::test_cli_explicit_signature_indices_and_exclusive_output -p no:cacheprovider -vv
1 passed in 28.86s

../.venv/bin/python -m ruff check memorii/tools/semantic_ingestion_lifecycle_signing.py tests/integration/test_semantic_ingestion_lifecycle_signing.py
All checks passed

../.venv/bin/pyright --pythonpath "$(../.venv/bin/python -c 'import sys; print(sys.executable)')" memorii/tools/semantic_ingestion_lifecycle_signing.py tests/integration/test_semantic_ingestion_lifecycle_signing.py
0 errors, 0 warnings, 0 informations
```

The 14-case integration proof creates deterministic ephemeral Ed25519 keys,
generates both ordinary and threshold-recovery current CTV chains, signs and
assembles records before the root, and validates the assembled root through
`validate_release_candidate`. It rejects a same-length bit-flipped signature
and a wrong trusted key for both record and root stages, plus tampered/cached
CTV bytes, altered profile/key/purpose/record order/signature order
coordinates, duplicate signer bindings, and noncanonical fields. The CLI proof
covers explicit per-index signature paths, PEM binding configuration, staged
record/root output, exclusive output, and direct `main` rejection of missing,
duplicate, and out-of-range indices without changing a sentinel output or
creating an absent output.

The lifecycle owner’s combined signing and provenance suite independently
passed 81 tests under warnings-as-errors in 75.03 seconds. Its existing
provenance coverage remains the owner of inactive recovery, revocation,
compromise, and post-activation-genesis behavior.

This is a bounded R13 partial: it proves lifecycle detached-signing preparation
and assembly through the existing validator. It does not close the parent
engineering-closure milestone, issue a production signature, or authorize
lifecycle history.
