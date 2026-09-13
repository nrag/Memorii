# Acceptance Authority Temporal And Byte-Entry Completion

Work type: design. Status: blocked at bounded correction limit. Coordinator: root. Created:2026-09-08.
Parent: ../engineering-closure/implementation.plan.md.
Related: ../acceptance-authority/design.plan.md (exhausted operation, preserved).
Baseline: d17466d5 on semantic_ingestion_m5, clean at start.
User authorizes the five-step consolidated closure campaign and engineering
design corrections; real production key provisioning/signature issuance remain
deferred. This successor is explicit new work, not another hidden revision of
the exhausted predecessor.

## Objective And Completion Contract

Resolve the three remaining rejection families in ../acceptance-authority/review.md:
issue-time/key-event chronology, bounded public byte-entry verification, and
closed signed artifact shapes. Produce an implementation-ready amendment with
executable boundary proof, authority/promotion matrix and all three independent
reviews. No authority contract may be promoted with required findings open.
Parent R14 remains partial until evaluator/CLI and required evaluation are done.

## Scope And Sources

AGENTS.md precedence applies: memorii_spec, storage_details, event_model,
IMPLEMENTATION_RULES, semantic_ingestion_architecture. Read the predecessor
proposal/model/review, independent acceptance numeric owner and current release
validation consumers. Preserve immutable lifecycle records, canonical map ordering,
separate issuance/evaluation authorization, historical rotation and compromise.
Do not choose external thresholds, keys, datasets or acceptance outcomes.

## Ownership, Identity And Change Impact

One Terra worker owns only this directory's proposal, feasibility code/tests,
ledgers and this packet. Root owns commands, freeze, review reconciliation and
canonical promotion. No edits to predecessor, production, registry or canonical
design before approval. Behavioral proposed identities must be mapped in the
proposal; planning coordinates remain documentation metadata only. Downstream
chain: canonical SIA -> typed schemas/acceptance verifier -> release configuration
and held context -> evaluator/CLI -> vectors/publication/pins -> CI artifacts.

## Validation And Failure Matrix

Specify supported key-event ordering/ties, issue/evaluation cutoffs, static
validity endpoints, rotation, compromise, receipt ordering, missing/reordered
history, malformed/duplicate/extra fields, exact types and byte/depth/count/string
ceilings at the actual public byte entry. Include accepted boundaries and
trusted re-signing mutations. Prove the chronological decision using independent
expected results; same-implementation repeat is not independence.

Root runs .venv/bin/python -W error -m pytest on this directory's proof, then
Ruff/type/identity checks appropriate to the candidate. Local Python3.12 evidence
does not grant CI or operational acceptance. Freeze all reviewed files by hash.

## Progress, Decisions And Limits

2026-09-08: successor authorized and created. No implementation or approval yet.
2026-09-08: drafted `proposal.md` and bounded nonproduction public-entry proof
(`authority_successor_feasibility.py` plus focused tests). The amendment closes
the planned contract surface for DREV-001 chronology, public byte entry and
closed modeled shapes together: protected current status supplies complete raw
history; issue and evaluation time are distinct; release/key/receipt/checkpoint
shapes are exact; the production revocation acknowledgement is ordered before
replacement activation. The proposed production-entrypoint binding ledger names
the future normal evaluator/CLI -> canonical verifier -> issuer chain and marks
it explicitly unimplemented. No canonical, production or predecessor file was
changed; parent R14 remains partial.
Budget: one coherent draft and one consolidated conformance correction; an
indeterminate external semantic choice is an explicit blocker, never fabricated.
Read-only reviews may overlap independent work; exactly one writer owns these
artifacts. Root retains every command to terminal outcome.

## Next Action

Reconstruct the issuance-prefix binding in a separately scoped design operation
before any acceptance-authority promotion. Preserve this rejected candidate.

## Delta Review Disposition

Candidate 2bcfcb74d6b7ef15ab64ece6757de6780a976ae4e99726678383e80c44502d95:
56 feasibility tests passed in 0.45 seconds; model Ruff and Pyright passed.
Correctness finding AA-S-DREV-003 is confirmed: `issued_at` alone cannot select
which equal-time key events existed at issuance. The release-bound issuance
snapshot must commit an exact key-history head/sequence. A later activation at
the same effective time can otherwise retroactively authorize issuance.
Classification: Not applicable / changes_required / security-lifecycle contract.
This is a design determinacy failure, not a demonstrated production defect.
The bounded draft/correction budget is exhausted. No canonical promotion or
implementation approval is granted; unaffected paging work continues. Real
signing keys do not resolve this missing contract.

## Root Verification Before Review

Root corrected readiness omissions with the sole worker before review: scanner
ceilings precede general decode, complete key history validates separately from
issue/evaluation cutoffs, unused fields are closed, and the protected adapter
executes the preserved lifecycle verifier before deriving linked result bytes.
Initial test failures were invalid negative fixtures or incoherent substituted
checkpoint/head fixtures, corrected without weakening validation. Root formatted
the model/tests and ran the public-entry proof:25 passed0.20s, directory Ruff
passed, model Pyright0 errors/warnings. No production or canonical acceptance
contract promoted. The worker is finished and the candidate is frozen for
independent review; new observed design gaps must be reconciled before editing.
