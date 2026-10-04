<!-- Current frozen design SHA-256: ec927db8397e567b4087767b11572a5a5ab734bce55137fc4e8655c1d0ed97d2; prior hashes below are review history. -->

# Durable Runtime Design Review Ledger

## First Full Cohort

Candidate SHA-256 c1f19b8d8340bdeed9b754542e376e1f91caa9aca5626bba80decba513ea2fcb. Roles: durable_spec (spec_auditor), durable_correctness (correctness_reviewer), durable_tests (test_reviewer). Scope: complete Level 3 design and governing sources; design implementation remains unclaimed. Coordinator reconciled all reports before one coherent conformance edit.

| Finding family | Classification / disposition | Coordinator resolution |
| --- | --- | --- |
| Checkpoint authentication, current trust and freshness | Not applicable / changes_required / persistence-security; tier 2; confirmed, correctness duplicate of spec | Specify signed checkpoint and tail purpose, trusted key lifecycle, current policy/control watermark, crash-safe data/control publication intent and fail-closed restoration. Final review required. |
| Durable attempt and outbox lifecycle | Not applicable / changes_required / runtime-contract; tier 2; confirmed | Closed persisted attempt/lease/fence/candidate/budget transitions, stable outbox delivery and unique action reservation; billing duplication expressly not guaranteed away. |
| Behavioral identity inventory and mutation gate | Not applicable / changes_required / governance; tier 3; confirmed | Enumerate source/schema/SQL/API/tool/CLI/generated/test/gate families, field-aware command and positive/negative mutation inventory. |
| Required harness compatibility contracts and event consumer | Not applicable / blocks_approval / compatibility; tier 1; confirmed governing coverage gap, determinate correction | Add documented LangGraph/AutoGen/OpenAI contracts and runnable local-spool event consumer. No new OpenAI implementation requested, no scope waiver or external semantic decision needed. |
| Legacy bare-ID API compatibility | Not applicable / changes_required / compatibility-security; tier 2; confirmed | Production denies legacy shapes before lookup; explicitly ephemeral roots retain test/demo compatibility; individual sibling gates specified. |
| Requirement-keyed production/gate ownership | Not applicable / changes_required / verification; tiers 1-3; confirmed | Complete DUR-01 through DUR-14 trigger/authority/owner/outcome/failure/gate ledger including individual hosts, admin, capacity, migration, consumer and installed roots. |

These are bounded design contract-conformance actions, not demonstrated defects in a shipped implementation. No P1/P2 product-remediation claim. Every family was inspected by the coordinator against the canonical design and governing requirements. The second candidate also bounds erasure to isolated partitions, distinguishes encrypted backups from active-volume confidentiality, and clarifies source admission outside graph transactions.

## Final Full Cohort

Frozen SHA-256 061f3ed4dc551fd8472f928cced6372b74a5100afda64e4e04b2212dd102e478. All three original roles requested to independently inspect the whole revised design, not just deltas, including publication protocol and evidence limits. Canonical document frozen while reviews run. All three requested changes to the publication/control boundary, consolidated below.

## Publication/Control Boundary Conformance

The final cohort on 061f3ed4... returned one shared family, with two aspects: normal materialized reads were not authenticated by the signed head (correctness/test), and control recovery authority lacked closed schema and restore/migration ownership (spec/test). Coordinator confirmed both against the read path and control inventory. Classification: Not applicable / changes_required / persistence-security-recovery-verification / tier 2; bounded contract_conformance_action. No demonstrated shipped P1/P2 claim.

Second and final planned conformance batch reconstructs this boundary as a whole: closed publication tuple and materialization manifest, complete normal-read verification, non-circular checkpoint/head binding, closed intent/journal/trust state, separate recovery bundle and owner-supplied anchor, explicit authorized generation restore/migration, complete mutation/crash family and identity inventory. The simultaneous rollback of control owner and its recovery anchor remains an explicit limitation; no local mechanism can detect it from the same rolled-back authority.

## Final Whole-Design Review After Boundary Reconstruction

Frozen SHA-256 14b4e1126dbd17c4c97f50a37b7e84a9b5fa66d9ad83ad87d19992c761daa828. Three standard reviewers requested to inspect the complete design after the material contract reconstruction. No canonical edits while reviewing. Results pending.

Final 14b4 cohort: test reviewer approved; correctness confirmed one absent-bootstrap transition; spec reported freeze-ledger mismatch. Coordinator verified plan/reviews already had 14b4 in current sections (older hashes were history); evidence latest-check record lagged and is now explicitly pinned in every header. Bootstrap conformance is confirmed Not applicable / changes_required / security-architecture / tier 1-2. Added bounded owner-only init, signed genesis position, initial trusted registry and exact absent/new crash recovery, plus real-root proof. This closes the initial state of the existing boundary; one bounded clarification beyond two planned batches, no product-remediation loop.

Final complete candidate ec927db8397e567b4087767b11572a5a5ab734bce55137fc4e8655c1d0ed97d2: all three reviewers inspect the whole design; results pending.

## Final Disposition

All three independent roles approved the complete final frozen design ec927db8397e567b4087767b11572a5a5ab734bce55137fc4e8655c1d0ed97d2: spec_auditor approved the parent design scope with no confirmed required findings; correctness_reviewer approved the bounded whole design with no remaining confirmed P1/P2 or conformance finding; test_reviewer approved the complete design and acceptance strategy. Coordinator reconciled these reports against the final artifact. All confirmed families are resolved; duplicates are clustered above. Earlier freeze-governance concern is resolved by identical current headers and explicit historical hashes. No implementation, production-call coverage, CI enforcement or rollout certification is approved.
