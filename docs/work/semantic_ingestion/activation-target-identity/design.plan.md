# Observation Activation Target Identity

Work type: design. Status: complete; bounded target-identity contract independently approved.
Parent implementation: ../observation-ledger/implementation.plan.md.
Problem: approved activation requires64hex writer/schema/codec fingerprints but
defines neither their complete recipes nor their protected runtime authority.
Production uses descriptive writer IDs. Hashing a label or selecting the
activation schema's decoder would invent persisted meaning.
Governing sources: semantic_ingestion_architecture.md SIA-R11 and3.13;
semantic_ingestion_observation.md Activation And Writer Fencing.
The fixed activation fields must not change silently.

## Scope And Decision

The user approved decision.md: an explicit protected target manifest and
source-derived identities, preserving historical admission bytes until atomic
cutover. proposal.md specifies the bounded contract; verification.md holds the
T01-T08 requirements, attack/evidence matrix, identity ledger and planned owner
chain. These are design artifacts, not implemented signature/activation authority.

The alternative is to redesign activation to retain descriptive writer IDs and
remove the SHA256 constraint; it weakens the intended implementation binding and
is not recommended. Do not arbitrarily hash the existing display label.

## Evidence And Classification

Spec consultation decoder_snapshot_review confirms Not applicable /
blocks_approval / external decision-governance: target fingerprint authority
is unspecified. Root confirms provider writer identifier is
memorii-provider-semantic-evidence-only-v1. memorii-semantic-graph-v1 is a graph
schema identifier, not the writer. Existing narrow source-finalization JSON
schema fingerprint is not full observation grammar identity.

## Completion And Budget

No canonical promotion or dependent activation until the exact contract is
reviewed. One bounded construction, feasibility matrix,
independent review and consolidated conformance action are budgeted. The
proposal must define every source component and its exact bytes, closure rules,
authority pins, runtime/wheel binding, historical reload, downgrade behavior,
mutations and affected registry/gate chain before approval.

## Next Action

Resume ../observation-ledger/implementation.plan.md using the promoted
`docs/design/semantic_ingestion_activation_target.md` contract.

## Owner Approval And Current Delegation

The user approved decision.md with "Go ahead". The protected target-manifest
direction, unchanged historical bytes, and deferred production signing are
authorized. No repeat direction approval is needed. Canonical promotion still
requires the predefined design proof/review.

Terra worker target_identity_design owns only proposal.md, a complete finite
contract draft. Root owns this plan, feasibility, evidence and canonical
promotion. Existing implementation remains safely unavailable while this
contract is constructed. Standard independent reviewers inspect a frozen draft.
The authority chain must not equate a disk hash or copied source directory with
arbitrary Python runtime attestation; trusted host and deployment immutability
assumptions must be explicit.

## Construction Findings And Feasibility

Root rejected an incomplete recursive import allowlist and an unspecified
signed release index before review. The complete installed payload replaces
the import compiler; protected host history replaces the invented index.
Root also required the host bootstrap/core verification boundary to be explicit:
core code cannot verify itself before any Memorii import. These are determinate
contract-conformance construction actions, not claimed production defects.

probe_package.py and feasibility.json measure the historical wheel and prove
stale timestamp bytecode can defeat disk-only verification. The fresh private
cache positive control executes the changed source. Full package identity is
conservatively broader than the writer alone. Exact dependency/runtime pins,
startup trust and cache isolation must be closed in the proposal before freeze.
No implementation tests or final candidate package evidence are claimed here.

## Frozen Review And Conformance Evidence

Initial candidate 54be5bed2680fc5f4d2273f294dd96f5b7caf8aa6c6eefc9dc6ba6768b1b84ce
received five confirmed governance/evidence findings; review-round-1.json records
their classification and consolidated correction. No P1/P2 product defect was
asserted. The exact host trigger, configuration selection/forwarding, closed
policy literals and signature grammar are now explicit. Configuration alone
never activates. Required dependency entrypoint scripts are pinned under a
separate protected script anchor rather than rejected categorically.

The separate Python delegate and coordinator JavaScript reference agree on all
five identity preimages and 56 individual field-mutation change sets. These are
nonproduction recipe proofs, not release acceptance. The first mutation harness
attempt created an invalid leading-zero schema version; the harness now mutates
decimal fields with canonical integer increment, preserving the contract.

Final candidate 415648c1fc8c5dfd64bad9065ad54a74e9cc8e01fe5a603344d315144fbf0a34
is frozen in candidate.json. All three reviewers are performing the fresh final
bounded-design review, including independent requirement/identity reconstruction.
Spark target_binding_map is a read-only future implementation preflight, not a
design reviewer or production writer. No production artifact is changing.

## Completion

closure.json records final approval and canonical promotion. DREV-006 was a
bounded phase-ownership clarification: preparation installs, runtime bootstrap
only verifies. Spec and correctness approved that exact delta; test approval
remains applicable to the unchanged recipes and strengthened proof map. No
unresolved validated design gaps remain under T01-T08 and the recorded sources
and review method. No runtime, CI or parent closure follows from this result.
