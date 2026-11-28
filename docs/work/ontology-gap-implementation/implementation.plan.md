# Implement the remaining ontology lifecycle

- Work ID: ontology-gap-implementation
- Work type: implementation
- Delivery fidelity: Level 2 for signed-in local work and household trials
- Status: active
- Coordinator: Codex
- Created: 2026-11-27
- Last updated: 2026-11-27
- Parent WorkPlan: [reviewed gap analysis and delivery order](../learned-ontology/design-gap-closure.plan.md)
- Related WorkPlans: [discovery design](../learned-ontology/design-packaged-catalog-discovery.plan.md), [v8 exact read closure](../ontology-read-workflow/implementation.plan.md), [earlier learning implementation](../learned-ontology/implementation.plan.md), parallel v8 hardening
- Canonical inputs: [learned ontology](../../design/learned_ontology.md), [base catalog](../../design/learned_ontology_base_catalog.md), [installed and legacy addendum](../../design/learned_ontology_hermes_and_legacy_addendum.md)
- Expected outputs: five sequential installed journeys with per-requirement evidence and a reviewable change at each milestone

[Resume packet](resume.md) · [Production entrypoint preflight](production-entrypoint-bindings.md)

## Objective and completion

From the tool list, an authenticated host can discover a relation and recall a
bill date. An authorized owner can review, reject or select a learned schema
edit and inspect or recall its authorized facts after restart. Two adapters
can submit observations into the same learner. Prove an observed second
relation, a manually submitted candidate with the observer and model disabled,
and a separate learned subtype. The existing catalog stays useful without
API keys. The signed-in account owns its local household logs and fact scope.

**1/5 milestones closed.** The packaged discovery and protected read
portion of OCI-01–04 is verified. The learned read portion and the four
partially exercised OLE requirements still have downstream acceptance.
The v8 packaged exact read and the narrow learned `mentors` evidence carry
forward at their recorded revisions. All 14 OLE rows below reflect the status
of the additional work. Close in order. Each milestone requires its frozen
design, scope-relevant manual work and household witnesses on the installed
path, ordinary failure proof, current gates, focused review and
`remaining_validated_p1_p2: []`. Name both witnesses when freezing the
milestone matrix. Where the new capability concerns only one domain,
exercise the other domain with its existing protected baseline.
Record base, head, workflow checkout, CI URL and evidence maturity. On the
existing authorized branch, commit and push the milestone when it closes.
If unrelated work shares that branch, stage only owned paths and reconcile
the push range before publication.

## Scope and readiness

