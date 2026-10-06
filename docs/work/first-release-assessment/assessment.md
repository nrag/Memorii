# Memorii First Release Assessment

Date: 2026-09-29. Inspected source: `bad9eeefb43f7f42fb95d583b11859e2f2ca9eb8` plus the pre-existing user modification to `docs/design/hermes_conversation_memory_trial.md`. This is a research and release-scope assessment, not exact-revision certification, a complete security audit, or a PR approval. No product code changed; no live provider campaign or broad CI suite ran.

## Judgment

Memorii has substantial Level 2 implementation and unusually strong component integrity machinery. It is not yet demonstrated ready for a first production release. The remaining work is concentrated in production activation, actual agent usefulness, a supported operational envelope, and a coherent install-to-recall product experience. More ontology breadth is not the first priority.

The latest ontology implementation records five completed Level 2 milestones, all 14 requirements ready for manual testing, 53 default relations plus inherited predicates, preferences, authenticated no-key structured writes, protected reads, and one learned-relation activation/replay/rollback journey. These are meaningful advances. Its sixth milestone, full package/migration/release conformance, is explicitly not started. See [implementation](../learned-ontology/implementation.plan.md), [current resume](../learned-ontology/resume.md), and [release conformance](../learned-ontology/milestones/release-conformance.plan.md).

Recommend a deliberately bounded v0.1: local, single-account durable semantic and preference memory; explicit project/task scope; correction/history/provenance; Hermes and one independently supported harness; optional authorized extraction; owner-reviewed learning. Do not claim distributed operation, cross-account household sharing, arbitrary self-learning, or complete persistent execution/solver orchestration. This is a scope proposal, not an amendment of governing requirements. If full durable execution/solver memory is a release promise, complete it before release.

## Harness Integration

The user clarified that the requested hosts are OpenClaw and Pi, not OpenAI. Pi is interpreted as the Pi coding agent.

| Host | Current external integration support | Recommended Memorii integration |
| --- | --- | --- |
| OpenClaw | Native exclusive memory plugin slot, memory capability registration, tools and typed lifecycle/prompt hooks | Native TypeScript memory plugin selected through `plugins.slots.memory`; forward to the Python core over a local typed boundary; retain host context management |
| Pi coding agent | TypeScript extensions, lifecycle/context events, tools, external storage and current MCP support | A Pi extension with a local Memorii process, using a shared typed boundary for automatic recall/capture and model-facing tools |

