# Current-Release Bootstrap V3 Free-Form Decision

- Work ID: hermes-current-release-freeform-decision
- Work type: design
- Delivery fidelity: Level 2 early real-world testing
- Status: complete
- Coordinator: `/root`
- Created: 2026-09-23
- Last updated: 2026-09-23
- Parent WorkPlan: `docs/work/hermes-bootstrap-v3-freeform-admission/design.plan.md`
- Related WorkPlans: `docs/work/hermes-conversation-memory-trial/implementation.plan.md`
- Canonical inputs: `AGENTS.md`, `.agents/PLANS.md`, `docs/design/semantic_ingestion_architecture.md`, `docs/design/hermes_conversation_memory_trial.md`, and `docs/work/hermes-conversation-memory-trial/implementation.plan.md`
- Expected outputs: one current-release Bootstrap V3 free-form admission contract and clean-volume Level 2 rollout evidence

## Product Decision

Memorii is unreleased. No backward compatibility, migration, rollback, legacy
decoder, V1/V2 artifact union, or preservation of literal-corpus local/dev data
is required. Existing local Docker state may be discarded and rebuilt on a
clean `/opt/data` volume. This decision applies only to the current-release
Bootstrap V3 free-form admission work.

## Completion Contract

The governing design names one in-place Bootstrap V3 free-form policy/artifact,
one route/proof schema, and one clean-volume implementation path. Bootstrap V3
remains the only runtime. Literal corpus fixtures are test/golden data outside
production artifacts and cannot select a route. Completion requires an exact
policy, trusted fixed-English issuer, raw-NFC validation, child cap, full
per-child proof, phase revalidation, clean-volume rebuild, and two-fact live
Hermes journey. No production code is changed by this plan.

## Requirement And Evidence Matrix

| Requirement | Current-release behavior | Evidence |
| --- | --- | --- |
| CRFA-01 | One Bootstrap artifact family binds free-form policy and installed resources. | Build/verify/install/reopen tests. |
| CRFA-02 | Only factory-issued fixed-English evidence and policy-valid raw NFC children select existing V3 transport. | Denial/boundary/no-detector tests. |
| CRFA-03 | Each prepared child has exactly one full coordinate route/proof pair. | Span/bijection/substitution tests. |
| CRFA-04 | Egress, commit, recovery, and read revalidate installed policy/authority. | Phase mutation and stale lease tests. |
| CRFA-05 | Clean-volume Windows image commits two golden-absent assertions and recalls after new session/restart. | Installed-loader operational evidence. |

## Final Cohort Review And Completion

The final spec, correctness, and test reviewers approved the frozen
current-release candidate. The review confirmed one Bootstrap V3 runtime, one
in-place free-form route/proof schema, factory-owned fixed-English authority,
clean-volume rollout, phase/read revalidation, and the required two-fact real
Hermes evidence contract. No confirmed design finding remains at Level 2.

This plan completes the product decision and its design consequences only. It
does not claim the first-party factory, route/proof persistence, normalizer,
writer, installed image, or Windows Docker journey is implemented.

The resumption target is the active
`docs/work/hermes-conversation-memory-trial/implementation.plan.md` WorkPlan.
It owns all product edits, checks, and operational evidence.

## Next Action

None. The current-release free-form decision is complete.

## Candidate Freeze Record

| File | SHA-256 |
| --- | --- |
| `docs/design/semantic_ingestion_architecture.md` | `c356119c1c497de32b6fa74ce6ba7174b6dd3a4f6d635add98584cc0bdb28517` |
| `docs/design/hermes_conversation_memory_trial.md` | `5e54607fc266f116a1c7a112f45ae4218cbd1665d4fe9dd213f18a3b18e090e4` |
| `docs/work/hermes-conversation-memory-trial/implementation.plan.md` | `bf03c92836f5197dcb44c6e7e8d543b7879f76e3d2d61965f8e8ba7adf03299e` |

This decision WorkPlan is not self-hashed. Review rejects any mismatched bytes.
