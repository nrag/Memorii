# Closed Declaration Parser Slice

- Owner: bounded declaration parser worker.
- Changed owners: `memorii/memorii/core/memory_evolution/typed_value_declarations.py` and its focused unit test.
- Delivered: strict UTF-8, no-terminal-LF, RFC8785-byte-equivalent raw declaration intake; JSON-number, duplicate-key, unknown-field, and unpaired-surrogate rejection; immutable typed IR for every declared role and `TypeExpr`; local ordering, uniqueness, literal, scalar, numeric, digest/signature, decoder, upcast, and registry-role checks; protected exact-positive-integer byte/node/depth limits. Intake accepts immutable `bytes` only, and performs the node/depth budget immediately after JSON decoding, before canonical re-serialization. Exact validated source bytes remain attached to each returned role.
- Evidence: worker runs Ruff and `py_compile`; root owns pytest and broader package gates.
- Production entrypoint binding: no update is applicable. This construction parser has zero production callers by the frozen `entrypoint-preflight.md` boundary and does not claim runtime publication, persistence, or composition.
- Explicit non-goals: cross-role schema/policy/enum dependency closure, source and decoder manifest verification, registry compiler, deployment pinning, composition, and any production runtime binding. This bounded slice does not close registry-publication milestone 1 or its parent milestone.

## Registry Compilation Slice

- Added `typed_value_registry_compilation.py`: raw-byte-only reparse, complete per-schema role-set checks, dependency closure/DAG validation, enum/union/optional/numeric/integrity-policy closure, LP profile/schema/policy/binding/decoder/entry/registry commitments, and active initial entries. Returned records retain parsed declaration IR and expose decoder ID/source digest for the later manifest join.
- Correction pass: compiler role narrowing is explicit and passes its exact-file Pyright check; entry ordering uses the required textual UTF-8 schema-version tuple while schema/policy closure ordering uses unsigned-decimal ordering; numeric wrappers must be direct own-root fields; empty ordinary schemas satisfy the vacuous ordinary-field rule. Integer-bound comparison avoids Python's digit-conversion ceiling.
- Focused proof now covers valid reparse/active compilation, incomplete and duplicate role sets, optional and enum-reference closure failures, direct/nested numeric-wrapper ownership failures, independent LP byte assembly, and distinct `2`/`10` entry versus closure ordering. Root owns pytest execution.
- Deferred: manifest and decoder-source snapshot verification, runtime decoder/body validation, retained-history status transitions, and production composition. The grammar leaves the exact lexical grammar for decimal numeric lower/upper strings unspecified; this compiler enforces the closed role shape and null/non-null policy but does not invent a decimal spelling grammar.
