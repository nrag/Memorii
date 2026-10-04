# Design Review: Durable Memory, Execution, Solver State And Harness Recovery

## Review Metadata

- Review ID: 2026-09-29-final-approval
- Review mode: full (final-approval pass on the design; first review of the implementation plan)
- Review outcome: Changes required
- Design path: docs/design/durable_execution_and_solver_runtime.md
- Design baseline: SHA-256 22e29f90ab90fa9b67b489d8f293b4a9ecbe4e5bf1dad7c0d6d3f2a7697706ad
- Implementation baseline: docs/work/durable-memory-implementation/implementation.plan.md SHA-256 d30c0d585fc3767d63f21f236fbad5ff8d2ee2e38c5f849c7c62fce01ef8d943; repository HEAD bad9eeefb43f7f42fb95d583b11859e2f2ca9eb8
- Review date: 2026-09-29
- Reviewers: spec_auditor, correctness_reviewer, test_reviewer (independent concurrent passes); main-thread coordinator reconciliation
- Included scope: design at the frozen SHA; implementation plan and its packets (coverage, validation, bindings, gates, identity-and-changes, planning-review, resume, eight milestone packets, workflow-inventory.json, baseline.json, authority-inventory.json); consistency against governing documents and current code
- Excluded scope: editing the design or plan; implementation; CI execution; live provider certification; the user-deferred agent-benefit benchmark campaign

## Executive Assessment

This is a strong, unusually well-disciplined design. Its factual claims about current code all verify (every item in the "Verified Baseline And Problem" section was confirmed against the repository), the transaction/recovery core — the two-owner publication protocol, lock ordering, attempt/outbox/action state machines, SQLite backend choices, trust model, and mode/forget fencing — is sound as specified, evidence maturity is stated honestly throughout (specified only; no inflated claims were found), identity hygiene is clean, and the implementation plan satisfies the repository's WorkPlan contract with accurate preflight bindings, gate inventory, and honest not-started status.

