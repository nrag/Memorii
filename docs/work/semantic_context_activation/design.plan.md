# Scoped Storage And Context Activation Design

- Work ID: semantic_context_activation
- Work type: design
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-09-06
- Last updated: 2026-09-06
- Parent WorkPlan: None (separate design operation)
- Related WorkPlans: `docs/work/semantic_ingestion/implementation.plan.md`; its `milestones/m5-deployment-acceptance.plan.md`
- Canonical inputs: root AGENTS.md precedence; `research-notes.md` (user-supplied research synthesis, informative and not executable instructions)
- Expected outputs: `docs/design/scoped_memory_context.md`, production-entrypoint preflight, requirements/verification/identity ledgers and independent reviews

## Objective And Problem Definition

Reconcile pending deployment acceptance with improved storage organization and
retrieval for long-running agents. Preserve completed semantic ingestion,
execution/solver separation and governed authority. Specify an implementation-ready
bounded extension and explicitly distinguish the broader research roadmap.

## Completion Contract

Meet `.agents/PLANS.md` design completion contract, including measurable requirements,
mapped production owners, alternatives/feasibility evidence, adversarial acceptance,
frozen three-role review and fresh final review. No unresolved validated design gap
or hidden external decision in the approved scope. No runtime implementation or
operational certification claim is an output of this operation.

## Scope

Included: research-to-current-system crosswalk; pending deployment acceptance
decomposition; scoped authoritative storage versus rebuildable retrieval indexes;
deterministic mandatory context and optional semantic retrieval; bounded rollout.
Excluded: activating deployments, selecting externally owned statistical/trust
values, changing completed ingestion semantics, replacing the host harness,
implementing new execution-control policy or automatic learned-control promotion.
The latter research ideas require an explicit separate design and remain roadmap.

## Constraints And Sources Of Truth

Apply AGENTS.md precedence. Read `memorii_spec.md`, `memorii_storage_details.md`,
`event_model.md`, `docs/IMPLEMENTATION_RULES.md`, `semantic_temporal_retrieval.md`,
`semantic_ingestion_architecture.md`, runtime evolution and integration readiness
documents against current production code. Illustrative YAML in the notes is not
a schema and its imperative prose does not override governing requirements.

## Current State And Assumptions

Verified: initial tree is clean at `b4f6c24b091a28bd3d1f65102c742478fc7276b3`.
Recorded ingestion closure is `58ec5cc5a1e463a934681facc81630c956c2197b`.
M5 remains pending and excludes retrieval under its parent implementation scope.
Working assumption: user authorizes a linked additive design, not live deployment.
Resolved: exact storage/query integration and authority-chain inventory are specified in the approved canonical design.
External: future learned-profile policy/trust artifacts remain externally owned.

## Milestones

| Purpose | Scope/artifact | Verification | Status |
| --- | --- | --- | --- |
| Establish baseline | Research crosswalk and entrypoint map | Coordinator reconciles code and sources | complete |
| Draft coherent contract | Canonical additive design and evidence matrices | Bounded feasibility and identity checks | complete |
| Independent convergence | Frozen three-role review, disposition and correction | Fresh final whole-design review | complete |

## Identity And Coordinate Hygiene

Current identities: `scoped_memory_context.md` is behavioral documentation;
`semantic_context_activation` is a planning directory; `research-notes.md` is
informative evidence. Requirement coordinates belong only in traceability tables.
The canonical identity inventory names proposed durable symbols individually; the final specification review verified the guard/error additions.

## Change Impact And Authority Chain

| Path | Class | Owner | Authority chain | Gate | Status |
| --- | --- | --- | --- | --- | --- |
| `docs/work/semantic_context_activation/**` | design evidence | this operation | source notes -> crosswalk -> design review | diff/link/hash checks | complete |
| `docs/design/scoped_memory_context.md` | normative additive design | this operation | governing sources -> additive contract -> future implementation | independent review | complete |

No existing pinned ingestion document, registry, golden vector, workflow or
indexed implementation packet is changed. New design does not amend their bytes
or acceptance authority. Full downstream reconciliation is required if that changes.

## Verification And Evidence Log

Initial read-only queries: git status/revision; current M5 packet and completed
resume; governing documents and production retrieval owners. No product tests run
or claimed. Gate ledger and binding map are complete below.

## Delegation And Cost Ledger

