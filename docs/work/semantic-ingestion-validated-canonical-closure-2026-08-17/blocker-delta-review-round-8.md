# Blocker Delta Review Round 8

Candidate v9 lock
`99cdf274ce91d999d497ee3ebec0c08adcd95cad977af331a298fd49a69e559d`
and all `89` tracked hashes passed independent read-only review by
`spec_auditor`, `correctness_reviewer`, and `test_reviewer`.

The targeted outcome is `CHANGES_REQUIRED`; this report makes no parent or
whole-design approval claim.

## Reconciled Finding: VCC-DREV-008B

- Product priority: `Not applicable`.
- Approval disposition: `changes_required`.
- Remediation eligibility: `contract_conformance_action`.
- Confidence: `high`.
- Finding type: governance / verification / production ownership.
- Coordinator classification: confirmed.
- Status: `OPEN`.
- Expected behavior: every receiver-semantic change in the Hermes and arena
  owners must fail, and exact AST evidence must either reproduce under its
  supported interpreter or fail with one explicit environment predicate.
- Evidence: fixed-oracle mutations using `receiver = self; receiver._service =
  object()`, alias `setattr`, indirect `__dict__` writes, and
  `self.__dict__.update(_service=...)` can pass v9. Rebinding arena `_entries`
  to a durable proxy can preserve an allowed `self._entries.clear` call while
  changing its effect. Raw `ast.dump` differs outside the implicit CPython 3.12
  environment and produces misleading semantic failures.
- Root invariant: receiver provenance is a property of the complete owning
  class, not selected target and call spellings; interpreter-specific AST
  serialization must be explicitly environment-bound.
- Positive behavior to preserve: all v9 exact constructor, filesystem,
  root-path, and arena-call contracts plus all twenty-seven attacks.
- Required correction: pin the AST runtime; freeze the complete normalized AST
  of both authoritative classes; return only `unsupported_ast_runtime` outside
  the pin; and add alias, mapping-update, indirect-dictionary, and arena-proxy
  attacks with oracle and source hashes fixed.
- Evidence maturity affected: locally verified source ownership and independent
  reproducibility.

Reviewer requests for runtime product execution remain outside this targeted
design-evidence slice.
