# Accepted Fact Group Commit Storage Retry Debugging

- Work ID: accepted_fact_group_commit_storage_retry_debugging
- Work type: debugging
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-09-05
- Last updated: 2026-09-05
- Parent WorkPlan: `docs/work/semantic_ingestion/builtin-target-materialization/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/builtin-target-materialization/testing.plan.md`; `docs/work/semantic_ingestion/bootstrap-v3-source-progress-bridge-2026-09-04/implementation.plan.md`; scoped candidate `docs/work/semantic_ingestion/group-commit-storage-retry/candidate-manifest.json`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md` Sections 4.8.2.17-4.8.2.27; `docs/design/memorii_storage_details.md`; `docs/design/event_model.md`; `docs/IMPLEMENTATION_RULES.md`
- Expected outputs: causal correction for the accepted entity-object fact group commit and revision-bound direct-root regression evidence

## Objective

Make the already-constructed typed accepted fact group pass the canonical group
commit/CAS boundary, producing a durable accepted graph effect instead of a
`BootstrapGraphDurableRetryProgressV3(reason="storage_retry")`.

## Completion Contract

Complete only when the exact commit rejection is reproduced and causally
explained; serious competing hypotheses are discriminated; the smallest safe
fix makes the same direct-root reproducer pass; sibling group-commit/recovery
checks pass; no temporary diagnostic behavior remains; independent
specification, correctness, and test review has no unresolved P1/P2 or
`changes_required` finding; and a revision-bound closure record is appended.

## Scope

Included: accepted fact group-commit request construction, atomic CAS
validation/materialization, durable retry selection, and the direct production
root reproducer. Excluded: other operation arms, provider API redesign,
unrelated storage behavior, M5, and claims of parent M3.1/M4 completion.
Deferred: four-root contention and JSONL closure until the direct accepted
effect passes.

## Constraints And Invariants

- Preserve the atomic store as the sole graph linearization owner.
- Do not weaken request, digest, authority, generation, replay, or recovery validation.
- Do not turn a real storage failure into success or bypass durable retry.
- Keep unsupported operation arms fail-closed and effect-free.
- Preserve unrelated coordinated dirty-tree changes.

## Identity And Coordinate Hygiene

| Surface | Identity | Class | Owner/meaning | Disposition | Proof |
| --- | --- | --- | --- | --- | --- |
| debugging plan | work ID in this file | planning/evidence | operation tracking | retain here only | repository identity gate before closure |
| product/test names | existing behavioral group-commit identities | behavioral | graph transaction behavior | retain | changed-family search before closure |

## Change Impact And Verification Closure

| Path or pattern | Surface class | Scope owner | Authority chain | Required gates | Status |
| --- | --- | --- | --- | --- | --- |
| `memorii/memorii/core/semantic_ingestion/bootstrap_graph_builtin.py` | product | this WorkPlan | sealed snapshot -> plan/attempt authority | four-root accepted-fact proof, Ruff | corrected and locally verified |
| `memorii/memorii/core/memory_evolution/bootstrap_graph_planning.py` | product | this WorkPlan | plan record order -> planning-state fold | four-root accepted-fact proof, Ruff | corrected and locally verified |
| `memorii/memorii/core/memory_evolution/atomic_store.py` | persistence | this WorkPlan | planning payload -> commit coordinates -> canonical durable records/event delta | transaction/recovery tests | corrected and locally verified |
| `memorii/memorii/core/semantic_ingestion/contracts.py` | persisted codec | this WorkPlan | native group result JSON -> typed reload | native codec and recovery tests | corrected and locally verified |
| `memorii/memorii/core/semantic_ingestion/bootstrap_graph_artifact_assembler.py`; `bootstrap_graph_coordinator.py` | product/persisted authority | this WorkPlan | exact group request -> terminal construction -> checkpoint/recovery | authority-substitution and JSON round-trip tests | corrected and locally verified |
| direct-root/four-root fact test | acceptance test | linked testing plan | public root -> built-in host -> commit | exact test node | passing |

## Production Entrypoint Bindings

| Requirement | Trigger/root | Callsite/authority | Owner chain | Proof/callers | Status |
| --- | --- | --- | --- | --- | --- |
| accepted fact commits graph state | `ProviderMemoryService.sync_event`, four normal roots | host executes coordinator; coordinator calls `commit_or_reload` with assembled group request | typed normalization -> planner -> coordinator -> atomic store -> group-result checkpoint | four-root test; one logical production chain shared by four roots | implemented; four roots pass and persist one group primary each |

## Sources Of Truth

The listed governing documents take repository precedence. Current production
code, persisted models, and exact test output establish observed behavior.

## Incident Or Symptom

Expected: `Atlas owner is Bob.` produces a durable accepted graph effect through
the direct production root. Observed: construction and checkpoint publication
succeed, but group execution returns durable `storage_retry`, which the provider
surfaces as `graph_transaction_authority_unavailable`; zero graph effects are
committed. Reproduction is deterministic in the current coordinated dirty tree.

## Reproduction Contract

Run `PYTHONPATH=memorii .venv/bin/python -m pytest memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_root_composition.py -k 'builtin_native_graph and direct' -xq -p no:cacheprovider`.
Expected signal: accepted graph terminal/effect. Actual signal: assertion sees
`graph_transaction_authority_unavailable`. Current reproducibility: 1/1 latest run.

## Timeline

- 2026-09-04: typed planning authority and accepted fact construction added.
- 2026-09-05: exceptions through construction/checkpoint boundaries removed;
  coordinator result isolated as durable `storage_retry` during group commit.

## Hypothesis Ledger

| ID | Hypothesis | Supporting evidence | Contradicting evidence | Experiment | Result | Status |
| --- | --- | --- | --- | --- | --- | --- |
| H1 | Assembled group request violates an atomic-store validation invariant | atomic validation rejects reduction authority before CAS | none for the first mismatch | compare reduction and attempt snapshot identities | mismatch confirmed and corrected | confirmed root cause |
| H2 | Valid request reaches a genuine store operational retry | result reason is `storage_retry` | exact rejection was a deterministic `ValueError` before CAS | distinguish exception class/message and compare direct store call | disproved for the captured failure | disproved |
| H3 | Commit succeeds but checkpoint/result construction converts it to retry | none after direct store trace | atomic rejection occurs before primary record lookup/CAS | inspect commit ordering and state delta | ruled out for the captured failure | disproved |

## Experiment Log

### E1: Capture exact group-commit rejection

- Hypotheses: H1 versus H2/H3.
- Procedure: preserve the identical assembled request and expose the exact
  exception at the coordinator commit boundary in the focused test only.
- Expected: validator exception confirms H1; store-specific retry confirms H2;
  advanced graph revision confirms H3.
- Actual result: `validate_bootstrap_native_operation_reduction_v3` rejected
  `reduction.sealed_snapshot_digest != request.attempt.graph_snapshot_digest`
  with `native bootstrap graph reduction authority is substituted`, before
  primary-record lookup or CAS.
- Conclusion: H1 confirmed for the captured failure; H2 and H3 disproved.

### E2: Separate planning order from durable materialization order

- Hypotheses: a second pre-CAS record-order validation mismatch versus an
  operational store retry.
- Procedure: capture the exact commit exception after the snapshot correction,
  compare the target-plan ordering contract with the store's post-commit
  ordering check, and rerun the direct root.
- Expected: a deterministic ordering error confirms the contract mismatch.
- Actual result: the store rejected `bootstrap graph materialized records are
  not canonical`. The plan is required to order by kind/ID/digest, while final
  durable digests exist only after store-owned commit-coordinate injection.
- Conclusion: the atomic owner must canonically order its derived durable
  records; the caller cannot predict that order. The correction preserved plan
  ordering and sorted store-materialized records by kind/digest.

### E3: Reload the native group result from persisted JSON

- Hypotheses: post-effect checkpoint failure from incompatible wire decoding
  versus invalid native result construction.
- Procedure: capture the group checkpoint rejection and its nested codec cause.
- Expected: a strict transport/domain mismatch identifies the decoder; a
  construction error identifies the producer.
- Actual result: group CAS succeeded, then checkpoint decode rejected serialized
  `SourceModality` value `"assertion"` because nested strict validation required
  an in-memory enum instance.
- Conclusion: decode the persisted transaction-group result with `strict=False`
  while retaining all typed validators and digest verification, matching the
  existing compilation reload boundary.

## Root-Cause Statement

Three invariant mismatches formed the accepted-path failure chain. First, the
built-in compiler mixed two snapshot identities in one accepted group. The
native reduction was derived from the complete `SealedGraphStateSnapshot`, but
the member, evidence, plan, and attempt used the narrower graph-authority
snapshot digest. Atomic admission correctly rejected the substituted authority
before CAS; the coordinator translated that deterministic validation failure
to durable `storage_retry`, and the provider surfaced authority unavailable.
Second, the store required caller intent order to predict post-commit durable
digest order even though the store alone injects commit coordinates. Third,
checkpoint reload used strict in-memory enum validation on persisted JSON.
These propagated as pre-CAS retry, then post-effect retry, and finally provider
authority-unavailable. Earlier unresolved-path tests did not exercise accepted
reduction admission, durable materialization, or native result reload.

## Fix Strategy

The compiler now binds reductions, members, evidence, plan, and attempt to one
sealed-snapshot digest. The atomic owner sorts only the durable records it
constructs after commit-coordinate injection; plan ordering remains unchanged.
The native transaction-result wire decoder accepts JSON representations through
non-strict parsing and still executes every model validator and digest check.
Retry semantics remain unchanged and old mixed-authority bytes fail closed.

## Regression Proof

Before-fix evidence is the deterministic direct-root failure above. Required
after-fix evidence is the same node passing plus focused transaction and
recovery siblings, Ruff, and diff checks.

## Progress Log

- 2026-09-05: opened linked debugging operation after isolating the failure to
  group commit/CAS preparation. Next action is E1.
- 2026-09-05: confirmed the first causal mismatch at atomic reduction admission
  and corrected the compiler-wide sealed-snapshot identity. The direct root now
  proceeds beyond that captured rejection but still returns authority
  unavailable, so a second discriminating request/result probe is required.
- 2026-09-05: completed E2 and E3. The direct production-root reproducer now
  passes and persists exactly one group-commit primary record. No temporary
  diagnostics remain.
- 2026-09-05: four-root accepted-fact matrix, native member codec suite, and
  post-effect group-checkpoint/terminal-ack recovery siblings passed. Candidate
  frozen for independent closure review.
- 2026-09-05: readiness remediation was frozen in `candidate-manifest.json`;
  its seven file hashes and scoped diff hash were independently recomputed, the
  shared binding map resolved through the updated candidate lock, and the full
  focused proof was rerun against that exact candidate.
- 2026-09-05: the substantive review found no product-correctness defect, but
  confirmed deterministic verification gaps and a persisted terminal-authority
  closure gap. Checkpoint and recovery validation now resolve the exact
  repository-owned group request/reload pair; normal,
  substituted-snapshot, codec-tampering, and direct memory/JSONL recovery proofs
  were added and passed. The candidate was refrozen for final delta review.

## Evidence Log

- Direct-root run: 1 failed, 41 deselected; observed
  `graph_transaction_authority_unavailable` instead of accepted graph outcome.
- Normalization authority/grammar checks: 6 passed.
- Focused changed production modules: Ruff passed; `git diff --check` passed.
- Correctness challenge located the atomic validation call and confirmed no CAS
  or graph effect occurs for the captured mismatch.
- Direct-root after-fix command: 1 passed, 41 deselected in 31.73 seconds.
- Four-root accepted-fact command: 4 passed, 38 deselected in 106.90 seconds.
- Native atomic-member codec command: 4 passed in 5.28 seconds.
- Post-effect recovery selection: 2 passed, 18 deselected in 54.08 seconds.
- Ruff on the six affected production modules passed; `git diff --check`
  passed; repository remains a coordinated dirty tree at base revision
  `821b0bc7fd47ca0c55a18ccebb4b1628fa13689b`.
- Frozen-candidate rerun: four-root accepted-fact 4 passed, 38 deselected in
  134.82 seconds; native atomic-member codec 4 passed in 6.05 seconds;
  post-effect recovery 2 passed, 18 deselected in 63.02 seconds; Ruff and
  `git diff --check` passed.
- Candidate identity: scoped diff SHA-256
  `ffd409fe541a0609806ec40e8140cb497cb930aa2628c81ca28745243097b250`;
  binding-map SHA-256
  `c6b1899b85fa41ed7b167f647e22fedd6ccc6002429dba17ad9daa0d636f5f97`;
  resolved candidate-lock SHA-256
  `44bf4fff0453fb130dd79d3829dc01d212c5ebb5661b9c36544adda427470918`.
- Strengthened accepted-effect/root selection: 5 passed, 38 deselected in
  282.53 seconds on the final candidate, including all four public roots and
  the snapshot-substitution negative.
- Native transaction-result JSON/tamper proof passed; the complete native codec
  suite passed 5 tests in 84.67 seconds on the final candidate.
- Built-in direct recovery command: `PYTHONPATH=memorii .venv/bin/python -m
  pytest memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_post_effect_recovery.py
  -k '(builtin_terminal_ack_loss or builtin_recovery_preserves) and direct' -q
  -p no:cacheprovider`; collected `direct-False` and `direct-True` for both test
  families; exit 0; 4 passed, 17 deselected in 221.25 seconds. Exact accepted
  effect identity remained stable after memory recovery and JSONL reopen.
- Terminal reload with its repository-owned group primary hidden failed closed:
  1 passed, 20 deselected in 113.82 seconds.

## Decision Log

- Treat the failure as debugging, not additional design or operation-arm scope.
- Preserve durable retry semantics until the exact commit rejection is known.

## Review Log

The first closure cohort unanimously identified one `Not applicable / blocks_approval /
governance-evidence` readiness finding: the coordinated dirty tree lacked a
scoped immutable candidate identity and the shared production-entrypoint map
lacked this exact accepted-fact commit chain. The finding is confirmed and
remediated by `candidate-manifest.json`, the `accepted_fact_group_commit` binding
entry, and the updated binding-map lock. No implementation finding was issued.

The substantive cohort classified the terminal request-closure issue as `Not
applicable / changes_required / persistence-integrity` and four missing proof
families as `Not applicable / changes_required / verification`. These findings
were confirmed. The store now binds the persisted terminal to the
repository-owned request and reload pair, and the focused tests now prove
accepted durable effects,
pre-CAS snapshot rejection with zero effects, JSON round-trip/tamper rejection,
and built-in memory/JSONL post-effect recovery. Correctness review otherwise
approved the bounded slice and independently ran the eight-case built-in
lease-reclaim matrix (8 passed, 12 deselected in 394.25 seconds).

The final refrozen cohort verified candidate
`ffd409fe541a0609806ec40e8140cb497cb930aa2628c81ca28745243097b250`.
Specification, correctness, and test reviewers reported no remaining findings;
the test review's last schema observation was reclassified as unsupported after
confirming the payload mutation adds a genuinely unknown field.

## Blockers And Limits

Experiment budget: six discriminating experiments. Used: three. No blocker
remains for this bounded debugging operation.

## Assumptions And Open Questions

- Verified: typed construction and checkpoint publication complete without exception.
- Verified: the failure was the three-part request/store/reload invariant chain
  recorded in the root-cause statement.
- Verified: all four roots and focused post-effect recovery pass.
- Unresolved: none within this debugging scope.
- External decisions: none.

## Next Action

Resume the parent implementation WorkPlan's direct production-root group-CAS
race proof.

## Outcome And Retrospective

Complete. The accepted entity-object fact now commits one canonical graph/event
effect through all four ordinary roots, substituted authority fails before any
effect, and checkpoint/terminal recovery proves the repository-owned request
and reload closure without duplicate effects. This closes only the linked
storage-retry debugging slice; it does not close M3.1 or M4.

## Revision-Bound Closure Record

```yaml
base_revision: 821b0bc7fd47ca0c55a18ccebb4b1628fa13689b
reviewed_revision: scoped-candidate:ffd409fe541a0609806ec40e8140cb497cb930aa2628c81ca28745243097b250
tested_revision: scoped-candidate:ffd409fe541a0609806ec40e8140cb497cb930aa2628c81ca28745243097b250
tested_tree_digest: 56c1a4384b0c7b77ea553b1632fa113293b28f0646136303d1e800094916f08f
tree_state: coordinated_dirty_tree_scoped_by_candidate_manifest
changed_surface_inventory_complete: true
scope_delta_resolved: true
authority_chains_complete: true
required_local_jobs:
  - accepted_fact_public_roots_and_snapshot_rejection
  - native_transaction_result_codec
  - direct_memory_jsonl_post_effect_recovery
  - absent_group_primary_terminal_reload_rejection
  - focused_ruff
  - scoped_diff_check
  - identity_hygiene