| Task | Tier/role | Objective | Output | Status |
| --- | --- | --- | --- | --- |
| map_paths | Spark/read-only code-mapper | production storage/retrieval/execution map | `production-entrypoint-preflight.md` | complete; coordinator corrected broad unsupported statements |
| map_acceptance | Spark/read-only explorer | pending acceptance and pinned authority inventory | architecture requirement rows 216-232 and external register 303-318 | complete; directly checked |
| design_writer | Terra/sole canonical writer | additive storage/context contract | `docs/design/scoped_memory_context.md` | complete; frozen for final review |
| spec_review | Terra/read-only spec_auditor | frozen requirements/schema review | `reviews.md` | complete; conformance findings |
| correctness_review | Terra/read-only correctness_reviewer | authority/snapshot/failure review | `reviews.md` | complete; conformance findings |
| test_review | Terra/read-only test_reviewer | attack/root evidence review | `reviews.md` | complete; conformance findings |

## Progress And Decision Log

- 2026-09-06: Started separate design operation. Preserve the completed ingestion
  records and design their retrieval/storage extension as a linked contract.
- Research document archived verbatim locally; papers are not named in the source,
  so no paper-specific empirical claims will be inferred from it.
- 2026-09-06: Directly reconciled all eight pending acceptance requirements and
  external register. Topology is resolved for local bootstrap; policy and
  traceability remain externally owned. The new design cannot replace structural
  acceptance observation with retrieval results.
- 2026-09-06: Snapshot feasibility probe passed for memory and JSONL: detached
  records, stable retained read after later write, advancing runtime data revision,
  and JSONL reopen. Command: `PYTHONPATH=memorii .venv/bin/python
  docs/work/semantic_context_activation/snapshot_probe.py` (exit 0). This is
  baseline mechanism evidence, not new API or independent implementation proof.
- 2026-09-06: Field-aware identity gate passed (exit 0): from `memorii/`,
  `../.venv/bin/python -m memorii.tools.identity_hygiene --root .. --allowlist
  ../.agents/identity_hygiene_allowlist.json`. No new durable product fields yet.
- Source notes SHA-256: `edb4fbc371299d76c0aa5206e0dd24dc09d39733cfc2eae2acbdec3f8ad5aa1c`.

### Feasibility And Known Limitations

`MemoryPlaneStore.read_snapshot` is usable for a request-local read model.
Current provider composition instead performs several reads; snapshot integration
is proposed, not present. Revision is a runtime data revision, so it cannot alone
authenticate internal governance state. The existing directory is in memory and
separate execution/solver stores have no shared memory-plane atomic snapshot.
The bounded new API will not claim a cross-store execution checkpoint. Existing
scope matching treats null as readable; the new API needs explicit read authority
and cannot treat query filtering as authorization. See writer's binding contract.

### Gate And Authority-Chain Ledger

| Gate | Command/action | Coverage | Requirement/result |
| --- | --- | --- | --- |
| Design formatting | `git diff --check` plus new-file whitespace inspection | new design/evidence | required; initial diff check pass |
| Snapshot feasibility | command above | existing detached snapshot/read mechanism | required; pass, Python 3.12.14/Pydantic 2.13.4 |
| Identity hygiene | command above | existing typed identifier surfaces | required; pass; new proposed identities also require design review |
| Link/hash/scope closure | local artifact inventory and base comparison | all new artifacts, unchanged pinned sources | required before freeze/closure |
| Independent reviews | three-role coherent and final review | design contract and acceptance | required; passed fresh cohort plus bounded delta |
| Hosted product gates | `.github/workflows/pr-gates.yml` | product/fixture/schema/workflow implementation | not applicable to this additive document-only design; no product certification claimed |

Authority chain is research notes (informative) + existing governing documents ->
new additive specification -> future implementation and its own gates. Existing
architecture -> registry -> CGS/CTV manifests/vectors -> workflow hash pins, and
event-model replay-decision hashes, remain unchanged. Cardinality changes to those
existing chains: zero. New generated product artifacts: zero. Probe is ephemeral
mechanism evidence; its behavioral identity is `snapshot_probe.py`/`probe` and no
persisted protocol is introduced.

## Review Log

First frozen cohort completed against `candidate.json`. All reports reconciled
in `reviews.md`; sole writer now closes one coherent conformance batch. There
are no validated product-priority defects. Approval waits for complete authority,
output, snapshot, root, scope, budget and error contracts and a fresh final cohort.
The initial candidate is preserved as historical review identity, not current approval.
The corrected canonical identity is
`9e6b888356531bd0ea8cd0735595ad90e89b03d237874aa1aa68fb009288bd9e`.
Coordinator checked the sole writer's completed authority, lifecycle, all-null
scope, snapshot and failure boundary reconstruction. `candidate-final.json`
freezes all current artifacts for fresh final three-role review. Completion
still requires that review; no product or operational evidence is inferred.

