# Structured Lifecycle Recovery Lease Debugging

- Work ID: `structured-lifecycle-recovery-lease` (planning coordinate only)
- Work type: debugging
- Delivery fidelity: Level 2, early real-world manual testing
- Status: active
- Coordinator: `/root`
- Created: 2026-09-26
- Last updated: 2026-09-27
- Parent WorkPlan: `implementation.plan.md`
- Related WorkPlans: `milestones/default-catalog-and-home.plan.md`
- Canonical inputs: root `AGENTS.md`, `.agents/PLANS.md`, `docs/design/memorii_storage_details.md`, `docs/design/event_model.md`, `docs/design/semantic_ingestion_architecture.md`, and the M3 milestone packet
- Expected outputs: a bounded root-cause correction and focused installed regression for no-key default-catalog lifecycle correction.

## Objective

Allow an installed, no-key, captured-turn default-catalog correction to complete
through its existing Bootstrap V3 owner and persist a recoverable terminal.
The protected lifecycle reader may then use the atomically retained request and
reload history. This operation does not change public ontology semantics.

## Completion Contract

At Level 2, the deterministic installed correction reproducer must pass through
the public Hermes provider entry point, persist a terminal without a competing
lease, and retain the existing source/pin/grant authority checks. The focused
transport regression, installed correction/reopen journey, and affected
semantic-ingestion checks must pass. Higher-fidelity hostile lease/tamper and
full platform matrices are deferred to Level 3.

## Scope

Included: the captured retained-source correction handoff, Bootstrap V3 recovery
lease ownership, semantic terminal coupling, and the installed default-catalog
entity-correction proof. Excluded: changing `_safe_ranges`, public tool
grammar, catalog relation semantics, reader authorization, and release-wide
hardening.

## Expected And Observed Behavior

Expected: after a source-complete first turn and a catalog-pinned second turn,
`project_owned_by` correction submitted through
`MemoriiHermesMemoryProvider.handle_tool_call` commits and exposes its terminal
to the normal recovery reader.

Observed: the deterministic installed reproducer
`PYTHONPATH=memorii .venv/bin/pytest memorii/tests/unit/integrations/test_hermes_memory_provider_bridge.py::test_installed_default_catalog_entity_relation_commits_and_recalls -q`
returns `status: unavailable` after approximately 199 seconds. The outer
failure is `SemanticTerminalPersistenceService.persist`: "semantic ingestion
terminal operation is leased by a different execution". The retained JSONL
image shows the new correction operation in `preplanning`, leased by
`bootstrap-v3-recovery`, with a claimed recovery index and no terminal group.
The initial corpus assertion commits in the same installed environment.

Classification: implementation/recovery handoff defect in the Level-2 ordinary
correction journey. Reproducibility is two of two runs after the source-span
grammar was corrected.

## Identity And Coordinate Hygiene

| Surface | Identity class | Status |
| --- | --- | --- |
| Existing Bootstrap V3/recovery and semantic-terminal identifiers | behavioral/protocol | retained; no new durable identifier planned |
| This WorkPlan and experiment labels | planning/evidence | confined to this document |

## Hypothesis Ledger

| Hypothesis | Mechanism | Evidence | Discriminating experiment | Status |
| --- | --- | --- | --- | --- |
| Recovery owner acquires a valid lease but returns a nonterminal result, after which the generic terminal fallback incorrectly attempts to acquire a semantic-pipeline lease. | The fallback sees no `bootstrap_graph_terminal_persisted` reason and conflicts with the live `bootstrap-v3-recovery` lease. | Persisted control has owner `bootstrap-v3-recovery`; outer fallback raises exactly at its owner guard. | Trace the recovery reload/execute result and the terminal reason code for the correction operation. | confirmed containment defect |
| The correction's retained request/reload content fails graph planning after recovery claim, leaving the recovery state incomplete. | A lifecycle-only carrier or transition cannot be compiled by the graph executor. | The first ordinary corpus assertion commits; correction control has no terminal group. | Capture the graph result/reason at recovery execution without changing lease behavior; compare with an entity assertion. | disproved: graph replay is never reached |
| The direct structured producer assumes one proposal request, while the correction retains two sentence routes and legitimately requires source-wide lifecycle grounding. | `DirectBootstrapV3ProposalProducer.produce` returns `None` when `len(authority.proposal_requests) != 1`, causing `proposal_run_unavailable` before sealing. | The installed observer reports `SourceNormalizationNonCommit(phase='proposal_sealed', reason='proposal_run_unavailable')`; the correction source has two sentence routes. | Add a fast direct-producer two-route correction reproducer, then identify the existing source-wide/parent authority that can normalize its two independently grounded facts without duplicating the operation. | confirmed root-cause candidate |
| The leading-space replacement source corrupts normalization and causes the recovery branch. | The exact persisted span may alter source normalization. | The fast public transport test accepts the exact leading-space envelope and contexts; no parser rejection occurs in installed execution. | Run the same correction with the already validated source grounding while observing graph result. | weakened |

## Experiment Ledger

