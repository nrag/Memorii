# Hermes Invalid Candidate Terminalization Debug

- Work ID: `hermes-invalid-candidate-terminalization-debug`
- Work type: debugging
- Delivery fidelity: Level 2 early real-world testing
- Status: complete
- Coordinator: `/root/invalid_candidate_terminal_fix`
- Created: 2026-09-24
- Last updated: 2026-09-24
- Parent WorkPlan: `docs/work/hermes-conversation-memory-trial/implementation.plan.md`
- Related WorkPlans: `docs/work/hermes-level2-pr/pr-review.plan.md`
- Canonical inputs: `docs/design/memorii_spec.md`, `docs/design/memorii_storage_details.md`, `docs/design/event_model.md`, `docs/design/hermes_conversation_memory_trial.md`, `memorii/memorii/core/provider/ingestion.py`, `memorii/memorii/core/semantic_ingestion/source_normalization_execution.py`
- Expected outputs: durable evidence-only terminalization for validation-rejected Hermes proposal candidates, a focused installed-path regression, and deterministic verification evidence.

## Expected And Observed Behavior

The Level 2 Hermes path must retain an admitted completed turn, reject unknown,
ungrounded, or ambiguous model candidates without creating graph, retrieval, or
runtime-context state, and publish one durable evidence-only terminal. A later
valid completed turn must then commit normally. This follows the trial design's
HCM-03 and HCM-05 atomic terminal/recovery boundary.

`memorii/tests/integration/test_hermes_bootstrap_v3_product.py::test_installed_hermes_rejected_candidates_do_not_commit_or_block_a_later_valid_turn`
currently fails deterministically. The rejected proposal is converted into
`SourceNormalizationNonCommit`, which the coordinator maps to
`source_alignment_authority_unavailable`; the completed-turn worker treats that
as unresolved and recovery remains pending. Impact: ordinary invalid model output
can block later conversation ingestion in a Level 2 Hermes installation.

## Hypotheses And Experiments

| ID | Hypothesis | Supporting evidence | Discriminating experiment | Status |
| --- | --- | --- | --- | --- |
| H1 | Candidate validation rejection is mistakenly classified as a missing source-alignment authority, so recovery retries instead of terminalizing. | The normalizer catches `ValueError` and returns `publication_conflict`; coordinator maps every `SourceNormalizationNonCommit` to `source_alignment_authority_unavailable`; reconciliation marks that code retryable. | Run the exact product regression and inspect the exception/call chain. | confirmed |
| H2 | The rejected candidate can be converted into an empty valid V3 normalization result and finalized by the existing graph writer. | The graph terminal path already supports empty abstained normalized proposals. | Inspect the source-normalization request/result contracts to determine whether an empty accepted result can faithfully retain rejected-candidate evidence. | confirmed |
| H3 | The generic semantic terminal persistence owner can safely terminalize the claimed V3 operation. | Reconciliation normally persists non-graph terminals. | Inspect its fence/control assumptions and run a minimal isolated proof if H1 shows graph terminalization unavailable. | rejected |

## Experiments

| ID | Hypotheses | Prediction | Result | Conclusion |
| --- | --- | --- | --- | --- |
| E1 | H1/H2/H3 | Exact installed-path regression reaches the mapped reason after a validation `ValueError`. | The test failed in 102.92s: the completed worker received `source_alignment_authority_unavailable`, then recovery remained pending. The model-output adapter converts rejected responses to `None`; the proposal producer treats `None` as unavailable, and the execution owner reports a retryable noncommit. | H1 confirmed. |
| E2 | H2/H3 | Contract/owner inspection identifies the one terminal owner able to close a live V3 recovery claim without bypassing validation. | `BootstrapNormalizedProposalV3` explicitly supports an empty `abstained` proposal. The existing installed Hermes abstention test proves that this valid closure reaches the graph's evidence-only terminal. Generic terminal persistence cannot close the already-claimed V3 graph operation, so H3 is rejected. | H2 confirmed: distinguish received-but-rejected model output from no transport response at the adapter boundary and retain the existing V3 abstention terminal path. |