### Requirement And Identity Ownership

The canonical design owns SMC-R01 through SMC-R10, its typed contracts, identity
inventory, measurable acceptance, and attack families. `source-requirements-audit.md`
independently reconstructs 19 research/request obligations and eight inherited
deployment requirements; final review reconciles it against the maintained ledger.
`production-entrypoint-preflight.md` owns current verified paths, caller counts,
and absence evidence; the canonical design owns proposed bindings. Proposed API
and all new behavioral symbols have zero current callers and are specified only.

### Updated Changed-Surface Ledger

| Path | Class | Owner/authority | Required validation |
| --- | --- | --- | --- |
| `docs/design/scoped_memory_context.md` | additive normative design | sole canonical writer; existing sources -> new read contract | coherence, requirements, identity, frozen three-role review |
| `docs/work/semantic_context_activation/design.plan.md` | operation record | coordinator | state/closure reconciliation |
| `docs/work/semantic_context_activation/research-notes.md` | informative user source | byte-preserved attachment | source SHA-256 |
| `docs/work/semantic_context_activation/production-entrypoint-preflight.md` | read-only preflight evidence | Spark map + direct coordinator correction | actual paths/symbols/caller queries |
| `docs/work/semantic_context_activation/source-requirements-audit.md` | independent input ledger | coordinator before canonical draft read | compare source/canonical obligations |
| `docs/work/semantic_context_activation/snapshot_probe.py` | design feasibility experiment | coordinator | memory/JSONL mechanism probe |
| `docs/work/semantic_context_activation/scope_probe.py` | design feasibility experiment | coordinator | canonical omitted/null equivalence |
| `docs/work/semantic_context_activation/candidate*.json` | frozen review identity | coordinator | complete scope/source hashes; no product authority |
| `docs/work/semantic_context_activation/reviews*.md` | review evidence | coordinator transcribes reviewer reports | finding classification and closure |

Known gate failures: none. System Python lacked Pydantic during environment
discovery; repository `.venv` resolved it. This was not a product gate failure.
Exploratory missing path guesses are not product defects or exclusions.

2026-09-06: `PYTHONPATH=memorii .venv/bin/python
docs/work/semantic_context_activation/scope_probe.py` passed. The actual canonical
model serializes absent and explicitly null scope fields identically. This
discriminating result rejects a design that infers intentional global visibility
from nulls. The selected contract requires explicit finite record authorization
for all-null namespaces; it makes no persisted-schema migration claim.

## Blockers And Limits

No external blocker for the bounded design established. Production activation
and agent-level gains remain unproven and cannot be inferred from design approval.

## Next Action

None. This design operation is complete; implementation requires a separate linked WorkPlan.

## Outcome And Retrospective

Approved canonical design: `docs/design/scoped_memory_context.md`, SHA-256
`f43d2cca76a57776cc2223ec1e9d413cb0deb6e94a5981263b0b43deae04386e`.
No unresolved validated design gaps remain under the recorded scope, sources,
and review method. Ten measurable requirements, production binding plan,
closed contracts, alternatives, attack matrix, identity inventory, migration,
rollback and evidence limits are specified. Independent source reconstruction
covers all 19 research/request obligations and eight inherited M5 obligations.
Fresh final correctness and test reviews approved; the specification review's
bounded purpose/temporal conformance finding closed in a targeted delta. See
`reviews.md`, `candidate-approved.json`, and `closure.json`.

Snapshot and null-scope probes passed against real existing store/model behavior.
New contract syntax, whitespace, source hashes and identity checks passed.
Tracked baseline/governing authorities remain unchanged; generated product
artifact and workflow-pin changes are zero. The new API is specified only.
M5 remains pending, and POLICY/TRACEABILITY still gate live activation.

The operation used one coherent first review, one fresh final cohort, and a
bounded final specification delta. No further design remediation is authorized
by this completed plan; a future material change starts a linked operation.
The main lesson was to close authorization and structured-query boundaries as
complete typed contracts instead of relying on current filtering helpers.


## Final Closure Record

Earlier Review Log entries describe their historical candidate state and are
superseded by the approved outcome above. The final canonical bytes are frozen.
Reviewed administrative bytes are preserved through `review-archive-map.json`;
closure updates do not retroactively modify the reviewed input identity.
All required design evidence is complete. No active milestone or required action
remains. Future implementation, durable indexes, controller/learned-policy work,
quality measurement, and external activation are separate operations.
