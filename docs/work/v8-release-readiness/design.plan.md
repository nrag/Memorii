# Close the Memorii v8 release gaps

- Work ID: v8-release-readiness
- Work type: design
- Delivery fidelity: Level 3, first production release
- Status: complete
- Coordinator: Codex
- Created: 2026-11-27
- Last updated: 2026-11-27
- Parent WorkPlan: None
- Related WorkPlans: [storage and operator security](../v8-production-hardening/milestones/storage-and-operator-security.plan.md), [durable delivery](../durable-delivery-implementation/implementation.plan.md), [installed release rehearsal](../installed-release-rehearsal/testing.plan.md), [ontology gap closure](../ontology-gap-implementation/implementation.plan.md), [reference capacity qualification](../reference-capacity-qualification/testing.plan.md)
- Canonical inputs: [spec](../../design/memorii_spec.md), [storage details](../../design/memorii_storage_details.md), [event model](../../design/event_model.md), [implementation rules](../../IMPLEMENTATION_RULES.md), [durable runtime](../../design/durable_execution_and_solver_runtime.md), [learned ontology](../../design/learned_ontology.md), [closure matrix](../../plans/engineering_hardening_closure_matrix.md)
- Expected outputs: [release design](../../design/v8_release_readiness.md), [validation and authority bindings](validation.md), evidence for a later implementation WorkPlan

## Problem, scope and completion

Operators can restore an intact installation, protect local SQLite data and
configure the native hosts with fixture assistance. First-release users need
their own installation path, safe dependencies and an evidenced envelope.
Losing the host can also lose current authority, making managed fresh-host
recovery unavailable. Native barriers and full catalog snapshots make normal
turn cost depend on installation history. The affected actors are installation
owners, exact-session native hosts, provider owners and release reviewers.

This design closes those release gaps and defines the evidence needed for
critical adoption. Level 4 fleet migration and backward compatibility for
public installations, distributed storage and comparative agent benchmark
execution are outside the current operation. No code or rollout is authorized
by design completion. Implementation approval is gated on the completeness
rules in .agents/PLANS.md, with release readiness later proved independently.

## Requirements ledger

| ID | Requirement | Source | Importance | Acceptance criteria | State |
| --- | --- | --- | --- | --- | --- |
| REL-01 | Runnable operator provisioning and oversight | Durable runtime operator and host binding, prior release review | First release | Fresh installed Pi and OpenClaw using CLI and bundled artifacts alone, two scopes, restart, rotation and revocation, required Hermes callbacks, status and rollback runbook | specified |
| REL-02 | Independent recovery and current authority | Durable runtime backup and independent control recovery | First release | Older archive plus latest independent authority on a host without original files. Current deny state, fresh grants, held unknown effects and restart after all cuts | specified |
| REL-03 | Safe supported distribution | Dependency review and installed host roots | First release | Clean install matrices and exact supported artifacts with scans, explicit disposition of optional local NLP and artifact provenance | specified |
| REL-04 | Bounded native spool, admission, recall and host deadlines | Durable runtime capacity, native turn audit | First release | Indexed query/candidate bounds with unrelated history, semantic parity/proof on crashes, real host timeouts and release recheck | specified |
| REL-05 | Scoped protected catalog read | Learned ontology and runtime scaling audit | First release | Exact statuses and release parity, bounded browse and inspection, full verified snapshot for exact recall | specified |
| REL-06 | Product/security parity and candidate evidence | Initial release decision, durable runtime capacity and closure matrix | First release | Existing permission/secret regressions, native Linux/macOS distributions, approval and tested exact-artifact restore and rollback | specified |
| REL-07 | Evidence for critical-project adoption | User's critical adoption question and agreed benchmark sequence | After hardening | Named adopter owns SLO/RPO/RTO, measured workload including comparative agent task outcomes before an adoption recommendation | specified |

## Baseline and artifacts

Frozen baseline is `665319c0e44fcedd848c3f6ce8e8a5b2f19b3df1` on
`codex/durable-delivery-implementation`. The verified permission/secret/log
slice is `c0fa889a`. Current catalog discovery merged at the baseline and
still calls the full protected read snapshot. Earlier staged v8 capacity
evidence is at `f5786d12`. Linux p95 acquisition 10.89/10.97 s and macOS
8.06/9.01 s establish feasibility for the accepted 11 s. Reuse the reference
test family with a fresh-default-v8 variant and candidate-bound evidence.
Prior local audit, implementation plan and VirtualEmployee work were already
untracked and remain outside these design edits.

