# Observed Provenance Materialization

Status: proposed, not canonical or implementation authority until review/promotion.
Baseline: 6029030d; canonical SIA remains unchanged. Parent implementation:
../engineering-closure/implementation.plan.md.

## Scope And Boundary

Close the exact ancestry and policy list recipes for ObservedProvenanceRecord,
and the shared claim policy_fingerprints field. Preserve every public field,
registered digest policy and historical artifact. This is a read-only projection
of already verified retained native authority, not new evidence or arbitration.
The source is the detached, replay-verified group request, its native compilation,
construction authority, accepted effect, evidence construction and projection.
The proposed future trigger is ProviderMemoryService.observe_graph through the
host-owned paging runtime and its concrete snapshot materializer. That public
method/materializer is not implemented; R19 remains unmapped. No request chooses these
inputs. Missing or nonunique joins deny the entire cohort before a page exists.

## Exact Evidence Join

For each native ProvenanceRecord P, find exactly one retained native evidence
projection E whose provenance_record.record_id equals P.provenance_id, and whose
materialized provenance payload equals P (including operation/version/digest).
Its paired citation must also match the retained graph payload. Resolve that
citation's cited_record_id to exactly one native graph/planning record C from
the same verified operation. Copy C.record_kind and its canonical ID as the
observed provenance target. Never choose a relation merely because the same
fact also produced one. For the built-in fact planner this target is its claim.

Match E.evidence_item_digest to exactly one evidence construction K in the
operation's BootstrapNativePlanningConstructionAuthorityV3 A. Require K's
citation/provenance IDs to equal the paired records. Require operation/source
coordinates to agree across P, E, K, A and native compilation N. K.source_span
and A.source_digest supply the citation's source span and digest. This rule
also applies to an effect nested in a correction; use the enclosing operation
identity and the actual nested effect owning E. Reject cross-operation pairing,
missing/duplicate pairs, divergent native bytes and ambiguous cited identities.
Each selected planning record's metadata kind and ID must equal its canonically
materialized kind and ID. Return the canonical materialized target identity.
For correction, replacement_effect.planning_records is the canonical target
universe; transition_records must equal its temporal-transition subset and is
not appended a second time. The other arms use fact/action planning_records,
retraction transition_records, or identity materialization's revision/alias,
lineage and reference-disposition records respectively.

## Proof Ancestry

proof_ancestry_ids means retained proof-context identities, not an inferred
causal ordering or a declaration that every policy was applied to every field.
For this native route it is exactly the lexically sorted unique tuple of:

- N.compilation_digest;
- A.authority_digest;
- A.source_authority_evidence.evidence_digest;
- A.source_authority_evidence.provenance_digest;
- K.evidence_digest;
- E.projection_digest;
- every effect_digest on the closed ownership path: one digest for fact,
  retraction, action_state or identity; both the enclosing correction digest
  and its replacement fact digest for correction. No other nesting is legal.

Every value is copied from a verified typed authority. A digest's preimage
already commits its transitive ancestors; do not recursively flatten arbitrary
objects or include current host/configuration values. Do not replace a missing
member with an empty tuple, record ID, source text hash or unrelated proof.
The tuple is deterministic and contains no evidence synthesized by retrieval.

## Policy Context

policy_fingerprints means the complete declared policy context retained in A.
It is exactly the lexically sorted unique tuple of:

- A.predicate_registry_fingerprint;
- A.predicate_state_rule.policy_fingerprint;
- A.action_policy_fingerprint;
- when A.identity_construction is present, its identity_policy_fingerprint;
- every A.temporal_constructions[i].temporal_policy_fingerprint;
- when A.arbitration_policy_bundle is present, its trust_policy.fingerprint
  and temporal_policy.fingerprint.

Include the entire declared context for every accepted operation arm, even
when a particular field did not consult all of it. This avoids inventing a
per-field execution trace. PredicateTrustRule has no independent fingerprint;
its exact content remains committed by A.authority_digest and is not hashed
again to manufacture one. A missing optional arbitration bundle adds no values;
a malformed/unverifiable bundle denies. No policy is fetched live. This same
recipe supplies an observed claim's policy_fingerprints from its own retained
operation construction authority. It does not combine temporal/trust winners.
Completeness is defined by the enumerated operation-planning context fields
above, not by recursively collecting every identifier from embedded governance,
schema, codec, source-admission or host configuration artifacts. Those artifacts
retain their own typed provenance and digest bindings.

## Compatibility, Rollout And Alternatives

No persisted source/graph record is rewritten. Old observed artifacts retain
their original declared profile and bytes. The new operational reader emits
this recipe only after its canonical design/source authority is refreshed.
Readers cannot infer the recipe from a legacy provenance record without its
verified construction chain; they deny rather than backfill. Rollback disables
the operational reader; it does not remove event history or rewrite proofs.

Alternative: add a typed persisted observed-provenance binding at commit. That
would duplicate already retained immutable joins and require a new write/replay
migration. It is unnecessary for the native paired-evidence path, but remains
required for any future writer that lacks those exact authorities. Alternative:
expose only applied policies is rejected because no field-level execution trace
is retained. The selected recipe exposes declared context explicitly.

## Verification And Promotion

A typed feasibility proof must construct exact tuples from real model fields;
mutations cover each required member, optional arbitration, duplicate/order
normalization, source/operation/pair substitution and claim-versus-relation
selection. A caller using live policy, omitted ancestry or an invented digest
must fail comparison. No fixture outcome certifies real provider quality.

Promotion updates semantic_ingestion_observation.md (SIA precedence retained),
then refreshes the affected canonical-design authority pins/gates. No schema or
role field changes are planned; inventory/cardinality must remain unchanged.
The implementation must add a public-provider positive path using real retained
authority before claiming runtime readiness. This draft and its model do not
close R19 or any of the 23 parent requirements.

### Bounded Verification Matrix

| Boundary | Required proof | Evidence limit |
| --- | --- | --- |
| Native operation ownership | Fact, correction, retraction, action-state and identity use their closed evidence owner; correction includes both effect digests | Typed recipe feasibility, not full provider execution of each arm |
| Retained target join | Exact provenance and paired citation payloads; unique same-operation target; claim wins over an unrelated co-produced relation | Native graph/planning records and canonical materialization, not arbitrary dictionaries |
| Substitution and absence | Missing/duplicate evidence, foreign operation/source, changed pair or target fail closed | No partial cohort or invented fallback |
| Complete policy context | Predicate registry/state, action, all temporal and optional identity/arbitration policies; sorted unique output | Retained declared context; no per-field application assertion |
| Historical authority | Verified original construction and commit coordinates only | No live policy lookup or rewriting old records |
| Runtime handoff | Existing registry emitter and detached-authority owner remain the intended consumers | Successful public provider integration remains a separate implementation obligation |

The bounded proof runs with the repository's local Python environment. Local
results do not claim Ubuntu/Python3.11 CI parity. No external model call, real
release key, statistical threshold or operational quality claim is needed for
this field-recipe decision. Atomic store snapshot time, checkpoint signatures,
the other structural field mappings and independent comparison remain outside
this narrowly scoped design amendment and retain their original requirements.

## Accepted Design-Owner Decision

On 2026-09-08 the user selected complete retained policy context. Applied-only
reporting is not the selected behavior. The prior frozen candidate and findings
remain preserved under history/. The current proposal corrects identity-policy
and correction-path omissions; expanded target/all-arm feasibility and review
are the remaining approval work.