## Changed Surface And Authority Chain

Production owner: `ProjectAssertionProviderProposalAdapter.from_response`. It converts received model bytes that fail its closed schema/source-grounding checks into an empty `ProviderSemanticProposal(abstained=True)`. The existing V3 normalizer, graph writer, and recovery state machine then own terminal publication. The Hermes bridge remains a caller only. Regression owners: `memorii/tests/unit/core/semantic_ingestion/test_project_assertions.py` and `memorii/tests/integration/test_hermes_bootstrap_v3_product.py`.

## Root Cause And Fix

The adapter used one `None` result for two different states: a transport that
did not yield a response and model bytes that failed closed validation. The V3
proposal producer correctly treats `None` as unavailable and retries; after the
retries, the execution owner produces a retryable source-alignment noncommit.
That is correct for unavailable transport but wrong for a received invalid
candidate. The fix preserves `None` for egress/credential/transport failure and
maps received invalid bytes to an explicit empty abstention. No invalid candidate
is normalized into a claim; the existing Bootstrap V3 abstention closure writes
only its durable evidence-only terminal.

## Completion Contract

- The exact regression passes for unknown, ungrounded, and ambiguous candidates followed by one valid fact.
- Each rejected candidate creates one durable evidence-only terminal and leaves graph/retrieval/projection state unchanged.
- A later valid turn fully commits and is recalled.
- Validation remains fail-closed; no rejected candidate becomes semantic truth.
- Focused test, Ruff, and affected type check pass.

## Evidence

- Original installed-path reproduction: `1 failed in 102.92s`. Its rejected
  candidate reached `source_alignment_authority_unavailable`, and recovery
  remained pending.
- Focused adapter and profile tests:
  `PYTHONPATH=memorii /Users/nandaraghunathan/Code/Memorii/Memorii/.venv/bin/python -m pytest memorii/tests/unit/core/semantic_ingestion/test_project_assertions.py memorii/tests/unit/core/semantic_ingestion/test_project_assertions_profile.py -q -p no:cacheprovider`
  passed: `9 passed in 18.85s`.
- Exact installed Hermes regression:
  `PYTHONPATH=memorii /Users/nandaraghunathan/Code/Memorii/Memorii/.venv/bin/python -m pytest memorii/tests/integration/test_hermes_bootstrap_v3_product.py::test_installed_hermes_rejected_candidates_do_not_commit_or_block_a_later_valid_turn -q -p no:cacheprovider`
  passed: `1 passed in 835.55s`. It covers unknown predicate, ungrounded
  quote, and ambiguous/repeated candidate responses, followed by a valid
  committed and recalled assertion.
- Ruff:
  `PYTHONPATH=memorii /Users/nandaraghunathan/Code/Memorii/Memorii/.venv/bin/python -m ruff check --no-cache memorii/memorii/core/semantic_ingestion/project_assertions.py memorii/tests/unit/core/semantic_ingestion/test_project_assertions.py memorii/tests/integration/test_hermes_bootstrap_v3_product.py`
  passed: `All checks passed!`.
- Affected type check:
  `/Users/nandaraghunathan/Code/Memorii/Memorii/.venv/bin/pyright --pythonpath /Users/nandaraghunathan/Code/Memorii/Memorii/.venv/bin/python memorii/core/semantic_ingestion/project_assertions.py`
  passed: `0 errors, 0 warnings, 0 informations`.

## Completion And Residual Scope

The Level 2 invalid project-assertion candidate path is complete. Received
invalid provider output is fail-closed into a V3 abstention and therefore
cannot create a semantic claim; absent transport output remains retryable. The
profile fingerprints were regenerated because the canonical adapter source is
verified by the installed Bootstrap V3 profile. Broader provider-output
diagnostics and malformed-output classifications outside this profile remain
separate future work and are not required for the tested Hermes path.

## Next Action

Hand this completed bounded debugging slice to the parent Level 2 PR work for
review and merge preparation.