Four validated P2 design defects prevent approval. Two are closed-grammar completeness gaps on the public command surface: the v1 command union cannot express task completion/pause/abort (which the spec requires of every adapter and which the design's own validation rule depends on), and merge/consolidation operations plus the "registered solver proposal union" are referenced but never defined while consolidation runs on today's mainstream runtime path. One is a migration-detection gap: the design never enumerates the legacy on-disk layouts it must detect, and the two live spellings (`memory-plane` vs `memory_plane`) differ per composition root. One is an unresolved internal tension: mandatory per-snapshot full-manifest verification ("cannot be skipped") is jointly unsatisfiable with the design's own latency budgets and tamper-rejection requirement because no incremental verification mechanism is specified. Two additional changes_required verification-planning gaps sit in the implementation plan's validation matrix (sidecar transport-security family; consumer-delivery and checkpoint-key-lifecycle families). All corrections are determinate and bounded; none requires re-architecting. Three P3 follow-ups are recorded as non-blocking.

## Governing Sources

Applied precedence per AGENTS.md: docs/design/memorii_spec.md (esp. §17 persistence/resume, §18 event log, §19-23 harness integration incl. §22.2 minimum adapter set, §27-28 acceptance/invariants); docs/design/memorii_storage_details.md (§2 scoped retrieval, §5 agent-scoped partitions, §6 pluggable backends, §10 checkpoints); docs/design/event_model.md (§3 envelope/batch, §8-9 versioning/idempotency, §10 replay, §15 checkpoints) with the frozen docs/design/equal_version_replay_decision-v1.json; docs/IMPLEMENTATION_RULES.md; docs/design/scoped_memory_context.md; docs/design/learned_ontology.md and the Hermes/legacy addendum; then the design under review. Code and tests at HEAD bad9eeef were inspected directly. No source conflicts required external escalation; the spec_auditor's source notes (e.g., IMPLEMENTATION_RULES citing a stale spec path) are recorded as follow-up documentation hygiene, not approval blockers.

## Independently Reconstructed Requirements

Requirements were reconstructed independently from the governing sources before the design was judged. Load-bearing citations: spec §17.1-17.6 (1150-1212), §18.1-18.3 (1215-1256), §20.1-20.3 (1293-1380), §22.1-22.3, §23.1-23.2 (1443-1473), §27 (1613-1645); storage §2.2-2.4, §5.2-5.5, §6, §8, §10; event model §3, §8-9, §10, §15 plus the frozen equal-version decision; IMPLEMENTATION_RULES resume/commit/adapter guarantees; scoped-context grant/authority boundaries; learned-ontology CAS/activation/replay ownership and the addendum's pin/recovery invariants. The reconstructed requirement set and per-requirement coverage is summarized in Requirements Coverage below; the full reconstruction is held in the review WorkPlan evidence log (docs/work/durable-release-design-review/design-review.plan.md).

## Contract And Evidence Boundaries

Normative sources are the governing documents plus the design's own closed schemas, state machines, ledgers, and identity inventory; the design's review/identity/entrypoint ledgers are declared part of the implementation contract, not evidence of existing callers (all new production caller counts are zero, honestly recorded). Canonical owners and trust boundaries: PartitionDataRepository coordinates transactions but holds no domain authority; SemanticIngestionAtomicStore, MemoryPlaneService, LearnedRelationRuntime, and catalog owners remain the only domain writers; the independent control owner and key owner hold current authority outside replaceable data generations; hosts own planning/tools/model invocation. Evidence maturity at review time is specified (design normative text) with bounded locally verified design probes (8 runtime tests, 27 JSONL/memory-plane tests, 14 ontology tests, toy SQLite import probe, toy reducer probe, SQLite crash probe) — none misreported. Production entrypoint bindings: the plan's preflight ledger accurately maps all current precursor roots (five direct JSONL constructor sites plus wrapper/factory consumers verified in code) with explicit not-implemented status. Identity ledger: complete; all proposed durable identities are behavioral; no planning/evidence coordinate appears in an executable or durable name; the mutation/positive corpus is mechanically defined in memorii/tools/identity_hygiene.py:23-36.

## Confirmed Findings

### DREV-001: Closed v1 runtime command union cannot express task completion, pause, or abort

- Product priority: P2
- Approval disposition: changes_required
- Remediation eligibility: eligible_p1_p2
- Confidence: high
- Finding type: runtime behavior / API contract conformance (closed-grammar completeness)
- Affected scenario and prevalence evidence: a host finishes, pauses, or abandons a durable task and reports it through the versioned API — the terminal step of every task journey. Spec §20.1 (1293-1307) requires every adapter to be able to send TASK_PAUSED/TASK_COMPLETED/TASK_ABORTED; spec §18.1 (1219-1240) requires those event types; storage §4.4 requires the task-completion hook; all 19 EventType values already exist in code (memorii/memorii/domain/enums.py:217-236).
- Design location: design line 274 (RuntimeCommandRequest closed union: start_task, resume_task, record_observation, propose_state_change, record_action_dispatch, record_action_result, checkpoint_task, replan_task); line 247 ("Task-completed input is a claim: validate required acceptance/tests and unresolved blockers before marking DONE"); line 192 (event business-label mapping must enumerate all labels including task events)
- Governing source or requirement: spec §20.1, §18.1, §23.2 (on_task_completed hook); storage §4.2 task-completion hook
- Expected behavior: every adapter can send the spec-required task-lifecycle events; a task can reach a terminal lifecycle state through the authenticated public protocol with acceptance-evidence validation.
- Design behavior: no command kind produces a task-lifecycle transition; the design's own completion-validation rule (line 247) and commit-time "task completion evidence" recheck (line 202) reference an input the closed union cannot express; the operator `pause` CLI (line 318) is an installation mode change, not the host task event.
- Evidence: design lines 202, 247, 274, 192 as quoted; spec citations above; enums.py:217-236; grep of the design finds no task-completion command.
- Impact: tasks can never be marked DONE/ABORTED through the public protocol; retention tiering, completion-triggered consolidation/writeback, and the §18.1 label mapping cannot complete; an implementer must invent the missing kind (a material semantic choice), violating implementation readiness.
- Root invariant or contract boundary: closed public surfaces must fail closed for unknown values and remain complete for governing canonical adapter events; committed state changes only through explicit validated commands.
- Equivalence class and adjacent bypasses inspected: checkpoint_task (snapshot, not lifecycle), replan_task, record_action_result (action-scoped), propose_state_change (solver-scoped), operator mode pause (different concept), RuntimeEventConsumer/HTTP/embedded ingress (all share the same union — no alternate ingress supplies it), legacy ephemeral roots (test-only by design).
- Positive behavior that must remain valid: the eight specified kinds with expected_revision conflict semantics and idempotent receipts; "chat session ending is not task completion"; acceptance-evidence validation before DONE.
- Recommended invariant-level resolution: extend the closed v1 union with explicit task-lifecycle command kind(s) (complete/abort/pause) carrying typed completion evidence, and enumerate the TASK_PAUSED/TASK_COMPLETED/TASK_ABORTED label mappings in the schema-generation inventory. No governing document records an exclusion, so coverage is the consistent resolution.
- Verification needed: generated union/tool/CLI manifests enumerate the lifecycle kinds; adapter conformance fixtures send all 11 §20.1 events; replay reconstructs task terminal state; completion-without-evidence rejects.
- Evidence maturity affected: specified; blocks the design's own line-192 mapping requirement and the DUR-14 full-union gate before implementation starts.

### DREV-002: merge_nodes, consolidate_*, and the "registered solver proposal union" are referenced but undefined; no durable contract for consolidation already on the mainstream path

- Product priority: P2
- Approval disposition: changes_required
- Remediation eligibility: eligible_p1_p2
- Confidence: high
- Finding type: architecture / API contract conformance / hidden assumption
- Affected scenario and prevalence evidence: (a) consolidation runs today on the default runtime path — RuntimeStepService composes Consolidator (memorii/memorii/core/execution/service.py:10, 91, 105; resolution path at :243); the durable rewrite must state how consolidation effects and the spec §20.2 CONSOLIDATION_RESULT output survive. (b) duplicate hypotheses arise in the design's own flagship journey (DUR-01 "three competing hypotheses"); spec §16.24 makes merge the required duplicate handler. (c) `propose_state_change` accepts "the registered solver proposal union" (design line 274), but no such registry exists in code (no proposal union class in core/execution, api/, domain/, or core/solver), so its membership — including spec §23.1 `update_belief(node_id, new_value, justification_ids)`, `update_status`, `reopen_node` — is entirely an implementer invention.
- Design location: design line 274 ("proposal supplies the registered solver proposal union"); whole document contains zero occurrences of "merge" or "consolidat*" (verified by grep); line 192 requires the NODE_MERGED label mapping to be enumerated
- Governing source or requirement: spec §23.1 (1443-1464: update_belief with justification_ids, update_status, reopen_node, merge_nodes, consolidate_task_graph, consolidate_solver_graph, start_solver), §12 Consolidator, §16.24, §18.1 NODE_MERGED, §20.2 CONSOLIDATION_RESULT, §25.6
- Expected behavior: the durable API surface and event profile either implement or explicitly record a governing exclusion for every §23.1 entry and §20.2 output; the proposal union membership is enumerated so justification-bound belief updates, status updates, reopens, and merges have determinate entry points.
- Design behavior: NODE_MERGED exists in the code enum but no operation in the design's closed profile (create/update/delete + overlay version) produces a merge; consolidate_* and CONSOLIDATION_RESULT are absent; the proposal union is referenced as if registered but is not defined anywhere.
- Evidence: grep of design (0 hits); spec citations; service.py Consolidator composition; enums.py:230; no merge_nodes implementation anywhere in memorii/memorii/.
- Impact: the DUR-14 full-union-coverage gate and the line-192 mapping enumeration cannot close; consolidation state on the existing mainstream resolution path has no stated durable contract; duplicate-hypothesis handling has no durable operation; update_belief's justification_ids contract has no defined carrier.
- Root invariant or contract boundary: closed-grammar completeness — a closed union that silently drops governing API entries is a fail-open surface; candidate-to-committed and justification-bound belief updates require explicit typed entry points.
- Equivalence class and adjacent bypasses inspected: solver update events (could encode merge as updates, but the design never says so and the NODE_MERGED mapping stays undefined); overlay flags (reopenable is not merge); outbox writeback candidates (cover §21.2 writebacks, not consolidation results); RuntimeStateRequest views (read-only); the six memorii_* tools (omit both); ActionAttemptRecord `selected` state (also has no named creating command — sibling under-specification).
- Positive behavior that must remain valid: existing Consolidator behavior at solver resolution; overlay/justification durability; writeback-candidate-only semantic writeback; backtracking never deletes history; the eight specified command kinds.
- Recommended invariant-level resolution: enumerate the solver proposal union membership in the design (belief-update-with-justification_ids, status update, reopen, merge) or add the missing command kinds; for consolidate_*, map consolidation effects into the durable profile and §20.2 output set or record an explicit exclusion with its owner. One design amendment closes the grammar.
- Verification needed: generated request/tool/CLI/OpenAPI manifests show a 1:1 mapping for every §23.1 entry and §20.2 output (implemented or excluded-with-owner); replay round-trips a consolidation effect and a merge; the independent reducer reconstructs them.
- Evidence maturity affected: specified; would otherwise surface mid-implementation as improvised schema, regressing DUR-14 evidence integrity.

### DREV-003: Legacy JSONL on-disk layout inventory is missing from the migration detection contract; live installations use two different spellings

- Product priority: P2
- Approval disposition: changes_required
- Remediation eligibility: eligible_p1_p2
- Confidence: high
- Finding type: compatibility / migration (architecture)
- Affected scenario and prevalence evidence: migrating an existing live JSONL installation (the entire legacy-migration milestone, DUR-18) and managed SQLite startup on an unmigrated root. Every existing installation is affected. The layouts diverge per composition root, verified in code: Hermes uses `storage_root / "memory-plane"` (hyphen) at integrations/hermes_factory.py:552 and :559, and installed inspection hard-codes `_canonical_home(hermes_home) / "memorii" / "memory-plane"` at integrations/hermes_local_authority.py:238; the filesystem bundle and persistent capture cells use `resolved_root / "memory_plane"` (underscore) at core/filesystem_storage/bundle.py:71 and core/semantic_ingestion/production_capture.py:195; inspection passes the plane directory itself as the store root (hermes_local_authority.py:242). Neither the design nor any plan packet mentions either spelling (grepped).
- Design location: design lines 115 (detection rule and "never creates an empty database alongside old memory"), 117 (LegacyStorageSelector "exact root and file fingerprints"), 416 (installed-root gate creates a legacy seed with unspecified layout)
- Governing source or requirement: DUR-18 acceptance (design line 396); DUR-12 unknown-schema rejection; the design's own startup rule at line 115; AGENTS.md Level 3 migration obligations
- Expected behavior: the detection rule enumerates every legacy layout reachable from supported production roots (Hermes hyphen layout, bundle/capture underscore layout, direct-plane-root layout), defines which directory is the migration input root for each, and specifies behavior when both coexist in one root.
- Design behavior: `migrate plan` "detects an existing JSONL installation" with a singular input-root concept and no legacy layout inventory anywhere in the design, identity inventory, or milestone packet.
- Evidence: code citations above; today's detection-by-file-existence assumes exactly one layout (hermes_local_authority.py:239-241 checks memory_records.jsonl under the hyphen path only); design/plan greps confirm silence.
- Impact: if detection matches only one spelling, managed SQLite startup on a real Hermes root would not see the legacy plane and would create a fresh SQLite database beside it — directly violating design line 115 — or `migrate plan` would mis-fingerprint the primary legacy base; the "exact root" in LegacyStorageSelector is ambiguous when one root can contain both spellings, weakening exact-old/exact-new selector recovery.
- Root invariant or contract boundary: crash-cut recovery keys on exact-old-selector identity; migration must not silently drop, double-adopt, or bypass legacy memory (design lines 119-121).
- Equivalence class and adjacent bypasses inspected: all five direct JSONL constructor sites; the delegated authority_is_current reopen (hermes_factory.py:541-556); the inspection root (hermes_local_authority.py:236-244); capture cells (production_capture.py:190-196); the bundle factory branch (hermes_provider.py:97-110). All preserve their own spelling; none is called out.
- Positive behavior that must remain valid: fresh empty roots initialize normally; a correctly detected single-layout installation migrates with original bytes untouched; ambiguous or hostile precreated roots quarantine.
- Recommended invariant-level resolution: add a closed legacy-layout inventory (path components per composition root, both spellings, auxiliary participants) to the MemoryPlaneMigrationPlan schema contract and startup detection rule; specify the multi-layout/ambiguous-root outcome as explicit unsupported_configuration/quarantine rather than implicit fresh init.
- Verification needed: installed-root gate fixtures covering a Hermes-layout seed, a bundle-layout seed, and a mixed-layout root, each asserting migration_required (not fresh SQLite creation) before adoption.
- Evidence maturity affected: DUR-18 and DUR-13; the legacy-migration milestone acceptance is not determinately authorable until the layout inventory is pinned.

### DREV-004: Snapshot-verification cost model is unspecified; mandatory full-manifest verification per released snapshot is jointly unsatisfiable with the design's own latency budgets and tamper-rejection requirement

- Product priority: P2
- Approval disposition: changes_required
- Remediation eligibility: eligible_p1_p2
- Confidence: high
- Finding type: architecture / feasibility
- Affected scenario and prevalence evidence: every read and every commit on every installation once data accumulates. The manifest covers every authoritative materialized catalog by canonical digest of all typed rows ordered by primary key (design line 225), including the memory-plane retained-history tables (line 107, "retain every batch and version"). Recomputing that digest is O(partition rows) per verification. The design simultaneously budgets "no-model bounded state read p95 <= 250 ms" and "durable no-model command p95 <= 500 ms" at a reference fixture of 10k execution nodes / 50k solver nodes / 100k events / 1 GiB sources (line 356), and requires that row mutations with a preserved signed head be rejected by "every read/resume/page/render path" (line 475) — which requires row-level re-hashing at read time, not a digest-of-stored-digests comparison.
- Design location: design lines 225 (manifest definition), 227 ("Before every released SQL snapshot ... verify the snapshot's complete catalog manifest ... These checks cannot be skipped to meet performance targets"; alternative in-process projection with unstated cache rules), 105-107 (partition tuple binds the complete application-data manifest), 111 ("full-log rewrites per commit are forbidden"), 356 (budgets), 475 (tamper matrix)
- Governing source or requirement: DUR-11 (measured latency and recovery envelope), DUR-17 (measured resource envelope), DUR-02 tamper evidence; the design's own anti-pattern ban at line 111
- Expected behavior: the design states the verification structure and cost model — when full recomputation happens, what O(1) revalidation occurs per snapshot, how per-catalog digests are maintained at write time (incremental chains for append-only catalogs; explicit treatment of mutable latest-pointer/current-record tables), the projection cache's scope and cross-process invalidation, and which tamper events are detected at which boundary — such that the 250 ms/500 ms budgets and the line-475 rejection requirement are simultaneously satisfiable.
- Design behavior: no mechanism or amortization rule is stated anywhere (no incremental/merkle/rolling/delta structure in the design; the only cache language is digest-cached package bytes and forget invalidation). The escape hatch "explicitly revised supported envelope" (line 356) defers rather than resolves the conflict; validation.md lists "verification dominates usable capacity" only as a defect to be detected later by measurement.
- Evidence: design lines 105-111, 225-227, 356, 475 as quoted; the current system's amortization key is a cheap O(1) file identity (core/memory_plane/store.py:768-775 stat-based cache) — the SQLite design removes that signal without naming a replacement; write-side manifest production inside the publication transaction (line 231) is O(catalog size) for mutable catalogs unless an unstated incremental structure exists.
- Impact: as specified, either reads/writes carry O(partition) hashing and the published DUR-11 budgets fail at the design's own reference fixture, forcing a drastically reduced supported envelope at Level 3, or implementations quietly cache verification per control tuple, violating line 227/475 (an in-process row mutation after first verification would no longer be rejected) and creating an implementation/design divergence. Multi-process deployments amplify: the projection path is per-process, so each sidecar/embedded/CLI process pays checkpoint-plus-tail reconstruction on first read after every commit (tail up to the 100-command checkpoint cadence).
- Root invariant or contract boundary: "these checks cannot be skipped" and the DUR-11 budgets are both design-mandated; the missing piece is the mechanism that makes them jointly achievable — tamper detection with unchanged signed head is exactly the threat the signed-manifest protocol exists for.
- Equivalence class and adjacent bypasses inspected: SQL-snapshot read path (line 227 path 1), immutable-projection read path (path 2, per-tuple reuse implied but unstated, cross-process behavior unstated), write/publication manifest maintenance (line 231), checkpoint/tail verification (lines 213-215), backup verification (line 324), doctor full validation (line 320 — fine, off the hot path). The gap is shared by the read and write paths.
- Positive behavior that must remain valid: tamper detection rejects mutated rows with unchanged signed head on every read/resume/page/render path; exact-old/exact-new/third-tuple recovery works; no unverified row influences a released result.
- Recommended invariant-level resolution: specify the verification structure (e.g., per-catalog rolling/Merkle digests maintained transactionally by the publication transaction with explicit treatment of mutable catalogs; full recomputation bound to control-tuple acquisition and process start; O(1) per-snapshot revalidation via finalized-tuple equality under the installation fence; projection cache keyed to tuple with stated cross-process invalidation; a documented statement of which tamper events are detected at which boundary), then re-derive the DUR-11 budgets against that structure.
- Verification needed: the named Linux/macOS engineering fixtures measuring verification cost per read/commit at the reference fixture; the line-475 mutation corpus run against implemented read paths including repeated reads within one process.
- Evidence maturity affected: DUR-11 and DUR-17; the capacity evidence plan can currently only detect, not prevent, the conflict.

### DREV-005: Advertised sidecar transport-security behaviors have no named verification family or failure signal

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: evidence_action
- Confidence: high
- Finding type: verification (trust-boundary proof-planning gap in the implementation plan)
- Affected scenario and prevalence evidence: every sidecar deployment; the sidecar is a first-class v1 surface (design line 9) and the OpenClaw and Pi bindings depend on it (design lines 381-382). The design specifies loopback bind, browser-origin rejection, installation-issued bearer credentials mapped to finite grants, owner-only credential file permissions, and disabled remote binding (design line 278) — a reachable trust boundary, which AGENTS.md requires validated at every level.
- Design location: design line 278 (specification); verification surfaces that omit it: attack-matrix Authorization row (line 438, scope/leak cases only), DUR-13 ledger row (line 391, startup/default-authority only), line-475 extension list
- Governing source or requirement: AGENTS.md Level 3 bar (security, broad gates) and "reachable trust-boundary validation applies at every level"; design line 445 ("Tests must exercise all advertised roots"); DUR-13/DUR-05 acceptance
- Expected behavior: each advertised transport-security behavior has a named proof family with an observable failure signal (non-loopback bind fails at startup; browser-origin request rejected before task-derived data; missing/invalid bearer credential returns unauthenticated with no content; credential file mode owner-only on both OSes; remote binding refused).
- Design behavior: the behaviors are specified at line 278 but no verification artifact names them; validation.md's host-state row (line 17) covers rendering/overflow/legacy-denial only; harness-state.plan.md mentions browser-origin exclusion only as a Non-Goal constraint, not a proof obligation.
- Evidence: grep for loopback|browser|bearer across the design and all plan packets returns only specification sites, none in a proof/failure-signal column.
- Impact: at Level 3 a network-listening component could ship with its advertised transport posture unverified while the gate ledger closes honestly, because no gate was ever required for it. The gap is in the verification contract, not the (unimplemented) product.
- Root invariant or contract boundary: every advertised behavior must be covered by a named family with a clear failure signal; reachable trust-boundary validation is level-independent.
- Equivalence class and adjacent bypasses inspected: outbox target-auth reissue (covered), backup credential exclusion (covered), per-host credential creation in OpenClaw/Pi bindings (only "credential mapping," no denial signal), remote-binding-disabled (same gap, same family).
- Positive behavior that must remain valid: valid loopback clients with installation-issued credentials succeed through the same typed API as embedded mode; generated HTTP schema parity remains green.
- Recommended invariant-level resolution: add a sidecar transport-security family to validation.md's Required Proof Families (and to the design's attack-matrix extension list when the design is next amended), with the observable failure signals enumerated above. The behaviors already exist in the frozen design; this fills the matrix without amending design semantics.
- Verification needed: after the row is added, confirm packet allocation (harness-state and additional-harnesses) and that the linked testing WorkPlan inventories exact test paths before creation.
- Evidence maturity affected: keeps "specified" honest for sidecar security; prevents a future implemented-and-verified claim that omits the security posture.

