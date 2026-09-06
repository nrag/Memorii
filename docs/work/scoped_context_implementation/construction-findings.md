# Construction Integrity Findings

Bounded read-only provenance_check consultation, not whole-candidate approval.
Coordinator directly inspected common eligibility and rendering and confirmed
four P2 / changes_required / runtime-behavior findings:

- Authorized expired/invalidated sources kept parents readable after sources
  were filtered out. Important case: retained stale evidence after invalidation.
- Inner invalidated entity links remained readable because projected envelope
  is ACTIVE. Important case: identity lifecycle correction in stored records.
- Typed source IDs were absent from emitted items and budget charging.
  Important case: normal entity-link/anchor projections hold sources internally.
- Empty claim provenance was vacuously accepted despite typed validation policy.
  Important case: retained or externally inserted schema-valid ungrounded claim.

One invariant-level correction is assigned to sole writer scoped_tests: build
one reference-time dependency-eligible fixed-point closure, enforce typed
lifecycle and required provenance, and derive emitted/charged source IDs from
that same owner. Preserve temporal selection of historical claim candidates.
This reconstructs the common boundary rather than patching four examples.
Both-root positive/adversarial proofs required; no completion yet.

Other construction corrections confirmed by coordinator: exact corruption
translation, empty failure echo validation, duplicate logical IDs, explicit
optional provenance omissions, and transitive evidence output. They require
focused tests and final whole-candidate review; no earlier scaffold report
is acceptance evidence.


Coordinator reconciliation: all four construction findings are corrected in the common eligibility/rendering boundary, with both-root source proofs recorded in source-proof-report.md. Construction status: resolved; independent cohort confirmation pending. No accepted product limitation substitutes for a correction.
