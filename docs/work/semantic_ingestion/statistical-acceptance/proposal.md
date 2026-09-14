# Policy-Bound Statistical Acceptance

Status: proposed correction, not canonical promotion or production certification.
Governing source: `docs/design/semantic_ingestion_architecture.md`, canonical
numeric grammar and Section 5.6. Existing signed release bytes remain unchanged.

## Authority And Ownership

The verifier receives three independent binary streams: a candidate certificate,
the frozen policy, and independently adjudicated event evidence. A host supplies
the exact SHA-256 identities of the last two and explicit transport ceilings.
Candidate fields cannot provision these identities. Production composition must
obtain policy identity from the approved pre-evaluation baseline and evidence
identity from the independent acceptance evidence owner. A SHA digest alone
does not establish approval or label quality; this boundary assumes those two
host inputs have already passed their respective authorization stages.

The host also supplies a `PreverifiedNumericCertificationContext` independently
of policy and candidate parsing. This is the acceptance owner's typed output
after baseline approval verification and reconstruction of coverage and the
sampling frame; it is not a new signed artifact. `NumericAuthority` records
the approved baseline, verified approval release, capability fingerprint and
contract, coverage manifest/release, statistical gate manifest, sampling frame,
independent-cluster definition, strata, weighting and numeric registry identities.
The host pins the expected authority separately in `HeldBinding`. Every
coordinate must match, and the certificate repeats those coordinates.

The context carries reconstructed encoding specifications, family alpha, the
complete expected gate family and cluster/event/provenance memberships. Policy
projections must equal them exactly, including sequence order, field-specific
specifications, thresholds, minima, methods, ranges and weights. Input order is
therefore frozen, while output order is canonical locator order. Missing or extra
gates and changed clusters reject before arithmetic. Evidence completeness and
Holm membership derive from the context. The binomial branch requires the
context's `iid_bernoulli_clusters_proven`; a policy IID flag is diagnostic and
must agree. A declaration inside a policy cannot prove independent sampling.
The component does not reconstruct signatures or sampling frames itself; a
future acceptance composition root must construct this context from separately
verified authorities, never by copying an unverified policy as test fixtures do.

The nonproduction executable contracts are the frozen dataclasses in
`wire_contract.py`; `bounded_math.py` owns arithmetic and inference. The future
acceptance owner is `acceptance/statistical_certification.py`, with production
deployment verification remaining read-only. No provider, routing, semantic
reconciliation, observation projector, or simulator oracle code enters the
evaluator. Only the public canonical typed-value codec is shared with production.

## Closed Inputs And Policy Numbers

Policy and event evidence are ASCII JSON transports (Unicode strings use JSON
escapes). Every object has an exact field set. Duplicate keys, JSON floats and
constants, wrong types, omitted fields and unsupported enums reject. Identifier
strings preserve their exact Unicode scalar sequence and have no case folding
or normalization. A capability fingerprint is 64 lowercase hexadecimal digits.

All substantive numeric inputs retain `CanonicalDecimalQuantity` with exactly
`encoding_spec_id` and `fixed_scale_value`. Each explicit encoding specification
defines its unit, positive scale, finite strict lower/upper bounds, endpoint
inclusivity and literal `reject_inexact: true`. No implicit entry, inheritance,
rounding or fallback exists. Lexemes have an optional minus, canonical integer
part, decimal point and exactly the declared fractional digits; negative zero,
plus, exponent and extra precision reject. Every gate explicitly names its
threshold, nominal-alpha, lower-range, upper-range, weight and event-value specs;
the family-alpha spec is explicit too. Alpha units are `probability`, weights
use `weight`, and metric-related fields must have the same declared unit.

The policy contains the complete gate family, independent cluster membership,
frozen provenance groups, expected event IDs, weights, ranges, cluster minima,
IID declaration and method/estimand/direction. A provenance group cannot belong
to different independent clusters. A cluster cannot repeat within a gate.
Events may supply labels to multiple metrics, but each `(locator,event_id)` is
unique and the event's provenance identity is consistent across metrics.

The supplied event set must equal the frozen expected set. Missing rows do not
vanish from denominators; they reject incomplete evidence. An explicitly missing
label is represented by `null` and contributes the predeclared cluster-failure
value: one for an any-failure indicator, or the unsafe endpoint for a macro
metric. The any-failure indicator is the maximum binary failure label within
the cluster. Macro means average the complete event set within each cluster
before applying frozen cluster weights. The any-failure safety estimand admits
only upper claims, consistent with the governing false-activation gate; a lower
claim would make missing-as-failure favorable and rejects. Both binomial tails
remain kernel feasibility cases, not permission for a lower safety policy.
A label must lie within its cluster's
declared range; weights are nonnegative and sum exactly to one.

Exact binomial use additionally requires the independently proven IID context, the
any-failure estimand, binary observations, unit interval ranges and equal
weights. IID provenance is supplied by the sampling authority; statistical
outcomes cannot establish independence. All thresholds must be within the
declared metric ranges. The kernel separately supports mathematically fixed
ranges, but the policy boundary preserves the governing strict range rule;
kernel degenerate-case feasibility does not silently expand admitted policy.

## Complete Computation

No certificate value selects a computation input. Trial counts, successes,
weighted mean, squared range-weight sum and directional margins are derived
from validated policy and event evidence.