### DREV-006: validation.md omits the consumer-delivery and checkpoint signing-key-lifecycle proof families the frozen design requires

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: evidence_action
- Confidence: high
- Finding type: verification (proof-matrix completeness)
- Affected scenario and prevalence evidence: (a) every `memorii consume` deployment — crash between intake and acknowledgement, divergent duplicate, poison message, reordered delivery; the local spool is the initial runnable transport (design lines 292-294). (b) every installation that rotates or revokes a checkpoint signing key — retired keys verify only within currently allowed trust intervals (design line 215). The design's own ledger requires both: DUR-06/DUR-03 row (line 383, "real local spool kill/redelivery/rejection"), DUR-03/DUR-04 row (line 378, "key rotation/rollback"), and the line-475 extension list names "consumer delivery family" and "signed checkpoint/tail key lifecycle."
- Design location: design lines 378, 383, 475 (requirements); omission site: docs/work/durable-memory-implementation/validation.md Required Proof Families (lines 7-25) and coverage.md DUR-03/DUR-06 test columns
- Governing source or requirement: the design's ledger rows are declared part of the implementation contract (design line 5, 373); the plan pins the design SHA
- Expected behavior: validation.md — the operative matrix packets select families from ("Each packet selects relevant families before code") — contains a row for every design-required family with an observable failure signal.
- Design behavior: the design specifies the proofs with signals, but validation.md has no consumer row (spool appears only inside the level column of the host-state row) and no key-rotation row (the publication family at line 44 covers selectors and same-head mutation, not key lifecycle); coverage.md DUR-03 omits key rotation and DUR-06 omits consumer. Five of the seven line-475 extension items are represented; these two are not.
- Evidence: validation.md:7-25, :44, :52; coverage.md:9, :12, :19; design lines 378, 383, 475; the bindings row (production_entrypoint_bindings.md:22) carries the strongest plan-side statement but is a callsite mapping, not the proof-family matrix.
- Impact: a packet selecting families from validation.md could close its milestone without consumer redelivery/dead-letter/ack-ordering proofs or checkpoint key-rotation negatives while the design-ledger obligation still exists — an inconsistency between milestone evidence and the frozen design's required gates at release-conformance time. Bounded: the design rows remain binding, so the requirement is not lost, only absent from the operative matrix.
- Root invariant or contract boundary: the implementation plan's proof matrix must be at least as complete as the frozen design's required proofs; packet-level family selection cannot silently drop a design-required family.
- Equivalence class and adjacent bypasses inspected: all seven line-475 extension items checked against validation.md (five present, two absent — one matrix-completeness invariant); DUR-03/DUR-06/DUR-13 rows in coverage.md; harness-state packet (covers spool intake/poison as contract text, no failure signal).
- Positive behavior that must remain valid: the five covered extension families; full DUR-01..18 row coverage in validation.md (verified complete); the design ledger's consumer-acceptance and runtime-recovery-acceptance gate names remain required at release.
- Recommended invariant-level resolution: add two rows to validation.md with failure signals drawn from the design ledger — (1) consumer delivery: crash-before-intake-ack redelivers with same operation ID; crash-after-ack resumes without broker; divergent duplicate dead-letters; transient storage failure does not acknowledge; invalid/untrusted message yields content-free rejection; (2) checkpoint key lifecycle: rotation retains historical verification only within current trust intervals; unknown/revoked signer rejects; retired key outside allowed interval rejects; key-registry rollback rejects. Mirror in coverage.md's DUR-03/DUR-06 test columns.
- Verification needed: re-run the requirement-to-family mapping check (all 18 requirements to at least one family, plus the line-475 extension set) and confirm packet family selections include both.
- Evidence maturity affected: none currently; prevents future family-complete claims while two design-required families were never selectable.

