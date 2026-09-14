# Production Registry Witness Exclusion

## Governing Requirement

semantic_ingestion_architecture.md31083 says only the acceptance harness
constructs IngestionTimeWitness. Lines33774-33776 prohibit acceptance witness
schemas, keys, trust policy and fixture/pass coordinates in production source
or persistence. The current observation publication table includes
SourceRetentionTimeWitness even though it is an acceptance witness. Apply the
AGENTS source precedence and remove that inclusion.

## Exact Amendment

In semantic_ingestion_observation.md's Stream and responses row, remove only
`SourceRetentionTimeWitness.v1`. Add immediately after that family table:

> Production time observation publishes only SourceRetentionTimeAttestation.v1
> and TransactionGroupCommitTimeAttestation.v1. SourceRetentionTimeWitness and
> TransactionGroupCommitTimeWitness are acceptance-only values owned by the
> acceptance harness under SIA's time-witness boundary. Neither witness is a
> production registry root, transitive schema dependency, static decoder target,
> source model, stored observation or public response. The acceptance harness
> reads and verifies production attestations through the authorized public
> boundary, then constructs and verifies witnesses under its separate acceptance
> authority. This publication contract does not define or relax that authority,
> and production never accepts expected witness IDs or fixture coordinates.

No signature policy is added to profile3 for these excluded witnesses. The
existing checkpoint exception and cursor signature policy are unchanged.
Production attestation digest policy authoring remains governed by the existing
canonical attestation contract; this amendment makes no new hash choice.

## Implementation Handoff

Remove the unpublished SourceRetentionTimeWitness core definition/export and
its import from the drafting inventory. Preserve attestation owners/fields and
public response union. Replace tests of the misplaced witness with a boundary
check that neither witness kind occurs in any production raw declaration,
model inventory or static decoder table. The production closure walker must
reject witness references just like any undeclared schema. Acceptance witness
implementation remains separate and incomplete where already recorded.

## Alternatives And Compatibility

Keeping the witness and inventing a combined production signature policy would
violate the higher authority and couple acceptance keys to production. Moving
acceptance signing into a production callback has the same defect. Excluding
the witness preserves the two production attestation schemas and the public
read contract. No deployed profile3 registry or witness record needs migration.
No native historical digest, legacy reader, wire grammar or authority pin changes.

## Verification Matrix

- Positive: both production attestation schemas remain in the root inventory and
  public time page/snapshot union; fields and canonical schema shapes unchanged.
- Negative: SourceRetentionTimeWitness and TransactionGroupCommitTimeWitness
  must be absent from production roots, nested ModelRefs, aliases and decoder
  targets; a supplied witness body cannot pass the attestation discriminator.
- Ownership: production imports no acceptance witness/key/trust/fixture package;
  acceptance may read public attestations without affecting their production
  digest or state. No receipt/global ledger synthesis from historical witnesses.
- Compatibility: exact SIA, CTV authority, structural fixtures, profile grammar
  and workflow hashes stay unchanged; only the erroneous unpublished inventory
  changes. Existing numeric amendment remains intact.
- Evidence: source inspection proves current absence of production witness
  callers; deterministic tests prove implementation exclusion after handoff.
  Neither establishes live acceptance, operational signatures or M5 closure.

## Evidence Maturity

This is specification conformance only. No runtime, publication, signing or
independent compiler claim follows from amendment approval.

## Concrete Verification Allocation

Implementation owner registry-publication adds feature-local tests to
test_semantic_ingestion_observation_source_draft.py: build the actual draft and
assert both witness IDs absent from roots, source_ids, schemas and recursively
walked model references/alias alternatives. Assert both attestation IDs present.
A deliberately unmapped schema still yields an unresolved policy, proving the
draft has no unknown-to-ordinary fallback.

The same implementation owner extends test_graph_observation_public_contracts.py
with both attestation variants through IngestionTimeObservationSnapshot and
IngestionTimeAttestationPage using raw model input and exact serialized-field
round trips. Feed both correctly shaped witness dictionaries (including their
kind and complete authority fields) through both boundaries and require typed
ValidationError with no result. Parameterize otherwise-valid attestation inputs
with witness_id, signing_key_id, trust_policy_digest and fixture-coordinate
extras and require rejection. No mocks replace the public contracts.

When authoritative package and static decoder construction exists, the parent
registry verification matrix owns paired witness attempts through root and
transitive declarations, alias alternatives and decoder targets. Undeclared
references must fail closure; supplying complete witness declarations must fail
the finite production inventory/decoder check. Generic declaration grammar need
not reserve or blacklist a witness name: exclusion is an owner/source-selection
invariant, not a universal syntax restriction. Untrusted draft tests alone do
not close that future boundary. Runtime authorization/transactions/live evidence
remain outside this specification amendment.
