# VCC-DREV-008B Closed-Family Remediation V10

## Correction

Candidate v11 freezes the exact 32-name adversarial corpus independently in
`production-entrypoint-bindings-v11.json` and
`production-owner-oracle-v8.json`. The validator requires both lists to be
nonempty, unique, sorted, and identical.

The result fails closed when any expected attack is missing, any undeclared
attack appears, or any expected attack survives. A deliberate omission
self-test removes one expected result and requires the detector to emit the
corresponding `missing_mutation` failure. This proves corpus completeness rather
than trusting the inherited mutation generator's size.

## Boundary

The accepted production grammar remains the source-hash-bound owner classes,
constructors, receiver assignments, calls, and composition chains frozen by
candidate v10. Same-module mutations alter governed bytes and fail closed.
Arbitrary external runtime monkeypatching is not an accepted production form
and is not added as an unbounded static syntax family.

## Acceptance

Closure requires all 32 exact attacks to be present and detected, the omission
self-test to pass, ledger and oracle bytes to remain unchanged, and the pinned
CPython 3.12 AST runtime contract to remain satisfied. No production code or
repository tests are changed.