### DREV-007: HostBinding does not map TaskContext framework_run_id (or metadata) despite claiming to subsume TaskContext

- Product priority: P3
- Approval disposition: follow_up
- Remediation eligibility: record_only
- Confidence: high
- Finding type: undefined term / host-contract completeness
- Affected scenario and prevalence evidence: every adapter mapping harness-native state per spec §20.3 constructs a TaskContext with framework_name and framework_run_id; all five §22.2 adapter contracts are affected at contract-definition time. TaskContext does not exist in code yet, so HostBinding (design line 154) is its first realization and the omission becomes the de facto contract.
- Design location: design line 154 (HostBinding closed field list)
- Governing source or requirement: spec §20.3 (1324-1336) TaskContext payload fields
- Expected behavior: the closed HostBinding carries, maps, or explicitly excludes each TaskContext field.
- Design behavior: framework_name maps to host kind, session_id to session, thread_id to thread/branch, goal to start_task input; framework_run_id and metadata have no mapping and no exclusion.
- Evidence: design line 154; spec lines 1324-1336; grep shows no TaskContext class in memorii/memorii/.
- Impact: an implementer must invent where the framework run ID goes; closed validation will either reject real host bindings supplying it or silently drop the only correlate between a Memorii task and a specific framework run.
- Root invariant or contract boundary: typed public contracts must be closed and complete relative to the canonical payloads they replace.
- Equivalence class and adjacent bypasses inspected: operation_id (retry identity, not run identity), host cursor (opaque position), thread/branch, client installation, metadata (no bounded substitute).
- Positive behavior that must remain valid: closed HostBinding rejecting unknown fields; core never executing/importing a cursor; native session ID is not user authority.
- Recommended invariant-level resolution: add a bounded optional run-coordinate field or record the explicit mapping decision in the HostBinding contract and generated schema inventory; ideally folded into the same design amendment as DREV-001/002.
- Verification needed: generated OpenAPI/TS schema for HostBinding shows a determinate mapping for every §20.3 field; LangGraph/AutoGen/OpenAI contract fixtures validate against it.
- Evidence maturity affected: specified only; low-cost amendment.