passed_local_jobs:
  - accepted_fact_public_roots_and_snapshot_rejection
  - native_transaction_result_codec
  - direct_memory_jsonl_post_effect_recovery
  - absent_group_primary_terminal_reload_rejection
  - focused_ruff
  - scoped_diff_check
  - identity_hygiene
known_local_failures: []
failure_exclusions: []
workflow_identities: []
ci_event: "not_applicable: bounded local debugging slice; no CI dispatch requested"
ci_executed_sha: "not_applicable: no CI dispatch"
ci_executed_ref: "not_applicable: no CI dispatch"
remaining_validated_p1_p2: []
remaining_blocks_approval: []
remaining_changes_required: []
local_ci_parity: "diagnostic_only: focused contract families and static gates passed; no whole-repository CI claim"
acceptance_gate_inventory:
  - "four public roots persist one accepted graph/event effect"
  - "substituted snapshot authority produces zero effects"
  - "native transaction result survives JSON round trip and rejects tampering"
  - "memory and JSONL post-effect recovery preserve exact effect identity"
  - "terminal reload rejects an absent repository-owned group primary"
github_run_urls: []
pr_head_sha: "not_applicable: coordinated dirty tree"
pr_base_sha: "not_applicable: no PR review"
merge_base_sha: 821b0bc7fd47ca0c55a18ccebb4b1628fa13689b
required_checks_green: "not_applicable: no PR or CI-required check set; all required local jobs passed"
```
