# Hermes Conversation Memory Trial: Diagnostic Cohort Review

- Reviewed design SHA-256: `37c2415ec22b5843f31fb37c359da1ae2db9c572ed3de19fe954b1530adaae61`
- Repository base: `3cfc1efc521c98ba4c8dfa048af8546cf4ec0d3e`
- Delivery fidelity: Level 2 early real-world testing
- Reviewers: `spec_auditor`, `correctness_reviewer`, `test_reviewer`
- Review scope: `HCM-01` through `HCM-06`, free-form Hermes turn to governed semantic commit to cross-session recall
- Disposition: diagnostic cohort complete; design not approved

This cohort ran at the user's explicit request while the normal candidate
freeze gate was not met. It reviews one frozen draft and is not implementation
or operational approval. All three reviewers read governing documents,
production paths, and existing tests. The coordinator reconciled overlapping
findings below; the canonical design was not edited during the cohort.

## Reconciled findings

| Finding | Classification | Affected case and evidence | Required correction and Level 2 proof |
| --- | --- | --- | --- |
| C01. Non-bootstrap model authority is unspecified | Product priority: Not applicable; approval: blocks_approval; type: governance/architecture | The draft defers its governing amendment, while `semantic_ingestion_architecture.md` SIA-R08/R09/R13/R14 requires explicit profile, egress, lifecycle, and capability authority; bootstrap v1 denies network. No production profile composition exists. | Amend the governing design with one exact opt-in profile, typed manifest/transport, per-segment egress decision, signed release/lifecycle, certification gate, and failure algebra. Map each HCM requirement to affected SIA requirements; prove a non-Hermes production-domain startup and zero-call denial before cohort re-review. |
| C02. Hermes principal and read authority have no trustworthy source | Product priority: P1; approval: blocks_approval; type: integration/security | Cross-session recall is the dominant journey. Current `hermes_memory_provider.py` derives user from `turn_author`/hook kwargs, while `prefetch` passes raw IDs without read ingress. The development issuer turns supplied user text into a principal handle. A second participant could be bound to the first participant's memory if the new factory repeats this pattern. | Name an actual Hermes-authenticated principal/session artifact or narrow the supported trial to one trusted principal and session. Define purpose-bound write and read ingress issuers in the runtime binding, bind reads to query/session/purpose, and deny missing/substituted/revoked authority without count or existence disclosure. Test turn-start, turn, session switch, and prefetch substitutions. |
| C03. Distinct equal-content turns can collide | Product priority: P2; approval: changes_required; type: runtime/persistence | `hermes_memory_provider.py` currently hashes session and content and documents that equal consecutive turns without transcript evidence are indistinguishable. HCM-02/HCM-05 require stable replay identity, but the draft names no new host envelope. | Require a host-issued immutable delivery ID or ordered immutable message coordinates. Carry it unchanged through user/assistant child events, ingress, fence, and replay. Without it, retain evidence but forbid semantic promotion. Test distinct equal-content turns, exact redelivery, changed history representation, restart, and concurrency. |
| C04. Memory-domain and scope routing are underdefined | Product priority: P2; approval: changes_required; type: architecture/runtime | The draft groups user preferences and project facts in one semantic fact vocabulary, while `memorii_spec.md` separates semantic, user-context, and task-local domains. Its proposed user-scope grant does not define which domain receives each claim. | Specify a typed route: durable user preference/constraint to user context; eligible reusable project fact to semantic; transient task claim to task-local evidence; ambiguous statement to non-promoting outcome. Define authorization for cross-session user scope and correction per route. Prove each with source, domain, scope, persistence, and recall assertions. |
| C05. Remote work has no Hermes hook acknowledgment contract | Product priority: P2; approval: changes_required; type: operability/integration | Current `sync_turn` calls ingestion synchronously and returns `None`; the draft proposes a remote model without timeout, pending-result, worker ownership, or outcome token. Network stall could block an ordinary conversation. | Choose bounded synchronous processing with a typed timeout, or durable admission acknowledgement plus leased background reconciliation. Define what Hermes observes, when memory becomes recallable, retry/release rechecks, shutdown, and operator lookup. Fault-test timeout, lost response, process kill, retry, and committed-only recall. |
| C06. First-party factory collides with the development connector | Product priority: P2; approval: changes_required; type: integration/operability | The current development connector also registers `memorii.hermes.provider_service`; the bridge rejects multiple factories. The user's existing Docker image installs that connector. | Specify one production-image owner of the service-factory entry point and an explicit migration from the development image. Check installed entry-point inventory for old, new, and accidental co-install images; verify rollback and old-volume reopening without duplicate writes. |
| C07. Acceptance proof does not yet exercise all required paths | Product priority: P2; approval: changes_required; type: verification | Current bridge tests use a fake Hermes ABC, test factory, and seeded recall. The draft lacks mandatory installed-wheel real-loader proof, read-ingress mutation, full exclusion family, interruption failpoints, and upgrade/rollback volume checks. | Require installed-distribution black-box discovery -> initialize -> real completed turn -> committed outcome -> protected prefetch. Add authority/substitution/raw-transcript-fallback mutations; table-driven nonassertions; source/attempt/graph/outcome crash points; old-volume upgrade/rollback; and a Windows Docker run with frozen fresh facts and exact source/outcome/answer evidence. |

## Coordinator classification

All seven clusters are confirmed. C02 combines the specification and
correctness read-authority findings with the test review's authority-mutation
gap. C03 combines the specification/correctness identity findings. C06
combines package migration and volume-compatibility findings. C07 combines
the test review's five verification gaps; the product-contract portions stay
in C02-C06. No finding is dismissed merely because a test is missing: each
required test is tied to the stated Level 2 path or a common failure.

The specification reviewer labeled C03 P1. The coordinator assigns P2 because
equal-content repeated turns are important but not the ordinary dominant
turn pattern; the collision is nevertheless a required correction. The
correctness reviewer labeled C02 P2. The coordinator assigns P1 because
authenticated cross-session recall is the stated primary user journey and a
missing or forged principal breaks that entire journey. These adjustments
do not change the approval disposition.

## Closure order and evidence

1. Resolve C02's real Hermes identity source. If Hermes supplies no
   authenticated cross-session principal, narrow the supported journey and
   revise HCM-04 before changing implementation.
2. Specify C01 and C04 in the governing semantic architecture, including the
   one selected profile, source eligibility, domain routing, and scope grant.
3. Specify C03/C05/C06 in the Hermes integration contract: delivery envelope,
   hook acknowledgment, and mutually exclusive package ownership.
4. Complete C07's requirement-to-proof matrix and a feasibility spike through
   real profile authority and protected retrieval; refresh the production
   entrypoint binding map and candidate digest.
5. Only then run a final whole-design cohort. A delta review may assess a
   bounded correction, but it cannot approve the still-open whole design.

No source code, test suite, Windows container, or live model was changed or
run by this cohort. The existing focused operation-identity test passed in
the correctness review, but it does not cover the documented equal-payload
fallback collision. This review establishes design gaps, not runtime quality.
