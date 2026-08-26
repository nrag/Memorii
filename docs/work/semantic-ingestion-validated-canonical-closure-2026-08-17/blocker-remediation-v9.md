# Blocker Remediation V9

This normative delta closes `VCC-DREV-008B` by binding the exact semantic owner
classes and their AST runtime. It changes no production code or repository
tests.

The oracle pins CPython `3.12`. A different interpreter returns only the named
`unsupported_ast_runtime` predicate before AST comparisons. Under the pinned
runtime, the complete normalized ASTs of `HermesMemoryProvider` and
`CanonicalEvidenceArena` must match. The narrower annotation, predicate,
assignment, filesystem def-use, path, call-allowlist, and call-multiset checks
remain active for field-specific diagnostics.

Because the complete owner classes are frozen semantically, direct aliases,
reflective aliases, `__dict__`/`vars` updates, indirect field names, helper
calls, receiver proxies, and substitutions behind allowed call spellings all
fail with hashes disabled. The mutation matrix retains all prior attacks and
adds those receiver-semantic families.
