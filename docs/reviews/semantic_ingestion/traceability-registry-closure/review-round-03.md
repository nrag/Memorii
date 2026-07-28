# Semantic Ingestion Traceability Registry Closure Review, Round 03

## Review Metadata

- Review date: 2026-07-27
- Review mode: fresh full review of revision 2
- Design baseline:
  `b8ea11b816241211e9d0c0f68707eb2f8e7d0fcbf5a8a60abdba23d782243d0b`
- Registry baseline:
  `2b5f3859bf606bc196ee747bf2e94d70c98bba6356fd1fd4f520fbcbbed03047`
- Registry source identity:
  `f1dd2039eaa3f5615b5d2037837b17dae599cc6b84d8ee5af2520d5769e31f90`
- Reviewers: new `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer` instances
- Revisions used before this review: 2 of 3

## Validated Findings

Each finding has product priority `Not applicable` and design disposition
`blocks_approval`. These are acceptance-governance defects, not demonstrated
product-use-case failures.

### TRC-R3-001: Manifest and execution-evidence identities form a digest cycle

- Requirements: SIA-R03
- Confidence: high

`NormativeExecutionEvidenceRecord` binds `traceability_manifest_digest`, while
`NormativeTraceabilityManifest` embeds those evidence records and derives
`manifest_digest` from the complete manifest. Constructing the manifest changes
the digest that each embedded record must contain, which changes the manifest
again. No deterministic finite construction is defined.

Completion requires separate identities and publication stages:

1. a structural manifest containing design, registry roots, extracted units,
   mappings, and assertions but no coverage or execution evidence;
2. coverage and execution records bound to that immutable structural-manifest
   digest;
3. separate coverage/evidence root digests;
4. a signed release binding the structural-manifest digest and both later roots.

The design must define exact digest preimages and atomic publication order.
An independent construction/round-trip test must build and verify the complete
artifact graph without fixed-point iteration or excluded fields invented by an
implementation.

### TRC-R3-002: Recovery and historical lifecycle trust records are not typed

- Requirements: SIA-R03 and SIA-R13
- Confidence: high

The bootstrap contract names a `recovery_anchor_coordinate`, but does not bind a
content-addressed recovery key/certificate, purpose/profile, signer
authorization rule, or activation sequence. Supersession, revocation, and
compromise are described as signed lifecycle records, but no record schema
binds effective time, issuer, signature, predecessor, monotonic sequence, and
ordering. A same-coordinate recovery substitution or ambiguous/backdated
lifecycle record could therefore change current authority or a historical
evidence verdict.

Completion requires typed canonical bootstrap, recovery-policy/root, and
append-only lifecycle-record schemas. Their signatures must bind purpose,
target, signer eligibility, effective and recorded times, predecessor,
sequence, key/certificate digests, and canonical profile. The design must
specify root rotation, recovery activation, compromise timing, historical
verification on both sides of lifecycle events, and deterministic rejection of
ambiguous ordering.

### TRC-R3-003: Report schema and runner environment are not content-bound

- Requirements: SIA-R03 and SIA-R13
- Confidence: high

Test groups currently name a report schema ID/version and describe the runner
environment as `clean_allowlisted`. Execution evidence carries identifiers but
not the exact report-schema bytes or immutable environment profile. A changed
parser/schema, pytest plugin/configuration set, `sitecustomize`, import path, or
environment policy could produce immutable passing report bytes under the same
declared IDs.

Completion requires content-addressed report-schema and runner-environment
profile roots. Each group binds their expected digests; each execution record
binds independently observed digests. The environment profile must cover the
interpreter, runner, plugins, configuration files and options, import path,
startup customization, selected environment variables, network policy, and
dependency lock/fingerprint. Tests must reject schema-byte substitution and
changes to pytest options/config/plugins, `PYTHONPATH`, `sitecustomize`, or
other allowlisted environment inputs.

## Rejected Or Deferred Observations

- The current implementation does not yet implement the now-determinate
  registry and release design. That is expected implementation work and not a
  new design finding.
- The 23 required acceptance tests are explicitly marked
  `required_not_yet_evidenced`; their absence prevents acceptance but does not
  make the target semantics implicit.
- The unresolved external decisions, including actual traceability trust
  identities and initial release, remain explicit prerequisites rather than
  internal design defects.

## Verified Positives

- Registry raw bytes equal recursive canonical serialization.
- All 144 emitted Sections 1-5 headings map one-to-one and in order.
- All requirement, assertion, test-group, command, selected-test, structural
  rule, and anchor references resolve.
- The trust bootstrap is independent of release-contained snapshots.
- Missing implementation does not produce a false design-approval claim.

## Disposition

**Not approved.** The third and final permitted revision is authorized for
exactly TRC-R3-001 through TRC-R3-003. If fresh review still finds a validated
blocking, high, or medium internal defect, this operation must stop with an
unresolved-findings report.
