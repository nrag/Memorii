# Signed Numeric-Context Authority Amendment

The acceptance runtime must derive, rather than decode, its full numeric
context. It authenticates signed coverage, gate, and sampling-frame manifests
under constructor-held trust; joins them to the approved baseline/release; and
then creates the complete `PreverifiedNumericCertificationContext` and
`VerifiedNumericAuthority`.

The approved baseline and approval release are V2 registered signed,
content-addressed artifacts selected only through the fenced authority commit.
The release binds the exact signed baseline bytes by digest; fixed runtime
configuration carries neither artifact and cannot select either.

Unsupported cells retain one abstention gate with normal clusters and evidence,
and those gates participate in the complete Holm family. The full sorted
coverage disposition projection is committed by
`unsupported_cells_digest` using the actual-NUL V2 domain. Numeric specs,
alpha, gates, IID proofs, memberships, weights, ranges, and event expectations
are signed sampling-frame data, absent from runtime configuration and compared
field-for-field with candidate policy.

The feasibility checker validates signed sampling-frame declarations only.
Observed-event missing/extra/duplicate/wrong-cluster cases remain explicit
requirements for the later production acceptance-vector suite.

V2 accepts/emits only `statistical_acceptance_certificate.v2`; retained V1
bytes have no V2 evaluator, receipt, deployment, or replay API. Details and
independent signed-manifest feasibility evidence are in `design.plan.md`.