### DREV-008: Implementation-plan/design consistency deltas: DUR-14 allocation mismatch, rollout-order inversion, missing four-category assumptions section

- Product priority: P3
- Approval disposition: follow_up
- Remediation eligibility: record_only
- Confidence: high
- Finding type: verification / plan conformance
- Affected scenario and prevalence evidence: a coordinator or resume agent reconciling milestone packets against the parent ledger and the design's rollout order. Three deltas: (a) coverage.md:20 allocates DUR-14 only to release-conformance while milestones/additional-harnesses.plan.md:7 lists "Requirements: DUR-06,13,14"; (b) design line 426 orders "complete operator controls and all-writer enrollment" before "second/third real host conformance," but the plan orders milestone 6 (additional-harnesses) before milestone 7 (operator-controls) — end state equivalent, sequencing statements disagree; (c) .agents/PLANS.md requires an "Assumptions And Open Questions" section with four categories; implementation.plan.md has no such section (assumptions are distributed through other sections).
- Design location: docs/work/durable-memory-implementation/coverage.md:20; milestones/additional-harnesses.plan.md:7; design line 426; implementation.plan.md section list
- Governing source or requirement: .agents/PLANS.md required common sections and indexed-WorkPlan allocation rules; design rollout sequencing
- Expected behavior: the parent coverage ledger is the single allocation authority; milestone requirement claims and design rollout order agree or record the deviation; the four-category assumptions section exists.
- Design behavior: as cited — small internal contradictions; all 18 requirements remain covered with no gap (verified row by row against all eight milestone headers).
- Evidence: file:line cites above (coordinator re-verified (a) directly after an initial too-literal grep suggested otherwise — "DUR-06,13,14" contains DUR-14 as the trailing value).
- Impact: resume agents may double-count or miss DUR-14 evidence ownership; sequencing ambiguity only.
- Root invariant or contract boundary: WorkPlan self-containment and resumability.
- Equivalence class and adjacent bypasses inspected: all eight milestone Requirements headers vs all 18 coverage rows (only the DUR-14 delta); both design sequencing statements (lines 131 and 426) vs the milestone dependency table; header fields, design baseline, verification commands, gate ledger, bindings ledger, identity ledger all conformant.
- Positive behavior that must remain valid: single next action; honest proposed status; plan-manifest checksums binding all packets.
- Recommended invariant-level resolution: one editorial pass — align the additional-harnesses header (or extend coverage.md), add one sentence recording the deliberate milestone-order deviation from design line 426, and add the four-category assumptions section; refresh plan-manifest hashes afterward.
- Verification needed: plan-manifest hash refresh; nothing product-level.
- Evidence maturity affected: planning artifacts only.