- Entry-point mapping baseline `80fc585228cf0b7d3e59067012f3d6998f34bbf8`.
  Readiness was refreshed at `c0fa889a1791fe059b94347215ecf03ecac275f1` on
  `codex/durable-delivery-implementation`, which adds managed storage and
  operator-secret hardening. The prior hosted exact-read
  closure exercised head `524fd8c6` via [workflow run 46083808916](https://github.com/nrag/Memorii/actions/runs/46083808916).
  New behavior requires new evidence.
- The frozen discovery design's canonical SHA-256 is
  `408be6aa9a2d263e55a566a7889ce81c3c87b0e007eb9109e2448580aa3d2c45`.
  The reviewed [capability audit](../learned-ontology/ontology-capability-audit.md)
  SHA-256 is `259a83e09810f5be09f2733d3291e59187488d2691e383eac1a8736a0226485e`.
  The audit and roadmap supply scope and evidence. Each packet names the
  design still required for its implementation. No deviations are approved.
- Governing precedence is [spec](../../design/memorii_spec.md),
  [storage](../../design/memorii_storage_details.md),
  [events](../../design/event_model.md),
  [implementation rules](../../IMPLEMENTATION_RULES.md) and the ontology
  contracts above. Carry forward fact/catalog grants, provenance validation,
  history, read-only lookup, and candidate-versus-committed separation.
- Existing dirty files belong to the prior audit, parallel v8 storage and
  runtime hardening, and virtual employee work. This work owns only
  `docs/work/ontology-gap-implementation/`. Recheck overlapping runtime
  files and pin the implementation base at each handoff.
- The parent tracks full managed default-persona/household verification and
  generic standalone no-key fact authoring as separate follow-up. Preserve
  H8 under its existing user-context owner. Calibrated auto-promotion,
  wider namespace rollout, interchange, and Level 3 release evidence
  remain deferred. No implicit remote fallback, tool-granted household
  access or cross-scope replay.

## Sequential milestones

| Order | Packet | Observable completion | Status |
| --- | --- | --- | --- |
| 1 | [Packaged catalog discovery](milestones/packaged-catalog-discovery.plan.md) | Both installed bindings expose discover/clarify/recall without a key, starting with a bill due date. | Complete for Level 2. Hosted scoped context, static analysis and Package Smoke passed. |
| 2 | [Learned catalog review and recall](milestones/learned-catalog-review-and-recall.plan.md) | Owner decision and retry work. A selected exact-parent `mentors` version is inspectable and readable. | Active design readiness |
| 3 | [Verified recurring gap](milestones/verified-recurring-gap.plan.md) | Two adapters yield one durable, scoped, explainable gap from independent evidence. | Queued behind 2 |
| 4 | [Grounded relation creation](milestones/grounded-relation-creation.plan.md) | Observed and manual paths exercise a different relation through paired evaluation, owner selection and protected use. | Queued behind 3 |
| 5 | [Learned entity subtype](milestones/learned-entity-subtype.plan.md) | An independently evidenced subtype is approved and usable with inherited capabilities. | Queued behind 4 |

## Requirement coverage

Packet acceptance is a subset of the governing requirement. Keep the parent
requirement partial whenever separate follow-up or broader design evidence
remains. OCI means the existing exact catalog inspection contract and its
recall boundary.

| Requirement | Implementation allocation | Verification owner | Other evidence or remaining work | Status |
| --- | --- | --- | --- | --- |
| OLE-01 | 3, 4, 5 | Observation, admission, installed host | Disabled observer pending and preselection zero facts | not started |
| OLE-02 | 2, 3, 4, 5 | Current grants and lineage | Agent-local bound, wider scopes deferred | not started |
| OLE-03 | 4, 5 | Closed edits and catalog/type registry | Separate typed edit paths | not started |
| OLE-04 | 2, 4, 5 | Review, evaluation and selection | Accept/reject, withheld cases, restart, CAS and rollback | not started |
| OLE-05 | 2, 4, 5 | Selected catalog and protected read/write | Preserve verified history, generic structured admission separately tracked | not started |
| OLE-06 | 2, 4, 5 | Ordinary replay writer | Restart, grant withdrawal and idempotent retry | not started |
| OLE-07 | 2, 3 | Recovery and scoped status | Reproduced publication defect, authority probe pending | not started |
| OLE-08 | 1, 3, 4, 5 | Installed dual adapter bindings | Packaged tools locally verified through both bindings. Learning through both adapters still open. | in progress |
| OLE-09 | 1, representative regression | Packaged catalog | Work-item and ambiguous project-owner reads passed locally. Full managed persona matrix separately tracked. | in progress |
| OLE-10 | 1, 2, isolation regression | Protected read and user-context | Signed-in bill recall passed locally. Full home/H8 matrix separately tracked. | in progress |
| OLE-11 | 3, 4, 5 | Observation and recurrence | Three lineages, two sessions, duplicate and rejection suppression | not started |
| OLE-12 | 3, 4 | Local/host capability and semantic owner | Generic standalone fact authoring separately tracked, optional remote profile deferred | not started |
| OLE-13 | 2, 4, 5 | Paired evaluator and owner review | Owner approval only in scope. Automatic confidence calibration deferred | not started |
| OLE-14 | 1, 3, 4 | Both installed roots | No-key packaged reads passed locally. Pending discovery and manual learned review still open. Generic fact authoring separately tracked. | in progress |
| OCI-01–04 | 1, 2 | Catalog and protected recall | Packaged browsing and exact recall locally verified through configured bindings. Stock scope, learned witness and hosted verification pending. | in progress |

## Change impact and authority

The only observed new surfaces are planning documents. Each packet forecasts
its Python contracts, test and composition surfaces. Runtime/schema changes
and serialized field names await the relevant design. CLI, deployment,
external providers, dependency changes and packaged catalog edits are outside
scope unless a linked design and impact review identify a required change.

| Surface | Owner and authority chain | Gate | State |
| --- | --- | --- | --- |
| WorkPlan files | Coordinator → requirement map → packet → closure record | Link, scope and whitespace checks | Planned here |
| Host read tools | Factory → authenticated ingress → catalog projection and protected snapshot → release; package entrypoints unchanged unless selected design changes them | Static, scoped context, host integration, Package Smoke for changed installed surfaces | Forecast |
| Learned catalog and evaluator | Closed declarations and capabilities → immutable parent/bundle and pointer → replay/pin → writer and historical read → exact tests and any affected checksums | Static, unit, scoped context, installed lifecycle and affected authority/artifact jobs | Forecast |
| Observation and proposal binding | Authorized retention → scoped observer/recurrence → validated candidate → durable status | Static, unit and installed host tests | Forecast |

Keep an identity ledger in the active packet from its first code edit. Track
typed requests, commands, operation tags, persisted identities, fixtures,
artifacts and CI labels down to exact fields. Reuse behavior-named existing
contracts. Run the field-aware identity check and representative mutations
on each changed surface before closure. Refresh all affected package indexes,
digests, pins and validators if an approved design changes a derived input.

## Verification and known failures

Shared commands run from `memorii/` in the activated project environment.
Local interpreter is 3.12.16. Static analysis, scoped-context and Package
Smoke use Python 3.11 in current CI. Read the actual
`.github/workflows/pr-gates.yml` again at every candidate, reconcile all
affected shards and aggregates, and record the exact job evidence.

```sh
python -W error -m pytest tests/unit -p no:cacheprovider
ruff check memorii tests
pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"
python -m memorii.tools.identity_hygiene --root .. --allowlist ../.agents/identity_hygiene_allowlist.json
pytest -W error tests/integration/test_scoped_context_production_binding.py -p no:cacheprovider
```

| Gate | Command or workflow owner | Status |
| --- | --- | --- |
| Static Analysis and unit shards | `static-analysis`, `unit-test-shards`; run affected workflow shards with their Python version and warning policy | Pending candidate |
| Package Smoke | `package-smoke` Build and smoke-test wheel step; full acquisition, installed proof, rejection checks and wheel import probes | Pending candidate, no substitute wheel-only claim |
| Scoped Context Integration, installed host checks | `scoped-context-integration`, affected host jobs and manual bill/work and learner journeys from packet | Pending candidate |
| Aggregate PR checks | `unit-tests` and other applicable required jobs at the actual hosted checkout, record head separately | Pending candidate |

Known P2 at the pinned baseline: the
[reproduction commands](../learned-ontology/ontology-capability-audit.md#reproduction-commands)
store `evaluating`, then load fails with `proposal is unavailable`. The
recovery owner is packet 2. Installed owner-grant withdrawal is a known
evidence gap, with a separate verify-before-mutation case in that packet.
Prior CI success applies only to the older delivered read path. No new lint,
type-check or CI failure is classified by this planning task.

## Progress and review

- 2026-11-27. Planned five slices from the reviewed audit. No implementation
  commands or candidate gates were run in this planning turn.
- Delegation. `ontology_plan_mapper` (fast, read-only) traced five boundaries
  at `80fc5852`. Its findings are reconciled in the entrypoint preflight.
  Mapping is complete. Coordinator is the sole document writer.
- Review. `ontology_validation_matrix_check` (fast, read-only) confirmed the
  order and identified three planning verification omissions. Product
  priority was not applicable and disposition was `changes_required`.
  Added authorized rebase and distinct legacy denials with owner/status
  evidence, made the observed and manual creation journeys independently
  testable, and required named work and household witnesses at each freeze.
  Targeted delta review passed. This is plan evidence.
- The parent audit passed independent review. Freeze the active packet and validation matrix for
  targeted independent review before its writer starts. At Level 2 use focused
  review on real-path correctness, ordinary failures, isolation and recovery.
- Keep the index and active packet current after each material result. Move
  the active pointer only after evidence and the milestone push are recorded.
- The user selected the host's verified canonical subject ID. No subject
  search is in scope. The Section 13 tool and browse design passed focused
  independent review and the sole product writer started the discovery slice.

## Next action

Execute the [proposal-state recovery slice](debug-learned-evaluation-recovery.plan.md)
for milestone 2 before widening learned catalog selection and recall.