Official sources accessed on the assessment date: [OpenClaw manifest](https://docs.openclaw.ai/plugins/manifest), [memory-core implementation](https://raw.githubusercontent.com/openclaw/openclaw/main/extensions/memory-core/index.ts), [prompt/session hooks](https://docs.openclaw.ai/plugins/hooks/prompt-and-session), [plugin permissions](https://docs.openclaw.ai/gateway/config-extensions), [Pi extensions](https://raw.githubusercontent.com/badlogic/pi-mono/main/packages/coding-agent/docs/extensions.md), and [Pi event types](https://raw.githubusercontent.com/earendil-works/pi/main/packages/coding-agent/src/core/extensions/types.ts). Pin actual supported versions before implementation; these upstream main-branch references are research evidence, not compatibility certification.

### Integration architecture recommendation

Keep one core implementation behind `ProviderMemoryService` and the existing authenticated-source boundary. There is already a generic adapter in `memorii/memorii/integrations/authenticated_source.py`; this is not a greenfield abstraction project. The local generic composition currently reuses the Hermes factory (`hermes_factory.py:427`), so isolate reusable host provisioning from Hermes naming as the second real harness requires it, rather than cloning the learner.

Two separate channels are necessary:

1. Host-controlled lifecycle: derive principal/project/session/branch scope, retain original messages, issue stable delivery IDs, recall before generation, record outcomes, and reconcile after interruption.
2. Model-callable tools: search/read with evidence, propose grounded facts, correct/retract through existing policy, manage preferences/work state, and inspect pending/conflicting memory.

MCP supplies a portable tool interface; it does not itself guarantee automatic capture, recall, authentic user provenance, or exactly-once logical effects. A model-facing write tool must never manufacture a user-source receipt or choose its own authority. Host credentials and grants stay out of prompts. Submit candidates through normal validation, not direct store writes.

For OpenClaw, declare `kind: "memory"` in the native manifest and select the Memorii plugin in the memory slot. Follow the bundled memory plugin's capability/tool registration contract and preserve the host's context engine. Implement scoped `memory_search`/`memory_get` compatibility plus Memorii-specific grounded write/status tools. These are integration recommendations, not existing Memorii capabilities.

Use authorized `before_prompt_build` enrichment for bounded recall, checking active tool authority. Capture stable host admission IDs and typed provenance; user-role text or a run trigger does not prove human origin. Observe completed runs with idempotent delivery and explicit partial/failure handling. Missing admission identity must not be replaced by a text hash that collapses distinct turns. Enable required conversation/prompt access explicitly and pin the supporting plugin API version. Validate actual channel/account/sender identity and session isolation; do not use agent identity as user identity. These requirements make OpenClaw's messaging surfaces an important trust-boundary integration rather than merely a tool wrapper.

Before replacement, make existing OpenClaw memory handling explicit: retain original files and provide a scoped, opt-in importer with provenance, or document that existing native memories remain outside Memorii. Do not silently discard them or run two conflicting automatic memory writers.

For Pi, use `session_start` for runtime resources and `before_agent_start`/context integration for recall. Persist stable source/branch coordinates and capture completed messages through an idempotent host delivery path. Current Pi distinguishes `agent_end` from final settling: automatic continuation can follow `agent_end`; use the documented settle boundaries as appropriate. Reconstruct the active branch, not every entry in an abandoned history. Prove fork/switch/compaction/retry semantics against the pinned Pi release. Run Python core behind a local process rather than porting memory policy to TypeScript.

Build OpenClaw first because it has an explicit external memory slot, then Pi on the shared local boundary. Keep MCP as a reusable tool transport where it helps; the native host adapters must still own reliable capture and automatic recall. Both wrappers can share transport/client mechanics, but their provenance, session and finalization rules need separate proofs. No OpenAI adapter is requested by this assessment.

Adapter acceptance: fresh install -> capture -> grounded commit -> new-session recall -> correction -> restart -> same recall; duplicate callback has no duplicate effect; equal-text distinct turns remain distinct; another principal/project is denied; host interruption recovers; unavailable memory is visibly unavailable; compaction never promotes summaries into original user evidence. Use native-memory/no-memory and Memorii modes to expose accidental double injection.

## Prioritized Findings

Classification follows AGENTS.md. Missing evidence is not automatically a P1/P2 product defect. Tier 1 is end-to-end utility, tier 2 is expected reliability, tier 3 is adversarial/exhaustive breadth. The ordering below is work priority, not a claim that every item is a demonstrated outage.

| Finding | Evidence and classification | Required closure |
| --- | --- | --- |
| Production host activation remains a Level 2 path | `memorii/pyproject.toml:40` installs `build_local_level2_runtime_binding`; `hermes_factory.py:514` loads local authority. Existing signed-production primitives do not make this installed path production-certified. Not applicable / changes_required / production integration / tier 1 | Select and implement the deployment trust/signing configuration; compose verified production ingress, read, evaluation and monitoring authority; prove installed initialization, write/read, revocation and restart. Do not relabel local authorization as production authorization |
| Level 3 conformance is explicitly deferred | `docs/work/learned-ontology/milestones/release-conformance.plan.md:3`; semantic closure table still lists R03/R08/R13/R16/R17/R19 partial. Not applicable / changes_required / verification / tiers 1-3 | Complete the current production-root and release packet; reconcile older closure rows against new ontology code before assigning work |
| Actual agent benefit is unestablished | README:12 and 269; agent evaluation plan distinguishes memory-component scores from agent outcomes. Not applicable / changes_required / product-quality evidence / tier 1 | Held-out agent tasks with native/no-memory, retrieval-only and full-memory arms; same model/budgets; real restart and correction tasks; task success, harmful recall, unsupported fact use, cost and latency; preregister thresholds |
| Durable execution/solver promise exceeds supplied stores | Only in-memory execution/solver/event-log store implementations found; filesystem bundle persists provider memory/work/decision state, not those graph stores. NextStepEngine has planner-unconfigured fallback. P1 conditional on shipping full durable execution/solver resume / changes_required / runtime durability / tier 1 | Either explicitly scope the first release to the provider-memory product through approved scope documentation, or implement and prove fresh-process reconstruction of execution frontier, solver branches, overlays and event history |
| Consumer installation and first successful memory journey are incomplete | README:95 starts with editable development install/tests; Docker uses editable source; user CLI is Hermes-specific. Not applicable / changes_required / onboarding / tier 1 | Versioned wheel/image, supported-platform prerequisites, one minimal library example and harness installers; validate outside checkout with no tests/fixtures on path |
| Recovery and data lifecycle are not packaged as an operational product | Filesystem policy and maintenance explicitly only report soft limits; no general backup/restore/forget command in inspected installed CLI. This is a verified limited implementation plus an operational evidence gap, not proof that all redaction primitives are absent. Not applicable / changes_required / operability / tier 2 | Document and rehearse consistent backup/restore, capacity exhaustion, interruption, corruption and authorization expiry; define retention and erasure across source, derived records, indexes, traces and backups |
| Performance envelope is unproved | No current product latency/scale acceptance result established in this investigation; completed-turn runtime uses an unbounded queue and single worker (`hermes_completed_turn_runtime.py:589`,1883). No overload failure reproduced. Not applicable / changes_required / performance evidence / tier 2 | Measure p50/p95/p99 recall, capture, commit visibility, reopen/replay, queue age and bytes at declared dataset sizes; define overload/backpressure, timeout, cost and disk limits |
| Production adversarial and compatibility breadth remains deferred | Semantic closure R08/R16/R17/R19; ontology release packet. Not applicable / changes_required / security and compatibility verification / tier 3 | Relevant hostile storage/lineage/authority cases, revocation between pages and at release, malformed signed records, restored historical meaning, old-store migration, pointer rotation and rollback for every advertised root |

The conditional execution finding is mainstream for the advertised restart/resume workflow, hence P1 if that feature ships. It is not a claim that the persistent semantic store loses memory. The scope decision itself is Not applicable / blocks_approval / external release-scope decision until resolved.

### What is already present

Do not restart work on typed lifecycle values, transaction atomicity, delivery idempotency, basic process restart, fenced leases, conservative candidate commit, scoped recall, correction history, or owner-reviewed ontology activation as though these were absent. The hardening matrix and recent real-root tests document substantial coverage. Level 3 requires new composition/operational/family evidence over the selected release, not indiscriminate reimplementation.

### Specific Level 3 backlog

The retained semantic closure table (`docs/work/semantic_ingestion_completion_readiness/closure-plan.md:356`) names:

- R03: final source/owner/gate/evidence identity.
- R08: supported-root authorization and revocation matrix.
- R13: evaluator-to-deployment binding, selected signing integration and final host evidence.
- R16: final package/profile and configured-root evidence.
- R17: observation-family mutations, forged topology, paging/revocation and host permutations.
- R19: supported host/platform composition and final release evidence.

R14/R15 being engineering-complete does not supply approved production quality measurements, monitoring policy or signatures. Select actual deployment/trust owners; use the existing signing and verification machinery. A selected KMS adapter is required by the retained release plan, but this assessment does not prescribe a cloud vendor or pretend every local product needs a hosted signing service. Any simpler release trust model needs an explicit governed decision.

Add exact artifact installation, dependency/security inventory, reproducible catalog/resource verification, supported host version matrix, old-data/new-code migration, rollback, restoration and no-key/no-network proofs. Existing pinned Hermes base image is useful; it is not equivalent to a fully resolved and signed Memorii release image. Gate the actual merged/released source and artifacts, not an earlier milestone's revision.

## Product Pieces Needed Out Of The Box

1. A five-minute first-value journey: install, choose storage and scope, capture a fact with evidence, restart, recall it, correct it, and show why the new answer changed. Provide a scripted deterministic mode and an explicitly authorized live mode.
2. Visible state: retained, pending extraction, candidate, committed, superseded, rejected, unavailable. A successful capture must not look like successful durable semantic recall. Include current principal/project, last ingestion, queue age, storage size and error reason in status/doctor output.
3. User control: inspect/search, explain provenance, correct/retract, export, and a clearly specified forget/redaction flow. With append-only evidence, deletion semantics need a design; do not merely remove graph nodes and allow replay to resurrect content.
4. Predictable service modes: normal operation, read-only/frozen writes, and host bypass, with explicit handling of in-flight work and unavailability. Hermes already supports switching providers/restarting, and learned-catalog rollback exists; these do not establish a general runtime pause/rollback control. Avoid the stale blanket claim that no rollback exists anywhere.
5. Honest optional-model behavior: no Memorii-owned OpenAI key for authenticated structured storage/read/restart; no silent remote fallback. Explain that no-key storage is not automatic extraction of arbitrary prose. Show when extraction/learning is pending and how a host/local/remote model becomes authorized.
6. Three supported example journeys: corrected project ownership across sessions; remembered preference with confirmation/retraction; engineering handoff with cited prior work. Include irrelevant/stale memory to test whether the host can ignore it.
7. A single current support matrix: released capabilities, supported harness/model/runtime versions, local limits, experimental features and exact evidence links. Correct stale current-state README/readiness text without rewriting historical plans.

## Research Evaluation

The existing paired eight-case learned-relation evaluator is valuable admission evidence, not broad language understanding or end-user task benefit. Do not infer arbitrary ontology induction from one relation journey.

Use representative multi-session work/home tasks with temporal correction, ambiguity/abstention, cross-project isolation, preference retraction, restarted handoff, irrelevant memory and conflicting sources. Separate extraction quality, retrieval quality and downstream action quality so failures are attributable. Native harness memory is the practical comparator, not only an artificially memoryless agent. Keep prompts, models, tools and resource budgets matched; freeze held-out cases before tuning. Measure success and harm by scenario family, report uncertainty, and review false-success cases. Set practical benefit and operational thresholds before the held-out run; this assessment invents no passing numbers.

For performance, instrument cold and warm paths separately and scale the retained store. Hundreds-of-seconds integration tests are a signal to investigate, not valid measurements of per-turn user latency. Measure admission-to-recall freshness as well as request latency; eventual processing can otherwise look like forgotten memory.

## Recommended Completion Order

1. Complete manual validation of the five ontology milestones and settle the v0.1 capability/support boundary, especially execution/solver durability and local versus hosted operation.
2. Make one clean install-to-correction/restart journey and build one real independent harness adapter. Establish the reusable host authority/lifecycle contract before multiplying integrations.
3. Close production activation, operator pause/bypass, backup/restore, data lifecycle and measured capacity/latency. Run development agent trials early enough to fix usefulness failures before release freeze.
4. Execute the deferred Level 3 security, migration, host and package matrices for that declared scope. Run frozen live component and held-out agent evaluations with approved budgets and independent outcome checks.
5. Freeze the final candidate, reconcile generated artifacts and evidence, run current required CI, perform independent full reviews, sign/publish verified artifacts and release the documented support envelope.

Defer additional harnesses beyond the chosen second, distributed storage, cross-account collaboration, unrestricted automatic ontology promotion and a large GUI unless selected release scenarios require them. Do not defer basic scope denial, source authenticity, persistence, ordinary recovery or useful first-run behavior.

## Coordinator Reconciliation And Limits

Two independent read-only investigations informed this assessment. Confirmed: Level 3 explicitly deferred, local factory registration, generic adapter availability, component-versus-agent evidence gap, developer-oriented quickstart and soft-limit-only maintenance. Corrected: old preflight claims of no working Hermes factory are superseded; current Level 2 factory works. Corrected: broad assertions that rollback is absent ignore host provider switching and learned-catalog rollback. Reclassified: missing security matrices and measurements are verification gaps, not demonstrated P1/P2 outages. Latest ontology closure supersedes historical partial progress paragraphs.

No current hosted CI, production credential availability, manual trial outcomes, package publication, or actual load measurements were independently established. This report therefore recommends release exit criteria and identifies implementation/evidence gaps; it does not certify failure or success of unexecuted gates. No full arbitrary-conversation learner, cross-harness identity federation or production-scale behavior should be inferred from the cited bounded tests.