### DREV-009: Displaced (lease-expired, fenced-takeover) operation attempt has no enumerated terminal transition

- Product priority: P3
- Approval disposition: follow_up
- Remediation eligibility: record_only
- Confidence: high
- Finding type: runtime behavior / state-machine specification gap
- Affected scenario and prevalence evidence: every crash or lease expiry during a model call that is retried — the designed-for common failure (design line 164 exists for this path). The displaced attempt from the crashed/expired worker remains at a nonterminal stage with no defined disposition.
- Design location: design line 158 ("one active attempt per receipt"; unique (receipt_id, attempt_ordinal); fenced takeover), line 164 (awaiting_model -> prepared retry), line 166 (nonterminal -> rejected/needs_reconciliation enumerates four causes, takeover not among them)
- Governing source or requirement: the design's own closed-lifecycle bar; validation.md:44 requires the lifecycle family to enumerate every permitted and forbidden attempt transition including lease expiry/reclaim; design line 475 requires every operation-attempt transition in the attack matrix
- Expected behavior: a closed transition table in which takeover assigns the displaced attempt an explicit terminal state (or an explicit activity model), so the lifecycle matrix is determinately authorable and status/inspection does not report permanently pending work.
- Design behavior: the displaced attempt's transition is absent; "one active attempt" is undefined as stage-based vs lease-based, so the two natural uniqueness implementations diverge (a nonterminal-stage unique index would make the specified retry sequence impossible).
- Evidence: design lines 158-166; the analogous outbox reclaim (line 171) does specify same-delivery-ID reuse, showing the omission is an oversight; no takeover-disposition text elsewhere.
- Impact: implementation-defined semantics for a mainstream recovery path: lingering nonterminal attempts polluting pending-work status, or ambiguous uniqueness blocking retry. No data-corruption path: commit-time lease/fence recheck (line 202) still prevents a displaced worker from publishing.
- Root invariant or contract boundary: closed lifecycle grammars must enumerate every reachable transition; unknown lifecycle values fail closed.
- Equivalence class and adjacent bypasses inspected: command-receipt transitions, candidate_persisted takeover (well specified — staged bytes protected), outbox delivering->pending (specified), external-action dispatched->outcome_unknown (specified).
- Positive behavior that must remain valid: retry after lease expiry with strictly increasing fence; conservative spend reservation; no second model invocation merely from restart; displaced staged bytes retained as protected evidence.
- Recommended invariant-level resolution: add one transition row (displaced attempt -> terminal disposition on fenced takeover, e.g. needs_reconciliation with cause superseded_by_fence, or an explicit superseded terminal) and one sentence defining "active" (lease-valid and stage-nonterminal) plus the resulting uniqueness enforcement; fold into the same design amendment as DREV-001/002.
- Verification needed: lifecycle transition-matrix tests including expiry/reclaim (already allocated in validation.md:44).
- Evidence maturity affected: DUR-03 lifecycle-family matrix authoring.

