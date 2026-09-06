# M4 Final Deterministic Gate Regressions

- Work ID: m4_final_deterministic_gate_regressions
- Work type: debugging
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-08-04
- Last updated: 2026-08-04
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/testing.plan.md`; `docs/work/semantic_ingestion/debug-temporal-projection-interval.plan.md`
- Canonical inputs: `docs/IMPLEMENTATION_RULES.md`; current memory-plane and semantic-generation contracts; `.github/workflows/pr-gates.yml`
- Expected outputs: causal classification, narrow production/test correction, focused family proof, and independent delta review

## Objective

Close the two deterministic failures exposed only by the final broad unit
matrix without weakening the M4 replay, generation-closure, or architecture
contracts.

## Completion Contract

Complete only when the exact architecture guard and all semantic-generation
transaction nodes pass; required terminal generation members remain fail
closed; the public/private module boundary is canonical; affected focused
families and static checks pass; and targeted correctness/test review has no
remaining required finding.

## Scope

Included: the cross-module checkpoint-purpose ownership violation and stale
semantic-generation transaction fixtures exposed by the final deterministic
unit shards.

Excluded: production terminal-closure semantics, artifact-index relaxation,
retained-terminal compatibility, broad-shard reruns, and unrelated M4 behavior.

Deferred: GitHub-hosted clean-head CI evidence until the parent implementation
has a reviewed revision.

## Constraints And Invariants

- Storage owns checkpoint signing material and its purpose identity.
- The public memory-plane service may name the protected purpose only through
  a public storage-owned symbol; it may never retrieve the signing bytes.
- Terminal generations retain exactly one canonical `artifact_index` and must
  equal the checkpoint-retained terminal and artifact closure byte-for-byte.
- Negative fixtures must start from a canonical request and mutate only the
  precondition under test.
- Test helpers may not replace required canonical generation members with
  placeholder payloads.

## Identity And Coordinate Hygiene

| Surface | Identity | Class | Owner or meaning | Disposition | Proof |
| ------- | -------- | ----- | ---------------- | ----------- | ----- |
| storage constant | `SEMANTIC_CHECKPOINT_SECRET_PURPOSE` | behavioral | storage-owned protected-secret purpose | retain as public storage symbol | architecture import guard and secret-access test |
| test | `test_finalization_requires_exact_singleton_group_result_closure` | behavioral | singleton persisted group-result closure | replace retired multigroup-order scenario | exact generation file |
| fixture helpers | `_committed_terminal_group_request`, `_noncommitting_terminal_group_request` | behavioral | canonical terminal generation builders | retain | required-member sibling tests |

## Change Impact And Verification Closure

| Path | Surface | Owner | Authority chain | Required gates | Status |
| ---- | ------- | ----- | --------------- | -------------- | ------ |
| `memorii/memorii/core/memory_plane/store.py` | product architecture/security | storage | protected purpose -> backend guard -> opaque signer | architecture guard, secret-access test, Pyright | candidate green |
| `memorii/memorii/core/memory_plane/service.py` | product architecture/security | service | public storage symbol -> public rejection -> private authority claim | architecture guard, secret-access test, Pyright | candidate green |
| `memorii/tests/unit/core/semantic_ingestion/test_semantic_generation_transactions.py` | test fixtures | this debug plan | retained checkpoint -> canonical group members -> closure/finalization assertions | full 22-node file, Ruff | candidate green |
| `memorii/tests/unit/core/benchmark/test_memory_evolution_architecture.py` | architecture test | this debug plan | storage public owner -> service import -> literal-copy rejection | exact AST guard | candidate green |

The production closure validator, artifact index encoding, and retained
terminal equality are unchanged by this operation.

## Sources Of Truth

`docs/IMPLEMENTATION_RULES.md` governs package/private boundaries. The current
memory-plane storage and service contracts govern secret ownership. The
terminal persistence member builders and atomic-store closure validator govern
canonical generation bytes. The exact failing tests and final workflow shard
commands provide observed evidence.

## Current State

- The architecture candidate now defines one public storage-owned checkpoint
  purpose and the service imports that public symbol. The unnecessary private
  alias was removed; storage uses the public owner internally.
- Before fixture remediation, the current candidate reproduced 10 failures and
  12 passes in the 22-node generation file. Failures separated into retained
  accepted/unresolved mismatch, noncanonical post-revision placeholders,
  pre-construction stale revision injection, and removed required members.
- After remediation, all 22 generation nodes pass in 35.60 seconds.
- The exact architecture/secret/retained-terminal/artifact-index sibling batch
  passes 24 nodes in 156.98 seconds.
- The review-remediation AST guard requires the service to import the public
  storage-owned purpose and forbids copying the protected-purpose literal; the
  exact architecture and secret-access batch passes 4/4.

## Assumptions And Open Questions

- Verified: no product-semantic change is required.
- Verified: canonical helpers include `artifact_index` and retained closure
  members and current sibling tests enforce both invariants.
- Unresolved questions: none.
- External decisions: none.

## Incident Or Symptom

Final Unit Test Shard 1 passed 869 nodes and failed only
`test_source_does_not_import_cross_module_private_symbols`: public
`memory_plane/service.py` imports private
`_SEMANTIC_CHECKPOINT_SECRET_PURPOSE` from `memory_plane/store.py`.

Final Unit Test Shard 2 passed 1,266 nodes, skipped one, and failed 11 nodes in
`test_semantic_generation_transactions.py`. Every failure reaches the current
terminal-group closure validator and rejects a fixture generation that omits
the required `artifact_index` member.

## Hypothesis Ledger

| ID | Hypothesis | Experiment | Status |
| -- | ---------- | ---------- | ------ |
| H1 | the checkpoint-purpose value has the correct semantics but the wrong private ownership boundary | map all imports and canonical public owner | confirmed: storage owns the value; service must consume a public storage symbol rather than import a private name |
| H2 | the generation failures encode retired fixture construction rather than a supported compatibility contract | compare fixture builders with current required-member, retained-terminal, and revision contracts | confirmed: committed setup retained an unresolved terminal, placeholder revisions bypass canonical derivation, invalidity was injected before canonical construction, and the old multi-group scenario replaced required members |
| H3 | production accidentally made artifact-index or retained-terminal equality mandatory where a valid terminal generation may omit it | trace governing replay/artifact closure and current integration proofs | rejected: canonical committed and noncommitting groups pass; artifact index and exact retained-terminal equality are required fail-closed closure |

## Experiments

| Experiment | Hypotheses | Procedure and prediction | Actual result | Conclusion |
| ---------- | ---------- | ------------------------ | ------------- | ---------- |
| exact boundary reproduction | H1 | run architecture import guard plus public secret-access nodes; public symbol candidate should pass without exposing bytes | 3 passed | boundary candidate preserves security and fixes cross-module import |
| exact generation reproduction | H2/H3 | run all 22 transaction nodes; stale fixtures fail at current closure while canonical fixtures retain strict checks | 10 failed, 12 passed | fixture drift, not production relaxation, is causal |
| canonical fixture remediation | H2/H3 | use terminal persistence builders, derive revisions, then mutate only tested preconditions | 22 passed | canonical migration fixes the family without weakening closure |
| invariant siblings | H3 | run retained-checkpoint substitution, artifact-index mutation, committed/noncommitting success, and secret-access siblings | 24 passed | required members and security remain fail closed |

## Delegation And Cost Ledger

| Phase | Task | Role/tier | Ownership | Status |
| ----- | ---- | --------- | --------- | ------ |
| isolate | map private constant ownership | Spark error-detective | read-only | complete; agent exceeded read-only scope with a narrow candidate edit, pending writer reconciliation |
| isolate | classify generation fixture versus product contract | Spark error-detective/debugger | read-only | complete |
| fix | apply one bounded correction after cause confirmation | worker, Terra-class | sole writer | complete |
| review | targeted correctness and test delta | Terra-class reviewers | read-only | active |

## Progress Log

- 2026-08-04: Reproduced the reconciled architecture candidate at 3/3 green and
  the generation file at 10 failed/12 passed. Recorded fixture-contract causal
  signatures; rejected production relaxation.
- 2026-08-04: Removed the unnecessary private checkpoint-purpose alias and
  migrated generation fixtures to canonical checkpoint/group construction.
- 2026-08-04: Full generation file passed 22/22; focused invariant siblings
  passed 24/24. Advanced candidate to targeted delta review.

## Evidence Log

- Architecture and secret access:
  `.venv/bin/python -m pytest -W error ...test_source_does_not_import_cross_module_private_symbols ...test_checkpoint_secret_cannot_be_retrieved_through_public_storage_api -p no:cacheprovider -q`;
  3 passed in 4.79 seconds before alias cleanup and included again in the green
  24-node post-fix sibling batch.
- Reproducer: full generation file, 10 failed/12 passed in 25.26 seconds.
- Fix proof: full generation file, 22 passed in 35.60 seconds.
- Sibling proof: architecture, public secret access, missing retained terminal,
  valid noncommitting, retained-terminal substitution, artifact-index mutation,
  and valid committed group; 24 passed in 156.98 seconds.
- Static proof: Ruff reports no findings; canonical repository Pyright with the
  active `.venv` interpreter reports 0 errors, 0 warnings, and 0 information;
  scoped diff check is clean; private checkpoint-purpose alias search is empty.

## Decision Log

- 2026-08-04: Keep one public storage-owned purpose symbol and remove the
  redundant private alias. This preserves behavior while satisfying the module
  boundary.
- 2026-08-04: Migrate tests to canonical terminal persistence builders; do not
  modify atomic-store closure validation or compatibility behavior.
- 2026-08-04: Replace the obsolete multi-group ordering fixture with the
  supported singleton group-result mismatch/pass closure proof.

## Review Log

- Correctness delta review: no findings; confirmed production closure and
  security behavior unchanged.
- Test delta finding 1: `Not applicable / changes_required / verification` on
  missing proof that the service consumes the public storage-owned purpose.
  Confirmed and remediated with an AST import/literal-copy guard; exact batch
  passes 4/4.
- Test delta finding 2: `Not applicable / changes_required / verification` on
  an unchanged authorization-rotation sibling's hypothetical incomplete
  zero-effect assertion. Classified unsupported for this bounded debug authority
  chain: no changed node or reproduced defect was identified, and remediation
  would expand scope beyond the private-import and stale-fixture causes.
- Test remediation delta: finding 1 is already resolved; finding 2 remains
  unsupported; no required in-scope test finding remains.

## Next Action

Return the completed debugging evidence to the parent M4 implementation
WorkPlan; the parent owns final branch/CI closure.

## Blockers And Limits

Budget: two discriminating maps, one correction batch, focused family proof,
and one targeted review round. No external blocker.

## Outcome And Retrospective

Both failures were deterministic contract-drift signals. The architecture fix
uses one public storage-owned checkpoint purpose without exposing signing
bytes, and an executable AST guard prevents either private import or literal
copying in the service. The generation family now uses canonical retained
terminal, artifact-index, revision, event, and group-result construction; only
the intended invalid precondition is mutated. All 22 generation nodes and 24
focused security/closure siblings pass, static checks are green, and both
targeted delta reviews have no remaining required finding. Failed broad-shard
timing artifacts remain diagnostic only and cannot enter a timing inventory
because their `exit_status` is nonzero.

## Revision-Bound Closure Record

```yaml
base_revision: 2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93
reviewed_revision: working-tree@2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93
tested_revision: working-tree@2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93
tested_tree_digest: 4c8257e339a61f56062d4922c3459ae8ff936ace1242e04c3db62728062a6de4
tree_state: dirty shared M4 worktree; digest covers this debug plan's four changed code/test surfaces
changed_surface_inventory_complete: true for bounded debug scope
scope_delta_resolved: true
authority_chains_complete: true
required_local_jobs:
  - exact generation transaction file
  - exact architecture and checkpoint-secret guards
  - retained-terminal and artifact-index sibling closure
  - Ruff
  - repository Pyright with active interpreter
  - scoped diff check
passed_local_jobs:
  - exact generation transaction file: 22 passed in 36.69s
  - focused closure/security sibling batch: 24 passed in 156.98s
  - architecture ownership remediation batch: 4 passed in 4.67s
  - Ruff: passed
  - Pyright: 0 errors, 0 warnings, 0 information
  - scoped diff check: passed
known_local_failures: []
failure_exclusions: []
workflow_identities:
  - Unit Tests
ci_event: not_run; parent implementation owns committed-head CI
ci_executed_sha: null
ci_executed_ref: null
remaining_validated_p1_p2: []
remaining_blocks_approval: []
remaining_changes_required: []
local_ci_parity: focused deterministic commands only; broad shards intentionally not rerun
acceptance_gate_inventory:
  - exact generation transaction file
  - architecture/private-boundary guard
  - checkpoint-secret access guard
  - retained-terminal equality siblings
  - artifact-index canonicality siblings
github_run_urls: []
pr_head_sha: null
pr_base_sha: null
merge_base_sha: 2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93
required_checks_green: not_applicable; parent implementation owns GitHub required checks
```
