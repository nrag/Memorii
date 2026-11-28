# Ontology lifecycle capability audit

## Scope and baseline

This comparison covers creation, change, and consumption for a signed-in
user learning authorized agent memory at Level 2. It inventories NVIDIA's
database semantic layer and conversation graph independently. Where they
solve a different user problem, the disposition says which idea transfers
and whether Memorii needs it for the agreed workflow.

- Memorii source `80fc585228cf0b7d3e59067012f3d6998f34bbf8`. PR #126
  ran at merge checkout `5386369702013cd0d859be33331227fe39624fbd` of
  implementation head `524fd8c6`. The diff from that implementation head
  to this audit baseline contains two WorkPlan files. The 146 scoped-context
  tests and hosted gates apply to the same product, test and workflow bytes.
  [Hosted evidence](https://github.com/nrag/Memorii/actions/runs/46083808916)
- NVIDIA source [`086b25ec1dbaa8f5911fb746f691d113654b650c`](https://github.com/NVIDIA/auto-ontology/tree/086b25ec1dbaa8f5911fb746f691d113654b650c).
  Code and upstream tests inspected. No local NVIDIA service, database
  suite or model calls were run.
- Normative inputs are the [Memorii specification](../../design/memorii_spec.md),
  [storage](../../design/memorii_storage_details.md), [events](../../design/event_model.md),
  [implementation rules](../../IMPLEMENTATION_RULES.md), and
  [ontology design](../../design/learned_ontology.md) Sections 3–10 and 12–13,
  the [base catalog](../../design/learned_ontology_base_catalog.md), and
  the [installed ontology addendum](../../design/learned_ontology_hermes_and_legacy_addendum.md).
  User constraints are agent-neutral intake and reads, a useful no-key
  deployment, and household visibility within the signed-in account.

The dispositions describe Memorii at this baseline. **Verified** means
the stated path has executed evidence. **Partial** means a bounded path
or a component exists and the full obligation remains open. **Missing**
means the scoped capability has no identified path in the audited code.
**Excluded** records a scope decision. A source or test path on its own
denotes inspection evidence.

## Capability matrix

Memorii Python paths below are relative to `memorii/memorii`, and test
paths are relative to `memorii`. NVIDIA links pin its inspected source.

| Capability | NVIDIA code and evidence boundary | Memorii code and evidence boundary | Disposition and effect |
| --- | --- | --- | --- |
| **Initial authoring and install** | Catalog ingestion reads schemas, declared keys and query history. Compilation samples data and proposes typed terms, aliases and mappings with model calls and deterministic checks. Incremental ingest has database fixtures. [Ingest](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/auto_ontology/ingestion_service/ingest.py) · [Compiler](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/auto_ontology/semantic/visit_enter.py#L881) | `default_catalog_corpus`, `catalog_authority.SelectedCatalogAuthorityRepository` and the package-indexed locator verify the product-authored seed and default release. Corpus, runtime and read tests prove the typed inventory and handoff. | **Verified** for release-owned bootstrap and no-key package installation. |
| **Out-of-box work and home breadth** | Compiler breadth depends on connected databases and configured model capabilities. [Architecture](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/docs/architecture.md#generate-an-ontology) | 53 typed corpus rows plus three inherited predicate declarations. `test_default_catalog_runtime.py` exercises relation-specific validation. The [historical installed run](milestones/default-catalog-and-home.plan.md) at `8d57deaa` exercised all 53 structured commit/read/deny rows. PR #126 exercises representative managed journeys. | **Partial** against full OLE-09/10 scenario coverage at this baseline. Persona-by-persona correction and abstention coverage needs its own evidence, as does ordinary transcript wording. |
| **Household preferences** | Conversation graph vocabulary includes preferences. A type in the graph alone supplies no holder confirmation or Memorii user-context grant semantics. [Node kinds](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/auto_ontology/conversations/semantic/extract.py#L74) | The base catalog defines H8 as a distinct user-context record. The [default catalog WorkPlan](milestones/default-catalog-and-home.plan.md) records installed confirmation, correction, expiry, history and delegated read/revocation evidence at `ca647222` and `f5f4f265`. | **Verified** for the recorded bounded H8 path. Preserve that domain and its holder grants. Future full default acceptance must cover it separately from semantic predicate rows. |
| **Initial import, export and editable catalog** | Native and Ossie import/export routes and term/attribute edit endpoints. Database tests cover merge/replace and round trips. [Interchange routes](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/auto_ontology/server/model_interchange/router.py) · [DAL tests](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/auto_ontology/dal/tests/test_model_interchange.py) | Product release imports and owner-controlled learned overlays supply the current entrypoints. No customer-owned initial catalog import, editable registry or interchange contract was found in the governing design. | **Excluded** for Level 2. Keep owner submission of grounded candidates in scope. Enterprise SQL, connectors and mutable replacement require a separate product decision. |
| **Transcript intake and lineage** | Ingestion and a callable conversation-graph library use bounded windows, quoted turn evidence and a fixed graph vocabulary. No tracked production caller of `populate_conversation_graph` was found outside the library and examples. Conversation retrieval can use an existing graph. [Ingest](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/auto_ontology/conversations/ingest.py) · [Graph entrypoint](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/auto_ontology/conversations/semantic/pipeline.py#L160) · [Agent retrieval](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/auto_ontology/retrieval/text_to_sql/react/conversation.py) | Provider ingestion and Hermes completed-turn retention feed `CoverageObservation`. The generic authenticated source root is a separate adapter into the same local factory. Its installed candidate/owner-path test in `test_hermes_memory_provider_bridge.py` already exercises the narrow `mentors` flow. | **Partial** for portability. Two adapter paths already exist for one deterministic relation. Prove a non-fixture observer and a second relation before claiming broader host conformance. |
| **Observation, attribution and missing capability** | Graph evidence has turn citation checks and optional semantic verification. SQL question coverage uses model extraction and matching against columns. [Graph verification](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/auto_ontology/conversations/semantic/verify.py) · [Question coverage](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/auto_ontology/retrieval/entity_coverage/main.py) | `coverage_observation` and `coverage_observer` retain source-scoped status and verify span and catalog coverage. Runner tests cover aliases, pending, outage and restart. The installed factory defaults to a deterministic, no-key direct `mentors` observer, and the observer-disabled path records durable pending. | **Partial** for general classification. Add an authorized host/local binding and demonstrate that source, extraction, identity, retrieval and exposure failures cannot be counted as schema gaps. Existing deterministic no-key learning is real and narrow. |
| **Recurrence and deduplication** | Conversation graph edges can merge and retain turn evidence. The model/graph tests and DB evidence cover a different unit from schema-change recurrence. [Graph consolidation](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/auto_ontology/conversations/semantic/consolidate.py) · [Edge evidence tests](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/auto_ontology/conversations/semantic/tests/test_store_edges.py) | `coverage_recurrence` and unit tests enforce three verified lineages across two sessions, scope and binding separation, copy exclusion and CAS. `LearnedRelationCandidateService.admit_recurrence` rechecks retained proof and accepts the frozen relation. | **Verified** recurrence mechanics for the bounded slice. Reprove grouping and add owner-visible reasons on a second relation. |
| **Synthesis and manual candidate authoring** | Metadata compilation calls model helpers and combines generated suggestions with declared structure. A human can import or edit definitions. [Term extraction](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/auto_ontology/semantic/term_extractor.py) · [Term routes](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/auto_ontology/server/terms/router.py) | `learned_relation.RelationDeclaration` and candidate admission hardcode `mentors(Person, Person)`. Scope-owner approval is exposed on both local compositions. Searches found no installed general synthesis or owner-submitted typed candidate entrypoint in those compositions. | **Partial** for synthesis, **missing** for owner authoring. Design one grounded, provider-neutral synthesis and owner-submission path into the same validator. |
| **Closed edit language and validation** | Conversation node kinds are fixed. The metadata compiler and import checks validate their own declarations and mappings. [Conversation types](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/auto_ontology/conversations/semantic/extract.py#L74) · [Interchange schemas](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/auto_ontology/server/model_interchange/schemas.py) | The approved language defines `add_relation` and `add_entity_type`. `OntologyChangeProposal.operation` permits only `add_relation`; its declaration is literal-locked. Type and literal capabilities in the shipped catalog do not prove learned edit support. | **Partial** for relation creation and **missing** for learned subtype creation. Track subtype as a separate delivery slice with parent, alias, identity and protected-use proof. |
| **Evaluation, calibration and veto** | Graph audits can compare evidence with generated edges. Glossary certification flags track human editorial review. [Graph audit](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/auto_ontology/conversations/semantic/audit.py) · [Certification rollup](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/auto_ontology/dal/terms.py#L157-L235) | `FrozenMentorsPairedEvaluator` compares parent and candidate, with positive read cases and mandatory vetoes. Installed isolated evaluator tests exercise the real writer/reader with scripted proposal evidence. `ActivationPolicy` declares a calibration check, and no installed calibrated automatic activation caller was found. | **Partial** for candidate-specific evaluation beyond the frozen corpus. Keep owner approval and withheld evidence gates. **Excluded** from Level 2: automatic promotion and its calibration claim. |
| **Owner review and approval** | Term, column and SQL certification are visibility-filtered editorial controls. [Terms DAL](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/auto_ontology/dal/terms.py#L157-L253) | `LearnedRelationRuntime.status` reports scoped IDs, counts and replay summaries. Hermes and the generic root expose approval and activation. No installed candidate detail/diff, evidence view or owner rejection port was found. | **Partial**. Add an owner-only view of the declaration, verified source references, paired outcomes, vetoes and decisions. Review a candidate on the exact pinned parent. |
| **Versioning, selection and rebase** | Mutable compilation with trigger/reset/status and import replacement. [Compilation router](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/auto_ontology/server/semantic_compilation/router.py) | `SelectedCatalogAuthorityRepository` proves seed/default; `LearnedRelationRuntime.activate_candidate` CAS-selects an agent-local overlay. Early first-child versions have no explicit exact parent version field. `catalog_read_workflow` returns unavailable for learned versions rather than guessing. Base and agent-local are code-backed; the larger namespace chain is specified. | **Partial**. Prove complete immutable parent closure for a new learned version. Early overlay rebase requires its own verified proof and owner action. Wider namespace rollout is deferred. |
| **Maintenance, replay and rollback** | Conversation maintenance includes derived relations, revision edges, and stale vector cleanup, with targeted tests. [Graph pipeline](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/auto_ontology/conversations/semantic/pipeline.py) | Existing narrow replay processes the proposal's evidence through an authorized writer and records durable outcomes, including skips. Same-scope selected ancestor rollback is available through Hermes. Generic source binding exposes approve, activate and status. | **Partial**. Verify generic maintenance, replay scope, retry policy and rollback boundaries without widening source visibility or historical meaning. |
| **Recovery and current mutation authority** | Scheduler and ingestion tests cover failure and cancellation within database build operations. [Scheduler tests](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/auto_ontology/ingestion_service/tests/test_completion_logs.py) | `record_evaluation` persists `evaluating`, which the proposal's closed schema rejects on decode. A focused interruption probe exercises that path. Both host paths forward callbacks in `hermes_factory.py:905–932`. Approval mutates using captured identity. Activation and rollback use captured identity and check resolver availability after durable selection. Narrow selection/replay crash tests cover later lifecycle boundaries. | **Partial**. The evaluation interruption is a reproduced P2 runtime recovery issue. Before extending maintenance, check live authority separately for approve, activate, and select-prior on both host surfaces. Exercise withdrawal before mutation and refresh failure after valid selection. Confirm the status reader stays scope-safe. Installed revocation proof for these callbacks is still open. |
| **Agent tool discovery and subject resolution** | Read-only MCP lists curated terms, related columns, SQL attributes, readiness and question tools. In-process tests exercise the tool inventory. [MCP](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/mcp/auto_ontology_mcp/tools.py) | Two direct read methods sit behind verified host bindings. Hermes's tool-schema listing still delegates to the completed-turn runtime. Installed integration passes stored canonical subject IDs and exact catalog names. | **Partial**. Wire the shared methods into tool discovery. Add bounded name discovery and preserve verified subject selection, ambiguity and version retry. |
| **Exact recall, readiness and explanation** | Three-probe readiness distinguishes deployment blockers. Entity coverage estimates mapping availability before answering. Results can include SQL and steps. [Readiness](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/mcp/auto_ontology_mcp/readiness.py) · [Coverage](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/auto_ontology/retrieval/entity_coverage/agents/coverage.py#L172-L209) | `read_catalog_workflow` and `structured_fact_read` enforce current grants, release authorization and suppression. Exact statuses and provenance/version coordinates are returned. Hosted test covers the packaged workflow through both bindings, using installed metadata and a stand-in for the optional Hermes ABI. | **Verified** packaged exact reads. **Partial** for learned reads and agent UX. Consider authorized startup/status explanations while retaining status-only denied reads. Composite free-form question grading is outside the exact workflow. |
| **Historical seed and unbound legacy continuity** | The database compiler and graph paths use their own metadata and evidence lifecycles. | Schema-1 seed-bound facts and genuinely unbound projection-era records have separate protected authorities. `test_ingestion_time_seal_minting.py` covers mixed reopen and `test_scoped_context_activation.py` exercises legacy verifier selection and denied fallthrough. | **Verified** for those bounded legacy paths. Preserve both as separate regressions when adding learned version reads. Their authority cannot supply a missing exact overlay parent. |
| **No-key, manual and isolation paths** | Model-backed compilation, question coverage and graph extraction depend on configured capabilities. Curated glossary HTTP methods can read already-persisted data through authenticated API access. [Models and stages](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/docs/architecture.md) | Installed tests prove no-key packaged reads, structured writes and the narrow local observer, and durable pending when disabled. `ProviderMemoryService.submit_structured_fact` exists in core. Generic source does not expose an equivalent installed standalone fact-authoring method in its public binding. | **Partial** for the complete OLE-12/14 contract. Preserve offline baseline, qualify the owner-authored candidate and generic structured-fact paths, and verify no implicit fallback. Household scope stays with its signed-in account. |
| **Agent workflow evidence** | The management skill links modeling, writes and publication readback. It says import and certification do not prove atomic promotion. NVIDIA reports live setup, query and management skill trials with Codex and Claude Code. [Management skill](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/skills/nvidia-ontology-management/SKILL.md) · [Skill benchmark](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/skills/nvidia-ontology-management/BENCHMARK.md) | PR #126 proves direct read composition. Host certification uses test-provider transport, and the installed read fixture supplies canonical subject IDs. | **Partial**. Verify tool listing and calls through the actual supported host transport, then separately record whether a host agent chooses the correct tool and carries subject and version through the user journey. NVIDIA's report supports skill-level evidence, with backend revision and transcript-to-schema quality unverified here. |

## Requirement reconciliation

| Governing requirement | Matrix coverage and remaining evidence |
| --- | --- |
| OLE-01, OLE-11 | Observation, attribution and recurrence. Narrow queues and counting verified. Broader gap attribution, manual proposal and restart across bindings open. |
| OLE-02 | Lineage, recurrence, owner and version scopes. Bounded scope isolation verified. New creation/maintenance paths need current-grant proof. |
| OLE-03 | Closed edit language. Generic learned relation grammar and learned subtype proof open. |
| OLE-04, OLE-07 | Evaluation, owner approval and rejection, version selection and recovery. Narrow activation and selected-ancestor rollback verified. Owner rejection, proposal interruption and current mutation authority are assigned to Milestone 2. |
| OLE-05, OLE-06 | Version pinning, protected reads, historical visibility and normal writer replay. Keep separate regression evidence for seed-bound and unbound legacy reads in Milestone 2. Exact learned-parent coverage, generic maintenance and evidence selection rules open. |
| OLE-08 | Two adapters already reach one local deterministic candidate path. Generalizing capability binding and a second relation need evidence. |
| OLE-09, OLE-10 | Default catalog inventory and work/home workflows. The historical 53-relation run and H8 confirmation and holder-delegation evidence establish distinct paths. Complete current persona/task acceptance is assigned to the default catalog and user-context owners in the roadmap. |
| OLE-12, OLE-14 | No-key structured admission/reads and disabled-observer pending. Broader observer bindings are assigned to Milestone 3, manual ontology candidates to Milestone 4, and generic structured fact authoring to a separate source-admission design slice. |
| OLE-13 | Owner-reviewed paired evidence and calibrated automatic policy. Candidate-specific evaluation open. Automatic activation deferred pending calibration evidence. |
| Sections 12–13 and OCI-01 through OCI-04 | Exact packaged read and release verified at hosted Level 2. Discovery exposure and learned catalog reads need their own acceptance. |

## Discriminating evidence and limits

- Frozen Memorii archive, macOS Python 3.12, warnings as errors.
  `pytest -p no:cacheprovider` over catalog inspection/read workflow,
  coverage observation/observer/recurrence and three default-catalog
  unit modules passed **176 tests**. The learned-relation unit suite passed
  **14 tests**. These are focused code evidence.
- Direct installed observer and declaration probe on the same archive
  compared `Ada mentors Bea.`, `Ada sponsors Bea.`, and the quoted first
  sentence. Outcomes were `unsupported_relation`, `uncertain`,
  `uncertain`. The current declaration parser accepted `mentors`
  and rejected `sponsors` with a literal validation error. This isolates
  the creation boundary from tool discoverability.
- An in-memory interruption probe ran `LearnedRelationRuntime.record_evaluation`
  and stopped immediately after it stored `evaluating`. The same runtime's
  fresh proposal load failed with `proposal is unavailable`. This proves
  the persisted representation and decoder disagree. The probe uses an
  in-memory unit fixture. Inference runs before result recording, so an
  earlier interruption can leave a readable `validated` proposal. Repeated
  admission returns the existing proposal before dispatching evaluation.
  The design slice should compare an atomic terminal update with a durable
  typed attempt and cover restart before publication, interrupted result
  recording, unavailable evaluation, and terminal evaluation.
- NVIDIA transcript graph reachability was checked with a tracked-source
  search for `populate_conversation_graph` and separate tracing of the
  conversation retrieval caller. The audit establishes callable library
  reachability and retrieval wiring, with upstream unit/fixture evidence.
- No comparative live inference scores, new model capabilities, all-persona
  shipped certification, or production rollout approval are inferred.
  Material future behavior belongs to the linked design slices and needs
  its own acceptance evidence.

### Reproduction commands

Run from the Memorii repository root with its Python development
environment. The archive isolates the common evidence from unrelated
working-tree changes. The recorded interpreter was Python 3.12.16.

```sh
audit_python="$PWD/.venv/bin/python"
audit_source=$(mktemp -d)
git archive 80fc585228cf0b7d3e59067012f3d6998f34bbf8 | tar -x -C "$audit_source"
cd "$audit_source/memorii"
export PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1
"$audit_python" -W error -m pytest -q -p no:cacheprovider \
  tests/unit/core/semantic_ingestion/test_catalog_inspection.py \
  tests/unit/core/semantic_ingestion/test_catalog_read_workflow.py \
  tests/unit/core/semantic_ingestion/test_coverage_observation.py \
  tests/unit/core/semantic_ingestion/test_coverage_observer.py \
  tests/unit/core/semantic_ingestion/test_coverage_recurrence.py \
  tests/unit/core/semantic_ingestion/test_default_catalog_corpus.py \
  tests/unit/core/semantic_ingestion/test_default_catalog_runtime.py \
  tests/unit/core/semantic_ingestion/test_default_catalog_values.py
"$audit_python" -W error -m pytest -q -p no:cacheprovider \
  tests/unit/core/semantic_ingestion/test_learned_relation.py
```

In that archive, run the following probes using `$audit_python`. The
first calls the observer component directly. The second pauses the real
evaluation transition on the unit fixture's in-memory store.

```python
from types import SimpleNamespace

from pydantic import ValidationError
from memorii.core.semantic_ingestion.learned_relation import (
    LearnedRelationError, RelationDeclaration,
)
from memorii.integrations.hermes_factory import _LocalNoKeyMentorsObserver
from tests.unit.core.semantic_ingestion.test_learned_relation import (
    _passing_evaluation, _proposal, _ReplayWriter, _runtime,
)

observer = _LocalNoKeyMentorsObserver()
examples = ("Ada mentors Bea.", "Ada sponsors Bea.", '"Ada mentors Bea."')
assert [observer.observe(SimpleNamespace(source_text=s)).semantic_outcome.value
        for s in examples] == ["unsupported_relation", "uncertain", "uncertain"]
assert RelationDeclaration(description="A mentor").relation_id == "mentors"
try:
    RelationDeclaration(relation_id="sponsors", description="A sponsor")
except ValidationError as exc:
    assert {item["type"] for item in exc.errors()} == {"literal_error"}
else:
    raise AssertionError("second relation unexpectedly accepted")

runtime = _runtime(_ReplayWriter())
proposal = runtime.prepare_candidate(_proposal())
replace = runtime._replace_proposal

def interrupt(current, next_proposal):
    replace(current, next_proposal)
    if next_proposal.lifecycle == "evaluating":
        raise InterruptedError("simulated abort after durable transition")

runtime._replace_proposal = interrupt
try:
    runtime.record_evaluation(proposal_id=proposal.proposal_id, evaluation=_passing_evaluation())
except InterruptedError:
    pass
else:
    raise AssertionError("transition never written")
try:
    runtime._require_proposal(proposal.proposal_id)
except LearnedRelationError as exc:
    assert str(exc) == "proposal is unavailable"
else:
    raise AssertionError("expected to reproduce decode failure")
```
