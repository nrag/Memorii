# Construction Consultation Record

These are narrow readiness/construction consultations, not frozen-candidate
approval. No implementation or parent closure is inferred.

- Specification readiness: confirmed missing closed intent/receipt, head/CAS,
  activation, checkpoint and production-binding contracts. Not applicable /
  blocks_approval / governance-readiness. Expected for draft consultation;
  response does not consume the full frozen-candidate review round. Root added
  closed-contracts.md and actual terminal grammar map, with remaining registry
  and transaction evidence explicit. No external user policy decision identified.
- Correctness digest consultation: confirmed group final-result/delta cycle if
  a final result enters its own semantic preimage. Root corrected the model's
  precommit/final distinction and added a discriminating test. The suggestion
  that a source cannot refer to prior groups' final results is not accepted as
  stated: earlier committed nodes do not create a source self-cycle. No new
  production precommit-result type is adopted solely from the model.
- Test consultation found six bounded evidence gaps (all Not applicable /
  changes_required / verification): isolated zero-operation group rejection,
  complete no-write state, immutable duplicate coordinates, independent chain
  contiguity, source precommit direction and actual public append argument
  rejection. Root addressed these in one test-only batch. Targeted independent
  delta review confirms all six closed with no new bounded-model finding.
  Root result: 19 passed in 0.13s. No actual backend/schema/trust claim.

The original transaction note's H(prior,id,delta_digest) was circular because
final delta includes successor; the revision-free semantic commitment replaces
it in proposal.md. Both construction failures remain retained in evidence.

Registry consultation: coordinator confirms two Not applicable /
blocks_approval findings concerning persisted-contract governance, not a
demonstrated product-priority defect. First, exact operational grammar/profile
authority is not published and current runtime/fixture profile identity differs
in meaning. Second, the registered outer-envelope grammar/dispatch boundary is
not frozen across profile versions. Direct code, canonical-source and byte-probe
evidence supports both findings. `profile-decision.md` provides the concrete
recommended versioned compatibility direction for the owner's decision.
No production edits or silent profile reinterpretation are permitted pending
that decision. All remaining registry API mechanics are determinate once these
boundaries are frozen. This consultation does not consume full candidate review.

The user approved profile-decision.md on 2026-09-06; the two external choices
are resolved, with exact technical construction/review still required.

Replay construction consultation confirmed incomplete signed lifecycle closure
(Not applicable / changes_required / architecture-verification). Root added a
complete immutable lifecycle snapshot in the signed preimage and an acyclic
publication receipt retained with the bundle and in the same CAS. A separate
suggestion that observation replay must itself materialize graph state is
unsupported by SIA23235-23240, which requires reconstructing observation records
and verifying graph/result links. Root clarified the distinct owners explicitly;
graph replay is not absorbed into observation replay.
