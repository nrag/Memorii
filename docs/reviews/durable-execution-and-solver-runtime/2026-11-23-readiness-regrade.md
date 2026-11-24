# Design Review: Durable Memory, Execution, Solver State And Harness Recovery

## Review Metadata

- Review ID: 2026-11-23-readiness-regrade
- Review mode: full, Level 3 design readiness
- Review outcome: Changes required
- Design path: [canonical design](../../design/durable_execution_and_solver_runtime.md)
- Design baseline: SHA-256 `63f90df2a4e822df430c32b209f03a671379189bc8e999e19d7f12ac5fbf94fe`
- Implementation baseline: `4c390de14d63fd1e13961e77bcca2f6b82f693f5`
- Review date: 2026-11-23
- Reviewers: coordinator plus independent spec, correctness and test/evidence passes
- Included scope: Level 3 contract and implementability, with deeper delivery, restoration and verification inspection
- Excluded scope: design edits, product changes, PR approval, provider execution and deferred comparative benchmark

## Executive Assessment

**68/100, Changes required.** This is a judgment against the Level 3 implementation-readiness bar. Any unresolved authority or recovery contract prevents approval regardless of the score.

| Review area | Score | Reason |
| --- | ---: | --- |
| Requirements and architectural boundaries | 18/20 | Clear physical and logical separation, canonical owners and source hierarchy |
| Public and persisted contracts | 12/20 | Consolidation output and host persistence decisions lack complete carriers |
| Authority and correctness | 12/20 | Target admission lacks a defined authorization and effect boundary |
| Recovery, migration and operations | 14/20 | Strong publication and legacy adoption story, open older-backup effect recovery |
| Acceptance and release evidence | 12/20 | Substantial failure matrix, incomplete delivery oracles and reproducible capacity contract |

## Governing Sources

Apply AGENTS.md source precedence. Core spec §§12, 17, 19–23 govern consolidation, restart, host outputs and persistence choice. Storage details govern typed backend and failure behavior. Event model §§3, 8–10, 15 govern canonical history and replay. Implementation rules preserve candidate lifecycle, typed domains and authority. Scoped context and learned ontology designs preserve grant and catalog semantics. The frozen September review and remediation packets are revision-bound context.

## Independently Reconstructed Requirements

| Requirement | Source | Design coverage | Acceptance criteria | Verification | Status |
| --- | --- | --- | --- | --- | --- |
| Local shared SQLite with domain-separated ownership, canonical legacy parity and cutover | storage details, ontology design, user scope | partition views, dual revisions, legacy adoption, indexed readers | old/new parity, unchanged bytes, no implicit fallback | production root mapping, migration fixtures | specified, no new finding |
| Recover full execution/solver state and distinguish uncertain external actions | spec §17, event model | typed batches, overlays, receipts, checkpoint and fencing | fresh process exact state and no repeated external action | opened catalog/transaction/replay boundaries | specified, no new finding |
| Represent every consolidation output and give the host a persistence decision | spec §§12.2, 20.2, 21.2 | closed delivery union and result envelopes | every produced output can be read, replayed and accepted or declined under the correct scope | output/union and wire comparison | contradictory or missing, DREV-001/002 |
| Authenticate delivery and commit one logical target effect | core invariants, DUR-03/05/07 | leased relay and stated target receipt | both race orders, per-target receipt/effect count and lost acknowledgement | source, target and barrier inspection | partial, DREV-003 |
| Restore safely under current authority and account for post-backup outcomes | spec §17, DUR-03/10/12 | independently anchored control, generation switch | older restore preserves effect knowledge or quarantines uncertain work | recovery/receipt cross-check | partial, DREV-004 |
| Match supported host and capacity claims to exact release artifacts | DUR-06/11/13/14/17 | pinned host roots, targets and artifact matrices | same reproducible workload per declared platform, required job and package proof | workflow and capacity fixture inspection | partial, DREV-005 |

## Contract And Evidence Boundaries

