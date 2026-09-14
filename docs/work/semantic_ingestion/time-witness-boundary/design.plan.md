# Production Attestation And Acceptance Witness Boundary

- Work type: design
- Status: complete for bounded specification conformance; implementation handed back
- Parent: ../registry-publication/implementation.plan.md
- Baseline: semantic_ingestion_m5, HEAD191826cd3afb38bf605a337a71d576063b3bae5e; authorized dirty tree.

## Scope And Authority

SIA31083 makes IngestionTimeWitness acceptance-only; SIA33774 prohibits importing
acceptance witness schemas into production source or persistence. Observation
design1110 nevertheless includes SourceRetentionTimeWitness in the production
registry. Its unpublished core model has no production caller. This is a
determinate authority-boundary correction, not a new signing design.

Coordinator owns proposal, evidence and normative promotion. The active source
writer remains disjoint and does not promote this amendment. The bounded Terra
spec consultation checks ownership before frozen review. Standard spec,
correctness and test reviewers inspect one frozen proposal before promotion.

Scope excludes witness construction/signing/verification, R14 acceptance
authority, operational release signatures, public attestation field changes,
new digest grammar, ledger transactions and registry implementation closure.

## Acceptance And Boundaries

Production public reads expose only SourceRetentionTimeAttestation and
TransactionGroupCommitTimeAttestation. Acceptance alone imports its own witness
schemas, copies verified production coordinates and applies its authority.
Registry raw source inventory and static decoder table must exclude both
acceptance witness kinds; they may not be admitted through helpers or aliases.
No shipped profile-3 publication exists: remove the erroneous unpublished
model rather than introduce a historical route or migration.

Authority chain: amend observation design only; future raw source package and
model inventory change accordingly. SIA, original CTV/structural artifacts,
profile grammar and existing workflow pins remain byte-identical. Snapshot and
page attestation union remains the same. Parent implementation owns code cleanup,
source regeneration and relevant checks after design approval.

Identity ledger: existing attestation/witness type names remain behavioral
identities; no planning name enters production schemas. Verification matrix
in proposal.md covers both witness kinds and transitive admission attempts.

Budget: one frozen review and one consolidated correction. Review classifications
follow AGENTS. No external decision is needed if the higher authority is confirmed.

## Next Action

None in this completed design operation. Implementation continues under
../registry-publication/implementation.plan.md.