| Design slice | Authority and detailed acceptance |
| --- | --- |
| Installation and distribution | [Entrypoints and validation](validation.md#entrypoint-bindings) |
| Recovery and rollback | [Recovery families](validation.md#verification-families) |
| Runtime bounds and release evidence | [Environment and artifact matrix](validation.md#environments-and-artifacts) |

## Alternatives and decision log

| Area | Selected and why | Serious alternative and tradeoff |
| --- | --- | --- |
| Setup | Thin installed owner entrypoints and foreground loopback runtime reuse. Exact signed lifecycle remains in the core owners. | Document assembly via Python APIs. Smallest code change, but grants and task provisioning remain ad hoc and unrehearsable. |
| Recovery | Independently sealed current control, pending-before-mutation, offline atomic new root, explicit old-host isolation. | Backup and matching anchor side by side is convenient but permits a routine later revocation to be lost. Distributed currentness/lease would improve reachability at much higher scope and availability complexity. |
| Distribution | Establish native base profile and qualify each additional profile independently. | Bumping a single Torch constraint is simple but leaves loader compatibility and later advisories unverified. |
| Spool | Separate private indexed transaction owner with signed partition receipts as effect truth. | Pending files alone reduce committed scan but still scan other tasks. Derived file index improves lookup but adds a second crash/rebuild relationship. |
| Recall | Ordered typed/indexed selection and closed candidate budget, preserving release checks. | A hard LIMIT before authorization would lose older eligible data. Read-optimistic redesign of the publication fence complicates revocation without evidence that it is needed. |
| Catalog | Existing typed ontology closure in a scoped verified snapshot. | Cache view results by projection alone risks stale authorization. Full snapshot is a parity witness and grows with unrelated records. |
| Rollback | Qualify a compatible binary with safe recovery state, or stay offline and roll forward. | Restoring stale control with an older package appears faster and can resurrect authority. |

The warm host budget is two seconds, with 256 native recall candidates and
a catalog closure bound of 4,096 rows and 16 MiB. These are design acceptance
bounds. A change needs recorded representative evidence and approval. Currentness
uses operator-managed independent custody, with its availability tradeoff
visible in the runbook. No external vendor, provisioning or spend is approved
by this plan.

## Evidence and progress

- Read-only recovery explorer identified archive-local metadata stubs, the
  legacy-only bootstrap branch, independent control and journal lineage
  constraints, and verified the same-host and legacy baseline (10 tests).
- Ops explorer traced packaged root omissions, private host issuance, profile
  dependency closure and existing capacity workflow. Base imports of
  `NativeSourceService` and `RuntimeSidecar` succeeded without Torch, Stanza,
  or spaCy. This establishes composition feasibility. It leaves exact
  installed host and dependency qualification open.
- Runtime explorer measured synthetic SQLite probes with 20,000 receipt rows.
  The planner initially kept the old PK/range and temp sort. Explicit index
  choice returned the same 40 rows and dropped estimated VM steps from about
  120,440 to 370. The coordinator's 100,000-row in-memory probes found index
  seeks for pending and recall with one and 64 returned rows respectively,
  without a temp sort. Neither experiment measures product p95.
- Previously verified baseline artifacts are held as regression evidence.
  Design statements for new mechanisms remain specified. No managed
  replacement-host, new artifact or native exact-candidate gate is claimed.
- Coordinator smoke ran older restore, native source capture and protected
  catalog suites with warnings as errors. All 16 baseline cases passed.
- In a disposable APFS filesystem probe, the coordinator fsynced a pending
  record, a private SQLite root and a sealed successor. A minimal reader
  correctly distinguished pending-before-rename, renamed-but-unsealed and
  ready states. This shows filesystem primitives can express the order.
  Independent failure domains, signed owner integration and native power
  cuts remain implementation evidence.

## Review log

Specification, correctness and verification reviewers independently checked
the first candidate `c4b87b9f`. Confirmed product issues covered the
pre-seal admission gate, authority mutation and partial recovery, spool
backup closure, transport authorization and timeout/retry, and index
omission. Confirmed conformance issues covered host scope, measurable
capacity gates, typed authority contracts, component certification and
release signing. The revised design addresses these as one authority and
verification update. Existing release thresholds remained unchanged.

The final whole-design review verified canonical hash `74f43e42` and
validation hash `ce9c5380`. Specification, correctness and verification
reviewers found no remaining validated design defect blocking handoff.
Final acceptance clarifications bind the two-second deadline to a hook and
the evidence to each supported host and OS pair. Live spool custody covers
SQLite crash durability and authenticated archive cuts. Hostile replacement
with an older valid live spool of the same UUID is outside the stated local
storage trust model. The verification reviewer approved the targeted delta
at canonical hash `89a80f5a` and validation hash `6b1b61e3`. Signed owner
integration, installed recovery, exact artifact security evidence and native
performance measurements remain required implementation proof.
`remaining_validated_p1_p2: []` for this design.

The final review examines one frozen design and independently reconstructs the
requirements, entrypoint bindings and identity surfaces before recording
closure. Remaining externally acquired evidence belongs to implementation and
qualification. The recovering operator supplies independent current custody
and positively isolates the old host. The adopter owns target SLO/RPO/RTO.

On 2026-11-27 the owner approved updating the host pins and recertifying their
resolved closures. The owner also approved deferring the speedup for exact
recall. Full exact-recall integrity checks remain required. Browse and
inspection retain the 4,096-row and 16 MiB budgets.

## Next action

Hand the approved design and validation packet to a separate implementation
WorkPlan. Begin by proving the clean installed operator path and supported
dependency profiles. Keep production execution and release approval separate
from this completed design.