Shared physical storage does not confer cross-domain write authority. Canonical payload owners and existing source admission remain independent of graph commits. State publication, host-visible results and target acceptance have different persistence boundaries. Existing typed backend and signature mechanisms are feasible. A delivery ID, enqueue row or callback return string supplies no evidence of production target acceptance. Prior CI certification and architectural approval attach to their recorded revision and scope. New review IDs are documentation coordinates only.

## Confirmed Findings

### DREV-001: Closed outbox cannot represent every required consolidation output

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: public and persisted contract, tier 1
- Affected scenario and prevalence evidence: Supported completion or pause with archive, unresolved summary, or several candidates of one category.
- Design location: Canonical design lines 171–174 and 201.
- Governing source or requirement: Core spec §12.2 and §21.2. DUR-01/03/07.
- Expected behavior: Every declared producer output has a typed, reconstructible representation and stable per-output identity.
- Design behavior: The closed kinds cover WorkStateSummary plus revision and WritebackCandidate. The consolidation contract additionally requires archive references and follow-up summaries without mapping those outputs to the union or naming their durable owner.
- Evidence: The archive reference has no member in either declared payload. WritebackCandidate also has generic content and selectable status, so reusing it alone does not define the accepted delivery grammar.
- Impact: An implementer must drop outputs, extend the format by guesswork, or overload an incompatible type.
- Root invariant or contract boundary: Total producer-to-payload-to-target mapping with replay closure.
- Equivalence class and adjacent bypasses inspected: Compared all six consolidation categories, four candidate domains, multiple same-kind outputs, archive pointers, and legacy digest-only entries.
- Positive behavior that must remain valid: Projections and candidate-only outputs preserve their distinct governed owners.
- Recommended invariant-level resolution: Specify the closed per-output mapping, payload bytes/ref, owner, provenance, digest and stable identity across retries. Use explicit rejected or reconciliation treatment for digest-only rows.
- Verification needed: Drive pause and completion on an installed root and prove each emitted type reopens with stable identity. Test repeated and divergent outputs and missing payload closure.
- Evidence maturity affected: Specified to derivable

### DREV-002: Host cannot exercise the required candidate persistence decision

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: wire contract and authorization, tier 1
- Affected scenario and prevalence evidence: An authorized host observes consolidation after task completion or reconnects after a process restart.
- Design location: Canonical design lines 201, 260–281.
- Governing source or requirement: Core spec §20.2 and §21.2. DUR-06/07.
- Expected behavior: Consolidation results and candidate offers survive restart. The host has a scoped way to accept or decline persistence.
- Design behavior: The text promises CONSOLIDATION_RESULT in the result envelope and points writeback candidates to the outbox. The published response and command unions contain neither an explicit result member nor a scoped decision route.
- Evidence: Compare HarnessStateEnvelope fields, RuntimeResult alternatives and RuntimeCommandRequest kinds with spec §21.2.
- Impact: Implementers may treat automatic delivery as consent or leave offers invisible to the host.
- Root invariant or contract boundary: Recommendation, offer, host decision and persisted candidate are distinct states.
- Equivalence class and adjacent bypasses inspected: Checked response receipt, summary envelope, tool set, consumer path and durable retry.
- Positive behavior that must remain valid: Hosts can still choose to persist valid candidates, with promotion under the original owner.
- Recommended invariant-level resolution: Specify the authorized result carrier or retrieval port and its accept/decline, expiry, retry and redaction rules. Define whether any automatic staging is only an inert offer.
- Verification needed: Use an installed host to observe the same scoped candidate after restart, decline or accept it, and prove only the accepted candidate is staged without creating a committed fact.
- Evidence maturity affected: Specified to derivable