For a lower claim the binomial raw p-value is `P_t(X >= k)`; for an upper claim
it is `P_t(X <= k)`, with the null `t` equal to the policy threshold. The lower
Clopper-Pearson endpoint solves `P_p(X >= k)=alpha`; the upper solves
`P_p(X <= k)=alpha`. Exact zero/all-success endpoint cases are explicit. Rational
bisection retains both sides of the root and reports an enclosure. An exact
root encountered during bisection reports an exact point.

Weighted Hoeffding derives `m=sum(w_i*x_i)` and
`S=sum(w_i^2*(upper_i-lower_i)^2)`. Its directional p-value uses
`exp(-2*max(0,m-t)^2/S)` for lower claims and the symmetric upper formula.
Positive Taylor terms for `exp(q)`, plus a proven geometric bound on the
omitted tail, give reciprocal rational bounds on `exp(-q)`. Zero margin gives
exact one. Insufficient series precision or a resource limit is inconclusive,
never a rounded pass. Inversion bisects the same test over the frozen weighted
range. A midpoint interval overlapping alpha does not justify discarding
either half; the current outer bracket is retained. Roots outside the declared
range are clipped to that range's endpoint.

Holm operates on the complete family. Exact p-values sort numerically;
Hoeffding exponents from the evaluator sort in reverse numeric order. Equal
exact or symbolic probabilities tie by the actual canonical locator bytes.
Cross-method unresolved overlap makes the family inconclusive. Certificate
fields cannot supply the symbolic sort exponent. At zero-based rank `i` in
family size `m`, effective alpha is
`min(nominal_alpha, family_alpha/(m-i))`. Failed or inconclusive prefixes cannot
permit later passes. Decisions join back to their locators rather than being
zipped against an earlier input order.

Confidence bounds use that same effective alpha. A pass requires both the
Holm p-value decision and the conservative bound endpoint to pass the frozen
threshold. An upper-bound enclosure passes only at its upper endpoint; a lower
bound uses its lower endpoint. Overlap is inconclusive. Alpha exactly one is
valid under the governing policy rule; non-endpoint inversion emits a full-domain
conservative confidence enclosure, preserving uncertainty rather than choosing
an informative zero-confidence limit. Exact CP lower-zero/upper-all endpoints
and deterministic fixed-range Hoeffding bounds take precedence at every alpha,
including one. Zero alpha rejects.

## Computed Types And Canonical Bytes

Policy decimals remain separate from computed values. A computed rational has
explicit integer `numerator` and positive integer `denominator`, reduced by
exact arithmetic. CTV encodes those integers using its existing tagged decimal
integer grammar. An `ExactValue` has `kind: exact` and one rational; an
`EnclosedValue` has `kind: enclosure`, `lower` and `upper`. This avoids premature
conversion to decimal strings and introduces no binary floating-point values.

The certificate includes exact policy/evidence hashes, all authority coordinates,
family alpha, complete
per-locator method/direction, derived counts, mean/range sum, threshold,
nominal/effective alpha, raw probability, confidence bound, Holm rank (nullable
for unresolved order), p/bound outcomes and combined acceptance. Dataclasses
are the explicit field/type inventory. Locators are ordinary typed maps passed
once to the canonical encoder; tagged JSON is not passed through the encoder
a second time and no newline is appended.

Verification reconstructs the whole expected typed certificate, encodes it,
and compares the candidate bytes exactly. It never parses candidate-controlled
numeric fields. Therefore alternate numeric forms, extra fields, duplicate
keys, unknown enums, swapped proof/result fields, malformed CTV, substituted
authority and changed decisions cannot be accepted through a secondary parser.

## Resource Boundary

Independently configured transport ceilings bound each stream, metadata integer
digits, nesting, members and strings before parsing. Reads handle short binary
reads and consume no more than the limit plus one byte. Policy budgets may
narrow but not expand transport ceilings. Policy precision explicitly controls
both root bisection steps and Taylor terms; it is a resource setting, not an
acceptance threshold.

One operation meter covers policy-number conversion, evidence aggregation,
all rational arithmetic/comparisons, exact coefficients, bisection, Taylor
terms, Holm and output integer-digit counting. Each operation checks a
conservative numerator/denominator bit bound before allocation, including
cross products and addition carry. Conservative exhaustion is allowed even
when a later cancellation could have reduced the final number. Input integer
text compares to the exact configured bound before conversion.

Computed numbers remain integers until after output-size preflight. An exact
CTV byte counter traverses the typed dataclass directly without expanding it
to a map, and covers the closed certificate algebra, including integer
digits, escaped strings, Unicode and container tags. Only after the total fits
the policy cap is the canonical encoder invoked. No candidate or certificate
is returned on exhaustion. Test hooks at the allocation/encoding boundaries
prove ordering; a marker placed after an allocation is not proof.

## Alternatives, Promotion And Evidence

Retaining fixed-scale decimals for irrational computed bounds would require
rounding semantics that the governing policy grammar forbids. Trusting
candidate derivations would retain the original forgery surface. Whole-result
recomputation is deliberately simpler and stricter than accepting arbitrary
alternative numerical proof transcripts.

The independent checker uses separate source and exact arithmetic to check
finite tails and root inequalities, not imports of the kernel. The public
wire tests additionally mutate authority, labels, structure, result fields and
resource limits. These establish nonproduction design feasibility only.

`promotion-map.md` identifies the required canonical declaration, profile/
registry version, compiler, structural inventory, golden and release-generation
changes. Existing v2 release identities must remain replayable under their
original bindings; changed declarations require a new authority generation.
Actual signing material and substantive policy values remain external release
inputs. This proposal does not authorize migration, alter existing signed
artifacts, certify labels/providers or close the parent semantic-ingestion work.
