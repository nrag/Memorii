# Current Release Detached Signing

Implemented owner: `memorii.tools.semantic_ingestion_release_signing`.
Supported current CTV artifacts: recovery policy, release, release history and
active pointer. Templates must have the current exact schema binding, complete
closed body, correct body digest and a string signature slot (which may be
empty). Preparation validates shape/purpose and recomputes the signature
preimage. It does not supply missing policy values or authorize a release.

## Commands

Run from an installed Memorii environment. Substitute operator-owned paths:

```text
python -m memorii.tools.semantic_ingestion_release_signing --prepare \
  --recovery-policy policy.ctv --release release.ctv \
  --release-history history.ctv --active-pointer pointer.ctv \
  --output requests.json
```

The output identifies each artifact kind, signature purpose, profile, expected
public-key digest and exact preimage in hexadecimal. The offline signer accepts
the decoded preimage file using `sign-preimage`; an external signer may produce
the same raw detached signature through `DetachedPreimageSigner`.

```text
python -m memorii.tools.semantic_ingestion_release_signing --assemble \
  --recovery-policy policy.ctv --release release.ctv \
  --release-history history.ctv --active-pointer pointer.ctv \
  --recovery-policy-signature policy.sig --release-signature release.sig \
  --release-history-signature history.sig --active-pointer-signature pointer.sig \
  --bindings trusted-bindings.json --output assembled
```

The independently configured binding file has one `bindings` array. Each entry
has exactly four string fields: `profile_id`, `expected_digest`,
`digest_domain_file`, `public_key_file`. Paths identify the exact digest-domain
bytes and an Ed25519 PEM public key. The loader checks the expected digest and
rejects duplicate JSON fields. This file is operator configuration, not a field
accepted from a release candidate as authority.

Assembly re-reads immutable template bytes and recomputes every request before
verifying signatures. It writes nothing for an invalid signature or binding.
The output directory and every output file require exclusive creation. An I/O
failure while writing is an error and may leave an incomplete new output
directory; it never publishes a release. Run the canonical release validator
with independently provisioned lifecycle/trust material before publication.

## Evidence And Remaining Scope

`tests/integration/test_semantic_ingestion_release_signing.py` exercises the
actual prepare, offline sign and assemble commands, and checks byte-identical
signed artifacts. API tests require a `VerifiedReleaseCandidate`, not merely
absence of rejection. Unknown fields, wrong purpose, cached-request
substitution, mismatched signer coordinates, invalid signatures, duplicate
configuration fields and existing outputs are rejected.

The first combined run passed 61 signing/trust tests, including registered
executor integration. Subsequent malformed-template additions require the
updated focused run recorded in the candidate evidence. Lifecycle multi-signer
preparation is a separate active slice. Full policy/coverage/monitoring emitters,
host composition, final trust/policy inputs and whole-package review remain
distinct obligations; R13 and the parent milestone are not closed here.
