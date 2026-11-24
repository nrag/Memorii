# Durable Delivery Implementation

- Work type: implementation
- Delivery fidelity: Level 3 first production release
- Status: active
- Coordinator: main task, with one product writer per overlapping slice
- Created and last updated: 2026-11-23
- Parent WorkPlan: [durable-memory release conformance](../durable-memory-implementation/implementation.plan.md)
- Related WorkPlans: [approved design remediation](../durable-delivery-design/design.plan.md), [readiness regrade](../durable-memory-design-regrade/design-review.plan.md), [delivery verification](../durable-delivery-testing/testing.plan.md)
- Canonical inputs: [durable-memory design](../../design/durable_execution_and_solver_runtime.md), governing specs and AGENTS.md source order
- Expected outputs: durable host offers and decisions, signed local delivery, restore-safe retries, installed client contracts and reproducible capacity evidence

## Objective And Baseline

On an installed managed partition, a host can recover the results of consolidation, accept or decline a candidate, and observe a correctly authorized target receipt. Work projections arrive automatically under the origin grant. After a crash or restore the system can distinguish a safe retry from one that requires reconciliation. Verify the reference workload on both supported platforms.

Design approved at SHA-256 `a51ec4e02a62b05a5b28dc2afed146263a56b125ac2bae8f9abbaf22cbb4f9f2`. Code preflight uses `4c390de14d63fd1e13961e77bcca2f6b82f693f5` on `codex/durable-memory-release`. Implementation branch codex/durable-delivery-implementation pins the pre-existing approved design and plan at fd74fc49. Preserve pre-existing edits to README and parent planning artifacts and the uncommitted approved design and review history. GitHub and project dependency downloads were unavailable during the prior trace. Recheck access and provision the pinned environments during execution. The [review evidence](../durable-delivery-design/evidence.md) supports only design approval and mechanism feasibility.

## Scope And Constraints

DUR-01/02/03/05/06/07/08/10/11/12/13/14/17 apply in the slices below. Parent claims remain partial until their full requirement evidence closes. Reuse signed publication, governed candidate admission, checkpoint and grants owners. Scope the delivery targets to one installation and partition. Keep native source capture, host choice and candidate staging distinct. Skill candidates use their own protected catalog. Keep the existing public command JSON shapes, with separately authenticated operation proof in managed transport. Preserve archived histories and sealed original payloads. Deferred comparative benchmark, unrelated release key ceremonies, remote targets, semantic promotion, and broader legacy data migration remain outside this child. No release candidate or product changes produced by plan creation.

## Sequence And Allocation

| Packet | Observable result | Depends on | Status |
| --- | --- | --- | --- |
| [Durable intent and output](milestones/durable-intent-and-output.plan.md) | New operations carry authenticated fixed origin across ingress and produce sealed outputs that survive restart | refreshed binding, registry and test preflight | Active. Signed SQLite replay and bounded lifecycle verified |
| [Host result and decision](milestones/host-result-and-decision.plan.md) | Authorized host reads an offer after restart and explicitly accepts or declines it | durable intent and output | Partial. Signed decisions and queue verified with sealed fixture offers |
| [Signed local delivery](milestones/signed-local-delivery.plan.md) | Installed worker publishes a target effect, receipt and terminal delivery together | host result and decision for implementation, see activation gate below | Partial. Explicit enrolled workers verified |
| [Restore delivery reconciliation](milestones/restore-delivery-reconciliation.plan.md) | Old generations cannot resend uncertain effects or rebind old commands | durable intent and output, exercise worker from signed local delivery | Partial. Verified staging through the owner CLI |
| [Reference capacity](milestones/reference-capacity.plan.md) | Same frozen fixture and procedure produce comparable Linux and macOS gate results | fixture/tool preparation can start early, timed acceptance requires the reviewed implementation | Partial. Installed diagnostic loader |

**Activation gate.** Keep the managed worker disabled outside the bounded test root until signed delivery and restore reconciliation both pass, including the legacy upgrade and current authority tests. This gate controls rollout. The delivery implementation has no dependency on completed rollout. The capacity fixture can be prepared in parallel with delivery, without overlapping writer files. The parent still owns signing, platform and host certification, quickstart and release decisions.

## Readiness, Evidence And Completion

Use the [resume packet](resume.md), [production bindings](production_entrypoint_bindings.md) and [validation and identity ledger](validation.md). Before editing persisted schemas, enumerate actual registry members, codecs, logical identities, SQL catalog and manifest coverage and generated artifact consumers. Benchmark design specifies fixture thresholds. No engineer may change them to pass. Linked design-tests work owns substantial suites, runner setup and CI changes. Use a test reviewer before high-risk implementation.

A packet closes only after exact production callsites and independent evidence at its candidate revision, applicable gates, one three-role review, and an empty remaining validated P1/P2 list with all required conformance findings resolved. The final combined branch review covers end-to-end closure and refreshes parent acceptance. Record exact implementation/run/artifact identities, distinguish direct local results from CI and real installed evidence, and reopen affected evidence if code or generated bytes change.

## Progress And Review

Implementation branch `codex/durable-delivery-implementation` is published to origin. The phase packets and validation ledger record the landed slices, local proof, and remaining acceptance. Full phase approval and parent release acceptance remain open. Use one writer per slice. Record reviewer role, source identity and verdict, and reconcile before remediation.

## Next Action

Bind provider-owned native source admission receipts to managed observation publication, then exercise a real source-backed pause result through signed replay and host acceptance.
