# Proposed Public Observation Field Semantics

Status: proposed; owner decision and feasibility/review pending. No production
or canonical design semantics are changed by this document.

## Recommendation

Keep structural observations a read-only view of retained native authority.
Use explicit joins to verified commit/evidence records; expose temporal and
trust projections separately. Do not introduce a new stored graph representation
or infer missing data from the caller, current host policy, text or model output.

| Public field | Proposed exact meaning |
| --- | --- |
| Entity canonical_type | Unique independently retained TypeEvidence.asserted_type applicable to that immutable entity and requested view/time. No eligible evidence means null; competing distinct types deny the cohort instead of choosing one. Full type evidence remains separately observable. |
| Entity valid_interval | Null: the structural entity revision has no native business-time interval. Type-evidence and claim intervals remain on their own records. |
| Entity lifecycle_state | Copy EntityRevision.lifecycle exactly. |
| Entity source_ids / operation_ids | Sorted unique source_id values from retained source evidence plus the exact creating/updating native operation's source; operation IDs come from the exact version's verified native/event ownership. Never substitute the selected cohort's entire ID set. |
| Relation supporting_claim_assertion_ids | Exact native claim(s) paired with this relation in its accepted fact/replacement effect, with canonical payload equality and endpoint/predicate binding. No unrelated same-predicate claim search. |
| Relation valid_interval | The common interval of those exact supporting claims; disagreement denies. |
| Relation lifecycle_state | `active` means that structural relation version exists at the requested system coordinate. It does not mean its claim currently wins temporal/trust arbitration. Those outcomes stay in separate projections. |
| Relation source_ids / provenance_ids | Exact supporting native claim/effect source IDs and the provenance pairs whose citations target those supporting claims. Do not reinterpret a claim-targeted provenance record as relation-targeted. |
| System intervals | Derive from verified commit-event ownership of the exact record version and its successor, never snapshot/request time. Preserve event sequence as ordering authority. Feasibility must settle same-time successors without inventing a positive interval or losing lineage. |
| SourceSpanReference fields | Copy a uniquely matched, complete retained SourceSpanReference, including artifact and mapping proof. A LineageEvidenceReference's source/start/end alone is insufficient to manufacture one. Missing or ambiguous full evidence denies. |

Claims and provenance retain the already approved policy-context and P/E/K/C
recipe unchanged. Action/identity/transition fields must use their exact retained
operation authorities; missing action transition or identity construction is a
typed refusal, never a guessed transition or rewritten identity.

The complete field audit must also prove valid/system view selection, all
seventeen stream families, canonical reference paths, boundary introductions,
version identity and projection-history ownership before promotion. This table
is the requested semantic decision, not a substitute for that proof.

## Projection Identity

Add one explicit registered root, ProjectionObservationIdentity.v1, with:

- projection_kind: literal temporal or trust;
- repository_id: nonempty string;
- generation_digest: lowercase SHA256;
- projection_digest: lowercase SHA256;
- observation_id: lowercase SHA256, the sole registered self-digest field.

Use the existing profile-3 registered self-digest construction and domain
`memorii.semantic_ingestion.observation.ProjectionObservationIdentity.v1`.
Its complete selected binding and four ordinary fields are the preimage;
observation_id excludes only itself, exactly as the existing owner prescribes.
The outward identity is the digest's lowercase hexadecimal string.

Both observed projection records copy the derived identity. Their protected
registered readers must derive and compare it using the identity root from the
same selected publication before accepting the record. Pure native model shape
validation is not a substitute for this profile-bound integrity check. Changing
kind, repository, generation or native projection changes/rejects identity.
The observed record_digest continues to bind the entire observed payload,
including that validated observation_id and the full publication pointers.

Existing historical registered artifacts retain their original identities and
read routes. The new rule requires an explicitly selected publication that
contains the identity root; no relabelling or silent retrofit is permitted.

## Alternative And Tradeoff

An alternative is to persist a new complete observation projection at commit,
including every currently missing field and identifier. That duplicates native
authority and requires writer, replay, migration and compatibility changes.
The recommendation avoids that duplication and uses retained evidence, but must
reject any historical record whose exact joins cannot be proved.

Actual production keys/signatures are unrelated to this decision and remain
deferred as requested. No production acceptance measurement is claimed.