### DREV-003: Target admission has no defined authorization and receipt commit boundary

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: authority, transaction and retry contract, tier 2
- Affected scenario and prevalence evidence: A queued delivery races with a pause, revocation or lease takeover. Another supported scenario loses the acknowledgement after target acceptance.
- Design location: Canonical design lines 171–174, 212–214, 311–321, 375 and 392.
- Governing source or requirement: DUR-03/05/07/08 and source/claim separation in the specs.
- Expected behavior: The target independently validates live scoped authority and commits a matching receipt with the governed effect.
- Design behavior: The design assumes an existing provider port and reissued authority while placing delivery outside the source barrier. It leaves the target method, issuer, identity/digest scope and target-side commit fence unspecified.
- Evidence: ProviderMemoryService.sync_event authenticates source ingress. WorkStateMemoryProjector handles provider events. Neither consumes both promised runtime payloads under the declared receipt contract.
- Impact: A source recheck after target commit cannot undo an unauthorized target effect. A missing or ambiguous receipt has no fully defined retry result.
- Root invariant or contract boundary: Linearize grant, source, mode and claim validation at target commit. Persist a target-owned receipt with the effect.
- Equivalence class and adjacent bypasses inspected: Inspected work projection and candidate targets, stale workers, duplicate or divergent target receipts, absent target, revoked or expired pending work, and lost acknowledgements.
- Positive behavior that must remain valid: Valid retries reuse the same identity. Semantic source testimony and generated candidates remain separate.
- Recommended invariant-level resolution: Name each target entry point and authority issuer. Define per-kind effect and atomic receipt, both race orders, stale-fence behavior, bounded retry and reconciliation. Keep network I/O outside the source write lock.
- Verification needed: Installed-root tests count durable target effects, prove candidate-only admission, both mode/revocation race orders, stale worker refusal and a crash after target commit before source finalization.
- Evidence maturity affected: Specified to derivable

### DREV-004: Older restore can lose the proof that a delivery already happened

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: recovery and idempotency, tier 2
- Affected scenario and prevalence evidence: An authorized owner restores an older generation after target acceptance and before both sides have durable evidence inside that backup.
- Design location: Canonical design lines 171–174, 212, 331, 337 and 345.
- Governing source or requirement: DUR-03/07/10/12.
- Expected behavior: Only proven safe deliveries resume after restoration. Unknown effects enter reconciliation.
- Design behavior: The design preserves current security authority and requires the restore preview to account for post-backup outbox effects. It supplies no worker eligibility rule or receipt evidence source across generations.
- Evidence: An older snapshot can return a delivery to pending while its target has already accepted it. The relevant target receipt can be restored away or unavailable depending on the participant boundary.
- Impact: After restore the same delivery may be sent without idempotency evidence, or silently dropped.
- Root invariant or contract boundary: An older generation cannot reauthorize an effect whose outcome is unknown.
- Equivalence class and adjacent bypasses inspected: Inspected co-restored and independent targets, fresh host, older generation, pending and delivering entries, lost acknowledgement, and host retries that reuse operation IDs. Preserve safe replay when the effect is demonstrably absent under the verified target watermark.
- Positive behavior that must remain valid: Retain normal delivery retry and current revocation checks when durable proof exists.
- Recommended invariant-level resolution: Specify which authoritative receipt survives and how its watermark is checked, or require a durable reconciliation hold for affected entries until proof is recovered.
- Verification needed: Exercise older backup before send, after target acceptance, and after source finalization. Check missing receipt, both target placements, revocation and no automatic repeat under uncertainty.
- Evidence maturity affected: Specified to derivable

