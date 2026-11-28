# Close the remaining ontology gaps

- Work ID: ontology-gap-closure
- Work type: design
- Delivery fidelity: Level 2 for signed-in local work and household trials
- Status: complete for Level 2 gap analysis
- Coordinator: Codex
- Created: 2026-11-27
- Last updated: 2026-11-27
- Parent WorkPlan: None
- Related WorkPlans: [v8 read workflow closure](../ontology-read-workflow/implementation.plan.md), [catalog inspection design](design-catalog-inspection.plan.md)
- Canonical inputs: [learned ontology](../../design/learned_ontology.md) Sections 3-10 and 12-13, [Memorii specification](../../design/memorii_spec.md), [storage](../../design/memorii_storage_details.md) and [event model](../../design/event_model.md)
- Expected outputs: independently reviewed lifecycle gap analysis, evidence ledger, and proposed milestone boundaries for subsequent design

## Baseline and objective

Memorii `80fc5852` includes the v8 protected read workflow verified in
[PR #126](https://github.com/nrag/Memorii/actions/runs/46083808916).
The installed 56-relation catalog supports exact-ID and normalized full-name
or alias inspection. The paired diagnosis accepts a verified subject and
can check the inspected catalog version. Both authenticated host bindings
passed with no API key, network or write-tool authorization. These are
closed gaps and provide the starting point for the milestones below.

The remaining read gaps are discovery from an agent's tool list and
inspection and recall of an approved learned relation. The creation gaps
cover finding a verified schema gap in transcripts, generating a grounded
declaration, and evaluating and promoting it beyond the single
`mentors(Person, Person)` case. NVIDIA's
[glossary and answerability tools](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/mcp/auto_ontology_mcp/tools.py)
motivate discovery. Its [certification code](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/auto_ontology/dal/terms.py#L157-L235)
motivates a review view with visible evidence and status. Memorii's
governing contracts determine authority and promotion.

## Gap analysis coverage gate

The [capability audit](ontology-capability-audit.md) records the pinned
inventories, evidence dispositions, requirement reconciliation and probes.
The proposal below is the delivery effect of that audit.

Bound the comparison to the ontology lifecycle at the pinned Memorii and
NVIDIA revisions. Cover both their inputs and the contracts that the local
work and household workflows require. Treat the milestone order as proposed
until the coverage gate is met.

1. **Build two inventories independently.** Walk each repository from its
   executable entrypoints, schemas, storage owners and tests. Separately
   reconstruct Memorii's requirements from its governing documents and user
   decisions. Reconcile these inventories after each is recorded so the
   shipped path and the requirements can each reveal omissions.
2. **Trace each lifecycle stage.** Include base catalog authoring and
   installation, source intake and lineage, observation and failure
   attribution, deduplication and recurrence, candidate construction,
   declaration and type validation, evaluation and calibration, owner
   review and activation, versioning and rebase, replay and rollback,
   inspection and recall, and operator visibility. Include disabled model,
   restart and scope-denial cases where they affect the supported path.
3. **Record evidence per capability.** For each row capture the user
   outcome, each project's owner and entrypoint, code reference, strongest
   executed test or reproducible probe, evidence maturity, and consequence
   for Memorii. Assign one disposition: verified, partial, missing,
   outside the agreed scope, or unresolved. Include evidence for both
   positive and negative conclusions.
4. **Challenge the inventory independently.** Have a spec auditor
   reconstruct coverage from the governing contracts, a correctness
   reviewer trace both implementations, and a test reviewer challenge
   whether the cited evidence exercises the production path. Ask each
   reviewer to find omitted stages and counterexamples. Reconcile their
   findings before assigning milestone scope.

The analysis can close when every lifecycle stage and in-scope requirement
has a disposition with evidence, every exclusion has a rationale, and every
unresolved material behavior has a named verification action. Resolve those
material uncertainties before calling the analysis complete. Publish the
matrix with the revisions, review findings, and limitations so a reader can
reproduce the conclusions.

### Learned edits are separate capabilities

Section 4 defines both `add_relation` and `add_entity_type`. The verified
`mentors` path covers one relation shape. V8 read acceptance covers the
packaged catalog. Milestone 5 separately covers subtype creation through
validation, activation, and protected use.

## Creation and learning gaps

| Stage | Current evidence | Gap to close |
| --- | --- | --- |
| Collect and classify | Two local adapters already feed one deterministic no-key `mentors` observer. When the observer is disabled, the runtime retains pending observations. | Prove the same durable learner with a second relation and an authorized host-supplied or local capability. Distinguish a catalog gap from source, extraction, entity resolution, retrieval and agent exposure failures. |
| Count recurrence | The narrow learner verifies source evidence and independent lineages before admitting a candidate. | Prove consistent grouping, deduplication and restart across hosts for a different relation. Expose the evidence count and reasons an observation was excluded to the authorized owner. |
| Generate and validate | Candidate admission checks for the fixed `mentors(Person, Person)` signature. The installed evaluator uses a frozen `mentors` corpus. | Construct a typed declaration from verified evidence for another relation, check it against the exact parent for collisions and unsupported types, and use a candidate-specific withheld evaluation set. Define how an owner can supply structured evidence when there is no observer. |
| Promote with evidence | The narrow path has owner approval, selection and rollback. The design's automatic confidence threshold is a policy target without calibration evidence. | Give the owner evidence of paired gain, regressions, abstentions and vetoes for the second candidate. Publish only an approved agent-local version and verify replay, restart and rollback. Any later automatic promotion needs measured calibration for its exact binding and scope. |
| Recover and maintain | A reproduced interruption leaves a persisted evaluation state the reader cannot decode. The narrow recovery path covers pointer selection and replay. | Resolve proposal retry and interruption behavior. Verify current mutation authority and status after activation or rollback if refreshing host authority fails. |

## Milestones

Execute in order. Approve each boundary through `$build-design` before
opening its linked `$implement-design` WorkPlan. Milestone identifiers
are planning metadata.

| Milestone | Design to resolve | Acceptance to close implementation | Status |
| --- | --- | --- | --- |
| 1. Discover and use the packaged catalog | Define one host-neutral read-tool contract over the existing ports. Choose the first supported discovery transport and a bounded deterministic partial-name or browse interface. Specify ordering, ambiguity, and how a caller obtains or supplies a verified subject ID. Reuse host-issued authority and carry the inspected version into recall. | From the tool list, use the same contract through Hermes and a generic authenticated host to find the bill relation and recall a date. Exercise an ambiguous work relation, missing subject, stale catalog and denied caller. Repeat after reopen with zero model calls, outbound access or read-triggered writes. | Proposed |
| 2. Make one approved learned relation readable | Specify how a new agent-local version binds the exact immutable packaged parent and verifies the complete effective catalog. Choose how an owner may explicitly rebase a provable early overlay. Specify a scoped review projection showing the proposed declaration, evidence, parent/candidate results, abstentions, blocking checks and decision. Reuse existing approval, activation and rollback owners. | An authorized owner reviews and approves `mentors`. After restart, the same tools inspect it and recall an authorized fact with no key. Prove peer-agent and foreign-account denial, failure on missing or ambiguous parent evidence, ordinary parent recall, rollback, and no widening of historical visibility. | Proposed |
| 3. Discover and verify a recurring gap | Reuse the coverage observation queue. Specify a provider-neutral observer contract, its first host-supplied or local binding, and its version, egress, retry and restart boundaries. Define typed failure attribution and canonical grouping over independent evidence. | Two transcript adapters feed the same scoped recurrence owner. Three independent lineages across two sessions qualify a verified gap for proposal. Duplicates, recall misses, uncertain roles and already-covered relations are excluded. Retry and reopen preserve counts and attribution. With no observer, pending status is visible and the packaged workflow works without a key. | Proposed |
| 4. Create, evaluate and promote a second relation | Select a genuinely different relation outside the packaged catalog. Replace relation-specific candidate construction and evaluation with bounded typed declarations and a candidate-specific evidence set. Define the owner-supplied structured path, validation and exact-parent paired evaluation. Reuse the review and catalog authority boundaries from Milestone 2. | Generate a candidate with source-span references and reject alias or type collisions, conflicting evidence and superseded parents. Compare the frozen parent and candidate on disjoint withheld positives, parent regressions, and abstention and scope cases. Show the evidence to an authorized owner. Approval selects one agent-local version. Restart, authorized replay, no-key inspection and recall, and rollback preserve facts and visibility. | Proposed |
| 5. Create and use a learned entity subtype | Specify a bounded subtype edit with one registered parent, declared identity/evidence rules and alias/inheritance validation. Reuse the candidate, evaluation and selection owners. | A subtype-only candidate can be evaluated and owner-approved without a relation edit. Prove parent compatibility, rejection of unknown parent or conflicting aliases, protected use after restart, and rollback that preserves historical meaning. | Proposed |

### Required milestone acceptance

- **Milestone 2, owner decision and history.** Record an authorized owner's
  rejection and show its terminal outcome after reopen. Deny an unauthorized
  decision and preserve proposal state, selected version and committed facts.
  Exercise seed-bound facts and genuinely unbound projection-era records
  separately across learned selection, restart and rollback. Deny malformed
  or out-of-scope legacy records through their respective readers.
- **Milestone 2, recovery and mutation authority.** Cover interruption before
  result recording, interruption while publishing a result, evaluator
  unavailability and retry, and already-terminal evaluation. Verify live
  grants at each approve, activate and select-prior mutation through Hermes
  and the generic binding wherever exposed. Require withdrawal before
  mutation to leave durable state unchanged. Exercise refresh failure after
  valid selection and after rollback, and verify that scoped status reports
  the durable result and the pending refresh accurately.
- **Milestone 4, manual creation.** With the observer and model disabled, an
  authorized owner supplies a typed candidate with verified retained source
  spans. The same validator and paired evaluation apply. Provenance or scope
  failure denies submission. Submission leaves selected catalog and facts
  untouched. An explicit approval is required to activate.

### Tracked follow-up

| Requirement | Owner and disposition | Closure evidence |
| --- | --- | --- |
| OLE-09/10, full default work and home coverage | Packaged catalog and user-context owners. Run a separate default acceptance slice so representative discovery and learned edits can proceed. The historical all-53 structured matrix and H8 evidence cover their recorded scenarios. | A current managed matrix against the agreed persona and household journeys, with representative transcript wording, correction, abstention, restart and scope checks. Cover H8 holder confirmation, correction, expiry, history and delegation/revocation through its typed user-context boundary. |
| OLE-12/14, generic no-key fact authoring | Authenticated source admission and semantic fact writer owners. Track in a separate source-authoring design slice. Existing protected reads and owner catalog-candidate submission can proceed independently. | A generic installed host submits a typed fact without a model, proves current source and fact grants, retries idempotently and reads the result through the protected workflow. Compare with the existing Hermes route and deny expired or foreign scope without mutation. |

## Design decisions and gates

- **Discovery and identity.** Core derives caller scope from the authenticated
  host binding. A discovery result may nominate relations. A separate
  authorized resolver or the caller's verified selection establishes subject
  identity before exact recall. Preserve a status-only denial or unavailable
  outcome when the selection cannot be verified.
- **Parent compatibility.** A historical catalog digest can identify more than
  one packaged version. Require exact retained evidence or an explicit
  authorized rebase. A read request cannot rewrite pointers, repair history,
  or infer broader scope.
- **Recovery and authority priority.** Complete Milestone 2's recovery and
  mutation-authority checks before widening activation or maintenance.
- **Promotion and no-key behavior.** Use owner approval for activation
  in these milestones. Recurrence qualifies evidence for review. A
  candidate still has to pass paired evaluation and the existing validation
  and authority gates. Report recurrence, evaluation outcomes and any
  available calibrated confidence as separate fields. A calibrated score
  concerns the proposed relation, while committed fact truth follows its
  own evidence and authority rules. An unconfigured observer leaves
  free-text discovery pending. A configured local or host capability must
  have explicit egress policy. No implicit remote fallback.
- **Acceptance and review.** Each milestone closes after its manual work and
  household journeys, restart and common failure tests, focused independent
  review, and applicable gates at the verified revision. Keep the chosen
  fidelity in the WorkPlan. Production rollout qualification, calibrated
  automatic promotion, enterprise SQL generation, and ontology interchange
  are outside this proposed delivery.
- **Household scope.** The signed-in user's account owns local transcript
  access and fact visibility. A household relation confers no read grant.

## Cohort review and conclusion

The spec auditor rebuilt the requirement inventory and confirmed all 14
OLE requirements have a disposition. The correctness reviewer traced
authoring, evaluation, selection, and reads in both projects. The test
reviewer independently ran all 190 Memorii tests and reproduced both
component probes on the pinned archive. The coordinator reran the
documented recipes and checked the cross-document links and OLE IDs.

| Confirmed finding | Audit disposition |
| --- | --- |
| Prior evidence combined the historical 53-row semantic run, the H8 user-context lifecycle, and current default breadth. Legacy continuity also required two distinct reader paths. | Addressed in the audit and acceptance criteria. Current full default acceptance remains assigned follow-up. |
| Owner rejection, generic no-key fact authoring and owner-submitted ontology candidates needed measurable and separate outcomes. | Addressed in Milestones 2 and 4 and the separate source-authoring slice. |
| The evaluation failure needed a reproducible boundary and independent checks for interruption, retry and current owner grants. | Documented runnable probes and assigned the reproduced P2 and the still-open host authority proof to Milestone 2. The runtime defect remains open. |

All three reviewers passed the corrected audit and roadmap in focused
follow-up. The reviewed audit SHA-256 was
`259a83e09810f5be09f2733d3291e59187488d2691e383eac1a8736a0226485e`,
and the reviewed roadmap SHA-256 before recording this closure was
`474fae433451ad257b03d1ec81777ee611dab35fc9b099b07cbe66cbc33891e1`.
The canonical design navigation update was reviewed with SHA-256
`ef1880d49a47bc06d73c02d95b16561ab628499cf04245038faff9dae939af13`.
No unresolved audit finding or external decision remains within the pinned
scope. The milestones each require a linked design before implementation
approval. No runtime contracts were changed during the audit.

## Next action

Open the linked design slice for Milestone 1, packaged catalog discovery.
