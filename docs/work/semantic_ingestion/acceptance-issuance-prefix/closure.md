# Issuance Prefix Correction Evidence

Bounded design correction approved. Current candidate is
`candidate-committed-lookup.json`, SHA256
`68dee476566df106018c512c29c53f46f95811cd8186176f4564b36406bf73f5`.
The preserved predecessor plans remain rejected historical candidates; this
packet resolves their exact issuance-prefix ambiguity without overwriting them.

Spec, correctness and test reviewers independently inspected the final frozen
correction and found no remaining concrete gap within this slice. Root confirmed
all reported gaps and applied explicit contract/evidence actions: signer purpose
and lifecycle, declaration joins, exact prefix preservation, closed/bounded byte
entry, atomic head/status-generation capture, immutable publication, and committed
release/snapshot pair lookup. The suggested effective-time suffix ban was rejected
because append order and effective time are distinct; the reviewer accepted the
explicit atomic issuance rule and its proof instead.

103 local checks pass (56 unchanged predecessor tests,47 new). Ruff and configured
Pyright pass. Portable output digests are in `evidence/manifest.json`. Earlier
intermediate counts are historical evidence for their own candidate identities.

This closes the bounded issuance-prefix correction only. It does not promote a
canonical registry schema or implement production acceptance signatures, bounded
repository traversal, evaluator/CLI, deployment binding or qualifying measurements.
The parent requirement remains incomplete. No production key or policy value was
chosen, and no runtime or persisted production artifact format changed.