| Experiment | Hypotheses | Prediction | Result |
| --- | --- | --- | --- |
| Fast transport correction with leading-space replacement span | third vs. first/second | If grammar is causal, parser rejects. | Passed in 6.71s; envelope, replacement fact, and replacement mention contexts bind exact span. |
| Installed public correction rerun without internal parser probe | first/second vs. probe interference | If probe is causal, public call commits. | Failed in 198.97s with the same competing recovery lease. The probe is not causal. |
| Inspect retained JSONL after failure | first vs. other causes | A handoff conflict leaves an identifiable lease owner. | Control is `preplanning`, owner `bootstrap-v3-recovery`, state claimed, no terminal group. |
| Observe `normalize_after_recovery_claim` in the installed public journey | graph-planning vs. direct-normalization hypotheses | If graph planning is causal, normalization returns a V3 result; otherwise it returns its own noncommit. | Failed in 198.89s with `SourceNormalizationNonCommit`, phase `proposal_sealed`, reason `proposal_run_unavailable`; graph replay is not reached. |

## Changed Surface And Evidence

- Changed test surface: `memorii/tests/unit/core/semantic_ingestion/test_hermes_completed_turn_runtime.py` adds the exact retained leading-space correction transport regression.
- Changed integration test surface: `memorii/tests/unit/integrations/test_hermes_memory_provider_bridge.py` exercises the public corpus-based correction journey; it currently reproduces the defect.
- No production owner is changed by this debugging record.

## One Next Action

Coordinator reruns the installed corpus correction journey after the protected
reader reconstructs lifecycle state from native projection and group-effect
records, then records either its first causal failure or the resulting reopen
and reader evidence.

## Current Update (2026-09-26)

The direct producer now assigns a lifecycle operation once to its exact
assertion-anchor route and seals sibling abstentions; its focused route-owner
proof passed. The next installed correction reached native group commit and
failed with `BootstrapGroupObservationAuditError: planning construction
authority is absent`. The generic terminal lease conflict is downstream.
`_planning_construction_authority_for_operation` and `_native_reduction_inputs`
were fact-only; authority construction now selects the replacement fact for a
correction and the target fact for a retraction. This alone is incomplete:
`BuiltInBootstrapGraphTargetMaterializationPlannerV3` remains fact-only, while
the reducer requires lifecycle-specific corrected/retracted targets and
temporal-transition records. Exactly one next action is to build the smallest
native group correction/retraction reproducer from the graph-observation
retention helpers, then extend that shared planner/reducer invariant before any
further installed run.

## Current Update (2026-09-26, lifecycle planner)

The shared planner now resolves lifecycle claim selectors from the canonical
pending planning state first and then the sealed durable snapshot, rejecting
zero or multiple exact statement-digest matches. It produces the existing
correction/retraction planning seeds, immutable temporal-transition record,
transition evidence, and role-specific target bindings; the existing reducer
then emits accepted correction/retraction effects without a group-audit
exception. Planning construction authority now carries an assertion plus
transition temporal construction for correction and a transition construction
for retraction.

Focused proof passed:

`PYTHONPATH=memorii .venv/bin/pytest memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_observation_retention.py -q`

Result: `2 passed in 48.97s`. The new lifecycle case proves pending exact-match
correction and retraction acceptance, one temporal transition, and missing and
ambiguous target denial. Ruff and whitespace checks pass for the changed
production and test files. The installed public journey has not been rerun
after this focused proof.

## Current Update (2026-09-26, role-specific temporal authority)

The frozen installed rerun reached source-normalization authority construction
and failed before planning with `StopIteration`. The canonical Bootstrap V3
interpreter emits correction consensus roles `replacement` and `corrected`, and
retraction role `retracted`; it does not emit `assertion` or `transition` for
these operations. Authority construction now maps `replacement` to native
`replacement`, and `corrected`/`retracted` to native `transition`, selecting
each source consensus exactly once. The fact planner accepts its one fact
construction as `assertion` or `replacement`, preserving correction replacement
authority without relabeling its source consensus.

Focused source-normalization role proof:

`PYTHONPATH=memorii .venv/bin/pytest memorii/tests/unit/core/semantic_ingestion/test_source_normalization_lifecycle_temporal_roles.py -q`

Result: `4 passed in 6.61s`, covering the exact V3 correction and retraction
mapping plus missing-role denial. Py-compile, targeted Ruff and
whitespace checks pass. The installed rerun is deliberately not repeated here;
the coordinator owns it. The next action remains the installed corpus journey.

## Current Update (2026-09-27, canonical lifecycle selector)

The coordinator's installed V3-role rerun reached a persisted terminal but
abstained with exact reason `graph_target_missing`. The planner selected its
target by `BootstrapProposalFactV3.fact_digest`; correction/retraction source
facts necessarily receive new source-local mention and fact digests, even when
their resolved entities, predicate, scope, and value are the same immutable
claim. The selector now derives `AcceptedClaimIdentity` through the same
canonical resolved-target helper used by `_claim_assertion`, and matches only
`ClaimAssertion.claim_identity.assertion_key_at_recording` across pending
records before the sealed snapshot. It never selects raw labels or text.

