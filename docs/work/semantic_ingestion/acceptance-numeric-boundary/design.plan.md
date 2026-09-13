# Acceptance Numeric Boundary Reconstruction

- Work type: design
- Status: blocked (reconstruction budget exhausted; no canonical promotion)
- Parent: ../acceptance-numeric-contract/design.plan.md
- Related implementation: ../engineering-closure/implementation.plan.md
- Coordinator: main thread
- Created: 2026-09-06

## Objective And Decision

Replace the incomplete prose/fixture boundary with one executable typed
contract and a real serialized-certificate verifier. The previous design's two
correction rounds did not close three determinate obligations: complete member
types and locator bytes; pre-allocation limits; and actual proof-validation
mutation signals. All three independent reviewers agree. These are contract
and evidence actions (Not applicable / changes_required), not a new product
defect or missing user policy decision. No additional example patches to the
old prototype are authorized.

The old frozen candidate and all nine reviewed file contents are preserved in
`../acceptance-numeric-contract/history/d44138f849576f9626f02f335250359aa2729ad5d31a1a5e079c9346375dabd2.json`.
Its feasibility math remains useful; its claimed boundary proof is rejected.

## Scope And Canonical Inputs

Governing architecture: semantic_ingestion_architecture.md, canonical numeric
rules and section 5.6, at 191826c. Preserve exact policy decimals, independent
clusters, exact binomial/Clopper-Pearson, weighted Hoeffding, Holm and fail-closed
outcomes. No thresholds, scales, operational limits, keys or production
authority are selected. Computed rational enclosure remains a proposed
correction; canonical architecture/CTV promotion requires final review.

Write only this directory. Define explicit strict immutable types for every
contribution, gate, budget, transport limit, locator, binding, probability,
interval, proof variant and bundle. Use distinct exact-point/enclosure variants;
define the precise existing canonical typed-value bytes for locator ordering
and every noncyclic digest. A complete field/type table is generated from, or
checked against, these types. No free-form dictionaries are contract stand-ins.

## Required Boundary Proof

One public nonproduction verifier consumes serialized bytes plus independently
supplied bounded transport, manifest and contribution authority. It checks
complete closed types, exact coordinates, manifest-owned work budget, valid
raw-p/bound pairing, mathematical result and input equality. Mutations must
execute that same entry point. A recomputed malicious digest alone must not
make wrong evidence or math valid.

Transport reads at most a supplied bound plus one byte before any document
parse. Lexical and projected bit/byte checks precede numeric conversion,
arithmetic and certificate serialization. Instrument those allocation sites
with tripwires in boundary tests; eventual rejection after allocation is not
evidence for the required property. Validate exact-limit and one-over cases,
retries, result absence on exhaustion, malformed fields, noncanonical numeric
forms, proof swaps, wrong pairs, changed evidence, and locator ordering.

Feasibility remains nonproduction. Reuse the old mathematical examples only as
vectors; do not import their weak mutation predicate as a validator. Independent
review must reproduce positive and negative entrypoint behavior.

## Verification, Ownership And Limits

One bounded writer owns this directory; old design and production files are
read-only. Expected local boundary proof runtime is below a minute. This is
not a CI gate until canonical promotion and implementation establish one.
Freeze actual file hashes before the standard specification, correctness and
test review cohort. One reconstruction and one coherent review are authorized;
if it cannot establish the boundary, stop this operation with exact remaining
obligations. Other implementation packages remain independent.

## Writer-Reported Reconstruction Evidence (Rejected Below)

The following is the writer's evidence claim, retained for traceability. It is
superseded by the coordinator readiness decision below and is not approval.
`numeric_boundary_contract.py` is the proposed nonproduction contract owner.
Its frozen dataclasses cover transport, manifest-owned work budget, locator,
point and enclosure values, contribution authority, gate binding, both proof
variants, proof bundle, and candidate certificate. Its strict decoders reject
unknown/missing fields and expose no dictionary-shaped extension point. The
field table is generated from those exact dataclasses by the proof runner.

