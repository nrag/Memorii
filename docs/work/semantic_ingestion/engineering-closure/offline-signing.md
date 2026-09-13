# Offline PEM Signing Slice

This bounded slice provides a local PEM Ed25519 adapter and a `python -m`
command for raw detached signatures over caller-supplied preimage bytes.  The
caller must supply the profile identifier, public-key digest, and exact digest
domain.  The adapter validates that an Ed25519 PEM public key produces that
existing binding, and a private key must derive the same public key before it
can sign.

The CLI is a non-test production entrypoint to the canonical signer:
`main -> _sign -> PemEd25519PrivateKeySigner.sign_preimage`.  It accepts only
PEM paths and binding paths, writes raw signature bytes with exclusive create,
and accepts encrypted-key passwords by file or standard input.  It performs no
network activity and never accepts a password as a command-line literal.

Primitive signing does not prepare or assemble release artifacts, issue trust
bindings, select policy values, certify policies, or publish a release.  Those
responsibilities remain the next release-assembly and registered-execution
slice.  This is therefore partial evidence for the parent R13 requirement.

## Local Evidence

From `memorii/` on Python 3.12.14 with cryptography 50.0.1:

```text
../.venv/bin/python -m pytest tests/unit/tools/test_semantic_ingestion_offline_signing.py -p no:cacheprovider
7 passed

../.venv/bin/python -m ruff check memorii/tools/semantic_ingestion_offline_signing.py tests/unit/tools/test_semantic_ingestion_offline_signing.py
All checks passed

../.venv/bin/pyright --pythonpath "$(../.venv/bin/python -c 'import sys; print(sys.executable)')" memorii/tools/semantic_ingestion_offline_signing.py tests/unit/tools/test_semantic_ingestion_offline_signing.py
0 errors, 0 warnings, 0 informations
```

The focused tests generate ephemeral keys, cover encrypted and unencrypted PEM,
malformed/wrong-algorithm PEM, a wrong password, a mismatched derived public
key, malformed digest binding, exact-byte signing, altered bytes/signatures,
and subprocess CLI sign/verify plus existing-output preservation.  The CLI
is the non-test caller named above; a coordinator must update the canonical
`production_entrypoint_bindings` ledger before using this partial slice as a
runtime completion claim.
