# Clarification Recovery Verification Under Corrupt Primary Replay

- Work ID: clarification_recovery_corruption
- Work type: debugging
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-08-03
- Last updated: 2026-08-04
- Parent WorkPlan: `docs/work/semantic_ingestion/debug-semantic-control-regressions.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/implementation.plan.md`; `docs/work/semantic_ingestion/testing.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md`; `docs/design/event_model.md`; current clarification recovery and replay-integrity implementation
- Expected outputs: causal isolation, smallest fail-closed recovery fix, corruption/reopen family proof, and targeted independent review

## Objective

Allow retained clarification recovery authority to be verified and recovered
without re-entering a known-corrupt live primary replay path, while preserving
strict corruption detection and preventing clean-recovery authority from
becoming self-authorizing.

## Completion Contract

Complete only when the exact filesystem reopen reproducer fails before and
passes after the fix, corrupt ordinary replay remains frozen/non-disclosable,
clarification recovery verifies only from immutable same-generation authority,
substitution/tamper/missing-authority cases fail closed, reopen/race behavior is
deterministic, and independent targeted review has no required finding.

## Scope

Included: `_accepted_clarification_recovery_authorities`, clarification-pair
verification, graph-delta/identity enrichment dependencies during recovery,
retained authority bindings, corrupt-primary reopen, and focused siblings.

Excluded: writer admission, clarification outcome derivation, CI topology and
timings, generic corruption policy, and unrelated replay recovery.

## Incident Or Symptom

The fresh isolated ordinary-plus-clarification filesystem reopen test fails
deterministically. The test intentionally corrupts the ordinary primary event
batch. Clean recovery loads the retained clarification authority but then calls
`_decode_conflict_clarification_pair`; verification invokes
`enrich_identity_graph_delta`, which reads live `semantic_replay_state()` and
encounters the corrupt ordinary batch. The retained authority therefore cannot
be verified and recovery reports `clean_recovery_authority_invalid`.

## Hypothesis Ledger

| ID | Hypothesis | Discriminating experiment | Status |
| -- | ---------- | ------------------------- | ------ |
| H1 | recovery verification incorrectly depends on live replay instead of retained same-generation inputs | trace every read from retained authority load to replay failure | supported |
| H2 | retained clarification authority lacks sufficient immutable bytes to verify independently | inventory stored pair/event/graph/evidence digests and attempt offline verification | weakened; the retained transaction, receipt, canonical event batch, replay aggregate, signed checkpoint, and generation members are sufficient when cross-bound |
| H3 | corruption injection also damages clarification recovery authority | compare exact corrupted record ID with retained clarification records | weakened; corruption targets ordinary batch |
| H4 | clean recovery can reuse the active aggregate's member bindings safely | corrupt the active ordinary batch and reconstruct from retained generation manifests only | rejected; using active bindings makes the clean generation self-authorizing and re-enters corrupt authority |

## Reproduction Contract

Run the exact ordinary-plus-clarification filesystem reopen node alone on a
fresh temporary path. Expected: ordinary corruption is detected/frozen and the
retained clarification recovery path can be independently verified. Actual:
deterministic `clean_recovery_authority_invalid` after live replay re-entry.

## Delegation And Cost Ledger

| Phase | Task | Role/tier | Ownership | Status |
| ----- | ---- | --------- | --------- | ------ |
| map | trace retained bytes and live dependency | code-mapper, Spark-class | read-only | complete |
| challenge | verify proposed authority boundary | correctness_reviewer, Terra-class | read-only | complete |
| fix | remove live replay dependency using immutable bound inputs | worker, Terra-class | sole writer | complete |
| review | targeted spec/correctness/test closure | Terra-class reviewers | read-only | complete |

## Next Action

Resume the linked testing WorkPlan's invalidated 566-node timing capture on the
closed recovery revision.

## Blockers And Limits

Budget: two discriminating experiments, one fix batch, one targeted remediation
round. No external blocker.

## Outcome And Retrospective

The second causal defect was confirmed: clarification authority verification
called live identity enrichment, clean preparation copied member bindings from
the active aggregate, validation reconstructed from those self-supplied
bindings, and activation re-read live replay authority. The candidate now:

* verifies accepted clarification transactions, receipts, typed canonical
  terminal/graph-delta bytes, batch digests, retained replay aggregate, and its
  signed checkpoint without live enrichment;
* derives the complete observation/progress/artifact binding closure from
  independently validated generation manifests and generation members;
* replays all retained event batches from genesis and creates a new aggregate
  from genesis rather than advancing the corrupt active aggregate;
* validates prepared plans against the independently re-derived exact binding
  closure and retained-only authority record snapshot;
* performs activation with raw record-digest CAS but does not decode or trust
  active replay state/aggregate, and no longer calls live replay authority after
  activation.

Evidence: the exact fresh ordinary-plus-clarification corrupt-primary reopen
reproducer passes (`1 passed, 147 deselected`) after the fix. A guard in that
reproducer makes both live identity enrichment and active replay authority
raise if clean recovery invokes them. Focused mutation-family and independent
review evidence remain before closure. The adversarial retained-authority
matrix also passes: five pre-existing bound-record mutations; a fully rebound
transaction/receipt/authority whose typed graph delta disagrees with the
retained event batch; omitted and swapped replay-member bindings with aggregate
and authority hashes recomputed; and a checkpoint revision mutation with
checkpoint, bundle, aggregate, payload, and binding hashes recomputed but an
unforgeable stale signature. Focused restart and provider siblings pass, Ruff
passes, Pyright reports `0 errors, 0 warnings`, and `git diff --check` passes.

Closure review found one confirmed P2 idempotence defect: activation returned
solely because the status row said `activated`, and restart reconciliation
searched only for `prepared` rows. A forged status could therefore suppress
both activation and validation while corrupt active mirrors remained. The
remediation treats both statuses as restart proof obligations. An idempotent
`activated` result now revalidates the exact request, plan, retained authority,
member closure, checkpoint, and clean digest, then requires every active event
record plus the replay-state and replay-aggregate records to equal the prepared
clean generation. The forged-status filesystem/reopen regression passes and
proves reconciliation fails, the lifecycle refreezes, and corrupt events remain
non-disclosable. The normal activation retry also passes and returns the
identical replay authority.

Final targeted specification, correctness, and test review reports no remaining
required finding. The exact guarded corrupt-primary reopen, retained-authority
mutation family, rehashed aggregate/checkpoint attacks, clean restart, forged
activated-status reopen/refreeze, normal activation retry, and zero-learned-
call provider siblings pass. Ruff, configured Pyright, and `git diff --check`
are clean.

- `remaining_validated_p1_p2: []`
- `remaining_blocks_approval: []`
- `remaining_changes_required: []`
