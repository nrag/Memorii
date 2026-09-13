# Recovery Index Validation

- Work ID: recovery-index-validation
- Work type: debugging
- Status: complete bounded repair
- Coordinator: root
- Created: 2026-09-07
- Last updated: 2026-09-07
- Parent WorkPlan: ../observation-ledger/implementation.plan.md
- Related WorkPlans: ../observation-ledger/milestones/target-authority.plan.md
- Canonical inputs: docs/design/semantic_ingestion_architecture.md; current atomic recovery owner and provider composition tests
- Expected outputs: isolated causal signature, minimal correction and family regression evidence

## Objective And Completion Contract

Restore ordinary configured provider normalization and JSONL recovery tests without
weakening index validation. Complete only after reproducer, sibling lost-ACK and
frozen-source cases pass, current codecs remain compatible, applicable checks and
independent review are recorded. No parent M5 closure follows from this repair.

## Scope And Invariants

Investigate five failures in full provider/target check (5 failed,89 passed,
325.88s). All reach source_alignment_authority_unavailable; direct probe reports
index_corrupt. Keep source/candidate/commit, legacy serialization and graph
separation intact. Bootstrap source writer is disjoint; root alone owns this
investigation and any integration/atomic fixes. No production keys or CI claims.
Baseline HEAD191826cd3afb38bf605a337a71d576063b3bae5e plus authorized dirty tree;
no claim these failures predate current changes. Full run began before final
authorization-only correction; current targeted activation four cases pass19.79s.

## Hypotheses And Experiments

1. Recovery control/claim digest reconstruction differs after optional activation
   binding serialization. Predict typed constructor digest mismatch inside probe.
2. Governed atomic publication rejects a valid recovery index transition. Predict
   writer authorization or record policy exception at conditional publication.
3. Recovery index is malformed independently of publication. Predict parse/key
   failure before ready-control construction.

Trace only exceptions in probe_bootstrap_v3_recovery for one deterministic failing
provider test; no persisted fixture or validator mutation. Record exact failing
boundary before choosing a correction. Existing tests are regression authority,
not evidence of whether the failure was preexisting.

## Identity And Evidence

New names describe recovery validation only; no new persisted schema or coordinate
is authorized. Root owns test commands and retained trace, then updates parent
known-failure evidence. Expected failure: index_corrupt before normalization;
expected success: ordinary provider reaches source-only graph terminal and reload.

## Next Action

Return to ../observation-ledger/milestones/target-authority.plan.md for installed deployment and release preparation.


## Causal Result And Correction

The trace captured BootstrapNormalizationReadyControlRecordV3 validation failure
before index publication. A standalone legacy binding produced different
contract digests as a model (fadc42f7e7e3e100e0aff07c4f656b9388711abe41672b22cec0e8a71ba7a587)
and its serialized map (df61fcd9dbcb304f30bf5c578b8b9b82465eff2a152f285ca5c67d3177322cb1).
This confirms hypothesis1 and excludes a writer-authorization failure as the
first cause. Canonical lowering enumerated new activation_digest=None, while
legacy serializers omitted it. Producer and validation preimages diverged.

Terra bootstrap_writer took a separate exclusive two-file repair assignment after
freezing bootstrap work. It added existing canonical-field hooks to admission and
commit binding, excluding only None, plus direct/nested legacy/activated tests.
Root owns tests/artifacts and corrected a tuple override annotation to SupportsIndex
without runtime behavior changes. Generic canonical encoder remains unchanged.
Eleven contract cases pass5.42s; all five previously failed provider cases pass
148.47s. Current candidate.json pins source/test/producer dependencies; final16case
run binds proof to final bytes. Source publication/58vectors and identity checks
were refreshed and pass. No final broad CI or parent closure is claimed.

Bounded correctness review initially requested exact hashes (confirmed governance
correction), then the producer dependency hash (added without source change).
Final review awaits the running final-regressions.log. These evidence requests
require no user decision and do not change product semantics.


## Completion

Exact frozen16case suite passed145.85s and bounded correctness reviewer approved.
Test reviewer identified an optional-null sibling gap; root added two cases with
previous_admission_digest=None, preserving that field while activation alone may
be omitted. Full13contractcase delta passed5.24s; reviewer approved the finite
test-only correction without unnecessary public rerun. All production hashes
remain identical to the approved parent candidate. CTV/lifecycle/structural exact
source commands pass. closure.json records bounded completion, no remaining
validated P1/P2 or changes_required findings, and explicit parent/CI limitations.