## Requirements Coverage

Coverage of the independently reconstructed governing requirements by the design: complete for spec §17 persistence/resume (including unexplained observations, reopenable branches, run independence, staleness ordering), §17.4-17.5 checkpoints/retention, §18.2-18.3 envelope/idempotency, §19 integration modes (hybrid initial), §21 provider interface, §22.1-22.3 adapter responsibilities/prohibitions/minimum contract set (all five named, Pi extra-spec as installed target), §26-§27 logical stores/packaging/acceptance, storage §1 verbatim transcript, §2 scoped retrieval, §3 temporal validity, §5 agent scoping, §6 pluggable backends (entry-point group + backend-neutral protocol; no-fallback is a managed-root policy, not a pluggability contradiction), §7 local-first, §9 namespaces, §10 checkpoint content/replayability; event-model §3/§8-§10/§15 conformance including the frozen equal-version decision (verified conformant: batch-position ordering authority, no batch zero, three atomic binding indexes, full-state payloads, logical delete, independent reducers); implementation-rules resume/commit/adapter guarantees; scoped-context boundaries (process-local grants remain non-persisted; separate authorities); learned-ontology ownership (prepared-attempt -> pointer-CAS lifecycle, dual-gated reads, legacy readers, grant fence preserved). Partial: §18.1/§20.1 event-type coverage (task lifecycle events unproducible — DREV-001), §20.2 CONSOLIDATION_RESULT and §23.1 merge/consolidate/update_belief carrier (DREV-002), §20.3 TaskContext field mapping (DREV-007), storage §4.4 task-completion hook (blocked by DREV-001). Storage §8 benchmarking: complete for in-scope deterministic metrics (state equality, checkpoint+tail equality, named capacity fixtures); the user-deferred comparative agent-benefit campaign is a distinct obligation and its deferral does not conflict. No reconstructed requirement is contradicted by the design other than as recorded in the findings; no requirement is silently missing from the plan's coverage ledger (all 18 DUR rows allocated; only the DREV-008 allocation delta found).

## Architecture And Feasibility

The transaction/recovery core is sound as specified. The coordinator (with the correctness pass) enumerated crash cuts of the two-owner publication protocol (init, adoption, migration/restore generation-change, intent-prepare, data-commit, finalize, ack-loss, modified-row-with-unchanged-head): every interleaving lands in exact-old, exact-new, or quarantine; double-finalization by racing resolvers is idempotent; data verification rather than a committed flag determines recovery. The documented lock orders (design lines 101, 306) are mutually consistent and acyclic; readers hold grant/integrity fences through result release; WAL-snapshot insufficiency for revocation semantics is correctly handled. The attempt/outbox/action state machines are correct except DREV-009's missing row. SQLite choices are feasible and internally consistent (WAL + synchronous=FULL multi-process; one physical database delivering the single cross-domain transaction; online backup under exclusive barrier; the attached-databases atomicity reasoning is technically correct and applied consistently — no ATTACH-based coupling anywhere; optimistic batches never hold write locks across model calls; cryptography>=50 already a dependency). The design's factual claims about existing mechanisms all verified against code (apply_batch preconditions and meanings, dual revisions and _contains_runtime_context, first-insertion ordering, ontology CAS lifecycle, delegated reopen, bare-ID API). Milestone ordering is feasible and matches the design's line-131 rollout; CI/toolchain gaps (no macOS runner, no TS tooling, Python 3.11/3.12 split) are disclosed rather than assumed. The two architecture-level gaps are DREV-003 (legacy layout inventory) and DREV-004 (verification cost model).

## Failure, Security, And Operations

Failure behavior is comprehensively addressed: fail-closed unknown formats/backends/authorities; quarantine with integrity_error and no task-derived output; exact-old/exact-new recovery with third-state quarantine; anti-rollback (post-new-write downgrade refusal, security epoch never rolls back); uncertain tool completion never auto-reruns; outcome_unknown reconciliation; bounded retries with conservative spend reservation; resource_exhausted with safe limit names; ENOSPC rollback and degraded health. Security posture is coherent: independent control owner with signed journal; honest stated limitation on simultaneous control rollback (stated twice consistently); loopback sidecar with server-side credential-to-grant mapping; per-page reauthorization with stale_cursor; denial without content/counts; candidate/committed distinctions preserved through rendering; retrieved text never authority. Operations: mode fencing with participant enrollment and the correct sequencing rule that backup/mode/forget are not exposed until all-writer enrollment; forgetting/erasure properly separated with erasure_incomplete honesty; retention that never prunes unresolved state. The gaps in this lane are DREV-005 (unverified sidecar transport posture) and DREV-006 (two unselectable proof families); DREV-004 is also an integrity-vs-operations tension.

## Verification And Evidence Maturity