The sole public feasibility entry point,
`verify_serialized_certificate`, consumes candidate bytes and independently
supplied typed transport, manifest, and contribution authority. It performs a
bounded `limit + 1` stream read before JSON parsing, parses projected rational
text before `int` or `Fraction`, and verifies locator pairing, authority and
binding digests, complete gate bijection, exact binomial result equality, and
the separately recomputed Taylor-enclosed weighted-Hoeffding result. Each
proof must name the complete independent contribution set: binomial trials and
successes are reconstructed from its binary contribution values, while the
Hoeffding squared range-weight sum is reconstructed from its weights/ranges.
The
locator CTV bytes are the explicit CTV-v2 tagged map body in
`_locator_ctv_bytes`; all authority digests use domain-separated canonical
ASCII JSON bytes.

`run_numeric_boundary_proof.py` creates only synthetic fixture values. It
drives positive behavior and all mutations through that entry point: wrong
math/result enclosure, proof-kind swap, changed authority or binding digest,
wrong locator pairing, noncanonical rational, malformed extra field, and an
over-digit input. It also proves exact document cap success; document,
contribution, digit, bit, operation, and certificate caps reject one-over.
Tripwires prove digit and bit rejection happens after parse but before integer
allocation, while arithmetic and certificate serialization are marked only
after their respective preflight checks. Rejection returns no candidate result.

The local commands below passed on 2026-09-06 and regenerate
`field-table.json`, `candidate.json`, and `candidate-hash-manifest.json`:

```text
PYTHONPATH=docs/work/semantic_ingestion/acceptance-numeric-boundary .venv/bin/python docs/work/semantic_ingestion/acceptance-numeric-boundary/run_numeric_boundary_proof.py
PYTHONPATH=docs/work/semantic_ingestion/acceptance-numeric-boundary .venv/bin/python -O docs/work/semantic_ingestion/acceptance-numeric-boundary/run_numeric_boundary_proof.py
```

This is a nonproduction design-boundary artifact, so no
`production_entrypoint_bindings` entry is applicable and no production caller
or persistence owner is claimed. Parent acceptance and canonical promotion
remain partial pending the required independent review.

## Next Action

Obtain a revised bounded design approach for the complete statistical boundary
before reopening this operation; preserve this rejected candidate as evidence.

## Coordinator Readiness Decision

The writer's passing proof runner does not establish the required contract.
On 2026-09-06 the coordinator independently reproduced two failures through
no-write imports and the public entry points: changing the binomial null
probability to `0/1` and its reported result to `0/1` is accepted under the
unchanged manifest; instrumenting `_canonical_json` confirms serialization
occurs before a one-byte certificate cap rejects. The command exited zero only
after both failures were observed. No production module was changed by this
experiment.

Read-only independent consultation by `offline_signer` confirmed the source
findings. Its proof-run invocation regenerated artifacts, so that execution is
not treated as independent no-write evidence. The candidate component hashes
matched the supplied manifest. This was a readiness consultation, not the
standard final approval cohort.

Confirmed obligations, all Not applicable / changes_required / design-contract
or verification: enforce allocation caps before serialization and arithmetic;
validate independently supplied authority through the real public boundary;
bind null probabilities, directions, ranges, weights and observed margins to
the predeclared manifest; include confidence-bound inversion, nominal and
family-wise alpha, and Holm; prove actual canonical locator bytes. Existing
point/enclosure dataclasses and passing fixture checks do not close these gaps.
For the locator finding, the coordinator compared the bytes directly with
`ingestion_contracts.encode_typed_value`: the synthetic locator produces 110
bytes versus canonical 109, with an extra trailing newline. Both use tagged
JSON; the defect is exact byte inequality, not the choice of JSON or lack of
a shared import. Independent implementations need not share the codec.

The one-reconstruction limit in this WorkPlan has been reached. No further
example patches or production promotion are authorized by this operation.
R14 remains incomplete. Production signing and observation work can proceed
independently. The smallest unblock is a revised design approach and bounded
verification plan covering these obligations; no production key or signature
is needed to resolve them.
