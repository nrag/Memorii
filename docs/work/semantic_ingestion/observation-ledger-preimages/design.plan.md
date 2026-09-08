# Observation Ledger Preimage Decision

Work type: design. Status: complete; owner accepted the reviewed persisted bytes and canonical amendment is promoted.
Parent: ../observation-ledger/implementation.plan.md (implementation paused at
append boundary; bounded activation approved). Scope: exactly the two missing
hash preimages. Root sole document writer; no production code changes.

Canonical baseline and proposed byte contract: proposal.md. Requirements:
complete selected binding/body commitment; repository/activation/predecessor
successor; deterministic replay; historical compatibility; no caller authority.
Independent spec consultation found missing exact domains/framing, not a runtime
bug. Product priority Not applicable; disposition blocks_approval; design ambiguity.

Identity ledger: both domain constants name durable observation ledger behavior
and protocol version; no task/milestone coordinates. Existing public and persisted
model fields, canonical map format and decimal policy remain unchanged.
Authority chain: canonical design amendment -> runtime hash owner and independent
vectors -> target installed writer fingerprint -> package source proof -> atomic
append/replay -> authenticated snapshot integration. Existing 179-entry registry
is unchanged by the proposed algorithm constants; final source/target evidence
must still be regenerated. No old package/activation evidence is promoted.

Root restored the unsuccessful provisional append changes and independently
matched all final-candidate source hashes before proposing this decision.
No active schema3, weakened post-activation policy or unused artifact helper is
left in production. Activation 24-case evidence and approved source remain intact.

Validation: proposal has a field/equivalence attack matrix and finite exact
byte recipes using existing length framing. Independent bounded review checks
spec fidelity, ambiguity closure, framing collisions and evidence boundaries.
No production/runtime/CI proof is claimed. Upon owner acceptance, promote the
reviewed amendment and resume the separate implementation packet with independent
byte vectors and all required integration checks.

## Next Action

Resume the linked implementation with the accepted exact preimages; no owner
decision remains for this design operation.

## Completion

Owner accepted with "Go ahead". Spec/test review found no gap; correctness
DREV-001 was resolved by retaining UTF-8 predecessor grammar and proving chain
reachability independently. Remaining validated P1/P2: none; remaining required
design corrections: none. owner-acceptance.json records proposal identity.
This closes only the byte-contract design; implementation and CI remain open.