The design's attack matrix covers twelve families with owners/levels; the independent-reducer contract is precisely specified and mechanically enforceable on the import prohibition; validation.md maps all 18 requirements to proof families with graduated levels; all 14 regression-anchor test files exist and commands are runnable; the workflow inventory matches the live workflow files exactly (28+4+2 job IDs, three SHA-verified files; the canonical-parity scheduled-only status and the 3.11/3.12 split are accurately represented); proposed test names are behavioral throughout; evidence maturity is honestly "specified" everywhere — every checkable historical claim (27/14/8 test counts, probe files, 1334-member authority inventory, 18 plan-manifest hashes, prior-review corrections present in the frozen design) reproduced exactly; no evidence inflation was found in either document or the prior review ledger; the completion contract prevents premature closure (milestone approvals are parent-partial; remaining_validated_p1_p2 is evidence-bound, never prefilled). The verification gaps are DREV-005 and DREV-006; DREV-001/002 additionally block the DUR-14 full-union generated-inventory gate as specified.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Residual risk | Status |
| --- | --- | --- | --- | --- | --- |
| Implementer invents task-lifecycle/proposal semantics mid-build | DREV-001/002 uncorrected | Unreviewed public/persisted grammar; DUR-14 gate cannot close | Amend closed grammar before implementation; delta review | Low after amendment | Open (changes required) |
| Migration mis-detects or double-adopts legacy installations | DREV-003 uncorrected | Fresh SQLite beside old memory or rejected primary legacy base | Closed layout inventory in migration plan schema + mixed-root quarantine fixtures | Low | Open (changes required) |
| Latency budgets fail or tamper checks silently weakened at scale | DREV-004 uncorrected | Reduced supported envelope or undetected row tampering; implementation/design divergence | Specify incremental verification structure; re-derive budgets; mutation corpus on hot paths | Medium until mechanism chosen | Open (changes required) |
| Sidecar ships with unverified transport posture | DREV-005 uncorrected | Level 3 network surface without required proof | Add transport-security family before harness-state packet | Low | Open (changes required) |
| Design-required proofs unselectable by packets | DREV-006 uncorrected | Milestone evidence inconsistent with design ledger at release | Add two families to validation.md/coverage.md | Low | Open (changes required) |
| No macOS runner / TS tooling / host credentials at implementation time | Environment availability | Release-conformance milestone blocked | Plan already records these as execution prerequisites and explicit blockers, not assumed evidence | Medium (external) | Tracked by plan |
| Simultaneous control-authority rollback | Owner supplies old valid bundle + old anchor | Undetectable (stated limitation) | Documented; owner-supplied recovery material required | Accepted limitation | Documented in design |

## Rejected Or Consolidated Findings

No reviewer finding was rejected as unsupported. Two accuracy nits from the coordinator's repository-reality pass are recorded as accepted-accuracy notes, not findings: hermes_local_authority.py inspect_local_memory is at line 236 (plan preflight cites 235, within its stated tolerance), and four semantic-ingestion regression test files live under tests/unit/core/semantic_ingestion/ while validation.md lists them by bare name (paths exist; commands runnable as written from memorii/). The spec_auditor's source-hygiene observation (IMPLEMENTATION_RULES cites a stale spec path) is documentation follow-up, not a finding. One coordinator false-alarm during reconciliation (an initially too-literal grep suggesting DREV-008(a) was unsupported) was resolved by direct re-verification; the finding stands as confirmed.

## Required Changes Before Approval

1. DREV-001 (P2): extend the closed v1 command union with task lifecycle command kind(s) and enumerate the task event-label mappings.
2. DREV-002 (P2): enumerate the solver proposal union membership and the merge/consolidation durable contract (or explicit governing exclusions), mapping every §23.1 entry and §20.2 output.
3. DREV-003 (P2): add the closed legacy-layout inventory (both spellings, per-root input-root definition, mixed-root behavior) to the migration plan schema and startup detection rule.
4. DREV-004 (P2): specify the snapshot-verification structure and cost model; re-derive the DUR-11/17 budgets against it and state which tamper events are detected at which boundary.
5. DREV-005 (changes_required evidence action): add the sidecar transport-security proof family with failure signals to validation.md (packet allocation: harness-state and additional-harnesses).
6. DREV-006 (changes_required evidence action): add the consumer-delivery and checkpoint-key-lifecycle families to validation.md and mirror in coverage.md.

Design changes 1-4 belong to a linked build-design remediation of docs/design/durable_execution_and_solver_runtime.md followed by a delta review against a new frozen baseline; items 5-6 (and the DREV-008 editorial pass) are bounded implementation-plan corrections. DREV-007 and DREV-009 should be folded into the same design amendment for efficiency but are not approval blockers.

## Non-Blocking Follow-Ups

- DREV-007: HostBinding framework_run_id/metadata mapping decision.
- DREV-008: plan consistency editorial pass (DUR-14 allocation, rollout-order deviation note, four-category assumptions section) plus plan-manifest hash refresh.
- DREV-009: displaced-attempt terminal transition row and "active" definition.
- Documentation hygiene: stale spec path in IMPLEMENTATION_RULES; preflight line-number nits (235->236) at next packet refresh.

## Final Outcome

Changes required. Four validated P2 design defects (DREV-001, DREV-002, DREV-003, DREV-004) and two unresolved changes_required verification-planning findings (DREV-005, DREV-006) prevent approval at this baseline. No finding is blocks_approval and no external decision is missing: every correction is determinate and bounded within the design's existing architecture. The transaction/recovery core, storage architecture, security model, evidence honesty, identity hygiene, and implementation-plan readiness are otherwise sound. Upon remediation of items 1-6 with a delta review of the new frozen design baseline, this review's scope is expected to close as Approved with follow-ups (DREV-007/008/009).

## Review Limitations

Read-only review at a frozen baseline; no code, tests, or CI were executed by the review itself (the coordinator's verification was static inspection plus collection-level checks delegated to read-only passes). Historical probe claims were verified by inspection of probe files and test collection, not re-execution. Performance reasoning in DREV-004 is analytical (complexity-based), not a measurement; the named capacity fixtures remain the authoritative arbiter after the mechanism is specified. Reviewer passes were independent and concurrent; the coordinator validated every load-bearing factual claim against direct evidence before confirmation. This report judges design and plan readiness only — it is not implementation, operational, or release certification, and it does not revisit the separately user-deferred agent-benefit benchmark decision.