Focused proof:

`PYTHONPATH=memorii .venv/bin/pytest memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_observation_retention.py::test_native_lifecycle_planner_selects_one_pending_claim_and_fails_closed memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_observation_retention.py::test_native_lifecycle_planner_selects_by_canonical_assertion_key memorii/tests/unit/core/semantic_ingestion/test_source_normalization_lifecycle_temporal_roles.py -q`

Result: `6 passed in 47.79s`. The new regression proves a distinct correction
subject mention/fact digest that resolves to the same canonical entity selects
the original pending assertion, while a distinct mention resolved to a changed
object remains `graph_target_missing`. Targeted Ruff and `git diff --check`
pass. This is canonical planner evidence; the production installed caller has
not been rerun for this change, so the Level-2 lifecycle journey remains open.

## Current Update (2026-09-27, scoped statement selector identity reuse)

The installed `graph_target_missing` persisted because every new source created
new canonical identity allocations before the lifecycle planner could compare
claim assertion keys. The canonical allocator now derives a source-independent
statement selector from exact grounded assertion/subject/object substrings (or
typed literal), predicate, polarity, commitment, attribution, and qualifier
substrings. It stores that selector in `ClaimAssertion.statement_digest` and,
for correction/retraction selector facts, resolves exactly one prior claim in
the authorized scope. Its immutable subject/object assertion refs then produce
`BootstrapExistingCanonicalIdentityDecisionV3` decisions. Zero, multiple,
conflicting, missing-entity, and foreign-scope matches become absent decisions;
no raw label or name is consulted. Exact same-text subject/object roles are
clustered only within one correction operation, so a changed replacement object
receives a distinct new allocation. Existing target projection now reads logical
and revision IDs from the authenticated entity payload.

Focused proof:

`PYTHONPATH=memorii .venv/bin/pytest memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_observation_retention.py::test_native_lifecycle_planner_selects_one_pending_claim_and_fails_closed memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_observation_retention.py::test_native_lifecycle_planner_selects_by_canonical_assertion_key memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_observation_retention.py::test_lifecycle_identity_allocator_reuses_only_one_scoped_prior_claim memorii/tests/unit/core/semantic_ingestion/test_source_normalization_lifecycle_temporal_roles.py -q`

Result: `7 passed in 61.68s`. The allocator regression uses a distinct source
with new mention IDs, proves one prior pending claim becomes an existing
decision, proves the changed replacement object remains new, and denies missing,
ambiguous, and foreign-scope selectors. The installed caller remains unrerun;
this is not a completed production entrypoint binding.

## Current Update (2026-09-27, interpreter provenance closure)

The first installed rerun at commit `6a7ebb48` reached the real V3 interpreter
and failed before canonical allocation. The correction subject's paired old and
replacement mentions share one segment provenance tuple, but the new cluster
builder retained that tuple twice. The closed cluster contract requires a
canonical set, so normalization rejected the publication and the outer
fallback later reported the already-known lease conflict. The cluster builder
now deduplicates provenance closure tuples before sorting. This is a narrow
construction defect; the scoped prior-claim allocator remains unchanged. The
next action is the same installed lifecycle journey on the corrected frozen
revision.

## Current Update (2026-09-27, native projection reader)

The installed rerun at `7a5b71ae` committed the correction, including the old
and replacement claim assertions, but the public current reader returned
`unavailable`. Two reader assumptions were false for this native path. The
lifecycle decoder inspected `native_compilation.accepted_carriers`, while the
committed transition and replacement claim records live under the accepted
effect's `transition_records` and `replacement_effect.planning_records`.
Further, this installed writer persists protected claim projections and
schema-2 catalog bindings without generic `ClaimState` rows.

The reader now decodes the committed group effect and reconstructs active,
superseded, and retracted transaction-time views from immutable protected
projections. Every projected result still passes the existing binding, pin,
catalog, current-grant, and endpoint-visibility verifier; malformed projection
identity fails closed. The exact persisted failed-run snapshot now returns the
replacement for current, both versions for history, and only the original for
an as-of timestamp before correction. The focused reader/runtime suite passes
`96 in 8.55s`; targeted Ruff and whitespace pass. This is focused and retained
snapshot evidence. The installed correction/current/history/reopen journey is
the one next action and no parent count changes yet.

The coordinator reran the installed journey on commit `27bf3e87`: `1 passed in
696.92s`. The native correction committed and protected current, history, and
pre-correction transaction-time reads completed through the installed Hermes
provider with no API key or model transport. This pass predates explicit JSONL
reopen equality assertions. The one next action is the same journey with those
reopen assertions added.

The first strengthened run at `cfbb1b53` reached post-restart in `1016.41s`
and returned `unavailable` before the protected reader because the test invoked
a Hermes tool without an active captured turn. The installed tool contract
requires `on_turn_start` and pinned schema egress in each process. The fixture
now starts a fresh recall turn and confirms `memorii_read_fact` schema egress
before comparing persisted current/history/as-of results. The one next action
is to rerun this corrected installed scenario.