### DREV-005: Capacity thresholds lack a reproducible acceptance workload

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: evidence_action
- Confidence: high
- Finding type: verification and release evidence, tier 2
- Affected scenario and prevalence evidence: Candidate approval on Linux and macOS for the proposed reference envelope.
- Design location: Canonical design line 363 and verification matrix.
- Governing source or requirement: DUR-11/17 and exact-release completion contract.
- Expected behavior: The same named versioned inputs and workload allow comparable pass/fail decisions.
- Design behavior: Aggregate counts and latency budgets are stated, but the fixture distribution, operation mix and measurement protocol are not frozen.
- Evidence: Identical node and event totals can be concentrated in one large task or spread over many tasks. The current measured test uses 200 tasks and different proofs.
- Impact: Independent runs may pass different workloads while claiming the same support envelope.
- Root invariant or contract boundary: Support claims must bind to a reproducible workload and timing boundary.
- Equivalence class and adjacent bypasses inspected: Compared warm read, acquisition, command, resume, backup pause, write amplification and supported platform cases.
- Positive behavior that must remain valid: Keep smaller fast regression fixtures and distinguish acquisition from warm latency.
- Recommended invariant-level resolution: Freeze fixture generator/version, task and source distribution, sampled operations and concurrency, warmup and quantile protocol, environment and named output artifacts.
- Verification needed: Run the same acceptance fixture across supported Linux and macOS environments and publish actual results as evidence.
- Evidence maturity affected: Derivable acceptance to operationally verified

## Requirements Coverage

The suite of architectural and runtime requirements remains in scope. Partial design coverage is called out above. No new approval is inferred for other requirements from the absence of a finding, and no ledger status is promoted.

## Architecture And Feasibility

Keep the existing storage and domain separation. Source tracing found a real installed consumer and signed publication owner. The current enqueue, receipt, target adapter and host result paths cannot deliver the design's full promise as composed. This is a bounded remediation around interfaces rather than a requirement to replace SQLite, the event model or the semantic pipeline.

## Failure, Security, And Operations

Current implementation drift is distinct from design omissions. The digest-only work projection producer in runtime_api.py:304–321 fails the design's explicit payload-reference requirement. The test-called drain at runtime_api.py:488–515 performs a callback in a raw partition write. The design already requires signed publication and separate target effects. These are implementation deviations even after the contract is repaired. The host binding and operator release journeys require their own production evidence.

## Verification And Evidence Maturity

Combine the delivery and authorization findings into an installed-path proof matrix with actual target effects and receipts as oracles. The October CI record does not close new design findings. Existing coverage is useful but source code and review artifacts establish only the scope inspected in this regrade. Do not infer whole-release acceptance.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Residual risk | Status |
| --- | --- | --- | --- | --- | --- |
| Output loss or implicit persistence | consolidation or reconnect | missing work or unapproved memory | closed carrier and explicit host decision | none assessed before revised contract | open |
| Wrong or repeated effect | pause/revoke, ack loss or restore | inconsistent target state | fenced target receipt and recovery hold | external systems still require revalidation | open |
| Noncomparable performance approval | different fixtures per platform | inaccurate support claim | frozen workload and timing protocol | hardware variance must be reported | open |

## Rejected Or Consolidated Findings

The test lane's missing target-effect assertions are included in DREV-003 rather than a duplicate. The spec and correctness lanes identified the same output grammar gap, reconciled as DREV-001. The correctness and test lanes agreed on restore scope, reconciled as DREV-004. Code deviations alone are excluded from the design score. The older accepted threat limitation for simultaneous rollback of trusted control and its recovery anchor was not reopened.

## Required Changes Before Approval

Reopen the consolidation, host decision, target receipt and restore contract together in a linked build-design operation. Freeze the capacity fixture and acceptance protocol before release qualification. Review the revised public and persisted boundaries on a new frozen baseline before beginning the outbox implementation slice.

## Non-Blocking Follow-Ups

Reconcile the implementation and release ledgers after remediation and refresh install documentation at the release candidate. The agent-benefit benchmark and explicitly deferred forgetting endpoint walks retain their existing disposition.

## Final Outcome

Changes required. The grade measures Level 3 readiness of the frozen document. It is not implementation or release approval. Design remediation is handed off separately.

## Review Limitations

Three read-only passes and coordinator checks. Current source, workflow and documented evidence were inspected. Tests and remote checks were not run for this design review. Product priority is Not applicable on these design contract and acceptance findings because the reviewed gaps would otherwise require inventing behavior. Current code deviations are identified separately without making a new incident or prevalence claim.
