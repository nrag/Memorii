# Create, evaluate and select a grounded relation

- Order: 4. Status: queued. Baseline: `80fc5852`; design and candidate head pending.
- Requirements: partial OLE-01/02/03/04/05/06/08/11/12/13/14.
- Dependencies: scoped recurrent evidence and exact-parent protected lifecycle. Freeze the witness, proposal transport, declaration grammar and evaluation corpus.

## Execution boundary

Use the existing recurrence admission seam in `LearnedRelationCandidateService`
and the scoped owner path. Generalize the closed typed relation declaration
over already registered endpoint, validator, writer and reader capabilities.
Both provider-neutral grounded synthesis and authenticated manual evidence
enter the same core validator. Freeze scope, collision/alias handling,
version/identity codecs and exact-parent compare-and-select. Use disjoint
withheld cases in the paired evaluator, preserve existing history, and
dispatch replay through source preparation and the ordinary semantic writer.
Record any schema version/decoder changes as part of the compatibility
design. Disabling future synthesis must leave approved catalog and facts
usable. No new domain or codec, automatic promotion or cross-scope edit.

## Acceptance and verification

- Exercise a relation genuinely different from `mentors(Person, Person)`
  through endpoint shape or policy and absent from the packaged catalog.
  Generate it from verified retained spans through the installed observer
  and recurrence path. Verify duplicate idempotence, valid typed
  declarations, and deny unknown capabilities, aliases/type collisions,
  conflicting evidence, wrong scope and stale parent without selection.
- With observer and model disabled, submit an owner-authored structured
  candidate. Check the same validator and paired evaluation, zero
  preapproval fact/version changes, then a distinct authorized selection.
  A standalone fact-write port is a separately tracked journey.
- For both creation paths, show the authorized owner candidate-specific
  withheld positives, mandatory regressions, scope and abstention outcomes
  for the parent and candidate, plus any vetoes, before explicit selection.
  An unavailable evaluator does not activate. After selection,
  retry/reopen/replay yields one ordinary authorized change, denied/revoked
  sources yield none, and no-key inspection and recall plus rollback
  preserve historical meaning.

```sh
python -W error -m pytest -q -p no:cacheprovider \
  tests/unit/core/semantic_ingestion/test_learned_relation.py \
  tests/unit/core/semantic_ingestion/test_coverage_recurrence.py \
  tests/unit/integrations/test_hermes_memory_provider_bridge.py \
  tests/integration/test_scoped_context_production_binding.py
```

Add feature-local equivalence tests for direct declaration, alias/overlap,
ordered typed roles, duplicate/retry and ordinary replay/recall. Close
with both creation paths, candidate-specific evaluation and current gates
and targeted review. Record operational behavior separately from unit fixtures.
