# Canonical Evidence Performance Proposal Baseline

## Objective

Reduce repeated canonical byte-tree construction on the semantic-ingestion
production path without changing canonical bytes, digest domains or values,
persisted schemas, strict semantic validation, authority, transaction, retry,
replay, or fail-closed behavior.

## Proposed Architecture

1. Freeze the current encoder's valid and invalid byte/digest behavior as the
   semantic equivalence oracle.
2. Classify every measured construction as new value, external validation,
   persisted reload, internal handoff, duplicate descendant, duplicate
   reconstruction, or closure comparison.
3. Introduce a private frozen `VerifiedCanonicalContract[T]` carrying the
   typed value, canonical bytes, digest, domain, concrete type, and schema
   version.
4. `seal_contract` validates a newly constructed value, constructs canonical
   bytes once, calculates and verifies its digest, and returns the evidence.
5. `load_verified_contract` verifies canonical wire syntax and digest from
   persisted bytes, decodes and semantically validates once, and retains the
   original bytes for downstream use.
6. Raw or persisted inputs retain full strict validation. Already verified
   internal handoffs verify evidence metadata and avoid recursive
   `model_validate(model_dump(...))` reconstruction.
7. Source normalization persists the retained canonical member bytes, reloads
   each member once, and passes verified authority evidence to graph execution.
8. Graph planning seals only genuinely new artifacts. One sealed group-result
   checkpoint is reused across the bounded exact retry.
9. Differential tests require legacy and optimized canonical bytes, digests,
   decoded values, and exception classes to match. Mutation tests cover nested
   substitution, wrong domain/type/schema, malformed bytes, persistence
   reopen, and exact retry.
10. Acceptance requires no unexplained repeated canonical construction, no
    trusted-path `model_validate(model_dump(...))`, exact functional and
    persisted equivalence, and material unprofiled and profiled runtime
    improvement.

## Scope Constraints

No public or persisted schema change, digest algorithm or domain change,
global cache, graph-traversal redesign, retry-policy change, M4 behavior,
timeout increase, or weakened validation is permitted.

## Measured Baseline

One fresh in-memory reproduction produced 42,343 `contract_digest` calls, 330
distinct domain-and-digest pairs, 42,013 repeated identical results, and
38,239 calls from `_ContentAddressedContract.validate_content_digest`.
