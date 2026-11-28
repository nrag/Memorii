# Review and recall an approved learned catalog

- Order: 2. Status: queued. Baseline: `80fc5852`; design and candidate head pending.
- Requirements: partial OLE-02/04/05/06/07/10/13 and selected learned OCI behavior.
- Dependencies: packaged discovery, plus approved exact-parent, owner-review and recovery design.

## Execution boundary

Use `LearnedRelationRuntime`, the selected-catalog authority and bundle
locator, the host callbacks in `hermes_factory.py`, and the protected
read workflow. Fix the reproduced evaluation publication recovery gap
before exposing broader owner maintenance. Establish transaction ownership
for current grants, durable selection and refresh. Freeze the proposal
state machine, exact parent representation, owner evidence projection,
and explicit rebase protocol. Verify prepublication interruption,
interrupted publication, evaluator unavailable/retry, and terminal retry
as distinct cases. Record recovery via the linked debugging design if the
reproduced defect needs a separate investigation.

Represent the exact immutable packaged parent and validate the whole
effective catalog. Old overlays without sufficient evidence are unavailable
until an authorized, validated rebase. No silent backfill, fact rewrite or
read-triggered repair. Rollback selects a previously verified same-scope
ancestor using pointer CAS. Retain the owner and version on existing facts.
Freeze any persisted schema compatibility policy before implementation.

## Acceptance and verification

- Owner can view the proposed declaration, verified evidence references,
  paired parent/candidate outcomes, abstentions, vetoes, parent/version
  status and recorded decision. Rejection is terminal across reopen.
  Deny unauthorized decisions with no mutation.
- Prove live approve, activate and select-prior grants on each exposed host
  path. Withdrawing authority before mutation leaves state unchanged.
  After valid activation or rollback, a failed refresh reports the durable
  result and pending refresh through scoped status. Verify CAS and retry.
- Inspect and recall an authorized `mentors` fact through both read
  bindings after restart. Verify ordinary parent reads, peer-agent and
  foreign-account denial, missing or ambiguous parent, same-scope rollback,
  retained historical meaning and revoked-source replay skip. Exercise
  seed-bound versus genuinely unbound readers separately, including malformed
  and out-of-scope records on each path.
- Rebase a provable early overlay through an explicit authorized selection.
  Missing or ambiguous parent evidence or withdrawn authority leaves the
  pointer and historical records unchanged.
- Exercise recovery on reopened durable storage. The baseline probe proves
  decoder disagreement on an in-memory store. It cannot close restart proof.

```sh
python -W error -m pytest -q -p no:cacheprovider \
  tests/unit/core/semantic_ingestion/test_learned_relation.py \
  tests/unit/core/test_scoped_context_activation.py \
  tests/unit/integrations/test_hermes_memory_provider_bridge.py \
  tests/integration/test_ingestion_time_seal_minting.py \
  tests/integration/test_scoped_context_production_binding.py
```

Close with installed restart/replay/rollback evidence, scoped decision and
recovery review, applicable gates and no open in-scope P1/P2. This packet
does not broaden the edit grammar or propose a new ontology.
